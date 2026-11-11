#!/usr/bin/env python3
"""台指選擇權結算日 O1（結算日順勢）與 O4（結算均價）的回測與紀錄（arm/lab/txo1.py；docs/lab_txo_plan.md 第 19 節）。
只讀資料分支、不抓任何東西。

  python3 scripts/run_txo1.py --root <資料分支 claude/txo-data 的 checkout>    # → data/lab/txo_settle.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.lab import txo1 as X  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="資料分支 claude/txo-data 的 checkout")
    ap.add_argument("--placebo", type=int, default=None, help="打亂測試次數（預設照 txospec）")
    ap.add_argument("--out", default=str(ROOT / "data/lab/txo_settle.json"))
    a = ap.parse_args()
    t0 = time.time()
    kw = {} if a.placebo is None else {"placebo_n": a.placebo}
    out = X.run(Path(a.root).resolve(), **kw)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=float) + "\n", "utf-8")
    print(f"[txo1] 寫入 {a.out}（{(time.time() - t0):.0f} 秒）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
