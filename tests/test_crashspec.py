"""大跌風險規格（docs/lab_crash_plan.md 第 10 節）：規格鎖定。

規格是在算任何「預測變數 → 之後大跌」的關係之前寫定的（VER 1，2026-10-19）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import crashspec as C


def test_crash_spec_v1_is_locked():
    assert C.VER == 1 and C.SPEC_DATE == "2026-10-19"
    assert C.MARKETS == ("tw", "spx", "ixic", "ndx", "sox")
    assert C.START == {"tw": "1990-01-04", "spx": "1950-01-03", "ixic": "1971-02-05", "ndx": "1985-10-01",
                       "sox": "1994-05-04"}
    assert C.OUTCOMES == ("A1", "A2", "A3", "A4", "A5") and C.BINARY == ("A1", "A2", "A3", "A4")
    assert C.H == {"A1": 20, "A2": 20, "A3": 60, "A4": 20, "A5": 60}
    assert (C.VOL_BEFORE, C.VOL_RATIO, C.WORST_K) == (60, 1.5, 3)
    assert C.TH == {"tw": (0.030, 0.080, 0.100), "spx": (0.020, 0.057, 0.066), "ixic": (0.026, 0.077, 0.094),
                    "ndx": (0.033, 0.087, 0.100), "sox": (0.050, 0.130, 0.155)}
    assert C.TH_BASE == ("2001-01-01", (0.243, 0.114, 0.215))
    assert (C.VOL_WIN, C.VOL_GROUPS, C.MIN_STRAT, C.MA_DEV) == (20, 3, 20, 60)
    assert C.HOT == 80 and [z for z, _ in C.ZONES] == [80, 60, 40, 20, 0]
    assert (C.PCT_DAILY, C.PCT_MONTHLY, C.VOL_MA) == ((750, 375), (36, 36), (20, 250))
    assert C.PRED["tw"] == ("W1", "W2", "W3", "W4", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "L5", "T9", "Dchip",
                            "Dfund", "BL2", "BP1")
    us = ("Dsent", "S1", "S2", "S3", "S4", "S5", "T9")
    assert C.PRED["spx"] == C.PRED["ixic"] == us + ("VOL", "BL2", "BP1")
    assert C.PRED["ndx"] == C.PRED["sox"] == us + ("BL2", "BP1")
    assert C.MONTHLY == ("W1", "W3", "BL2", "BP1") and C.FLAGS == ("BL2", "BP1") and C.SHORT_SAMPLE == ("Dchip",)
    assert (C.BOOT_N, C.BOOT_SEED, C.BLOCK, C.CI) == (2000, 20261019, 60, 0.95)
    assert (C.MIN_HOT_DAYS, C.MIN_EPISODES, C.EP_GAP, C.BH_Q, C.NW_Z) == (120, 4, 20, 0.10, 1.96)
    assert (C.OOS_START, C.OOS_MIN_TRAIN, C.OOS_MIN_EVENTS, C.HOLM_ALPHA) == ("2010-01-01", 2000, 50, 0.05)
    assert {k: (v["mk"], v["pred"], v["out"]) for k, v in C.PRIMARY.items()} == {
        "HA1": (("tw",), {"tw": "W1"}, "A2"),
        "HA2": (("tw",), {"tw": "C2"}, "A4"),
        "HA3": (("spx",), {"spx": "Dsent"}, "A1"),
        "HA4": (("tw", "spx", "ixic"), {"tw": "L5", "spx": "VOL", "ixic": "VOL"}, "A5"),
    }
    assert C.SHOW == ("up", "down") and set(C.VERDICT) == {"up", "down", "none", "few"}


def test_spec_consistency():
    """每個預測變數都有名稱來源（新算的在 PRED_NAMES，其餘用景氣頁的名稱）；主要假說的預測變數都在該市場的清單裡。"""
    new = {"W1", "W2", "W3", "W4", "Dchip", "Dfund", "Dsent", "VOL", "BL2", "BP1"}
    for mk, ps in C.PRED.items():
        assert len(set(ps)) == len(ps)
        for p in ps:
            assert p in C.PRED_NAMES or p not in new
    for h, v in C.PRIMARY.items():
        for mk in v["mk"]:
            assert v["pred"][mk] in C.PRED[mk], h
        assert v["out"] in C.OUTCOMES
    # 門檻換算的方向：越會波動的指數門檻越寬（台股 2001 年起的同樣頻率）
    assert C.TH["spx"] < C.TH["ixic"] < C.TH["ndx"] < C.TH["sox"]
