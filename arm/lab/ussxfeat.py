"""美股飆股研究：每週的樣本——條件（ussxspec.FEATS）與五本帳的標籤（ussxspec VER 1；docs/lab_us_sleeve_plan.md 第 9 節）。

build(P, liq)  每週最後一個交易日、範圍內而且股價條件算得出來的（代號, 週）→ Cols（ussxmine 的格式）：
               {"d", "di", "c", "j", "w", "f": {條件: 陣列}, "y": {帳: {"y", "mx", "dd", "fr"}}}
股價條件的算法照 superx.Px.raw／feats_on（含息價、往前補齊；RS 在範圍內的股票之間排）；美股的差別：
  近 20 日大漲天數＝收盤比前一天 ≥ +BIG_UP（台股是漲停）、VCP（vcp.SPEC）、族群強弱（同產業 RS 中位數）。
EPS（那斯達克財報行事曆）、財報（SEC）的算法見 ussxspec 檔頭；拿得到＝公布日（申報日）的下一個交易日。
標籤（訊號那天收盤之後；含息價、往前補齊；那一檔資料提早結束＝用最後一天；第 n 個交易日超過資料尾端＝還不知道）：
  mx＝n 天內最高價、dd＝最低價、fr＝到期（或最後一天）收盤，都相對訊號日收盤；y 依 BOOKS 的 how。
"""
from __future__ import annotations

import bisect
import warnings
from datetime import date, timedelta

import numpy as np

from . import ussxpanel as UP
from . import ussxspec as X


# ── 小工具 ───────────────────────────────────────────────────────────────────

def week_ends(cal: list[str]) -> list[int]:
    """每週最後一個交易日的索引（ISO 週）。"""
    out = []
    for i, d in enumerate(cal):
        w = date.fromisoformat(d).isocalendar()[:2]
        if i + 1 == len(cal) or date.fromisoformat(cal[i + 1]).isocalendar()[:2] != w:
            out.append(i)
    return out


def ffill(A: np.ndarray) -> np.ndarray:
    """每一欄往前補齊（第一個有值以前維持 nan）。"""
    T = A.shape[0]
    ok = np.isfinite(A)
    idx = np.where(ok, np.arange(T)[:, None], 0)
    np.maximum.accumulate(idx, axis=0, out=idx)
    out = A[idx, np.arange(A.shape[1])[None, :]]
    seen = np.maximum.accumulate(ok, axis=0)
    out[~seen] = np.nan
    return out


def roll_mean(A: np.ndarray, w: int) -> np.ndarray:
    """往前 w 天（含當天）的平均；那 w 天都要有值，否則 nan。"""
    ok = np.isfinite(A)
    x = np.where(ok, A, 0.0)
    cs = np.concatenate([np.zeros((1, A.shape[1])), np.cumsum(x, axis=0)])
    cn = np.concatenate([np.zeros((1, A.shape[1]), dtype=np.int64), np.cumsum(ok, axis=0)])
    out = np.full(A.shape, np.nan)
    s = cs[w:] - cs[:-w]
    n = cn[w:] - cn[:-w]
    out[w - 1:] = np.where(n == w, s / w, np.nan)
    return out


def _mean_vol(V: np.ndarray, w: int, k_min: float = 0.8) -> np.ndarray:
    """superx.wmean：往前 w 天、至少 k_min 比例有值的平均（量沒成交＝0，算有值）。"""
    cs = np.concatenate([np.zeros((1, V.shape[1])), np.cumsum(V.astype(float), axis=0)])
    out = np.full(V.shape, np.nan)
    out[w - 1:] = (cs[w:] - cs[:-w]) / w
    return out


class Sparse:
    """一段區間的最大值／最小值（倍增表；只建到需要的最大長度）。"""

    def __init__(self, A: np.ndarray, op: str, nmax: int):
        f = np.fmax if op == "max" else np.fmin
        self.f = f
        self.L = [A]
        k = 1
        while (1 << k) <= nmax:
            prev = self.L[-1]
            h = 1 << (k - 1)
            nxt = prev.copy()
            nxt[:-h] = f(prev[:-h], prev[h:])
            self.L.append(nxt)
            k += 1

    def query(self, a: np.ndarray, b: np.ndarray, j: np.ndarray) -> np.ndarray:
        """[a, b]（含兩端）的最大／最小值；a > b 的位置回 nan。"""
        out = np.full(len(a), np.nan)
        ok = b >= a
        ln = np.where(ok, b - a + 1, 1)
        k = np.floor(np.log2(ln)).astype(int)
        for kk in np.unique(k[ok]):
            m = ok & (k == kk)
            T = self.L[kk]
            out[m] = self.f(T[a[m], j[m]], T[b[m] - (1 << kk) + 1, j[m]])
        return out


# ── 股價條件 ─────────────────────────────────────────────────────────────────

def price_block(P: dict, wk: list[int]) -> dict:
    """每週最後一個交易日的股價原始數值（W × N）：valid、score、tt7（7 個布林）、d52h、r120、bu20、vdry。
    valid＝superx.Px.raw 算得出來（有股價滿 252 天、當天在資料期間內、均線與報酬都有值）。"""
    C, H, L, V = P["C"], P["H"], P["L"], P["V"]
    T, N = C.shape
    Cf, Hf, Lf = ffill(C), ffill(H), ffill(L)
    wk = np.asarray(wk)
    ma = {w: roll_mean(Cf, w) for w in (50, 150, 200)}
    ma200p = np.full((T, N), np.nan)
    ma200p[20:] = ma[200][:-20]
    up = np.zeros((T, N))
    with np.errstate(invalid="ignore", divide="ignore"):
        up[1:] = (Cf[1:] / Cf[:-1] - 1 >= X.BIG_UP) & np.isfinite(Cf[:-1]) & np.isfinite(Cf[1:])
    cu = np.concatenate([np.zeros((1, N)), np.cumsum(up, axis=0)])
    v10, v50 = _mean_vol(V, 10), _mean_vol(V, 50)
    W = len(wk)
    out = {k: np.full((W, N), np.nan) for k in ("score", "d52h", "r120", "bu20", "vdry")}
    tt = np.zeros((W, 7, N), dtype=bool)
    valid = np.zeros((W, N), dtype=bool)
    first, last = P["first"], P["last"]
    for w, i in enumerate(wk):
        if i < 252:
            continue
        c = Cf[i]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            hs = np.nanmax(Hf[i - 251:i + 1], axis=0)
            ls = np.nanmin(Lf[i - 251:i + 1], axis=0)
        r = {n: c / Cf[i - n] - 1 for n in (63, 120, 126, 189, 252)}
        m50, m150, m200, m200p = ma[50][i], ma[150][i], ma[200][i], ma200p[i]
        ok = (first >= 0) & (i - first >= 252) & np.isfinite(c) & (i <= last) & np.isfinite(m50) & np.isfinite(m150) & \
             np.isfinite(m200) & np.isfinite(m200p) & np.isfinite(hs) & np.isfinite(ls)
        for n in (63, 126, 189, 252):
            ok &= np.isfinite(r[n])
        valid[w] = ok
        out["score"][w] = 0.4 * r[63] + 0.2 * r[126] + 0.2 * r[189] + 0.2 * r[252]
        out["d52h"][w] = c / hs - 1
        out["r120"][w] = r[120]
        out["bu20"][w] = cu[i + 1] - cu[i - 19]
        with np.errstate(invalid="ignore", divide="ignore"):
            vd = np.where((v10[i] > 0) & (v50[i] > 0), v10[i] / v50[i], np.nan)
            out["vdry"][w] = vd
            tt[w, 0] = (c > m150) & (c > m200)
            tt[w, 1] = m150 > m200
            tt[w, 2] = m200 > m200p
            tt[w, 3] = (m50 > m150) & (m50 > m200)
            tt[w, 4] = c > m50
            tt[w, 5] = c >= 1.3 * ls
            tt[w, 6] = c >= 0.75 * hs
    return {**out, "tt": tt, "valid": valid, "Cf": Cf, "Hf": Hf, "Lf": Lf}


def rs_rank(score: np.ndarray, use: np.ndarray) -> np.ndarray:
    """每一週在 use 的股票之間排：1～99（superx.rs_pct：分數由低到高、同分依代號）。"""
    W, N = score.shape
    out = np.full((W, N), np.nan)
    for w in range(W):
        cols = np.nonzero(use[w])[0]
        if not len(cols):
            continue
        order = cols[np.argsort(score[w, cols], kind="stable")]
        n = len(order)
        out[w, order] = np.clip(np.round(100 * (np.arange(n) + 1) / (n + 1)), 1, 99)
    return out


# ── EPS（財報行事曆） ───────────────────────────────────────────────────────────

_MON = {m: k + 1 for k, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}


def qlabel(s) -> int | None:
    """「Mar/2024」→ 月序（年 × 12 ＋ 月）。"""
    try:
        m, y = str(s).split("/")
        return int(y) * 12 + _MON[m[:3].title()]
    except (ValueError, KeyError, AttributeError):
        return None


def split_between(spl: list, d0: str, d1: str) -> float:
    """d0 之後、d1 當天以前（d0 < 生效日 ≤ d1）每一次分割的倍數相乘。"""
    f = 1.0
    for d, r in spl or []:
        if d0 < d <= d1 and r and r > 0:
            f *= float(r)
    return f


def _yoy(e, b, floor):
    if e is None or b is None:
        return None
    if b > floor:
        return max(-1.0, min(3.0, e / b - 1))
    return 3.0 if e > floor else None


def eps_reports(rows: list, spl: list) -> list[dict]:
    """一檔的財報行事曆 → 每一季（同一個季度標籤取第一次公布）的 EPS 條件，依公布日排序：
    [{"date", "m"（季度月序）, "ey", "eacc", "eaccn", "e4", "eturn", "sur", "nest"}]。"""
    first: dict[int, list] = {}
    for r in sorted(rows, key=lambda r: r[0]):
        m = qlabel(r[4] if len(r) > 4 else None)
        if m is None or m in first:
            continue
        first[m] = r
    Q = {m: {"date": r[0], "e": r[1], "f": r[2], "n": r[3]} for m, r in first.items()}

    def find(m: int, back: int, date_max: str):
        for dm in (0, -1, 1):
            q = Q.get(m - back + dm)
            if q is not None and q["date"] <= date_max:
                return m - back + dm
        return None

    def e_on(m_old: int, m_new: int):
        q, base = Q[m_old], Q[m_new]
        if q["e"] is None:
            return None
        return q["e"] / split_between(spl, q["date"], base["date"])

    ey_c: dict[int, float | None] = {}

    def ey(m):
        if m in ey_c:
            return ey_c[m]
        q = Q[m]
        p4 = find(m, 12, q["date"])
        v = _yoy(q["e"], e_on(p4, m) if p4 is not None else None, X.EPS_FLOOR)
        ey_c[m] = v
        return v

    def eacc(m):
        p1 = find(m, 3, Q[m]["date"])
        a, b = ey(m), ey(p1) if p1 is not None else None
        return a - b if a is not None and b is not None else None

    out = []
    for m in sorted(Q, key=lambda k: (Q[k]["date"], k)):
        q = Q[m]
        f: dict = {"date": q["date"], "m": m, "ey": ey(m), "eacc": eacc(m)}
        if f["eacc"] is None:
            f["eaccn"] = None
        else:
            k, cur = 0, m
            while k < 4 and cur is not None:
                a = eacc(cur)
                if a is None or a <= 0:
                    break
                k += 1
                cur = find(cur, 3, Q[cur]["date"])
            f["eaccn"] = float(k)
        chain, cur = [m], m
        for _ in range(7):
            cur = find(cur, 3, Q[cur]["date"]) if cur is not None else None
            chain.append(cur)
        if None in chain or any(e_on(c, m) is None for c in chain):
            f["e4"] = None
        else:
            a = sum(e_on(c, m) for c in chain[:4])
            b = sum(e_on(c, m) for c in chain[4:])
            f["e4"] = _yoy(a, b, 4 * X.EPS_FLOOR)
        p4 = find(m, 12, q["date"])
        if q["e"] is None or p4 is None or e_on(p4, m) is None:
            f["eturn"] = None
        else:
            f["eturn"] = bool(q["e"] > 0 and e_on(p4, m) <= 0)
        f["sur"] = (q["e"] - q["f"]) / max(abs(q["f"]), X.SUR_FLOOR) if q["e"] is not None and q["f"] is not None else None
        f["nest"] = float(q["n"]) if q["n"] is not None else None
        out.append(f)
    return out


# ── 財報（SEC） ─────────────────────────────────────────────────────────────────

def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def sec_quarters(f: dict) -> dict[str, dict]:
    """secfin 的 {"f": {項目: [[起日, 迄日, 數值, 公布日, 表單]]}} → {項目: {季底: (數值, 公布日)}}（單季；第四季＝全年 − 前三季）。
    時點項目（起日空字串：股東權益、流通股數）→ {迄日: (數值, 公布日)}。"""
    out: dict[str, dict] = {}
    for tag, rows in (f or {}).items():
        q: dict[str, tuple] = {}
        inst = all(not r[0] for r in rows)
        if inst:
            for s, e, v, fd, _ in rows:
                if e not in q or fd < q[e][1]:
                    q[e] = (v, fd)
            out[tag] = q
            continue
        nine: dict[str, list] = {}
        for s, e, v, fd, _ in rows:
            if not s:
                continue
            n = _days(s, e)
            if X.SEC_Q_DAYS[0] <= n <= X.SEC_Q_DAYS[1]:
                if e not in q or fd < q[e][1]:
                    q[e] = (v, fd)
            elif X.SEC_9M_DAYS[0] <= n <= X.SEC_9M_DAYS[1]:
                nine.setdefault(s, []).append((e, v, fd))
        for s, e, v, fd, _ in rows:
            if not s or not (X.SEC_FY_DAYS[0] <= _days(s, e) <= X.SEC_FY_DAYS[1]) or e in q:
                continue
            for e9, v9, fd9 in nine.get(s, []):
                if 60 <= _days(e9, e) <= 120:
                    q[e] = (v - v9, max(fd, fd9))
                    break
        out[tag] = q
    return out


def first_filed(Q: dict, tags: tuple, extra: tuple = ()) -> dict[str, tuple]:
    """（ussxspec VER 2）每一季在 tags 裡取最早公布的那個 (數值, 公布日)，同一天公布依 tags 順序；
    tags 都沒有那一季時用 extra 的加總（這家公司有申報過的 extra 項目，那一季都要有才算；公布日取較晚的）。"""
    out: dict[str, tuple] = {}
    for tag in tags:
        for e, (v, fd) in (Q.get(tag) or {}).items():
            if e not in out or fd < out[e][1]:
                out[e] = (v, fd)
    used = [t for t in extra if Q.get(t)]
    if used:
        for e in sorted(set().union(*[set(Q[t]) for t in used])):
            if e in out or not all(e in Q[t] for t in used):
                continue
            out[e] = (sum(Q[t][e][0] for t in used), max(Q[t][e][1] for t in used))
    return out


def _ko(keys) -> list[tuple[str, int]]:
    """日期鍵 → [(鍵, 日序)]，照原本的順序（_near_o 用，日期只解析一次）。"""
    return [(k, date.fromisoformat(k).toordinal()) for k in keys]


def _near_o(ko: list[tuple[str, int]], t: int, tol: int) -> str | None:
    """離日序 t 最近、而且差距在 tol 天以內的鍵；差距相同時取 ko 裡先遇到的（ko 的順序＝原本字典或清單的順序）。"""
    best, bd = None, tol + 1
    for k, o in ko:
        dd = abs(o - t)
        if dd < bd:
            best, bd = k, dd
    return best


def _sec_ctx(Q: dict, eps: list[dict]):
    """季資料（sec_quarters 的結果）＋EPS → (營收 {季底: (數值, 公布日)}, 季底清單, rec(季底) → 那一季的財報條件)。
    sec_reports（全部資料）與 sec_states（每次申報後只用當時的資料，ussxspec VER 8）共用同一套算法。"""
    rev = first_filed(Q, X.REV_TAGS, X.REV_EXTRA)
    cost = first_filed(Q, X.COST_TAGS)
    gp = dict(Q.get("GrossProfit") or {})
    for e, (r, fd) in rev.items():
        if e not in gp and e in cost:
            gp[e] = (r - cost[e][0], max(fd, cost[e][1]))
    oi, ni = Q.get("OperatingIncomeLoss") or {}, Q.get("NetIncomeLoss") or {}
    eq = Q.get("StockholdersEquity") or {}
    ends = sorted(rev)
    tol = X.SEC_TOL_D
    ko_ends = _ko(ends)
    M = {"gp": (gp, _ko(gp)), "oi": (oi, _ko(oi)), "ni": (ni, _ko(ni)), "eq": (eq, _ko(eq))}
    od: dict[str, int] = {}

    def o_of(e: str) -> int:
        v = od.get(e)
        if v is None:
            v = od[e] = date.fromisoformat(e).toordinal()
        return v

    def back(e: str, days: int):
        return _near_o(ko_ends, o_of(e) - days, tol)

    def val(name: str, e: str | None):
        if e is None:
            return None
        d, kd = M[name]
        k = _near_o(kd, o_of(e), tol) if e not in d else e
        return d[k][0] if k is not None else None

    def sy(e):
        p = back(e, 365)
        a, b = rev[e][0], rev[p][0] if p else None
        return max(-1.0, min(3.0, a / b - 1)) if a is not None and b and b > 0 else None

    def gm(e):
        r, g = rev[e][0], val("gp", e)
        return g / r if r and g is not None and r > 0 else None

    def om(e):
        r, o = rev[e][0], val("oi", e)
        return o / r if r and o is not None and r > 0 else None

    em = {}
    for x in eps:
        em.setdefault(x["m"], x)

    def ey_at(e):
        m = int(e[:4]) * 12 + int(e[5:7])
        for dm in (0, -1, 1):
            if m + dm in em:
                return em[m + dm]["ey"]
        return None

    def rec(e: str) -> dict:
        fd = rev[e][1]
        p1, p2, p4 = back(e, 91), back(e, 182), back(e, 365)
        s0 = sy(e)
        s1 = sy(p1) if p1 else None
        s2 = sy(p2) if p2 else None
        g0, g1, g2 = gm(e), gm(p1) if p1 else None, gm(p2) if p2 else None
        g4 = gm(p4) if p4 else None
        o0, o4 = om(e), om(p4) if p4 else None
        f = {"filed": fd, "end": e, "sy": s0, "sacc": s0 - s1 if s0 is not None and s1 is not None else None,
             "gm": g0, "gmd": g0 - g4 if g0 is not None and g4 is not None else None,
             "om": o0, "omd": o0 - o4 if o0 is not None and o4 is not None else None}
        chain = [e, p1, back(e, 182), back(e, 273)]
        # 只給研究用（不在 FEATS，規則不看）：上一季營益率、近四季營益率（四季營業利益合計 ÷ 四季營收合計，四季都要有）
        f["om1"] = om(p1) if p1 else None
        ois = [val("oi", c) for c in chain] if None not in chain else [None]
        rvs = [rev[c][0] for c in chain] if None not in chain else [None]
        f["om4"] = (sum(ois) / sum(rvs) if None not in ois and None not in rvs and sum(rvs) > 0 else None)
        oms = [om(c) for c in chain] if None not in chain else [None]
        f["omm"] = float(np.median(oms)) if None not in oms else None       # 近四季營益率的中位數
        # 和去年同一季比：營業利益增加的比營收增加的多多少（÷ 這一季營收；> 0＝不是靠賣得多，是一次性收入或成本變少）
        oy, ry = (val("oi", p4), rev[p4][0]) if p4 else (None, None)
        o_now = val("oi", e)
        f["oxr"] = (((o_now - oy) - (rev[e][0] - ry)) / rev[e][0]
                    if o_now is not None and oy is not None and ry is not None and rev[e][0] and rev[e][0] > 0 else None)
        nis = [val("ni", c) for c in chain] if None not in chain else [None]
        e0, e4 = val("eq", e), val("eq", p4) if p4 else None
        f["roe"] = (sum(nis) / ((e0 + e4) / 2) if None not in nis and e0 and e4 and e0 > 0 and e4 > 0 else None)
        y0, y1, y2 = ey_at(e), ey_at(p1) if p1 else None, ey_at(p2) if p2 else None
        vals = (y0, y1, y2, s0, s1, s2, g0, g1, g2)
        f["c33"] = None if any(v is None for v in vals) else bool(y0 > y1 > y2 and s0 > s1 > s2 and g0 > g1 > g2)
        return f

    return rev, ends, rec


def _shares(Q: dict) -> list[dict]:
    """流通股數（時點項目，每一個日子只用第一次申報的那一列；本來就只用當時拿得到的）。"""
    sh = [{"filed": fd, "end": e, "v": v} for e, (v, fd) in ((Q.get("EntityCommonStockSharesOutstanding") or {}).items())]
    sh.sort(key=lambda x: (x["filed"], x["end"]))
    return sh


def sec_reports(doc: dict, eps: list[dict]) -> list[dict]:
    """一檔的 SEC 資料（全部）→ 每一季的財報條件（依申報日排序）：[{"filed", "end", "sy", "sacc", "gm", "gmd", "om", "omd", "roe", "c33"}]
    ＋流通股數 [{"filed", "end", "v"}]。eps＝eps_reports 的結果（連三季變好用 EPS 年增）。
    ussxspec VER 2～7 的算法：每一季的值用全部資料（會用到後來才申報的數字）；VER 8 起每週用 sec_states，這一支留著當對照與切資料測試的定義。"""
    Q = sec_quarters((doc or {}).get("f") or {})
    _, ends, rec = _sec_ctx(Q, eps)
    out = [rec(e) for e in ends]
    out.sort(key=lambda x: (x["filed"], x["end"]))
    return out, _shares(Q)


def sec_states(doc: dict, eps: list[dict]) -> tuple[list[dict], list[dict]]:
    """ussxspec VER 8：每一次有新的申報（或新的 EPS 公布）就重算——只用那一天以前（含）申報的列與公布的 EPS，照 sec_reports 的算法，
    取最新的那一季（依申報日、季底排最後的那一筆）；和上一次不一樣才記一筆，"avail"＝重算那一天（申報日或公布日）。
    第 i 天用 avail 早於那一天的最後一筆＝把資料切在那一天以前、用 sec_reports 算的最後一筆（"filed" 照舊是那一季營收第一次申報的日子）。
    算出來沒有任何一季（例：後來申報的項目讓營收湊不齊）也記一筆 {"avail", "filed": None, "end": None}＝那天起沒有財報條件。"""
    f = (doc or {}).get("f") or {}
    fds = {r[3] for rows in f.values() for r in rows}
    cps = sorted(fds | {x["date"] for x in eps})
    out: list[dict] = []
    prev: dict | None = None
    Q = None
    k = 0
    for cp in cps:
        if cp in fds:
            Q = sec_quarters({t: [r for r in rows if r[3] <= cp] for t, rows in f.items()})
        while k < len(eps) and eps[k]["date"] <= cp:
            k += 1
        if Q is None:
            continue
        rev, ends, rec = _sec_ctx(Q, eps[:k])
        cur = rec(max(ends, key=lambda e: (rev[e][1], e))) if ends else None
        if cur != prev and (cur is not None or prev is not None):
            out.append({**cur, "avail": cp} if cur is not None else {"avail": cp, "filed": None, "end": None})
        prev = cur
    return out, _shares(sec_quarters(f))


def sec_index(sr: list[dict], cal: list[str], pit: bool) -> tuple[list[int], list[int | None]]:
    """每一筆從第幾個交易日起拿得到（sec_states 用重算那一天、sec_reports 用申報日；都是下一個交易日起），
    以及這一季營收第一次申報的交易日索引（多久沒更新從這天算；沒有任何一季的那一筆＝None）。"""
    sa = [bisect.bisect_right(cal, x["avail" if pit else "filed"]) for x in sr]
    fa = [bisect.bisect_right(cal, x["filed"]) if x["filed"] else None for x in sr]
    return sa, fa


def sec_at(sr: list[dict], sa: list[int], fa: list[int | None], i: int) -> dict | None:
    """第 i 天用的那一筆：拿得到的最後一筆，而且這一季營收第一次申報在 EPS_RECENT 個交易日以內（太舊、或那一筆沒有任何一季＝None）。"""
    q = bisect.bisect_right(sa, i) - 1
    if q >= 0 and fa[q] is not None and i - fa[q] <= X.EPS_RECENT:
        return sr[q]
    return None


# ── 標籤 ─────────────────────────────────────────────────────────────────────

def labels(pb: dict, P: dict, ii: np.ndarray, jj: np.ndarray, chunk: int = 300) -> dict:
    """每一列（交易日 ii、代號 jj）五本帳的標籤。"""
    T = len(P["cal"])
    n_set = sorted({b["n"] for b in X.BOOKS.values()})
    nmax = max(n_set)
    out = {b: {k: np.full(len(ii), np.nan) for k in ("mx", "dd", "fr", "mc")} for b in X.BOOKS}
    last = P["last"]
    Cf, Hf, Lf = pb["Cf"], pb["Hf"], pb["Lf"]
    for a in range(0, P["C"].shape[1], chunk):
        sel = np.nonzero((jj >= a) & (jj < a + chunk))[0]
        if not len(sel):
            continue
        cols = slice(a, a + chunk)
        SH = Sparse(Hf[:, cols], "max", nmax)
        SL = Sparse(Lf[:, cols], "min", nmax)
        SC = Sparse(Cf[:, cols], "max", nmax)
        i0, j0 = ii[sel], jj[sel]
        jl = j0 - a
        c0 = Cf[i0, j0]
        for n in n_set:
            end = i0 + n
            known = end < T
            e = np.minimum(end, last[j0])
            lo, hi = i0 + 1, np.where(known, e, i0)
            mx = SH.query(lo, hi, jl) / c0 - 1
            dd = SL.query(lo, hi, jl) / c0 - 1
            mc = SC.query(lo, hi, jl) / c0 - 1
            fr = np.where(known & (hi >= lo), Cf[np.clip(hi, 0, T - 1), j0] / c0 - 1, np.nan)
            ok = known & (hi >= lo)
            for b, spec in X.BOOKS.items():
                if spec["n"] != n:
                    continue
                for k, v in (("mx", mx), ("dd", dd), ("fr", fr), ("mc", mc)):
                    out[b][k][sel] = np.where(ok, v, np.nan)
    res = {}
    for b, spec in X.BOOKS.items():
        o = out[b]
        key = {"close": "fr", "high": "mx", "maxclose": "mc"}[spec["how"]]
        y = np.full(len(ii), -1, dtype=np.int8)
        ok = np.isfinite(o[key])
        y[ok] = (o[key][ok] >= spec["g"] - 1e-12).astype(np.int8)
        res[b] = {"y": y, "mx": o["mx"], "dd": o["dd"], "fr": o["fr"]}
    return res


# ── VCP（逐列；可以平行） ───────────────────────────────────────────────────────

_G: dict = {}


def _vcp_one(j: int) -> tuple[int, list[tuple[int, bool]]]:
    from . import vcp
    Hf, Lf, Cf, V, ws = _G["Hf"], _G["Lf"], _G["Cf"], _G["V"], _G["rows"][j]
    h = [None if not np.isfinite(x) else float(x) for x in Hf[:, j]]
    l = [None if not np.isfinite(x) else float(x) for x in Lf[:, j]]
    c = [None if not np.isfinite(x) else float(x) for x in Cf[:, j]]
    v = [float(x) for x in V[:, j]]
    res = []
    for k, i in ws:
        r = vcp.check(h, l, c, v, int(i), vcp.SPEC)
        res.append((k, bool(r and r.get("ok"))))
    return j, res


def vcp_flags(pb: dict, P: dict, ii: np.ndarray, jj: np.ndarray, workers: int = 4) -> np.ndarray:
    import multiprocessing as mp
    by: dict[int, list] = {}
    for k, (i, j) in enumerate(zip(ii.tolist(), jj.tolist())):
        by.setdefault(j, []).append((k, i))
    _G.update(Hf=pb["Hf"], Lf=pb["Lf"], Cf=pb["Cf"], V=P["V"], rows=by)
    out = np.zeros(len(ii))
    js = sorted(by)
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for j, res in pool.imap_unordered(_vcp_one, js, chunksize=8):
                for k, ok in res:
                    out[k] = 1.0 if ok else 0.0
    else:
        for j in js:
            for k, ok in _vcp_one(j)[1]:
                out[k] = 1.0 if ok else 0.0
    _G.clear()
    return out


# ── 組成一份樣本 ─────────────────────────────────────────────────────────────────

def build(P: dict, liq: float = X.LIQ_MIN, earn: dict | None = None, sec: dict | None = None, screen: dict | None = None,
          workers: int = 4, log=print, vcp: bool = True, labels_on: bool = True, extra: tuple = (), pit: bool | None = None) -> dict:
    """earn＝ussxpanel.earnings()；sec＝{代號: secfin 的檔}（None＝讀資料夾的 sec/，還沒抓過＝財報條件全部 nan）；screen＝篩選器。
    vcp、labels_on＝False：不算 VCP（全部 False）、不算標籤（y＝{}）——美股三成規則 QM 用不到（ussxspec VER 3），省一半時間。
    extra＝另外要填的財報欄位（sec_reports 有、FEATS 沒有的，例 om1、om4；只給研究用，預設不填＝和原本完全相同）。
    pit＝財報條件只用當時已經申報的數字（sec_states；None＝ussxspec.SEC_PIT，VER 8 起 True）；False＝VER 2～7 的舊算法（sec_reports，對照用）。"""
    pit = X.SEC_PIT if pit is None else bool(pit)
    import time
    t0 = time.time()
    cal = P["cal"]
    wk = week_ends(cal)
    earn = earn if earn is not None else UP.earnings()
    rep = UP.report_days(cal, P["sym"], earn)
    D20 = UP.dv20(P)
    el = UP.eligible(P, liq=liq, rep=rep, D20=D20)
    pb = price_block(P, wk)
    W = len(wk)
    use = pb["valid"] & el[np.asarray(wk)]
    rs = rs_rank(pb["score"], use)
    log(f"[ussxfeat] 股價條件 {time.time() - t0:.0f}s，樣本 {int(use.sum()):,} 列")
    ww, jj = np.nonzero(use)
    ii = np.asarray(wk)[ww]
    n = len(ii)
    f: dict[str, np.ndarray] = {}
    tt = pb["tt"][ww, :, jj]
    rsv = rs[ww, jj]
    tt8 = np.concatenate([tt, (rsv >= 70)[:, None]], axis=1)
    f["tt_n"] = tt8.sum(axis=1).astype(float)
    f["tt_all"] = tt8.all(axis=1).astype(float)
    f["rs"] = rsv
    for k in ("d52h", "r120", "bu20", "vdry"):
        f[k] = pb[k][ww, jj]
    f["liq"] = D20[ii, jj]
    screen = screen if screen is not None else _screen()
    ind = np.array([(screen.get(s) or [None, None, ""])[2] or "" for s in P["sym"]])
    grs = np.full(n, np.nan)
    for w in np.unique(ww):
        m = np.nonzero(ww == w)[0]
        g = ind[jj[m]]
        for name in np.unique(g):
            if not name:
                continue
            mm = m[g == name]
            if len(mm) >= X.GROUP_MIN:
                grs[mm] = float(np.median(rsv[mm]))
    f["grs"] = grs
    log(f"[ussxfeat] 族群 {time.time() - t0:.0f}s")
    f["vcp"] = vcp_flags(pb, P, ii, jj, workers=workers) if vcp else np.zeros(n, dtype=bool)
    log(f"[ussxfeat] VCP {time.time() - t0:.0f}s")
    # EPS 與財報
    eps_keys = [k for k, _, _, s in X.FEATS if s == "eps"]
    sec_keys = [k for k, _, _, s in X.FEATS if s == "sec"]
    sec_keys += [k for k in extra if k not in sec_keys]
    for k in eps_keys + sec_keys:
        f[k] = np.full(n, np.nan)
    sec_get = _sec_loader(sec)
    by: dict[int, list] = {}
    for k, j in enumerate(jj.tolist()):
        by.setdefault(j, []).append(k)
    n_sec = 0
    for j, ks in by.items():
        s = P["sym"][j]
        spl = _splits(s)
        er = eps_reports(earn.get(s) or [], spl)
        ra = [bisect.bisect_right(cal, x["date"]) for x in er]
        doc = sec_get(s) if sec_get else None
        sr, sh = (sec_states(doc, er) if pit else sec_reports(doc, er)) if doc else ([], [])
        if sr:
            n_sec += 1
        sa, fa = sec_index(sr, cal, pit)
        ha = [bisect.bisect_right(cal, x["filed"]) for x in sh]
        for k in ks:
            i = int(ii[k])
            q = bisect.bisect_right(ra, i) - 1
            if q >= 0 and i - ra[q] <= X.EPS_RECENT:
                x = er[q]
                for key in eps_keys:
                    v = x.get(key)
                    f[key][k] = np.nan if v is None else float(v)
            x = sec_at(sr, sa, fa, i)
            if x is not None:
                for key in sec_keys:
                    if key == "cap":
                        continue
                    v = x.get(key)
                    f[key][k] = np.nan if v is None else float(v)
            q = bisect.bisect_right(ha, i) - 1
            if q >= 0 and i - ha[q] <= X.EPS_RECENT and sh[q]["v"]:
                mult = split_between(spl, sh[q]["end"], cal[i])
                raw = float(P["RAW"][i, j])
                f["cap"][k] = sh[q]["v"] * mult * raw if np.isfinite(raw) else np.nan
    log(f"[ussxfeat] EPS／財報 {time.time() - t0:.0f}s（有 SEC 資料 {n_sec} 檔；{'每次申報後只用當時的數字' if pit else '舊算法：用全部資料'}）")
    y = labels(pb, P, ii, jj) if labels_on else {}
    log(f"[ussxfeat] 標籤 {time.time() - t0:.0f}s")
    return {"d": np.array([cal[i] for i in ii]), "di": ii, "c": np.array([P["sym"][j] for j in jj]), "j": jj, "w": ww,
            "f": f, "y": y, "wk": wk, "el": el, "D20": D20}


_SPL: dict = {}


def _splits(sym: str) -> list:
    if sym not in _SPL:
        from . import ussxdata as UD
        p = UD._read(UD.px_path(sym)) or {}
        _SPL[sym] = p.get("spl") or []
    return _SPL[sym]


def _screen() -> dict:
    from . import ussxdata as UD
    return UD.load_screen()


def _sec_loader(sec):
    """sec＝dict → 查表；None → 有抓過 SEC（sec_meta 有日期）就讀資料夾，沒有＝None（財報條件全部 nan）。"""
    if isinstance(sec, dict):
        return sec.get
    from . import secfin as SF
    if sec is None and SF.load_meta().get("asof"):
        return SF.load
    return None
