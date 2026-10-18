#!/usr/bin/env python3
"""產業泡沫的驗證（docs/lab_risk_plan.md 第 12.4 節；規格 bubindspec）→ data/lab/bubind_research.json。

資料或規格改了才重跑（約 1 分鐘）：TZ=Asia/Taipei python3 scripts/run_bubind.py
台股產業用 data/lab/indtw（CI 每天由 scripts/fetch_heat.py 更新；本機沒有就先跑 bubind.indtw_update(True)）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import bubind as BD  # noqa: E402


def main() -> None:
    t0 = time.time()
    R = BD.research()
    ch = BD.save_research(R)
    for g in ("ff", "us", "tw"):
        G = R.get(g) or {}
        print(f"[{g}] {G.get('a')}～{G.get('z')}，{G.get('n_ind')} 個產業，等級分布 {G.get('dist')}")
        for t, v in (G.get("tests") or {}).items():
            for h in ("12", "24"):
                x = v.get(h) or {}
                ph, pa = x.get("p_hot"), x.get("p_all")
                print(f"   {t:4s} {h}m 成立 {x.get('n_hot')}／{x.get('n')}  大跌 {None if ph is None else round(100 * ph, 1)}% "
                      f"vs {None if pa is None else round(100 * pa, 1)}%  {x.get('verdict')}  段 {x.get('n_epi')}／產業段 {x.get('n_iepi')}")
    print(f"研究檔{'已更新' if ch else '沒有變更'}（{time.time() - t0:.0f} 秒）")


if __name__ == "__main__":
    main()
