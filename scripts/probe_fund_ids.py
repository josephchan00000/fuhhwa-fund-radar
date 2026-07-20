"""一次性診斷：掃 /api/fund 的 fundID 區間，印出各 id 實際對到哪支基金。

背景：創新指數傘型三檔新基金（2026-06-22 開募）中，133/135 為相鄰檔號推定
（假設 AI 動力有美元級別），CI 實跑回 NoData——需用 CI 的完整網路確認真實 id。
只讀不寫，跑完即可從日誌讀結果。
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
