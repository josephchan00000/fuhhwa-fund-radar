"""過熱之後 3 個月的最大回撤（docs/lab_hotdd_plan.md）：和逐筆直接算的版本比對。"""
import math
import random
from datetime import date, timedelta

import numpy as np

from arm.lab import heatpos as P
from arm.lab import heatviz as HV
from arm.lab import hotdd as K
from arm.lab import hotddspec as S


def _walk(n=900, seed=3, vol=0.012):
    rnd = random.Random(seed)
    px = [100.0]
    for _ in range(n - 1):
        px.append(px[-1] * math.exp(rnd.gauss(0.0003, vol)))
    return px


def _cal(n, start=date(2001, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_outcomes_match_direct_computation():
    px = _walk(400)
    O = K.outcomes(px, h=20, lag=1)
    for t in range(len(px)):
        a, b = t + 1, t + 21
        if b >= len(px):
            assert math.isnan(O["mdd"][t]) and O["pk"][t] == -1
            continue
        m, pk, tr = K.mdd_direct(px, a, b)
        assert abs(O["mdd"][t] - m) < 1e-12 and O["pk"][t] == pk and O["tr"][t] == tr
        assert abs(O["dd0"][t] - max(0.0, 1 - min(px[a + 1:b + 1]) / px[a])) < 1e-12
        assert abs(O["r60"][t] - (px[b] / px[a] - 1)) < 1e-12
        assert O["mdd"][t] >= O["dd0"][t] - 1e-12             # 從最高點算的回撤一定不小於從起點算的


def test_outcomes_gap_and_monotone():
    px = [float(i + 1) for i in range(100)]                    # 一路漲：沒有回撤
    O = K.outcomes(px, h=10, lag=1)
    assert np.nanmax(O["mdd"]) == 0 and O["pk"][0] == O["tr"][0] == 1
    px2 = list(px)
    px2[50] = None
    O2 = K.outcomes(px2, h=10, lag=1)
    for t in range(len(px)):                                  # 期間（t＋1～t＋11）缺一天＝沒有結果
        if t + 1 <= 50 <= t + 11:
            assert math.isnan(O2["mdd"][t])
        elif t + 11 < len(px):
            assert not math.isnan(O2["mdd"][t])


def test_events_week_streaks_exits():
    cal = _cal(200)
    we = P.week_ends(cal)
    x = [None] * 200
    for i in range(10, 200):
        x[i] = 50.0
    for i in range(40, 100):                                  # 第 40～99 天過熱
        x[i] = 90.0
    x[70] = None                                              # 中間一天沒有值（不是週末就不影響週數）
    runs = K.week_runs(x, we)
    for i, r in zip(we, runs):                                # 直接數：往回連續的週末都 ≥ 80
        n, j = 0, we.index(i)
        while j >= 0 and x[we[j]] is not None and x[we[j]] >= 80:
            n, j = n + 1, j - 1
        assert r == n
    assert we[:3] == [4, 9, 14]                                # 2001-01-01 是星期一：每週五是週末
    assert K.streaks(x, we, 4) == [59] and K.streaks(x, we, 8) == [79] and K.streaks(x, we, 13) == []
    assert K.exits(x, we, 4) == [104] and K.enter(x) == [40]
    # 沒有值的週末讓週數歸零、不算結束
    y = list(x)
    y[74] = None
    assert K.streaks(y, we, 4) == [59, 94]
    assert K.exits(y, we, 1) == [104] and K.exits(y, we, 7) == []


def test_multi_and_bubble_events():
    T = 120
    comp = {d: [50.0] * T for d in ("a", "b", "c", "d")}
    for t in range(60, 70):
        comp["a"][t] = comp["b"][t] = 85.0
    comp["c"][30] = 90.0                                       # 只有一個面向過熱不算
    assert K.multi(comp, list(comp)) == [60]
    comp2 = {d: list(v) for d, v in comp.items()}
    for d in ("b", "c", "d"):
        comp2[d][45] = None                                    # 前 20 天有一天不到 3 個面向有值
    assert K.multi(comp2, list(comp2)) == []
    cal = _cal(400)
    rows = [{"d": "2001-01-31", "L": 0}, {"d": "2001-02-28", "L": 2}, {"d": "2001-03-30", "L": 3},
            {"d": "2001-04-30", "L": 1}, {"d": "2001-05-31", "L": 2}, {"d": cal[-1], "L": 3}]
    months = K.bubble_months(rows, cal[-1])
    assert months[-1][0] == "2001-05-31"                       # 最後一個月還沒過完，不算
    ev2 = K.bubble_events(cal, months, 2)
    assert [cal[i] for i in ev2] == ["2001-02-28", "2001-05-31"]
    ev3 = K.bubble_events(cal, months, 3)
    assert [cal[i] for i in ev3] == ["2001-03-30"]


def test_boot_reps_match_direct_loop():
    rnd = np.random.default_rng(7)
    n, L = 700, 60
    y = rnd.random(n)
    flag = np.zeros(n, dtype=bool)
    flag[[10, 100, 300, 450, 600]] = True
    reps = K.boot_reps(y, flag, L=L, n_boot=50, seed=11)
    st = np.random.default_rng(11).integers(0, n - L + 1, size=(50, math.ceil(n / L)))
    for b in range(50):
        idx = np.concatenate([np.arange(s, s + L) for s in st[b]])
        f = flag[idx]
        want = y[idx][f].mean() - y[idx].mean() if f.any() else np.nan
        assert (math.isnan(want) and math.isnan(reps[b])) or abs(reps[b] - want) < 1e-12
    assert K.boot_reps(y, np.zeros(n, dtype=bool), L=L) is None
    assert K.boot_reps(y[:100], flag[:100], L=L) is None
    lo, hi, p, p1 = K.ci_p(K.boot_reps(y, flag, L=L))
    assert lo < hi and 0 < p <= 1 and 0 < p1 <= 1


def test_row_stats_match_direct():
    px = _walk(1500, seed=5)
    cal = _cal(1500)
    O = K.outcomes(px)
    vol = K.vol20(px)
    mask = ~np.isnan(O["mdd"])
    mask[:30] = False
    ev = [40, 41, 200, 420, 700, 900, 1100, 1300, 1350, 1600]   # 41 重複一段；1600 超出資料
    r = K.row_stats(ev, mask, O, vol, cal)
    evs = [t for t in ev if t < len(mask) and mask[t]]
    base = [t for t in range(len(px)) if mask[t]]
    me = [O["mdd"][t] for t in evs]
    mb = [O["mdd"][t] for t in base]
    assert r["n"] == len(evs) == 9 and r["ep"] == 7 and r["nb"] == len(base)
    assert abs(r["d"] - (np.mean(me) - np.mean(mb))) < 1e-12
    assert abs(r["ev"]["q10"] - np.mean([m >= 0.10 for m in me])) < 1e-12
    assert abs(r["base"]["med"] - np.median(mb)) < 1e-12
    m = len(evs) // 2
    cut = evs[m]
    h1 = np.mean(me[:m]) - np.mean([O["mdd"][t] for t in base if t < cut])
    h2 = np.mean(me[m:]) - np.mean([O["mdd"][t] for t in base if t >= cut])
    assert abs(r["h1"] - h1) < 1e-12 and abs(r["h2"] - h2) < 1e-12
    assert r["worst"]["mdd"] == max(me) and len(r["list"]) == 9 and r["list"][0][0] == cal[40]
    assert r["v"] is None                                      # 9 次、7 段：不是樣本不足
    few = K.row_stats(ev[:5], mask, O, vol, cal)
    assert few["v"] == "few"
    # 扣掉波動：直接算
    bv = np.array([vol[t] for t in base])
    ok = ~np.isnan(bv)
    cuts = np.quantile(bv[ok], [1 / 3, 2 / 3])
    g = lambda v: int(v >= cuts[0]) + int(v >= cuts[1])        # noqa: E731
    gm = {k: np.mean([O["mdd"][t] for t in base if not math.isnan(vol[t]) and g(vol[t]) == k]) for k in range(3)}
    want = np.mean([O["mdd"][t] - gm[g(vol[t])] for t in evs if not math.isnan(vol[t])])
    assert abs(r["vadj"] - want) < 1e-12


def test_verdict_rules():
    base = {"lo": 0.01, "hi": 0.05, "h1": 0.02, "h2": 0.01, "v": None}
    assert K.verdict(base, 0.05) == "up"
    assert K.verdict(base, 0.2) == "none"
    assert K.verdict({**base, "h2": -0.01}, 0.05) == "none"
    assert K.verdict({"lo": -0.05, "hi": -0.01, "h1": -0.02, "h2": -0.01, "v": None}, 0.01) == "down"
    assert K.verdict({**base, "v": "few"}, 0.01) == "few"


def _swing_direct(px, thr):
    """多空門檻法則的逐筆版本（測試對照）：上漲段記最高點、跌 thr 進下跌段；下跌段記最低點、反彈 thr 回上漲段。"""
    out, state, ext = [], "up", 0
    peak = None
    for i in range(1, len(px)):
        if state == "up":
            if px[i] > px[ext]:
                ext = i
            elif px[i] / px[ext] - 1 <= -thr:
                state, peak, ext = "down", ext, i
        else:
            if px[i] < px[ext]:
                ext = i
            elif px[i] / px[ext] - 1 >= thr:
                out.append((peak, ext, False))
                state, ext = "up", i
    if state == "down":
        out.append((peak, ext, True))
    return out


def test_declines_swing_rule_matches_direct():
    for seed in (9, 10, 11):
        px = _walk(3000, seed=seed, vol=0.02)
        cal = _cal(3000)
        for th in S.DECL_TH:
            a = K.declines(cal, px, th)
            assert [(e["pk"], e["tr"], e["open"]) for e in a] == _swing_direct(px, th)
            for e in a:
                assert e["dd"] >= th - 1e-12 and abs(e["dd"] - (1 - px[e["tr"]] / px[e["pk"]])) < 1e-12
                assert px[e["pk"]] == max(px[e["pk"]:e["tr"] + 1]) and px[e["tr"]] == min(px[e["pk"]:e["tr"] + 1])


def test_declines_count_drops_inside_long_underwater_period():
    """VER 2 的理由：一次大跌之後還沒回到前高，中間又出現的大跌也要算（VER 1 的回到前高規則看不到）。"""
    px = [100.0, 60.0, 80.0, 90.0, 60.0, 75.0, 95.0, 99.0]       # 100 → 60（−40%）、反彈到 90、再跌到 60（−33%）
    cal = _cal(len(px))
    a = K.declines(cal, px, 0.20)
    assert [(e["pk"], e["tr"]) for e in a] == [(0, 1), (3, 4)]
    assert len(HV.episodes(cal, px, 0.20)) == 1                  # 回到前高的規則只算一段


def test_recall_direct():
    cal = _cal(600)
    we = P.week_ends(cal)
    x = [None] * 20 + [50.0] * 580
    for i in range(200, 260):
        x[i] = 85.0
    decl = [{"pk": 270, "tr": 300, "dd": 0.2, "open": False}, {"pk": 500, "tr": 520, "dd": 0.15, "open": False},
            {"pk": 60, "tr": 70, "dd": 0.12, "open": False}]           # 第三段高點前 60 天還沒有資料，不算
    r = K.recall(x, we, decl)
    assert r["n"] == 2 and r["h1"] == 1 and r["h4"] == 1 and r["hit"] == [[1, 1], [0, 0]]
    days = [d for d in range(600) if x[d] is not None and d - 60 >= 20]
    want = np.mean([any(x[j] is not None and x[j] >= 80 for j in range(d - 60, d + 1)) for d in days])
    assert abs(r["c1"] - want) < 1e-12


def _fake_B(n=700, seed=4):
    from arm.lab import heatspec as HS
    from arm.lab import heatpage as HP
    cal = _cal(n)
    px = _walk(n, seed=seed)
    dims = list(HP.shown_dims())
    comp = {d: [50.0] * n for d in HS.DIMS}
    hc = {k: [40.0] * n for k in HS.KEYS}
    for i in range(n - 30, n):
        comp["tech"][i] = 88.0
        hc["C1"][i] = 92.0
    for i in range(n - 100, n - 50):
        hc["C2"][i] = 85.0                                     # 7 週多以前開始、50 天前結束
    return {"cal": cal, "px": px, "comp": comp, "hc": hc}, dims


def test_now_state():
    B, dims = _fake_B()
    st = K.now(B, None)
    ks = [r["k"] for r in st["hot"]]
    assert ks[0] == "tech" and "C1" in ks                       # 面向在前
    r = next(r for r in st["hot"] if r["k"] == "tech")
    n = len(B["cal"])
    we = P.week_ends(B["cal"])
    assert r["start"] == B["cal"][n - 30] and r["wk"] >= 5 and r["ev"] == ["E", "S4"]
    e = r["inst"]["E"]
    m, pk, tr = K.mdd_direct(B["px"], n - 30 + S.LAG, n - 1)          # 不到 60 天：算到今天
    assert abs(e["mdd"] - m) < 1e-12 and e["days"] == (n - 1) - (n - 30 + S.LAG) and not e["full"]
    w4 = [i for i in we if i >= n - 30][3]                              # 第 4 個過熱的週末
    s4 = r["inst"]["S4"]
    assert s4["d"] == B["cal"][w4] and abs(s4["mdd"] - K.mdd_direct(B["px"], w4 + S.LAG, n - 1)[0]) < 1e-12
    x = next(e for e in st["exit"] if e["k"] == "C2")["inst"]["X4"]
    assert x["d"] in B["cal"] and x["days"] <= S.H
    assert [e["k"] for e in st["exit"]] == ["C2"]
    assert st["multi"]["n"] == 1 and st["multi"]["dims"] == ["tech"]


def test_instance_caps_at_three_months():
    px = _walk(400, seed=8)
    cal = _cal(400)
    a = K.instance(cal, np.array(px), 100, 399)
    m = K.mdd_direct(px, 101, 161)[0]
    assert a["full"] and a["days"] == 60 and abs(a["mdd"] - m) < 1e-12
    b = K.instance(cal, np.array(px), 399, 399)                         # 今天才進入：還沒有之後的收盤
    assert b["mdd"] is None and b["days"] == 0 and not b["full"]
