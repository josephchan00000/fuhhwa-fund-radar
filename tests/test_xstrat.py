"""大神策略的計算（arm/lab/xstrat.py；規格 xstratspec VER 1）——和逐筆直接算的版本比對。"""
from datetime import date, timedelta

import numpy as np

from arm.lab import xstrat as X
from arm.lab import xstratspec as S


def _cal(n, start="2000-01-03"):
    """n 個平日（不管假日）。"""
    out, d = [], date.fromisoformat(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _px(n, seed=1, drift=0.0003, vol=0.012):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))


# ── 指標 ──

def test_sma_and_rsi_match_direct_computation():
    px = _px(300)
    for n in (2, 5, 200):
        m = X.sma(px, n)
        for i in range(len(px)):
            exp = np.nan if i < n - 1 else px[i - n + 1:i + 1].mean()
            assert (np.isnan(m[i]) and np.isnan(exp)) or abs(m[i] - exp) < 1e-9
    x = px.copy()
    x[50] = np.nan
    m = X.sma(x, 5)
    assert np.isnan(m[50:55]).all() and not np.isnan(m[55])
    r = X.rsi(px, 2)
    d = np.diff(px)
    au, ad = max(d[0], 0) / 2 + max(d[1], 0) / 2, max(-d[0], 0) / 2 + max(-d[1], 0) / 2
    assert abs(r[2] - (100 - 100 / (1 + au / ad) if ad else 100)) < 1e-9
    for i in range(3, 40):                         # Wilder 平滑
        au = (au + max(d[i - 1], 0)) / 2
        ad = (ad + max(-d[i - 1], 0)) / 2
        assert abs(r[i] - (100.0 if ad == 0 else 100 - 100 / (1 + au / ad))) < 1e-9


# ── 交易型 ──

def _brute_sig(setup, exit_ok, s0, lag):
    T = len(setup)
    out, i = [], s0
    while i < T:
        if setup[i]:
            e = i + lag
            if e >= T:
                return out, "buy"
            x = max(e, i + 1)
            while x < T and not exit_ok[x]:
                x += 1
            if x >= T:
                return out, "hold"
            q = x + lag
            if q >= T:
                return out, "sell"
            out.append((i, e, x, q))
            i = q
            continue
        i += 1
    return out, "wait"


def test_sig_trades_match_brute_force():
    rng = np.random.default_rng(3)
    for trial in range(200):
        T = int(rng.integers(5, 80))
        setup = rng.random(T) < rng.choice([0.05, 0.2, 0.5])
        ex = rng.random(T) < rng.choice([0.1, 0.4, 0.8])
        s0 = int(rng.integers(0, 4))
        for lag in (0, 1):
            tr, st = X.sig_trades(setup, ex, s0, lag)
            bt, bst = _brute_sig(setup, ex, s0, lag)
            assert tr == bt and st["st"] == bst


def test_tom_trades_and_now_states():
    cal = _cal(120)
    ends = [k for k in range(len(cal) - 1) if cal[k][:7] != cal[k + 1][:7]]
    tr, _ = X.tom_trades(cal, 0, 1, 3)
    assert tr == [(L - 1, L - 1, L + 3, L + 3) for L in ends if L + 3 < len(cal)]
    tr, _ = X.tom_trades(cal, 30, 0, 2)
    assert all(e >= 30 for _, e, _, _ in tr) and all(q - e == 2 for _, e, _, q in tr)


def test_trade_stats_and_base_win():
    px = _px(400, seed=5)
    trades = [(10, 11, 14, 15), (40, 41, 41, 42), (100, 101, 110, 111), (300, 301, 305, 306)]
    c = 0.001
    s = X.trade_stats(px, trades, 20, c)            # 第一筆買在 11 < 20：不算
    r = np.array([px[q] / px[e] * (1 - c) / (1 + c) - 1 for _, e, _, q in trades[1:]])
    assert s["n"] == 3 and abs(s["win"] - (r > 0).mean()) < 1e-12 and abs(s["avg"] - r.mean()) < 1e-12
    assert abs(s["hold"] - np.mean([1, 10, 5])) < 1e-12 and abs(s["worst"] - r.min()) < 1e-12
    bw = []
    for h in (1, 10, 5):
        x = [px[i + h] / px[i] * (1 - c) / (1 + c) - 1 > 0 for i in range(20, len(px) - h)]
        bw.append(np.mean(x))
    assert abs(s["base"] - np.mean(bw)) < 1e-12


def test_trade_equity_matches_trade_by_trade_compounding():
    px = _px(300, seed=7)
    trades = [(5, 6, 9, 10), (50, 51, 60, 61), (200, 200, 230, 230)]
    c = 0.002
    eq = X.trade_equity(px, trades, 0, c)
    exp = np.prod([px[q] / px[e] * (1 - c) / (1 + c) for _, e, _, q in trades])
    assert abs(eq[-1] - exp) < 1e-9
    # 持有中每天跟著指數動、空手不動
    assert abs(eq[8] / eq[7] - px[8] / px[7]) < 1e-12 and eq[30] == eq[20]


# ── 進出型 ──

def _brute_pos_monthly(px, ends, dec_fn, lag):
    T = len(px)
    pos = np.full(T, np.nan)
    for k in range(T):
        done = [m for m, e in enumerate(ends) if e + lag <= k]   # 已經照做的最近一次決定
        if done:
            pos[k] = dec_fn(done[-1])
    return pos


def test_monthly_positions_match_brute_force():
    cal = _cal(700)
    px = _px(700, seed=11)
    ends = X.month_ends(cal)
    mc = px[ends]
    for n in (3, 10):
        for lag in (0, 1):
            f = X.pos_faber(px, ends, n, lag)
            bf = _brute_pos_monthly(px, ends, lambda m: np.nan if m < n - 1 else float(mc[m] > mc[m - n + 1:m + 1].mean()), lag)
            assert np.array_equal(np.isnan(f), np.isnan(bf)) and np.allclose(np.nan_to_num(f), np.nan_to_num(bf))
            g = X.pos_mom(px, ends, n, lag)
            bg = _brute_pos_monthly(px, ends, lambda m: np.nan if m < n else float(mc[m] > mc[m - n]), lag)
            assert np.array_equal(np.isnan(g), np.isnan(bg)) and np.allclose(np.nan_to_num(g), np.nan_to_num(bg))


def test_daily_ma_and_halloween_positions():
    cal = _cal(500)
    px = _px(500, seed=13)
    m = X.sma(px, 50)
    p = X.pos_daily_ma(px, 50, 1)
    for k in range(1, 500):
        exp = np.nan if np.isnan(m[k - 1]) else float(px[k - 1] > m[k - 1])
        assert (np.isnan(p[k]) and np.isnan(exp)) or p[k] == exp
    h = X.pos_hal(cal, 11, 6)
    for k in range(len(cal) - 1):                  # 第 k 天收盤之後的部位＝下一個交易日在不在 11～4 月
        assert h[k] == (1.0 if int(cal[k + 1][5:7]) in (11, 12, 1, 2, 3, 4) else 0.0)
    assert X.hal_months(10, 6) == {10, 11, 12, 1, 2, 3} and X.hal_months(12, 6) == {12, 1, 2, 3, 4, 5}


def test_alloc_equity_matches_day_by_day_loop():
    px = _px(400, seed=17)
    rng = np.random.default_rng(2)
    pos = (rng.random(400) < 0.6).astype(float)
    pos[:5] = np.nan
    c = 0.001
    for lo in (10, 37):
        eq, nsw = X.alloc_equity(px, pos, lo, c)
        v, n, out = 1.0, 0, [1.0]
        p = np.nan_to_num(pos)
        for k in range(lo + 1, 400):
            if p[k - 1] > 0:
                v *= px[k] / px[k - 1]
            if p[k] != p[k - 1]:
                v *= 1 - c
                n += 1
            out.append(v)
        assert nsw == n and np.allclose(eq, out)


def test_curve_stats_cagr_mdd_worst_year():
    cal = _cal(800, "2001-01-01")
    px = _px(800, seed=19)
    eq = px / px[0]
    st = X.curve_stats(eq, cal, 0)
    yrs = (date.fromisoformat(cal[-1]) - date.fromisoformat(cal[0])).days / 365.25
    assert abs(st["cagr"] - (eq[-1] ** (1 / yrs) - 1)) < 1e-12
    peak, mdd = 0, 0
    for v in eq:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak)
    assert abs(st["mdd"] - mdd) < 1e-12
    last = {}
    for i, d in enumerate(cal):
        last[d[:4]] = i
    ys = sorted(last)
    full = [eq[last[b]] / eq[last[a]] - 1 for a, b in zip(ys, ys[1:]) if b != cal[-1][:4]]
    assert abs(st["worst"] - min(full)) < 1e-12


# ── 判定 ──

def test_pass_rules_and_tiers():
    ok = {"n": 40, "win": 0.65, "base": 0.55, "avg": 0.001}
    assert X.trade_pass(ok) and not X.trade_pass({**ok, "n": 29}) and not X.trade_pass({**ok, "win": 0.59})
    assert not X.trade_pass({**ok, "base": 0.61}) and not X.trade_pass({**ok, "avg": -0.0001})
    assert X.trade_pass_recent({**ok, "n": 9}) is None and X.trade_pass_recent({**ok, "n": 10}) is True
    b = {"cagr": 0.08, "mdd": 0.5}
    assert X.alloc_pass({"cagr": 0.06, "mdd": 0.3}, b)                     # 回撤 0.6 倍、0.2 ≥ 0.16
    assert not X.alloc_pass({"cagr": 0.06, "mdd": 0.34}, b)                # 回撤 0.68 倍
    assert not X.alloc_pass({"cagr": 0.04, "mdd": 0.3}, b)                 # 0.133 < 0.16
    assert X.tier("trade", True, True, 2 / 3, False) == "good"
    assert X.tier("trade", True, None, 1.0, False) == "good"               # 近 10 年筆數不夠＝不看
    assert X.tier("trade", True, False, 1.0, False) == "ref" and X.tier("alloc", True, True, 0.5, False) == "ref"
    assert X.tier("trade", False, True, 1.0, False) == "none" and X.tier("trade", True, True, 1.0, True) == "few"


def test_luck_is_deterministic_and_bounded():
    px = _px(2000, seed=23, drift=0.0002)
    trades = [(i, i + 1, i + 3, i + 4) for i in range(100, 1900, 37)]
    a = X.luck_trade(px, trades, 50, 0.0005, "xs:t:a")
    assert a == X.luck_trade(px, trades, 50, 0.0005, "xs:t:a") and 1 / 401 <= a <= 1
    cal = _cal(2000)
    pos = X.pos_daily_ma(px, 100, 1)
    b = X.luck_alloc(px, pos, 120, 0.0005, cal, "xs:t:b")
    assert b == X.luck_alloc(px, pos, 120, 0.0005, cal, "xs:t:b") and 1 / 401 <= b <= 1


# ── 用真的資料：結構、現在、和規格一致 ──

def test_real_markets_structure_and_now():
    R = X.run_all(force=True)
    assert set(R) == set(S.MARKETS)
    for mk, M in R.items():
        assert set(M) == {s["k"] for s in S.STRATS if mk in s["mk"]}
        for k, r in M.items():
            assert r["tier"] in S.TIERS and r["a"] >= S.EVAL_START[mk]
            assert len(r["grid"]) == np.prod([len(v) for v in S.BY_KEY[k]["grid"].values()])
            assert sum(g["ok"] for g in r["grid"]) / len(r["grid"]) == r["grid_ok"]
            main = [g for g in r["grid"] if all(S.BY_KEY[k]["p"][kk] == v for kk, v in g["p"].items())]
            assert len(main) == 1 and main[0]["ok"] == r["full"]["ok"]
            n = r["now"]
            assert n["d"] == r["z"] and n["st"] in S.STATE_NAMES
            if r["kind"] == "trade":
                assert n["st"] in ("buy", "hold", "sell", "wait")
                assert len(r["tr"]) == r["full"]["n"]
            else:
                assert n["st"] in ("in", "out", "turn_in", "turn_out")
            e = r["eq"]
            assert len(e["d"]) == len(e["s"]) == len(e["b"]) and e["d"][-1] == r["z"]
