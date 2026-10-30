"""寬度與深度的算法（arm/lab/breadth.py；規格 breadthspec VER 1）：小資料驗算。"""
import random

import numpy as np

from arm.lab import breadth as BR
from arm.lab import breadthspec as S


def test_tw_ewgap_and_ma200_on_small_matrices():
    cal = [f"2020-01-{d:02d}" for d in range(1, 7)]
    C = np.array([[10, 11, 12, 13, 14, 15], [10, 10, 10, 10, 10, 20], [10, np.nan, 10, 10, 10, 10]], dtype=float)
    E = np.ones_like(C, dtype=bool) & ~np.isnan(C)
    tr = {d: 100.0 + 10 * i for i, d in enumerate(cal)}
    g = BR.ewgap_tw(cal, C, E, tr, lb=2, min_n=2)
    # 1/3：指數 120/100−1＝20%；三檔 20%、0%、0% → 平均 6.67% → 差 13.33 個百分點
    assert round(g["2020-01-03"], 6) == round(20 - 20 / 3, 6)
    # 1/4：指數 130/110−1；第三檔 1/2 沒收盤不算 → 兩檔平均
    assert round(g["2020-01-04"], 6) == round(100 * ((130 / 110 - 1) - (13 / 11 - 1) / 2), 6)
    m = BR.ma200_tw(cal, C, E, n=3, min_n=2)
    assert "2020-01-02" not in m and "2020-01-03" in m           # 近 3 天都要有收盤；第三檔 1/2 缺價，1/3 只剩兩檔
    # 1/6：第一檔 15 ÷ 14 − 1、第二檔 20 ÷ (40/3) − 1、第三檔 10 ÷ 10 − 1 → 中位數＝第一檔
    assert round(m["2020-01-06"], 6) == round(100 * (15 / 14 - 1), 6)


def test_us_adv_upv_and_ewgap():
    br = {f"2020-01-{d:02d}": [d, 10 - d, 0, 2 * d, 10, 0, 0, 10, 10] for d in range(1, 5)}
    adv, upv = BR.us_adv(br, w=2)
    assert "2020-01-01" not in adv and round(adv["2020-01-02"], 6) == round(100 * 3 / 20, 6)
    assert round(upv["2020-01-04"], 6) == round(100 * 14 / 34, 6)
    cw = {"a": 100.0, "b": 110.0, "c": 121.0}
    ew = {"a": 100.0, "b": 100.0, "c": 100.0, "d": 90.0}
    g = BR.ewgap_us(cw, ew, lb=2)                                        # 只用兩檔都有收盤的日子
    assert list(g) == ["c"] and round(g["c"], 9) == 21.0


def test_heat100_never_looks_ahead(monkeypatch):
    from arm.lab import heatspec as HS
    monkeypatch.setitem(HS.PCT_WIN, "d", 10)
    monkeypatch.setitem(HS.PCT_MIN, "d", 3)
    cal = [str(i) for i in range(30)]
    raw = {d: float(i % 7) for i, d in enumerate(cal)}
    a = BR.heat100(cal, raw)
    raw2 = dict(raw, **{cal[29]: 1e9, cal[28]: -1e9})                # 改最後兩天，前面的 0～100 不變
    b = BR.heat100(cal, raw2)
    assert np.allclose(a[:28], b[:28], equal_nan=True) and np.isnan(a[:3]).all()


def test_breadth_series_depth_and_forward_drawdown():
    Lv = {"A": {"2000-01": 2, "2000-02": 0}, "B": {"2000-01": 0, "2000-02": 3}, "C": {"2000-02": 4}}
    caps = {"A": {"2000-01": 30.0}, "B": {"2000-01": 70.0, "2000-02": 10.0}, "C": {"2000-02": 90.0}}
    s = BR.breadth_series(Lv, caps)
    assert s["2000-01"] == [1, 2, 0.5, 0.3] and s["2000-02"][:3] == [2, 3, 2 / 3] and abs(s["2000-02"][3] - 1.0) < 1e-12
    me = {f"2001-{m:02d}": v for m, v in zip(range(1, 13), [100, 120, 90, 95, 100, 101, 102, 103, 104, 105, 106, 107])}
    me.update({"2002-01": 108.0, "2002-02": 109.0})
    dd = BR.fwd_dd(me, h=12)
    assert abs(dd["2001-01"] - 0.25) < 1e-12 and dd["2001-03"] is None    # 1 月：高點 120 → 90；3 月之後沒走完 12 個月
    gap = dict(me)
    del gap["2001-06"]
    assert BR.fwd_dd(gap, h=12)["2001-01"] is None                       # 中間缺月不算


def test_tests_one_and_two_use_spec_rules():
    ms = [f"{1931 + i // 12}-{i % 12 + 1:02d}" for i in range(240)]
    ev = {m: (i % 40) < 6 for i, m in enumerate(ms)}                   # 6 段事件
    dd = {m: (0.3 if ((i % 40) < 6 or i % 9 == 0) else 0.05) for i, m in enumerate(ms)}
    one = BR.test_one(ev, dd, random.Random(S.SEED))
    assert one["n_ev"] == 36 and one["epi"] == 6 and one["p_ev"] == 1.0 and one["diff"] > S.EDGE
    assert one["lo"] is not None and one["lo"] > 0 and one["pass"]
    again = BR.test_one(ev, dd, random.Random(S.SEED))
    assert (again["lo"], again["hi"]) == (one["lo"], one["hi"])         # 固定種子：每次一樣
    lv = {m: (2 if i % 2 == 0 else 0) for i, m in enumerate(ms)}
    two = BR.test_two(ev, lv, dd, random.Random(S.SEED))
    assert two["n_g"] == 120 and two["p_ev"] == 1.0 and two["epi_ev"] >= 3 and two["diff"] > 0


# ── 第三段：接進訊號總覽（sigspec VER 25 第 4.15 節）與市場頁的讀數 ─────────────────────

def test_market_vars_follow_var_mkt_and_skip_missing(monkeypatch):
    from arm.lab import heatspec as HS
    monkeypatch.setitem(HS.PCT_WIN, "d", 10)
    monkeypatch.setitem(HS.PCT_MIN, "d", 3)
    cal = [f"2020-01-{d:02d}" for d in range(1, 21)]
    raw = {"TW_EWGAP": {d: float(i) for i, d in enumerate(cal)}, "US_ADV": {d: 50.0 for d in cal}}
    tw = BR.market_vars("tw", cal, raw)
    assert [v["key"] for v in tw] == ["TW_EWGAP"]                       # 台股只收台股的變數；落檔沒有的（TW_MA200）不列
    v = tw[0]
    assert v["grp"] == "bd" and v["H"] == S.H and v["name"] == S.VAR_NAMES["TW_EWGAP"] and len(v["x"]) == len(cal)
    assert v["raw"][5] == 5.0 and v["fmt"].format(-3.8) == "-3.8 個百分點"
    assert [v["key"] for v in BR.market_vars("sox", cal, raw)] == ["US_ADV"]   # 費半沒有等權 ETF
    assert BR.market_vars("spx", cal, {}) == []


def test_bd_vars_fail_open(monkeypatch):
    from arm.lab import sigcat as G

    def boom(mk, cal):
        raise RuntimeError("落檔壞了")
    monkeypatch.setattr(BR, "market_vars", boom)
    assert G.bd_vars("tw", ["2020-01-01"]) == []                         # 算不出來就沒有這一類，不擋其他訊號


def test_bd_signals_use_the_six_heat_variants():
    from arm.lab import sigcat as G
    from arm.lab import sigspec as X
    T = 60
    cal = [f"d{i:03d}" for i in range(T)]
    x = np.array([np.nan] * 5 + [90.0] * 20 + [50.0] * 20 + [10.0] * 15)
    F = {"mk": "spx", "cal": cal, "we": list(range(4, T, 5))}
    sds = G._var_signals(F, {"key": "US_ADV", "name": "上漲家數占比", "grp": "bd", "H": S.H, "x": x}, X.BD_CAT)
    assert [sd["sig"] for sd in sds] == list(X.VARIANTS)
    assert all(sd["id"].startswith("spx:bd:US_ADV:") and sd["cat"] == "bd" for sd in sds)
    assert "brk" in next(sd for sd in sds if sd["sig"] == "hot") and "exp" in next(sd for sd in sds if sd["sig"] == "hot_in")


def test_sigpage_puts_bd_under_tech_indicators():
    from arm.lab import sigpage as SP
    r = {"cat": "bd", "mk": "spx", "var": "US_EWGAP", "vn": S.VAR_NAMES["US_EWGAP"], "name": "x", "id": "spx:bd:US_EWGAP:cold"}
    assert SP.ind_of(r) == ("spx:bd:US_EWGAP", "bd", S.VAR_NAMES["US_EWGAP"], "US_EWGAP")
    assert SP.facet_of("bd", None, "US_EWGAP") == ("tech", "ind") and "bd" in SP.IND_CATS


def test_ind_now_counts_levels_and_cap_share():
    I = {"tw": {"A": {"now": {"d": "2026-10-30", "L": 2, "P1": True, "P2": False}},
                "B": {"now": {"d": "2026-10-30", "L": 0, "P1": False, "P2": False}},
                "C": {"now": {"d": "2026-10-30", "L": 3, "P1": True, "P2": True}},
                "D": {"now": {"d": "2026-10-30", "L": 0, "P1": None, "P2": False}}}}    # P1 算不出來＝沒有等級（同 levels）
    caps = {"A": {"2026-08": 1.0, "2026-09": 30.0}, "B": {"2026-09": 50.0}, "C": {"2026-09": 20.0, "2026-11": 99.0}, "D": {"2026-09": 900.0}}
    n = BR.ind_now(I, "tw", caps)
    assert (n["n_hot"], n["n"], n["hot"], n["cap_m"]) == (2, 3, ["A", "C"], "2026-09")
    assert abs(n["id"] - 0.5) < 1e-12                                     # (30＋20) ÷ (30＋50＋20)；D 沒有等級不算、11 月的市值還不能用
    assert BR.ind_now(I, "tg") is None and BR.ind_now(I, "tw")["id"] is None


def test_prev_max_and_wide_spells():
    ser = {"2020-01": [1, 10, 0.1, 0.2], "2020-02": [3, 10, 0.3, None], "2020-03": [3, 10, 0.3, 0.9],
           "2021-06": [2, 10, 0.2, 0.5], "2021-07": [0, 10, 0.0, 0.0]}
    assert BR.prev_max(ser, 0, "2021-07") == (3, "2020-03") and BR.prev_max(ser, 3, "2020-03") == (0.2, "2020-01")
    sp = BR.wide_spells(ser)
    assert [(e["a"], e["z"], e["n"], e["hot"], e["id"]) for e in sp] == [("2020-02", "2020-03", 2, 3, 0.9), ("2021-06", "2021-06", 1, 2, 0.5)]


def test_bdepth_update_recomputes_only_when_needed(monkeypatch):
    """CI 每班（fetch_heat.py 最後一項）：官方分片有新的一天、或最新一天的大型股撐盤還在等報酬指數，才重讀個股面板重算。"""
    from arm.lab import bt3d, store
    from arm.lab import heatdata as HD
    from arm.lab import heatfetch as F
    state = {"bdepth": {"2026-10-29": [1.0, 2.0], "2026-10-30": [None, 2.5]}}
    calls = []
    monkeypatch.setattr(HD, "load", lambda name: state.get(name, {}))
    monkeypatch.setattr(store, "dates", lambda kind: ["2026-10-29", "2026-10-30"])
    tr = {"q": {"2026-10-29": 1.0}}
    monkeypatch.setattr(store, "read_json", lambda name, default=None: tr)
    monkeypatch.setattr(HD, "ShardPanel", lambda: object())
    monkeypatch.setattr(bt3d, "Panel", lambda: object())
    monkeypatch.setattr(HD, "extend", lambda P, SP: None)
    monkeypatch.setattr(BR, "tw_bdepth", lambda P: {"2026-10-30": [3.0, 2.5]})
    monkeypatch.setattr(F, "_replace", lambda name, src, new: calls.append((name, src, new)) or 1)
    assert F.bdepth_update() == 0 and calls == []                       # 報酬指數還沒有 10/30：重算也一樣，不重讀
    tr["q"]["2026-10-30"] = 2.0
    assert F.bdepth_update() == 1 and calls[-1] == ("bdepth", "v3px+mkt+v3_tr", {"2026-10-30": [3.0, 2.5]})
    state["bdepth"]["2026-10-30"] = [3.0, 2.5]
    n = len(calls)
    assert F.bdepth_update() == 0 and len(calls) == n                   # 都算過了
    assert F.bdepth_update(True) == 1 and len(calls) == n + 1          # 回補：整段重算
