"""景氣溫度頁第五版研究（docs/lab_heat_plan.md 第 14.14 節第 4、6 點；規格 heatspec VER 5）。

研究檔才算（scripts/run_heat.py → data/lab/heat_research.json 的 rel、deriv）；每天建頁只讀結果。純標準庫。
  · 單項分析（44 項＋5 個面向，每週樣本）：領先落後相關、Granger 雙向（每月樣本、HC1 Wald、BH 校正）、滾動相關、
    五區回測、進入過熱／過冷事件（每天樣本）；
  · 邊際變化（核心 13 項）：各狀態之後的表現、二階熱度的等級相關、扣掉水準之後的偏等級相關（BH 校正）。
重抽一律移動區塊、固定種子；相關係數的重抽用「區塊動差前綴和」，和逐筆重抽（heat.spearman_ci 的抽法）結果相同。
"""
from __future__ import annotations

import math
import random
import statistics

from . import heat as H
from . import heatpos as P
from . import heatspec as S
from . import heattech as TT


# ── 小工具 ───────────────────────────────────────────────────────────

def month_ends(cal: list[str]) -> list[int]:
    return [i for i in range(len(cal)) if i == len(cal) - 1 or cal[i + 1][:7] != cal[i][:7]]


def wk_block(h: int) -> int:
    """每週樣本的重抽區塊長度（週）＝max(4, ⌈h ÷ 5⌉)。"""
    return max(S.WK_BLOCK_MIN, math.ceil(h / 5))


def _r(x, k=4):
    return None if x is None else round(x, k)


def _prefix(xs: list) -> list:
    p = [0.0]
    for v in xs:
        p.append(p[-1] + v)
    return p


def _q(reps: list, ci: float = S.CI) -> tuple:
    reps = sorted(reps)
    a = (1 - ci) / 2
    return reps[int(a * len(reps))], reps[min(len(reps) - 1, int((1 - a) * len(reps)))]


# ── 重抽：區塊動差前綴和 ─────────────────────────────────────────────

def _draws(rnd: random.Random, n: int, L: int) -> list[tuple[int, int]]:
    """一次重抽的區塊：(起點, 長度)；湊滿 n 筆，最後一塊截斷（和逐筆重抽同一串亂數）。"""
    starts = n - L + 1
    out, got = [], 0
    while got < n:
        s = rnd.randrange(starts)
        ln = min(L, n - got)
        out.append((s, ln))
        got += ln
    return out


def boot_corr(rx: list, ry: list, L: int, n_boot: int = S.BOOT_N, seed: int = S.BOOT_SEED) -> tuple:
    """（已排名的）rx、ry 的 Pearson 相關，移動區塊重抽 95% 區間。樣本 < max(30, 2L) 回 (None, None)。"""
    n = len(rx)
    if n < max(30, 2 * L):
        return None, None
    px, py = _prefix(rx), _prefix(ry)
    pxx, pyy = _prefix([a * a for a in rx]), _prefix([b * b for b in ry])
    pxy = _prefix([a * b for a, b in zip(rx, ry)])
    rnd = random.Random(seed)
    reps = []
    for _ in range(n_boot):
        sx = sy = sxx = syy = sxy = 0.0
        for s, ln in _draws(rnd, n, L):
            e = s + ln
            sx += px[e] - px[s]
            sy += py[e] - py[s]
            sxx += pxx[e] - pxx[s]
            syy += pyy[e] - pyy[s]
            sxy += pxy[e] - pxy[s]
        vx, vy = sxx - sx * sx / n, syy - sy * sy / n
        if vx > 1e-12 and vy > 1e-12:
            reps.append((sxy - sx * sy / n) / math.sqrt(vx * vy))
    if len(reps) < n_boot // 2:
        return None, None
    return _q(reps)


def partial(rxy: float, rxz: float, ryz: float) -> float | None:
    d = (1 - rxz * rxz) * (1 - ryz * ryz)
    if d <= 1e-12:
        return None
    return (rxy - rxz * ryz) / math.sqrt(d)


def _corr_from(s1, s2, s11, s22, s12, n):
    v1, v2 = s11 - s1 * s1 / n, s22 - s2 * s2 / n
    if v1 <= 1e-12 or v2 <= 1e-12:
        return None
    return (s12 - s1 * s2 / n) / math.sqrt(v1 * v2)


def boot_partial(rx: list, ry: list, rz: list, L: int, n_boot: int = S.BOOT_N,
                 seed: int = S.BOOT_SEED) -> tuple:
    """偏相關（x、y 扣掉 z）的移動區塊重抽：→ (lo, hi, p)。p＝2 × 落在 0 另一側的比例（最多 1）。"""
    n = len(rx)
    if n < max(30, 2 * L):
        return None, None, None
    cols = {"x": rx, "y": ry, "z": rz}
    pre = {a: _prefix(v) for a, v in cols.items()}
    pre.update({a + b: _prefix([u * w for u, w in zip(cols[a], cols[b])]) for a, b in
                (("x", "x"), ("y", "y"), ("z", "z"), ("x", "y"), ("x", "z"), ("y", "z"))})
    rnd = random.Random(seed)
    reps = []
    keys = list(pre)
    for _ in range(n_boot):
        acc = dict.fromkeys(keys, 0.0)
        for s, ln in _draws(rnd, n, L):
            e = s + ln
            for kk in keys:
                p = pre[kk]
                acc[kk] += p[e] - p[s]
        rxy = _corr_from(acc["x"], acc["y"], acc["xx"], acc["yy"], acc["xy"], n)
        rxz = _corr_from(acc["x"], acc["z"], acc["xx"], acc["zz"], acc["xz"], n)
        ryz = _corr_from(acc["y"], acc["z"], acc["yy"], acc["zz"], acc["yz"], n)
        if None in (rxy, rxz, ryz):
            continue
        pr = partial(rxy, rxz, ryz)
        if pr is not None:
            reps.append(pr)
    if len(reps) < n_boot // 2:
        return None, None, None
    lo, hi = _q(reps)
    below = sum(1 for v in reps if v <= 0) / len(reps)
    above = sum(1 for v in reps if v >= 0) / len(reps)
    return lo, hi, min(1.0, 2 * min(below, above))


def spearman_rank(x: list, y: list) -> tuple[list, list, float | None]:
    rx, ry = H._rank(x), H._rank(y)
    return rx, ry, H._pearson(rx, ry)


def partial_spearman(x: list, y: list, z: list) -> float | None:
    if len(x) < 3:
        return None
    rx, ry, rz = H._rank(x), H._rank(y), H._rank(z)
    a, b, c = H._pearson(rx, ry), H._pearson(rx, rz), H._pearson(ry, rz)
    if None in (a, b, c):
        return None
    return partial(a, b, c)


# ── 迴歸、χ²、BH ─────────────────────────────────────────────────────

def _inv(A: list[list[float]]) -> list[list[float]] | None:
    """高斯–約旦消去（部分選主元）；奇異回 None。"""
    n = len(A)
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        M[c] = [v / pv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c] != 0.0:
                f = M[r][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [row[n:] for row in M]


def ols_hc1(X: list[list[float]], y: list[float]) -> tuple[list[float], list[list[float]]] | None:
    """OLS 係數與 HC1（White×n/(n−k)）共變異數；X 不滿秩回 None。"""
    n, k = len(X), len(X[0])
    if n <= k:
        return None
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for row, yi in zip(X, y):
        for a in range(k):
            ra = row[a]
            xty[a] += ra * yi
            xa = xtx[a]
            for b in range(a, k):
                xa[b] += ra * row[b]
    for a in range(k):
        for b in range(a):
            xtx[a][b] = xtx[b][a]
    inv = _inv(xtx)
    if inv is None:
        return None
    beta = [sum(inv[a][b] * xty[b] for b in range(k)) for a in range(k)]
    meat = [[0.0] * k for _ in range(k)]
    for row, yi in zip(X, y):
        e = yi - sum(r * b for r, b in zip(row, beta))
        e2 = e * e
        for a in range(k):
            ra = row[a] * e2
            ma = meat[a]
            for b in range(a, k):
                ma[b] += ra * row[b]
    for a in range(k):
        for b in range(a):
            meat[a][b] = meat[b][a]
    tmp = [[sum(inv[a][c] * meat[c][b] for c in range(k)) for b in range(k)] for a in range(k)]
    V = [[sum(tmp[a][c] * inv[c][b] for c in range(k)) * n / (n - k) for b in range(k)] for a in range(k)]
    return beta, V


def _gammq(a: float, x: float) -> float:
    """正規化上不完全 Gamma Q(a, x)（級數＋連分數，Numerical Recipes 的作法）。"""
    if x <= 0:
        return 1.0
    lg = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1:
        ap, s = a, 1.0 / a
        d = s
        for _ in range(10000):
            ap += 1
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-15:
                break
        return max(0.0, 1.0 - s * math.exp(lg))
    tiny = 1e-300
    b = x + 1 - a
    c, d = 1 / tiny, 1 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        de = d * c
        h *= de
        if abs(de - 1) < 1e-15:
            break
    return math.exp(lg) * h


def chi2_sf(x: float, k: int) -> float:
    return _gammq(k / 2.0, x / 2.0)


def wald(beta: list, V: list, idx: list[int]) -> tuple[float, float] | None:
    b = [beta[i] for i in idx]
    Vs = [[V[i][j] for j in idx] for i in idx]
    inv = _inv(Vs)
    if inv is None:
        return None
    w = sum(b[a] * inv[a][c] * b[c] for a in range(len(b)) for c in range(len(b)))
    return w, chi2_sf(max(0.0, w), len(idx))


def bh(ps: list) -> list:
    """Benjamini–Hochberg q 值（None 不算進家族）。"""
    idx = sorted((p, i) for i, p in enumerate(ps) if p is not None)
    m = len(idx)
    q: list = [None] * len(ps)
    prev = 1.0
    for rank in range(m, 0, -1):
        p, i = idx[rank - 1]
        prev = min(prev, p * m / rank)
        q[i] = prev
    return q


# ── 單項分析 ─────────────────────────────────────────────────────────

def leadlag(xw: list, we: list[int], px: list) -> dict:
    """xw＝每週樣本的 0～100（對應 we）。之前的期間只算相關；之後的期間加信賴區間與前後兩半。"""
    past, fut = {}, {}
    for h in S.LL_H:
        pr = [(x, px[i] / px[i - h] - 1.0) for x, i in zip(xw, we)
              if x is not None and i - h >= 0 and px[i] and px[i - h]]
        past[h] = {"n": len(pr), "rho": _r(H.spearman([a for a, _ in pr], [b for _, b in pr]))}
        fr = [(x, H.fwd(px, i, h)[0]) for x, i in zip(xw, we) if x is not None]
        fr = [(a, b) for a, b in fr if b is not None]
        xs, ys = [a for a, _ in fr], [b for _, b in fr]
        e = {"n": len(fr), "rho": None, "lo": None, "hi": None, "h1": None, "h2": None, "verdict": "few"}
        if len(fr) >= 3:
            rx, ry, rho = spearman_rank(xs, ys)
            lo, hi = boot_corr(rx, ry, wk_block(h))
            m = len(fr) // 2
            r1, r2 = H.spearman(xs[:m], ys[:m]), H.spearman(xs[m:], ys[m:])
            e.update({"rho": rho, "lo": lo, "hi": hi, "h1": r1, "h2": r2, "verdict": H.verdict(rho, lo, hi, r1, r2, len(fr), 0)})
        fut[h] = e
    mp = max((abs(v["rho"]) for v in past.values() if v["rho"] is not None), default=0.0)
    mf = max((abs(v["rho"]) for v in fut.values() if v["rho"] is not None), default=0.0)
    thr, ratio = S.LL_FOLLOW
    follow = mp >= thr and mp >= ratio * mf
    best_past = max(((h, v["rho"]) for h, v in past.items() if v["rho"] is not None), key=lambda x: abs(x[1]), default=None)
    leads = [(h, v) for h, v in fut.items() if v["verdict"] in ("weak", "strong")]
    lead = max(leads, key=lambda hv: abs(hv[1]["rho"]))[0] if leads else None
    return {"past": past, "fut": {h: {k: (_r(v) if k in ("rho", "lo", "hi", "h1", "h2") else v) for k, v in e.items()}
                                  for h, e in fut.items()},
            "follow": follow, "follow_h": best_past[0] if follow and best_past else None, "lead": lead}


def monthly_rx(x_daily: list, px: list, cal: list[str]) -> tuple[list, list, list[str]]:
    """每月樣本：r_m＝第 m − 1 個月底的下一個交易日收盤 → 第 m 個月底的下一個交易日收盤的對數報酬；x_m＝第 m 個月底的值。"""
    me = month_ends(cal)
    r, x, ds = [], [], []
    for m in range(len(me)):
        x.append(x_daily[me[m]])
        ds.append(cal[me[m]][:7])
        if m == 0:
            r.append(None)
            continue
        a, b = me[m - 1] + 1, me[m] + 1
        r.append(math.log(px[b] / px[a]) if b < len(px) and px[a] and px[b] else None)
    return r, x, ds


def _gr_rows(dep: list, own: list, oth: list, p: int) -> tuple[list, list]:
    X, y = [], []
    for m in range(p, len(dep)):
        vals = [dep[m]] + [own[m - j] for j in range(1, p + 1)] + [oth[m - j] for j in range(1, p + 1)]
        if any(v is None for v in vals):
            continue
        y.append(vals[0])
        X.append([1.0] + vals[1:])
    return X, y


def _gr_fit(X: list, y: list, p: int) -> dict | None:
    f = ols_hc1(X, y)
    if f is None:
        return None
    beta, V = f
    idx = list(range(1 + p, 1 + 2 * p))
    w = wald(beta, V, idx)
    if w is None:
        return None
    return {"w": w[0], "p": w[1], "sum": sum(beta[i] for i in idx)}


def granger(r: list, x: list, p: int) -> dict:
    """模型 A（x → r）、模型 B（r → x）。→ {"A": {...}, "B": {...}}，各含 n、p、sum、前後兩半的係數和。"""
    out = {}
    for key, dep, own, oth in (("A", r, r, x), ("B", x, x, r)):
        X, y = _gr_rows(dep, own, oth, p)
        e = {"n": len(y), "p": None, "w": None, "sum": None, "s1": None, "s2": None}
        if len(y) >= S.GR_MIN:
            full = _gr_fit(X, y, p)
            if full:
                e.update(full)
            m = len(y) // 2
            h1, h2 = _gr_fit(X[:m], y[:m], p), _gr_fit(X[m:], y[m:], p)
            e["s1"], e["s2"] = (h1 or {}).get("sum"), (h2 or {}).get("sum")
        out[key] = e
    return out


def gr_verdict(e: dict, q: float | None) -> str:
    """有額外預測力＝q ≤ BH 門檻，而且前後兩半的係數和都和全期間同號。"""
    if e.get("p") is None or q is None or e.get("sum") is None:
        return "few"
    if q <= S.BH_Q and e["s1"] is not None and e["s2"] is not None and e["sum"] != 0 \
            and (e["s1"] > 0) == (e["sum"] > 0) and (e["s2"] > 0) == (e["sum"] > 0) and e["s1"] != 0 and e["s2"] != 0:
        return "strong" if e["sum"] > 0 else "weak"
    return "none"


def rolling(xw: list, we: list[int], px: list, cal: list[str]) -> list:
    """每 4 週一點（從最新一週往回對齊），取到那一週為止的 260 週樣本，熱度和之後 60 日漲跌的等級相關。→ [[週序號, ρ], ...]"""
    f = [H.fwd(px, i, S.ROLL_H)[0] for i in we]
    out = []
    last = len(we) - 1
    for j in range(last, -1, -S.ROLL_STEP):
        a = j - S.ROLL_WEEKS + 1
        if a < 0:
            break
        pr = [(xw[k], f[k]) for k in range(a, j + 1) if xw[k] is not None and f[k] is not None]
        if len(pr) >= S.ROLL_MIN:
            out.append([j, _r(H.spearman([u for u, _ in pr], [v for _, v in pr]), 3)])
    out.reverse()
    return out


def bands_w(xw: list, we: list[int], px: list, cal: list[str]) -> dict:
    """五區回測（每週樣本）：之後 20、60、120、250 日。"""
    out = {}
    for h in S.REL_H:
        rows = []
        for x, i in zip(xw, we):
            if x is None:
                continue
            r, dd = H.fwd(px, i, h)
            if r is not None:
                rows.append((cal[i], x, r, dd))
        bs = H.bands([b for _, b, _, _ in rows], [c for _, _, c, _ in rows], [d for *_, d in rows])
        for b, (lo, hi, _) in zip(bs, S.BANDS):
            b["yrs"] = sorted({d[:4] for d, v, _, _ in rows if lo <= v < hi})
        out[h] = bs
    return out


def heat_events(x: list, kind: str) -> list[int]:
    """進入過熱：今天 ≥ 80、前 20 個交易日都有值且 < 80；進入過冷：今天 < 20、前 20 個交易日都有值且 ≥ 20。"""
    thr, prior = S.EVT[kind]
    out = []
    for t in range(prior, len(x)):
        v = x[t]
        if v is None:
            continue
        w = x[t - prior:t]
        if any(u is None for u in w):
            continue
        if kind == "hot" and v >= thr and all(u < thr for u in w):
            out.append(t)
        elif kind == "cold" and v < thr and all(u >= thr for u in w):
            out.append(t)
    return out


def event_vs_mask(px: list, cal: list[str], idx: list[int], h: int, mask: list[bool], f: list) -> dict:
    """事件之後 h 日 vs「mask 為真的所有日子」（同 heattech.event_study 的方法，只是基準日子換成這一項有 0～100 的日子）。"""
    base = [i for i in range(len(px)) if mask[i] and f[i] is not None]
    evs = [i for i in idx if f[i] is not None and mask[i]]
    allr = [f[i] for i in base]
    er = [f[i] for i in evs]
    mean = lambda xs: statistics.mean(xs) if xs else None          # noqa: E731
    out = {"n": len(evs), "avg": mean(er), "up": (sum(1 for v in er if v > 0) / len(er)) if er else None,
           "all_avg": mean(allr), "all_up": (sum(1 for v in allr if v > 0) / len(allr)) if allr else None,
           "a": cal[evs[0]] if evs else None, "z": cal[evs[-1]] if evs else None, "yrs": sorted({cal[i][:4] for i in evs})}
    out["diff"] = None if out["avg"] is None or out["all_avg"] is None else out["avg"] - out["all_avg"]
    ise = set(evs)
    out["lo"], out["hi"] = TT.boot_diff(allr, [i in ise for i in base], h)
    halves = []
    if len(evs) >= 2:
        m = len(evs) // 2
        cut = evs[m]
        for part, rng in ((evs[:m], (0, cut)), (evs[m:], (cut, len(px)))):
            ar = [f[i] for i in base if rng[0] <= i < rng[1]]
            pr = [f[i] for i in part]
            halves.append({"n": len(pr), "diff": None if not ar or not pr else mean(pr) - mean(ar)})
    out["h1"], out["h2"] = (halves + [None, None])[:2]
    out["verdict"] = TT.ev_verdict(out)
    return out


def _round_ev(r: dict) -> dict:
    out = dict(r)
    for k in ("avg", "all_avg", "diff", "lo", "hi"):
        out[k] = _r(out.get(k), 5)
    for k in ("up", "all_up"):
        out[k] = _r(out.get(k), 3)
    for k in ("h1", "h2"):
        if out.get(k):
            out[k] = {"n": out[k]["n"], "diff": _r(out[k]["diff"], 5)}
    return out


def group_stats(ret: list, flag: list, dates: list[str], L: int) -> dict:
    """每週樣本（ret＝之後漲跌，已排除沒有值的週）：flag 為真的週 vs 全部週。
    週數、段數（相鄰的週算一段）、平均、上漲機率、差、信賴區間（移動區塊、2,000 次）、前後兩半（依日期切在全部週的中間）、判定。"""
    n = sum(flag)
    runs = sum(1 for i, f in enumerate(flag) if f and (i == 0 or not flag[i - 1]))
    sel = [r for r, f in zip(ret, flag) if f]
    mean = lambda xs: statistics.mean(xs) if xs else None          # noqa: E731
    out = {"n": n, "runs": runs, "avg": mean(sel), "up": (sum(1 for v in sel if v > 0) / n) if n else None,
           "all_avg": mean(ret), "diff": None, "lo": None, "hi": None, "d1": None, "d2": None, "verdict": "few",
           "yrs": sorted({d[:4] for d, f in zip(dates, flag) if f})}
    if out["avg"] is not None and out["all_avg"] is not None:
        out["diff"] = out["avg"] - out["all_avg"]
    out["lo"], out["hi"] = TT.boot_diff(ret, flag, L) if n else (None, None)
    m = len(ret) // 2
    for key, rng in (("d1", range(0, m)), ("d2", range(m, len(ret)))):
        a = [ret[i] for i in rng]
        s = [ret[i] for i in rng if flag[i]]
        if a and s:
            out[key] = mean(s) - mean(a)
    if n >= S.CPL_MIN_WEEKS and runs >= S.CPL_MIN_RUNS and None not in (out["lo"], out["hi"], out["d1"], out["d2"]):
        if out["lo"] > 0 and out["d1"] > 0 and out["d2"] > 0:
            out["verdict"] = "strong"
        elif out["hi"] < 0 and out["d1"] < 0 and out["d2"] < 0:
            out["verdict"] = "weak"
        else:
            out["verdict"] = "none"
    return out


def _round_g(g: dict) -> dict:
    return {k: (_r(v, 5) if k in ("avg", "all_avg", "diff", "lo", "hi", "d1", "d2") else (_r(v, 3) if k == "up" else v))
            for k, v in g.items()}


def series_all(B: dict) -> dict[str, list]:
    """研究用的逐日 0～100：44 項用算進分數的（台指 VIX 不含代替）；5 個面向用面向分數。"""
    out = {k: B["hc"][k] for k in S.KEYS}
    out.update({d: B["comp"][d] for d in S.DIMS})
    return out


def run(B: dict) -> dict:
    """→ {"wk": 週日期, "rel": {id: {...}}, "gr_q": {...}}；只當參考，不拿來刪項目。"""
    cal, px = B["cal"], B["px"]
    we = P.week_ends(cal)
    ser = series_all(B)
    fw = {h: TT.fwd_all(px, h) for h in S.EVT_FWD}
    rel = {}
    gr_raw = {}
    for sid, x in ser.items():
        xw = [x[i] for i in we]
        mask = [v is not None for v in x]
        evt = {}
        for kind in ("hot", "cold"):
            idx = heat_events(x, kind)
            evt[kind] = {str(h): _round_ev(event_vs_mask(px, cal, idx, h, mask, fw[h])) for h in S.EVT_FWD}
            evt[kind]["list"] = [[cal[i]] + [_r(fw[h][i], 4) for h in S.EVT_FWD] for i in idx]
        r, xm, _ = monthly_rx(x, px, cal)
        gr_raw[sid] = {p: granger(r, xm, p) for p in S.GR_LAGS}
        first = next((cal[i] for i, v in enumerate(x) if v is not None), None)
        rel[sid] = {"first": first, "ll": leadlag(xw, we, px), "roll": rolling(xw, we, px, cal),
                    "bands": bands_w(xw, we, px, cal), "evt": evt}
    # Granger：44 項一家族、5 個面向一家族，模型 A、B 各自做 BH（主要落後期數）
    for fam in (list(S.KEYS), list(S.DIMS)):
        for key in ("A", "B"):
            ps = [gr_raw[s][S.GR_MAIN][key]["p"] for s in fam]
            qs = bh(ps)
            for s, q in zip(fam, qs):
                e = gr_raw[s][S.GR_MAIN][key]
                g = rel[s].setdefault("gr", {})
                g[key] = {"n": e["n"], "p": _r(e["p"], 5), "q": _r(q, 5), "sum": _r(e["sum"], 6),
                          "s1": _r(e["s1"], 6), "s2": _r(e["s2"], 6), "verdict": gr_verdict(e, q),
                          "rob": {str(p): _r(gr_raw[s][p][key]["p"], 5) for p in S.GR_LAGS if p != S.GR_MAIN}}
    return {"wk": [cal[i] for i in we], "rel": rel}


# ── 邊際變化驗證（核心 13 項） ───────────────────────────────────────

def deriv_all(B: dict) -> dict:
    cal, px = B["cal"], B["px"]
    we = P.week_ends(cal)
    out = {}
    tests = []
    for k in S.DERIV:
        D = P.deriv(B, k)
        hs = S.DIMS[S.DIM_OF[k]]["fwd"]
        lvl = B["hc"][k]
        res = {"first": next((cal[i] for i, v in enumerate(D["state"]) if v is not None), None), "h": {}}
        for h in hs:
            rows = []
            for i in we:
                r = H.fwd(px, i, h)[0]
                if r is None or D["state"][i] is None:
                    continue
                rows.append((cal[i], D["state"][i], D["acc"][i], lvl[i], r))
            ret = [x[4] for x in rows]
            dates = [x[0] for x in rows]
            L = wk_block(h)
            states = {}
            for st in (1, 2, 3, 4, 0):
                states[str(st)] = _round_g(group_stats(ret, [x[1] == st for x in rows], dates, L))
            # (b) 二階熱度 vs 之後漲跌
            pr = [(x[2], x[4]) for x in rows if x[2] is not None]
            acc = {"n": len(pr), "rho": None, "lo": None, "hi": None, "h1": None, "h2": None, "verdict": "few"}
            if len(pr) >= 3:
                xs, ys = [a for a, _ in pr], [b for _, b in pr]
                rx, ry, rho = spearman_rank(xs, ys)
                lo, hi = boot_corr(rx, ry, L)
                m = len(pr) // 2
                r1, r2 = H.spearman(xs[:m], ys[:m]), H.spearman(xs[m:], ys[m:])
                acc.update({"rho": _r(rho), "lo": _r(lo), "hi": _r(hi), "h1": _r(r1), "h2": _r(r2),
                            "verdict": H.verdict(rho, lo, hi, r1, r2, len(pr), 0)})
            # (c) 扣掉水準之後的偏等級相關
            tr = [(x[2], x[4], x[3]) for x in rows if x[2] is not None and x[3] is not None]
            pc = {"n": len(tr), "r": None, "lo": None, "hi": None, "p": None, "h1": None, "h2": None}
            if len(tr) >= 3:
                xs, ys, zs = [a for a, _, _ in tr], [b for _, b, _ in tr], [c for *_, c in tr]
                pc["r"] = partial_spearman(xs, ys, zs)
                lo, hi, p = boot_partial(H._rank(xs), H._rank(ys), H._rank(zs), L)
                m = len(tr) // 2
                pc.update({"lo": lo, "hi": hi, "p": p, "h1": partial_spearman(xs[:m], ys[:m], zs[:m]),
                           "h2": partial_spearman(xs[m:], ys[m:], zs[m:])})
            tests.append((k, h, pc))
            res["h"][str(h)] = {"states": states, "acc": acc, "pc": pc}
        out[k] = res
    qs = bh([pc["p"] for _, _, pc in tests])
    for (k, h, pc), q in zip(tests, qs):
        v = "few"
        if pc["r"] is not None and q is not None:
            v = "none"
            if q <= S.BH_Q and pc["h1"] is not None and pc["h2"] is not None and pc["r"] != 0 \
                    and (pc["h1"] > 0) == (pc["r"] > 0) and (pc["h2"] > 0) == (pc["r"] > 0) and pc["h1"] != 0 and pc["h2"] != 0:
                v = "strong" if pc["r"] > 0 else "weak"
        out[k]["h"][str(h)]["pc"] = {**{kk: (_r(vv) if kk in ("r", "lo", "hi", "h1", "h2") else vv) for kk, vv in pc.items()},
                                     "p": _r(pc["p"], 5), "q": _r(q, 5), "verdict": v}
    return out
