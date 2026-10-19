"""過熱之後 3 個月的最大回撤（docs/lab_hotdd_plan.md 第 4 節；規格 hotddspec VER 1）。

  outcomes(px)       每一天的事件 → 之後 60 日（t＋1 收盤起算）的最大回撤、最高點與最低點、比起點最多跌多少、漲跌
  enter／streaks／exits／multi／bubble_events   五種事件（只用當天以前的 0～100）
  boot_reps()        移動區塊重抽（事件日平均 − 全部日子平均）
  row_stats()        一個變數 × 一種事件：分布、和全部日子比、區間、p 值、前後兩半、扣掉波動、每一次的清單
  declines()         大跌段（每天收盤，多空門檻法則：跌 10%／20% 算一段，反彈同樣幅度才結束）
  recall()           大跌前 3 個月有沒有過熱、碰巧的比例
  market()           一個市場：全部變數 × 事件＋BH
  research()         五個市場＋主要假說（Holm）→ data/lab/hotdd_research.json
  now()              每天建頁：現在過熱中的面向與項目、已連續幾週、這一段之後到今天的最大回撤、剛結束過熱

研究檔只在資料或規格改了才重跑：TZ=Asia/Taipei python3 scripts/run_hotdd.py（numpy）。
"""
from __future__ import annotations

import bisect
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import hotddspec as S

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "lab" / "hotdd_research.json"


def _arr(xs) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in xs], dtype=float)


# ── 結果 ─────────────────────────────────────────────────────────────────

def outcomes(px, h: int = S.H, lag: int = S.LAG) -> dict[str, np.ndarray]:
    """→ 以事件日 t 為索引：mdd（最大回撤，正數）、pk／tr（造成最大回撤那一段的最高點、最低點位置；沒有＝−1）、
    dd0（比起點最多跌多少）、r60（漲跌）。起點 a＝t＋lag、終點 a＋h；期間缺任何一天或超出資料＝NaN。"""
    p = _arr(px) if not isinstance(px, np.ndarray) else px.astype(float)
    T = len(p)
    out = {k: np.full(T, np.nan) for k in ("mdd", "dd0", "r60")}
    out["pk"] = np.full(T, -1, dtype=int)
    out["tr"] = np.full(T, -1, dtype=int)
    na = T - h                                        # 起點 a 可以是 0..na−1
    if na <= 0:
        return out
    from numpy.lib.stride_tricks import sliding_window_view
    W = sliding_window_view(p, h + 1)                 # W[a]＝第 a～a＋h 天
    ok = ~np.isnan(W).any(axis=1) & (W[:, 0] > 0)
    Wf = np.where(np.isnan(W), 1.0, W)
    run = np.maximum.accumulate(Wf, axis=1)
    dd = 1.0 - Wf / run
    s = dd.argmax(axis=1)
    mdd = dd[np.arange(na), s]
    cols = np.arange(h + 1)
    pk = np.where(cols[None, :] <= s[:, None], Wf, -np.inf).argmax(axis=1)
    dd0 = np.maximum(0.0, 1.0 - Wf[:, 1:].min(axis=1) / Wf[:, 0])
    r60 = Wf[:, h] / Wf[:, 0] - 1.0
    a = np.arange(na)
    t = a - lag
    m = ok & (t >= 0)
    tt, aa = t[m], a[m]
    out["mdd"][tt] = mdd[m]
    out["dd0"][tt] = dd0[m]
    out["r60"][tt] = r60[m]
    out["pk"][tt] = aa + pk[m]
    out["tr"][tt] = aa + s[m]
    return out


def mdd_direct(px: list, a: int, b: int) -> tuple:
    """逐筆直接算（測試對照）：第 a～b 天收盤的最大回撤、最高點、最低點位置。"""
    best, pk, tr = 0.0, a, a
    hi, hi_i = px[a], a
    for s in range(a, b + 1):
        if px[s] > hi:
            hi, hi_i = px[s], s
        d = 1.0 - px[s] / hi
        if d > best:
            best, pk, tr = d, hi_i, s
    return best, pk, tr


def vol20(px) -> np.ndarray:
    """近 VOL_WIN 個交易日（第 t−19～t 天）日對數報酬的標準差。"""
    p = _arr(px) if not isinstance(px, np.ndarray) else px.astype(float)
    n, k = len(p), S.VOL_WIN
    out = np.full(n, np.nan)
    if n > k:
        from numpy.lib.stride_tricks import sliding_window_view
        lr = np.log(p[1:] / p[:-1])
        out[k:] = sliding_window_view(lr, k).std(axis=1, ddof=1)
    return out


# ── 事件 ─────────────────────────────────────────────────────────────────

def enter(x: list) -> list[int]:
    """進入過熱：同景氣頁（heatrel.heat_events）。"""
    from .heatrel import heat_events
    return heat_events(list(x), "hot")


def _hot(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v)) and v >= S.HOT


def _has(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def week_runs(x: list, we: list[int]) -> list[int]:
    """每個週末（we）到那一週為止連續過熱的週數（< 80 或沒有值＝0）。"""
    out, run = [], 0
    for i in we:
        run = run + 1 if _hot(x[i]) else 0
        out.append(run)
    return out


def streaks(x: list, we: list[int], n: int) -> list[int]:
    """連續過熱滿 n 週：連續週數第一次到 n 的那個週末。"""
    return [i for i, r in zip(we, week_runs(x, we)) if r == n]


def exits(x: list, we: list[int], n: int = S.EXIT_MIN) -> list[int]:
    """過熱結束：連續過熱 ≥ n 週之後，第一個有值而且 < 80 的週末（沒有值的週末只讓週數歸零）。"""
    out, run = [], 0
    for i in we:
        v = x[i]
        if _hot(v):
            run += 1
            continue
        if _has(v) and run >= n:
            out.append(i)
        run = 0
    return out


def multi_count(comp: dict, dims: list[str]) -> tuple[list, list]:
    """每天：過熱的面向數、有值的面向數。"""
    T = len(next(iter(comp.values()))) if comp else 0
    hot, have = [], []
    for t in range(T):
        vs = [comp[d][t] for d in dims if _has(comp[d][t])]
        have.append(len(vs))
        hot.append(sum(1 for v in vs if v >= S.HOT))
    return hot, have


def multi(comp: dict, dims: list[str], k: int = S.MULTI_K) -> list[int]:
    """同時 k 個以上面向過熱：今天 ≥ k、前 EVT_PRIOR 個交易日都 < k；這 EVT_PRIOR＋1 天每天都至少 MULTI_MIN_DIMS 個面向有值。"""
    hot, have = multi_count(comp, dims)
    pr = S.EVT_PRIOR
    out = []
    for t in range(pr, len(hot)):
        if have[t] < S.MULTI_MIN_DIMS or hot[t] < k:
            continue
        if all(have[j] >= S.MULTI_MIN_DIMS and hot[j] < k for j in range(t - pr, t)):
            out.append(t)
    return out


def bubble_months(rows: list, last_day: str) -> list[tuple[str, int]]:
    """泡沫頁每月判定 → [(月底日期, 等級)]，只用已經過完的月份（日曆最後一天所在的月份不算）。"""
    return [(str(r["d"]), int(r["L"])) for r in rows
            if r.get("L") is not None and str(r.get("d"))[:7] < last_day[:7]]


def bubble_events(cal: list[str], months: list[tuple[str, int]], k: int) -> list[int]:
    """泡沫等級升到 k 以上：月底等級 ≥ k，前一個月有值而且 < k；事件日＝交易日曆上 ≤ 月底的最後一天。"""
    out = []
    for (d0, l0), (d1, l1) in zip(months, months[1:]):
        if l1 >= k and l0 < k:
            i = bisect.bisect_right(cal, d1) - 1
            if i >= 0:
                out.append(i)
    return out


def episodes(pos: list[int], gap: int = S.EP_GAP) -> int:
    if not pos:
        return 0
    p = sorted(pos)
    return 1 + sum(1 for a, b in zip(p, p[1:]) if b - a > gap)


# ── 統計 ─────────────────────────────────────────────────────────────────

def boot_reps(y: np.ndarray, flag: np.ndarray, L: int = S.BLOCK, n_boot: int = S.BOOT_N,
              seed: int = S.BOOT_SEED) -> np.ndarray | None:
    """移動區塊重抽：y、flag 照時間排；每次抽 ⌈n／L⌉ 塊（每塊 L 天）湊滿天數，算「事件日平均 − 全部日子平均」。
    事件少於 2 天或天數不到 2L 回 None；某次沒有抽到事件＝NaN。"""
    n = len(y)
    if int(flag.sum()) < 2 or n < 2 * L:
        return None
    P = np.concatenate([[0.0], np.cumsum(y)])
    PE = np.concatenate([[0.0], np.cumsum(np.where(flag, y, 0.0))])
    PF = np.concatenate([[0], np.cumsum(flag.astype(np.int64))])
    k = math.ceil(n / L)
    rng = np.random.default_rng(seed)
    st = rng.integers(0, n - L + 1, size=(n_boot, k))
    sa = (P[st + L] - P[st]).sum(axis=1)
    se = (PE[st + L] - PE[st]).sum(axis=1)
    ne = (PF[st + L] - PF[st]).sum(axis=1)
    return np.where(ne > 0, se / np.where(ne > 0, ne, 1) - sa / (k * L), np.nan)


def ci_p(reps: np.ndarray | None) -> tuple:
    """→ (下緣, 上緣, 雙尾 p, 單尾 p（差 ≤ 0 的比例）)；有效次數不到一半＝全部 None。"""
    if reps is None:
        return None, None, None, None
    r = reps[~np.isnan(reps)]
    if len(r) < len(reps) // 2:
        return None, None, None, None
    a = (1.0 - S.CI) / 2.0
    lo, hi = np.quantile(r, [a, 1.0 - a])
    le, ge = float(np.mean(r <= 0)), float(np.mean(r >= 0))
    pmin = 1.0 / S.BOOT_N
    return float(lo), float(hi), min(1.0, max(pmin, 2.0 * min(le, ge))), max(pmin, le)


def bh(ps: list) -> list:
    from .heatrel import bh as _bh
    return _bh(ps)


def holm(ps: dict, alpha: float = S.HOLM_ALPHA) -> tuple[dict, dict]:
    from .heatreg import holm as _h
    return _h(ps, alpha)


def _mean(a) -> float | None:
    return float(np.mean(a)) if len(a) else None


def _q(a, q) -> float | None:
    return float(np.quantile(a, q)) if len(a) else None


def dist(m: np.ndarray) -> dict:
    """最大回撤的分布：平均、中位數、第 75／90 百分位、≥ 10%、≥ 20% 的比例。"""
    t1, t2 = S.DD_TH
    return {"mean": _mean(m), "med": _q(m, 0.5), "p75": _q(m, 0.75), "p90": _q(m, 0.9),
            "q10": float(np.mean(m >= t1)) if len(m) else None, "q20": float(np.mean(m >= t2)) if len(m) else None}


def row_stats(ev: list[int], mask: np.ndarray, O: dict, vol: np.ndarray, cal: list[str],
              x: np.ndarray | None = None) -> dict:
    """一個變數 × 一種事件。mask＝基準日子（變數有值、之後 60 日算得出來、在樣本內）；O＝outcomes()；x＝事件當天的 0～100。"""
    mdd = O["mdd"]
    base = np.nonzero(mask)[0]
    evs = sorted({int(t) for t in ev if 0 <= t < len(mask) and mask[t]})
    n = len(evs)
    out: dict = {"n": n, "ep": episodes(evs), "nb": int(len(base))}
    mb = mdd[base]
    out["base"] = dist(mb)
    out["base"]["r60"] = _mean(O["r60"][base])
    out["base"]["up"] = float(np.mean(O["r60"][base] > 0)) if len(base) else None
    if n == 0:
        out["v"] = "few"
        return out
    E = np.array(evs)
    me = mdd[E]
    out["ev"] = dist(me)
    out["ev"]["dd0"] = _mean(O["dd0"][E])
    out["ev"]["r60"] = _mean(O["r60"][E])
    out["ev"]["up"] = float(np.mean(O["r60"][E] > 0))
    w = int(E[int(np.argmax(me))])
    out["worst"] = {"d": cal[w], "mdd": float(mdd[w]), "pk": cal[O["pk"][w]], "tr": cal[O["tr"][w]]}
    out["a"], out["z"] = cal[evs[0]], cal[evs[-1]]
    out["d"] = float(me.mean() - mb.mean())
    flag = np.isin(base, E)
    out["lo"], out["hi"], out["p"], out["p1"] = ci_p(boot_reps(mb, flag))
    out["h1"] = out["h2"] = None
    if n >= 2:
        m = n // 2
        cut = evs[m]
        b1, b2 = mb[base < cut], mb[base >= cut]
        if len(b1):
            out["h1"] = float(mdd[E[:m]].mean() - b1.mean())
        if len(b2):
            out["h2"] = float(mdd[E[m:]].mean() - b2.mean())
    out["vadj"] = vol_adjusted(E, base, mdd, vol)
    out["list"] = [[cal[t], float(mdd[t]), float(O["dd0"][t]), float(O["r60"][t]), cal[O["pk"][t]], cal[O["tr"][t]]]
                   + ([None if x is None or math.isnan(x[t]) else float(x[t])]) for t in evs]
    few = n < S.MIN_EVENTS or out["ep"] < S.MIN_EPISODES or out["lo"] is None
    out["v"] = "few" if few else None
    return out


def vol_adjusted(E: np.ndarray, base: np.ndarray, mdd: np.ndarray, vol: np.ndarray) -> float | None:
    """扣掉波動（只列）：基準日子依近 20 日波動分三組；每個事件 − 同一組基準日子的平均，再平均。"""
    bv = vol[base]
    ok = ~np.isnan(bv)
    if ok.sum() < S.VOL_GROUPS:
        return None
    cuts = np.quantile(bv[ok], [1.0 / 3.0, 2.0 / 3.0])
    g = lambda v: int(v >= cuts[0]) + int(v >= cuts[1])   # noqa: E731
    gb = np.array([g(v) for v in bv[ok]])
    mbo = mdd[base][ok]
    gm = {k: float(mbo[gb == k].mean()) for k in range(S.VOL_GROUPS) if (gb == k).any()}
    ds = [float(mdd[t]) - gm[g(vol[t])] for t in E if not math.isnan(vol[t]) and g(vol[t]) in gm]
    return float(np.mean(ds)) if ds else None


def verdict(r: dict, q: float | None) -> str:
    if r.get("v") == "few":
        return "few"
    lo, hi, h1, h2 = r.get("lo"), r.get("hi"), r.get("h1"), r.get("h2")
    if None in (lo, hi, h1, h2) or q is None or q > S.BH_Q:
        return "none"
    if lo > 0 and h1 > 0 and h2 > 0:
        return "up"
    if hi < 0 and h1 < 0 and h2 < 0:
        return "down"
    return "none"


# ── 大跌前有沒有過熱 ───────────────────────────────────────────────────────

def declines(cal: list[str], px, thr: float) -> list[dict]:
    """大跌段（VER 2，多空門檻法則）：從最高收盤跌 ≥ thr＝一段大跌；從之後的最低收盤反彈 ≥ thr 才算結束，再從那裡找下一個高點。
    → [{"pk": 高點位置, "tr": 低點位置, "dd": 跌幅（正數）, "open": 還沒反彈夠}]。"""
    p = _arr(px) if not isinstance(px, np.ndarray) else px
    out: list[dict] = []
    hi = lo = None                                    # 上漲段：hi＝最高收盤位置；下跌段：lo＝最低收盤位置
    pk = None                                         # 下跌段的高點（None＝在上漲段）
    for i, v in enumerate(p):
        if math.isnan(v) or v <= 0:
            continue
        if pk is None:
            if hi is None or v > p[hi]:
                hi = i
            elif v <= p[hi] * (1.0 - thr):
                pk, lo = hi, i
        else:
            if v < p[lo]:
                lo = i
            elif v >= p[lo] * (1.0 + thr):
                out.append({"pk": pk, "tr": lo, "dd": float(1.0 - p[lo] / p[pk]), "open": False})
                pk, hi, lo = None, i, None
    if pk is not None:
        out.append({"pk": pk, "tr": lo, "dd": float(1.0 - p[lo] / p[pk]), "open": True})
    return out


def warn_flags(x: list, we: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """逐日：R1＝今天 ≥ 80；R4＝今天是週末而且已連續過熱滿 RECALL_N 週。"""
    T = len(x)
    r1 = np.array([_hot(v) for v in x], dtype=bool)
    r4 = np.zeros(T, dtype=bool)
    for i, r in zip(we, week_runs(x, we)):
        if r >= S.RECALL_N:
            r4[i] = True
    return r1, r4


def _window_any(f: np.ndarray, L: int) -> np.ndarray:
    """逐日：第 d−L～d 天有沒有任何一天成立。"""
    c = np.concatenate([[0], np.cumsum(f.astype(np.int64))])
    d = np.arange(len(f))
    lo = np.maximum(0, d - L)
    return (c[d + 1] - c[lo]) > 0


def recall(x: list, we: list[int], decl: list[dict], i0: int = 0) -> dict:
    """大跌段（高點前 60 日都在這個變數第一個有值之後）高點前 61 天有沒有過熱，和碰巧的比例。"""
    first = next((i for i, v in enumerate(x) if _has(v)), None)
    if first is None:
        return {"n": 0}
    L = S.LOOKBACK
    r1, r4 = warn_flags(x, we)
    w1, w4 = _window_any(r1, L), _window_any(r4, L)
    has = np.array([_has(v) for v in x], dtype=bool)
    d = np.arange(len(x))
    elig = has & (d - L >= max(first, i0))
    ok = [e for e in decl if e["pk"] - L >= max(first, i0)]
    out = {"n": len(ok), "h1": int(sum(1 for e in ok if w1[e["pk"]])), "h4": int(sum(1 for e in ok if w4[e["pk"]])),
           "c1": float(w1[elig].mean()) if elig.any() else None, "c4": float(w4[elig].mean()) if elig.any() else None,
           "hit": [[int(bool(w1[e["pk"]])), int(bool(w4[e["pk"]]))] for e in ok], "pk": [e["pk"] for e in ok]}
    return out


# ── 市場層級 ──────────────────────────────────────────────────────────────

def variables(B: dict) -> tuple[list[str], list[str]]:
    """景氣頁顯示的面向、那些面向的項目（依當下規格）。"""
    from . import heatpage as HP
    from . import heatspec as HS
    dims = list(HP.shown_dims())
    items = [k for k in HS.KEYS if HS.DIM_OF[k] in dims]
    return dims, items


def var_events(x: list, we: list[int], i0: int) -> dict[str, list[int]]:
    ev = {"E": enter(x)}
    for n in S.STREAK_N:
        ev[f"S{n}"] = streaks(x, we, n)
    ev["X4"] = exits(x, we, S.EXIT_MIN)
    return {k: [t for t in v if t >= i0] for k, v in ev.items()}


def market(mk: str, B: dict, start: str | None = None, bub_rows: list | None = None) -> dict:
    """一個市場（台股或美股一個指數；美股要在 heatspec.use(該指數) 裡呼叫）。start＝驗證起點；bub_rows＝泡沫頁每月判定。"""
    from . import heatpos as P
    cal, px = B["cal"], _arr(B["px"])
    i0 = 0 if not start else next((i for i, d in enumerate(cal) if d >= start), len(cal))
    O = outcomes(px)
    vol = vol20(px)
    we = P.week_ends(cal)
    T = len(cal)
    inrange = np.arange(T) >= i0
    okO = ~np.isnan(O["mdd"])
    dims, items = variables(B)
    rows: dict = {}
    for kind, keys, src in (("dim", dims, B["comp"]), ("item", items, B["hc"])):
        for k in keys:
            x = list(src.get(k) or [None] * T)
            xa = _arr(x)
            mask = ~np.isnan(xa) & okO & inrange
            first = next((cal[i] for i in range(i0, T) if _has(x[i])), None)
            evs = var_events(x, we, i0)
            rows[k] = {"kind": kind, "first": first,
                       "ev": {e: row_stats(v, mask, O, vol, cal, xa) for e, v in evs.items()}}
    # 綜合：同時過熱的面向數、泡沫等級
    hot, have = multi_count({d: B["comp"][d] for d in dims}, dims)
    mask_m = (np.array(have) >= S.MULTI_MIN_DIMS) & okO & inrange
    ev_m = [t for t in multi({d: B["comp"][d] for d in dims}, dims) if t >= i0]
    rows["M2"] = {"kind": "mkt", "first": next((cal[i] for i in range(i0, T) if have[i] >= S.MULTI_MIN_DIMS), None),
                  "ev": {"E": row_stats(ev_m, mask_m, O, vol, cal, _arr(hot))}}
    if bub_rows:
        months = bubble_months(bub_rows, cal[-1])
        m0 = next((bisect.bisect_left(cal, d) for d, _ in months), None)
        for k in S.BUB_K:
            key = f"BL{k}"
            if m0 is None:
                rows[key] = {"kind": "mkt", "first": None, "ev": {"E": {"n": 0, "v": "few"}}}
                continue
            mask_b = okO & inrange & (np.arange(T) >= m0)
            evb = [t for t in bubble_events(cal, months, k) if t >= i0]
            lv = np.full(T, np.nan)
            for d, L in months:
                i = bisect.bisect_right(cal, d) - 1
                if i >= 0:
                    lv[i] = L
            rows[key] = {"kind": "mkt", "first": cal[min(max(m0, i0), T - 1)], "ev": {"E": row_stats(evb, mask_b, O, vol, cal, lv)}}
    # BH：同一事件類型的全部變數（綜合組另一家族）
    fams: dict[str, list] = {}
    for k, r in rows.items():
        for e, st in r["ev"].items():
            fam = "mkt" if r["kind"] == "mkt" else e
            fams.setdefault(fam, []).append((k, e, st))
    for fam, lst in fams.items():
        ks = [(k, e, st) for k, e, st in lst if st.get("v") != "few" and st.get("p") is not None]
        qs = bh([st["p"] for _, _, st in ks])
        for (_, _, st), q in zip(ks, qs):
            st["q"] = q
        for _, _, st in lst:
            st["v"] = verdict(st, st.get("q"))
    # 全部日子（市場層級的基準，從樣本起點起）
    allm = okO & inrange
    base = dist(O["mdd"][allm])
    base.update({"n": int(allm.sum()), "r60": _mean(O["r60"][allm]), "up": float(np.mean(O["r60"][allm] > 0))})
    # 大跌前有沒有過熱
    dec = {str(int(th * 100)): [{**e, "pk": e["pk"] + i0, "tr": e["tr"] + i0} for e in declines(cal[i0:], px[i0:], th)]
           for th in S.DECL_TH}                      # 從樣本起點起算前高（S&P 500 不從 1929 年的高點算起）
    rec = {}
    for k in dims + items:
        src = B["comp"] if k in dims else B["hc"]
        x = list(src.get(k) or [None] * T)
        rec[k] = {th: recall(x, we, dec[th], i0) for th in dec}
    for k in rows:
        if k in rec:
            rows[k]["rec"] = {th: {a: b for a, b in v.items() if a not in ("hit", "pk")} for th, v in rec[k].items()}
    dims_hit = {th: [{d: rec[d][th]["hit"][rec[d][th]["pk"].index(e["pk"])] if e["pk"] in rec[d][th].get("pk", []) else None
                      for d in dims} for e in dec[th]] for th in dec}
    decl_out = {th: [{"pk": cal[e["pk"]], "tr": cal[e["tr"]], "dd": e["dd"], "open": e["open"], "dims": dims_hit[th][j]}
                     for j, e in enumerate(dec[th])] for th in dec}
    return {"start": cal[i0] if i0 < T else None, "end": cal[-1], "dims": dims, "items": items, "base": base,
            "rows": rows, "decl": decl_out}


def primary(M: dict) -> dict:
    """主要假說（Holm、單尾）。"""
    out: dict = {}
    for h, spec in S.PRIMARY.items():
        st = ((M.get(spec["mk"]) or {}).get("rows") or {}).get(spec["var"], {}).get("ev", {}).get(spec["ev"]) or {}
        out[h] = {k: st.get(k) for k in ("n", "ep", "d", "lo", "hi", "p1", "h1", "h2")}
        out[h]["few"] = st.get("v") == "few" or st.get("p1") is None
    adj, rej = holm({h: (None if v["few"] else v["p1"]) for h, v in out.items()})
    for h, v in out.items():
        v["padj"] = adj.get(h)
        v["ok"] = bool(rej.get(h) and (v.get("h1") or 0) > 0 and (v.get("h2") or 0) > 0)
    return out


# ── 研究檔 ────────────────────────────────────────────────────────────────

def _r(x):
    """浮點數留 4 位有效數字（回撤、比例、差都夠用）。"""
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(x) else float(f"{float(x):.4g}")
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, dict):
        return {a: _r(b) for a, b in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(b) for b in x]
    return x


def research(BT: dict | None = None, BA: dict | None = None, BX: dict | None = None) -> dict:
    """BT＝heatcalc.build()、BA＝heatcalc_us.build_all()、BX＝bubble.compute()（測試可傳假資料）。"""
    from . import heatcalc as HC
    from . import heatcalc_us as HU
    from . import heatspec as HS
    from . import heatspec_us as U
    BT = BT if BT is not None else HC.build()
    BA = BA if BA is not None else HU.build_all()
    if BX is None:
        from . import bubble as BU
        BX = BU.compute()
    rows = lambda mk: (((BX or {}).get(mk) or {}).get("_C") or {}).get("rows") or []   # noqa: E731
    M = {"tw": market("tw", BT, None, rows("tw"))}
    for idx in U.INDEX_ORDER:
        with HS.use(U.spec_for(idx)):
            M[idx] = market(idx, BA[idx], U.VAL_START[idx], rows(idx))
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "markets": _r(M), "primary": _r(primary(M))}


def save_research(R: dict) -> None:
    RESEARCH.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load_research() -> dict | None:
    try:
        R = json.loads(RESEARCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None


# ── 每天建頁：現在的狀態 ──────────────────────────────────────────────────

def run_mdd(px: np.ndarray, a: int, b: int) -> dict | None:
    """第 a～b 天收盤的最大回撤、最高點、最低點、期間漲跌。"""
    if a > b or a < 0 or b >= len(px):
        return None
    w = px[a:b + 1]
    if np.isnan(w).any() or w[0] <= 0:
        return None
    run = np.maximum.accumulate(w)
    dd = 1.0 - w / run
    s = int(dd.argmax())
    pk = int(np.argmax(w[:s + 1]))
    return {"mdd": float(dd[s]), "pk": a + pk, "tr": a + s, "days": b - a, "chg": float(w[-1] / w[0] - 1.0)}


def instance(cal: list[str], px: np.ndarray, i: int, t: int) -> dict:
    """這一次的事件（第 i 天）：之後 3 個月（第 i＋LAG～i＋LAG＋H 天，最多到今天 t）的最大回撤；full＝3 個月已經走完。"""
    a = i + S.LAG
    out = {"d": cal[i], "days": max(0, min(a + S.H, t) - a) if a <= t else 0, "full": a + S.H <= t, "mdd": None}
    r = run_mdd(px, a, min(a + S.H, t)) if a <= t else None
    if r:
        out.update({"mdd": r["mdd"], "pk": cal[r["pk"]], "tr": cal[r["tr"]], "chg": r["chg"], "days": r["days"]})
    return out


def now(B: dict, R_mk: dict | None) -> dict:
    """今天（日曆最後一天）：過熱中的面向與項目（已連續幾週、這一次進入過熱與連續滿 N 週之後 3 個月的最大回撤，
    不到 3 個月的算到今天）、最近 60 個交易日內剛結束過熱的、同時過熱的面向數。R_mk＝研究檔裡這個市場的結果。"""
    from . import heatpos as P
    cal, px = B["cal"], _arr(B["px"])
    T = len(cal)
    t = T - 1
    we = P.week_ends(cal)
    dims, items = variables(B)
    out: dict = {"d": cal[t], "hot": [], "exit": [], "multi": None}
    for kind, keys, src in (("dim", dims, B["comp"]), ("item", items, B["hc"])):
        for k in keys:
            x = list(src.get(k) or [None] * T)
            v = x[t]
            if _hot(v):
                runs = week_runs(x, we)
                wk = runs[-1] if we and we[-1] == t else 0
                j = t
                while j > 0 and _hot(x[j - 1]):
                    j -= 1
                inst = {"E": instance(cal, px, j, t)}
                ns = [n for n in S.STREAK_N if n <= wk]
                if ns:
                    n = ns[-1]
                    w = we[len(we) - wk + n - 1]                # 這一段連續過熱的第 n 個週末
                    inst[f"S{n}"] = instance(cal, px, w, t)
                out["hot"].append({"k": k, "kind": kind, "v": float(v), "wk": wk, "start": cal[j],
                                   "ev": list(inst), "inst": inst})
            elif _has(v):
                ex = [i for i in exits(x, we, S.EXIT_MIN) if i >= t - S.H]
                if ex:
                    out["exit"].append({"k": k, "kind": kind, "v": float(v), "inst": {"X4": instance(cal, px, ex[-1], t)}})
    hot, have = multi_count({d: B["comp"][d] for d in dims}, dims)
    out["multi"] = {"n": hot[t] if T else 0, "have": have[t] if T else 0,
                    "dims": [d for d in dims if _hot(B["comp"][d][t])]}
    out["hot"].sort(key=lambda r: (r["kind"] != "dim", -r["wk"], -r["v"]))
    return out
