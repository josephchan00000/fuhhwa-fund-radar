"""選擇權作戰表（arm/lab/txocalc.py；docs/lab_txo_plan.md 第 17 節）：讀資料分支最新一天的日行情與 5 秒指數，寫 data/lab/txo_calc.json。
只在 CI 跑（.github/workflows/txo_data.yml 存完資料之後）；容器裡沒有資料分支的檔。

  python3 scripts/run_txocalc.py --root txodata --out data/lab/txo_calc.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm.clock import today_tw  # noqa: E402
from arm.lab import txocalc as C  # noqa: E402
from arm.lab import txodata as T  # noqa: E402


def latest(root: Path, today):
    for i in range(0, 15):
        d = today - timedelta(days=i)
        idx = T.read(root, f"idx/{d.year}/{d.isoformat()}.json.gz")
        day = T.read(root, f"day/{d:%Y-%m}.json.gz")
        if not idx or not day:
            continue
        rows = [r for r in day.get("rows", []) if r[0] == d.isoformat()]
        if rows and idx.get("v"):
            return d, rows, sum(idx["v"]) / 100
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default=str(ROOT / "data/lab/txo_calc.json"))
    a = ap.parse_args()
    got = latest(Path(a.root).resolve(), today_tw())
    if not got:
        print("[txocalc] 最近 15 天找不到同時有日行情與 5 秒指數的日子，不改檔", flush=True)
        return 0
    d, rows, close = got
    doc = C.build(rows, close, d)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if out.exists() and out.read_text(encoding="utf-8") == txt:
        print(f"[txocalc] {d} 沒變", flush=True)
        return 0
    out.write_text(txt, encoding="utf-8")
    print(f"[txocalc] {d} 收盤 {close:,.2f}，下一個交易日 {doc['next']}，{len(doc['exps'])} 批到期，正常波動 ±{doc['em']} 點", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
