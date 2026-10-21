"""大跌後的買點與落底訊號（docs/lab_crash_plan.md 第 13、16、17 節）：和逐筆直接算的版本比對。"""
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
           "c5floor": 10000.0, "pc": _series(n, seed + 6, 50, 150, 8.0), "vol": _series(n, seed + 7, 1, 100, 6.0),
           "mr": _series(n, seed + 10, 110.0, 200.0, 4.0)}
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
    need = {"C1": "vix", "C2": "mchg", "C3": "t5", "C4": "nl", "C5": "net", "C6": "pc", "C7": "vol", "C8": "adv",
            "C9": "mr"}[k]
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
        elif k == "C9":                                       # 事件那天起到前一天有一天 < 140%，當天 ≥ 150%
            v = sig["mr"]
            if ok(v[s]) and v[s] >= 150.0 and any(ok(u) and u < 140.0 for u in v[t:s]):
                return s
    return None


def test_signals_match_direct():
    hits = {k: 0 for k in S.SIGNALS}
    for seed in (3, 8, 13):
        I = _inputs(1500, seed)
        I["sig"]["vix"][700:705] = np.nan                     # 中間缺幾天：那幾天不成立
        I["sig"]["net"][400] = np.nan                         # 事件那天沒有值＝na
        I["sig"]["mr"][300:340] = np.nan                      # 融資維持率缺一段
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


def test_ver2_signals_are_judged_against_w10():
    """VER 2：訊號的判定和固定等 10 天比（同一個事件、兩個買進日的 NL20 與 R60 都有）；BH 家族只有訊號；
    固定等 10 天照 VER 1（和事件隔天買比）；訊號和事件隔天買比的判定留作 v1。"""
    I = _inputs(3000, 21)
    I["px"] = _walk(3000, 21, vol=0.022)
    M = X.market(I)
    for ev in S.EVENTS:
        recs = X.event_recs(I, ev)
        rs = M["ev"][ev]["rules"]
        assert "w10" not in rs["W10"] and rs["W10"]["v2"] == rs["W10"]["v1"] == X.rule_verdict(rs["W10"])
        for k in S.SIG_MK["tw"]:
            st, w = rs[k], rs[k]["w10"]
            rows = []
            for r in recs:
                o, ob = r["rules"][k].get("o") or {}, r["rules"]["W10"].get("o") or {}
                if None not in (o.get("nl"), o.get("r60"), ob.get("nl"), ob.get("r60")):
                    rows.append((o["nl"] - ob["nl"], o["r60"] - ob["r60"], o["nl"], ob["nl"], o["r60"], ob["r60"]))
            assert w["n"] == len(rows)
            if rows:
                a = np.array(rows, dtype=float)
                assert math.isclose(w["nl_d"], a[:, 0].mean(), abs_tol=1e-12)
                assert math.isclose(w["r_d"], a[:, 1].mean(), abs_tol=1e-12)
                assert math.isclose(w["nl_rule"], a[:, 2].mean()) and math.isclose(w["nl_w10"], a[:, 3].mean())
                assert math.isclose(w["r_rule"], a[:, 4].mean()) and math.isclose(w["r_w10"], a[:, 5].mean())
                h = len(rows) // 2
                if h:
                    assert math.isclose(w["nl_h1"], a[:h, 0].mean(), abs_tol=1e-12)
                    assert math.isclose(w["r_h2"], a[h:, 1].mean(), abs_tol=1e-12)
            assert w["few"] == (w["n"] < S.MIN_N or w["ep"] < S.MIN_EP or w.get("nl_lo") is None or w.get("r_lo") is None)
            assert st["v2"] == w["v"] == X.rule_verdict(w) and st["v1"] == X.rule_verdict(st)
            assert (w["nl_dir"], w["r_dir"], st["nl_dir"], st["r_dir"]) == (
                X.sdir(w, "nl"), X.sdir(w, "r"), X.sdir(st, "nl"), X.sdir(st, "r"))
        for pre in ("nl", "r"):                               # BH：只有訊號一起校正（固定等 10 天是對照）；VER 4 新訊號另一個家族
            for fam in ([k for k in S.SIG_MK["tw"] if k not in S.SIG_ADD4["tw"]], list(S.SIG_ADD4["tw"])):
                ks = [k for k in fam if not rs[k]["w10"]["few"] and rs[k]["w10"].get(f"{pre}_p") is not None]
                for k, q in zip(ks, X.bh([rs[k]["w10"][f"{pre}_p"] for k in ks])):
                    assert rs[k]["w10"][f"{pre}_q"] == q
                for k in set(fam) - set(ks):
                    assert f"{pre}_q" not in rs[k]["w10"]


def _direct_wave(px, t, p):
    T, P = len(px), px[p]
    r = next((u for u in range(t + 1, T) if px[u] >= P), None)
    if r is not None and r <= t + S.WAVE_H:
        end = r
    elif t + S.WAVE_H <= T - 1:
        end = t + S.WAVE_H
    else:
        return None
    return min(px[p:end + 1]), end


def test_wave_position_lp_match_direct():
    for seed in (4, 5, 6):
        I = _inputs(2600, seed)
        I["px"] = _walk(2600, seed, vol=0.021)
        px = I["px"]
        for ev in S.EVENTS:
            for r in X.event_recs(I, ev):
                t, p = r["t"], r["p"]
                w = _direct_wave(px, t, p)
                assert (X.wave(px, t, p) is None) == (w is None)
                for k, b in [("b1", t + S.LAG)] + [(k, (rr.get("o") or {}).get("b")) for k, rr in r["rules"].items()]:
                    o = r["b1"] if k == "b1" else (r["rules"][k].get("o") or {})
                    if b is None or not o:
                        continue
                    if w is None or b >= len(px):
                        assert o.get("pos") is None and o.get("lp") is None
                        continue
                    lo, end = w
                    pos = (px[b] - lo) / (px[p] - lo)
                    assert math.isclose(o["pos"], pos, abs_tol=1e-12)
                    assert o["lp"] == int(b <= end and pos <= 1 / 3)
                    assert math.isclose(o["reb"], px[b] / min(px[p:b + 1]) - 1, abs_tol=1e-12)
    # 手算：100 跌到 80 買在 86 → 下三分之一；之後又跌到 70 → 不算；回到前高之後才買 → 不算；這一波還沒結束 → 沒有值
    base = [100.0] * 60 + [95.0, 90.0, 85.0, 82.0, 80.0, 84.0, 86.0, 87.0, 88.0, 90.0]
    px = np.array(base + [91.0] * 130)
    w = X.wave(px, 64, 59)
    assert w == (80.0, 64 + S.WAVE_H)
    assert X.position(px, 59, 66, w) == (0.3, 1) and X.position(px, 59, 69, w) == (0.5, 0)
    px2 = np.array(base[:67] + [75.0, 70.0] + [91.0] * 130)
    w2 = X.wave(px2, 64, 59)
    assert w2[0] == 70.0 and X.position(px2, 59, 66, w2)[1] == 0          # 86 之後跌到 70：位置 0.53
    px3 = np.array(base[:66] + [101.0, 85.0] + [91.0] * 130)
    w3 = X.wave(px3, 64, 59)
    assert w3 == (80.0, 66) and X.position(px3, 59, 67, w3) == (0.25, 0)   # 回到前高之後才買：不算
    assert X.wave(np.array(base + [91.0] * 50), 64, 59) is None            # 還沒到第 120 天、也沒回到前高


def test_rule_verdict3():
    up = {"few": False, "lp_lo": 0.05, "lp_hi": 0.3, "lp_h1": 0.1, "lp_h2": 0.2, "lp_q": 0.05,
          "r_d": -0.01, "r_lo": -0.03, "r_hi": 0.01, "r_h1": -0.02, "r_h2": 0.01, "r_q": 0.5}
    assert X.rule_verdict3(up) == "better"                                 # 報酬差一點但不顯著：仍有用
    rdown = {"r_lo": -0.06, "r_hi": -0.01, "r_h1": -0.02, "r_h2": -0.04, "r_q": 0.02}
    assert X.rule_verdict3({**up, **rdown}) == "trade"
    assert X.rule_verdict3({**up, "lp_q": 0.2}) == "none"
    assert X.rule_verdict3({**up, "lp_h2": -0.01}) == "none"
    assert X.rule_verdict3({**up, "lp_lo": -0.3, "lp_hi": -0.05, "lp_h1": -0.1, "lp_h2": -0.2}) == "worse"
    assert X.rule_verdict3({**up, "lp_q": 0.5, **rdown}) == "worse"
    assert X.rule_verdict3({**up, "few": True}) == "few"


def test_ver3_lp_comparisons_match_direct():
    """VER 3：落底訊號 vs 固定等 10 天、固定等 10 天 vs 事件隔天買；樣本＝兩邊 LP 與 R60 都有值；BH 兩個家族；判定與 v1、v2 並存。"""
    I = _inputs(3000, 21)
    I["px"] = _walk(3000, 21, vol=0.022)
    M = X.market(I)
    for ev in S.EVENTS:
        recs = X.event_recs(I, ev)
        rs = M["ev"][ev]["rules"]
        for k in ("W10",) + tuple(S.SIG_MK["tw"]):
            c = rs[k]["lp"]
            base = "b1" if k == "W10" else "W10"
            assert c["base"] == base
            rows = []
            for r in recs:
                o = r["rules"][k].get("o") or {}
                ob = r["b1"] if base == "b1" else (r["rules"]["W10"].get("o") or {})
                if None not in (o.get("lp"), o.get("r60"), ob.get("lp"), ob.get("r60")):
                    rows.append((o["lp"], ob["lp"], o["r60"], ob["r60"], r["b1"]["lp"]))
            assert c["n"] == len(rows)
            if rows:
                a = np.array(rows, dtype=float)
                assert math.isclose(c["lp_rule"], a[:, 0].mean()) and math.isclose(c["lp_base"], a[:, 1].mean())
                assert math.isclose(c["lp_d"], (a[:, 0] - a[:, 1]).mean(), abs_tol=1e-12)
                assert math.isclose(c["r_d"], (a[:, 2] - a[:, 3]).mean(), abs_tol=1e-12)
                assert math.isclose(c["lp_b1"], a[:, 4].mean())
                rb = [(o["reb"]) for r in recs for o in [r["rules"][k].get("o") or {}]
                      if None not in (o.get("lp"), o.get("r60"))
                      and None not in ((r["b1"] if base == "b1" else (r["rules"]["W10"].get("o") or {})).get(x) for x in ("lp", "r60"))]
                assert math.isclose(c["reb_rule"], float(np.median(rb)))
                h = len(rows) // 2
                if h:
                    assert math.isclose(c["lp_h1"], (a[:h, 0] - a[:h, 1]).mean(), abs_tol=1e-12)
            assert c["few"] == (c["n"] < S.MIN_N or c["ep"] < S.MIN_EP or c.get("lp_lo") is None or c.get("r_lo") is None)
            assert rs[k]["v"] == c["v"] == X.rule_verdict3(c)
            assert (c["lp_dir"], c["r_dir"]) == (X.sdir(c, "lp"), X.sdir(c, "r"))
            assert rs[k]["v1"] in S.VERDICT and rs[k]["v2"] in S.VERDICT
        for pre in ("lp", "r"):
            for fam in ([k for k in S.SIG_MK["tw"] if k not in S.SIG_ADD4["tw"]], list(S.SIG_ADD4["tw"])):   # VER 4：新訊號另一個家族
                sig = [k for k in fam if not rs[k]["lp"]["few"] and rs[k]["lp"].get(f"{pre}_p") is not None]
                for k, q in zip(sig, X.bh([rs[k]["lp"][f"{pre}_p"] for k in sig])):
                    assert rs[k]["lp"][f"{pre}_q"] == q
            w = rs["W10"]["lp"]                                       # 固定等 10 天 vs 事件隔天買自成一個家族：q＝p
            if not w["few"] and w.get(f"{pre}_p") is not None:
                assert w[f"{pre}_q"] == w[f"{pre}_p"]
        A = M["ev"][ev]["all"]
        lp = [r["b1"]["lp"] for r in recs if r["b1"].get("lp") is not None]
        assert A["lp"]["n"] == len(lp) and (not lp or math.isclose(A["lp"]["rate"], float(np.mean(lp))))
        assert [x.get("lp") for x in M["ev"][ev]["list"]] == [r["b1"].get("lp") for r in recs]


def test_now_active_events():
    I = _inputs(800, 6)
    px = np.array([100.0] * 700 + [100 * (0.985 ** i) for i in range(1, 101)])   # 最後 100 天一路跌
    I["px"] = px
    N = X.now(I)
    kinds = [a["ev"] for a in N["active"]]
    assert "E10" in kinds and N["dd60"] < -0.10
    a = next(x for x in N["active"] if x["ev"] == "E10")
    assert a["p"] == I["cal"][699] and a["nowdd"] < -0.2
    assert a["pos_now"] == 0.0                                  # 一路跌：今天就是這一波到今天的最低收盤
    assert set(a["sig"]) == set(S.SIG_MK["tw"])
    I["px"] = np.array([100.0 * (1.0002 ** i) for i in range(800)])
    N = X.now(I)
    assert N["active"] == [] and N["last"]["E5"] is None


# ── VER 4：融資維持率（C9）、美股寬度（C3、C8） ──────────────────────────────

def test_us_breadth_series_matches_direct_and_tw_algorithm():
    """美股漲跌家數 → 最近 10 筆的上漲占比（合計 ≥ 100 家）與當天上漲占比（≥ 100 家）；和台股 breadth_series 同一個算法。"""
    rnd = random.Random(5)
    cal = _cal(300)
    br, tw = {}, {}
    for i, d in enumerate(cal):
        if i in (40, 41, 200):                                # 缺幾天：用依日期排好的最近 10 筆
            continue
        n = 8 if i < 12 else rnd.randint(150, 490)            # 開頭幾天家數很少
        a = rnd.randint(0, n)
        b = n - a - rnd.randint(0, min(5, n - a))
        br[d] = [a, b, n - a - b, 1.0, 1.0, 1.0, 1.0, n, 500]
        tw[d] = [a, b, 0, 0, 0, 0, 0]
    U = X.us_breadth_series(br)
    ks = sorted(br)
    for i, d in enumerate(ks):
        a, b = br[d][0], br[d][1]
        assert (d in U["adv"]) == (a + b >= 100)
        if d in U["adv"]:
            assert math.isclose(U["adv"][d], a / (a + b))
        if i >= 9:
            A = sum(br[k][0] for k in ks[i - 9:i + 1])
            Z = A + sum(br[k][1] for k in ks[i - 9:i + 1])
            assert (d in U["t5"]) == (Z >= 100)
            if d in U["t5"]:
                assert abs(U["t5"][d] - A / Z) < 1e-5
        else:
            assert d not in U["t5"]
    T = X.breadth_series(tw)
    assert U["t5"] == T["t5"] and U["adv"] == T["adv"]


def test_ver4_new_signals_do_not_change_original_results(monkeypatch):
    """VER 4：新訊號在多重比較自成一個家族——拿掉新訊號重算，原本每一個規則的統計與判定都一樣。"""
    I = _inputs(3000, 21)
    I["px"] = _walk(3000, 21, vol=0.022)
    with_new = X.market(I)
    monkeypatch.setitem(S.SIG_MK, "tw", tuple(k for k in S.SIG_MK["tw"] if k not in S.SIG_ADD4["tw"]))
    without = X.market(I)
    for ev in S.EVENTS:
        a, b = with_new["ev"][ev]["rules"], without["ev"][ev]["rules"]
        assert set(a) - set(b) == set(S.SIG_ADD4["tw"])
        for k in b:
            assert a[k] == b[k], (ev, k)
        assert "C9" in a and a["C9"]["v"] in S.VERDICT


def test_c9_family_q_values_are_separate():
    """C9 自己一個家族：只有一個檢定時 q＝p。"""
    I = _inputs(3000, 21)
    I["px"] = _walk(3000, 21, vol=0.022)
    M = X.market(I)
    for ev in S.EVENTS:
        c = M["ev"][ev]["rules"]["C9"]
        for blk, pre in ((c, "nl"), (c, "r"), (c["w10"], "nl"), (c["lp"], "lp")):
            if blk.get(f"{pre}_q") is not None:
                assert math.isclose(blk[f"{pre}_q"], blk[f"{pre}_p"])


def test_now_reports_margin_ratio_since_event():
    I = _inputs(800, 6)
    I["px"] = np.array([100.0] * 700 + [100 * (0.985 ** i) for i in range(1, 101)])
    mr = np.full(800, 170.0)
    mr[750:760] = 135.0
    mr[780] = np.nan
    mr[799] = np.nan
    I["sig"]["mr"] = mr
    N = X.now(I)
    a = next(x for x in N["active"] if x["ev"] == "E10")
    assert a["mr"]["min"] == 135.0 and a["mr"]["min_d"] == I["cal"][750]
    assert a["mr"]["now"] == 170.0 and a["mr"]["now_d"] == I["cal"][798]      # 今天沒有值：用最近有值的一天
    assert a["sig"]["C9"]["st"] == "on"                                     # 135% → 170%：從 140% 以下回到 150% 以上
