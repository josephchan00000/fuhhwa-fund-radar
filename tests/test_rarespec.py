"""少見但勝率高的策略的規格（docs/lab_rare_plan.md）：規格鎖定。

規格是在算任何報酬之前寫定的（VER 1，2026-10-27）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import rarespec as X
from arm.lab import robust
from arm.lab import sigspec
from arm.lab import xstrat
from arm.lab import xstratspec


def test_rare_spec_v1_is_locked():
    assert X.VER == 1 and X.SPEC_DATE == "2026-10-27"
    assert X.MARKETS == xstratspec.MARKETS and X.NAMES == xstratspec.NAMES
    assert X.START == {"tw": "1991-01-04", "spx": "1950-01-01", "ixic": "1972-02-07", "ndx": "1986-10-01", "sox": "1995-05-04"}
    assert X.EARLY == ("spx", "1928-01-01", "1949-12-31")
    assert X.RECENT_YEARS == 10 == xstratspec.RECENT_YEARS
    assert X.COST == xstratspec.COST and X.LAG == 1 == xstratspec.LAG
    assert X.WHEN == ("sched", "sig") and X.US_HOME == "spx"
    assert set(X.GROUPS) == {"cal", "event", "tw"}
    assert X.KEYS == ("mid", "santa", "jan", "ath", "bull", "vixinv", "lnypre", "lnypost", "nsf")
    want = {
        "mid": ("cal", "sched", X.MARKETS, "spx", {"H": 250}, {"H": (190, 250, 310)}, None),
        "santa": ("cal", "sched", X.MARKETS, "spx", {"before": 5, "after": 2}, {"before": (4, 5, 6), "after": (1, 2, 3)}, 1973),
        "jan": ("cal", "sig", X.MARKETS, "spx", {"th": 0.0}, {"th": (0.0, 0.01, 0.02)}, 2004),
        "ath": ("event", "sig", X.MARKETS, "spx", {"gap": 250, "H": 250}, {"gap": (190, 250, 375)}, 2017),
        "bull": ("event", "sig", X.MARKETS, "spx", {"th": 0.20, "H": 250}, {"th": (0.15, 0.20, 0.25)}, None),
        "vixinv": ("event", "sig", X.MARKETS, "spx", {"th": 1.00, "reset": 60, "H": 60}, {"th": (1.00, 1.05, 1.10)}, None),
        "lnypre": ("tw", "sched", ("tw",), "tw", {"k": 5}, {"k": (3, 5, 7)}, 2013),
        "lnypost": ("tw", "sched", ("tw",), "tw", {"H": 20}, {"H": (10, 20, 40)}, 2019),
        "nsf": ("tw", "sig", ("tw",), "tw", {"H": 250}, {"H": (60, 120, 250)}, None),
    }
    for R in X.RULES:
        assert (R["grp"], R["when"], R["mk"], R["home"], R["p"], R["grid"], R["pub"]) == want[R["k"]], R["k"]
        assert R["home"] in R["mk"] and R["when"] in X.WHEN and R["grp"] in X.GROUPS
        for k, vs in R["grid"].items():
            assert R["p"][k] in vs                                       # 主參數在參數鄰近裡
        assert R["src"] and all(u.startswith("https://") for u in R["src"])
        assert R["name"] and R["who"] and R["claim"] and R["logic"]
    assert X.LNY_WINDOW == ("01-10", "02-28")
    assert [d for d, _ in X.NSF] == ["2000-03-16", "2000-10-03", "2004-05-20", "2008-09-19", "2011-12-21",
                                     "2015-08-25", "2020-03-20", "2022-07-13", "2025-04-09"]
    assert all(w for _, w in X.NSF)


def test_rare_judgment_matches_macro_dip_ver6():
    """判定＝總經策略落底型 VER 6 同一套門檻；次數少的標示＝訊號總覽的 ★ 次數下限。"""
    assert xstratspec.VER == 6
    assert (X.N_MIN, X.N10, X.WIN) == (xstratspec.DIP_N_MIN, xstratspec.DIP_N10, xstratspec.DIP_WIN) == (5, 5, 0.60)
    assert (X.TRIM_Q, X.TRIM_N) == (xstratspec.DIP_TRIM_Q, xstratspec.DIP_TRIM_N) == (0.05, 20)
    assert X.GRID_OK == xstratspec.GRID_OK == 2 / 3
    assert X.FEW_TAG == sigspec.STAR_N == 15
    assert X.TIERS == xstratspec.TIERS and X.TIER_MARK == xstratspec.TIER_MARK and X.TIER_NAMES == xstratspec.TIER_NAMES
    assert X.OUT_N == 3 and X.REC == ("rec", "watch", "no") and set(X.REC_NAMES) == set(X.REC)
    assert (X.LUCK_DRAWS, X.LUCK_SEED, X.LUCK_SHIFT) == (400, 20261027, (0.15, 0.85))
    for f in (xstrat.data, xstrat.trade_stats, xstrat.base_win, xstrat.dedupe, xstrat.net, xstrat.tier,
              xstrat.future_days, robust.trim_mean, robust.lbo_mean):
        assert callable(f)
