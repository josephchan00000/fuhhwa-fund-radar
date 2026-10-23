"""美股飆股研究 A：存活偏誤的量法（ussxspec VER 1 的 SURV；docs/lab_us_sleeve_plan.md 第 4.3、9 節）。研究用，不上頁面。

每個月最後一個交易日收盤：依 20 日平均成交值排名（實際成交價 ≥ px_min、有股價滿 age 個交易日、不是 ETF、不要求財報），
每一組等權、下一個月抱著（含息、不算成本）；PIT＝當時的 S&P 500 成分股（usstk 的 spans）有股價的等權。
和 ETF 的含息價格比（ETF 加回管理費）：差＝組的年化 − ETF 的年化。持有中資料結束（下市）的股票用最後一天的收盤。
"""
from __future__ import annotations

import bisect
import math
from datetime import date

import numpy as np

from . import ussxpanel as UP
from . import ussxspec as X


def month_ends(cal: list[str]) -> list[int]:
    out = []
    for i, d in enumerate(cal):
        if i + 1 == len(cal) or cal[i + 1][:7] != d[:7]:
            out.append(i)
    return out


def periods(cal: list[str], start: str = X.SURV["start"]) -> list[tuple[int, int]]:
    """[(決定日, 持有到)]：決定日＝start 之前最後一個月底起的每一個月底；最後一段持有到資料最後一天。"""
    me = month_ends(cal)
    k0 = max(k for k, i in enumerate(me) if cal[i] < start)
    out = []
    for k in range(k0, len(me)):
        a = me[k]
        b = me[k + 1] if k + 1 < len(me) else len(cal) - 1
        if b > a:
            out.append((a, b))
    return out


def hold_ret(C: np.ndarray, a: int, b: int, cols: np.ndarray) -> np.ndarray:
    """cols 從 a 收盤抱到 b 收盤的含息報酬；b 沒有收盤（資料提早結束）用 a～b 之間最後一個收盤。"""
    seg = C[a:b + 1, cols]
    c0 = seg[0]
    have = np.isfinite(seg)
    lastk = np.where(have.any(axis=0), seg.shape[0] - 1 - np.argmax(have[::-1], axis=0), 0)
    c1 = seg[lastk, np.arange(seg.shape[1])]
    return c1 / c0 - 1


def group_returns(P: dict, pers: list[tuple[int, int]], groups: dict, D20: np.ndarray, A: np.ndarray,
                  pit: np.ndarray | None = None) -> dict:
    """{組: [每一期的等權報酬]}、{組: [每一期幾檔]}。groups＝{名稱: (第幾名起, 到第幾名)}；pit＝T×N 當時是不是成分股。"""
    C, RAW, etf = P["C"], P["RAW"], P["etf"]
    ret = {g: [] for g in groups}
    cnt = {g: [] for g in groups}
    if pit is not None:
        ret["PIT"], cnt["PIT"] = [], []
    for a, b in pers:
        with np.errstate(invalid="ignore"):
            ok = (~etf) & np.isfinite(C[a]) & (np.nan_to_num(RAW[a], nan=0.0) >= X.SURV["px_min"]) & (A[a] >= X.SURV["age"]) & \
                 np.isfinite(D20[a])
        cols = np.nonzero(ok)[0]
        order = cols[np.lexsort((np.array(P["sym"])[cols], -D20[a, cols]))]     # 成交值高到低，同值依代號
        for g, (lo, hi) in groups.items():
            sel = order[lo - 1:hi]
            r = hold_ret(C, a, b, sel) if len(sel) else np.array([])
            ret[g].append(float(np.mean(r)) if len(r) else float("nan"))
            cnt[g].append(int(len(sel)))
        if pit is not None:
            sel = np.nonzero(pit[a] & np.isfinite(C[a]) & ~etf)[0]
            r = hold_ret(C, a, b, sel) if len(sel) else np.array([])
            ret["PIT"].append(float(np.mean(r)) if len(r) else float("nan"))
            cnt["PIT"].append(int(len(sel)))
    return {"ret": ret, "n": cnt}


def etf_returns(P: dict, pers: list[tuple[int, int]], sym: str, fee: float) -> list[float]:
    """ETF 每一期的含息報酬，加回管理費（年費 × 期間的日曆天 ÷ 365.25）。"""
    j = P["col"][sym]
    C, cal = P["C"], P["cal"]
    out = []
    for a, b in pers:
        days = (date.fromisoformat(cal[b]) - date.fromisoformat(cal[a])).days
        out.append(float(C[b, j] / C[a, j] - 1) + fee * days / 365.25)
    return out


def cagr(rs: list[float], cal: list[str], pers: list[tuple[int, int]]) -> float | None:
    v = 1.0
    for r in rs:
        if not math.isfinite(r):
            return None
        v *= 1 + r
    yrs = (date.fromisoformat(cal[pers[-1][1]]) - date.fromisoformat(cal[pers[0][0]])).days / 365.25
    return v ** (1 / yrs) - 1 if yrs > 0 and v > 0 else None


def yearly(rs: list[float], cal: list[str], pers: list[tuple[int, int]]) -> dict[str, float]:
    """每一年（持有到哪一天的年份）的報酬。"""
    out: dict[str, float] = {}
    for r, (a, b) in zip(rs, pers):
        y = cal[b][:4]
        out[y] = (1 + out.get(y, 0.0)) * (1 + r) - 1
    return out


def pit_mask(P: dict) -> np.ndarray:
    """T×N：那一天是不是 S&P 500 成分股（usstk 的 spans；代號是當時的代號，對到資料裡同一個代號）。"""
    from . import usstk as U
    cal, col = P["cal"], P["col"]
    T, N = P["C"].shape
    M = np.zeros((T, N), dtype=bool)
    for s, a, z in U.load_meta().get("spans") or []:
        j = col.get(U.ysym(s))
        if j is None:
            continue
        lo = bisect.bisect_left(cal, a)
        hi = T if not z else bisect.bisect_left(cal, z)
        if lo < hi:
            M[lo:hi, j] = True
    return M


def research(P: dict | None = None) -> dict:
    P = P or UP.load()
    cal = P["cal"]
    D20, A = UP.dv20(P), UP.age(P)
    pers = periods(cal)
    G = {g: (lo, hi) for g, (lo, hi, _) in X.SURV["groups"].items()}
    pit = pit_mask(P)
    gr = group_returns(P, pers, G, D20, A, pit)
    etf = {g: X.SURV["groups"][g][2] for g in G}
    etf["PIT"] = X.SURV["pit"]
    mid = len(pers) // 2
    halves = ((0, mid), (mid, len(pers)))
    out = {"ver": X.VER, "spec": X.SPEC_DATE, "made": date.today().isoformat(), "a": cal[pers[0][0]], "b": cal[pers[-1][1]],
           "months": len(pers), "groups": {}}
    for g in list(G) + ["PIT"]:
        e = etf[g]
        er = etf_returns(P, pers, e, X.SURV["fees"][e])
        rg = gr["ret"][g]
        row = {"etf": e, "n": {"first": gr["n"][g][0], "last": gr["n"][g][-1], "min": min(gr["n"][g])},
               "cagr": cagr(rg, cal, pers), "etf_cagr": cagr(er, cal, pers)}
        row["gap"] = row["cagr"] - row["etf_cagr"] if row["cagr"] is not None and row["etf_cagr"] is not None else None
        hs = []
        for h0, h1 in halves:
            pp = pers[h0:h1]
            c1, c2 = cagr(rg[h0:h1], cal, pp), cagr(er[h0:h1], cal, pp)
            hs.append({"a": cal[pp[0][0]], "b": cal[pp[-1][1]], "cagr": c1, "etf": c2,
                       "gap": c1 - c2 if c1 is not None and c2 is not None else None})
        row["halves"] = hs
        yg, ye = yearly(rg, cal, pers), yearly(er, cal, pers)
        row["years"] = {y: [yg[y], ye[y]] for y in sorted(yg)}
        cnt_y: dict[str, list] = {}
        for (a, _), k in zip(pers, gr["n"][g]):
            cnt_y.setdefault(cal[a][:4], []).append(k)
        row["count_y"] = {y: int(np.median(v)) for y, v in sorted(cnt_y.items())}
        out["groups"][g] = row
    gaps = [out["groups"][g]["gap"] for g in X.SURV["stop"] if out["groups"][g]["gap"] is not None]
    out["G"] = max(gaps) if gaps else None
    out["stop"] = bool(out["G"] is not None and out["G"] * 100 >= X.PASS["surv_max"])
    return out
