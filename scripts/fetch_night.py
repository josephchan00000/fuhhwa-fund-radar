#!/usr/bin/env python3
"""台指期夜盤（期交所 MIS 盤後報價）→ data/lab/fut/night.json（arm/lab/futdata.update_night；docs/lab_premarket_plan.md）。
只在 CI 跑（容器連不到期交所）：afterhours_refresh.yml（清晨 05:08 那班＝夜盤剛收）、txo_data.yml、daily.yml。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.lab import futdata as F  # noqa: E402

if __name__ == "__main__":
    try:
        F.update_night()
    except Exception as e:  # noqa: BLE001 —— 抓不到就沿用舊檔（盤前圖會標「夜盤未更新」）
        print(f"[fut] 夜盤抓取失敗：{type(e).__name__}: {e}")
