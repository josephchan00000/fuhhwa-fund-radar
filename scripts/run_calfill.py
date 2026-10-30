#!/usr/bin/env python3
"""行事曆官方自動補值（arm/calfill.py；docs/macrocal_fill_plan.md 第二段）。

CI 每一班抓完官方資料之後、重建儀表板之前跑：TZ=Asia/Taipei python3 scripts/run_calfill.py
  最新一份 reports/macrocal/*.md 裡日期已到、實際值空白的列，對得上專案已在抓的官方序列就補上；
  已填而和官方不同的只在「註」加一行「官方核對」。只讀本機落檔、不連網、不擋發佈（永遠 exit 0）。
  --dry：只印、不寫檔。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm import calfill as CF  # noqa: E402
from arm.clock import now_tw, today_tw  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只印、不寫檔")
    a = ap.parse_args()
    try:
        r = CF.run(today_tw(), now_tw(), write=not a.dry)
    except Exception as e:                                    # noqa: BLE001 —— 不擋發佈
        print(f"[calfill] ✗ {type(e).__name__}: {str(e)[:200]}")
        return 0
    if not r["file"]:
        print("[calfill] 沒有行事曆檔")
        return 0
    name = Path(r["file"]).name
    if not r["acts"]:
        print(f"[calfill] {name}：沒有可補的列")
    for x in r["acts"]:
        tag = "補值" if x["kind"] == "fill" else "⚠ 和官方不同（不覆寫）"
        old = f"；表中「{x['actual']}」" if x["kind"] == "mismatch" else ""
        print(f"[calfill] {name} {tag}：{x['item']} → {x['value']}（{x['src']}）{old}")
    if r.get("wrote"):
        print(f"[calfill] 已寫入 {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
