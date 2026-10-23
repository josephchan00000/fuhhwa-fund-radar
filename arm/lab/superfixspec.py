"""修正飆股（W7）的規格。VER 1：2026-10-23，找任何新規則、跑任何新結果之前寫定（tw-superstock-lab/reports/W7_plan.md）。

使用者 2026-10-23：「修正飆股策略吧」（交易計畫第四輪，docs/lab_core70_plan.md 第 11.3 節的診斷之後）。
診斷：現行飆股候選的規則是用「之後 60 個交易日內最高價碰到 +50%」（superx 標籤 A）挑的，挑到的多半是會衝高又跌回來的股票：
訊號之後 60 天平均最高 +31%、到期只剩 +11.6%、中位數 −0.9%；碰到 +50% 的 20%，60 天後還在 +50% 的只有 13%。
所以這一版只改「目標」：改用實際拿得到的報酬（到期那天的收盤）重新找規則；找規則的流程、門檻、買賣做法全部照舊。

標籤（LABELS）：訊號那天（週最後一個交易日）收盤之後第 N 個交易日的收盤（含息還原）≥ 訊號日收盤 ×（1＋g）＝是
  （superx.Px.label 的 fr：已下市用下市前最後一天；第 N 天超過資料尾端＝不算）。主要 R60（60 天、+20%）；次要 R120（120 天、+35%）；
  鄰近 NEIGHBORS（60 天 +15%／+25%）只看方向；CURRENT＝現行目標 A（60 天內最高價 +50%），同一套流程跑一次當對照。
逐年重新找規則（FOLDS，walk-forward）：交易年 Y 的規則只用 Y 年以前已經走完的資料——
  樣本內 IS(Y)＝IS_START～(Y−VAL_YEARS−1) 年底、子期間＝IS 依日曆對半；驗證期 VAL(Y)＝最後 VAL_YEARS 個年度，
  只留標籤在 (Y−1) 年最後一個交易日以前走完的樣本。找規則的函式與門檻照 superx VER 2（RULE、QS、KEEP_FINAL、OVERLAP_MAX）。
  主門檻那一年一條都沒有 → 用 FALLBACK（樣本內 1.5、子期間 1.3、驗證期 1.3）；還是沒有 → 那一年沒有訊號。
買賣（TRADE）：和「飆股候選照頁面做」（R1）同一個引擎、同一套做法——每週最後一個交易日收盤符合那一年任一條規則 → 隔天開盤買、
  每檔 12.5%（8 檔）、同一天依 RS 高到低、抱 60 天（R120 抱 120 天）、不停損、成本照引擎預設；OOS_START 起一次連續跑到資料最後一天。
判定（PASS，只看 PRIMARY）：①前後兩半（HALVES）的年化都比 CURRENT 逐年高；②整段年化比合格股票等權高 ew_pts 個百分點以上、
  而且兩半都比等權高；③整段最大回落沒有比 CURRENT 逐年深超過 mdd_extra 個百分點。三條都過＝「修好了」。
放進交易計畫的三成（只描述）：台股 corespec VER 2 的時點，OOS_START 起到財報驚喜回測最後一期，
  三成＝大盤／財報驚喜／新飆股／兩者各半（SAT_MIX）／現行飆股。
要改就 VER＋1、寫進計畫文件，不在舊版本上改。
"""
from __future__ import annotations

VER = 1
SPEC_DATE = "2026-10-23"

LABELS = {"R60": (60, 0.20), "R120": (120, 0.35)}
PRIMARY = "R60"
NEIGHBORS = {"R60": (0.15, 0.25)}
CURRENT = "A"

FOLDS = tuple(range(2019, 2027))
IS_START = "2014-01-01"
VAL_YEARS = 2
FALLBACK = {"lift": 1.5, "sub_lift": 1.3, "val_lift": 1.3}

TRADE = {"weight": 0.125, "hold": {"R60": 60, "R120": 120, "A": 60}}
OOS_START = "2019-01-02"
HALVES = (("2019-01-01", "2022-12-31"), ("2023-01-01", "2100-12-31"))

PASS = {"ew_pts": 3.0, "mdd_extra": 5.0}
SAT_MIX = 0.5


def fold_periods(y: int) -> dict:
    """交易年 y 的 IS、子期間、VAL、交易期間（日期字串）。VAL 另外只留「訊號日索引＋持有天數 ≤ (y−1) 年最後一個交易日的索引」的樣本。"""
    from datetime import date
    is_end = f"{y - VAL_YEARS - 1}-12-31"
    a, b = date.fromisoformat(IS_START), date.fromisoformat(is_end)
    mid = date.fromordinal(a.toordinal() + (b.toordinal() - a.toordinal()) // 2)
    nxt = date.fromordinal(mid.toordinal() + 1)
    return {"is": (IS_START, is_end), "subs": ((IS_START, mid.isoformat()), (nxt.isoformat(), is_end)),
            "val": (f"{y - VAL_YEARS}-01-01", f"{y - 1}-12-31"), "trade": (f"{y}-01-01", f"{y}-12-31")}


def hold_of(lab: str) -> int:
    """標籤的持有天數：鄰近（R60_15 這種）跟 R60 一樣。"""
    return TRADE["hold"].get(lab.split("_")[0], 60)
