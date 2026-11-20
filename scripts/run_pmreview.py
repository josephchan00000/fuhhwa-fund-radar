#!/usr/bin/env python3
"""盤前自我檢討（arm/lab/pmreview.py；規格 arm/lab/pmrevspec.py）。

    python3 scripts/run_pmreview.py              # 用現有紀錄重算檢討、印推播那一行
    python3 scripts/run_pmreview.py --backfill   # 第一次：從 git 歷史找每一天 08:45 以前最後公布的 premkt.json，補進「公布的那一版」

每天的記錄由 scripts/run_premkt.py 順手做（CI）；這支只在第一次補歷史、或手動看結果時用。只讀 repo、不連網。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.lab import pm850  # noqa: E402
from arm.lab import pmreview as R  # noqa: E402
from arm.lab import pmrevspec as S  # noqa: E402


def backfill(log: dict, ref: str) -> int:
    rows = subprocess.run(["git", "log", ref, "--format=%H %cd", "--date=format-local:%Y-%m-%d %H:%M", "--", "data/lab/premkt.json"],
                          capture_output=True, text=True, cwd=ROOT, env={"TZ": "Asia/Taipei", "PATH": "/usr/bin:/bin"}).stdout.splitlines()
    best: dict[str, tuple[str, dict]] = {}
    for line in rows:
        h, t = line.split(" ", 1)
        try:
            pm = json.loads(subprocess.run(["git", "show", f"{h}:data/lab/premkt.json"], capture_output=True, text=True, cwd=ROOT).stdout)
        except ValueError:
            continue
        d = pm.get("next")
        if not d or t >= f"{d} {S.FREEZE}":
            continue
        if d not in best or t > best[d][0]:
            best[d] = (t, pm)
    n = 0
    for d, (t, pm) in sorted(best.items()):
        s = R.snap(pm)
        if s and d not in log["pub"]:
            log["pub"][d] = s
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--ref", default="HEAD")
    a = ap.parse_args()
    log = R.read()
    if a.backfill:
        print(f"[pmreview] 從 git 歷史補了 {backfill(log, a.ref)} 天")
    try:
        e850 = json.loads(pm850.LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e850 = {}
    R.update(log, e850)
    R.write(log)
    s = log["sum"]
    print(f"[pmreview] 公布 {len(log['pub'])} 天、檢討 {len(log['rev'])} 天；近 {s.get('n')} 天：{json.dumps(s, ensure_ascii=False)}")
    if log["rev"]:
        print(R.push_line(log, max(log["rev"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
