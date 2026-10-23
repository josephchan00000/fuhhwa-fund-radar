#!/usr/bin/env python3
"""交易計畫（核心 70%＋衛星 30%）的回測（corespec VER 1；docs/lab_core70_plan.md 第 9～10 節）→ data/lab/core_research.json。

  TZ=Asia/Taipei python3 scripts/run_core.py
資料或規格改了才重跑；每天建頁只讀研究檔（現在的讀數每天在景氣頁建頁時算）。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import core  # noqa: E402


def _w(m: float) -> str:
    return f"{m * 100:,.0f} 萬"


def main() -> None:
    t0 = time.time()
    R = core.research()
    changed = core.save(R)
    for mk, M in R["mk"].items():
        for key, s in M["sc"].items():
            p, h, f = s["plan"], s["hold"], s["fixed"]
            print(f"{mk:4} {key:6} {s['a']}～{s['b']}  照計畫 {_w(p['m'])} 年化 {p['cagr'] * 100:5.1f}% 最慘 {p['mdd'] * 100:3.0f}% "
                  f"最差年 {(p['worst'] or 0) * 100:6.1f}%｜一直抱著 {_w(h['m'])} {h['cagr'] * 100:5.1f}% 最慘 {h['mdd'] * 100:3.0f}% "
                  f"最差年 {(h['worst'] or 0) * 100:6.1f}%｜固定 {_w(f['m'])}｜平均部位 {s['avg'] * 100:.0f}% 一年動 {s['sw']:.1f} 次")
            print("        前半", _w(s["halves"][0]["plan"]["m"]), "vs", _w(s["halves"][0]["hold"]["m"]),
                  "後半", _w(s["halves"][1]["plan"]["m"]), "vs", _w(s["halves"][1]["hold"]["m"]),
                  f"近 10 年 {_w(s['recent']['plan']['m'])} vs {_w(s['recent']['hold']['m'])}"
                  f"（最慘 {s['recent']['plan']['mdd'] * 100:.0f}% vs {s['recent']['hold']['mdd'] * 100:.0f}%）")
            if p.get("q"):
                print(f"        12 個月 最差一成／中位／最好一成 {p['q'][0] * 100:5.1f}／{p['q'][1] * 100:5.1f}／{p['q'][2] * 100:5.1f}% "
                      f"虧 {p['loss'] * 100:.0f}%｜抱著 {h['q'][0] * 100:5.1f}／{h['q'][1] * 100:5.1f}／{h['q'][2] * 100:5.1f}% 虧 {h['loss'] * 100:.0f}%"
                      f"｜去掉最好一年 {(p.get('ex_best') or 0) * 100:.1f}% vs {(h.get('ex_best') or 0) * 100:.1f}%")
            win = sum(1 for (y, r, n), (_, rh, _) in zip(p["years"], h["years"]) if n >= 120 and r > rh)
            tot = sum(1 for y in p["years"] if y[2] >= 120)
            print(f"        贏的年份 {win}／{tot}；換現金 {len(s['eps'])} 段")
    print("研究檔", "已更新" if changed else "沒有變更", core.RES, f"（{time.time() - t0:.0f}s）")


if __name__ == "__main__":
    main()
