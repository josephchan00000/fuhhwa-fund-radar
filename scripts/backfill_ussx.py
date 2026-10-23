#!/usr/bin/env python3
"""美股飆股研究的資料回補（docs/lab_us_sleeve_plan.md 第 8 節；只在 CI 跑，而且只在資料分支 claude/ussx-data）。

  python3 scripts/backfill_ussx.py --budget-min 50   # 篩選器（一天一次）→ 股價（沒抓過的）→ SEC（有 secret、一天一次）
  python3 scripts/backfill_ussx.py --status           # 第一行 DONE／LEFT／STUCK（給 workflow 判斷要不要再派一輪）
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import secfin as SF  # noqa: E402
from arm.lab import ussxdata as UD  # noqa: E402

STUCK = Path("/tmp/ussx_stuck.txt")          # 同一個 job 裡才看得到（不入庫）
SEC_MIN = 15                                 # 剩這麼多分鐘以上才開始抓 SEC（下載＋解析約 5～10 分鐘）


def line() -> str:
    px = UD.status()
    sec_done = bool(SF.load_meta().get("asof")) or not SF.contact()
    head = "DONE" if px.startswith("DONE") and sec_done else "LEFT"
    out = f"{head} {px.split(' ', 1)[1]}｜{SF.status()}"
    if STUCK.exists() and head != "DONE":
        out = "STUCK " + STUCK.read_text(encoding="utf-8").strip() + "｜" + out
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=float, default=50)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        print(line())
        return
    t0 = time.time()
    budget = a.budget_min * 60
    UD.update_screen()
    st = UD.backfill_px(budget_s=max(60.0, budget - (time.time() - t0) - 60))
    # 一整輪一檔都沒進展（全部失敗）＝卡住，不要原地重試好幾個小時
    if st.get("todo") and not st.get("ok") and not st.get("none"):
        STUCK.write_text(f"股價一檔都抓不到（還剩 {st.get('left')} 檔）\n", encoding="utf-8")
    elif STUCK.exists():
        STUCK.unlink()
    left_min = (budget - (time.time() - t0)) / 60
    if st.get("left", 1) == 0 and left_min >= SEC_MIN:
        SF.run()
    print(line())


if __name__ == "__main__":
    main()
