#!/usr/bin/env python3
"""景氣溫度頁研究檔：五個面向的分數、每一項的驗證、16 種技術事件的事件研究 → data/lab/heat_research.json
（docs/lab_heat_plan.md 第 12、13 節）。

規格（heatspec VER 4）與實作細節（規劃文件第 12.7、13.9 節）都在跑之前寫定。資料或規格改了才重跑：
  TZ=Asia/Taipei python3 scripts/run_heat.py
每天建頁只讀這個檔（過去的分區統計與判定，只當資訊），當天的分數用同一套算法重算。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import heatcalc as C  # noqa: E402
from arm.lab import heatspec as S  # noqa: E402

OUT = ROOT / "data" / "lab" / "heat_research.json"


def _r(x) -> str:
    return "  —  " if x is None else f"{x:+.3f}"


def _p(x) -> str:
    return "  —  " if x is None else f"{100 * x:+.2f}%"


def line(name: str, first: str | None, e: dict) -> str:
    ref = e.get("ref") or [{}, {}]
    return (f"  {name:8s} 起 {first or '—':10s} n={e['n']:5d} ρ={_r(e['rho'])} [{_r(e['lo'])}, {_r(e['hi'])}]"
            f"  前半 {_r(e['h1']['rho'])}  後半 {_r(e['h2']['rho'])}  → {S.VERDICT[e['verdict']]:8s}"
            f"  對照 {_r(ref[0].get('rho'))}／{_r(ref[1].get('rho'))}")


def main() -> None:
    t0 = time.time()
    res = C.research()
    OUT.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"資料日曆 {res['cal']}")
    for dim, R in res["dims"].items():
        L = S.DIMS[dim]
        for h in L["fwd"]:
            print(f"\n■ {L['name']}：之後 {h} 個交易日（{'每月' if L['freq'] == 'm' else '每天'}一個樣本）")
            print(line("面向分數", R["comp_first"], R["comp"][h]))
            for k in S.ITEMS[dim]:
                print(line(k, R["first"][k], R["items"][k][h]))
    print("\n■ 技術事件（之後 10／60 個交易日，和所有日子比）")
    for k, nm in S.EVENTS.items():
        cells = []
        for h in S.EV_FWD:
            e = res["events"][k][str(h)]
            if not e["n"]:
                cells.append(f"{h} 日 —")
                continue
            h1, h2 = (e.get("h1") or {}).get("diff"), (e.get("h2") or {}).get("diff")
            cells.append(f"{h} 日 n={e['n']:3d} 平均 {_p(e['avg'])} 差 {_p(e['diff'])} [{_p(e['lo'])}, {_p(e['hi'])}]"
                         f" 兩半 {_p(h1)}／{_p(h2)} → {S.EV_VERDICT[e['verdict']]}")
        print(f"  {nm:14s} " + "｜".join(cells))
    print(f"\n寫 {OUT}（{OUT.stat().st_size // 1024} KB），{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
