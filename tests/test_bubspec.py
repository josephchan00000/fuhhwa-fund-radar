"""泡沫頁規格（docs/lab_risk_plan.md 第 8 節）：規格鎖定。

規格是看任何新結果之前寫定的（VER 1，2026-10-18）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import bubspec as B
from arm.lab import heatspec as S


def test_bubble_spec_v1_is_locked():
    assert B.VER == 1 and B.SPEC_DATE == "2026-10-18"
    assert B.MARKETS == ("tw", "spx", "ixic", "ndx", "sox")
    assert B.DRIFT_GRID == (0.0, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15, 0.20)
    assert (B.CV_REPS, B.CV_SEED, B.CV_NMAX, B.DRIFT_MIN_N, B.PSY_RUN, B.CPI_GAP_MAX) == (2000, 20261020, 2100, 60, 3, 2)
    assert (B.RUN2_PCT, B.RUN2_ATH, B.TREND_Z) == (100.0, 0.05, 2.0)
    assert (B.VAL_ITEMS, B.VAL_PCT, B.VAL_MIN_MONTHS, B.VAL_NEED, B.VAL_MARKETS) == (("X6", "X8", "X9"), 95.0, 240, 2, ("spx",))
    assert (B.FUEL_PCT, B.FUEL_MIN_MONTHS) == (90.0, {"tw": 120, "us": 240})
    assert B.P_KEYS == ("P1", "P2", "P3") and set(B.COND_NAMES) == {"P1", "P2", "P3", "V", "F"}
    assert B.TESTS == ("P1", "P2", "P3", "V", "F", "L2", "L3", "L4")
    assert (B.SPX_ROBUST_START, B.EXT_RUN_MONTHS) == ("1950-01-01", 24)
    assert B.REFS == {"tw": ("X5", "X3", "X6", "Q1"), "us": ("X5", "X3", "X7", "Q2")}
    assert list(B.LEVELS) == [0, 1, 2, 3, 4]


def test_shared_constants_come_from_heatspec():
    """PSY 序列與 BSADF、趨勢偏離、兩年漲幅、大跌定義、區塊重抽沿用景氣頁的同一份（不另寫一套）。"""
    assert B.PSY is S.PSY and B.TREND is S.TREND and B.RUNUP_DAYS == S.RUNUP_DAYS == 504
    assert B.BUB_DD == S.BUB_DD == ((252, 0.20), (504, 0.40)) and B.DAILY_LAG == S.DAILY_LAG
    assert (B.BUB_BLOCK, B.BUB_BOOT, B.BUB_SEED, B.BUB_MIN_HOT, B.BUB_EPI_MIN, B.BUB_EPI_GAP) == (12, 2000, 20261019, 12, 4, 6)


def test_level_table():
    """等級只看「幾種不同類型同時成立」：價格條件 0～3 個 × 估值 × 燃料。"""
    got = {(p, v, f): B.level(p, v, f) for p in range(4) for v in (False, True) for f in (False, True)}
    want = {}
    for p in range(4):
        for v in (False, True):
            for f in (False, True):
                if p == 0:
                    want[(p, v, f)] = 1 if v else 0
                elif p == 1:
                    want[(p, v, f)] = 3 if (v or f) else 2
                else:
                    want[(p, v, f)] = 4 if (v or f) else 3
    assert got == want
    assert B.level(0, False, True) == 0                 # 只有槓桿高不算泡沫
    assert B.level(3, False, False) == 3                # 只有價格類，最高到泡沫警戒
