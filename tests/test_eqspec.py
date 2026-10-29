"""個股報告評等與目標價的規格鎖定：寫在看任何一份報告的估值結果之前（arm/lab/eqspec.py、docs/lab_equity_report_plan.md 第 6 節）。"""
import pytest

from arm.lab import eqspec as S


def test_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-29"
    assert S.HORIZON_M == 12 and S.CONS_MIN == 3 and S.MOM_CLIP == (0.7, 1.5)
    assert S.PE_MAX == 80.0 and S.BAND_YEARS == 5 and S.BAND_PE_MAX == 100.0 and S.BAND_PB_MAX == 20.0
    assert S.PEER_MIN == 3 and S.PB_INDUSTRIES == ("金融保險",)
    assert S.BUY_UP == 0.15 and S.SELL_DN == -0.10 and S.SCEN_EPS == 0.15
    assert S.RATINGS == ("買進", "中立", "減碼", "暫不評等")
    assert S.TICK_TP["tw"] == ((50, 0.5), (100, 1.0), (500, 5.0), (1000, 10.0), (float("inf"), 50.0))
    assert S.TICK_TP["us"] == ((50, 0.5), (float("inf"), 1.0))
    assert S.PEER_N == 6 and S.PEER_LEADERS == 2 and S.PEER_SWAP_MAX == 3


def test_rating_thresholds():
    assert S.rating(115, 100) == "買進" and S.rating(114.9, 100) == "中立"
    assert S.rating(90, 100) == "減碼" and S.rating(90.1, 100) == "中立"
    assert S.rating(None, 100) == "暫不評等" and S.rating(100, 0) == "暫不評等"
    assert not [r for r in S.RATINGS if "建議" in r]


def test_round_tp():
    assert S.round_tp(47.3) == 47.5 and S.round_tp(87.4) == 87.0 and S.round_tp(352.4) == 350.0
    assert S.round_tp(647) == 650.0 and S.round_tp(1234) == 1250.0 and S.round_tp(2480) == 2500.0
    assert S.round_tp(48.74, "us") == 48.5 and S.round_tp(123.6, "us") == 124.0


def test_f12m_and_momentum():
    assert S.year_weight("2026-10-29") == pytest.approx(2 / 12)
    assert S.year_weight("2026-12-31") == 0 and S.year_weight("2026-01-05") == pytest.approx(11 / 12)
    assert S.f12m("2026-10-29", 14.23, 25.7) == pytest.approx(2 / 12 * 14.23 + 10 / 12 * 25.7)
    assert S.f12m("2026-10-29", None, 25.7) is None
    assert S.mom_factor(130, 100) == pytest.approx(1.3) and S.mom_factor(200, 100) == 1.5 and S.mom_factor(50, 100) == 0.7
    assert S.mom_factor(100, 0) is None


def test_bands_range_and_method():
    b = S.band([10, 12, 14, 16, 18])
    assert b == {"p25": 12, "p50": 14, "p75": 16, "n": 5}
    peer = S.band([20, 30, 40])
    r = S.mult_range(b, peer)
    assert r == {"lo": 12, "hi": 35, "dflt": (14 + 30) / 2}
    assert S.mult_range(b, S.band([20, 30])) == {"lo": 12, "hi": 16, "dflt": 14}     # 同業不到 3 家只用本公司
    assert S.mult_range(None, None) is None
    assert S.method(10, 200, 50, "半導體業") == "pe"
    assert S.method(2, 200, 50, "半導體業") == "pb"                                    # 100 倍 > PE_MAX
    assert S.method(10, 200, 50, "金融保險") == "pb"
    assert S.method(-1, 200, None, "半導體業") == "none"


def test_scenarios():
    r = {"lo": 15, "hi": 30, "dflt": 20}
    s = S.scenarios(20, r, 400)
    assert s == {"bear": S.round_tp(20 * 0.85 * 15), "base": 400, "bull": S.round_tp(20 * 1.15 * 30)}
    assert S.scenarios(100, r, 2000, pe=False) == {"bear": 1500.0, "base": 2000, "bull": 3000.0}
