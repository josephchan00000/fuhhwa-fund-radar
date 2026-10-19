"""大跌後的買點與落底訊號規格（docs/lab_crash_plan.md 第 13 節）：規格鎖定。

規格是在算任何「事件或訊號 → 之後漲跌」的關係之前寫定的（VER 1，2026-10-19）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import bottomspec as S


def test_bottom_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-19"
    assert S.MARKETS == ("tw", "spx", "ixic", "ndx", "sox")
    assert S.EVENTS == ("E5", "E10")
    assert S.E5_DAYS == 5 and S.E5_GAP == 60
    assert S.E5_TH == {"tw": 0.060, "spx": 0.042, "ixic": 0.057, "ndx": 0.067, "sox": 0.098}
    assert S.E5_BASE == ("2001-01-01", 0.0274)
    assert (S.E10_WIN, S.E10_IN, S.E10_OUT, S.PEAK_WIN) == (60, 0.10, 0.05, 60)
    assert S.GROUPS == ("fund", "chip", "bub")
    assert (S.FUND_MIN, S.FUND_LOOK) == (50, 63)
    assert S.CHIP_VAR == {"tw": "W1", "us": "S5"} and (S.CHIP_LOOK, S.CHIP_HOT, S.BUB_MIN) == (20, 80, 2)
    assert (S.LAG, S.WAIT, S.HS, S.MAIN_H, S.NL_H, S.MAE_H, S.REC_H) == (1, 10, (20, 60, 120), 60, 20, 60, (60, 120, 250))
    assert S.SIG_WIN == 60
    assert S.SIGNALS == ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")
    assert S.SIG_MK == {"tw": S.SIGNALS, "spx": ("C1", "C5", "C7"), "ixic": ("C1", "C5", "C7"),
                        "ndx": ("C1", "C5", "C7"), "sox": ("C1", "C5")}
    assert S.C1_DROP == 0.20 and (S.C2_DAYS, S.C2_DROP) == (20, 0.10)
    assert (S.C3_WIN, S.C3_LO, S.C3_HI) == (10, 0.40, 0.615) and (S.C4_HALF, S.C4_FLOOR) == (0.5, 0.05)
    assert S.C5_CUT == 0.30 and S.C5_FLOOR == {"tw": 10000.0, "us": 5.0}
    assert S.C6_MA == 20 and (S.C7_GAP, S.C7_UP) == (4, 0.0125) and S.C8_UP == 0.90 and S.BREADTH_MIN == 100
    assert S.RULES == ("W10",) + S.SIGNALS
    assert (S.BOOT_N, S.BOOT_SEED, S.BLOCK, S.CI) == (2000, 20261019, 250, 0.95)
    assert (S.MIN_N, S.MIN_EP, S.EP_GAP, S.BH_Q) == (10, 6, 120, 0.10)
    assert set(S.VERDICT) == {"better", "trade", "worse", "none", "few"}
    assert set(S.GVERDICT) == {"up", "down", "none", "few"}
    assert {k: (v["group"], v["ev"], v["out"]) for k, v in S.PRIMARY.items()} == {
        "HB1": ("fund", "E5", "R60"), "HB2": ("chip", "E5", "R60")}
    assert S.POOL == ("tw", "spx") and S.POOL_MIN == 5 and S.HOLM_ALPHA == 0.05


def test_spec_consistency():
    # 門檻換算的方向：越會波動的指數門檻越寬（和台股 2001 年起同樣常見）
    assert S.E5_TH["spx"] < S.E5_TH["ixic"] < S.E5_TH["ndx"] < S.E5_TH["sox"]
    for mk, sigs in S.SIG_MK.items():
        assert mk in S.MARKETS and set(sigs) <= set(S.SIGNALS)
    assert "C7" not in S.SIG_MK["sox"]                       # 費半沒有成交量
    for r in S.RULES:
        assert r in S.RULE_NAMES
    for g in S.GROUPS:
        assert len(S.GROUP_NAMES[g]) == 2
    for h, v in S.PRIMARY.items():
        assert v["group"] in S.GROUPS and v["ev"] in S.EVENTS and v["out"] == f"R{S.MAIN_H}"
    assert set(S.POOL) <= set(S.MARKETS)
