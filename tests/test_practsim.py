"""實戰模擬（arm/lab/practsim.py；規格 practspec VER 1）：和逐筆直接算的版本比對。"""
import bisect
import math
from datetime import date, timedelta

import numpy as np
import pytest

from arm.lab import practsim as P
from arm.lab import practspec as S
from arm.lab import sigspec as SS
from arm.lab import xstrat as XT
from arm.lab import xstratspec as XS


def _cal(n: int, start: str = "2000-01-03") -> list[str]:
    out, d = [], date.fromisoformat(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _direct(cal, px, p, c, a, b):
    """逐日直接算：淨值、年化、最大回撤、夏普、平均部位、一年調整幾次。"""
    nav, navs, rets = 1.0, [1.0], []
    for k in range(a + 1, b):
        r = px[k] / px[k - 1] - 1.0
        x = (1.0 + p[k - 1] * r) * (1.0 - c * abs(p[k] - p[k - 1])) - 1.0
        nav *= 1.0 + x
        navs.append(nav)
        rets.append(x)
    yrs = (date.fromisoformat(cal[b - 1]) - date.fromisoformat(cal[a])).days / 365.25
    pk, mdd = navs[0], 0.0
    for v in navs:
        pk = max(pk, v)
        mdd = max(mdd, 1.0 - v / pk)
    rs = np.array(rets)
    w = p[a:b - 1]
    adj = sum(1 for k in range(a + 1, b - 1) if p[k] != p[k - 1])
    return {"cagr": nav ** (1 / yrs) - 1, "mdd": mdd, "sharpe": rs.mean() / rs.std(ddof=1) * math.sqrt(252),
            "w": float(np.mean(w)), "adj": adj / yrs, "nav": navs}


def test_compare_matches_direct():
    rng = np.random.default_rng(1)
    n = 900
    cal = _cal(n)
    px = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, n))
    p = rng.choice([0.0, 0.5, 1.0], size=n)
    c = 0.001
    a, b = 37, n
    r = P.daily_ret(px)
    got = P.compare(cal, r, p, P.turn_cost(p, c), a, b)
    want = _direct(cal, px, p, c, a, b)
    for k in ("cagr", "mdd", "sharpe", "w", "adj"):
        assert got["rule"][k] == pytest.approx(want[k], rel=1e-9, abs=1e-12), k
    wbar = float(np.mean(p[a:b - 1]))
    fix = _direct(cal, px, np.full(n, wbar), 0.0, a, b)
    assert got["fix"]["cagr"] == pytest.approx(fix["cagr"]) and got["fix"]["mdd"] == pytest.approx(fix["mdd"])
    assert got["fix"]["sharpe"] == pytest.approx(got["bh"]["sharpe"])        # 空手報酬 0：部位大小不影響夏普
    bh = _direct(cal, px, np.ones(n), 0.0, a, b)
    assert got["bh"]["cagr"] == pytest.approx(bh["cagr"]) and got["wbar"] == pytest.approx(wbar)
    nav = want["nav"]
    ends = {}
    for i in range(a, b):
        ends[cal[i][:4]] = i - a
    ys = sorted(ends)
    want_y = [[y1, nav[ends[y1]] / nav[ends[y0]] - 1] for y0, y1 in zip(ys, ys[1:]) if y1 != cal[-1][:4]]
    assert [y for y, _ in got["rule"]["yearly"]] == [y for y, _ in want_y]
    for (_, g), (_, w) in zip(got["rule"]["yearly"], want_y):
        assert g == pytest.approx(w)


def test_yearly_skips_partial_last_year_of_a_window():
    cal = _cal(800)
    px = np.linspace(100, 180, 800)
    r = P.daily_ret(px)
    b = next(i for i in range(1, 800) if cal[i][:4] == "2002") + 30          # 半段結束在 2002 年中
    st = P.stats(cal, r[1:b], 0, b)
    assert [y for y, _ in st["yearly"]] == ["2001"]


def test_verdict_rules():
    def x(rs, fs, rm=0.3, fm=0.4):
        return {"rule": {"sharpe": rs, "mdd": rm}, "fix": {"sharpe": fs, "mdd": fm}}
    assert P.verdict(x(0.6, 0.5), x(0.7, 0.6), x(0.5, 0.4)) == "better"
    assert P.verdict(x(0.6, 0.5, rm=0.5), x(0.7, 0.6), x(0.5, 0.4)) == "same"            # 回撤比固定持有大
    assert P.verdict(x(0.6, 0.5), x(0.7, 0.6), x(0.3, 0.4)) == "same"                    # 後半沒有比較好
    assert P.verdict(x(0.4, 0.5), x(0.5, 0.6), x(0.3, 0.4)) == "worse"
    assert P.verdict(x(0.4, 0.5), x(0.7, 0.6), x(0.3, 0.4)) == "same"


def _rank_direct(c, j):
    prior = c[max(0, j - SS.CAL_RANK_W):j]
    if len(prior) < SS.CAL_RANK_MIN:
        return None
    lt = sum(1 for x in prior if x < c[j])
    eq = sum(1 for x in prior if x == c[j])
    return (lt + 0.5 * eq) / len(prior)


def test_thermo_positions_match_direct():
    rng = np.random.default_rng(7)
    nw = 420
    t = [4 + 5 * j for j in range(nw)]
    T = t[-1] + 3
    hist = {k: {"t": list(t), "u": [int(x) for x in rng.poisson(4, nw)], "w": [int(x) for x in rng.poisson(3, nw)]}
            for k in SS.THERMO_H}
    hist["short"]["u"][300:310] = [0] * 10
    pos, s0, weeks = P.thermo_positions(T, {"hist": hist})
    first = SS.CAL_RANK_MIN
    assert s0 == t[first] + S.LAG and len(weeks) == nw - first
    for name, R in S.THERMO_RULES.items():
        want = np.full(T, np.nan)
        for j in range(first, nw):
            if R.get("any"):
                on = hist["short"]["u"][j] >= 1
            else:
                on = sum(_rank_direct(hist[k][R["side"]], j) >= 2 / 3 for k in R["hz"]) >= R["need"]
            z = t[j + 1] + S.LAG if j + 1 < nw else T
            want[t[j] + S.LAG:z] = R["on"] if on else R["off"]
        np.testing.assert_array_equal(pos[name][s0:], want[s0:], err_msg=name)
        assert np.isnan(pos[name][:s0]).all()
    assert (pos["D1"][t[300] + 1:t[310]] == 0.0).all()


def test_page_check():
    res = {"tw": {"rules": {"A1": {"v": "better"}, "B1": {"v": "worse"}, "M2": {"v": "better"}}},
           "spx": {"rules": {"A1": {"v": "better"}, "B1": {"v": "same"}, "M2": {"v": "better"}}},
           "ixic": {"rules": {"A1": {"v": "better"}, "M2": {"v": "same"}}}}
    pc = P.page_check(res)
    assert pc["A1"] == {"n": 3, "better": 3, "worse": 0, "ok": True}
    assert pc["B1"]["ok"] is False and pc["B1"]["worse"] == 1
    assert pc["M2"] == {"n": 3, "better": 2, "worse": 0, "ok": False}


def _xs_data(mk):
    try:
        D = XT.data(mk)
    except Exception:                                # noqa: BLE001
        return None
    return D if len(D["cal"]) > 5000 else None


@pytest.mark.parametrize("mk", ["tw", "spx"])
def test_judge_equals_strategy_tier(mk):
    """practsim 逐年重新判定用的 xstrat.judge 和頁面用的 strategy() 判定一樣（全部資料）。"""
    D = _xs_data(mk)
    if D is None:
        pytest.skip("沒有總經策略的資料")
    full = XT.run_all().get(mk) or {}
    C = XT.Ctx(D)
    for s in P.xs_specs(mk, D):
        if s["k"] in full:
            assert XT.judge(C, s) == full[s["k"]]["tier"], s["k"]


@pytest.mark.parametrize("mk", ["tw", "spx"])
def test_held_pos_is_causal_and_matches_trades(mk):
    """照規則的部位只用到當天以前的價格：截到 2010 年前算的和全部資料算的一樣；交易型＝每一筆買進到賣出。"""
    D = _xs_data(mk)
    if D is None:
        pytest.skip("沒有總經策略的資料")
    cal = D["cal"]
    cut = bisect.bisect_left(cal, "2010-01-01")
    C, Ct = XT.Ctx(D), XT.Ctx(P.truncate(D, cut))
    for s in P.xs_specs(mk, D):
        p, pt = XT.held_pos(C, s), XT.held_pos(Ct, s)
        # 月底月初最後一個月要用休市表推月底（只比到一個月前）；Halloween 最後一天看的是下一個交易日的月份（截斷之後不知道）
        stop = cut - 25 if s["k"] == "tom" else cut - 1 if s["k"] == "hal" else cut
        np.testing.assert_array_equal(p[:stop], pt[:stop], err_msg=s["k"])
        if s["kind"] == "trade" and s["k"] != "tom":
            tr, _ = C.trades(s["k"], s["p"], XS.lag(mk, s["k"]))
            last = max(q for _, _, _, q in tr)
            held = XT.trade_held(C.T, tr)
            np.testing.assert_array_equal(held[1:last + 1], p[:last] > 0)


def test_xs_positions_match_direct():
    D = _xs_data("spx")
    if D is None:
        pytest.skip("沒有總經策略的資料")
    cal = D["cal"]
    C = XT.Ctx(D)
    specs = {s["k"]: s for s in P.xs_specs("spx", D)}
    ks = [k for k in ("rsi2", "faber", "coppock") if k in specs]
    sel = {2010: ks[:2], 2011: ks, 2012: [], 2013: ks[1:]}
    a = bisect.bisect_left(cal, "2010-01-01")
    z = bisect.bisect_left(cal, "2014-01-01")
    D4 = P.truncate(D, z)
    expo, cost, _ = P.xs_positions(D4, sel, a)
    hp = {k: XT.held_pos(XT.Ctx(D4), specs[k]) for k in ks}
    prev = {k: 0.0 for k in ks}
    for d in range(a, z):
        y = int(cal[d][:4])
        cur = {k: (hp[k][d] / len(sel[y]) if k in sel[y] else 0.0) for k in ks}
        assert expo[d] == pytest.approx(sum(cur.values())), cal[d]
        if d > a:
            assert cost[d] == pytest.approx(sum(abs(cur[k] - prev[k]) * XS.cost("spx", k) for k in ks)), cal[d]
        prev = cur
    assert C.T == len(cal)


def test_research_file_matches_spec():
    R = P.load()
    if R is None:
        pytest.skip("研究檔還沒產生")
    assert R["ver"] == S.VER and set(R["page"]) == set(S.PAGE_RULES)
    for mk, M in R["mk"].items():
        assert mk in S.MARKETS
        for k, x in M["rules"].items():
            assert k in S.RULES and x["v"] in S.VERDICTS
            assert 0.0 <= x["full"]["wbar"] <= 1.0
