"""寬度與深度（docs/lab_breadth_plan.md）。VER 1：2026-10-30，算任何新讀數之後的漲跌之前寫定。

使用者 2026-10-30：「關於寬廣度跟深度測試的部分 你幫我深度評估一下是否要納入一般市場的訊號 還是要納入泡沫的訊號」；
看過規劃選「兩邊都放」（股票層級→一般市場訊號、產業層級→泡沫）、美股站上 60 日線比例與新高減新低「先不做」。

一、一般市場訊號（股票層級；只當訊號、不進雷達分數，同 2026-10-20 法人；接進訊號總覽時 sigspec 下一版第 4.15 節照這裡寫）
  變數（MKT_VARS）：
    TW_EWGAP 台股大型股撐盤＝加權報酬指數近 LB 個交易日的報酬 − 等權報酬。等權＝前一個月底市值 ≥ 40 億的上市櫃股票（同 T5～T7 的範圍）
             每檔近 LB 個交易日含息還原收盤報酬的平均；兩端都有收盤的才算，少於 MIN_N 檔那天沒有值。高＝大型股漲得比一般股票多（窄）。
    TW_MA200 台股一般股票離 200 日線＝同範圍每檔含息還原收盤 ÷ 近 MA_N 日平均 − 1 的中位數（有 MA_N 日資料的才算，至少 MIN_N 檔）。
    US_ADV   美股上漲家數占比＝S&P 500 成分股（data/lab/heat/us_breadth）近 ADV_W 個交易日上漲家數合計 ÷（上漲＋下跌）。1996 起，四個指數共用。
    US_UPV   美股上漲成交金額占比＝近 ADV_W 個交易日上漲成交金額合計 ÷（上漲＋下跌成交金額）。1996 起，四個指數共用。
    US_EWGAP 美股大型股撐盤＝近 LB 個交易日含息報酬：S&P 500 用 SPY − RSP；那斯達克、那斯達克 100 用 QQQ − QQEW（EW_PAIRS）；
             費半沒有等權的 ETF，不做。ETF 上市後滿 LB 個交易日才有值。
  0～100：同 sigspec 第 4.1 節的景氣項目（和自己過去 PCT_WIN 個交易日比、至少 PCT_MIN 天、只用當天以前的資料）；高＝熱。
  訊號：同 sigspec 第 4.1 節的 6 種（過熱中、已連續過熱 13 週以上、進入過熱、過熱結束、過冷中、進入過冷），看多久 H 個交易日；
    次數、命中率、判定、報酬、溫度計全部照 sigspec 現行規則（VER 24），規則不因為這些新變數改。
  台股已有的 T5～T7（上漲家數占比、站上 60 日線、新高減新低）不重算、不重複列。

二、泡沫（產業層級；bubind 的四組 GROUPS）
  讀數（每個月）：
    IB 泡沫寬度＝等級 ≥ LEVEL_MIN 的產業數 ÷ 那個月有等級的產業數。
    ID 泡沫深度＝等級 ≥ LEVEL_MIN 的產業市值 ÷ 有等級的產業市值合計。只算 DEPTH_GROUPS：ff＝家數 × 平均規模（Ken French 月初市值）；
       tw＝產業指數的成分市值。us（類股 ETF 沒有市值）、tg（一家公司可以在好幾個族群）不算深度。
  頁面：不論驗證結果都放（標「參考」）：市場頁泡沫那一塊等級下面一行；歷史圖放研究紀錄。
  驗證（只用 ff，1931-08 起；其他三組太短，只描述）：
    結果＝那個月底之後 FWD_M 個月內，美國大盤（bubind.ff_build 的 mkt：市值加權、不含股利）從那個月底起算的最大回落 ≥ DD。
      之後 FWD_M 個月還沒走完的月份不算。
    事件月＝IB ≥ IB_TH 的月份（另一組：ID ≥ ID_TH）。段＝事件月相隔 ≥ EPI_GAP 個月算新的一段。
    ① 單看：事件月大跌的比例 − 全部月份的比例 ≥ EDGE，而且以 BLOCK 個月一塊重抽 BOOT 次（種子 SEED）的差 95% 區間下緣 > 0，
       而且事件月至少 MIN_EPI 段。
    ② 加值：市場泡沫等級（bubble.py 的 S&P 500，VER 4）≥ LEVEL_MIN 的月份裡，事件月的比例 − 非事件月的比例 ≥ EDGE，
       重抽的差 95% 區間下緣 > 0，兩組各至少 MIN_EPI2 段。
    判定（IB、ID 各自）：①②都過＝「寫進泡沫等級」的候選（例 價格過熱＋產業過熱很廣＝等級 3；bubspec 下一版，改之前先問使用者）；
      只過 ①＝參考讀數旁邊加一句過去的比例；都沒過＝只當參考讀數，照實寫「看不出」。
  只描述（不判定）：門檻 DESCRIBE_TH 的結果；tw、tg、us 三組的歷史與之後的大盤回落。

已經看過的：各組現在幾個產業過熱、ff 歷史上 IB ≥ 20% 的時段（規劃第 4 節）；規格前另外只數了資料起點、事件月數與段數（規劃第 9 節）。
沒有算過任何一個新讀數之後的漲跌或回落。要改就 VER＋1、寫進規劃文件，不在舊版本上改。
"""
from __future__ import annotations

VER = 1
SPEC_DATE = "2026-10-30"

# 一、一般市場訊號
MKT_VARS = ("TW_EWGAP", "TW_MA200", "US_ADV", "US_UPV", "US_EWGAP")
VAR_NAMES = {"TW_EWGAP": "大型股撐盤（加權報酬指數 − 等權）", "TW_MA200": "一般股票離 200 日線（中位數）",
             "US_ADV": "上漲家數占比（S&P 500 成分股）", "US_UPV": "上漲成交金額占比（S&P 500 成分股）",
             "US_EWGAP": "大型股撐盤（市值加權 − 等權 ETF）"}
VAR_MKT = {"TW_EWGAP": ("tw",), "TW_MA200": ("tw",), "US_ADV": ("spx", "ixic", "ndx", "sox"),
           "US_UPV": ("spx", "ixic", "ndx", "sox"), "US_EWGAP": ("spx", "ixic", "ndx")}
LB = 120                                   # 大型股撐盤看近幾個交易日的報酬
MA_N = 200
ADV_W = 10
MIN_N = 50                                 # 台股等權、中位數至少幾檔
EW_PAIRS = {"spx": ("SPY", "RSP"), "ixic": ("QQQ", "QQEW"), "ndx": ("QQQ", "QQEW")}
H = 20                                     # 看多久（交易日；同 sigspec.H_TECH）

# 二、泡沫（產業層級）
GROUPS = ("tw", "tg", "us", "ff")
DEPTH_GROUPS = ("tw", "ff")
LEVEL_MIN = 2
FWD_M = 12
DD = 0.20
IB_TH = 0.20
ID_TH = 0.20
EDGE = 0.10
BLOCK = 12
BOOT = 2000
SEED = 20261030
EPI_GAP = 12
MIN_EPI = 5
MIN_EPI2 = 3
DESCRIBE_TH = (0.10, 0.30)


def episodes(months: list[str]) -> int:
    """事件月（YYYY-MM，排好）→ 段數：和前一個事件月相隔 ≥ EPI_GAP 個月算新的一段。"""
    n, prev = 0, None
    for m in months:
        y, mo = map(int, m.split("-"))
        k = y * 12 + mo
        if prev is None or k - prev >= EPI_GAP:
            n += 1
        prev = k
    return n


def passes(diff: float | None, lo: float | None, epi: int, min_epi: int) -> bool:
    """① 或 ② 過不過：差 ≥ EDGE、重抽 95% 下緣 > 0、段數夠。"""
    return diff is not None and lo is not None and diff >= EDGE and lo > 0 and epi >= min_epi


def verdict(one: bool, two: bool) -> str:
    if one and two:
        return "寫進泡沫等級的候選"
    if one:
        return "參考讀數加一句過去的比例"
    return "只當參考讀數（看不出）"
