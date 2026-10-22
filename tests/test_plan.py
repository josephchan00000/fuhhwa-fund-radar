"""交易計畫（arm/lab/plan.py；planspec VER 1）：和逐筆直接算的版本比對。"""
import math
from datetime import date, timedelta

import numpy as np

from arm.lab import plan as PN
from arm.lab import planspec as S
from arm.lab import practlive as PL
from arm.lab import practsim as P
from arm.lab import tilt as TL
from arm.lab import tiltspec as TS


def _cal(start: str, n: int) -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_weeks_rounds_half_up():
    assert [PN.weeks(n) for n in S.CHECKS] == [13, 25, 50, 101, 151]
    assert PN.weeks(2) == 1 and PN.weeks(7.5) == 2 and PN.weeks(12.5) == 3


def test_same_market_matches_direct_neighbours():
    rng = np.random.default_rng(3)
    W = 400
    bh = np.cumprod(1 + rng.normal(0.001, 0.02, W))
    nav = np.cumprod(1 + rng.normal(0.0005, 0.01, W))
    n, x, y = 63, 0.05, 0.02
    res = PN.same_market(x, y, bh, nav, n)
    w = 13
    pairs = [(math.log(bh[i + w] / bh[i]), math.log(nav[i + w] / nav[i]), i) for i in range(W - w)]
    k = max(S.NB_MIN, math.ceil(S.NB_Q * len(pairs)))
    nb = sorted(pairs, key=lambda t: (abs(t[0] - x), t[2]))[:k]
    p = (sum(1 for t in nb if t[1] < y) + 0.5 * sum(1 for t in nb if t[1] == y)) / k
    assert res["w"] == w and res["N"] == len(pairs) and res["k"] == k
    assert math.isclose(res["p"], round(p, 4))
    assert res["st"] == ("bad" if p < S.P_LOW else "good" if p > S.P_HIGH else "ok")
    assert PN.same_market(x, y, bh[:30], nav[:30], n)["st"] is None          # 窗口不到 NB_MIN 個＝不比


def test_same_market_flags_extremes():
    rng = np.random.default_rng(4)
    bh = np.cumprod(1 + rng.normal(0.001, 0.02, 500))
    nav = bh ** 0.5
    assert PN.same_market(0.0, -0.5, bh, nav, 63)["st"] == "bad"
    assert PN.same_market(0.0, 0.5, bh, nav, 63)["st"] == "good"


def test_year_range_matches_direct():
    rng = np.random.default_rng(5)
    bh = np.cumprod(1 + rng.normal(0.002, 0.02, 300))
    nav = np.cumprod(1 + rng.normal(0.001, 0.01, 300))
    R = PN.year_range(bh, nav)
    ry = [nav[i + 52] / nav[i] - 1 for i in range(300 - 52)]
    assert R["n"] == len(ry)
    assert all(math.isclose(a, round(b, 4)) for a, b in zip(R["q"], np.quantile(ry, S.RANGE_Q)))
    assert math.isclose(R["loss"], round(np.mean(np.array(ry) < 0), 4))


def test_fut_episodes_match_direct_loop():
    rng = np.random.default_rng(6)
    n = 120
    cal = _cal("2020-01-01", n)
    px = 100 * np.cumprod(1 + rng.normal(0.0, 0.015, n))
    r = P.daily_ret(px)
    a = np.where((np.arange(n) // 9) % 2 == 0, TS.ADD, 0.0)
    g = rng.normal(0.0, 0.015, n)
    s0, b = 4, n
    dr = r[s0 + 1:b] + a[s0:b - 1] * g[s0 + 1:b] - 0.00002
    E = PN.fut_episodes(cal, r, dr, a, s0, b)
    nv = {s0: 1.0}
    for k in range(s0 + 1, b):
        nv[k] = nv[k - 1] * (1 + dr[k - s0 - 1])
    eps, k = [], s0
    while k < b:
        if a[k] > 0:
            s = k
            while k < b and a[k] > 0:
                k += 1
            base = s - 1 if s > s0 else s0
            cum, lo = 0.0, 0.0
            for j in range(max(s, s0 + 1), min(k, b - 1) + 1):
                cum += nv[j - 1] * (dr[j - s0 - 1] - r[j]) / nv[base]
                lo = min(lo, cum)
            eps.append((cal[s], cal[k] if k < b else None, lo, cum))
        else:
            k += 1
    assert E["n"] == len(eps)
    for got, want in zip(E["list"], eps):
        assert got[0] == want[0] and got[1] == want[1]
        assert math.isclose(got[2], round(want[2], 6), abs_tol=1e-9) and math.isclose(got[4], round(want[3], 6), abs_tol=1e-9)
    assert math.isclose(E["worst"], min(e[2] for e in eps), abs_tol=1e-6)


def test_forward_checkpoints_and_flags():
    rng = np.random.default_rng(7)
    W = 600
    wk = (None, np.cumprod(1 + rng.normal(0.002, 0.02, W)), np.cumprod(1 + rng.normal(0.001, 0.01, W)))
    n = 130
    cal = _cal("2027-01-01", n + 1)
    nav = np.concatenate([[1.0], np.cumprod(1 + rng.normal(0.0005, 0.01, n))])
    bh = np.concatenate([[1.0], np.cumprod(1 + rng.normal(0.001, 0.015, n))])
    lv = {"a": 0, "cal": cal, "nav": nav, "bh": bh, "gap": 0, "fut": {"worst": -0.03}}
    F = PN.forward("spx", "atk", lv, wk, mdd_hist=0.9, fut_hist=-0.02)
    assert [c["n"] for c in F["chk"]] == [63, 126] and F["chk"][1]["d"] == cal[126]
    assert F["next"]["n"] == 252 and F["flags"] == ["fut"] and F["st"] == "fut"
    ref = PN.same_market(math.log(bh[63]), math.log(nav[63]), wk[1], wk[2], 63)
    assert F["chk"][0]["p"] == ref["p"]
    F2 = PN.forward("spx", "def", lv, wk, mdd_hist=0.0, fut_hist=None)
    assert F2["flags"] == ["dd"]
    F3 = PN.forward("spx", "def", dict(lv, nav=nav[:10], bh=bh[:10]), wk, mdd_hist=0.9, fut_hist=None)
    assert F3["chk"] == [] and F3["st"] == "wait" and F3["next"]["n"] == 63


def test_live_def_matches_practlive_forward():
    n = 80
    cal = _cal("2026-09-01", n)
    rng = np.random.default_rng(8)
    px = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    log = {cal[40]: {"M2": 0.5}, cal[45]: {"M2": 0.25}, cal[60]: {"M2": 0.75}}
    D = {"mk": "spx", "cal": cal, "px": px}
    lv = PN.live_def("spx", D, {"mk": {"spx": log}})
    fw = PL.forward(log, D)["M2"]
    assert cal[lv["a"]] == fw["a"] and math.isclose(lv["nav"][-1] - 1, fw["ret"], rel_tol=1e-12)
    assert math.isclose(lv["bh"][-1] - 1, fw["bh"], rel_tol=1e-12)


def test_now_atk_flip_level_is_tomorrows_ma_crossing():
    n = 260
    cal = _cal("2025-06-02", n)
    px = np.concatenate([np.linspace(100, 130, 230), np.linspace(130, 125, 30)])
    st = PN.now_atk("tw", {"cal": cal, "px": px})
    flip = st["flip"]
    for c, up in ((flip * 1.0001, True), (flip * 0.9999, False)):
        nxt = np.append(px, c)
        assert bool(c > np.mean(nxt[-TS.MA_N:])) == up
    lots = {x[0]: x for x in st["lots"]}
    per = px[-1] * 10
    assert lots["微台"][2] == round(per) and lots["微台"][4] == math.floor(S.CAPITAL["tw"] * TS.ADD / per + 0.5)


def test_research_fut_reproduces_tilt_research_nav():
    """研究期間重算的淨值＝tilt 研究檔的 100 萬變多少（同一套函式、同一段期間）。"""
    from arm.lab import xstrat as XT
    TR = TL.load()
    if not TR:
        return
    mk = "ndx"
    out = PN.research_fut(mk, XT.data(mk), TR, TL.load_carry())
    assert math.isclose(out["man"], TR["mk"][mk]["rules"]["K4"]["man"] / 1e6, rel_tol=1e-6)
    assert out["n"] == len(TR["mk"][mk]["rules"]["K4"]["ep"]["list"])
