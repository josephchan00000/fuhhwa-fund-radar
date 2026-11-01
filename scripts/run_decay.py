#!/usr/bin/env python3
"""天數衰減（arm/lab/decayspec.py VER 1；docs/lab_signal_quality_plan.md 第 13.3 節）→ data/lab/decay_research.json。

  TZ=Asia/Taipei python3 scripts/run_decay.py
只讀已入庫的資料（不抓資料）；VER 25、VER 26 的每週票數與比例要和 thermocal 一模一樣，不一樣就停。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigdecay as M  # noqa: E402


def main() -> None:
    t0 = time.time()
    log = lambda s: print(f"{s}（{time.time() - t0:.0f}s）", flush=True)   # noqa: E731
    R = M.run(log=log)
    M.save(R)
    log(f"[decay] 寫入 {M.OUT}（{M.OUT.stat().st_size // 1024} KB）")
    s = R["sum"]
    print(f"  衰減 − 第 26 版：{s['d'] * 100:.2f} 點（95% 區間 {s['lo'] * 100:.2f}～{s['hi'] * 100:.2f}），30 組裡 {s['win']} 組比較好；"
          f"項目週數 VER 25 {s['cover']['v25']}、VER 26 {s['cover']['v26']}、衰減 {s['cover']['decay']}；換＝{s['better']}")


if __name__ == "__main__":
    main()
