#!/usr/bin/env python3
"""「可能落底」框的逐年檢查（sigspec 第 5.5 節，VER 30；docs/lab_thermo_fair_plan.md 第 5、6 節）→ data/lab/bottombox_research.json。

  TZ=Asia/Taipei python3 scripts/run_bottombox.py
每年 1 月 1 日只用那時以前走完的窗口挑強的落底型訊號，那一年每個週末框有沒有出現（大跌中＋強的亮著），之後 3 個月怎麼走；
和大跌中全部週、全部週比。網頁的框每天建頁時用研究檔的成績算（bottombox.today），只從這個檔讀逐年檢查的一句。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import bottombox as BB  # noqa: E402
from arm.lab import sigcat as G  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[bottombox] 資料 {time.time() - t0:.0f}s", flush=True)
    R = BB.research(F)
    BB.save(R)
    for mk, m in R["mk"].items():
        b, d = m["box"], m["drop"]
        print(f"[bottombox] {mk} 段數 {m['ep']} 框週 {b['n']} 大跌中週 {d['n']} 判定 {m['v']}", flush=True)
    print(f"[bottombox] 寫入 {BB.OUT}（{BB.OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
