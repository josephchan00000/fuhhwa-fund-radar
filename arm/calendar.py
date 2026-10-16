"""TWSE 交易日曆（M1-9）。

權威來源用 0050 官方日價序列：0050 在每個 TWSE 交易日都有收盤，
故其日期集合即為交易日曆——免去額外去爬節假日表（少一個易壞端點）。

用途：
  - NAV 含息回補只跑真正交易日，不空打假日。
  - 盤後流程判定「今天是不是交易日」，非交易日不誤報為當日資料。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .connectors import twse

CST = timezone(timedelta(hours=8))          # 台北時間 UTC+8
CALENDAR_ANCHOR = "0050"                      # 以 0050 序列當交易日曆


def today_cst() -> str:
    return datetime.now(CST).date().isoformat()


def trading_days(start_iso: str, end_iso: str) -> list[str]:
    """[start, end] 區間內的 TWSE 交易日（ISO 字串，遞增）。"""
    series = twse.fetch_history(CALENDAR_ANCHOR, start_iso, end_iso)
    return [d for d, _, _ in series]


def is_trading_day(iso_date: str, days: list[str] | None = None) -> bool:
    """iso_date 是否為交易日。可傳入已取得的交易日清單避免重抓。"""
    if days is None:
        days = trading_days(iso_date, iso_date)
    return iso_date in set(days)


def latest_trading_day(all_today: dict | None = None) -> str:
    """目前可得的最近交易日（= TWSE 當日全表最新日期）。"""
    return twse.latest_trade_date(all_today)


def run_context(all_today: dict | None = None) -> dict:
    """盤後流程用：回傳 {today, latest, is_trading_today, stale}。
    stale = 最近交易日資料不是今天（週末／假日／盤後尚未更新）。
    """
    latest = latest_trading_day(all_today)
    today = today_cst()
    return {"today": today, "latest": latest,
            "is_trading_today": latest == today, "stale": latest != today}
