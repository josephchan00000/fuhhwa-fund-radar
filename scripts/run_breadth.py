#!/usr/bin/env python3
"""寬度與深度的研究（規格 arm/lab/breadthspec.py VER 1；docs/lab_breadth_plan.md 第 9、10 節）→ data/lab/breadth_research.json。

  TZ=Asia/Taipei python3 scripts/run_breadth.py
只研究：不改訊號總覽（sig_research.json）、不改泡沫等級、不進頁面。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import breadth as BR  # noqa: E402
from arm.lab import bubble as BU  # noqa: E402
from arm.lab import sigcat as G  # noqa: E402


def main() -> None:
    t0 = time.time()
    BX = BU.compute()
    F = G.frames(BX=BX)
    print(f"[breadth] 五個市場的資料 {time.time() - t0:.0f}s", flush=True)
    R = BR.research(F, BX)
    BR.save(R)
    print(f"[breadth] 寫入 {BR.RESEARCH}（{BR.RESEARCH.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
