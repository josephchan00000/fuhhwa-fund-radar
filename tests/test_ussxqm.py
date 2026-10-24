"""美股三成的規則 QM（arm/lab/ussxqm.py；ussxspec VER 3、docs/lab_us_sleeve_plan.md 第 13 節）：用假資料驗證規則、
資金帳戶（和 ussxbook.run 同一套）、最新一天的狀態、每週紀錄只增不改、每天的 50 日線檢查、檢討的百分位。"""
from datetime import date, timedelta

import numpy as np
import pytest

from arm.lab import ussxbook as BK
from arm.lab import ussxfeat as UF
from arm.lab import ussxqm as QM
from arm.lab import ussxspec as X
from arm.usnews import _US_MKT_HOLIDAYS


def _cal(a: str, b: str) -> list[str]:
    d, out = date.fromisoformat(a), []
    while d <= date.fromisoformat(b):
        if d.weekday() < 5 and d not in _US_MKT_HOLIDAYS:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _ctx(cal: list[str], N: int = 6, seed: int = 7) -> dict:
    """假的 context：N 檔股票隨機走、每週末每一檔都有一列（RS 隨機、財報條件都過）。"""
    rng = np.random.default_rng(seed)
    T = len(cal)
    C = 50 * np.cumprod(1 + rng.normal(0.0008, 0.02, size=(T, N)), axis=0)
    O = C * (1 + rng.normal(0, 0.004, size=(T, N)))
    syms = [f"S{k}" for k in range(N)]
    P = {"cal": cal, "sym": syms, "col": {s: j for j, s in enumerate(syms)}, "O": O, "C": C, "RAW": C * 0.8,
         "last": np.full(N, T - 1)}
    wk = UF.week_ends(cal)
    di, jj, cc, rs = [], [], [], []
    for i in wk:
        r = rng.permutation(np.linspace(60, 99, N))
        for j in range(N):
            di.append(i)
            jj.append(j)
            cc.append(syms[j])
            rs.append(float(round(r[j])))
    n = len(di)
    f = {"rs": np.array(rs), "d52h": np.full(n, -0.1), "om": np.full(n, 0.2), "roe": np.full(n, 0.2), "cap": np.full(n, 5e9),
         "om1": np.full(n, 0.2), "omd": np.zeros(n), "oxr": np.zeros(n)}
    cols = {"di": np.array(di), "j": np.array(jj), "c": np.array(cc), "d": np.array([cal[i] for i in di]), "f": f, "wk": wk}
    return {"P": P, "cal": cal, "T": T, "cols": cols, "D20": np.full((T, N), 1e12), "Cf": C.copy(), "DIV": np.zeros((T, N)),
            "MA": UF.roll_mean(C, X.QM_EXIT["ma"]), "yr": np.array([int(d[:4]) for d in cols["d"]]),
            "PQ": {"spx": {"idle": np.full(T, 0.0003), "cash": np.full(T, 0.0001)}}}


@pytest.fixture
def y0(monkeypatch):
    monkeypatch.setattr(X, "QM_Y0", 2025)
    return 2025


def test_mask_is_inclusive_and_missing_fails():
    f = {"rs": np.array([80, 79.9, 90, 90, np.nan]), "d52h": np.array([-0.25, 0, 0, 0, 0]),
         "om": np.array([0.10, 0.2, 0.2, np.nan, 0.2]), "roe": np.array([0.15, 0.2, 0.2, 0.2, 0.2]),
         "cap": np.array([2e9, 3e9, 1.99e9, 3e9, 3e9]),
         "om1": np.full(5, 0.2), "omd": np.zeros(5), "oxr": np.zeros(5)}
    assert QM.qm_mask(f).tolist() == [True, False, False, False, False]
    assert QM.qm_mask(f, {**X.QM, "cap": 1e9}).tolist() == [True, False, True, False, False]


def test_mask_drops_one_off_income_spikes():
    """VER 7（omfixspec 的 D）：上一季 < 10%、比上一季與去年同季都高 20 點以上、營業利益比營收多增加 → 不算；
    營收一起增加（真的轉盈）照算；任一個沒有值照算；fix=False＝VER 6 的條件（重現檢查用）。"""
    n = 5
    f = {"rs": np.full(n, 99.0), "d52h": np.zeros(n), "roe": np.full(n, 0.3), "cap": np.full(n, 5e9),
         "om": np.array([0.858, 0.654, 0.858, 0.858, 0.30]),          # CareDx、Moderna、沒有 oxr、上一季已經 ≥10%、小跳升
         "om1": np.array([0.010, -0.482, 0.010, 0.55, 0.05]),
         "omd": np.array([0.986, 16.25, 0.986, 0.986, 0.15]),
         "oxr": np.array([0.599, -0.275, np.nan, 0.5, 0.2])}
    assert QM.om_fix_block(f).tolist() == [True, False, False, False, False]
    assert QM.qm_mask(f).tolist() == [False, True, True, True, True]
    assert QM.qm_mask(f, fix=False).tolist() == [True] * 5


def test_signals_sorted_by_rs_then_code_and_drop(y0):
    cal = _cal("2024-12-02", "2025-03-28")
    C = _ctx(cal)
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    for i, v in sig.items():
        assert cal[i] >= "2025-01-01"
        rs = [s for _, s in v]
        assert rs == sorted(rs, reverse=True)
        for (j1, s1), (j2, s2) in zip(v, v[1:]):
            assert s1 > s2 or C["P"]["sym"][j1] < C["P"]["sym"][j2]
    sig2 = QM.signals(C, QM.qm_mask(C["cols"]["f"]), drop=frozenset({0}))
    assert all(j != 0 for v in sig2.values() for j, _ in v)


def test_week_done_uses_nyse_holidays():
    assert QM.week_done("2026-10-23") and not QM.week_done("2026-10-22")
    assert not QM.week_done("2026-11-25") and QM.week_done("2026-11-27")      # 感恩節那週：週三之後還有週五
    assert QM.week_done("2026-07-02")                                        # 7/3 休市：週四就是那一週最後一天
    assert QM.next_day("2026-12-24") == "2026-12-28"


def test_run_is_ussxbook_with_qm_settings(y0):
    cal = _cal("2024-11-01", "2025-09-30")
    C = _ctx(cal)
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    r = QM.run(C, sig)
    a = QM.a_of(cal, 2025)
    w = 1 / X.QM_SLOTS
    # VER 4：空位放現金、進出不付指數的成本
    r0 = BK.run(C["P"]["O"], C["Cf"], C["P"]["C"], C["P"]["last"], sig, a, C["T"], C["PQ"]["spx"]["cash"], ex={"ma": 50},
                style="trend", MA=C["MA"], D20=C["D20"], DIV=C["DIV"], weight=w, max_pos=8, max_weight=max(w, 0.20), c_idx=0.0)
    assert r["a"] == a and np.array_equal(r["eq"], r0["eq"]) and r["trades"] == r0["trades"]
    assert len(r["trades"]) > 0 and max(r["n"]) <= X.QM_SLOTS
    # VER 3 的設定（重現檢查用）：空位放指數、付指數的成本
    r3 = QM.run(C, sig, idle="index")
    r30 = BK.run(C["P"]["O"], C["Cf"], C["P"]["C"], C["P"]["last"], sig, a, C["T"], C["PQ"]["spx"]["idle"], ex={"ma": 50},
                 style="trend", MA=C["MA"], D20=C["D20"], DIV=C["DIV"], weight=w, max_pos=8, max_weight=max(w, 0.20))
    assert np.array_equal(r3["eq"], r30["eq"]) and r3["trades"] == r30["trades"]
    assert not np.array_equal(r["eq"], r3["eq"])


def test_snapshot_matches_state_and_trades(y0):
    cal = _cal("2024-11-01", "2025-09-30")
    C = _ctx(cal)
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    r = QM.run(C, sig)
    n = QM.snapshot(C, r, sig)
    T = C["T"]
    assert n["d"] == cal[-1] and n["next"] == QM.next_day(cal[-1])
    assert sorted(h["c"] for h in n["hold"]) == sorted(C["P"]["sym"][j] for j in r["state"]["pos"])
    h2 = {h["c"]: h for h in QM._held_at(C, r, T - 1)}
    for h in n["hold"]:
        assert h2[h["c"]]["ent"] == h["ent"] and h2[h["c"]]["w"] == pytest.approx(h["w"], rel=1e-9)
        assert h["epx"] == pytest.approx(h2[h["c"]]["epx"]) and h["px"] == pytest.approx(C["Cf"][T - 1, C["P"]["col"][h["c"]]] * 0.8)
    assert sum(h["w"] for h in n["hold"]) + n["idle"] == pytest.approx(1.0)
    # 最後一天（2025-09-30 週二）不是一週的最後一個交易日 → 名單還不算數、不列要買的
    assert not n["wk_done"] and n["buy"] == []


def test_snapshot_buys_fill_free_slots_on_week_end(y0):
    cal = _cal("2024-11-01", "2025-09-26")                                   # 最後一天是週五
    C = _ctx(cal)
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    r = QM.run(C, sig)
    n = QM.snapshot(C, r, sig)
    assert n["wk_done"] and n["wk"] == cal[-1]
    S = r["state"]
    free = X.QM_SLOTS - (len(S["pos"]) - len(S["pend"]))
    want = [C["P"]["sym"][j] for j, _ in sig[C["T"] - 1] if j not in S["pos"]][:free]
    assert n["buy"] == want


def test_snapshot_met_five_numbers_this_week_and_at_buy(y0):
    """docs/lab_cfg_v2_plan.md 第 4 節：美股個股卡「為什麼選它」——這一週（手上、要買、名單前 20 名）的五個條件，
    與手上的股票買進那一週（帳戶記的訊號日）的五個條件。"""
    cal = _cal("2024-11-01", "2025-09-26")
    C = _ctx(cal)
    C["cols"]["f"]["cap"] = C["cols"]["f"]["cap"] + 123456.0                  # 市值存到百萬美元
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    r = QM.run(C, sig)
    n = QM.snapshot(C, r, sig)
    cols = C["cols"]

    def row(i, c):
        k = next(k for k in range(len(cols["di"])) if cols["di"][k] == i and cols["c"][k] == c)
        f = cols["f"]
        return [round(f["rs"][k], 1), round(f["d52h"][k], 4), round(f["om"][k], 4), round(f["roe"][k], 4), 5e9]

    want = {h["c"] for h in n["hold"]} | set(n["buy"]) | {x["c"] for x in n["list"]}
    assert set(n["met"]) == want and n["wk"] == cal[-1]
    for c, v in n["met"].items():
        assert v == row(C["T"] - 1, c)
    assert sorted(n["met0"]) == sorted(h["c"] for h in n["hold"])
    for j, q in r["state"]["pos"].items():
        c = C["P"]["sym"][j]
        assert n["met0"][c] == {"wk": cal[q["si"]], "v": row(q["si"], c)} and q["si"] in sig
        assert n["met0"][c]["v"][0] >= X.QM["rs"]                            # 買進那一週五個條件都過


def test_live_update_records_finished_weeks_once(y0, monkeypatch):
    monkeypatch.setattr(X, "QM_LIVE", "2025-06-06")
    cal = _cal("2024-11-01", "2025-07-30")                                   # 7/30 週三：最後一週還沒結束
    C = _ctx(cal)
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    r = QM.run(C, sig)
    L = QM.live_update(C, r, sig, L=QM._empty_live(), made="2025-07-31")
    ws = sorted(L["weeks"])
    assert ws[0] == "2025-06-06" and ws[-1] == "2025-07-25" and all(QM.week_done(d) for d in ws)
    assert L["start"] == "2025-06-06" and L["weeks"]["2025-06-06"]["nav"] == pytest.approx(1.0)
    assert L["curve"]["d"][0] == "2025-06-06" and L["curve"]["d"][-1] == cal[-1]
    # 每一週的買賣都落在那一週
    for k, d in enumerate(ws[1:], 1):
        for t in L["weeks"][d]["trades"]:
            assert ws[k - 1] < t["d"] <= d
    # 同一份資料再跑一次：一模一樣、沒有差異紀錄
    import copy
    L2 = QM.live_update(C, r, sig, L=copy.deepcopy(L), made="2025-08-01")
    assert L2["weeks"] == L["weeks"] and not L2["diff"]
    # 已經記下的週被改過：不覆蓋，另記一筆差異
    L3 = copy.deepcopy(L)
    L3["weeks"]["2025-06-13"]["hold"] = []
    L3 = QM.live_update(C, r, sig, L=L3)
    assert L3["weeks"]["2025-06-13"]["hold"] == [] and any("2025-06-13" in x["what"] for x in L3["diff"])


def test_live_week_holdings_match_engine_state_at_that_close(y0, monkeypatch):
    """紀錄裡某一週的持股＝帳戶只跑到那一天收盤時的持股（由逐筆交易重建的和直接截斷重跑的一樣）。"""
    monkeypatch.setattr(X, "QM_LIVE", "2025-06-06")
    cal = _cal("2024-11-01", "2025-07-25")
    C = _ctx(cal)
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    r = QM.run(C, sig)
    L = QM.live_update(C, r, sig, L=QM._empty_live())
    for d in ("2025-06-20", "2025-07-11"):
        i = cal.index(d)
        rb = QM.run(C, sig, b=i + 1)
        assert sorted(h["c"] for h in L["weeks"][d]["hold"]) == sorted(C["P"]["sym"][j] for j in rb["state"]["pos"])
        assert sorted(L["weeks"][d]["sell_next"]) == sorted(C["P"]["sym"][j] for j in rb["state"]["pend"])


def _yahoo(ds, cs):
    return {"d": ds, "c": cs, "o": cs, "h": cs, "l": cs, "v": [1.0] * len(cs), "div": [], "spl": []}


def test_watch_one_trigger_after_standing_above():
    ds = _cal("2026-06-01", "2026-10-23")
    cs = [100 + k for k in range(len(ds))]                                   # 一路漲：一直在 50 日線上
    k0 = ds.index("2026-10-20")
    for k in range(k0, len(ds)):
        cs[k] = 100.0                                                        # 10/20 急跌到 50 日線下
    w = QM.watch_one({"c": "AAA", "above": False}, "2026-10-01", _yahoo(ds, cs))
    assert w["trig"] == "2026-10-20" and w["on"] == "2026-10-21" and w["pct"] < 0
    # 買進以後從來沒站上過均線：跌破不算
    w2 = QM.watch_one({"c": "BBB", "above": False}, "2026-10-19", _yahoo(ds, [200 - k * 0.5 for k in range(len(ds))]))
    assert w2["trig"] is None and not w2["above"]
    # 紀錄那天以前的跌破不算（帳已經處理過）：10/14 跌破一天、之後回到均線上
    cs3 = [100 + k for k in range(len(ds))]
    cs3[ds.index("2026-10-14")] = 100.0
    assert QM.watch_one({"c": "CCC", "above": True}, "2026-10-16", _yahoo(ds, cs3))["trig"] is None
    assert QM.watch_one({"c": "CCC", "above": True}, "2026-10-13", _yahoo(ds, cs3))["trig"] == "2026-10-14"
    assert QM.watch_one({"c": "DDD"}, "2026-10-01", None)["err"]


def test_watch_lists_sells_and_errors():
    ds = _cal("2026-06-01", "2026-10-23")
    up = [100 + k for k in range(len(ds))]
    dn = up[:-3] + [100.0] * 3
    data = {"UP": _yahoo(ds, up), "DN": _yahoo(ds, dn)}
    L = {"now": {"d": "2026-10-16", "hold": [{"c": "UP", "ent": "2026-09-01", "above": True},
                                             {"c": "DN", "ent": "2026-09-01", "above": True},
                                             {"c": "XX", "ent": "2026-09-01", "above": True}]}}
    W = QM.watch(L, fetch=lambda s, start: (s, data.get(s), "ok" if s in data else "404"), made="2026-10-24")
    assert [x["c"] for x in W["sell"]] == ["DN"] and W["sell"][0]["on"] == QM.next_day(W["sell"][0]["trig"])
    assert [e["c"] for e in W["err"]] == ["XX"] and W["d"] == "2026-10-23"


def test_review_percentile_and_low_flag():
    R = {"review": {str(k): {"q": [round(-0.3 + 0.006 * x, 5) for x in range(101)]} for k in X.QM_REVIEW}}
    n = max(X.QM_REVIEW) + 1
    L = {"curve": {"d": [f"d{k}" for k in range(n)], "nav": [1.0] * n, "spx": [1.0 + 0.001 * k for k in range(n)]}}
    out = QM.review_now(L, R)
    assert [x["k"] for x in out] == list(X.QM_REVIEW)
    for x in out:
        assert x["pct"] == pytest.approx(np.interp(x["ex"], R["review"][str(x["k"])]["q"], np.linspace(0, 1, 101)))
    assert out[-1]["low"] and out[-1]["ex"] < 0
    short = QM.review_now({"curve": {"d": ["a", "b"], "nav": [1, 1], "spx": [1, 1]}}, R)
    assert all(x["due"] is None for x in short)


def test_saved_research_reproduces_section_12_and_follows_the_verdict():
    """入庫的研究檔（scripts/run_ussx.py --qm）：照 VER 3 的設定重現第 12 節（ussxspec VER 4 ③）；
    VER 4 的設定（空位現金、核心＝corespec 的 core_of）算判定，換不換照判定。"""
    from arm.lab import corespec as CS
    R = QM.load()
    assert R and R["ver"] == X.VER and R["repro"]["ok"] and R["repro"]["set"] == X.QM_REPRO_SET
    assert abs(R["repro"]["cagr"] - X.QM_REF["cagr"]) <= X.QM_REPRO["cagr"]
    assert R["idle"] == X.QM_IDLE == "cash" and R["core"] == {mk: CS.core_of(mk) for mk in X.QM_PLANS}
    assert R["switch"] == {mk: bool(R["repro"]["ok"] and R["verdict"]["pass"][mk]) for mk in X.QM_PLANS}
    for mk in X.QM_PLANS:
        sc = R["sc"][mk]
        assert sc["key"] == "plan" and sc["sleeve"] == "qm" and sc["core"] == CS.core_of(mk)
        assert sc["plan"]["m"] > R["plans"][f"{mk}_main"]["cur"]["plan"]["m"]
    assert set(R["review"]) == {str(k) for k in X.QM_REVIEW}
