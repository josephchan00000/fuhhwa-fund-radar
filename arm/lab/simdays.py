"""現在的情境：相似的日子（sigspec VER 5 第 4.12 節；docs/lab_outlook_plan.md）。只當參考，不進 ★／● 判定與溫度計。

  estimate(F)   某一天（預設資料最後一天）：每個期間挑過去最像的 NB_K 天 → 報酬與中途最多跌的分布、平常、最像的幾段、加上籌碼的一版
  oos(F, h)     樣本外檢查：每個月最後一個交易日只用當天拿得到的資料估一次上漲機率，和「只看平常的比例」比 Brier
  research()    五個市場的樣本外 → data/lab/sim_research.json（scripts/run_sim.py；資料或規格改了才重跑）

面向分數＝情境用的四個共通面向（sigcat.scen_series：台股資金＝全球與台灣資金平均，兩個都有值才算；美股籌碼＝情緒籌碼）。
報酬、中途最多跌用訊號總覽同一組陣列（sigcat.ret_arrays：第 t 格＝第 t 天、隔一個交易日收盤進場）。
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import sigcat as G
from . import sigspec as S

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "lab" / "sim_research.json"


def features(F: dict, dims=S.NB_DIMS) -> np.ndarray:
    """→ T × 面向數的分數（沒有值＝NaN）。"""
    X = G.scen_series(F)
    return np.vstack([np.asarray(X[d], dtype=float) for d in dims]).T


def candidates(X: np.ndarray, RA: dict, T: int, h: int) -> np.ndarray:
    """估計那一天 T、期間 h 的候選：面向都有值、窗口在 T 之前已經走完（d＋LAG＋h ≤ T）、報酬與中途最多跌都算得出來。"""
    z = T - S.LAG - h
    if z < 0:
        return np.zeros(0, dtype=np.int64)
    idx = np.arange(z + 1)
    ok = np.all(np.isfinite(X[:z + 1]), axis=1) & np.isfinite(RA["R"][h][:z + 1]) & np.isfinite(RA["A"][h][:z + 1])
    return idx[ok]


def pick(X: np.ndarray, today: np.ndarray, cand: np.ndarray, k: int = S.NB_K, gap: int = S.NB_GAP) -> tuple[list, list]:
    """依距離（各面向分數差的絕對值平均）由小到大挑，同距離挑日期較晚的；挑到的日子彼此至少隔 gap 個交易日。→（位置, 距離）。"""
    if not len(cand):
        return [], []
    D = np.mean(np.abs(X[cand] - today), axis=1)
    order = np.lexsort((-cand, D))
    blocked = np.zeros(int(cand.max()) + 1, dtype=bool)
    out, dist = [], []
    for j in order:
        i = int(cand[j])
        if blocked[i]:
            continue
        out.append(i)
        dist.append(float(D[j]))
        blocked[max(0, i - gap + 1):i + gap] = True
        if len(out) >= k:
            break
    return out, dist


def _cell(RA: dict, h: int, idx) -> list | None:
    """挑到的日子 → sigcat.ret_cell（最後兩個＝最大跌幅最差一次與那一天，sigspec VER 24）。"""
    idx = np.asarray(idx, dtype=np.int64)
    if not len(idx):
        return None
    r, a = RA["R"][h][idx], RA["A"][h][idx]
    dh = (RA.get("D") or {}).get(h)
    return G.ret_cell(r, a, np.ones(len(idx)), len(idx), dd=None if dh is None else dh[idx], ix=idx, cal=RA.get("cal"))


def estimate(F: dict, T: int | None = None, RA: dict | None = None) -> dict | None:
    """估計那一天（預設資料最後一天）→ {"d": 日期, "x": 現在的面向分數, "rows": 每個期間 {h, n, dist, far, s, b, a}, "list": 最像的幾段, "chip": 加上籌碼的一版}。
    s／b＝挑到的日子／全部候選的 sigcat.ret_cell；a＝候選最早的一天；list 每段另附當時的籌碼分數 c（只顯示，不算距離）。面向有缺值 → None。"""
    cal = F["cal"]
    T = len(cal) - 1 if T is None else T
    RA = RA if RA is not None else G.ret_arrays(F["px"], cal=cal)
    X = features(F)
    today = X[T]
    if not np.all(np.isfinite(today)):
        return None
    rows, picks = [], {}
    for h in S.RET_H:
        cand = candidates(X, RA, T, h)
        ch, dist = pick(X, today, cand)
        picks[h] = (ch, dist)
        md = float(np.mean(dist)) if dist else None
        rows.append({"h": h, "n": len(ch), "dist": md, "far": md is not None and md > S.NB_FAR, "s": _cell(RA, h, ch),
                     "b": _cell(RA, h, cand), "a": cal[int(cand[0])] if len(cand) else None})
    ch, dist = picks[S.NB_LIST_H]
    XX = features(F, S.NB_DIMS_X)
    ci = list(S.NB_DIMS_X).index("chip")
    lst = []
    for i, d in sorted(zip(ch, dist), key=lambda p: (p[1], -p[0])):
        c = XX[i, ci]
        e = {"d": cal[i], "dist": d, "x": [None if not math.isfinite(v) else float(v) for v in X[i]],
             "c": None if not math.isfinite(c) else float(c), "r": {}}
        for h in S.NB_LIST_EXTRA:
            v = RA["R"][h][i] if h in RA["R"] else np.nan
            e["r"][h] = None if not np.isfinite(v) or i + S.LAG + h > T else float(v)
        a = RA["A"][S.NB_LIST_H][i]
        e["mae"] = None if not np.isfinite(a) else float(a)
        dd = (RA.get("D") or {}).get(S.NB_LIST_H)
        v = np.nan if dd is None else dd[i]
        e["dd"] = None if not np.isfinite(v) else float(v)          # VER 24：最大跌幅（大跌的同一個算法）
        lst.append(e)
    out = {"d": cal[T], "dims": list(S.NB_DIMS), "x": [float(v) for v in today], "rows": rows, "list": lst}
    tx = XX[T]
    if np.all(np.isfinite(tx)):
        chip = []
        for h in S.NB_H_X:
            cand = candidates(XX, RA, T, h)
            c2, d2 = pick(XX, tx, cand)
            chip.append({"h": h, "n": len(c2), "dist": float(np.mean(d2)) if d2 else None, "s": _cell(RA, h, c2),
                         "b": _cell(RA, h, cand), "a": cal[int(cand[0])] if len(cand) else None})
        out["chip"] = {"dims": list(S.NB_DIMS_X), "x": [float(v) for v in tx], "rows": chip}
    return out


# ── 樣本外檢查 ───────────────────────────────────────────────────────────────

def month_end_idx(cal: list[str], start: str) -> list[int]:
    """start 起每個月最後一個交易日的位置（最後一個月沒過完也算，由呼叫端看窗口）。"""
    out = []
    for i, d in enumerate(cal):
        if d < start:
            continue
        if i == len(cal) - 1 or cal[i + 1][:7] != d[:7]:
            out.append(i)
    return out


def block_boot(x: np.ndarray, block: int = S.NB_BLOCK, n_boot: int = S.NB_BOOT, seed: int = S.NB_SEED) -> np.ndarray:
    """移動區塊重抽（不循環）：每次從 0～n−block 均勻抽區塊起點、接起來截成 n 個 → 每次的平均。"""
    n = len(x)
    rng = np.random.default_rng(seed)
    b = min(block, n)
    nb = math.ceil(n / b)
    cs = np.concatenate([[0.0], np.cumsum(x)])
    out = np.empty(n_boot)
    for k in range(n_boot):
        st = rng.integers(0, n - b + 1, size=nb)
        tot, left = 0.0, n
        for s0 in st:
            m = min(b, left)
            tot += cs[s0 + m] - cs[s0]
            left -= m
            if left <= 0:
                break
        out[k] = tot / n
    return out


def oos(F: dict, h: int, RA: dict | None = None, X: np.ndarray | None = None) -> dict:
    """一個期間的樣本外檢查（sigspec 第 4.12 節）→ 判定、Δ（Brier 差，> 0＝相似的日子比較準）、區間、前後兩半、p ≥ NB_HI、分組。"""
    cal = F["cal"]
    RA = RA if RA is not None else G.ret_arrays(F["px"])
    X = X if X is not None else features(F)
    last = len(cal) - 1
    rec = []
    for T in month_end_idx(cal, S.NB_OOS_START[F["mk"]]):
        if T + S.LAG + h > last or not np.all(np.isfinite(X[T])) or not np.isfinite(RA["R"][h][T]):
            continue
        cand = candidates(X, RA, T, h)
        ch, _ = pick(X, X[T], cand)
        if not ch:
            continue
        p = float(np.mean(RA["R"][h][np.asarray(ch)] > 0))
        q = float(np.mean(RA["R"][h][cand] > 0))
        y = 1.0 if RA["R"][h][T] > 0 else 0.0
        rec.append((cal[T], p, q, y))
    n = len(rec)
    out = {"h": h, "n": n, "a": rec[0][0] if rec else None, "z": rec[-1][0] if rec else None}
    if not n:
        out["v"] = "few"
        return out
    p = np.array([r[1] for r in rec])
    q = np.array([r[2] for r in rec])
    y = np.array([r[3] for r in rec])
    dm = (q - y) ** 2 - (p - y) ** 2
    half = math.ceil(n / 2)
    h1, h2 = float(dm[:half].mean()), float(dm[half:].mean()) if n > half else float("nan")
    out.update(bp=float(np.mean((p - y) ** 2)), bq=float(np.mean((q - y) ** 2)), d=float(dm.mean()), h1=h1, h2=h2,
               up=float(y.mean()), pm=float(p.mean()), qm=float(q.mean()))
    if n < S.NB_OOS_MIN:
        out["v"] = "few"
    else:
        bs = block_boot(dm)
        lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
        out.update(lo=lo, hi=hi)
        out["v"] = ("better" if lo > 0 and h1 > 0 and h2 > 0 else
                    "worse" if hi < 0 and h1 < 0 and h2 < 0 else "none")
    m = p >= S.NB_HI
    out["hi_n"] = int(m.sum())
    out["hi_up"] = float(y[m].mean()) if m.any() else None
    out["hi_q"] = float(q[m].mean()) if m.any() else None
    edges = (-1.0,) + tuple(S.NB_BINS) + (2.0,)
    bins = []
    for a, b in zip(edges[:-1], edges[1:]):
        k = (p >= a) & (p < b)
        bins.append({"lo": None if a < 0 else a, "hi": None if b > 1 else b, "n": int(k.sum()),
                     "p": float(p[k].mean()) if k.any() else None, "up": float(y[k].mean()) if k.any() else None})
    out["bins"] = bins
    return out


def market(F: dict) -> dict:
    RA = G.ret_arrays(F["px"])
    X = features(F)
    return {"oos": [oos(F, h, RA, X) for h in S.RET_H], "last": F["cal"][-1]}


def research(F: dict | None = None) -> dict:
    F = F if F is not None else G.frames()
    out = {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "markets": {}}
    for mk in S.MARKETS:
        if mk in F:
            out["markets"][mk] = market(F[mk])
    return G._r(out)


def save_research(R: dict) -> None:
    RESEARCH.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load_research() -> dict | None:
    try:
        R = json.loads(RESEARCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if (R.get("ver") or 0) >= S.SIM_VER else None
