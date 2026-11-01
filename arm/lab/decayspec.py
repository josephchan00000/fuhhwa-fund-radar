"""天數衰減（docs/lab_signal_quality_plan.md 第 13.3 節，C 段第二部分；VER 1，2026-11-01 寫定，算任何衰減的成績之前 commit）。

使用者決定 D3 a：試 EMA 賣壓＋天數衰減（規劃第 7 節），比現在的好才換。規劃第 3.1 節 C：「訊號出現後的影響力照半衰期遞減；
半衰期用過去資料估（同一類訊號一起估）……一條衰減曲線用全部天數一起估，比較穩，也沒有『第 4 天和第 5 天差一格』的硬邊界；
條件斷了的另外估一條」。比較的對象＝sigspec VER 26 的「今天落的那一格也要過」（第 5.1 節，6 段 × 條件還成立／已斷）。

**事前寫定**：模型、估法、比較方法、換不換的規則，都在算任何衰減曲線或比較結果之前寫進這裡並 commit；tests/test_decayspec.py 鎖住。
要改＝VER＋1。寫這一版之前看過的：VER 26 第二段的新舊比較結果（docs/lab_signal_listing_plan.md 第 9.3 節，併進來後重算一次、數字差不多）。

1. 範圍與時間：同 thermocal 的溫度計票（sigspec 第 5 節 ③d、第 5.1 節）：五個市場、THERMO_X_CATS 的訊號、三支溫度計、偏多與警示；
   每年 1 月 1 日（cut）只用窗口在 cut 之前走完的日子估，那一年每個週末照估出來的規則列。
2. 模型：訊號 s、這支溫度計、這一邊，那時候自己的成績 e_s＝命中率 − 平常（thermocal.stats_before）；
   出現後第 k 天（sigage.days 的 k：事件型＝距最近一次出現、狀態型＝距這一段第一天，交易日）預估 e_s × 0.5^(k ÷ h)。
   h＝半衰期，按「組」估：組＝(類別, 條件, 邊)——條件＝sigage 的三種（還成立、已斷、不分；第 0 天一定算成立）。
3. 估 h（每個 cut、每支溫度計、每個市場各估一次）：這一組裡「那時候自己的成績會投這一邊」的訊號（thermocal.vote），
   每一個訓練日（樣本日、窗口在 cut 之前走完、算得到哪一次；同 sigage.Prefix）按第幾天 k（超過 K_CAP 算 K_CAP）加總：
   上面 Σ(那天的結果 − 平常_s)、下面 Σ e_s；R(k)＝上 ÷ 下。h 從 H_GRID 挑使 Σ_k 下(k) ×（R(k) − 0.5^(k ÷ h)）² 最小的（同分取大的）。
   組裡投票的訊號不到 FIT_MIN_SIG 個、或下的總和不到 FIT_MIN_W：退到 (全部類別, 條件, 邊)；還是不夠＝這一組不擋（照 VER 25 只看自己的成績）。
4. 列不列（衰減版）：自己的成績會投這一邊（VER 25 的票）而且 e_s × 0.5^(k ÷ h) ≥ THERMO_EDGE（第 k 天、那天的條件）。
5. 比較（同 thermocal.compare，只描述＋換不換）：每個市場 × 溫度計 × 邊，逐年滾動每個週末三套規則列出來的項目（項目 × 週）之後實際的
   上漲（偏多）或大回撤（警示）比例：VER 25（只看自己）、VER 26（格子）、衰減。差＝衰減 − VER 26（百分點）。
   30 組的差平均（每組一樣重），以「年」為一塊重抽 DRAWS 次求 95% 區間（同一批年用在每一組；那一年沒有資料的組跳過）。
6. 換不換（第 D 段做頁面時接上）：30 組的差平均 > 0、而且 95% 區間下限 > 0、而且衰減列出來的項目週數總和 ≥ COVER_MIN × VER 26 的
   ——三個都成立才把格子換成衰減；否則照 VER 26（差不多就不換；「列得比較少才比較準」不算）。
7. 核對：這裡的迴圈算出來的 VER 25 每週票數要和 thermocal 的一模一樣；不一樣就停。
"""
from __future__ import annotations

VER = 1
SPEC_DATE = "2026-11-01"
OUT = "data/lab/decay_research.json"

H_GRID = (1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120, 180, 250, 500, 1000)   # 半衰期候選（交易日）；1000＝幾乎不衰減
K_CAP = 250                                 # 第幾天超過這個數算這個數（狀態型可以很長）
FIT_MIN_SIG = 5                             # 一組至少幾個投票的訊號才估
FIT_MIN_W = 1.0                             # 下（Σ e_s）的總和至少多少（e 是比例：例 20 天 × 0.05）
COVER_MIN = 0.8                             # 衰減列出來的項目週數至少是 VER 26 的幾成
DRAWS = 1000
SEED = 20261102
CONDS = ("on", "off", "-")                  # 同 sigage：還成立、已斷、不分（cid % 3＝0、1、2）
ALL = "*"                                   # 退到全部類別


def decay(k, h: float):
    """0.5^(k ÷ h)；k 可以是 numpy 陣列。"""
    return 0.5 ** (k / float(h))


def better(dmean: float | None, lo: float | None, cover_d: int, cover_26: int) -> bool:
    """第 6 點：30 組的差平均 > 0、區間下限 > 0、衰減列出來的項目週數 ≥ COVER_MIN × VER 26 的，三個都成立才換。"""
    if dmean is None or lo is None or not cover_26:
        return False
    return dmean > 0 and lo > 0 and cover_d >= COVER_MIN * cover_26
