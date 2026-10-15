#!/usr/bin/env python3
"""回測方法 v3：長歷史樣本內外結果 → data/lab/bt3_research.json（頁面「策略」分頁讀）。

只在資料或規則改了才需要重跑（docs/backtest_v3_plan.md 第 11～13 節）；容器內約 4 分鐘。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import bt3d, bt3l, store  # noqa: E402


def main() -> None:
    t0 = time.time()
    P = bt3d.Panel()
    main_ = bt3l.run(P)
    t5 = bt3l.top5(P)
    doc = bt3l.export(main_, t5, P)
    store.write_json("bt3_research.json", doc)
    print(f"[bt3] {len(doc['rows'])} 列、列入本期操作 {doc['list']}、{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
