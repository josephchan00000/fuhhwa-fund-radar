"""美股個股策略研究（規格 arm/lab/usstratspec.py；docs/lab_core70_plan.md 第 15 節）。

    TZ=Asia/Taipei python3 scripts/run_usstrat.py [--data 目錄]   → data/lab/usstrat_research.json
--data＝美股個股資料（data/lab/usstk）放在別的地方時（例如還沒併進 main 的回補分支）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import store, usstk  # noqa: E402
from arm.lab import usstrat as US  # noqa: E402


def main() -> None:
    if "--data" in sys.argv:
        usstk.DIR = Path(sys.argv[sys.argv.index("--data") + 1])
    t0 = time.time()
    P = US.panel()
    print(f"[usstrat] 面板 {len(P['sym'])} 檔、{len(P['cal'])} 個交易日（{P['cal'][0]}～{P['cal'][-1]}），{time.time() - t0:.0f} 秒")
    R = US.research(P)
    cal = R.pop("cal")
    out = {k: v for k, v in R.items()}
    for grp in ("runs", "bench"):
        for k, v in out[grp].items():
            nav = v.pop("nav")
            v["navm"] = {cal[i][:7]: round(float(nav[i]), 6) for i in US.period_ends(cal, "m") if np.isfinite(nav[i])}
    p = store.LAB / "usstrat_research.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    f = lambda x: "—" if x is None else f"{x * 100:.1f}%"  # noqa: E731
    for k in ("U1", "U2", "U3"):
        s = out["runs"][k]
        print(f"[usstrat] {k}：{f(s['cagr']['all'])}（{f(s['cagr']['h1'])}／{f(s['cagr']['h2'])}）回落 {f(s['mdd'])}；判定 {out['verdict'][k]}")
    for k in ("EW", "SPX"):
        s = out["bench"][k]
        print(f"[usstrat] {k}：{f(s['cagr']['all'])}（{f(s['cagr']['h1'])}／{f(s['cagr']['h2'])}）回落 {f(s['mdd'])}")
    print(f"[usstrat] {time.time() - t0:.0f} 秒 → {p}")


if __name__ == "__main__":
    main()
