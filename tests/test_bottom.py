"""大跌後的買點與落底訊號（docs/lab_crash_plan.md 第 13 節）：和逐筆直接算的版本比對。"""
import math
import random
from datetime import date, timedelta

import numpy as np

from arm.lab import bottom as X
from arm.lab import bottomspec as S


def _walk(n=1500, seed=3, vol=0.016, drift=0.0002):
    rnd = random.Random(seed)
    px = [100.0]
    for _ in range(n - 1):
        px.append(px[-1] * math.exp(rnd.gauss(drift, vol)))
    return np.array(px)


def _cal(n, start=date(2001, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _series(n, seed, lo=0.0, hi=100.0, step=4.0, start=None):
    rnd = random.Random(seed)
    v, out = (lo + hi) / 2, []
    for i in range(n):
        v = min(hi, max(lo, v + rnd.gauss(0, step)))
        out.append(np.nan if start is not None and i < start else v)
    return np.array(out)


def _inputs(n=1500, seed=3, mk="tw"):
    px = _walk(n, seed)
    cal = _cal(n)
    rnd = random.Random(seed + 100)
    sig = {"vix": _series(n, seed + 1, 10, 60, 2.0), "mchg": _series(n, seed + 2, -0.25, 0.15, 0.02),
           "t5": _series(n, seed + 3, 0.2, 0.8, 0.05), "adv": np.array([rnd.random() for _ in range(n)]),
           "nl": _series(n, seed + 4, 0.0, 0.4, 0.02), "net": _series(n, seed + 5, -60000, 40000, 3000),
           "c5floor": 10000.0, "pc": _series(n, seed + 6, 50, 150, 8.0), "vol": _series(n, seed + 7, 1, 100, 6.0)}
    pc = sig["pc"]
    sig["pcma"] = np.array([pc[i - 19:i + 1].mean() if i >= 19 else np.nan for i in range(n)])
    return {"mk": mk, "cal": cal, "px": px, "fund": _series(n, seed + 8, start=80), "chip": _series(n, seed + 9, start=40),
            "bub": np.array([100.0 if (i // 200) % 4 == 1 else 0.0 for i in range(n)]),
            "bublv": np.array([float((i // 200) % 4) for i in range(n)]), "sig": sig}


# ── 事件 ─────────────────────────────────────────────────────────────────

def test_events_e5_matches_direct():
    for seed in (1, 2, 3):
        px = _walk(2000, seed, vol=0.02)
        ev = X.events_e5(px, 0.06)
        direct, last = [], -10 ** 9
        for i in range(5, len(px)):
            if px[i] / px[i - 5] - 1 <= -0.06 and i - last > 60:
                direct.append(i)
                last = i
        assert ev == direct and len(ev) > 3
        for a, b in zip(ev, ev[1:]):
            assert b - a > S.E5_GAP


def test_e10_segments_match_direct():
    for seed in (4, 5):
        px = _walk(2500, seed, vol=0.02)
        segs = X.e10_segments(px)
        direct, start = [], None
        for i in range(59, len(px)):
            h = max(px[i - 59:i + 1])
            dd = 1 - px[i] / h
            if start is None and dd >= 0.10:
                start = i
            elif start is not None and dd < 0.05:
                direct.append((start, i))
                start = None
        if start is not None:
            direct.append((start, None))
        assert segs == direct and len(segs) > 3
        for a, z in segs:                                    # 開始那天離 60 日高點 ≥ 10%，結束那天 < 5%
            assert 1 - px[a] / max(px[a - 59:a + 1]) >= 0.10
            if z is not None:
                assert 1 - px[z] / max(px[z - 59:z + 1]) < 0.05


def test_peak_buy_out_recovery_match_direct():
    px = _walk(1200, 9, vol=0.02)
    for t in (100, 300, 555, 900):
        p = X.peak_of(px, t)
        w = list(px[t - 59:t + 1])
        m = max(w)
        assert p == t - 59 + max(i for i, v in enumerate(w) if v == m)
        for b in (t + 1, t + 10, t + 37):
            o = X.buy_out(px, p, b)
            assert math.isclose(o["r60"], px[b + 60] / px[b] - 1)
            assert math.isclose(o["r20"], px[b + 20] / px[b] - 1)
            ref = min(px[p:b + 1])
            assert o["nl"] == int(min(px[b + 1:b + 21]) < ref)
            assert math.isclose(o["mae"], max(0.0, 1 - min(px[b + 1:b + 61]) / px[b]))
        rec, fu = X.recovery(px, t, p)
        direct = next((u - t for u in range(t + 1, len(px)) if px[u] >= px[p]), None)
        assert rec == direct and fu == len(px) - 1 - t
    o = X.buy_out(px, X.peak_of(px, 1150), 1170)            # 1170＋20 還在資料內、＋60 超出＝沒有值
    assert o.get("r60") is None and o.get("nl") is not None and o.get("mae") is None


# ── 訊號 ─────────────────────────────────────────────────────────────────

def _direct_signal(k, sig, px, t, end):
    """逐日照規格直接判斷（不共用 bottom.first_signal 的程式）。"""
    end = min(end, len(px) - 1)

    def ok(x):
        return x is not None and not math.isnan(x)
    need = {"C1": "vix", "C2": "mchg", "C3": "t5", "C4": "nl", "C5": "net", "C6": "pc", "C7": "vol", "C8": "adv"}[k]
    if not ok(sig[need][t]) or (k == "C6" and not ok(sig["pcma"][t])):
        return "na"
    for s in range(t + 1, end + 1):
        if k == "C1":
            hi = max(v for v in sig["vix"][t:s + 1] if ok(v))
            if ok(sig["vix"][s]) and sig["vix"][s] <= 0.8 * hi:
                return s
        elif k == "C2":
            if ok(sig["mchg"][s]) and sig["mchg"][s] <= -0.10:
                return s
        elif k == "C3":
            v = sig["t5"]
            if ok(v[s]) and v[s] >= 0.615 and any(ok(u) and u <= 0.40 for u in v[max(0, s - 10):s]):
                return s
        elif k == "C4":
            v = sig["nl"]
            hi = max(u for u in v[t:s + 1] if ok(u))
            if ok(v[s]) and hi >= 0.05 and v[s] <= 0.5 * hi:
                return s
        elif k == "C5":
            v = sig["net"]
            hi = max([0.0] + [-u for u in v[t:s + 1] if ok(u)])
            if ok(v[s]) and hi >= sig["c5floor"] and -v[s] <= 0.7 * hi:
                return s
        elif k == "C6":
            v, ma = sig["pc"], sig["pcma"]
            was = any(ok(v[u]) and ok(ma[u]) and v[u] > ma[u] for u in range(t, s))
            if ok(v[s]) and ok(ma[s]) and was and v[s] < ma[s]:
                return s
        elif k == "C7":
            seg = px[t:s + 1]
            m = t + max(i for i, v in enumerate(seg) if v == min(seg))
            vol = sig["vol"]
            if (s - m >= 4 and px[s] / px[s - 1] - 1 >= 0.0125 and ok(vol[s]) and ok(vol[s - 1])
                    and vol[s] > vol[s - 1]):
                return s
        elif k == "C8":
            if ok(sig["adv"][s]) and sig["adv"][s] >= 0.90:
                return s
    return None


def test_signals_match_direct():
    hits = {k: 0 for k in S.SIGNALS}
    for seed in (3, 8, 13):
        I = _inputs(1500, seed)
        I["sig"]["vix"][700:705] = np.nan                     # 中間缺幾天：那幾天不成立
        I["sig"]["net"][400] = np.nan                         # 事件那天沒有值＝na
        px = I["px"]
        for t in range(25, 1400, 7):
            for k in S.SIGNALS:
                a = X.first_signal(k, I["sig"], px, t, t + S.SIG_WIN)
                b = _direct_signal(k, I["sig"], px, t, t + S.SIG_WIN)
                assert a == b, (seed, t, k, a, b)
                if isinstance(a, int):
                    hits[k] += 1
    assert all(v > 3 for v in hits.values()), hits          # 每個訊號都真的有出現過（測試有測到東西）


def test_rule_buy_and_lag():
    I = _inputs(800, 4)
    s, b = X.rule_buy("W10", I["sig"], I["px"], 100)
    assert (s, b) == (109, 110)
    for k in S.SIGNALS:
        s, b = X.rule_buy(k, I["sig"], I["px"], 100)
        if isinstance(s, int):
            assert b == s + S.LAG and 100 < s <= 100 + S.SIG_WIN
        else:
            assert b is None


def test_groups_at():
    I = _inputs(600, 5)
    I["fund"][:] = np.nan
    I["fund"][200], I["fund"][200 - 63] = 55.0, 50.0
    I["fund"][300], I["fund"][300 - 63] = 55.0, 60.0
    I["fund"][400], I["fund"][400 - 63] = 45.0, 40.0
    I["chip"][:] = 50.0
    I["chip"][190] = 85.0                                   # 事件前第 10 天過熱
    I["chip"][300] = 90.0                                   # 事件當天過熱不算（只看事件前 20 天）
    g, v = X.groups_at(I, 200)
    assert g["fund"] == 1 and g["chip"] == 1 and v["chip"] == 85.0
    g, _ = X.groups_at(I, 300)
    assert g["fund"] == 0 and g["chip"] == 0
    g, _ = X.groups_at(I, 400)
    assert g["fund"] == 0
    g, _ = X.groups_at(I, 500)
    assert g["fund"] is None
    I["bublv"][200], I["bublv"][300] = 2.0, 1.0
    assert X.groups_at(I, 200)[0]["bub"] == 1 and X.groups_at(I, 300)[0]["bub"] == 0
    del I["bublv"]
    I["bub"][200] = 100.0
    assert X.groups_at(I, 200)[0]["bub"] == 1


# ── 重抽 ─────────────────────────────────────────────────────────────────

def test_cboot_counts_match_direct_blocks():
    pos = np.array([3, 40, 41, 150, 299, 300, 512, 600])
    lo, hi, L, B = 3, 600, 100, 50
    C = X.cboot_counts(pos, lo, hi, L=L, n_boot=B, seed=7)
    n = hi - lo + 1
    k = math.ceil(n / L)
    st = np.random.default_rng(7).integers(0, n, size=(B, k))
    for b in range(B):
        cover = [0] * n
        for j in range(k):
            for off in range(L):
                cover[(st[b, j] + off) % n] += 1
        assert list(C[b]) == [cover[p - lo] for p in pos]
    assert X.cboot_counts(pos, 0, 150, L=100) is None      # 天數不到 2 塊


def test_paired_and_two_group_point_and_halves():
    rnd = random.Random(2)
    pos = np.array(sorted(rnd.sample(range(5000), 30)))
    d = np.array([rnd.gauss(0.01, 0.05) for _ in pos])
    r = X.paired(pos, d)
    assert math.isclose(r["d"], d.mean())
    assert math.isclose(r["h1"], d[:15].mean()) and math.isclose(r["h2"], d[15:].mean())
    assert r["lo"] < r["d"] < r["hi"] and 0 < r["p"] <= 1
    g = np.array([1 if i % 3 == 0 else 0 for i in range(30)])
    y = np.array([rnd.gauss(0.02 if gg else -0.01, 0.05) for gg in g])
    r = X.two_group(pos, g, y)
    assert math.isclose(r["d"], y[g == 1].mean() - y[g == 0].mean())
    h1 = y[:15][g[:15] == 1].mean() - y[:15][g[:15] == 0].mean()
    assert math.isclose(r["h1"], h1)
    assert r["lo"] is not None and r["lo"] < r["hi"]


def test_pool_stat_matches_direct():
    rnd = random.Random(4)
    mm = np.array([0] * 20 + [1] * 30)
    gg = np.array([rnd.random() < 0.4 for _ in range(50)]).astype(int)
    yy = np.array([rnd.gauss(0, 1) for _ in range(50)])
    one = np.ones((1, 50), dtype=np.int64)
    num = den = 0.0
    for m in (0, 1):
        a, b = (mm == m) & (gg == 1), (mm == m) & (gg == 0)
        num += a.sum() * (yy[a].mean() - yy[b].mean())
        den += a.sum()
    assert math.isclose(X.pool_stat(one, mm, gg, yy)[0], num / den)
    C = np.zeros((1, 50), dtype=np.int64)
    C[0, :20] = 2                                           # 只抽到第一個市場（各算兩次）
    a, b = (mm == 0) & (gg == 1), (mm == 0) & (gg == 0)
    assert math.isclose(X.pool_stat(C, mm, gg, yy)[0], yy[a].mean() - yy[b].mean())


def test_verdicts():
    base = {"few": False, "nl_lo": -0.3, "nl_hi": -0.05, "nl_h1": -0.2, "nl_h2": -0.1, "nl_q": 0.05,
            "r_d": 0.01, "r_lo": -0.02, "r_hi": 0.04, "r_h1": 0.0, "r_h2": 0.02, "r_q": 0.5}
    assert X.rule_verdict(base) == "better"
    assert X.rule_verdict({**base, "r_h1": -0.01}) == "none"
    assert X.rule_verdict({**base, "r_d": -0.03, "r_lo": -0.06, "r_hi": -0.01, "r_h1": -0.02, "r_h2": -0.04,
                           "r_q": 0.02}) == "trade"
    assert X.rule_verdict({**base, "nl_q": 0.2}) == "none"
    assert X.rule_verdict({**base, "nl_lo": 0.05, "nl_hi": 0.3, "nl_h1": 0.1, "nl_h2": 0.2}) == "worse"
    assert X.rule_verdict({**base, "nl_q": 0.5, "r_d": -0.03, "r_lo": -0.06, "r_hi": -0.01, "r_h1": -0.02,
                           "r_h2": -0.04, "r_q": 0.02}) == "worse"
    assert X.rule_verdict({**base, "few": True}) == "few"
    g = {"few": False, "lo": 0.01, "hi": 0.05, "h1": 0.02, "h2": 0.03, "q": 0.05}
    assert X.group_verdict(g) == "up"
    assert X.group_verdict({**g, "lo": -0.05, "hi": -0.01, "h1": -0.02, "h2": -0.03}) == "down"
    assert X.group_verdict({**g, "h2": -0.01}) == "none"
    assert X.group_verdict({**g, "q": 0.2}) == "none"


def test_desc_recovery_shares():
    recs = [{"rec": 30, "fu": 1000, "b1": {}}, {"rec": 100, "fu": 900, "b1": {}}, {"rec": None, "fu": 400, "b1": {}},
            {"rec": None, "fu": 70, "b1": {}}, {"rec": 50, "fu": 55, "b1": {}}]
    d = X.desc(recs)
    r = d["rec"]
    # 60 天：可判斷的 5 個（最後一個 50 天就回到；第 4 個觀察了 70 天沒回到）；回到的 2 個
    assert r["60"]["n"] == 5 and math.isclose(r["60"]["share"], 2 / 5)
    # 120 天：第 4 個觀察不夠（70 天）不算；回到的 3 個／4 個
    assert r["120"]["n"] == 4 and math.isclose(r["120"]["share"], 3 / 4)
    # 250 天：第 3 個觀察 400 天沒回到；可判斷 4 個（30、100、∞、50）→ 中位數 (50＋100)÷2
    assert r["250"]["n"] == 4 and r["med"] == 75.0 and r["gt"] is False
    d = X.desc([{"rec": None, "fu": 500, "b1": {}}, {"rec": 300, "fu": 900, "b1": {}}, {"rec": 20, "fu": 900, "b1": {}}])
    assert d["rec"]["med"] is None and d["rec"]["gt"] is True


# ── 一個市場 ──────────────────────────────────────────────────────────────

def test_market_runs_and_is_consistent():
    I = _inputs(3000, 21)
    I["px"] = _walk(3000, 21, vol=0.022)
    M = X.market(I)
    for ev in S.EVENTS:
        E = M["ev"][ev]
        assert E["n"] == len(E["list"]) > 5
        for k, st in E["rules"].items():
            assert st["v"] in S.VERDICT
            if st["n"]:
                assert 0 <= st["nl_rule"] <= 1 and st["fired"] <= st["seen"] <= st["elig"]
        for g, st in E["groups"].items():
            assert st["v"] in S.GVERDICT
    # 事件隔天買的 R60 平均＝清單逐筆平均
    lst = M["ev"]["E5"]["list"]
    r60 = [r["r60"] for r in lst if r["r60"] is not None]
    assert math.isclose(M["ev"]["E5"]["all"]["r60"]["mean"], float(np.mean(r60)))


def test_now_active_events():
    I = _inputs(800, 6)
    px = np.array([100.0] * 700 + [100 * (0.985 ** i) for i in range(1, 101)])   # 最後 100 天一路跌
    I["px"] = px
    N = X.now(I)
    kinds = [a["ev"] for a in N["active"]]
    assert "E10" in kinds and N["dd60"] < -0.10
    a = next(x for x in N["active"] if x["ev"] == "E10")
    assert a["p"] == I["cal"][699] and a["nowdd"] < -0.2
    assert set(a["sig"]) == set(S.SIG_MK["tw"])
    I["px"] = np.array([100.0 * (1.0002 ** i) for i in range(800)])
    N = X.now(I)
    assert N["active"] == [] and N["last"]["E5"] is None
