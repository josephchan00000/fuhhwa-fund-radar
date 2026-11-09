#!/usr/bin/env python3
"""自算台指選擇權 30 天隱含波動率 → data/lab/heat/txoiv.json.gz（arm/lab/txoiv.py；docs/lab_dims_plan.md 第 4 節）。

只讀資料分支的日行情（--root＝資料分支 checkout 的目錄，txo_data.yml 裡是 txodata/），不連外網。
  python3 scripts/run_txoiv.py --root txodata              # 每天：最近 2 個月重算、併進既有的檔
  python3 scripts/run_txoiv.py --root <目錄> --months 0    # 全部月份（2002 起）重算
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import heatdata as HD  # noqa: E402
from arm.lab import txodata as T  # noqa: E402
from arm.lab import txoiv as V  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--months", type=int, default=2, help="只重算最近幾個月（0＝全部）")
    a = ap.parse_args()
    root = Path(a.root)
    files = sorted(p.name for p in (root / "day").glob("*.json.gz"))
    if a.months:
        files = files[-a.months:]
    taiex = HD.load("taiex")
    cal = sorted(taiex)
    new: dict = {}
    for f in files:
        doc = T.read(root, f"day/{f}")
        if doc:
            new.update(V.month_series(doc, taiex, cal))
    if not new:
        print("[txoiv] 沒有算出任何一天")
        return 0
    old = HD.load("txoiv")
    n = sum(1 for k, v in new.items() if old.get(k) != v)
    if n:
        HD.save("txoiv", "txo-data+self", {**old, **new})
    ks = sorted({**old, **new})
    print(f"[txoiv] {len(files)} 個月、{len(new)} 天算出、{n} 天新增或改動；檔案 {ks[0]} ～ {ks[-1]}（{len(ks)} 天）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
