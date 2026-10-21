"""打亂日子測試（arm/lab/sigluck.py；sigspec 第 3.5 節，VER 9）——和逐筆直接算的版本、正式統計函式比對。"""
import math

import numpy as np

from arm.lab import sigcat as G
from arm.lab import sigluck as LK
from arm.lab import sigspec as S


def _ys(T=900, seed=1):
    rng = np.random.default_rng(seed)
    Yu = (rng.random(T) < 0.6).astype(float)
    Yw = (rng.random(T) < 0.3).astype(float)
    Yu[-25:] = np.nan
    Yw[-25:] = np.nan
    return Yu, Yw


def _event(days, samp, H=20, sid="tw:t:e"):
    return {"id": sid, "kind": "event", "H": H, "samp": samp, "days": days}


def _state(state, samp, H=20, sid="tw:t:s", monthly=False):
    sd = {"id": sid, "kind": "state", "H": H, "samp": samp, "state": state}
    if monthly:
        sd["monthly"] = True
    return sd


def _brute_event(sd, Yu, Yw, o):
    """直接算：每一個出現日在樣本序列裡的位置加 o（環狀）→ G.dedupe → 窗口完整的平均。"""
    samp = list(np.asarray(sd["samp"]))
    L = len(samp)
    pos = {t: i for i, t in enumerate(samp)}
    days = sorted(samp[(pos[t] + o) % L] for t in sd["days"] if t in pos)
    kept = [t for t in G.dedupe(days, sd["H"]) if not (np.isnan(Yu[t]) or np.isnan(Yw[t]))]
    return len(kept), (float(np.mean(Yu[kept])) if kept else None), (float(np.mean(Yw[kept])) if kept else None)


def test_shift_zero_matches_production_stats():
    Yu, Yw = _ys()
    rng = np.random.default_rng(3)
    samp = np.arange(40, 900)
    for trial in range(30):
        days = sorted(rng.choice(np.arange(0, 900), size=int(rng.integers(3, 60)), replace=False).tolist())
        sd = _event(days, samp, H=int(rng.choice([5, 20, 60])))
        R = G.ev_stat(sd["days"], Yu, Yw, samp, sd["H"], 600)
        first, u, w = LK.Shift(sd, Yu, Yw).occ(0)
        assert len(u) == R["up"]["n"] and (not len(u) or abs(u.mean() - R["up"]["hit"]) < 1e-12)
        assert not len(w) or abs(w.mean() - R["warn"]["hit"]) < 1e-12
        st = rng.random(len(samp)) < rng.choice([0.05, 0.3])
        sd2 = _state(st, samp, monthly=bool(trial % 3 == 0))
        gap = 1 if sd2.get("monthly") else S.EP_GAP
        R2 = G.st_stat(st, samp, Yu, Yw, gap, 600)
        first, u, w = LK.Shift(sd2, Yu, Yw).occ(0)
        assert len(u) == R2["up"]["n"]
        if len(u):
            assert abs(u.mean() - R2["up"]["hit"]) < 1e-12 and abs(w.mean() - R2["warn"]["hit"]) < 1e-12
            assert [int(x) for x in first] == [o[0] for o in R2["occ"]]


def test_shifted_events_match_brute_force():
    Yu, Yw = _ys(seed=2)
    rng = np.random.default_rng(5)
    samp = np.arange(30, 900, 2)                          # 樣本日不連續
    for trial in range(40):
        days = sorted(rng.choice(samp, size=int(rng.integers(2, 40)), replace=False).tolist())
        sd = _event(days, samp, H=int(rng.choice([3, 20])))
        sh = LK.Shift(sd, Yu, Yw)
        for o in rng.integers(0, len(samp), size=5):
            first, u, w = sh.occ(int(o))
            n, hu, hw = _brute_event(sd, Yu, Yw, int(o))
            assert len(u) == n and (n == 0 or (abs(u.mean() - hu) < 1e-12 and abs(w.mean() - hw) < 1e-12))


def test_shifted_state_equals_rolled_state():
    Yu, Yw = _ys(seed=4)
    rng = np.random.default_rng(6)
    samp = np.arange(0, 880)
    st = np.zeros(len(samp), dtype=bool)
    st[100:180] = st[400:420] = st[850:] = True           # 尾端那一段平移後會從頭接
    sd = _state(st, samp)
    sh = LK.Shift(sd, Yu, Yw)
    for o in (0, 37, 300, 700):
        first, u, _ = sh.occ(o)
        R = G.st_stat(np.roll(st, o), samp, Yu, Yw, S.EP_GAP, 10 ** 9)
        assert len(u) == R["up"]["n"] and abs(u.mean() - R["up"]["hit"]) < 1e-12


def test_p_values_and_leave_one_out():
    hits = np.array([0.5, 0.7, np.nan, 0.9, 0.7, 0.2])
    assert LK.p_of(hits, 0.7) == (1 + 3) / 7 and LK.p_of(hits, 0.95) == 1 / 7 and LK.p_of(hits, None) is None
    pj = LK.loo_p(hits)
    D = len(hits)
    for j, h in enumerate(hits):
        if np.isnan(h):
            assert pj[j] == 1.0
            continue
        others = [x for k, x in enumerate(hits) if k != j and not np.isnan(x)]
        assert abs(pj[j] - (1 + sum(x >= h for x in others)) / D) < 1e-12


def test_sign_test_matches_binomial():
    for b in range(0, 12):
        for c in range(0, 12):
            n = b + c
            exp = 1.0 if n == 0 else sum(math.comb(n, k) * 0.5 ** n for k in range(b, n + 1))
            assert abs(LK.sign_p(b, c) - exp) < 1e-12
    assert abs(LK.sign_p(6, 1) - 8 / 128) < 1e-12              # 台股 5 日急跌・融資減少：6 比 1 → p＝0.0625
    assert LK.sign_p(7, 0) < S.LUCK_P                          # 7 比 0 才過 1%


def test_market_p_is_deterministic_and_separates_signal_from_noise():
    T = 3000
    rng = np.random.default_rng(9)
    Yu = (rng.random(T) < 0.55).astype(float)
    Yw = (rng.random(T) < 0.3).astype(float)
    good = sorted(rng.choice(np.arange(100, T - 100), size=40, replace=False).tolist())
    for t in good:                                            # 之後都上漲：很難是運氣
        Yu[t] = 1.0
    samp = np.arange(50, T - 30)
    sd = _event(good, samp, H=20, sid="tw:t:good")
    R = G.ev_stat(sd["days"], Yu, Yw, samp, 20, 2000)
    a = LK.market_p(sd, Yu, Yw, 2000, R)
    assert a["up"]["p"] <= S.LUCK_P and a == LK.market_p(sd, Yu, Yw, 2000, R)   # 同一個代號、同一個結果
    ps = []
    for i in range(30):                                       # 隨機的日子：p 不該常常 ≤ 1%
        days = sorted(rng.choice(samp, size=30, replace=False).tolist())
        sdx = _event(days, samp, H=20, sid=f"tw:t:r{i}")
        Rx = G.ev_stat(days, Yu, Yw, samp, 20, 2000)
        ps.append(LK.market_p(sdx, Yu, Yw, 2000, Rx)["up"]["p"])
    assert sum(p <= S.LUCK_P for p in ps) <= 2 and np.median(ps) > 0.1
    assert LK.rng_for("a").integers(0, 10 ** 9) == LK.rng_for("a").integers(0, 10 ** 9) != LK.rng_for("b").integers(0, 10 ** 9)


def test_luck_count_uses_threshold_by_shifted_count():
    """VER 14：運氣會產生幾個 ★——每一次平移用平移後的次數決定門檻（次數 < 15 是 10%，其餘 1%）。"""
    T = 2400
    rng = np.random.default_rng(4)
    Yu = (rng.random(T) < 0.6).astype(float)
    Yw = (rng.random(T) < 0.3).astype(float)
    samp = np.arange(50, T - 30)
    days = sorted(rng.choice(samp, size=9, replace=False).tolist())      # 次數少的訊號
    for t in days:
        Yu[t] = 1.0
    sd = _event(days, samp, H=20, sid="tw:t:rare")
    R = G.ev_stat(days, Yu, Yw, samp, 20, 2000)
    got = LK.market_p(sd, Yu, Yw, 2000, R)["up"]["luck"]
    sh = LK.Shift(sd, Yu, Yw)
    rows = [LK._summ(*sh.occ(int(o)), 2000) for o in LK.offsets(LK.rng_for(sd["id"]), sh.L)]
    hits = np.array([np.nan if x["up"][1] is None else x["up"][1] for x in rows])
    pj = LK.loo_p(hits)
    exp = sum(1 for j, x in enumerate(rows) if pj[j] <= S.luck_p(x["up"][0])
              and LK.passes(*x["up"][:2], R["up"]["base"], *x["up"][2:], R["up"]["base10"], "up")) / len(rows)
    old = sum(1 for j, x in enumerate(rows) if pj[j] <= S.LUCK_P
              and LK.passes(*x["up"][:2], R["up"]["base"], *x["up"][2:], R["up"]["base10"], "up")) / len(rows)
    assert abs(got - exp) < 1e-12 and got > old                # 次數少的平移多數用 10%，比只用 1% 多


def test_tier_uses_p_and_thresholds():
    st = {"n": 7, "hit": 1.0, "base": 0.4, "n10": 0, "p": 0.003}
    assert G.tier(st, "up") == "good" and G.tier({**st, "p": 0.2}, "up") == "ref"
    assert G.tier({**st, "hit": 0.55}, "up") == "none"         # 沒過門檻：p 再小也不是 ★
    assert LK.passes(7, 1.0, 0.4, 0, None, None, "up") and not LK.passes(4, 1.0, 0.4, 0, None, None, "up")


def test_stock_hit_zero_shift_and_wrap():
    hit = {"A": np.array([1, 0, 1, np.nan, 1, 0, 0, 1, 1, 0], dtype=float), "B": np.array([0] * 10, dtype=float)}
    fired = {"A": [10, 11, 15, 19], "B": [12, 18]}           # t0＝10、L＝10；A 的 11 在 10 之後 1 天內 → 不算
    assert LK.stock_hit(fired, hit, 10, 10, 1, 0) == np.mean([1, 0, 0, 0, 0])
    # 平移 3：A 13、14、18、12（環狀）→ 排序 12、13、14、18 → 去重（含略過的那天）12、18；B 15、11 → 11、15
    v = [hit["A"][2], hit["A"][8], hit["B"][1], hit["B"][5]]
    assert LK.stock_hit(fired, hit, 10, 10, 1, 3) == np.mean(v)


def test_ind_p_needs_actual_and_is_deterministic():
    rng = np.random.default_rng(2)
    seqs = []
    for _ in range(5):
        fl = np.zeros(120, dtype=bool)
        fl[30:40] = True
        yu = rng.random(120).round()
        yw = np.where(fl, 1.0, 0.0)                         # 狀態中之後都大跌
        seqs.append((fl, yu, yw))
    assert LK.ind_p("ind:t:L2", seqs, {}) == {"up": None, "warn": None}
    p = LK.ind_p("ind:t:L2", seqs, {"warn": 1.0})
    assert p["up"] is None and p["warn"] <= S.LUCK_P and p == LK.ind_p("ind:t:L2", seqs, {"warn": 1.0})
