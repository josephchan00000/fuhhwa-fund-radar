#!/usr/bin/env python3
"""盤前價位第 4 段（arm/lab/pmlvl.py；規格 arm/lab/pmlvlspec.py；docs/lab_premarket_plan.md 第 15 節）。只讀資料分支、不抓任何東西。

  python3 scripts/run_pmlvl.py --root <資料分支 claude/txo-data 的 checkout>   # → data/lab/pmlvl_research.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.lab import pmlvl as L  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="資料分支 claude/txo-data 的 checkout")
    ap.add_argument("--out", default=str(ROOT / "data/lab/pmlvl_research.json"))
    a = ap.parse_args()
    t0 = time.time()
    out = L.run(Path(a.root).resolve(), log=lambda s: print(f"[pmlvl] {s}", flush=True))
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", "utf-8")
    print(f"[pmlvl] 寫入 {a.out}（{(time.time() - t0):.0f} 秒）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
