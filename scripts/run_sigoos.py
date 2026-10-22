#!/usr/bin/env python3
"""預估之後的研究（sigspec 第 4.14 節，VER 18；docs/lab_practical_plan.md 第 10 節）：五個市場的市場層級訊號與大跌後買點，
逐年樣本外的衰退表 → data/lab/sigoos_research.json。

  TZ=Asia/Taipei python3 scripts/run_sigoos.py
資料或規格改了才重跑；每天建頁只讀研究檔（每個訊號的預估之後在建頁時用研究檔的衰退表算）。
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigcat as G  # noqa: E402
from arm.lab import sigoos as O  # noqa: E402
from arm.lab import sigspec as S  # noqa: E402

_F: dict = {}


def _one(mk: str) -> tuple[str, list]:
    t = time.time()
    recs = O.market(_F[mk])
    print(f"[sigoos] {mk} {len(recs)} 筆 {time.time() - t:.0f}s", flush=True)
    return mk, recs


def main() -> None:
    t0 = time.time()
    _F.update(G.frames())
    print(f"[sigoos] 資料 {time.time() - t0:.0f}s", flush=True)
    mks = [mk for mk in S.MARKETS if mk in _F]
    with mp.get_context("fork").Pool(min(len(mks), 5)) as pool:
        got = dict(pool.map(_one, mks))
    recs = [r for mk in mks for r in got[mk]]
    R = O.research(_F, recs)
    O.save(R)
    print(f"[sigoos] 寫入 {O.OUT}（{O.OUT.stat().st_size // 1024} KB），{len(recs)} 筆、{len(R['cells'])} 格，共 {time.time() - t0:.0f}s",
          flush=True)


if __name__ == "__main__":
    main()
