#!/usr/bin/env python3
"""從 git 歷史回填基金 NAV 序列 → data/fund_nav_history.json（冪等，可重跑）。

原理：CI 每日 commit data/funds/_index.json（含每檔 nav＋nav_date），
走 `git log -- data/funds/_index.json` 逐 commit 取快照即可重建序列；
最後再併入目前工作區的 data/funds/*.json。日常累積由
scripts/fetch_holdings.py 內建的 fundnav.record() 負責，本腳本只在
初始化或斷史時使用。

用法：python3 scripts/backfill_fund_nav.py
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import fundnav  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INDEX = "data/funds/_index.json"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=False).stdout


def run() -> None:
    shas = _git("log", "--format=%H", "--", INDEX).split()
    print(f"[NAV 回填] {INDEX} 歷史 {len(shas)} 個 commit")
    hist = fundnav.load()
    before = sum(len(s) for s in hist.values())
    for sha in reversed(shas):                      # 舊→新，後值覆蓋前值
        raw = _git("show", f"{sha}:{INDEX}")
        if not raw.strip():
            continue
        try:
            snap = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for f in (snap.get("funds") or []):
            fid, nav = str(f.get("id") or ""), f.get("nav")
            d = fundnav._parse_date(f.get("nav_date"))
            if fid and nav is not None and d is not None:
                hist.setdefault(fid, {})[d.strftime("%Y/%m/%d")] = float(nav)
    # 併入目前工作區快照（可能比最後一個 commit 新）
    for p in sorted((ROOT / "data" / "funds").glob("[0-9]*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        fid, nav = str(doc.get("fund_id") or ""), doc.get("nav")
        d = fundnav._parse_date(doc.get("nav_date"))
        if fid and nav is not None and d is not None:
            hist.setdefault(fid, {})[d.strftime("%Y/%m/%d")] = float(nav)
    fundnav.save(hist)
    after = sum(len(s) for s in hist.values())
    days = sorted({d for s in hist.values() for d in s})
    print(f"  ✓ {len(hist)} 檔基金、共 {after} 筆（新增 {after - before}）；"
          f"NAV 日範圍 {days[0] if days else '—'} ~ {days[-1] if days else '—'}")


if __name__ == "__main__":
    run()
