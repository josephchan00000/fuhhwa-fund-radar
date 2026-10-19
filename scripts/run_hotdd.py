#!/usr/bin/env python3
"""過熱之後 3 個月的最大回撤（docs/lab_hotdd_plan.md 第 4 節）：五個市場 × 面向／項目 × 事件 → data/lab/hotdd_research.json。

  TZ=Asia/Taipei python3 scripts/run_hotdd.py
資料或規格改了才重跑；每天建頁只讀研究檔（現在的狀態每天重算）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import hotdd as K  # noqa: E402


def main() -> None:
    t0 = time.time()
    R = K.research()
    print(f"[hotdd] 研究 {time.time() - t0:.0f}s", flush=True)
    K.save_research(R)
    print(f"[hotdd] 寫入 {K.RESEARCH}（{K.RESEARCH.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
