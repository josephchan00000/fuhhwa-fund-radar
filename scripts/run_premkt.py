#!/usr/bin/env python3
"""盤前作戰圖 → data/lab/premkt.json（arm/lab/premkt.py；docs/lab_premarket_plan.md）。只讀已存的資料、不連網，容器裡也能跑。
夜盤要先由 scripts/fetch_night.py（CI）抓進 data/lab/fut/night.json。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm import clock  # noqa: E402
from arm.lab import pmreview as R  # noqa: E402
from arm.lab import premkt as P  # noqa: E402

if __name__ == "__main__":
    pm = P.write()
    if pm is None:
        print("[premkt] 資料不夠（沒有 5 秒指數或收盤），沒寫")
        raise SystemExit(0)
    print(f"[premkt] {pm['d']} → {pm['next']}：{pm['push']}" + (f"（{'；'.join(pm['warn'])}）" if pm["warn"] else ""))
    try:                                                  # 自我檢討（arm/lab/pmrevspec.py；失敗不擋盤前作戰圖）
        log = R.run(pm, clock.now_tw())
        print(f"[pmreview] 公布 {len(log['pub'])} 天、檢討 {len(log['rev'])} 天：{R.push_line(log, max(log['rev'])) if log['rev'] else '—'}")
    except Exception as e:                                # noqa: BLE001
        print(f"[pmreview] 檢討沒算出來：{type(e).__name__}: {e}")
