#!/usr/bin/env python3
"""盤前作戰圖 → data/lab/premkt.json（arm/lab/premkt.py；docs/lab_premarket_plan.md）。只讀已存的資料、不連網，容器裡也能跑。
夜盤要先由 scripts/fetch_night.py（CI）抓進 data/lab/fut/night.json。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.lab import premkt as P  # noqa: E402

if __name__ == "__main__":
    pm = P.write()
    if pm is None:
        print("[premkt] 資料不夠（沒有 5 秒指數或收盤），沒寫")
        raise SystemExit(0)
    print(f"[premkt] {pm['d']} → {pm['next']}：{pm['push']}" + (f"（{'；'.join(pm['warn'])}）" if pm["warn"] else ""))
