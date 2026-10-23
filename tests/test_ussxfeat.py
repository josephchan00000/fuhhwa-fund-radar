"""美股飆股的每週樣本（arm/lab/ussxfeat.py；ussxspec VER 1）：股價條件對照 superx.Px、標籤對照逐筆直接算、EPS 與 SEC 條件的算法。
不連網、不用真的資料。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from arm.lab import superx as SX
from arm.lab import ussxfeat as F
from arm.lab import ussxspec as X


def _days(n: int, start: str = "2010-01-04") -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _panel(T=700, N=6, seed=3):
    rng = np.random.default_rng(seed)
    cal = _days(T)
    C = np.cumprod(1 + rng.normal(0.0008, 0.02, (T, N)), axis=0) * 30
    H = C * (1 + np.abs(rng.normal(0, 0.01, (T, N))))
    L = C * (1 - np.abs(rng.normal(0, 0.01, (T, N))))
    V = rng.integers(1000, 5000, (T, N)).astype(np.float32)
    C[:100, 5] = np.nan                                  # 第 6 檔晚上市
    H[:100, 5] = L[:100, 5] = np.nan
    C[650:, 4] = np.nan                                  # 第 5 檔提早下市
    H[650:, 4] = L[650:, 4] = np.nan
    has = np.isfinite(C)
    first = np.where(has.any(axis=0), np.argmax(has, axis=0), -1)
    last = np.where(has.any(axis=0), T - 1 - np.argmax(has[::-1], axis=0), -1)
    return {"cal": cal, "sym": [f"S{j}" for j in range(N)], "C": C, "H": H, "L": L, "V": V, "first": first, "last": last}


def test_sparse_query_matches_brute_force():
    rng = np.random.default_rng(1)
    A = rng.normal(size=(300, 4))
    S = F.Sparse(A, "max", 200)
    a = rng.integers(0, 290, 500)
    b = np.minimum(a + rng.integers(-3, 200, 500), 299)
    j = rng.integers(0, 4, 500)
    got = S.query(a, b, j)
    for k in range(500):
        if b[k] < a[k]:
            assert np.isnan(got[k])
        else:
            assert got[k] == pytest.approx(A[a[k]:b[k] + 1, j[k]].max())


def test_price_block_matches_superx_px():
    P = _panel()
    wk = F.week_ends(P["cal"])
    pb = F.price_block(P, wk)
    for j in range(6):
        s = {"c": [None if not np.isfinite(x) else float(x) for x in P["C"][:, j]],
             "h": [None if not np.isfinite(x) else float(x) for x in P["H"][:, j]],
             "l": [None if not np.isfinite(x) else float(x) for x in P["L"][:, j]],
             "v": [float(x) for x in P["V"][:, j]]}
        px = SX.Px(s, P["cal"])
        for w, i in enumerate(wk):
            r = px.raw(i)
            assert pb["valid"][w, j] == (r is not None), (j, i)
            if r is None:
                continue
            assert pb["score"][w, j] == pytest.approx(r["score"])
            assert pb["d52h"][w, j] == pytest.approx(r["d52h"])
            assert pb["r120"][w, j] == pytest.approx(r["r120"])
            assert pb["vdry"][w, j] == pytest.approx(r["vdry"])
            assert list(pb["tt"][w, :, j]) == [bool(x) for x in r["tt7"]]


def test_rs_rank_matches_superx():
    rng = np.random.default_rng(2)
    score = rng.normal(size=(3, 8))
    use = rng.random((3, 8)) < 0.8
    rs = F.rs_rank(score, use)
    for w in range(3):
        cols = [j for j in range(8) if use[w, j]]
        ref = SX.rs_pct({f"S{j}": score[w, j] for j in cols})
        for j in cols:
            assert rs[w, j] == ref[f"S{j}"]
        assert np.isnan(rs[w, [j for j in range(8) if not use[w, j]]]).all()


def test_labels_match_brute_force():
    P = _panel(T=1400, N=6)
    wk = F.week_ends(P["cal"])
    pb = F.price_block(P, wk)
    ii = np.array([i for i in wk if i >= 260 for _ in range(6)])
    jj = np.array([j for i in wk if i >= 260 for j in range(6)])
    ok = np.isfinite(P["C"][ii, jj])
    ii, jj = ii[ok], jj[ok]
    y = F.labels(pb, P, ii, jj)
    Cf, Hf, Lf = pb["Cf"], pb["Hf"], pb["Lf"]
    T = len(P["cal"])
    for k in range(0, len(ii), 7):
        i, j = int(ii[k]), int(jj[k])
        for b, spec in X.BOOKS.items():
            n = spec["n"]
            if i + n >= T:
                assert y[b]["y"][k] == -1
                continue
            e = min(i + n, int(P["last"][j]))
            if e <= i:
                assert y[b]["y"][k] == -1
                continue
            c0 = Cf[i, j]
            mx = Hf[i + 1:e + 1, j].max() / c0 - 1
            mc = Cf[i + 1:e + 1, j].max() / c0 - 1
            fr = Cf[e, j] / c0 - 1
            dd = Lf[i + 1:e + 1, j].min() / c0 - 1
            want = {"close": fr, "high": mx, "maxclose": mc}[spec["how"]] >= spec["g"]
            assert y[b]["y"][k] == int(want), (b, i, j)
            assert y[b]["mx"][k] == pytest.approx(mx) and y[b]["fr"][k] == pytest.approx(fr)
            assert y[b]["dd"][k] == pytest.approx(dd)


def test_eps_reports_yoy_acceleration_split_and_surprise():
    rows = [["2019-02-01", 1.00, 0.9, 5, "Dec/2018"], ["2019-05-01", 1.00, None, None, "Mar/2019"],
            ["2019-08-01", 1.00, 1.0, 3, "Jun/2019"], ["2019-11-01", 1.20, 1.0, 3, "Sep/2019"],
            ["2020-02-01", 1.50, 1.2, 4, "Dec/2019"], ["2020-05-01", 0.60, 0.5, 4, "Mar/2020"],   # 2020-03-10 2:1 分割之後公布
            ["2020-05-02", 9.99, 0.5, 4, "Mar/2020"],                                              # 同一季第二次：不算
            ["2020-08-01", 0.75, 0.70, 4, "Jun/2020"], ["2020-11-01", 0.90, 0.8, 4, "Sep/2020"]]
    spl = [["2020-03-10", 2.0]]
    er = {x["m"]: x for x in F.eps_reports(rows, spl)}
    m = F.qlabel
    assert m("Mar/2020") == 2020 * 12 + 3
    q = er[m("Dec/2019")]
    assert q["ey"] == pytest.approx(0.5) and q["sur"] == pytest.approx(0.3 / 1.2) and q["nest"] == 4.0
    q = er[m("Mar/2020")]                                  # 去年同季 1.00 換成分割後的基準 0.50 → 年增 20%
    assert q["ey"] == pytest.approx(0.2)
    assert q["eacc"] == pytest.approx(0.2 - 0.5)
    q = er[m("Jun/2020")]
    assert q["ey"] == pytest.approx(0.75 / 0.5 - 1)
    assert q["eacc"] == pytest.approx(0.5 - 0.2) and q["eaccn"] == 1.0
    q = er[m("Sep/2020")]
    assert q["ey"] == pytest.approx(0.9 / 0.6 - 1) and q["eacc"] == pytest.approx(0.0) and q["eaccn"] == 0.0
    # 近四季：2019Q4～2020Q3（分割後基準）vs 2018Q4～2019Q3
    a = 1.5 / 2 + 0.6 + 0.75 + 0.9
    b = (1.0 + 1.0 + 1.0 + 1.2) / 2
    assert q["e4"] == pytest.approx(a / b - 1)
    assert er[m("Mar/2019")]["sur"] is None and er[m("Mar/2019")]["ey"] is None


def test_eps_turnaround_and_small_base():
    rows = [["2019-02-01", -0.20, None, None, "Dec/2018"], ["2020-02-01", 0.30, None, None, "Dec/2019"],
            ["2021-02-01", 0.02, None, None, "Dec/2020"]]
    er = {x["m"]: x for x in F.eps_reports(rows, [])}
    q = er[F.qlabel("Dec/2019")]
    assert q["eturn"] is True and q["ey"] == 3.0          # 去年同季虧損、今年 > 0.05 → 300%
    q = er[F.qlabel("Dec/2020")]
    assert q["eturn"] is False and q["ey"] == pytest.approx(max(-1.0, 0.02 / 0.30 - 1))


def test_sec_quarters_derive_q4_and_reports():
    f = {"Revenues": [["2019-01-01", "2019-03-31", 100, "2019-05-01", "10-Q"],
                      ["2019-04-01", "2019-06-30", 110, "2019-08-01", "10-Q"],
                      ["2019-07-01", "2019-09-30", 120, "2019-11-01", "10-Q"],
                      ["2019-01-01", "2019-09-30", 330, "2019-11-01", "10-Q"],
                      ["2019-01-01", "2019-12-31", 460, "2020-02-15", "10-K"],
                      ["2020-01-01", "2020-03-31", 150, "2020-05-01", "10-Q"]],
         "CostOfRevenue": [["2019-01-01", "2019-03-31", 60, "2019-05-01", "10-Q"],
                           ["2020-01-01", "2020-03-31", 75, "2020-05-01", "10-Q"]],
         "StockholdersEquity": [["", "2019-03-31", 400, "2019-05-01", "10-Q"], ["", "2020-03-31", 600, "2020-05-01", "10-Q"]],
         "NetIncomeLoss": [["2019-04-01", "2019-06-30", 10, "2019-08-01", "10-Q"],
                           ["2019-07-01", "2019-09-30", 12, "2019-11-01", "10-Q"],
                           ["2019-01-01", "2019-09-30", 30, "2019-11-01", "10-Q"],
                           ["2019-01-01", "2019-12-31", 45, "2020-02-15", "10-K"],
                           ["2020-01-01", "2020-03-31", 20, "2020-05-01", "10-Q"]],
         "EntityCommonStockSharesOutstanding": [["", "2020-04-20", 1000, "2020-05-01", "10-Q"]]}
    Q = F.sec_quarters(f)
    assert Q["Revenues"]["2019-12-31"] == (130, "2020-02-15")          # 460 − 330
    assert Q["NetIncomeLoss"]["2019-12-31"] == (15, "2020-02-15")
    assert Q["StockholdersEquity"]["2020-03-31"] == (600, "2020-05-01")
    sr, sh = F.sec_reports({"f": f}, [])
    q = {x["end"]: x for x in sr}["2020-03-31"]
    assert q["sy"] == pytest.approx(0.5) and q["gm"] == pytest.approx(0.5) and q["gmd"] == pytest.approx(0.5 - 0.4)
    assert q["roe"] == pytest.approx((20 + 15 + 12 + 10) / 500)
    assert q["c33"] is None and q["filed"] == "2020-05-01"
    assert sh == [{"filed": "2020-05-01", "end": "2020-04-20", "v": 1000}]


def test_split_between_and_week_ends():
    spl = [["2020-03-10", 2.0], ["2021-01-05", 3.0]]
    assert F.split_between(spl, "2020-01-01", "2021-12-31") == 6.0
    assert F.split_between(spl, "2020-03-10", "2020-12-31") == 1.0           # 生效日當天公布的已經是新基準
    cal = ["2024-01-04", "2024-01-05", "2024-01-08", "2024-01-12", "2024-01-16"]
    assert F.week_ends(cal) == [1, 3, 4]
