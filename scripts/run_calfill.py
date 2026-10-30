#!/usr/bin/env python3
"""行事曆官方自動補值（arm/calfill.py；docs/macrocal_fill_plan.md 第二、三段）。

CI 每一班抓完官方資料之後、重建儀表板之前跑：TZ=Asia/Taipei python3 scripts/run_calfill.py
  最新一份 reports/macrocal/*.md 裡日期已到、實際值空白的列，對得上官方序列就補上；
  已填而和官方不同的只在「註」加一行「官方核對」。不擋發佈（永遠 exit 0）。
  先看有沒有列在等只有行事曆用的來源（勞工統計局非農等、歐洲央行、主計總處 GDP 年增；calfill.wanted），
  本機還沒有那一期才連網抓（arm/calsrc.py），其他只讀本機落檔。
  --dry：只印、不抓、不寫檔。--no-fetch：不抓（盤後那支 push 被拒重試時用，剛才已經抓過）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm import calfill as CF  # noqa: E402
from arm import calsrc  # noqa: E402
from arm.clock import now_tw, today_tw  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只印、不抓、不寫檔")
    ap.add_argument("--no-fetch", action="store_true", help="不連網抓（只用本機落檔）")
    a = ap.parse_args()
    try:
        today = today_tw()
        got = CF.latest(CF.MN.CAL_DIR, today)
        keys = CF.wanted(got[0].read_text(encoding="utf-8"), got[1], today) if got else set()
        if keys and not (a.dry or a.no_fetch):
            for line in calsrc.fetch(keys, today):
                print(f"[calfill] 抓 {line}")
        elif keys:
            print(f"[calfill] 有列在等 {'、'.join(sorted(keys))}（這次不抓）")
        r = CF.run(today, now_tw(), write=not a.dry)
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
        tag = {"fill": "補值", "mismatch": "⚠ 和官方不同（不覆寫）", "prev": "⚠ 前值已被官方修正（不覆寫）"}[x["kind"]]
        old = f"；表中「{x['actual']}」" if x["kind"] != "fill" else ""
        seen = "" if x.get("new", True) else "（註裡已有）"
        print(f"[calfill] {name} {tag}：{x['item']} → {x['value']}（{x['src']}）{old}{seen}")
    if r.get("wrote"):
        print(f"[calfill] 已寫入 {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
