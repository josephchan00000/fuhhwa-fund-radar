"""反向檢查（docs/lab_hotdd_plan.md 第 7 節）：和逐筆直接算的版本比對。"""
import json
import math
import random
from datetime import date, timedelta

import numpy as np

from arm.lab import heatpos as P
from arm.lab import heatviz as HV
from arm.lab import hotch as X
from arm.lab import hotchspec as S
from arm.lab import hotdd as K


def _walk(n=900, seed=3, vol=0.012, drift=0.0003):
    rnd = random.Random(seed)
    px = [100.0]
    for _ in range(n - 1):
        px.append(px[-1] * math.exp(rnd.gauss(drift, vol)))
    return px


def _cal(n, start=date(2001, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _score(n, seed=5):
    """0～100 的慢慢移動的分數（有長段落在 80 以上），開頭一段沒有值。"""
    rnd = random.Random(seed)
    v, out = 50.0, []
    for i in range(n):
        v = min(100.0, max(0.0, v + rnd.gauss(0, 4)))
        out.append(None if i < 30 else round(v, 2))
    return out


def test_streak_days_matches_direct():
    cal = _cal(700)
    we = P.week_ends(cal)
    x = _score(700, 7)
    x[300] = None                                          # 中間缺一天（如果剛好是週末就讓週數斷掉）
    w = X.streak_days(x, we)
    for t in range(len(x)):
        if x[t] is None:
            assert w[t] is None
            continue
        if x[t] < 80:
            assert w[t] == 0
            continue
        prior = [i for i in we if i < t]
        run = 0
        for i in reversed(prior):
            if x[i] is not None and x[i] >= 80:
                run += 1
            else:
                break
        assert w[t] == 1 + run
    for j, i in enumerate(we):                             # 週末那天＝景氣頁的「已連續幾週」
        if x[i] is not None and x[i] >= 80:
            assert w[i] == K.week_runs(x, we)[j]


def test_hot_runs_matches_direct():
    cal = _cal(900)
    we = P.week_ends(cal)
    x = _score(900, 11)
    runs = X.hot_runs(x, we)
    hot = [x[i] is not None and x[i] >= 80 for i in we]
    direct, j = [], 0
    while j < len(we):
        if hot[j]:
            k = j
            while k + 1 < len(we) and hot[k + 1]:
                k += 1
            if k - j + 1 >= 4:
                direct.append((j, k))
            j = k + 1
        else:
            j += 1
    assert runs == direct and runs


def test_window_mdds_and_pct_rank_match_direct():
    px = np.array(_walk(300, 9))
    L, lo = 25, 40
    m = X.window_mdds(px, L, lo, chunk=37)                 # 切塊的結果要和整段一樣
    assert len(m) == len(px) - L - lo
    for i, a in enumerate(range(lo, len(px) - L)):
        assert abs(m[i] - K.mdd_direct(list(px), a, a + L)[0]) < 1e-12
    v = float(np.median(m))
    assert X.pct_rank(v, m) == (np.sum(m < v) + 0.5 * np.sum(m == v)) / len(m)
    px2 = px.copy()
    px2[100] = np.nan
    m2 = X.window_mdds(px2, L, lo)
    for i, a in enumerate(range(lo, len(px) - L)):
        assert math.isnan(m2[i]) == (a <= 100 <= a + L)


def test_run_rows_window_and_percentile():
    n = 800
    cal = _cal(n)
    we = P.week_ends(cal)
    px = np.array(_walk(n, 13))
    x = [None] * 50 + [50.0] * (n - 50)
    for j in range(40, 52):                                # 第 40～51 個週末那幾週過熱（12 週）
        for t in range(we[j - 1] + 1, we[j] + 1):
            x[t] = 90.0
    for t in range(we[-6] + 1, n):                         # 最後 5 週也過熱、還沒結束
        x[t] = 85.0
    rows = X.run_rows(x, we, cal, px, 0)
    assert len(rows) == 2
    r = rows[0]
    assert (r["a"], r["s4"], r["z"], r["wk"], r["open"]) == (cal[we[40]], cal[we[43]], cal[we[51]], 12, False)
    a, b = we[43] + 1, we[51] + 60
    m, pk, tr = K.mdd_direct(list(px), a, b)
    assert abs(r["mdd"] - m) < 1e-12 and r["days"] == b - a
    pool = [K.mdd_direct(list(px), s, s + b - a)[0] for s in range(50, n - (b - a))]
    assert abs(r["pct"] - (sum(p < m for p in pool) + 0.5 * sum(p == m for p in pool)) / len(pool)) < 1e-12
    assert rows[1]["open"] and rows[1]["wk"] == 5 and rows[1]["days"] == n - 1 - (we[-2] + 1)


def test_td1_matches_direct():
    x = _score(1500, 21)
    ev = X.td1(x)
    for t in range(len(x)):
        ok = (t >= 60 and x[t] is not None and x[t] < 50
              and all(x[u] is not None and x[u] >= 50 for u in range(t - 20, t))
              and any(x[u] is not None and x[u] >= 80 for u in range(t - 60, t)))
        assert (t in ev) == ok
    assert ev


def test_phase_events_match_phase_track():
    cal = _cal(2000)
    we = P.week_ends(cal)
    x = _score(2000, 31)
    _, _, Ph = HV.phase_track([x[i] for i in we])
    for q in (1, 2):
        ev = X.phase_events(x, we, q)
        direct = [we[j] for j in range(1, len(we)) if Ph[j] == q and Ph[j - 1] not in (None, q)]
        assert ev == direct and ev


def _mask_setup(n=1500, seed=41):
    px = np.array(_walk(n, seed, vol=0.015))
    O = K.outcomes(px, S.H, S.LAG)
    O2 = K.outcomes(px, S.H_LONG, S.LAG)
    vol = K.vol20(px)
    mask = ~np.isnan(O["mdd"])
    mask[:100] = False
    return px, O, O2, vol, mask


def test_stats_matches_direct():
    px, O, O2, vol, mask = _mask_setup()
    cal = _cal(len(px))
    days = list(range(150, 1350, 70)) + [5, 1490]                      # 相隔 70 天（各自一段）；不在基準的日子要被拿掉
    st = X.stats(days, mask, O, O2, vol, cal, "ev", px=px, keep_list=True)
    base = np.nonzero(mask)[0]
    evs = sorted(t for t in set(days) if mask[t])
    mdd = O["mdd"]
    assert st["n"] == len(evs) and st["nb"] == len(base)
    assert abs(st["d"] - (mdd[evs].mean() - mdd[base].mean())) < 1e-12
    m = len(evs) // 2
    cut = evs[m]
    assert abs(st["h1"] - (mdd[evs[:m]].mean() - mdd[base[base < cut]].mean())) < 1e-12
    assert abs(st["h2"] - (mdd[evs[m:]].mean() - mdd[base[base >= cut]].mean())) < 1e-12
    # 扣掉波動：同一組波動的基準日子平均
    bv = vol[base]
    ok = ~np.isnan(bv)
    c1, c2 = np.quantile(bv[ok], [1 / 3, 2 / 3])
    grp = lambda v: int(v >= c1) + int(v >= c2)            # noqa: E731
    gm = {g: np.mean([mdd[b] for b in base[ok] if grp(vol[b]) == g]) for g in range(3)}
    res = [mdd[t] - gm[grp(vol[t])] for t in evs if not math.isnan(vol[t])]
    assert abs(st["dv"] - np.mean(res)) < 1e-9
    assert abs(st["dv"] - K.vol_adjusted(np.array(evs), base, mdd, vol)) < 1e-9   # 和過熱後回撤的「扣掉波動」同一個數
    # 比例、6 個月
    for th in S.DD_TH:
        k = f"q{int(round(th * 100))}"
        assert abs(st[f"d{k}"] - (np.mean(mdd[evs] >= th) - np.mean(mdd[base] >= th))) < 1e-12
        assert st[f"lo{k}"] <= st[f"d{k}"] <= st[f"hi{k}"]
    m2 = O2["mdd"]
    b2 = base[~np.isnan(m2[base])]
    e2 = [t for t in evs if not math.isnan(m2[t])]
    assert abs(st["long"]["d"] - (m2[e2].mean() - m2[b2].mean())) < 1e-12
    # 事件清單與訊號出現時已經跌了多少
    assert len(st["list"]) == len(evs)
    t = evs[3]
    assert abs(st["list"][3][4] - (1 - px[t] / px[max(0, t - 60):t + 1].max())) < 1e-12
    assert st["ev"]["dq10"] == np.mean(O["dd0"][evs] >= 0.10)
    assert st["n"] == st["ep"] == 18 and st["v"] is None and st["vv"] is None   # 18 次 18 段：可以判定


def test_stats_state_few_rules():
    px, O, O2, vol, mask = _mask_setup()
    cal = _cal(len(px))
    st = X.stats(list(range(200, 300)), mask, O, O2, vol, cal, "st")       # 100 天 < 120 天
    assert st["v"] == "few" and st["vv"] == "few"
    days = list(range(200, 230)) + list(range(400, 430)) + list(range(600, 630)) + list(range(800, 830)) \
        + list(range(1000, 1030)) + list(range(1200, 1230))                   # 180 天、6 段
    st2 = X.stats(days, mask, O, O2, vol, cal, "st")
    assert st2["n"] == 180 and st2["ep"] == 6 and st2["v"] is None
    assert "list" not in st2 and st2["yrs"] is None


def test_boot_two_matches_loop():
    rnd = np.random.default_rng(7)
    y = rnd.normal(size=500)
    f1 = rnd.random(500) < 0.05
    f2 = rnd.random(500) < 0.08
    L, nb = 20, 50
    reps = X.boot_two(y, f1, f2, L=L, n_boot=nb, seed=11)
    r2 = np.random.default_rng(11)
    k = math.ceil(500 / L)
    st = r2.integers(0, 500 - L + 1, size=(nb, k))
    for b in range(nb):
        idx = np.concatenate([np.arange(s, s + L) for s in st[b]])
        a1, a2 = f1[idx], f2[idx]
        want = y[idx][a1].mean() - y[idx][a2].mean() if a1.any() and a2.any() else np.nan
        assert (math.isnan(want) and math.isnan(reps[b])) or abs(reps[b] - want) < 1e-12
    v = X.versus(list(np.nonzero(f1)[0]), list(np.nonzero(f2)[0]), np.ones(500, dtype=bool), y)
    assert abs(v["d"] - (y[f1].mean() - y[f2].mean())) < 1e-12 and v["lo"] < v["hi"]


def test_decline_signals_direct():
    px = np.array([100, 105, 110, 104, 99, 95, 90, 85, 92, 98, 96, 88, 80, 79, 85, 96, 99], dtype=float)
    decl = K.declines(None, px, 0.20)
    assert [(e["pk"], e["tr"]) for e in decl] == [(2, 13)]      # 85 → 98 只反彈 15%，還在同一段
    rows = X.decline_signals(px, decl, [1, 5, 9], 0)        # 第一次在高點之後、低點以前的是 5
    r = rows[0]
    assert r["s"] == 5 and r["days"] == 3
    assert abs(r["lost"] - (1 - px[6] / px[2])) < 1e-12 and abs(r["rem"] - (1 - px[13] / px[6])) < 1e-12
    assert X.decline_signals(px, decl, [13], 0)[0]["rem"] == 0.0     # 低點那天才出現：賣在低點之後
    assert X.decline_signals(px, decl, [1, 16], 0)[0] == {"s": None}
    assert X.decline_signals(px, decl, [5], 3) == [None]              # 高點在可以算的日子以前
    s = X.decl_summary(rows + [None, {"s": None}])
    assert (s["n"], s["hit"]) == (2, 1) and s["lost"] == rows[0]["lost"]


def test_apply_bh_and_verdicts():
    def st(d, lo, hi, p, h1, h2, v=None):
        return {"d": d, "lo": lo, "hi": hi, "p": p, "h1": h1, "h2": h2, "v": v,
                "dv": d, "lov": lo, "hiv": hi, "pv": p, "hv1": h1, "hv2": h2, "vv": v}
    a = st(0.03, 0.01, 0.05, 0.001, 0.02, 0.03)
    b = st(-0.03, -0.05, -0.01, 0.002, -0.02, -0.01)
    c = st(0.01, -0.01, 0.03, 0.3, 0.02, -0.01)
    d = st(0.05, 0.02, 0.08, 0.001, 0.05, 0.05, v="few")
    d["vv"] = "few"
    X.apply_bh({"f": [a, b, c, d]})
    assert (a["v"], b["v"], c["v"], d["v"]) == ("up", "down", "none", "few")
    assert (a["vv"], b["vv"], c["vv"], d["vv"]) == ("up", "down", "none", "few")
    qs = K.bh([0.001, 0.002, 0.3])
    assert (a["q"], b["q"], c["q"]) == tuple(qs) and "q" not in d


def _fake_inputs(n=2600, seed=51):
    cal = _cal(n, date(1995, 1, 2))
    px = np.array(_walk(n, seed, vol=0.014))
    x = {k: _score(n, seed + i) for i, k in enumerate(S.CHIP_VARS["tw"] + S.CONTRAST_VARS)}
    return {"cal": cal, "px": px, "x": x, "i0": 0}


def test_market_research_and_primary_smoke():
    I = _fake_inputs()
    M = X.market("tw", I)
    A, B = M["A"], M["B"]
    assert set(A) == set(S.CHIP_VARS["tw"]) | set(S.CONTRAST_VARS)
    for k, row in A.items():
        assert set(row["st"]) == {"H0"} | set(S.STATES_A)
        assert ("runs" in row) == (row["kind"] == "chip")
        n = [row["st"][s]["n"] for s in S.STATES_A]
        assert n == sorted(n, reverse=True)                   # 累計狀態：天數越來越少
    assert set(B["ev"]) == set(S.TECH_EVENTS) and set(B["st"]) == set(S.TECH_STATES) and set(B["vs"]) == set(S.TECH_EVENTS)
    for th in ("10", "20"):
        assert set(B["dsum"][th]) == set(S.TECH_EVENTS)
        assert all(len(B["drows"][th][k]) == len(B["decl"][th]) for k in S.TECH_EVENTS)
    for st in B["ev"].values():
        assert st["v"] in ("up", "down", "none", "few") and st["vv"] in ("up", "down", "none", "few")
    IU = {"spx": {**_fake_inputs(2400, 61), "x": {k: _score(2400, 70 + i) for i, k in
                                                  enumerate(S.CHIP_VARS["us"] + S.CONTRAST_VARS)}}}
    R = X.research(IT=I, IU=IU)
    assert R["ver"] == S.VER and set(R["markets"]) == {"tw", "spx"}
    assert set(R["primary"]) == set(S.PRIMARY)
    for h, v in R["primary"].items():
        assert isinstance(v["ok"], bool) and isinstance(v["few"], bool)
    json.dumps(R, ensure_ascii=False)                          # 研究檔寫得出來


def test_loo_drops_each_episode():
    y = np.arange(400, dtype=float) / 100.0
    evs = list(range(10, 20)) + list(range(200, 205)) + list(range(390, 400))   # 三段
    bm = 1.5
    lo, hi = X.loo(evs, y, bm)
    groups = [list(range(10, 20)), list(range(200, 205)), list(range(390, 400))]
    vals = [np.mean([y[t] for t in evs if t not in g]) - bm for g in groups]
    assert abs(lo - min(vals)) < 1e-12 and abs(hi - max(vals)) < 1e-12
    assert X.loo(list(range(10, 30)), y, bm) is None                            # 只有一段


def test_state_key_and_now():
    assert [X.state_key(w) for w in (None, 0, 1, 3, 4, 12, 13, 25, 26, 99)] == \
        [None, "H0", "H1", "H1", "H4", "H4", "H13", "H13", "H26", "H26"]
    n = 900
    cal = _cal(n)
    we = P.week_ends(cal)
    px = np.array(_walk(n, 17))
    xs = [50.0] * n
    for t in range(we[-7] + 1, n):                         # 最後 6 週都過熱（今天＝最後一天，也是週末）
        xs[t] = 88.0
    I = {"cal": cal, "px": px, "x": {"C1": xs, "Dtech": [50.0] * n}, "i0": 0}
    N = X.now(I)
    c = N["chip"]["C1"]
    assert c["w"] == 6 and c["key"] == "H4" and c["v"] == 88.0
    s4 = we[-3]
    r = c["run"]
    assert (r["a"], r["s4"], r["wk"]) == (cal[we[-6]], cal[s4], 6)
    m, pk, tr = K.mdd_direct(list(px), s4 + 1, n - 1)
    assert abs(r["mdd"] - m) < 1e-12 and r["days"] == n - 1 - (s4 + 1)
    assert N["chip"]["Dtech"]["w"] == 0 and N["chip"]["Dtech"]["run"] is None
    assert set(N["recent"]) == set(S.TECH_EVENTS) and N["d"] == cal[-1]
    assert set(N["states"]) == set(S.TECH_STATES)
