"""美股飆股研究 B：換一個指數（ussxspec VER 1 的 SWAP；docs/lab_us_sleeve_plan.md 第 5、9 節）。研究用，不上頁面。

交易計畫（corespec VER 2）的核心、警訊、成本、換現金的規則全部不變（core.scenario）；三成的每天報酬換成 ETF 的含息報酬。
對照＝現在的計畫（三成放同一個指數）。判定＝ussxspec 的判定②。長歷史用指數本身（核心與三成都不含息）只描述。
"""
from __future__ import annotations

from datetime import date

import numpy as np

from . import core as CO
from . import corespec as CS
from . import ussxspec as X


def etf_daily(P: dict, sym: str, cal: list[str]) -> np.ndarray:
    """ETF 在 cal 上每天的含息報酬（沒有資料的日子 0；第一天 nan）。"""
    j = P["col"][sym]
    ix = {d: i for i, d in enumerate(P["cal"])}
    c = np.array([P["C"][ix[d], j] if d in ix else np.nan for d in cal])
    out = np.zeros(len(cal))
    prev = np.nan
    for k in range(len(cal)):
        if np.isfinite(c[k]):
            out[k] = c[k] / prev - 1 if np.isfinite(prev) else (np.nan if k == 0 else 0.0)
            prev = c[k]
    return out


def judge(sw: dict, cur: dict) -> dict:
    """判定②：100 萬比現在多、前後兩半都不比現在少、最慘時跌最多比現在深 mdd_extra 個百分點。"""
    m = sw["plan"]["m"] > cur["plan"]["m"]
    hv = all(a["plan"]["m"] >= b["plan"]["m"] for a, b in zip(sw["halves"], cur["halves"]))
    dd = sw["plan"]["mdd"] <= cur["plan"]["mdd"] + X.PASS["mdd_extra"] / 100
    return {"money": m, "halves": hv, "mdd": dd, "pass": bool(m and hv and dd)}


def _brief(sc: dict) -> dict:
    keep = ("m", "cagr", "mdd", "worst", "ex_best")
    return {"a": sc["a"], "b": sc["b"], "plan": {k: sc["plan"].get(k) for k in keep},
            "hold": {k: sc["hold"].get(k) for k in keep}, "halves": [{"a": h["a"], "b": h["b"], "plan": h["plan"], "hold": h["hold"]}
                                                                    for h in sc["halves"]],
            "years": sc["plan"]["years"], "sw": sc["sw"]}


def plan_ctx(mk: str) -> dict:
    M = CO.market_inputs(mk)
    F = CO.families(M["px"], M["inf"], M["lev"], CO.macro_flat(mk, M["cal"]), mk)
    return {**M, "F": F}


def research(P: dict, ctx: dict | None = None) -> dict:
    from . import xstrat as XT
    out = {"ver": X.VER, "spec": X.SPEC_DATE, "made": date.today().isoformat(), "plans": {}}
    for mk, etfs in X.SWAP.items():
        Q = (ctx or {}).get(mk) or plan_ctx(mk)
        cal, px, tot, rf, F = Q["cal"], Q["px"], Q["tot"], Q["rf"], Q["F"]
        T = len(cal)
        a = next(k for k, d in enumerate(cal) if d >= X.SWAP_START)
        c = CS.COST["us"]
        cur = CO.scenario("cur", mk, cal, px, tot, rf, F, a, T, c)
        row = {"cur": _brief(cur), "swap": {}, "long": {}}
        for e in etfs:
            sl = etf_daily(P, e, cal)
            sw = CO.scenario(e, mk, cal, px, tot, rf, F, a, T, c, sl=sl)
            row["swap"][e] = {**_brief(sw), "judge": judge(sw, cur)}
            lk = X.SWAP_LONG.get(e)
            if lk:                                          # 長歷史：核心與三成都用指數本身（不含息）
                D = XT.data(lk)
                ix = {d: i for i, d in enumerate(D["cal"])}
                lp = np.array([D["px"][ix[d]] if d in ix else np.nan for d in cal], dtype=float)
                r_core = np.zeros(T)
                r_core[1:] = px[1:] / px[:-1] - 1
                r_sl = np.zeros(T)
                ok = np.isfinite(lp)
                prev = np.nan
                for k in range(T):
                    if ok[k]:
                        r_sl[k] = lp[k] / prev - 1 if np.isfinite(prev) else 0.0
                        prev = lp[k]
                k0 = max(next(k for k in range(T) if ok[k]) + 1, next(k for k in range(T) if np.isfinite(F["ma"][k])))
                lg = {}
                for nm, k1 in (("early", a + 1), ("all", T)):     # early＝ETF 期間以前（獨立的一段）；all＝到最後
                    if k1 - k0 > 2 * CS.ROLL:
                        c0 = CO.scenario("long_cur", mk, cal, px, r_core, rf, F, k0, k1, c)
                        s0 = CO.scenario("long_" + e, mk, cal, px, r_core, rf, F, k0, k1, c, sl=r_sl)
                        lg[nm] = {"cur": _brief(c0), "swap": _brief(s0), "judge": judge(s0, c0),
                                  "same_dir": bool((s0["plan"]["m"] > c0["plan"]["m"]) == (sw["plan"]["m"] > cur["plan"]["m"]))}
                row["long"][e] = lg
        out["plans"][mk] = row
    return out
