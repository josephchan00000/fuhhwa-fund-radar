"""台股早年官方每日行情回補（arm/lab/twearly.py；docs/lab_earnings_plan.md 第 14 節第 1 段）。只在 CI 跑（本容器擋證交所、櫃買）。

用法：python3 scripts/backfill_twearly.py [--budget 秒] [--only tw|tp] [--cov]
可以重跑續補；--cov 只印每年的涵蓋情形。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    from arm.lab import twearly as E
    a = sys.argv[1:]
    if "--cov" not in a:
        budget = float(a[a.index("--budget") + 1]) if "--budget" in a else 9000
        mk = (a[a.index("--only") + 1],) if "--only" in a else ("tw", "tp")
        print("[早年行情] 這一輪", json.dumps(E.run(budget, mk), ensure_ascii=False))
    for k, v in E.coverage().items():
        print(f"  {k}：{json.dumps(v, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
