"""回測 v3：長歷史（2013 起）、大型／中型分開、樣本外 2014-01～2021-09（docs/backtest_v3_plan.md 第 11 節）。

主規格一律同 packtest.P1–P7，不改。每條策略整段跑一次，再依訊號日切成「樣本外（2021-10 之前，從沒看過）」與
「樣本內（2021-10 起，主規格是看這段訂的）」各自統計；參數鄰近同一組 9 格兩段各算一次。
"""
from __future__ import annotations

import statistics

from . import bt3, bt3d, bt3s
from . import packtest as PT

OOS_END = "2021-10-01"
EDGES3 = ["2014-01-01", "2018-01-01", OOS_END]


def _cut(xs: list[dict], a: str | None, z: str | None) -> list[dict]:
    return [u for u in xs if (a is None or u["d"] >= a) and (z is None or u["d"] < z)]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def _part(P, U, U2, per, acc, ew, a, z, *, trades=False) -> dict:
    u = _cut(U, a, z)
    sub = lambda cv: bt3.curve_stats([(i, v) for i, v in cv if (a is None or P.cal[i] >= a)
                                      and (z is None or P.cal[i] < z)], P.cal) if cv else {}
    return {"sel": bt3.sel_stats(u, trades=trades), "pay": bt3.payoff(u), "x2": _mean(x["xe"] for x in _cut(U2, a, z)),
            "fac": bt3.fac_summary(_cut(per, a, z)) if per is not None else None,
            "acc": sub(acc), "ew": sub(ew)}


def _grade(ins: dict, oos: dict, nb: dict | None, event: bool) -> dict:
    g = bt3.grade3(ins["sel"], ins["pay"], ins["x2"], nb, event=event, oos=oos["sel"] if oos["sel"].get("n") else None)
    if g["grade"] == "A" and not oos["pay"].get("ok"):
        g = {**g, "grade": "B", "why": g["why"] + ["樣本外報酬型態未達門檻（A 級需樣本內外都過）"]}
    return g


def _nb2(cells: dict, a_vals, b_vals, lbl) -> tuple[dict, dict]:
    """cells[(a, b)]＝(樣本內平均, 樣本外平均) → 兩張 9 格表。"""
    return (PT.grid(lambda a, b: cells[(a, b)][0], a_vals, b_vals, lbl),
            PT.grid(lambda a, b: cells[(a, b)][1], a_vals, b_vals, lbl))


class _Cache:
    """同一組 rows（只差買進比例）的同一批股票等權帳戶共用。"""

    def __init__(self, P, b):
        self.P, self.b, self.ew = P, b, {}

    def run(self, key, rows, top, nmin, asc=False, umin=None, mult=1.0):
        done = [r for r in rows if r[1] is not None]
        pk = bt3s.pick(done, top, nmin, asc, umin)
        ek = (key, umin or nmin)                        # 對照組只看「哪幾期、哪些股票有分數」，與買幾檔無關
        if ek not in self.ew:
            self.ew[ek] = bt3s._ew(self.P, self.b, done, pk)
        return done, pk, bt3.account(self.P, pk, self.b, mult=mult), self.ew[ek]


def periodic(P, b: str, key: str, rows_fn, a0, *, top: float, nmin: int, asc: bool = False, umin: int | None = None,
             event: bool = False, grid: tuple | None = None) -> dict:
    """rows_fn(a)→rows（a＝第一個參數）；grid＝(第一參數各值, 買進比例各值, 標籤)。"""
    C = _Cache(P, b)
    rows = rows_fn(a0)
    done, pk, acc, ew = C.run((key, a0), rows, top, nmin, asc, umin)
    U = bt3.vs_ew(acc, ew)
    U2 = bt3.vs_ew(bt3.account(P, pk, b, mult=2), ew)
    per = bt3.quint_per(P, done, asc=asc)
    ins = _part(P, U, U2, per, acc["curve"], ew["curve"], OOS_END, None)
    oos = _part(P, U, U2, per, acc["curve"], ew["curve"], None, OOS_END)
    nb_i = nb_o = None
    if grid:
        avals, tvals, lbl = grid                        # tvals：買進比例，或 (比例, 最少檔數) ＝前 N 檔版本
        cells = {}
        for a in avals:
            rr = rows if a == a0 else rows_fn(a)
            for tv in tvals:
                tp, nm = tv if isinstance(tv, tuple) else (tv, nmin)
                _, _, ac, e = C.run((key, a), rr, tp, nm, asc, umin or nmin)
                V = bt3.vs_ew(ac, e)
                cells[(a, tv)] = (_mean(u["xe"] for u in _cut(V, OOS_END, None)), _mean(u["xe"] for u in _cut(V, None, OOS_END)))
        nb_i, nb_o = _nb2(cells, avals, tvals, lbl)
        if tvals and isinstance(tvals[0], tuple):       # 表頭顯示檔數
            for nb in (nb_i, nb_o):
                nb["bd"] = [str(t[1]) for t in tvals]
    now = None
    if rows and rows[-1][1] is None:
        cur = bt3s.pick([rows[-1]], top, nmin, asc, umin)
        if cur:
            now = {"d": P.cal[rows[-1][0]], "picks": cur[0][2], "n_uni": len(rows[-1][2])}
    return {"b": b, "ins": ins, "oos": oos, "nb": nb_i, "nb_oos": nb_o, "grade": _grade(ins, oos, nb_i, event),
            "fac_sub": bt3.subperiods(per, EDGES3), "sel_sub": bt3.subperiods(U, EDGES3, "xe"),
            "lim": sum(u["lim"] for u in acc["units"]), "lock": sum(u["lock"] for u in acc["units"]), "now": now,
            "units": U}


def p2(P, b: str, E, EWb, codes, with_grid=True) -> dict:
    lo = bt3.BUCKET[b]["cap"][0]
    TP = PT._Tpl(P, codes, elig=lambda t: E(t, b), cap_floor=lo)

    def units(spec, mult=1.0):
        sg = PT.p2_signals(TP, spec)
        return bt3.trade_units(PT.p2_trades(TP, sg, P.idx, P.idx_o, EWb[b], spec), P, EWb, b_fix=b, mult=mult)
    U, U2 = units(PT.P2), units(PT.P2, 2.0)
    sl = bt3.slots(P, U)
    I = EWb[b][0]
    ewc = [(i, I[i]) for i, _ in sl["curve"] if I[i]]
    ins = _part(P, U, U2, None, sl["curve"], ewc, OOS_END, None, trades=True)
    oos = _part(P, U, U2, None, sl["curve"], ewc, None, OOS_END, trades=True)
    nb_i = nb_o = None
    if with_grid:
        cells = {}
        for stop in (0.06, 0.08, 0.10):
            for vol in (1.25, 1.5, 2.0):
                V = units({**PT.P2, "stop": stop, "vol": vol})
                cells[(stop, vol)] = (_mean(u["xe"] for u in _cut(V, OOS_END, None)),
                                      _mean(u["xe"] for u in _cut(V, None, OOS_END)))
        nb_i, nb_o = _nb2(cells, (0.06, 0.08, 0.10), (1.25, 1.5, 2.0), ("停損", "突破量倍數"))
    return {"b": b, "ins": ins, "oos": oos, "nb": nb_i, "nb_oos": nb_o, "grade": _grade(ins, oos, nb_i, False),
            "sel_sub": bt3.subperiods(U, EDGES3, "xe"), "taken": sl["taken"], "skipped": sl["skipped"], "units": U}


def run(P=None, *, buckets=("L", "M"), with_grid: bool = True) -> dict:
    P = P or bt3d.Panel()
    E = bt3.Elig(P)
    EWb = {b: bt3.ew_index(P, E, b) for b in bt3.BUCKET}
    codes = P.codes
    eps = bt3d.load_eps()
    rev = PT.load_rev()
    out: dict = {"meta": {"d0": P.cal[0], "d1": P.cal[-1], "n_codes": len(codes),
                          "n_finmind": sum(1 for c in codes if P.src.get(c) == "finmind"),
                          "n_eps": len(eps), "rev_m": len({ym for r in rev.values() for ym in r}), "oos_end": OOS_END}}
    G1 = (105, 126, 147)
    T3 = (0.05, 0.10, 0.20)
    for b in buckets:
        r = {}
        r["p1"] = periodic(P, b, "p1", lambda look: bt3s.p1_rows(P, E, b, codes, look), 126, top=0.10, nmin=10,
                           grid=(G1, T3, ("排序期間（交易日）", "買進比例")) if with_grid else None)
        r["p4"] = periodic(P, b, "p4", lambda look: bt3s.p4_rows(P, E, b, codes, eps, look), 126, top=0.10, nmin=10,
                           grid=(G1, T3, ("動能期間（交易日）", "買進比例")) if with_grid else None)
        r["p3"] = periodic(P, b, "p3", lambda hold: bt3s.p3_rows(P, E, b, codes, eps, hold), 60, top=0.20, nmin=10,
                           umin=20, event=True)
        if with_grid:                                   # P3 的鄰近是「買進比例 × 持有天數」，第一參數是比例
            cells = {}
            for tp in (0.10, 0.20, 0.30):
                for hold in (40, 60, 80):
                    rr = bt3s.p3_rows(P, E, b, codes, eps, hold)
                    done = [x for x in rr if x[1] is not None]
                    pk = bt3s.pick(done, tp, 10, False, 20)
                    V = bt3.vs_ew(bt3.account(P, pk, b), bt3s._ew(P, b, done, pk))
                    cells[(tp, hold)] = (_mean(u["xe"] for u in _cut(V, OOS_END, None)),
                                         _mean(u["xe"] for u in _cut(V, None, OOS_END)))
            r["p3"]["nb"], r["p3"]["nb_oos"] = _nb2(cells, (0.10, 0.20, 0.30), (40, 60, 80), ("買進比例", "持有天數"))
            r["p3"]["grade"] = _grade(r["p3"]["ins"], r["p3"]["oos"], r["p3"]["nb"], True)
        r["p5"] = periodic(P, b, "p5", lambda look: bt3s.p5_rows(P, E, b, codes, P.cal[0], look), 5, top=0.10, nmin=10,
                           asc=True, grid=((3, 5, 10), T3, ("排序天數", "買進比例")) if with_grid else None)
        r["p7"] = periodic(P, b, "p7", lambda win: bt3s.p7_rows(P, E, b, codes, rev, win), 12, top=0.10, nmin=10,
                           grid=((9, 12, 18), T3, ("標準差期間（月）", "買進比例")) if with_grid else None)
        r["p2"] = p2(P, b, E, EWb, codes, with_grid)
        out[b] = r
    return out

def top5(P=None, *, buckets=("M", "L"), with_grid: bool = True, n: int = 5) -> dict:
    """第 13 節：月營收驚喜、財報驚喜「每期只買分數最高的 n 檔」版本（有分數的股票數門檻同主規格）。"""
    P = P or bt3d.Panel()
    E = bt3.Elig(P)
    codes = P.codes
    eps = bt3d.load_eps()
    rev = PT.load_rev()
    NV = ((0.0, 3), (0.0, 5), (0.0, 8))
    out: dict = {}
    for b in buckets:
        r = {}
        r["p7"] = periodic(P, b, "p7", lambda win: bt3s.p7_rows(P, E, b, codes, rev, win), 12, top=0.0, nmin=n, umin=10,
                           grid=((9, 12, 18), NV, ("標準差期間（月）", "買進檔數")) if with_grid else None)
        r["p3"] = periodic(P, b, "p3", lambda hold: bt3s.p3_rows(P, E, b, codes, eps, hold), 60, top=0.0, nmin=n,
                           umin=20, event=True, grid=((40, 60, 80), NV, ("持有天數", "買進檔數")) if with_grid else None)
        out[b] = r
    return out


# ── 研究結果檔（頁面讀；scripts/run_bt3.py 產生，資料或規則改了才重跑） ──────────────────

V3 = [  # (鍵, 來源, 名稱, 範圍, 版本, 單位, 事件型) —— 前 5 檔版本是使用者選的「本期操作」版本（第 13 節）
    ("v7m", "p7", "月營收驚喜", "M", "top5", "月", False), ("v3l", "p3", "財報驚喜", "L", "top5", "季", True),
    ("v7l", "p7", "月營收驚喜", "L", "top5", "月", False), ("v3m", "p3", "財報驚喜", "M", "top5", "季", True)]
BASKET = [("p7", "月營收驚喜", "月", False), ("p3", "財報驚喜", "季", True), ("p1", "相對強勢", "月", False),
          ("p4", "價值＋動能", "月", False), ("p2", "趨勢突破", "筆", False), ("p5", "短期反轉", "週", False)]


def _r(v, k=2):
    return None if v is None or (isinstance(v, float) and v != v) else (round(v, k) if isinstance(v, float) else v)


def _side(part: dict) -> dict:
    s, p, f, a, e = part["sel"], part["pay"], part.get("fac") or {}, part.get("acc") or {}, part.get("ew") or {}
    ratio = p.get("ratio")
    return {"n": s.get("n"), "xe": _r(s.get("xe")), "t": _r(s.get("t")), "pos": _r(s.get("pos"), 0), "drop5": _r(s.get("drop5")),
            "x2": _r(part.get("x2")), "win": _r(p.get("win"), 0), "m": _r(p.get("m")),
            "ratio": None if ratio is None else (99.0 if ratio == float("inf") else _r(ratio, 1)), "pay_ok": bool(p.get("ok")),
            "sp": _r(f.get("sp")), "sp_t": _r(f.get("t")), "mono": _r(f.get("mono")), "q": [_r(x) for x in f.get("q") or []],
            "cagr": _r(a.get("cagr"), 1), "mdd": _r(a.get("mdd"), 0), "ew_cagr": _r(e.get("cagr"), 1), "ew_mdd": _r(e.get("mdd"), 0),
            "d0": a.get("d0"), "d1": a.get("d1")}


def _curve(units: list[dict]) -> dict:
    s = e = 1.0
    out = {"d": [], "s": [], "e": []}
    for u in units:
        if u.get("r") is None or u.get("ew") is None:
            continue
        s *= 1 + u["r"] / 100
        e *= 1 + u["ew"] / 100
        out["d"].append(u["d"])
        out["s"].append(round(s, 4))
        out["e"].append(round(e, 4))
    return out


def _dist(units: list[dict]) -> dict:
    """每期（或每筆）扣成本後報酬的分布（樣本內＋樣本外）：給「本期操作」卡的預估報酬。"""
    rs = sorted(u["r"] for u in units if u.get("r") is not None)
    if not rs:
        return {}
    q = lambda p: rs[min(len(rs) - 1, max(0, round(p * (len(rs) - 1))))]
    med = statistics.median(rs)
    hd = [u["hd"] for u in units if u.get("hd")]
    return {"n": len(rs), "med": round(med, 2), "p25": round(q(0.25), 2), "p75": round(q(0.75), 2),
            "win": round(100 * sum(1 for x in rs if x > 0) / len(rs)), "kwin": sum(1 for x in rs if x > 0),
            "lo": round(rs[0], 2), "hi": round(rs[-1], 2), "per10": round(med * 1000), "lo10": round(rs[0] * 1000),
            "hd": round(statistics.mean(hd)) if hd else None}


def _row(k, src, name, b, ver, unit, event, r) -> dict:
    nb, no = r.get("nb") or {}, r.get("nb_oos") or {}
    return {"k": k, "src": src, "name": name, "b": b, "ver": ver, "unit": unit, "event": event,
            "grade": r["grade"]["grade"], "why": r["grade"]["why"],
            "oos": _side(r["oos"]), "ins": _side(r["ins"]),
            "nb": {"pos": nb.get("pos"), "n": nb.get("n"), "lbl": nb.get("lbl"), "ad": nb.get("ad"), "bd": nb.get("bd"),
                   "cells": [[c[0], c[1], _r(c[2])] for c in nb.get("cells") or []]},
            "nb_oos": {"pos": no.get("pos"), "n": no.get("n")},
            "sub": [[x["from"], x["n"], _r(x["avg"])] for x in r.get("sel_sub") or []],
            "fsub": [[x["from"], x["n"], _r(x["avg"])] for x in r.get("fac_sub") or []],
            "curve": _curve([u for u in r.get("units") or [] if "ew" in u]) if src != "p2" else None,
            "dist": _dist(r.get("units") or [])}


def export(main: dict, t5: dict, P) -> dict:
    rows = [_row(k, src, name, b, ver, unit, ev, t5[b][src]) for k, src, name, b, ver, unit, ev in V3]
    for b in ("M", "L"):
        for src, name, unit, ev in BASKET:
            rows.append(_row(f"b{src[1]}{b.lower()}", src, name, b, "basket", unit, ev, main[b][src]))
    return {"asof": P.cal[-1], "oos_end": OOS_END, "meta": main.get("meta"),
            "list": [k for k, src, _, b, _, _, _ in V3 if t5[b][src]["grade"]["grade"] in ("A", "B")], "rows": rows}
