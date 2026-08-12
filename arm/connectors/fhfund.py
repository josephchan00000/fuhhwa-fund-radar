"""復華共同基金（非 ETF）持股介紹連接器 —— 追蹤版本的權威資料源。

與 ETF 的 `/api/assetsExcel`（每日、逐股張數）不同，共同基金在官網揭露的是
**月底前十大持股**＋國家/產業配置＋淨值/報酬/月報，沒有逐日持股張數（故追蹤版本
不做「每天持股變化」）。本連接器把兩個公開端點合成一份「持股介紹」快照：

  1. Meta / NAV / 報酬 / 月報：JSON  GET /api/fund?fundID={id}
  2. 十大持有標的 + 國家配置 + 產業配置 + 資料日期：SSR HTML /funds/funds_detail/{id}

純標準庫解析（正則），比照 arm/connectors/fhtrust.py 的作法，不裝 bs4/openpyxl。
唯讀、可重跑；某端點缺就該欄回 None/空，不整批崩。
"""
from __future__ import annotations

import json
import re

from ..http import get_bytes, get_json

API = "https://www.fhtrust.com.tw/api/fund?fundID={fid}"
API_NAV = "https://www.fhtrust.com.tw/api/fundNav?fundID={fid}"
PAGE = "https://www.fhtrust.com.tw/funds/funds_detail/{fid}"


class NoData(Exception):
    """該基金無揭露資料（代號錯誤 / 尚未公告）。"""


def _text(html: str) -> str:
    """去標籤 + 收斂空白（含零寬字元 ​）。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("​", "").strip()


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    m = re.search(r"-?\d+\.?\d*", str(s).replace(",", ""))
    return float(m.group()) if m else None


def _pct(s: str | None) -> float | None:
    """'4.58%' / '60.76 %' → 4.58；取第一個數字。"""
    if not s:
        return None
    m = re.search(r"-?\d+\.?\d*", s)
    return float(m.group()) if m else None


def _parse_first_json(text: str) -> object:
    """容錯解析 /api/fundNav 的髒回應：取字串中第一份完整 JSON 文件。

    2026-07-21 CI 實測該端點大多回「有效 JSON＋尾端黏多餘資料」（json.loads 報
    Extra data），偶爾開頭還有垃圾（報 Expecting value char 0）——去 BOM、必要時
    從第一個 '{' 起 raw_decode，兩者都救得回來。"""
    text = text.lstrip("\ufeff \t\r\n")
    dec = json.JSONDecoder()
    for start in (0, text.find("{")):
        if start < 0:
            continue
        try:
            obj, _end = dec.raw_decode(text, start)
            return obj
        except json.JSONDecodeError:
            continue
    raise NoData("回應非 JSON（開頭與首個 '{' 起都解不出文件）")


def fetch_nav_history(fund_id: str | int, days: int = 90) -> dict[str, float]:
    """官方每日淨值史 → {"YYYY/MM/DD": nav}，預設只取最近 days 個日曆日。

    /api/fundNav 回自成立日起的完整每日序列（2026-07-20 CI probe 發現；101 全史約
    620KB），供 arm/fundnav 回填「新加入追蹤清單」基金的短史——沒有它，1週/1月
    報酬要等 CI 日日累積一個月才會出現。回應髒（見 _parse_first_json）→ 不快取
    （避免垃圾回應毒化 TTL）、解析失敗重抓一次。"""
    from datetime import datetime, timedelta

    d = None
    for _attempt in range(2):
        raw = get_bytes(API_NAV.format(fid=fund_id), use_cache=False, retries=2)
        try:
            d = _parse_first_json(raw.decode("utf-8", "ignore"))
            break
        except NoData:
            continue
    if d is None:
        raise NoData(f"fundID={fund_id} /api/fundNav 回應兩次都解析不出 JSON")
    res = (d or {}).get("result") or []
    if not res:
        raise NoData(f"fundID={fund_id} 無 /api/fundNav 資料")
    out: dict[str, float] = {}
    for o in res:
        dt, nav = (o or {}).get("navDate"), _num((o or {}).get("pnav"))
        if dt and nav:
            out[dt] = nav
    if days and out:
        try:
            cutoff = (datetime.strptime(max(out), "%Y/%m/%d")
                      - timedelta(days=days)).strftime("%Y/%m/%d")
            out = {k: v for k, v in out.items() if k >= cutoff}
        except ValueError:
            pass  # 日期格式異常時不截斷、整段保留
    return out


def fetch_meta(fund_id: str | int) -> dict:
    """基金基本資料 / 淨值 / 多期報酬 / 經理人 / 月報 / 投資策略敘述。"""
    d = get_json(API.format(fid=fund_id), cache_ttl=6 * 3600)
    res = (d or {}).get("result") or []
    if not res:
        raise NoData(f"fundID={fund_id} 無 /api/fund 資料")
    o = res[0]

    # manager＝基金經理人、manager01＝協管經理人（2026-07-22 經 MoneyDJ 經理人資料交叉驗證）
    managers, co_managers = [], []
    for key, acc in (("manager", managers), ("manager01", co_managers)):
        for m in (o.get(key) or []):
            nm = (m or {}).get("name")
            if nm and nm not in managers and nm not in co_managers:
                acc.append(nm)

    monthly_report = None
    for p in (o.get("pdf") or []):
        if (p or {}).get("name") == "基金月報" and p.get("url"):
            monthly_report = "https://www.fhtrust.com.tw" + p["url"]
            break

    return {
        "fund_id": str(fund_id),
        "name": o.get("twNameFull"),
        "short_name": o.get("twName"),
        "en_name": o.get("enName"),
        "category": o.get("ec020"),          # 如「跨國投資股票型」
        "region": o.get("ec024"),            # 主要投資區域，如「美國」
        "asset_kind": o.get("ec026"),        # 「股票型」/「平衡型」
        "currency": o.get("ec006"),
        "inception": o.get("ec005"),
        "risk_level": o.get("ec009"),        # RRx
        "mgmt_fee": o.get("ec012"),
        "size_twd": _num(o.get("fundSize_TWD")),
        "nav": _num(o.get("pnav")),
        "nav_date": o.get("navDate"),
        "nav_change": _num(o.get("change")),
        "nav_change_pct": o.get("changeRange"),
        "returns": {k: o.get(v) for k, v in {
            "ytd": "roiY2D", "3m": "roi3m", "6m": "roi6m", "1y": "roi1y",
            "2y": "roi2y", "3y": "roi3y", "since": "roiLaunch"}.items() if o.get(v)},
        "managers": managers,
        "co_managers": co_managers,
        "strategy": _text(o.get("contents") or "") or None,
        "monthly_report": monthly_report,
        "dist_date": o.get("ddate"),
        "dist_rate": o.get("disRate"),
    }


def _rows_of_table_after(html: str, heading: str) -> list[list[str]]:
    """回傳 heading 之後第一張 fundTable 的資料列（每列為去標籤 td 文字）。"""
    i = html.find(heading)
    if i < 0:
        return []
    m = re.search(r'<table[^>]*class="[^"]*fundTable[^"]*"[^>]*>(.*?)</table>',
                  html[i:], re.S)
    if not m:
        return []
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        tds = [_text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if tds:
            rows.append(tds)
    return rows


def _svg_pairs(html: str, start_heading: str, end_heading: str) -> list[dict]:
    """國家/產業配置為 server-rendered SVG：先出現一組數值 <text>，再一組類別標籤 <text>，
    兩組平行對位。回傳 [{name, weight}]（濾掉數量不對位的情形）。"""
    i = html.find(start_heading)
    j = html.find(end_heading, i + 1) if i >= 0 else -1
    if i < 0 or j < 0:
        return []
    seg = html[i:j]
    texts = [_text(t) for t in re.findall(r"<text[^>]*>(.*?)</text>", seg, re.S)]
    texts = [t for t in texts if t and t != start_heading]
    vals = [_pct(t) for t in texts if re.search(r"\d+\.?\d*\s*%", t)]
    labels = [t for t in texts if not re.search(r"\d", t)]
    n = min(len(vals), len(labels))
    return [{"name": labels[k], "weight": vals[k]} for k in range(n) if vals[k] is not None]


# 持有標的段落的候選標題，依序試、first-match 勝。一般基金＝「十大持有標的」；
# 組合型（fund-of-funds）頁面同表改列持有基金，標題措辭不同（2026-08-12 使用者
# 反映「官網明明就有」——舊版只認第一種，組合型整段落空還被誤標成官網不揭露）。
_HOLDING_HEADINGS = ("十大持有標的", "十大持有基金", "主要持有基金", "十大持有")


def fetch_holdings(fund_id: str | int) -> dict:
    """月底十大持有標的（含每檔所屬產業）＋ 國家配置 ＋ 產業配置 ＋ 資料日期。

    列形兩種都收：3 欄以上＝[產業, 名稱, …, 比例]（一般基金）；2 欄＝[名稱, 比例]
    （組合型持有基金表常無產業欄，sector 記 None）。候選標題全落空時把頁面上
    含「持有」的片段印進 CI 日誌——proxy 擋本容器、日誌是唯一除錯管道，一輪收斂。"""
    html = get_bytes(PAGE.format(fid=fund_id), cache_ttl=6 * 3600).decode("utf-8", "replace")

    holdings, matched = [], None
    for heading in _HOLDING_HEADINGS:
        rows = []
        for r in _rows_of_table_after(html, heading):
            if _pct(r[-1]) is None:
                continue
            if len(r) >= 3:
                rows.append({"sector": r[0], "name": r[1], "weight": _pct(r[-1])})
            elif len(r) == 2 and r[0]:
                rows.append({"sector": None, "name": r[0], "weight": _pct(r[-1])})
        if rows:
            holdings, matched = rows, heading
            break
    if not holdings:
        hints = [_text(seg) for seg in re.findall(r".{0,40}持有.{0,40}", html)][:6]
        if hints:
            print(f"[fhfund] {fund_id} 持有標的段落未匹配任何候選標題；"
                  f"頁面含「持有」片段：{' ｜ '.join(hints)}")

    # 資料日期與日期之間夾了 <span>，且全頁多處出現 → 取「持有標的段落之前最近一個」當持股基準日
    dates = [(mm.start(), mm.group(1)) for mm in
             re.finditer(r"資料日期：(?:\s|<[^>]+>)*(\d{4}/\d{2}/\d{2})", html)]
    hpos = html.find(matched or "十大持有標的")
    before = [d for p, d in dates if hpos < 0 or p < hpos]
    as_of = (before[-1] if before else (dates[0][1] if dates else None))

    return {
        "as_of": as_of,
        "top_holdings": holdings,
        "country_alloc": _svg_pairs(html, "國家配置", "產業配置"),
        "sector_alloc": _svg_pairs(html, "產業配置", matched or "十大持有標的"),
    }


def fetch_fund(fund_id: str | int) -> dict:
    """整合一檔基金的『持股介紹』快照（meta + 持股 + 配置）。"""
    out = fetch_meta(fund_id)
    try:
        out.update(fetch_holdings(fund_id))
    except Exception as e:  # 持股頁暫時抓不到 → 保留 meta，持股留空、不崩
        out.update({"as_of": None, "top_holdings": [], "country_alloc": [],
                    "sector_alloc": [], "holdings_error": f"{type(e).__name__}: {e}"})
    return out
