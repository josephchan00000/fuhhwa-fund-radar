"""盤前第 5 段：用台指期 08:45 開盤重估 09:01 加權指數（pmestspec VER 1；docs/lab_premarket_plan.md 第 16 節）。
2026-11-12 寫定、算任何成績之前 commit。

為什麼：頁面的預估開盤用清晨 05:00 收盤的夜盤（premktspec Q1 的 E1），05:00～09:00 之間的消息與亞洲盤都沒算進去；
11/5、11/6、11/11 估錯 769、982、682 點。台指期日盤 08:45 就開始交易，比 09:00 現貨早 15 分鐘，
如果用 08:45 的價格重估更準，就在 08:50 左右多更新一次頁面（使用者 2026-11-12 回「好」：先驗、真的比較準才加排程）。

共同
  日子＝有 5 秒指數、夜盤、期貨日盤開盤與前一天收盤、正常波動的交易日，FIRST 起（事前只數了天數：2,310 天）。
  契約 k＝夜盤（交易日期＝當天）成交量最大的契約（同 pmval.night_k）；C＝前一天加權指數收盤。
  E1（現在頁面的）＝C＋（k 的夜盤最後價 − k 前一天日盤收盤）。
  E2（新的）＝C＋（k 當天日盤開盤價（08:45 開盤那一筆）− k 前一天日盤收盤）。
  N（對照）＝C。
  目標 O＝09:01:00 的 5 秒指數（第 OPEN_T 個，同 premktspec）。誤差 e＝O − 估計；em＝正常波動（同 premktspec）。
  列 |e| 中位數、80 百分位（點與 em 倍數）、e 的平均（偏差）；依日期切前後兩半各列中位數。

判定
  E2 的 |e| 中位數比 E1 小至少 MIN_GAIN（相對），而且前後兩半都比 E1 小 → 過：頁面在 08:50 前後用 E2 更新一次「預估 09:01」與八成範圍
  （八成範圍＝E2 的 |e|/em 80 百分位 × 今天的 em）；沒過 → 不加排程，頁面照舊。

只列（不判定）
  E1 估錯很大的日子（|e1| > E1 的 80 百分位）裡，E2 把誤差縮小一半以上的比例；
  有存逐筆的日子（約 30～40 天）用 08:50:00 那一刻的台指期價（E3＝C＋（08:50 價 − 前一天 13:30 價））的誤差。
要改＝VER＋1，不在看過結果之後改這一版。
"""
from __future__ import annotations

import hashlib
import json

VER = 1
SPEC_DATE = "2026-11-12"

FIRST = "2017-05-16"
OPEN_T = 12
TRADING_YEAR = 252
MIN_GAIN = 0.10
E3_T = 8 * 3600 + 50 * 60      # 08:50:00（秒）


def fingerprint() -> str:
    """規格常數的指紋（tests 鎖住；改任何一個都要 VER＋1）。"""
    keys = sorted(k for k, v in globals().items() if k.isupper() and not callable(v))
    blob = json.dumps({k: globals()[k] for k in keys}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
