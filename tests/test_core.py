"""交易計畫（arm/lab/core.py；corespec VER 2）：三種過熱、美股「總經策略全部空手」、台股買回要等幾天、部位、觸發價位、
回測、個股頁的衛星資料、前瞻紀錄。"""
import json
import math
import random
from datetime import date, timedelta

import numpy as np
import pytest

from arm.lab import core as C
from arm.lab import corespec as S


def test_families_lit_rules_and_missing_data():
    px = np.array([100.0] * 199 + [100.0, 90.0])                         # 第 200 天起才有 200 日均線
    inf = np.array([np.nan] * 199 + [80.0, 79.9])
    lev = np.array([np.nan] * 200 + [95.0])
    F = C.families(px, inf, lev)
    assert not F["lit"]["trend"][198] and math.isnan(F["ma"][198])         # 均線還沒有＝不亮
    assert not F["lit"]["trend"][199] and F["lit"]["trend"][200]         # 收盤低於含當天的 200 日均線才亮
    assert F["lit"]["inf"][199] and not F["lit"]["inf"][200]             # 80 以上算亮、沒有資料不亮
    assert list(F["n"][199:]) == [1, 2] and list(F["on"][199:]) == [True, False]


def test_decide_sells_at_once_and_waits_for_clear_days_to_buy_back():
    ok = np.array([1, 0, 1, 1, 0, 1, 1, 1, 1, 0], dtype=bool)
    on1, c1 = C.decide(ok, 1)
    assert list(on1) == list(ok) and list(c1) == [1, 0, 1, 2, 0, 1, 2, 3, 4, 0]      # need＝1：和 VER 1 一樣
    on3, _ = C.decide(ok, 3)
    assert list(on3) == [1, 0, 0, 0, 0, 0, 0, 1, 1, 0]                              # 連續 3 天 ok 那天才決定買回；不 ok 當天就賣
    rnd = random.Random(5)
    ok = np.array([rnd.random() > 0.2 for _ in range(500)])
    for need in (1, 2, 5, 10):                                                       # 和逐日直接算的版本一樣
        on, _ = C.decide(ok, need)
        st, run, exp = True, 0, []
        for x in ok:
            run = run + 1 if x else 0
            st = False if not x else (True if (st or run >= need) else False)
            exp.append(st)
        assert list(on) == exp


def test_families_flat_cuts_alone_and_tw_waits_ten_days():
    T = 260
    px = np.linspace(100, 130, T)                                                   # 一路漲：年線不會跌破
    inf, lev = np.full(T, 50.0), np.full(T, 50.0)
    flat = np.zeros(T, dtype=bool)
    flat[230:235] = True
    F = C.families(px, inf, lev, flat, "spx")
    assert F["n"][232] == 0 and not F["ok"][232] and not F["on"][232] and F["lit"]["flat"][232]   # 全部空手單獨就換現金
    assert F["on"][235] and F["need"] == 1                                          # 美股隔天就買回
    lev2 = lev.copy()
    inf2 = inf.copy()
    inf2[200:203], lev2[200:203] = 90.0, 90.0                                      # 台股：兩種亮三天
    F = C.families(px, inf2, lev2, None, "tw")
    assert F["need"] == S.REENTRY["tw"] == 10 and "flat" not in F["lit"]
    assert not F["on"][200] and not F["on"][211] and F["on"][212]                  # 203～212 連續 10 天 ok，212 收盤決定買回
    assert F["clear"][212] == 10


def test_macro_flat_matches_held_positions():
    from arm.lab import practsim as PS
    from arm.lab import xstrat as XT
    assert C.macro_flat("tw", ["2026-10-22"]) is None
    D = XT.data("spx")
    Cx = XT.Ctx(D)
    held_any = np.zeros(len(D["cal"]), dtype=bool)
    for s in PS.xs_specs("spx", D):
        held_any |= np.asarray(XT.held_pos(Cx, s)) > 0.5
    pick = [D["cal"][k] for k in range(1000, len(D["cal"]), 997)]
    got = C.macro_flat("spx", ["1900-01-02"] + pick)
    assert not got[0]                                                               # 總經策略資料以前＝不算
    assert list(got[1:]) == [not held_any[D["cal"].index(d)] for d in pick]
    H = C.macro_holding("spx")
    assert H["n"] == len(PS.xs_specs("spx", D)) and H["d"] == D["cal"][-1]


def test_held_lags_one_day_and_trigger_price():
    on = np.array([True, True, False, False, True])
    assert list(C.held(on)) == [1, 1, 1, 0, 0]                          # 收盤決定、下一個交易日收盤照做
    rnd = random.Random(3)
    px = np.array([100 + rnd.uniform(-5, 5) for _ in range(260)])
    trig = C.trigger_price(px)
    for nxt, below in ((trig * 0.999, True), (trig * 1.001, False)):     # 明天收盤在觸發價位下＝明天收盤在 200 日均線下
        F = C.families(np.append(px, nxt), np.full(261, np.nan), np.full(261, np.nan))
        assert bool(F["lit"]["trend"][-1]) == below


def _direct(tot, rf, sat, a, b, c_idx, sl=None, inpos=None, swc=None, c_stk=None):
    """逐日直接算（和 simulate 不同寫法）。"""
    sl = tot if sl is None else sl
    out = [1.0]
    for k in range(a + 1, b):
        r = 0.7 * tot[k] + 0.3 * (sl[k] if sat[k - 1] else rf[k])
        c = 0.0
        if sat[k - 1] and swc is not None:
            c += 0.3 * swc[k]
        if sat[k] != sat[k - 1]:
            c += 0.3 * (c_stk if (inpos is not None and inpos[k]) else c_idx)
        out.append(out[-1] * (1 + r) * (1 - c))
    return np.array(out)


def test_simulate_matches_direct_loop():
    rnd = random.Random(7)
    T = 400
    tot = np.array([rnd.gauss(0.0004, 0.012) for _ in range(T)])
    rf = np.full(T, 0.00005)
    sl = np.array([rnd.gauss(0.0008, 0.02) for _ in range(T)])
    on = np.array([rnd.random() > 0.1 for _ in range(T)])
    sat = C.held(on)
    inpos = np.array([rnd.random() > 0.5 for _ in range(T)])
    swc = np.array([0.001 if rnd.random() > 0.95 else 0.0 for _ in range(T)])
    for args in ((None, None, None, None), (sl, inpos, swc, 0.0024)):
        a = C.simulate(tot, rf, sat, 10, T, 0.001, *args)
        b = _direct(tot, rf, sat, 10, T, 0.001, *args)
        assert a == pytest.approx(b, rel=1e-12)
    f = C.simulate_fixed(tot, rf, 1.0, 10, T)                           # 一直拿滿＝70% 大盤＋30% 大盤
    assert f[-1] == pytest.approx(float(np.prod(1 + tot[11:T])), rel=1e-12)


def test_stats_years_roll_and_ex_best():
    cal, d = [], date(2019, 1, 1)
    while len(cal) < 800:
        if d.weekday() < 5:
            cal.append(d.isoformat())
        d += timedelta(days=1)
    rnd = random.Random(11)
    nav = np.cumprod(np.concatenate([[1.0], 1 + np.array([rnd.gauss(0.0005, 0.01) for _ in range(799)])]))
    st = C.stats(cal, nav, 0, 800)
    ys = st["years"]
    assert [y[0] for y in ys] == ["2019", "2020", "2021", "2022"]
    assert math.prod(1 + y[1] for y in ys) == pytest.approx(nav[-1])
    r = [nav[i + 252] / nav[i] - 1 for i in range(800 - 252)]
    assert st["q"] == pytest.approx(list(np.quantile(r, S.Q))) and st["loss"] == pytest.approx(np.mean(np.array(r) < 0))
    assert st["mdd"] == pytest.approx(max(1 - nav[i] / max(nav[:i + 1]) for i in range(800)))


def test_cash_runs_and_scenario_episodes():
    sat = np.array([1, 1, 0, 0, 1, 1, 0, 1], dtype=float)
    assert C.cash_runs(sat, 0, 8) == [(2, 3), (6, 6)]


def test_stk_from_adv_keeps_only_star_strategies_and_next_45_days():
    A = {"book": [{"k": "s3", "tier": "good", "name": "臺灣50 提前卡位"}, {"k": "v3l", "tier": "good", "name": "財報驚喜（大型股）"},
                  {"k": "s1", "tier": "ref", "name": "共識加碼"}],
         "picks": [{"k": "v3l", "act": "持有中", "c": "2330", "n": "台積電", "ent": "2026-08-17", "out": "2026-11-12", "now_r": -1.0},
                   {"k": "s1", "act": "持有中", "c": "2891", "n": "中信金"}],
         "cal": [{"k": "v3l", "d": "2026-11-12", "at": "收盤", "act": "賣出", "held": True, "ent": "2026-08-17",
                  "items": [{"c": "2330", "n": "台積電"}], "sname": "財報驚喜（大型股）"},
                 {"k": "v3l", "d": "2026-11-17", "at": "開盤", "act": "買進", "pending": True, "fix": "2026-11-16", "items": []},
                 {"k": "s1", "d": "2026-10-27", "at": "收盤", "act": "賣出", "items": []},
                 {"k": "s3", "d": "2027-01-30", "at": "收盤", "act": "賣出", "items": []}],
         "trades": {"v3l": {"kind": "per"}, "s3": {"kind": "rev"}, "s1": {"kind": "trade"}}}
    X = C.stk_from_adv(A, "2026-10-23")
    assert [s["kind"] for s in X["st"]] == ["rev", "per"]                         # 定期換股的分法要看 kind
    assert [s["k"] for s in X["st"]] == ["s3", "v3l"] and X["w"] == pytest.approx(0.80 * 0.5 / 2)   # VER 4：★ 那一半平分
    assert X["bw"] == pytest.approx(0.40) and X["boom"] is None
    assert [h["c"] for h in X["hold"]["v3l"]] == ["2330"] and X["hold"]["s3"] == []
    assert [(e["k"], e["d"]) for e in X["ev"]] == [("v3l", "2026-11-12"), ("v3l", "2026-11-17")]   # ● 的、45 天以後的不列
    assert X["ev"][1]["pending"] and X["ev"][1]["fix"] == "2026-11-16"


def test_record_only_in_ci_and_overwrites_same_day(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LIVE", tmp_path / "core_live.json")
    d = S.LIVE_START
    n = {"d": d, "fams": [{"k": "inf", "lit": False, "v": 76.7}, {"k": "lev", "lit": False, "v": 54.5},
                          {"k": "trend", "lit": False, "pct": 14.1}], "n": 0, "next": 1.0}
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert C.record({"tw": n}, None) is False and not C.LIVE.exists()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert C.record({"tw": n, "spx": dict(n, d="2026-10-23")}, {"st": [{"k": "v3l"}], "boom": {"book": "R60"}}) is True
    L = json.loads(C.LIVE.read_text(encoding="utf-8"))
    assert list(L["days"]) == [d] and L["days"][d]["tw"]["sat"] == ["v3l", "R60"]   # 起點以前的不記；VER 4 台股機動另有新飆股
    assert C.record({"tw": dict(n, n=2, next=0.2)}, None) is True
    assert json.loads(C.LIVE.read_text(encoding="utf-8"))["days"][d]["tw"]["E"] == 0.2
    assert C.forward("tw")["n"] == 1 and C.forward("tw")["next"] == S.CHECKS[0]
    C.LIVE.write_text(json.dumps({"ver": S.VER - 1, "days": {d: {"tw": {}}}}), encoding="utf-8")
    assert C.load_live() == {"ver": S.VER, "days": {}}                            # 規則改過＝前瞻從頭記
    fl = {"k": "flat", "lit": False, "held": ["10 個月均線", "200 日均線"]}
    assert C.record({"spx": dict(n, fams=n["fams"] + [fl], clear=4)}, None) is True
    r = json.loads(C.LIVE.read_text(encoding="utf-8"))["days"][d]["spx"]
    assert r["held"] == 2 and r["clear"] == 4 and "flat" not in r["v"]


def test_research_file_matches_spec():
    R = C.load()
    assert R is not None and R["ver"] == S.VER
    assert set(R["mk"]) == set(S.MARKETS)
    assert set(R["mk"]["tw"]["sc"]) == {"rule", "long", "plan"} and set(R["mk"]["spx"]["sc"]) == {"rule", "early"}
    for mk, M in R["mk"].items():                                                # VER 4：每段都照這個市場的核心比例
        assert all(s["core"] == S.core_of(mk) for s in M["sc"].values())
    for mk, M in R["mk"].items():
        for key, s in M["sc"].items():
            assert s["plan"]["m"] > 0 and 0 < s["plan"]["mdd"] < 1 and s["chart"]["pts"]
            assert s["a"] >= S.RULE_START[mk] if key == "rule" else True
            assert all(e["sell"] <= (e["buy"] or "9999") for e in s["eps"])
    tw = R["mk"]["tw"]["sc"]
    assert tw["plan"]["sleeve"] == "R60+star" and tw["plan"]["a"] >= S.PLAN4_START and tw["long"]["a"] >= S.PLAN_START
    assert tw["plan"]["b"] == tw["long"]["b"] and 0.9 < tw["plan"]["boom_x"] < 1
    assert R["mk"]["spx"]["sc"]["early"]["b"] <= S.EARLY["spx"] and R["mk"]["ndx"]["sc"]["early"]["b"] <= S.EARLY["ndx"]
