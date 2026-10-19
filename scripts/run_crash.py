#!/usr/bin/env python3
"""大跌風險研究（docs/lab_crash_plan.md 第 10 節）：五個市場 × 預測變數 × 五個結果 → data/lab/crash_research.json。

  TZ=Asia/Taipei python3 scripts/run_crash.py            # 完整（含樣本外，約幾分鐘）
  TZ=Asia/Taipei python3 scripts/run_crash.py --no-oos   # 不跑樣本外（測速用，不寫檔）
資料或規格改了才重跑；每天建頁只讀研究檔。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import crash as K  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-oos", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    I = K.inputs_all()
    print(f"[crash] 輸入 {time.time() - t0:.0f}s", flush=True)
    R = K.research(I, with_oos=not a.no_oos)
    print(f"[crash] 研究 {time.time() - t0:.0f}s", flush=True)
    if a.no_oos:
        return
    K.save_research(R)
    print(f"[crash] 寫入 {K.RESEARCH}（{K.RESEARCH.stat().st_size // 1024} KB），共 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
