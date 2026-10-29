"""交易計畫（核心 70%＋衛星 30%）的規格（docs/lab_core70_plan.md 第 9 節）：規格鎖定。

VER 1 是在算任何正式數字之前寫定的（2026-10-23）；VER 2 是看過第 11 節的探索結果、使用者決定之後寫定的；
VER 3 只換美股三成放什麼（ussxspec VER 3，使用者決定「現在就換」）；
VER 4 是看過第 16～18 節之後寫定的（空檔放現金、台股機動各半放新飆股與 ★ 策略、核心比例照第 18 節寫定的選法），
寫定之後才跑正式數字（scripts/run_core.py）；VER 5 只把台股新飆股那一半從 R60 換成 N8（使用者「要改」），
寫在算任何 VER 5 的計畫數字之前。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import corespec as X
from arm.lab import heatspec
from arm.lab import heatspec_us


def test_core_spec_v5_is_locked():
    assert X.VER == 5 and X.SPEC_DATE == "2026-10-29"
    assert X.US_SLEEVE_FILE == "ussx_qm.json"           # VER 3：美股衛星＝美股三成規則 QM（ussxspec VER 3）
    # VER 4：核心比例照第 18 節的選法（第 19 節的表）；機動＝1 − 核心
    assert X.CORE_OF == {"tw": 0.20, "spx": 0.0, "ndx": 0.0}
    assert X.CORE_GRID == (0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10, 0.0)
    assert set(X.CORE_OF) == set(X.MARKETS) and all(c in X.CORE_GRID for c in X.CORE_OF.values())
    assert X.core_of("tw") == 0.20 and X.sat_of("tw") == 0.80 and X.core_of("spx") == 0.0 and X.sat_of("ndx") == 1.0
    assert X.BOOM_SHARE == {"tw": 0.5} and X.BOOM_BOOK == "N8" and X.IDLE == "cash" and X.STAR_ACTIVE == 0.69
    assert X.PLAN4_START == "2019-01-02" and X.SX_CURVE_FILE == "sx_n8_curve.json" and X.SX_CURVE_R60 == "sx_r60_curve.json"
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
    assert X.LIVE_START == "2026-10-26" and X.LIVE_KEEP == (4,) and X.CHECKS == (63, 126, 252, 504, 756) and (X.WEEK, X.P_LOW) == (5, 0.20)


def test_v4_plan_start_is_the_w7_walk_forward_start():
    """台股照計畫的回測起點＝新飆股逐年規則的第一個交易日（W7 的 OOS_START）；VER 5 新飆股＝選股頁那一本（N8），
    名單照舊是 R60 的（W7 的主帳）；回測起點和 W10 一樣。"""
    from arm.lab import superfixspec as W
    from arm.lab import sxfixspec as F
    from arm.lab import sxlivespec as L
    assert X.PLAN4_START == W.OOS_START == F.START and X.BOOM_BOOK == L.PLAN_BOOK and L.LIST_BOOK == W.PRIMARY == L.BOOKS[0]


def test_family_items_exist_in_heat_specs():
    """通膨、槓桿用的是景氣頁現有的項目（台股 B8、美股 F6、S5），不是另外定義的。"""
    assert "B8" in {k for k, *_ in heatspec.IND}
    for mk in ("spx", "ndx"):
        with heatspec.use(heatspec_us.spec_for(mk)):
            assert {"F6", "S5"} <= {k for k, *_ in heatspec.IND}
