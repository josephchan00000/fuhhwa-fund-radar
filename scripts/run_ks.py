#!/usr/bin/env python3
"""策略熔斷（arm/lab/ks.py、ksspec）：算回測門檻寫進 data/lab/ks_bounds.json（同一份、同一版規格已經有就不覆蓋）。

  TZ=Asia/Taipei python3 scripts/run_ks.py --bounds tw                    # 台股新飆股、財報驚喜（大型股）
  USSX_DIR=… TZ=Asia/Taipei python3 scripts/run_ks.py --bounds us         # 美股強勢品質股（資料分支）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.clock import today_tw  # noqa: E402
from arm.lab import ks  # noqa: E402


def _show(k: str, b: dict) -> None:
    print(f"  {k}：回測 {b['a']}～{b['b']}（{b['n']} 天）落後最深 {b['dd_bt'] * 100:.1f}%（{'→'.join(b.get('dd_at', []))}）"
          f" → 熔斷邊界 {b['dd'] * 100:.1f}%；最久 {b['uw_bt']} 個交易日沒追上（{'→'.join(b.get('uw_at', []))}）→ 標示 {b['uw']} 天")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bounds", choices=("tw", "us"), required=True)
    a = ap.parse_args()
    new = {}
    if a.bounds == "tw":
        bench = ks.tw_bench()
        d, n = ks.bt_boom()
        new["tw_boom"] = ks.bounds_of(d, n, bench)
        d, n = ks.bt_v3l()
        new["tw_v3l"] = ks.bounds_of(d, n, bench)
    else:
        from arm.lab import ussxqm as QM
        C = QM.context()
        d, n, bench = ks.bt_qm(C)
        new["us_qm"] = ks.bounds_of(d, n, bench)
    for k, b in new.items():
        _show(k, b)
    doc = ks.save_bounds(new, today_tw().isoformat())
    print(f"[ks] 寫入 data/lab/{ks.K.BOUNDS_FILE}：{sorted(doc['slices'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
