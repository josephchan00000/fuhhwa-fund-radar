#!/usr/bin/env python3
"""美股三成每天的檢查（ussxspec VER 3；docs/lab_us_sleeve_plan.md 第 13.3 節）：最新一週紀錄的持股逐檔抓 Yahoo 日線，
收盤跌破 50 日線（買進以後曾經站上）→ 頁面提醒「下一個交易日開盤賣」。只是提醒，帳以每週重跑為準。

  TZ=Asia/Taipei python3 scripts/fetch_ussx_watch.py     # → data/lab/ussx_qm_watch.json（只在 CI；本容器擋 Yahoo）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import ussxqm as QM  # noqa: E402


def main() -> None:
    L = QM.load_live()
    if not (L.get("now") or {}).get("hold"):
        print("[美股三成] 還沒有每週紀錄的持股，不檢查")
        return
    W = QM.watch(L)
    ch = QM.save_watch(W)
    print(f"[美股三成] 持股 {len(W['hold'])} 檔、資料到 {W.get('d')}（{'有更新' if ch else '沒有變'}）："
          + ("、".join(f"{x['c']} {x['trig']} 收盤跌破 50 日線→{x['on']} 開盤賣" for x in W["sell"]) or "沒有跌破 50 日線的"))
    for e in W["err"]:
        print(f"  ⚠ {e['c']}：{e['msg']}")


if __name__ == "__main__":
    main()
