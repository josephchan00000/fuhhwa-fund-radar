"""過熱之後 3 個月最大回撤的規格（docs/lab_hotdd_plan.md 第 4 節）：規格鎖定。

規格是在算任何「過熱事件 → 之後回撤」的關係之前寫定的（VER 1，2026-10-19）；VER 2 只改大跌段的定義（規劃第 4.11 節）。
要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import heatspec as HS
from arm.lab import hotddspec as D


def test_hotdd_spec_v2_is_locked():
    assert D.VER == 2 and D.SPEC_DATE == D.VER2_DATE == "2026-10-19"
    assert D.MARKETS == ("tw", "spx", "ixic", "ndx", "sox")
    assert (D.H, D.LAG, D.DD_TH, D.HOT) == (60, 1, (0.10, 0.20), 80)
    assert D.STREAK_N == (4, 8, 13, 26) and D.EXIT_MIN == 4
    assert D.EVENTS == ("E", "S4", "S8", "S13", "S26", "X4") and set(D.EVENT_NAMES) == set(D.EVENTS)
    assert (D.EVT_PRIOR, D.MULTI_K, D.MULTI_MIN_DIMS, D.BUB_K) == (20, 2, 3, (2, 3))
    assert D.MKT_VARS == ("M2", "BL2", "BL3") and set(D.MKT_NAMES) == set(D.MKT_VARS)
    assert (D.BOOT_N, D.BOOT_SEED, D.BLOCK, D.CI) == (2000, 20261019, 60, 0.95)
    assert (D.MIN_EVENTS, D.MIN_EPISODES, D.EP_GAP, D.BH_Q) == (8, 6, 60, 0.10)
    assert (D.VOL_WIN, D.VOL_GROUPS, D.HOLM_ALPHA) == (20, 3, 0.05)
    assert {k: (v["mk"], v["var"], v["ev"]) for k, v in D.PRIMARY.items()} == {
        "HD1": ("tw", "tech", "E"),
        "HD2": ("tw", "tech", "S4"),
        "HD3": ("tw", "C1", "S4"),
        "HD4": ("spx", "tech", "S4"),
    }
    assert (D.DECL_TH, D.DECL_RULE, D.LOOKBACK, D.RECALL_N) == ((0.10, 0.20), "swing", 60, 4)
    assert set(D.VERDICT) == {"up", "down", "none", "few"}


def test_spec_matches_heat_page_rules():
    """事件、過熱門檻、起算日和景氣頁同一套：進入過熱的規則、80 分、t＋1 收盤起算、3 個月＝60 個交易日。"""
    assert HS.EVT["hot"] == (D.HOT, D.EVT_PRIOR)
    assert HS.DAILY_LAG == D.LAG
    assert D.H in HS.EVT_FWD
    assert HS.band(D.HOT) == "過熱" and HS.band(D.HOT - 0.01) != "過熱"
    assert D.PRIMARY["HD3"]["var"] in HS.KEYS and HS.DIM_OF["C1"] == "chip"
    assert all(v["mk"] in D.MARKETS and v["ev"] in D.EVENTS for v in D.PRIMARY.values())
    assert D.EXIT_MIN == D.RECALL_N == min(D.STREAK_N)
