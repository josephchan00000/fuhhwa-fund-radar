"""交易計畫（核心 70%＋衛星 30%）的規格（docs/lab_core70_plan.md 第 9 節）：規格鎖定。

VER 1 是在算任何正式數字之前寫定的（2026-10-23）；VER 2 是看過第 11 節的探索結果、使用者決定之後寫定的，
寫定之後才跑正式數字（scripts/run_core.py）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import corespec as X
from arm.lab import heatspec
from arm.lab import heatspec_us


def test_core_spec_v2_is_locked():
    assert X.VER == 2 and X.SPEC_DATE == "2026-10-23"
    assert X.FLAT == ("spx", "ndx") and X.REENTRY == {"tw": 10}
    assert X.MARKETS == ("tw", "spx", "ndx")
    assert (X.CORE, X.SAT, X.HOT, X.NEED, X.MA, X.LAG) == (0.70, 0.30, 80.0, 2, 200, 1)
    assert {mk: [f[0] for f in X.FAMS[mk]] for mk in X.MARKETS} == {mk: ["inf", "lev", "trend"] for mk in X.MARKETS}
    assert [f[3:] for f in X.FAMS["tw"]] == [("heat", "B8"), ("crash", "W2"), ("ma", 200)]
    for mk in ("spx", "ndx"):
        assert [f[3:] for f in X.FAMS[mk]] == [("heat", "F6"), ("heat", "S5"), ("ma", 200)]
    assert X.SLEEVE_TIER == "good" and X.PERIOD_KINDS == ("per",)
    assert X.SLOTS == {"s3": 4, "s5": 16} and X.SLOTS_DEFAULT == 5 and X.BACKTEST_SLEEVE == ("v3l",)
    assert X.RULE_START == {"tw": "2006-01-25", "spx": "2000-01-03", "ndx": "2000-12-29"} and X.PLAN_START == "2014-05-15"
    assert X.EARLY == {"spx": "1999-12-31", "ndx": "2000-12-28"}
    assert X.COST == {"tw": 0.001, "tw_stk": 0.0024, "us": 0.00025}
    assert (X.RECENT_Y, X.YEAR_MIN, X.ROLL, X.Q) == (10, 120, 252, (0.10, 0.50, 0.90))
    assert X.LIVE_START == "2026-10-23" and X.CHECKS == (63, 126, 252, 504, 756) and (X.WEEK, X.P_LOW) == (5, 0.20)


def test_family_items_exist_in_heat_specs():
    """通膨、槓桿用的是景氣頁現有的項目（台股 B8、美股 F6、S5），不是另外定義的。"""
    assert "B8" in {k for k, *_ in heatspec.IND}
    for mk in ("spx", "ndx"):
        with heatspec.use(heatspec_us.spec_for(mk)):
            assert {"F6", "S5"} <= {k for k, *_ in heatspec.IND}
