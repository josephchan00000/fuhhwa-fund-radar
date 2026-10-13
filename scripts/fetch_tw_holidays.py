#!/usr/bin/env python3
"""證交所官方休市表 → data/tw_holidays.json（CI 每日跑；一個請求、抓不到沿用既有）。

台股「今天有沒有開」的權威來源，取代子代理寫的行事曆市況文字——見 arm/twholidays.py。
本容器 proxy 擋 twse，本地跑會印失敗並沿用既有（內建 2026 種子照常可用）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import twholidays  # noqa: E402

if __name__ == "__main__":
    twholidays.fetch_and_save()
