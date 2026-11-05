"""台指選擇權資料（docs/lab_txo_plan.md 第 15 節；arm/lab/txodata.py）。只在 CI 跑：.github/workflows/txo_data.yml 把資料分支
claude/txo-data checkout 到 txodata/ 後執行，寫完由 workflow commit 回資料分支（絕不合併進 main）。

  python3 scripts/fetch_txo.py --root txodata --mode daily              # 每天：逐筆（30 天內還沒存的）、這個月與上個月的日行情、最近的 5 秒指數
  python3 scripts/fetch_txo.py --root txodata --mode day --start 2002-01   # 回補日行情（已存的月份跳過）
  python3 scripts/fetch_txo.py --root txodata --mode idx --start 2016-01-04 # 回補 5 秒指數（已存與證交所說沒有的日子跳過）
  python3 scripts/fetch_txo.py --root txodata --mode backfill             # 日行情從 2002 起、5 秒指數從 2016 起，照 --budget-min 能做多少做多少
  python3 scripts/fetch_txo.py --root txodata --mode fomc                 # 聯準會會議行程頁（O2 的 FOMC 聲明日；arm/lab/txoevents.py）
  python3 scripts/fetch_txo.py --root txodata --mode futday --start 2017-05  # 台指期每日行情（日盤＋夜盤；盤前作戰圖第 3 段）

容器連不到期交所與證交所，不要在容器裡跑（wiki/env/container.md）。
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.clock import today_tw  # noqa: E402
from arm.lab import txodata as T  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="資料分支 checkout 的位置（例 txodata）")
    ap.add_argument("--mode", default="daily", choices=["daily", "bars", "day", "idx", "backfill", "fomc", "futday"])
    ap.add_argument("--start", default="", help="day：YYYY-MM；idx：YYYY-MM-DD")
    ap.add_argument("--budget-min", type=float, default=100)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if not (root / "README.md").exists():
        print(f"[txo] {root} 不是資料分支（沒有 README.md）", flush=True)
        return 1
    today = today_tw()
    t0 = time.time()
    deadline = t0 + a.budget_min * 60
    out = {}
    if a.mode in ("daily", "bars"):
        out["bars"] = T.update_bars(root, ROOT, deadline)
    if a.mode == "daily":
        prev = (today.replace(day=1) - timedelta(days=1))
        out["day"] = T.update_day(root, f"{prev:%Y-%m}", today, deadline)
        out["idx"] = T.update_idx(root, today - timedelta(days=10), today, deadline)
        out["futday"] = T.update_futday(root, f"{prev:%Y-%m}", today, deadline)
    if a.mode in ("day", "backfill"):
        out["day"] = T.update_day(root, a.start[:7] if a.mode == "day" and a.start else "2002-01", today,
                                  deadline if a.mode == "day" else t0 + a.budget_min * 60 * 0.4)
    if a.mode == "futday":
        out["futday"] = T.update_futday(root, a.start[:7] if a.start else T.FUT_FIRST, today, deadline)
    if a.mode == "fomc":
        from arm.lab import txoevents as E
        out["fomc"] = E.update_pages(root, today)
        E.summary(E.parse_all(E.load_pages(root)))
    if a.mode in ("idx", "backfill"):
        s = date.fromisoformat(a.start) if a.mode == "idx" and a.start else T.IDX_FIRST
        out["idx"] = T.update_idx(root, max(s, T.IDX_FIRST), today, deadline)
    print(f"[txo] {a.mode} 完成：{out}，{(time.time() - t0) / 60:.1f} 分", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
