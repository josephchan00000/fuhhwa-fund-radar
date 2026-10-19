#!/usr/bin/env python3
"""大跌後的買點與落底訊號研究檔（docs/lab_crash_plan.md 第 13 節）：五個市場 × 兩種事件 × 分組與落底訊號
→ data/lab/bottom_research.json（資料或規格改了才重跑；每天建頁只讀研究檔）。

  TZ=Asia/Taipei python3 scripts/run_bottom.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import bottom as X  # noqa: E402


def main() -> None:
    t0 = time.time()
    R = X.research()
    X.save_research(R)
    print(f"[bottom] 研究檔 {X.RESEARCH}（{time.time() - t0:.0f} 秒）")
    for h, v in R["primary"].items():
        print(f"  {h}: n={v.get('n')} d={v.get('d')} lo={v.get('lo')} hi={v.get('hi')} p1={v.get('p1')} "
              f"h1={v.get('h1')} h2={v.get('h2')} padj={v.get('padj')} ok={v.get('ok')}")


if __name__ == "__main__":
    main()
