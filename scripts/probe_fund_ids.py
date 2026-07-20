"""診斷工具：掃 /api/fund 的 fundID 區間，印出各 id 實際對到哪支基金。

新基金檔號不保證比舊檔大（2026-07-20 實例：菁英50=126、AI動力=128，比同梯
創新金融 131 小），相鄰推定不可靠；新增基金 NoData 時用本掃描確認真實 id。
容器 proxy 連不上 fhtrust——由 .github/workflows/probe_fund_ids.yml 借 CI 網路跑，
只讀不寫，結果從 CI 日誌讀。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm.connectors import fhfund  # noqa: E402

LO, HI = 125, 145

for fid in range(LO, HI + 1):
    try:
        meta = fhfund.fetch_meta(fid)
        print(f"  {fid}: {meta.get('name')}｜NAV {meta.get('nav')} ({meta.get('nav_date')})｜成立 {meta.get('inception')}")
    except fhfund.NoData:
        print(f"  {fid}: （無資料）")
    except Exception as e:  # 網路/解析異常也照印，不中斷掃描
        print(f"  {fid}: 錯誤 {type(e).__name__}: {e}")
