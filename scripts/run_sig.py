#!/usr/bin/env python3
"""訊號總覽的研究（docs/lab_signal_plan.md、arm/lab/sigspec.py）：五個市場的所有市場層級訊號＋產業泡沫 → data/lab/sig_research.json。

  TZ=Asia/Taipei python3 scripts/run_sig.py
資料或規格改了才重跑；每天建頁只讀研究檔（現在有沒有效每天重算）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigcat as G  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[sig] 資料 {time.time() - t0:.0f}s", flush=True)
    R = G.research(F)
    print(f"[sig] 研究 {time.time() - t0:.0f}s，{len(R['rows'])} 列", flush=True)
    G.save_research(R)
    print(f"[sig] 寫入 {G.RESEARCH}（{G.RESEARCH.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
