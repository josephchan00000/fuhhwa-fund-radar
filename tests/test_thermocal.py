"""溫度計「過去讀數這樣的時候」（arm/lab/thermocal.py；sigspec 第 5 節 ③d，VER 16）：和直接算的版本比對。"""
from datetime import date, timedelta

import numpy as np

from arm.lab import sigcat as G
from arm.lab import sigspec as S
from arm.lab import thermocal as TC


def _cal(T, start=date(2000, 1, 3)):
    out, d = [], start
    while len(out) < T:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _px(T, seed=5):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, T)))


def test_active_matches_now_market_rules():
    """現在有效（第 5 節 ③a）：狀態型＝樣本日在狀態中；月資料到下一個月底；事件型＝出現後 H 個交易日（樣本開始以前的不算）。"""
    T = 100
    samp = np.arange(10, T)
    st = np.zeros(len(samp), dtype=bool)
    st[[0, 1, 50]] = True
    a = TC.active({"kind": "state", "samp": samp, "state": st}, T, 20)
    assert list(np.nonzero(a)[0]) == [10, 11, 60]
    ms = np.array([20, 40, 60])
    am = TC.active({"kind": "state", "monthly": True, "samp": ms, "state": np.array([True, False, True])}, T, 250)
    assert list(np.nonzero(am)[0]) == list(range(20, 40)) + list(range(60, T))
    ae = TC.active({"kind": "event", "samp": samp, "days": [5, 30, 95]}, T, 20)
    assert list(np.nonzero(ae)[0]) == list(range(30, 50)) + list(range(95, T))


def test_stats_before_uses_only_windows_finished_before_cut():
    """cut 之前走完的窗口才算（t＋LAG＋H < cut），和把資料截到 cut 再算一模一樣；樣本日不夠 CAL_MIN_SAMP 不投票。"""
    T, H = 600, 20
    px = _px(T)
    Y = G.outcomes(px, H, G.warn_th("tw", H))
    samp = np.arange(30, T)
    rng = np.random.default_rng(1)
    st = rng.random(len(samp)) < 0.2
    days = sorted(set(int(x) for x in rng.integers(30, T, 30)))
    cut = 400
    for sd in ({"kind": "state", "samp": samp, "state": st}, {"kind": "event", "samp": samp, "days": days}):
        R = TC.stats_before(sd, cut, Y, H)
        Yc = G.outcomes(px[:cut], H, G.warn_th("tw", H))                 # 只有 cut 以前的收盤：之後的窗口自然不完整
        m = samp < cut
        if sd["kind"] == "event":
            R2 = G.ev_stat([t for t in days if t < cut], Yc[0], Yc[1], samp[m], H, 0)
        else:
            R2 = G.st_stat(st[m], samp[m], Yc[0], Yc[1], S.EP_GAP, 0)
        for d in ("up", "warn"):
            assert R[d]["n"] == R2[d]["n"] and R[d]["hit"] == R2[d]["hit"] and abs(R[d]["base"] - R2[d]["base"]) < 1e-12
    few = {"kind": "state", "samp": np.arange(T - 60, T), "state": np.ones(60, dtype=bool)}
    assert TC.stats_before(few, T - 30, Y, H) is None


def test_vote_rule_is_listing_rule():
    """VER 23：票＝第 5 節 ④b 列出來的規則——次數 ≥ 5、這個方向命中率比平常高 5 點以上（偏多方向 → u、警示方向 → w）；
    偏弱拿掉（上漲機率比平常低不投警示）；跨期間與訊號自己的看多久同一條。"""
    st = lambda n, hit, base: {"n": n, "hit": hit, "base": base}
    assert TC.vote({"up": st(20, 0.71, 0.65), "warn": st(20, 0.36, 0.30)}) == "uw"                # 差 6 點
    assert TC.vote({"up": st(20, 0.69, 0.65), "warn": st(20, 0.34, 0.30)}) == ""                  # 差 4 點
    assert TC.vote({"up": st(20, 0.50, 0.60), "warn": st(20, 0.30, 0.30)}) == ""                  # 偏弱不投（VER 23）
    assert TC.vote({"up": st(4, 0.90, 0.60), "warn": st(4, 0.9, 0.3)}) == ""                     # 次數 4
    assert TC.vote({"up": st(5, 0.70, 0.60), "warn": {}}) == "u"                                   # 次數 5 就算
    assert TC.vote({"up": st(20, None, 0.6), "warn": st(20, 0.45, 0.30)}) == "w"
    assert TC.vote(None) == ""
    for d, x in (("up", st(20, 0.70, 0.65)), ("warn", st(20, 0.40, 0.30)), ("up", st(20, 0.50, 0.60)), ("warn", st(9, 0.349, 0.30))):
        cls = G.list_cls(d, x["hit"] - x["base"])
        assert (TC.vote({"up": x, "warn": {}} if d == "up" else {"up": {}, "warn": x}) != "") == (cls is not None)


def test_rank_and_group_compare_with_own_past():
    counts = list(range(300)) + [150, 150]
    rk = TC.rank(counts)
    assert rk[:S.CAL_RANK_MIN] == [None] * S.CAL_RANK_MIN
    lt, mid = rk[300]
    prior = np.asarray(counts[300 - S.CAL_RANK_W if 300 > S.CAL_RANK_W else 0:300])
    assert lt == (prior < 150).mean() and abs(mid - ((prior < 150).sum() + 0.5) / len(prior)) < 1e-12
    assert rk[260][0] == 1.0 and TC.group(1.0) == "hi" and TC.group(0.2) == "lo" and TC.group(0.5) == "mid"
    assert TC.group(1 / 3) == "lo" and TC.group(2 / 3) == "hi"
    long = [7] * 700
    assert all(r == (0.0, 0.5) for r in TC.rank(long)[S.CAL_RANK_MIN:])     # 全部一樣多＝中間那組


def test_verdict_bootstrap_is_deterministic_and_reads_direction():
    rng = np.random.default_rng(3)
    n = 900
    gs = list(rng.choice(TC.GROUPS, size=n))
    y_rel = [float(rng.random() < (0.6 if g == "hi" else 0.2 if g == "lo" else 0.4)) for g in gs]
    y_rev = [1.0 - y for y in y_rel]
    y_none = [float(rng.random() < 0.4) for _ in gs]
    v1, v1b = TC.verdict(gs, y_rel), TC.verdict(gs, y_rel)
    assert v1 == v1b and v1["v"] == "rel" and v1["ci"][0] > 0                # 同一份資料同一個結果（固定種子）
    assert TC.verdict(gs, y_rev)["v"] == "rev" and TC.verdict(gs, y_none)["v"] == "none"
    hi = [i for i, g in enumerate(gs) if g == "hi"]
    assert abs(v1["g"]["hi"][0] - np.mean([y_rel[i] for i in hi])) < 1e-12 and v1["g"]["hi"][1] == len(hi)
    assert abs(v1["d"] - (v1["g"]["hi"][0] - v1["g"]["lo"][0])) < 1e-12 and v1["all"] == [float(np.mean(y_rel)), n]
    few = TC.verdict(["hi"] * 50 + ["lo"] * 200, [1.0] * 250)
    assert few["v"] == "few" and few["ci"] is None


def test_market_counts_items_with_yearly_rolling_votes(monkeypatch):
    """逐年滾動：每年 1 月 1 日用之前走完的窗口重算統計、照 ④b 的規則（VER 23）決定會投哪一邊；同一個項目一票；
    週末的票數＝有效而且會投的項目數；今天的票數用最後一年那一次的統計（votes）。"""
    T = 260 * 14
    cal = _cal(T)
    px = _px(T, seed=11)
    we = [i for i in range(T) if i == T - 1 or date.fromisoformat(cal[i + 1]).isocalendar()[1] != date.fromisoformat(cal[i]).isocalendar()[1]]
    samp = np.arange(T)
    rng = np.random.default_rng(2)
    sds = []
    for j in range(6):
        st = np.zeros(T, dtype=bool)
        for s0 in rng.integers(0, T - 40, 25):
            st[s0:s0 + 30] = True
        sds.append({"id": f"tw:heat:V{j % 3}:s{j}", "cat": "heat", "var": f"V{j % 3}", "kind": "state", "H": 60,
                    "samp": samp, "state": st})
    sds.append({"id": "tw:tech:e", "cat": "tech", "var": "e", "kind": "event", "H": 20, "samp": samp,
                "days": sorted(set(int(x) for x in rng.integers(0, T, 80)))})
    sds.append({"id": "tw:buy:x", "cat": "buy", "var": "x", "kind": "event", "H": 60, "samp": samp, "days": [100]})   # 不算
    monkeypatch.setattr(G, "signals", lambda F: sds)
    F = {"mk": "tw", "cal": cal, "px": px, "we": we, "r0": cal[0]}
    M = TC.market(F)
    assert M["y0"] == TC.first_year(cal) == 2011 and M["cut"] == f"{cal[-1][:4]}-01-01"
    # 直接算某一年某一週的票數
    k, H = "mid", 60
    Y = G.outcomes(px, H, G.warn_th("tw", H))
    yr = 2012
    cut = next(i for i, d in enumerate(cal) if d >= f"{yr}-01-01")
    want_w = []
    wk = [t for t in we if cal[t][:4] == str(yr)]
    for t in wk:
        items = set()
        for sd in sds[:-1]:
            v = TC.vote(TC.stats_before(sd, cut, Y, H))
            if "w" in v and TC.active(sd, T, H)[t]:
                items.add(TC.item_of(sd))
        want_w.append(len(items))
    i0 = sum(1 for t in we if cal[t][:4] < str(yr) and cal[t][:4] >= str(M["y0"]))
    assert len(M["hz"][k]["wk"]) == len(M["hz"][k]["w"]) <= S.CAL_RANK_W + 1
    full = TC.market(F)                                                        # 同資料同結果
    assert full == M
    # 從頭重建一次歷史（不截尾）來比對那一年
    hist = []
    for y in range(M["y0"], int(cal[-1][:4]) + 1):
        c = next(i for i, d in enumerate(cal) if d >= f"{y}-01-01")
        for t in [t for t in we if cal[t][:4] == str(y)]:
            its = {TC.item_of(sd) for sd in sds[:-1]
                   if "w" in TC.vote(TC.stats_before(sd, c, Y, H)) and TC.active(sd, T, H)[t]}
            hist.append(len(its))
    assert hist[i0:i0 + len(wk)] == want_w and M["hz"][k]["w"] == hist[-(S.CAL_RANK_W + 1):]
    assert "tw:buy:x" not in M["votes"] and set(M["votes"]) <= {sd["id"] for sd in sds[:-1]}
    for sid, x in M["votes"].items():
        sd = next(s for s in sds if s["id"] == sid)
        assert x["i"] == TC.item_of(sd)
        for kk, v in x["v"].items():
            Hk = S.THERMO_H[kk]
            assert v == TC.vote(TC.stats_before(sd, cut_last(cal), G.outcomes(px, Hk, G.warn_th("tw", Hk)), Hk))


def cut_last(cal):
    return next(i for i, d in enumerate(cal) if d >= f"{cal[-1][:4]}-01-01")


def test_now_counts_active_votes_and_ranks_against_research(monkeypatch, tmp_path):
    """今天的票數＝研究檔 votes 裡、現在在那支溫度計有效（原本那個看多久看 on、其他看 xon）的項目數；位置和研究檔最後的週末比。"""
    R = {"ver": S.CAL_VER, "mk": {"tw": {
        "votes": {"tw:heat:A:hot": {"i": "item:A", "v": {"mid": "w", "long": "uw"}},
                  "tw:deriv:A:1": {"i": "item:A", "v": {"mid": "w"}},
                  "tw:tech:e": {"i": "tech:e", "v": {"mid": "w", "short": "u"}}},
        "hz": {k: {"H": H, "th": 0.1, "wk": [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(300)],
                   "u": [0] * 150 + [1] * 150, "w": [i % 3 for i in range(300)],
                   "up": {"g": {"lo": [0.5, 200], "mid": [0.6, 100], "hi": [0.7, 200]}, "all": [0.6, 500], "d": 0.2, "ci": [0.1, 0.3], "v": "rel"},
                   "warn": {"g": {"lo": [0.2, 200], "mid": [0.3, 100], "hi": [0.25, 200]}, "all": [0.25, 500], "d": 0.05, "ci": [-0.1, 0.2], "v": "none"}}
               for k, H in S.THERMO_H.items()}}}}
    p = tmp_path / "t.json"
    TC.save(R, p)
    TC._CACHE.clear()
    monkeypatch.setattr(TC, "OUT", p)
    rows = [{"id": "tw:heat:A:hot", "H": 60}, {"id": "tw:deriv:A:1", "H": 60}, {"id": "tw:tech:e", "H": 20}]
    monkeypatch.setattr(G, "research_rows", lambda: rows)
    on = {"tw:heat:A:hot": {}, "tw:deriv:A:1": {}}                             # 兩個是同一個項目 A
    xon = {"tw:tech:e": {"mid": {}}, "tw:heat:A:hot": {"long": {}}}
    c = TC.counts_now(R["mk"]["tw"], on, xon)
    assert c == {"short": {"u": 0, "w": 0}, "mid": {"u": 0, "w": 2}, "long": {"u": 1, "w": 1}}
    N = TC.now("tw", on, xon, "2026-12-31")
    w = N["mid"]["warn"]
    prior = np.asarray([i % 3 for i in range(300)], dtype=float)
    assert w["n"] == 2 and abs(w["pct"] - (prior < 2).mean()) < 1e-12 and w["grp"] == "hi" and w["v"] == "none"
    u = N["long"]["up"]
    assert u["n"] == 1 and u["pct"] == 0.5 and u["grp"] == "hi" and u["rate"] == 0.7 and u["all"] == 0.6 and u["v"] == "rel"
    assert TC.now("spx", on, xon, None) is None
    TC._CACHE.clear()


BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價", "零風險", "無風險")


def test_calibration_lines_text():
    """頁面一行（heatviz.cal_line）：位置＋有關係才寫同一組之後的比例（附對照組）；相反、看不出、週數不夠各一句。"""
    import re
    from arm.lab import heatviz as VZ
    plain = lambda h: re.sub(r"<[^>]+>", "", h)
    base = {"n": 8, "pct": 0.84, "grp": "hi", "rate": 0.25, "hi": 0.25, "lo": 0.11, "all": 0.18}
    w = plain(VZ.cal_line("warn", dict(base, v="rel"), 20, 0.057))
    assert w == "警示比過去 10 年 84% 的週多・過去警示一樣多的週，之後 1 個月內大回撤 5.7% 以上 25%（少的週 11%）"
    u = plain(VZ.cal_line("up", dict(base, v="none", pct=0.06, grp="lo"), 20, 0.057))
    assert u == "偏多比過去 10 年 6% 的週多・過去看不出和之後漲不漲有關係"
    m = plain(VZ.cal_line("warn", dict(base, v="rel", grp="mid", pct=0.52, rate=0.14, hi=0.24, lo=0.08), 250, 0.2))
    assert m.endswith("過去警示數量也在中間的週，之後 12 個月內大回撤 20% 以上 14%（多的週 24%、少的週 8%）")
    r = plain(VZ.cal_line("up", dict(base, v="rev", pct=1.0), 60, 0.1))
    assert r == "偏多比過去 10 年所有的週都多・過去偏多越多、之後上漲反而越少（多的週 25%、少的週 11%）"
    f = plain(VZ.cal_line("warn", dict(base, v="few", pct=0.0), 250, 0.2))
    assert f == "警示過去 10 年最少（或一樣少）・過去的週數不夠，看不出和之後大回撤有沒有關係"
    C = {"H": 20, "th": 0.057, "up": dict(base, v="none"), "warn": dict(base, v="rel")}
    h = VZ.cal_block({"short": C})                         # 只列有關係、相反的；其他不寫（2026-10-23，docs/lab_ia_v5_plan.md 第 3 節②）
    assert h.count('class="tzca"') == 1 and "短線" in plain(h) and "看不出" not in plain(h) and "其他" not in plain(h)
    assert VZ.cal_block(None) == "" and not [x for x in BANNED if x in plain(h)]
    assert VZ.cal_block({"short": dict(C, warn=dict(base, v="few"))}) == ""          # 一個都沒有＝整塊不出現
    T = {"thermo": [{"k": "short", "name": "短線", "h": "看 1 個月", "H": 20, "n": {"up": 1, "warn": 0}, "share": 1.0, "lean": "up",
                     "up": [], "warn": []}], "cal": {"short": C}}
    assert VZ.today_core(T, "tw", None).count('class="tzca"') == 1 and VZ.today_core(dict(T, cal=None), "tw", None).count("tzca") == 0
    assert VZ.today_core(T, "tw", None, cal=False).count("tzca") == 0                     # 訊號總覽不放


def test_research_file_covers_markets_and_is_this_year():
    """研究檔（scripts/run_thermo.py）：五個市場、三支溫度計；投票的訊號都在訊號研究檔裡；
    今天的票數用今年 1 月 1 日那一次的統計——跨年了還沒重跑就紅（重跑 TZ=Asia/Taipei python3 scripts/run_thermo.py）。"""
    from arm import clock
    R = TC.load()
    assert R and R["ver"] >= S.CAL_VER and set(R["mk"]) == set(S.MARKETS)
    ids = {r["id"] for r in G.research_rows()}
    for mk, M in R["mk"].items():
        assert M["cut"] == f"{clock.today_tw().year}-01-01", "跨年了：重跑 scripts/run_thermo.py"
        assert set(M["hz"]) == set(S.THERMO_H) and M["votes"] and set(M["votes"]) <= ids
        for k, h in M["hz"].items():
            assert h["H"] == S.THERMO_H[k] and len(h["wk"]) == len(h["u"]) == len(h["w"]) == S.CAL_RANK_W + 1
            for side in ("up", "warn"):
                V = h[side]
                assert V["v"] in ("rel", "rev", "none", "few") and set(V["g"]) == set(TC.GROUPS)
                assert sum(V["g"][g][1] for g in TC.GROUPS) == V["all"][1]
