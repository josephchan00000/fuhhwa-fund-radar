"""景氣溫度頁第六版研究：邊際變化（二次微分）的多層回歸（docs/lab_heat_plan.md 第 15.11 節；規格 heatspec VER 6）。

研究檔才算（scripts/run_heat.py → data/lab/heat_research.json 的 m6）；每天建頁只讀結果。純標準庫。
  · 每月樣本：每個月最後一個交易日的訊號（只用當天拿得到的）；報酬 R(t; k, m)＝第 t＋k 個月底的下一個交易日收盤
    到第 t＋k＋m 個月底的下一個交易日收盤的對數報酬；控制台股過去 1、12 個月的報酬；
  · L1 延遲反應（局部投影）、L2 扣掉水準與一階、L3 交互（水準、四個狀態、多頭／升息）、L4 跨訊號（三組加速度、加速擴散）、
    L5 綜合模型（脊回歸、深度 2 決策樹，只看樣本外）、L6 轉折事件之後 1～24 個月；
  · 統計：OLS＋Newey–West t（只列出）、移動區塊重抽（區塊動差前綴和，和把抽到的列接起來重跑相同）的信賴區間與 p、
    Benjamini–Hochberg、主要假說 Holm；
  · 樣本外：擴張視窗，訓練只用報酬在預測當天以前就結束的月份（t＋k＋m ＜ 預測月份）；R²、Clark–West、命中率、依預測值三分組。
"""
from __future__ import annotations

import bisect
import calendar as _calendar
import math
import random

from . import heat as H
from . import heatcalc as C
from . import heatpos as P
from . import heatrel as RL
from . import heatspec as S
from . import heattech as TT

ITEMS = list(S.DERIV)
GROUPS = list(S.M6_GROUPS)
GVARS = [f"GA_{g}" for g in GROUPS] + ["DI"]                 # 跨訊號：三組加速度、加速擴散
SVARS = [f"SH_{g}" for g in GROUPS]                          # 對照圖的三條組線：組內幾成在加速（只當描述）
DELAY = [(k, S.M6_WIN) for k in S.M6_DELAY]
CUM = [(0, m) for m in S.M6_CUM]
PATH_H = tuple(range(1, S.M6_EVENT_PATH + 1))
WINDOWS = sorted(set(DELAY) | set(CUM) | {(0, h) for h in PATH_H} | set(S.M6_OOS_WINDOWS)
                 | {w for _, w in S.M6_PRIMARY.values()} | {(0, h) for h in S.M6_STATE_H})
STATES = ("hi_acc", "hi_dec", "lo_acc", "lo_dec")             # 水準 ≥ 50／< 50 × 加速（原始二階 > 0）／其他
GSTATES = ("gA_rA", "gA_rD", "gD_rA", "gD_rD")               # 景氣動能 × 通膨利率：加速（組加速度 > 0）／減速（≤ 0）
X1_ITEMS = [k for k in ITEMS if S.DERIV[k]["d1"] in ("chg", "pct")]   # 一階就是項目本身（年增率、PMI−50）的不放 X1
M1_G = ("LV_grow", "LV_rate")                                 # 組的樣本外模型（沒有控制變數）
M2_G = M1_G + ("GA_grow", "GA_rate")
M3_G = M2_G + ("GA_grow*GA_rate", "GA_grow*LV_grow", "GA_rate*LV_rate")
VERDICT = {"pred": "有預測性", "in_only": "樣本內看得到、樣本外沒有", "in_untested": "樣本內看得到（這個期間沒有做樣本外）",
           "none": "看不出", "few": "樣本不足"}


# ── 小工具 ───────────────────────────────────────────────────────────

def wkey(w: tuple) -> str:
    return f"{w[0]},{w[1]}"


def nw_lag(m: int) -> int:
    a, lo = S.M6_NW
    return max(lo, math.ceil(a * m))


def block(m: int) -> int:
    return max(S.M6_BLOCK_MIN, m)


def _sign(v) -> int | None:
    return None if v is None else (1 if v > 0 else (-1 if v < 0 else 0))


def _scale(p):
    return None if p is None else (p - 50.0) / 50.0


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def month_end_day(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{ym}-{_calendar.monthrange(y, m)[1]:02d}"


def _gmean(xs: list, mn: int):
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if len(v) >= mn else None


def _rnd(x):
    """輸出取位數（判定都已經用沒有四捨五入的數字算好）。"""
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: _rnd(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_rnd(v) for v in x]
    return x


# ── 線性代數、OLS、Newey–West ─────────────────────────────────────────

def solve(A: list, b: list) -> list | None:
    """A x = b（部分選主元高斯消去；不改 A、b）。主元 ≤ 1e-10 × 對角線最大絕對值＝奇異，回 None。"""
    n = len(A)
    scale = max((abs(A[i][i]) for i in range(n)), default=0.0)
    if scale <= 0.0:
        return None
    tol = 1e-10 * scale
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        piv, best = c, abs(M[c][c])
        for r in range(c + 1, n):
            v = abs(M[r][c])
            if v > best:
                piv, best = r, v
        if best <= tol:
            return None
        if piv != c:
            M[c], M[piv] = M[piv], M[c]
        rc = M[c]
        d = rc[c]
        for r in range(c + 1, n):
            rr = M[r]
            f = rr[c] / d
            if f:
                for j in range(c, n + 1):
                    rr[j] -= f * rc[j]
    x = [0.0] * n
    for c in range(n - 1, -1, -1):
        rc = M[c]
        s = rc[n]
        for j in range(c + 1, n):
            s -= rc[j] * x[j]
        x[c] = s / rc[c]
    return x


def _xtx(X: list, y: list) -> tuple[list, list]:
    k = len(X[0])
    A = [[0.0] * k for _ in range(k)]
    v = [0.0] * k
    for row, yi in zip(X, y):
        for a in range(k):
            ra = row[a]
            v[a] += ra * yi
            Aa = A[a]
            for c in range(a, k):
                Aa[c] += ra * row[c]
    for a in range(k):
        for c in range(a):
            A[a][c] = A[c][a]
    return A, v


def ols(X: list, y: list) -> dict | None:
    """→ {"beta", "inv"（(X'X)⁻¹）, "e"（殘差）}；列數不夠或不滿秩回 None。"""
    if len(X) <= len(X[0]):
        return None
    A, v = _xtx(X, y)
    inv = RL._inv(A)
    if inv is None:
        return None
    k = len(v)
    beta = [sum(inv[a][c] * v[c] for c in range(k)) for a in range(k)]
    e = [yi - _dot(row, beta) for row, yi in zip(X, y)]
    return {"beta": beta, "inv": inv, "e": e}


def nw_var(w: list, X: list, fit: dict, ti: list, lag: int) -> float:
    """線性組合 w·β 的 Newey–West 變異數（Bartlett 權重 1 − d/(lag＋1)，不做小樣本校正，同 statsmodels HAC 的預設）。
    ti＝每列的月序號：落後依實際相隔的月數配對（中間缺月也對）。"""
    inv, e = fit["inv"], fit["e"]
    k = len(w)
    h = [sum(w[a] * inv[a][c] for a in range(k)) for c in range(k)]
    g = [_dot(h, row) * ei for row, ei in zip(X, e)]
    s = 0.0
    for a in range(len(g)):
        ga = g[a]
        s += ga * ga
        b = a - 1
        while b >= 0 and ti[a] - ti[b] <= lag:
            d = ti[a] - ti[b]
            if d > 0:
                s += 2.0 * (1.0 - d / (lag + 1.0)) * ga * g[b]
            b -= 1
    return s


def nw_mean_t(f: list, ti: list, lag: int) -> float | None:
    """序列平均的 Newey–West t（同「對常數項做 OLS」的 HAC，不做小樣本校正）。"""
    n = len(f)
    if n < 2:
        return None
    mu = sum(f) / n
    u = [x - mu for x in f]
    s = 0.0
    for a in range(n):
        s += u[a] * u[a]
        b = a - 1
        while b >= 0 and ti[a] - ti[b] <= lag:
            d = ti[a] - ti[b]
            if d > 0:
                s += 2.0 * (1.0 - d / (lag + 1.0)) * u[a] * u[b]
            b -= 1
    var = s / (n * n)
    return mu / math.sqrt(var) if var > 0 else None


# ── 移動區塊重抽（區塊動差前綴和） ─────────────────────────────────────

def boot_ols(X: list, y: list, L: int, combos: list, n_boot: int | None = None, seed: int | None = None) -> list | None:
    """移動區塊重抽（X、y 的列依時間排好）：每次抽區塊（長 L，heatrel._draws，最後一塊截斷）湊滿 n 列，
    用區塊動差前綴和算 X'X、X'y 再解（和把抽到的列接起來重跑 OLS 相同）。
    combos＝[係數的權重向量]；→ 每個 combo 一串重抽值（不滿秩的那一次跳過）；成功不到一半回 None。"""
    n_boot = S.M6_BOOT if n_boot is None else n_boot
    n, k = len(X), len(X[0])
    pairs = [(a, c) for a in range(k) for c in range(a, k)]
    npair = len(pairs)
    pre = [[0.0] * (npair + k)]
    for row, yi in zip(X, y):
        cur = [row[a] * row[c] for a, c in pairs] + [r * yi for r in row]
        pre.append([u + v for u, v in zip(pre[-1], cur)])
    rnd = random.Random(S.M6_SEED if seed is None else seed)
    out: list = [[] for _ in combos]
    for _ in range(n_boot):
        acc = [0.0] * (npair + k)
        for s, ln in RL._draws(rnd, n, L):
            acc = [a + u - v for a, u, v in zip(acc, pre[s + ln], pre[s])]
        A = [[0.0] * k for _ in range(k)]
        for (a, c), v in zip(pairs, acc):
            A[a][c] = A[c][a] = v
        beta = solve(A, acc[npair:])
        if beta is None:
            continue
        for o, w in zip(out, combos):
            o.append(_dot(w, beta))
    if len(out[0]) < n_boot // 2:
        return None
    return out


def boot_p(reps: list) -> float:
    """p＝2 × 落在 0 另一側的比例（最多 1）。"""
    n = len(reps)
    below = sum(1 for v in reps if v <= 0) / n
    above = sum(1 for v in reps if v >= 0) / n
    return min(1.0, 2.0 * min(below, above))


def reg(ym: list, y: list, xs: list, m: int, *, focus: int = 1, lin: dict | None = None, boot: bool = True,
        keep: list | None = None) -> dict:
    """y、xs＝每月序列（同長度，None＝沒有）；回歸 y ~ 1 ＋ xs，只用全部有值（而且 keep[t] 為真）的月份，依月份排好。
    focus＝要看的係數（含截距的索引，1＝第一個變數）；lin＝另外要的線性組合 {名稱: 權重向量}。
    → {"n", "a", "z", "b", "t"（Newey–West）, "lo", "hi", "p"（重抽）, "h1", "h2"（前後兩半的係數）, "lin"}"""
    rows = [t for t in range(len(y)) if y[t] is not None and (keep is None or keep[t])
            and all(x[t] is not None for x in xs)]
    n = len(rows)
    out = {"n": n, "a": ym[rows[0]] if rows else None, "z": ym[rows[-1]] if rows else None,
           "b": None, "t": None, "lo": None, "hi": None, "p": None, "h1": None, "h2": None}
    if n < S.M6_MIN_N:
        return out
    X = [[1.0] + [x[t] for x in xs] for t in rows]
    Y = [y[t] for t in rows]
    f = ols(X, Y)
    if f is None:
        return out
    k = len(X[0])
    unit = [1.0 if i == focus else 0.0 for i in range(k)]
    beta = f["beta"]
    out["b"] = beta[focus]
    v = nw_var(unit, X, f, rows, nw_lag(m))
    out["t"] = out["b"] / math.sqrt(v) if v > 0 else None
    half = n // 2
    for key, sl in (("h1", slice(0, half)), ("h2", slice(half, n))):
        g = ols(X[sl], Y[sl])
        out[key] = g["beta"][focus] if g else None
    if lin:
        out["lin"] = {nm: {"b": _dot(w, beta), "lo": None, "hi": None, "p": None} for nm, w in lin.items()}
    if boot:
        reps = boot_ols(X, Y, block(m), [unit] + list((lin or {}).values()))
        if reps:
            out["lo"], out["hi"] = RL._q(reps[0])
            out["p"] = boot_p(reps[0])
            for nm, rr in zip(lin or {}, reps[1:]):
                lo, hi = RL._q(rr)
                out["lin"][nm].update(lo=lo, hi=hi, p=boot_p(rr))
    return out


def l1_of(ym: list, R: dict, x: list, r1: list, r12: list, boot: bool = True) -> dict:
    """L1：R(t; k, m) ~ 1 ＋ x ＋ 過去 1、12 個月報酬，延遲視窗（d）與累積期間（c）各跑一次。"""
    return {"d": {wkey(w): reg(ym, R[w], [x, r1, r12], w[1], boot=boot) for w in DELAY},
            "c": {wkey(w): reg(ym, R[w], [x, r1, r12], w[1], boot=boot) for w in CUM}}


def brief(l1: dict) -> dict:
    """穩健度（v1、v2）只留月數、係數、t 與前後兩半。"""
    return {part: {ws: {kk: e[kk] for kk in ("n", "b", "t", "h1", "h2")} for ws, e in d.items()} for part, d in l1.items()}


# ── 每月樣本 ─────────────────────────────────────────────────────────

def daily_d1(N: dict, spec: dict) -> tuple[list, list]:
    """來源日期上的一階（和 heatpos._daily_d 同一套：先取 smooth 筆平均，再和 L1 筆前比）→ (日期, 一階；沒有＝None)。"""
    ks = sorted(d for d, v in N.items() if v is not None)
    vs = [N[d] for d in ks]
    if spec.get("smooth"):
        vs = H.roll_mean(vs, spec["smooth"])
    d1: list = [None] * len(vs)
    for i, v in enumerate(vs):
        if v is None:
            continue
        if spec["d1"] == "self":
            d1[i] = v
        elif spec["d1"] == "minus50":
            d1[i] = v - 50.0
        else:
            j = i - spec["L1"]
            b = vs[j] if j >= 0 else None
            if b is None:
                continue
            if spec["d1"] == "chg":
                d1[i] = v - b
            elif b:
                d1[i] = 100.0 * (v / b - 1.0)
    return ks, d1


def d2_list(d1: list, L2: int, variant: str) -> list:
    """依筆數的一階 → 二階：v0＝L2 筆變化；v1＝先取 L2 筆平均再算 L2 筆變化；v2＝2 × L2 筆變化。"""
    if variant == "v1":
        src, lag = H.roll_mean(d1, L2), L2
    else:
        src, lag = d1, (L2 if variant == "v0" else 2 * L2)
    return [None if i < lag or src[i] is None or src[i - lag] is None else src[i] - src[i - lag] for i in range(len(src))]


def d2_monthly(d1: dict, L2: int, variant: str) -> dict:
    """月份上的一階 {YYYY-MM: 值} → 二階（同 d2_list，以月份相減；缺月就沒有）。"""
    if variant == "v1":
        src = {}
        for ym in d1:
            xs = [d1.get(C.ym_add(ym, -j)) for j in range(L2)]
            if all(x is not None for x in xs):
                src[ym] = sum(xs) / L2
        lag = L2
    else:
        src, lag = d1, (L2 if variant == "v0" else 2 * L2)
    out = {}
    for ym, v in src.items():
        b = src.get(C.ym_add(ym, -lag))
        if b is not None:
            out[ym] = v - b
    return out


def item_native(B: dict, k: str) -> dict:
    """核心訊號 k 的一階、三個版本的二階（月資料：{月份: 值}；日資料：{來源日期: 值}）。"""
    spec = S.DERIV[k]
    if S.FREQ_OF[k] == "m":
        d1 = P._monthly_d(B["mraw"].get(k) or {}, spec)[0]
        return {"d1": d1, "d2": {v: d2_monthly(d1, spec["L2"], v) for v in S.M6_VARIANTS}}
    ks, d1 = daily_d1(B["nat"].get(k) or {}, spec)
    pack = lambda xs: {d: x for d, x in zip(ks, xs) if x is not None}   # noqa: E731
    return {"d1": pack(d1), "d2": {v: pack(d2_list(d1, spec["L2"], v)) for v in S.M6_VARIANTS}}


def _pct_monthly(d: dict, dates: list, rel: tuple) -> list:
    """月序列在過去 120 個月（有值的筆數）的百分位，換成每個日期當下拿得到的值。"""
    ks = sorted(d)
    p = H.pct_series([d[x] for x in ks], S.DERIV_PCT_WIN["m"], S.DERIV_PCT_MIN["m"])
    return H.asof_monthly(dates, {x: q for x, q in zip(ks, p) if q is not None}, rel)


def item_panel(B: dict, k: str, me: list, dates: list, nat: dict | None = None) -> dict:
    """核心訊號 k 在每個月底：X2[v]（二階百分位換成 −1～1）、S2[v]（原始二階的正負號）、X1、D1（原始一階）、XL（水準）。"""
    nat = nat if nat is not None else item_native(B, k)
    out: dict = {"X2": {}, "S2": {}}
    if S.FREQ_OF[k] == "m":
        rel = S.RELEASE[k]
        out["D1"] = H.asof_monthly(dates, nat["d1"], rel)
        out["X1"] = [_scale(q) for q in _pct_monthly(nat["d1"], dates, rel)]
        for v in S.M6_VARIANTS:
            out["X2"][v] = [_scale(q) for q in _pct_monthly(nat["d2"][v], dates, rel)]
            out["S2"][v] = [_sign(x) for x in H.asof_monthly(dates, nat["d2"][v], rel)]
    else:
        cal = B["cal"]
        after, stale = k in S.US, S.STALE.get(k, 7)
        win, mn = S.DERIV_PCT_WIN["d"], S.DERIV_PCT_MIN["d"]
        a1 = H.asof_daily(cal, nat["d1"], after=after, stale=stale)
        p1 = H.pct_series(a1, win, mn)
        out["D1"] = [a1[i] for i in me]
        out["X1"] = [_scale(p1[i]) for i in me]
        for v in S.M6_VARIANTS:
            a2 = H.asof_daily(cal, nat["d2"][v], after=after, stale=stale)
            p2 = H.pct_series(a2, win, mn)
            out["X2"][v] = [_scale(p2[i]) for i in me]
            out["S2"][v] = [_sign(a2[i]) for i in me]
    hc = B["hc"].get(k) or [None] * len(B["cal"])
    out["XL"] = [_scale(hc[i]) for i in me]
    return out


def share_up(ss: list, mn: int):
    """有值的原始二階正負號裡 > 0 的比例，換成 −1～1（(比例 × 100 − 50) ÷ 50）；有值的不到 mn 個回 None。"""
    v = [x for x in ss if x is not None]
    return None if len(v) < mn else 2.0 * sum(1 for x in v if x > 0) / len(v) - 1.0


def groups_of(it: dict, T: int, variants=S.M6_VARIANTS) -> tuple[dict, dict, dict]:
    """→ (GA[v][組], LV[組], DI[v])：組加速度＝組內有值的 X2 平均；組水準＝XL 平均；
    加速擴散＝13 項裡原始二階 > 0 的比例，換成 −1～1（(比例 × 100 − 50) ÷ 50）。"""
    GA = {v: {} for v in variants}
    LV = {}
    for g, keys in S.M6_GROUPS.items():
        mn = S.M6_GROUP_MIN[g]
        for v in variants:
            GA[v][g] = [_gmean([it[k]["X2"][v][t] if it.get(k) else None for k in keys], mn) for t in range(T)]
        LV[g] = [_gmean([it[k]["XL"][t] if it.get(k) and "XL" in it[k] else None for k in keys], mn) for t in range(T)]
    DI = {v: [share_up([it[k]["S2"][v][t] for k in ITEMS if it.get(k)], S.M6_DI_MIN) for t in range(T)]
          for v in variants}
    return GA, LV, DI


def shares_of(it: dict, T: int, v: str = S.M6_MAIN_VARIANT) -> dict:
    """對照圖的組線：組內原始二階 > 0 的比例（−1～1；至少 M6_GROUP_MIN 項有值）。"""
    return {g: [share_up([it[k]["S2"][v][t] for k in keys if it.get(k)], S.M6_GROUP_MIN[g]) for t in range(T)]
            for g, keys in S.M6_GROUPS.items()}


def panel(B: dict) -> dict:
    """每月樣本（每個月最後一個交易日；最後一個月可能還沒結束，它的報酬算不出來，只當「現在」）。"""
    cal, px = B["cal"], B["px"]
    me = RL.month_ends(cal)
    ym = [cal[i][:7] for i in me]
    for a, b in zip(ym, ym[1:]):
        if C.ym_add(a, 1) != b:
            raise ValueError(f"交易日曆缺月份：{a} → {b}")
    dates = [cal[i] for i in me]
    T = len(me)

    def lp(j: int):
        return math.log(px[j]) if j < len(px) and px[j] else None
    lnx = [lp(i + S.M6_LAG) for i in me]                    # 月底的下一個交易日收盤
    lme = [lp(i) for i in me]
    R = {}
    for k, m in WINDOWS:
        R[(k, m)] = [None if t + k + m >= T or lnx[t + k + m] is None or lnx[t + k] is None
                     else lnx[t + k + m] - lnx[t + k] for t in range(T)]
    ctrl = {}
    for c in S.M6_CTRL:
        ctrl[c] = [None if t < c or lme[t] is None or lme[t - c] is None else lme[t] - lme[t - c] for t in range(T)]
    pme = [px[i] for i in me]
    n_ma = S.M6_MA_MONTHS
    bull = []
    for t in range(T):
        w = pme[t - n_ma + 1:t + 1] if t >= n_ma - 1 else []
        bull.append(None if len(w) < n_ma or any(p is None for p in w) else (1.0 if pme[t] > sum(w) / n_ma else 0.0))
    g1 = B["raw"].get("G1") or [None] * len(cal)
    hike = [None if g1[i] is None else (1.0 if g1[i] > 0 else 0.0) for i in me]
    nat = {k: item_native(B, k) for k in ITEMS}
    it = {k: item_panel(B, k, me, dates, nat[k]) for k in ITEMS}
    GA, LV, DI = groups_of(it, T)
    return {"T": T, "ym": ym, "dates": dates, "me": me, "R": R, "r1": ctrl[S.M6_CTRL[0]], "r12": ctrl[S.M6_CTRL[1]],
            "BULL": bull, "HIKE": hike, "it": it, "nat": nat, "GA": GA, "LV": LV, "DI": DI, "SH": shares_of(it, T)}


# ── 狀態表、轉折事件 ─────────────────────────────────────────────────

def item_labels(Pn: dict, k: str) -> list:
    """水準 ≥ 50（XL ≥ 0）或 < 50 × 加速（原始二階 > 0）或其他（≤ 0）。"""
    it = Pn["it"][k]
    out = []
    for xl, s in zip(it["XL"], it["S2"][S.M6_MAIN_VARIANT]):
        out.append(None if xl is None or s is None else ("hi" if xl >= 0 else "lo") + ("_acc" if s > 0 else "_dec"))
    return out


def group_labels(Pn: dict, v: str = S.M6_MAIN_VARIANT) -> list:
    out = []
    for g, r in zip(Pn["GA"][v]["grow"], Pn["GA"][v]["rate"]):
        out.append(None if g is None or r is None else ("gA" if g > 0 else "gD") + ("_rA" if r > 0 else "_rD"))
    return out


def state_tab(Pn: dict, labels: list, names: tuple, h: int) -> dict:
    """每個狀態之後 h 個月的累積報酬 R(t; 0, h)：月數、段數、平均、和所有月份比的差［區塊重抽］、前後兩半、判定。"""
    T, ym, R = Pn["T"], Pn["ym"], Pn["R"][(0, h)]
    rows = [t for t in range(T) if labels[t] is not None and R[t] is not None]
    r = [R[t] for t in rows]
    all_avg = _mean(r)
    half = len(rows) // 2
    out = {}
    for s in names:
        flag = [labels[t] == s for t in rows]
        n = sum(flag)
        runs = sum(1 for i, f in enumerate(flag) if f and (i == 0 or not flag[i - 1] or rows[i] != rows[i - 1] + 1))
        sel = [x for x, f in zip(r, flag) if f]
        e = {"n": n, "runs": runs, "avg": _mean(sel), "all": all_avg, "up": (sum(1 for x in sel if x > 0) / n) if n else None,
             "diff": None, "lo": None, "hi": None, "d1": None, "d2": None, "verdict": "few",
             "yrs": sorted({ym[t][:4] for t, f in zip(rows, flag) if f})}
        if e["avg"] is not None and all_avg is not None:
            e["diff"] = e["avg"] - all_avg
        if n:
            e["lo"], e["hi"] = TT.boot_diff(r, flag, block(h), S.M6_BOOT, S.M6_SEED)
        for key, rng in (("d1", range(0, half)), ("d2", range(half, len(rows)))):
            a = [r[i] for i in rng]
            b = [r[i] for i in rng if flag[i]]
            if a and b:
                e[key] = _mean(b) - _mean(a)
        nmin, rmin = S.M6_STATE_MIN
        if n >= nmin and runs >= rmin and None not in (e["lo"], e["hi"], e["d1"], e["d2"]):
            if e["lo"] > 0 and e["d1"] > 0 and e["d2"] > 0:
                e["verdict"] = "strong"
            elif e["hi"] < 0 and e["d1"] < 0 and e["d2"] < 0:
                e["verdict"] = "weak"
            else:
                e["verdict"] = "none"
        out[s] = e
    return out


def turn_events(s: list, d1: list) -> list[tuple[int, int]]:
    """原始二階的正負號 s[t]：t 與 t − 1 同號 σ（≠ 0），而且 t − 1 之前最近一個不是 0 的正負號是 −σ（中間只能是 0、不能沒有值）
    → [(t, 種類)]；事件月＝新方向的第 2 個月。種類依一階正負（heatpos.state_of：1 加速、2 趨緩、3 加劇、4 收斂），一階 0 或沒有＝0。"""
    out = []
    for t in range(2, len(s)):
        a = s[t]
        if a is None or a == 0 or s[t - 1] != a:
            continue
        j = t - 2
        while j >= 0 and s[j] == 0:
            j -= 1
        if j < 0 or s[j] is None or s[j] != -a:
            continue
        out.append((t, P.state_of(d1[t], a) or 0))
    return out


def event_stats(Pn: dict, base_t: list, et: list, h: int) -> dict:
    """事件月之後 h 個月 vs 所有月份（base_t）：差、區塊重抽（區塊 12 個月）、前後兩半（依事件數切）、判定。"""
    R = Pn["R"][(0, h)]
    base = [t for t in base_t if R[t] is not None]
    ise = set(et)
    evs = [t for t in base if t in ise]
    allr = [R[t] for t in base]
    out = {"n": len(evs), "avg": _mean([R[t] for t in evs]), "all": _mean(allr), "diff": None, "lo": None, "hi": None,
           "h1": None, "h2": None, "verdict": "few"}
    if out["avg"] is not None and out["all"] is not None:
        out["diff"] = out["avg"] - out["all"]
    out["lo"], out["hi"] = TT.boot_diff(allr, [t in ise for t in base], S.M6_BLOCK_MIN, S.M6_BOOT, S.M6_SEED)
    if len(evs) >= 2:
        m = len(evs) // 2
        cut = evs[m]
        for key, part, ok in (("h1", evs[:m], lambda t: t < cut), ("h2", evs[m:], lambda t: t >= cut)):
            a = [R[t] for t in base if ok(t)]
            if a and part:
                out[key] = _mean([R[t] for t in part]) - _mean(a)
    if out["n"] >= S.M6_EVENT_MIN and None not in (out["lo"], out["hi"], out["h1"], out["h2"]):
        if out["lo"] > 0 and out["h1"] > 0 and out["h2"] > 0:
            out["verdict"] = "strong"
        elif out["hi"] < 0 and out["h1"] < 0 and out["h2"] < 0:
            out["verdict"] = "weak"
        else:
            out["verdict"] = "none"
    return out


def l6_item(Pn: dict, k: str) -> dict:
    """平滑版（v1）二階翻正、翻負之後 1～24 個月的累積報酬路徑（依一階分四種），和所有月份比。"""
    it, ym, T = Pn["it"][k], Pn["ym"], Pn["T"]
    s = it["S2"]["v1"]
    evs = turn_events(s, it["D1"])
    base_t = [t for t in range(T) if s[t] is not None]
    out = {"n": len(evs), "flat": sum(1 for _, kd in evs if kd == 0),
           "base": [_mean([Pn["R"][(0, h)][t] for t in base_t if Pn["R"][(0, h)][t] is not None]) for h in PATH_H],
           "kinds": {}}
    for kd in (1, 2, 3, 4):
        et = [t for t, x in evs if x == kd]
        e = {"n": len(et), "dates": [ym[t] for t in et], "path": [], "h": {}}
        for h in PATH_H:
            R = Pn["R"][(0, h)]
            e["path"].append(_mean([R[t] for t in et if R[t] is not None]))
        for h in S.M6_STATE_H:
            e["h"][str(h)] = event_stats(Pn, base_t, et, h)
        out["kinds"][str(kd)] = e
    return out


# ── 樣本外 ───────────────────────────────────────────────────────────

class Inc:
    """擴張視窗的 OLS：列一筆一筆加入，累加 X'X、X'y、y'y；fit() → (係數, 殘差平方和)。"""
    __slots__ = ("k", "A", "v", "yy", "sy", "n")

    def __init__(self, k: int):
        self.k = k
        self.A = [[0.0] * k for _ in range(k)]
        self.v = [0.0] * k
        self.yy = self.sy = 0.0
        self.n = 0

    def add(self, x: list, y: float) -> None:
        A, v, k = self.A, self.v, self.k
        for a in range(k):
            xa = x[a]
            v[a] += xa * y
            Aa = A[a]
            for c in range(a, k):
                Aa[c] += xa * x[c]
        self.yy += y * y
        self.sy += y
        self.n += 1

    def fit(self) -> tuple[list, float] | None:
        k, A = self.k, self.A
        M = [[A[min(a, c)][max(a, c)] for c in range(k)] for a in range(k)]
        b = solve(M, self.v)
        if b is None:
            return None
        return b, self.yy - _dot(b, self.v)


class Ridge:
    """擴張視窗的脊回歸：列依月份加入（前綴和）。每次預測：變數用訓練期平均與標準差（母體）標準化，標準差 0 的欄位不用；
    懲罰＝λ × 列數 × 係數平方和（截距不懲罰）；λ 用 5 段時間序列交叉驗證選（連續分段，驗證段前後各空出 m 個月，
    驗證誤差平方和加總最小；同值取較小的 λ）。"""

    def __init__(self, p: int):
        self.p = p
        self.pairs = [(a, c) for a in range(p) for c in range(a, p)]
        self.ts: list[int] = []
        self.pre = [[0.0] * (1 + 2 * p + len(self.pairs) + 2)]

    def add(self, x: list, y: float, t: int) -> None:
        cur = [1.0] + list(x) + [x[a] * x[c] for a, c in self.pairs] + [xi * y for xi in x] + [y, y * y]
        self.pre.append([u + v for u, v in zip(self.pre[-1], cur)])
        self.ts.append(t)

    def n(self) -> int:
        return len(self.ts)

    def _rng(self, a: int, b: int) -> list:
        return [u - v for u, v in zip(self.pre[b], self.pre[a])]

    def _system(self, s: list, mu: list, rho: list) -> tuple[list, list, float, float]:
        """區間加總 → 標準化之後的 [1, x̃] 的 Z'Z、Z'y、y'y、列數。"""
        p, npair = self.p, len(self.pairs)
        n = s[0]
        S1 = s[1:1 + p]
        S2 = s[1 + p:1 + p + npair]
        Sxy = s[1 + p + npair:1 + 2 * p + npair]
        Sy, Syy = s[-2], s[-1]
        G = [[0.0] * (p + 1) for _ in range(p + 1)]
        G[0][0] = n
        for a in range(p):
            G[0][a + 1] = G[a + 1][0] = (S1[a] - n * mu[a]) * rho[a]
        for (a, c), v in zip(self.pairs, S2):
            G[a + 1][c + 1] = G[c + 1][a + 1] = (v - mu[a] * S1[c] - mu[c] * S1[a] + n * mu[a] * mu[c]) * rho[a] * rho[c]
        r = [Sy] + [(Sxy[a] - mu[a] * Sy) * rho[a] for a in range(p)]
        return G, r, Syy, n

    def _fit(self, G: list, r: list, lam: float, n: float) -> list | None:
        A = [row[:] for row in G]
        for j in range(1, self.p + 1):
            A[j][j] += lam * n
        return solve(A, r)

    def stdz(self) -> tuple[list, list]:
        p, n = self.p, self.n()
        tot = self.pre[-1]
        mu = [tot[1 + a] / n for a in range(p)]
        diag = {a: tot[1 + p + i] for i, (a, c) in enumerate(self.pairs) if a == c}
        rho = []
        for a in range(p):
            var = diag[a] / n - mu[a] * mu[a]
            rho.append(1.0 / math.sqrt(var) if var > 1e-12 else 0.0)
        return mu, rho

    def cv(self, m: int, mu: list, rho: list, lams=S.M6_RIDGE_LAMBDA, folds: int = S.M6_CV_FOLDS) -> list:
        """每個 λ 的交叉驗證誤差平方和。"""
        n = self.n()
        tot = self.pre[-1]
        out = [0.0] * len(lams)
        a = 0
        for f in range(folds):
            b = a + n // folds + (1 if f < n % folds else 0)
            lo = bisect.bisect_left(self.ts, self.ts[a] - m)
            hi = bisect.bisect_right(self.ts, self.ts[b - 1] + m)
            tr = [u - v for u, v in zip(tot, self._rng(lo, hi))]
            Gt, rt, _, nt = self._system(tr, mu, rho)
            Gv, rv, yyv, _ = self._system(self._rng(a, b), mu, rho)
            for li, lam in enumerate(lams):
                th = self._fit(Gt, rt, lam, nt) if nt > 0 else None
                if th is None:
                    out[li] = math.inf
                    continue
                out[li] += yyv - 2.0 * _dot(th, rv) + sum(th[i] * _dot(Gv[i], th) for i in range(len(th)))
            a = b
        return out

    def predict(self, x: list, m: int) -> tuple[float, float] | None:
        mu, rho = self.stdz()
        errs = self.cv(m, mu, rho)
        li = min(range(len(errs)), key=lambda i: errs[i])
        lam = S.M6_RIDGE_LAMBDA[li]
        G, r, _, n = self._system(self.pre[-1], mu, rho)
        th = self._fit(G, r, lam, n)
        if th is None:
            return None
        z = [1.0] + [(xi - mi) * ri for xi, mi, ri in zip(x, mu, rho)]
        return _dot(th, z), lam


def tree_fit(X: list, y: list, depth: int = S.M6_TREE["depth"], min_leaf: int = S.M6_TREE["min_leaf"],
             cuts: tuple = S.M6_TREE["cuts"]):
    """深度 2 的回歸樹：每個節點試每個變數的 10%～90% 分位點（節點內排序後第 ⌊q × (n − 1) ÷ 100⌋ 個值），x ≤ 分點往左；
    兩邊都要 ≥ min_leaf 列；挑殘差平方和最小的（同值取先試到的：變數順序、分位點順序），比不分還小才分。
    → 節點：("leaf", 平均) 或 ("split", 變數索引, 分點, 左, 右, 列數)。"""
    p = len(X[0]) if X else 0

    def build(idx: list, d: int):
        n = len(idx)
        ys = [y[i] for i in idx]
        mean = sum(ys) / n
        if d == 0 or n < 2 * min_leaf:
            return ("leaf", mean, n)
        sse0 = sum((v - mean) ** 2 for v in ys)
        best = None
        for j in range(p):
            order = sorted(idx, key=lambda i: (X[i][j], i))
            vals = [X[i][j] for i in order]
            cy, cyy = [0.0], [0.0]
            for i in order:
                cy.append(cy[-1] + y[i])
                cyy.append(cyy[-1] + y[i] * y[i])
            seen = set()
            for q in cuts:
                c = vals[(q * (n - 1)) // 100]
                if c in seen:
                    continue
                seen.add(c)
                nl = bisect.bisect_right(vals, c)
                nr = n - nl
                if nl < min_leaf or nr < min_leaf:
                    continue
                sl, ql = cy[nl], cyy[nl]
                sr, qr = cy[n] - sl, cyy[n] - ql
                sse = (ql - sl * sl / nl) + (qr - sr * sr / nr)
                if best is None or sse < best[0] - 1e-12:
                    best = (sse, j, c, order[:nl], order[nl:])
        if best is None or best[0] >= sse0 - 1e-12:
            return ("leaf", mean, n)
        return ("split", best[1], best[2], build(best[3], d - 1), build(best[4], d - 1), n)

    return build(list(range(len(y))), depth)


def tree_predict(node, x: list) -> float:
    while node[0] == "split":
        node = node[3] if x[node[1]] <= node[2] else node[4]
    return node[1]


def tree_desc(node, names: tuple) -> dict:
    if node[0] == "leaf":
        return {"leaf": node[1], "n": node[2]}
    return {"x": names[node[1]], "cut": node[2], "n": node[5],
            "le": tree_desc(node[3], names), "gt": tree_desc(node[4], names)}


def cw_test(y: list, fs: list, fb: list, ti: list, lag: int) -> tuple[float | None, float | None]:
    """Clark–West（大模型 fb 對小模型 fs，單尾）：f＝(y − fs)² − [(y − fb)² − (fs − fb)²] 的平均 > 0；Newey–West t。"""
    f = [(yi - a) ** 2 - ((yi - b) ** 2 - (a - b) ** 2) for yi, a, b in zip(y, fs, fb)]
    t = nw_mean_t(f, ti, lag)
    return t, (None if t is None else 1.0 - _ncdf(t))


def terciles(pred: list, y: list) -> list:
    """依預測值排序分三組（同值依時間）→ 每組的月數、平均預測、實際平均報酬。"""
    idx = sorted(range(len(pred)), key=lambda i: (pred[i], i))
    n = len(idx)
    c1, c2 = round(n / 3), round(2 * n / 3)
    return [{"n": len(g), "pred": _mean([pred[i] for i in g]), "avg": _mean([y[i] for i in g])}
            for g in (idx[:c1], idx[c1:c2], idx[c2:])]


def oos_metrics(rec: list, m: int, ym: list, models: tuple, pairs: tuple) -> dict:
    """rec＝[{"t", "y", 模型: 預測, ...}]（依月份）→ 月數、期間、各模型 R²（對過去平均 m0、對 m1）、命中率、三分組、Clark–West。"""
    n = len(rec)
    out = {"n": n, "a": ym[rec[0]["t"]] if rec else None, "z": ym[rec[-1]["t"]] if rec else None,
           "few": n < S.M6_OOS_MIN_PRED, "models": {}, "cw": {}}
    if not n:
        return out
    y = [r["y"] for r in rec]
    ti = [r["t"] for r in rec]
    sse = {mo: sum((r["y"] - r[mo]) ** 2 for r in rec) for mo in models}
    for mo in models:
        e = {"hit": sum(1 for r in rec if (r[mo] > 0) == (r["y"] > 0)) / n}
        if mo != "m0":
            e["r2_0"] = 1.0 - sse[mo] / sse["m0"] if sse["m0"] > 0 else None
            e["terc"] = terciles([r[mo] for r in rec], y)
        if mo not in ("m0", "m1") and "m1" in sse:
            e["r2_1"] = 1.0 - sse[mo] / sse["m1"] if sse["m1"] > 0 else None
        out["models"][mo] = e
    lag = nw_lag(m)
    for a, b in pairs:
        t, p = cw_test(y, [r[a] for r in rec], [r[b] for r in rec], ti, lag)
        out["cw"][f"{b}>{a}"] = {"t": t, "p": p, "r2": 1.0 - sse[b] / sse[a] if sse[a] > 0 else None}
    for key in ("v_m2", "v_m3", "lam"):
        vals = [r[key] for r in rec if key in r]
        if vals:
            out[key] = {str(v): vals.count(v) for v in sorted(set(vals), key=str)}
    return out


def oos_item_rec(Pn: dict, k: str, w: tuple) -> list:
    """單項：M0＝過去平均、M1＝XL＋控制變數、M2＝M1＋X2（版本取訓練期殘差平方和最小的）。
    每個預測月份 τ：訓練＝t ＋ k ＋ m ＜ τ 而且全部變數有值的月份（至少 96 個月）。"""
    kk, mm = w
    T, R, ym = Pn["T"], Pn["R"][w], Pn["ym"]
    it = Pn["it"][k]
    XL, X2, r1, r12 = it["XL"], it["X2"], Pn["r1"], Pn["r12"]
    V = S.M6_VARIANTS

    def feats(t: int):
        x = [1.0, XL[t], r1[t], r12[t]]
        if any(v is None for v in x) or any(X2[v][t] is None for v in V):
            return None
        return x
    t0 = next((t for t in range(T) if ym[t] >= S.M6_OOS_START), T)
    inc1 = Inc(4)
    inc2 = {v: Inc(5) for v in V}
    nxt, last, rec = 0, None, []
    for tau in range(t0, T):
        while nxt <= tau - kk - mm - 1:
            t = nxt
            nxt += 1
            x = feats(t)
            if x is None or R[t] is None:
                continue
            inc1.add(x, R[t])
            for v in V:
                inc2[v].add(x + [X2[v][t]], R[t])
            last = t
        x = feats(tau)
        if x is None or R[tau] is None or inc1.n < S.M6_MIN_N:
            continue
        f1 = inc1.fit()
        fits = [(f, v) for f, v in ((inc2[v].fit(), v) for v in V) if f is not None]
        if f1 is None or not fits:
            continue
        (b2, _), v2 = min(fits, key=lambda fv: fv[0][1])
        rec.append({"t": tau, "y": R[tau], "m0": inc1.sy / inc1.n, "m1": _dot(f1[0], x),
                    "m2": _dot(b2, x + [X2[v2][tau]]), "v_m2": v2, "ntr": inc1.n, "last": last})
    return rec


def oos_item(Pn: dict, k: str, w: tuple) -> dict:
    return oos_metrics(oos_item_rec(Pn, k, w), w[1], Pn["ym"], ("m0", "m1", "m2"), (("m1", "m2"),))


def gvars(Pn: dict, t: int, v: str) -> dict | None:
    """組層的變數（版本 v 的組加速度、加速擴散）；有一個沒有值就回 None。"""
    d = {"GA_grow": Pn["GA"][v]["grow"][t], "GA_rate": Pn["GA"][v]["rate"][t], "LV_grow": Pn["LV"]["grow"][t],
         "LV_rate": Pn["LV"]["rate"][t], "DI": Pn["DI"][v][t], "BULL": Pn["BULL"][t], "HIKE": Pn["HIKE"][t]}
    if any(x is None for x in d.values()):
        return None
    for nm in set(S.M6_RIDGE_X) | set(M3_G):
        if "*" in nm:
            a, b = nm.split("*")
            d[nm] = d[a] * d[b]
    return d


def oos_group_rec(Pn: dict, w: tuple) -> tuple[list, object]:
    """組：M0、M1＝LV_grow＋LV_rate、M2＝M1＋GA_grow＋GA_rate、M3＝M2＋三個交互（M2、M3 版本取訓練期殘差平方和最小的；
    同一個版本用在所有項目）、脊回歸與決策樹（v0）。全部模型用同一組月份（每個版本的變數都有值）。→ (rec, 最後一次訓練的樹)"""
    kk, mm = w
    T, R, ym = Pn["T"], Pn["R"][w], Pn["ym"]
    V = S.M6_VARIANTS
    t0 = next((t for t in range(T) if ym[t] >= S.M6_OOS_START), T)
    inc1 = Inc(1 + len(M1_G))
    inc2 = {v: Inc(1 + len(M2_G)) for v in V}
    inc3 = {v: Inc(1 + len(M3_G)) for v in V}
    rid = Ridge(len(S.M6_RIDGE_X))
    tX, tY = [], []
    nxt, last, rec, tree = 0, None, [], None

    def allv(t: int):
        g = {v: gvars(Pn, t, v) for v in V}
        return None if any(x is None for x in g.values()) else g
    for tau in range(t0, T):
        while nxt <= tau - kk - mm - 1:
            t = nxt
            nxt += 1
            g = allv(t)
            if g is None or R[t] is None:
                continue
            y = R[t]
            inc1.add([1.0] + [g["v0"][x] for x in M1_G], y)
            for v in V:
                inc2[v].add([1.0] + [g[v][x] for x in M2_G], y)
                inc3[v].add([1.0] + [g[v][x] for x in M3_G], y)
            rid.add([g["v0"][x] for x in S.M6_RIDGE_X], y, t)
            tX.append([g["v0"][x] for x in S.M6_TREE_X])
            tY.append(y)
            last = t
        g = allv(tau)
        if g is None or R[tau] is None or inc1.n < S.M6_MIN_N:
            continue
        f1 = inc1.fit()
        if f1 is None:
            continue
        r = {"t": tau, "y": R[tau], "m0": inc1.sy / inc1.n, "m1": _dot(f1[0], [1.0] + [g["v0"][x] for x in M1_G]),
             "ntr": inc1.n, "last": last}
        ok = True
        for key, incs, names in (("m2", inc2, M2_G), ("m3", inc3, M3_G)):
            fits = [(f, v) for f, v in ((incs[v].fit(), v) for v in V) if f is not None]
            if not fits:
                ok = False
                break
            (b, _), v = min(fits, key=lambda fv: fv[0][1])
            r[key] = _dot(b, [1.0] + [g[v][x] for x in names])
            r["v_" + key] = v
        pr = rid.predict([g["v0"][x] for x in S.M6_RIDGE_X], mm) if ok else None
        if pr is None:
            continue
        r["ridge"], r["lam"] = pr
        tree = tree_fit(tX, tY)
        r["tree"] = tree_predict(tree, [g["v0"][x] for x in S.M6_TREE_X])
        rec.append(r)
    return rec, tree


def oos_group(Pn: dict, w: tuple) -> dict:
    rec, tree = oos_group_rec(Pn, w)
    out = oos_metrics(rec, w[1], Pn["ym"], ("m0", "m1", "m2", "m3", "ridge", "tree"),
                      (("m1", "m2"), ("m1", "m3"), ("m2", "m3"), ("m1", "ridge"), ("m0", "tree")))
    out["tree"] = tree_desc(tree, S.M6_TREE_X) if tree else None
    return out


# ── 主要假說 ─────────────────────────────────────────────────────────

def holm(ps: dict, alpha: float = S.M6_ALPHA) -> tuple[dict, dict]:
    """Holm 校正：→ (校正後的 p, 是否拒絕)；None 不算進家族。"""
    items = sorted((p, h) for h, p in ps.items() if p is not None)
    m = len(items)
    adj = {h: None for h in ps}
    rej = {h: False for h in ps}
    run, stop = 0.0, False
    for i, (p, h) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        adj[h] = run
        if not stop and p <= alpha / (m - i):
            rej[h] = True
        else:
            stop = True
    return adj, rej


def wald_states(ym: list, y: list, dums: list, ctrl: list, m: int) -> dict:
    """y ~ 1 ＋ 三個狀態虛擬變數 ＋ 控制變數：三個係數聯合為 0。重抽共變異數算 Wald；
    p＝以觀察值為中心的重抽 Wald ≥ 觀察 Wald 的比例。另列 Newey–West Wald（χ²，只列出）。"""
    xs = dums + ctrl
    rows = [t for t in range(len(y)) if y[t] is not None and all(x[t] is not None for x in xs)]
    n = len(rows)
    out = {"n": n, "a": ym[rows[0]] if rows else None, "z": ym[rows[-1]] if rows else None,
           "b": None, "w": None, "p": None, "nw_p": None}
    if n < S.M6_MIN_N:
        return out
    X = [[1.0] + [x[t] for x in xs] for t in rows]
    Y = [y[t] for t in rows]
    f = ols(X, Y)
    if f is None:
        return out
    k = len(X[0])
    q = len(dums)
    units = [[1.0 if i == j + 1 else 0.0 for i in range(k)] for j in range(q)]
    d = f["beta"][1:1 + q]
    out["b"] = d
    lag = nw_lag(m)
    Vn = [[0.0] * q for _ in range(q)]
    var = [nw_var(units[a], X, f, rows, lag) for a in range(q)]
    for a in range(q):
        for c in range(q):
            Vn[a][c] = var[a] if a == c else \
                (nw_var([u + v for u, v in zip(units[a], units[c])], X, f, rows, lag) - var[a] - var[c]) / 2.0
    wn = RL.wald(d, Vn, list(range(q)))
    out["nw_p"] = wn[1] if wn else None
    reps = boot_ols(X, Y, block(m), units)
    if not reps:
        return out
    R = list(zip(*reps))
    mu = [sum(c) / len(R) for c in reps]
    Vb = [[sum((r[a] - mu[a]) * (r[c] - mu[c]) for r in R) / (len(R) - 1) for c in range(q)] for a in range(q)]
    Vi = RL._inv(Vb)
    if Vi is None:
        return out
    quad = lambda u: sum(u[a] * Vi[a][c] * u[c] for a in range(q) for c in range(q))   # noqa: E731
    W = quad(d)
    Ws = [quad([r[a] - d[a] for a in range(q)]) for r in R]
    out["w"] = W
    out["p"] = sum(1 for x in Ws if x >= W) / len(Ws)
    return out


def primary(Pn: dict) -> dict:
    """H1～H4（規格 M6_PRIMARY）；Holm 校正、α 0.05。H3 是有方向的假說：要校正後顯著而且「減速」的係數 < 0 才算通過。"""
    ym, R, r1, r12 = Pn["ym"], Pn["R"], Pn["r1"], Pn["r12"]
    v0 = S.M6_MAIN_VARIANT
    GAg, LVg, DI = Pn["GA"][v0]["grow"], Pn["LV"]["grow"], Pn["DI"][v0]
    out = {}
    w = S.M6_PRIMARY["H1"][1]
    out["H1"] = reg(ym, R[w], [GAg, r1, r12], w[1])
    w = S.M6_PRIMARY["H2"][1]
    lab = group_labels(Pn)
    dums = [[None if s is None else (1.0 if s == st else 0.0) for s in lab] for st in GSTATES[:-1]]   # 基準＝兩個都減速
    out["H2"] = wald_states(ym, R[w], dums, [r1, r12], w[1])
    out["H2"]["states"] = state_tab(Pn, lab, GSTATES, w[1])
    w = S.M6_PRIMARY["H3"][1]
    dec = [None if g is None else (1.0 if g <= 0 else 0.0) for g in GAg]
    keep = [lv is not None and lv >= 0 for lv in LVg]
    out["H3"] = reg(ym, R[w], [dec, r1, r12], w[1], keep=keep)
    sub = [t for t in range(Pn["T"]) if keep[t] and dec[t] is not None and R[w][t] is not None]
    out["H3"]["n_dec"] = sum(1 for t in sub if dec[t] == 1.0)
    out["H3"]["n_acc"] = sum(1 for t in sub if dec[t] == 0.0)
    w = S.M6_PRIMARY["H4"][1]
    out["H4"] = reg(ym, R[w], [DI, r1, r12], w[1])
    adj, rej = holm({h: out[h]["p"] for h in S.M6_PRIMARY})
    for h in S.M6_PRIMARY:
        out[h]["holm"] = adj[h]
        out[h]["pass"] = rej[h] and (h != "H3" or (out[h]["b"] is not None and out[h]["b"] < 0))
        out[h]["what"] = S.M6_PRIMARY[h][0]
    return out


# ── 延伸樣本（國發會股價指數月平均） ──────────────────────────────────

def ext_panel(B: dict, Pn: dict, A: dict) -> dict | None:
    """1982 年起：報酬＝月平均的對數變化、視窗晚 M6_EXT_SHIFT 個月起算；控制變數也用月平均。訊號在主樣本的月份
    和主樣本相同；更早的月份用曆月最後一天、月資料照公布時間差，日資料沒有二階百分位（只有正負號給加速擴散用）。"""
    yms = sorted(x for x, v in A.items() if v)
    if not yms:
        return None
    months = [yms[0]]
    while months[-1] < yms[-1]:
        months.append(C.ym_add(months[-1], 1))
    main = {x: i for i, x in enumerate(Pn["ym"])}
    dates = [Pn["dates"][main[x]] if x in main else month_end_day(x) for x in months]
    T = len(months)
    la = [math.log(A[x]) if A.get(x) and A[x] > 0 else None for x in months]
    sh = S.M6_EXT_SHIFT
    R = {}
    for k, m in set(DELAY) | set(CUM) | {S.M6_PRIMARY["H1"][1], S.M6_PRIMARY["H4"][1]}:
        R[(k, m)] = [None if t + k + m + sh >= T or la[t + k + m + sh] is None or la[t + k + sh] is None
                     else la[t + k + m + sh] - la[t + k + sh] for t in range(T)]
    ctrl = {c: [None if t < c or la[t] is None or la[t - c] is None else la[t] - la[t - c] for t in range(T)]
            for c in S.M6_CTRL}
    v0 = S.M6_MAIN_VARIANT
    it = {}
    for k in ITEMS:
        nat = Pn["nat"][k]
        if S.FREQ_OF[k] == "m":
            rel = S.RELEASE[k]
            x2 = [_scale(q) for q in _pct_monthly(nat["d2"][v0], dates, rel)]
            s2 = [_sign(x) for x in H.asof_monthly(dates, nat["d2"][v0], rel)]
        else:
            src = Pn["it"][k]["X2"][v0]
            x2 = [src[main[x]] if x in main else None for x in months]
            s2 = [_sign(x) for x in H.asof_daily(dates, nat["d2"][v0], after=k in S.US, stale=S.STALE.get(k, 7))]
        it[k] = {"X2": {v0: x2}, "S2": {v0: s2}}
    GA, _, DI = groups_of(it, T, (v0,))
    return {"T": T, "ym": months, "R": R, "r1": ctrl[S.M6_CTRL[0]], "r12": ctrl[S.M6_CTRL[1]], "it": it,
            "GA": GA[v0], "DI": DI[v0]}


def ext_run(E: dict) -> dict:
    ym, r1, r12 = E["ym"], E["r1"], E["r12"]
    ser = {k: E["it"][k]["X2"][S.M6_MAIN_VARIANT] for k in ITEMS if S.FREQ_OF[k] == "m"}
    ser.update({"GA_grow": E["GA"]["grow"], "GA_rate": E["GA"]["rate"], "DI": E["DI"]})
    out = {"a": ym[0], "z": ym[-1], "T": E["T"], "l1": {}}
    for nm, x in ser.items():
        out["l1"][nm] = l1_of(ym, E["R"], x, r1, r12)
    for h, nm in (("H1", "GA_grow"), ("H4", "DI")):
        w = S.M6_PRIMARY[h][1]
        out[h] = reg(ym, E["R"][w], [ser[nm], r1, r12], w[1])
    return out


# ── 判定 ─────────────────────────────────────────────────────────────

def _bh(results: list) -> None:
    for r, q in zip(results, RL.bh([r.get("p") for r in results])):
        r["q"] = q


def _adj(d: dict, k: int) -> bool:
    """延遲視窗：前一個或後一個延遲視窗（k ∓ 3）的係數至少一個同號。"""
    b = d[wkey((k, S.M6_WIN))]["b"]
    i = S.M6_DELAY.index(k)
    for j in (i - 1, i + 1):
        if 0 <= j < len(S.M6_DELAY):
            e = d[wkey((S.M6_DELAY[j], S.M6_WIN))]
            if b is not None and e["b"] is not None and b != 0 and e["b"] != 0 and (e["b"] > 0) == (b > 0):
                return True
    return False


def verdict(e: dict, adj: bool, oo: dict | None) -> str:
    """pred＝有預測性；in_only＝樣本內看得到、樣本外沒有；in_untested＝樣本內看得到、這個期間沒有樣本外；none；few。"""
    if e["n"] < S.M6_MIN_N or e["b"] is None:
        return "few"
    b, h1, h2, q = e["b"], e["h1"], e["h2"], e.get("q")
    same = (b != 0 and h1 is not None and h2 is not None and h1 != 0 and h2 != 0
            and (h1 > 0) == (b > 0) and (h2 > 0) == (b > 0))
    if not (q is not None and q <= S.BH_Q and same and adj):
        return "none"
    if not oo or oo.get("few") or oo.get("r2") is None or oo.get("p") is None:
        return "in_untested"
    return "pred" if oo["r2"] > 0 and oo["p"] < S.M6_CW_ALPHA else "in_only"


def _oo(oos: dict | None, pair: str) -> dict | None:
    if not oos or pair not in oos.get("cw", {}):
        return None
    c = oos["cw"][pair]
    return {"few": oos["few"], "r2": c["r2"], "p": c["p"]}


def _judge(d: dict, oos: dict, pair: str, delay: bool) -> None:
    for ws, e in d.items():
        k, m = (int(x) for x in ws.split(","))
        e["v"] = verdict(e, _adj(d, k) if delay else True, _oo(oos.get(ws), pair) if (k, m) in S.M6_OOS_WINDOWS else None)


def summary_of(l1: dict) -> dict:
    """頁面精簡表：有證據的期間 [段（d＝延遲、c＝累積）, k, m, 正負, 判定] 與樣本外結論。"""
    react = [[part] + [int(x) for x in ws.split(",")] + [1 if e["b"] > 0 else -1, e["v"]]
             for part in ("d", "c") for ws, e in l1[part].items() if e.get("v") in ("pred", "in_only", "in_untested")]
    vs = [r[4] for r in react]
    if "pred" in vs:
        oos = "pred"
    elif "in_only" in vs:
        oos = "fail"
    elif vs:
        oos = "untested"
    elif all(e["n"] < S.M6_MIN_N for part in ("d", "c") for e in l1[part].values()):
        oos = "few"
    else:
        oos = "none"
    return {"react": react, "oos": oos}


def react_text(react: list) -> str:
    """[[段, k, m, 正負, 判定], ...] → 「6～12 個月後較弱、累積 12 個月較弱」（連續的延遲期間、同方向的併成一段）。"""
    step = S.M6_DELAY[1] - S.M6_DELAY[0]
    out, runs = [], []
    for r in sorted((r for r in react if r[0] == "d"), key=lambda r: r[1]):
        if runs and runs[-1][-1][3] == r[3] and r[1] - runs[-1][-1][1] == step:
            runs[-1].append(r)
        else:
            runs.append([r])
    for run in runs:
        out.append(f'{run[0][1]}～{run[-1][1] + run[-1][2]} 個月後{"較強" if run[0][3] > 0 else "較弱"}')
    cs = sorted((r for r in react if r[0] == "c"), key=lambda r: r[2])
    for sg in (1, -1):
        ms = [str(r[2]) for r in cs if r[3] == sg]
        if ms:
            out.append(f'累積 {"、".join(ms)} 個月{"較強" if sg > 0 else "較弱"}')
    return "、".join(out)


# ── 全部 ─────────────────────────────────────────────────────────────

def run(B: dict, A: dict | None = None) -> dict:
    """→ 研究檔的 m6。A＝國發會股價指數月平均 {YYYY-MM: 值}（延伸樣本；沒有就不做）。"""
    Pn = panel(B)
    ym, T, R, r1, r12 = Pn["ym"], Pn["T"], Pn["R"], Pn["r1"], Pn["r12"]
    v0 = S.M6_MAIN_VARIANT
    fam: dict[str, list] = {f: [] for f in ("l1d", "l1c", "l2", "l3a", "l3c_bull", "l3c_hike", "l4d", "l4c", "l4i_d", "l4i_c",
                                            "l4s_d", "l4s_c")}
    items = {}
    for k in ITEMS:
        it = Pn["it"][k]
        X2, XL = it["X2"][v0], it["XL"]
        res = {"first": next((ym[t] for t in range(T) if X2[t] is not None), None), "x1": k in X1_ITEMS}
        res["l1"] = l1_of(ym, R, X2, r1, r12)
        fam["l1d"] += res["l1"]["d"].values()
        fam["l1c"] += res["l1"]["c"].values()
        res["rob"] = {v: brief(l1_of(ym, R, it["X2"][v], r1, r12, boot=False)) for v in S.M6_VARIANTS if v != v0}
        l2x = [X2, XL] + ([it["X1"]] if k in X1_ITEMS else []) + [r1, r12]
        res["l2"] = {wkey(w): reg(ym, R[w], l2x, w[1]) for w in DELAY}
        fam["l2"] += res["l2"].values()
        xlx2 = [None if a is None or b is None else a * b for a, b in zip(XL, X2)]
        lin = {f"at{L}": [0.0, 1.0, 0.0, (L - S.M6_LEVEL_SPLIT) / 50.0, 0.0, 0.0] for L in S.M6_INTER_AT}
        res["l3a"] = {wkey(w): reg(ym, R[w], [X2, XL, xlx2, r1, r12], w[1], focus=3, lin=lin) for w in DELAY}
        fam["l3a"] += res["l3a"].values()
        res["l3c"] = {}
        for zn, Z in (("bull", Pn["BULL"]), ("hike", Pn["HIKE"])):
            x2z = [None if a is None or z is None else a * z for a, z in zip(X2, Z)]
            res["l3c"][zn] = {wkey(w): reg(ym, R[w], [X2, x2z, Z, r1, r12], w[1], focus=2,
                                           lin={"z0": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0], "z1": [0.0, 1.0, 1.0, 0.0, 0.0, 0.0]})
                              for w in DELAY}
            fam[f"l3c_{zn}"] += res["l3c"][zn].values()
        lab = item_labels(Pn, k)
        res["l3b"] = {str(h): state_tab(Pn, lab, STATES, h) for h in S.M6_STATE_H}
        res["oos"] = {wkey(w): oos_item(Pn, k, w) for w in S.M6_OOS_WINDOWS}
        res["l6"] = l6_item(Pn, k)
        items[k] = res
    gser = {f"GA_{g}": Pn["GA"][v0][g] for g in GROUPS}
    gser["DI"] = Pn["DI"][v0]
    groups = {}
    for nm, x in gser.items():
        e = {"first": next((ym[t] for t in range(T) if x[t] is not None), None)}
        e["l1"] = l1_of(ym, R, x, r1, r12)
        fam["l4d"] += e["l1"]["d"].values()
        fam["l4c"] += e["l1"]["c"].values()
        e["rob"] = {v: brief(l1_of(ym, R, Pn["DI"][v] if nm == "DI" else Pn["GA"][v][nm[3:]], r1, r12, boot=False))
                    for v in S.M6_VARIANTS if v != v0}
        groups[nm] = e
    for g in GROUPS:                                          # 對照圖的組線（幾成在加速）：只當描述，自成一個家族、沒有樣本外
        x = Pn["SH"][g]
        e = {"first": next((ym[t] for t in range(T) if x[t] is not None), None), "l1": l1_of(ym, R, x, r1, r12)}
        fam["l4s_d"] += e["l1"]["d"].values()
        fam["l4s_c"] += e["l1"]["c"].values()
        groups[f"SH_{g}"] = e
    GAg, GAr = Pn["GA"][v0]["grow"], Pn["GA"][v0]["rate"]
    gxr = [None if a is None or b is None else a * b for a, b in zip(GAg, GAr)]
    l4 = {"inter": {"d": {wkey(w): reg(ym, R[w], [GAg, GAr, gxr, r1, r12], w[1], focus=3) for w in DELAY},
                    "c": {wkey(w): reg(ym, R[w], [GAg, GAr, gxr, r1, r12], w[1], focus=3) for w in CUM}}}
    fam["l4i_d"] += l4["inter"]["d"].values()
    fam["l4i_c"] += l4["inter"]["c"].values()
    glab = group_labels(Pn)
    l4["states"] = {str(h): state_tab(Pn, glab, GSTATES, h) for h in S.M6_STATE_H}
    goos = {wkey(w): oos_group(Pn, w) for w in S.M6_OOS_WINDOWS}
    for rs in fam.values():
        _bh(rs)
    for k, res in items.items():
        oos = res["oos"]
        _judge(res["l1"]["d"], oos, "m2>m1", True)
        _judge(res["l1"]["c"], oos, "m2>m1", False)
        _judge(res["l2"], oos, "m2>m1", True)
        _judge(res["l3a"], oos, "m2>m1", True)
        for zn in ("bull", "hike"):
            _judge(res["l3c"][zn], oos, "m2>m1", True)
        res["sum"] = summary_of(res["l1"])
    for nm, e in groups.items():                             # GA_lev、DI、SH_* 沒有樣本外模型
        oos = goos if nm in ("GA_grow", "GA_rate") else {}
        _judge(e["l1"]["d"], oos, "m2>m1", True)
        _judge(e["l1"]["c"], oos, "m2>m1", False)
        e["sum"] = summary_of(e["l1"])
    _judge(l4["inter"]["d"], goos, "m3>m2", True)
    _judge(l4["inter"]["c"], goos, "m3>m2", False)
    out = {"ver": S.VER, "sample": {"a": ym[0], "z": ym[-1], "T": T, "oos_start": S.M6_OOS_START},
           "items": items, "groups": groups, "l4": l4, "goos": goos, "primary": primary(Pn), "ext": None,
           "now": now_of(Pn)}
    if A:
        E = ext_panel(B, Pn, A)
        if E:
            out["ext"] = ext_run(E)
    return _rnd(out)


def now_of(Pn: dict) -> dict:
    """最後一個月底（最新的交易日）各項與三組的二階狀態：加速幾項、組加速度、加速擴散（給頁面一句話用，研究檔只記錄當時的值）。"""
    t = Pn["T"] - 1
    v0 = S.M6_MAIN_VARIANT
    acc = {k: Pn["it"][k]["S2"][v0][t] for k in ITEMS}
    return {"ym": Pn["ym"][t], "s2": acc, "GA": {g: Pn["GA"][v0][g][t] for g in GROUPS},
            "SH": {g: Pn["SH"][g][t] for g in GROUPS}, "DI": Pn["DI"][v0][t]}
