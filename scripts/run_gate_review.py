#!/usr/bin/env python3
"""新項目過關每年重驗（arm/lab/gatereview.py）：用現在的資料重算過關判定，寫 data/lab/heat_gate_review.json。

不改現行過關檔與研究檔；名單有變時推播一行、研究紀錄・後台列出，使用者回「好」才重跑整套研究換上。
每年 1 月由 .github/workflows/gate_review.yml 跑；手動：TZ=Asia/Taipei python3 scripts/run_gate_review.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.clock import now_tw  # noqa: E402
from arm.lab import gatereview as R  # noqa: E402
from arm.lab import store  # noqa: E402


def main() -> int:
    t0 = time.time()
    doc = R.run(now_tw())
    store.write_json(R.REVIEW_FP, doc)
    st = R.state(now_tw(), doc)
    print(f"[gate-review] {doc['made']}：名單{'有變' if doc['changed'] else '沒變'}，{time.time() - t0:.0f} 秒", flush=True)
    for s in R.summary(st) if st else []:
        print("  ", s, flush=True)
    print(f"[gate-review] 寫 data/lab/{R.REVIEW_FP}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
