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

from . import robust as RB
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


def ret_cell(r: np.ndarray, a: np.ndarray, w: np.ndarray, n: int, occ=None) -> list | None:
    """→ [次數, 平均, 25%, 中位數, 75%, 上漲比例, 中途最多跌中位數, 中途最多跌最差 10%, 最差一次, 排除極端, 去掉最好一次]。
    最後兩個（VER 17，第 4.11 節）用 occ＝每一次（狀態型＝每一段的平均）的報酬；沒給＝r 的每一個值各算一次（每一天等權）。"""
    if n <= 0 or not len(r):
        return None
    W = float(w.sum())
    o = r if occ is None else occ
    return [int(n), float((r * w).sum() / W), *(wquant(r, w, q) for q in S.RET_Q), float(w[r > 0].sum() / W),
            wquant(a, w, 0.5), wquant(a, w, S.MAE_Q), float(a.min()), RB.trim_mean(o), RB.lbo_mean(o)]


def ret_stats(groups: list, RA: dict) -> dict:
    """groups＝每一次在 RA 陣列裡的索引（事件：一天；狀態：一段的樣本日）；每一段一樣重（段內窗口完整的日子平分）。
    → {"s": RET_H 每一期一格（ret_cell）, "p": PATH_D 每一天 [25%, 中位數, 75%]}。"""
    gs = [np.asarray(g, dtype=np.int64) for g in groups]
    gs = [g for g in gs if len(g)]

    def pick(Y, Z=None):
        rs, zs, ws, ms, n = [], [], [], [], 0
        for g in gs:
            m = np.isfinite(Y[g]) if Z is None else (np.isfinite(Y[g]) & np.isfinite(Z[g]))
            k = g[m]
            if not len(k):
                continue
            n += 1
            rs.append(Y[k])
            ws.append(np.full(len(k), 1.0 / len(k)))
            ms.append(float(Y[k].mean()))                 # VER 17：每一段的平均（排除極端、去掉最好一次的單位）
            if Z is not None:
                zs.append(Z[k])
        if not n:
            return None
        return (np.concatenate(rs), np.concatenate(zs) if Z is not None else None, np.concatenate(ws), n, ms)

    out_s = []
    for h in RA["hs"]:
        P = pick(RA["R"][h], RA["A"][h])
        out_s.append(None if P is None else ret_cell(P[0], P[1], P[2], P[3], P[4]))
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


def skipped(days, ok: set, H: int, Yu: np.ndarray, cal: list[str]) -> list[list]:
    """事件型「出現了但沒算進次數」的日子（訊號總覽「最近幾次」與走勢圖標灰，docs/lab_audit_plan.md 第 3.4 節；只呈現）：
    → [[日期, 原因, 算進去的那一次的日期]]：原因 "d"＝和上一次算進去的相隔不到 H 個交易日（之後的漲跌和那一次重疊，算同一次）、
    "i"＝之後 H 個交易日還沒走完。輸入沒有值的日子（不在 ok）不列。"""
    kept = dedupe([t for t in days if t in ok], H)
    ks = set(kept)
    out = []
    for t in sorted(int(x) for x in days if int(x) in ok):
        if t in ks:
            if np.isnan(Yu[t]):
                out.append([cal[t], "i", None])
        else:
            j = bisect.bisect_right(kept, t) - 1
            out.append([cal[t], "d", cal[kept[j]] if j >= 0 else None])
    return out


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


def episodes(pos: list[int], gap: int, brk=None) -> list[list[int]]:
    """pos＝狀態中的樣本在樣本序列裡的位置（遞增）→ 每一段的位置；中斷的樣本數 < gap 算同一段。
    brk（sigspec VER 20）＝每個樣本是不是相反的極端（和樣本序列同長度）：中斷的樣本裡有一個是，就切成兩段。"""
    cb = None if brk is None else np.concatenate([[0], np.cumsum(np.asarray(brk, dtype=np.int64))])
    out: list[list[int]] = []
    for p in pos:
        if out and p - out[-1][-1] - 1 < gap and (cb is None or cb[p] == cb[out[-1][-1] + 1]):
            out[-1].append(p)
        else:
            out.append([p])
    return out


def exp_end(sd: dict, days, H: int) -> np.ndarray:
    """事件型每一次出現 t 的「有效到」（不含）：min(t＋H, 之後第一個相反讀數的那天)（sigspec VER 20 第 5 節；
    sd["exp"]＝同一個項目相反讀數的日子，沒有就只看 H）。"""
    D = np.asarray(days, dtype=np.int64)
    end = D + int(H)
    ex = sd.get("exp")
    if ex is not None and len(ex) and len(D):
        ex = np.asarray(ex, dtype=np.int64)
        j = np.searchsorted(ex, D, side="right")
        has = j < len(ex)
        nxt = np.where(has, ex[np.minimum(j, len(ex) - 1)], end)
        end = np.minimum(end, nxt)
    return end


def st_stat(state: np.ndarray, samp: np.ndarray, Yu: np.ndarray, Yw: np.ndarray, gap: int, r0: int,
            Yd: np.ndarray | None = None, Yr: np.ndarray | None = None, brk=None) -> dict:
    """狀態型：samp＝樣本日（輸入有值；月資料＝每月最後一個交易日）索引，state＝這些樣本日是否在狀態中（同長度）。
    一段的命中率＝段內窗口完整的日子的比例；整體＝各段平均。Yd＝每一天的最大回撤（VER 3，只呈現：一段＝段內平均，整體＝各段中位數）。
    Yr＝每一天之後的漲跌（只呈現，一段＝段內平均）。
    → {"up", "warn", "occ": [[第一天, 最後一天, 天數, 偏多, 警示, 最大回撤, 之後漲跌], …]}。"""
    pos = [i for i in range(len(samp)) if state[i]]
    occ = []
    for ep in episodes(pos, gap, brk):
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
    """sigspec 第 3 節（VER 9；VER 14 起門檻依次數）：★＝過門檻而且打亂測試 p ≤ luck_p(次數)（次數 < 15 是 10%，其餘 1%）；
    ●＝過門檻但 p 超過門檻（可能是運氣）；○ 沒過門檻；— 次數不夠。
    st["p"]＝打亂測試（sigluck；沒有算＝None，當作沒過）。用沒有四捨五入的數字。"""
    n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
    if n < S.N_MIN or hit is None or base is None:
        return "few"
    if not LK.passes(n, hit, base, st.get("n10"), st.get("hit10"), st.get("base10"), d, recent):
        return "none"
    p = st.get("p")
    return "good" if p is not None and p <= S.luck_p(n) else "ref"


def judge(st: dict, d: str, recent: bool = True) -> str:
    st["tier"] = tier(st, d, recent)
    return st["tier"]


# ── VER 17：絕對成績（第 3 節；個股訊號以外都用這一套） ────────────────────────────

def ret_at(ret: dict | None, H: int, monthly: bool = False) -> list | None:
    """這個訊號自己看多久那一期的報酬格（第 4.11 節 ret_cell；monthly＝產業泡沫的 RET_H_M 個月）。"""
    hs = S.RET_H_M if monthly else S.RET_H
    s = (ret or {}).get("s") or []
    if H not in hs:
        return None
    i = hs.index(H)
    return s[i] if i < len(s) else None


def win_pass(st: dict | None, d: str) -> bool:
    """第 3 節 VER 17 的命中率部分：次數 ≥ N_MIN、命中率 ≥ HIT_MIN[方向]、命中率 ≥ 平常（溫度計的 △、跨期間的票、
    「過去讀數這樣的時候」也用這一條）。"""
    if not st:
        return False
    n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
    return bool(n >= S.N_MIN and hit is not None and base is not None and hit >= S.HIT_MIN[d] and hit >= base)


def abs_pass(st: dict, d: str, cell: list | None, cost: float) -> bool:
    """第 3 節 VER 17 的過門檻：命中率部分（win_pass）、近 10 年同一條；偏多與買點另外要報酬中位數與排除極端的平均都高於來回成本
    （cell＝ret_at 的那一格，cost＝每一邊的成本）。"""
    if not win_pass(st, d):
        return False
    if (st.get("n10") or 0) >= S.RECENT_N:
        h10, b10 = st.get("hit10"), st.get("base10")
        if h10 is None or b10 is None or h10 < S.HIT_MIN[d] or h10 < b10:
            return False
    if d == "warn":
        return True
    if not cell or len(cell) < 11:
        return False
    rt = 2 * cost
    med, trim = cell[3], cell[9]
    return bool(med is not None and trim is not None and med > rt and trim > rt)


def tier_abs(st: dict, d: str, cell: list | None, cost: float) -> str:
    """第 3 節 VER 17：★ good＝次數 ≥ STAR_N、過門檻；◆ rare＝次數 N_MIN～STAR_N − 1、過門檻；○ none；— few。"""
    n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
    if n < S.N_MIN or hit is None or base is None:
        return "few"
    if not abs_pass(st, d, cell, cost):
        return "none"
    return "good" if n >= S.STAR_N else "rare"


def judge_abs(st: dict, d: str, cell: list | None, cost: float) -> str:
    st["tier"] = tier_abs(st, d, cell, cost)
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
            "deriv": DV, "deriv_words": dict(HS.DERIV_WORDS), "bub": rows, "IB": IB, "r0": recent_from(cal),
            "stale": sorted((B.get("stale") or {}).keys())}


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
    return _opposite(out, x, cat)


def _opposite(out: list[dict], x: np.ndarray, cat: str) -> list[dict]:
    """sigspec VER 20：0～100 的變數——狀態型加 "brk"（每個樣本是不是相反的極端，第 3.4 節分段用）、
    事件型加 "exp"（之後出現就不再算現在有效的日子，第 5 節 EXPIRE_ON）。"""
    if cat not in S.EP_BREAK_CATS:
        return out
    x = np.asarray(x, dtype=float)
    ok = ~np.isnan(x)
    cond = {"lt_cold": np.nonzero(ok & (np.nan_to_num(x, nan=50.0) < S.COLD))[0],
            "ge_hot": np.nonzero(ok & (np.nan_to_num(x, nan=50.0) >= S.HOT))[0]}
    ev = {sd["sig"]: np.asarray(sd["days"], dtype=np.int64) for sd in out if sd["kind"] == "event"}
    for sd in out:
        if sd["kind"] == "state" and sd["sig"] in S.EP_BREAK:
            xs = x[np.asarray(sd["samp"], dtype=np.int64)]
            sd["brk"] = (xs < S.COLD) if S.EP_BREAK[sd["sig"]] == "lt_cold" else (xs >= S.HOT)
        elif sd["kind"] == "event" and sd["sig"] in S.EXPIRE_ON:
            parts = [cond[c] if c in cond else ev.get(c, np.zeros(0, dtype=np.int64)) for c in S.EXPIRE_ON[sd["sig"]]]
            sd["exp"] = np.unique(np.concatenate(parts)).astype(np.int64)
    return out


def _sides(out: list[dict], side: dict) -> None:
    """sigspec VER 20：成對的事件（技術事件 TECH_PAIRS、法人單日與連續 INST_SIDE）——另一邊的事件之後出現就不再算現在有效。
    side＝{訊號 sig: 哪一邊}；同一邊的不算相反。"""
    by: dict = {}
    for sd in out:
        if sd["sig"] in side:
            by.setdefault(side[sd["sig"]], []).append(np.asarray(sd["days"], dtype=np.int64))
    for sd in out:
        if sd["sig"] in side:
            other = [d for k, ds in by.items() if k != side[sd["sig"]] for d in ds]
            sd["exp"] = np.unique(np.concatenate(other)).astype(np.int64) if other else np.zeros(0, dtype=np.int64)


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
            pos_out = []
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
                pos_out.append(sd)
            out += _opposite(pos_out, x, "inst")
            continue
        hi, lo = S.INST_DAY
        day_out = []
        day_out.append({**base, "id": f"{mk}:inst:{v['key']}:day_sell", "sig": "day_sell", "kind": "event", "samp": samp,
                    "name": f"{v['name']}・單日大賣（過去 3 年賣超最多的 5%）", "days": [int(t) for t in samp if x[t] >= hi]})
        day_out.append({**base, "id": f"{mk}:inst:{v['key']}:day_buy", "sig": "day_buy", "kind": "event", "samp": samp,
                    "name": f"{v['name']}・單日大買（過去 3 年買超最多的 5%）", "days": [int(t) for t in samp if x[t] <= lo]})
        amt = np.asarray(v["amt"], dtype=float)
        sa = np.nonzero(~np.isnan(amt))[0]
        who = S.INST_NAMES[v["who"]]
        for sign, tag, word in ((-1, "sell", "賣超"), (1, "buy", "買超")):
            for n in S.INST_RUN:
                day_out.append({**base, "H": S.INST_H["run"], "id": f"{mk}:inst:{v['key']}:{tag}_run{n}", "sig": f"{tag}_run{n}",
                                "kind": "event", "samp": sa, "name": f"{v['name']}・{who}連續 {n} 天{word}",
                                "days": run_days(amt, sign, n)})
        _sides(day_out, S.INST_SIDE)                    # VER 20：另一邊（買超／賣超）的事件之後出現就不再算現在有效
        out += day_out
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
    tech = [{"id": f"{mk}:tech:{k}", "cat": "tech", "grp": "tech", "var": k, "vn": nm, "sig": "ev", "name": nm,
             "kind": "event", "H": S.H_TECH, "samp": samp, "days": [t for t in ev[k] if t >= S.EV_START]}
            for k, nm in HS.EVENTS.items()]
    days = {sd["var"]: sd["days"] for sd in tech}
    for a, b in S.TECH_PAIRS:                           # VER 20：成對的另一個之後出現就不再算現在有效
        for sd in tech:
            if sd["var"] in (a, b):
                sd["exp"] = np.unique(np.asarray(days.get(b if sd["var"] == a else a, []), dtype=np.int64))
    out += tech
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


def _small(st: dict) -> dict:
    return {k: st[k] for k in ("n", "hit", "base")}


def cross_stats(F: dict, sd: dict, Ycache: dict) -> dict:
    """溫度計跨期間（sigspec 第 5 節 ③a，VER 15）：同一個訊號在另外兩支溫度計的看多久（THERMO_H）的統計——
    成功條件、次數、平常照第 2、3.4 節，只是 H 換掉。→ {k: {"H", "th", "up": {n, hit, base}, "warn": {n, hit, base}}}；
    不跨期間的類別回 {}。"""
    if sd["cat"] not in S.THERMO_X_CATS:
        return {}
    mk, cal = F["mk"], F["cal"]
    r0 = bisect.bisect_left(cal, F["r0"])
    samp = np.asarray(sd["samp"], dtype=np.int64)
    out = {}
    for k, H in S.THERMO_H.items():
        if H == sd["H"]:
            continue
        if H not in Ycache:
            Ycache[H] = outcomes(F["px"], H, warn_th(mk, H))
        Yu, Yw, _ = Ycache[H]
        if sd["kind"] == "event":
            R = ev_stat(sd["days"], Yu, Yw, samp, H, r0)
        else:
            gap = 1 if sd.get("monthly") else S.EP_GAP
            R = st_stat(np.asarray(sd["state"], dtype=bool), samp, Yu, Yw, gap, r0, brk=sd.get("brk"))
        out[k] = {"H": H, "th": warn_th(mk, H), "up": _small(R["up"]), "warn": _small(R["warn"])}
    return out


def evaluate(F: dict, sd: dict, Ycache: dict) -> dict:
    """一個訊號 → 一列（含每一次；VER 15 起另有 "xh"＝另外兩支溫度計的看多久的統計）。"""
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
    skip = None
    if sd["kind"] == "event":
        R = ev_stat(sd["days"], Yu, Yw, samp, H, r0, Yd, Yr)
        occ = [[cal[t], int(u), int(w), d, r] for t, u, w, d, r in R["occ"]]
        ok = set(int(i) for i in samp)
        ret = _ret_flat(np.asarray(dedupe([t for t in sd["days"] if t in ok], H), dtype=np.int64), RA)
        skip = skipped(sd["days"], ok, H, Yu, cal)
    else:
        gap = 1 if sd.get("monthly") else S.EP_GAP
        state = np.asarray(sd["state"], dtype=bool)
        R = st_stat(state, samp, Yu, Yw, gap, r0, Yd, Yr, brk=sd.get("brk"))
        occ = [[cal[a], cal[z], n, u, w, d, r] for a, z, n, u, w, d, r in R["occ"]]
        ret = ret_stats([samp[ep] for ep in episodes([i for i in range(len(samp)) if state[i]], gap, sd.get("brk"))], RA)
    ret["bk"] = ret_base(samp, RA, Ycache.setdefault("bases", {}), mk)
    LP = LK.market_p(sd, Yu, Yw, r0, R)                 # 打亂日子測試（VER 9；VER 17 起只呈現）
    cell = ret_at(ret, H)
    dirs = {}
    for d in ("up", "warn"):
        st = R[d]
        st["p"] = LP[d]["p"]
        judge_abs(st, d, cell, S.ABS_COST[mk])             # VER 17：絕對成績
        dirs[d] = st
    tr, ds = best(dirs)
    row = {k: sd[k] for k in ("id", "cat", "grp", "var", "vn", "sig", "name", "kind", "H")}
    row.update({"mk": mk, "th": warn_th(mk, H), "a": cal[int(samp[0])] if len(samp) else None,
                "z": cal[int(samp[-1])] if len(samp) else None, "up": dirs["up"], "warn": dirs["warn"],
                "tier": tr, "dir": ds, "occ": occ, "ret": ret})
    if skip:
        row["skip"] = skip
    if sd.get("monthly"):
        row["monthly"] = True
    xh = cross_stats(F, sd, Ycache)
    if xh:
        row["xh"] = xh
    row["_luck"] = {d: [LP[d]["luck"], LP[d]["luck_rare"]] for d in ("up", "warn")}   # 運氣會產生 ★、◆ 的機率（research 加總後拿掉）
    return row


# ── 大跌後買點（sigspec 第 4.7 節，VER 10） ──────────────────────────────────────

BUY_RULES = ("B1", "W10")


def buy_signals(F: dict) -> tuple[dict | None, list[dict]]:
    """大跌後買點（第 4.7 節）每一條規則的事件型訊號（訊號日＝買進日 − LAG）：buy_rows 與逐年樣本外（sigoos，第 4.14 節）共用。
    → (輸入 {"cal", "px", "samp"}, [{"id", "ev", "k", "kind": "event", "H", "samp", "days", "buys": [(事件日, 買進日, o, 隔天就買的 o)…]}…])；
    沒有 bottom 的輸入 → (None, [])。"""
    from . import bottom as BO
    from . import bottomspec as BS
    I = F["IB"]
    if not I:
        return None, []
    mk = F["mk"]
    cal = list(I["cal"])
    px = np.asarray(I["px"], dtype=float)
    T = len(px)
    samp = np.arange(BS.E10_WIN - 1, T, dtype=np.int64)
    samp = samp[~np.isnan(px[samp])]
    out = []
    for ev in BS.EVENTS:
        recs = BO.event_recs(I, ev)
        for k in BUY_RULES + tuple(BS.SIG_MK[mk]):
            buys = []
            for r in recs:
                o = r["b1"] if k == "B1" else (((r["rules"].get(k) or {}).get("o")) or None)
                if o and o.get("b") is not None and 0 <= o["b"] - S.LAG:
                    buys.append((r["t"], int(o["b"]), o, r["b1"]))
            out.append({"id": f"{mk}:buy:{ev}:{k}", "ev": ev, "k": k, "kind": "event", "H": S.H_BUY, "samp": samp,
                        "days": [b - S.LAG for _, b, _, _ in buys], "buys": buys})
    return {"cal": cal, "px": px, "samp": samp}, out


def buy_rows(F: dict, bases: dict | None = None) -> list[dict]:
    """兩種大跌 × 規則（大跌隔天就買、固定等 10 天、落底訊號）：每個事件的買進日當成事件型訊號（訊號日＝買進日 − LAG）；
    命中＝買進後 H_BUY 天收盤比買價高、平常＝隨便挑一天、打亂測試＝事件型平移（同偏多訊號）。
    另列（不判定）：同一批事件大跌隔天就買的上漲比例、買在相對低點的比例。報酬（VER 5）：買進日收盤進場。"""
    from . import bottomspec as BS
    I, sds = buy_signals(F)
    if I is None:
        return []
    mk = F["mk"]
    cal, px, samp = I["cal"], I["px"], I["samp"]
    H = S.H_BUY
    Yu, Yw, Yd = outcomes(px, H, warn_th(mk, H))
    Yr = fwd_ret(px, H)
    RA = ret_arrays(px)
    r0 = bisect.bisect_left(cal, F["r0"])
    bases = {} if bases is None else bases
    out = []
    for sd0 in sds:
        ev, k, days, buys, rid = sd0["ev"], sd0["k"], sd0["days"], sd0["buys"], sd0["id"]
        sd = {"id": rid, "kind": "event", "H": H, "samp": samp, "days": days}
        R = ev_stat(days, Yu, Yw, samp, H, r0, Yd, Yr)
        st = R["up"]
        LP = LK.market_p(sd, Yu, Yw, r0, R)
        st["p"] = LP["up"]["p"]
        kept = {int(t) + S.LAG for t, *_ in R["occ"]}
        ret = _ret_flat(np.asarray(sorted(b - S.LAG for b in kept), dtype=np.int64), RA)
        judge_abs(st, "buy", ret_at(ret, H), S.ABS_COST[mk])   # VER 17：絕對成績（報酬＝買進後 H_BUY 天）
        by_b = {b: (o, ob) for _, b, o, ob in buys}
        occ = []
        for t, u, _, _, rr in R["occ"]:
            o, ob = by_b[int(t) + S.LAG]
            occ.append([cal[int(t) + S.LAG], int(u), None if o.get("lp") is None else int(o["lp"]),
                        None if ob.get("r60") is None else int(ob["r60"] > 0), None if _nan(rr) else round(float(rr), 5)])
        lps = [o[2] for o in occ if o[2] is not None]
        b1s = [o[3] for o in occ if o[3] is not None]
        st.update({"lp": _mean(lps), "lp_n": len(lps), "b1": None if k == "B1" else _mean(b1s)})
        ret["bk"] = ret_base(samp, RA, bases, mk)
        out.append({"id": rid, "mk": mk, "cat": "buy", "grp": ev, "var": k,
                    "vn": BS.RULE_NAMES.get(k, "大跌隔天就買") if k != "B1" else "大跌隔天就買", "sig": ev, "kind": "event", "H": H,
                    "name": f"{BS.EVENT_NAMES[ev]}・{'大跌隔天就買' if k == 'B1' else BS.RULE_NAMES[k]}",
                    "base_name": "隨便挑一天",
                    "a": occ[0][0] if occ else None, "z": occ[-1][0] if occ else None,
                    "buy": st, "tier": st["tier"], "dir": ["buy"], "occ": occ, "ret": ret,
                    "_luck": {"up": [LP["up"]["luck"], LP["up"]["luck_rare"]], "warn": [0.0, 0.0]}})
    return out


# ── 產業泡沫 ─────────────────────────────────────────────────────────────────

def _months_add(m: str, k: int) -> str:
    y, mm = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mm // 12:04d}-{mm % 12 + 1:02d}"


def _ret_groups(groups: list[list[dict]], hs: tuple, ps: tuple | None = None) -> dict:
    """每一次＝一組樣本（每個樣本 {期間: (報酬, 中途最多跌)}），每一組一樣重 → 同 ret_stats 的格式（路徑 ps 預設＝同一批期間）。"""
    def pool(h):
        rs, as_, ws, ms, n = [], [], [], [], 0
        for g in groups:
            v = [x[h] for x in g if x.get(h) is not None]
            if not v:
                continue
            n += 1
            rs += [a for a, _ in v]
            as_ += [b for _, b in v]
            ws += [1.0 / len(v)] * len(v)
            ms.append(float(np.mean([a for a, _ in v])))     # VER 17：每一組（一次／一段）的平均
        return n, np.asarray(rs, dtype=float), np.asarray(as_, dtype=float), np.asarray(ws, dtype=float), ms

    out_s, out_p = [], []
    for h in hs:
        n, r, a, w, ms = pool(h)
        out_s.append(ret_cell(r, a, w, n, ms) if n else None)
    for d in (hs if ps is None else ps):
        n, r, _, w, _ = pool(d)
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
        # 打亂日子測試（VER 9；VER 17 起只呈現）：次數夠的方向都算
        need = {d: st["hit"] for d, st in dirs.items() if st["n"] >= S.N_MIN and st["hit"] is not None}
        pv = LK.ind_p(f"ind:{group}:{k}", seqs, need) if need else {}
        ret = {**_ret_groups(rgroups, S.RET_H_M), "bk": bk, "hm": True}
        cell = ret_at(ret, S.H_IND_M, monthly=True)
        cost = S.ABS_COST["us" if group in ("ff", "us") else "tw"]
        for d, st in dirs.items():
            st["p"] = pv.get(d)
            judge_abs(st, d, cell, cost)                    # VER 17：絕對成績（報酬＝12 個月）
        dirs["warn"].update(mdd=_median([o[6] for o in occ]), mdd_base=_median(base_d))
        tr, ds = best(dirs)
        gname = BIS.GROUP_NAMES[group] if hasattr(BIS, "GROUP_NAMES") else group
        out.append({"id": f"ind:{group}:{k}", "mk": "us" if group in ("ff", "us") else "tw", "cat": "ind", "grp": group,
                    "var": k, "vn": gname, "sig": k, "name": f"{gname}・{S.BUB_NAMES[k]}", "kind": "state",
                    "H": S.H_IND_M, "monthly": True, "th": S.WARN_LONG, "a": occ[0][0] if occ else None, "z": zl,
                    "up": dirs["up"], "warn": dirs["warn"], "tier": tr, "dir": ds, "occ": occ, "ret": ret})
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
    """運氣會產生幾個 ★、◆（sigspec 第 3.5 節，只呈現；VER 17 起用新判定的命中率部分）：市場層級訊號與大跌後買點 →
    {市場: {方向: [實際 ★, 運氣會產生的 ★, 實際 ◆, 運氣會產生的 ◆]}}。會把列裡的 _luck 拿掉。"""
    out: dict = {}
    for r in rows:
        lk = r.pop("_luck", None)
        if lk is None:
            continue
        m = out.setdefault(r["mk"], {d: [0, 0.0, 0, 0.0] for d in ("up", "warn")})
        for d in ("up", "warn"):
            st = r.get("buy") if (r.get("cat") == "buy" and d == "up") else r.get(d)
            t = (st or {}).get("tier")
            m[d][0] += t == "good"
            m[d][1] += lk[d][0]
            m[d][2] += t == "rare"
            m[d][3] += lk[d][1]
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
    return R if (R.get("ver") or 0) >= S.RES_VER else None


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
    out = {"mk": now["mk"], "d": now["d"], **board(rows, now["on"], now["mk"], now.get("acts"), now.get("xon"))}
    try:                                              # 溫度計下面「過去讀數這樣的時候」（VER 16，第 5 節 ③d）；研究檔沒有就不顯示
        from . import thermocal as TC
        out["cal"] = TC.now(now["mk"], now["on"], now.get("xon"), now["d"])
    except Exception as e:                            # noqa: BLE001
        print(f"[訊號總覽] 過去讀數這樣的時候算不出來：{type(e).__name__}: {e}")
        out["cal"] = None
    return out


# ── 現在有沒有效（每天建頁） ───────────────────────────────────────────────────

def activity(sd: dict, T: int, H: int | None = None) -> np.ndarray:
    """過去「出現」的日子（sigspec 第 5 節 ①b，同類合併用）：狀態型＝樣本日裡在狀態中的日子；事件型＝每一次出現那天起 H 個交易日
    （H 沒給＝這個訊號自己的看多久；跨期間的票用那支溫度計的 THERMO_H，第 5 節 ③a）。"""
    a = np.zeros(T, dtype=bool)
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if sd["kind"] == "state":
        a[samp[np.asarray(sd["state"], dtype=bool)]] = True
    else:
        H = sd["H"] if H is None else H
        D = np.asarray(sd["days"], dtype=np.int64)
        for t, e in zip(D.tolist(), exp_end(sd, D, H).tolist()):   # VER 20：相反的讀數出現就不再算
            a[t:e] = True
    return a


def xkey(sid: str, k: str) -> str:
    """跨期間的票在 acts 裡的鍵（同一個訊號在另一支溫度計）。"""
    return f"{sid}@{k}"


def trade_dates(mk: str, cal: list[str], t: int, H: int) -> dict:
    """訊號第 t 天 → 照規則的那一筆交易（sigspec 第 2 節）：第 t＋LAG 天收盤進場、第 t＋LAG＋H 天收盤出場；
    超過資料最後一天的日子用休市表往後推（xstrat.future_days）。→ {"buy", "sell", "rem": 出場前還有幾個交易日（今天＝資料最後一天）}。"""
    from . import xstrat as XS
    T = len(cal)
    e, z = t + S.LAG, t + S.LAG + H
    need = z - (T - 1)
    fut = XS.future_days(mk, cal[-1], need) if need > 0 else []
    at = lambda i: cal[i] if i <= T - 1 else fut[i - T]   # noqa: E731
    return {"buy": at(e), "sell": at(z), "rem": max(0, z - (T - 1))}


def now_market(F: dict, acts: dict | None = None, xon: dict | None = None) -> dict:
    """一個市場 → {訊號 id: {"since": 開始日, "n": 已經幾天（月資料＝幾個月）, "left": 事件型剩幾天,
    "buy"／"sell"／"rem"：照規則的那一筆交易（trade_dates；狀態型＝今天看到、下一個交易日收盤進場）}}，只列現在有效的。
    狀態型＝資料最後一天在狀態中（月資料＝最後一個過完的月份）；事件型＝最近一次出現在最後 H 個交易日內；
    買點＝目前一段大跌（bottom.now 進行中）之後已經出現。acts＝給了就順便填現在有效的訊號過去出現的日子（同類合併用）。
    xon＝給了就填跨期間（sigspec 第 5 節 ③a，VER 15）：{訊號 id: {溫度計: 同上的現在狀態}}，只列原本那個看多久以外、現在有效的；
    acts 同時填 xkey(id, 溫度計)＝那支溫度計的看多久下出現的日子。"""
    cal = F["cal"]
    T = len(cal)
    out: dict = {}
    stale = set(F.get("stale") or ())                  # VER 20：資料過期的項目不算現在有效
    mk = F.get("mk")
    trd = (lambda t, H: trade_dates(mk, cal, t, H)) if mk else (lambda t, H: {})   # noqa: E731（沒有市場代號＝不排交易日）
    for sd in signals(F):
        if stale and sd["cat"] in ("heat", "deriv") and sd.get("var") in stale:
            continue
        samp = np.asarray(sd["samp"], dtype=np.int64)
        xs = ([(k, H) for k, H in S.THERMO_H.items() if H != sd["H"]]
              if xon is not None and sd["cat"] in S.THERMO_X_CATS else [])
        if sd["kind"] == "state":
            st = np.asarray(sd["state"], dtype=bool)
            if not len(samp) or not st[-1]:
                continue
            if not sd.get("monthly") and samp[-1] != T - 1:
                continue
            gap = 1 if sd.get("monthly") else S.EP_GAP
            ep = episodes([i for i in range(len(samp)) if st[i]], gap, sd.get("brk"))[-1]   # VER 20：遇到相反的極端就是新的一段
            out[sd["id"]] = {"since": cal[int(samp[ep[0]])], "n": len(ep), **trd(T - 1, sd["H"])}
            for k, H in xs:                              # 狀態型：現在有效、出現的日子都和原本一樣（交易照那支溫度計的看多久）
                xon.setdefault(sd["id"], {})[k] = {**out[sd["id"]], **trd(T - 1, H)}
        else:
            ds = [t for t in sd["days"] if t >= (samp[0] if len(samp) else 0)]
            alive = bool(ds) and int(exp_end(sd, [ds[-1]], T)[0]) >= T   # VER 20：之後出現相反的讀數就不再算
            if alive and T - 1 - ds[-1] < sd["H"]:
                out[sd["id"]] = {"since": cal[ds[-1]], "n": T - 1 - ds[-1], "left": sd["H"] - (T - 1 - ds[-1]),
                                 **trd(ds[-1], sd["H"])}
            for k, H in xs:
                if alive and T - 1 - ds[-1] < H:
                    xon.setdefault(sd["id"], {})[k] = {"since": cal[ds[-1]], "n": T - 1 - ds[-1], "left": H - (T - 1 - ds[-1]),
                                                       **trd(ds[-1], H)}
        if acts is not None and sd["id"] in out:
            acts[sd["id"]] = activity(sd, T)
        if acts is not None and xon is not None:
            for k, H in xs:
                if k in xon.get(sd["id"], {}):
                    acts[xkey(sd["id"], k)] = acts[sd["id"]] if sd["kind"] == "state" else activity(sd, T, H)
    I = F.get("IB")
    if I:
        from . import bottom as BO
        Nw = BO.now(I)
        for a in Nw.get("active") or []:
            evs = (a["ev"],) + ((a["also"],) if a.get("also") else ())
            sigs = {"B1": {"st": "on", "d": a["t"]}, "W10": a.get("w10") or {}, **(a.get("sig") or {})}
            for k, v in sigs.items():
                if v.get("st") == "on":
                    j = bisect.bisect_left(cal, v["d"])
                    tr = trd(j, S.H_BUY) if j < T and cal[j] == v["d"] else {}
                    for ev in evs:
                        out[f"{F['mk']}:buy:{ev}:{k}"] = {"since": v["d"], "event": a["t"], **tr}
    return out


def edge(st: dict | None) -> float | None:
    if not st or st.get("hit") is None or st.get("base") is None:
        return None
    return st["hit"] - st["base"]


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


def overlap(a: np.ndarray | None, b: np.ndarray | None) -> tuple[float, float]:
    """（出現日子比較少的那個，出現的日子裡另一個也成立的比例，另一個在全部樣本日成立的比例）；資料不齊回 (0, 1)。"""
    if a is None or b is None or len(a) != len(b) or not len(a):
        return 0.0, 1.0
    na, nb = int(a.sum()), int(b.sum())
    if not na or not nb:
        return 0.0, 1.0
    lo, hi = (a, b) if na <= nb else (b, a)
    return int((lo & hi).sum()) / int(lo.sum()), float(hi.mean())


def _ak(x: dict) -> str:
    """同類合併查「出現的日子」用的鍵：跨期間的票（VER 15）是 xkey(id, 溫度計)，其他就是訊號 id。"""
    return x.get("ak") or x["id"]


def same_family(a: np.ndarray | None, b: np.ndarray | None) -> bool:
    """sigspec 第 5 節 ①b（VER 11）：比較少出現的那個出現時，另一個過半也成立，而且至少是互不相干時的 FAMILY_X 倍。"""
    o, q = overlap(a, b)
    return o >= S.FAMILY_O and o >= S.FAMILY_X * q


def families(items: list[dict], acts: dict | None) -> list[dict]:
    """同類合併（sigspec 第 5 節 ①b；VER 8 寫定、VER 11 改條件）：同一支溫度計、同一邊，same_family 的併成一類（單一連結）；
    大跌後買點同一個市場算一類。→ 每一類的領頭（差最大），其他放在 "fam"。"""
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
                if (a["cat"] == "buy" and b["cat"] == "buy") or same_family(acts.get(_ak(a)), acts.get(_ak(b))):
                    parent[find(i)] = find(j)
        cl: dict = {}
        for i, x in enumerate(xs):
            cl.setdefault(find(i), []).append(x)
        for ms in cl.values():
            ms.sort(key=lambda x: (-x["edge"], x["id"]))
            out.append({**ms[0], "fam": ms[1:]})
    out.sort(key=lambda x: (-x["edge"], x["id"]))
    return out


def list_cls(d: str, H: int, g: float) -> str | None:
    """sigspec 第 5 節 ④（VER 21）：預估之後的差 g（預估之後的命中率 − 平常）→ 偏多 up／買點 buy／偏弱 weak（只看 WEAK_H）／
    大跌風險 risk；不列＝None。"""
    if d == "buy":
        return "buy" if g >= S.LIST_GAP else None
    if d == "warn":
        return "risk" if g >= S.LIST_GAP else None
    if g >= S.LIST_GAP:
        return "up"
    return "weak" if H == S.WEAK_H and g <= -S.LIST_GAP else None


def _lrank(c: dict) -> tuple:
    """同一個項目、同一支溫度計留哪一個（第 5 節 ④）：|g| 大的；同分＝訊號自己的看多久優先，再取代號小的（回傳值小的優先）。"""
    return (-abs(c["g"]), c.get("xk") is not None, c["id"])


def listing(rows: list[dict], on: dict, mk: str, acts: dict | None = None, xon: dict | None = None,
            T: dict | None = None) -> list[dict] | None:
    """第 5 節 ④ 列出來的規則（VER 21）：這個市場現在有效的市場層級訊號（MARKET_CATS 與大跌後買點），預估之後和隨便挑一天差
    LIST_GAP 以上的（訊號自己的看多久＝研究列的統計；跨期間＝xon 現在有效、xh 的統計、sigoos.est_x）；同一個項目同一支溫度計
    一邊留一個、「震盪」（both）、同類合併（families）。→ 每一類的領頭："cls"（偏多／買點／偏弱／大跌風險）、"side"、"hz"、
    "g"＝預估之後的差、"edge"＝|g|、"fe"＝預估之後（sigoos.est／est_x）、"now"、"fam"＝同一類的其他訊號；跨期間的列另有
    "xk"、"H0"、"ak"，H、th、up、warn 換成那支溫度計的。預估之後的研究檔沒有（或版本不夠）＝None。"""
    from . import sigoos as OOS
    T = OOS.load() if T is None else T
    if not T:
        return None
    best: dict = {}

    def put(c: dict) -> None:
        key = (item_key(c), c["hz"], "w" if c["d"] == "warn" else "u")
        if key not in best or _lrank(c) < _lrank(best[key]):
            best[key] = c
    for r in rows:
        if r.get("mk") != mk or r["id"] not in on or r.get("cat") not in OOS.MARKET_CATS + ("buy",):
            continue
        for d in (("buy",) if r["cat"] == "buy" else ("up", "warn")):
            fe = OOS.est(r, d, T)
            if not fe:
                continue
            g = fe["fh"] - fe["base"]
            cls = list_cls(d, int(r["H"]), g)
            if cls:
                put({**r, "d": d, "cls": cls, "side": S.LIST_SIDE[cls], "hz": horizon(r), "g": g, "edge": abs(g), "fe": fe,
                     "now": on[r["id"]]})
    for r in rows:                                    # 跨期間（第 5 節 ③a 的現在有效 × 第 4.14 節 ⑧）
        if r.get("mk") != mk or not xon or r["id"] not in xon or not r.get("xh"):
            continue
        for k, nk in xon[r["id"]].items():
            X = r["xh"].get(k)
            if not X:
                continue
            for d in ("up", "warn"):
                fe = OOS.est_x(r, d, k, T)
                if not fe:
                    continue
                g = fe["fh"] - fe["base"]
                cls = list_cls(d, int(X["H"]), g)
                if cls:
                    put({**r, "H": X["H"], "th": X["th"], "up": X["up"], "warn": X["warn"], "H0": r["H"], "d": d, "cls": cls,
                         "side": S.LIST_SIDE[cls], "hz": k, "g": g, "edge": abs(g), "fe": fe, "now": nk, "xk": k,
                         "ak": xkey(r["id"], k)})
    items: dict = {}
    for (ik, hz, slot), c in best.items():
        items.setdefault((ik, hz), {})[slot] = c
    out = []
    for sl in items.values():
        u, w = sl.get("u"), sl.get("w")
        if u is not None and w is not None and u["cls"] == "weak":    # 兩個都在警示那一邊：只留 |g| 大的
            out.append({**min((u, w), key=_lrank), "both": False})
            continue
        both = u is not None and w is not None                        # 偏多（買點）＋大跌風險＝震盪
        out += [{**c, "both": both} for c in (u, w) if c is not None]
    return families(out, acts)


def today(rows: list[dict], on: dict, mk: str, acts: dict | None = None, xon: dict | None = None,
          T: dict | None = None) -> dict:
    """訊號總覽「今天有效的訊號」（sigspec 第 5 節 ④，VER 21）：同 listing 的規則，偏多、警示兩邊各依 |g| 排序。
    → {"ok": 預估之後的研究檔有沒有, "up": [...], "warn": [...]}。"""
    fams = listing(rows, on, mk, acts, xon, T)
    if fams is None:
        return {"ok": False, "up": [], "warn": []}
    return {"ok": True, **{s: [f for f in fams if f["side"] == s] for s in ("up", "warn")}}


def board(rows: list[dict], on: dict, mk: str, acts: dict | None = None, xon: dict | None = None,
          T: dict | None = None) -> dict:
    """景氣頁「今天的重點」（sigspec 第 5 節 ④，VER 21）：listing 的每一類依溫度計分三段，每段偏多、警示兩張清單（依 |g| 排序）；
    溫度計＝每一支、每一邊的類數（一類算 1），偏多占比 ≥ THERMO_LEAN 偏多、≤ 1 − THERMO_LEAN 偏警示、其他差不多，兩邊都沒有＝中性。
    → {"ok", "up": [...], "warn": [...], "thermo": [{"k", "name", "h", "H", "n": {side: 類數}, "share", "lean", "up": [...], "warn": [...]}]}；
    預估之後的研究檔沒有＝ok False、全部空的。"""
    fams = listing(rows, on, mk, acts, xon, T)
    ok = fams is not None
    fams = fams or []
    th = []
    for k, name, h in S.THERMO_HZ:
        L = {s: [f for f in fams if f["hz"] == k and f["side"] == s] for s in ("up", "warn")}
        n = {s: len(L[s]) for s in L}
        tot = n["up"] + n["warn"]
        share = n["up"] / tot if tot else None
        lean = None if share is None else "up" if share >= S.THERMO_LEAN else "warn" if share <= 1 - S.THERMO_LEAN else "even"
        th.append({"k": k, "name": name, "h": h, "H": S.THERMO_H[k], "n": n, "share": share, "lean": lean, **L})
    return {"ok": ok, "up": [f for f in fams if f["side"] == "up"], "warn": [f for f in fams if f["side"] == "warn"], "thermo": th}


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
        xon: dict = {}
        on = now_market(F, acts, xon)
        NOW[F["mk"]] = {"mk": F["mk"], "d": F["cal"][-1], "on": on, "acts": acts, "xon": xon, "cv": crash_now(F),
                        "sim": _sim_now(F)}
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
    return R if (R.get("ver") or 0) >= S.RES_VER else None
