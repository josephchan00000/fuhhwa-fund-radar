"""泡沫頁研究（bubspec VER 1；docs/lab_risk_plan.md 第 8 節）。

  --cv     算有長期漲勢的 PSY 臨界值表 → data/lab/heat/psy_cv_drift（8 檔漂移 × 2,000 次，約 20 分鐘；規格沒變就不用重算）
  （預設） 五個市場的條件、等級與驗證 → data/lab/bub_research.json（資料或規格改了才重跑）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str]) -> int:
    from arm.lab import bubble as BB
    from arm.lab import heatdata as HD
    if "--cv" in argv:
        t0 = time.time()
        T = BB.cv_table(progress=lambda g, cv: print(f"drift {g:.3f}  n=480 q95={cv['q95'][479]}  {time.time() - t0:.0f}s",
                                                     flush=True))
        HD.save(BB.CV_NAME, "simulation（bubspec VER 1）", T)
        print("saved", BB.CV_NAME, f"{time.time() - t0:.0f}s")
        return 0
    t0 = time.time()
    out = BB.research()
    print("changed" if BB.save_research(out) else "unchanged", BB.RESEARCH, f"{time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
