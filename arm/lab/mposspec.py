"""台股股市位階的規格（docs/lab_earnings_plan.md 第 8 節；使用者 2026-11-20 傳一張別人的「股市位階」照片，回「好 照你建議」「繼續」）。

VER 1（2026-11-20，只描述現在在哪裡；第一次正式算之前寫定。規劃第 8 節的試算是用每週資料、看過之後才寫這份，照實寫在這裡）
1. 四組，用市場頁台股景氣的每日 0～100（arm/lab/heatcalc.build 的 heat；熱＝高）。每組的項目＝下面的清單和「現在有算分的項目」（heat 的 inc）的交集，
   之後年度重驗把項目拿掉，這裡也跟著拿掉：
   價格位置 PRICE、部位與籌碼 POS、情緒 MOOD、廣度 BREADTH。
2. 每組一天的分數＝有值項目的平均；有值的項目要 ≥ 該組項目數的一半（無條件進位），不然那一天那組沒有分數。
3. 原值＝四組平均（四組都要有分數）。
4. 位階＝0～10：原值和過去 WIN 個交易日（含當天）的原值比，比當天低的天數 ÷ 有值的天數 × 10，四捨五入到小數一位；
   有值的天數 < MIN_DAYS 就沒有位階。
5. 字：≤ X_LOW 極端低位、≤ LOW 低位、≥ X_HIGH 極端高位、≥ HIGH 高位，其他「中間」。
6. 圖：近 CHART_YEARS 年每天的位階；綠帶＝≤ LOW、紅帶＝≥ HIGH；高點＝≥ HIGH 且是前後 PEAK_GAP 個交易日內最高、低點＝≤ LOW 且是前後 PEAK_GAP 個交易日內最低
   （同一種點相隔 < PEAK_GAP 個交易日只留比較極端的那個）。
7. 每天記「公布的數字」（只增不改）：那一天第一次算出來的位階、原值、四組。之後重算不一樣（資料補到前幾天）就照寫「昨天公布 X，用今天的資料重算是 Y」。
8. 總經另寫三個面向（基本面、全球資金、台灣資金）現在的分數與 MACRO_CHG 個交易日前的變化，用市場頁原本的五區名稱；不合成一個數。
9. 這一版不寫「低位／高位之後會怎樣」；要寫得先另寫一版規格、照每年只用過去資料的方式驗過。
"""
from __future__ import annotations

import hashlib
import json

VER = 1
SPEC_DATE = "2026-11-20"

PRICE = ("T1", "T2", "T3", "T4", "T11", "T12", "T13")        # 乖離、RSI、均線排列、季線斜率、距高點
POS = ("C1", "C2", "C3", "C4", "C5", "C6", "C8")              # 融資、券資比、散戶小台、外資期貨與選擇權、投信持股
MOOD = ("T8", "T9", "T10", "C7", "C11")                       # 波動、VIX、台指隱含波動率、P/C 成交量與未平倉
BREADTH = ("T5", "T6", "T7")                                  # 上漲家數、站上 60 日線、新高減新低
GROUPS = (("價格位置", PRICE), ("部位與籌碼", POS), ("情緒", MOOD), ("廣度", BREADTH))
WIN = 2520            # 約 10 年
MIN_DAYS = 1250       # 約 5 年
X_LOW, LOW, HIGH, X_HIGH = 1.0, 3.0, 8.0, 9.0
CHART_YEARS = 5
PEAK_GAP = 60
MACRO = ("fund", "gliq", "tliq")
MACRO_CHG = 20


def fingerprint() -> str:
    keys = ("VER", "GROUPS", "WIN", "MIN_DAYS", "X_LOW", "LOW", "HIGH", "X_HIGH", "CHART_YEARS", "PEAK_GAP", "MACRO", "MACRO_CHG")
    g = globals()
    return hashlib.sha256(json.dumps({k: g[k] for k in keys}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
