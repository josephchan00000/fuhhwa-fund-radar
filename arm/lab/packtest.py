"""籌碼雷達：資料包策略回測（2026-10-15 使用者：「副檔給你參考，把能用的拿來用就好」）。

主規格見 docs/strategy_pack_plan.md（回測前先 commit；結果出來後不改規格，改規格＝新版本、成績歸零）。
資料：Yahoo 五年日線（Data(long=True)，yhl 605 檔）＋單季 EPS（fin 469 檔）；短期反轉用兩年日線（yh 1,296 檔）。

共同口徑：
  · 價格口徑連續化（同 hdmodel.HD.ser）：相鄰兩個有價日收盤比 >1.8 倍＝口徑改變，更早的價格換到最新口徑。
  · 進場＝訊號日次一交易日開盤；開盤 ≥ 前收 × 1.095 視為漲停開盤、買不到（D1）。
  · 成本：來回 0.585%；月／週換股依換股比例計（續抱不計）。
  · 超額：x＝對加權指數（進場日開盤 → 出場日收盤）；xe＝對同宇宙等權平均（同一時窗）。
  · 存活者偏誤：yhl 是「目前市值前約 600 名」。形成日另要求市值（收盤 × 目前發行股數）≥ 300 億，
    只會漏掉之後跌超過三分之二的公司；平均沒贏同宇宙等權平均＝成績只是這批倖存股票的漲幅 → 評 C。
  · 月換股時，續抱的股票在換股日也是「收盤賣、隔天開盤買」的算法（少算一個隔夜），基準同樣口徑。
"""
from __future__ import annotations

import math
import statistics
from collections import deque
from datetime import date

from . import store, ta
from .backtest import exit_day

COST = 0.00585
LIMIT = 1.095                 # 開盤 ≥ 前收 × 1.095 視為漲停開盤（台股漲停 10%、依升降單位取整後約 9.5～10%）
LOCK = 0.905                  # 開＝高＝低＝收且 ≤ 前收 × 0.905＝整天鎖跌停、賣不掉
CAP_L, LIQ_L = 300e8, 2e8     # 五年宇宙：形成日市值、20 日均成交值
CAP_S = 100e8                 # 兩年宇宙（短期反轉）

# 主規格（事前寫死；參數鄰近只在這些值附近各 ±1 檔）
P1 = {"look": 126, "skip": 21, "top": 0.10, "nmin": 10}
P2 = {"stop": 0.08, "vol": 1.5, "base": 25, "depth": 0.25, "tight": 0.10, "maxd": 120}
P3 = {"top": 0.20, "nmin": 10, "hold": 60}
P4 = {"look": 126, "skip": 21, "top": 0.10, "nmin": 10, "ep_max": 0.25}
P5 = {"look": 5, "top": 0.10, "nmin": 10}
P7 = {"win": 12, "min": 6, "top": 0.10, "nmin": 10}     # S26 月營收驚喜（docs/strategy_pack_plan.md 第 6 節，回測前寫定）

# 法定公告期限：季底 → (同年或次年, 月, 日)
DEADLINE = {"03-31": (0, 5, 15), "06-30": (0, 8, 14), "09-30": (0, 11, 14), "12-31": (1, 3, 31)}


def form_after_deadline(cal: list[str], dl: str) -> int | None:
    """法定期限遇假日順延到下一個上班日：取期限當天或之後的第一個交易日（收盤時全部公司都已公告）。
    2026-10-15 修正：原本取「期限之前的最後一個交易日」，期限落在週末時（例：2026-11-14 週六）會用到
    週一才公告的財報（前視偏誤）。"""
    return next((i for i, d in enumerate(cal) if d >= dl), None)


def deadline(period: str) -> str:
    """單季 EPS 的季底日 → 法定公告期限。"""
    y = int(period[:4])
    dy, m, d = DEADLINE[period[5:]]
    return f"{y + dy:04d}-{m:02d}-{d:02d}"


def _basis(cl: list) -> list[float]:
    """口徑倍數 F：由新往舊，相鄰有價日收盤比超過 1.8 倍就把更早的價格換算（同 HD.ser）。"""
    T = len(cl)
    F = [1.0] * T
    f, later = 1.0, None
    for i in range(T - 1, -1, -1):
        if cl[i] is not None:
            if later is not None:
                r = cl[i] / cl[later]
                if r > 1.8 or r < 1 / 1.8:
                    f *= r
            later = i
        F[i] = f
    return F


def _roll(xs: list, w: int, fn) -> list:
    """xs[i-w+1..i] 的 max／min（單調佇列；None 跳過；窗內全 None → None）。fn＝max 或 min。"""
    out = [None] * len(xs)
    q: deque = deque()
    better = (lambda a, b: a >= b) if fn is max else (lambda a, b: a <= b)
    for i, x in enumerate(xs):
        while q and q[0][0] <= i - w:
            q.popleft()
        if x is not None:
            while q and better(x, q[-1][1]):
                q.pop()
            q.append((i, x))
        out[i] = q[0][1] if q else None
    return out


def _rmean(xs: list, w: int, k_min: int | None = None) -> list:
    """xs[i-w+1..i] 的平均（None 不計；有效值少於 k_min → None）。"""
    k_min = k_min or max(1, w // 2)
    out = [None] * len(xs)
    s, k = 0.0, 0
    for i, x in enumerate(xs):
        if x is not None:
            s += x
            k += 1
        if i >= w and xs[i - w] is not None:
            s -= xs[i - w]
            k -= 1
        out[i] = s / k if k >= k_min else None
    return out


def _series(D, c: str, off: list) -> dict:
    """同 analyze.Data.series（官方分片優先、官方兩市齊全卻沒有此檔＝當天沒交易、其餘退回 Yahoo），只是快：
    先整段填 Yahoo，再用官方分片（只有 off 這些日子）覆蓋。"""
    T = D.T
    o, h, l, cl, v, val = ([None] * T for _ in range(6))
    yq = D.yh.get(c) or {}
    if yq:
        for i, d in enumerate(D.cal):
            y = yq.get(d)
            if y and y[3]:
                o[i], h[i], l[i], cl[i], v[i] = y[0], y[1], y[2], y[3], y[4]
    for i, d, doc in off:
        q = None
        for part in ("q_tw", "q_tp"):
            x = (doc.get(part) or {}).get(c)
            if x and x[3]:
                q = x
                break
        if q:
            o[i], h[i], l[i], cl[i], v[i], val[i] = q[0], q[1], q[2], q[3], q[4], q[5]
        elif doc.get("q_tw") and doc.get("q_tp"):
            o[i] = h[i] = l[i] = cl[i] = v[i] = val[i] = None
    return {"o": o, "h": h, "l": l, "c": cl, "v": v, "val": val}


class Px:
    """宇宙每檔與交易日曆對齊的價量（口徑連續化）＋市值、20 日均成交值。"""

    def __init__(self, D, codes: list[str], iss: dict):
        self.D, self.T, self.cal = D, D.T, D.cal
        self.s: dict[str, dict] = {}
        self.cap: dict[str, list] = {}
        self.liq: dict[str, list] = {}
        self.basis: dict[str, list] = {}                 # 每檔的口徑倍數 F（_basis；sxlive.panel 用來認出已經換算過的配股）
        off = [(i, d, D.mkt[d]) for i, d in enumerate(self.cal)
               if D.mkt.get(d) and (D.mkt[d].get("q_tw") or D.mkt[d].get("q_tp"))]
        for c in codes:
            if c not in iss:
                continue
            S = _series(D, c, off)
            raw = S["c"]
            if sum(1 for x in raw if x) < 130:
                continue
            F = _basis(raw)
            adj = lambda xs: [None if x is None else x / F[i] for i, x in enumerate(xs)]
            o, h, l, cl = adj(S["o"]), adj(S["h"]), adj(S["l"]), adj(raw)
            v = [None if x is None else x * F[i] for i, x in enumerate(S["v"])]
            val = [vl if vl else (vv * cc if vv and cc else None) for vv, cc, vl in zip(S["v"], raw, S["val"])]
            self.s[c] = {"o": o, "h": h, "l": l, "c": cl, "v": v}
            self.basis[c] = F
            self.cap[c] = [None if x is None else x * iss[c] for x in cl]
            self.liq[c] = _rmean(val, 20, 10)
        self.codes = sorted(self.s)
        self.lock_n = 0                                  # 出場日整天鎖跌停、順延的次數（D1）
        self._el: dict[tuple, frozenset] = {}            # (日, 市值門檻) → 合格名單（參數鄰近重跑時共用）
        self._win: dict[tuple, tuple] = {}

    def ok(self, c: str, i: int, cap_min: float, liq_min: float = LIQ_L) -> bool:
        cp, lq = self.cap[c][i], self.liq[c][i]
        return bool(cp and lq and cp >= cap_min and lq >= liq_min)

    def elig(self, i: int, cap_min: float, liq_min: float = LIQ_L) -> frozenset:
        k = (i, cap_min, liq_min)
        if k not in self._el:
            self._el[k] = frozenset(c for c in self.codes if self.ok(c, i, cap_min, liq_min))
        return self._el[k]

    def close_on_or_before(self, c: str, x: int, lo: int) -> float | None:
        cs = self.s[c]["c"]
        for i in range(x, lo - 1, -1):
            if cs[i]:
                return cs[i]
        return None

    def win(self, c: str, t: int, j: int, x: int, check_limit: bool = True):
        """t＝訊號日、j＝進場日（開盤）、x＝出場日（收盤）→ 報酬；'L'＝漲停開盤買不到；None＝沒價格。"""
        k = (c, t, j, x, check_limit)
        if k not in self._win:
            self._win[k] = self._win_calc(c, t, j, x, check_limit)
        r, locked = self._win[k]
        if locked and check_limit:
            self.lock_n += 1
        return r

    def _win_calc(self, c: str, t: int, j: int, x: int, check_limit: bool) -> tuple:
        s = self.s[c]
        o, c0 = s["o"][j], s["c"][t]
        if not o or not c0:
            return None, False
        if check_limit and o >= c0 * LIMIT:
            return "L", False
        x2 = exit_day(s, x, self.T)                      # 整天鎖跌停賣不掉 → 順延到下一個交易日收盤
        cx = self.close_on_or_before(c, x2, j)
        return (cx / o - 1 if cx else None), x2 != x


def regime_map(D) -> dict[str, bool]:
    """交易日 → 加權指數收盤是否高於 200 日均線（D4；用五年日線算，2022 起才有值）。"""
    ix = D.taiex()
    ma = ta.sma(ix, 200)
    return {d: (ix[i] > ma[i]) for i, d in enumerate(D.cal) if ix[i] and ma[i]}


def _bench(idx: list, io: list, t: int, j: int, x: int) -> float | None:
    i0 = (io[j] if io and io[j] else None) or idx[t]
    return idx[x] / i0 - 1 if idx[x] and i0 else None


def _month_ends(cal: list[str]) -> list[int]:
    return [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]


def _week_ends(cal: list[str]) -> list[int]:
    wk = lambda d: date.fromisoformat(d).isocalendar()[:2]
    return [i for i in range(len(cal) - 1) if wk(cal[i]) != wk(cal[i + 1])]


# ── 月／週換股的橫斷面組合（P1、P4、P5） ─────────────────────────────────

def xsec(P: Px, codes: list[str], forms: list[int], score, *, top: float, nmin: int, cap_min: float,
         idx: list, io: list, asc: bool = False) -> dict:
    """forms＝形成日索引（相鄰兩個形成日＝一期）；score(c, t)→排序值（None＝不排）。
    → {"units": 每期 {d, r, x, xe, c, n, to, lim}, "now": 最新一期名單（還沒到下一個形成日）}。"""
    cal = P.cal
    units, prev = [], set()
    now = None
    for k, t in enumerate(forms):
        E = P.elig(t, cap_min)
        el = [c for c in codes if c in E]
        sc = {}
        for c in el:
            v = score(c, t)
            if v is not None:
                sc[c] = v
        if len(sc) < nmin:
            prev = set()
            continue
        n = max(nmin, math.ceil(top * len(sc)))
        picks = sorted(sc, key=lambda c: (sc[c] if asc else -sc[c], c))[:n]
        if k + 1 >= len(forms):
            now = {"t": t, "d": cal[t], "picks": picks, "n_uni": len(sc)}
            break
        x = forms[k + 1]
        j = t + 1
        if j > x:
            continue
        rs, lim = [], 0
        for c in picks:
            r = P.win(c, t, j, x, check_limit=c not in prev)
            if r == "L":
                lim += 1
            elif r is not None:
                rs.append(r)
        ew = [r for r in (P.win(c, t, j, x, check_limit=False) for c in sc) if isinstance(r, float)]
        b = _bench(idx, io, t, j, x)
        if not rs or b is None or not ew:
            prev = set()
            continue
        to = len(set(picks) - prev) / len(picks)
        prev = set(picks)
        cost = to * COST
        port = statistics.mean(rs) - cost
        units.append({"d": cal[t], "r": port * 100, "x": (port - b) * 100, "xe": (port - statistics.mean(ew)) * 100,
                      "cost": cost * 100, "n": len(rs), "to": round(to, 2), "lim": lim})
    return {"units": units, "now": now}


def _mom(P: Px, look: int, skip: int):
    def f(c, t):
        if t < look:
            return None
        cs = P.s[c]["c"]
        a, b = cs[t - look], cs[t - skip]
        return b / a - 1 if a and b else None
    return f


def p1_units(P: Px, codes: list[str], idx: list, io: list, spec: dict = P1) -> dict:
    forms = [t for t in _month_ends(P.cal) if t >= spec["look"]]
    return xsec(P, codes, forms, _mom(P, spec["look"], spec["skip"]), top=spec["top"], nmin=spec["nmin"],
                cap_min=CAP_L, idx=idx, io=io)


def p5_units(P: Px, codes: list[str], idx: list, io: list, start: str, spec: dict = P5) -> dict:
    forms = [t for t in _week_ends(P.cal) if P.cal[t] >= start and t >= spec["look"]]

    def f(c, t):
        cs = P.s[c]["c"]
        a, b = cs[t - spec["look"]], cs[t]
        return b / a - 1 if a and b else None
    return xsec(P, codes, forms, f, top=spec["top"], nmin=spec["nmin"], cap_min=CAP_S, idx=idx, io=io, asc=True)


# ── 財報：SUE（P3）、盈餘殖利率（P4） ───────────────────────────────────

def load_eps() -> dict[str, dict]:
    from . import store
    out = {}
    d = store.LAB / "fin"
    if d.exists():
        for p in d.glob("*.json.gz"):
            doc = store.read("fin", p.name.split(".json")[0]) or {}
            if doc.get("eps"):
                out[p.name.split(".json")[0]] = {k[:10]: float(v) for k, v in doc["eps"].items() if v is not None}
    return out


def _prev_year(q: str) -> str:
    return f"{int(q[:4]) - 1:04d}{q[4:]}"


def sue(eps: dict, q: str, n_max: int = 8, n_min: int = 4) -> float | None:
    """（當季 − 去年同季）÷ 前 n_max 季（至少 n_min 季）同季差的標準差。"""
    if q not in eps or _prev_year(q) not in eps:
        return None
    qs = sorted(k for k in eps if k < q)
    diffs = []
    for k in reversed(qs):
        if _prev_year(k) in eps:
            diffs.append(eps[k] - eps[_prev_year(k)])
        if len(diffs) >= n_max:
            break
    if len(diffs) < n_min:
        return None
    sd = statistics.stdev(diffs)
    return (eps[q] - eps[_prev_year(q)]) / sd if sd > 0 else None


def ttm_eps(eps: dict, d: str) -> float | None:
    """d 日已過法定期限的最近四季 EPS 合計（四季須連續）。"""
    qs = sorted(k for k in eps if deadline(k) <= d)
    if len(qs) < 4:
        return None
    last4 = qs[-4:]
    y0, y3 = date.fromisoformat(last4[0]), date.fromisoformat(last4[-1])
    if (y3 - y0).days > 300:                       # 中間缺季
        return None
    return sum(eps[k] for k in last4)


def p3_events(P: Px, codes: list[str], eps: dict, idx: list, io: list, spec: dict = P3) -> dict:
    """每個法定期限一次：期限次一交易日開盤買 SUE 前 top、持有 hold 個交易日。"""
    cal, T = P.cal, P.T
    quarters = sorted({q for e in eps.values() for q in e})
    units, now = [], None
    for q in quarters:
        t = form_after_deadline(cal, deadline(q))
        if t is None or t + 1 >= T:
            continue
        j = t + 1
        sc = {}
        E = P.elig(t, CAP_L)
        for c in codes:
            if c in E and c in eps:
                v = _sue_cached(P, eps, c, q)
                if v is not None:
                    sc[c] = v
        if len(sc) < max(spec["nmin"], 20):
            continue
        n = max(spec["nmin"], math.ceil(spec["top"] * len(sc)))
        picks = sorted(sc, key=lambda c: (-sc[c], c))[:n]
        x = j + spec["hold"] - 1
        done = x < T
        xx = min(x, T - 1)
        rs, lim = [], 0
        for c in picks:
            r = P.win(c, t, j, xx)
            if r == "L":
                lim += 1
            elif r is not None:
                rs.append(r)
        ew = [r for r in (P.win(c, t, j, xx, check_limit=False) for c in sc) if isinstance(r, float)]
        b = _bench(idx, io, t, j, xx)
        if not rs or b is None or not ew:
            continue
        port = statistics.mean(rs) - COST
        u = {"d": cal[t], "review": q, "r": port * 100, "x": (port - b) * 100,
             "xe": (port - statistics.mean(ew)) * 100, "cost": COST * 100, "n": len(rs), "lim": lim, "entry": cal[j],
             "exit": cal[xx]}
        if done:
            units.append(u)
        else:
            now = {**u, "picks": picks, "n_uni": len(sc)}
    nq = None
    if quarters:
        y, m = int(quarters[-1][:4]), int(quarters[-1][5:7])
        y, m = (y + 1, 3) if m == 12 else (y, m + 3)
        nq = f"{y:04d}-{m:02d}-{ {3: 31, 6: 30, 9: 30, 12: 31}[m]:02d}"
    return {"units": units, "now": now, "next": {"q": nq, "deadline": deadline(nq)} if nq else None}


def p4_units(P: Px, codes: list[str], eps: dict, idx: list, io: list, spec: dict = P4) -> dict:
    forms = [t for t in _month_ends(P.cal) if t >= spec["look"]]
    mom = _mom(P, spec["look"], spec["skip"])
    cache: dict[int, dict] = {}

    def ranks(t):
        if t in cache:
            return cache[t]
        d = P.cal[t]
        ep, mm = {}, {}
        E = P.elig(t, CAP_L)
        for c in codes:
            if c not in E or c not in eps:
                continue
            px = P.s[c]["c"][t]
            e = _ttm_cached(P, eps, c, d)
            m = mom(c, t)
            if px and e is not None and m is not None:
                v = e / px
                if v <= spec["ep_max"]:
                    ep[c], mm[c] = v, m
        pr = lambda m: {c: (i + 1) / len(m) for i, c in enumerate(sorted(m, key=lambda c: m[c]))}
        a, b = pr(ep), pr(mm)
        cache[t] = {c: (a[c] + b[c]) / 2 for c in a}
        return cache[t]
    return xsec(P, codes, forms, lambda c, t: ranks(t).get(c), top=spec["top"], nmin=spec["nmin"],
                cap_min=CAP_L, idx=idx, io=io)


# ── 趨勢樣板＋突破（P2，Minervini） ─────────────────────────────────────

def _wmax(xs: list, a: int, b: int):
    v = [x for x in xs[max(a, 0):b] if x is not None]
    return max(v) if v else None


def _wmin(xs: list, a: int, b: int):
    v = [x for x in xs[max(a, 0):b] if x is not None]
    return min(v) if v else None


def _sue_cached(P: Px, eps: dict, c: str, q: str):
    k = ("sue", c, q)
    if k not in P._win:
        P._win[k] = sue(eps[c], q)
    return P._win[k]


def _ttm_cached(P: Px, eps: dict, c: str, d: str):
    k = ("ttm", c, d)
    if k not in P._win:
        P._win[k] = ttm_eps(eps[c], d)
    return P._win[k]


class _Tpl:
    """趨勢樣板用的預先計算陣列。"""

    def __init__(self, P: Px, codes: list[str], elig=None, cap_floor: float = CAP_L):
        """elig(t)→合格名單（預設市值 ≥300 億）；回測方法 v3 的中型股傳 bt3.Elig 的 "M"。"""
        self.P = P
        self.E = elig or (lambda t: P.elig(t, CAP_L))
        self.codes = [c for c in codes if c in P.s and max((x or 0) for x in P.cap[c]) >= cap_floor]
        self.a: dict[str, dict] = {}
        for c in self.codes:
            s = P.s[c]
            cl, h, l, v = s["c"], s["h"], s["l"], s["v"]
            hh = [x if x is not None else y for x, y in zip(h, cl)]
            ll = [x if x is not None else y for x, y in zip(l, cl)]
            self.a[c] = {"ma50": ta.sma(cl, 50), "ma150": ta.sma(cl, 150), "ma200": ta.sma(cl, 200),
                         "hi250": _roll(hh, 250, max), "lo250": _roll(ll, 250, min),
                         "v10": _rmean(v, 10, 8), "v50": _rmean(v, 50, 40), "hh": hh, "ll": ll}
        self.rs: dict[int, dict] = {}
        self.sig: dict[tuple, list] = {}

    def rs_rank(self, t: int) -> dict:
        if t not in self.rs:
            rets = {}
            E = self.E(t)
            for c in self.codes:
                cs = self.P.s[c]["c"]
                if t >= 250 and cs[t] and cs[t - 250] and c in E:
                    rets[c] = cs[t] / cs[t - 250] - 1
            order = sorted(rets, key=lambda c: rets[c])
            self.rs[t] = {c: (i + 1) / len(order) for i, c in enumerate(order)}
        return self.rs[t]


def p2_signals(TP: _Tpl, spec: dict = P2) -> list[tuple[str, int]]:
    """所有符合樣板＋整理＋突破的 (代號, 訊號日)。持有中不重複進場在模擬時處理。
    量的條件只差倍數，所以先用最低倍數（1.25）掃一次、記下每個訊號的量比，各倍數再篩（參數鄰近不必重掃）。"""
    key = (spec["depth"], spec["tight"])
    if key not in TP.sig:
        TP.sig[key] = _p2_scan(TP, {**spec, "vol": min(spec["vol"], 1.25)})
    return [(c, t) for c, t, ratio in TP.sig[key] if ratio >= spec["vol"]]


def _p2_scan(TP: _Tpl, spec: dict) -> list[tuple[str, int, float]]:
    P = TP.P
    out = []
    for t in range(260, P.T):
        rk = None
        for c in TP.codes:
            a = TP.a[c]
            s = P.s[c]
            cl = s["c"][t]
            if not cl:
                continue
            m50, m150, m200 = a["ma50"][t], a["ma150"][t], a["ma200"][t]
            m200p = a["ma200"][t - 20]
            if not (m50 and m150 and m200 and m200p):
                continue
            if not (cl > m150 and cl > m200 and m150 > m200 and m200 > m200p and m50 > m150 and m50 > m200 and cl > m50):
                continue
            hi, lo = a["hi250"][t], a["lo250"][t]
            if not (hi and lo and cl >= lo * 1.3 and cl >= hi * 0.75):
                continue
            h25, l25 = _wmax(a["hh"], t - 25, t), _wmin(a["ll"], t - 25, t)       # 前 25 日（不含當日）
            h10, l10 = _wmax(a["hh"], t - 10, t), _wmin(a["ll"], t - 10, t)
            if not (h25 and l25 and h10 and l10) or h25 / l25 - 1 > spec["depth"] or h10 / l10 - 1 > spec["tight"]:
                continue
            v10, v50p = a["v10"][t - 1], a["v50"][t - 11]
            v50 = a["v50"][t - 1]
            vt = s["v"][t]
            if not (v10 and v50p and v50 and vt) or v10 > v50p:
                continue
            if not (cl > h25 and vt >= spec["vol"] * v50):
                continue
            if c not in TP.E(t):
                continue
            rk = rk if rk is not None else TP.rs_rank(t)
            if (rk.get(c) or 0) < 0.70:
                continue
            out.append((c, t, vt / v50))
    return out


def ew_index(P: Px, codes: list[str], cap_min: float) -> tuple[list, list]:
    """同宇宙等權指數（每天依前一日合格名單重新等權）：(收盤指數, 開盤指數)。單日漲跌超過 11% 視為資料錯誤不計。"""
    T = P.T
    I, IO = [None] * T, [None] * T
    lvl = 1.0
    I[0] = lvl
    for i in range(1, T):
        rs, gs = [], []
        E = P.elig(i - 1, cap_min)
        for c in codes:
            if c not in E:
                continue
            s = P.s[c]
            c0, c1 = s["c"][i - 1], s["c"][i]
            if not (c0 and c1):
                continue
            r = c1 / c0
            if abs(r - 1) > 0.11:
                continue
            rs.append(r)
            o1 = s["o"][i]
            if o1 and abs(o1 / c0 - 1) <= 0.11:
                gs.append(o1 / c0)
        if rs:
            IO[i] = lvl * (statistics.mean(gs) if gs else 1.0)
            lvl *= statistics.mean(rs)
        I[i] = lvl
    return I, IO


def p2_trades(TP: _Tpl, sigs: list[tuple[str, int]], idx: list, io: list, EW: tuple, spec: dict = P2) -> list[dict]:
    P = TP.P
    T, cal = P.T, P.cal
    EI, EO = EW
    held: dict[str, int] = {}
    out = []
    for c, t in sorted(sigs, key=lambda x: (x[1], x[0])):
        if held.get(c, -1) >= t:
            continue
        j = t + 1
        base = {"c": c, "d": cal[t]}
        if j >= T:
            out.append({**base, "st": "cand"})
            continue
        s, a = P.s[c], TP.a[c]
        o = s["o"][j]
        if not o or not s["c"][t]:
            continue
        if o >= s["c"][t] * LIMIT:
            out.append({**base, "st": "skip", "why": "漲停開盤買不到"})
            continue
        stop = o * (1 - spec["stop"])
        xi, why = None, None
        last = min(j + spec["maxd"] - 1, T - 1)
        for i in range(j, last + 1):
            cl = s["c"][i]
            if not cl:
                continue
            if cl < stop:
                xi, why = i, "停損"
                break
            m50 = a["ma50"][i]
            if m50 and cl < m50:
                xi, why = i, "跌破 50 日線"
                break
        done = xi is not None or last == j + spec["maxd"] - 1
        if xi is None:
            xi = max((i for i in range(j, last + 1) if s["c"][i]), default=None)
            why = "滿 120 日" if done else None
        if xi is None:
            continue
        lock = 0
        if done:
            x2 = exit_day(s, xi, T)                      # 整天鎖跌停賣不掉 → 順延到下一個交易日收盤
            lock, xi = x2 - xi, x2
        held[c] = xi if done else T
        r = s["c"][xi] / o - 1 - COST
        b = _bench(idx, io, t, j, xi)
        e = EI[xi] / EO[j] - 1 if EI[xi] and EO[j] else None
        out.append({**base, "st": "closed" if done else "open", "entry": round(o, 2), "exit" if done else "now":
                    round(s["c"][xi], 2), "why": why, "held": xi - j + 1, "r": round(r * 100, 2),
                    "x": None if b is None else round((r - b) * 100, 2),
                    "xe": None if e is None else round((r - e) * 100, 2), "cost": COST * 100,
                    **({"lock": lock} if lock else {})})
    return out


# ── 彙整 ──────────────────────────────────────────────────────────────

def _avg(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def _fmt(v) -> str:
    if isinstance(v, float) and v < 1:
        return f"{v * 100:g}%"
    return f"{v:g}" if isinstance(v, float) else str(v)


def grid(fn, a_vals, b_vals, lbl: tuple[str, str] | None = None) -> dict:
    """參數鄰近（D5）：fn(a, b) → 平均超額（%）或 None；回傳 9 格與幾格為正。lbl＝兩個參數的名稱（頁面表頭）。"""
    cells, pos, n = [], 0, 0
    for a in a_vals:
        for b in b_vals:
            v = fn(a, b)
            cells.append([a, b, None if v is None else round(v, 2)])
            if v is not None:
                n += 1
                pos += v > 0
    return {"a": list(a_vals), "b": list(b_vals), "ad": [_fmt(a) for a in a_vals], "bd": [_fmt(b) for b in b_vals],
            "lbl": list(lbl or ("參數一", "參數二")), "cells": cells, "n": n, "pos": pos}


# ── 月營收驚喜（P7，S26） ─────────────────────────────────────────────

@store.memo("rev")
def load_rev() -> dict[str, dict[str, float]]:
    """rev 分片（MOPS 營業收入彙總表回補＋官方 openapi 每月）→ {代號: {YYYY-MM: 當月營收(千元)}}。"""
    out: dict[str, dict] = {}
    for ym, doc in store.load("rev"):
        for c, v in (doc.get("s") or {}).items():
            if v and v[0] is not None:
                out.setdefault(c, {})[ym] = float(v[0])
    return out


def ym_shift(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + k
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return f"{y:04d}-{m:02d}"


def sur(rev: dict, ym: str, win: int = 12, mn: int = 6) -> float | None:
    """標準化營收驚喜＝（當月 − 去年同月）÷ 前 win 個月（至少 mn 個）「當月 − 去年同月」差額的標準差。"""
    a, b = rev.get(ym), rev.get(ym_shift(ym, -12))
    if a is None or b is None:
        return None
    diffs = []
    for k in range(1, win + 1):
        x, y = rev.get(ym_shift(ym, -k)), rev.get(ym_shift(ym, -k - 12))
        if x is not None and y is not None:
            diffs.append(x - y)
    if len(diffs) < mn:
        return None
    sd = statistics.stdev(diffs)
    return (a - b) / sd if sd > 0 else None


def rev_forms(cal: list[str]) -> list[tuple[int, str]]:
    """形成日＝月營收法定公告期限：每月 10 日，遇假日順延到下一個上班日 → 取 10 日當天或之後的第一個交易日
    （收盤後全部公司都已公告，隔天開盤進場）→ (索引, 可得的最新營收月份＝上個月)。
    回測前修正（docs 6b-1）：原寫「10 日當天或之前的最後一個交易日」，10 日遇假日時期限順延，會用到還沒公告的資料。"""
    first: dict[str, int] = {}
    for i, d in enumerate(cal):
        if int(d[8:10]) >= 10 and d[:7] not in first:
            first[d[:7]] = i
    return [(t, ym_shift(ym, -1)) for ym, t in sorted(first.items())]


def non_fin(codes: list[str]) -> list[str]:
    """排除金融保險業（P7 宇宙）：2026 起金控可延到 15 日申報營收；銀行保險的營收含投資損益，與一般公司不可比。"""
    from .. import stockmeta
    ind = stockmeta.industry_map()
    return [c for c in codes if "金融" not in (ind.get(c) or "")]


def p7_units(P: Px, codes: list[str], rev: dict, idx: list, io: list, spec: dict = P7) -> dict:
    fm = rev_forms(P.cal)
    ym_of = dict(fm)
    cache: dict[tuple, float | None] = {}

    def f(c, t):
        k = (c, ym_of[t], spec["win"], spec["min"])
        if k not in cache:
            cache[k] = sur(rev.get(c) or {}, ym_of[t], spec["win"], spec["min"])
        return cache[k]
    out = xsec(P, codes, [t for t, _ in fm], f, top=spec["top"], nmin=spec["nmin"], cap_min=CAP_L, idx=idx, io=io)
    if out.get("now"):
        out["now"]["ym"] = ym_of.get(out["now"]["t"])
    return out


def run(DL, names: dict | None = None, *, with_grid: bool = True) -> dict:
    """五個新策略（P1–P5）的樣本內成績、參數鄰近與最新一期名單。DL＝Data(long=True)。"""
    from .collect import yh_codes, yhl_codes
    names = names or DL.names
    iss = DL.issued()
    stock = lambda c: len(c) == 4 and c.isdigit() and not c.startswith("00")
    longc = [c for c in yhl_codes() if stock(c)]
    allc = [c for c in yh_codes() if stock(c)]
    P = Px(DL, allc, iss)
    longc = [c for c in longc if c in P.s]
    idx, io = DL.taiex(), DL.taiex_open()
    eps = load_eps()
    out: dict = {}

    # P1 相對強勢
    P.lock_n = 0
    r1 = p1_units(P, longc, idx, io)
    out["p1"] = {"units": r1["units"], "now": r1["now"], "lock": P.lock_n}
    if with_grid:
        out["p1"]["nb"] = grid(lambda look, top: _avg(u["x"] for u in p1_units(
            P, longc, idx, io, {**P1, "look": look, "top": top})["units"]), (105, 126, 147), (0.05, 0.10, 0.20),
            ("排序期間（交易日）", "買進比例"))

    # P2 趨勢樣板＋突破
    TP = _Tpl(P, longc)
    EW = ew_index(P, longc, CAP_L)
    sigs = p2_signals(TP)
    tr2 = p2_trades(TP, sigs, idx, io, EW)
    out["p2"] = {"trades": tr2, "n_sig": len(sigs)}
    if with_grid:
        def g2(stop, vol):
            sg = p2_signals(TP, {**P2, "vol": vol})
            return _avg(t["x"] for t in p2_trades(TP, sg, idx, io, EW, {**P2, "stop": stop}) if t.get("st") == "closed")
        out["p2"]["nb"] = grid(g2, (0.06, 0.08, 0.10), (1.25, 1.5, 2.0), ("停損", "突破量倍數"))

    # P3 SUE
    fc = [c for c in longc if c in eps]
    P.lock_n = 0
    r3 = p3_events(P, fc, eps, idx, io)
    out["p3"] = {**r3, "lock": P.lock_n}
    if with_grid:
        out["p3"]["nb"] = grid(lambda top, hold: _avg(u["x"] for u in p3_events(
            P, fc, eps, idx, io, {**P3, "top": top, "hold": hold})["units"]), (0.10, 0.20, 0.30), (40, 60, 80),
            ("買進比例", "持有天數"))

    # P4 價值＋動能
    P.lock_n = 0
    r4 = p4_units(P, fc, eps, idx, io)
    out["p4"] = {"units": r4["units"], "now": r4["now"], "lock": P.lock_n}
    if with_grid:
        out["p4"]["nb"] = grid(lambda look, top: _avg(u["x"] for u in p4_units(
            P, fc, eps, idx, io, {**P4, "look": look, "top": top})["units"]), (105, 126, 147), (0.05, 0.10, 0.20),
            ("動能期間（交易日）", "買進比例"))

    # P5 短期反轉（兩年宇宙：yh 全部從 2024-10 起才有，形成日從兩年資料齊全後開始）
    start = min((min(DL.yh[c]) for c in allc if c in DL.yh and c not in set(longc)), default=DL.cal[0])
    start = DL.cal[min(DL.ix.get(start, 0) + 10, DL.T - 1)] if start in DL.ix else start
    P.lock_n = 0
    r5 = p5_units(P, allc, idx, io, start)
    out["p5"] = {"units": r5["units"], "now": r5["now"], "start": start, "lock": P.lock_n}
    if with_grid:
        out["p5"]["nb"] = grid(lambda look, top: _avg(u["x"] for u in p5_units(
            P, allc, idx, io, start, {**P5, "look": look, "top": top})["units"]), (3, 5, 10), (0.05, 0.10, 0.20),
            ("排序天數", "買進比例"))
    # P7 月營收驚喜（S26）：rev 分片要有 2020 起的全市場歷史（MOPS 彙總表回補）才算
    rv = load_rev()
    months = sorted({ym for r in rv.values() for ym in r})
    if len(months) >= 30:
        P.lock_n = 0
        c7 = non_fin(longc)
        r7 = p7_units(P, c7, rv, idx, io)
        out["p7"] = {"units": r7["units"], "now": r7["now"], "lock": P.lock_n, "m0": months[0], "m1": months[-1]}
        if with_grid:
            out["p7"]["nb"] = grid(lambda win, top: _avg(u["x"] for u in p7_units(
                P, c7, rv, idx, io, {**P7, "win": win, "top": top})["units"]), (9, 12, 18), (0.05, 0.10, 0.20),
                ("標準差期間（月）", "買進比例"))
    out["meta"] = {"n_long": len(longc), "n_all": len(P.codes), "n_eps": len(fc), "d0": DL.cal[0], "d1": DL.cal[-1],
                   "rev_m": len(months)}
    return out


# ── 頁面用：資料包策略測試表 ────────────────────────────────────────────

PACK = [
    {"k": "p1", "src": "S11", "name": "相對強勢・月換股", "unit": "月", "event": False,
     "rule": "每月最後一個交易日，市值 300 億以上的股票依「約 6 個月前到 1 個月前」的漲幅排序，買前 10%（至少 10 檔），持有一個月"},
    {"k": "p2", "src": "S09", "name": "趨勢樣板＋突破", "unit": "筆", "event": False,
     "rule": "50／150／200 日線多頭排列、距一年高點 25% 以內，25 日整理後帶量突破，隔天開盤買；跌破進場價 8% 或 50 日線賣出"},
    {"k": "p3", "src": "S10", "name": "財報驚喜（SUE）", "unit": "季", "event": True,
     "rule": "每季財報法定公告期限後第一個交易日，買單季 EPS 比去年同季成長最出乎意料的前 20%，持有 60 個交易日"},
    {"k": "p4", "src": "S16", "name": "價值＋動能", "unit": "月", "event": False,
     "rule": "每月依盈餘殖利率與約 6 個月漲幅兩項排名的平均，買前 10%（至少 10 檔），持有一個月"},
    {"k": "p5", "src": "S13", "name": "短期反轉・週換股", "unit": "週", "event": False,
     "rule": "每週買進市值 100 億以上、過去 5 日跌最多的 10%（至少 10 檔），持有一週"},
    {"k": "p7", "src": "S26", "name": "月營收驚喜・月換股", "unit": "月", "event": False,
     "rule": "每月 10 日公告期限後，買上個月營收比去年同月成長最出乎意料（依過去一年的波動標準化）的前 10%（不含金融保險業），持有一個月"},
]

SKIPPED = [
    ["S01–S07 產業前瞻與名家選股（Fisher、Lynch、Buffett、Graham 等）", "要人工研究客戶、產品與產能，沒辦法由現有資料自動算出與回測"],
    ["S12 均線趨勢", "改成「大盤年線上／下」分組，套用在每一條策略的成績上"],
    ["S14 日內突破", "沒有分鐘資料"],
    ["S15 配對交易", "需要放空，本頁不做放空"],
    ["S17 機器學習、S18 強化學習", "參數多、樣本只有二到五年，過度擬合的風險大於可能的好處"],
    ["S19 AI 多角色投資代理", "結果無法重現"],
    ["S20 選擇權、S21 做市、S24 下單執行", "沒有選擇權報價、委託簿與成交資料"],
    ["S22 網格與攤平加碼", "高勝率掩蓋少數大虧，原文也不建議當核心"],
    ["S23 風險配置", "部位規則已用評級上限與停損虧損上限控管；另加「本期全部照做的總部位」"],
    ["S25 事件驅動", "可取得的事件只有指數調整，已有臺灣50、高股息兩段"],
    ["資料包 03（美股三檔）、04（宏致定價）", "單一公司的基本面估值與價格情境；本頁只放由資料算出、可回測的內容"],
]


def _units(k: str, r: dict) -> list[dict]:
    if k == "p2":
        return [{"d": t["d"], "r": t["r"], "x": t["x"], "xe": t.get("xe"), "cost": t.get("cost")}
                for t in r.get("trades") or [] if t.get("st") == "closed" and t.get("x") is not None]
    return r.get("units") or []


def summary(res: dict, reg: dict | None) -> dict:
    """→ {"rows": 每條策略的評級與成績, "skipped": 不採用清單, "meta": 宇宙與期間}。主規格與鄰近 9 組都是事前寫死的。"""
    from . import advice
    rows = []
    for m in PACK:
        if m["k"] not in res:                            # P7 要等月營收歷史回補齊全才算
            continue
        r = res.get(m["k"]) or {}
        u = _units(m["k"], r)
        sc = advice.score(u, event=m["event"], reg=reg, nb=r.get("nb"), xe_rule=True) if u else {"n": 0, "grade": "C"}
        row = {**m, "score": sc}
        if m["k"] == "p2":
            row["n_sig"] = r.get("n_sig")
            row["lim"] = sum(1 for t in r.get("trades") or [] if t.get("st") == "skip")
            row["lock"] = sum(1 for t in r.get("trades") or [] if t.get("lock"))
        else:
            row["lim"] = sum(x.get("lim") or 0 for x in u)
            row["lock"] = r.get("lock") or 0
        rows.append(row)
    return {"rows": rows, "skipped": SKIPPED, "meta": res.get("meta") or {}}
