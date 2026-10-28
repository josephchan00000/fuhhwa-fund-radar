#!/usr/bin/env python3
"""美股個股卡的季報摘要（arm/lab/usfin.py；docs/lab_review_plan.md 第 4 節 (b)(c)）：每週六資料分支的 SEC 財報更新以後跑。

  USSX_DIR=<資料分支>/data/lab/ussx TZ=Asia/Taipei python3 scripts/run_usfin.py   # → data/lab/ussx_fin.json
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import usfin as UF  # noqa: E402
from arm.lab import ussxqm as QM  # noqa: E402


def main() -> None:
    L = QM.load_live()
    if not (L.get("now") or {}).get("list"):
        print("[美股季報] 還沒有每週紀錄，不算")
        return
    doc = UF.build(L)
    miss = [c for c in doc["codes"] if c not in doc["s"]]
    ch = UF.save(doc)
    print(f"[美股季報] SEC {doc.get('sec')}：{len(doc['s'])}／{len(doc['codes'])} 檔有季報（{'有更新' if ch else '沒有變'}）"
          + (f"；沒有：{'、'.join(miss)}" if miss else ""))


if __name__ == "__main__":
    main()
