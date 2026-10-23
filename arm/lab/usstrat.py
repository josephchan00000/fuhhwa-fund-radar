"""美股個股策略（規格 usstratspec VER 1；docs/lab_core70_plan.md 第 15 節）。研究用，不上頁面。

  panel()          S&P 500 歷史成分股 × 交易日（^GSPC 的日曆）的還原收盤（nan＝沒有）、當天是不是成分股
  events(P)        財報驚喜：每週最後一個交易日 → [(代號, 驚喜)]（驚喜 > 0、至少 MIN_EST 位分析師、當天是成分股而且有收盤）
  run_u1(P, ev)    U1：sxlive.Book（和台股飆股同一個引擎；開盤＝收盤、沒有漲跌停、零股、沒有成交量上限、每一邊 COST）
  run_month(P, f)  U2、U3、同一批等權：每個月最後一個交易日決定、下一個交易日收盤換股、只有換掉的部位算成本
  research()       三條＋鄰近＋對照＋判定 → data/lab/usstrat_research.json（scripts/run_usstrat.py）
"""
from __future__ import annotations

import bisect
import math
from datetime import date

import numpy as np

from . import usstratspec as S


# ── 資料 ─────────────────────────────────────────────────────────────

def panel(start: str = "2006-01-01") -> dict:
    """{"cal", "sym", "C"（T×N 還原收盤）, "M"（T×N 成分股）, "spx"（^GSPC 收盤）, "i_spx"（cal 在 xstrat 日曆的位置）}。"""
    from . import usstk as U
    from . import xstrat as XT
    D = XT.data("spx")
    cal_all = list(D["cal"])
    k0 = next(k for k, d in enumerate(cal_all) if d >= start)
    cal = cal_all[k0:]
    ix = {d: i for i, d in enumerate(cal)}
    meta = U.load_meta()
    syms = sorted(s for s, n in (meta.get("px_done") or {}).items() if n)
    T, N = len(cal), len(syms)
    C = np.full((T, N), np.nan)
    for j, s in enumerate(syms):
        ds, ps = U.load_px(s)
        for d, p in zip(ds, ps):
            i = ix.get(d)
            if i is not None and p and p > 0:
                C[i, j] = p
    col = {s: j for j, s in enumerate(syms)}
    M = np.zeros((T, N), dtype=bool)
    for s, a, z in meta.get("spans") or []:
        j = col.get(s)
        if j is None:
            continue
        lo = bisect.bisect_left(cal, a)
        hi = T if not z else bisect.bisect_left(cal, z)
        if lo < hi:
            M[lo:hi, j] = True
    return {"cal": cal, "sym": syms, "col": col, "C": C, "M": M, "spx": np.asarray(D["px"][k0:], dtype=float), "k0": k0}


def history_ok(C: np.ndarray, look: int = S.LOOK) -> np.ndarray:
    """往前 look 個交易日（含當天，共 look＋1 天）都有收盤。"""
    have = np.isfinite(C).astype(np.int32)
    cs = np.cumsum(have, axis=0)
    out = np.zeros(C.shape, dtype=bool)
    out[look:] = (cs[look:] - np.vstack([np.zeros((1, C.shape[1]), dtype=np.int64), cs[:-look - 1]])) == look + 1
    return out


def period_ends(cal: list[str], kind: str) -> list[int]:
    """每個月（m）或每週（w）的最後一個交易日（照日曆本身）。"""
    def key(d):
        x = date.fromisoformat(d)
        return (x.year, x.month) if kind == "m" else tuple(x.isocalendar())[:2]
    return [i for i in range(len(cal)) if i + 1 == len(cal) or key(cal[i + 1]) != key(cal[i])]


def surprise(a: float, f: float) -> float:
    return (a - f) / max(abs(f), S.EPS_FLOOR)


def events(P: dict, years: range | None = None) -> dict[int, list]:
    """{週末索引: [(代號, 驚喜)]}：公布日所在那一週的最後一個交易日；驚喜高到低、同分依代號。"""
    from . import usstk as U
    cal, col, C, M = P["cal"], P["col"], P["C"], P["M"]
    wk = period_ends(cal, "w")
    wkey = {}
    for i in wk:
        x = date.fromisoformat(cal[i])
        wkey[tuple(x.isocalendar())[:2]] = i
    out: dict[int, dict] = {}
    for y in years or range(int(cal[0][:4]), int(cal[-1][:4]) + 1):
        for d, rows in (U.load_earn(y).get("rows") or {}).items():
            i = wkey.get(tuple(date.fromisoformat(d).isocalendar())[:2])
            if i is None or cal[i] < d:
                continue
            for r in rows:
                s, a, f, n = U.ysym(str(r[0])), r[1], r[2], r[3]
                j = col.get(s)
                if j is None or a is None or f is None or n is None or n < S.MIN_EST:
                    continue
                if not (M[i, j] and np.isfinite(C[i, j])):
                    continue
                x = surprise(float(a), float(f))
                if x > 0 and x > out.setdefault(i, {}).get(s, -1.0):
                    out[i][s] = x
    return {i: sorted(v.items(), key=lambda kv: (-kv[1], kv[0])) for i, v in out.items()}


# ── U1：財報驚喜（sxlive.Book） ──────────────────────────────────────────

def book_px(P: dict, syms) -> dict:
    """Book 要的欄位：開高低收都是收盤、f＝1、沒有成交值與成交量（滑價固定 COST、沒有量的上限）、沒有漲跌停。"""
    C = P["C"]
    T = len(P["cal"])
    out = {}
    for s in syms:
        j = P["col"][s]
        c = [None if not np.isfinite(x) else float(x) for x in C[:, j]]
        cff, prev = [None] * T, None
        for i, x in enumerate(c):
            if x is not None:
                prev = x
            cff[i] = prev
        last = max((i for i, x in enumerate(c) if x is not None), default=-1)
        out[s] = {"o": c, "h": c, "l": c, "c": c, "cff": cff, "f": [1.0] * T, "av": [None] * T, "avv": [None] * T,
                  "lu": [False] * T, "ld": [False] * T, "last": last}
    return out


def trade_cfg(weight: float = S.BOOK["weight"], hold: int = S.BOOK["hold"]) -> dict:
    return {"capital": 1_000_000.0, "weight": weight, "hold": hold, "lot": 1, "max_weight": max(0.20, weight),
            "max_adv": math.inf, "max_positions": S.BOOK["max_positions"], "commission": 0.0, "discount": 1.0,
            "min_fee": 0.0, "sell_tax": 0.0, "slip_tiers": ((0.0, S.COST),)}


def run_u1(P: dict, ev: dict, i0: int, weight: float = S.BOOK["weight"], hold: int = S.BOOK["hold"]) -> dict:
    from .sxlive import Book
    T = len(P["cal"])
    syms = sorted({s for v in ev.values() for s, _ in v})
    bk = Book(book_px(P, syms), T, None, trade_cfg(weight, hold))
    eq = [bk.step(i, ev.get(i)) for i in range(i0, T)]
    cap = bk.T["capital"]
    nav = np.full(T, np.nan)
    nav[i0:] = np.asarray(eq) / cap
    return {"nav": nav, "trades": bk.trades, "open": len(bk.pos)}


# ── U2、U3、同一批等權：每月換股 ─────────────────────────────────────────

def run_month(P: dict, pick, i0: int) -> dict:
    """pick(m) → 第 m 天收盤決定的名單；第 m＋1 天收盤換成等權、只有換掉的部位算成本（每一邊 COST）。"""
    C = P["C"]
    T, N = C.shape
    Cf = C.copy()
    for i in range(1, T):                                  # 沒有收盤的日子沿用前一天（被併購、下市的停在最後收盤）
        bad = ~np.isfinite(Cf[i])
        Cf[i, bad] = Cf[i - 1, bad]
    me = set(period_ends(P["cal"], "m"))
    units = np.zeros(N)
    cash = 1.0
    nav = np.full(T, np.nan)
    turns, held = [], []
    for i in range(i0, T):
        if (i - 1) in me and i - 1 >= i0 - 1:              # 前一天是月底 → 今天收盤換股
            px = Cf[i]
            val = np.where(units != 0, units * np.nan_to_num(px), 0.0)
            V = cash + val.sum()
            names = [j for j in pick(i - 1) if np.isfinite(C[i, j])]
            tgt = np.zeros(N)
            if names:
                tgt[names] = V / len(names)
            turn = float(np.abs(tgt - val).sum())
            fee = S.COST * turn
            V2 = V - fee
            scale = V2 / V if V > 0 else 0.0
            tgt *= scale
            units = np.zeros(N)
            ok = tgt > 0
            units[ok] = tgt[ok] / px[ok]
            cash = V2 - tgt.sum()
            turns.append(turn / V if V > 0 else 0.0)
            held.append(len(names))
        nav[i] = cash + float(np.nansum(units * np.nan_to_num(Cf[i])))
    return {"nav": nav, "turn": float(np.mean(turns)) if turns else None, "n": float(np.mean(held)) if held else None}


def picker(P: dict, kind: str, top: int = S.TOP_N):
    """U2（動能 12-1）、U3（52 週新高）、EW（同一批成分股全部）的選股函式。"""
    C, M = P["C"], P["M"]
    U = M & np.isfinite(C)
    H = U & history_ok(C)

    def ew(m):
        return list(np.nonzero(U[m])[0])

    def mom(m):
        js = np.nonzero(H[m])[0]
        sc = C[m - S.SKIP, js] / C[m - S.LOOK, js] - 1
        order = sorted(range(len(js)), key=lambda k: (-sc[k], P["sym"][js[k]]))
        return [int(js[k]) for k in order[:top]]

    def high(m):
        js = np.nonzero(H[m])[0]
        hi = np.nanmax(C[m - S.LOOK:m + 1, js], axis=0)
        r = C[m, js] / hi
        mo = C[m - S.SKIP, js] / C[m - S.LOOK, js] - 1
        order = sorted(range(len(js)), key=lambda k: (-r[k], -mo[k], P["sym"][js[k]]))
        return [int(js[k]) for k in order[:top]]
    return {"EW": ew, "U2": mom, "U3": high}[kind]


# ── 統計與判定 ────────────────────────────────────────────────────────

def cagr(cal: list[str], nav: np.ndarray, a: str, b: str) -> float | None:
    """[a, b] 的年化：以 a 之前最後一天當起點（沒有就用期間第一天）。"""
    ks = [k for k in range(len(cal)) if np.isfinite(nav[k])]
    pre = [k for k in ks if cal[k] < a]
    win = [k for k in ks if a <= cal[k] <= b]
    if len(win) < 2:
        return None
    k0 = pre[-1] if pre else win[0]
    yrs = (date.fromisoformat(cal[win[-1]]) - date.fromisoformat(cal[k0])).days / 365.25
    return float((nav[win[-1]] / nav[k0]) ** (1 / yrs) - 1) if yrs > 0 and nav[k0] > 0 else None


def mdd(nav: np.ndarray) -> float | None:
    x = nav[np.isfinite(nav)]
    if not len(x):
        return None
    return float(np.max(1 - x / np.maximum.accumulate(x)))


def yearly(cal: list[str], nav: np.ndarray) -> dict:
    out, prev = {}, None
    for y in sorted({d[:4] for d, v in zip(cal, nav) if np.isfinite(v)}):
        ks = [k for k, d in enumerate(cal) if d[:4] == y and np.isfinite(nav[k])]
        base = prev if prev is not None else nav[ks[0]]
        out[y] = float(nav[ks[-1]] / base - 1)
        prev = nav[ks[-1]]
    return out


def stats(cal: list[str], nav: np.ndarray) -> dict:
    P = {"all": (S.START, "2100-12-31"), "h1": S.HALVES[0], "h2": S.HALVES[1]}
    return {"cagr": {k: cagr(cal, nav, *v) for k, v in P.items()}, "mdd": mdd(nav), "yearly": yearly(cal, nav)}


def trade_stats(trades: list) -> dict:
    if not trades:
        return {"n": 0}
    r = sorted(t[4] for t in trades)
    pnl = sorted((t[7] for t in trades), reverse=True)
    k = max(1, len(pnl) // 10)
    tot = sum(pnl)
    return {"n": len(r), "win": sum(1 for x in r if x > 0) / len(r), "avg": sum(r) / len(r), "med": r[len(r) // 2],
            "top10": sum(pnl[:k]) / tot if tot > 0 else None}


def judge(st: dict, ew: dict, spx: dict) -> dict:
    c1 = (st["cagr"]["all"] - ew["cagr"]["all"] >= S.PASS["ew_pts"] / 100
          and all(st["cagr"][h] > ew["cagr"][h] for h in ("h1", "h2")))
    c2 = all(st["cagr"][h] > spx["cagr"][h] for h in ("all", "h1", "h2"))
    c3 = st["mdd"] <= spx["mdd"] + S.PASS["mdd_extra"] / 100
    return {"c1": c1, "c2": c2, "c3": c3, "pass": c1 and c2 and c3}


# ── 研究 ─────────────────────────────────────────────────────────────

def research(P: dict | None = None) -> dict:
    """三條主要版本＋鄰近、同一批等權、S&P 500 含息 → 判定（usstratspec 第 PASS 條）。"""
    from . import tilt as TL
    from . import xstrat as XT
    P = P or panel()
    cal = P["cal"]
    i0 = next(k for k, d in enumerate(cal) if d >= S.START)
    D = XT.data("spx")
    tot = np.asarray(TL.carry_inputs("spx", list(D["cal"]), np.asarray(D["px"], dtype=float))["tot"], dtype=float)[P["k0"]:]
    spx = np.full(len(cal), np.nan)
    spx[i0:] = np.cumprod(np.concatenate([[1.0], 1 + np.nan_to_num(tot[i0 + 1:])]))
    runs: dict = {}
    ev = events(P)
    r = run_u1(P, ev, i0)
    runs["U1"] = {**stats(cal, r["nav"]), "trades": trade_stats(r["trades"]), "nav": r["nav"]}
    for k in ("EW", "U2", "U3"):
        r = run_month(P, picker(P, k), i0)
        runs[k] = {**stats(cal, r["nav"]), "turn": r["turn"], "n": r["n"], "nav": r["nav"]}
    bench = {"EW": runs.pop("EW"), "SPX": {**stats(cal, spx), "nav": spx}}
    nb: dict = {}
    for k, vs in S.NEIGHBORS.items():
        nb[k] = []
        for v in vs:
            if k == "U1":
                rr = run_u1(P, ev, i0, weight=v.get("weight", S.BOOK["weight"]), hold=v.get("hold", S.BOOK["hold"]))
            else:
                rr = run_month(P, picker(P, k, v["top"]), i0)
            st = stats(cal, rr["nav"])
            nb[k].append({"v": v, "cagr": st["cagr"], "mdd": st["mdd"]})
    verdict = {}
    E, X = bench["EW"], bench["SPX"]
    sign = lambda x: (x > 0) - (x < 0)  # noqa: E731
    for k in S.STRATS:
        v = judge(runs[k], E, X)
        base = sign(runs[k]["cagr"]["all"] - E["cagr"]["all"])
        v["sensitive"] = any(sign(n["cagr"]["all"] - E["cagr"]["all"]) != base for n in nb[k])
        verdict[k] = v
    cover = {cal[m][:4]: [int((P["M"][m] & np.isfinite(P["C"][m])).sum()), int(P["M"][m].sum())]
             for m in period_ends(cal, "m") if cal[m][5:7] == "06"}
    return {"ver": S.VER, "spec": S.SPEC_DATE, "made": date.today().isoformat(), "last": cal[-1], "cal": cal,
            "runs": runs, "bench": bench, "neighbors": nb, "verdict": verdict, "cover": cover,
            "events": {"weeks": len(ev), "n": sum(len(v) for v in ev.values())}}
