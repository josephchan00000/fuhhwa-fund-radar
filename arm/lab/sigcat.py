"""訊號總覽（docs/lab_signal_plan.md、arm/lab/sigspec.py）：把所有市場訊號依規格展開，算命中率、平常、判定與現在有沒有效。

研究：scripts/run_sig.py → data/lab/sig_research.json（資料或規格改了才重跑）。
每天建頁：frames() 由各頁已經算好的資料組成，now_market() 只算「現在有沒有效」。
"""
from __future__ import annotations

import bisect
import json
import math
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from . import sigluck as LK
from . import sigspec as S

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "lab" / "sig_research.json"

CAT_NAMES = {"heat": "景氣項目", "multi": "景氣面向", "scen": "情境", "inst": "法人買賣超", "tech": "技術事件", "deriv": "邊際變化",
             "crash": "大跌風險", "bub": "泡沫", "ind": "產業泡沫", "buy": "大跌後買點", "stock": "個股訊號", "strat": "個股策略"}
TIER_ORDER = {t: i for i, t in enumerate(S.TIERS)}


def _arr(xs) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in xs], dtype=float)


def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _lst(a) -> list:
    """NaN → None（heatrel／hotdd 的事件函式用 None 表示沒有值）。"""
    return [None if _nan(float(v)) else float(v) for v in a]


# ── 結果 ─────────────────────────────────────────────────────────────────────

def warn_th(mk: str, H: int) -> float:
    from . import crashspec as CS
    return CS.TH[mk][S.WARN_TH_IDX[H]] if H in S.WARN_TH_IDX else S.WARN_LONG


def mdd_path(xs) -> float | None:
    """一段收盤（依時間）的最大回撤：期間最高收盤到之後最低收盤的跌幅（0～1）；沒有值回 None。"""
    pk, dd = None, 0.0
    for x in xs:
        if x is None or _nan(x) or x <= 0:
            continue
        if pk is None or x > pk:
            pk = x
        else:
            dd = max(dd, 1.0 - x / pk)
    return None if pk is None else dd


def outcomes(px, H: int, th: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """第 t 天的訊號 → (偏多, 警示, 最大回撤)：偏多與警示 1／0、最大回撤 0～1；窗口不完整或沒有收盤＝NaN。
    e＝t＋LAG；偏多＝第 e＋H 天收盤 > 第 e 天；警示（sigspec VER 3）＝第 e～e＋H 天收盤的最大回撤 ≥ th
    （期間最高收盤到之後最低收盤；第 e 天也可以是高點）。窗口完整的條件和 VER 1～2 一樣（第 e、e＋H 天有收盤、中間至少一天有收盤）。"""
    px = np.asarray(px, dtype=float)
    T = len(px)
    up = np.full(T, np.nan)
    wn = np.full(T, np.nan)
    dd = np.full(T, np.nan)
    n = T - S.LAG - H
    if n <= 0:
        return up, wn, dd
    pe = px[S.LAG:S.LAG + n]
    pz = px[S.LAG + H:S.LAG + H + n]
    win = np.lib.stride_tricks.sliding_window_view(px[S.LAG:], H + 1)[:n]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mn = np.nanmin(win[:, 1:], axis=1)
        pk = np.fmax.accumulate(win, axis=1)
        mdd = np.nanmax(1.0 - win / pk, axis=1)
    ok = ~np.isnan(pe) & ~np.isnan(pz) & ~np.isnan(mn)
    mdd = np.maximum(mdd, 0.0)
    up[:n] = np.where(ok, (pz > pe).astype(float), np.nan)
    wn[:n] = np.where(ok, (mdd >= th).astype(float), np.nan)
    dd[:n] = np.where(ok, mdd, np.nan)
    return up, wn, dd


def fwd_ret(px, H: int) -> np.ndarray:
    """第 t 天的訊號 → 第 e＋H 天收盤 ÷ 第 e 天收盤 − 1（e＝t＋LAG；只呈現，訊號總覽「最近幾次」的之後漲跌）。"""
    px = np.asarray(px, dtype=float)
    T = len(px)
    out = np.full(T, np.nan)
    n = T - S.LAG - H
    if n > 0:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            out[:n] = px[S.LAG + H:S.LAG + H + n] / px[S.LAG:S.LAG + n] - 1.0
    return out


def fwd_mae(px, H: int) -> np.ndarray:
    """第 t 天的訊號 → 中途最多跌＝min(0, 第 e＋1～e＋H 天最低收盤 ÷ 第 e 天收盤 − 1)（e＝t＋LAG；sigspec 第 4.11 節，只呈現）。"""
    px = np.asarray(px, dtype=float)
    T = len(px)
    out = np.full(T, np.nan)
    n = T - S.LAG - H
    if n > 0:
        win = np.lib.stride_tricks.sliding_window_view(px[S.LAG:], H + 1)[:n]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            out[:n] = np.minimum(0.0, np.nanmin(win[:, 1:], axis=1) / win[:, 0] - 1.0)
    return out


def ret_arrays(px, hs=None, ps=None) -> dict:
    """報酬（PATH_D 每一天）與中途最多跌（RET_H 每一期）的逐日陣列；第 t 格＝第 t 天訊號、隔一個交易日收盤進場。"""
    hs = S.RET_H if hs is None else hs
    ps = S.PATH_D if ps is None else ps
    return {"R": {d: fwd_ret(px, d) for d in sorted(set(ps) | set(hs))}, "A": {h: fwd_mae(px, h) for h in hs},
            "hs": tuple(hs), "ps": tuple(ps)}


def wquant(v: np.ndarray, w: np.ndarray, q: float) -> float:
    """加權百分位（sigspec 第 4.11 節）：由小到大排，累計權重第一次 ≥ q × 總權重的那一個值（不內插）。"""
    o = np.argsort(v, kind="stable")
    cw = np.cumsum(w[o])
    k = int(np.searchsorted(cw, q * cw[-1] * (1 - 1e-12), side="left"))
    return float(v[o][min(k, len(v) - 1)])


def ret_cell(r: np.ndarray, a: np.ndarray, w: np.ndarray, n: int) -> list | None:
    """→ [次數, 平均, 25%, 中位數, 75%, 上漲比例, 中途最多跌中位數, 中途最多跌最差 10%, 最差一次]。"""
    if n <= 0 or not len(r):
        return None
    W = float(w.sum())
    return [int(n), float((r * w).sum() / W), *(wquant(r, w, q) for q in S.RET_Q), float(w[r > 0].sum() / W),
            wquant(a, w, 0.5), wquant(a, w, S.MAE_Q), float(a.min())]


def ret_stats(groups: list, RA: dict) -> dict:
    """groups＝每一次在 RA 陣列裡的索引（事件：一天；狀態：一段的樣本日）；每一段一樣重（段內窗口完整的日子平分）。
    → {"s": RET_H 每一期一格（ret_cell）, "p": PATH_D 每一天 [25%, 中位數, 75%]}。"""
    gs = [np.asarray(g, dtype=np.int64) for g in groups]
    gs = [g for g in gs if len(g)]

    def pick(Y, Z=None):
        rs, zs, ws, n = [], [], [], 0
        for g in gs:
            m = np.isfinite(Y[g]) if Z is None else (np.isfinite(Y[g]) & np.isfinite(Z[g]))
            k = g[m]
            if not len(k):
                continue
            n += 1
            rs.append(Y[k])
            ws.append(np.full(len(k), 1.0 / len(k)))
            if Z is not None:
                zs.append(Z[k])
        if not n:
            return None
        return (np.concatenate(rs), np.concatenate(zs) if Z is not None else None, np.concatenate(ws), n)

    out_s = []
    for h in RA["hs"]:
        P = pick(RA["R"][h], RA["A"][h])
        out_s.append(None if P is None else ret_cell(P[0], P[1], P[2], P[3]))
    out_p = []
    for d in RA["ps"]:
        P = pick(RA["R"][d])
        out_p.append(None if P is None else [wquant(P[0], P[2], q) for q in S.RET_Q])
    return {"s": out_s, "p": out_p}


def ret_base(samp: np.ndarray, RA: dict, cache: dict, tag: str) -> str:
    """平常＝樣本日每一天等權；同一批樣本日的結果只算一次、存一份（→ 研究檔 bases[key]）。"""
    import hashlib
    samp = np.asarray(samp, dtype=np.int64)
    key = tag + ":" + hashlib.md5(samp.tobytes()).hexdigest()[:12]
    if key not in cache:
        cache[key] = _ret_flat(samp, RA)
    return key


def _ret_flat(idx: np.ndarray, RA: dict) -> dict:
    """每一天等權（平常、事件）：和 ret_stats 每一天各自一組的結果相同，比較快。"""
    idx = np.asarray(idx, dtype=np.int64)
    out_s = []
    for h in RA["hs"]:
        R, A = RA["R"][h][idx], RA["A"][h][idx]
        m = np.isfinite(R) & np.isfinite(A)
        out_s.append(ret_cell(R[m], A[m], np.ones(int(m.sum())), int(m.sum())))
    out_p = []
    for d in RA["ps"]:
        R = RA["R"][d][idx]
        R = R[np.isfinite(R)]
        out_p.append([wquant(R, np.ones(len(R)), q) for q in S.RET_Q] if len(R) else None)
    return {"s": out_s, "p": out_p}


# ── 次數、命中率、判定 ─────────────────────────────────────────────────────────

def recent_from(cal: list[str]) -> str:
    """資料最後一天往前 RECENT_YEARS 年（同月同日；2/29 改 2/28）。"""
    d = date.fromisoformat(cal[-1])
    try:
        return d.replace(year=d.year - S.RECENT_YEARS).isoformat()
    except ValueError:
        return d.replace(year=d.year - S.RECENT_YEARS, day=28).isoformat()


def dedupe(days, H: int) -> list[int]:
    """一次訊號之後 H 個交易日內再出現不算新的一次。"""
    out, last = [], None
    for t in sorted(days):
        if last is not None and t - last <= H:
            continue
        out.append(int(t))
        last = t
    return out


def _mean(xs) -> float | None:
    xs = [x for x in xs if not _nan(x)]
    return float(np.mean(xs)) if xs else None


def _base(Y: np.ndarray, samp: np.ndarray) -> float | None:
    v = Y[samp]
    v = v[~np.isnan(v)]
    return float(v.mean()) if len(v) else None


def _median(xs) -> float | None:
    xs = [x for x in xs if not _nan(x)]
    return float(np.median(xs)) if xs else None


def _base_med(Y: np.ndarray | None, samp: np.ndarray) -> float | None:
    if Y is None:
        return None
    v = Y[samp]
    v = v[~np.isnan(v)]
    return float(np.median(v)) if len(v) else None


def ev_stat(days, Yu: np.ndarray, Yw: np.ndarray, samp: np.ndarray, H: int, r0: int, Yd: np.ndarray | None = None,
            Yr: np.ndarray | None = None) -> dict:
    """事件型：samp＝可以算平常的日子（輸入有值）索引；r0＝近 10 年起點的索引；Yd＝每一天的最大回撤（VER 3，只呈現）；
    Yr＝每一天之後的漲跌（只呈現）。
    → {"up": 統計, "warn": 統計（另有 mdd、mdd_base＝最大回撤中位數）, "occ": [[t, 偏多, 警示, 最大回撤, 之後漲跌], …]}（只含窗口完整的次）。"""
    ok = set(int(i) for i in samp)
    kept = dedupe([t for t in days if t in ok], H)
    occ = [[t, Yu[t], Yw[t], np.nan if Yd is None else Yd[t], np.nan if Yr is None else Yr[t]]
           for t in kept if not (np.isnan(Yu[t]) or np.isnan(Yw[t]))]
    samp10 = samp[samp >= r0]
    out = {"occ": occ}
    for j, (dk, Y) in enumerate((("up", Yu), ("warn", Yw))):
        ys = [o[1 + j] for o in occ]
        ys10 = [o[1 + j] for o in occ if o[0] >= r0]
        out[dk] = {"n": len(ys), "hit": _mean(ys), "base": _base(Y, samp),
                   "n10": len(ys10), "hit10": _mean(ys10), "base10": _base(Y, samp10)}
    if Yd is not None:
        out["warn"].update(mdd=_median([o[3] for o in occ]), mdd_base=_base_med(Yd, samp))
    return out


def episodes(pos: list[int], gap: int) -> list[list[int]]:
    """pos＝狀態中的樣本在樣本序列裡的位置（遞增）→ 每一段的位置；中斷的樣本數 < gap 算同一段。"""
    out: list[list[int]] = []
    for p in pos:
        if out and p - out[-1][-1] - 1 < gap:
            out[-1].append(p)
        else:
            out.append([p])
    return out


def st_stat(state: np.ndarray, samp: np.ndarray, Yu: np.ndarray, Yw: np.ndarray, gap: int, r0: int,
            Yd: np.ndarray | None = None, Yr: np.ndarray | None = None) -> dict:
    """狀態型：samp＝樣本日（輸入有值；月資料＝每月最後一個交易日）索引，state＝這些樣本日是否在狀態中（同長度）。
    一段的命中率＝段內窗口完整的日子的比例；整體＝各段平均。Yd＝每一天的最大回撤（VER 3，只呈現：一段＝段內平均，整體＝各段中位數）。
    Yr＝每一天之後的漲跌（只呈現，一段＝段內平均）。
    → {"up", "warn", "occ": [[第一天, 最後一天, 天數, 偏多, 警示, 最大回撤, 之後漲跌], …]}。"""
    pos = [i for i in range(len(samp)) if state[i]]
    occ = []
    for ep in episodes(pos, gap):
        ts = samp[ep]
        u, w = Yu[ts], Yw[ts]
        m = ~np.isnan(u) & ~np.isnan(w)
        if not m.any():
            continue
        occ.append([int(ts[0]), int(ts[-1]), int(len(ts)), float(u[m].mean()), float(w[m].mean()),
                    np.nan if Yd is None else float(Yd[ts][m].mean()), _mean(Yr[ts][m]) if Yr is not None else np.nan])
    samp10 = samp[samp >= r0]
    out = {"occ": occ}
    for j, (dk, Y) in enumerate((("up", Yu), ("warn", Yw))):
        ys = [o[3 + j] for o in occ]
        ys10 = [o[3 + j] for o in occ if o[0] >= r0]
        out[dk] = {"n": len(ys), "hit": _mean(ys), "base": _base(Y, samp),
                   "n10": len(ys10), "hit10": _mean(ys10), "base10": _base(Y, samp10)}
    if Yd is not None:
        out["warn"].update(mdd=_median([o[5] for o in occ]), mdd_base=_base_med(Yd, samp))
    return out


def tier(st: dict, d: str, recent: bool = True) -> str:
    """sigspec 第 3 節（VER 9）：★＝過門檻而且打亂測試 p ≤ LUCK_P；●＝過門檻但 p > LUCK_P（可能是運氣）；○ 沒過門檻；— 次數不夠。
    st["p"]＝打亂測試（sigluck；沒有算＝None，當作沒過）。用沒有四捨五入的數字。"""
    n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
    if n < S.N_MIN or hit is None or base is None:
        return "few"
    if not LK.passes(n, hit, base, st.get("n10"), st.get("hit10"), st.get("base10"), d, recent):
        return "none"
    p = st.get("p")
    return "good" if p is not None and p <= S.LUCK_P else "ref"


def judge(st: dict, d: str, recent: bool = True) -> str:
    st["tier"] = tier(st, d, recent)
    return st["tier"]


def best(dirs: dict) -> tuple[str, list[str]]:
    """這一列的判定＝各方向裡較好的（同級取差大的）；兩個方向都是 ★ 就兩個都列。"""
    def key(d):
        e = edge(dirs[d])
        return (TIER_ORDER[dirs[d]["tier"]], -(e if e is not None else -9))
    ds = sorted(dirs, key=key)
    top = dirs[ds[0]]["tier"]
    return top, ([d for d in ds if dirs[d]["tier"] == "good"] if top == "good" else [ds[0]])


# ── 市場資料 ─────────────────────────────────────────────────────────────────

def _names(HS) -> dict:
    return {k: nm for k, _, nm, *_ in HS.IND}


def frame(mk: str, B: dict, I: dict, IB: dict | None = None, BX: dict | None = None) -> dict:
    """一個市場的訊號資料（美股要在 heatspec.use(該指數) 裡呼叫）：
    B＝景氣頁的 build、I＝crash 的輸入（日曆、收盤、W1～W4／VOL）、IB＝bottom 的輸入、BX＝bubble.compute()。"""
    from . import crash as CR
    from . import heatpage as HP
    from . import heatpos as P
    from . import heatspec as HS
    cal = list(I["cal"])
    px = np.asarray(I["px"], dtype=float)
    nm = _names(HS)
    dims = list(HP.shown_dims())
    V = []
    for d in dims:
        V.append({"key": "D" + d, "name": HS.DIMS[d]["name"], "grp": d, "H": S.H_DIM[d],
                  "x": CR.align(cal, B["cal"], B["comp"][d])})
        for k in HS.ITEMS[d]:
            V.append({"key": k, "name": nm[k], "grp": d, "H": S.H_DIM[d],
                      "x": CR.align(cal, B["cal"], B["hc"].get(k) or [None] * len(B["cal"]))})
    CV = []
    from . import crashspec as CS
    for k in S.CRASH_VARS[mk]:
        if k in I["x"]:
            CV.append({"key": k, "name": CS.PRED_NAMES[k], "grp": "crash", "H": S.H_CRASH, "x": np.asarray(I["x"][k], float)})
    comp = {d: CR.align(cal, B["cal"], B["comp"][d]) for d in dims}
    DV = []
    for k in HS.DERIV:
        st = P.deriv(B, k)["state"]
        x = CR.align(cal, B["cal"], [None if s in (None, 0) else float(s) for s in st])
        flat = CR.align(cal, B["cal"], [None if s is None else float(s) for s in st])
        DV.append({"key": k, "name": nm[k], "kind": HS.DERIV[k]["kind"], "x": x, "have": ~np.isnan(flat)})
    rows = ((BX or {}).get(mk) or {}).get("_C", {}).get("rows") or []
    return {"mk": mk, "cal": cal, "px": px, "we": P.week_ends(cal), "vars": V, "cvars": CV, "comp": comp, "dims": dims,
            "ivars": inst_vars(cal, B) if mk == "tw" else [],
            "deriv": DV, "deriv_words": dict(HS.DERIV_WORDS), "bub": rows, "IB": IB, "r0": recent_from(cal)}


def frames(BT: dict | None = None, BA: dict | None = None, BX: dict | None = None) -> dict:
    """五個市場（研究用；每天建頁由各頁自己組 frame）。"""
    from . import bottom as BO
    from . import bubble as BU
    from . import crash as CR
    from . import heatcalc as HC
    from . import heatcalc_us as HU
    from . import heatdata as HD
    from . import heatspec as HS
    from . import heatspec_us as U
    BX = BX if BX is not None else BU.compute()
    BT = BT if BT is not None else HC.build()
    IT = CR.tw_inputs(B=BT, BX=BX)
    F = {"tw": frame("tw", BT, IT, BO.inputs_tw(BT, IT, BX), BX)}
    BA = BA if BA is not None else HU.build_all()
    for idx in U.INDEX_ORDER:
        with HS.use(U.spec_for(idx)):
            I0 = CR.us_inputs(idx, Bu=BA[idx], BX=BX)
            from . import bottomspec as BS
            vol = HD.load(f"us_vol_{idx}") if "C7" in BS.SIG_MK[idx] else None
            F[idx] = frame(idx, BA[idx], I0, BO.inputs_us(idx, BA[idx], I0, vol, BX), BX)
    return F


# ── 訊號展開 ─────────────────────────────────────────────────────────────────

def _var_signals(F: dict, v: dict, cat: str) -> list[dict]:
    """景氣項目／面向／大跌風險項目的 6 種。"""
    from . import hotch as HCH
    from . import hotdd as HDD
    from .heatrel import heat_events
    x = v["x"]
    T = len(x)
    have = ~np.isnan(x)
    samp = np.nonzero(have)[0]
    xl = _lst(x)
    out = []
    for sg in S.VARIANTS:
        kind = S.VARIANT_KIND[sg]
        sd = {"id": f"{F['mk']}:{cat}:{v['key']}:{sg}", "cat": cat, "grp": v["grp"], "var": v["key"], "vn": v["name"],
              "sig": sg, "name": f"{v['name']}・{S.VARIANT_NAMES[sg]}", "kind": kind, "H": v["H"], "samp": samp}
        if sg == "hot":
            sd["state"] = x[samp] >= S.HOT
        elif sg == "cold":
            sd["state"] = x[samp] < S.COLD
        elif sg == "hot13":
            w = HCH.streak_days(xl, F["we"])
            sd["state"] = np.array([(w[i] or 0) >= S.HOT_WEEKS for i in samp], dtype=bool)
        elif sg == "hot_in":
            sd["days"] = heat_events(xl, "hot")
        elif sg == "cold_in":
            sd["days"] = heat_events(xl, "cold")
        elif sg == "hot_out":
            sd["days"] = HDD.exits(xl, F["we"], S.EXIT_MIN)
        out.append(sd)
    return out


# ── 法人買賣超（sigspec VER 6 第 4.13 節） ─────────────────────────────────────

def inst_vars(cal: list, B: dict) -> list[dict]:
    """15 個法人變數在這個日曆上的 0～100（賣超＝熱；和景氣項目同一套：交易日對齊、和過去 750 天比、至少 375 天）
    與單日買賣超金額（元，連續買賣超用；沒有資料＝NaN）。只當訊號（sigspec VER 7），不算進任何面向。"""
    from . import crash as CR
    from . import heat as H
    from . import heatcalc as HC
    from . import heatspec as HS
    D = B.get("D") or {}
    if not D.get("inst"):
        return []
    A = HC.inst_amounts(D["inst"])
    out = []
    for who in S.INST_WHO:
        amt = np.array([np.nan if A[who].get(d) is None else float(A[who][d]) for d in cal], dtype=float)
        for w in S.INST_WIN:
            if (who, w) in S.INST_SKIP:
                continue
            raw = H.asof_daily(B["cal"], HC.inst_ratio(B["cal"], D, who, w, A), stale=7)
            hb = [H.to_heat(p, -1) for p in H.pct_series(raw, HS.PCT_WIN["d"], HS.PCT_MIN["d"])]
            name = f"{S.INST_NAMES[who]}{'單日' if w == 1 else f' {w} 日'}買賣超"
            out.append({"key": f"{who}{w}", "who": who, "w": w, "name": name, "H": S.INST_H[w],
                        "x": CR.align(cal, B["cal"], hb), "amt": amt})
    return out


def cold_exits(x: list, we: list[int], n: int) -> list[int]:
    """大買超結束（hotdd.exits 的鏡像）：連續 ≥ n 週的週末都 < COLD 之後，第一個有值而且 ≥ COLD 的週末。"""
    out, run = [], 0
    for i in we:
        v = x[i]
        if v is not None and not _nan(v) and v < S.COLD:
            run += 1
            continue
        if v is not None and not _nan(v) and run >= n:
            out.append(i)
        run = 0
    return out


def run_days(amt: np.ndarray, sign: int, n: int) -> list[int]:
    """連續 n 個交易日買超（sign＝1，金額 > 0）或賣超（−1，< 0）的第 n 天；沒有資料或等於 0 算中斷，同一段只算一次。"""
    out, c = [], 0
    for t, a in enumerate(amt):
        c = c + 1 if (not np.isnan(a) and a * sign > 0) else 0
        if c == n:
            out.append(t)
    return out


def inst_signals(F: dict) -> list[dict]:
    """位階 6 種（5、20、60 日）、單日極端、連續買超／賣超（sigspec 第 4.13 節）。"""
    from . import hotdd as HDD
    from .heatrel import heat_events
    mk = F["mk"]
    out = []
    for v in F.get("ivars") or []:
        x = np.asarray(v["x"], dtype=float)
        samp = np.nonzero(~np.isnan(x))[0]
        xl = _lst(x)
        base = {"cat": "inst", "grp": v["who"], "var": f"{v['who']}1" if v["w"] == 1 else v["key"], "vn": v["name"],
                "H": v["H"]}
        if v["w"] in S.INST_POS_WIN:
            for sg in S.INST_VARIANTS:
                sd = {**base, "id": f"{mk}:inst:{v['key']}:{sg}", "sig": sg, "name": f"{v['name']}・{S.INST_VARIANT_NAMES[sg]}",
                      "kind": "state" if sg in ("hot", "cold") else "event", "samp": samp}
                if sg == "hot":
                    sd["state"] = x[samp] >= S.HOT
                elif sg == "cold":
                    sd["state"] = x[samp] < S.COLD
                elif sg == "hot_in":
                    sd["days"] = heat_events(xl, "hot")
                elif sg == "cold_in":
                    sd["days"] = heat_events(xl, "cold")
                elif sg == "hot_out":
                    sd["days"] = HDD.exits(xl, F["we"], S.EXIT_MIN)
                else:
                    sd["days"] = cold_exits(xl, F["we"], S.EXIT_MIN)
                out.append(sd)
            continue
        hi, lo = S.INST_DAY
        out.append({**base, "id": f"{mk}:inst:{v['key']}:day_sell", "sig": "day_sell", "kind": "event", "samp": samp,
                    "name": f"{v['name']}・單日大賣（過去 3 年賣超最多的 5%）", "days": [int(t) for t in samp if x[t] >= hi]})
        out.append({**base, "id": f"{mk}:inst:{v['key']}:day_buy", "sig": "day_buy", "kind": "event", "samp": samp,
                    "name": f"{v['name']}・單日大買（過去 3 年買超最多的 5%）", "days": [int(t) for t in samp if x[t] <= lo]})
        amt = np.asarray(v["amt"], dtype=float)
        sa = np.nonzero(~np.isnan(amt))[0]
        who = S.INST_NAMES[v["who"]]
        for sign, tag, word in ((-1, "sell", "賣超"), (1, "buy", "買超")):
            for n in S.INST_RUN:
                out.append({**base, "H": S.INST_H["run"], "id": f"{mk}:inst:{v['key']}:{tag}_run{n}", "sig": f"{tag}_run{n}",
                            "kind": "event", "samp": sa, "name": f"{v['name']}・{who}連續 {n} 天{word}",
                            "days": run_days(amt, sign, n)})
    return out


def scen_series(F: dict) -> dict:
    """情境用的四個共通面向（sigspec 第 4.10 節）→ {面向: 依日曆的分數陣列}；台股資金＝全球與台灣資金平均，兩個都有值才算。"""
    src = S.SCEN_SRC["tw" if F["mk"] == "tw" else "us"]
    T = len(F["cal"])
    out = {}
    for g in S.SCEN_DIMS:
        arrs = [np.asarray(F["comp"][d], dtype=float) for d in src[g] if d in F["comp"]]
        out[g] = np.mean(np.vstack(arrs), axis=0) if len(arrs) == len(src[g]) else np.full(T, np.nan)
    return out


def scen_flags(X: dict, cond) -> tuple[np.ndarray, np.ndarray]:
    """一個情境 → (樣本：條件用到的面向都有值的日子, 每一天在不在情境中)。多數面向：至少 SCEN_MIN_DIMS 個面向有值。"""
    if cond in ("many_hi", "many_lo"):
        M = np.vstack([X[g] for g in S.SCEN_DIMS])
        have = (~np.isnan(M)).sum(axis=0) >= S.SCEN_MIN_DIMS
        on = (M >= S.SCEN_HI) if cond == "many_hi" else (M < S.SCEN_LO)
        return have, have & ((on & ~np.isnan(M)).sum(axis=0) >= S.SCEN_MANY)
    have = np.ones(len(next(iter(X.values()))), dtype=bool)
    on = have.copy()
    for g, o in cond:
        x = X[g]
        have &= ~np.isnan(x)
        on &= (x >= S.SCEN_HI) if o == "hi" else (x < S.SCEN_LO)
    return have, have & on


def scen_signals(F: dict) -> list[dict]:
    X = scen_series(F)
    out = []
    for key, name, cond, why in S.SCENARIOS:
        have, on = scen_flags(X, cond)
        samp = np.nonzero(have)[0]
        out.append({"id": f"{F['mk']}:scen:{key}", "cat": "scen", "grp": "scen", "var": key, "vn": name, "sig": "on",
                    "name": name, "kind": "state", "H": S.H_SCEN, "samp": samp, "state": on[samp], "why": why})
    return out


def signals(F: dict) -> list[dict]:
    """一個市場的全部市場層級訊號定義（不含結果）。"""
    from . import heatspec as HS
    from . import heattech as TT
    from . import hotdd as HDD
    mk, cal, px = F["mk"], F["cal"], F["px"]
    T = len(cal)
    out: list[dict] = []
    for v in F["vars"]:
        out += _var_signals(F, v, "heat")
    for v in F["cvars"]:
        out += _var_signals(F, v, "crash")
    # 同時兩個以上面向過熱
    dims = F["dims"]
    hot = np.zeros(T, dtype=int)
    have = np.zeros(T, dtype=int)
    for d in dims:
        c = F["comp"][d]
        hot += (~np.isnan(c) & (np.nan_to_num(c, nan=-1) >= S.HOT)).astype(int)
        have += (~np.isnan(c)).astype(int)
    samp = np.nonzero(have >= S.MULTI_MIN_DIMS)[0]
    base = {"cat": "multi", "grp": "multi", "var": "M2", "vn": "同時兩個以上面向過熱", "H": S.H_MULTI, "samp": samp}
    out.append({**base, "id": f"{mk}:multi:M2:hot", "sig": "hot", "name": "同時兩個以上面向過熱中", "kind": "state",
                "state": hot[samp] >= S.MULTI_K})
    comp = {d: _lst(F["comp"][d]) for d in dims}
    out.append({**base, "id": f"{mk}:multi:M2:hot_in", "sig": "hot_in", "name": "進入同時兩個以上面向過熱", "kind": "event",
                "days": HDD.multi(comp, dims, S.MULTI_K)})
    # 情境（VER 4）
    out += scen_signals(F)
    # 法人買賣超（VER 6）
    out += inst_signals(F)
    # 技術事件
    ev = TT.all_events([None if _nan(p) else float(p) for p in px])
    samp = np.arange(S.EV_START, T)
    for k, nm in HS.EVENTS.items():
        out.append({"id": f"{mk}:tech:{k}", "cat": "tech", "grp": "tech", "var": k, "vn": nm, "sig": "ev", "name": nm,
                    "kind": "event", "H": S.H_TECH, "samp": samp, "days": [t for t in ev[k] if t >= S.EV_START]})
    # 邊際變化
    for v in F["deriv"]:
        samp = np.nonzero(v["have"])[0]
        words = F["deriv_words"][v["kind"]]
        for s in S.DERIV_STATES:
            out.append({"id": f"{mk}:deriv:{v['key']}:{s}", "cat": "deriv", "grp": "deriv", "var": v["key"], "vn": v["name"],
                        "sig": str(s), "name": f"{v['name']}・{words[s - 1]}", "kind": "state", "H": S.H_DERIV,
                        "samp": samp, "state": v["x"][samp] == s})
    # 泡沫（每月最後一個交易日一個樣本；只用已經過完的月份）
    from . import crash as CR
    me = CR.month_ends(cal)
    done = CR.complete_months(cal)
    rows = [r for r in F["bub"] if str(r.get("d"))[:7] in done and str(r.get("d"))[:7] in me]
    for k in S.BUB_SIGNALS:
        val = []
        for r in rows:
            if k in ("L2", "L3"):
                L = r.get("L")
                val.append((me[str(r["d"])[:7]], None if L is None else L >= int(k[1])))
            else:
                f = r.get(k)
                val.append((me[str(r["d"])[:7]], None if f is None else bool(f)))
        val = [(i, f) for i, f in val if f is not None]
        if not val:
            continue
        samp = np.array([i for i, _ in val], dtype=np.int64)
        out.append({"id": f"{mk}:bub:{k}", "cat": "bub", "grp": "bub", "var": k, "vn": S.BUB_NAMES[k], "sig": k,
                    "name": S.BUB_NAMES[k], "kind": "state", "H": S.H_BUB, "samp": samp, "monthly": True,
                    "state": np.array([f for _, f in val], dtype=bool)})
    return out


def evaluate(F: dict, sd: dict, Ycache: dict) -> dict:
    """一個訊號 → 一列（含每一次）。"""
    mk, cal = F["mk"], F["cal"]
    H = sd["H"]
    if H not in Ycache:
        Ycache[H] = outcomes(F["px"], H, warn_th(mk, H))
    Yu, Yw, Yd = Ycache[H]
    if ("r", H) not in Ycache:
        Ycache[("r", H)] = fwd_ret(F["px"], H)
    Yr = Ycache[("r", H)]
    r0 = bisect.bisect_left(cal, F["r0"])
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if "ra" not in Ycache:
        Ycache["ra"] = ret_arrays(F["px"])
    RA = Ycache["ra"]
    if sd["kind"] == "event":
        R = ev_stat(sd["days"], Yu, Yw, samp, H, r0, Yd, Yr)
        occ = [[cal[t], int(u), int(w), d, r] for t, u, w, d, r in R["occ"]]
        ok = set(int(i) for i in samp)
        ret = _ret_flat(np.asarray(dedupe([t for t in sd["days"] if t in ok], H), dtype=np.int64), RA)
    else:
        gap = 1 if sd.get("monthly") else S.EP_GAP
        state = np.asarray(sd["state"], dtype=bool)
        R = st_stat(state, samp, Yu, Yw, gap, r0, Yd, Yr)
        occ = [[cal[a], cal[z], n, u, w, d, r] for a, z, n, u, w, d, r in R["occ"]]
        ret = ret_stats([samp[ep] for ep in episodes([i for i in range(len(samp)) if state[i]], gap)], RA)
    ret["bk"] = ret_base(samp, RA, Ycache.setdefault("bases", {}), mk)
    LP = LK.market_p(sd, Yu, Yw, r0, R)                 # 打亂日子測試（VER 9）
    dirs = {}
    for d in ("up", "warn"):
        st = R[d]
        st["p"] = LP[d]["p"]
        judge(st, d)
        dirs[d] = st
    tr, ds = best(dirs)
    row = {k: sd[k] for k in ("id", "cat", "grp", "var", "vn", "sig", "name", "kind", "H")}
    row.update({"mk": mk, "th": warn_th(mk, H), "a": cal[int(samp[0])] if len(samp) else None,
                "z": cal[int(samp[-1])] if len(samp) else None, "up": dirs["up"], "warn": dirs["warn"],
                "tier": tr, "dir": ds, "occ": occ, "ret": ret})
    if sd.get("monthly"):
        row["monthly"] = True
    row["_luck"] = {d: LP[d]["luck"] for d in ("up", "warn")}   # 運氣會產生 ★ 的機率（research 加總後拿掉）
    return row


# ── 大跌後買點（bottomspec VER 3） ─────────────────────────────────────────────

def buy_rows(F: dict, bases: dict | None = None) -> list[dict]:
    """兩種大跌 × 規則：命中＝買在這一波的相對低點；平常＝同一批事件固定等 10 天（固定等 10 天＝事件隔天買）。
    報酬（VER 5）：買進日收盤進場（RA 第 b−LAG 格＝第 b 天收盤進場）；平常＝同一批事件的對照規則。"""
    from . import bottom as BO
    from . import bottomspec as BS
    I = F["IB"]
    if not I:
        return []
    mk, cal = F["mk"], F["cal"]
    RA = ret_arrays(I["px"])
    bases = {} if bases is None else bases
    out = []
    for ev in BS.EVENTS:
        recs = BO.event_recs(I, ev)
        for k in ("W10",) + tuple(BS.SIG_MK[mk]):
            base = "b1" if k == "W10" else BS.SIG_BASE
            rows = BO._lp_rows(recs, k, base)
            occ = [[cal[t], int(o["lp"]), int(ob["lp"])] for t, o, ob, _ in rows]
            r10 = [o for o in occ if o[0] >= F["r0"]]
            st = {"n": len(occ), "hit": _mean([o[1] for o in occ]), "base": _mean([o[2] for o in occ]),
                  "n10": len(r10), "hit10": _mean([o[1] for o in r10]), "base10": _mean([o[2] for o in r10]),
                  "p": LK.sign_p(sum(1 for o in occ if o[1] and not o[2]), sum(1 for o in occ if o[2] and not o[1]))}
            judge(st, "buy")
            r60 = [o.get("r60") for t, o, _, _ in rows]
            ret = _ret_flat(np.asarray([o["b"] - S.LAG for _, o, _, _ in rows], dtype=np.int64), RA)
            bk = f"{mk}:buy:{ev}:{k}:base"
            bases[bk] = _ret_flat(np.asarray([ob["b"] - S.LAG for _, _, ob, _ in rows], dtype=np.int64), RA)
            ret["bk"] = bk
            out.append({"id": f"{mk}:buy:{ev}:{k}", "mk": mk, "cat": "buy", "grp": ev, "var": k,
                        "vn": BS.RULE_NAMES[k], "sig": ev, "kind": "event", "H": None,
                        "name": f"{BS.EVENT_NAMES[ev]}・{BS.RULE_NAMES[k]}",
                        "base_name": "事件隔天就買" if k == "W10" else "固定等 10 天",
                        "a": occ[0][0] if occ else None, "z": occ[-1][0] if occ else None,
                        "buy": st, "tier": st["tier"], "dir": ["buy"], "occ": occ,
                        "up60": _mean([1.0 if (r or 0) > 0 else 0.0 for r in r60 if r is not None]), "ret": ret})
    return out


# ── 產業泡沫 ─────────────────────────────────────────────────────────────────

def _months_add(m: str, k: int) -> str:
    y, mm = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mm // 12:04d}-{mm % 12 + 1:02d}"


def _ret_groups(groups: list[list[dict]], hs: tuple, ps: tuple | None = None) -> dict:
    """每一次＝一組樣本（每個樣本 {期間: (報酬, 中途最多跌)}），每一組一樣重 → 同 ret_stats 的格式（路徑 ps 預設＝同一批期間）。"""
    def pool(h):
        rs, as_, ws, n = [], [], [], 0
        for g in groups:
            v = [x[h] for x in g if x.get(h) is not None]
            if not v:
                continue
            n += 1
            rs += [a for a, _ in v]
            as_ += [b for _, b in v]
            ws += [1.0 / len(v)] * len(v)
        return n, np.asarray(rs, dtype=float), np.asarray(as_, dtype=float), np.asarray(ws, dtype=float)

    out_s, out_p = [], []
    for h in hs:
        n, r, a, w = pool(h)
        out_s.append(ret_cell(r, a, w, n) if n else None)
    for d in (hs if ps is None else ps):
        n, r, _, w = pool(d)
        out_p.append([wquant(r, w, q) for q in S.RET_Q] if n else None)
    return {"s": out_s, "p": out_p}


def _stock_ret(Sx: dict, t: int) -> dict:
    """個股：第 t＋1 天開盤（沒有就用收盤）進場 → {期間: (第 t＋h 天收盤報酬, 第 t＋1～t＋h 天收盤的中途最多跌)}（VER 5）。"""
    c, o = Sx["c"], Sx["o"]
    T = len(c)
    if t + 1 >= T:
        return {}
    p0 = o[t + 1] or c[t + 1]
    if not p0:
        return {}
    want = set(S.RET_H) | set(S.PATH_D)
    out, lo = {}, None
    for h in range(1, max(want) + 1):
        if t + h >= T:
            break
        ch = c[t + h]
        if ch:
            lo = ch if lo is None else min(lo, ch)
            if h in want:
                out[h] = (ch / p0 - 1.0, min(0.0, lo / p0 - 1.0))
    return out


def _me_ret(me: dict, m: str) -> dict:
    """產業月底值 → {RET_H_M 每一期: (報酬, 中途最多跌)}（第 m 個月底進場；走完的期間才有）。"""
    v0 = me.get(m)
    out = {}
    if not v0:
        return out
    fut = []
    for j in range(1, max(S.RET_H_M) + 1):
        v = me.get(_months_add(m, j))
        if v is None:
            break
        fut.append(v)
        if j in S.RET_H_M:
            out[j] = (fut[-1] / v0 - 1.0, min(0.0, min(fut) / v0 - 1.0))
    return out


def ind_rows(group: str, I: dict, T: dict, last: str | None = None, bases: dict | None = None) -> list[dict]:
    """一組產業（bubind 的輸入）：每個產業各自分段、全部合併。報酬（VER 5）＝月底進場、RET_H_M 個月。"""
    from . import bubind as BI
    from . import bubindspec as BIS
    pan = []
    for code, Sx in I["S"].items():
        C = BI.conditions(Sx, T)
        rows = C["rows"]
        j0 = next((j for j, r in enumerate(rows) if r["P1"] is not None and r["P2"] is not None), None)
        if j0 is None:
            continue
        pan.append((code, Sx["me"], rows[j0:]))
    months_all = sorted({r["d"] for _, _, rows in pan for r in rows})
    if not months_all:
        return []
    zl = last or months_all[-1]
    r0m = _months_add(zl, -12 * S.RECENT_YEARS)
    out = []
    bk = f"ind:{group}:base"
    if bases is not None and bk not in bases:
        bases[bk] = _ret_groups([[_me_ret(me, r["d"])] for _, me, rows in pan for r in rows
                                 if r.get("L") is not None and r["d"] in me], S.RET_H_M)
    for k in S.IND_SIGNALS:
        lv = int(k[1])
        occ, base_u, base_w, b10u, b10w, base_d = [], [], [], [], [], []
        rgroups = []
        seqs = []                                     # 打亂日子測試用：每個產業（狀態, 偏多, 警示）
        for code, me, rows in pan:
            seq = []
            for r in rows:
                m = r["d"]
                if r.get("L") is None or m not in me:
                    continue
                v0 = me[m]
                fut = [me.get(_months_add(m, j)) for j in range(1, S.H_IND_M + 1)]
                if not v0 or any(v is None for v in fut):
                    u = w = dd = rr = None
                else:
                    u = 1.0 if fut[-1] > v0 else 0.0
                    dd = mdd_path([v0] + fut)                 # VER 3：第 m～m＋12 個月底的最大回撤
                    w = 1.0 if dd >= S.WARN_LONG else 0.0
                    rr = fut[-1] / v0 - 1.0
                seq.append((m, r["L"] >= lv, u, w, dd, rr))
                if u is not None:
                    base_u.append(u)
                    base_w.append(w)
                    base_d.append(dd)
                    if m >= r0m:
                        b10u.append(u)
                        b10w.append(w)
            seqs.append((np.array([s[1] for s in seq], dtype=bool),
                         np.array([np.nan if s[2] is None else s[2] for s in seq], dtype=float),
                         np.array([np.nan if s[3] is None else s[3] for s in seq], dtype=float)))
            pos = [i for i, s in enumerate(seq) if s[1]]
            for ep in episodes(pos, 1):
                us = [seq[i][2] for i in ep if seq[i][2] is not None]
                ws = [seq[i][3] for i in ep if seq[i][3] is not None]
                ds = [seq[i][4] for i in ep if seq[i][4] is not None]
                rs = [seq[i][5] for i in ep if seq[i][5] is not None]
                if us:
                    occ.append([seq[ep[0]][0], seq[ep[-1]][0], len(ep), float(np.mean(us)), float(np.mean(ws)), code,
                                float(np.mean(ds)), float(np.mean(rs))])
                rgroups.append([_me_ret(me, seq[i][0]) for i in ep])
        occ.sort(key=lambda o: (o[0], o[5]))
        dirs = {}
        for j, (d, bs, b10) in enumerate((("up", base_u, b10u), ("warn", base_w, b10w))):
            ys = [o[3 + j] for o in occ]
            ys10 = [o[3 + j] for o in occ if o[0] >= r0m]
            dirs[d] = {"n": len(ys), "hit": _mean(ys), "base": _mean(bs), "n10": len(ys10), "hit10": _mean(ys10),
                       "base10": _mean(b10)}
        # 打亂日子測試（VER 9）：只對過門檻的方向算（其他方向的判定和 p 無關）
        need = {d: st["hit"] for d, st in dirs.items()
                if LK.passes(st["n"], st["hit"], st["base"], st["n10"], st["hit10"], st["base10"], d)}
        pv = LK.ind_p(f"ind:{group}:{k}", seqs, need) if need else {}
        for d, st in dirs.items():
            st["p"] = pv.get(d)
            judge(st, d)
        dirs["warn"].update(mdd=_median([o[6] for o in occ]), mdd_base=_median(base_d))
        tr, ds = best(dirs)
        gname = BIS.GROUP_NAMES[group] if hasattr(BIS, "GROUP_NAMES") else group
        out.append({"id": f"ind:{group}:{k}", "mk": "us" if group in ("ff", "us") else "tw", "cat": "ind", "grp": group,
                    "var": k, "vn": gname, "sig": k, "name": f"{gname}・{S.BUB_NAMES[k]}", "kind": "state",
                    "H": S.H_IND_M, "monthly": True, "th": S.WARN_LONG, "a": occ[0][0] if occ else None, "z": zl,
                    "up": dirs["up"], "warn": dirs["warn"], "tier": tr, "dir": ds, "occ": occ,
                    "ret": {**_ret_groups(rgroups, S.RET_H_M), "bk": bk, "hm": True}})
    return out


def ind_all(bases: dict | None = None) -> list[dict]:
    from . import bubble as BU
    from . import bubind as BI
    T = BU.load_cv_table()
    if not T:
        return []
    L = BU.us_inputs(BU.load_us())["L"]
    out = []
    for g, fn in (("ff", lambda: BI.ff_inputs(L)), ("us", lambda: BI.us_inputs(L)), ("tw", BI.tw_inputs)):
        I = fn()
        if I:
            out += ind_rows(g, I, T, bases=bases)
    return out


# ── 研究 ─────────────────────────────────────────────────────────────────────

def market(F: dict, bases: dict | None = None) -> list[dict]:
    Yc: dict = {"bases": {} if bases is None else bases}
    rows = [evaluate(F, sd, Yc) for sd in signals(F)]
    return rows + buy_rows(F, Yc["bases"])


def _r(x):
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(x) or math.isinf(x) else float(f"{float(x):.4g}")
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, dict):
        return {a: _r(b) for a, b in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(b) for b in x]
    return x


def luck_summary(rows: list[dict]) -> dict:
    """運氣會產生幾個 ★（sigspec 第 3.5 節，只呈現）：市場層級訊號 → {市場: {方向: [實際 ★, 運氣會產生的 ★]}}。
    會把列裡的 _luck 拿掉。"""
    out: dict = {}
    for r in rows:
        lk = r.pop("_luck", None)
        if lk is None:
            continue
        m = out.setdefault(r["mk"], {d: [0, 0.0] for d in ("up", "warn")})
        for d in ("up", "warn"):
            m[d][0] += (r.get(d) or {}).get("tier") == "good"
            m[d][1] += lk[d]
    return out


def research(F: dict | None = None, with_ind: bool = True) -> dict:
    F = F if F is not None else frames()
    rows, bases = [], {}
    for mk in S.MARKETS:
        if mk in F:
            rows += market(F[mk], bases)
    luck = luck_summary(rows)
    if with_ind:
        rows += ind_all(bases)
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": {mk: F[mk]["cal"][-1] for mk in F}, "rows": _r(rows), "bases": _r(bases), "luck": _r(luck)}


def save_research(R: dict) -> None:
    RESEARCH.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load_research() -> dict | None:
    try:
        R = json.loads(RESEARCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None


_RCACHE: dict = {}


def research_rows() -> list[dict]:
    """研究檔的列（同一個程序裡只讀一次：五個景氣頁與訊號總覽共用）。"""
    if "rows" not in _RCACHE:
        R = load_research() or {}
        _RCACHE["rows"] = R.get("rows") or []
        _RCACHE["bases"] = R.get("bases") or {}
    return _RCACHE["rows"]


def research_bases() -> dict:
    """研究檔的「平常」報酬（ret_base 的鍵 → ret_stats），景氣頁情境表用。"""
    research_rows()
    return _RCACHE.get("bases") or {}


def today_for(now: dict | None) -> dict | None:
    """景氣頁「今天的重點」：now＝now_for_B 的結果；研究檔沒有就回 None。"""
    rows = research_rows()
    if not now or not rows:
        return None
    return {"mk": now["mk"], "d": now["d"], **board(rows, now["on"], now["mk"], now.get("acts"))}


# ── 現在有沒有效（每天建頁） ───────────────────────────────────────────────────

def activity(sd: dict, T: int) -> np.ndarray:
    """過去「出現」的日子（sigspec 第 5 節 ①b，同類合併用）：狀態型＝樣本日裡在狀態中的日子；事件型＝每一次出現那天起 H 個交易日。"""
    a = np.zeros(T, dtype=bool)
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if sd["kind"] == "state":
        a[samp[np.asarray(sd["state"], dtype=bool)]] = True
    else:
        for t in sd["days"]:
            a[int(t):int(t) + sd["H"]] = True
    return a


def now_market(F: dict, acts: dict | None = None) -> dict:
    """一個市場 → {訊號 id: {"since": 開始日, "n": 已經幾天（月資料＝幾個月）, "left": 事件型剩幾天}}，只列現在有效的。
    狀態型＝資料最後一天在狀態中（月資料＝最後一個過完的月份）；事件型＝最近一次出現在最後 H 個交易日內；
    買點＝目前一段大跌（bottom.now 進行中）之後已經出現。acts＝給了就順便填現在有效的訊號過去出現的日子（同類合併用）。"""
    cal = F["cal"]
    T = len(cal)
    out: dict = {}
    for sd in signals(F):
        samp = np.asarray(sd["samp"], dtype=np.int64)
        if sd["kind"] == "state":
            st = np.asarray(sd["state"], dtype=bool)
            if not len(samp) or not st[-1]:
                continue
            if not sd.get("monthly") and samp[-1] != T - 1:
                continue
            gap = 1 if sd.get("monthly") else S.EP_GAP
            ep = episodes([i for i in range(len(samp)) if st[i]], gap)[-1]
            out[sd["id"]] = {"since": cal[int(samp[ep[0]])], "n": len(ep)}
        else:
            ds = [t for t in sd["days"] if t >= (samp[0] if len(samp) else 0)]
            if ds and T - 1 - ds[-1] < sd["H"]:
                out[sd["id"]] = {"since": cal[ds[-1]], "n": T - 1 - ds[-1], "left": sd["H"] - (T - 1 - ds[-1])}
        if acts is not None and sd["id"] in out:
            acts[sd["id"]] = activity(sd, T)
    I = F.get("IB")
    if I:
        from . import bottom as BO
        Nw = BO.now(I)
        for a in Nw.get("active") or []:
            evs = (a["ev"],) + ((a["also"],) if a.get("also") else ())
            sigs = {"W10": a.get("w10") or {}, **(a.get("sig") or {})}
            for k, v in sigs.items():
                if v.get("st") == "on":
                    for ev in evs:
                        out[f"{F['mk']}:buy:{ev}:{k}"] = {"since": v["d"], "event": a["t"]}
    return out


def edge(st: dict | None) -> float | None:
    if not st or st.get("hit") is None or st.get("base") is None:
        return None
    return st["hit"] - st["base"]


def today(rows: list[dict], on: dict, mk: str) -> dict:
    """訊號總覽「今天有效的好訊號」（sigspec 第 5 節）：這個市場現在有效的 ★，同一個變數只留差最大的一種，依差排序、最多 TODAY_MAX 列；
    沒有 ★ 就沒有（VER 9）。→ {"good": [...]}（每列＝研究列＋現在的狀態＋方向＋差）。"""
    def pick(tr: str) -> list[dict]:
        best_by: dict = {}
        for r in rows:
            if r.get("mk") != mk or r["tier"] != tr or r["id"] not in on:
                continue
            for d in r["dir"]:
                e = edge(r.get(d))
                if e is None:
                    continue
                key = (r["cat"], r["var"])
                if key not in best_by or e > best_by[key]["edge"]:
                    best_by[key] = {**r, "d": d, "edge": e, "now": on[r["id"]]}
        return sorted(best_by.values(), key=lambda x: (-x["edge"], x["id"]))
    return {"good": pick("good")[:S.TODAY_MAX]}


def horizon(r: dict) -> str:
    """溫度計分哪一支（sigspec 第 5 節）：short／mid／long。"""
    if r["cat"] == "buy":
        return "mid"
    if r["cat"] == "ind":
        return "long"
    H = r.get("H") or 0
    return "short" if H <= S.H_TECH else "mid" if H <= S.H_CRASH else "long"


def item_key(r: dict) -> tuple:
    """「同一個項目」：景氣項目的水準（heat）與邊際變化（deriv）算同一個項目；其他依類別＋變數。"""
    return ("item", r["var"]) if r["cat"] in ("heat", "deriv") else (r["cat"], r["var"])


def jaccard(a: np.ndarray | None, b: np.ndarray | None) -> float:
    """過去一起出現的日子 ÷ 任一個出現的日子。"""
    if a is None or b is None or len(a) != len(b):
        return 0.0
    u = int((a | b).sum())
    return int((a & b).sum()) / u if u else 0.0


def families(items: list[dict], acts: dict | None) -> list[dict]:
    """同類合併（sigspec 第 5 節 ①b，VER 8 寫定、VER 9 照用）：同一支溫度計、同一邊，過去一起出現的比例 ≥ FAMILY_J 的併成一類
    （單一連結）；大跌後買點同一個市場算一類。→ 每一類的領頭（差最大），其他放在 "fam"。"""
    acts = acts or {}
    groups: dict = {}
    for x in items:
        groups.setdefault((x["hz"], x["side"]), []).append(x)
    out = []
    for xs in groups.values():
        parent = list(range(len(xs)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                a, b = xs[i], xs[j]
                if (a["cat"] == "buy" and b["cat"] == "buy") or jaccard(acts.get(a["id"]), acts.get(b["id"])) >= S.FAMILY_J:
                    parent[find(i)] = find(j)
        cl: dict = {}
        for i, x in enumerate(xs):
            cl.setdefault(find(i), []).append(x)
        for ms in cl.values():
            ms.sort(key=lambda x: (-x["edge"], x["id"]))
            out.append({**ms[0], "fam": ms[1:]})
    out.sort(key=lambda x: (-x["edge"], x["id"]))
    return out


def board(rows: list[dict], on: dict, mk: str, acts: dict | None = None) -> dict:
    """景氣頁「今天的重點」（sigspec 第 5 節，2026-10-20 起）：現在有效的 ★（VER 9；● 不列），偏多（含買點）與警示兩個方向
    各自看自己的判定（VER 3）；同一個項目在同一支溫度計、同一邊只留一種（差最大）；兩邊都成立的標 both（「震盪」）。
    同類合併（families；acts＝現在有效的訊號過去出現的日子，now_market 填），溫度計一類只算一次（THERMO_W）。
    → {"up": [...], "warn": [...], "thermo": [{"k", "name", "h", "n": {side: {tier: 類數}}, "w": {side: 分}, "share", "lean"}]}"""
    rank = {"good": 1}
    best: dict = {}
    for r in rows:
        if r.get("mk") != mk or r["id"] not in on:
            continue
        for d in (("buy",) if r["cat"] == "buy" else ("up", "warn")):
            st = r.get(d)
            if not st or st.get("tier") not in rank:
                continue
            e = edge(st)
            if e is None:
                continue
            side = "warn" if d == "warn" else "up"
            key = (item_key(r), horizon(r), side)
            k = (rank[st["tier"]], e)
            if key not in best or k > best[key][0]:
                best[key] = (k, {**r, "tier": st["tier"], "d": d, "edge": e, "now": on[r["id"]], "side": side,
                                 "hz": horizon(r)})
    sides: dict = {}
    for (ik, hz, side) in best:
        sides.setdefault((ik, hz), set()).add(side)
    items = []
    for (ik, hz, side), (_, x) in best.items():
        x["both"] = len(sides[(ik, hz)]) == 2
        items.append(x)
    items = families(items, acts)
    out: dict = {s: [x for x in items if x["side"] == s] for s in ("up", "warn")}
    th = []
    for k, name, h in S.THERMO_HZ:
        n = {s: {t: sum(1 for x in out[s] if x["hz"] == k and x["tier"] == t) for t in S.THERMO_W} for s in out}
        w = {s: sum(S.THERMO_W[t] * c for t, c in n[s].items()) for s in n}
        tot = w["up"] + w["warn"]
        share = w["up"] / tot if tot else None
        lean = None if share is None else "up" if share >= S.THERMO_LEAN else "warn" if share <= 1 - S.THERMO_LEAN else "even"
        th.append({"k": k, "name": name, "h": h, "n": n, "w": w, "share": share, "lean": lean})
    out["thermo"] = th
    return out


# ── 每天建頁：景氣頁的 B → 這個市場現在有沒有效（存在程序裡給訊號總覽沿用） ──────────

NOW: dict = {}                                       # {市場: {"d": 資料最後一天, "on": now_market(...)}}


def frame_from_B(B: dict) -> dict | None:
    """景氣頁的 B（heatcalc.build／heatcalc_us.build；美股要在 heatspec.use(該指數) 裡呼叫）→ frame。
    做法同 bottompage.state：泡沫用 bubble.market_for、台股融資 ÷ 市值用 crash.tw_inputs 現算。"""
    from . import bottom as BO
    from . import bottomspec as BS
    from . import bubble as BU
    from . import crash as CR
    from . import heatdata as HD
    mk = B.get("idx") or "tw"
    if mk not in S.MARKETS or not B.get("cal") or B.get("D") is None:
        return None
    BX = {mk: BU.market_for(mk, B["D"])}
    if mk == "tw":
        D = dict(B["D"])
        for n in ("twcap", "twmgn", "taiex90"):
            if n not in D:
                D[n] = HD.load(n)
        D["_tsmc"] = CR._tsmc_month(None)
        I = CR.tw_inputs(D=D, B=B, BX=BX)
        IB = BO.inputs_tw(B=B, IT=I, BX=BX)
    else:
        I = CR.us_inputs(mk, Bu=B, BX=BX)
        vol = HD.load(f"us_vol_{mk}") if "C7" in BS.SIG_MK[mk] else None
        IB = BO.inputs_us(mk, B, I, vol, BX)
    if not len(I["cal"]):
        return None
    return frame(mk, B, I, IB, BX)


def crash_now(F: dict) -> dict:
    """大跌風險項目（台股 W1～W4、美股 VOL）的現在：最後一個有值的 0～100、區、日期、近 53 個週末的 0～100
    （訊號總覽依指標整理的「現在」與小走勢圖，docs/lab_sigview_plan.md；景氣頁沒有這幾項）。"""
    from . import heatspec as HS
    out = {}
    we = list(F["we"])[-53:]
    for v in F["cvars"]:
        x = np.asarray(v["x"], dtype=float)
        ok = np.nonzero(~np.isnan(x))[0]
        if not len(ok):
            continue
        i = int(ok[-1])
        out[v["key"]] = {"h": round(float(x[i]), 1), "band": HS.band(float(x[i])), "d": F["cal"][i],
                         "sp": [None if np.isnan(x[j]) else int(math.floor(x[j] + 0.5)) for j in we]}
    for v in F.get("ivars") or []:                     # 法人買賣超（景氣頁沒有這幾項）
        x = np.asarray(v["x"], dtype=float)
        ok = np.nonzero(~np.isnan(x))[0]
        if not len(ok):
            continue
        i = int(ok[-1])
        seg = np.asarray(v["amt"], dtype=float)[max(0, i - v["w"] + 1):i + 1]
        txt = f"{seg.sum() / 1e8:+,.1f} 億" if len(seg) == v["w"] and not np.isnan(seg).any() else ""
        out[v["key"]] = {"h": round(float(x[i]), 1), "band": HS.band(float(x[i])), "d": F["cal"][i], "v": txt, "hot": -1,
                         "sp": [None if np.isnan(x[j]) else int(math.floor(x[j] + 0.5)) for j in we]}
    return out


def _sim_now(F: dict) -> dict | None:
    """景氣頁「現在的情境」：相似的日子（simdays.estimate，sigspec 第 4.12 節）；算不出來回 None、不擋其他部分。"""
    try:
        from . import simdays
        return simdays.estimate(F)
    except Exception as e:                            # noqa: BLE001
        print(f"[訊號總覽] 相似的日子算不出來：{type(e).__name__}: {e}")
        return None


def now_for_B(B: dict) -> dict | None:
    """景氣頁建頁時呼叫：算這個市場現在有效的訊號，存進 NOW（訊號總覽沿用）。失敗回 None、不擋景氣頁。"""
    try:
        F = frame_from_B(B)
        if F is None:
            return None
        acts: dict = {}
        on = now_market(F, acts)
        NOW[F["mk"]] = {"mk": F["mk"], "d": F["cal"][-1], "on": on, "acts": acts, "cv": crash_now(F), "sim": _sim_now(F)}
        return NOW[F["mk"]]
    except Exception as e:                            # noqa: BLE001
        print(f"[訊號總覽] 現在的狀態算不出來：{type(e).__name__}: {e}")
        return None


# ── 個股訊號與策略（籌碼雷達建頁時算，寫 data/lab/sig_stock.json 給訊號總覽） ─────────────

STOCK = ROOT / "data" / "lab" / "sig_stock.json"


def _stock_dd(Sx: dict, t: int, H: int) -> float | None:
    """第 t＋1 天開盤價（沒有就用收盤）與第 t＋1～t＋H 天收盤的最大回撤（sigspec 第 4.8 節，VER 3）。"""
    o1 = Sx["o"][t + 1] or Sx["c"][t + 1]
    return mdd_path([o1] + list(Sx["c"][t + 1:t + H + 1]))


def stock_signal_rows(D, sig_hist: dict, idx: list, io: list) -> list[dict]:
    """籌碼雷達 8 種訊號（sigspec 第 4.8 節）：同一檔 DEDUP 日內重複只算一次（同 backtest.signal_stats）；
    t＋1 開盤買、第 t＋H_STOCK 天收盤賣。偏多：扣成本後賺錢，平常＝同一批窗口加權指數上漲。
    警示（集體撤退，VER 3）：之後 H_STOCK 天的最大回撤 ≥ STOCK_MDD，平常＝訊號第一次出現起、所有有訊號紀錄的股票
    每一個窗口完整的日子（窗口完整＝和 backtest._ret 同一個條件）。
    occ＝[日期, 代號, 中了, 平常那一邊（警示＝None）, 報酬%, 最大回撤%]。"""
    from . import analyze as AN
    from . import backtest as BT
    H = S.H_STOCK
    cal = list(D.cal)
    T = len(cal)
    cache: dict = {}

    def ser(code):
        if code not in cache:
            cache[code] = D.series(code)
        return cache[code]

    out = []
    rbase: dict = {}
    for k, (nm, desc) in AN.SIG_DEF.items():
        d = "warn" if k in S.STOCK_WARN else "up"
        occ = []
        live = []
        rg = []
        for code, hist in sig_hist.items():
            fired = [i for i, day in enumerate(hist) if k in day]
            if not fired:
                continue
            Sx = ser(code)
            last = -999
            for t in fired:
                if t - last <= BT.DEDUP:
                    last = t
                    continue
                last = t
                if t == T - 1:
                    live.append(code)
                rg.append([_stock_ret(Sx, t)])
                r = BT._ret(Sx, idx, t, H, io)
                if not r:
                    continue
                dd = _stock_dd(Sx, t, H)
                if d == "up":
                    hit = r["r"] > 0
                    bh = int(r["r"] - r["x"] > 0)
                else:
                    hit = dd is not None and dd >= S.STOCK_MDD
                    bh = None
                occ.append([cal[t], code, int(hit), bh, round(100 * r["r"], 2), None if dd is None else round(100 * dd, 2)])
        occ.sort(key=lambda o: (o[0], o[1]))
        wb = None
        if d == "up":
            base = _mean([o[3] for o in occ])
            bmed = None
        else:
            wb = _stock_warn_arrays(D, sig_hist, idx, io, cal.index(occ[0][0]) if occ else None, H, ser)
            base, bmed = (wb["base"], wb["med"]) if wb else (None, None)
        st = {"n": len(occ), "hit": _mean([o[2] for o in occ]), "base": base,
              "n10": None, "hit10": None, "base10": None}
        if d == "warn":
            st.update(mdd=_median([None if o[5] is None else o[5] / 100 for o in occ]), mdd_base=bmed)
        # 打亂日子測試（VER 9，sigspec 第 3.5 節）：只對過門檻的算
        if LK.passes(st["n"], st["hit"], st["base"], None, None, None, d, recent=False):
            if d == "up":
                st["p"] = LK.sign_p(sum(1 for o in occ if o[2] and not o[3]), sum(1 for o in occ if o[3] and not o[2]))
            elif wb:
                fired = {c: [i for i, day in enumerate(h) if k in day] for c, h in sig_hist.items()}
                fired = {c: v for c, v in fired.items() if v}
                st["p"] = LK.shift_p(st["hit"], lambda o: LK.stock_hit(fired, wb["hit"], wb["t0"], wb["L"], BT.DEDUP, o),
                                     wb["L"], f"stk:sig:{k}")
        judge(st, d, recent=False)
        t0 = min((min(i for i, day in enumerate(h) if k in day) for h in sig_hist.values() if any(k in day for day in h)),
                 default=None)
        ret = _ret_groups(rg, S.RET_H, S.PATH_D)
        if t0 is not None:
            if t0 not in rbase:
                rbase[t0] = _ret_groups([[_stock_ret(ser(c), t)] for c in sig_hist for t in range(t0, T - 1)],
                                        S.RET_H, S.PATH_D)
            ret["base"] = rbase[t0]
        out.append({"id": f"stk:sig:{k}", "mk": "stk", "cat": "stock", "grp": "stock", "var": k, "vn": nm, "sig": k,
                    "name": nm, "desc": desc, "kind": "event", "H": H, "th": S.STOCK_MDD if d == "warn" else None,
                    d: st, "tier": st["tier"], "dir": [d],
                    "a": occ[0][0] if occ else None, "z": cal[-1], "occ": occ, "live": sorted(set(live)),
                    "avg": _mean([o[4] for o in occ]), "ret": ret})
    return out


def _stock_warn_arrays(D, sig_hist: dict, idx: list, io: list, t0: int | None, H: int, ser) -> dict | None:
    """個股警示的平常：第 t0 天起、所有有訊號紀錄的股票、每一個窗口完整的日子，最大回撤 ≥ STOCK_MDD 的比例與最大回撤中位數；
    另回每一檔第 t0 天起每一天中了沒有（1／0／nan＝窗口不完整），打亂日子測試用（L＝T − H − t0 天）。"""
    from . import backtest as BT
    if t0 is None:
        return None
    hits, dds = [], []
    T = len(D.cal)
    L = T - H - t0
    if L <= 0:
        return None
    per = {}
    for code in sig_hist:
        Sx = ser(code)
        h = np.full(L, np.nan)
        for t in range(t0, T - H):
            if not BT._ret(Sx, idx, t, H, io):
                continue
            dd = _stock_dd(Sx, t, H)
            if dd is None:
                continue
            dds.append(dd)
            h[t - t0] = 1.0 if dd >= S.STOCK_MDD else 0.0
            hits.append(h[t - t0])
        per[code] = h
    return {"base": _mean(hits), "med": _median(dds), "hit": per, "t0": t0, "L": L}


def _strat_tier(pay: dict, n: int) -> str:
    if n < S.STRAT_N_MIN:
        return "few"
    if pay.get("ok"):
        return "good"
    return "ref" if (pay.get("avg") or 0) > 0 else "none"


def strat_pay(v: dict) -> tuple[dict, dict]:
    """逐筆交易（advice.trade_book 的一條）→ (報酬型態 bt3.payoff, 命中率統計 st)。只算已出場、有報酬與持有天數的。"""
    from . import bt3
    from . import trades as TR
    I = {c: i for i, c in enumerate(TR.TR_COLS)}
    tr = ((v.get("res") or {}).get("tr")) or []
    rows = [r for r in tr if len(r) > I["hd"] and r[I["st"]] == "c" and r[I["r"]] is not None and r[I["hd"]]]
    pay = bt3.payoff([{"r": r[I["r"]], "hd": r[I["hd"]]} for r in rows])
    mk = [r[I["mk"]] for r in rows if r[I["mk"]] is not None]
    st = {"n": pay.get("n", 0), "hit": None if not pay.get("n") else pay["win"] / 100.0,
          "base": _mean([1.0 if m > 0 else 0.0 for m in mk]), "n10": None, "hit10": None, "base10": None}
    st["tier"] = _strat_tier(pay, st["n"])
    return pay, st


def strat_judge(tbook: dict) -> dict:
    """機會頁的推薦判定（sigspec 第 4.9 節，VER 2）：{策略鍵: {tier, n, win, m, avg, ratio, path, few}}。
    tbook＝advice.trade_book 的結果；和訊號總覽的個股策略列同一套算法（strat_pay）。"""
    out = {}
    for k, v in (tbook or {}).items():
        pay, st = strat_pay(v)
        out[k] = {"tier": st["tier"], "n": st["n"], "few": 0 < st["n"] < S.STRAT_FEW,
                  **{x: pay.get(x) for x in ("win", "m", "avg", "ratio", "path")}}
    return out


def strat_rows(adv: dict, bt3r: dict | None = None) -> list[dict]:
    """個股策略（sigspec 第 4.9 節）：有逐筆紀錄的（機會頁那幾條）用全部已出場交易算報酬型態；
    回測方法 v3 其他版本（整組）沒有逐筆紀錄，用研究檔的樣本內、樣本外報酬型態（兩段都過才 ★）。"""
    out = []
    names = {g["k"]: g for g in (adv.get("grades3") or [])}
    for k, v in (adv.get("trades") or {}).items():
        pay, st = strat_pay(v)
        g = names.get(k) or {}
        tr_ = st["tier"]
        out.append({"id": f"stk:strat:{k}", "mk": "stk", "cat": "strat", "grp": "strat", "var": k,
                    "vn": g.get("name") or k, "sig": k, "name": g.get("name") or k, "desc": g.get("kind"),
                    "kind": "trade", "H": None, "up": st, "tier": tr_, "dir": ["up"], "pay": pay, "old": g.get("grade"),
                    "unit": v.get("unit"), "few": 0 < st["n"] < S.STRAT_FEW, "a": None, "z": None, "occ": []})
    for row in ((bt3r or {}).get("rows") or []):
        k = row.get("k")
        if not k or k in names:
            continue
        ins, oos = row.get("ins") or {}, row.get("oos") or {}
        n = (ins.get("n") or 0) + (oos.get("n") or 0)
        ok = bool(ins.get("pay_ok")) and (not oos.get("n") or bool(oos.get("pay_ok")))
        avg = _mean([x for x in ((ins.get("m"), oos.get("m")) if oos.get("n") else (ins.get("m"),)) if x is not None])
        tr_ = "few" if n < S.STRAT_N_MIN else ("good" if ok else ("ref" if (avg or 0) > 0 else "none"))
        bname = {"L": "大型股", "M": "中型股"}.get(row.get("b"), "")
        nm = f"{row.get('name')}（{bname}・整組）"
        win = _mean([x for x in (ins.get("win"), oos.get("win")) if x is not None])
        st = {"n": n, "hit": None if win is None else win / 100.0, "base": None, "n10": None, "hit10": None,
              "base10": None, "tier": tr_}
        out.append({"id": f"stk:strat:{k}", "mk": "stk", "cat": "strat", "grp": "strat", "var": k, "vn": nm, "sig": k,
                    "name": nm, "desc": "回測方法 v3 研究版本（同一批股票全部買）", "kind": "trade", "H": None, "up": st,
                    "tier": tr_, "dir": ["up"], "old": row.get("grade"), "unit": row.get("unit"),
                    "pay": {"ins": {x: ins.get(x) for x in ("n", "win", "ratio", "m", "pay_ok")},
                            "oos": {x: oos.get(x) for x in ("n", "win", "ratio", "m", "pay_ok")}},
                    "a": ins.get("d0"), "z": oos.get("d1") or ins.get("d1"), "occ": []})
    return out


def stock_rows(data: dict, ctx: dict) -> list[dict] | None:
    """個股訊號＋策略的列；任一個算不出來回 None（不拿殘缺的資料蓋掉前一版）。"""
    if ctx.get("D") is None or not ((data.get("adv") or {}).get("trades")):
        return None
    rows = []
    try:
        rows += stock_signal_rows(ctx["D"], ctx["sig_hist"], ctx["taiex"], ctx["D"].taiex_open())
    except Exception as e:                            # noqa: BLE001
        print(f"[訊號總覽] 個股訊號算不出來：{type(e).__name__}: {e}")
        return None
    try:
        bt3r = json.loads((ROOT / "data" / "lab" / "bt3_research.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bt3r = None
    try:
        rows += strat_rows(data.get("adv") or {}, bt3r)
    except Exception as e:                            # noqa: BLE001
        print(f"[訊號總覽] 個股策略算不出來：{type(e).__name__}: {e}")
        return None
    return rows


def write_stock(data: dict, ctx: dict, path: Path | None = None, rows: list[dict] | None = None) -> bool:
    """籌碼雷達建頁後呼叫（page.build）：個股訊號＋策略 → data/lab/sig_stock.json（內容沒變不改寫）。
    個股訊號或機會頁的策略任一個算不出來就不寫（不拿殘缺的資料蓋掉前一版）。rows＝已經算好的 stock_rows。"""
    path = path or STOCK
    rows = rows if rows is not None else stock_rows(data, ctx)
    if not rows:
        return False
    txt = json.dumps({"ver": S.VER, "d": list(ctx["D"].cal)[-1] if ctx.get("D") is not None else None,
                      "rows": _r(rows)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == txt:
        return False
    path.write_text(txt, encoding="utf-8")
    return True


def stock_brief(rows: list[dict] | None) -> dict:
    """籌碼頁「今日訊號」、後台「訊號成績」用（docs/lab_signal_plan.md 第 6.3 節）：{訊號鍵: [判定, 方向, 次數, 命中率%, 平常%]}。"""
    out = {}
    for r in rows or []:
        if r.get("cat") != "stock":
            continue
        d = r["dir"][0]
        st = r[d]
        pc = lambda x: None if x is None else round(100 * x, 1)
        out[r["var"]] = [st["tier"], d, st["n"], pc(st["hit"]), pc(st["base"])]
    return out


def load_stock() -> dict | None:
    try:
        R = json.loads(STOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None
