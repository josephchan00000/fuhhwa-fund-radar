#!/usr/bin/env python3
"""列出來的每一列分強弱的逐年檢查（sigspec 第 5.6 節，VER 31；docs/lab_thermo_fair_plan.md 第 8 節）→ data/lab/thermolevel_research.json。

  TZ=Asia/Taipei python3 scripts/run_thermolevel.py
只描述＋規格寫定的判定、不論結果都分；網頁每一列的強弱每天建頁時用研究檔已有的差分（sigcat.listing 的 "lv"），不讀這個檔。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigcat as G  # noqa: E402
from arm.lab import thermocal as TC  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = G.frames()
    print(f"[thermolevel] 資料 {time.time() - t0:.0f}s", flush=True)
    R = TC.level_research(F)
    TC.LEVEL_OUT.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"[thermolevel] 寫入 {TC.LEVEL_OUT}（{TC.LEVEL_OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
