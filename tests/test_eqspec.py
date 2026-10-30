"""個股報告評等與目標價的規格鎖定（arm/lab/eqspec.py、docs/lab_equity_report_plan.md 第 6 節）。VER 2：倍數與 EPS 同一把尺、不自己預估；VER 3：會計年度與美股口徑。"""
import pytest

from arm.lab import eqspec as S


def test_spec_v3_is_locked():
    assert S.VER == 3 and S.SPEC_DATE == "2026-10-30"
    assert S.HORIZON_M == 12 and S.CONS_MIN == 3 and not hasattr(S, "MOM_CLIP") and not hasattr(S, "mom_factor")   # 不自己預估
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


def test_f12m_and_fiscal_year():
    assert S.year_weight("2026-10-29") == pytest.approx(2 / 12)
    assert S.year_weight("2026-12-31") == 0 and S.year_weight("2026-01-05") == pytest.approx(11 / 12)
    assert S.year_weight("2026-10-30", "2027-01-31") == pytest.approx(3 / 12)       # 美股會計年度到 1 月：11、12、1 月
    assert S.year_weight("2026-10-30", "2026-09-30") == 0                            # 今年已結束還沒公布 → F12M＝明年
    assert S.year_weight("2026-10-30", "2028-06-30") == 1                            # 夾在 12 個月
    assert S.f12m("2026-10-30", 8.8, 9.6, "2026-09-30") == pytest.approx(9.6)
    assert S.f12m("2026-10-29", 14.23, 25.7) == pytest.approx(2 / 12 * 14.23 + 10 / 12 * 25.7)
    assert S.f12m("2026-10-29", None, 25.7) is None


def test_basis_same_yardstick():
    """VER 2：倍數和它乘的 EPS 同一把尺——共識法只用同業未來本益比；近四季法用本公司與同業的近四季本益比。"""
    assert S.basis(True, 3) == "fwd" and S.basis(True, 2) == "ttm" and S.basis(False, 6) == "ttm"
    assert S.fwd_range(S.band([10, 12, 14, 16, 18])) == {"lo": 12, "hi": 16, "dflt": 14}
    assert S.fwd_range(S.band([10, 20])) is None and S.fwd_range(None) is None


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
