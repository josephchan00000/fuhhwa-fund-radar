#!/usr/bin/env python3
"""台指選擇權日資料回測 O2、O3（arm/lab/txobt.py；docs/lab_txo_plan.md 第 18 節）。只讀資料分支、不抓任何東西。

  python3 scripts/run_txobt.py --root <資料分支 checkout> --events     # 由資料分支的聯準會行程頁重產 data/lab/txo_events.json
  python3 scripts/run_txobt.py --root <資料分支 checkout>              # 回測 → data/lab/txo_research.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.lab import txobt as B  # noqa: E402
from arm.lab import txoevents as E  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="資料分支 claude/txo-data 的 checkout")
    ap.add_argument("--events", action="store_true", help="只重產 data/lab/txo_events.json")
    ap.add_argument("--placebo", type=int, default=None, help="打亂測試次數（預設照 txospec）")
    ap.add_argument("--out", default=str(ROOT / "data/lab/txo_research.json"))
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if a.events:
        r = E.parse_all(E.load_pages(root))
        E.summary(r)
        doc = {"src": E.FED + E.CAL + "（及 fomchistorical{年}.htm）", "rule": "排定會議（Meeting、非 unscheduled／cancelled、有 Statement）的最後一天",
               "fomc": r["sched"], "fomc_other": r["other"], "by_year": r["by_year"]}
        (ROOT / "data/lab/txo_events.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
        return 0
    t0 = time.time()
    kw = {} if a.placebo is None else {"placebo_n": a.placebo}
    out = B.run(root, **kw)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", "utf-8")
    print(f"[txobt] 寫入 {a.out}（{(time.time() - t0):.0f} 秒）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
