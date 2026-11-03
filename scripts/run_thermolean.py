#!/usr/bin/env python3
"""溫度計讀數的新舊比較（sigspec 第 5.3 節，VER 28；docs/lab_thermo_lean_plan.md 第 4、5 節）→ data/lab/thermolean_research.json。

  TZ=Asia/Taipei python3 scripts/run_thermolean.py
只描述、不參與任何判定；網頁的讀數每天建頁時用 thermo_research.json 的週末票數算（thermocal.now 的 mid），不讀這個檔。
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
    print(f"[thermolean] 資料 {time.time() - t0:.0f}s", flush=True)
    R = TC.lean_research(F)
    TC.LEAN_OUT.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"[thermolean] 寫入 {TC.LEAN_OUT}（{TC.LEAN_OUT.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
