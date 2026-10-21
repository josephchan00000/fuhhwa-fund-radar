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


def fetch_today_all(rwd_fallback: bool = True, **kw) -> dict[str, dict]:
    """回傳 {code: {date,name,close,change,volume}}，與 twse.fetch_today_all 同格式。

    上櫃每日收盤含 Close/Change/TradingShares；date 為 ISO。取不到單欄即 None。

    **雙端點（2026-08-05 踩坑）**：openapi `tpex_mainboard_daily_close_quotes` 當日整輪
    GET 失敗（同站 basic 端點正常），全部上櫃持股的當日漲跌／貢獻整片變 —。
    openapi 掛掉時自動改走官方 rwd `dailyQuotes`（同資料、不同管線），並把診斷印進
    CI 日誌（本容器 proxy 擋 tpex，日誌是唯一除錯管道）。
    rwd_fallback=False＝只要 openapi（arm/dayquotes 自己會抓指定日期版，不需這層備援）。
    """
    try:
        rows = get_json(ALL_URL, cache_ttl=1800, **kw)
        out = _from_openapi(rows)
        if out:
            return out
        print(f"  · tpex openapi 每日收盤 0 列（型別 {type(rows).__name__}）"
              + ("→ 改試 rwd dailyQuotes" if rwd_fallback else ""))
    except Exception as e:                                # noqa: BLE001 —— 換備援端點
        print(f"  · tpex openapi 每日收盤失敗（{type(e).__name__}: {str(e)[:90]}）"
              + ("→ 改試 rwd dailyQuotes" if rwd_fallback else ""))
    return _from_rwd() if rwd_fallback else {}


def _from_openapi(rows) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows or []:
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


# 官方 rwd 上櫃日收盤行情（與 openapi 同資料、不同管線；type=EW＝不含權證等）。
# 列格式＝[代號, 名稱, 收盤, 漲跌, 開盤, 最高, 最低, 均價, 成交股數, …]。
RWD_URL = ("https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
           "?date={d}&type=EW&response=json")


def _from_rwd() -> dict[str, dict]:
    """rwd dailyQuotes 備援：日期參數民國／西元都試；盤後才有當日 → 回退最多 4 個平日。
    解析 0 列時把回應鍵名與首列印進日誌（同 stockmeta 慣例，一輪收斂）。"""
    from datetime import timedelta
    from .. import clock
    from ..lab.market import tpex_date_mismatch
    d = clock.today_tw()                                  # 容器/CI 多為 UTC，台北清晨會差一天
    tried = 0
    while tried < 5:
        if d.weekday() < 5:
            tried += 1
            for ds in (f"{d.year - 1911}/{d.month:02d}/{d.day:02d}",
                       f"{d.year}/{d.month:02d}/{d.day:02d}"):
                try:
                    doc = get_json(RWD_URL.format(d=ds), cache_ttl=1800)
                except Exception as e:                    # noqa: BLE001
                    print(f"  · tpex rwd {ds} ✗ {type(e).__name__}: {str(e)[:70]}")
                    continue
                # 回應自帶資料日≠請求日（尚未公布或休市時回最近交易日）→ 不可貼上請求日的標籤，
                # 往前一天找（2026-10-21：舊碼照收，會把前一天的漲跌標成今天）
                bad = tpex_date_mismatch(doc, d.isoformat())
                if bad:
                    print(f"  · tpex rwd {ds} {bad[7:]} → 往前一天")
                    break
                rows = _rwd_rows(doc)
                if rows:
                    iso = d.isoformat()
                    out = {}
                    for row in rows:
                        code = str(row[0]).strip()
                        # 排除權證/牛熊證（6 碼純數字）；保留 4 碼個股與帶字尾的 ETF/債（00998A/00679B）
                        if not code[:1].isdigit() or (len(code) >= 6 and code.isdigit()):
                            continue
                        out[code] = {"date": iso, "name": str(row[1]).strip(),
                                     "close": _num(row[2]), "change": _num(row[3]),
                                     "volume": int((_num(row[8]) or 0) if len(row) > 8 else 0)}
                    if out:
                        print(f"  · tpex rwd dailyQuotes ✓ {len(out)} 檔（{ds}）")
                        return out
                if isinstance(doc, dict):                 # 有回應但解析 0 列 → 印結構供收斂
                    print(f"  · tpex rwd {ds} 解析 0 列：keys={list(doc)[:8]}")
        d -= timedelta(days=1)
    print("  · tpex rwd dailyQuotes 亦不可得（回退 4 平日皆空）")
    return {}


def _rwd_rows(doc) -> list:
    """rwd 回應歷有 tables 包裝與否兩版（同 TWSE MI_MARGN 慣例）——都收。"""
    if not isinstance(doc, dict):
        return []
    for t in (doc.get("tables") or [doc]):
        rows = (t or {}).get("data") or (t or {}).get("aaData") or []
        if rows:
            return rows
    return []


def latest_trade_date(all_today: dict[str, dict] | None = None) -> str:
    all_today = all_today or fetch_today_all()
    return max(v["date"] for v in all_today.values())


BASIC_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"


def fetch_basic_rows() -> list[dict]:
    """上櫃公司基本資料（含產業別）原始列；介面對齊 twse.fetch_basic_rows。"""
    rows = get_json(BASIC_URL, cache_ttl=86400)
    return rows if isinstance(rows, list) else []
