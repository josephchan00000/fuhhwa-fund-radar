"""TWSE 官方資料連接器 —— 績效的權威來源（收盤價 100% 官方）。

- STOCK_DAY_ALL：當日全上市收盤（取最新交易日 + 單檔當日收盤）。
- STOCK_DAY   ：單檔逐月歷史日價（多週期報酬 + Alpha 用）。
"""
from __future__ import annotations

from datetime import date

from ..http import _cache_path, get_json

ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={ymd}&stockNo={code}"


def _stat_ok(b: bytes) -> bool:
    """STOCK_DAY 回應是否為有效（stat=OK）；只有有效才值得寫快取。"""
    return b'"stat":"OK"' in b or b'"stat": "OK"' in b


def _roc_compact_to_iso(s: str) -> str:
    """'1150612' -> '2026-06-12'"""
    y = int(s[:3]) + 1911
    return f"{y:04d}-{s[3:5]}-{s[5:7]}"


def _roc_slash_to_iso(s: str) -> str:
    """'115/06/12' -> '2026-06-12'"""
    y, m, d = s.split("/")
    return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"


def _num(x: str) -> float | None:
    x = (x or "").replace(",", "").strip()
    try:
        return float(x)
    except ValueError:
        return None


def fetch_today_all(**kw) -> dict[str, dict]:
    """回傳 {code: {date,close,change,volume,name}}，date 為 ISO。"""
    rows = get_json(ALL_URL, cache_ttl=1800, **kw)
    out: dict[str, dict] = {}
    for r in rows:  # type: ignore[union-attr]
        out[r["Code"]] = {
            "date": _roc_compact_to_iso(r["Date"]),
            "name": r["Name"],
            "close": _num(r["ClosingPrice"]),
            "change": _num(r["Change"]),
            "volume": int(_num(r["TradeVolume"]) or 0),
        }
    return out


def latest_trade_date(all_today: dict[str, dict] | None = None) -> str:
    all_today = all_today or fetch_today_all()
    return max(v["date"] for v in all_today.values())


def fetch_month(code: str, year: int, month: int) -> list[tuple[str, float, int]]:
    """單月逐日 (iso_date, close, volume)；無資料回空。

    只快取 stat=OK 回應；若讀到的是先前被毒化的非 OK 舊快取，清掉重抓一次（self-heal），
    避免 TWSE 偶發「查無資料」卡住 6 小時 TTL（曾導致部分新檔近月誤判成無歷史）。
    """
    url = DAY_URL.format(ymd=f"{year:04d}{month:02d}01", code=code)
    try:
        data = get_json(url, cache_ttl=6 * 3600, cache_ok=_stat_ok)
    except Exception:
        return []
    if not isinstance(data, dict) or data.get("stat") != "OK":
        cp = _cache_path(url)                      # 舊快取可能是暫時性失敗被毒化 → 清掉重抓一次
        if cp.exists():
            cp.unlink()
            try:
                data = get_json(url, cache_ttl=6 * 3600, cache_ok=_stat_ok)
            except Exception:
                return []
    if not isinstance(data, dict) or data.get("stat") != "OK":
        return []
    out: list[tuple[str, float, int]] = []
    for row in data.get("data", []):
        close = _num(row[6])
        if close is None:
            continue  # 無交易日跳過
        out.append((_roc_slash_to_iso(row[0]), close, int(_num(row[1]) or 0)))
    return out


def fetch_history(code: str, start_iso: str, end_iso: str) -> list[tuple[str, float, int]]:
    """從 start 到 end 逐月抓取並合併排序的日價序列。"""
    sy, sm = int(start_iso[:4]), int(start_iso[5:7])
    ey, em = int(end_iso[:4]), int(end_iso[5:7])
    series: list[tuple[str, float, int]] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        series += fetch_month(code, y, m)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    series = [s for s in series if start_iso <= s[0] <= end_iso]
    return sorted(set(series))


BASIC_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"


def fetch_basic_rows() -> list[dict]:
    """上市公司基本資料（含產業別）原始列——解析交給 arm.stockmeta.rows_to_map。

    產業別半年才動一次 → 快取 24 小時即可（同一日 CI 多次執行不重打官方）。
    """
    rows = get_json(BASIC_URL, cache_ttl=86400)
    return rows if isinstance(rows, list) else []
