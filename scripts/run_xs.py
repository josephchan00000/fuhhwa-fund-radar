#!/usr/bin/env python3
"""大神策略（arm/lab/xstratspec.py、arm/lab/xstrat.py）的成績摘要：印出每個市場每個策略的判定與主要數字。

  TZ=Asia/Taipei python3 scripts/run_xs.py
頁面每天建頁時自己算（只用指數收盤與 VIX，幾秒），不另存研究檔；這支只是給人看、寫文件用。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import xstrat as X  # noqa: E402
from arm.lab import xstratspec as S  # noqa: E402


def _p(v, d=1, sign=False):
    if v is None:
        return "—"
    return f"{v * 100:+.{d}f}%" if sign else f"{v * 100:.{d}f}%"


def main() -> None:
    t0 = time.time()
    R = X.run_all(force=True)
    print(f"[xs] VER {S.VER}，{time.time() - t0:.1f}s")
    for mk in S.MARKETS:
        print(f"===== {S.NAMES[mk]}")
        for k, r in (R.get(mk) or {}).items():
            f, rc = r["full"], r["rec"]
            mark = S.TIER_MARK[r["tier"]]
            if r["kind"] == "trade":
                print(f"  {mark} {S.BY_KEY[k]['name']}：{f['n']} 筆 勝率 {_p(f['win'])}（隨便挑 {_p(f['base'])}）平均 {_p(f['avg'], 2, True)}｜"
                      f"近 10 年 {rc.get('n', 0)} 筆 {_p(rc.get('win'))}（{_p(rc.get('base'))}）｜鄰近 {r['grid_ok']:.2f}｜現在 {r['now']['st']}")
            else:
                b, br = r["bh"], r["bh_r"]
                print(f"  {mark} {S.BY_KEY[k]['name']}：年化 {_p(f['cagr'])}（{_p(b['cagr'])}）回撤 {_p(f['mdd'], 0)}（{_p(b['mdd'], 0)}）｜"
                      f"近 10 年 {_p(rc['cagr'])}（{_p(br['cagr'])}）回撤 {_p(rc['mdd'], 0)}（{_p(br['mdd'], 0)}）｜鄰近 {r['grid_ok']:.2f}｜現在 {r['now']['st']}")


if __name__ == "__main__":
    main()
