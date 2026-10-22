#!/usr/bin/env python3
"""期貨加碼（規格 arm/lab/tiltspec.py；docs/lab_tilt_plan.md）→ data/lab/tilt_research.json。

  TZ=Asia/Taipei python3 scripts/run_tilt.py
資料或規格改了才重跑（溫度計逐年票數同 run_thermo.py，總經策略每年重新判定一次）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigcat as G  # noqa: E402
from arm.lab import tilt as P  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[tilt] 資料 {time.time() - t0:.0f}s", flush=True)
    R = P.research(F)
    P.save(R)
    print(f"[tilt] 寫入 {P.OUT}（{P.OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)
    for k, x in R["page"].items():
        print(f"[tilt] {k}：訊號有用 {x['better']}／比固定加碼差 {x['worse']}（{x['n']} 個市場）"
              f"{'，可以放上網頁' if x['ok'] else ''}", flush=True)


if __name__ == "__main__":
    main()
