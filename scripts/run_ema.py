#!/usr/bin/env python3
"""EMA 賣壓（arm/lab/emaspec.py VER 1；docs/lab_signal_quality_plan.md 第 13 節）→ data/lab/ema_research.json。

  TZ=Asia/Taipei python3 scripts/run_ema.py
只讀已入庫的資料（不抓資料）；現在的合計與連續買賣超用這裡的程式算的逐年紀錄要和「預估之後」一模一樣，不一樣就停。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import emaspec as E  # noqa: E402
from arm.lab import sigema as M  # noqa: E402


def main() -> None:
    t0 = time.time()
    log = lambda s: print(f"{s}（{time.time() - t0:.0f}s）", flush=True)   # noqa: E731
    R = M.run(log=log)
    M.save(R)
    log(f"[ema] 寫入 {M.OUT}（{M.OUT.stat().st_size // 1024} KB）")
    for k in E.FAMILIES:
        a = R["fam"][k]["all"]
        print(f"  {E.FAMILY_NAMES[k]}：列出來 {a['n']} 筆、實際平均比平常高 {a['mean'] * 100:.1f} 點、比平常好的 {a['pos'] * 100:.0f}%")
    for k, d in R["diff"].items():
        print(f"  {k}：差 {d['d'] * 100:.1f} 點（95% 區間 {d['lo'] * 100:.1f}～{d['hi'] * 100:.1f}）；換＝{R['better'][k[2:]]}")


if __name__ == "__main__":
    main()
