"""美股飆股的找規則（arm/lab/ussxmine.py）＝superx VER 2 同一套算法：同一份資料，兩邊的條件、規則、成績逐項相同。不用真的資料。"""
from __future__ import annotations

import numpy as np
import pytest

from arm.lab import superx as SX
from arm.lab import ussxmine as UM
from arm.lab import ussxspec as X


def _data(n: int = 6000, seed: int = 7):
    rng = np.random.default_rng(seed)
    weeks = [f"{y}-{m:02d}-{d:02d}" for y in range(2009, 2014) for m in range(1, 13) for d in (7, 14, 21, 28)]
    d = np.array(sorted(rng.choice(weeks, n)))
    c = np.array([f"S{k % 400:03d}" for k in range(n)])
    f = {}
    for k, _, typ, _ in X.FEATS:
        if typ == "bool":
            v = (rng.random(n) < 0.3).astype(float)
        elif k in ("tt_n", "bu20", "nest", "eaccn"):
            v = rng.integers(0, 9, n).astype(float)
        else:
            v = rng.normal(size=n)
        v[rng.random(n) < 0.08] = np.nan
        f[k] = v
    p = 0.07 + 0.30 * ((np.nan_to_num(f["rs"]) > 0.8) & (np.nan_to_num(f["ey"]) > 0.5)) + 0.15 * (f["tt_all"] == 1)
    y = (rng.random(n) < p).astype(np.int8)
    y[rng.random(n) < 0.05] = -1
    lab = {"y": y, "mx": rng.normal(0.3, 0.2, n), "dd": rng.normal(-0.1, 0.05, n), "fr": rng.normal(0.05, 0.2, n)}
    for k in ("mx", "dd", "fr"):
        lab[k][y < 0] = np.nan
    cols = {"d": d, "c": c, "f": f, "y": {"R60": lab}}
    rows = []
    for j in range(n):
        fj = {}
        for k, _, typ, _ in X.FEATS:
            x = f[k][j]
            fj[k] = None if np.isnan(x) else (bool(x == 1) if typ == "bool" else float(x))
        yj = None if y[j] < 0 else {"y": bool(y[j] == 1), "mx": float(lab["mx"][j]), "dd": float(lab["dd"][j]),
                                     "fr": float(lab["fr"][j])}
        rows.append({"c": str(c[j]), "d": str(d[j]), "f": fj, "y": {"R60": yj}})
    return cols, rows


@pytest.fixture()
def superx_us(monkeypatch):
    monkeypatch.setattr(SX, "FEATS", [(k, nm, t) for k, nm, t, _ in X.FEATS])
    SX._BITS.clear()
    yield
    SX._BITS.clear()


def _norm_rule(r):
    return {"conds": [tuple(c) for c in r["conds"]], "is": r["is"], "val": r.get("val")}


@pytest.mark.parametrize("seed", [7, 11])
def test_port_matches_superx(superx_us, monkeypatch, seed):
    cols, rows = _data(seed=seed)
    rule = {**X.RULE, "n": 120, "pos": 25, "lift": 1.6, "sub_lift": 1.2, "val_lift": 1.2}
    subs = (("2009-01-01", "2010-06-30"), ("2010-07-01", "2011-12-31"))
    monkeypatch.setattr(SX, "RULE", rule)
    monkeypatch.setattr(SX, "SUBS", subs)
    is_idx = np.nonzero(cols["d"] <= "2011-12-31")[0]
    val_idx = np.nonzero(cols["d"] >= "2012-01-01")[0]
    rows_is = [rows[j] for j in is_idx]
    rows_val = [rows[j] for j in val_idx]
    ft = SX.feature_table(rows_is, "R60")
    conds = SX.candidate_conds(ft)
    rules, tried = SX.mine_rules(rows_is, "R60", conds)
    fin = SX.select_final([dict(r) for r in rules], rows_val, "R60")

    Bi, Bv = UM.Bits(cols, is_idx, "R60"), UM.Bits(cols, val_idx, "R60")
    ft2 = UM.feature_table(Bi)
    assert ft2["base"] == ft["base"]
    for k, t in ft["feats"].items():
        t2 = ft2["feats"][k]
        assert t2["cuts"] == t["cuts"] and t2["n"] == t["n"], k
        assert [(g["g"], g["n"], g["pos"], g["p"], g["lift"]) for g in t2["groups"]] == \
               [(g["g"], g["n"], g["pos"], g["p"], g["lift"]) for g in t["groups"]], k
    conds2 = UM.candidate_conds(ft2, rule)
    assert conds2 == conds and len(conds) > 6
    rules2, tried2 = UM.mine_rules(Bi, conds2, subs, rule)
    assert tried2 == tried and len(rules) > 0
    assert [_norm_rule(r) for r in rules2] == [_norm_rule(r) for r in rules]
    fin2 = UM.select_final([dict(r) for r in rules2], Bv, rule)
    assert len(fin) > 0
    assert [_norm_rule(r) for r in fin2] == [_norm_rule(r) for r in fin]


def test_rule_mask_and_ones():
    cols, _ = _data(n=500)
    rules = [{"conds": [["rs", ">=", 0.5], ["tt_all", "=", True]]}, {"conds": [["ey", "<=", -1.0]]}]
    m = UM.rule_mask(cols, rules)
    f = cols["f"]
    with np.errstate(invalid="ignore"):
        ref = ((f["rs"] >= 0.5) & (f["tt_all"] == 1)) | (f["ey"] <= -1.0)
    assert np.array_equal(m, ref)
    x = UM.pack(ref)
    assert np.array_equal(UM.ones(x, 500), np.nonzero(ref)[0])
