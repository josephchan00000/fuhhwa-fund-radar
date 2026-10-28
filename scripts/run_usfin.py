#!/usr/bin/env python3
"""美股個股卡的季報摘要（arm/lab/usfin.py；docs/lab_review_plan.md 第 4 節 (b)(c)）：每週六資料分支的 SEC 財報更新以後跑。

  USSX_DIR=<資料分支>/data/lab/ussx TZ=Asia/Taipei python3 scripts/run_usfin.py   # → data/lab/ussx_fin.json（CI 先更新 ussx_gics.json）
  TZ=Asia/Taipei python3 scripts/run_usfin.py --gics-only                         # 只抓 GICS 細產業（CI 探針：lab_backfill.yml 的 usgics）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os  # noqa: E402

from arm.lab import usfin as UF  # noqa: E402


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gics-only", action="store_true")
    a = ap.parse_args()
    if os.environ.get("GITHUB_ACTIONS"):                    # 本容器擋 wikipedia：只在 CI 更新
        print(f"[美股季報] GICS 細產業：{UF.update_gics()}")
    if a.gics_only:
        return
    from arm.lab import ussxqm as QM                       # 要 numpy（每週那一支有裝）
    L = QM.load_live()
    if not (L.get("now") or {}).get("list"):
        print("[美股季報] 還沒有每週紀錄，不算")
        return
    doc = UF.build(L, name_fetch=None if os.environ.get("GITHUB_ACTIONS") else (lambda: {}))   # 本容器擋那斯達克
    miss = [c for c in doc["codes"] if c not in doc["s"]]
    ch = UF.save(doc)
    npr = sum(1 for x in doc["s"].values() if x.get("peer"))
    print(f"[美股季報] SEC {doc.get('sec')}：{len(doc['s'])}／{len(doc['codes'])} 檔有季報、{npr} 檔有同產業比較"
          f"（篩選器 {doc.get('scr')}，公司名 {len(doc.get('names') or {})} 家；{'有更新' if ch else '沒有變'}）"
          + (f"；沒有：{'、'.join(miss)}" if miss else ""))


if __name__ == "__main__":
    main()
