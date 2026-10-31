"""今天的訊號「第幾天進場」的格子（sigspec VER 26 第 5.1 節；arm/lab/sigage.py、sigcat.listing ④c、thermocal 的票）。"""
import numpy as np

from arm.lab import sigage as A
from arm.lab import sigcat as G
from arm.lab import sigspec as S
from arm.lab import thermocal as TC


def test_buckets_and_cell_keys():
    """分段 0／1～4／5～9／10～19／20～59／60 以上；格＝分段 × 條件（o 成立、x 已斷、- 不分）。"""
    assert [int(A.bucket(k)) for k in (0, 1, 4, 5, 9, 10, 19, 20, 59, 60, 300)] == [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert A.ck_now(5, "off") == "2x" and A.ck_now(0, "on") == "0o" and A.ck_now(249, "-") == "5-"
    assert all(A.cid_of(A.ckey(c)) == c for c in range(A.NC))


def _ev(days, exp=(), T=60):
    return {"id": "tw:x:v:hot_in", "cat": "x", "sig": "hot_in", "kind": "event", "H": 20, "samp": np.arange(T),
            "days": list(days), "exp": np.asarray(exp, dtype=np.int64)}


def test_days_event_age_cluster_condition_and_expiry():
    """事件型：第幾天＝那天 − 最近一次出現（再出現就重算）、算哪一次照第 3.4 節去重、相反的讀數之後不算、第 0 天一定成立。"""
    T = 60
    cx = np.zeros(T, dtype=bool)
    cx[10:13] = True                                   # 第 10～12 天還成立，13 起斷了
    cx[40:45] = True
    D = A.days(_ev([10, 15, 40], exp=[30]), T, 20, cx)
    t = D["t"].tolist()
    assert t == list(range(10, 30)) + list(range(40, 60))                # 第 15 天再出現 → 有效到 min(15＋20, 相反那天 30)
    k = dict(zip(t, D["k"].tolist()))
    assert (k[10], k[14], k[15], k[29], k[40], k[59]) == (0, 4, 0, 14, 0, 19)
    cl = dict(zip(t, D["cl"].tolist()))
    assert cl[15] == cl[10] == 0 and cl[40] == 1                          # 第 15 天和第 10 天相隔不到 20 天，算同一次
    ck = {d: A.ckey(int(c)) for d, c in zip(t, D["cid"].tolist())}
    assert (ck[10], ck[12], ck[13], ck[15], ck[16], ck[20]) == ("0o", "1o", "1x", "0o", "1x", "2x")   # 第 15 天再出現：第 0 天一定成立
    assert A.days(_ev([10, 15, 40], exp=[30]), T, 20, None)["cid"].tolist()[:3] == [2, 5, 5]          # 沒有條件＝只分第幾天


def test_days_state_daily_and_monthly():
    """狀態型：第幾天＝那天 − 這一段第一天（第 3.4 節的分段）；月資料一個月底到下一個月底前都算同一格。"""
    T = 100
    samp = np.arange(T)
    st = np.zeros(T, dtype=bool)
    st[10:30] = True
    st[35:40] = True                                   # 中斷 5 天（< EP_GAP）＝同一段
    sd = {"kind": "state", "samp": samp, "state": st}
    D = A.days(sd, T, 60)
    k = dict(zip(D["t"].tolist(), D["k"].tolist()))
    assert k[10] == 0 and k[29] == 19 and k[35] == 25 and set(D["cl"].tolist()) == {0}
    assert set(D["cid"].tolist()) == {2, 5, 8, 11, 14} and D["s"].all()
    ms = np.array([20, 41, 62, 83], dtype=np.int64)
    sm = {"kind": "state", "samp": ms, "state": np.array([False, True, True, False]), "monthly": True}
    Dm = A.days(sm, T, 250)
    assert Dm["t"].tolist() == list(range(41, 83)) and Dm["s"].sum() == 2          # 只有月底算樣本日
    km = dict(zip(Dm["t"].tolist(), Dm["k"].tolist()))
    assert km[41] == 0 and km[61] == 0 and km[62] == 21 and km[82] == 21


def test_table_prefix_and_passes():
    """全部資料的格：次數＝有幾次、命中率每一天一樣重；逐年只用窗口在 cut 之前走完的日子（t＋LAG＋H < cut）。"""
    T, H = 400, 20
    days = [100, 200, 300]
    D = A.days(_ev(days, T=T), T, H, None)
    Yu = np.full(T, np.nan)
    Yw = np.full(T, np.nan)
    Yu[:T - S.LAG - H] = 0.5
    Yw[:T - S.LAG - H] = 0.0
    Yu[100:105] = 1.0                                   # 第 0～4 天都漲
    Yu[300:305] = 1.0
    Yu[200:205] = 0.0
    Yr = np.zeros(T)
    Yd = np.zeros(T)
    cal = [f"d{i}" for i in range(T)]
    tb = A.table(D, Yu, Yw, Yr, Yd, np.arange(T), cal)
    c0 = tb["c"]["0-"]
    assert c0[:2] == [3, 3] and abs(c0[2] - 2 / 3) < 1e-12           # 三次、三天、兩次漲
    c1 = tb["c"]["1-"]
    assert c1[:2] == [3, 12] and abs(c1[2] - 8 / 12) < 1e-12
    P = A.Prefix(D, Yu, Yw, np.arange(T), H)
    p = P.at(250)                                       # cut 250：窗口走完＝t < 250 − 1 − 20＝229 → 第 100、200 那兩次
    assert p["n"][A.cid_of("0-")] == 2 and p["m"][A.cid_of("1-")] == 8
    assert abs(p["up"][A.cid_of("0-")] - 0.5) < 1e-12 and abs(p["bu"] - Yu[:229].mean()) < 1e-12
    y = P.year(290, 310)
    assert y["m"][A.cid_of("0-")] == 1 and y["up"][A.cid_of("0-")] == 1.0
    assert A.passes(None, "up").sum() == 0 and not A.passes(p, "up")[A.cid_of("0-")]   # 次數 2 < N_MIN


def test_cond_run_and_side():
    """條件：法人連續＝那天同一邊連續 ≥ N 天（沒有資料照前一天）；均線類＝那天還在事件那一邊。"""
    T = 30
    amt = np.full(T, 1.0)
    amt[5:16] = -1.0                                    # 第 5～15 天賣超（11 天）
    amt[16] = np.nan                                    # 沒有資料：照前一天
    F = {"cal": [str(i) for i in range(T)], "ivars": [{"key": "dl1", "amt": amt}]}
    c = A.cond(F, {"cat": "inst", "sig": "sell_run10", "var": "dl1"})
    assert c[14] and c[15] and c[16] and not c[17] and not c[13]
    px = np.concatenate([np.linspace(100, 120, 300), np.linspace(120, 100, 30)])
    F2 = {"cal": [str(i) for i in range(len(px))], "px": px}
    s = A.cond(F2, {"cat": "tech", "sig": "ev", "var": "ma20_dn"})
    assert not s[250] and s[-1]                          # 漲的時候收盤在月線上、跌一段之後在月線下
    assert A.cond(F2, {"cat": "tech", "sig": "ev", "var": "pv_up"}) is None          # 前波高低點只分第幾天


def _rows():
    st = lambda h, b, n=20: {"n": n, "hit": h, "base": b}
    return [{"id": "tw:heat:a:hot_in", "mk": "tw", "cat": "heat", "var": "a", "kind": "event", "H": 20, "name": "甲",
             "up": st(0.8, 0.6), "warn": st(0.1, 0.1)},
            {"id": "tw:heat:b:hot_in", "mk": "tw", "cat": "heat", "var": "b", "kind": "event", "H": 20, "name": "乙",
             "up": st(0.8, 0.6), "warn": st(0.1, 0.1)},
            {"id": "tw:heat:c:hot_in", "mk": "tw", "cat": "heat", "var": "c", "kind": "event", "H": 20, "name": "丙",
             "up": st(0.8, 0.6), "warn": st(0.1, 0.1)},
            {"id": "tw:heat:d:hot_in", "mk": "tw", "cat": "heat", "var": "d", "kind": "event", "H": 20, "name": "丁",
             "up": st(0.8, 0.6), "warn": st(0.1, 0.1)}]


def _age():
    cell = lambda n, hu: [n, n * 3, hu, 0.1, 0.01, 0.05, "2020-01-02"]
    return {"ver": S.AGE_VER, "cells": {}, "rows": {
        "tw:heat:a:hot_in": {"short": {"H": 20, "b": [0.6, 0.1, 0.0], "c": {"2x": cell(9, 0.7)}}},     # 過
        "tw:heat:b:hot_in": {"short": {"H": 20, "b": [0.6, 0.1, 0.0], "c": {"2x": cell(9, 0.62)}}},    # 不比平常高 5 點
        "tw:heat:c:hot_in": {"short": {"H": 20, "b": [0.6, 0.1, 0.0], "c": {"2x": cell(3, 0.9)}}},     # 次數不夠
        "tw:heat:d:hot_in": {"short": {"H": 20, "b": [0.6, 0.1, 0.0], "c": {"3o": cell(9, 0.9)}}}}}


def test_listing_needs_own_and_today_cell_and_keeps_pending():
    """④c：訊號自己會列、而且今天那一格也過才列（edge＝那一格的 e、st＝那一格、st0＝自己的）；沒過的放進行中並寫原因；
    之後出現相反的讀數的（gone）也放進行中；研究檔沒有（傳 {}）照 ④b。"""
    rows = _rows()
    now = {"since": "2026-10-21", "n": 5, "k": 5, "st": "off", "ck": "2x"}
    on = {r["id"]: dict(now) for r in rows[:3]}
    gone = {"tw:heat:d:hot_in": {"short": {**now, "k": 12, "ck": "3o", "exp": "2026-10-27"}}}
    pend: list = []
    L = G.listing(rows, on, "tw", T={}, A=_age(), gone=gone, pend=pend)
    assert [x["id"] for x in L] == ["tw:heat:a:hot_in"]
    x = L[0]
    assert abs(x["edge"] - 0.1) < 1e-12 and abs(x["e0"] - 0.2) < 1e-12 and x["st"]["n"] == 9 and x["st0"]["n"] == 20
    assert x["age"] is True and x["cell"]["ck"] == "2x"
    why = {p["id"]: p["why"] for p in pend}
    assert why == {"tw:heat:b:hot_in": "weak", "tw:heat:c:hot_in": "few", "tw:heat:d:hot_in": "exp"}
    old = G.listing(rows, on, "tw", T={}, A={})
    assert {x["id"] for x in old} == {r["id"] for r in rows[:3]} and all(x["age"] is False for x in old)


def test_today_and_board_carry_pending(monkeypatch):
    """today／board：進行中依溫度計與邊放好、不算溫度計；"age"＝第幾天的研究檔有沒有。"""
    monkeypatch.setattr(A, "load", lambda path=None: _age())
    rows = _rows()
    now = {"since": "2026-10-21", "n": 5, "k": 5, "st": "off", "ck": "2x"}
    on = {r["id"]: dict(now) for r in rows[:3]}
    B = G.board(rows, on, "tw", T={})
    short = next(t for t in B["thermo"] if t["k"] == "short")
    assert short["n"] == {"up": 1, "warn": 0} and len(short["pend"]["up"]) == 2 and B["age"] is True
    Td = G.today(rows, on, "tw", T={})
    assert len(Td["up"]) == 1 and len(Td["pend"]["up"]) == 2


def test_thermocal_counts_cells_and_old_votes(monkeypatch, tmp_path):
    """③d VER 26：votes 每支溫度計是 {格: 邊}，看今天落的那一格；rule="v25" 用研究檔另存的舊票。"""
    hz = {k: {"H": H, "th": 0.1, "wk": [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(300)],
              "u": [i % 3 for i in range(300)], "w": [0] * 300,
              "up": {"g": {"lo": [0.5, 200], "mid": [0.6, 100], "hi": [0.7, 200]}, "all": [0.6, 500], "v": "rel"},
              "warn": {"g": {"lo": [0.2, 200], "mid": [0.3, 100], "hi": [0.25, 200]}, "all": [0.25, 500], "v": "none"}}
          for k, H in S.THERMO_H.items()}
    M = {"votes": {"tw:heat:a:hot_in": {"i": "item:a", "v": {"short": {"2x": "u", "0o": "uw"}}}},
         "hz": hz, "v25": {"votes": {"tw:heat:a:hot_in": {"i": "item:a", "v": {"short": "uw"}}}, "hz": hz}}
    monkeypatch.setattr(G, "research_rows", lambda: [{"id": "tw:heat:a:hot_in", "H": 20}])
    on = {"tw:heat:a:hot_in": {"ck": "2x"}}
    assert TC.counts_now(M, on, {})["short"] == {"u": 1, "w": 0}
    assert TC.counts_now(M, {"tw:heat:a:hot_in": {"ck": "1x"}}, {})["short"] == {"u": 0, "w": 0}
    assert TC.counts_now(M, {"tw:heat:a:hot_in": {"ck": "1x"}}, {}, rule="v25")["short"] == {"u": 1, "w": 1}
    p = tmp_path / "t.json"
    TC.save({"ver": S.CAL_VER, "mk": {"tw": M}}, p)
    TC._CACHE.clear()
    monkeypatch.setattr(TC, "OUT", p)
    assert TC.now("tw", on, {}, "2026-12-31")["short"]["up"]["n"] == 1
    assert TC.now("tw", on, {}, "2026-12-31", rule="v25")["short"]["warn"]["n"] == 1
    TC._CACHE.clear()


def test_research_file_covers_markets():
    """研究檔（scripts/run_sigage.py）：版本夠、五個市場都有、跨期間的類別三支溫度計都有、之後也成立的格子兩套前綴都有。"""
    R = A.load()
    assert R and R["ver"] >= S.AGE_VER and set(R["last"]) == set(S.MARKETS)
    mks = {sid.split(":")[0] for sid in R["rows"]}
    assert mks == set(S.MARKETS)
    for sid, X in R["rows"].items():
        cat = sid.split(":")[1]
        if cat in S.THERMO_X_CATS:
            assert set(X) == set(S.THERMO_H), sid
        for hz, Y in X.items():
            assert Y["H"] == S.THERMO_H[hz] and len(Y["b"]) == 3
            assert all(len(c) == 7 and c[0] >= 1 and c[1] >= c[0] for c in Y["c"].values())
    assert any(k.startswith(S.AGE_XP[0]) for k in R["cells"]) and any(k.startswith(S.AGE_XP[1]) for k in R["cells"])
