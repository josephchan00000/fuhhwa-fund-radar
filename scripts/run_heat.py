#!/usr/bin/env python3
"""景氣溫度頁研究檔：各指標與各線總分的驗證＋納入規則 → data/lab/heat_research.json（docs/lab_heat_plan.md 第 5、11 節）。

規格（heatspec）與實作細節（規劃文件第 10.4 節）都在跑之前寫定。資料或規格改了才重跑：
  TZ=Asia/Taipei python3 scripts/run_heat.py
每天建頁只讀這個檔（哪些指標算進總分、過去的分區統計），當天的分數用同一套算法重算。
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


def line_txt(ln: str, L: dict) -> None:
    main = S.LINES[ln]["main"]
    print(f"\n■ {S.LINES[ln]['name']}（主要看 {main} 日；方向 {L['dir']}；算進總分 {L['inc'] or '無'}）")
    for k, ev in L["items"].items():
        e = ev[main]
        print(f"  {k:3s} 起 {L['first'][k] or '—':10s}  樣本內 n={e['is']['n']:5d} ρ={e['is']['rho']} "
              f"[{e['is']['lo']}, {e['is']['hi']}]  樣本外 n={e['oos']['n']:5d} ρ={e['oos']['rho']}  → {S.VERDICT[e['verdict']]}")
    if L["comp"]:
        e = L["comp"][main]
        print(f"  總分  樣本內 ρ={e['is']['rho']} [{e['is']['lo']}, {e['is']['hi']}]  樣本外 ρ={e['oos']['rho']} "
              f"[{e['oos']['lo']}, {e['oos']['hi']}]  → {S.VERDICT[e['verdict']]}")


def main() -> None:
    t0 = time.time()
    res = C.research()
    OUT.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"資料日曆 {res['cal']}")
    for ln, L in res["lines"].items():
        line_txt(ln, L)
    print(f"\n寫 {OUT}（{OUT.stat().st_size // 1024} KB），{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
