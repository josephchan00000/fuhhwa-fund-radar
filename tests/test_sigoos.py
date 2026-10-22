"""預估之後（arm/lab/sigoos.py；sigspec 第 4.14 節 VER 18～21；docs/lab_practical_plan.md 第 10 節、docs/lab_audit_plan.md 第 11 節）。

逐年紀錄和逐筆直接算的版本比對、訓練不偷看 cut 之後的資料、衰退表的比例與截斷、往上一層的順序、預估之後的公式、
跨期間的格子（x:）與逐年加總（溫度計校正用）。"""
import math

import numpy as np
import pytest

from arm.lab import sigcat as G
from arm.lab import sigoos as O
from arm.lab import sigspec as S

RNG = np.random.default_rng(7)
T = 3000
PX = 100 * np.exp(np.cumsum(RNG.normal(0.0004, 0.012, T)))
H = 20


def _sd_event(days, samp):
    return {"id": "t:ev", "kind": "event", "H": H, "samp": np.asarray(samp, dtype=np.int64), "days": list(days)}


def _sd_state(state, samp):
    return {"id": "t:st", "kind": "state", "H": H, "samp": np.asarray(samp, dtype=np.int64), "state": np.asarray(state, dtype=bool)}


def _arrays(px=PX):
    Yu, Yw, _ = G.outcomes(px, H, G.warn_th("tw", H))
    return Yu, Yw, O._ra1(px, H)


def _med_direct(xs, ws=None):
    """第 4.11 節：由小到大排，累計權重第一次 ≥ 一半的那一個值（不內插）。"""
    ws = [1.0] * len(xs) if ws is None else ws
    pairs = sorted(zip(xs, ws), key=lambda p: p[0])
    tot = sum(ws)
    acc = 0.0
    for x, w in pairs:
        acc += w
        if acc >= 0.5 * tot * (1 - 1e-12):
            return x
    return pairs[-1][0]


def _ret(px, t):
    return px[t + S.LAG + H] / px[t + S.LAG] - 1.0


def test_buckets_and_chain_are_locked():
    assert [O.nb(n) for n in (5, 14, 15, 39, 40, 400)] == [0, 0, 1, 1, 2, 2]
    assert [O.eb(e) for e in (-0.3, -1e-9, 0.0, 0.0499, 0.05, 0.0999, 0.10, 0.1999, 0.20, 0.5)] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert O.chain("up", 60, 20, 0.12) == ["up|60|1|3", "up|60|*|3", "up|60|*|p"]
    assert O.chain("warn", 250, 7, -0.02) == ["warn|250|0|0", "warn|250|*|0", "warn|250|*|n"]
    assert O.chain("buy", 60, 9, 0.07) == ["buy|60|0|2", "buy|60|*|2", "buy|60|*|p", "up|60|0|2", "up|60|*|2", "up|60|*|p"]
    assert O._neg("up|60|*|0") and O._neg("up|60|*|n") and not O._neg("up|60|1|1") and not O._neg("up|60|*|p")
    assert len(O.LEVEL_NAMES) == 6 and O.MARKET_CATS == ("heat", "multi", "scen", "inst", "tech", "deriv", "crash", "bub")


def test_train_event_matches_direct_and_does_not_look_ahead():
    samp = np.arange(30, T, dtype=np.int64)
    days = sorted(int(x) for x in RNG.choice(np.arange(40, T - 5), 160, replace=False))
    sd = _sd_event(days, samp)
    Yu, Yw, ra = _arrays()
    c, r0 = 1800, 600
    Tn = O.train(sd, c, r0, Yu, Yw, ra)
    # 直接算：窗口在 cut 之前走完的樣本日、出現日去重
    ts = [int(t) for t in samp if t + S.LAG + H < c]
    kept, last = [], None
    for t in days:
        if t + S.LAG + H < c and t in set(ts) and (last is None or t - last > H):
            kept.append(t)
            last = t
    up = [float(PX[t + S.LAG + H] > PX[t + S.LAG]) for t in kept]
    base = np.mean([float(PX[t + S.LAG + H] > PX[t + S.LAG]) for t in ts])
    st = Tn["R"]["up"]
    assert st["n"] == len(kept) and math.isclose(st["hit"], np.mean(up)) and math.isclose(st["base"], base)
    assert math.isclose(Tn["cell"][3], _med_direct([_ret(PX, t) for t in kept]))
    assert math.isclose(Tn["bmed"], _med_direct([_ret(PX, t) for t in ts]))
    assert math.isclose(Tn["cell"][1], np.mean([_ret(PX, t) for t in kept])) and math.isclose(Tn["bmean"], np.mean([_ret(PX, t) for t in ts]))
    # 不偷看：把 cut 之後的資料全部拿掉重算，結果一樣
    px2 = PX[:c].copy()
    Yu2, Yw2, ra2 = _arrays(px2)
    sd2 = _sd_event([t for t in days if t < c], samp[samp < c])
    T2 = O.train(sd2, c, r0, Yu2, Yw2, ra2)
    assert T2["R"]["up"] == st and T2["R"]["warn"] == Tn["R"]["warn"] and T2["cell"] == Tn["cell"] and T2["bmed"] == Tn["bmed"]


def test_train_state_matches_direct_and_does_not_look_ahead():
    samp = np.arange(30, T, dtype=np.int64)
    st = np.zeros(len(samp), dtype=bool)
    for a in RNG.choice(np.arange(0, len(samp) - 80), 25, replace=False):
        st[a:a + int(RNG.integers(5, 60))] = True
    sd = _sd_state(st, samp)
    Yu, Yw, ra = _arrays()
    c, r0 = 2100, 900
    Tn = O.train(sd, c, r0, Yu, Yw, ra)
    m = samp + S.LAG + H < c
    ts, sm = samp[m], st[m]
    eps = G.episodes(np.nonzero(sm)[0].tolist(), S.EP_GAP)
    alld = [t for ep in eps for t in ts[ep]]
    hits = [float(PX[t + S.LAG + H] > PX[t + S.LAG]) for t in alld]
    assert Tn["R"]["up"]["n"] == len(eps) and math.isclose(Tn["R"]["up"]["hit"], np.mean(hits))   # VER 22：每一天一樣重
    xs = [_ret(PX, t) for t in alld]
    assert math.isclose(Tn["cell"][3], _med_direct(xs))
    assert math.isclose(Tn["cell"][1], np.mean(xs))
    px2 = PX[:c].copy()
    Yu2, Yw2, ra2 = _arrays(px2)
    keep = samp < c
    T2 = O.train(_sd_state(st[keep], samp[keep]), c, r0, Yu2, Yw2, ra2)
    assert T2["R"]["up"] == Tn["R"]["up"] and T2["cell"] == Tn["cell"] and T2["bmed"] == Tn["bmed"]


def test_test_year_matches_direct():
    samp = np.arange(30, T, dtype=np.int64)
    days = sorted(int(x) for x in RNG.choice(np.arange(40, T - 5), 200, replace=False))
    sd = _sd_event(days, samp)
    Yu, Yw, ra = _arrays()
    Yr = ra["R"][H]
    c, c2 = 1500, 1750
    te = O.test(sd, O.prep(sd), c, c2, Yu, Yr)
    kept, last = [], None
    for t in days:                                   # 全部資料去重，再取這一年
        if last is None or t - last > H:
            kept.append(t)
            last = t
    tt = [t for t in kept if c <= t < c2]
    assert te[2] == len(tt) and math.isclose(te[0], np.mean([float(PX[t + S.LAG + H] > PX[t + S.LAG]) for t in tt]))
    assert math.isclose(te[1], np.mean([_ret(PX, t) for t in tt]))              # VER 19：平均
    bs = [int(t) for t in samp if c <= t < c2]
    assert math.isclose(te[3], np.mean([float(PX[t + S.LAG + H] > PX[t + S.LAG]) for t in bs]))
    assert math.isclose(te[4], np.mean([_ret(PX, t) for t in bs]))
    # 狀態型：這一年在狀態中的樣本日，依全部資料的分段；VER 22 起每一天一樣重（次數＝段數）
    st = np.zeros(len(samp), dtype=bool)
    st[1440:1530] = True                              # 跨過 cut 的一段
    st[1600:1610] = True
    st[1700:1760] = True                              # 跨過下一個 cut
    sd2 = _sd_state(st, samp)
    te2 = O.test(sd2, O.prep(sd2), c, c2, Yu, Yr)
    groups = [[int(samp[i]) for i in range(1440, 1530) if c <= samp[i] < c2], [int(samp[i]) for i in range(1600, 1610)],
              [int(samp[i]) for i in range(1700, 1760) if c <= samp[i] < c2]]
    assert te2[2] == 3
    alld = [t for g in groups for t in g]
    assert math.isclose(te2[0], np.mean([float(PX[t + S.LAG + H] > PX[t + S.LAG]) for t in alld]))
    assert math.isclose(te2[1], np.mean([_ret(PX, t) for t in alld]))
    assert O.test(sd2, O.prep(sd2), 2900, 3000, Yu, Yr) is None      # 窗口沒走完的不算


def _rec(d, H_, n, e, o, er=None, orr=None, mk="tw", yr=2000, tier="none"):
    r = {"mk": mk, "id": f"{mk}:{d}:{n}:{e}", "d": d, "H": H_, "yr": yr, "n": n, "e": e, "o": o, "tn": 1, "tier": tier}
    if er is not None:
        r.update(er=er, **{"or": orr})
    return r


def test_cell_ratio_clip_and_thresholds():
    rs = [_rec("up", 20, 20, 0.12, 0.04, 0.02, 0.005, yr=1990 + i % 40, mk=("tw", "spx")[i % 2]) for i in range(200)]
    T_ = O.table(rs)
    c = T_["up|20|1|3"]
    assert c["n"] == 200 and c["ncl"] == 40 and math.isclose(c["k"], 0.04 / 0.12) and math.isclose(c["kr"], 0.25)
    assert c["ci"][0] - 1e-9 <= c["kraw"] <= c["ci"][1] + 1e-9
    # 之後比過去還好 → 截成 1；之後比平常差 → 截成 0
    hi = O.table([_rec("up", 20, 20, 0.12, 0.30, yr=1990 + i % 40, mk=("tw", "spx")[i % 2]) for i in range(200)])["up|20|1|3"]
    lo = O.table([_rec("up", 20, 20, 0.12, -0.05, yr=1990 + i % 40, mk=("tw", "spx")[i % 2]) for i in range(200)])["up|20|1|3"]
    assert hi["k"] == 1.0 and lo["k"] == 0.0 and hi["kr"] is None
    # 筆數、市場 × 年數不夠 → 算不出
    few = O.table([_rec("up", 20, 20, 0.12, 0.04, yr=1990 + i % 40) for i in range(99)])["up|20|1|3"]
    assert few["k"] is None
    one_cl = O.table([_rec("up", 20, 20, 0.12, 0.04, yr=2000) for i in range(300)])["up|20|1|3"]
    assert one_cl["k"] is None and one_cl["ncl"] == 1
    # 比平常低那一格：e 的平均要 < 0
    neg = O.table([_rec("warn", 60, 20, -0.08, -0.02, yr=1990 + i % 40, mk=("tw", "spx")[i % 2]) for i in range(200)])
    assert math.isclose(neg["warn|60|1|0"]["k"], 0.25) and math.isclose(neg["warn|60|*|n"]["k"], 0.25)
    # 前後兩段、★◆ 與其他
    assert c["split"]["a"][0] + c["split"]["b"][0] == 200 and c["gs"]["other"][0] == 200 and c["gs"]["star"][0] == 0


def test_lookup_goes_up_levels_and_buy_falls_back_to_bullish():
    rs = []
    for i in range(400):                                          # L1 只有 50 筆（不夠）、L2 夠
        yr, mk = 1980 + i % 45, ("tw", "spx", "sox")[i % 3]
        rs.append(_rec("up", 60, 20 if i < 50 else 60, 0.15, 0.03, 0.04, 0.01, mk=mk, yr=yr))
    for i in range(120):
        rs.append(_rec("buy", 60, 8, 0.07, 0.01, mk="tw", yr=1990 + i % 10))   # 只有 10 個市場 × 年 → buy 的格子都不夠
    cells = O.table(rs)
    L = O.lookup(cells, "up", 60, 20, 0.15)
    assert L["lv"] == 1 and L["key"] == "up|60|*|3" and math.isclose(L["k"], 0.2) and math.isclose(L["kr"], 0.25)
    B = O.lookup(cells, "buy", 60, 8, 0.15)
    assert B["key"] == "up|60|*|3" and O.LEVEL_NAMES[B["lv"]] == "L2・偏多"
    none = O.lookup(cells, "warn", 20, 20, 0.15)
    assert none["k"] == 0.0 and none["lv"] is None and none["kr"] == 0.0        # 都找不到：k＝0、k_r 用 k


def test_est_formula():
    cells = {"up|60|1|3": {"k": 0.3, "kr": 0.5}, "warn|60|1|3": {"k": 0.2, "kr": None}}
    Tf = {"cells": cells, "own": {"x:1": {"up": [7, 0.14, 0.04, 0.02, 0.01]}}}
    r = {"id": "x:1", "mk": "tw", "cat": "heat", "H": 60, "ret": {"s": [None] * 4 + [[30, 0, 0, 0.05, 0, 0, 0, 0, 0, 0, 0]], "bk": "zz"},
         "up": {"n": 20, "hit": 0.80, "base": 0.65}, "warn": {"n": 20, "hit": 0.55, "base": 0.40}}
    G._RCACHE["rows"], G._RCACHE["bases"] = [], {"zz": {"s": [None] * 4 + [[1, 0, 0, 0.02, 0]]}}
    try:
        u = O.est(r, "up", Tf)
        assert math.isclose(u["fh"], 0.65 + 0.3 * 0.15) and u["lv"] == 0
        assert math.isclose(u["ex"], 0.03) and math.isclose(u["fx"], 0.015) and math.isclose(u["fm"], 0.035)
        assert u["own"] == [7, 0.14, 0.04, 0.02, 0.01]
        w = O.est(r, "warn", Tf)
        assert math.isclose(w["fh"], 0.40 + 0.2 * 0.15) and "fx" not in w
        assert O.est({**r, "cat": "ind"}, "up", Tf) is None and O.est({**r, "cat": "stock"}, "up", Tf) is None
        assert O.est({**r, "up": {"n": 4, "hit": 0.9, "base": 0.6}}, "up", Tf) is None
        assert O.est(r, "up", {}) is None
    finally:
        G._RCACHE.clear()


def test_table_is_deterministic():
    rs = [_rec("up", 20, 20, 0.12 + 0.001 * (i % 7), 0.04 - 0.01 * (i % 5), yr=1990 + i % 40, mk=("tw", "spx")[i % 2]) for i in range(300)]
    assert O.table(rs) == O.table(list(rs))


def test_cross_horizon_keys_are_separate():
    """VER 21 ⑧：跨期間的紀錄放另一套格子（鍵前面 x:），往上找只找 x 的格子；大跌後買點不接偏多那一串。"""
    assert O.key("up", 20, 1, 3, x=True) == "x:up|20|1|3" and O.split_key("x:warn|250|*|n") == (True, "warn", 250, "*", "n")
    assert O.split_key("up|60|0|2") == (False, "up", 60, "0", "2")
    assert O.chain("up", 20, 20, 0.12, x=True) == ["x:up|20|1|3", "x:up|20|*|3", "x:up|20|*|p"]
    assert O.chain("buy", 60, 9, 0.07, x=True) == ["x:buy|60|0|2", "x:buy|60|*|2", "x:buy|60|*|p"]
    own = [_rec("up", 20, 20, 0.12, 0.04, yr=1990 + i % 40, mk=("tw", "spx")[i % 2]) for i in range(200)]
    xr = [{**_rec("up", 20, 20, 0.12, 0.0, yr=1990 + i % 40, mk=("tw", "spx")[i % 2]), "x": 1} for i in range(200)]
    cells = O.table(own + xr)
    assert math.isclose(cells["up|20|1|3"]["k"], 0.04 / 0.12) and cells["x:up|20|1|3"]["k"] == 0.0
    assert O.lookup(cells, "up", 20, 20, 0.12)["key"] == "up|20|1|3"
    L = O.lookup(cells, "up", 20, 20, 0.12, x=True)
    assert L["key"] == "x:up|20|1|3" and L["k"] == 0.0
    only_own = O.table(own)                                         # 沒有 x 的格子＝k 0，不借訊號自己看多久的格子
    assert O.lookup(only_own, "up", 20, 20, 0.12, x=True)["k"] == 0.0 and O.lookup(only_own, "up", 20, 20, 0.12, x=True)["lv"] is None
    # 自己的逐年、各市場的 L3 不算跨期間的紀錄
    assert O.by_market(own + xr) == O.by_market(own) and O.own(own + xr) == O.own(own)


def test_yearly_sums_reproduce_table_and_respect_lag():
    """VER 21 ⑨：逐年加總到最後一年＝衰退表的 k；加總到某一年＝只用那一年以前的紀錄（減 CAL_K_LAG）。"""
    rng = np.random.default_rng(3)
    rs = []
    for i in range(900):
        H_ = (20, 60, 250)[i % 3]
        d = ("up", "warn")[(i // 3) % 2]
        e = float(rng.normal(0.08, 0.06))
        rs.append({**_rec(d, H_, int(rng.integers(5, 80)), e, float(e * 0.4 + rng.normal(0, 0.05)),
                          yr=1985 + int(rng.integers(0, 40)), mk=S.MARKETS[i % 5]), **({"x": 1} if i % 4 == 0 else {})})
    tab, yk = O.table(rs), O.yearly(rs)
    assert set(yk) == set(tab)
    full = O.ktab(yk, 3000)
    for k, c in tab.items():
        assert (full[k]["k"] is None) == (c["k"] is None), k
        if c["k"] is not None:
            assert math.isclose(full[k]["k"], c["k"], abs_tol=1e-6), k
        ys = yk[k]
        assert sum(a[0] for a in ys.values()) == c["n"] and sum(a[1] for a in ys.values()) == c["ncl"]
    for year in (2005, 2012, 2020):
        part = O.ktab(yk, year)
        for k in tab:
            lag = S.CAL_K_LAG[O.split_key(k)[2]]
            sub = [r for r in rs if r["yr"] <= year - lag and k in O.chain(r["d"], r["H"], r["n"], r["e"], bool(r.get("x")))[:3]]
            want = O.table(sub).get(k, {"k": None})["k"] if sub else None
            assert (part[k]["k"] is None) == (want is None), (year, k)
            if want is not None:
                assert math.isclose(part[k]["k"], want, abs_tol=1e-6), (year, k)


def test_est_x_uses_cross_cells_and_xh_stats():
    cells = {"x:up|20|1|3": {"k": 0.4}, "up|20|1|3": {"k": 0.9}, "x:warn|250|0|2": {"k": 0.1}}
    Tf = {"cells": cells, "own": {}}
    r = {"id": "tw:heat:a:hot", "mk": "tw", "cat": "heat", "H": 60,
         "xh": {"short": {"H": 20, "th": 0.08, "up": {"n": 20, "hit": 0.75, "base": 0.62}, "warn": {"n": 3, "hit": 0.6, "base": 0.3}},
                "long": {"H": 250, "th": 0.2, "up": {"n": 9, "hit": 0.6, "base": 0.7}, "warn": {"n": 9, "hit": 0.35, "base": 0.28}}}}
    u = O.est_x(r, "up", "short", Tf)
    assert u["key"] == "x:up|20|1|3" and math.isclose(u["fh"], 0.62 + 0.4 * 0.13) and u["H"] == 20 and u["lv"] == 0
    assert O.est_x(r, "warn", "short", Tf) is None                         # 次數 < N_MIN
    w = O.est_x(r, "warn", "long", Tf)
    assert w["key"] == "x:warn|250|0|2" and math.isclose(w["fh"], 0.28 + 0.1 * 0.07)
    lu = O.est_x(r, "up", "long", Tf)                                       # 找不到 x 的格子＝k 0（預估之後＝平常）
    assert lu["k"] == 0.0 and math.isclose(lu["fh"], 0.7) and lu["lv"] is None
    assert O.est_x(r, "up", "mid", Tf) is None and O.est_x({**r, "cat": "ind"}, "up", "short", Tf) is None
    assert O.est_x(r, "up", "short", {}) is None


def test_research_file_is_consistent():
    R = O.load()
    if R is None:
        pytest.skip("研究檔要先跑：TZ=Asia/Taipei python3 scripts/run_sigoos.py")
    assert R["ver"] >= S.FWD_VER and R["nrec"] > 10000 and 0 < R["nrec_x"] < R["nrec"]
    assert set(R["yk"]) == set(R["cells"])
    for k, c in R["cells"].items():
        x, d, H_, b, g = O.split_key(k)
        assert d in ("up", "warn", "buy") and H_ in (20, 60, 250) and not (x and d == "buy")
        for f in ("k", "kr"):
            assert c[f] is None or 0.0 <= c[f] <= 1.0
        if c["k"] is not None:
            assert c["n"] >= S.FWD_MIN_N and c["ncl"] >= S.FWD_MIN_CL
    assert {m for m in R["mk"]} <= set(S.MARKETS)
