#!/usr/bin/env python3
"""少見但勝率高的策略：回測九條規則、寫 data/lab/rare_research.json（規格 arm/lab/rarespec.py；docs/lab_rare_plan.md）。

  TZ=Asia/Taipei python3 scripts/run_rare.py            # 算完寫檔、印摘要
  TZ=Asia/Taipei python3 scripts/run_rare.py --no-write # 只印
資料或規格改了才重跑。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import rare as R          # noqa: E402
from arm.lab import rarespec as S      # noqa: E402


def pct(v, k: int = 1) -> str:
    return "—" if v is None else f"{v * 100:.{k}f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    res = R.run()
    print(f"[rare] 規格 VER {S.VER}，資料到 {res['asof']}，{time.time() - t0:.1f} 秒")
    for Rl in S.RULES:
        print(f"\n== {Rl['k']} {Rl['name']}（主要市場 {S.NAMES[Rl['home']]}）")
        for mk, x in res["rules"][Rl["k"]].items():
            f = x["full"]
            o = "；".join(f"{k}:{v.get('n', 0)}次 {pct(v.get('win'), 0)}／{pct(v.get('base'), 0)}" for k, v in x["outs"].items())
            print(f"  {S.NAMES[mk]:<8} {S.TIER_MARK[x['tier']]} n={f.get('n', 0):<3} 賺錢 {pct(f.get('win'), 0):>5} 任一天 {pct(f.get('base'), 0):>5}"
                  f" 中位 {pct(f.get('med')):>7} 排除極端 {pct(f.get('trim')):>7} 最差 {pct(f.get('worst')):>7}"
                  f" 近10年 {x['rec'].get('n', 0)}次 {pct(x['rec'].get('win'), 0)} 鄰近 {pct(x['grid_ok'], 0)}"
                  f" 亂排 {pct(x['luck'], 0)} 二項 {x['binom']}{'  ' + o if o else ''}"
                  f"{'  建議：' + S.REC_NAMES[x['rec_v']] if x['rec_v'] else ''}")
    if not a.no_write:
        print("\n[rare] 寫檔：", "已更新" if R.write(res) else "內容沒變")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
