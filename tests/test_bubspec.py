"""泡沫頁規格（docs/lab_risk_plan.md 第 8、9 節）：規格鎖定。

規格是看任何新結果之前寫定的（VER 1～4 都是 2026-10-18）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import bubspec as B
from arm.lab import heatspec as S


def test_bubble_spec_v1_is_locked():
    assert B.VER == 4 and B.SPEC_DATE == "2026-10-18"
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


def test_bubble_spec_v2_is_locked():
    """VER 2：價格過熱＋價格漲得比基本面快（比值爆發）兩個都要；VER 1 的等級留著對照。"""
    assert B.FUND == {"spx": ("pe",), "tw": ("pe_tw", "ex"), "sox": ("wsts",), "ixic": ("cp",), "ndx": ("cp",)}
    assert set(B.FUND_NAMES) == {"pe", "pe_tw", "ex", "wsts", "cp"}
    assert B.FUND_REL == {"pe": (6, 1), "ex": (2, 28), "wsts": (2, 10), "cp": (3, 1)}
    assert B.FUND_SUM == {"ex": 12, "wsts": 12, "cp": 4} and B.CP_SERIES == ("A055RC", "A551RC")
    assert B.E_RUN == 3 and B.SPLIT_MONTHS == 24
    assert B.TESTS2 == ("P1", "P2", "P3", "E", "V", "F", "PF", "PN", "L2", "L3", "L4", "L3v1")
    from arm.lab import heatspec_us as U
    assert B.FUND_REL["pe"] == U.RELEASE["F8"] and B.FUND_REL["wsts"] == U.RELEASE["F10"]
    assert B.FUND_REL["ex"] == S.RELEASE["B5"]


def test_level2_table():
    """VER 2：價格過熱但基本面有跟上（E、V 都沒成立）最多到 2；3 要 E 或 V；4 要 E、V、F 至少兩個。"""
    for price in (False, True):
        for e in (False, True):
            for v in (False, True):
                for f in (False, True):
                    n = e + v + f
                    if not price:
                        want = 1 if v else 0
                    elif not (e or v):
                        want = 2
                    else:
                        want = 4 if n >= 2 else 3
                    assert B.level2(price, e, v, f) == want, (price, e, v, f)
    assert B.level2(True, False, False, True) == 2         # 價格過熱＋槓桿高，但基本面有跟上：不算泡沫
    assert B.level2(False, True, False, True) == 0         # 比值爆發但價格沒過熱（例如盈餘崩掉）：不算


def test_bubble_spec_v3_is_locked():
    """VER 3：P1、E 加方向條件（近 12 個月價格上漲；E 另要比值上升）；VER 2 等級留著對照。"""
    assert B.DIR_MONTHS == 12 and B.TESTS3 == B.TESTS2 + ("L3v2",)


def test_bubble_spec_v4_is_locked():
    """VER 4（第 11 節）：G＝成長減速而且預估下修、股價還在漲；現在用分析師預估、過去用替代資料；那斯達克 E 改科技業獲利。"""
    assert (B.G_PRICE_MONTHS, B.G_PRICE_DAYS) == (3, 91)
    assert set(B.EST_SRC) == set(B.MARKETS)
    assert (B.EST_NQ_TOP, B.EST_COVER_MIN, B.EST_STALE_DAYS, B.EST_PE_RANGE, B.EST_TREND_DAYS) == (300, 0.50, 7, (3.0, 300.0), 90)
    assert B.PROXY == {"spx": "spf", "ixic": "tech", "ndx": "tech", "sox": "wsts", "tw": "orders"}
    assert set(B.PROXY_NAMES) == {"spf", "tech", "wsts", "orders", "cp"}
    assert B.PROXY_SUM == {"tech": 4, "cp": 4, "wsts": 12, "orders": 12}
    assert (B.PROXY_G1_BACK, B.PROXY_G2_BACK) == ({"q": 2, "m": 6}, {"q": 1, "m": 3})
    assert B.PROXY_REL == {"tech": (3, 1), "cp": (3, 1), "wsts": (2, 10), "orders": (1, 21)}
    assert B.PROXY_REL["wsts"] == B.FUND_REL["wsts"] and B.PROXY_REL["orders"] == S.RELEASE["B4"]
    assert (B.SPF_FILE, B.SPF_FIRST_ANNUAL, B.SPF_BREAK) == ("Median_CPROF_Level", (1981, 3), (2006, 1))
    assert B.TECH_NAICS_Q == ("BEA/NIPA-T61600D/N501RC-Q", "BEA/NIPA-T61600D/N502RC-Q")
    assert B.TECH_NAICS_A == ("BEA/NIPA-T61600D/N501RC-A", "BEA/NIPA-T61600D/N502RC-A")
    assert [c.rsplit("/", 1)[1] for c in B.TECH_SIC_C_Q] == ["A409RC-Q", "A410RC-Q", "A418RC-Q"]
    assert [c.rsplit("/", 1)[1] for c in B.TECH_SIC_C_A] == ["A409RC-A", "A410RC-A", "A418RC-A"]
    assert [c.rsplit("/", 1)[1] for c in B.TECH_SIC_B_Q] == ["A409RBC-Q", "A410RBC-Q", "A418RBC-Q"]
    assert (B.TECH_K1_YEARS, B.TECH_K2_YEAR) == ((1998, 1999, 2000), 1987)
    assert B.FUND4 == {**B.FUND, "ixic": ("tech",), "ndx": ("tech",)} and B.FUND["ixic"] == ("cp",)
    assert B.FUND_REL4["tech"] == B.FUND_REL["cp"] and B.FUND_SUM4["tech"] == 4 and "tech" in B.FUND_NAMES4
    assert B.TESTS4 == B.TESTS3 + ("G1", "G2", "G", "PG", "PnG", "L3v3") and B.TESTS4_SPX == B.TESTS4 + ("Gr", "PGr")


def test_level4_table():
    """VER 4：價格過熱但 E、V、G 都沒成立最多到 2；3 要 E、V、G 其中之一；4 要 E、V、G、F 至少兩個。"""
    for price in (False, True):
        for e in (False, True):
            for v in (False, True):
                for g in (False, True):
                    for f in (False, True):
                        n = e + v + g + f
                        if not price:
                            want = 1 if v else 0
                        elif not (e or v or g):
                            want = 2
                        else:
                            want = 4 if n >= 2 else 3
                        assert B.level4(price, e, v, g, f) == want, (price, e, v, g, f)
    assert B.level4(True, False, False, True, False) == 3        # 只有未來獲利跟不上：泡沫警戒
    assert B.level4(False, False, False, True, True) == 0        # 價格沒過熱：不算
    for p in (False, True):                                     # G 不成立時和 VER 2 分級一樣
        for e in (False, True):
            for v in (False, True):
                for f in (False, True):
                    assert B.level4(p, e, v, False, f) == B.level2(p, e, v, f)
