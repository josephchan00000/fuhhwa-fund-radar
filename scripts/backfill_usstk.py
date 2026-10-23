#!/usr/bin/env python3
"""美股個股策略的資料回補（docs/lab_core70_plan.md 第 9 節；只在 CI 跑，本容器擋 nasdaq／yahoo）。

  python3 scripts/backfill_usstk.py --budget-min 50   # 股價（沒抓過的）＋財報行事曆（時間內能查幾天算幾天）
  python3 scripts/backfill_usstk.py --status           # 第一行 DONE／LEFT／STUCK（給 workflow 判斷要不要再派一輪）
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import usstk  # noqa: E402

STUCK = Path("/tmp/usstk_stuck.txt")          # 同一個 job 裡才看得到（不入庫）


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=float, default=50)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--refresh-px", action="store_true", help="股價全部重抓")
    a = ap.parse_args()
    if a.status:
        line = usstk.status()
        if STUCK.exists() and not line.startswith("DONE"):
            line = "STUCK " + STUCK.read_text(encoding="utf-8").strip()
        print(line)
        return
    t0 = time.time()
    meta = usstk.load_meta()
    need_px = a.refresh_px or not meta["spans"] or any(s not in meta["px_done"] for s in usstk.wanted(meta["spans"]))
    if need_px:
        usstk.backfill_px(refresh=a.refresh_px)
    left = a.budget_min * 60 - (time.time() - t0)
    if left > 60:
        st = usstk.backfill_earn(budget_s=left - 30)
        # 一整輪一天都沒查到也算卡住（2026-10-23：最後 14 天每次都失敗、不到 25 次，job 原地重試 3.5 小時還會再派一輪）
        if st.get("stuck") or (st.get("todo") and not st.get("ok")):
            STUCK.write_text(f"財報行事曆查不到（還剩 {st.get('left')} 天）\n", encoding="utf-8")
        elif STUCK.exists():
            STUCK.unlink()
    print(usstk.status())


if __name__ == "__main__":
    main()
