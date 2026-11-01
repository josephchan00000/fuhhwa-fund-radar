"""天數衰減的規格鎖（arm/lab/decayspec.py；docs/lab_signal_quality_plan.md 第 13.3 節）。改任何一個值＝VER＋1。"""
import numpy as np

from arm.lab import decayspec as D
from arm.lab import sigage as A


def test_version_and_constants():
    assert D.VER == 1 and D.SPEC_DATE == "2026-11-01" and D.OUT == "data/lab/decay_research.json"
    assert D.H_GRID == (1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120, 180, 250, 500, 1000)
    assert D.K_CAP == 250 and D.FIT_MIN_SIG == 5 and D.FIT_MIN_W == 1.0 and D.COVER_MIN == 0.8
    assert D.DRAWS == 1000 and D.SEED == 20261102 and D.CONDS == ("on", "off", "-") and D.ALL == "*"
    assert len(D.CONDS) == len(A.CK)                                      # 同 sigage 的三種條件（cid % 3）


def test_decay_curve():
    assert D.decay(0, 10) == 1.0 and abs(D.decay(10, 10) - 0.5) < 1e-12
    assert np.allclose(D.decay(np.array([0, 20]), 20), [1.0, 0.5])


def test_switch_rule():
    assert D.better(0.01, 0.002, 900, 1000) is True
    assert D.better(0.01, -0.002, 900, 1000) is False                    # 區間碰到 0
    assert D.better(0.01, 0.002, 700, 1000) is False                     # 列得比 VER 26 少很多
    assert D.better(-0.01, 0.002, 900, 1000) is False and D.better(None, None, 0, 0) is False
