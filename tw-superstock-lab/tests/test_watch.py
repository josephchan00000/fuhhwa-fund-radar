"""watch（超級飆股觀察名單評估）：段落切分、抓到與抓得早、隨機名單、挑選規則。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from superstock import engine as EN
from superstock import watch as WT


def _market(c: np.ndarray) -> EN.Market:
    c = np.asarray(c, dtype=float)
    if c.ndim == 1:
        c = c[:, None]
    v = np.full_like(c, 1e6)
    dates = pd.bdate_range("2015-01-01", periods=len(c))
    return EN.Market(dates, [f"{1000 + k}" for k in range(c.shape[1])], c, c, c, c, value=c * v, volume=v)


def _run_up() -> np.ndarray:
    """100 天平盤 → 100 天內漲到 3 倍 → 回落。"""
    return np.concatenate([np.full(100, 10.0), np.linspace(10, 30, 100), np.linspace(30, 20, 400)])


def test_episode_t0_is_lowest_close_and_peak_is_max():
    m = _market(_run_up())
    y = WT.labels(m, np.ones(m.c.shape, dtype=bool))["B"]
    ep = WT.episodes(m, y)
    assert len(ep) == 1
    j, t0, pk, gain = ep[0]
    assert m.c[t0, 0] == 10.0 and pk == 199 and abs(gain - 2.0) < 1e-9


def test_capture_early_requires_room_left():
    m = _market(_run_up())
    W = np.arange(0, m.n, 5)
    ep = [(0, 99, 199, 2.0)]
    L = np.zeros((len(W), 1), dtype=bool)
    L[np.searchsorted(W, 190), 0] = True                      # 快到頂才出現：抓到但不算早
    x = WT.capture(ep, L, W, m.c, m.h)[0]
    assert x["hit"] and not x["early"]
    L[np.searchsorted(W, 60), 0] = True                       # 起漲前 39 天出現：抓得早
    x = WT.capture(ep, L, W, m.c, m.h)[0]
    assert x["hit"] and x["early"] and abs(x["rem"] - 2.0) < 1e-9
    L[:] = False
    L[np.searchsorted(W, 20), 0] = True                       # 比起漲點早超過 60 天：不算
    assert not WT.capture(ep, L, W, m.c, m.h)[0]["hit"]


def test_random_lists_keep_weekly_size_within_eligible():
    rng = np.random.default_rng(1)
    L = np.zeros((10, 50), dtype=bool)
    L[:, :7] = True
    el = np.ones((10, 50), dtype=bool)
    el[:, 40:] = False
    R = WT.random_lists(L, el, rng)
    assert (R.sum(axis=1) == 7).all() and not R[:, 40:].any()


def test_choose_applies_size_lift_and_ranks_by_early_super():
    good = {"size": 20, "rlift_early_C": 2.0, "lift_B": 2.0, "early_C": 0.4, "early_B": 0.3}
    big = {**good, "size": 80, "early_C": 0.9}
    weak = {**good, "rlift_early_C": 1.1, "early_C": 0.6}
    stats = {"S1": {"IS": good, "VAL": good}, "S2": {"IS": big, "VAL": big}, "S3": {"IS": weak, "VAL": weak}}
    assert WT.choose(stats) == "S1"
    assert WT.choose({"S2": {"IS": big, "VAL": big}}) is None


def test_preregistered_constants():
    assert WT.LABELS == {"A": (60, 0.5), "B": (250, 1.0), "C": (250, 2.0)}
    assert (WT.SIZE_MAX, WT.PRE, WT.GAP, WT.EARLY, WT.N_RAND, WT.LIFT_MIN) == (30, 60, 20, 0.5, 20, 1.5)
    assert list(WT.SCREENS) == [f"S{k}" for k in range(1, 10)]
