"""盤前價位第 4 段的規格：依正常波動畫價位、停損也跟著波動放寬（pmlvlspec VER 1；docs/lab_premarket_plan.md 第 15 節）。
2026-11-12 寫定、算任何成績之前 commit。

為什麼：使用者 2026-11-12「你選擇權的判斷都很爛欸 why」——原本四張買賣點卡的價位（昨天高低、樞紐點、均線、整數關卡…）
過去 10 年擋住的比例跟任意價位一樣（premktspec VER 2 的 Q3），停損又固定只有 0.1 倍正常波動，11/6～11/11 碰到進場價的 12 張裡 7 張幾分鐘內停損，
卡片已經拿掉（docs/lab_txo_plan.md 第 20 節）。這一段驗證另一種畫法：價位＝預估開盤上下幾倍「正常波動」、停損目標也用正常波動的倍數，
過了才把卡片放回頁面。

共同
  日子＝有證交所 5 秒指數、夜盤、正常波動的交易日，FIRST 起。
  錨點 A＝預估開盤＝前一天加權指數收盤 C＋（夜盤成交量最大契約的最後價 − 同一契約前一天日盤收盤）（同 pmval.q1 的 E1，盤前就知道）。
  正常波動 em＝C × 前一天價平跨式隱含波動率 × √(1/252)（同 premktspec）。
  路徑＝5 秒加權指數，代替小台的價格（基差變化不算，寫在限制）；開盤 O＝09:01:00（第 OPEN_T 個）。
  只能在 ENTRY_FROM（09:01:05）到 ENTRY_LAST（12:30:00）之間進場；EXIT_T（13:25:00）還沒出場就以那一點的價出。
  上方價位 U＝A＋k·em、下方價位 D＝A－k·em。09:01 那一點已經在價位外（O ≥ U 或 O ≤ D）→ 那一邊當天不做（不追跳空）。
  進場價＝第一個越過價位的 5 秒點的價（越過那一點可能已經超過價位，照那一點算、不是價位本身）。
  停損＝進場價往不利方向 s·em、目標＝往有利方向 t·em；先碰到哪個就以那一點的價出場（跳過也照那一點）。
  同一時間最多一筆；一筆出場之後，另一邊的價位之後才被越過，可以再做一筆；每一邊一天最多一筆。
  口數 1 口小台；損益＝點數 × 50 － 兩邊成本；成本一邊＝手續費 25 元＋期交稅 0.00002 × 價 × 50＋滑價 1 點（50 元）（同 premkt.fut_cost）；
  判定用 2 倍成本。

兩族（各自挑參數、各自判定）
  rev（回頭）：碰到上方價位就賣、碰到下方價位就買（賭會拉回）。
  brk（突破）：越過上方價位就買、越過下方價位就賣（賭會延續）。
  參數表＝K × STOP × TARGET（各族 36 組）。

挑參數（walk-forward）
  每年 1 月 1 日，用之前所有年份（FIRST 起）各組的「平均每筆淨損益（2 倍成本）」挑最高的一組，筆數要 ≥ MIN_PICK_N，同分取參數表前面的；
  OOS_FIRST 那一年起接成樣本外（那一年用 FIRST～前一年挑）。

判定（每一族，全部都要過）
  ① 樣本外平均每筆（2 倍成本）> 0
  ② 打亂測試：樣本外每一筆以一半機率換成反方向（同一天、同一刻進場、同樣的停損與目標距離），PLACEBO_N 次、種子 SEED；
     p＝隨機版平均 ≥ 實際的比例 ≤ P_MAX
  ③ 樣本外年份裡至少 YEARS_OK 不虧
  ④ 樣本外依日期切兩半，兩半平均都 > 0
  ⑤ 樣本外筆數 ≥ MIN_N
  ⑥ 扣掉最賺的 TOP_DROP 筆，平均仍 > 0
  全過＝過關：頁面放回卡片（價位＝A ± k·em、停損目標照挑到的那組，附樣本外成績）；沒過＝不放回、照實寫，附可以試的下一步。

只列（不判定、不拿來挑）
  錨點改成 09:01 實際開盤 O（盤前看不到，盤中才知道）；1 倍成本；72 組各自全期成績；正常波動高中低三分組（em ÷ C 的過去一年三分位）分開的成績。
要改＝VER＋1，不在看過結果之後改這一版。
"""
from __future__ import annotations

import hashlib
import json

VER = 1
SPEC_DATE = "2026-11-12"

FIRST = "2017-05-16"           # 夜盤日行情從這天起
OOS_FIRST = 2019
TRADING_YEAR = 252
OPEN_T = 12                    # 09:01:00（5 秒指數第 0 個＝前一天收盤、第 1 個＝09:00:05）
ENTRY_FROM = 13                # 09:01:05
ENTRY_LAST = 2520              # 12:30:00
EXIT_T = 3180                  # 13:25:00

FAMILIES = ("rev", "brk")
K = (0.25, 0.5, 0.75, 1.0)
STOP = (0.15, 0.25, 0.5)
TARGET = (0.25, 0.5, 1.0)

MTX = 50
FEE = 25
TAX = 0.00002
SLIP_PTS = 1
COST_MULT = 2

MIN_PICK_N = 60
PLACEBO_N = 1000
SEED = 20261112
P_MAX = 0.05
YEARS_OK = 2 / 3
MIN_N = 100
TOP_DROP = 3


def grid() -> list[tuple[float, float, float]]:
    """參數表（k, s, t），順序固定（同分取前面的）。"""
    return [(k, s, t) for k in K for s in STOP for t in TARGET]


def side_cost(px: float) -> float:
    """一邊的成本（元）。"""
    return FEE + TAX * px * MTX + SLIP_PTS * MTX


def fingerprint() -> str:
    """規格常數的指紋（tests 鎖住；改任何一個都要 VER＋1）。"""
    keys = sorted(k for k, v in globals().items() if k.isupper() and not callable(v))
    blob = json.dumps({k: globals()[k] for k in keys}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
