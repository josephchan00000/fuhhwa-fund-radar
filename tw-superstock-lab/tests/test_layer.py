"""W2／W3 研究：技術指標向量化版與 fuhhwa 純 Python 版逐日一致；第二層篩選的評估函式。"""

import numpy as np
import pandas as pd
import pytest

from superstock import engine as EN
from superstock import features as FT
from superstock import layer as LA
from superstock import sepa as SE

SP = SE.shared()


def _market(T=520, N=4, seed=7):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, (T, N)), axis=0))
    h = c * (1 + np.abs(rng.normal(0, 0.01, (T, N))))
    l = c * (1 - np.abs(rng.normal(0, 0.01, (T, N))))
    o = c * (1 + rng.normal(0, 0.005, (T, N)))
    v = rng.uniform(5e5, 2e6, (T, N))
    dates = pd.bdate_range("2015-01-01", periods=T)
    tr = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, T))), index=dates)
    return EN.Market(dates, [f"{1000 + j}" for j in range(N)], o, h, l, c, value=c * v, volume=v, index_tr=tr)


def _l(a):
    return [None if x != x else float(x) for x in a]


def test_tight_matches_pure():
    m = _market()
    hi52 = pd.DataFrame(m.h).rolling(252, min_periods=200).max().to_numpy()
    ok, H, L = SE.tight(m, hi52, 10, 0.08, SP.NEAR_HIGH)
    for j in range(m.c.shape[1]):
        h, l, c = _l(m.h[:, j]), _l(m.l[:, j]), _l(m.c[:, j])
        for t in range(260, m.n):
            r = SP.tight_at(h, l, c, None if hi52[t, j] != hi52[t, j] else float(hi52[t, j]), t, 10, 0.08)
            assert bool(ok[t, j]) == (r is not None), (t, j)
            if r:
                assert r == (H[t, j], L[t, j])


def test_rs_line_matches_pure():
    m = _market()
    new, lead = SE.rs_line(m)
    idx = _l(m.index_tr.to_numpy())
    for j in range(m.c.shape[1]):
        c = _l(m.c_ff[:, j])
        for t in range(220, m.n):
            assert (bool(new[t, j]), bool(lead[t, j])) == SP.rsl_at(c, idx, t), (t, j)


def test_ma200_and_base_counts_match_pure():
    m = _market()
    ma, prev, up = SE.ma200_up(m)
    for j in range(m.c.shape[1]):
        pma, pprev, pup = SP.ma200_info(_l(m.c_ff[:, j]))
        assert list(up[:, j]) == pup
        for t in range(m.n):
            assert (pma[t] is None) == (ma[t, j] != ma[t, j])
            if pma[t] is not None:
                assert abs(pma[t] - ma[t, j]) < 1e-9 * pma[t]
    b = SE.base_no(m, ma, prev)
    for j in range(m.c.shape[1]):
        assert list(b[:, j]) == SP.base_counts(_l(m.c_ff[:, j]), _l(ma[:, j]), _l(prev[:, j]))


def test_ud_ratio_matches_pure():
    m = _market()
    r = SE.ud_ratio(m)
    for j in range(m.c.shape[1]):
        c, v = _l(m.c[:, j]), _l(m.vol[:, j])
        for t in range(m.n):
            p = SP.ud_at(c, v, t)
            if p is None:
                assert r[t, j] != r[t, j], (t, j)
            else:
                assert abs(p - r[t, j]) < 1e-9 * max(1.0, p), (t, j)


def _surge_market():
    """第 2 檔在 200～230 日 1 個月漲 1 倍（有一天 3 倍量），之後橫盤 → 爆發型。"""
    m = _market(T=320, N=3, seed=3)
    c, h, l, v = m.c.copy(), m.h.copy(), m.l.copy(), m.vol.copy()
    base = c[199, 1]
    for k in range(200, 320):
        x = base * (1 + min(k - 199, 30) / 30) * (1 + 0.01 * np.sin(k)) if k < 235 else base * 1.9 * (1 + 0.02 * np.sin(k))
        c[k, 1], h[k, 1], l[k, 1] = x, x * 1.01, x * 0.99
    v[210, 1] = 3 * v[150:200, 1].mean()
    return EN.Market(m.dates, m.stocks, c, h, l, c, value=c * v, volume=v, index_tr=m.index_tr)


def test_power_play_prefilter_keeps_every_pure_hit():
    m = _surge_market()
    el = np.ones(m.c.shape, dtype=bool)
    vo = FT.volume(m)
    ok, piv, low = SE.power_play(m, el, vo["vol50"], vo["dry"])
    hits = 0
    for j in range(m.c.shape[1]):
        h, l, c, v, v50 = _l(m.h[:, j]), _l(m.l[:, j]), _l(m.c_ff[:, j]), _l(m.vol[:, j]), _l(vo["vol50"][:, j])
        for t in range(70, m.n):
            dy = vo["dry"][t, j]
            r = SP.pp_at(h, l, c, v, v50, float(m.c[t, j]), None if dy != dy else float(dy), t)
            assert bool(ok[t, j]) == (r is not None), (t, j)
            hits += r is not None
    assert hits > 0


def test_statuses_match_pure_loop():
    m = _market(T=420, N=3, seed=11)
    F = FT.compute(m, None, FT.VCP_V2)
    rng = np.random.default_rng(5)
    S9 = rng.random(m.c.shape) < 0.6
    PP = (np.zeros(m.c.shape, bool), np.full(m.c.shape, np.nan), np.full(m.c.shape, np.nan))
    TG = SE.tight(m, F["hi52"], 10, 0.08, SP.NEAR_HIGH)
    S = SE.statuses(m, F, S9, PP, TG)
    for j in range(m.c.shape[1]):
        tr = SP.Track()
        c, vol, v50, dry, ma50 = (_l(a[:, j]) for a in (m.c, m.vol, F["vol50"], F["dry"], F["ma50"]))
        started = False
        for t in range(m.n):
            on = bool(S9[t, j])
            started = started or on
            if not started:
                assert S["st"][t, j] == -1
                continue
            ready = None
            if on and c[t] is not None:
                vc = (float(F["vcp_pivot"][t, j]), float(F["vcp_low"][t, j])) if F["vcp_ok"][t, j] else None
                tg = (float(TG[1][t, j]), float(TG[2][t, j])) if TG[0][t, j] else None
                ready = SP.ready_at(on, bool(F["elig"][t, j]), c[t], dry[t], vc, tg, None)
            s = tr.step(t, c[t], vol[t], v50[t - 1] if t else None, ma50[t], on, ready)[0]
            assert S["st"][t, j] == s, (t, j)
    assert (S["st"] >= 0).any()


# ---------------------------------------------------------------------------------------------- 評估
def _toy_tab():
    """3 檔 × 30 週：條件 ud12 成立的股票週命中率較高。"""
    LY, _, _ = LA.shared()
    rows = []
    rng = np.random.default_rng(1)
    dates = [f"2015-{(k // 4) + 1:02d}-{(k % 4) * 7 + 1:02d}" for k in range(30)]
    for k in range(30):
        for j in range(3):
            cond = {key: False for key in LY.CKEYS}
            cond["ud12"] = j == 0
            cond["rsl"] = k % 2 == 0
            y = int(rng.random() < (0.6 if j == 0 else 0.2))
            rows.append({"k": k, "j": j, "c": str(j), "d": dates[k], "x": [cond[key] for key in LY.CKEYS],
                         "fam": LY.families(cond), "y": {"A": y, "B": y, "C": 0}})
    return LA.Tab({"rows": rows, "dates": dates, "W": list(range(30)), "base": {}}), dates


def test_tab_stat_new_entry_and_tier():
    T, dates = _toy_tab()
    a, b = dates[0], dates[-1]
    allm = np.ones(len(T.d), dtype=bool)
    s = T.stat(allm, a, b)
    assert s["n"] == 90 and s["per_week"] == 3
    ne = T.new_entry(allm, gap=13)
    assert ne.sum() == 3 * 3                       # 每檔 30 週裡第 0、13、26 週
    curve = LA.score_curve(T, a, b)
    assert [c["s"] for c in curve] == list(range(8))
    assert curve[0]["ge"]["n"] == 90
    s_star = LA.pick_tier(curve, s["p"])
    assert s_star >= 1


def test_greedy_picks_the_informative_condition():
    T, dates = _toy_tab()
    subs = {"IS1": (dates[0], dates[14]), "IS2": (dates[15], dates[-1])}
    old = dict(LA.GREEDY)
    LA.GREEDY.update({"pos": 5, "per_week": 0.5})
    try:
        steps = LA.greedy(T, dates[0], dates[-1], subs, exclude=("arule", "brule"))
    finally:
        LA.GREEDY.update(old)
    assert steps and steps[0]["add"] == "ud12"


def test_capture_w():
    W = np.array([0, 5, 10, 15, 20])
    Cw = np.array([[10.0], [10.0], [12.0], [20.0], [30.0]], dtype=np.float32)
    eps = [(0, 6, 22, 2.0, 30.0)]                  # 起漲第 6 日、高點第 22 日、高點價 30
    L = np.array([[False], [False], [True], [False], [False]])
    r = LA.capture_w(eps, L, W, Cw, 0.5)
    assert r == {"n": 1, "hit": 1, "early": 1, "p_early": 1.0}
    L2 = np.array([[False], [False], [False], [False], [True]])   # 第 20 日才列出、收盤 30 → 不算早
    assert LA.capture_w(eps, L2, W, Cw, 0.5)["early"] == 0


def test_pair_search_needs_both_conditions():
    LY, _, _ = LA.shared()
    rows = []
    rng = np.random.default_rng(2)
    dates = [f"2015-{(k // 4) + 1:02d}-{(k % 4) * 7 + 1:02d}" for k in range(40)]
    for k in range(40):
        for j in range(6):
            cond = {key: False for key in LY.CKEYS}
            cond["mom10"], cond["eacc"] = j in (0, 1), j in (0, 2)
            y = int(rng.random() < (0.7 if j == 0 else 0.15))      # 只有兩個都成立的那檔命中率高
            rows.append({"k": k, "j": j, "c": str(j), "d": dates[k], "x": [cond[key] for key in LY.CKEYS],
                         "fam": LY.families(cond), "y": {"A": y, "B": y, "C": 0}})
    T = LA.Tab({"rows": rows, "dates": dates, "W": list(range(40)), "base": {}})
    old = dict(LA.GREEDY)
    LA.GREEDY.update({"pos": 5, "per_week": 0.5})
    try:
        r = LA.pair_search(T, dates[0], dates[-1], {"IS1": (dates[0], dates[19]), "IS2": (dates[20], dates[-1])},
                           exclude=LY.LIST_ONLY)
    finally:
        LA.GREEDY.update(old)
    assert r["tried"] == 26 * 25 // 2
    assert r["best"]["pair"] == ["eacc", "mom10"]
