"""美股飆股（美股三成）的規格鎖定：在算任何報酬、任何標籤之前寫定（arm/lab/ussxspec.py、docs/lab_us_sleeve_plan.md 第 9 節）。
要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
import math

from arm.lab import corespec as CS
from arm.lab import superfixspec as SF
from arm.lab import superx as SX
from arm.lab import ussxspec as X


def test_ussx_spec_v1_is_locked():
    assert X.VER == 7 and X.SPEC_DATE == "2026-10-24" and X.DATA_BRANCH == "claude/ussx-data"
    assert X.PX_START == "2006-01-01"
    assert (X.LIQ_MIN, X.PX_MIN, X.AGE_MIN, X.EPS_RECENT, X.SMALL_LIQ) == (20e6, 5.0, 252, 270, 5e6)
    assert X.BOOKS == {"R60": {"n": 60, "g": 0.20, "how": "close"}, "A": {"n": 60, "g": 0.50, "how": "high"},
                       "B": {"n": 250, "g": 1.00, "how": "high"}, "M3": {"n": 500, "g": 2.00, "how": "maxclose"},
                       "M10": {"n": 1250, "g": 9.00, "how": "maxclose"}}
    assert X.FIXED == ("R60", "A") and X.TREND == ("B", "M3", "M10")
    assert (X.IS_START, X.FIRST_YEAR, X.VAL_YEARS, X.LAST_FOLD) == ("2009-01-01", 2014, 2, 2026)
    assert X.TRADE == {"capital": 1_000_000, "weight": 0.125, "max_pos": 8, "max_weight": 0.20, "max_adv": 0.05}
    assert X.COST == {"stk": 0.0005, "stk_alt": 0.0025, "idx": 0.00025}
    assert X.TREND_EXIT == {"trail": 0.30, "ma": 200}
    assert X.ALT_EXITS == {
        "fixed": {"X1": {"ma": 50}, "X2": {"ma": 20}, "X3": {"trail": 0.20}, "X4": {"trail": 0.30},
                  "X5": {"stop": 0.08, "ma": 50}, "X6": {"stop": 0.20, "trail": 0.30}},
        "trend": {"ma50": {"ma": 50, "max": True}, "trail25": {"trail": 0.25, "max": True}, "hold": {"max": True}}}
    assert X.ALT_SLOTS == (4, 16) and X.PLANS == ("spx", "ndx")
    assert X.PASS == {"mdd_extra": 10.0, "surv_max": 2.0}
    assert X.CAPTURE_LEFT == math.sqrt(10) and X.SEED == 20261023 and X.BIG_MOVE == 2.5 and X.WHT == 0.30


def test_survivorship_and_swap_settings():
    assert X.SURV == {"start": "2009-01-01", "px_min": 1.0, "age": 20,
                      "groups": {"L": (1, 500, "RSP"), "M": (501, 900, "IJH"), "S": (901, 1500, "IJR"),
                                 "R": (1001, 3000, "IWM")},
                      "pit": "RSP", "fees": {"RSP": 0.0020, "IJH": 0.0005, "IJR": 0.0006, "IWM": 0.0019},
                      "stop": ("PIT", "S", "R")}
    assert X.SWAP == {"spx": ("QQQ", "SOXX", "RSP", "IVW"), "ndx": ("SOXX",)}
    assert X.SWAP_START == "2006-01-03" and X.SWAP_LONG == {"QQQ": "ndx", "SOXX": "sox"}


def test_features_and_thresholds():
    keys = [f[0] for f in X.FEATS]
    assert keys == ["tt_n", "tt_all", "rs", "d52h", "r120", "bu20", "vdry", "vcp", "grs", "liq",
                    "ey", "eacc", "eaccn", "e4", "eturn", "sur", "nest",
                    "sy", "sacc", "gm", "gmd", "om", "omd", "roe", "c33", "cap"]
    assert {f[2] for f in X.FEATS} == {"num", "bool"} and {f[3] for f in X.FEATS} == {"px", "eps", "sec"}
    assert [f[0] for f in X.FEATS if f[2] == "bool"] == ["tt_all", "vcp", "eturn", "c33"]
    assert (X.BIG_UP, X.GROUP_MIN, X.EPS_FLOOR, X.SUR_FLOOR, X.EPS_TOL_M, X.SEC_TOL_D) == (0.10, 5, 0.05, 0.10, 1, 15)
    assert (X.SEC_Q_DAYS, X.SEC_FY_DAYS, X.SEC_9M_DAYS) == ((80, 100), (350, 380), (260, 290))
    assert X.REV_TAGS[0] == "Revenues" and X.COST_TAGS[0] == "CostOfRevenue"
    # VER 2（規劃第 10.5 節）：同一季取最早公布的、商品＋勞務營收當備用
    assert X.SEC_PICK == "earliest" and X.REV_EXTRA == ("SalesRevenueGoodsNet", "SalesRevenueServicesNet")
    assert X.REV_TAGS == ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                          "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "RevenuesNetOfInterestExpense")
    assert X.COST_TAGS == ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices")


def test_folds_wait_for_labels():
    assert [X.lag_years(X.BOOKS[b]["n"]) for b in X.BOOKS] == [0, 0, 1, 2, 5]
    assert [X.first_year(b) for b in X.BOOKS] == [2014, 2014, 2015, 2016, 2019]
    for b in X.BOOKS:
        assert X.folds(b)[-1] == 2026
        f = X.fold_periods(X.first_year(b), b)
        assert f["is"] == ("2009-01-01", "2011-12-31") and f["val"] == ("2012-01-01", "2013-12-31")
        assert f["subs"] == (("2009-01-01", "2010-07-02"), ("2010-07-03", "2011-12-31"))
    f = X.fold_periods(2026, "M10")
    assert f["is"] == ("2009-01-01", "2018-12-31") and f["val"] == ("2019-01-01", "2020-12-31")
    assert f["known"] == "2025-12-31" and f["trade"] == ("2026-01-01", "2026-12-31")
    f = X.fold_periods(2026, "R60")
    assert f["is"] == ("2009-01-01", "2023-12-31") and f["val"] == ("2024-01-01", "2025-12-31")
    # 標籤一定在交易年之前走完：VAL 最後一年 + n 個交易日不超過 Y−1 年底（252 個交易日一年）
    for b, d in X.BOOKS.items():
        L = X.lag_years(d["n"])
        assert d["n"] <= 126 or d["n"] <= 252 * L


def test_exits():
    assert X.exit_of("R60") == {"hold": 60} and X.exit_of("A") == {"hold": 60}
    assert X.exit_of("B") == {"trail": 0.30, "ma": 200, "hold": 250}
    assert X.exit_of("M10")["hold"] == 1250 and X.hold_of("M3") == 500


def test_rule_search_settings_are_the_existing_ones():
    """找規則的門檻照 superx VER 2、備用門檻照台股 W7；交易計畫照 corespec VER 2（只換三成放什麼）。"""
    assert SX.VER == 2
    assert X.RULE == SX.RULE and X.QS == SX.QS and X.KEEP_FINAL == SX.KEEP_FINAL and X.OVERLAP_MAX == SX.OVERLAP_MAX
    assert X.FALLBACK == SF.FALLBACK and X.VAL_YEARS == SF.VAL_YEARS
    assert CS.VER == 4 and CS.COST["us"] == X.COST["idx"] and CS.SAT == 0.30
    assert set(X.PLANS) <= set(CS.MARKETS)


def test_spec_text_has_no_banned_words():
    from pathlib import Path
    s = Path(X.__file__).read_text(encoding="utf-8")
    for w in ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
              "零風險", "無風險"):
        assert w not in s, w


def test_qm_rule_v3_is_locked():
    """VER 3（規劃第 13 節）：使用者 2026-10-23 選的 A 穩健版，寫死之後不再調參數。"""
    assert X.QM == {"rs": 80.0, "d52h": -0.25, "om": 0.10, "roe": 0.15, "cap": 2e9}
    assert {"rs", "d52h", "om", "roe", "cap"} <= {f[0] for f in X.FEATS}          # 條件的算法沿用 FEATS
    assert X.QM_SLOTS == 8 and X.QM_EXIT == {"ma": 50} and X.QM_STYLE == "trend"
    assert (X.QM_Y0, X.QM_EVAL, X.QM_PLANS) == (2010, 2014, ("spx", "ndx"))
    assert X.QM_REF == {"cagr": 0.2444, "plan_m": 8.8625} and X.QM_REPRO == {"cagr": 0.001, "plan_m": 0.01}
    assert X.QM_NB == {"rs": (70.0, 90.0), "d52h": (-0.15, -0.35), "om": (0.05, 0.15), "roe": (0.10, 0.20), "cap": (1e9, 5e9)}
    assert X.QM_DROP == (1, 2, 3, 5, 8)
    assert (X.QM_LIVE, X.QM_LIST, X.QM_REVIEW, X.QM_P_LOW) == ("2026-10-23", 20, (63, 126, 252), 0.20)
    assert X.QM_P_LOW == CS.P_LOW and CS.US_SLEEVE_FILE == "ussx_qm.json"


def test_qm_v4_idle_cash_is_locked():
    """VER 4（corespec 第 19 節）：空位放現金、判定 ② 用 corespec 當時的核心比例；重現檢查照 VER 3 的設定。"""
    assert X.QM_IDLE == "cash" and X.QM_REPRO_SET == {"idle": "index", "core": 0.70}
    assert X.QM_REPRO_SET["core"] == CS.CORE                     # VER 3 的核心比例
    assert all(CS.core_of(mk) == 0.0 for mk in X.QM_PLANS)        # VER 4：美股計畫全部機動


def test_qm_v5_judge_base_is_the_plan_in_use():
    """VER 5（corespec 第 20 節）：判定 ② 跟現在在用的計畫比（VER 3 的設定：核心 70%、空位放指數），不是同核心比例的指數計畫。"""
    assert X.QM_JUDGE_BASE == {"idle": "index", "core": 0.70} == X.QM_REPRO_SET
    assert X.PASS["mdd_extra"] == 10.0 and X.QM_IDLE == "cash"


def test_qm_v6_overseas_broker_only():
    """VER 6（corespec 第 20 節）：使用者決定美股用海外券商——判定不再要求複委託成本也成立（照算、只描述）。"""
    assert X.QM_NEED_ALT is False and X.COST["stk"] < X.COST["stk_alt"]


def test_qm_v7_one_off_income_fix_is_locked():
    """VER 7（規劃第 14 節）：使用者選 omfixspec 的 D——營益率暴增而且營業利益增加的比營收多的那一週不算。"""
    from arm.lab import omfixspec as OS
    assert X.QM_OM_FIX == {"kind": "spike_ox", "spike": 0.20} == OS.CANDS["D"]
    assert X.QM_EXTRA == ("om1", "oxr") and X.QM_REPRO_FIX is False and X.QM_REF_END == "2026-10-22"
    assert X.QM["om"] == OS.OM_MIN
