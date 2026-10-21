"""現在的情境：相似的日子（arm/lab/simdays.py；sigspec 第 4.12 節）——和逐筆直接算的版本比對。"""
from datetime import date, timedelta

import numpy as np

from arm.lab import sigcat as G
from arm.lab import sigspec as S
from arm.lab import simdays as M


def _cal(n, start=date(2000, 1, 3)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _frame(T=1200, seed=3, mk="spx"):
    rng = np.random.default_rng(seed)
    cal = _cal(T)
    px = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, T)))
    comp = {k: np.clip(50 + np.cumsum(rng.normal(0, 2, T)), 0, 100) for k in ("fund", "liq", "tech", "sent")}
    comp["fund"][:30] = np.nan
    return {"mk": mk, "cal": cal, "px": px, "comp": comp}


def _brute_pick(X, today, cand, k, gap):
    """直接算：依（距離, −日期）排，逐一檢查和已挑的日子是否都隔 gap 個交易日以上。"""
    D = {int(i): float(np.mean(np.abs(X[i] - today))) for i in cand}
    order = sorted(D, key=lambda i: (D[i], -i))
    out = []
    for i in order:
        if all(abs(i - j) >= gap for j in out):
            out.append(i)
        if len(out) >= k:
            break
    return out, [D[i] for i in out]


def test_pick_matches_brute_force():
    rng = np.random.default_rng(7)
    for trial in range(20):
        X = rng.integers(0, 100, size=(500, 3)).astype(float)   # 整數分數：同距離常見，檢查同距離挑日期較晚的
        cand = np.sort(rng.choice(400, size=300, replace=False))
        today = X[450]
        got, gd = M.pick(X, today, cand, k=20, gap=60 if trial % 2 else 13)
        exp, ed = _brute_pick(X, today, cand, 20, 60 if trial % 2 else 13)
        assert got == exp and np.allclose(gd, ed)


def test_candidates_window_and_missing_values():
    F = _frame()
    RA = G.ret_arrays(F["px"])
    X = M.features(F)
    T = 900
    for h in S.RET_H:
        c = M.candidates(X, RA, T, h)
        assert c.max() == T - S.LAG - h                               # 窗口在 T 之前已經走完
        assert c.min() == 30                                          # 前 30 天基本面沒有值
        assert np.all(np.isfinite(X[c])) and len(c) == T - S.LAG - h + 1 - 30
    assert len(M.candidates(X, RA, 10, 60)) == 0


def test_tw_liquidity_is_mean_of_global_and_taiwan():
    F = _frame(mk="tw")
    F["comp"]["chip"] = F["comp"].pop("sent")
    F["comp"]["gliq"] = F["comp"]["liq"].copy()
    F["comp"]["tliq"] = F["comp"].pop("liq") + 10
    F["comp"]["tliq"][100:110] = np.nan
    X = M.features(F)
    assert np.allclose(X[200, 1], F["comp"]["gliq"][200] + 5)
    assert np.all(np.isnan(X[100:110, 1]))


def test_estimate_matches_direct():
    F = _frame()
    RA = G.ret_arrays(F["px"])
    X = M.features(F)
    E = M.estimate(F, RA=RA)
    T = len(F["cal"]) - 1
    assert E["d"] == F["cal"][T] and E["dims"] == list(S.NB_DIMS) and len(E["rows"]) == len(S.RET_H)
    px = F["px"]
    for row in E["rows"]:
        h = row["h"]
        cand = [i for i in range(T - S.LAG - h + 1) if np.all(np.isfinite(X[i]))]
        ch, dist = _brute_pick(X, X[T], np.array(cand), S.NB_K, S.NB_GAP)
        r = np.array([px[i + S.LAG + h] / px[i + S.LAG] - 1 for i in ch])
        assert row["n"] == len(ch) and abs(row["dist"] - np.mean(dist)) < 1e-12
        assert row["far"] == (np.mean(dist) > S.NB_FAR)
        s = row["s"]
        assert s[0] == len(ch) and abs(s[1] - r.mean()) < 1e-12 and abs(s[5] - np.mean(r > 0)) < 1e-12
        rb = np.array([px[i + S.LAG + h] / px[i + S.LAG] - 1 for i in cand])
        assert row["b"][0] == len(cand) and abs(row["b"][5] - np.mean(rb > 0)) < 1e-12
        mae = [min(0.0, min(px[i + S.LAG + 1:i + S.LAG + h + 1]) / px[i + S.LAG] - 1) for i in ch]
        assert abs(s[8] - min(mae)) < 1e-12
        assert row["a"] == F["cal"][cand[0]]
    L = E["list"]
    ch60 = [r for r in E["rows"] if r["h"] == S.NB_LIST_H][0]
    assert len(L) == ch60["n"] and [e["dist"] for e in L] == sorted(e["dist"] for e in L)
    idx = [F["cal"].index(e["d"]) for e in L]
    assert all(abs(a - b) >= S.NB_GAP for a in idx for b in idx if a != b)
    for e, i in zip(L, idx):
        for h in S.NB_LIST_EXTRA:
            if i + S.LAG + h > T:
                assert e["r"][h] is None
            else:
                assert abs(e["r"][h] - (px[i + S.LAG + h] / px[i + S.LAG] - 1)) < 1e-12
    for e, i in zip(L, idx):
        assert e["c"] == float(F["comp"]["sent"][i])                  # 當時的籌碼（美股＝情緒籌碼），只顯示
    assert E["chip"]["dims"] == list(S.NB_DIMS_X) and [r["h"] for r in E["chip"]["rows"]] == list(S.NB_H_X)


def test_estimate_none_when_today_missing():
    F = _frame()
    F["comp"]["tech"][-1] = np.nan
    assert M.estimate(F) is None


def test_month_end_idx():
    cal = ["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02", "2020-03-03"]
    assert M.month_end_idx(cal, "2020-01-01") == [1, 3, 5]
    assert M.month_end_idx(cal, "2020-02-01") == [3, 5]


def test_block_boot():
    x = np.arange(30, dtype=float)
    a = M.block_boot(x, block=30, n_boot=50, seed=1)
    assert np.allclose(a, x.mean())                                   # 一塊就是全部 → 每次都是原本的平均
    b = M.block_boot(x, block=5, n_boot=200, seed=2)
    assert np.array_equal(b, M.block_boot(x, block=5, n_boot=200, seed=2))
    rng = np.random.default_rng(2)                                    # 直接算同一組起點
    for k in range(200):
        st = rng.integers(0, 26, size=6)
        assert abs(b[k] - np.concatenate([x[s:s + 5] for s in st]).mean()) < 1e-12
    c = M.block_boot(np.arange(7, dtype=float), block=3, n_boot=20, seed=3)
    rng = np.random.default_rng(3)
    for k in range(20):
        st = rng.integers(0, 5, size=3)
        v = np.concatenate([np.arange(s, s + 3) for s in st])[:7]
        assert abs(c[k] - v.mean()) < 1e-12


def _regime_frame(T=3600, seed=5, flip=False):
    """技術面分數在 20、80 兩種狀態輪流（每段 300 天）；80 的時候股價上漲、20 的時候下跌 → 相似的日子應該比平常準。"""
    rng = np.random.default_rng(seed)
    cal = _cal(T, date(1990, 1, 1))
    st = (np.arange(T) // 300) % 2 == 0
    if flip:
        st = rng.random(T) < 0.5
    drift = np.where(st, 0.002, -0.002) if not flip else np.zeros(T)
    px = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.004, T)))
    tech = np.where(st, 80.0, 20.0) + rng.normal(0, 1, T)
    comp = {"fund": 50 + rng.normal(0, 1, T), "liq": 50 + rng.normal(0, 1, T), "tech": tech, "sent": np.full(T, 50.0)}
    return {"mk": "spx", "cal": cal, "px": px, "comp": comp}


def test_oos_direct_and_verdict():
    F = _regime_frame()
    RA = G.ret_arrays(F["px"])
    X = M.features(F)
    h = 20
    o = M.oos(F, h, RA, X)
    last = len(F["cal"]) - 1
    rec = []
    for T in M.month_end_idx(F["cal"], S.NB_OOS_START["spx"]):
        if T + S.LAG + h > last:
            continue
        cand = M.candidates(X, RA, T, h)
        ch, _ = _brute_pick(X, X[T], cand, S.NB_K, S.NB_GAP)
        if not ch:
            continue
        p = np.mean(RA["R"][h][ch] > 0)
        q = np.mean(RA["R"][h][cand] > 0)
        y = float(RA["R"][h][T] > 0)
        rec.append((p, q, y))
    p, q, y = (np.array(v) for v in zip(*rec))
    dm = (q - y) ** 2 - (p - y) ** 2
    assert o["n"] == len(rec) and abs(o["d"] - dm.mean()) < 1e-12
    half = -(-len(rec) // 2)
    assert abs(o["h1"] - dm[:half].mean()) < 1e-12 and abs(o["h2"] - dm[half:].mean()) < 1e-12
    assert o["v"] == "better" and o["lo"] > 0
    assert sum(b["n"] for b in o["bins"]) == o["n"] and o["hi_n"] == int((p >= S.NB_HI).sum())


def test_oos_no_relation_and_few():
    F = _regime_frame(flip=True)
    o = M.oos(F, 20)
    assert o["v"] in ("none", "worse")
    F2 = _regime_frame(T=700)
    o2 = M.oos(F2, 20)
    assert o2["n"] < S.NB_OOS_MIN and o2["v"] == "few" and "lo" not in o2


def test_research_shape_and_version(monkeypatch):
    F = {"spx": _regime_frame(T=1500)}
    R = M.research(F)
    assert R["ver"] == S.VER and set(R["markets"]) == {"spx"}
    assert [o["h"] for o in R["markets"]["spx"]["oos"]] == list(S.RET_H)


def test_research_file_survives_later_spec_versions(tmp_path, monkeypatch):
    """研究檔版本 ≥ SIM_VER（第 4.12 節最後一次改動的版本）就能用；2026-10-21 前要求＝VER，VER 6 起景氣頁一直寫「還沒產生」。"""
    import json
    from arm.lab import sigspec as SS
    from arm.lab import simdays as SD
    f = tmp_path / "sim.json"
    monkeypatch.setattr(SD, "RESEARCH", f)
    for v, ok in ((SS.SIM_VER - 1, False), (SS.SIM_VER, True), (SS.VER, True)):
        f.write_text(json.dumps({"ver": v, "markets": {}}), encoding="utf-8")
        assert (SD.load_research() is not None) is ok
    assert SS.SIM_VER == 5 and SS.SIM_VER <= SS.VER
