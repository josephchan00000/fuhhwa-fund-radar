"""ETF 每日持股（申購買回清單 PCF／持股明細）抓取層。

主動式 ETF 依規定每日揭露完整持股，但**沒有跨投信的統一官方端點**（2026-07-29 查證：
證交所／櫃買／政府開放平台皆無彙總 API，各投信自行在官網揭露）→ 只能一家一個 adapter。

因此本模組刻意做成「候選來源清單 + 通用解析 + 探針」三件套：

  · SOURCES  ：每檔 ETF 一組**候選** URL（依投信官網型態推導）。同一檔可列多個候選，
               依序試、第一個解析出持股就用。
  · 通用解析 ：JSON（任意巢狀陣列找持股欄）／HTML 表格／xlsx（重用 fhtrust._parse_xlsx）。
  · probe()  ：印出每個候選的 HTTP 狀態、content-type、內容前段。

**為什麼要探針**：本 Claude 容器 proxy 擋掉所有投信站（CONNECT 403），無法在此驗證任何
URL；正式區 CI 才連得上。盲寫十家 scraper 只會十家一起錯，改成「候選＋探針」後，
一次 CI 就能把實際回應收進日誌，再據以收斂各家 adapter——與 cnyesfund.py 當初
歷經 6 輪 CI 收斂的做法相同（見 CLAUDE.md）。

抓不到的檔：安靜降級（該 ETF 就沒有展開明細），絕不影響其餘欄位與其他 ETF。
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable

from ..fhtrust import _parse_xlsx

_TIMEOUT = 20
_UA = {"User-Agent": "Mozilla/5.0 (fuhhwa-fund-radar; etf-holdings)",
       "Accept": "application/json,text/html,*/*"}

# 股票代號：台股 4 碼數字（含 4 碼＋1 英文的特別股／KY 等）
_SID = re.compile(r"^[0-9]{4}[A-Z]?$")


class Probe:
    """單一候選來源的抓取結果＋診斷（CI 日誌用）。"""

    def __init__(self, name: str, url: str):
        self.name, self.url = name, url
        self.status: int | None = None
        self.ctype: str = ""
        self.nbytes: int = 0
        self.head: str = ""
        self.error: str = ""
        self.n_holdings: int = 0

    def line(self) -> str:
        if self.error:
            return f"{self.name} ✗ {self.error}｜{self.url}"
        return (f"{self.name} HTTP {self.status} {self.ctype} {self.nbytes}B "
                f"→ 持股 {self.n_holdings} 檔｜{self.url}"
                + (f"｜首段：{self.head}" if not self.n_holdings else ""))


def _get(url: str, probe: Probe) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            raw = r.read()
            probe.status = getattr(r, "status", None)
            probe.ctype = (r.headers.get("Content-Type") or "").split(";")[0]
        probe.nbytes = len(raw)
        probe.head = re.sub(r"\s+", " ", raw[:400].decode("utf-8", "replace"))[:220]
        return raw
    except Exception as e:                              # noqa: BLE001 —— 每來源獨立降級
        probe.error = f"{type(e).__name__}: {str(e)[:120]}"
        return None


# ── 通用解析（三種版式；各自回 [{stock_id,name,shares,weight}]） ──────────

# 欄名關鍵字：比對方式為「候選字串是否為正規化欄名的子字串」，故短字串（代號／名稱）
# 必須列進來——各家 PCF 表頭常只寫「代號／名稱／股數／比重」（2026-07-29 測試補強）。
_KEY_ID = ("stockid", "stockno", "stockcode", "code", "id",
           "代號", "代碼", "商品代號", "股票代號", "證券代號")
_KEY_NM = ("stockname", "name", "名稱", "商品名稱", "股票名稱", "證券名稱")
_KEY_SH = ("shares", "share", "qty", "quantity", "amount", "股數", "數量", "庫存股數")
_KEY_WT = ("weight", "ratio", "percent", "pct", "權重", "比重", "比例")


def _norm_key(k: str) -> str:
    return re.sub(r"[\s_\-()（）%％]", "", str(k)).lower()


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return None


def _row_from_mapping(d: dict) -> dict | None:
    """任意 dict → 持股列（靠欄名關鍵字比對，容忍各家命名差異）。"""
    keys = {_norm_key(k): k for k in d}

    def pick(cands):
        for c in cands:
            for nk, orig in keys.items():
                if c in nk:
                    return d.get(orig)
        return None

    sid = str(pick(_KEY_ID) or "").strip().upper()
    if not _SID.match(sid):
        return None
    return {"stock_id": sid, "name": str(pick(_KEY_NM) or "").strip(),
            "shares": (lambda v: int(v) if v is not None else None)(_num(pick(_KEY_SH))),
            "weight": _num(pick(_KEY_WT))}


def parse_json(raw: bytes) -> list[dict]:
    """任意巢狀 JSON：遞迴找出「看起來是持股清單」的 dict 陣列，取最長的一組。"""
    try:
        doc = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return []
    best: list[dict] = []

    def walk(node):
        nonlocal best
        if isinstance(node, list):
            rows = [r for r in (_row_from_mapping(x) for x in node if isinstance(x, dict)) if r]
            if len(rows) > len(best):
                best = rows
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)

    walk(doc)
    return best


_TAG = re.compile(r"<[^>]+>")
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)


def _cells(html: str) -> list[list[str]]:
    out = []
    for tr in _TR.findall(html):
        cells = [_TAG.sub("", c).replace("&nbsp;", " ").strip() for c in _TD.findall(tr)]
        if cells:
            out.append(cells)
    return out


def _rows_from_table(rows: list[list[str]]) -> list[dict]:
    """表格列（含表頭）→ 持股列。表頭認得出欄位就用表頭，否則靠「代號欄＋數字欄」推斷。"""
    if not rows:
        return []
    header = next((r for r in rows[:5] if any(_norm_key(c) and any(
        k in _norm_key(c) for k in _KEY_ID) for c in r)), None)
    out: list[dict] = []
    if header:
        for r in rows:
            if r is header or len(r) != len(header):
                continue
            got = _row_from_mapping(dict(zip(header, r)))
            if got:
                out.append(got)
        if out:
            return out
    # 無可辨識表頭：找出代號欄位置，名稱取其右、股數取最大整數欄、權重取 0–100 的小數欄
    for r in rows:
        idx = next((i for i, c in enumerate(r) if _SID.match(c.strip().upper())), None)
        if idx is None:
            continue
        # 只看代號欄「右側」的數字：左側常是序號欄，1、2、3… 會被誤判成權重（實測踩到）
        nums = [(i, _num(c)) for i, c in enumerate(r) if i > idx and _num(c) is not None]
        shares = max((v for _i, v in nums if v is not None and v >= 1000), default=None)
        weight = next((v for _i, v in nums if v is not None and 0 < v <= 100), None)
        out.append({"stock_id": r[idx].strip().upper(),
                    "name": (r[idx + 1].strip() if len(r) > idx + 1 else ""),
                    "shares": int(shares) if shares is not None else None,
                    "weight": weight})
    return out


def parse_html(raw: bytes) -> list[dict]:
    for enc in ("utf-8", "big5"):
        try:
            return _rows_from_table(_cells(raw.decode(enc)))
        except UnicodeDecodeError:
            continue
    return []


def parse_xlsx(raw: bytes) -> list[dict]:
    try:
        return _rows_from_table(_parse_xlsx(raw))
    except Exception:
        return []


def parse_auto(raw: bytes, probe: Probe) -> list[dict]:
    """依 content-type／位元組特徵選解析器（各家常改格式 → 全部試一遍取最長）。"""
    cands: list[Callable[[bytes], list[dict]]] = []
    if raw[:2] == b"PK":                                  # xlsx/zip 魔數
        cands = [parse_xlsx]
    elif "json" in probe.ctype or raw.lstrip()[:1] in (b"{", b"["):
        cands = [parse_json, parse_html]
    else:
        cands = [parse_html, parse_json]
    best: list[dict] = []
    for fn in cands:
        got = fn(raw)
        if len(got) > len(best):
            best = got
    return best


# ── 候選來源清單（依投信官網型態推導；由 CI 探針逐檔證實後收斂） ─────────
#
# 已證實可用的網址型態：
#   · 元大 www.yuantaetfs.com/tradeInfo/pcf/{code}         （2026-07-29 WebSearch 逐檔命中）
#   · 復華 www.fhtrust.com.tw/api/assetsExcel/{id}/{ymd}   （既有基金持股同一站，ETF 代碼待證）
# 其餘為同型態推導的候選，探針證實前一律當「未知」——抓不到就沒有展開明細，不影響其他欄位。
def _cands(code: str, issuer: str) -> list[tuple[str, str]]:
    """回 [(來源名, URL)]，依序嘗試。"""
    out: list[tuple[str, str]] = []
    if issuer == "元大":
        out.append(("元大PCF", f"https://www.yuantaetfs.com/tradeInfo/pcf/{code}"))
        out.append(("元大PCF-api", f"https://www.yuantaetfs.com/api/pcf/{code}"))
    elif issuer == "復華":
        out.append(("復華PCF", f"https://www.fhtrust.com.tw/ETF/PCF/{code}"))
        out.append(("復華ETF頁", f"https://www.fhtrust.com.tw/etf/{code}/holdings"))
    elif issuer == "國泰":
        out.append(("國泰PCF", f"https://www.cathaysite.com.tw/ETF/purchase?code={code}"))
    elif issuer == "富邦":
        out.append(("富邦PCF", f"https://websys.fsit.com.tw/FubonETF/Trade/Pcf.aspx?fundid={code}"))
    elif issuer == "群益":
        out.append(("群益PCF", f"https://www.capitalfund.com.tw/ETF/PCF/{code}"))
    elif issuer == "統一":
        out.append(("統一PCF", f"https://www.ezmoney.com.tw/ETF/PCF/{code}"))
    elif issuer == "野村":
        out.append(("野村PCF", f"https://www.nomurafunds.com.tw/ETF/PCF/{code}"))
    elif issuer == "安聯":
        out.append(("安聯PCF", f"https://etf.allianzgi.com.tw/api/pcf/{code}"))
    elif issuer == "中信":
        out.append(("中信PCF", f"https://www.ctbcinvestments.com.tw/ETF/PCF/{code}"))
    elif issuer == "台新":
        out.append(("台新PCF", f"https://www.tsit.com.tw/ETF/PCF/{code}"))
    elif issuer == "第一金":
        out.append(("第一金PCF", f"https://www.fsitc.com.tw/ETF/PCF/{code}"))
    elif issuer == "凱基":
        out.append(("凱基PCF", f"https://www.kgifsitc.com.tw/ETF/PCF/{code}"))
    # 全檔通用候選：證交所官方 ETF 資訊頁（若含成分股即為最佳來源——跨投信統一、Tier A）
    out.append(("證交所ETFortune", f"https://www.twse.com.tw/zh/ETFortune/etfInfo/{code}"))
    return out


def fetch_one(code: str, issuer: str) -> tuple[list[dict], str, list[Probe]]:
    """單檔 ETF：依序試候選來源，回 (持股列, 來源名, 全部探針)。"""
    probes: list[Probe] = []
    for name, url in _cands(code, issuer):
        p = Probe(name, url)
        probes.append(p)
        raw = _get(url, p)
        if not raw:
            continue
        rows = parse_auto(raw, p)
        p.n_holdings = len(rows)
        if len(rows) >= 5:                        # ≥5 檔才算有效持股清單（濾掉零星誤判）
            return _normalize(rows), name, probes
    return [], "", probes


def _normalize(rows: list[dict]) -> list[dict]:
    """同代號合併、權重補算（僅有股數時不硬算價值權重——缺價格資料，寧缺勿錯）。"""
    merged: dict[str, dict] = {}
    for r in rows:
        sid = r["stock_id"]
        cur = merged.setdefault(sid, {"stock_id": sid, "name": r.get("name") or "",
                                      "shares": None, "weight": None})
        for k in ("shares", "weight"):
            if r.get(k) is not None:
                cur[k] = (cur[k] or 0) + r[k] if cur[k] is not None else r[k]
        if r.get("name") and not cur["name"]:
            cur["name"] = r["name"]
    return sorted(merged.values(), key=lambda h: -(h.get("weight") or 0))
