"""修正飆股（W7）的規格鎖定：在找任何新規則之前寫定（arm/lab/superfixspec.py、tw-superstock-lab/reports/W7_plan.md）。
要改就 VER＋1、寫進計畫文件，不在舊版本上改。"""
from arm.lab import superfixspec as X
from arm.lab import superx as SX


def test_superfix_spec_v1_is_locked():
    assert X.VER == 1 and X.SPEC_DATE == "2026-10-23"
    assert X.LABELS == {"R60": (60, 0.20), "R120": (120, 0.35)} and X.PRIMARY == "R60" and X.CURRENT == "A"
    assert X.NEIGHBORS == {"R60": (0.15, 0.25)}
    assert X.FOLDS == tuple(range(2019, 2027)) and X.IS_START == "2014-01-01" and X.VAL_YEARS == 2
    assert X.FALLBACK == {"lift": 1.5, "sub_lift": 1.3, "val_lift": 1.3}
    assert X.TRADE == {"weight": 0.125, "hold": {"R60": 60, "R120": 120, "A": 60}}
    assert X.OOS_START == "2019-01-02" and X.HALVES == (("2019-01-01", "2022-12-31"), ("2023-01-01", "2100-12-31"))
    assert X.PASS == {"ew_pts": 3.0, "mdd_extra": 5.0} and X.SAT_MIX == 0.5


def test_fold_periods():
    f = X.fold_periods(2019)
    assert f["is"] == ("2014-01-01", "2016-12-31") and f["val"] == ("2017-01-01", "2018-12-31")
    assert f["subs"] == (("2014-01-01", "2015-07-02"), ("2015-07-03", "2016-12-31"))
    assert f["trade"] == ("2019-01-01", "2019-12-31")
    f = X.fold_periods(2026)
    assert f["is"] == ("2014-01-01", "2023-12-31") and f["val"] == ("2024-01-01", "2025-12-31")
    assert f["subs"][0][0] == "2014-01-01" and f["subs"][1][1] == "2023-12-31"
    assert [X.hold_of(k) for k in ("R60", "R60_15", "R60_25", "R120", "A")] == [60, 60, 60, 120, 60]


def test_rule_search_settings_are_the_existing_ones():
    """找規則的函式與門檻照 superx VER 2，只換標籤與期間。"""
    assert SX.VER == 2 and SX.LABELS["A"] == (60, 0.5)
    assert SX.RULE == {"lift": 2.0, "n": 300, "pos": 50, "sub_lift": 1.5, "val_lift": 1.5, "max_k": 3, "top_feats": 12}
    assert SX.QS == (0.1, 0.2, 0.3) and SX.KEEP_FINAL == 5 and SX.OVERLAP_MAX == 0.8
