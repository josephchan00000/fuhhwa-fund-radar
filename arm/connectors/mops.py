"""公開資訊觀測站（MOPS）ETF 收益分配連接器 —— 補「當月投信預告的預計配息金額」。

etfinfo 只揭露「已實際除息」的配息，不含投信於配息月 1 日公告的『預計每單位分配金額』。
此連接器改抓 MOPS 官方 ETF 收益分配彙總（權威來源），取每檔「最近一次公告」的
除息日與每受益權單位分配金額；由上層 arm/etfwatch 判斷是否為當月預告。

MOPS 端點形狀未定且偶改版——本連接器一律防禦式解析、抓不到回 {}（上層優雅降級，
預估欄留空、不影響其他欄位）。CI（GitHub Actions，不受雲端 Claude proxy 擋）實跑驗證。

回傳格式：{code: {"ex_date": "YYYY-MM-DD", "amount": float, "announced": "YYYY-MM-DD"|None}}
"""
from __future__ import annotations

import json
import re

from ..http import get_bytes

# MOPS「ETF（受益憑證）收益分配情形」彙總——優先試 JSON API，失敗再退 HTML 表格解析。
# 端點若改版，於此集中調整；抓不到一律回空、不拋例外中斷整批。
_CANDIDATES = (
    "https://mopsov.twse.com.tw/mops/web/ajax_t51sb01",
    "https://mops.twse.com.tw/mops/web/ajax_t51sb01",
)


def _num(s) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", str(s or "").replace(",", ""))
    return float(m.group()) if m else None


def _iso(s: str) -> str | None:
    """民國/西元日期字串 → ISO；'115/07/16' 或 '2026/07/16' 或 '2026-07-16'。"""
    m = re.match(r"(\d{2,4})[/-](\d{1,2})[/-](\d{1,2})", str(s or "").strip())
    if not m:
        return None
    y = int(m.group(1))
    if y < 1911:
        y += 1911
    try:
        return f"{y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    except ValueError:
        return None


# 台股 ETF 代碼樣態：0050/0056(4 碼)、00878/00929(5 碼)、006208(6 碼)、00980A(5 碼+字母)。
_CODE_RE = re.compile(r"\b(0\d{3,5}[A-Z]?)\b")


def _row_entry(cells: list, codes: set[str] | None) -> tuple[str, dict] | None:
    """一列 → (code, {ex_date, amount})；代碼優先比對 watchlist（無誤判），
    金額只取『含小數點、0<x<100』者（避開把代碼數字當金額）。"""
    strs = [str(c).strip() for c in cells]
    code = None
    if codes:
        code = next((s for s in strs if s in codes), None)
    if not code:
        m = _CODE_RE.search(" ".join(strs))
        code = m.group(1) if m else None
    if not code:
        return None
    ex = next((_iso(s) for s in strs if _iso(s)), None)
    amt = None
    for s in strs:
        if s == code or "." not in s:
            continue
        v = _num(s)
        if v is not None and 0 < v < 100:
            amt = v
            break
    if ex and amt is not None:
        return code, {"ex_date": ex, "amount": amt, "announced": None}
    return None


def _parse_rows(text: str, codes: set[str] | None = None) -> dict[str, dict]:
    """從 MOPS 回應（JSON 或 HTML 表格）盡量解析出 {code: {ex_date, amount, announced}}。防禦式。"""
    out: dict[str, dict] = {}
    text = (text or "").strip()
    if not text:
        return out
    try:                                              # 1) JSON：{"data": [[...]]} 或 [{...}]
        obj = json.loads(text)
        rows = obj.get("data") if isinstance(obj, dict) else obj
        for r in rows or []:
            cells = list(r.values()) if isinstance(r, dict) else list(r)
            e = _row_entry(cells, codes)
            if e:
                out.setdefault(e[0], e[1])
        if out:
            return out
    except (ValueError, AttributeError):
        pass
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):   # 2) HTML 表格 fallback
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        e = _row_entry(cells, codes)
        if e:
            out.setdefault(e[0], e[1])
    return out


def etf_distributions(codes: set[str] | None = None, *, cache_ttl: int = 6 * 3600) -> dict[str, dict]:
    """全 ETF 最近一次收益分配公告 {code: {ex_date, amount, announced}}。抓不到回 {}。

    codes：追蹤清單代碼集合（有給則優先精準比對，避免誤判）。"""
    for url in _CANDIDATES:
        try:
            body = get_bytes(url, cache_ttl=cache_ttl, retries=2).decode("utf-8", "ignore")
        except Exception:
            continue
        rows = _parse_rows(body, codes)
        if rows:
            return rows
    return {}
