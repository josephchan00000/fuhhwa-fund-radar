#!/usr/bin/env python3
"""盤前作戰圖第 3 段驗證（arm/lab/pmval.py；規格 arm/lab/premktspec.py；docs/lab_premarket_plan.md 第 11、12 節）。只讀資料分支、不抓任何東西。

  python3 scripts/run_pmval.py --root <資料分支 claude/txo-data 的 checkout>   # → data/lab/premkt_research.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.lab import pmval as V  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="資料分支 claude/txo-data 的 checkout")
    ap.add_argument("--out", default=str(ROOT / "data/lab/premkt_research.json"))
    ap.add_argument("--open-t", type=int, default=None, help="開盤＝第幾個 5 秒（1＝重現 VER 1 的 09:00:05；預設照規格）")
    a = ap.parse_args()
    t0 = time.time()
    out = V.run(Path(a.root).resolve(), log=lambda s: print(f"[pmval] {s}", flush=True), open_t=a.open_t)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", "utf-8")
    print(f"[pmval] 寫入 {a.out}（{(time.time() - t0):.0f} 秒）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
