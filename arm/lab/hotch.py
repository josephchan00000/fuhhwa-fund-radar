"""反向檢查：籌碼連續過熱、技術面轉空之後 3 個月的最大回撤（docs/lab_hotdd_plan.md 第 7 節；規格 hotchspec VER 1）。

  streak_days(x, we)    每天的已連續過熱週數（今天 ≥ 80 → 1＋今天以前連續過熱的週末數；今天 < 80 → 0）
  hot_runs(x, we)       週末連續過熱 ≥ 4 週的每一段
  run_rows()            每一段：滿 4 週之後到結束後 60 日的最大回撤、和同樣長度窗口比的百分位
  td1()／phase_events() 技術面熱度退燒、階段轉換事件
  tech_events()         12 種轉空事件；tech_states() 3 種空頭狀態
  stats()               一組日子（事件或狀態）：原始、扣掉波動、≥ 10%／≥ 20% 比例、6 個月、前後兩半
  boot_two()            兩組事件平均的差（移動區塊重抽）
  decline_signals()     大跌時轉空訊號出現的位置
  market()              一個市場；research()：五個市場＋主要假說 → data/lab/hotch_research.json
  now()                 每天建頁：今天的連續過熱週數、最近的轉空事件、空頭狀態

研究檔只在資料或規格改了才重跑：TZ=Asia/Taipei python3 scripts/run_hotch.py（numpy）。
"""
from __future__ import annotations

import bisect
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import hotchspec as S
from . import hotdd as K

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "lab" / "hotch_research.json"


def _lst(a) -> list:
    """numpy／list → list（NaN、None 都變 None）。"""
    return [None if v is None or (isinstance(v, (float, np.floating)) and math.isnan(v)) else float(v) for v in a]


def _arr(a) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in a], dtype=float)


def _hot(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v)) and v >= S.HOT


def _has(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# ── A：已連續過熱 ────────────────────────────────────────────────────────

def streak_days(x: list, we: list[int]) -> list:
    """每天：今天 ≥ 80 → 1＋今天以前（不含今天）連續 ≥ 80 的週末數；今天 < 80 → 0；沒有值 → None。"""
    T = len(x)
    out: list = [None] * T
    j, last = 0, 0                               # last＝今天以前最後一個週末為止的連續過熱週數
    run = 0
    for t in range(T):
        while j < len(we) and we[j] < t:
            run = run + 1 if _hot(x[we[j]]) else 0
            last = run
            j += 1
        v = x[t]
        if _has(v):
            out[t] = 1 + last if v >= S.HOT else 0
    return out


def hot_runs(x: list, we: list[int], n: int = S.RUN_MIN) -> list[tuple[int, int]]:
    """週末連續 ≥ 80 的每一段（週末的位置 j0..j1，長度 ≥ n）。"""
    out, j0 = [], None
    for j, i in enumerate(we):
        if _hot(x[i]):
            if j0 is None:
                j0 = j
        else:
            if j0 is not None and j - j0 >= n:
                out.append((j0, j - 1))
            j0 = None
    if j0 is not None and len(we) - j0 >= n:
        out.append((j0, len(we) - 1))
    return out


def window_mdds(px: np.ndarray, L: int, a_lo: int, chunk: int = 2048) -> np.ndarray:
    """起點 a＝a_lo..T−1−L 的每個窗口（第 a～a＋L 天）的最大回撤；窗口內缺價格＝NaN。"""
    T = len(px)
    na = T - L - a_lo
    if na <= 0 or L < 1:
        return np.array([])
    from numpy.lib.stride_tricks import sliding_window_view
    W = sliding_window_view(px[a_lo:], L + 1)
    out = np.empty(na)
    for s in range(0, na, chunk):
        w = W[s:s + chunk]
        bad = np.isnan(w).any(axis=1) | ~(w[:, 0] > 0)
        wf = np.where(np.isnan(w), 1.0, w)
        dd = 1.0 - wf / np.maximum.accumulate(wf, axis=1)
        m = dd.max(axis=1)
        m[bad] = np.nan
        out[s:s + chunk] = m
    return out


def pct_rank(v: float, pool: np.ndarray) -> float | None:
    """比 v 小的比例（相同算一半）。"""
    p = pool[~np.isnan(pool)]
    if not len(p):
        return None
    return float((np.sum(p < v) + 0.5 * np.sum(p == v)) / len(p))


def run_rows(x: list, we: list[int], cal: list[str], px: np.ndarray, i0: int) -> list[dict]:
    """每一段連續過熱（≥ 4 週）：從第 4 個過熱週末的下一個交易日收盤起，到最後一個過熱週末之後第 60 個交易日的最大回撤，
    和同樣長度、起點在這個變數第一個有值的日子以後的所有窗口比的百分位。"""
    T = len(cal)
    first = next((i for i in range(i0, T) if _has(x[i])), None)
    if first is None:
        return []
    out, cache = [], {}
    for j0, j1 in hot_runs(x, we):
        if we[j0] < i0:
            continue
        s4 = we[j0 + S.RUN_MIN - 1]
        a = s4 + S.LAG
        b = min(we[j1] + S.H, T - 1)
        row = {"a": cal[we[j0]], "s4": cal[s4], "z": cal[we[j1]], "wk": j1 - j0 + 1,
               "open": we[j1] + S.H > T - 1, "mdd": None}
        r = K.run_mdd(px, a, b) if a <= b else None
        if r:
            L = b - a
            if L not in cache:
                cache[L] = window_mdds(px, L, first)
            row.update({"mdd": r["mdd"], "pk": cal[r["pk"]], "tr": cal[r["tr"]], "days": L,
                        "pct": pct_rank(r["mdd"], cache[L])})
        out.append(row)
    return out


# ── B：技術面轉空 ──────────────────────────────────────────────────────────

def td1(x: list) -> list[int]:
    """技術面熱度退燒：今天 < 50、前 20 個交易日都有值而且 ≥ 50、前 60 個交易日內有一天 ≥ 80。"""
    out = []
    for t in range(max(S.TD1_PRIOR, S.TD1_LOOK), len(x)):
        v = x[t]
        if not _has(v) or v >= S.TD1_TO:
            continue
        pr = x[t - S.TD1_PRIOR:t]
        if not all(_has(u) and u >= S.TD1_TO for u in pr):
            continue
        if any(_has(u) and u >= S.TD1_FROM for u in x[t - S.TD1_LOOK:t]):
            out.append(t)
    return out


def phase_events(x: list, we: list[int], target: int) -> list[int]:
    """階段時間軸（heatviz.phase_track，每週最後一個交易日）：這一週是 target、上一週有階段而且不是 target。"""
    from .heatviz import phase_track
    _, _, P = phase_track([x[i] for i in we])
    return [we[j] for j in range(1, len(we)) if P[j] == target and P[j - 1] is not None and P[j - 1] != target]


def tech_events(px: list, tech: list, we: list[int], i0: int) -> dict[str, list[int]]:
    """12 種轉空事件（索引；均線類從第 EV_START＋1 個交易日起、技術面熱度類從樣本起點起）。"""
    from . import heattech as TT
    from .heatrel import heat_events
    ev = TT.all_events(list(px))
    lo = max(i0, S.EV_START)
    out = {k: [t for t in ev[k] if t >= lo] for k in S.MA_EVENTS}
    out["TD1"] = [t for t in td1(tech) if t >= i0]
    out["TD2"] = [t for t in heat_events(list(tech), "cold") if t >= i0]
    for k, q in S.PH_TARGET.items():
        out[k] = [t for t in phase_events(tech, we, q) if t >= i0]
    return {k: out[k] for k in S.TECH_EVENTS}


def tech_states(px: list, tech: list) -> dict[str, np.ndarray]:
    """3 種空頭狀態（逐日 True／False；算不出來的日子 False）＋可用的日子（ok）。"""
    from . import heattech as TT
    M = TT.mas(list(px), (60, 240))
    T = len(px)
    st = {k: np.zeros(T, dtype=bool) for k in S.TECH_STATES}
    ok = {k: np.zeros(T, dtype=bool) for k in S.TECH_STATES}
    for t in range(T):
        p = px[t]
        for n, k in ((60, "below60"), (240, "below240")):
            m = M[n][t]
            if p is not None and m is not None and t >= S.EV_START:
                ok[k][t] = True
                st[k][t] = p < m
        if _has(tech[t]):
            ok["cold"][t] = True
            st["cold"][t] = tech[t] < S.COLD
    return {"st": st, "ok": ok}


def pre_drop(px: np.ndarray, t: int) -> float | None:
    """事件那天收盤比第 t−60～t 天（共 61 天）的最高收盤低多少。"""
    w = px[max(0, t - S.PEAK_LOOK):t + 1]
    if not len(w) or np.isnan(w).any():
        return None
    return float(1.0 - px[t] / w.max())


# ── 統計 ─────────────────────────────────────────────────────────────────

def vol_resid(mdd: np.ndarray, base: np.ndarray, vol: np.ndarray) -> np.ndarray:
    """基準日子依近 20 日波動分三組（三分位），每天的 MDD 減掉同一組基準日子的平均；沒有波動或不在基準＝NaN。"""
    out = np.full(len(mdd), np.nan)
    bv = vol[base]
    ok = ~np.isnan(bv)
    if ok.sum() < S.VOL_GROUPS:
        return out
    b = base[ok]
    cuts = np.quantile(bv[ok], [1.0 / 3.0, 2.0 / 3.0])
    g = (bv[ok] >= cuts[0]).astype(int) + (bv[ok] >= cuts[1]).astype(int)
    m = mdd[b]
    for k in range(S.VOL_GROUPS):
        sel = g == k
        if sel.any():
            out[b[sel]] = m[sel] - m[sel].mean()
    return out


def _halves(y: np.ndarray, base: np.ndarray, evs: list[int]) -> tuple:
    """前後兩半：事件（狀態）日子依時間切在中間那一筆；y 以日子為索引（NaN 不算）。"""
    n = len(evs)
    if n < 2:
        return None, None
    m = n // 2
    cut = evs[m]
    E = np.array(evs)
    out = []
    for e, b in ((E[:m], base[base < cut]), (E[m:], base[base >= cut])):
        ye, yb = y[e], y[b]
        ye, yb = ye[~np.isnan(ye)], yb[~np.isnan(yb)]
        out.append(float(ye.mean() - yb.mean()) if len(ye) and len(yb) else None)
    return out[0], out[1]


def _diff_ci(y: np.ndarray, base: np.ndarray, E: np.ndarray, L: int) -> dict:
    """y 在基準日子上：事件日平均 − 全部平均、區間、p（雙尾、單尾）。"""
    yb = y[base]
    ok = ~np.isnan(yb)
    b = base[ok]
    flag = np.isin(b, E)
    if not flag.any():
        return {"d": None, "lo": None, "hi": None, "p": None, "p1": None}
    d = float(y[b[flag]].mean() - y[b].mean())
    lo, hi, p, p1 = K.ci_p(K.boot_reps(y[b], flag, L=L))
    return {"d": d, "lo": lo, "hi": hi, "p": p, "p1": p1}


def stats(days, mask: np.ndarray, O: dict, O2: dict, vol: np.ndarray, cal: list[str], kind: str,
          px: np.ndarray | None = None, keep_list: bool = False) -> dict:
    """一組日子（kind＝"ev" 事件、"st" 狀態）× 基準 mask：原始與扣掉波動的差、區間、前後兩半；≥ 10%／≥ 20% 的比例差；
    6 個月最大回撤的差；事件另記 DD0、R60、訊號出現時已經跌了多少（px）與每一次的清單。"""
    mdd = O["mdd"]
    base = np.nonzero(mask)[0]
    evs = sorted({int(t) for t in days if 0 <= t < len(mask) and mask[t]})
    n = len(evs)
    out: dict = {"n": n, "ep": K.episodes(evs, S.EP_GAP), "nb": int(len(base))}
    mb = mdd[base]
    out["base"] = K.dist(mb)
    out["base"].update({"dd0": K._mean(O["dd0"][base]), "dq10": float(np.mean(O["dd0"][base] >= S.DD_TH[0])) if len(base) else None,
                        "r60": K._mean(O["r60"][base]), "up": float(np.mean(O["r60"][base] > 0)) if len(base) else None})
    if n == 0:
        out["v"] = out["vv"] = "few"
        return out
    E = np.array(evs)
    out["ev"] = K.dist(mdd[E])
    out["ev"].update({"dd0": float(O["dd0"][E].mean()), "dq10": float(np.mean(O["dd0"][E] >= S.DD_TH[0])),
                      "r60": float(O["r60"][E].mean()), "up": float(np.mean(O["r60"][E] > 0))})
    out["a"], out["z"] = cal[evs[0]], cal[evs[-1]]
    out["yrs"] = sorted({cal[t][:4] for t in evs}) if kind == "ev" else None
    raw = _diff_ci(mdd, base, E, S.BLOCK)
    out.update(raw)
    out["h1"], out["h2"] = _halves(mdd, base, evs)
    out["loo"] = loo(evs, mdd, float(mb.mean()))
    res = vol_resid(mdd, base, vol)
    v = _diff_ci(res, base, E, S.BLOCK)
    out.update({"dv": v["d"], "lov": v["lo"], "hiv": v["hi"], "pv": v["p"], "pv1": v["p1"]})
    out["hv1"], out["hv2"] = _halves(res, base, evs)
    for th in S.DD_TH:
        k = f"q{int(round(th * 100))}"
        y = np.where(np.isnan(mdd), np.nan, (mdd >= th).astype(float))
        r = _diff_ci(y, base, E, S.BLOCK)
        out[f"d{k}"], out[f"lo{k}"], out[f"hi{k}"] = r["d"], r["lo"], r["hi"]
    m2 = O2["mdd"]
    base2 = base[~np.isnan(m2[base])]
    E2 = E[~np.isnan(m2[E])]
    if len(E2):
        r = _diff_ci(m2, base2, E2, S.BLOCK_LONG)
        out["long"] = {"n": int(len(E2)), "ev": float(m2[E2].mean()), "base": float(m2[base2].mean()),
                       "med": float(np.median(m2[E2])), "bmed": float(np.median(m2[base2])),
                       "d": r["d"], "lo": r["lo"], "hi": r["hi"]}
    if kind == "ev" and px is not None:
        pre = [pre_drop(px, t) for t in evs]
        pv = [p for p in pre if p is not None]
        out["pre"] = float(np.median(pv)) if pv else None
        if keep_list:
            out["list"] = [[cal[t], float(mdd[t]), float(O["dd0"][t]), float(O["r60"][t]), pre[i]] for i, t in enumerate(evs)]
    mn = S.MIN_EVENTS if kind == "ev" else S.MIN_STATE_DAYS
    few = n < mn or out["ep"] < S.MIN_EPISODES
    out["v"] = "few" if few or out["lo"] is None else None
    out["vv"] = "few" if few or out["lov"] is None else None
    return out


def loo(evs: list[int], y: np.ndarray, base_mean: float, gap: int = S.EP_GAP) -> list | None:
    """事後檢查（看過結果才加，不影響判定；規劃第 8 節）：拿掉其中一段（相隔 > gap 個交易日分段）之後，
    其餘日子的平均 − 基準平均，各段拿掉一次 → [最小, 最大]；不到 2 段＝None。"""
    if len(evs) < 2:
        return None
    E = np.array(evs)
    gid = np.concatenate([[0], np.cumsum(np.diff(E) > gap)])
    k = int(gid[-1]) + 1
    if k < 2:
        return None
    vals = [float(y[E[gid != g]].mean() - base_mean) for g in range(k)]
    return [min(vals), max(vals)]


def verdict(lo, hi, h1, h2, q) -> str:
    if None in (lo, hi, h1, h2) or q is None or q > S.BH_Q:
        return "none"
    if lo > 0 and h1 > 0 and h2 > 0:
        return "up"
    if hi < 0 and h1 < 0 and h2 < 0:
        return "down"
    return "none"


def apply_bh(fams: dict[str, list[dict]]) -> None:
    """每個家族：原始（p→q、v）與扣掉波動（pv→qv、vv）各做一次 BH 與判定。"""
    for lst in fams.values():
        for pk, qk, vk, lo, hi, h1, h2 in (("p", "q", "v", "lo", "hi", "h1", "h2"),
                                            ("pv", "qv", "vv", "lov", "hiv", "hv1", "hv2")):
            ks = [st for st in lst if st.get(vk) != "few" and st.get(pk) is not None]
            for st, q in zip(ks, K.bh([st[pk] for st in ks])):
                st[qk] = q
            for st in lst:
                if st.get(vk) == "few":
                    continue
                st[vk] = verdict(st.get(lo), st.get(hi), st.get(h1), st.get(h2), st.get(qk))


def boot_two(y: np.ndarray, f1: np.ndarray, f2: np.ndarray, L: int = S.BLOCK, n_boot: int = S.BOOT_N,
             seed: int = S.BOOT_SEED) -> np.ndarray | None:
    """移動區塊重抽（同 hotdd.boot_reps 的抽法）：每次「f1 日子的平均 − f2 日子的平均」；某一組沒抽到＝NaN。"""
    n = len(y)
    if int(f1.sum()) < 2 or int(f2.sum()) < 2 or n < 2 * L:
        return None
    P1 = np.concatenate([[0.0], np.cumsum(np.where(f1, y, 0.0))])
    P2 = np.concatenate([[0.0], np.cumsum(np.where(f2, y, 0.0))])
    N1 = np.concatenate([[0], np.cumsum(f1.astype(np.int64))])
    N2 = np.concatenate([[0], np.cumsum(f2.astype(np.int64))])
    k = math.ceil(n / L)
    rng = np.random.default_rng(seed)
    st = rng.integers(0, n - L + 1, size=(n_boot, k))
    s1, n1 = (P1[st + L] - P1[st]).sum(axis=1), (N1[st + L] - N1[st]).sum(axis=1)
    s2, n2 = (P2[st + L] - P2[st]).sum(axis=1), (N2[st + L] - N2[st]).sum(axis=1)
    ok = (n1 > 0) & (n2 > 0)
    return np.where(ok, s1 / np.where(n1 > 0, n1, 1) - s2 / np.where(n2 > 0, n2, 1), np.nan)


def versus(ev1: list[int], ev2: list[int], mask: np.ndarray, mdd: np.ndarray) -> dict:
    """兩組事件的平均 MDD60 相減（只用 mask 的日子；轉空 − 技術面進入過熱）。"""
    base = np.nonzero(mask)[0]
    f1, f2 = np.isin(base, ev1), np.isin(base, ev2)
    out = {"n1": int(f1.sum()), "n2": int(f2.sum()), "d": None, "lo": None, "hi": None}
    if f1.any() and f2.any():
        y = mdd[base]
        out["d"] = float(y[f1].mean() - y[f2].mean())
        lo, hi, _, _ = K.ci_p(boot_two(y, f1, f2))
        out["lo"], out["hi"] = lo, hi
    return out


# ── 大跌時轉空訊號的位置 ────────────────────────────────────────────────────

def decline_signals(px: np.ndarray, decl: list[dict], ev: list[int], first_ok: int) -> list[dict | None]:
    """每一段大跌（高點在 first_ok 以後；之前的＝None）：高點之後、低點以前（含）的第一次事件；
    賣出＝事件下一個交易日收盤。→ {"s": 事件位置, "days": 高點到事件, "lost": 賣出時已跌, "rem": 賣出後到低點又跌} 或 {"s": None}。"""
    T = len(px)
    evs = sorted(ev)
    out: list = []
    for e in decl:
        pk, tr = e["pk"], e["tr"]
        if pk < first_ok:
            out.append(None)
            continue
        j = bisect.bisect_right(evs, pk)
        if j >= len(evs) or evs[j] > tr:
            out.append({"s": None})
            continue
        s = evs[j]
        x = s + S.LAG
        if x >= T or np.isnan(px[x]):
            out.append({"s": s, "days": s - pk, "lost": None, "rem": None})
            continue
        lost = float(1.0 - px[x] / px[pk])
        rem = float(1.0 - px[tr] / px[x]) if x <= tr else 0.0
        out.append({"s": s, "days": s - pk, "lost": lost, "rem": rem})
    return out


def decl_summary(rows: list) -> dict:
    ok = [r for r in rows if r is not None]
    hit = [r for r in ok if r.get("s") is not None and r.get("lost") is not None]
    med = lambda k: float(np.median([r[k] for r in hit])) if hit else None   # noqa: E731
    return {"n": len(ok), "hit": len(hit), "days": med("days"), "lost": med("lost"), "rem": med("rem")}


# ── 市場 ─────────────────────────────────────────────────────────────────

def inputs_tw(B: dict | None = None, I: dict | None = None) -> dict:
    """台股：1990 起的日曆與加權指數（crash.tw_inputs）＋籌碼變數、技術面熱度的 0～100。"""
    from . import crash as CR
    if B is None:
        from . import heatcalc as HC
        B = HC.build()
    I = I if I is not None else CR.tw_inputs(B=B, BX={})
    cal = list(I["cal"])
    x = {}
    for k in S.CHIP_VARS["tw"]:
        if k in I["x"]:
            x[k] = _lst(I["x"][k])
        else:
            x[k] = _lst(CR.align(cal, B["cal"], B["hc"].get(k) or [None] * len(B["cal"])))
    x["Dtech"] = _lst(CR.align(cal, B["cal"], B["comp"]["tech"]))
    return {"cal": cal, "px": np.asarray(I["px"], dtype=float), "x": x, "i0": 0}


def inputs_us(idx: str, Bu: dict) -> dict:
    """美股一個指數：景氣頁美股版的日曆（從日曆第一天起；樣本從驗證起點起）。要在 heatspec.use(該指數) 裡呼叫。"""
    from . import heatspec_us as U
    cal = list(Bu["cal"])
    st = U.VAL_START.get(idx) or cal[0]
    i0 = next((i for i, d in enumerate(cal) if d >= st), len(cal))
    x = {"Dsent": _lst(Bu["comp"]["sent"]), "Dtech": _lst(Bu["comp"]["tech"])}
    for k in S.CHIP_VARS["us"]:
        if k != "Dsent":
            x[k] = _lst(Bu["hc"].get(k) or [None] * len(cal))
    return {"cal": cal, "px": _arr(Bu["px"]), "x": x, "i0": i0}


def market(mk: str, I: dict) -> dict:
    """一個市場：A（籌碼連續過熱狀態＋每一段）、B（轉空事件、空頭狀態、對照、大跌時訊號的位置），BH 與判定。"""
    from . import heatpos as P
    cal, px, i0 = I["cal"], I["px"], I["i0"]
    T = len(cal)
    O = K.outcomes(px, S.H, S.LAG)
    O2 = K.outcomes(px, S.H_LONG, S.LAG)
    vol = K.vol20(px)
    we = P.week_ends(cal)
    okO = ~np.isnan(O["mdd"])
    inr = np.arange(T) >= i0
    cvars = S.CHIP_VARS["tw" if mk == "tw" else "us"]
    # A：籌碼（＋對照技術面）
    A: dict = {}
    famA: dict[str, list] = {}
    for k in tuple(cvars) + S.CONTRAST_VARS:
        x = I["x"][k]
        has = np.array([_has(v) for v in x], dtype=bool)
        mask = has & okO & inr
        w = streak_days(x, we)
        first = next((cal[i] for i in range(i0, T) if _has(x[i])), None)
        row = {"first": first, "kind": "contrast" if k in S.CONTRAST_VARS else "chip", "st": {}}
        h0 = [t for t in range(T) if w[t] == 0]
        row["st"]["H0"] = {kk: vv for kk, vv in stats(h0, mask, O, O2, vol, cal, "st").items()
                           if kk in ("n", "ep", "nb", "base", "ev", "d")}
        for key, nw in zip(S.STATES_A, S.STATE_WEEKS):
            days = [t for t in range(T) if w[t] is not None and w[t] >= nw]
            st = stats(days, mask, O, O2, vol, cal, "st")
            row["st"][key] = st
            famA.setdefault(f"{row['kind']}:{key}", []).append(st)
        if row["kind"] == "chip":
            row["runs"] = run_rows(x, we, cal, px, i0)
        A[k] = row
    apply_bh(famA)
    # B：轉空事件與空頭狀態
    tech = I["x"]["Dtech"]
    hasT = np.array([_has(v) for v in tech], dtype=bool)
    ev = tech_events(_lst(px), tech, we, i0)
    ma_ok = okO & inr & (np.arange(T) >= S.EV_START)
    td_ok = okO & inr & hasT
    Bev: dict = {}
    for k in S.TECH_EVENTS:
        Bev[k] = stats(ev[k], ma_ok if k in S.MA_EVENTS else td_ok, O, O2, vol, cal, "ev", px=px, keep_list=True)
    TS = tech_states(_lst(px), tech)
    Bst = {}
    for k in S.TECH_STATES:
        days = np.nonzero(TS["st"][k])[0]
        Bst[k] = stats(days, TS["ok"][k] & okO & inr, O, O2, vol, cal, "st")
    apply_bh({"ev": list(Bev.values()), "st": list(Bst.values())})
    # 對照：技術面進入過熱（hotdd 的 E），兩邊都算得出來的期間
    hot = [t for t in K.enter(tech) if t >= i0]
    both = ma_ok & hasT
    hot_st = stats(hot, both, O, O2, vol, cal, "ev", px=px)
    vs = {k: versus(ev[k], hot, both, O["mdd"]) for k in S.TECH_EVENTS}
    # 大跌時轉空訊號的位置
    tfirst = next((i for i in range(i0, T) if _has(tech[i])), T)
    decl, dsum, drows = {}, {}, {}
    for th in S.DECL_TH:
        tk = str(int(round(th * 100)))
        dl = [{**e, "pk": e["pk"] + i0, "tr": e["tr"] + i0} for e in K.declines(cal[i0:], px[i0:], th)]
        decl[tk] = [{"pk": cal[e["pk"]], "tr": cal[e["tr"]], "dd": e["dd"], "open": e["open"]} for e in dl]
        dsum[tk], drows[tk] = {}, {}
        for k in S.TECH_EVENTS:
            first_ok = max(i0, S.EV_START) if k in S.MA_EVENTS else tfirst
            rr = decline_signals(px, dl, ev[k], first_ok)
            dsum[tk][k] = decl_summary(rr)
            drows[tk][k] = [None if r is None else ([None] if r.get("s") is None else
                            [cal[r["s"]], r["days"], r["lost"], r["rem"]]) for r in rr]
    allm = okO & inr
    base = K.dist(O["mdd"][allm])
    base.update({"n": int(allm.sum()), "a": cal[int(np.argmax(allm))] if allm.any() else None})
    return {"start": cal[i0] if i0 < T else None, "end": cal[-1], "base": base, "A": A,
            "B": {"ev": Bev, "st": Bst, "hot": hot_st, "vs": vs, "decl": decl, "dsum": dsum, "drows": drows,
                  "tfirst": cal[tfirst] if tfirst < T else None}}


def primary(M: dict) -> dict:
    """主要假說（原始、單尾、Holm）。"""
    out: dict = {}
    for h, sp in S.PRIMARY.items():
        m = M.get(sp["mk"]) or {}
        if sp["part"] == "A":
            st = (((m.get("A") or {}).get(sp["var"]) or {}).get("st") or {}).get(sp["key"]) or {}
        else:
            st = ((m.get("B") or {}).get("ev") or {}).get(sp["key"]) or {}
        out[h] = {k: st.get(k) for k in ("n", "ep", "d", "lo", "hi", "p1", "h1", "h2")}
        out[h]["few"] = st.get("v") == "few" or st.get("p1") is None
    adj, rej = K.holm({h: (None if v["few"] else v["p1"]) for h, v in out.items()})
    for h, v in out.items():
        v["padj"] = adj.get(h)
        v["ok"] = bool(rej.get(h) and (v.get("h1") or 0) > 0 and (v.get("h2") or 0) > 0)
    return out


# ── 每天建頁：現在的狀態 ──────────────────────────────────────────────────

def state_key(w) -> str | None:
    """已連續過熱週數 → 狀態（H0 不熱、H1、H4、H13、H26 取最高的那個）；沒有值＝None。"""
    if w is None:
        return None
    key = "H0"
    for k, n in zip(S.STATES_A, S.STATE_WEEKS):
        if w >= n:
            key = k
    return key


def now(I: dict) -> dict:
    """今天（日曆最後一天，一定是週末）：籌碼變數（＋技術面向）的已連續過熱週數、狀態、正在進行的一段
    （從第 4 個過熱週末的下一個交易日到今天的最大回撤）；最近 RECENT 個交易日的轉空事件；現在的空頭狀態與從哪天開始。"""
    from . import heatpos as P
    cal, px, x = I["cal"], I["px"], I["x"]
    T = len(cal)
    t = T - 1
    we = P.week_ends(cal)
    chip = {}
    for k, xs in x.items():
        w = streak_days(xs, we)[t] if T else None
        run = None
        if w and w >= S.RUN_MIN:
            rs = hot_runs(xs, we)
            if rs and rs[-1][1] == len(we) - 1:
                j0, j1 = rs[-1]
                s4 = we[j0 + S.RUN_MIN - 1]
                run = {"a": cal[we[j0]], "s4": cal[s4], "wk": j1 - j0 + 1, "mdd": None, "days": max(0, t - s4 - S.LAG)}
                r = K.run_mdd(px, s4 + S.LAG, t) if s4 + S.LAG <= t else None
                if r:
                    run.update({"mdd": r["mdd"], "pk": cal[r["pk"]], "tr": cal[r["tr"]], "chg": r["chg"]})
        chip[k] = {"v": xs[t] if T else None, "w": w, "key": state_key(w), "run": run}
    tech = x["Dtech"]
    ev = tech_events(_lst(px), tech, we, I["i0"]) if T else {k: [] for k in S.TECH_EVENTS}
    recent = {k: [cal[i] for i in ix if i > t - S.RECENT] for k, ix in ev.items()}
    st = {}
    if T:
        TS = tech_states(_lst(px), tech)
        for k in S.TECH_STATES:
            a = TS["st"][k]
            if a[t]:
                j = t
                while j > 0 and a[j - 1]:
                    j -= 1
                st[k] = {"on": True, "since": cal[j], "days": t - j + 1}
            else:
                st[k] = {"on": False} if TS["ok"][k][t] else None
    return {"d": cal[t] if T else None, "chip": chip, "recent": recent, "states": st,
            "tech": tech[t] if T else None}


# ── 研究檔 ────────────────────────────────────────────────────────────────

def research(IT: dict | None = None, IU: dict | None = None) -> dict:
    """IT＝inputs_tw()、IU＝{指數: inputs_us()}（測試可傳假資料）。"""
    from . import heatspec as HS
    from . import heatspec_us as U
    M = {"tw": market("tw", IT if IT is not None else inputs_tw())}
    if IU is None:
        from . import heatcalc_us as HU
        BA = HU.build_all()
        IU = {}
        for idx in U.INDEX_ORDER:
            with HS.use(U.spec_for(idx)):
                IU[idx] = inputs_us(idx, BA[idx])
    for idx in U.INDEX_ORDER:
        if idx in IU:
            with HS.use(U.spec_for(idx)):
                M[idx] = market(idx, IU[idx])
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "markets": K._r(M), "primary": K._r(primary(M))}


def save_research(R: dict) -> None:
    RESEARCH.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load_research() -> dict | None:
    try:
        R = json.loads(RESEARCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None
