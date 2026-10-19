"""大跌風險研究（arm/lab/crash.py）：結果變數、扣掉波動的差、重抽、回歸、樣本外、主要假說的算法，用逐筆直接算的版本比對。"""
from __future__ import annotations

import math
import random

import pytest

np = pytest.importorskip("numpy")

from arm.lab import crash as K  # noqa: E402
from arm.lab import crashspec as S  # noqa: E402


def _px(n=900, seed=3, sd=0.015):
    rnd = random.Random(seed)
    p, out = 100.0, []
    for _ in range(n):
        p *= math.exp(rnd.gauss(0.0003, sd * (2.0 if rnd.random() < 0.05 else 1.0)))
        out.append(p)
    return np.array(out)


def test_outcomes_match_direct_definitions():
    px = _px()
    th = (0.03, 0.06, 0.09)
    sig = K.sigma(px)
    A = K.outcomes(px, th, sig)
    n = len(px)
    sr = [px[i] / px[i - 1] - 1.0 for i in range(1, n)]          # sr[i－1]＝第 i 天
    lr = [math.log(px[i] / px[i - 1]) for i in range(1, n)]

    def sd(xs):
        m = sum(xs) / len(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

    for t in (0, 5, 61, 300, n - 61, n - 60, n - 21, n - 20, n - 1):
        a1 = any(sr[t + k - 1] <= -th[0] for k in range(1, 21)) if t + 20 <= n - 1 else None
        a2 = (min(px[t + 1:t + 21]) / px[t] - 1 <= -th[1]) if t + 20 <= n - 1 else None
        a3 = (min(px[t + 1:t + 61]) / px[t] - 1 <= -th[2]) if t + 60 <= n - 1 else None
        a4 = (sd(lr[t:t + 20]) >= 1.5 * sd(lr[t - 60:t])) if 60 <= t and t + 20 <= n - 1 else None
        a5 = (-sum(sorted(sr[t:t + 60])[:3]) / 3 / sig) if t + 60 <= n - 1 else None
        for k, v in (("A1", a1), ("A2", a2), ("A3", a3), ("A4", a4)):
            if v is None:
                assert math.isnan(A[k][t]), (k, t)
            else:
                assert A[k][t] == float(v), (k, t)
        if a5 is None:
            assert math.isnan(A["A5"][t])
        else:
            assert abs(A["A5"][t] - a5) < 1e-12
    v = K.vol20(px)
    d = K.dev60(px)
    for t in (19, 20, 100, n - 1):
        if t < 20:
            assert math.isnan(v[t])
        else:
            assert abs(v[t] - sd(lr[t - 20:t])) < 1e-12
    assert math.isnan(d[58]) and abs(d[59] - (px[59] / (sum(px[:60]) / 60) - 1)) < 1e-12


def test_strat_diff_is_hot_weighted_within_vol_groups():
    rnd = random.Random(1)
    n = 600
    y = np.array([float(rnd.random() < 0.3) for _ in range(n)])
    hot = np.array([rnd.random() < 0.3 for _ in range(n)])
    g = np.array([rnd.randrange(3) for _ in range(n)])
    tot, w = 0.0, 0.0
    for s in range(3):
        h = [y[i] for i in range(n) if hot[i] and g[i] == s]
        c = [y[i] for i in range(n) if not hot[i] and g[i] == s]
        if len(h) >= S.MIN_STRAT and len(c) >= S.MIN_STRAT:
            tot += len(h) * (sum(h) / len(h) - sum(c) / len(c))
            w += len(h)
    assert abs(K.strat_diff(y, hot, g) - tot / w) < 1e-12
    # 只有一組熱的天數夠：只算那一組
    hot2 = (g == 1) & (np.arange(n) % 3 == 0)
    h = [y[i] for i in range(n) if hot2[i]]
    c = [y[i] for i in range(n) if not hot2[i] and g[i] == 1]
    assert abs(K.strat_diff(y, hot2, g) - (sum(h) / len(h) - sum(c) / len(c))) < 1e-12


def test_bootstrap_equals_explicit_block_resampling():
    rnd = random.Random(2)
    n, L = 500, 60
    y = np.array([float(rnd.random() < 0.25) for _ in range(n)])
    hot = np.array([rnd.random() < 0.35 for _ in range(n)])
    g = np.array([rnd.randrange(3) for _ in range(n)])
    reps = K.boot(K._cols(y, hot, g, 3), n_boot=40, L=L, seed=7)
    rng = np.random.default_rng(7)
    k = math.ceil(n / L)
    st = rng.integers(0, n - L + 1, size=(40, k))       # 和 boot 一次抽 250 次的順序一樣（40 < 250）
    for b in range(40):
        idx = [s + j for s in st[b] for j in range(L)]
        d = K.strat_diff(y[idx], hot[idx], g[idx])
        assert (d is None and math.isnan(reps[b])) or abs(d - reps[b]) < 1e-12
    assert K.boot(K._cols(y[:100], hot[:100], g[:100], 3), L=L) is None      # 不到兩個區塊
    lo, hi, p, p1 = K.ci_p(reps)
    assert lo <= hi and 1 / S.BOOT_N <= p <= 1 and 1 / S.BOOT_N <= p1 <= 1


def test_episodes_zones_and_verdict():
    assert K.episodes(np.array([3, 5, 20, 41, 100])) == 3          # 5→20 相隔 15、20→41 相隔 21（新的一段）、41→100
    assert K.episodes(np.array([], dtype=int)) == 0
    assert list(K.zone_of(np.array([100.0, 80.0, 79.9, 60.0, 45.0, 20.0, 19.99, 0.0]))) == [0, 0, 1, 1, 2, 3, 4, 4]
    r = {"lo": 0.01, "hi": 0.05, "h1": 0.02, "h2": 0.03}
    assert K.verdict(r, 0.05) == "up" and K.verdict(r, 0.2) == "none"
    assert K.verdict({**r, "h2": -0.01}, 0.01) == "none"
    assert K.verdict({"lo": -0.05, "hi": -0.01, "h1": -0.02, "h2": -0.03}, 0.01) == "down"
    assert K.verdict({"v": "few"}, 0.01) == "few"


def test_monthly_values_apply_to_next_month_and_only_complete_months():
    cal = ["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02", "2020-03-03"]
    assert K.complete_months(cal) == {"2020-01", "2020-02"}
    d = K.monthly_to_daily(cal, {"2020-01": 10.0, "2020-02": 20.0, "2020-03": 30.0})
    assert [None if math.isnan(v) else v for v in d] == [None, None, 10.0, 10.0, 20.0, 20.0]
    rows = [{"d": "2020-01-31", "L": 2, "P1": True}, {"d": "2020-02-28", "L": 1, "P1": False},
            {"d": "2020-03-03", "L": 3, "P1": True}]                      # 3 月還沒過完：不用
    b = K.rows_to_daily(cal + ["2020-04-01"], rows, lambda r: 100.0 if r["L"] >= 2 else 0.0,
                        K.complete_months(cal))
    assert [None if math.isnan(v) else v for v in b] == [None, None, 100.0, 100.0, 0.0, 0.0, None]


def test_cap_interpolation_uses_latest_cbc_month():
    me_px = {"2026-07": 100.0, "2026-08": 110.0, "2026-09": 121.0}
    twcap = {"2026-07": [1, 1, 1000.0], "2026-08": [1, 1, 1100.0]}
    m = K._cap_month(twcap, me_px)
    assert m["2026-08"] == 1100e6 and abs(m["2026-09"] - 1100e6 * 121 / 110) < 1e-3
    cal = ["2026-08-31", "2026-09-01", "2026-09-30", "2026-10-01"]
    px = np.array([110.0, 115.5, 121.0, 132.0])
    d = K._cap_daily(cal, px, twcap, {"2026-07": 100.0, "2026-08": 110.0, "2026-09": 121.0})
    assert abs(d[0] - 1000e6 * 110 / 100) < 1e-3                       # 8 月的日子用 7 月底
    assert abs(d[1] - 1100e6 * 115.5 / 110) < 1e-3 and abs(d[3] - 1100e6 * 132 / 110) < 1e-3   # 央行沒有 9 月：用 8 月


def _logit_data(n=1500, seed=5):
    rnd = random.Random(seed)
    X, y, e = [], [], 0.0
    for _ in range(n):
        h = 1.0 if rnd.random() < 0.3 else 0.0
        lv = rnd.gauss(-4.3, 0.4)
        dv = rnd.gauss(0.0, 0.05)
        e = 0.6 * e + rnd.gauss(0, 1)
        z = -1.0 + 0.5 * h + 0.8 * (lv + 4.3) - 2.0 * dv + 0.3 * e
        X.append([1.0, h, lv, dv])
        y.append(1.0 if rnd.random() < 1 / (1 + math.exp(-z)) else 0.0)
    return np.array(X), np.array(y)


def test_logit_and_ols_hac_match_statsmodels():
    sm = pytest.importorskip("statsmodels.api")
    X, y = _logit_data()
    b, se = K.logit_hac(y, X, 20)
    r = sm.Logit(y, X).fit(disp=0, cov_type="HAC", cov_kwds={"maxlags": 20, "use_correction": False})
    assert np.max(np.abs(b - r.params)) < 1e-6
    assert np.max(np.abs(se / r.bse - 1)) < 1e-6
    r9 = random.Random(9)
    yc = X @ np.array([0.1, 0.3, 0.2, -1.0]) + np.array([r9.gauss(0, 1) for _ in range(len(y))])
    b2, se2 = K.ols_hac(yc, X, 20)
    r2 = sm.OLS(yc, X).fit(cov_type="HAC", cov_kwds={"maxlags": 20, "use_correction": False})
    assert np.max(np.abs(b2 - r2.params)) < 1e-10 and np.max(np.abs(se2 / r2.bse - 1)) < 1e-8
    r4 = random.Random(4)
    d = np.array([r4.gauss(0.1, 1) for _ in range(300)])
    rm = sm.OLS(d, np.ones((300, 1))).fit(cov_type="HAC", cov_kwds={"maxlags": 10, "use_correction": False})
    assert abs(K.nw_t(d, 10) - rm.params[0] / rm.bse[0]) < 1e-9


def test_oos_trains_only_on_days_whose_outcome_is_known():
    """t＋h < 那個月第一天才進訓練：把「會偷看」的日子的結果改掉，預測不變。"""
    n = 5200
    cal = []
    from datetime import date, timedelta
    d0 = date(1995, 1, 2)
    while len(cal) < n:
        if d0.weekday() < 5:
            cal.append(d0.isoformat())
        d0 += timedelta(days=1)
    rnd = random.Random(8)
    pos = np.arange(n)
    hot = np.array([rnd.random() < 0.3 for _ in range(n)])
    lv = np.array([rnd.gauss(-4.3, 0.4) for _ in range(n)])
    dv = np.array([rnd.gauss(0, 0.05) for _ in range(n)])
    y = np.array([1.0 if rnd.random() < 0.2 + 0.1 * h else 0.0 for h in hot])
    h = 20
    r1 = K.oos(pos, y, hot, lv, dv, cal, h)
    assert r1["n"] > 0
    # 2010 年以後第一個用來預測的月份：把那個月第一天前 h 天內（結果還不知道）的 y 全部翻轉，第一個月的預測不能變
    m0 = next(i for i, d in enumerate(cal) if d >= S.OOS_START and cal[i - 1][:7] != d[:7])
    y2 = y.copy()
    y2[m0 - h:m0] = 1 - y2[m0 - h:m0]
    y2[m0:] = y[m0:]
    r2 = K.oos(pos[: m0 + 15], y2[: m0 + 15], hot[: m0 + 15], lv[: m0 + 15], dv[: m0 + 15], cal, h)
    r3 = K.oos(pos[: m0 + 15], y[: m0 + 15], hot[: m0 + 15], lv[: m0 + 15], dv[: m0 + 15], cal, h)
    assert r2["n"] == r3["n"] > 0 and abs(r2["bV"] - r3["bV"]) < 1e-12 and abs(r2["bX"] - r3["bX"]) < 1e-12


def test_pooled_strata_are_market_by_vol_group():
    rnd = random.Random(6)
    parts = []
    for m in range(2):
        cal = [f"20{10 + m}-{k // 28 + 1:02d}-{k % 28 + 1:02d}" for k in range(300)]
        x = np.array([rnd.choice([90.0, 10.0, 50.0]) for _ in range(300)])
        y = np.array([rnd.random() for _ in range(300)])
        v = np.array([rnd.random() for _ in range(300)])
        parts.append((f"m{m}", cal, x, y, v))
    r = K.pooled(parts)
    tot = w = 0.0
    for (_, cal, x, y, v) in parts:
        g = K.groups(v, K.terciles(v))
        hot = x >= S.HOT
        for s in range(3):
            h = y[hot & (g == s)]
            c = y[~hot & (g == s)]
            if len(h) >= S.MIN_STRAT and len(c) >= S.MIN_STRAT:
                tot += len(h) * (h.mean() - c.mean())
                w += len(h)
    assert abs(r["d"] - tot / w) < 1e-12 and r["n"] == 600 and r["days"] == 600


def test_analyze_marks_small_samples_and_keeps_strata():
    px = _px(n=1400)
    A = K.outcomes(px, (0.03, 0.06, 0.09))
    vol, dv = K.vol20(px), K.dev60(px)
    cal = [f"d{i:05d}" for i in range(len(px))]
    x = np.full(len(px), 30.0)
    x[:50] = 90.0                                                  # 熱的只有 50 天：樣本不足
    r = K.analyze(cal, x, A["A2"], vol, dv, 20, True, with_oos=False)
    assert r["v"] == "few" and r["nh"] == len([i for i in range(50) if not math.isnan(vol[i])])
    x2 = np.where(np.arange(len(px)) % 50 < 15, 90.0, 30.0)       # 很多段、每段 15 天
    r2 = K.analyze(cal, x2, A["A2"], vol, dv, 20, True, with_oos=False)
    assert "v" not in r2 and r2["ep"] >= S.MIN_EPISODES and len(r2["strata"]) == 3 and len(r2["zones"]) == 5
    assert r2["lo"] is not None and r2["rob"]["z"] is not None


def test_vol_state_matches_direct_computation():
    """每天建頁的「先看波動」：今天的 20 日波動在全部日子裡的百分位、三分位組別、同一組波動的日子之後的比例（逐筆直接算）。"""
    px = _px(n=700, seed=11)
    cal = [f"d{i:04d}" for i in range(len(px))]
    out = K.vol_state("tw", {"cal": cal, "px": px})
    lr = [math.log(px[i] / px[i - 1]) for i in range(1, len(px))]

    def sd(xs):
        m = sum(xs) / len(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
    vol = [None] * 20 + [sd(lr[i - 20:i]) for i in range(20, len(px))]   # 第 t 天＝t−19～t 這 20 個日報酬
    have = [v for v in vol if v is not None]
    vt = vol[-1]
    assert out["vol"] == pytest.approx(vt) and out["a"] == cal[20]
    assert out["pct"] == pytest.approx(sum(v < vt for v in have) / len(have))
    c0, c1 = np.quantile(np.array(have), [1 / 3, 2 / 3])
    g = int(vt >= c0) + int(vt >= c1)
    assert out["g"] == g
    A = K.outcomes(px, S.TH["tw"])
    for o in S.OUTCOMES:
        ys = [(A[o][i], int(vol[i] >= c0) + int(vol[i] >= c1)) for i in range(len(px))
              if vol[i] is not None and not math.isnan(A[o][i])]
        same = [y for y, gg in ys if gg == g]
        r = out["rows"][o]
        assert r["ng"] == len(same) and r["n"] == len(ys)
        assert r["g"] == pytest.approx(sum(same) / len(same)) and r["all"] == pytest.approx(sum(y for y, _ in ys) / len(ys))
    assert K.vol_state("tw", {"cal": cal[:10], "px": px[:10]})["g"] is None   # 波動還算不出來
