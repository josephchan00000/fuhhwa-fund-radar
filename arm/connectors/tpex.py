"""TPEx（櫃買中心）官方資料連接器 —— 上櫃 ETF 的權威價量來源。

關鍵：復華自家 00998A（主動金融股息）、00986D（主動金融債息）與多檔債券/債競品
（00679B/00772B/00773B/00937B…）皆為**上櫃**掛牌，TWSE openapi STOCK_DAY_ALL 抓不到，
價量必須走 TPEx openapi。介面刻意對齊 arm.connectors.twse.fetch_today_all，
讓 fetch_peers / firsthand 可把兩個交易所的當日價量合併使用（同一格式、同走 certifi 驗證）。

來源：tpex_mainboard_daily_close_quotes（上櫃主板每日收盤，官方、免金鑰）。
"""
from __future__ import annotations

from ..http import get_json

ALL_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"


def _roc_compact_to_iso(s: str) -> str:
    """'1150615' -> '2026-06-15'"""
    s = s.strip()
    y = int(s[:3]) + 1911
    return f"{y:04d}-{s[3:5]}-{s[5:7]}"


def _num(x) -> float | None:
    """容錯數字：去千分位、去 +/- 前後空白；'--'/空白回 None。"""
    x = str(x or "").replace(",", "").replace("+", "").strip()
    if x in ("", "--", "---"):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def fetch_today_all() -> dict[str, dict]:
    """回傳 {code: {date,name,close,change,volume}}，與 twse.fetch_today_all 同格式。

    上櫃每日收盤含 Close/Change/TradingShares；date 為 ISO。取不到單欄即 None。
    """
    rows = get_json(ALL_URL, cache_ttl=1800)
    out: dict[str, dict] = {}
    for r in rows:  # type: ignore[union-attr]
        code = (r.get("SecuritiesCompanyCode") or "").strip()
        if not code:
            continue
        out[code] = {
            "date": _roc_compact_to_iso(r["Date"]),
            "name": (r.get("CompanyName") or "").strip(),
            "close": _num(r.get("Close")),
            "change": _num(r.get("Change")),
            "volume": int(_num(r.get("TradingShares")) or 0),
        }
    return out


def latest_trade_date(all_today: dict[str, dict] | None = None) -> str:
    all_today = all_today or fetch_today_all()
    return max(v["date"] for v in all_today.values())


BASIC_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"


def fetch_basic_rows() -> list[dict]:
    """上櫃公司基本資料（含產業別）原始列；介面對齊 twse.fetch_basic_rows。"""
    rows = get_json(BASIC_URL, cache_ttl=86400)
    return rows if isinstance(rows, list) else []
