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

import re

from ..http import get_bytes, get_json

API = "https://www.fhtrust.com.tw/api/fund?fundID={fid}"
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


def fetch_meta(fund_id: str | int) -> dict:
    """基金基本資料 / 淨值 / 多期報酬 / 經理人 / 月報 / 投資策略敘述。"""
    d = get_json(API.format(fid=fund_id), cache_ttl=6 * 3600)
    res = (d or {}).get("result") or []
    if not res:
        raise NoData(f"fundID={fund_id} 無 /api/fund 資料")
    o = res[0]

    managers = []
    for key in ("manager", "manager01"):
        for m in (o.get(key) or []):
            nm = (m or {}).get("name")
            if nm and nm not in managers:
                managers.append(nm)

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


# 組合型（fof，如台灣智能79）詳情頁無標準「十大持有標的」表；其標的多為基金／ETF，
# 揭露於不同標題下。以下為候選標題，抓不到標準表時依序嘗試（結構須以實際頁面查證）。
_FOF_HEADINGS = ["前十大投資標的", "十大投資標的", "基金投資明細", "投資標的明細",
                 "基金持股明細", "投資標的"]


def _extract_holdings(rows: list[list[str]]) -> list[dict]:
    """把去標籤的表格列轉為持股 dict。相容兩種結構：
      · 個股表：[產業, 名稱, …, 比例]（≥3 欄）→ {sector, name, weight}
      · fof 標的表：[名稱, …, 比例]（2 欄，無產業）→ {sector: None, name, weight}
    """
    out = []
    for r in rows:
        if _pct(r[-1]) is None:
            continue
        if len(r) >= 3:
            out.append({"sector": r[0], "name": r[1], "weight": _pct(r[-1])})
        elif len(r) == 2:
            out.append({"sector": None, "name": r[0], "weight": _pct(r[-1])})
    return out


def fetch_holdings(fund_id: str | int) -> dict:
    """月底十大持有標的（含每檔所屬產業）＋ 國家配置 ＋ 產業配置 ＋ 資料日期。

    組合型（fof）無標準十大持股表 → 退而嘗試 _FOF_HEADINGS 下的基金／ETF 標的表，
    並以 holdings_kind 標記（"stock"／"fund"），供儀表板呈現差異（D4）。"""
    html = get_bytes(PAGE.format(fid=fund_id), cache_ttl=6 * 3600).decode("utf-8", "replace")

    holdings = _extract_holdings(_rows_of_table_after(html, "十大持有標的"))
    holdings_kind = "stock" if holdings else None
    holdings_heading = "十大持有標的" if holdings else None
    if not holdings:                                   # fof 退路：改抓基金／ETF 標的表
        for hd in _FOF_HEADINGS:
            h2 = _extract_holdings(_rows_of_table_after(html, hd))
            if h2:
                holdings, holdings_kind, holdings_heading = h2, "fund", hd
                break

    # 資料日期與日期之間夾了 <span>，且全頁多處出現 → 取「持股表之前最近一個」當持股基準日
    anchor = holdings_heading or "十大持有標的"
    dates = [(mm.start(), mm.group(1)) for mm in
             re.finditer(r"資料日期：(?:\s|<[^>]+>)*(\d{4}/\d{2}/\d{2})", html)]
    hpos = html.find(anchor)
    before = [d for p, d in dates if hpos < 0 or p < hpos]
    as_of = (before[-1] if before else (dates[0][1] if dates else None))

    return {
        "as_of": as_of,
        "top_holdings": holdings,
        "holdings_kind": holdings_kind,          # "stock" | "fund"(fof) | None
        "holdings_heading": holdings_heading,
        "country_alloc": _svg_pairs(html, "國家配置", "產業配置"),
        "sector_alloc": _svg_pairs(html, "產業配置", "十大持有標的"),
    }


def fetch_fund(fund_id: str | int) -> dict:
    """整合一檔基金的『持股介紹』快照（meta + 持股 + 配置）。"""
    out = fetch_meta(fund_id)
    try:
        out.update(fetch_holdings(fund_id))
    except Exception as e:  # 持股頁暫時抓不到 → 保留 meta，持股留空、不崩
        out.update({"as_of": None, "top_holdings": [], "holdings_kind": None,
                    "holdings_heading": None, "country_alloc": [],
                    "sector_alloc": [], "holdings_error": f"{type(e).__name__}: {e}"})
    return out
