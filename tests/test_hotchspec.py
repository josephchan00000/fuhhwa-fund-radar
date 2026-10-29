"""反向檢查（籌碼連續過熱、技術面轉空）的規格（docs/lab_hotdd_plan.md 第 7 節）：規格鎖定。

規格是在算任何「狀態或事件 → 之後回撤」的關係之前寫定的（VER 1，2026-10-19）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import crashspec as CS
from arm.lab import heatspec as HS
from arm.lab import heatspec_us as U
from arm.lab import heatviz as HV
from arm.lab import hotchspec as X
from arm.lab import hotddspec as D


def test_hotch_spec_v1_is_locked():
    assert X.VER == 2 and X.SPEC_DATE == "2026-10-29"         # VER 2：美股籌碼變數依指數（docs/lab_us_chip_plan.md）
    assert X.MARKETS == ("tw", "spx", "ixic", "ndx", "sox") and X.TW_START == "1990-01-04" and X.EV_START == 250
    assert (X.H, X.LAG, X.H_LONG, X.DD_TH, X.PEAK_LOOK) == (60, 1, 120, (0.10, 0.20), 60)
    assert (X.HOT, X.STATE_WEEKS, X.STATES_A, X.RUN_MIN) == (80, (1, 4, 13, 26), ("H1", "H4", "H13", "H26"), 4)
    assert X.CHIP_VARS == {"tw": ("Dchip", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "W1", "W2"),
                           "spx": ("Dsent", "S1", "S2", "S3", "S4", "S5", "S6", "S7"),
                           "ixic": ("Dsent", "S3", "S4", "S5", "S6", "S7", "S8", "S9"),
                           "ndx": ("Dsent", "S3", "S4", "S5", "S6", "S7", "S8", "S9"),
                           "sox": ("Dsent", "S3", "S4", "S5", "S6", "S7", "S8", "S9")}
    assert X.CONTRAST_VARS == ("Dtech",)
    assert X.TECH_EVENTS == ("ma20_dn", "ma60_dn", "ma240_dn", "x_dead", "s60_dn", "pv_dn", "dtop", "hstop",
                             "TD1", "TD2", "PH1", "PH2")
    assert X.MA_EVENTS == X.TECH_EVENTS[:8] and set(X.EVENT_NAMES) == set(X.TECH_EVENTS)
    assert (X.TD1_FROM, X.TD1_TO, X.TD1_PRIOR, X.TD1_LOOK) == (80, 50, 20, 60)
    assert X.PH_TARGET == {"PH1": 1, "PH2": 2} and X.PHASE_PARAMS == {"ma": 8, "chg": 13, "hl": 5, "hm": 3}
    assert X.TECH_STATES == ("below60", "below240", "cold") and set(X.TECH_STATE_NAMES) == set(X.TECH_STATES)
    assert (X.COLD, X.CONTRAST_EVENT) == (20, "E")
    assert (X.BOOT_N, X.BOOT_SEED, X.BLOCK, X.BLOCK_LONG, X.CI) == (2000, 20261019, 60, 120, 0.95)
    assert (X.MIN_EVENTS, X.MIN_STATE_DAYS, X.MIN_EPISODES, X.EP_GAP, X.BH_Q) == (8, 120, 6, 60, 0.10)
    assert (X.VOL_WIN, X.VOL_GROUPS, X.HOLM_ALPHA) == (20, 3, 0.05)
    assert {k: (v["mk"], v["part"], v["var"], v["key"]) for k, v in X.PRIMARY.items()} == {
        "HX1": ("tw", "A", "C1", "H13"),
        "HX2": ("tw", "A", "W1", "H13"),
        "HX3": ("tw", "B", None, "TD1"),
        "HX4": ("tw", "B", None, "ma60_dn"),
        "HX5": ("spx", "B", None, "TD1"),
        "HX6": ("spx", "B", None, "ma60_dn"),
    }
    assert X.DECL_TH == (0.10, 0.20) and X.RECENT == 60
    assert set(X.VERDICT) == {"up", "down", "none", "few"}


def test_spec_matches_other_studies():
    """樣本、事件、統計和景氣頁、過熱後回撤、短線大跌風險同一套。"""
    assert X.TW_START == CS.START["tw"]
    assert X.EV_START == HS.EV_START
    assert X.PHASE_PARAMS == HV.PH                      # 階段時間軸改了這裡要 VER＋1
    assert set(X.MA_EVENTS) <= set(HS.EVENTS)
    assert HS.EVT["cold"] == (X.COLD, X.TD1_PRIOR) and HS.EVT["hot"] == (X.HOT, X.TD1_PRIOR)
    assert (X.H, X.LAG, X.HOT, X.DD_TH) == (D.H, D.LAG, D.HOT, D.DD_TH)
    assert (X.BOOT_N, X.BOOT_SEED, X.BLOCK, X.CI) == (D.BOOT_N, D.BOOT_SEED, D.BLOCK, D.CI)
    assert (X.MIN_EVENTS, X.MIN_EPISODES, X.EP_GAP, X.BH_Q, X.VOL_WIN, X.VOL_GROUPS) == (
        D.MIN_EVENTS, D.MIN_EPISODES, D.EP_GAP, D.BH_Q, D.VOL_WIN, D.VOL_GROUPS)
    assert X.DECL_TH == D.DECL_TH and D.DECL_RULE == "swing"
    assert X.CONTRAST_EVENT in D.EVENTS and X.RUN_MIN == min(D.STREAK_N)
    assert X.STATE_WEEKS[1:] == D.STREAK_N[:1] + D.STREAK_N[2:]
    for k in X.CHIP_VARS["tw"]:
        assert k in ("Dchip", "W1", "W2") or HS.DIM_OF[k] == "chip"
    for idx in ("spx", "ixic", "ndx", "sox"):
        with HS.use(U.spec_for(idx)):
            assert set(X.CHIP_VARS[idx]) == {"Dsent"} | set(HS.ITEMS["sent"])     # 就是那個指數的情緒籌碼項目
    assert all(v["mk"] in X.MARKETS for v in X.PRIMARY.values())
    assert all(v["key"] in (X.STATES_A if v["part"] == "A" else X.TECH_EVENTS) for v in X.PRIMARY.values())
    assert all(v["var"] in X.CHIP_VARS["tw"] for v in X.PRIMARY.values() if v["part"] == "A")
