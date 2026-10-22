"""交易計畫（planspec VER 1）：算一次、印摘要（每天建頁時策略頁自己算，這支只給規劃文件與核對用）。

  TZ=Asia/Taipei python3 scripts/run_plan.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import plan as PN  # noqa: E402
from arm.lab import tilt as TL  # noqa: E402

B = PN.build()
TR = TL.load()
for mk, M in B["mk"].items():
    print(f"== {mk} ({M['d']})")
    for p in ("def", "atk"):
        X = M.get(p)
        if not X:
            continue
        pa = X["past"]
        print(f"  [{p}] {pa['a']}～{pa['z']} 年化 {pa['cagr']:.4f} 最大回撤 {pa['mdd']:.4f} 最差一年 {pa['worst']:.4f} "
              f"100萬→{pa['man'] * 100:,.0f}萬（一直抱著 {pa['bman'] * 100:,.0f}萬）")
        if pa.get("yr"):
            print("      一年：", json.dumps(pa["yr"], ensure_ascii=False))
        if pa.get("fut"):
            fu = pa["fut"]
            ref = (TR["mk"][mk]["rules"]["K4"]["man"]) / 1e6
            print(f"      期貨部位：{fu['n']} 段，最差一段 {fu['worst']:.4f}（{fu['wa']}～{fu['wz']}，最低點 {fu['wt']}），"
                  f"最差一天 {fu['day']:.4f}（{fu['dday']}）")
            print(f"      核對：重算的淨值 {pa['man']:.4f} vs 研究檔 {ref:.4f}")
        print("      現在：", json.dumps(X["now"], ensure_ascii=False))
        print("      前瞻：", json.dumps(X["live"], ensure_ascii=False))
    if M.get("bh"):
        print("  沒有可以照做的：", M["bh"])
