"""台北時區時間單一來源。

本專案的「今天」一律指台北日期：本機、GitHub Actions（UTC）、雲端 Claude 容器（UTC）
都可能在非 UTC+8 時區執行，直接用 date.today()/datetime.now() 會在跨日時段產生
「日期錯置」（例：台北週六清晨在 UTC 容器跑出前一天的提示包檔名）。
所有需要「今天／現在」的模組請 import 這裡，不要各自 datetime.now()。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))          # 台北時間 UTC+8（台灣無日光節約）


def now_tw() -> datetime:
    """台北此刻（tz-aware）。"""
    return datetime.now(TW_TZ)


def today_tw() -> date:
    """台北今天。"""
    return now_tw().date()


def stamp_tw(fmt: str = "%Y-%m-%d %H:%M") -> str:
    """台北此刻的字串戳（預設 YYYY-MM-DD HH:MM）。"""
    return now_tw().strftime(fmt)
