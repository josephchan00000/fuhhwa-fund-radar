"""計算正確性的兩道核對（docs/lab_signal_quality_plan.md 第 5、8 節，A 段）：
第二套算法（arm/lab/sigverify.py）——手算的例子對、亂數資料上和網頁用的程式一樣、整個市場的比對抓得到故意改壞的地方；
截斷重建（arm/lab/truncheck.py）——截斷規則對、抓得到「當時還拿不到的資料」、乾淨的不會誤報。"""
from datetime import date, timedelta

import numpy as np

from arm.lab import heat as H
from arm.lab import heattech as TT
from arm.lab import hotch as HCH
from arm.lab import hotdd as HDD
from arm.lab import sigcat as G
from arm.lab import sigspec as S
from arm.lab import sigverify as V
from arm.lab import truncheck as TC
from arm.lab.heatrel import heat_events


def _cal(T):
    d, out = date(2001, 1, 1), []
    while len(out) < T:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _we(cal):
    return [i for i in range(len(cal)) if i == len(cal) - 1 or
            date.fromisoformat(cal[i + 1]).isocalendar()[:2] != date.fromisoformat(cal[i]).isocalendar()[:2]]


def _walk(rng, T, head=40, holes=5):
    """0～100、會回到 50 的隨機走勢（常常進出過熱、過冷），開頭沒有值、中間幾個洞。"""
    x = np.empty(T)
    v = 50.0
    for t in range(T):
        v = min(100.0, max(0.0, 50 + 0.985 * (v - 50) + rng.normal(0, 5)))
        x[t] = v
    x[:head] = np.nan
    x[rng.choice(np.arange(head, T), size=holes, replace=False)] = np.nan
    return x


def _px(rng, T):
    return 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, T)))


# ── 手算的例子 ────────────────────────────────────────────────────────────────

def test_hand_examples():
    x = np.array([50.0] * 20 + [85.0, 90.0])
    assert V._zone_events(x, "hot") == [20]                        # 前 20 天都有值而且 < 80，今天 ≥ 80
    x[3] = np.nan
    assert V._zone_events(x, "hot") == []                           # 前 20 天有一天沒有值
    w = np.array([85.0, 85.0, 85.0, 85.0, 70.0, 85.0, 85.0, 85.0, 70.0])
    we = list(range(len(w)))
    assert V._exits(w, we, True) == [4]                             # 連 4 週之後離開；只連 3 週不算
    w2 = np.array([85.0, 85.0, np.nan, 85.0, 85.0, 70.0])
    assert V._exits(w2, list(range(6)), True) == []                 # 沒有值的週末讓週數歸零
    amt = np.array([1.0, -1, -1, -1, 1, -1, -1, -1, -1, np.nan, -1])
    assert V._runs(amt, -1, 3) == [3, 7]                            # 第 3 天連續才算一次，同一段不重複
    p = np.array([100.0, 100.0 + 1e-13, 99.0, np.nan])
    q = np.array([100.0, 100.0, 100.0, 100.0])
    assert V._side(p, q) == [0, 0, -1, None]                        # 浮點誤差＝相等
    s = V._sma(np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0]), 2)
    assert np.isnan(s[0]) and s[1] == 1.5 and np.isnan(s[2]) and np.isnan(s[3]) and s[4] == 4.5 and s[5] == 5.5
    px = np.array([100.0, 100.0, 110.0, 99.0, 105.0, 104.0])        # LAG＝1：第 t 天的訊號第 t＋1 天收盤進場
    up, wn = V.outcomes(px, 3, 0.08)
    assert S.LAG == 1 and up[0] == 1.0 and wn[0] == 1.0             # 100→105 上漲；110→99 跌 10% ≥ 8%
    assert up[1] == 0.0 and wn[1] == 1.0                            # 110→104
    assert np.isnan(up[2]) and np.isnan(wn[2])                      # 窗口還沒走完
    assert V._dedupe([5, 6, 30, 31, 52], 20) == [5, 30, 52]


# ── 亂數資料上和網頁用的程式一樣 ──────────────────────────────────────────────

def test_detectors_match_production_on_random_series():
    for seed in range(6):
        rng = np.random.default_rng(seed)
        T = 1200
        cal = _cal(T)
        we = _we(cal)
        x = _walk(rng, T)
        xl = G._lst(x)
        for k in ("hot", "cold"):
            assert V._zone_events(x, k) == heat_events(xl, k)
        assert V._exits(x, we, True) == HDD.exits(xl, we, S.EXIT_MIN)
        assert V._exits(x, we, False) == G.cold_exits(xl, we, S.EXIT_MIN)
        a, b = V._streak13(x, we), HCH.streak_days(xl, we)
        assert all((np.isnan(u) and v is None) or u == v for u, v in zip(a, b))
        amt = rng.normal(0, 1, T)
        amt[rng.choice(T, 20, replace=False)] = np.nan
        for sign in (-1, 1):
            for n in S.INST_RUN:
                assert V._runs(amt, sign, n) == G.run_days(amt, sign, n)


def test_outcomes_dedupe_and_tech_match_production():
    for seed in range(4):
        rng = np.random.default_rng(100 + seed)
        T = 1500
        px = _px(rng, T)
        px[rng.choice(np.arange(300, T), 6, replace=False)] = np.nan
        for h in (20, 60):
            th = G.warn_th("spx", h)
            u1, w1 = V.outcomes(px, h, th)
            u2, w2, _ = G.outcomes(px, h, th)
            assert np.array_equal(np.isnan(u1), np.isnan(u2)) and np.allclose(np.nan_to_num(u1), np.nan_to_num(u2))
            assert np.allclose(np.nan_to_num(w1), np.nan_to_num(w2))
        days = sorted(rng.choice(T, 80, replace=False).tolist())
        assert V._dedupe(days, 20) == G.dedupe(days, 20)
        px = _px(rng, T)                                            # 技術事件：沒有洞的收盤
        ev = TT.all_events([float(p) for p in px])
        for sd in V._tech("spx", px):
            k = sd["id"].split(":")[2]
            assert sd["days"] == [t for t in ev[k] if t >= S.EV_START], k


# ── 整個市場的比對 ────────────────────────────────────────────────────────────

def _frame(mk="spx", T=1600, seed=7):
    """一個市場的人工 frame（sigcat.frame 的欄位）：景氣項目、大跌風險項目、面向、法人、邊際變化、泡沫月資料。"""
    rng = np.random.default_rng(seed)
    cal = _cal(T)
    dims = ["fund", "liq", "tech", "sent"] if mk != "tw" else ["fund", "chip", "gliq", "tliq", "tech"]
    var = lambda k, grp, H=60: {"key": k, "name": k, "grp": grp, "H": H, "x": _walk(rng, T)}
    F = {"mk": mk, "cal": cal, "px": _px(rng, T), "we": _we(cal), "dims": dims,
         "comp": {d: _walk(rng, T) for d in dims},
         "vars": [var("A1", "fund"), var("B2", "liq")], "cvars": [var("W1", "crash", 120)], "bvars": [var("BD1", "bd")],
         "deriv": [{"key": "A1", "name": "A1", "kind": "grow",
                    "x": rng.integers(1, 5, T).astype(float), "have": np.r_[np.zeros(60, bool), np.ones(T - 60, bool)]}],
         "deriv_words": {"grow": ["加速", "趨緩", "加劇", "收斂"]}, "IB": None, "ivars": []}
    if mk == "tw":
        F["ivars"] = [{"key": "fi20", "who": "fi", "w": 20, "name": "外資 20 日", "H": 60, "x": _walk(rng, T)},
                      {"key": "fi1", "who": "fi", "w": 1, "name": "外資單日", "H": 20,
                       "x": rng.uniform(0, 100, T), "amt": rng.normal(0, 1, T)}]
    me = {}
    for i, d in enumerate(cal):
        me[d[:7]] = d
    F["bub"] = [{"d": d, "L": int(rng.integers(0, 5)), **{k: bool(rng.random() < 0.3) for k in ("P1", "P2", "P3", "E", "G", "F", "V")}}
                for d in list(me.values())[:-1]]
    return F


def test_check_market_agrees_on_synthetic_frames():
    for mk in ("spx", "tw"):
        r = V.check_market(_frame(mk))
        assert r["bad"] == [], r["bad"][:5]
        assert r["checked"] == r["n"] - len(r["skip"]) and r["checked"] >= 50
        assert all(s.split(":")[2] in V.TECH_SKIP for s in r["skip"])


def test_check_market_catches_a_broken_detector(monkeypatch):
    """故意把第二套的「過熱結束」改成晚一週：比對一定要報出來（證明比對不是空轉）。"""
    real = V._exits
    monkeypatch.setattr(V, "_exits", lambda x, we, hot: [we[we.index(i) + 1] for i in real(x, we, hot) if i != we[-1]])
    bad = V.check_market(_frame("spx"))["bad"]
    assert any(b[0].endswith(":hot_out") and b[1] == "出現日不同" for b in bad)


# ── 截斷重建 ──────────────────────────────────────────────────────────────────

def test_cut_rules():
    D = {"2025-11-10": 1, "2025-11-30": 2, "2025-09": 3, "2025-10": 4, "2025-11": 5, "2025-Q3": 6, "2024": 7, "note": 8}
    c = TC.cut(D, "2025-11-20", (1, 16))
    assert set(c) == {"2025-11-10", "2025-09", "2025-10", "2025-Q3", "2024", "note"}   # 10 月 11/16 公布、11 月 12/16
    assert set(TC.cut(D, "2025-11-20")) == {"2025-11-10", "2025-09", "2025-10", "2025-Q3", "2024", "note"}
    assert "2025-10" not in TC.cut(D, "2025-11-15", (1, 16))
    assert TC.cut([1, 2], "2025-01-01") == [1, 2]
    q = TC.cut_q({"2025-Q3": 1, "2025-Q4": 2, "x": 3}, "2025-09-01")                  # 第 3 季調查 8/31 公布
    assert set(q) == {"2025-Q3", "x"}


def _toy(ser, cal, leak):
    """月資料 → 每天拿得到的最新一個月（公布時間差 (1, 16)）。leak＝缺一個月時用前後兩個月平均補，
    而且補出來的月份照它自己的月份算公布日（補值其實要等下一個月公布才有）。"""
    s = dict(ser)
    if leak:
        ks = sorted(s)
        for a, b in zip(ks, ks[1:]):
            m = f"{int(a[:4]) + int(a[5:]) // 12:04d}-{int(a[5:]) % 12 + 1:02d}"
            if m < b:
                s[m] = (s[a] + s[b]) / 2
    return {"cal": cal, "hc": {"X": H.asof_monthly(cal, s, (1, 16))}, "comp": {}}


def test_truncation_flags_value_known_only_later():
    cal = [(date(2025, 8, 1) + timedelta(days=i)).isoformat() for i in range(200)]
    ser = {"2025-07": 100.0, "2025-08": 101.0, "2025-10": 105.0, "2025-11": 106.0}    # 9 月缺
    day = "2025-10-20"                                                               # 9 月本來 10/16 公布、10 月要到 11/16
    for leak in (False, True):
        full = _toy(ser, cal, leak)
        cut = _toy(TC.cut(ser, day, (1, 16)), [d for d in cal if d <= day], leak)
        r = TC.compare(full, cut, day)
        if leak:
            assert r["bad"] and r["bad"][0][0] == "hc:X" and r["bad"][0][1] == "2025-10-16"
        else:
            assert r["bad"] == [] and r["items"] == 1


def test_compare_bub_rows():
    rows = [{"d": "2025-09-30", "L": 1, "P1": True}, {"d": "2025-10-31", "L": 2, "P1": False},
            {"d": "2025-11-28", "L": 3, "P1": True}]
    Xf = {"spx": {"_C": {"rows": rows}}}
    same = TC.compare_bub(Xf, {"spx": {"_C": {"rows": [dict(r) for r in rows[:2]]}}}, "2025-11-15")
    assert same["spx"] == {"rows": 2, "bad": []}                                      # 11 月底在截斷之後，不比
    diff = TC.compare_bub(Xf, {"spx": {"_C": {"rows": [rows[0], {**rows[1], "L": 1}]}}}, "2025-11-15")
    assert diff["spx"]["bad"] == [["2025-10-31", ["L"]]]
    gone = TC.compare_bub(Xf, {"spx": {"_C": {"rows": rows[:1]}}}, "2025-11-15")
    assert gone["spx"]["bad"] == [["2025-10-31", "截斷之後沒有這個月"]]


def test_cut_frame_slices_and_drops_unfinished_week():
    F = _frame("spx", T=300)
    F["IB"] = {"cal": list(F["cal"]), "px": F["px"].copy(), "sig": {"vix": np.arange(300.0), "c5floor": 12.0}}
    day = next(d for d in F["cal"][200:] if date.fromisoformat(d).weekday() == 2)    # 星期三：那一週還沒過完
    c = F["cal"].index(day) + 1
    G2 = TC.cut_frame(F, day)
    assert G2["cal"][-1] == day and len(G2["px"]) == c and len(G2["vars"][0]["x"]) == c
    assert len(G2["comp"]["fund"]) == c and len(G2["IB"]["sig"]["vix"]) == c and G2["IB"]["sig"]["c5floor"] == 12.0
    assert G2["we"] and G2["we"][-1] < c - 1 and set(G2["we"]) <= set(F["we"])
    assert all(r["d"] <= day for r in G2["bub"])
    assert G2["vars"][0]["key"] == F["vars"][0]["key"] and len(F["px"]) == 300                # 原本的不動


def test_sig_check_clean_and_catches_peeking(monkeypatch):
    F = _frame("spx")
    real = HDD.exits
    x, we = G._lst(F["vars"][0]["x"]), F["we"]
    nxt = dict(zip(we, we[1:]))
    ev = [i for i in real(x, we, S.EXIT_MIN) if i in nxt and nxt[i] < len(x) - 1 and not x[nxt[i]] >= S.HOT]
    assert ev
    day = F["cal"][ev[0]]                                           # 截在一個「過熱結束」的週末
    assert TC.sig_check(F, day)["bad"] == []

    def peek(x, we, n=S.EXIT_MIN):                                  # 故意偷看：下一個週末也不在過熱才算結束
        nx = dict(zip(we, we[1:]))
        return [i for i in real(x, we, n) if i in nx and not (x[nx[i]] is not None and x[nx[i]] >= S.HOT)]
    monkeypatch.setattr(HDD, "exits", peek)
    bad = TC.sig_check(F, day)["bad"]
    assert any(b[0].endswith(":hot_out") for b in bad)
