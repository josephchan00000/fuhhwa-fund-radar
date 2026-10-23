"""美股飆股（美股三成）的規格鎖定：在算任何報酬、任何標籤之前寫定（arm/lab/ussxspec.py、docs/lab_us_sleeve_plan.md 第 9 節）。
要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
import math

from arm.lab import corespec as CS
from arm.lab import superfixspec as SF
from arm.lab import superx as SX
from arm.lab import ussxspec as X


def test_ussx_spec_v1_is_locked():
    assert X.VER == 1 and X.SPEC_DATE == "2026-10-23" and X.DATA_BRANCH == "claude/ussx-data"
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
    assert CS.VER == 2 and CS.COST["us"] == X.COST["idx"] and CS.SAT == 0.30
    assert set(X.PLANS) <= set(CS.MARKETS)


def test_spec_text_has_no_banned_words():
    from pathlib import Path
    s = Path(X.__file__).read_text(encoding="utf-8")
    for w in ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
              "零風險", "無風險"):
        assert w not in s, w
