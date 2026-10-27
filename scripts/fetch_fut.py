#!/usr/bin/env python3
"""台指期早盤策略的資料：期交所近 30 個交易日每筆成交（台指期日盤）＋證交所每 5 秒指數（docs/lab_fut_plan.md）。

只增不改：已存的日子不再抓。期交所只留 30 個交易日，所以每天都要跑（afterhours_refresh.yml）；
lab_backfill.yml mode=futfill 一次補完清單上的日子。

  TZ=Asia/Taipei python3 scripts/fetch_fut.py [--budget 240]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import futdata  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=240, help="秒")
    a = ap.parse_args()
    futdata.update(budget_s=a.budget)


if __name__ == "__main__":
    main()
