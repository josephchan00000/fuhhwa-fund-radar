"""訊號總覽的計算（arm/lab/sigcat.py）：和逐筆直接算的版本比對。"""
import numpy as np

from arm.lab import sigcat as G
from arm.lab import sigspec as S


def _px(T=400, seed=1):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, T)))


def _mdd(xs):
    """直接算：所有 i ≤ j 的 1 − 收盤j ÷ 收盤i 取最大。"""
    return max(max(0.0, 1 - xs[j] / xs[i]) for i in range(len(xs)) for j in range(i, len(xs)))


def test_outcomes_match_direct_loop():
    """sigspec VER 3：警示＝第 e～e＋H 天收盤的最大回撤 ≥ 門檻（先漲再跌也算）。"""
    px = _px()
    for H, th in ((20, 0.08), (60, 0.10)):
        up, wn, dd = G.outcomes(px, H, th)
        for t in range(len(px)):
            e = t + S.LAG
            if e + H > len(px) - 1:
                assert np.isnan(up[t]) and np.isnan(wn[t]) and np.isnan(dd[t])
                continue
            assert up[t] == float(px[e + H] > px[e])
            m = _mdd(list(px[e:e + H + 1]))
            assert abs(dd[t] - m) < 1e-12
            assert wn[t] == float(m >= th)


def test_warn_counts_rise_then_fall():
    """先漲 20% 再從高點跌 15%：從進場價算只跌 2%（VER 1～2 不算），最大回撤 15% 算中了。"""
    px = [100.0, 100.0] + [100 + i for i in range(1, 21)] + [120 * (1 - 0.0075 * i) for i in range(1, 21)] + [102.0] * 30
    up, wn, dd = G.outcomes(px, 60, 0.10)
    assert abs(dd[0] - 0.15) < 1e-9 and wn[0] == 1.0 and up[0] == 1.0
    assert abs(G.mdd_path([100, None, 120, 102, float("nan"), 110]) - 0.15) < 1e-12
    assert G.mdd_path([100, 101, 102]) == 0.0 and G.mdd_path([None]) is None


def test_outcomes_with_gaps():
    px = _px(200, 3)
    px[50:55] = np.nan
    up, wn, dd = G.outcomes(px, 20, 0.08)
    for t in range(len(px) - 21):
        e = t + 1
        w = [x for x in px[e:e + 21] if not np.isnan(x)]
        if np.isnan(px[e]) or np.isnan(px[e + 20]):
            assert np.isnan(dd[t])
            continue
        assert abs(dd[t] - _mdd(w)) < 1e-12


def test_dedupe_skips_repeats_within_horizon():
    assert G.dedupe([5, 10, 25, 26, 47, 100], 20) == [5, 26, 47, 100]
    assert G.dedupe([], 20) == []


def test_episodes_gap_rule():
    # 中斷的樣本數 < gap 算同一段
    assert G.episodes([0, 1, 2, 10, 30, 31], 20) == [[0, 1, 2, 10, 30, 31]]     # 中斷 19 天
    assert G.episodes([0, 1, 2, 10, 31, 32], 20) == [[0, 1, 2, 10], [31, 32]]   # 中斷 20 天
    assert G.episodes([3, 4, 6], 1) == [[3, 4], [6]]


def test_state_stat_is_mean_over_state_days():
    T = 300
    Yu = np.array([float(i % 3 == 0) for i in range(T)])
    Yw = 1 - Yu
    Yu[-5:] = np.nan
    Yw[-5:] = np.nan
    samp = np.arange(T)
    state = np.zeros(T, dtype=bool)
    state[10:20] = True                    # 一段
    state[100:105] = True                  # 一段
    state[110:112] = True                  # 中斷 4 天 < 20 → 同一段
    state[297:300] = True                  # 窗口都不完整 → 不算
    Yd = np.linspace(0, 0.3, T)
    Yd[-5:] = np.nan
    R = G.st_stat(state, samp, Yu, Yw, 20, 150, Yd)
    days = np.concatenate([Yu[10:20], Yu[100:105], Yu[110:112]])       # VER 22：狀態中的每一天一樣重（次數仍是段數）
    assert R["up"]["n"] == 2 and abs(R["up"]["hit"] - days.mean()) < 1e-12
    assert abs(R["up"]["base"] - np.nanmean(Yu)) < 1e-12
    assert R["up"]["n10"] == 0 and R["up"]["hit10"] is None
    assert abs(R["up"]["base10"] - np.nanmean(Yu[150:])) < 1e-12
    assert [o[:3] for o in R["occ"]] == [[10, 19, 10], [100, 111, 7]]
    d2 = np.concatenate([Yd[100:105], Yd[110:112]]).max()               # VER 24：一段的最大回撤＝段內最慘的一天
    dd = np.concatenate([Yd[10:20], Yd[100:105], Yd[110:112]])
    assert abs(R["occ"][1][5] - d2) < 1e-12 and abs(R["warn"]["mdd"] - np.median(dd)) < 1e-12
    assert abs(R["warn"]["mdd_base"] - np.median(Yd[:-5])) < 1e-12
    assert "mdd" not in G.st_stat(state, samp, Yu, Yw, 20, 150)["warn"]
    cal = [f"d{i:03d}" for i in range(T)]                              # VER 24：最慘一次＋日期（狀態中的每一天裡最大的）
    R2 = G.st_stat(state, samp, Yu, Yw, 20, 150, Yd, cal=cal)
    assert abs(R2["warn"]["mddw"] - dd.max()) < 1e-12 and R2["warn"]["mddw_d"] == "d111"


def test_event_stat_counts_and_recent():
    T = 300
    Yu = np.array([float(i % 2 == 0) for i in range(T)])
    Yw = np.zeros(T)
    Yu[-10:] = np.nan
    Yw[-10:] = np.nan
    samp = np.arange(50, T)
    Yd = np.arange(T) / 1000.0
    R = G.ev_stat([10, 60, 70, 100, 200, 295], Yu, Yw, samp, 20, 150, Yd)   # 10 不在樣本、70 在 60 之後 20 天內、295 窗口不完整
    assert [o[0] for o in R["occ"]] == [60, 100, 200]
    assert abs(R["warn"]["mdd"] - 0.1) < 1e-12 and abs(R["warn"]["mdd_base"] - np.median(Yd[50:])) < 1e-12
    assert R["up"]["n"] == 3 and R["up"]["hit"] == 1.0
    assert R["up"]["n10"] == 1 and R["up"]["hit10"] == 1.0
    assert abs(R["up"]["base"] - np.nanmean(Yu[50:])) < 1e-12


def test_tier_rules():
    """VER 9：★＝過門檻而且打亂測試 p ≤ 1%；●＝過門檻但 p > 1%（可能是運氣）；○ 沒過門檻；— 不到 5 次。
    VER 14：次數 < 15 的門檻放寬到 10%。"""
    st = {"n": 22, "hit": 0.72, "base": 0.60, "n10": 3, "hit10": 0.2, "base10": 0.6, "p": 0.005}
    assert G.tier(st, "up") == "good"                      # 近 10 年不到 5 次：不檢查
    st.update(n10=6)
    assert G.tier(st, "up") == "none"                      # 近 10 年沒過 → 沒過門檻
    st.update(hit10=0.75, base10=0.62)
    assert G.tier(st, "up") == "good"
    assert G.tier({**st, "p": 0.0125}, "up") == "ref"      # 門檻都過、但亂排也做得到 1.25% → 可能是運氣
    assert G.tier({**st, "p": None}, "up") == "ref"        # 沒算打亂測試 → 不能給 ★
    few = {**st, "n": 14}
    assert G.tier({**few, "p": 0.0125}, "up") == "good"     # VER 14：次數少於 15 次，亂排做得到 10% 以內就算
    assert G.tier({**few, "p": 0.10}, "up") == "good" and G.tier({**few, "p": 0.1025}, "up") == "ref"
    assert G.tier({**few, "n": 15, "p": 0.0125}, "up") == "ref"   # 15 次以上照舊 1%
    assert G.tier({**few, "p": None}, "up") == "ref"
    assert G.tier({"n": 12, "hit": 0.58, "base": 0.40, "n10": 0, "p": 0.001}, "up") == "none"     # 命中率不到 60%
    assert G.tier({"n": 12, "hit": 0.52, "base": 0.40, "n10": 0, "p": 0.001}, "warn") == "good"  # 警示門檻 50%
    assert G.tier({"n": 12, "hit": 0.63, "base": 0.60, "n10": 0, "p": 0.001}, "up") == "none"
    assert G.tier({"n": 5, "hit": 1.0, "base": 0.4, "n10": 0, "p": 0.002}, "up") == "good"      # 5 次也可以（VER 9）
    assert G.tier({"n": 4, "hit": 1.0, "base": 0.1, "n10": 0, "p": 0.001}, "up") == "few"


def test_best_direction():
    dirs = {"up": {"tier": "ref", "hit": 0.6, "base": 0.5}, "warn": {"tier": "good", "hit": 0.6, "base": 0.3}}
    assert G.best(dirs) == ("good", ["warn"])
    dirs["up"]["tier"] = "good"
    assert G.best(dirs) == ("good", ["warn", "up"])
    assert G.best({"up": {"tier": "few", "hit": None, "base": None}, "warn": {"tier": "few", "hit": 0.5, "base": 0.4}})[0] == "few"


def test_write_stock_never_writes_partial_data(tmp_path):
    p = tmp_path / "s.json"
    assert G.write_stock({}, {}, p) is False and not p.exists()                    # 沒有個股資料
    assert G.write_stock({"adv": {"trades": {}}}, {"D": object()}, p) is False and not p.exists()


def _tr(r, hd, mk=1.0, st="c"):
    from arm.lab import trades as TR
    row = [None] * len(TR.TR_COLS)
    I = {c: i for i, c in enumerate(TR.TR_COLS)}
    row[I["c"]], row[I["r"]], row[I["hd"]], row[I["mk"]], row[I["st"]] = "2330", r, hd, mk, st
    return row


def test_strat_judge_uses_closed_trades_and_count_floor_10():
    """sigspec VER 2（使用者 2026-10-19：「次數不夠沒關係」）：10 筆以上就判定，不到 30 筆只加註次數少。"""
    good = [_tr(5.0, 20)] * 8 + [_tr(-2.0, 20)] * 4 + [_tr(99.0, 20, st="o")]        # 持有中不算
    J = G.strat_judge({"a": {"res": {"tr": good}}, "b": {"res": {"tr": good[:9]}},
                       "c": {"res": {"tr": [_tr(1.0, 20)] * 5 + [_tr(-1.5, 20)] * 7}}, "d": {"res": {}}})
    assert J["a"]["tier"] == "good" and J["a"]["n"] == 12 and J["a"]["few"] and abs(J["a"]["win"] - 200 / 3) < 1e-9
    assert J["b"]["tier"] == "few" and J["b"]["n"] == 9                       # 不到 10 筆
    assert J["c"]["tier"] == "none" and J["d"]["tier"] == "few" and not J["d"]["few"]
    pay, st = G.strat_pay({"res": {"tr": good}})
    assert st["tier"] == J["a"]["tier"] and st["base"] == 1.0 and pay["path"] == "一般"


def _scen_direct(X, cond, i):
    """逐日直接判斷（sigspec 第 4.10 節），用來對照向量化版本。"""
    if cond in ("many_hi", "many_lo"):
        vals = [X[g][i] for g in S.SCEN_DIMS if not np.isnan(X[g][i])]
        if len(vals) < S.SCEN_MIN_DIMS:
            return False, False
        n = sum(1 for v in vals if (v >= S.SCEN_HI if cond == "many_hi" else v < S.SCEN_LO))
        return True, n >= S.SCEN_MANY
    if any(np.isnan(X[g][i]) for g, _ in cond):
        return False, False
    return True, all((X[g][i] >= S.SCEN_HI) if o == "hi" else (X[g][i] < S.SCEN_LO) for g, o in cond)


def test_scenarios_match_direct_rules_and_tw_liquidity_average():
    rng = np.random.default_rng(7)
    T = 400
    comp = {d: rng.uniform(0, 100, T) for d in ("fund", "chip", "gliq", "tliq", "tech")}
    comp["chip"][:150] = np.nan                                 # 籌碼晚開始（台股 2019-12 起）
    comp["gliq"][:60] = np.nan                                  # 資金要兩個都有值
    comp["fund"][200:205] = [60.0, 59.99, 40.0, 39.99, np.nan]  # 門檻：≥ 60、< 40
    F = {"mk": "tw", "cal": [f"d{i:04d}" for i in range(T)], "comp": comp}
    X = G.scen_series(F)
    assert np.isnan(X["liq"][:60]).all() and np.allclose(X["liq"][60:], (comp["gliq"][60:] + comp["tliq"][60:]) / 2)
    assert np.isnan(X["chip"][:150]).all()
    for key, _, cond, _ in S.SCENARIOS:
        have, on = G.scen_flags(X, cond)
        for i in range(T):
            h, o = _scen_direct(X, cond, i)
            assert (bool(have[i]), bool(on[i])) == (h, o), (key, i)
    sig = {s["var"]: s for s in G.scen_signals(F)}
    assert list(sig) == [k for k, *_ in S.SCENARIOS]
    s5 = sig["SC5"]                                             # 籌碼 × 技術：籌碼有值才是樣本
    assert s5["samp"][0] == 150 and s5["kind"] == "state" and s5["H"] == S.H_SCEN and s5["cat"] == "scen"
    assert s5["id"] == "tw:scen:SC5" and len(s5["state"]) == len(s5["samp"])
    s8 = sig["SC8"]                                             # 多數面向：前 60 天只有基本面、技術 2 個有值 → 不是樣本
    assert s8["samp"][0] == 60


def test_scenarios_us_use_sentiment_and_liquidity():
    T = 10
    comp = {"fund": np.full(T, 70.0), "sent": np.full(T, 65.0), "liq": np.full(T, 30.0), "tech": np.full(T, 20.0)}
    F = {"mk": "spx", "cal": [f"d{i}" for i in range(T)], "comp": comp}
    on = {s["var"]: bool(s["state"].all()) for s in G.scen_signals(F)}
    assert on == {"SC1": False, "SC2": True, "SC3": False, "SC4": False, "SC5": True, "SC6": False, "SC7": True,
                  "SC8": False, "SC9": False}


# ── 訊號觸發後的報酬（sigspec 第 4.11 節，VER 5） ────────────────────────────────

def _wq_direct(v, w, q):
    """直接算：由小到大排，累計權重第一次 ≥ q × 總權重的那一個值。"""
    pairs = sorted(zip(v, w), key=lambda x: x[0])
    tot, acc = sum(w), 0.0
    for x, ww in pairs:
        acc += ww
        if acc >= q * tot - 1e-12:
            return x
    return pairs[-1][0]


def test_weighted_quantile_matches_direct_and_ceil_rule():
    rng = np.random.default_rng(3)
    for _ in range(50):
        n = int(rng.integers(1, 40))
        v, w = rng.normal(size=n), rng.uniform(0.1, 2.0, n)
        for q in (0.1, 0.25, 0.5, 0.75):
            assert G.wquant(v, w, q) == _wq_direct(list(v), list(w), q)
    v = np.array([5.0, 1.0, 3.0, 2.0, 4.0, 6.0])                  # 等權：第 ⌈q·n⌉ 個（不內插）
    assert G.wquant(v, np.ones(6), 0.5) == 3.0 and G.wquant(v, np.ones(6), 0.25) == 2.0 and G.wquant(v, np.ones(6), 0.1) == 1.0


def test_fwd_mae_matches_direct_loop():
    px = _px(300, seed=4)
    px[37] = np.nan
    for H in (1, 5, 20, 60):
        a = G.fwd_mae(px, H)
        r = G.fwd_ret(px, H)
        for t in range(len(px)):
            e = t + S.LAG
            if e + H > len(px) - 1:
                assert np.isnan(a[t])
                continue
            xs = [x for x in px[e + 1:e + H + 1] if not np.isnan(x)]
            if np.isnan(px[e]) or not xs:
                assert np.isnan(a[t])
                continue
            m = min(xs)
            assert abs(a[t] - min(0.0, m / px[e] - 1)) < 1e-12
            if not np.isnan(px[e + H]):
                assert abs(r[t] - (px[e + H] / px[e] - 1)) < 1e-12


def test_ret_stats_state_weights_each_day_equally():
    """狀態型（VER 22）：每一天一樣重；排除極端、去掉最好一次以段為單位、依天數加權；等權的 _ret_flat 和一天一組的 ret_stats 相同。"""
    from arm.lab import robust as RB
    px = _px(500, seed=5)
    RA = G.ret_arrays(px)
    segs = [list(range(10, 13)), list(range(100, 160)), [300]]
    R = G.ret_stats(segs, RA)
    for i, h in enumerate(S.RET_H):
        r, a, w = [], [], []
        n = 0
        for g in segs:
            ok = [t for t in g if np.isfinite(RA["R"][h][t]) and np.isfinite(RA["A"][h][t])]
            if not ok:
                continue
            n += 1
            r += [RA["R"][h][t] for t in ok]
            a += [RA["A"][h][t] for t in ok]
            w += [1.0] * len(ok)
        c = R["s"][i]
        assert c[0] == n
        assert abs(c[1] - sum(x * y for x, y in zip(r, w)) / sum(w)) < 1e-12
        assert c[3] == _wq_direct(r, w, 0.5) and c[7] == _wq_direct(a, w, S.MAE_Q) and c[8] == min(a)
        assert abs(c[5] - sum(y for x, y in zip(r, w) if x > 0) / sum(w)) < 1e-12
        allr = [RA["R"][h][t] for g in segs for t in g if np.isfinite(RA["R"][h][t]) and np.isfinite(RA["A"][h][t])]
        assert abs(c[5] - np.mean([x > 0 for x in allr])) < 1e-12                       # ＝每一天的比例（同命中率）
        segm = [[RA["R"][h][t] for t in g if np.isfinite(RA["R"][h][t]) and np.isfinite(RA["A"][h][t])] for g in segs]
        segm = [x for x in segm if x]
        mm, mw = [float(np.mean(x)) for x in segm], [len(x) for x in segm]
        assert c[9] == RB.trim_mean_w(mm, mw) and c[10] == RB.lbo_mean_w(mm, mw)
    idx = np.array([3, 50, 51, 200, 480])
    F1, F2 = G._ret_flat(idx, RA), G.ret_stats([[int(t)] for t in idx], RA)
    assert F1 == F2


def test_research_returns_agree_with_hit_rates():
    """研究檔：在訊號自己看多久那一期，次數與上漲比例＝原本的次數與命中率，平常＝原本的平常（判定不變的檢查）。"""
    R = G.load_research()
    assert R and R.get("bases")
    n = 0
    for r in R["rows"]:
        if r["cat"] == "ind" or r.get("H") not in S.RET_H:
            continue
        i = S.RET_H.index(r["H"])
        c, b = r["ret"]["s"][i], R["bases"][r["ret"]["bk"]]["s"][i]
        u = r["buy"] if r["cat"] == "buy" else r["up"]                  # VER 10：大跌後買點也看 60 天後上漲、平常＝隨便挑一天
        if not u["n"]:
            continue
        assert c[0] == u["n"] and abs(c[5] - u["hit"]) < 1e-3, r["id"]
        assert abs(b[5] - u["base"]) < 1e-3, r["id"]
        n += 1
    assert n > 1500


def test_stock_and_industry_returns():
    c = [10.0, 10.5, 9.5, 11.0, 9.0, None, 12.0, 12.0, 12.0, 12.0, 13.0, 12.5]
    Sx = {"o": [None, 10.0] + [None] * 10, "c": c}
    r = G._stock_ret(Sx, 0)                                             # 第 1 天開盤 10 進場、第 h 天收盤
    assert set(r) == {1, 10}                                            # 第 5 天停牌沒有收盤；20 天超過資料
    assert abs(r[1][0] - 0.05) < 1e-12 and r[1][1] == 0.0
    assert abs(r[10][0] - 0.30) < 1e-12 and abs(r[10][1] - (9.0 / 10 - 1)) < 1e-12
    Sx2 = {"o": [None] * 12, "c": c}                                    # 沒有開盤價就用收盤
    assert abs(G._stock_ret(Sx2, 0)[1][0]) < 1e-12
    me = {"2026-01": 100.0, "2026-02": 90.0, "2026-03": 110.0, "2026-04": 120.0}
    x = G._me_ret(me, "2026-01")
    assert set(x) == {1, 3, "_d"} and abs(x[1][0] + 0.10) < 1e-12 and abs(x[3][0] - 0.20) < 1e-12 and abs(x[3][1] + 0.10) < 1e-12
    # VER 24：最大跌幅＝期間最高收盤到之後最低收盤（含進場價當起點），最慘一次的日期＝樣本的 "_d"
    assert x["_d"] == "2026-01" and G._me_ret(me, "2026-01", "XLK")["_d"] == "2026-01 XLK"
    assert abs(x[1][2] - 0.10) < 1e-12 and abs(x[3][2] - 0.10) < 1e-12
    assert r[1][2] == 0.0 and abs(r[10][2] - (1 - 9.0 / 11.0)) < 1e-12                  # 10→10.5→9.5→11→9：從 11 跌到 9
    assert G._stock_ret(Sx, 0, "2026-01-02 2330")["_d"] == "2026-01-02 2330"
    cell = G._ret_groups([[r | {"_d": "a"}], [G._stock_ret(Sx2, 0, "b")]], (10,))["s"][0]
    assert abs(cell[11] - (1 - 9.0 / 11.0)) < 1e-12 and cell[12] in ("a", "b")


# ── 法人買賣超（sigspec 第 4.13 節；VER 7 起只當訊號） ──────────────────────────

def test_inst_amounts_and_ratio():
    from arm.lab import heatcalc as HC
    inst = {"2014-11-28": {"Dealer": -5, "Foreign_Investor": 10, "Investment_Trust": 2, "total": 7},
            "2014-12-01": {"Dealer_Hedging": -3, "Dealer_self": 4, "Foreign_Investor": 6, "Investment_Trust": -1, "total": 6},
            "2018-01-02": {"Dealer_Hedging": 1, "Dealer_self": -2, "Foreign_Dealer_Self": 5, "Foreign_Investor": -8,
                           "Investment_Trust": 3, "total": -1}}
    A = HC.inst_amounts(inst)
    assert A["tot"] == {"2014-11-28": 7, "2014-12-01": 6, "2018-01-02": -1}
    assert A["fi"] == {"2014-11-28": 10, "2014-12-01": 6, "2018-01-02": -3}          # 外資＝外資＋外資自營商（同 L3）
    assert A["it"]["2018-01-02"] == 3 and A["dl"] == {"2014-12-01": 4, "2018-01-02": -2}   # 自營商自行買賣 2014-12 起
    cal = ["2014-11-28", "2014-12-01", "2018-01-02"]
    D = {"inst": inst, "turnover": {d: [100.0, 0] for d in cal}}
    assert HC.inst_ratio(cal, D, "fi", 1) == {"2014-11-28": 10.0, "2014-12-01": 6.0, "2018-01-02": -3.0}
    r2 = HC.inst_ratio(cal, D, "tot", 2)
    assert r2 == {"2014-12-01": 6.5, "2018-01-02": 2.5}                            # 2 日合計 ÷ 2 日成交金額（%）


def test_run_days_and_cold_exits_direct():
    amt = np.array([1, 2, 3, 4, 5, 6, np.nan, 1, 1, 1, 1, 1, -1, -2, 0, -1, -1, -1, -1, -1], dtype=float)
    assert G.run_days(amt, 1, 5) == [4, 11] and G.run_days(amt, -1, 5) == [19] and G.run_days(amt, -1, 2) == [13, 16]
    rng = np.random.default_rng(7)
    x = [None if rng.random() < 0.05 else float(rng.choice([5, 15, 30, 50]) if rng.random() < 0.7 else rng.uniform(0, 100))
         for _ in range(600)]
    we = list(range(4, 600, 5))
    got = G.cold_exits(x, we, 4)
    out, run = [], 0                                                    # 直接算：連續 ≥ 4 個週末 < 20，之後第一個 ≥ 20
    for i in we:
        if x[i] is not None and x[i] < 20:
            run += 1
            continue
        if x[i] is not None and run >= 4:
            out.append(i)
        run = 0
    assert got == out
    from arm.lab import hotdd as HDD                                    # 鏡像：把 0～100 反過來，就是大賣超結束的規則
    flip = [None if v is None else 100 - v for v in x]                 # （沒有剛好等於 20 的值，兩條界線一致）
    assert HDD.exits(flip, we, 4) == got


def test_research_has_inst_rows_and_no_duplicate_heat_rows():
    R = G.load_research()
    rows = [r for r in R["rows"] if r["cat"] == "inst"]
    assert len(rows) == 90 and len({r["id"] for r in rows}) == 90
    assert not [r for r in R["rows"] if r["cat"] == "heat" and r["var"] in ("C9", "C10", "C11", "C12", "C13", "C14")]
    for r in rows:
        assert r["mk"] == "tw" and r["grp"] in S.INST_WHO
        sig = r["sig"]
        if sig.endswith(("run5", "run10")):
            assert r["H"] == S.INST_H["run"] and r["var"].endswith("1")
        else:
            w = int(r["var"][len(r["grp"]):])
            assert r["H"] == S.INST_H[w] and (r["grp"], w) not in S.INST_SKIP


# ── 溫度計跨期間（sigspec 第 5 節 ③a，VER 15） ─────────────────────────────────────

def _cross_direct(px, days, samp, state, kind, H, th):
    """直接算：成功條件同第 2 節（第 e＋H 天收盤 > 第 e 天；第 e～e＋H 天最大回撤 ≥ th）；事件型同一次觀察期間內再出現不算；
    狀態型一段＝連續在狀態中（中斷 < EP_GAP 個樣本），命中率＝每一天一樣重（VER 22）；平常＝樣本日的平均（窗口不完整的不算）。"""
    T = len(px)

    def out(t):
        e = t + S.LAG
        if e + H >= T:
            return None
        return float(px[e + H] > px[e]), float(_mdd(list(px[e:e + H + 1])) >= th)
    ok = [t for t in samp if out(t) is not None]
    base = [np.mean([out(t)[j] for t in ok]) for j in (0, 1)]
    if kind == "event":
        kept, last = [], None
        for t in days:
            if t in set(samp) and (last is None or t - last >= H):
                kept.append(t)
                last = t
        ys = [out(t) for t in kept if out(t) is not None]
        hit = [np.mean([y[j] for y in ys]) if ys else None for j in (0, 1)]
        n = len(ys)
    else:
        segs, cur, gap = [], [], 0
        for i, t in enumerate(samp):
            if state[i]:
                if cur and gap >= S.EP_GAP:
                    segs.append(cur)
                    cur = []
                cur.append(t)
                gap = 0
            elif cur:
                gap += 1
        if cur:
            segs.append(cur)
        alld, n = [], 0
        for sg in segs:
            ys = [out(t) for t in sg if out(t) is not None]
            if ys:
                n += 1
                alld += ys
        hit = [np.mean([y[j] for y in alld]) if alld else None for j in (0, 1)]
    return {"up": (n, hit[0], base[0]), "warn": (n, hit[1], base[1])}


def test_cross_stats_match_direct_and_skip_native_horizon():
    px = _px(700, seed=7)
    cal = [f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(px))]
    F = {"mk": "tw", "cal": cal, "px": px, "r0": cal[400]}
    rng = np.random.default_rng(3)
    samp = np.arange(30, len(px))
    st = rng.random(len(samp)) < 0.15
    ev = sorted(set(int(t) for t in rng.integers(30, len(px), 40)))
    sds = [{"id": "tw:tech:e", "cat": "tech", "kind": "event", "H": 20, "samp": samp, "days": ev},
           {"id": "tw:heat:s", "cat": "heat", "kind": "state", "H": 60, "samp": samp, "state": st}]
    for sd in sds:
        X = G.cross_stats(F, sd, {})
        assert set(X) == {k for k, H in S.THERMO_H.items() if H != sd["H"]}         # 原本那個看多久不重複存
        for k, x in X.items():
            H = S.THERMO_H[k]
            assert x["H"] == H and x["th"] == G.warn_th("tw", H)
            want = _cross_direct(px, ev, samp, st, sd["kind"], H, x["th"])
            for d in ("up", "warn"):
                n, hit, base = want[d]
                assert x[d]["n"] == n, (sd["id"], k, d)
                assert (x[d]["hit"] is None and hit is None) or abs(x[d]["hit"] - hit) < 1e-12
                assert abs(x[d]["base"] - base) < 1e-12
            if sd["kind"] == "event":                   # VER 24：同一批次數的報酬格（上漲比例、最大跌幅最慘一次和統計一致）
                c = x["c"]
                assert c[0] == x["up"]["n"] and abs(c[5] - x["up"]["hit"]) < 1e-3
                if x["warn"].get("mddw") is not None:
                    assert abs(c[11] - x["warn"]["mddw"]) < 1e-9 and c[12] == x["warn"]["mddw_d"]
            else:
                assert "c" not in x
    assert G.cross_stats(F, dict(sds[0], cat="buy"), {}) == {} and G.cross_stats(F, dict(sds[0], cat="ind"), {}) == {}


def test_now_market_cross_horizon_activity(monkeypatch):
    """現在有效（第 5 節 ③a）：事件型在最後 THERMO_H[k] 個交易日內出現就算那支溫度計有效；狀態型同原本。
    出現的日子：事件型每一次出現那天起 THERMO_H[k] 個交易日（acts 的鍵 xkey）；狀態型和原本同一份。"""
    T = 400
    cal = [f"d{i:03d}" for i in range(T)]
    samp = np.arange(T)
    state = np.zeros(T, dtype=bool)
    state[-30:] = True
    sds = [{"id": "e", "cat": "tech", "kind": "event", "H": 20, "samp": samp, "days": [100, T - 1 - 30]},
           {"id": "s", "cat": "heat", "kind": "state", "H": 60, "samp": samp, "state": state},
           {"id": "old", "cat": "tech", "kind": "event", "H": 20, "samp": samp, "days": [T - 1 - 300]}]
    monkeypatch.setattr(G, "signals", lambda F: sds)
    acts, xon = {}, {}
    on = G.now_market({"cal": cal}, acts, xon)
    assert set(on) == {"s"}                                                     # 事件 e 已過 30 天 > 20
    cur = {"since": cal[T - 31], "n": 30, "k": 30, "st": "-", "ck": "4-"}         # VER 26：第幾天、條件（沒有條件＝"-"）、今天那一格
    assert xon["e"] == {"mid": {**cur, "left": 30}, "long": {**cur, "left": 220}}
    assert set(xon["s"]) == {"short", "long"} and xon["s"]["long"] == on["s"]
    assert "old" not in xon                                                     # 300 天前：12 個月（250 天）也過了
    a = acts[G.xkey("e", "long")]
    assert a[100:350].all() and not a[350:T - 31].any() and a[T - 31:].all()
    assert acts[G.xkey("s", "short")] is acts["s"] and "e" not in acts
    assert G.now_market({"cal": cal}) == on                                    # 沒給 xon：同 VER 14


def test_research_cross_stats_agree_with_returns_table():
    """研究檔（VER 15）：市場層級訊號都有另外兩支溫度計的統計 xh；狀態型的段數、上漲比例、平常要和報酬表（ret，另一套程式算的）
    在那個看多久那一期相同（事件型去重用的看多久不同，次數本來就不同，不比）。原本的欄位不變由 test_research_returns_agree_with_hit_rates 守。"""
    R = G.load_research()
    rows = [r for r in R["rows"] if r["cat"] in S.THERMO_X_CATS]
    assert rows and all(set(r["xh"]) == {k for k, H in S.THERMO_H.items() if H != r["H"]} for r in rows)
    assert not [r for r in R["rows"] if r["cat"] not in S.THERMO_X_CATS and r.get("xh")]
    n = 0
    for r in rows:
        if r["kind"] != "state":
            continue
        for k, x in r["xh"].items():
            i = S.RET_H.index(x["H"])
            c, b = r["ret"]["s"][i], R["bases"][r["ret"]["bk"]]["s"][i]
            if not x["up"]["n"]:
                continue
            assert c[0] == x["up"]["n"] and abs(c[5] - x["up"]["hit"]) < 1e-3, (r["id"], k)
            assert abs(b[5] - x["up"]["base"]) < 1e-3, (r["id"], k)
            assert "c" not in x                                                 # 狀態型的段不隨看多久改變：用自己那一格
            if x["warn"].get("mddw") is not None:
                assert abs(c[11] - x["warn"]["mddw"]) < 1e-9 and c[12] == x["warn"]["mddw_d"], (r["id"], k)
            n += 1
    assert n > 1500
    m = 0
    for r in rows:                     # 事件型（VER 24）：xh 自帶那個看多久、同一批次數的報酬格，和上面那一行的統計一致
        if r["kind"] != "event":
            continue
        for k, x in r["xh"].items():
            c = x.get("c")
            if not x["up"]["n"]:
                continue
            assert c and c[0] == x["up"]["n"] and abs(c[5] - x["up"]["hit"]) < 1e-3, (r["id"], k)
            if x["warn"].get("mddw") is not None:
                assert abs(c[11] - x["warn"]["mddw"]) < 1e-9 and c[12] == x["warn"]["mddw_d"], (r["id"], k)
            m += 1
    assert m > 1000
