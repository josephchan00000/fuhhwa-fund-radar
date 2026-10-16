"""combos（綜合策略族）與 validate（DSR、參數鄰近、隨機）：人造資料驗證。"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from superstock import combos as CB
from superstock import engine as EN
from superstock import features as FT
from superstock import validate as VD


def _market(T: int = 320, N: int = 4, seed: int = 3) -> EN.Market:
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0008, 0.02, (T, N))
    c = 100 * np.exp(np.cumsum(r, axis=0))
    o = c * (1 + rng.normal(0, 0.003, (T, N)))
    h, l = np.maximum(o, c) * 1.01, np.minimum(o, c) * 0.99
    v = np.full((T, N), 2e6)
    dates = pd.bdate_range("2015-01-01", periods=T)
    return EN.Market(dates, [f"{1000 + k}" for k in range(N)], o, h, l, c, value=c * v, volume=v)


def _ctx(m: EN.Market, a_rows=()) -> CB.Ctx:
    F = FT.compute(m)
    return CB.Ctx(m, F, lambda c, i: {}, list(a_rows), [])


def test_pullback_only_looks_forward_and_needs_trend():
    m = _market()
    ctx = _ctx(m)
    mask = np.zeros(m.c.shape, dtype=bool)
    mask[250, 0] = True
    out = CB.pullback(ctx, mask, CB.BASE)
    hits = np.flatnonzero(out[:, 0])
    assert all(250 < d <= 270 for d in hits) and len(hits) <= 1
    ma20, ma50 = ctx.ma(20), ctx.ma(50)
    for d in hits:
        assert m.c[d, 0] <= ma20[d, 0] * 1.01 and m.c[d, 0] > ma50[d, 0]
    m.c[:251, 0] *= 1.0                                           # 訊號日以前的資料不影響結果（只看之後）
    c2 = m.c.copy()
    c2[271:, 0] = 1.0
    m2 = EN.Market(m.dates, m.stocks, m.o, m.h, m.l, c2, value=m.val, volume=m.vol)
    ctx2 = _ctx(m2)
    assert (CB.pullback(ctx2, mask, CB.BASE)[:271] == out[:271]).all()


def test_watch_window_covers_next_weeks_only():
    m = _market()
    W = CB._week_ends(m.dates)
    k = 20
    w0 = W[k]
    ctx = _ctx(m, [(m.stocks[1], str(m.dates[w0].date()))])
    w = ctx.watch(8)
    end = W[k + 8]
    assert w[w0, 1] and not w[w0 - 1, 1]                          # 從訊號那個週末起算
    assert w[end - 1, 1] and not w[end, 1]                        # 到第 8 個之後的週末前一天為止
    assert not w[:, [0, 2, 3]].any()


def test_fast_run_matches_engine_run_trades():
    m = _market(N=6)
    ctx = _ctx(m)
    sig = pd.DataFrame({"date": m.dates[[260, 270, 280]], "stock_id": [m.stocks[0], m.stocks[2], m.stocks[4]],
                        "entry": "open", "stop_pct": 0.08, "score": [3.0, 2.0, 1.0], "tag": "t"})
    ex = pd.DataFrame(CB.exit_flags(ctx, 50), index=m.dates, columns=m.stocks)
    cfg = EN.EngineConfig(breakeven_r=2.0, market_filter=False, block_disposition=False)
    a = EN.run_trades(m, sig, cfg, exit_flags=ex)
    b = CB.run(ctx, sig, market=False, mf=np.ones(m.n, dtype=bool), ma_exit=50, max_hold=None)
    assert np.allclose(a.equity.to_numpy(), b.equity.to_numpy())
    assert len(a.trades) == len(b.trades)


def test_random_signals_same_days_and_count_different_stocks():
    m = _market(N=6)
    ctx = _ctx(m)
    ctx.F["elig"][:] = True
    sig = pd.DataFrame({"date": m.dates[[100, 100, 150]], "stock_id": [m.stocks[0], m.stocks[1], m.stocks[2]],
                        "stop_pct": 0.08})
    r = CB.random_signals(ctx, sig, np.random.default_rng(1))
    assert list(r["date"]) == list(sig["date"])
    assert all(a != b for a, b in zip(r["stock_id"], sig["stock_id"]))


def test_dsr_penalizes_more_trials():
    rng = np.random.default_rng(0)
    few = list(rng.normal(0.0, 0.02, 5)) + [0.08]
    many = list(rng.normal(0.0, 0.02, 200)) + [0.08]
    a = VD.dsr(0.08, 750, 0.0, 3.0, few)["dsr"]
    b = VD.dsr(0.08, 750, 0.0, 3.0, many)["dsr"]
    assert a > b
    # 只有一個顯著好的試驗、試驗數少：DSR 接近 1
    assert VD.dsr(0.15, 1500, 0.0, 3.0, [0.0, 0.01, 0.15])["dsr"] > 0.95


def test_sr_per_obs_and_plateau_and_pct_rank():
    assert math.isclose(VD.sr_per_obs(math.sqrt(252), 252, 1.0), 1.0)
    assert VD.plateau(1.0, [0.9, 0.8, 1.1, 0.95])["ok"]
    assert not VD.plateau(2.0, [0.9, 0.8, 1.1, 0.95])["ok"]          # 孤峰
    assert not VD.plateau(0.5, [-0.1, -0.2, 0.0])["ok"]
    assert VD.pct_rank(5, [1, 2, 3, 4, 6]) == 0.8


def test_configs_are_the_preregistered_84():
    assert len(CB.configs()) == 84
    assert CB.BASE == {"stop_pct": 0.08, "breakeven_r": 2.0, "vol": 1.5, "watch_weeks": 8, "rev_yoy": 0.20,
                       "pull_days": 20, "pull_tol": 0.01}
    assert CB.EXITS == {"X1": {"ma_exit": 50, "max_hold": None}, "X2": {"ma_exit": 20, "max_hold": None},
                        "X3": {"ma_exit": None, "max_hold": 60}}
