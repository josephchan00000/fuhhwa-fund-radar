"""飆股前瞻記錄（規格 sxlivespec VER 3；docs/lab_core70_plan.md 第 14、19 節、docs/lab_review_plan.md 第 9.1 節）。
VER 2：R60（PLAN_BOOK）那本帳放進交易計畫（台股機動的一半）、上配置頁——plan_state() 給頁面現在的持股、要買賣的、名單；
A、R1 兩本照舊只記、不上頁面、不放錢。
VER 3：R60 照回測那本帳 TAKE（10/22）收盤的狀態接手（data/lab/sxlive_seed.json，scripts/run_sxlive_seed.py 只算一次）；
成績從 TAKE 收盤起算（Book.take／place）；持股另給 take、bt（回測買的）、rl（上線以來）。
每週紀錄另記 why（R60 每一檔符合哪幾條規則與當時的數字；配置頁寫「符合：…」，docs/lab_cfg_v2_plan.md 第 3.1 節⑥）。

  update(DL, ctx)   每次建頁算一次：補記新的訊號週（只增不改）、從 START 起重算三本帳照做的成績與兩個對照；
                    只有 CI（GITHUB_ACTIONS＝true）寫回 data/lab/sxlive.json。摘要放 LAST（valog 讀，檢討日推播提醒）。
  Book              照做：tw-superstock-lab engine.Simulator＋combos.run 固定權重模式的同一套規則
                    （tests/test_sxlive.py 用同一份價格對照引擎：每天的資產、每一筆交易都相同）。
  rules_for(y, b)   那一年那本帳的規則（data/lab/sxlive_rules.json；2027 起由 scripts/run_sxlive_rules.py 找）。
價格＝頁面同一份（官方收盤＋Yahoo 補缺、口徑連續化）乘上官方除權息參考價的還原倍數（含息）。
和引擎唯一不同：資料最後幾天還在上市、只是沒成交（停牌）的股票不當成下市——引擎跑的是完整歷史，不會遇到這種情況。
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import os
from datetime import date, timedelta

from . import sxlivespec as S
from . import store

LAST: dict = {}                       # 這一次建頁的摘要（valog 讀）
LIM = 0.10 - 0.015                    # 一價到底漲跌停：漲跌幅 ≥ 漲跌停 − 1.5 個百分點（tw-superstock-lab labpanel.locks）
NAMES = {"R60": "新飆股", "A": "舊目標", "R1": "頁面飆股"}


def _ok(x) -> bool:
    return x is not None and x == x


# ── 規則 ─────────────────────────────────────────────────────────────

def load_rules() -> dict:
    doc = store.read_json(S.RULES_FILE, {}) or {}
    return doc.get("years") or {}


def rules_for(y: int, book: str, R: dict | None = None) -> list | None:
    """y 年 book 的規則 [[(特徵, 運算, 門檻)…]…]；那一年還沒找 → None；找了但一條都沒有 → []（那一年沒有訊號）。"""
    b = ((R if R is not None else load_rules()).get(str(y)) or {}).get(book)
    if b is None:
        return None
    return [[tuple(c) for c in r["conds"]] for r in b.get("rules") or []]


def digest(rules: list) -> str:
    return hashlib.sha1(json.dumps([[list(c) for c in r] for r in rules], ensure_ascii=False).encode()).hexdigest()[:10]


# ── 訊號日 ───────────────────────────────────────────────────────────

def week_ends(start: str, end: str) -> list[str]:
    """[start, end] 之間每週的最後一個交易日（證交所官方休市表）；最後一個交易日在 end 之後的那一週還沒結束、不算。"""
    from .. import twholidays
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    out = []
    w = d0 - timedelta(days=d0.weekday())
    while w <= d1:
        days = [w + timedelta(k) for k in range(5) if twholidays.is_closed(w + timedelta(k)) is not True]
        if days and d0 <= days[-1] <= d1:
            out.append(days[-1].isoformat())
        w += timedelta(7)
    return out


def complete(DL, d: str) -> bool:
    """那一天上市、上櫃的官方收盤都進來了。"""
    doc = (getattr(DL, "mkt", None) or {}).get(d) or {}
    return bool(doc.get("q_tw")) and bool(doc.get("q_tp"))


def context(DL) -> dict:
    """頁面每天算飆股候選的同一套物件（company.market_table；那裡也可以用 keep 交出同一份，免得算兩次）。"""
    from . import bt3d, company, v3data
    from . import packtest as PT
    from . import superx as SX
    lst = company.listed_now()
    iss = DL.issued()
    P = PT.Px(DL, [c for c in sorted(lst) if c in iss], iss)
    cal = P.cal
    for c in P.codes:
        P.cap[c] = [None] * len(cal)
    pxs = {c: SX.Px(P.s[c], cal) for c in P.codes}
    fs, eps, rev = v3data.load_fs(), bt3d.mops_quarterly(), PT.load_rev()
    funds = {c: SX.Fund(company.quarters(fs.get(c), eps.get(c)), rev.get(c) or {}) for c in P.codes}
    qs, rf = SX.avail_index(cal)
    return {"DL": DL, "P": P, "pxs": pxs, "funds": funds, "qitems": sorted((t, q) for q, t in qs.items()), "rf": rf,
            "snaps": bt3d.month_end_caps(), "listed": set(lst)}


WHY_MAX = 60                          # 每週每本最多記幾檔「符合哪幾條」（配置頁只列前 20）


def _jv(x):
    """記進紀錄的數字（JSON；整數、布林照原樣，小數四位有效）。"""
    if x is None or isinstance(x, bool):
        return x
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or math.isinf(v):
        return None
    return int(v) if v == int(v) and abs(v) < 1e15 else float(f"{v:.4g}")


def day_signals(j: int, ctx: dict, sets: dict, why: dict | None = None) -> dict:
    """第 j 天收盤：合格（superx）、那天有成交、符合任一條規則 → {本: [[代號, RS]…]}，RS 高到低、同分依代號。
    why（dict）＝另外記每一檔符合哪幾條（規則在那一年清單裡的順序）與那幾條用到的數字：
    {本: {代號: {"k": [第幾條…], "v": {條件: 數字}}}}（前 WHY_MAX 檔；只給頁面顯示，不影響訊號）。"""
    from . import superx as SX
    P = ctx["P"]
    cal = P.cal
    sd = [d for d, _ in ctx["snaps"]]
    k = bisect.bisect_right(sd, cal[j]) - 1
    snap = ctx["snaps"][k][1] if k >= 0 else {}
    for c in P.codes:                                   # 合格判斷的市值＝最近月底快照（同研究、同頁面）
        P.cap[c][j] = snap.get(c)
    F = SX.feats_on(j, P, ctx["pxs"], ctx["funds"], ctx["qitems"], ctx["rf"], all_rows=True)
    out = {}
    for b, rules in sets.items():
        preds = [SX.rule_pred(r) for r in rules]
        hit = sorted(((c, f["rs"]) for c, f in F.items()
                      if f.get("el") and P.s[c]["c"][j] is not None and any(p(f) for p in preds)),
                     key=lambda x: (-x[1], x[0]))
        out[b] = [[c, rs] for c, rs in hit]
        if why is not None:
            wb = {}
            for c, _ in hit[:WHY_MAX]:
                f = F[c]
                ks = [k for k, p in enumerate(preds) if p(f)]
                feats = sorted({cond[0] for k in ks for cond in rules[k]})
                wb[c] = {"k": ks, "v": {x: _jv(f.get(x)) for x in feats}}
            why[b] = wb
    return out


def why_text(rules: list | None, w: dict | None) -> tuple[str | None, int]:
    """符合的第一條規則寫成「實際數字（要多少）」、另外還符合幾條（只影響顯示）。沒有紀錄＝(None, 0)。"""
    from . import superx as SX
    if not rules or not w or not w.get("k"):
        return None, 0
    ks = [k for k in w["k"] if 0 <= k < len(rules)]
    if not ks:
        return None, 0
    v = w.get("v") or {}
    return "、".join(SX.cond_value_text(tuple(c), v.get(c[0])) for c in rules[ks[0]]), len(ks) - 1


def _why_lines(rules: list | None, w: dict | None) -> list[str]:
    t, more = why_text(rules, w)
    if not t:
        return []
    return [f"符合：{t}" + (f"（另外也符合 {more} 條）" if more else "")]


def add_week(weeks: dict, d: str, sig: dict, t: str, r1v: str | None = None, why: dict | None = None) -> bool:
    """把第 d 週算出來的訊號併進紀錄：已經記過的本不改；這一週先記過、後來才補上的本標 late。→ 有沒有變。
    why＝day_signals 記的「符合哪幾條」（只記跟著這一本一起新增的；配置頁顯示用）。"""
    old = weeks.get(d)
    new = dict(old) if old else {"t": t}
    changed = False
    for b in S.BOOKS:
        if b in sig and b not in new:
            new[b] = sig[b]
            changed = True
            if old is not None:
                new["late"] = sorted(set(new.get("late") or []) | {b})
            if b == "R1" and r1v:
                new["r1v"] = r1v
            if why and b in why:
                new["why"] = {**(new.get("why") or {}), b: why[b]}
    if changed:
        weeks[d] = new
    return changed


# ── 照做（引擎同一套） ─────────────────────────────────────────────────

def series(o: list, h: list, l: list, c: list, f: list, av: list, avv: list) -> dict:
    """一檔的引擎欄位：含息 o h l c、f＝含息價 ÷ 成交價、av／avv＝含當天的 20 日平均成交值／量、c 往前補、一價到底漲跌停、最後有收盤的那天。"""
    T = len(c)
    cff, prev = [None] * T, None
    for i, x in enumerate(c):
        if x is not None:
            prev = x
        cff[i] = prev
    lu, ld = [False] * T, [False] * T
    for i in range(1, T):
        x = c[i]
        if x is None or None in (o[i], h[i], l[i]) or not cff[i - 1]:
            continue
        if o[i] == h[i] == l[i] == x:
            r = x / cff[i - 1] - 1
            lu[i], ld[i] = r >= LIM, r <= -LIM
    last = max((i for i, x in enumerate(c) if x is not None), default=-1)
    return {"o": o, "h": h, "l": l, "c": c, "cff": cff, "f": f, "av": av, "avv": avv, "lu": lu, "ld": ld, "last": last}


def panel(ctx: dict, codes, ev: dict | None = None) -> dict:
    """codes 的引擎欄位（頁面同一份價量 × 官方除權息還原倍數）。av＝頁面的 20 日均成交值（同 superx 合格判斷）。"""
    from . import bt3d
    from . import packtest as PT
    P = ctx["P"]
    cal = P.cal
    ev = bt3d.events() if ev is None else ev
    out = {}
    for c in codes:
        s = P.s.get(c)
        if not s:
            continue
        F = bt3d.factor_events(cal, [(d, f) for d, f, _ in ev.get(c) or []])
        adj = [[None if x is None else x * F[i] for i, x in enumerate(s[k])] for k in ("o", "h", "l", "c")]
        out[c] = series(*adj, F, P.liq.get(c) or [None] * len(cal), PT._rmean(s["v"], 20, 1))
    return out


class Book:
    """照做一本帳（engine.Simulator 用到的部分；順序與算式照抄，見檔頭）。"""

    def __init__(self, px: dict, n: int, listed: set | None = None, T: dict | None = None):
        self.px, self.n, self.listed, self.T = px, n, listed, T or S.TRADE
        self.cash = float(self.T["capital"])
        self.eq_prev = self.cash
        self.pos: dict[str, dict] = {}
        self.orders: list[tuple] = []
        self.trades: list[list] = []

    def _fee(self, v: float) -> float:
        return 0.0 if v <= 0 else max(self.T["min_fee"], v * self.T["commission"] * self.T["discount"])

    def _slip(self, av) -> float:
        tiers = self.T["slip_tiers"]
        s = tiers[-1][1]
        if _ok(av):
            for floor, bp in tiers:
                if av >= floor:
                    s = bp
                    break
        return s

    def _lots(self, sh: float) -> float:
        return float(math.floor(sh / self.T["lot"]) * self.T["lot"])

    @staticmethod
    def _prev(a: list, i: int):
        return a[i - 1] if i > 0 else None

    def _tradable(self, c: str, i: int) -> bool:
        p = self.px[c]
        return _ok(p["o"][i]) and _ok(p["c"][i])

    def value(self, i: int) -> float:
        tot = 0.0
        for c, q in self.pos.items():
            p = self.px[c]
            tot += q["k"] * (p["c"][i] if _ok(p["c"][i]) else p["cff"][i])
        return tot

    def _buy(self, i: int, c: str, si: int) -> bool:
        T, p = self.T, self.px[c]
        f, pa = p["f"][i], p["o"][i]
        if not (_ok(f) and f > 0 and _ok(pa) and pa > 0):
            return False
        px = pa * (1 + self._slip(self._prev(p["av"], i)))
        raw = px / f
        eq = self.eq_prev
        sh = min(T["weight"] * eq, T["max_weight"] * eq) / raw
        adv = self._prev(p["avv"], i)
        if _ok(adv) and T["max_adv"] < math.inf:
            sh = min(sh, T["max_adv"] * adv)
        rate = T["commission"] * T["discount"]
        sh = self._lots(min(sh, self.cash / (raw * (1 + rate))))
        while sh > 0 and sh * raw + self._fee(sh * raw) > self.cash + 1e-6:
            sh = self._lots(sh - T["lot"])
        if sh <= 0:
            return False
        v = sh * raw
        fee = self._fee(v)
        self.cash -= v + fee
        self.pos[c] = {"k": sh / f, "sh": sh, "ei": i, "si": si, "epx": px, "cin": v + fee, "pend": None}
        return True

    def _sell(self, i: int, c: str, pa: float, why: str, slip: bool = True) -> None:
        p, q = self.px[c], self.pos[c]
        px = pa * (1 - (self._slip(self._prev(p["av"], i)) if slip else 0.0))
        gross = q["k"] * px
        net = gross - self._fee(gross) - max(0.0, gross) * self.T["sell_tax"]
        self.cash += net
        t = [c, q["si"], q["ei"], min(i, self.n - 1), net / q["cin"] - 1, why, q["sh"], net - q["cin"]]
        if q.get("v0"):                                    # VER 3：接手時拿著的 → 另記接手以來（÷ 接手那天收盤市值）
            t += [net / q["v0"] - 1, net - q["v0"]]
        self.trades.append(t)
        del self.pos[c]

    def place(self, i: int, today: list | None) -> None:
        """收盤後下明天的單（step 的最後一段；接手那天單獨呼叫）。"""
        if today and i + 1 < self.n:
            pend = {o[0] for o in self.orders}
            for c, sc in today:
                if c in self.pos or c in pend or c not in self.px:
                    continue
                self.orders.append((c, float(sc), i, i + 1))
                pend.add(c)

    def take(self, seed: dict, cal: list[str], i: int) -> float:
        """VER 3：接手——seed 的持股、現金原封不動放進來（股數照那本帳；還原股數用頁面的除權息倍數重算），
        每一檔記下接手那天收盤的市值（v0）。→ 接手那天收盤的總資產。"""
        ix = {d: k for k, d in enumerate(cal)}
        self.cash = float(seed["cash"])
        self.pos, self.orders = {}, []
        for p in seed.get("pos") or []:
            c = p["c"]
            ei, si = ix[p["ent"]], ix[p["sig"]]
            k = p["sh"] / self.px[c]["f"][ei]
            cl = self.px[c]["c"][i] if _ok(self.px[c]["c"][i]) else self.px[c]["cff"][i]
            self.pos[c] = {"k": k, "sh": p["sh"], "ei": ei, "si": si, "epx": p.get("epx"), "cin": p["cin"],
                           "pend": p.get("pend"), "v0": k * cl}
        self.eq_prev = self.cash + self.value(i)
        return self.eq_prev

    def step(self, i: int, today: list | None = None) -> float:
        """第 i 天：下市 → 開盤賣到期的 → 開盤買昨天的訊號 → 收盤標到期 → 收盤後下明天的單。→ 收盤總資產。"""
        T = self.T
        for c in list(self.pos):
            p = self.px[c]
            if p["last"] < i and (self.listed is None or c not in self.listed):
                self._sell(i, c, p["c"][p["last"]], "delisted", slip=False)
        for c in list(self.pos):
            q = self.pos[c]
            if q["pend"] and i - q["ei"] >= 0 and self._tradable(c, i) and not self.px[c]["ld"][i]:
                self._sell(i, c, self.px[c]["o"][i], q["pend"])
        keep = []
        for c, sc, si, until in sorted(self.orders, key=lambda o: -o[1]):
            if c in self.pos:
                continue
            filled = False
            if len(self.pos) < T["max_positions"] and self._tradable(c, i) and not self.px[c]["lu"][i]:
                filled = self._buy(i, c, si)
            if not filled and i < until:
                keep.append((c, sc, si, until))
        self.orders = keep
        for c, q in self.pos.items():
            if not _ok(self.px[c]["c"][i]):
                continue
            if T["hold"] and i - q["ei"] >= T["hold"]:
                q["pend"] = q["pend"] or "time"
        self.place(i, today)
        eq = self.cash + self.value(i)
        self.eq_prev = eq
        return eq


# ── 成績與對照 ─────────────────────────────────────────────────────────

def _mdd(xs: list) -> float | None:
    hi, dd = None, 0.0
    for x in xs:
        if x is None:
            continue
        hi = x if hi is None or x > hi else hi
        dd = max(dd, 1 - x / hi) if hi else dd
    return dd if hi is not None else None


def tr_series(dates: list) -> list:
    """加權報酬指數（含息），以第一天為 1；缺的日子沿用前一天。"""
    q = (store.read_json("v3_tr.json", {}) or {}).get("q") or {}
    out, base, prev = [], None, None
    for d in dates:
        x = q.get(d)
        x = x if x else prev
        prev = x
        if base is None and x:
            base = x
        out.append(x / base if x and base else None)
    return out


def ew_series(ctx: dict, i0: int, i1: int, ev: dict | None = None) -> list:
    """合格股票等權（每天再平衡、含息、不含成本）：前一天合格（superx 的條件）而且有成交的股票，等權平均當天報酬。"""
    from . import bt3d
    from . import superx as SX
    P, pxs = ctx["P"], ctx["pxs"]
    cal = P.cal
    sd = [d for d, _ in ctx["snaps"]]
    ev = bt3d.events() if ev is None else ev
    adj: dict = {}
    nav, v = [1.0], 1.0
    for t in range(i0 + 1, i1 + 1):
        k = bisect.bisect_right(sd, cal[t - 1]) - 1
        snap = ctx["snaps"][k][1] if k >= 0 else {}
        rs = []
        for c in P.codes:
            s = P.s[c]
            if s["c"][t - 1] is None:
                continue
            lq, cp, first = (P.liq.get(c) or [None] * len(cal))[t - 1], snap.get(c), pxs[c].first
            if not (lq is not None and lq >= SX.LIQ_MIN and cp is not None and cp >= SX.CAP_MIN
                    and first is not None and t - 1 - first >= SX.AGE_MIN):
                continue
            if c not in adj:
                F = bt3d.factor_events(cal, [(d, f) for d, f, _ in ev.get(c) or []])
                cff, prev = [None] * len(cal), None
                for i, x in enumerate(s["c"]):
                    if x is not None:
                        prev = x * F[i]
                    cff[i] = prev
                adj[c] = cff
            a, b = adj[c][t - 1], adj[c][t]
            if a and b:
                rs.append(b / a - 1)
        v *= 1 + (sum(rs) / len(rs) if rs else 0.0)
        nav.append(v)
    return nav


def start_index(cal: list[str]) -> int | None:
    """起算那天收盤：VER 3＝接手那天（TAKE，START 前最後一個交易日）；VER 2 是 START（休市就之後第一個交易日）。"""
    return next((i for i, d in enumerate(cal) if d >= S.TAKE), None)


def load_seed() -> dict | None:
    """接手的狀態（sxlivespec VER 3 ⑥；scripts/run_sxlive_seed.py 只算一次）。版本或接手日不對＝None（R60 照 VER 2 從現金開始）。"""
    doc = store.read_json(S.SEED_FILE, None)
    if not isinstance(doc, dict) or doc.get("take") != S.TAKE or doc.get("book") != S.TAKE_BOOK or (doc.get("ver") or 0) < 3:
        return None
    return doc


def seed_weeks(seed: dict | None) -> dict:
    """接手用到的幾週名單（{訊號日: {"R60": [[代號, RS]…], "why": …}}）；只給頁面查「那週名單第幾名、符合哪一條」。"""
    return dict((seed or {}).get("weeks") or {})


def perf(ctx: dict, weeks: dict, last: str, ev: dict | None = None, seed: dict | None = None) -> dict:
    """TAKE 收盤＝100 起算，到 last 收盤：每天三本帳與兩個對照、已出場與持有中的交易、統計。
    seed（VER 3）＝R60 接手的狀態：持股與現金原封不動放進來、TAKE 那一週的名單在 TAKE 收盤下單；沒有就從現金開始。"""
    from . import bt3d
    P = ctx["P"]
    cal = P.cal
    ix = {d: i for i, d in enumerate(cal)}
    i0, i1 = start_index(cal), ix[last]
    ev = bt3d.events() if ev is None else ev
    sw = seed_weeks(seed)
    codes = sorted({c for w in weeks.values() for b in S.BOOKS for c, _ in w.get(b) or []}
                   | {p["c"] for p in (seed or {}).get("pos") or []}
                   | {c for c, _ in (sw.get(S.TAKE) or {}).get(S.TAKE_BOOK) or []})
    px = panel(ctx, codes, ev)
    dates = cal[i0:i1 + 1]
    cap = float(S.TRADE["capital"])
    nav, trades, opens, stats = {}, {}, {}, {}
    books, base = {}, {}
    for b in S.BOOKS:
        sig = {ix[d]: w[b] for d, w in weeks.items() if b in w and d in ix}
        bk = Book(px, i1 + 1, ctx["listed"])
        if b == S.TAKE_BOOK and seed:
            e0 = bk.take(seed, cal, i0)                    # 接手：TAKE 收盤的狀態
            bk.place(i0, (sw.get(S.TAKE) or {}).get(S.TAKE_BOOK))
            eq = [e0] + [bk.step(i, sig.get(i)) for i in range(i0 + 1, i1 + 1)]
        else:
            e0 = cap
            eq = [bk.step(i, sig.get(i)) for i in range(i0, i1 + 1)]
        books[b], base[b] = bk, e0
        nav[b] = [x / e0 for x in eq]

        def val(c: str, q: dict) -> float:
            return q["k"] * (px[c]["c"][i1] if _ok(px[c]["c"][i1]) else px[c]["cff"][i1])
        trades[b] = [[c, cal[si], cal[ei], cal[xi], round(r * 100, 2), why] + ([round(t[0] * 100, 2)] if t else [])
                     for c, si, ei, xi, r, why, _, _, *t in bk.trades]
        opens[b] = sorted([[c, cal[q["ei"]], i1 - q["ei"], round((val(c, q) / q["cin"] - 1) * 100, 2)]
                           + ([round((val(c, q) / q["v0"] - 1) * 100, 2)] if q.get("v0") else [])
                           for c, q in bk.pos.items()], key=lambda x: (x[1], x[0]))
        live = [(t[8], t[9]) if len(t) > 8 else (t[4], t[7]) for t in bk.trades]   # 接手的那幾筆只算接手以來
        pnl = sorted((x[1] for x in live), reverse=True)
        tot = sum(pnl)
        k = max(1, len(pnl) // 10)
        rets = [x[0] for x in live]
        stats[b] = {"ret": round((nav[b][-1] - 1) * 100, 2), "mdd": round((_mdd(nav[b]) or 0) * 100, 2), "n": len(rets),
                    "win": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1) if rets else None,
                    "avg": round(sum(rets) / len(rets) * 100, 2) if rets else None,
                    "top10": round(sum(pnl[:k]) / tot * 100, 1) if pnl and tot > 0 else None, "open": len(bk.pos)}
    tr = tr_series(dates)
    ew = ew_series(ctx, i0, i1, ev)
    for nm, xs in (("TR", tr), ("EW", ew)):
        ok = [x for x in xs if x is not None]
        stats[nm] = {"ret": round((ok[-1] - 1) * 100, 2) if ok else None, "mdd": round((_mdd(xs) or 0) * 100, 2) if ok else None}
    rows = {d: [None if x is None else round(x * 100, 2) for x in (nav["R60"][k], nav["A"][k], nav["R1"][k], tr[k], ew[k])]
            for k, d in enumerate(dates)}
    return {"nav": rows, "trades": trades, "open": opens, "stats": stats, "_book": books[S.PLAN_BOOK], "_px": px,
            "_base": base[S.PLAN_BOOK], "_i0": i0}


# ── 配置頁（VER 2）：PLAN_BOOK 那本帳現在的狀態 ─────────────────────────────

def _raw(p: dict, k: str, i: int):
    """含息價 → 那一天的成交價（f＝含息價 ÷ 成交價）。"""
    x, f = p[k][i], p["f"][i]
    return x / f if _ok(x) and _ok(f) and f else None


def exit_day(ent: str, cal: list[str]) -> tuple[str, str]:
    """買進日 → (到期日＝買進後第 hold 個交易日收盤, 賣出日＝下一個交易日開盤)；超過資料尾端用證交所休市表往後推。"""
    from .strategy import trading_days_after
    h = S.TRADE["hold"]
    i = cal.index(ent)
    if i + h < len(cal):
        due = cal[i + h]
    else:
        due = trading_days_after(cal[-1], i + h - len(cal) + 1)[-1]
    return due, trading_days_after(due, 1)[0]


def next_week_end(d: str) -> str | None:
    """d 之後的第一個週訊號日（每週最後一個交易日）。"""
    from datetime import date as _d, timedelta as _t
    x = _d.fromisoformat(d)
    ws = week_ends((x + _t(1)).isoformat(), (x + _t(21)).isoformat())
    return ws[0] if ws else None


def plan_state(rec: dict, ctx: dict, names: dict | None = None, trial: list | None = None, R: dict | None = None,
               seed: dict | None = None) -> dict:
    """配置頁（台股）要的 PLAN_BOOK 狀態（sxlivespec VER 2 ②）：持股（買進日、買進價、收盤、報酬、占那本帳多少、到期與賣出日、
    明天開盤要賣）、明天開盤要買的（最新一週名單依 RS，估計現金夠買幾檔）、最新一週的名單、下一次看名单的日子、週中的試算名單。
    比重都是占那本帳；頁面再乘 corespec 的新飆股比重。
    why（名單、要買的、持股）＝那一週符合哪一條規則與實際數字（紀錄的 why；沒有＝空），持股另寫那一週名單第幾名。
    VER 3：seed＝接手的狀態——名單與「第幾名、符合哪一條」也查接手用到的那幾週；持股另給 take（接手時就拿著）、
    bt（買進日不晚於接手那天＝回測）、rl（上線以來：接手那天收盤或之後實際買進起算，含息、不含成本）。"""
    from .strategy import trading_days_after
    P = ctx["P"]
    cal = P.cal
    last = rec.get("last")
    nm = names or {}
    out: dict = {"book": S.PLAN_BOOK, "start": S.START, "take": S.TAKE if seed else None, "d": last, "hold": [], "buy": [],
                 "sell": [], "list": [], "n_list": 0, "wk": None, "cash": 1.0, "trial": trial or [], "hold_n": S.TRADE["hold"],
                 "w": S.TRADE["weight"]}
    if not last or last not in cal:
        return out
    i1 = cal.index(last)
    out["next"] = trading_days_after(last, 1)[0]
    out["next_wk"] = next_week_end(last)
    out["wk_today"] = last in week_ends(last, last)
    W = {**seed_weeks(seed), **(rec.get("weeks") or {})}   # 接手用到的幾週（10/22 以前）＋紀錄（10/30 起），日期不重疊
    wks = sorted(d for d, w in W.items() if S.PLAN_BOOK in w and d <= last)
    _rules: dict = {}

    def why_of(wd: str, c: str) -> list[str]:
        y = int(wd[:4])
        if y not in _rules:
            try:
                _rules[y] = rules_for(y, S.PLAN_BOOK, R)
            except Exception:                              # noqa: BLE001
                _rules[y] = None
        w = ((W.get(wd) or {}).get("why") or {}).get(S.PLAN_BOOK) or {}
        return _why_lines(_rules[y], w.get(c))
    if wks:
        wd = wks[-1]
        L = W[wd][S.PLAN_BOOK]
        out.update({"wk": wd, "n_list": len(L),
                    "list": [{"c": c, "n": nm.get(c, c), "rs": round(float(rs), 1), "why": why_of(wd, c)} for c, rs in L[:S.LIST_SHOW]]})
    bk, px = rec.get("_book"), rec.get("_px") or {}
    if bk is None:
        return out
    eq = bk.eq_prev or 1.0
    out["cash"] = float(bk.cash / eq) if eq else 1.0
    out["nav"] = round(eq / float(rec.get("_base") or S.TRADE["capital"]), 6)
    i0 = rec.get("_i0")
    for c, q in sorted(bk.pos.items(), key=lambda x: (x[1]["ei"], x[0])):
        p = px[c]
        ei = q["ei"]
        cl = p["c"][i1] if _ok(p["c"][i1]) else p["cff"][i1]
        o = p["o"][ei]
        due, sell = exit_day(cal[ei], cal)
        sd = cal[q["si"]]
        rank = next((k + 1 for k, (cc, _) in enumerate((W.get(sd) or {}).get(S.PLAN_BOOK) or []) if cc == c), None)
        why = ([f"{int(sd[5:7])}/{int(sd[8:])} 那週名單第 {rank} 名"] if rank else []) + why_of(sd, c)
        r = float(cl / o - 1) if _ok(cl) and _ok(o) and o else None
        take = bool(q.get("v0")) and i0 is not None
        c0 = (p["c"][i0] if _ok(p["c"][i0]) else p["cff"][i0]) if take else None
        out["hold"].append({"c": c, "n": nm.get(c, c), "ent": cal[ei], "sig": sd, "epx": _raw(p, "o", ei), "why": why,
                            "px": (cl / p["f"][i1]) if _ok(cl) and _ok(p["f"][i1]) and p["f"][i1] else None, "r": r,
                            "w": float(q["k"] * cl / eq) if _ok(cl) and eq else None, "due": due,
                            "out": out["next"] if q["pend"] else sell, "sell": bool(q["pend"]),
                            "take": take, "bt": bool(seed) and cal[ei] <= S.TAKE,
                            "rl": (float(cl / c0 - 1) if _ok(cl) and _ok(c0) and c0 else None) if take else r})
    out["sell"] = [h["c"] for h in out["hold"] if h["sell"]]
    cash = bk.cash + sum(q["k"] * (px[c]["c"][i1] if _ok(px[c]["c"][i1]) else px[c]["cff"][i1]) * (1 - S.TRADE["sell_tax"])
                         for c, q in bk.pos.items() if q["pend"])
    tgt = min(S.TRADE["weight"], S.TRADE["max_weight"]) * eq
    nbuy = 0
    if wks and wks[-1] == last:                            # 最後一天就是訊號日：明天開盤照名單買（Book 在最後一天不下單，這裡照它的規則列）
        cand = [(c, rs) for c, rs in rec["weeks"][last][S.PLAN_BOOK] if c not in bk.pos and c in px]
        for c, rs in sorted(cand, key=lambda x: -x[1]):
            fill = cash >= 0.25 * tgt and len(bk.pos) - len(out["sell"]) + nbuy < S.TRADE["max_positions"]
            out["buy"].append({"c": c, "n": nm.get(c, c), "rs": round(float(rs), 1), "fill": bool(fill), "why": why_of(last, c)})
            if fill:
                nbuy += 1
                cash -= min(tgt, cash)
    out["n_buy"] = nbuy
    return out


def trial_list(ctx: dict, d: str, R: dict | None = None, why: dict | None = None) -> list:
    """週中：到 d 收盤為止符合 PLAN_BOOK 那一年規則的股票（day_signals 同一套；只是試算、不記錄）。
    why（dict）＝另外填 {代號: {"k", "v"}}（符合哪幾條）。"""
    rules = rules_for(int(d[:4]), S.PLAN_BOOK, R)
    if not rules or d not in ctx["P"].cal:
        return []
    wy: dict = {}
    out = day_signals(ctx["P"].cal.index(d), ctx, {S.PLAN_BOOK: rules}, why=wy).get(S.PLAN_BOOK) or []
    if why is not None:
        why.update(wy.get(S.PLAN_BOOK) or {})
    return out


def ytd_part(rec: dict, ctx: dict, last: str | None) -> dict | None:
    """今年逐月、逐筆表（ytdspec VER 1）要的：PLAN_BOOK 接手以後每天的總資產與每一筆（元，那本帳自己的規模）。
    → {"take", "e0"（接手那天收盤）, "eq": {日期: 總資產}, "closed": [[代號, 買進日, 賣出日, 報酬, 原因, 賺賠, 股數, 接手以來賺賠|None]],
       "open": [[代號, 買進日, 買進成本, 接手那天的市值|None, 最新市值, 股數]]}；沒有接手的狀態或還沒算＝None。"""
    bk, e0, px = rec.get("_book"), rec.get("_base"), rec.get("_px")
    if bk is None or not e0 or not px or not last:
        return None
    cal = ctx["P"].cal
    i1 = cal.index(last)
    eq = {d: round(v[0] / 100 * e0, 2) for d, v in (rec.get("nav") or {}).items() if v and v[0] is not None}
    closed = []
    for t in bk.trades:
        c, si, ei, xi, r, why, sh, pnl, *tk = t
        closed.append([c, cal[ei], cal[xi], round(float(r), 6), why, round(float(pnl), 2), float(sh),
                       round(float(tk[1]), 2) if tk else None])
    opens = []
    for c, q in sorted(bk.pos.items(), key=lambda x: (x[1]["ei"], x[0])):
        p = px[c]
        v = q["k"] * (p["c"][i1] if _ok(p["c"][i1]) else p["cff"][i1])
        opens.append([c, cal[q["ei"]], round(float(q["cin"]), 2), round(float(q["v0"]), 2) if q.get("v0") else None,
                      round(float(v), 2), float(q["sh"])])
    return {"take": S.TAKE, "e0": round(float(e0), 2), "eq": eq, "closed": closed, "open": opens}


# ── 紀錄 ─────────────────────────────────────────────────────────────

def read() -> dict:
    doc = store.read_json(S.LOG_FILE, {}) or {}
    if not isinstance(doc, dict) or doc.get("ver") != S.VER:
        doc = {}
    return {"ver": S.VER, "spec": S.SPEC_DATE, "start": S.START, "weeks": dict(doc.get("weeks") or {})}


def dump(rec: dict) -> str:
    """決定性；每週、每天、每筆各一行（每天只多幾行，git diff 小）。"""
    J = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))  # noqa: E731

    def obj(key: str, items: list) -> list[str]:
        if not items:
            return [J(key) + ":{},"]
        return [J(key) + ":{", ",\n".join(J(k) + ":" + J(v) for k, v in items), "},"]
    out = ["{"] + [J(k) + ":" + J(rec[k]) + "," for k in ("ver", "spec", "start", "last") if k in rec]
    out += obj("weeks", sorted((rec.get("weeks") or {}).items()))
    out += obj("nav", sorted((rec.get("nav") or {}).items()))
    tr = rec.get("trades") or {}
    tl = [J(b) + ":[" + ("\n" + ",\n".join(J(t) for t in tr[b]) + "\n" if tr[b] else "") + "]" for b in S.BOOKS if b in tr]
    out.append(J("trades") + ":{" + ("\n" + ",\n".join(tl) + "\n" if tl else "") + "},")
    out.append(J("open") + ":" + J(rec.get("open") or {}) + ",")
    out.append(J("stats") + ":" + J(rec.get("stats") or {}))
    out.append("}")
    return "\n".join(out) + "\n"


def write(rec: dict) -> bool:
    p = store.LAB / S.LOG_FILE
    txt = dump(rec)
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return True


def due(last: str | None) -> str | None:
    """last 已經到了的最後一個檢討日（half／year）。"""
    out = None
    for k, d in S.REVIEWS:
        if last and last >= d:
            out = k
    return out


def missing_year(last: str | None, R: dict | None = None) -> int | None:
    """今年（last 那一年）已經有訊號日、規則卻還沒找 → 那一年；其他 → None。"""
    if not last:
        return None
    y = int(last[:4])
    if y <= S.SEED_YEAR or not week_ends(f"{y}-01-01", last):
        return None
    return y if rules_for(y, S.RULE_BOOKS[0], R) is None else None


def update(DL, ctx: dict | None = None, now=None, write_file: bool | None = None) -> dict:
    """補記新的訊號週、重算成績；只有 CI 寫回。→ 紀錄（含 nav、trades、open、stats）。"""
    from .. import clock
    from . import superx as SX
    now = now or clock.now_tw()
    if write_file is None:
        write_file = os.environ.get("GITHUB_ACTIONS") == "true"
    ctx = ctx or context(DL)
    P = ctx["P"]
    cal = P.cal
    ix = {d: i for i, d in enumerate(cal)}
    last = next((cal[i] for i in range(len(cal) - 1, -1, -1) if complete(DL, cal[i])), None)
    rec = read()
    R = load_rules()
    seed = load_seed()
    if seed is None:
        print(f"[sxlive] ⚠ 沒有接手的狀態（data/lab/{S.SEED_FILE}）：新飆股那本帳從現金開始（sxlivespec VER 3 ⑥）")
    r1 = [[tuple(c) for c in conds] for _, conds in SX.live_rules(SX.load_res())]
    r1v = digest(r1) if r1 else None
    t = now.strftime("%Y-%m-%d %H:%M")
    if last and last >= S.START:
        for d in week_ends(S.START, last):
            if d not in ix or not complete(DL, d):
                continue
            w = rec["weeks"].get(d) or {}
            sets = {}
            for b in S.BOOKS:
                if b in w:
                    continue
                rs = (r1 if r1 else None) if b == "R1" else rules_for(int(d[:4]), b, R)
                if rs is not None:
                    sets[b] = rs
            if sets:
                wy: dict = {}
                sg = day_signals(ix[d], ctx, sets, why=wy)
                add_week(rec["weeks"], d, sg, t, r1v, why={b: v for b, v in wy.items() if b == S.PLAN_BOOK})
        rec["last"] = last
        i0 = start_index(cal)
        if i0 is not None and i0 <= ix[last]:
            rec.update(perf(ctx, rec["weeks"], last, seed=seed))
    if write_file:
        write(rec)
    st = rec.get("stats") or {}
    plan = None
    try:                                                   # VER 2：配置頁（台股）要的新飆股狀態；算不出來只少那一塊
        from . import company
        nm = company.names()
        tr = []
        if last and last not in week_ends(last, last):      # 這一週還沒結束：試算到今天收盤為止符合的股票
            tw: dict = {}
            rl = rules_for(int(last[:4]), S.PLAN_BOOK, R)
            tr = [{"c": c, "n": nm.get(c, c), "rs": round(float(rs), 1), "why": _why_lines(rl, tw.get(c))}
                  for c, rs in trial_list(ctx, last, R, why=tw)[:S.LIST_SHOW]]
        plan = plan_state(dict(rec, last=last), ctx, nm, tr, R, seed)  # START 之前（資料停在 START 前一天）也要算下一次看名單的日子
        yp = ytd_part(rec, ctx, last)                      # 今年逐月、逐筆表（ytdspec）：接手以後那本帳的錢
        if plan is not None and yp:
            plan["ytd"] = yp
    except Exception as e:                                 # noqa: BLE001
        print(f"[sxlive] ⚠ 新飆股的配置頁狀態算不出來：{type(e).__name__}: {e}")
    for k in ("_book", "_px", "_base", "_i0"):
        rec.pop(k, None)
    LAST.clear()
    LAST.update({"d": last, "start": S.START, "weeks": len(rec["weeks"]), "due": due(last), "miss": missing_year(last, R),
                 "v": {b: (st.get(b) or {}).get("ret") for b in (*S.BOOKS, "TR", "EW")}, "plan": plan})
    return rec
