#!/usr/bin/env python3
"""今天的訊號「第幾天進場」的格子（sigspec VER 26 第 5.1 節；docs/lab_signal_listing_plan.md）→ data/lab/sigage_research.json。

  TZ=Asia/Taipei python3 scripts/run_sigage.py
資料或規格改了才重跑（和 run_sig.py、run_thermo.py 一起）；每天建頁只讀研究檔，今天落哪一格每天重算。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigage as A  # noqa: E402
from arm.lab import sigcat as G  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[sigage] 資料 {time.time() - t0:.0f}s", flush=True)
    R = A.research(F)
    print(f"[sigage] 研究 {time.time() - t0:.0f}s，{len(R['rows'])} 個訊號、逐年紀錄 {R['nrec']} 筆（跨期間 {R['nrec_x']}）", flush=True)
    A.save(R)
    print(f"[sigage] 寫入 {A.OUT}（{A.OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
