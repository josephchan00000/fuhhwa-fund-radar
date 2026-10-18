"""泡沫面向的模型（arm/lab/heatbubble.py；docs/lab_heat_us_plan.md 第 15.5、15.7 節）：和直接算的版本逐項比對。"""
import math
import random

import pytest

from arm.lab import heatbubble as B
from arm.lab import heatspec as S


def _ols_t(y: list, r1: int, t: int) -> float:
    """直接解 Δy_s ＝ a ＋ b y_{s−1}（s＝r1＋1…t），回 b 的 t 值。"""
    xs = [y[s - 1] for s in range(r1 + 1, t + 1)]
    zs = [y[s] - y[s - 1] for s in range(r1 + 1, t + 1)]
    n = len(xs)
    mx, mz = sum(xs) / n, sum(zs) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (z - mz) for x, z in zip(xs, zs)) / sxx
    a = mz - b * mx
    s2 = sum((z - a - b * x) ** 2 for x, z in zip(xs, zs)) / (n - 2)
    return b / math.sqrt(s2 / sxx)


def test_adf_and_bsadf_match_direct_ols():
    rnd = random.Random(7)
    y = [0.0]
    for _ in range(59):
        y.append(y[-1] + rnd.gauss(0, 1))
    P = B._prefix(y)
    for r1, t in ((0, 59), (5, 30), (20, 59), (40, 59)):
        assert B.adf_window(P, r1, t) == pytest.approx(_ols_t(y, r1, t), rel=1e-9, abs=1e-9)
    w0 = 12
    st = B.bsadf(y, w0)
    assert all(v is None for v in st[:w0 - 1])
    for t in (w0 - 1, 25, 59):
        assert st[t] == pytest.approx(max(_ols_t(y, r1, t) for r1 in range(0, t - w0 + 2)), rel=1e-9)


def test_psy_cv_reproducible_and_heat_mapping():
    np = pytest.importorskip("numpy")  # noqa: F841 —— 模擬只在研究時用
    a = B.psy_cv(10, 60, 30, 123)
    b = B.psy_cv(10, 60, 30, 123)
    assert a == b and a["q50"][:9] == [None] * 9
    assert all(lo < hi for lo, hi in zip(a["q50"][9:], a["q95"][9:]))
    lo, hi = S.PSY["map"]
    assert B.psy_heat(1.0, 1.0, 2.0) == lo and B.psy_heat(2.0, 1.0, 2.0) == hi
    assert B.psy_heat(-50.0, 1.0, 2.0) == 0.0 and B.psy_heat(50.0, 1.0, 2.0) == 100.0
    assert B.psy_heat(1.0, 2.0, 1.0) is None and B.psy_heat(None, 1.0, 2.0) is None


def test_psy_monthly_restarts_after_gap(monkeypatch):
    monkeypatch.setitem(S.PSY, "w0", 5)
    rnd = random.Random(5)
    seg1 = [f"2000-{m:02d}" for m in range(1, 13)]
    seg2 = [f"2002-{m:02d}" for m in range(1, 13)]                            # 2001 整年缺：缺口之後重新起算
    M = {k: rnd.gauss(0, 1) for k in seg1 + seg2}
    cv = {"q50": [0.0] * 24, "q95": [1.0] * 24}
    raw, heat = B.psy_monthly(M, cv)
    for seg in (seg1, seg2):
        st = B.bsadf([M[k] for k in seg], 5)
        assert [raw.get(k) for k in seg] == st
    assert min(raw) == "2000-05" and min(k for k in raw if k >= "2002") == "2002-05"
    assert heat["2002-05"] == B.psy_heat(raw["2002-05"], 0.0, 1.0)            # 臨界值用「這一段的第幾個月」


def test_trend_z_and_detrended_pct():
    rnd = random.Random(3)
    M = {}
    for i in range(300):
        y, m = 1950 + i // 12, i % 12 + 1
        M[f"{y}-{m:02d}"] = 0.01 * i + rnd.gauss(0, 0.05)
    z, hz = B.trend_z(M, 240)
    ks = sorted(M)
    assert len(z) == 300 - 239 and min(z) == ks[239]
    xs = list(range(300))
    ys = [M[k] for k in ks]
    n = 300
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    s = math.sqrt(sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / (n - 2))
    assert z[ks[-1]] == pytest.approx((ys[-1] - a - b * xs[-1]) / s, rel=1e-9)
    lo, k15 = S.TREND["map"]
    assert hz[ks[-1]] == pytest.approx(max(0, min(100, lo + k15 * z[ks[-1]])))
    exact = {k: math.exp(0.002 * i) for i, k in enumerate(ks)}
    d = B.detrended_pct(exact, 240)
    assert len(d) == 61 and max(abs(v) for v in d.values()) < 1e-6


def test_runup_accel_net_runup():
    px = [100.0, 110.0, 121.0, 133.1, 146.41]
    assert B.runup(px, 2)[2] == pytest.approx(21.0) and B.runup(px, 2)[:2] == [None, None]
    acc = B.accel(px, 4, 2)
    assert acc[:4] == [None] * 4 and acc[4] == pytest.approx(0.0, abs=1e-9)           # 一直等速上漲＝加速度 0
    ref = [10.0, 10.0, 10.0, 10.0, 10.0]
    assert B.net_runup(px, ref, 4)[4] == pytest.approx(100 * math.log(1.4641))


def _lppls_series(n: int, tc: float, m: float, w: float) -> list[float]:
    A, Bc, C1, C2 = 5.0, -0.02, 0.0008, 0.0006
    out = []
    for t in range(n):
        f = (tc - t) ** m
        out.append(math.exp(A + Bc * f + C1 * f * math.cos(w * math.log(tc - t)) + C2 * f * math.sin(w * math.log(tc - t))))
    return out


SMALL = {"dt": (30, 120, 10), "m": (0.3, 0.5, 0.7), "w": (6.0, 8.0, 10.0), "tc": (5, 10, 20),
         "m_ok": (0.1, 0.9), "w_ok": (2, 25), "tc_ok": 0.2, "osc": 2.5, "damp": 1.0, "err": 0.2, "map": (50, 100)}


def test_lppls_grid_finds_synthetic_bubble():
    pytest.importorskip("numpy")
    g = B.LPPLSGrid(SMALL)
    n = g.N
    px = _lppls_series(n, n - 1 + 10, 0.5, 8.0)                               # tc＝最後一天之後 10 天
    pos, neg = g.fit([math.log(p) for p in px])
    assert pos > 0.5 and neg == 0.0
    down = [px[0] * px[0] / p for p in px]                                     # 鏡像＝加速下跌
    pos2, neg2 = g.fit([math.log(p) for p in down])
    assert neg2 > 0.5 and pos2 == 0.0
    assert g.fit([0.0] * (n - 1)) is None
    assert B.lppls_heat(30.0, 0.0) == pytest.approx(80.0) and B.lppls_heat(0.0, 80.0) == 0.0


def test_lppls_series_equals_point_helper_and_update_drops_midweek(monkeypatch):
    pytest.importorskip("numpy")
    from datetime import date, timedelta
    g = B.LPPLSGrid(SMALL)
    d0 = date(2020, 1, 6)
    days = []
    d = d0
    while len(days) < g.N + 30:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    vals = _lppls_series(len(days), len(days) + 15, 0.5, 8.0)
    px = dict(zip(days, vals))
    full = B.lppls_series(px, grid=g)
    ds, lnp, want = B.lppls_points(px)
    pos = {x: i for i, x in enumerate(ds)}
    assert full == {x: B.lppls_at(g, lnp, pos[x]) for x in want if pos[x] + 1 >= g.N}
    store = {}
    monkeypatch.setattr(B.HD, "load", lambda name: dict(store.get(name, {})))
    monkeypatch.setattr(B.HD, "save", lambda name, src, dct: store.__setitem__(name, dict(dct)) or True)

    class Fake:                                                                 # 每日更新用小網格
        def __new__(cls, spec=None):
            return g

        @staticmethod
        def n_needed(spec=None):
            return g.N
    monkeypatch.setattr(B, "LPPLSGrid", Fake)
    cut = [x for x in days if date.fromisoformat(x).weekday() == 2][-2]              # 某個週三：那週還沒結束
    part = {x: v for x, v in px.items() if x <= cut}
    store["t"] = B.lppls_series(part, grid=g)
    assert cut in store["t"]
    assert B.lppls_update("t", px) > 0
    assert cut not in store["t"] and store["t"] == full                          # 週中那筆拿掉，和整段一次算的一樣
    assert B.lppls_update("t", px) == 0


def test_max_drawdown_and_episodes():
    px = [100.0, 120.0, 90.0, 130.0, 104.0]
    assert B.max_drawdown(px, 0, 4) == pytest.approx(0.25)
    assert B.max_drawdown(px, 3, 4) == pytest.approx(0.2)
    assert B.max_drawdown(px, 0, 5) is None and B.max_drawdown([None, 5.0, None], 0, 2) is None
    months = [0, 1, 2, 3, 10, 11, 20]
    flags = [True, True, False, True, True, False, True]
    gap = S.BUB_EPI_GAP
    assert gap == 6
    assert B.episodes(months, flags) == [(0, 3), (4, 4), (6, 6)]                # 3→10 隔 6 個月＝新的一段


def test_crash_test_verdicts():
    rnd = random.Random(11)
    n = 360
    dates = [f"{1990 + j // 12}-{j % 12 + 1:02d}-28" for j in range(n)]
    hot = [(j // 30) % 3 == 0 for j in range(n)]                                # 每 90 個月熱 30 個月（4 段）
    x = [90.0 if h else 40.0 for h in hot]
    dd = {h: [(0.5 if hot[j] else 0.05) if rnd.random() < 0.95 else 0.0 for j in range(n)] for h, _ in S.BUB_DD}
    r = B.crash_test(dates, x, dd)
    a = r["252"]
    assert a["n_hot"] == sum(hot) and a["verdict"] == "crash" and a["diff"] > 0 and a["lo"] > 0
    assert len(r["epi"]) == 4 and r["epi"][0]["a"] == dates[0] and r["epi"][0]["n"] == 30
    calm = {h: [(0.0 if hot[j] else 0.5) for j in range(n)] for h, _ in S.BUB_DD}
    assert B.crash_test(dates, x, calm)["504"]["verdict"] == "calm"
    few = [90.0 if j < 5 else 40.0 for j in range(n)]
    assert B.crash_test(dates, few, dd)["252"]["verdict"] == "few"


def test_bubble_ext_uses_monthly_path():
    A = {f"{1980 + j // 12}-{j % 12 + 1:02d}": 100.0 + j for j in range(120)}
    A["1985-01"] = 50.0                                                          # 中間一次大跌
    pre = {"X1": {f"{1980 + j // 12}-{j % 12 + 1:02d}": (90.0 if j < 36 else 40.0) for j in range(120)}}
    out = B.bubble_ext(pre, A)
    assert set(out) == {"X1"}
    assert out["X1"]["252"]["n"] == 120 - 1 - 12                                  # 之後第 1 個月起 12 個月都要有
