"""參數鄰近檢查的程式（arm/lab/sigrobust.py；nbrspec VER 1）。用造出來的資料，不讀落檔。"""
import numpy as np
import pytest

from arm.lab import crashspec as CS
from arm.lab import heatspec as HS
from arm.lab import heatspec_us as U
from arm.lab import heattech as TT
from arm.lab import hotchspec as HCS
from arm.lab import hotddspec as HDS
from arm.lab import nbrspec as N
from arm.lab import sigrobust as R
from arm.lab import sigspec as S


def _px(n=1400, seed=7):
    rnd = np.random.default_rng(seed)
    r = rnd.normal(0.0003, 0.012, n)
    r[300:340] -= 0.01                                   # 一段急跌、一段急漲，均線與轉折點才有事件
    r[700:760] += 0.008
    return [float(x) for x in 100 * np.exp(np.cumsum(r))]


def test_tech_events_default_equals_all_events_and_params_matter():
    px = _px()
    base = R.tech_events(px, R.tech_params())
    assert base == TT.all_events(px)
    assert sum(len(v) for v in base.values()) > 20
    for dim, v in (("ma20", 22), ("ma60", 54), ("ma240", 216), ("tpr", 8), ("tcf", 2), ("pv", 0.04)):
        assert R.tech_events(px, R.tech_params(**{dim: v})) != base, dim     # 參數真的有傳進去


def test_patched_restores_even_on_error():
    old = (S.HOT, S.COLD, HS.EVT, HDS.HOT, HCS.HOT)
    with pytest.raises(ValueError):
        with R.patched(*R.th_pairs(75, 25)):
            assert (S.HOT, S.COLD, HDS.HOT, HCS.HOT) == (75, 25, 75, 75) and HS.EVT == {"hot": (75, 20), "cold": (25, 20)}
            raise ValueError
    assert (S.HOT, S.COLD, HS.EVT, HDS.HOT, HCS.HOT) == old
    with R.patched(*R.prior_pairs(15)):
        assert HS.EVT == {"hot": (80, 15), "cold": (20, 15)} and HDS.EVT_PRIOR == 15
    assert HS.EVT == {"hot": (80, 20), "cold": (20, 20)} and HDS.EVT_PRIOR == 20


def test_windows_change_and_restore_shared_dicts():
    w0, m0 = dict(HS.PCT_WIN), dict(HS.PCT_MIN)
    for i in range(2):
        with R.windows(i):
            assert HS.PCT_WIN == {"d": N.WIN["d"][i][0], "m": N.WIN["m"][i][0]}
            assert HS.PCT_MIN == {"d": N.WIN["d"][i][1], "m": N.WIN["m"][i][1]}
            assert U.PCT_WIN is HS.PCT_WIN                   # 美股用的是同一個 dict
            assert HS.PCT_WIN_ITEM["X2"] == N.WIN["d10"][i] and U.PCT_WIN_ITEM["S5"] == N.WIN["q10"][i]
            assert set(U.spec_for("spx")["PCT_WIN_ITEM"].values()) <= {N.WIN["d10"][i], N.WIN["q10"][i]}
            assert CS.PCT_DAILY == N.WIN["cd"][i] and CS.PCT_MONTHLY == N.WIN["cm"][i]
    assert HS.PCT_WIN == w0 and HS.PCT_MIN == m0 and HS.PCT_WIN_ITEM == {"X2": (2500, 1250), "X3": (2500, 1250)}
    assert CS.PCT_DAILY == (750, 375) and CS.PCT_MONTHLY == (36, 36)


def test_same_and_passes():
    a = {"kind": "event", "days": [3, 5]}
    assert R.same(a, {"kind": "event", "days": np.array([3, 5])}) and not R.same(a, {"kind": "event", "days": [3]})
    s = {"kind": "state", "samp": np.arange(4), "state": np.array([1, 0, 1, 0], dtype=bool)}
    assert R.same(s, {**s}) and not R.same(s, {**s, "state": np.array([1, 1, 1, 0], dtype=bool)})
    assert R.same(None, None) and not R.same(a, None)
    assert R.passes({"n": 5, "hit": 0.65, "base": 0.60}) and not R.passes({"n": 4, "hit": 0.9, "base": 0.5})
    assert not R.passes({"n": 9, "hit": 0.64, "base": 0.60}) and not R.passes(None) and R.passes([7, 0.7, 0.6])


def test_targets_scope_and_true_threshold():
    rows = [{"id": "tw:heat:B1:hot", "mk": "tw", "cat": "heat", "H": 60, "th": 0.1,
             "up": {"n": 9, "hit": 0.70, "base": 0.60}, "warn": {"n": 9, "hit": 0.30, "base": 0.40},
             "xh": {"short": {"H": 20, "th": 0.08, "up": {"n": 9, "hit": 0.66, "base": 0.60}, "warn": None},
                    "long": {"H": 250, "th": 0.2, "up": {"n": 3, "hit": 0.99, "base": 0.6}, "warn": None}}},
            {"id": "tw:buy:E5:C3", "mk": "tw", "cat": "buy", "H": 60, "buy": {"n": 6, "hit": 0.8, "base": 0.6}},
            {"id": "ind:tw:L2", "mk": "tw", "cat": "ind", "H": 12, "up": {"n": 9, "hit": 0.9, "base": 0.5}}]
    T = R.targets(rows)
    assert [(t["id"], t["d"], t["H"], t["k"]) for t in T] == [("tw:heat:B1:hot", "up", 60, None),
                                                            ("tw:heat:B1:hot", "up", 20, "short"),
                                                            ("tw:buy:E5:C3", "buy", 60, None)]
    from arm.lab import sigcat as G
    assert T[0]["th"] == G.warn_th("tw", 60) and T[1]["th"] == G.warn_th("tw", 20) and T[2]["th"] == G.warn_th("tw", 60)


def test_dims_of_each_category():
    d = lambda cat, sig=None, var=None, i="x:y:z:w": R.dims_of({"cat": cat, "sig": sig, "var": var, "id": i}, "tw")  # noqa: E731
    assert d("heat", "hot13") == ("th", "wk", "win") and d("bd", "hot_in") == ("th", "pr", "win")
    assert d("inst", "cold_out") == ("th", "ex", "win", "iw") and d("inst", "day_buy") == ("tail", "win")
    assert d("inst", "sell_run10") == ("run",) and d("multi", "hot_in") == ("th", "pr", "win") and d("scen") == ("hl", "win")
    assert d("tech", var="x_gold") == ("ma20", "ma60", "tpr", "tcf") and d("bub", var="L3") == tuple(N.BUB)
    assert d("deriv", var="B1") == ("L1", "L2") and d("deriv", var="C1") == ("L1", "L2", "smooth")
    assert d("buy", i="tw:buy:E5:W10") == ("e5th", "e5d", "wait") and d("buy", i="tw:buy:E10:B1") == ("e10",)
    assert d("buy", i="tw:buy:E10:C9") == ("e10", "sigwin", "c9")


def test_halves_split_counts_and_bases():
    from datetime import date, timedelta
    T = 400
    px = np.array([100.0 + (t % 50) for t in range(T)])
    cal = [(date(2010, 1, 1) + timedelta(days=t)).isoformat() for t in range(T)]
    sd = {"kind": "event", "samp": np.arange(T), "days": [10, 100, 250, 300]}
    hv = R.halves(px, cal, cal[0], sd, 20, 0.05, {})
    assert len(hv) == 2 and hv[0]["up"][0] == 2 and hv[1]["up"][0] == 2
    st = {"kind": "state", "samp": np.arange(T), "state": (np.arange(T) // 50) % 2 == 0}   # 四段，前後兩半各兩段
    hv = R.halves(px, cal, cal[0], st, 20, 0.05, {})
    full = R.stats(px, cal, cal[0], st, 20, 0.05, {})
    assert hv[0]["up"][0] == hv[1]["up"][0] == 2 and full["up"][0] == 4
    assert R.halves(px, cal, cal[0], {"kind": "event", "samp": np.arange(1), "days": []}, 20, 0.05, {}) == []


def test_filtered_rows_drop_only_unstable_parts():
    rows = [{"id": "a", "up": {"n": 9, "hit": 0.7, "base": 0.6}, "xh": {"short": {"up": {"n": 9}, "warn": {"n": 9}}}},
            {"id": "b", "up": {"n": 9, "hit": 0.7, "base": 0.6}}]
    out = [{"id": "a", "d": "up", "k": None, "ok": False}, {"id": "a", "d": "warn", "k": "short", "ok": False},
           {"id": "b", "d": "up", "k": None, "ok": None}]
    f = R.filtered_rows(rows, out)
    assert f[0]["up"]["hit"] is None and f[0]["xh"]["short"]["warn"] is None and f[0]["xh"]["short"]["up"] == {"n": 9}
    assert f[1] is rows[1] and rows[0]["up"]["hit"] == 0.7                   # 原本的列不動
