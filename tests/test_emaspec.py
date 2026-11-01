"""EMA 賣壓的規格鎖（arm/lab/emaspec.py；docs/lab_signal_quality_plan.md 第 13 節）。改任何一個值＝VER＋1。"""
from arm.lab import emaspec as E
from arm.lab import sigspec as S


def test_version_and_constants():
    assert E.VER == 1 and E.SPEC_DATE == "2026-11-01" and E.OUT == "data/lab/ema_research.json"
    assert E.SPANS == (5, 20, 60) and E.SPANS == S.INST_POS_WIN          # 和現在的合計位階一一對應
    assert E.SKIP == (("fi", 60),) and set(E.SKIP) == set(S.INST_SKIP)
    assert E.KEY == "e" and E.SENS == (0.8, 1.2) and E.DRAWS == 1000 and E.SEED == 20261101
    assert E.FAMILIES == ("E", "S", "R")


def test_alpha_matches_average_lag_of_sums():
    for w in E.SPANS:
        a = E.alpha(w)
        assert abs((1 - a) / a - (w - 1) / 2) < 1e-12                    # EMA 平均落後＝w 日合計平均落後
    assert [E.span_nb(w, f) for w in E.SPANS for f in E.SENS] == [4, 6, 16, 24, 48, 72]


def test_switch_rule():
    assert E.better(0.08, 0.05, 0.01, 0.6, 0.55) is True
    assert E.better(0.08, 0.05, -0.01, 0.6, 0.55) is False               # 區間碰到 0＝差不多，不換
    assert E.better(0.08, 0.05, 0.01, 0.5, 0.55) is False                # o > 0 的比例比較低
    assert E.better(0.04, 0.05, 0.01, 0.6, 0.55) is False
    assert E.better(None, 0.05, 0.01, 0.6, 0.55) is False
