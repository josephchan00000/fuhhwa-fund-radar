#!/usr/bin/env python3
"""現在的情境：相似的日子的樣本外檢查（docs/lab_outlook_plan.md、arm/lab/sigspec.py 第 4.12 節）→ data/lab/sim_research.json。

  TZ=Asia/Taipei python3 scripts/run_sim.py
資料或規格改了才重跑；每天建頁只讀研究檔（現在的估計每天重算）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigcat as G  # noqa: E402
from arm.lab import simdays as M  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[sim] 資料 {time.time() - t0:.0f}s", flush=True)
    R = M.research(F)
    for mk, v in R["markets"].items():
        print(f"[sim] {mk}：" + "，".join(f"{o['h']}日 {o['v']}（{o['n']} 個月）" for o in v["oos"]), flush=True)
    M.save_research(R)
    print(f"[sim] 寫入 {M.RESEARCH}（{M.RESEARCH.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
