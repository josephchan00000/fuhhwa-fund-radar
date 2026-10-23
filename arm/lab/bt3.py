"""籌碼雷達：回測方法 v3（docs/backtest_v3_plan.md；2026-10-15 使用者：「回測策略也要深度詳細規劃」）。

兩層檢定：
  · 因子檢定（訊號有沒有用）：每期依訊號分五組、每組等權，看下一期報酬（開盤 t+1 → 收盤 x，未扣成本）：
    選的那組減另一端、等級相關（IC）、Newey-West t、組序與報酬是否單調。
  · 策略檢定（能不能操作）：資金帳戶模擬——t 收盤決定名單、t+1 開盤成交；漲停開盤買不到、整天鎖跌停順延賣出；
    成本依實際交易金額。比較對象＝同一批股票的等權平均（同樣的換股時點，不扣成本、不檢查漲停）。
評級依第 6 節（使用者決定）：選股（贏同一批股票平均）、報酬型態（賺錢機率、每月平均、賺賠比）、穩健度；
樣本外（2014–2021，資料回補後）與前瞻另計。
"""
from __future__ import annotations

import math
import statistics

from .backtest import LIMIT_UP, exit_day, locked_down

# ── 成本與範圍（第 6a 節、Q2、Q3） ─────────────────────────────────────
COMM = 0.001425 * 0.28            # 手續費每邊（2.8 折）
TAX = 0.003                        # 證交稅（賣出）
SLIP = {"L": 0.0005, "M": 0.0015}  # 滑價每邊
# 成交值門檻：大型、中型都 5,000 萬（使用者核定的範圍只對中型股訂了成交值；原本大型股另加 2 億，
# 2014 年的成交量只有現在的幾分之一，134 檔 300 億以上的公司有 65 檔被它排除——docs 第 11 節回測前修正）
BUCKET = {"L": {"name": "大型股", "cap": (300e8, None), "liq": 0.5e8},
          "M": {"name": "中型股", "cap": (50e8, 300e8), "liq": 0.5e8}}
MONTH = 21                         # 一個月＝21 個交易日
# 報酬型態門檻（第 6b 節「標準」）：賺錢機率 %、每月平均 %、賺賠比
PAY = {"win": 60.0, "m": 1.0, "win2": 40.0, "ratio": 2.5, "m2": 2.0}
DROP = 0.05                        # 穩健度：去掉最好的 5%
LOWDD = {"gap": 3.0, "dd": 0.7, "nb": 5}   # 低回落例外（第 15 節）：年化少不到 3 個百分點、回落 ≤0.7 倍、鄰近 ≥5 組


def side_cost(b: str, sell: bool, mult: float = 1.0) -> float:
    return mult * (COMM + SLIP[b] + (TAX if sell else 0.0))


def rt_cost(b: str, mult: float = 1.0) -> float:
    """來回成本（比例）：大型 0.48%、中型 0.68%。"""
    return side_cost(b, False, mult) + side_cost(b, True, mult)


def bucket_of(cap: float | None) -> str | None:
    if not cap:
        return None
    for b, v in BUCKET.items():
        lo, hi = v["cap"]
        if cap >= lo and (hi is None or cap < hi):
            return b
    return None


class Elig:
    """某日、某範圍（市值區間＋20 日均成交值）的合格名單；P＝packtest.Px 介面（codes、cap、liq）。"""

    def __init__(self, P):
        self.P, self._c = P, {}

    def __call__(self, t: int, b: str) -> frozenset:
        k = (t, b)
        if k not in self._c:
            lo, hi = BUCKET[b]["cap"]
            lq = BUCKET[b]["liq"]
            P = self.P
            self._c[k] = frozenset(c for c in P.codes
                                   if P.cap[c][t] and P.liq[c][t] and P.cap[c][t] >= lo
                                   and (hi is None or P.cap[c][t] < hi) and P.liq[c][t] >= lq)
        return self._c[k]


# ── 統計 ────────────────────────────────────────────────────────────

def nw_t(xs: list, lag: int | None = None) -> float | None:
    """平均數的 Newey-West t 值（Bartlett 權重；lag 預設 ⌊4(n/100)^(2/9)⌋）。"""
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n < 3:
        return None
    m = statistics.mean(xs)
    d = [x - m for x in xs]
    if lag is None:
        lag = int(4 * (n / 100) ** (2 / 9))
    s = sum(v * v for v in d) / n
    for l in range(1, min(lag, n - 1) + 1):
        s += 2 * (1 - l / (lag + 1)) * sum(d[i] * d[i - l] for i in range(l, n)) / n
    return m / math.sqrt(s / n) if s > 0 else None


def _rank(xs: list) -> list[float]:
    o = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a: list, b: list) -> float | None:
    if len(a) < 3:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    sa = math.sqrt(sum((x - ma) ** 2 for x in ra))
    sb = math.sqrt(sum((x - mb) ** 2 for x in rb))
    if not sa or not sb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (sa * sb)


def by_month(units: list[dict], key: str = "xe") -> list[float]:
    """逐筆交易 → 依訊號月份平均（日曆時間），給 Newey-West 用（同月份多筆交易彼此相關）。"""
    g: dict[str, list] = {}
    for u in units:
        if u.get(key) is not None:
            g.setdefault(u["d"][:7], []).append(u[key])
    return [statistics.mean(g[m]) for m in sorted(g)]


def sel_stats(units: list[dict], *, trades: bool = False) -> dict:
    """選股：扣成本後對同一批股票等權平均的超額（%）。"""
    xs = [u["xe"] for u in units if u.get("xe") is not None]
    if not xs:
        return {"n": 0}
    k = math.ceil(DROP * len(xs))
    rest = sorted(xs)[:-k] if len(xs) > k else []
    return {"n": len(xs), "xe": statistics.mean(xs), "med": statistics.median(xs),
            "pos": 100 * sum(1 for x in xs if x > 0) / len(xs),
            "t": nw_t(by_month(units) if trades else xs),
            "drop5": statistics.mean(rest) if rest else None, "k_drop": k}


def payoff(units: list[dict]) -> dict:
    """報酬型態（第 6b 節）：r＝扣成本後報酬（%）、hd＝持有交易日數。每月平均＝平均報酬 ÷ 平均持有月數。"""
    rs = [u["r"] for u in units if u.get("r") is not None and u.get("hd")]
    hd = [u["hd"] for u in units if u.get("r") is not None and u.get("hd")]
    if not rs:
        return {"n": 0, "ok": False}
    g = [r for r in rs if r > 0]
    lo = [r for r in rs if r <= 0]
    win = 100 * len(g) / len(rs)
    ratio = (statistics.mean(g) / -statistics.mean(lo)) if g and lo and statistics.mean(lo) < 0 else \
        (math.inf if g and not lo else None)
    hm = statistics.mean(hd) / MONTH
    m = statistics.mean(rs) / hm if hm > 0 else None
    ok1 = m is not None and win >= PAY["win"] and m >= PAY["m"]
    ok2 = m is not None and ratio is not None and win >= PAY["win2"] and ratio >= PAY["ratio"] and m >= PAY["m2"]
    return {"n": len(rs), "win": win, "ratio": ratio, "m": m, "hm": hm, "avg": statistics.mean(rs),
            "ok": bool(ok1 or ok2), "path": "一般" if ok1 else ("上漲空間大" if ok2 else None)}


def curve_stats(curve: list[tuple[int, float]], cal: list[str]) -> dict:
    """淨值曲線 → 年化報酬、最大回落、年化波動（日報酬 × √252）。"""
    if len(curve) < 2:
        return {}
    v0, v1 = curve[0][1], curve[-1][1]
    yrs = (curve[-1][0] - curve[0][0]) / 252
    pk, mdd = curve[0][1], 0.0
    rets = []
    for (i0, a), (i1, b) in zip(curve, curve[1:]):
        if a > 0 and i1 > i0:
            rets.append(b / a - 1)
        pk = max(pk, b)
        mdd = max(mdd, 1 - b / pk if pk > 0 else 0)
    vol = statistics.stdev(rets) * math.sqrt(252) if len(rets) > 2 else None
    cagr = (v1 / v0) ** (1 / yrs) - 1 if yrs > 0 and v0 > 0 and v1 > 0 else None
    return {"cagr": None if cagr is None else cagr * 100, "mdd": mdd * 100, "vol": None if vol is None else vol * 100,
            "d0": cal[curve[0][0]], "d1": cal[curve[-1][0]], "yrs": yrs}


# ── 資金帳戶：定期換股 ─────────────────────────────────────────────────

def account(P, periods: list, b: str, *, mult: float = 1.0, limit: bool = True, log: list | None = None) -> dict:
    """periods＝[(t, x, picks)] 依 t 排序：t 收盤決定名單、t+1 開盤換成等權、x 收盤為期末。
    下一期 t 等於本期 x 時續抱（下一期開盤再調權重），否則 x 收盤全部賣出、持有現金到下一期。
    兩期重疊（下一期的 t ＜ 本期的 x，例：財報驚喜年報那一期持有 60 天、和第一季那一期重疊約 30 天）＝兩份名單同時持有，
    錢平分：新一期開盤時把還在持有的那一期等比例賣掉一部分，兩期各一半；先到期的那一期收盤賣出，錢隔天開盤等比例加進還在持有的那一期
    （2026-10-23 修正：之前會用後一期到期賣出的錢、回頭在前一天開盤買新名單，每年那一個月的報酬算兩次）。
    mult＝成本倍數（0＝不扣成本）；limit＝檢查漲停開盤買不到、整天鎖跌停順延賣出。
    log＝逐筆紀錄（給頁面「逐筆交易」；不影響任何數字）：每一筆整檔買進／整檔賣出／沒買到，
      ("b", 期, 代號, 日索引, 價) 買進（開盤）；("s", 期, 代號, 日索引, 價, 開盤?, 原因) 賣出；("x", 期, 代號, 日索引, 原因)。
      賣出原因：drop＝不在新名單、開盤賣；lock＝不在新名單但整天鎖跌停、順延收盤賣；end＝期末收盤賣（下一期不相連）；
      endlock＝期末遇鎖跌停順延。沒買到：lim＝漲停開盤、noopen＝沒有開盤價。價＝面板價格（還原權息）；續抱時的調回等額、
      重疊時的平分與加碼都不記（不是整檔買賣）。重疊時紀錄依「份」排：前一份的買賣全部在前。
    → {"units": 每期 {d, t, x, r(%), hd, to, cost(%), n, lim, lock}, "curve": [(日索引, 淨值)]}
    每期的 r 是那一份名單自己的報酬（平分、加碼按比例，不改變每一單位的報酬）；curve 是整個帳戶。"""
    return engine(P, periods, b, mult=mult, limit=limit, log=log)


class _Sub:
    """資金帳戶裡的一份（一期名單的持股與現金；續抱時下一期接手同一份）。"""
    __slots__ = ("k", "hold", "cash", "pend", "ref", "units", "V0", "Vo", "buy", "cost", "cpu", "lim", "lock", "ngap", "nstop",
                 "log")

    def __init__(self, cash: float):
        self.k, self.hold, self.cash, self.pend, self.ref = -1, {}, cash, {}, {}
        self.units = self.V0 = self.Vo = 0.0
        self.buy = self.cost = self.cpu = 0.0
        self.lim = self.lock = self.ngap = self.nstop = 0
        self.log: list = []


def engine(P, periods: list, b: str, *, mult: float = 1.0, limit: bool = True, log: list | None = None,
           gap: float | None = None, stop: float | None = None, knobs: bool = False) -> dict:
    """資金帳戶（account 的本體；optim.account_v 多兩個候選旋鈕：gap＝不在原持股的新名單股票開盤 ≥ 前一日收盤 ×（1＋gap）
    當期不買；stop＝當期第一天開盤為參考價、收盤跌破參考價 ×（1 − stop）當天收盤賣出、持有現金到期末；knobs＝每期多記
    gap、stop 兩欄）。兩期不重疊時和 2026-10-23 以前的寫法逐位相同（tests/test_bt3.py 用舊版逐期、逐日、逐筆比對）。"""
    S, T, cal = P.s, P.T, P.cal
    last: dict[str, float] = {}
    curve: list = []
    out_units: dict[int, dict] = {}
    free = 1.0                                           # 不屬於任何一份的現金（期與期之間）
    act: list[_Sub] = []                                 # 持有中的份（建立順序）
    carry: _Sub | None = None                            # 期末和下一期相連、等下一期接手的那一份
    subs_made: list[_Sub] = []

    def px(c: str, i: int) -> float | None:
        v = S[c]["c"][i]
        if v:
            last[c] = v
        return v or last.get(c)

    def sval(s: _Sub, i: int) -> float:
        return s.cash + sum(sh * (px(c, i) or 0.0) for c, sh in s.hold.items())

    def sval_open(s: _Sub, j: int, t: int) -> float:
        return s.cash + sum(sh * ((S[c]["o"][j] or px(c, t)) or 0.0) for c, sh in s.hold.items())

    def total(i: int) -> float:
        v = free
        for s in act:
            v += sval(s, i)
        if carry is not None:
            v += sval(carry, i)
        return v

    def units_changed(s: _Sub, m: float) -> None:      # 平分、加碼：每一單位的報酬不變
        s.cpu += s.cost / s.units if s.units > 0 else 0.0
        s.cost = 0.0
        s.units *= m

    valid = [k for k, (t, x, picks) in enumerate(periods) if picks and t + 1 <= x and t + 1 < T]
    if not valid:
        return {"units": [], "curve": []}
    starts: dict[int, list[int]] = {}
    for k in valid:
        starts.setdefault(periods[k][0] + 1, []).append(k)
    i_end = max(periods[k][1] for k in valid)
    i0 = min(starts)
    for i in range(i0, i_end + 1):
        # ── 開盤：新的一期 ────────────────────────────────────────────
        for k in starts.get(i, ()):
            t, x, picks = periods[k]
            j = i
            if carry is not None:                            # 續抱：上一期的那一份接手
                s, carry = carry, None
                act.append(s)
                s.V0 = sval(s, t)
            elif not act:                                    # 期與期之間：拿全部現金
                s = _Sub(free)
                free = 0.0
                act.append(s)
                subs_made.append(s)
                s.V0 = sval(s, t)
            else:                                            # 重疊：和持有中的各份平分
                s = _Sub(free)
                free = 0.0
                vs = [(o, sval_open(o, j, t)) for o in act]
                tgt = (s.cash + sum(v for _, v in vs)) / (len(act) + 1)
                for o, v in vs:
                    if v <= tgt or v <= 0:
                        continue
                    f = (v - tgt) / v
                    for c in list(o.hold):
                        p = S[c]["o"][j] or px(c, t)
                        if not p:
                            continue                         # 沒有價格的不動（它在 v 裡也算 0）
                        q = o.hold[c] * f
                        o.hold[c] -= q
                        s.cash += q * p * (1 - side_cost(b, True, mult))
                    s.cash += o.cash * f
                    o.cash -= o.cash * f
                    units_changed(o, 1 - f)
                act.append(s)
                subs_made.append(s)
                s.V0 = s.cash
            if not curve:
                curve.append((t, s.V0 if len(act) == 1 else total(t)))
            s.k, s.units = k, s.V0
            s.buy = s.cost = s.cpu = 0.0
            s.lim = s.lock = s.ngap = s.nstop = 0
            s.pend = {}
            tgt_set = set(picks)
            for c in [c for c in s.hold if c not in tgt_set]:
                st = S[c]
                if limit and locked_down(st, j):
                    s.pend[c] = exit_day(st, j, T)
                    s.lock += 1
                    continue
                p = st["o"][j] or px(c, t)
                amt = s.hold.pop(c) * p
                s.cash += amt * (1 - side_cost(b, True, mult))
                s.cost += amt * side_cost(b, True, mult)
                s.log.append(("s", k, c, j, p, True, "drop"))
            s.Vo = s.cash + sum(sh * ((S[c]["o"][j] or px(c, t)) or 0.0) for c, sh in s.hold.items())
            tv = s.Vo * (1 - side_cost(b, False, mult)) / len(picks)
            for c in picks:
                st = S[c]
                o = st["o"][j]
                if not o:
                    if c not in s.hold:
                        s.log.append(("x", k, c, j, "noopen"))
                    continue
                cur = s.hold.get(c, 0.0) * o
                diff = tv - cur
                if diff > 0:
                    if limit and o >= (st["c"][t] or px(c, t) or o) * LIMIT_UP:
                        s.lim += c not in s.hold
                        if c not in s.hold:
                            s.log.append(("x", k, c, j, "lim"))
                        continue
                    if gap is not None and c not in s.hold and o >= (st["c"][t] or px(c, t) or o) * (1 + gap):
                        s.ngap += 1
                        s.log.append(("x", k, c, j, "gap"))
                        continue
                    if c not in s.hold:
                        s.log.append(("b", k, c, j, o))
                    s.cash -= diff * (1 + side_cost(b, False, mult))
                    s.cost += diff * side_cost(b, False, mult)
                    s.hold[c] = s.hold.get(c, 0.0) + diff / o
                    s.buy += diff
                elif diff < 0:
                    s.cash += -diff * (1 - side_cost(b, True, mult))
                    s.cost += -diff * side_cost(b, True, mult)
                    s.hold[c] = s.hold.get(c, 0.0) + diff / o
            s.ref = {c: S[c]["o"][j] for c in s.hold if S[c]["o"][j]} if stop is not None else {}
        # ── 開盤：前一天到期那一份的錢加進還在持有的各份（等比例） ─────────────
        if free > 0 and act and i not in starts:
            a = free / len(act)
            for s in act:
                wh = sum(sh * ((S[c]["o"][i] or px(c, i - 1)) or 0.0) for c, sh in s.hold.items())
                den = wh * (1 + side_cost(b, False, mult)) + s.cash
                if den <= 0:
                    continue
                g = a / den
                for c in s.hold:
                    s.hold[c] *= 1 + g
                s.cash += s.cash * g
                free -= a
                units_changed(s, 1 + g)
            if free < 1e-15:
                free = 0.0
        if not act:
            continue
        # ── 收盤：順延賣出、停損、記淨值 ─────────────────────────────────
        for s in act:
            k = s.k
            for c in [c for c, d2 in s.pend.items() if d2 == i]:
                p = px(c, i) or 0.0
                amt = s.hold.pop(c) * p
                s.cash += amt * (1 - side_cost(b, True, mult))
                s.cost += amt * side_cost(b, True, mult)
                del s.pend[c]
                s.log.append(("s", k, c, i, p, False, "lock"))
            if stop is not None:
                for c in [c for c in s.hold if c not in s.pend and s.ref.get(c)]:
                    cl = S[c]["c"][i]
                    if not cl or cl >= s.ref[c] * (1 - stop):
                        continue
                    s.nstop += 1
                    i2 = exit_day(S[c], i, T)
                    if i2 != i:
                        s.pend[c] = i2                        # 鎖跌停賣不掉：順延（超過期末就留給期末處理）
                        continue
                    amt = s.hold.pop(c) * cl
                    s.cash += amt * (1 - side_cost(b, True, mult))
                    s.cost += amt * side_cost(b, True, mult)
                    s.log.append(("s", k, c, i, cl, False, "stop"))
        curve.append((i, sval(act[0], i) if len(act) == 1 and free == 0.0 else total(i)))
        # ── 收盤：到期 ──────────────────────────────────────────────────
        for s in [s for s in act if periods[s.k][1] == i]:
            k = s.k
            t, x, picks = periods[k]
            nxt = periods[k + 1][0] if k + 1 < len(periods) else None
            act.remove(s)
            if nxt != x:
                for c in list(s.hold):
                    st = S[c]
                    i2 = exit_day(st, x, T) if limit else x
                    s.lock += i2 != x
                    p = px(c, i2) or px(c, x) or 0.0
                    amt = s.hold.pop(c) * p
                    s.cash += amt * (1 - side_cost(b, True, mult))
                    s.cost += amt * side_cost(b, True, mult)
                    s.log.append(("s", k, c, i2, p, False, "end" if i2 == x else "endlock"))
                V1 = s.cash
                free = free + s.cash if act or free else s.cash
                s.cash = 0.0
                curve[-1] = (x, free if not act else total(x))
            else:
                V1 = sval(s, x)
                carry = s
            u = {"d": cal[t], "t": t, "x": x, "r": (V1 / s.units - 1) * 100 if s.units > 0 else None, "hd": x - t,
                 "to": s.buy / s.Vo if s.Vo > 0 else None,
                 "cost": (s.cpu + s.cost / s.units) * 100 if s.units > 0 else None,
                 "n": len(picks), "lim": s.lim, "lock": s.lock}
            if knobs:
                u.update({"gap": s.ngap, "stop": s.nstop})
            out_units[k] = u
    if log is not None:
        for s in subs_made:
            log.extend(s.log)
    return {"units": [out_units[k] for k in valid if k in out_units], "curve": curve}


def vs_ew(acc: dict, ew: dict) -> list[dict]:
    """策略帳戶與同一批股票等權帳戶逐期對齊 → 每期 xe＝策略 − 等權（%）。"""
    e = {u["t"]: u["r"] for u in ew["units"]}
    out = []
    for u in acc["units"]:
        b = e.get(u["t"])
        out.append({**u, "ew": b, "xe": None if b is None or u["r"] is None else u["r"] - b})
    return out


# ── 因子檢定 ──────────────────────────────────────────────────────────

def quint_per(P, rows: list, k: int = 5, asc: bool = False, min_per: int = 5) -> list[dict]:
    """rows＝[(t, x, {代號: 分數})]。各期依分數分 k 組（每組等權、開盤 t+1 → 收盤 x、未扣成本）。
    第 k 組＝策略選的那一端（asc＝分數低的那端）；sp＝第 k 組 − 第 1 組（%）。每組至少 min_per 檔才算該期。"""
    per = []
    for t, x, sc in rows:
        j = t + 1
        if x is None or j > x or j >= P.T:
            continue
        rr = []
        for c, v in sc.items():
            s = P.s[c]
            o = s["o"][j]
            cx = P.close_on_or_before(c, x, j)
            if o and cx:
                rr.append((v, cx / o - 1))
        if len(rr) < k * min_per:
            continue
        rr.sort(key=lambda z: (z[0], z[1]))
        n = len(rr)
        grp = [statistics.mean(r for _, r in rr[g * n // k:(g + 1) * n // k]) * 100 for g in range(k)]
        if asc:
            grp = grp[::-1]
        ic = spearman([v for v, _ in rr], [r for _, r in rr])
        per.append({"d": P.cal[t], "q": grp, "sp": grp[-1] - grp[0], "ic": None if ic is None else (-ic if asc else ic),
                    "n": n})
    return per


def fac_summary(per: list[dict], k: int = 5) -> dict:
    if not per:
        return {"n": 0}
    sp = [p["sp"] for p in per]
    ics = [p["ic"] for p in per if p["ic"] is not None]
    q = [statistics.mean(p["q"][g] for p in per) for g in range(k)]
    return {"n": len(per), "q": q, "sp": statistics.mean(sp), "t": nw_t(sp), "pos": 100 * sum(1 for v in sp if v > 0) / len(sp),
            "ic": statistics.mean(ics) if ics else None, "ic_t": nw_t(ics), "mono": spearman(list(range(k)), q),
            "uni": statistics.mean(p["n"] for p in per), "d0": per[0]["d"], "d1": per[-1]["d"]}


def quint(P, rows: list, k: int = 5, asc: bool = False, min_per: int = 5) -> dict:
    per = quint_per(P, rows, k, asc, min_per)
    return {**fac_summary(per, k), "per": per} if per else {"n": 0}


def subperiods(per: list[dict], edges: list[str], key: str = "sp") -> list[dict]:
    """依日期切段（edges＝各段起日）→ 每段平均與期數。"""
    out = []
    for a, z in zip(edges, edges[1:] + ["9999"]):
        xs = [p[key] for p in per if a <= p["d"] < z and p.get(key) is not None]
        out.append({"from": a, "n": len(xs), "avg": statistics.mean(xs) if xs else None})
    return out


# ── 逐筆交易 ─────────────────────────────────────────────────────────

def ew_index(P, E: Elig, b: str) -> tuple[list, list]:
    """同一範圍的等權指數（每天依前一日合格名單重新等權）：(收盤指數, 開盤指數)。單日漲跌超過 11% 視為資料錯誤不計。"""
    T = P.T
    I, IO = [None] * T, [None] * T
    lvl = 1.0
    I[0] = lvl
    for i in range(1, T):
        rs, gs = [], []
        for c in E(i - 1, b):
            s = P.s[c]
            c0, c1 = s["c"][i - 1], s["c"][i]
            if not (c0 and c1) or abs(c1 / c0 - 1) > 0.11:
                continue
            rs.append(c1 / c0)
            o1 = s["o"][i]
            if o1 and abs(o1 / c0 - 1) <= 0.11:
                gs.append(o1 / c0)
        if rs:
            IO[i] = lvl * (statistics.mean(gs) if gs else 1.0)
            lvl *= statistics.mean(rs)
        I[i] = lvl
    return I, IO


def trade_units(trades: list[dict], P, EW: dict, *, b_fix: str | None = None, old_cost: float = 0.585,
                mult: float = 1.0) -> list[dict]:
    """既有逐筆交易（r 已扣舊成本 old_cost%）→ v3 單位：r 改扣新成本、xe＝對同一範圍等權（同一段時間）。
    交易需有 c、d（訊號日）、held（出場日 − 訊號日）；範圍依訊號日市值（b_fix 指定時用它）。"""
    ix = {d: i for i, d in enumerate(P.cal)}
    out = []
    for tr in trades:
        if tr.get("st") != "closed" or tr.get("r") is None or tr.get("held") is None:
            continue
        t = ix.get(tr["d"])
        c = tr["c"]
        if t is None:
            continue
        b = b_fix or (bucket_of(P.cap[c][t]) if c in P.cap else None)
        if b is None:
            continue
        j, x = t + 1, t + tr["held"]
        if x >= P.T:
            continue
        r = tr["r"] + old_cost - rt_cost(b, mult) * 100
        I, IO = EW[b]
        e = (I[x] / IO[j] - 1) * 100 if I[x] and IO[j] else None
        out.append({"d": tr["d"], "c": c, "b": b, "t": t, "x": x, "hd": x - t, "r": r,
                    "xe": None if e is None else r - e})
    return out


def slots(P, units: list[dict], *, n: int = 8) -> dict:
    """逐筆交易放進資金帳戶：最多 n 檔、每筆以進場當時淨值的 1/n 買進（成本已在 r 內），滿檔時略過新訊號。
    進場＝訊號日 t+1 開盤、出場＝x 收盤，中間逐日以收盤估值。→ {"curve", "taken", "skipped"}"""
    S = P.s
    evs = sorted(units, key=lambda u: (u["t"], u["c"]))
    if not evs:
        return {"curve": [], "taken": 0, "skipped": 0}
    i0, i1 = evs[0]["t"], max(u["x"] for u in evs)
    cash, pos = 1.0, []                                   # pos：[代號, 進場資金, 進場價, 出場日, 淨報酬]
    curve, taken, skipped = [], 0, 0
    k = 0
    for i in range(i0, i1 + 1):
        while k < len(evs) and evs[k]["t"] + 1 == i:
            u = evs[k]
            k += 1
            if len(pos) >= n:
                skipped += 1
                continue
            o = S[u["c"]]["o"][i]
            if not o:
                skipped += 1
                continue
            eq = cash + sum(_pv(S, p, i - 1) for p in pos)
            amt = min(cash, eq / n)
            if amt <= 0:
                skipped += 1
                continue
            cash -= amt
            pos.append([u["c"], amt, o, u["x"], u["r"] / 100])
            taken += 1
        for p in [p for p in pos if p[3] == i]:
            cash += p[1] * (1 + p[4])
            pos.remove(p)
        curve.append((i, cash + sum(_pv(S, p, i) for p in pos)))
    return {"curve": curve, "taken": taken, "skipped": skipped}


def _pv(S, p, i):
    """持有中部位以收盤估值（找不到收盤用進場價）。"""
    c = S[p[0]]["c"]
    for k in range(i, max(i - 10, -1), -1):
        if c[k]:
            return p[1] * c[k] / p[2]
    return p[1]


# ── 評級 v3（第 6c 節） ───────────────────────────────────────────────

def robust(sel: dict, x2: float | None, nb: dict | None) -> list[str]:
    """穩健度未過的項目。"""
    fails = []
    if x2 is None or x2 <= 0:
        fails.append("成本加倍後沒有贏同一批股票" if x2 is not None else "沒有成本加倍結果")
    if not nb or not nb.get("n"):
        fails.append("尚未做參數鄰近檢查")
    elif nb["pos"] < math.ceil(2 * nb["n"] / 3):
        fails.append(f"參數鄰近 {nb['n']} 組中 {nb['pos']} 組為正（需 ≥{math.ceil(2 * nb['n'] / 3)}）")
    if sel.get("drop5") is None or sel["drop5"] <= 0:
        fails.append("去掉最好的 5% 後沒有贏同一批股票")
    return fails


def grade3(sel: dict, pay: dict, x2: float | None, nb: dict | None, *, event: bool = False,
           oos: dict | None = None, fwd: dict | None = None) -> dict:
    """→ {"grade", "why", "rob"}。sel＝sel_stats、pay＝payoff、x2＝成本加倍後的選股平均、nb＝參數鄰近
    {n, pos}（以選股平均計）、oos＝樣本外 sel_stats、fwd＝前瞻 sel_stats。
    沒有樣本外資料的策略以前瞻代替樣本外（第 6c 節）：前瞻滿期數且平均 >0 ＝樣本外條件過；滿期數而為負 ＝反向 → C。"""
    rob = robust(sel, x2, nb)
    n_min = 4 if event else 10
    need = 2 if event else 10
    has_oos = bool(oos and oos.get("n"))
    fwd_full = bool(fwd and fwd.get("n", 0) >= need and fwd.get("xe") is not None)
    why: list[str] = []
    c = []
    if sel.get("n", 0) < n_min:
        c.append(f"樣本 {sel.get('n', 0)} {'次' if event else '筆'}，不足 {n_min}")
    if nb and nb.get("n") and nb["pos"] * 2 < nb["n"]:
        c.append(f"參數稍微改動就失效（鄰近 {nb['n']} 組只有 {nb['pos']} 組為正）")
    if sel.get("n") and sel["xe"] <= 0:
        c.append(f"平均沒有贏同一批股票（{sel['xe']:+.2f}%）")
    if not pay.get("ok"):
        c.append(_pay_why(pay))
    if has_oos and oos["xe"] < 0:
        c.append(f"樣本外反向（{oos['xe']:+.2f}%）")
    if not has_oos and fwd_full and fwd["xe"] < 0:
        c.append(f"前瞻反向（{fwd['xe']:+.2f}%，沒有樣本外資料時以前瞻代替）")
    if len(rob) > 1:
        c.append("穩健度兩項以上未過：" + "；".join(rob))
    if c:
        return {"grade": "C", "why": c, "rob": rob}
    if rob:
        why += rob
    if sel.get("t") is None or sel["t"] < 2:
        why.append(f"選股超額 t 值 {sel.get('t') or 0:.2f}（A 級需 ≥2）")
    if not has_oos:
        if not (fwd_full and fwd["xe"] > 0):
            why.append("樣本外尚未驗證")
    elif oos["xe"] <= 0 or (oos.get("t") or 0) < 1:
        why.append(f"樣本外 {oos['xe']:+.2f}%、t {oos.get('t') or 0:.2f}（A 級需同號且 t ≥1）")
    if not fwd or fwd.get("n", 0) < need:
        why.append(f"前瞻 {fwd.get('n', 0) if fwd else 0} {'次' if event else '筆'}（A 級需滿 {need}）")
    elif fwd["xe"] <= 0:
        why.append(f"前瞻平均 {fwd['xe']:+.2f}%（A 級需 >0）")
    return {"grade": "B" if why else "A", "why": why, "rob": rob}


def low_dd_side(acc: dict, ew: dict) -> dict:
    """單一期間（樣本內或樣本外）的資金帳戶對同一批股票：年化差、回落倍數、報酬÷回落是否較好（第 15b 節第 2～4 條）。"""
    c, m, ec, em = (acc or {}).get("cagr"), (acc or {}).get("mdd"), (ew or {}).get("cagr"), (ew or {}).get("mdd")
    if None in (c, m, ec, em) or em <= 0:
        return {"ok": False, "gap": None, "ddr": None}
    gap, ddr = c - ec, m / em
    calmar = (c / m if m > 0 else math.inf) >= ec / em
    return {"ok": gap > -LOWDD["gap"] and ddr <= LOWDD["dd"] and calmar, "gap": gap, "ddr": ddr, "calmar": calmar}


def low_dd(ins: dict, oos: dict | None, *, cagr2: float | None, nb_ok: tuple | None, n_min: int) -> dict:
    """低回落例外（docs/backtest_v3_plan.md 第 15 節）。ins／oos＝{"sel", "pay", "acc", "ew"}；cagr2＝樣本內成本加倍後的
    資金帳戶年化；nb_ok＝(參數鄰近中同時符合第 2、3 條的格數, 總格數)。只在選股沒過時用來把 C 改成 B。"""
    fails = []
    if (ins.get("sel") or {}).get("n", 0) < n_min:
        fails.append("樣本不足")
    si = low_dd_side(ins.get("acc"), ins.get("ew"))
    so = low_dd_side(oos.get("acc"), oos.get("ew")) if oos and (oos.get("sel") or {}).get("n") else None
    for nm, part, sd in (("樣本內", ins, si), ("樣本外", oos, so)):
        if sd is None:
            continue
        if not (part.get("pay") or {}).get("ok"):
            fails.append(f"{nm}報酬型態沒過")
        if sd["gap"] is None:
            fails.append(f"{nm}資金帳戶資料不足")
            continue
        if sd["gap"] <= -LOWDD["gap"]:
            fails.append(f"{nm}年化少 {abs(sd['gap']):.1f} 個百分點")
        if sd["ddr"] > LOWDD["dd"]:
            fails.append(f"{nm}回落是 {sd['ddr']:.2f} 倍")
        elif not sd["calmar"]:
            fails.append(f"{nm}年化÷回落較差")
    ec = ((ins.get("ew") or {}).get("cagr"))
    if cagr2 is None or ec is None or cagr2 - ec <= -LOWDD["gap"]:
        fails.append("成本加倍後年化少 3 個百分點以上")
    if not nb_ok or nb_ok[0] < LOWDD["nb"]:
        fails.append(f"參數鄰近 {nb_ok[0] if nb_ok else 0}／{nb_ok[1] if nb_ok else 9} 組符合（需 ≥{LOWDD['nb']}）")
    return {"ok": not fails, "fails": fails, "gap": si.get("gap"), "ddr": si.get("ddr"),
            "gap_oos": so.get("gap") if so else None, "ddr_oos": so.get("ddr") if so else None,
            "nb": list(nb_ok) if nb_ok else None}


def low_dd_why(ld: dict) -> str:
    gp = lambda g: f"{'少' if g < 0 else '多'} {abs(g):.1f} 個百分點"
    t = f"低回落例外：選股沒贏同一批股票，但扣成本後賺錢；年化比同一批股票{gp(ld['gap'])}、最大回落只有 {ld['ddr']:.2f} 倍（樣本內）"
    if ld.get("gap_oos") is not None:
        t += f"，樣本外{gp(ld['gap_oos'])}、{ld['ddr_oos']:.2f} 倍"
    return t + "；最高 B"


def _pay_why(p: dict) -> str:
    if not p.get("n"):
        return "沒有已出場的交易"
    r = "—" if p.get("ratio") is None else ("∞" if p["ratio"] == math.inf else f"{p['ratio']:.1f}")
    return (f"報酬型態未達門檻：賺錢機率 {p['win']:.0f}%、每月平均 {p['m']:+.2f}%、賺賠比 {r}"
            f"（需 ≥60% 且每月 ≥+1%，或 ≥40%、賺賠比 ≥2.5、每月 ≥+2%）")
