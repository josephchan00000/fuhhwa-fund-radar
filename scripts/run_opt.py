#!/usr/bin/env python3
"""策略健檢與自我改良（docs/lab_selfopt_plan.md）：每週一重跑 → data/lab/opt_research.json（入庫）。

第一部分：v3 長歷史面板的回測參考（財報、月營收的每期報酬、持有路徑分位數表、逐筆進場特徵），每日健檢查表用。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import bt3d, health, store  # noqa: E402


def main() -> None:
    t0 = time.time()
    P = bt3d.Panel()
    doc = health.build_ref_file(P)
    store.write_json(health.REF_FILE, doc)
    print(f"[opt] 回測參考 {sorted(doc['ref'])}（資料到 {doc['asof']}）、{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
