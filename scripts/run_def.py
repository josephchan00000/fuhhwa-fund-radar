#!/usr/bin/env python3
"""個股策略防守研究（arm/lab/defspec.py VER 1、arm/lab/defres.py；docs/lab_stock_page_plan.md 第 9、10 節）。

  TZ=Asia/Taipei python3 scripts/run_def.py --tw                       # 新飆股、財報驚喜（main 上的資料）
  USSX_DIR=<資料分支>/data/lab/ussx TZ=Asia/Taipei python3 scripts/run_def.py --us   # 美股強勢品質股
→ data/lab/def_research.json（兩次各寫自己那一段，另一段保留）。只讀資料，不抓任何東西。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "src"))
sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from arm.clock import today_tw  # noqa: E402
from arm.lab import defres as D  # noqa: E402
from arm.lab import defspec as S  # noqa: E402

OUT = ROOT / "data" / "lab" / "def_research.json"


def log(*a):
    print("[def]", *a, flush=True)


def _r(x, n=4):
    return None if x is None else round(float(x), n)


# ── 新飆股 ────────────────────────────────────────────────────────────────────

def boom() -> dict:
    import run_w7 as W
    import run_w10 as W10
    from arm.lab import ks
    t0 = time.time()
    off = json.loads((ROOT / S.BASE_SRC["boom"]).read_text(encoding="utf-8"))
    end = off["d"][-1]
    R = json.loads((W.REPORTS / "W10_results.json").read_text(encoding="utf-8"))
    P = W10.prep()
    g = W10.pick_g(R["pick"])
    ctx, mask, wk = P["ctx"], P["mask"], P["wk"]
    m = ctx.m

    def go(e, **kw):
        return W10.run(ctx, mask, wk, g, W10.S.START, e, **kw)

    def three(eq: pd.Series) -> dict:
        st = W.curve_stats(eq)
        return D.three(*({"cagr": _r(st["cagr"][k]), "mdd": _r(st["mdd"][k])} for k in ("all", "h1", "h2")))

    base = go(end)
    got = W.curve_stats(base.equity)["cagr"]["all"]
    ok = abs(got - off["cagr"]) <= S.BASE_CHECK
    log(f"新飆股 基準 {got * 100:.2f}%（官方 {off['cagr'] * 100:.2f}%）{'對上' if ok else '對不上'}，{time.time() - t0:.0f}s")
    idx = [float(x) for x in m.index_level]
    gates = {n: np.array(D.ma_gate(idx, n)) for n in (S.D1_MA, *S.D1_ALT)}
    ind = D.TwInd()
    dates = [d.date().isoformat() for d in m.dates]
    codes = list(m.stocks)

    def f(i, j):
        return ind.at(str(codes[j]), dates[i])

    variants = {f"d1_{n}": {"gate": gates[n]} for n in (S.D1_MA, *S.D1_ALT)}
    variants.update({f"d2_{k}": {"ind": f, "cap_k": k} for k in (S.D2_K, *S.D2_ALT)})
    variants["d12"] = {"gate": gates[S.D1_MA], "ind": f, "cap_k": S.D2_K}
    res = {"base": base}
    for k, kw in variants.items():
        res[k] = go(end, **kw)
        log(f"  {k} {time.time() - t0:.0f}s")
    out = {k: three(r.equity) for k, r in res.items()}
    ntr = {k: int(len(r.trades)) if r.trades is not None else 0 for k, r in res.items()}
    # D3：基準淨值加熔斷
    eq = base.equity.dropna()
    bench = ks.tw_bench()
    ds = [d.date().isoformat() for d in eq.index]
    keep = [i for i, d in enumerate(ds) if bench.get(d)]
    nav = [float(eq.iloc[i]) for i in keep]
    bn = [float(bench[ds[i]]) for i in keep]
    ix = [eq.index[i] for i in keep]
    d3 = {f"d3_{x:g}": dict(mult=x) for x in (S.D3_MULT, *S.D3_ALT)}
    d3["d3_fix"] = dict(fixed=S.D3_FIXED)
    ev3 = {}
    for k, kw in d3.items():
        nv, ev = D.ks_overlay(nav, bn, **kw)
        out[k] = three(pd.Series(nv, index=ix))
        ev3[k] = [{"d": ds[keep[e["i"]]], "k": e["k"]} for e in ev]
    yearly = {k: {str(y): _r(v) for y, v in W.curve_stats(r.equity)["yearly"].items()} for k, r in res.items()}
    # 2026-10 以後（到最新資料，只描述）
    rec = {}
    for k in ("base", f"d1_{S.D1_MA}", f"d2_{S.D2_K}"):
        e = go(None, **variants.get(k, {})).equity.dropna()
        a = e[e.index < pd.Timestamp(S.RECENT_FROM)]
        if len(a):
            rec[k] = {"from": str(a.index[-1].date()), "to": str(e.index[-1].date()), "ret": _r(e.iloc[-1] / a.iloc[-1] - 1)}
    primary = {"D1": f"d1_{S.D1_MA}", "D2": f"d2_{S.D2_K}", "D3": f"d3_{S.D3_MULT:g}"}
    log(f"新飆股 完成 {time.time() - t0:.0f}s")
    return {"end": end, "base_check": {"got": _r(got, 6), "ref": off["cagr"], "ok": ok}, "stats": out, "n_trades": ntr,
            "d3_events": ev3, "yearly": yearly, "recent": rec, "judge": D.verdicts(out["base"], out, primary)}


# ── 財報驚喜（大型股） ─────────────────────────────────────────────────────────

def v3l() -> dict:
    from arm.lab import bt3, bt3d, bt3l, bt3s, core, ks
    t0 = time.time()
    off = next(x for x in json.loads((ROOT / S.BASE_SRC["v3l"]).read_text(encoding="utf-8"))["rows"] if x["k"] == "v3l")["all"]
    end = off["d1"]
    P = bt3d.Panel()
    pk = core.sleeve_periods(P)
    E = bt3.Elig(P)
    rows = bt3s.p3_rows(P, E, "L", P.codes, bt3d.load_eps(), 60)
    done = [r for r in rows if r[1] is not None]
    split = S.HALVES["v3l"][1]

    def curve(pp, to=end):
        return [(i, v) for i, v in bt3.account(P, pp, "L")["curve"] if to is None or P.cal[i] <= to]

    def three(cv) -> dict:
        a = bt3.curve_stats(cv, P.cal)
        h1, h2 = bt3l._sub(P, cv, None, split), bt3l._sub(P, cv, split, None)
        return D.three(*({"cagr": _r(x["cagr"] / 100), "mdd": _r(x["mdd"] / 100)} for x in (a, h1, h2)))

    base_cv = curve(pk)
    got = bt3.curve_stats(base_cv, P.cal)["cagr"]
    ok = round(got, 1) == off["cagr"]
    log(f"財報驚喜 基準 {got:.2f}%（官方 {off['cagr']}%）{'對上' if ok else '對不上'}，{time.time() - t0:.0f}s")
    ind = D.TwInd()
    pps = {"base": pk}
    for n in (S.D1_MA, *S.D1_ALT):
        gt = D.ma_gate(P.idx, n)
        pps[f"d1_{n}"] = [p for p in pk if gt[p[0]]]
    for k in (S.D2_K, *S.D2_ALT):
        pps[f"d2_{k}"] = D.cap_pick(done, k, ind, P.cal)
    gt = D.ma_gate(P.idx, S.D1_MA)
    pps["d12"] = [p for p in D.cap_pick(done, S.D2_K, ind, P.cal) if gt[p[0]]]
    cvs = {k: curve(v) for k, v in pps.items()}
    out = {k: three(cv) for k, cv in cvs.items()}
    nper = {k: len([p for p in v if P.cal[p[0]] <= end]) for k, v in pps.items()}
    # D3：基準的逐日淨值（沒有部位的日子不動）加熔斷
    pts = dict(base_cv)
    i0, i1 = min(pts), max(pts)
    bench = ks.tw_bench()
    days, nav, last = [], [], None
    for i in range(i0, i1 + 1):
        last = pts.get(i, last)
        if bench.get(P.cal[i]) and last:
            days.append(i)
            nav.append(last)
    bn = [float(bench[P.cal[i]]) for i in days]
    ev3 = {}
    d3 = {f"d3_{x:g}": dict(mult=x) for x in (S.D3_MULT, *S.D3_ALT)}
    d3["d3_fix"] = dict(fixed=S.D3_FIXED)
    for k, kw in d3.items():
        nv, ev = D.ks_overlay(nav, bn, **kw)
        out[k] = three(list(zip(days, nv)))
        ev3[k] = [{"d": P.cal[days[e["i"]]], "k": e["k"]} for e in ev]
    rec = {}
    for k in ("base", f"d1_{S.D1_MA}", f"d2_{S.D2_K}"):
        cv = curve(pps[k], None)
        a = [(i, v) for i, v in cv if P.cal[i] < S.RECENT_FROM]
        if a and cv:
            rec[k] = {"from": P.cal[a[-1][0]], "to": P.cal[cv[-1][0]], "ret": _r(cv[-1][1] / a[-1][1] - 1)}
    primary = {"D1": f"d1_{S.D1_MA}", "D2": f"d2_{S.D2_K}", "D3": f"d3_{S.D3_MULT:g}"}
    log(f"財報驚喜 完成 {time.time() - t0:.0f}s")
    return {"end": end, "base_check": {"got": _r(got, 3), "ref": off["cagr"], "ok": ok}, "stats": out, "n_periods": nper,
            "d3_events": ev3, "recent": rec, "judge": D.verdicts(out["base"], out, primary)}


# ── 美股強勢品質股 ─────────────────────────────────────────────────────────────

def us_sector(P: dict) -> dict[int, str | None]:
    """代號欄 → GICS 產業部門（data/lab/ussx_gics.json，現在的分類）；不在 S&P 1500 的用資料分支 Nasdaq 篩選器的 sector；都沒有＝None。"""
    from arm.lab import ussxdata as UD
    gics = (json.loads((ROOT / "data" / "lab" / "ussx_gics.json").read_text(encoding="utf-8")).get("s") or {})
    scr = UD.load_screen() or {}
    rows = scr.get("rows") if isinstance(scr, dict) and "rows" in scr else scr
    sec: dict[str, str] = {}
    if isinstance(rows, dict):
        for k, v in rows.items():
            x = v.get("sector") if isinstance(v, dict) else None
            if x:
                sec[UD.ysym(k)] = x
    elif isinstance(rows, list):
        for v in rows:
            if isinstance(v, dict) and v.get("symbol") and v.get("sector"):
                sec[UD.ysym(v["symbol"])] = v["sector"]
    out = {}
    for j, sym in enumerate(P["sym"]):
        g = gics.get(sym) or gics.get(sym.replace("-", "."))
        out[j] = (g[1] if g and len(g) > 1 and g[1] else None) or sec.get(UD.ysym(sym))
    return out


def qm() -> dict:
    from arm.lab import ussxbook as BK
    from arm.lab import ussxpanel as UP
    from arm.lab import ussxqm as QM
    from arm.lab import ussxspec as X
    t0 = time.time()
    off = json.loads((ROOT / S.BASE_SRC["qm"]).read_text(encoding="utf-8"))["sleeve"]["main"]
    P = UP.load()
    C = QM.context(P)
    cal = C["cal"]
    a14 = QM.a_of(cal, X.QM_EVAL)
    end = off["b"]
    b_end = max(k for k, d in enumerate(cal) if d <= end) + 1
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))

    def go(sg, cap=None):
        r = QM.run(C, sg, "spx", X.COST["stk"], cap=cap)
        return r, QM.rets(C, r)

    def three(rr) -> dict:
        st = BK.curve_stats(cal, rr, a14, b_end)
        h1, h2 = st["halves"]
        return D.three(*({"cagr": _r(x["cagr"]), "mdd": _r(x["mdd"])} for x in (st, h1, h2)))

    base_r, base_rr = go(sig)
    got = BK.curve_stats(cal, base_rr, a14, b_end)["cagr"]
    ok = abs(got - off["cagr"]) <= S.BASE_CHECK
    log(f"美股 基準 {got * 100:.2f}%（官方 {off['cagr'] * 100:.2f}%）{'對上' if ok else '對不上'}，{time.time() - t0:.0f}s")
    spy = P["sym"].index("SPY")
    px = [float(x) for x in C["Cf"][:, spy]]
    sect = us_sector(P)
    fn = sect.get
    sigs = {"base": (sig, None)}
    for n in (S.D1_MA, *S.D1_ALT):
        gt = D.ma_gate(px, n)
        sigs[f"d1_{n}"] = ({i: v for i, v in sig.items() if gt[i]}, None)
    for k in (S.D2_K, *S.D2_ALT):
        sigs[f"d2_{k}"] = (sig, (fn, k))
    gt = D.ma_gate(px, S.D1_MA)
    sigs["d12"] = ({i: v for i, v in sig.items() if gt[i]}, (fn, S.D2_K))
    rrs, ntr = {"base": base_rr}, {"base": len(base_r["trades"])}
    for k, (sg, cap) in sigs.items():
        if k == "base":
            continue
        r, rr = go(sg, cap)
        rrs[k], ntr[k] = rr, len(r["trades"])
        log(f"  {k} {time.time() - t0:.0f}s")
    out = {k: three(rr) for k, rr in rrs.items()}
    # D3：基準淨值加熔斷（S&P 500 含息當大盤，同 ks.bt_qm）
    sp = np.nan_to_num(np.asarray(C["PQ"]["spx"]["idle"], dtype=float))
    nav = list(np.cumprod(1 + np.nan_to_num(base_rr[a14:b_end])))
    bn = list(np.cumprod(1 + sp[a14:b_end]))
    ev3 = {}
    d3 = {f"d3_{x:g}": dict(mult=x) for x in (S.D3_MULT, *S.D3_ALT)}
    d3["d3_fix"] = dict(fixed=S.D3_FIXED)
    for k, kw in d3.items():
        nv, ev = D.ks_overlay(nav, bn, **kw)
        r2 = np.zeros(len(cal))
        r2[a14 + 1:b_end] = np.asarray(nv[1:]) / np.asarray(nv[:-1]) - 1
        out[k] = three(r2)
        ev3[k] = [{"d": cal[a14 + e["i"]], "k": e["k"]} for e in ev]
    rec = {}
    i0 = max(k for k, d in enumerate(cal) if d < S.RECENT_FROM)
    for k in ("base", f"d1_{S.D1_MA}", f"d2_{S.D2_K}"):
        rr = rrs[k]
        rec[k] = {"from": cal[i0], "to": cal[-1], "ret": _r(float(np.prod(1 + np.nan_to_num(rr[i0 + 1:]))) - 1)}
    nsec = sum(1 for v in sect.values() if v)
    primary = {"D1": f"d1_{S.D1_MA}", "D2": f"d2_{S.D2_K}", "D3": f"d3_{S.D3_MULT:g}"}
    log(f"美股 完成 {time.time() - t0:.0f}s")
    return {"end": end, "base_check": {"got": _r(got, 6), "ref": off["cagr"], "ok": ok}, "stats": out, "n_trades": ntr,
            "sector_known": [nsec, len(sect)], "d3_events": ev3, "recent": rec, "judge": D.verdicts(out["base"], out, primary)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tw", action="store_true")
    ap.add_argument("--us", action="store_true")
    ap.add_argument("--only", default="", help="只跑 boom 或 v3l（除錯用）")
    a = ap.parse_args()
    doc = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    doc.update({"spec": S.VER, "spec_fp": S.fingerprint(), "made": today_tw().isoformat()})
    if a.tw:
        if a.only in ("", "boom"):
            doc["boom"] = boom()
        if a.only in ("", "v3l"):
            doc["v3l"] = v3l()
    if a.us:
        doc["qm"] = qm()
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", "utf-8")
    log("寫入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
