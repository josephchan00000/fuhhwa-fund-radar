"""天數衰減的程式（arm/lab/sigdecay.py；decayspec VER 1）。用造出來的資料，不讀落檔。"""
import numpy as np

from arm.lab import decayspec as D
from arm.lab import sigdecay as M


def test_fit_h_recovers_half_life_and_ties():
    k = np.arange(0, 60, dtype=float)
    den = np.ones(D.K_CAP + 1)
    num = np.zeros(D.K_CAP + 1)
    num[:60] = D.decay(k, 10)
    den[60:] = 0
    assert M.fit_h(num, den) == 10
    flat = np.zeros(D.K_CAP + 1)
    flat[:30] = 1.0
    d2 = np.zeros(D.K_CAP + 1)
    d2[:30] = 1.0
    assert M.fit_h(flat, d2) == 1000                     # 不衰減 → 最大的
    assert M.fit_h(np.zeros(5), np.zeros(5)) is None


def test_year_sums_and_rate():
    cal = [f"{2010 + i // 3}-06-0{1 + i % 3}" for i in range(9)]
    Yu = np.array([1, 0, 1, 1, 1, 0, np.nan, 1, 0], dtype=float)
    Y = {k: (Yu, Yu, None) for k in ("short", "mid", "long")}
    h = {k: {"t": list(range(9)), "u": [1, 2, 0, 1, 1, 1, 5, 0, 2], "w": [0] * 9} for k in ("short", "mid", "long")}
    ys = M.year_sums(cal, Y, h)
    assert ys["short"]["up"] == {2010: [1.0, 3.0], 2011: [2.0, 3.0], 2012: [0.0, 2.0]}   # nan 那一週不算
    assert M.rate(ys["short"]["up"]) == [3.0 / 8.0, 8]


def test_summary_decision():
    def m(rd, r26):
        ys = {r: {k: {s: {2010: [v * 10, 10.0], 2011: [v * 10, 10.0]} for s in ("up", "warn")} for k in ("short", "mid", "long")}
              for r, v in (("v25", 0.5), ("v26", r26), ("decay", rd))}
        cmp = {k: {s: {r: M.rate(ys[r][k][s]) for r in ys} for s in ("up", "warn")} for k in ("short", "mid", "long")}
        return {"cmp": cmp, "ys": ys}
    S1 = M.summary({"tw": m(0.62, 0.60)}, draws=200)
    assert abs(S1["d"] - 0.02) < 1e-12 and S1["lo"] > 0 and S1["better"] is True and S1["win"] == 6
    S2 = M.summary({"tw": m(0.59, 0.60)}, draws=200)
    assert S2["better"] is False
