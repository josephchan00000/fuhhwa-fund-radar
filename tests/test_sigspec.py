"""訊號總覽實務判定的規格（docs/lab_signal_plan.md）：規格鎖定。

規格是在算任何訊號的命中率之前寫定的（VER 1，2026-10-19；VER 2 同日只改個股策略的次數下限，規劃第 15 節）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import analyze as AN
from arm.lab import backtest as BT
from arm.lab import bottomspec as BS
from arm.lab import bt3
from arm.lab import crashspec as CS
from arm.lab import heatspec as HS
from arm.lab import heatspec_us as U
from arm.lab import sigspec as X


def test_sig_spec_v1_is_locked():
    assert X.VER == 2 and X.SPEC_DATE == "2026-10-19"
    assert X.MARKETS == ("tw", "spx", "ixic", "ndx", "sox")
    assert X.LAG == 1 and X.DIRS == ("up", "warn", "buy") and X.WARN_LONG == 0.20
    assert X.WARN_TH_IDX == {20: 1, 60: 2}
    assert X.HIT_MIN == {"up": 0.60, "warn": 0.50, "buy": 0.60}
    assert (X.EDGE_GOOD, X.EDGE_REF, X.N_MIN, X.RECENT_YEARS, X.RECENT_N) == (0.10, 0.05, 10, 10, 5)
    assert X.TIERS == ("good", "ref", "none", "few") and set(X.TIER_NAMES) == set(X.TIERS) == set(X.TIER_MARK)
    assert X.KINDS == ("event", "state") and X.EP_GAP == 20
    assert (X.HOT, X.COLD, X.HOT_WEEKS, X.EXIT_MIN) == (80, 20, 13, 4)
    assert X.VARIANTS == ("hot", "hot13", "hot_in", "hot_out", "cold", "cold_in")
    assert X.VARIANT_KIND == {"hot": "state", "hot13": "state", "hot_in": "event", "hot_out": "event",
                              "cold": "state", "cold_in": "event"}
    assert set(X.VARIANT_NAMES) == set(X.VARIANTS)
    assert X.H_DIM == {"tech": 20, "chip": 60, "sent": 60, "gliq": 60, "tliq": 60, "liq": 60, "fund": 250}
    assert (X.MULTI_K, X.MULTI_MIN_DIMS, X.H_MULTI) == (2, 3, 60)
    assert (X.H_TECH, X.EV_START) == (20, 250)
    assert X.DERIV_STATES == (1, 2, 3, 4) and X.H_DERIV == 60
    assert X.CRASH_VARS == {"tw": ("W1", "W2", "W3", "W4"), "spx": ("VOL",), "ixic": ("VOL",), "ndx": (), "sox": ()}
    assert X.H_CRASH == 60
    assert X.BUB_SIGNALS == ("L2", "L3", "P1", "P2", "P3", "E", "G", "F", "V") and set(X.BUB_NAMES) == set(X.BUB_SIGNALS)
    assert X.IND_GROUPS == ("ff", "us", "tw") and X.IND_SIGNALS == ("L2", "L3")
    assert (X.H_BUB, X.H_IND_M) == (250, 12)
    assert X.H_STOCK == 20 and X.STOCK_WARN == ("exit",)
    assert X.STRAT_N_MIN == X.N_MIN == 10 and X.STRAT_FEW == 30          # VER 2：次數不夠沒關係（使用者 2026-10-19）
    assert X.STRAT_CAP == {"good": 0.05, "ref": 0.02, "none": 0.0, "few": 0.0}
    assert (X.TODAY_MAX, X.TODAY_REF) == (8, 3)


def test_sig_spec_refers_to_existing_definitions():
    """規格引用的其他規格都還在、意思沒變。"""
    for mk in X.MARKETS:
        assert len(CS.TH[mk]) == 3                        # (A1 單日, A2 20 日, A3 60 日)
    assert CS.TH["tw"][X.WARN_TH_IDX[20]] == 0.08 and CS.TH["tw"][X.WARN_TH_IDX[60]] == 0.10
    assert len(HS.EVENTS) == 16
    assert set(HS.EVT) >= {"hot", "cold"} and HS.EVT["hot"][0] == X.HOT and HS.EVT["cold"][0] == X.COLD
    dims_tw = set(HS.DIMS) - {"bubl"}
    assert dims_tw <= set(X.H_DIM)
    for idx in U.INDEX_ORDER:
        with HS.use(U.spec_for(idx)):
            assert set(HS.DIMS) - {"bubl"} <= set(X.H_DIM)
            assert len(HS.DERIV) >= 1
    assert BS.VER == 3 and BS.LP_CUT == 1 / 3 and BS.SIG_BASE == "W10"
    assert set(X.STOCK_WARN) <= set(AN.SIG_DEF) and len(AN.SIG_DEF) == 8
    assert BT.DEDUP == 5
    assert bt3.PAY == {"win": 60.0, "m": 1.0, "win2": 40.0, "ratio": 2.5, "m2": 2.0}
