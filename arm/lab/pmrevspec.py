"""盤前自我檢討的規格（docs/lab_premarket_plan.md 第 17 節）。

使用者 2026-11-20：「我希望你在每日排程的時候可以加入一塊自我檢討，看一下預測為什麼不準，提供優化想法驗證，但不要消耗過多 token」。
做法：檢討全部由 CI 照這份規格算（不花 Claude 的 token），結果寫成一行推播（06:35 那班照貼）和選擇權頁盤前分頁的一塊。

VER 1（2026-11-20，任何檢討數字算出來之前寫定；改＝VER＋1，不改舊版）
1. 記「公布的那一版」：盤前作戰圖每次重算，都更新「下一個交易日」那一天的紀錄，到那一天 FREEZE（08:45）為止，之後不再改。
   記：清晨估的 09:01（est）、正常波動（em）、平常差（typ）、八成範圍（p80）、上下的壓力支撐帶（lo、hi、今天碰到的比例）。
   08:46 重估照舊記在 data/lab/fut/e850.json（arm/lab/pm850.py）。
2. 實際：那一天 09:01 的 5 秒指數（premktspec.OPEN_T）、09:00:05 起的最高、最低。
3. 每天的檢討：
   - 差＝實際 − 清晨估；倍數＝|差| ÷ em；在八成範圍內＝|差| ≤ p80。
   - 有 08:46 重估時拆兩段：「夜盤收盤後到 08:45」＝重估 − 清晨估；「08:45 到 09:01」＝實際 − 重估。主因＝絕對值大的那一段。
   - 當天晃動 ÷ 正常波動＝（最高 − 最低）÷ em。
   - 帶子碰到＝當天最低 ≤ 帶子上緣，而且最高 ≥ 帶子下緣。
4. 近 N 個有紀錄的交易日（不夠 N 天就用有的、照寫天數）：八成範圍包住幾天；|差| ÷ em 的中位數；
   帶子碰到：頁面說的平均 vs 實際碰到的比例；當天晃動 ÷ 正常波動的中位數。
5. 警示（照順序，最多寫兩條；天數不到 MIN_DAYS 不警示）：
   W1 八成範圍包住的比例 < COVER_LO →「範圍太窄」；> COVER_HI →「範圍太寬」。
   W2 當天晃動 ÷ 正常波動的中位數 > RANGE_WARN →「最近實際晃得比正常波動大」。
   W3 帶子 ≥ TOUCH_MIN 條，且 |實際碰到 − 頁面說的| > TOUCH_WARN →「碰到的比例失準」。
6. 優化想法（影子版本：事前寫定、每天跟著記、不自動換）：
   R1「範圍跟著最近的晃動放大」：八成範圍 × clamp(前 N 天（不含當天）當天晃動 ÷ 正常波動 的中位數 ÷ RANGE_NORM, R1_CLAMP)。
      RANGE_NORM＝1.6：常態下一天最高最低差的期望值約是一個標準差的 1.6 倍（√(8/π)），正常波動就是一個標準差；事前假設，不是看結果定的。
   換版條件（全部要過）：R1 有 ≥ SWITCH_MIN 天；R1 包住的比例在 SWITCH_R1 之內、現行版不在 SWITCH_LIVE_OK 之內；R1 平均寬度 ≤ 現行版 × SWITCH_WIDTH。
   過了只在推播與頁面寫「可以考慮換，回『好』才換」，不自動換。
7. 推播一行：「盤前檢討（M/D）：估 X、實際 Y，差 ±Z（N 倍正常波動，在／超出八成範圍）；主因：…。近 n 天八成範圍包住 a 天[；警示]。」
"""
from __future__ import annotations

import hashlib
import json

VER = 1
SPEC_DATE = "2026-11-20"

FREEZE = "08:45"          # 那一天這個時間之後不再改「公布的那一版」
N = 20                    # 近幾個有紀錄的交易日
MIN_DAYS = 10             # 警示至少要幾天
COVER_LO, COVER_HI = 0.65, 0.95
RANGE_WARN = 1.3
TOUCH_MIN, TOUCH_WARN = 30, 0.15
RANGE_NORM = 1.6
R1_CLAMP = (1.0, 2.0)
SWITCH_MIN = 40
SWITCH_R1 = (0.75, 0.88)
SWITCH_LIVE_OK = (0.70, 0.90)
SWITCH_WIDTH = 1.6


def fingerprint() -> str:
    keys = ("VER", "FREEZE", "N", "MIN_DAYS", "COVER_LO", "COVER_HI", "RANGE_WARN", "TOUCH_MIN", "TOUCH_WARN",
            "RANGE_NORM", "R1_CLAMP", "SWITCH_MIN", "SWITCH_R1", "SWITCH_LIVE_OK", "SWITCH_WIDTH")
    g = globals()
    return hashlib.sha256(json.dumps({k: g[k] for k in keys}, sort_keys=True).encode()).hexdigest()[:12]
