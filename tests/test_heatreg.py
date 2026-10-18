"""景氣溫度頁第六版：邊際變化多層回歸的計算模組（arm/lab/heatreg.py；規劃文件第 15.11 節）。"""
import json
import math
import random
from datetime import date, timedelta

import pytest

from arm.lab import heat as H
from arm.lab import heatcalc as C
from arm.lab import heatpos as P
from arm.lab import heatreg as G
from arm.lab import heatrel as RL
from arm.lab import heatspec as S


# ── 合成資料 ─────────────────────────────────────────────────────────

def _weekdays(a: str, z: str) -> list[str]:
    d, end, out = date.fromisoformat(a), date.fromisoformat(z), []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def fake_B(start="1997-07-01", end="2013-12-31", seed=7, m_from="1985-01", px=None) -> dict:
    """主樣本 1997-07 起的交易日（週一到週五）；月資料 1985 起、日資料 1990 起（百分位需要的歷史）。"""
    rnd = random.Random(seed)
    cal = _weekdays(start, end)
    if px is None:
        p, px = 1000.0, []
        for _ in cal:
            p *= math.exp(rnd.gauss(0.0003, 0.012))
            px.append(p)
    months = [m_from]
    while months[-1] < end[:7]:
        months.append(C.ym_add(months[-1], 1))
    mraw, nat = {}, {}
    days = _weekdays("1990-01-01", end)
    for k in G.ITEMS:
        if S.FREQ_OF[k] == "m":
            x, ser = 0.0, {}
            for ym in months:
                x = 0.9 * x + rnd.gauss(0, 1)
                ser[ym] = (50 + 3 * x) if k == "B3" else (20 + x if k == "B1" else x)
            mraw[k] = ser
        else:
            x, ser = 100.0, {}
            for d in days:
                x = max(1.0, x + rnd.gauss(0, 1))
                ser[d] = x if k == "C1" else x - 100.0
            nat[k] = ser
    hc = {}
    for k in G.ITEMS:
        h, col = 50.0, []
        for _ in cal:
            h = min(100.0, max(0.0, h + rnd.gauss(0, 2)))
            col.append(h)
        hc[k] = col
    return {"cal": cal, "px": px, "mraw": mraw, "nat": nat, "hc": hc, "raw": {"G1": [rnd.gauss(0, 1) for _ in cal]}}


# ── 線性代數、OLS、Newey–West ─────────────────────────────────────────

def test_solve_matches_known_and_detects_singular():
    A = [[4.0, 1.0, 2.0], [1.0, 3.0, 0.0], [2.0, 0.0, 5.0]]
    x = [1.0, -2.0, 0.5]
    b = [sum(a * xi for a, xi in zip(row, x)) for row in A]
    got = G.solve(A, b)
    assert all(abs(u - v) < 1e-12 for u, v in zip(got, x))
    assert G.solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0]) is None          # 奇異
    assert G.solve([[0.0, 0.0], [0.0, 0.0]], [0.0, 0.0]) is None


def _rand_reg(n=150, seed=3, rho=0.6):
    rnd = random.Random(seed)
    X, y, e = [], [], 0.0
    for _ in range(n):
        x1, x2 = rnd.gauss(0, 1), rnd.gauss(0, 1)
        e = rho * e + rnd.gauss(0, 1)
        X.append([1.0, x1, x2])
        y.append(0.2 + 0.5 * x1 - 0.3 * x2 + e)
    return X, y


def test_ols_and_newey_west_match_statsmodels():
    np = pytest.importorskip("numpy")
    sm = pytest.importorskip("statsmodels.api")
    X, y = _rand_reg()
    f = G.ols(X, y)
    r = sm.OLS(np.array(y), np.array(X)).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    assert max(abs(a - b) for a, b in zip(f["beta"], r.params)) < 1e-10
    V = r.cov_params()
    ti = list(range(len(y)))
    for a in range(3):
        w = [1.0 if i == a else 0.0 for i in range(3)]
        assert abs(G.nw_var(w, X, f, ti, 6) - V[a, a]) < 1e-10 * max(1.0, V[a, a])
    w = [0.0, 1.0, 1.0]                                                    # 線性組合：b1 + b2
    assert abs(G.nw_var(w, X, f, ti, 6) - (V[1, 1] + V[2, 2] + 2 * V[1, 2])) < 1e-10
    # 平均的 Newey–West t ＝ 對常數項做 OLS 的 HAC t
    fs = [yi * 0.1 + 0.05 for yi in y]
    rm = sm.OLS(np.array(fs), np.ones((len(fs), 1))).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    assert abs(G.nw_mean_t(fs, ti, 6) - rm.params[0] / rm.bse[0]) < 1e-9


def test_newey_west_pairs_by_month_distance():
    """中間缺月：落後依實際相隔月數，不是依列數。"""
    X, y = _rand_reg(n=40)
    f = G.ols(X, y)
    ti = list(range(20)) + [t + 30 for t in range(20)]                   # 第 20 列和第 19 列相隔 11 個月
    w = [0.0, 1.0, 0.0]
    inv, e = f["inv"], f["e"]
    h = [sum(w[a] * inv[a][c] for a in range(3)) for c in range(3)]
    g = [sum(hc * xc for hc, xc in zip(h, row)) * ei for row, ei in zip(X, e)]
    s = sum(v * v for v in g)
    for a in range(len(g)):
        for b in range(a):
            d = ti[a] - ti[b]
            if 0 < d <= 6:
                s += 2 * (1 - d / 7) * g[a] * g[b]
    assert abs(G.nw_var(w, X, f, ti, 6) - s) < 1e-14


def test_block_bootstrap_prefix_sums_equal_direct_resampling():
    X, y = _rand_reg(n=120, seed=5)
    L, nb = 12, 60
    combos = [[0.0, 1.0, 0.0], [0.0, 1.0, 1.0]]
    got = G.boot_ols(X, y, L, combos, n_boot=nb, seed=11)
    rnd = random.Random(11)
    want = [[], []]
    for _ in range(nb):
        Xs, ys = [], []
        for s, ln in RL._draws(rnd, len(y), L):
            Xs += X[s:s + ln]
            ys += y[s:s + ln]
        b = G.ols(Xs, ys)["beta"]
        for o, w in zip(want, combos):
            o.append(sum(a * c for a, c in zip(w, b)))
    for a, b in zip(got, want):
        assert max(abs(u - v) for u, v in zip(a, b)) < 1e-9
    assert G.boot_p([1.0] * 10) == 0.0 and G.boot_p([-1.0, 1.0]) == 1.0


def test_reg_recovers_slope_and_needs_96_months():
    rnd = random.Random(2)
    T = 200
    x = [rnd.gauss(0, 1) for _ in range(T)]
    c1 = [rnd.gauss(0, 1) for _ in range(T)]
    y = [0.5 * a + 0.1 * b + rnd.gauss(0, 0.5) for a, b in zip(x, c1)]
    ym = [C.ym_add("1990-01", t) for t in range(T)]
    e = G.reg(ym, y, [x, c1], 3)
    assert e["n"] == T and e["a"] == "1990-01" and abs(e["b"] - 0.5) < 0.1
    assert e["lo"] < 0.5 < e["hi"] and e["p"] < 0.01 and e["t"] > 5
    assert e["h1"] > 0 and e["h2"] > 0
    few = G.reg(ym[:90], y[:90], [x[:90], c1[:90]], 3)
    assert few["n"] == 90 and few["b"] is None                            # 不到 96 個月
    keep = [t % 2 == 0 for t in range(T)]
    sub = G.reg(ym, y, [x, c1], 3, keep=keep, boot=False)
    assert sub["n"] == 100 and sub["lo"] is None


# ── 二階的三個版本 ───────────────────────────────────────────────────

def test_second_derivative_variants():
    d1 = {C.ym_add("2000-01", i): float(i * i) for i in range(12)}        # 一階 i²
    v0 = G.d2_monthly(d1, 3, "v0")
    v1 = G.d2_monthly(d1, 3, "v1")
    v2 = G.d2_monthly(d1, 3, "v2")
    i = 8
    ym = C.ym_add("2000-01", i)
    assert v0[ym] == i * i - (i - 3) ** 2                                 # 3 個月變化
    sm = lambda j: sum((j - a) ** 2 for a in range(3)) / 3                 # noqa: E731
    assert abs(v1[ym] - (sm(i) - sm(i - 3))) < 1e-12                       # 先取 3 個月平均再算 3 個月變化
    assert v2[ym] == i * i - (i - 6) ** 2                                  # 6 個月變化
    assert C.ym_add("2000-01", 2) not in v0 and C.ym_add("2000-01", 4) not in v1 and C.ym_add("2000-01", 5) not in v2
    lst = [float(i * i) for i in range(12)]
    assert G.d2_list(lst, 3, "v0")[i] == v0[ym] and abs(G.d2_list(lst, 3, "v1")[i] - v1[ym]) < 1e-12
    assert G.d2_list(lst, 3, "v2")[i] == v2[ym] and G.d2_list(lst, 3, "v2")[5] is None


def test_daily_first_derivative_same_as_heatpos():
    rnd = random.Random(4)
    N = {d: 100 + rnd.gauss(0, 5) for d in _weekdays("2001-01-01", "2002-06-30")}
    for k in ("C1", "C5", "G1"):
        spec = S.DERIV[k]
        ks, d1 = G.daily_d1(N, spec)
        want1, want2 = P._daily_d(N, spec)
        assert {d: v for d, v in zip(ks, d1) if v is not None} == want1
        d2 = G.d2_list(d1, spec["L2"], "v0")
        assert {d: v for d, v in zip(ks, d2) if v is not None} == want2


def test_item_panel_v0_matches_fifth_version():
    """v0 的二階、正負號、百分位和第五版（heatpos.deriv）完全相同。"""
    B = fake_B(end="2006-12-31")
    me = RL.month_ends(B["cal"])
    dates = [B["cal"][i] for i in me]
    for k in ("B2", "B1", "G2", "C1"):
        D = P.deriv(B, k)
        it = G.item_panel(B, k, me, dates)
        for t, i in enumerate(me):
            acc = D["acc"][i]
            raw = None if acc is None else (acc if S.HOT[k] > 0 else 100.0 - acc)
            got = it["X2"]["v0"][t]
            assert (got is None) == (raw is None), (k, t)
            if raw is not None:
                assert abs(got - (raw - 50) / 50) < 1e-12
            assert it["S2"]["v0"][t] == G._sign(D["d2"][i])
            assert it["D1"][t] == D["d1"][i]
        assert sum(1 for x in it["X2"]["v0"] if x is not None) > 20


# ── 每月樣本 ─────────────────────────────────────────────────────────

def test_panel_returns_controls_and_environment():
    cal = _weekdays("1997-07-01", "2001-12-31")
    px = [math.exp(0.001 * i) for i in range(len(cal))]
    B = fake_B(end="2001-12-31", px=px)
    B["raw"]["G1"] = [1.0 if i % 400 < 200 else -1.0 for i in range(len(cal))]
    Pn = G.panel(B)
    me, T = Pn["me"], Pn["T"]
    assert Pn["ym"][0] == "1997-07" and Pn["ym"][-1] == "2001-12" and T == 54
    for (k, m) in ((0, 3), (6, 6), (21, 3), (0, 24)):
        R = Pn["R"][(k, m)]
        for t in (0, 10, 25):
            if t + k + m < T - 1:
                assert abs(R[t] - 0.001 * (me[t + k + m] - me[t + k])) < 1e-12   # 月底的下一個交易日起算
        assert R[T - 1 - k - m] is None                                      # 終點是最後一個月底的下一天：還沒有
    assert Pn["r1"][0] is None and abs(Pn["r1"][5] - 0.001 * (me[5] - me[4])) < 1e-12
    assert Pn["r12"][11] is None and abs(Pn["r12"][12] - 0.001 * (me[12] - me[0])) < 1e-12
    assert Pn["BULL"][8] is None and all(b == 1.0 for b in Pn["BULL"][9:])  # 一路上漲：都在 10 個月均線之上
    assert Pn["HIKE"] == [1.0 if B["raw"]["G1"][i] > 0 else 0.0 for i in me]


def test_groups_and_diffusion():
    T = 3
    it = {k: {"X2": {"v0": [0.5, None, -0.2]}, "S2": {"v0": [1, None, -1]}, "XL": [0.1, 0.2, None]} for k in G.ITEMS}
    GA, LV, DI = G.groups_of(it, T, ("v0",))
    assert GA["v0"]["grow"] == [0.5, None, -0.2] and LV["rate"][2] is None
    assert DI["v0"] == [1.0, None, -1.0]                                   # 全部加速＝+1、全部不是＝−1
    it["B1"]["S2"]["v0"][0] = 0                                            # 0 不算加速
    assert G.groups_of(it, T, ("v0",))[2]["v0"][0] == 2.0 * 12 / 13 - 1.0
    sh = G.shares_of(it, T)
    assert sh["grow"][0] == 2.0 * 6 / 7 - 1.0 and sh["lev"] == [1.0, None, -1.0]   # 組內幾成在加速
    it["C1"]["S2"]["v0"][1] = 1                                            # 籌碼組只要 1 項有值
    assert G.shares_of(it, T)["lev"][1] == 1.0 and G.shares_of(it, T)["grow"][1] is None


# ── 狀態表與轉折事件 ─────────────────────────────────────────────────

def test_turn_events():
    s = [None, -1, -1, 1, 1, 1, 0, -1, -1, 0, 0, 1, 1, None, -1, -1]
    d1 = [1.0] * len(s)
    ev = G.turn_events(s, d1)
    assert [t for t, _ in ev] == [4, 8, 12]                              # 新方向第 2 個月；0 跳過；沒有值就斷開
    assert [kd for _, kd in ev] == [1, 2, 1]                              # 一階 > 0：翻正＝加速、翻負＝趨緩
    assert G.turn_events([1, None, -1, -1], [1.0] * 4) == []
    assert G.turn_events([1, -1, -1], [None, None, -2.0]) == [(2, 3)]     # 一階 < 0、翻負＝加劇


def test_state_table_runs_and_verdict():
    T = 120
    ym = [C.ym_add("2000-01", t) for t in range(T)]
    lab = ["hi_acc" if (t // 6) % 2 == 0 else "lo_dec" for t in range(T)]
    R = [0.05 if lab[t] == "hi_acc" else -0.05 for t in range(T)]
    Pn = {"T": T, "ym": ym, "R": {(0, 12): R}}
    tab = G.state_tab(Pn, lab, G.STATES, 12)
    a = tab["hi_acc"]
    assert a["n"] == 60 and a["runs"] == 10 and abs(a["diff"] - 0.05) < 1e-12
    assert a["verdict"] == "strong" and tab["lo_dec"]["verdict"] == "weak" and tab["hi_dec"]["n"] == 0


# ── 樣本外 ───────────────────────────────────────────────────────────

def _fake_panel(T=220, seed=9, k="B2"):
    rnd = random.Random(seed)
    ym = [C.ym_add("1990-01", t) for t in range(T)]
    x2 = {v: [None if t < 5 else rnd.uniform(-1, 1) for t in range(T)] for v in S.M6_VARIANTS}
    xl = [rnd.uniform(-1, 1) for _ in range(T)]
    r1 = [rnd.gauss(0, 0.05) for _ in range(T)]
    r12 = [rnd.gauss(0, 0.2) for _ in range(T)]
    R = {}
    for w in S.M6_OOS_WINDOWS:
        R[w] = [None if t + w[0] + w[1] >= T - 1 else 0.3 * x2["v1"][t] + rnd.gauss(0, 0.1) if x2["v1"][t] is not None
                else rnd.gauss(0, 0.1) for t in range(T)]
    return {"T": T, "ym": ym, "R": R, "r1": r1, "r12": r12, "it": {k: {"XL": xl, "X2": x2}}}


def test_oos_uses_only_finished_return_windows_and_matches_direct_fit(monkeypatch):
    monkeypatch.setattr(S, "M6_OOS_START", "2002-01")
    Pn = _fake_panel()
    for w in ((0, 3), (6, 6), (0, 24)):
        rec = G.oos_item_rec(Pn, "B2", w)
        assert rec and all(r["last"] + w[0] + w[1] < r["t"] for r in rec)   # 訓練＝報酬已經結束的月份
        assert all(r["ntr"] >= S.M6_MIN_N for r in rec)
        r = rec[len(rec) // 2]
        tau = r["t"]
        it, R = Pn["it"]["B2"], Pn["R"][w]
        rows = [t for t in range(tau - w[0] - w[1]) if R[t] is not None and it["X2"]["v0"][t] is not None]
        X1 = [[1.0, it["XL"][t], Pn["r1"][t], Pn["r12"][t]] for t in rows]
        y = [R[t] for t in rows]
        assert abs(r["m0"] - sum(y) / len(y)) < 1e-12
        b1 = G.ols(X1, y)["beta"]
        assert abs(r["m1"] - sum(a * c for a, c in zip(b1, [1.0, it["XL"][tau], Pn["r1"][tau], Pn["r12"][tau]]))) < 1e-9
        best = None
        for v in S.M6_VARIANTS:
            X2 = [row + [it["X2"][v][t]] for row, t in zip(X1, rows)]
            f = G.ols(X2, y)
            rss = sum(e * e for e in f["e"])
            if best is None or rss < best[0]:
                best = (rss, v, f["beta"])
        assert r["v_m2"] == best[1]
        xt = [1.0, it["XL"][tau], Pn["r1"][tau], Pn["r12"][tau], it["X2"][best[1]][tau]]
        assert abs(r["m2"] - sum(a * c for a, c in zip(best[2], xt))) < 1e-9
    m = G.oos_item(Pn, "B2", (0, 3))
    assert m["n"] >= S.M6_OOS_MIN_PRED and not m["few"] and m["models"]["m2"]["r2_1"] > 0
    assert m["cw"]["m2>m1"]["p"] < 0.05 and m["v_m2"].get("v1", 0) > m["n"] // 2   # 真正有用的版本會被選到


def _ridge_direct(xs, ys, ts, xnew, m, lams=S.M6_RIDGE_LAMBDA, folds=S.M6_CV_FOLDS):
    n, p = len(ys), len(xs[0])
    mu = [sum(r[a] for r in xs) / n for a in range(p)]
    sd = [math.sqrt(sum((r[a] - mu[a]) ** 2 for r in xs) / n) for a in range(p)]
    rho = [1 / s if s * s > 1e-12 else 0.0 for s in sd]
    Z = [[1.0] + [(r[a] - mu[a]) * rho[a] for a in range(p)] for r in xs]

    def fit(idx, lam):
        A = [[sum(Z[i][a] * Z[i][c] for i in idx) for c in range(p + 1)] for a in range(p + 1)]
        for j in range(1, p + 1):
            A[j][j] += lam * len(idx)
        return G.solve(A, [sum(Z[i][a] * ys[i] for i in idx) for a in range(p + 1)])
    cv, a = [0.0] * len(lams), 0
    for f in range(folds):
        b = a + n // folds + (1 if f < n % folds else 0)
        tr = [i for i in range(n) if not (ts[a] - m <= ts[i] <= ts[b - 1] + m)]
        for li, lam in enumerate(lams):
            th = fit(tr, lam)
            cv[li] += sum((ys[i] - sum(t * z for t, z in zip(th, Z[i]))) ** 2 for i in range(a, b))
        a = b
    li = min(range(len(lams)), key=lambda i: cv[i])
    th = fit(range(n), lams[li])
    z = [1.0] + [(x - u) * r for x, u, r in zip(xnew, mu, rho)]
    return sum(t * c for t, c in zip(th, z)), lams[li]


def test_ridge_prefix_sums_match_direct_computation():
    rnd = random.Random(8)
    rd = G.Ridge(4)
    xs, ys, ts = [], [], []
    for t in range(130):
        x = [rnd.gauss(0, 1), rnd.gauss(2, 3), float(rnd.random() < 0.3), 1.0]   # 最後一欄是常數（標準差 0，不用）
        y = 0.4 * x[0] - 0.1 * x[1] + rnd.gauss(0, 1)
        tt = t + (5 if t > 60 else 0)                                        # 中間缺 5 個月
        rd.add(x, y, tt)
        xs.append(x)
        ys.append(y)
        ts.append(tt)
    xnew = [0.5, 1.0, 1.0, 1.0]
    for m in (3, 12):
        got = rd.predict(xnew, m)
        want = _ridge_direct(xs, ys, ts, xnew, m)
        assert abs(got[0] - want[0]) < 1e-9 and got[1] == want[1]


def test_tree_finds_split_and_respects_min_leaf():
    rnd = random.Random(1)
    X, y = [], []
    for _ in range(200):
        a, b = rnd.random(), rnd.random()
        X.append([b, a, float(rnd.random() < 0.5)])
        y.append((1.0 if a > 0.5 else 0.0) + 0.5 * (b > 0.7) + rnd.gauss(0, 0.05))
    tr = G.tree_fit(X, y)
    assert tr[0] == "split" and tr[1] == 1                                 # 根節點分在第 2 個變數
    leaves = []

    def walk(nd):
        if nd[0] == "leaf":
            leaves.append(nd[2])
        else:
            walk(nd[3])
            walk(nd[4])
    walk(tr)
    assert all(n >= S.M6_TREE["min_leaf"] for n in leaves) and sum(leaves) == 200 and len(leaves) <= 4
    assert G.tree_predict(tr, [0.9, 0.9, 0.0]) > 1.2 and G.tree_predict(tr, [0.1, 0.1, 0.0]) < 0.3
    assert G.tree_fit([[1.0]] * 100, [1.0] * 100)[0] == "leaf"           # 不分比較好就不分
    # 根節點＝窮舉同一組分點的最佳
    best = None
    for j in range(3):
        vals = sorted(x[j] for x in X)
        for q in S.M6_TREE["cuts"]:
            c = vals[(q * 199) // 100]
            L = [yy for x, yy in zip(X, y) if x[j] <= c]
            Rr = [yy for x, yy in zip(X, y) if x[j] > c]
            if len(L) < 36 or len(Rr) < 36:
                continue
            sse = sum((v - sum(L) / len(L)) ** 2 for v in L) + sum((v - sum(Rr) / len(Rr)) ** 2 for v in Rr)
            if best is None or sse < best[0] - 1e-12:
                best = (sse, j, c)
    assert (tr[1], tr[2]) == best[1:]


def test_clark_west_and_metrics():
    y = [0.1, -0.2, 0.3, 0.05, -0.1]
    fs = [0.0] * 5
    fb = [0.05, -0.1, 0.1, 0.0, 0.0]
    f = [(a - s) ** 2 - ((a - b) ** 2 - (s - b) ** 2) for a, s, b in zip(y, fs, fb)]
    t, p = G.cw_test(y, fs, fb, list(range(5)), 6)
    assert abs(t - G.nw_mean_t(f, list(range(5)), 6)) < 1e-12 and abs(p - (1 - G._ncdf(t))) < 1e-12
    rec = [{"t": i, "y": a, "m0": 0.01, "m1": s, "m2": b} for i, (a, s, b) in enumerate(zip(y, fs, fb))]
    m = G.oos_metrics(rec, 3, [C.ym_add("2008-01", i) for i in range(5)], ("m0", "m1", "m2"), (("m1", "m2"),))
    sse = lambda col: sum((r["y"] - r[col]) ** 2 for r in rec)               # noqa: E731
    assert abs(m["models"]["m2"]["r2_0"] - (1 - sse("m2") / sse("m0"))) < 1e-12
    assert abs(m["models"]["m2"]["r2_1"] - (1 - sse("m2") / sse("m1"))) < 1e-12
    assert m["models"]["m2"]["hit"] == 4 / 5 and m["few"] and m["a"] == "2008-01"
    assert [g["n"] for g in m["models"]["m2"]["terc"]] == [2, 1, 2]


def test_holm():
    adj, rej = G.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.005, "e": None})
    assert rej == {"a": True, "b": False, "c": False, "d": True, "e": False}
    assert adj["d"] == 0.02 and adj["a"] == 0.03 and abs(adj["c"] - 0.06) < 1e-12 and abs(adj["b"] - 0.06) < 1e-12
    assert adj["e"] is None


def test_wald_states_detects_state_effect():
    rnd = random.Random(6)
    T = 240
    ym = [C.ym_add("1990-01", t) for t in range(T)]
    st = [(t // 12) % 4 for t in range(T)]
    dums = [[1.0 if s == j else 0.0 for s in st] for j in range(3)]
    ctrl = [[rnd.gauss(0, 1) for _ in range(T)]]
    y = [(0.2 if s == 0 else 0.0) + rnd.gauss(0, 0.1) for s in st]
    e = G.wald_states(ym, y, dums, ctrl, 12)
    assert e["n"] == T and e["p"] < 0.05 and e["nw_p"] < 0.05 and abs(e["b"][0] - 0.2) < 0.05
    y0 = [rnd.gauss(0, 0.1) for _ in st]
    assert G.wald_states(ym, y0, dums, ctrl, 12)["p"] > 0.05


def test_verdict_rules():
    base = {"n": 200, "b": 0.1, "h1": 0.05, "h2": 0.2, "q": 0.05}
    ok = {"few": False, "r2": 0.01, "p": 0.01}
    assert G.verdict(base, True, ok) == "pred"
    assert G.verdict(base, True, {**ok, "p": 0.2}) == "in_only"
    assert G.verdict(base, True, {**ok, "r2": -0.01}) == "in_only"
    assert G.verdict(base, True, None) == "in_untested"
    assert G.verdict(base, True, {**ok, "few": True}) == "in_untested"
    assert G.verdict(base, False, ok) == "none"                           # 相鄰延遲視窗沒有同號
    assert G.verdict({**base, "h2": -0.1}, True, ok) == "none"            # 前後兩半不同號
    assert G.verdict({**base, "q": 0.2}, True, ok) == "none"
    assert G.verdict({**base, "n": 50, "b": None}, True, ok) == "few"
    d = {G.wkey(w): {"b": b} for w, b in zip(G.DELAY, [0.1, -0.1, -0.2, 0.3, None, 0.1, 0.2, -0.1])}
    assert [G._adj(d, k) for k in S.M6_DELAY] == [False, True, True, False, False, True, True, False]


def test_ext_panel_uses_monthly_average_one_month_later():
    B = fake_B(end="2006-12-31")
    Pn = G.panel(B)
    A = {C.ym_add("1985-01", i): 100.0 * math.exp(0.01 * i) for i in range(264)}   # 1985-01～2006-12
    E = G.ext_panel(B, Pn, A)
    assert E["ym"][0] == "1985-01" and E["ym"][-1] == "2006-12"
    t = 10
    assert abs(E["R"][(0, 3)][t] - 0.03) < 1e-12                          # log A[t+4] − log A[t+1]
    assert E["R"][(0, 3)][E["T"] - 4] is None and E["R"][(0, 3)][E["T"] - 5] is not None
    main = {y: i for i, y in enumerate(Pn["ym"])}
    for k in ("B2", "G2"):                                                 # 主樣本月份的訊號和主樣本相同
        for ym, x in zip(E["ym"], E["it"][k]["X2"]["v0"]):
            if ym in main:
                assert x == Pn["it"][k]["X2"]["v0"][main[ym]]
            elif S.FREQ_OF[k] == "d":
                assert x is None
    assert any(x is not None for ym, x in zip(E["ym"], E["it"]["B2"]["X2"]["v0"]) if ym < "1997-07")


def test_run_smoke(monkeypatch):
    """合成資料跑完整流程：結構、判定代碼、可存成 JSON、樣本外切點。"""
    monkeypatch.setattr(S, "M6_BOOT", 40)
    B = fake_B()
    A = {C.ym_add("1985-01", i): 100.0 * math.exp(0.005 * i + 0.05 * math.sin(i)) for i in range(348)}
    out = G.run(B, A)
    json.dumps(out, allow_nan=False)
    assert out["ver"] == S.VER == 6 and set(out["items"]) == set(S.DERIV)
    codes = set()
    for k, e in out["items"].items():
        assert set(e["l1"]["d"]) == {G.wkey(w) for w in G.DELAY} and set(e["l1"]["c"]) == {G.wkey(w) for w in G.CUM}
        assert set(e["oos"]) == {G.wkey(w) for w in S.M6_OOS_WINDOWS}
        codes |= {r["v"] for part in ("d", "c") for r in e["l1"][part].values()}
        assert set(e["l3b"]) == {str(h) for h in S.M6_STATE_H} and set(e["l6"]["kinds"]) == {"1", "2", "3", "4"}
        assert e["sum"]["oos"] in ("pred", "fail", "untested", "few", "none")
    assert codes <= set(G.VERDICT)
    assert set(out["groups"]) == set(G.GVARS) | set(G.SVARS) and set(out["primary"]) == set(S.M6_PRIMARY)
    assert all(r["v"] in ("in_untested", "none", "few") for r in out["groups"]["SH_grow"]["l1"]["d"].values())
    assert all("holm" in out["primary"][h] and "pass" in out["primary"][h] for h in S.M6_PRIMARY)
    g = out["goos"][G.wkey((0, 3))]
    assert g["n"] > 0 and set(g["models"]) == {"m0", "m1", "m2", "m3", "ridge", "tree"} and g["tree"]
    assert out["ext"]["a"] == "1985-01" and "H1" in out["ext"]
    # 每一家族的 q 都算了（有 p 的就有 q）
    assert all((r.get("p") is None) == (r.get("q") is None) for e in out["items"].values() for r in e["l1"]["d"].values())
