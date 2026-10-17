#!/usr/bin/env python3
"""法人預估落檔（docs/lab_forward_plan.md；CI 用——本容器 proxy 擋 cnyes／yahoo，在此跑只會全數失敗）。

  python3 scripts/fetch_fcst.py                               # 每日：FactSet 快訊補到現在＋Yahoo 一天一次
  python3 scripts/fetch_fcst.py --backfill 150 --full --budget 2400   # 回補（lab_backfill.yml 的 fcfill）

失敗一律不擋呼叫端（exit 0）。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm.lab import company, fcst  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int, default=0, help="FactSet 快訊往回補幾週")
    ap.add_argument("--full", action="store_true", help="Yahoo 重掃全部上市櫃")
    ap.add_argument("--budget", type=float, default=300, help="秒")
    a = ap.parse_args()
    try:
        st = fcst.update_factset(backfill_weeks=a.backfill, budget_s=max(60.0, a.budget * 0.6 if a.backfill else 90))
        print(f"[fcst] FactSet 快訊：{st}")
    except Exception as e:                                # noqa: BLE001
        print(f"[fcst] FactSet 快訊失敗：{type(e).__name__}: {e}")
    try:
        st = fcst.update_yahoo(company.listed_now(), full=a.full, budget_s=a.budget * (0.4 if a.backfill else 0.7))
        print(f"[fcst] Yahoo 分析師：{st}")
    except Exception as e:                                # noqa: BLE001
        print(f"[fcst] Yahoo 分析師失敗：{type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                                # noqa: BLE001 —— 不擋呼叫端
        print(f"[fcst] fetch_fcst 失敗（不影響其他步驟）：{type(e).__name__}: {e}")
