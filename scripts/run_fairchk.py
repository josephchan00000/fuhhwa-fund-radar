#!/usr/bin/env python3
"""研究方法檢查（sigspec 第 5.9 節，VER 33；docs/lab_thermo_fair_plan.md 第 11、12 節）→ data/lab/fairchk_research.json。

  TZ=Asia/Taipei python3 scripts/run_fairchk.py
落底 B1～B6、強弱 L1～L4 全部一次算、全部照列；頁面怎麼標不看這個結果決定。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import fairchk as FC  # noqa: E402
from arm.lab import sigcat as G  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[fairchk] 資料 {time.time() - t0:.0f}s", flush=True)
    R = FC.research(F)
    FC.save(R)
    for mk, x in R["bottom"].items():
        print(f"[fairchk] {mk} 落底 主結果 {x['main']['v']} 第二套一致 {x['B6']['ok']}", flush=True)
    for mk, x in R["level"].items():
        if "L4" in x:
            print(f"[fairchk] {mk} 強弱 第二套一致 {x['L4']['ok']}", flush=True)
    print(f"[fairchk] 判定改變 {len(R['flips'])} 處；寫入 {FC.OUT}（{FC.OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
