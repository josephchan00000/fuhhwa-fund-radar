#!/usr/bin/env python3
"""實戰模擬（規格 arm/lab/practspec.py；docs/lab_practical_plan.md 第 11 節）→ data/lab/practsim_research.json。

  TZ=Asia/Taipei python3 scripts/run_practsim.py
資料或規格改了才重跑（約 5～8 分鐘：溫度計逐年票數同 run_thermo.py，總經策略每年重新判定一次）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import practsim as P  # noqa: E402
from arm.lab import sigcat as G  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[practsim] 資料 {time.time() - t0:.0f}s", flush=True)
    R = P.research(F)
    P.save(R)
    print(f"[practsim] 寫入 {P.OUT}（{P.OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)
    for k, x in R["page"].items():
        print(f"[practsim] {k}：比固定持有好 {x['better']}／差 {x['worse']}（{x['n']} 個市場）", flush=True)


if __name__ == "__main__":
    main()
