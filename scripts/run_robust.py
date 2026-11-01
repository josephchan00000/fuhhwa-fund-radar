#!/usr/bin/env python3
"""參數鄰近檢查（arm/lab/nbrspec.py VER 1；docs/lab_signal_quality_plan.md 第 12 節）→ data/lab/robust_research.json。

  TZ=Asia/Taipei python3 scripts/run_robust.py
只讀已入庫的資料（不抓資料）；原本參數的重算要和 data/lab/sig_research.json 一模一樣，不一樣就停。研究檔改了（run_sig.py）才要重跑。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sigcat as G  # noqa: E402
from arm.lab import sigrobust as R  # noqa: E402


def main() -> None:
    t0 = time.time()
    log = lambda s: print(f"{s}（{time.time() - t0:.0f}s）", flush=True)   # noqa: E731
    base = R.base_data()
    log("[robust] 原本的資料")
    rows = (G.load_research() or {}).get("rows") or []
    if not rows:
        sys.exit("[robust] 沒有訊號總覽研究檔（先跑 scripts/run_sig.py）")
    out = R.run(base, rows, log)
    out["impact"] = R.impact(base, rows, out["rows"])
    R.save(out)
    log(f"[robust] 寫入 {R.OUT}（{R.OUT.stat().st_size // 1024} KB）")
    for cat, c in sorted(out["summary"].items()):
        print(f"  {cat}: 穩定 {c['ok']}、只在這個參數成立 {c['bad']}、看不出來 {c['na']}；不穩定的參數 {c['dims']}")
    for mk, m in out["impact"].items():
        print(f"  {mk}: 今天的重點 偏多 {m['n0']['up']}→{m['n1']['up']}、警示 {m['n0']['warn']}→{m['n1']['warn']}；"
              f"少掉 {len(m['gone'])} 個、變成別人那一類的 {len(m['lead'])} 個")


if __name__ == "__main__":
    main()
