#!/usr/bin/env python3
"""O4 結算均價的紙上紀錄（arm/lab/o4live.py；docs/lab_txo_plan.md 第 21 節）。只讀資料分支、不抓任何東西。

  python3 scripts/run_o4live.py --root <資料分支 claude/txo-data 的 checkout>    # → data/lab/txo_o4_live.json（只增不改）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm import clock, fileio  # noqa: E402
from arm.lab import o4live as L  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="資料分支 claude/txo-data 的 checkout")
    ap.add_argument("--out", default=str(L.LIVE))
    a = ap.parse_args()
    out = Path(a.out)
    try:
        led = json.loads(out.read_text(encoding="utf-8")) if out.exists() else L.new_book()
    except ValueError:
        print(f"[O4 紙上紀錄] {out} 讀不進來，不覆寫（只增不改）", flush=True)
        return 1
    old = {d: json.dumps(v, sort_keys=True) for d, v in (led.get("days") or {}).items()}
    L.update(Path(a.root).resolve(), led, clock.today_tw().isoformat())
    if any(json.dumps(led["days"].get(d), sort_keys=True) != v for d, v in old.items()):
        print("[O4 紙上紀錄] 舊的日子被改了，不寫（只增不改）", flush=True)
        return 1
    s = L.summarize(led)
    fileio.write_text(out, json.dumps(led, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=float) + "\n")
    m = s["metrics"]
    print(f"[O4 紙上紀錄] {len(s['days'])} 個結算日、{m.get('n', 0)} 筆、合計 {m.get('total', 0):,.0f} 元；{s['judge']['verdict']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
