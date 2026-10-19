"""部位參考（arm/lab/pos.py；docs/lab_crash_plan.md 第 18 節）：和逐筆直接算的版本比對。"""
import math

import numpy as np

from arm.lab import pos as P
from arm.lab import posspec as S


def _px(T=1600, seed=3):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, T)))


def test_vol20_and_target_match_direct():
    px = _px()
    r = P.daily_returns(px)
    v = P.vol20(r)
    lr = np.log1p(r)
    for t in (S.VOL_N, 100, 777, len(px) - 1):
        assert abs(v[t] - np.std(lr[t - S.VOL_N + 1:t + 1], ddof=1) * math.sqrt(252)) < 1e-10
    assert np.isnan(v[S.VOL_N - 1])
    tg = P.target_vol(v)
    assert np.isnan(tg[S.VOL_WARM - 1])
    for t in (S.VOL_WARM, 1400, len(px) - 1):
        prior = v[:t][~np.isnan(v[:t])]
        assert abs(tg[t] - prior.mean()) < 1e-12               # 只用到前一天
    p1 = P.r1_pos(v, tg)
    assert np.nanmax(p1) <= 1.0 and abs(p1[1400] - min(1.0, tg[1400] / v[1400])) < 1e-12


def _sim_ref(r, tgt, cost, s0):
    w, nav, out, pend = 1.0, 1.0, [], None
    for t in range(s0, len(r)):
        nav = nav * (1 + w * r[t])
        if pend is not None and not math.isnan(pend) and abs(pend - w) >= S.BAND - 1e-12:
            nav = nav * (1 - abs(pend - w) * cost)
            w = pend
        pend = tgt[t]
        out.append((nav, w))
    return out


def test_simulate_trades_one_day_later_with_band_and_cost():
    r = np.array([0.0, 0.01, -0.02, 0.03, 0.01, -0.01, 0.02])
    tgt = np.array([1.0, 0.5, 0.55, 0.95, 1.0, 0.3, 0.3])
    sm = P.simulate(r, tgt, 0.001, 1)
    ref = _sim_ref(r, tgt, 0.001, 1)
    assert np.allclose(sm["nav"], [x for x, _ in ref]) and np.allclose(sm["w"], [x for _, x in ref])
    # 第 1 天收盤決定 50%，第 2 天收盤才調整（第 2 天的報酬仍是 100% 部位）；0.55 和 0.5 差不到 10 點不調整
    assert list(sm["w"]) == [1.0, 0.5, 0.5, 0.95, 0.95, 0.3] and sm["n_tr"] == 3
    assert abs(sm["nav"][1] - 1.01 * (1 - 0.02) * (1 - 0.5 * 0.001)) < 1e-12
    full = P.simulate(r, np.ones(len(r)), 0.001, 1)
    assert full["n_tr"] == 0 and abs(full["nav"][-1] - np.prod(1 + r[1:])) < 1e-12


def test_metrics_drawdown_and_verdict():
    nav = np.array([1.0, 1.1, 0.88, 0.99, 1.2, 1.08])
    pr = np.concatenate([[0.0], nav[1:] / nav[:-1] - 1])
    m = P.metrics(nav, pr, np.ones(6), 3)
    assert abs(m["mdd"] - 0.2) < 1e-12 and m["dd_days"] == 2 and abs(m["tr_y"] - 3 / (6 / 252)) < 1e-9
    base = {"mdd": 0.40, "cagr": 0.10}
    assert P.verdict({"mdd": 0.34, "cagr": 0.095}, base) == "better"
    assert P.verdict({"mdd": 0.30, "cagr": 0.08}, base) == "trade"
    assert P.verdict({"mdd": 0.37, "cagr": 0.12}, base) == "none"


def test_activity_windows_and_targets():
    a = P.active_state(10, [2, 5, 8], [True, False, True], monthly=True)
    assert list(np.nonzero(a)[0]) == [2, 3, 4, 8, 9]
    assert list(np.nonzero(P.active_state(10, [2, 5, 8], [True, False, True]))[0]) == [2, 8]
    assert list(np.nonzero(P.active_event(10, [1, 7], 3, start=2))[0]) == [7, 8, 9]   # 第 1 天在樣本起點之前
    p1 = np.array([np.nan, 0.8, 0.8, 0.8, 0.8])
    act = {"warn": np.array([0, 1, 1, 0, 0], bool), "buy": np.array([0, 0, 1, 0, 0], bool), "up": np.array([0, 0, 0, 1, 0], bool)}
    T = P.targets(p1, act)
    assert np.isnan(T["vwb"][0]) and list(T["vw"][1:]) == [0.5, 0.5, 0.8, 0.8]
    assert list(T["vwb"][1:]) == [0.5, 1.0, 0.8, 0.8] and list(T["vwbu"][1:]) == [0.5, 1.0, 1.0, 0.8]
    assert list(T["full"][1:]) == [1.0] * 4


def test_star_ids_and_spx_dividend():
    rows = [{"mk": "tw", "tier": "good", "dir": ["warn"], "id": "a"}, {"mk": "tw", "tier": "good", "dir": ["up", "warn"], "id": "b"},
            {"mk": "tw", "tier": "ref", "dir": ["warn"], "id": "c"}, {"mk": "spx", "tier": "good", "dir": ["buy"], "id": "d"}]
    assert P.star_ids(rows, "tw") == {"warn": ["a", "b"], "buy": [], "up": ["b"]}
    d = P.spx_div(["2026-08-31", "2026-09-30", "2026-10-15"], {"2026-08": [100.0, 2.0], "2026-09": [200.0, 3.0], "2026-10": [210.0, None]})
    assert np.allclose(d, [0.02 / 252, 0.015 / 252, 0.015 / 252])                # 最新月份沒有股利：沿用最後一個比例


def test_now_uses_overview_active_signals():
    px = _px(1500)
    cal = [f"d{i:05d}" for i in range(1500)]
    ids = {"warn": ["w1"], "buy": ["b1"], "up": ["u1"]}
    n = P.now("tw", cal, px, {"w1": {"since": cal[1490]}}, ids)
    assert n["warn"] == ["w1"] and n["buy"] == [] and n["pos"]["vw"] == min(n["pos"]["v"], 0.5) and n["pos"]["full"] == 1.0
    n2 = P.now("tw", cal, px, {"b1": {"since": cal[1499 - 59]}, "w1": {}}, ids)
    assert n2["buy"] == ["b1"] and n2["pos"]["vwb"] == 1.0
    assert P.now("tw", cal, px, {"b1": {"since": cal[1499 - 60]}}, ids)["buy"] == []      # 出現已 60 個交易日
    assert P.now("tw", cal[:100], px[:100], {}, ids) is None                              # 還在暖身期
