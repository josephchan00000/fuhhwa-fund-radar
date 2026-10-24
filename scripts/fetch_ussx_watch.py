#!/usr/bin/env python3
"""美股三成每天的檢查（ussxspec VER 3；docs/lab_us_sleeve_plan.md 第 13.3 節）：最新一週紀錄的持股逐檔抓 Yahoo 日線，
收盤跌破 50 日線（買進以後曾經站上）→ 頁面提醒「下一個交易日開盤賣」。只是提醒，帳以每週重跑為準。
接著補美股個股卡要的資料（arm/lab/uscard.py；docs/lab_cfg_v2_plan.md 第 4 節）：配置頁美股列的股票的一年日線、
Yahoo 分析師預估與下次財報日（同一個美股收盤只抓一次；日線和上面的檢查共用同一次抓取）。

  TZ=Asia/Taipei python3 scripts/fetch_ussx_watch.py               # → data/lab/ussx_qm_watch.json、ussx_card.json（只在 CI；本容器擋 Yahoo）
  TZ=Asia/Taipei python3 scripts/fetch_ussx_watch.py --card-force  # 個股卡的資料全部重抓（CI 探針：lab_backfill.yml 的 uscard）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import uscard as UC  # noqa: E402
from arm.lab import ussxqm as QM  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--card-force", action="store_true", help="美股個股卡的資料不管這個收盤有沒有抓過都重抓")
    a = ap.parse_args()
    L = QM.load_live()
    fetch = UC.cached()
    if not (L.get("now") or {}).get("hold"):
        print("[美股三成] 還沒有每週紀錄的持股，不檢查")
    else:
        W = QM.watch(L, fetch=fetch)
        ch = QM.save_watch(W)
        print(f"[美股三成] 持股 {len(W['hold'])} 檔、資料到 {W.get('d')}（{'有更新' if ch else '沒有變'}）："
              + ("、".join(f"{x['c']} {x['trig']} 收盤跌破 50 日線→{x['on']} 開盤賣" for x in W["sell"]) or "沒有跌破 50 日線的"))
        for e in W["err"]:
            print(f"  ⚠ {e['c']}：{e['msg']}")
    try:
        print(UC.summary(UC.update(L, fetch=fetch, force=a.card_force)))
    except Exception as e:                                   # noqa: BLE001 —— 個股卡的資料抓不到不影響上面的檢查
        print(f"[美股個股卡] 失敗（{type(e).__name__}: {e}），沿用既有落檔")


if __name__ == "__main__":
    main()
