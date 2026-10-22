#!/usr/bin/env python3
"""溫度計「過去讀數這樣的時候」的研究（sigspec 第 5 節 ③d，VER 16；docs/lab_noise_plan.md 第 14.10 節）→ data/lab/thermo_research.json。

  TZ=Asia/Taipei python3 scripts/run_thermo.py
資料或規格改了、或是跨年了（今天的票數用今年 1 月 1 日那一次的統計）才重跑；每天建頁只讀研究檔。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigcat as G  # noqa: E402
from arm.lab import thermocal as TC  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[thermo] 資料 {time.time() - t0:.0f}s", flush=True)
    R = TC.research(F)
    TC.save(R)
    print(f"[thermo] 寫入 {TC.OUT}（{TC.OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
