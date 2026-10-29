"""飆股前瞻記錄（規格 sxlivespec VER 4；docs/lab_core70_plan.md 第 14、19 節、docs/lab_review_plan.md 第 9.1 節、docs/lab_boom_v2_plan.md 第 8、9 節）。
VER 2：R60（PLAN_BOOK）那本帳放進交易計畫（台股機動的一半）、上配置頁——plan_state() 給頁面現在的持股、要買賣的、名單；
A、R1 兩本照舊只記、不上頁面、不放錢。
VER 3：R60 照回測那本帳 TAKE（10/22）收盤的狀態接手（data/lab/sxlive_seed.json，scripts/run_sxlive_seed.py 只算一次）；
成績從 TAKE 收盤起算（Book.take／place）；持股另給 take、bt（回測買的）、rl（上線以來）。
每週紀錄另記 why（R60 每一檔符合哪幾條規則與當時的數字；配置頁寫「符合：…」，docs/lab_cfg_v2_plan.md 第 3.1 節⑥）。
VER 4：多一本 N8（PLAN_BOOK）——買 R60 的每週名單（LIST_BOOK），固定 8 格（現金 ÷ 空格數）、新上名單的先買，START4 起從現金開始；
選股頁與推播看它（LAST["n8"]，含 pick＝選股頁的名單）。交易計畫、今年逐月表照舊看 R60（LAST["plan"]）。
上名單週數＝連續幾個週末在 R60 名單上：START 以前用 HIST_FILE（scripts/run_sxlive_hist.py 只算一次），START 起用紀錄。

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
NAMES = {"R60": "新飆股", "A": "舊目標", "R1": "頁面飆股", "N8": "新飆股（8 格）"}


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


def feats_at(ctx: dict, j: int) -> dict:
    """第 j 天收盤的特徵（superx.feats_on，全部股票）；合格判斷的市值＝最近月底快照（同研究、同頁面）。"""
    from . import superx as SX
    P = ctx["P"]
    sd = [d for d, _ in ctx["snaps"]]
    k = bisect.bisect_right(sd, P.cal[j]) - 1
    snap = ctx["snaps"][k][1] if k >= 0 else {}
    for c in P.codes:
        P.cap[c][j] = snap.get(c)
    return SX.feats_on(j, P, ctx["pxs"], ctx["funds"], ctx["qitems"], ctx["rf"], all_rows=True)


def day_signals(j: int, ctx: dict, sets: dict, why: dict | None = None) -> dict:
    """第 j 天收盤：合格（superx）、那天有成交、符合任一條規則 → {本: [[代號, RS]…]}，RS 高到低、同分依代號。
    why（dict）＝另外記每一檔符合哪幾條（規則在那一年清單裡的順序）與那幾條用到的數字：
    {本: {代號: {"k": [第幾條…], "v": {條件: 數字}}}}（前 WHY_MAX 檔；只給頁面顯示，不影響訊號）。"""
    from . import superx as SX
    P = ctx["P"]
    F = feats_at(ctx, j)
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


def absorbed(cal: list[str], basis: list | None, close: list, d: str) -> bool:
    """除權息日 d 那一跳是不是已經被頁面價格的口徑連續化（packtest._basis：相鄰收盤差 1.8 倍以上就把更早的價格換算）吃掉了。
    大比例配股或分割（例 2026-08-14 世紀 5314、2026-09-02 緯穎 6669）會這樣；再乘一次除權倍數＝還原兩次，
    持有跨過那天的部位會被算成漲好幾倍（2026-10-29 接手 N8B 時發現）。"""
    if not basis:
        return False
    ie = next((i for i, x in enumerate(cal) if x >= d), None)
    if not ie:
        return False
    jp = next((i for i in range(ie - 1, -1, -1) if close[i] is not None), None)
    return jp is not None and abs(basis[jp] / basis[ie] - 1) > 1e-9


def panel(ctx: dict, codes, ev: dict | None = None) -> dict:
    """codes 的引擎欄位（頁面同一份價量 × 官方除權息還原倍數）。av＝頁面的 20 日均成交值（同 superx 合格判斷）。
    已經被口徑連續化換算過的除權息（absorbed）不再乘。"""
    from . import bt3d
    from . import packtest as PT
    P = ctx["P"]
    cal = P.cal
    ev = bt3d.events() if ev is None else ev
    bas = getattr(P, "basis", {}) or {}
    out = {}
    for c in codes:
        s = P.s.get(c)
        if not s:
            continue
        F = bt3d.factor_events(cal, [(d, f) for d, f, _ in ev.get(c) or [] if not absorbed(cal, bas.get(c), s["c"], d)])
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
        n = T.get("slots")
        if n:                                              # VER 4（N8）：固定 n 格，有空格時把現金平分給空格；一格不到 1/n 的 min_slot 就不買
            free = n - len(self.pos)
            if free <= 0 or eq <= 0:
                return False
            tgt = self.cash / free
            if tgt < T["min_slot"] * eq / n:
                return False
        else:
            tgt = T["weight"] * eq
        sh = min(tgt, T["max_weight"] * eq) / raw
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


def load_seed_bt() -> dict | None:
    """VER 5：N8B（N8 做法的回測延續）在 TAKE 收盤的狀態（scripts/run_sxlive_seed.py --n8 只算一次）；沒有＝None（N8B 不算）。"""
    doc = store.read_json(S.SEED_BT_FILE, None)
    if not isinstance(doc, dict) or doc.get("take") != S.TAKE or doc.get("book") != S.BT_BOOK or (doc.get("ver") or 0) < 5:
        return None
    return doc


def seed_weeks(seed: dict | None) -> dict:
    """接手用到的幾週名單（{訊號日: {"R60": [[代號, RS]…], "why": …}}）；只給頁面查「那週名單第幾名、符合哪一條」。"""
    return dict((seed or {}).get("weeks") or {})


HIST_FROM = "2026-01-01"              # VER 4：HIST_FILE 從這一年開始（之前的週末沒有名單＝斷掉）


def load_hist() -> dict:
    """VER 4：START 以前 2026 年每個週末的 R60 名單 {週末: [[代號, 強度]…]}（scripts/run_sxlive_hist.py 只算一次）；沒有＝{}。"""
    doc = store.read_json(S.HIST_FILE, None)
    if not isinstance(doc, dict) or (doc.get("ver") or 0) < 4:
        return {}
    return dict(doc.get("weeks") or {})


def prior_lists(d: str, weeks: dict, hist: dict, incl: bool = True) -> list[set]:
    """d 那個週末（incl＝False：d 之前）往回每個週末的 R60 名單（新到舊）；哪一個週末沒有名單就停在那裡。
    START 以前用 hist、START 起用紀錄（sxlivespec VER 4 ①）。"""
    ws = week_ends(HIST_FROM, d)
    if not incl:
        ws = [w for w in ws if w < d]
    out = []
    for w in reversed(ws):
        L = ((weeks.get(w) or {}).get(S.LIST_BOOK)) if w >= S.START else hist.get(w)
        if L is None:
            break
        out.append({c for c, _ in L})
    return out


def run_len(c: str, lists: list[set]) -> int:
    n = 0
    for s in lists:
        if c not in s:
            break
        n += 1
    return n


def n8_orders(d: str, weeks: dict, hist: dict) -> list:
    """VER 4：d 那個週末 N8 的下單順序 [[代號, 分數]]——分數＝強度 − 1000 ×（上名單週數 − 1），名單原本的順序（強度高到低）。"""
    L = (weeks.get(d) or {}).get(S.LIST_BOOK) or []
    lists = prior_lists(d, weeks, hist)
    return [[c, float(rs) - 1000.0 * (max(1, run_len(c, lists)) - 1)] for c, rs in L]


def perf(ctx: dict, weeks: dict, last: str, ev: dict | None = None, seed: dict | None = None, hist: dict | None = None,
         seed_bt: dict | None = None) -> dict:
    """TAKE 收盤＝100 起算，到 last 收盤：每天三本帳與兩個對照、已出場與持有中的交易、統計。
    seed（VER 3）＝R60 接手的狀態：持股與現金原封不動放進來、TAKE 那一週的名單在 TAKE 收盤下單；沒有就從現金開始。
    seed_bt（VER 5）＝N8B 接手的狀態（N8 做法的回測延續，今年逐月表用）：TAKE 收盤照它記的 N8 順序下單，之後每週照 R60 名單、N8 的順序；
    沒有就不算 N8B。"""
    from . import bt3d
    P = ctx["P"]
    cal = P.cal
    ix = {d: i for i, d in enumerate(cal)}
    i0, i1 = start_index(cal), ix[last]
    ev = bt3d.events() if ev is None else ev
    sw = seed_weeks(seed)
    codes = sorted({c for w in weeks.values() for b in S.BOOKS for c, _ in w.get(b) or []}
                   | {p["c"] for p in (seed or {}).get("pos") or []}
                   | {c for c, _ in (sw.get(S.TAKE) or {}).get(S.TAKE_BOOK) or []}
                   | {p["c"] for p in (seed_bt or {}).get("pos") or []}
                   | {c for c, _ in ((seed_bt or {}).get("orders") or {}).get(S.TAKE) or []})
    px = panel(ctx, codes, ev)
    dates = cal[i0:i1 + 1]
    cap = float(S.TRADE["capital"])
    nav, trades, opens, stats = {}, {}, {}, {}
    books, base = {}, {}
    hist = load_hist() if hist is None else hist
    for b in S.BOOKS + ((S.BT_BOOK,) if seed_bt else ()):
        if b == S.PLAN_BOOK:                               # VER 4：N8 買 R60 的名單（START4 起），新上名單的先買
            sig = {ix[d]: n8_orders(d, weeks, hist) for d, w in weeks.items()
                   if d >= S.START4 and S.LIST_BOOK in w and d in ix}
            bk = Book(px, i1 + 1, ctx["listed"], T=S.TRADE_N8)
        elif b == S.BT_BOOK:                               # VER 5：N8B 每週照 R60 的名單、N8 的順序（START 起的紀錄）
            sig = {ix[d]: n8_orders(d, weeks, hist) for d, w in weeks.items() if S.LIST_BOOK in w and d in ix}
            bk = Book(px, i1 + 1, ctx["listed"], T=S.TRADE_N8)
        else:
            sig = {ix[d]: w[b] for d, w in weeks.items() if b in w and d in ix}
            bk = Book(px, i1 + 1, ctx["listed"])
        if b == S.TAKE_BOOK and seed:
            e0 = bk.take(seed, cal, i0)                    # 接手：TAKE 收盤的狀態
            bk.place(i0, (sw.get(S.TAKE) or {}).get(S.TAKE_BOOK))
            eq = [e0] + [bk.step(i, sig.get(i)) for i in range(i0 + 1, i1 + 1)]
        elif b == S.BT_BOOK:
            e0 = bk.take(seed_bt, cal, i0)
            bk.place(i0, (seed_bt.get("orders") or {}).get(S.TAKE))
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
    bt = nav.get(S.BT_BOOK)
    rows = {d: [None if x is None else round(x * 100, 2) for x in (nav["R60"][k], nav["A"][k], nav["R1"][k], tr[k], ew[k], nav["N8"][k],
                                                                     bt[k] if bt else None)]
            for k, d in enumerate(dates)}                  # 欄位：R60、A、R1、加權報酬指數、合格股等權、N8（VER 4）、N8B（VER 5）
    return {"nav": rows, "trades": trades, "open": opens, "stats": stats, "_book": books[S.TAKE_BOOK], "_px": px,
            "_base": base[S.TAKE_BOOK], "_i0": i0, "_pbook": books[S.PLAN_BOOK], "_pbase": base[S.PLAN_BOOK],
            "_bt": books.get(S.BT_BOOK), "_btbase": base.get(S.BT_BOOK)}


# ── 頁面：R60（交易計畫）與 N8（選股頁）那本帳現在的狀態 ─────────────────────────────

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
               seed: dict | None = None, book: str | None = None, hist: dict | None = None) -> dict:
    """那本帳現在的狀態（sxlivespec VER 2 ②）：持股（買進日、買進價、收盤、報酬、占那本帳多少、到期與賣出日、
    明天開盤要賣）、明天開盤要買的（最新一週名單依 RS，估計現金夠買幾檔）、最新一週的名單、下一次看名单的日子、週中的試算名單。
    比重都是占那本帳；頁面再乘 corespec 的新飆股比重。
    why（名單、要買的、持股）＝那一週符合哪一條規則與實際數字（紀錄的 why；沒有＝空），持股另寫那一週名單第幾名。
    VER 3：seed＝接手的狀態——名單與「第幾名、符合哪一條」也查接手用到的那幾週；持股另給 take（接手時就拿著）、
    bt（買進日不晚於接手那天＝回測）、rl（上線以來：接手那天收盤或之後實際買進起算，含息、不含成本）。
    VER 4：book＝哪一本（預設 TAKE_BOOK＝R60，交易計畫與今年逐月表用；PLAN_BOOK＝N8，選股頁與推播用）。
    名單一律是 LIST_BOOK（R60）的；N8 要買的照它的順序（新上名單的先、同週數依強度）與 8 格的買法估。"""
    from .strategy import trading_days_after
    P = ctx["P"]
    cal = P.cal
    last = rec.get("last")
    nm = names or {}
    book = book or S.TAKE_BOOK
    n8 = book == S.PLAN_BOOK
    T = S.TRADE_N8 if n8 else S.TRADE
    seed = None if n8 else seed                            # N8 從現金開始，不接手
    out: dict = {"book": book, "start": S.START4 if n8 else S.START, "take": S.TAKE if seed else None, "d": last, "hold": [],
                 "buy": [], "sell": [], "list": [], "n_list": 0, "wk": None, "cash": 1.0, "trial": trial or [],
                 "hold_n": T["hold"], "w": (1 / T["slots"]) if n8 else T["weight"], "slots": T.get("slots")}
    if not last or last not in cal:
        return out
    i1 = cal.index(last)
    out["next"] = trading_days_after(last, 1)[0]
    out["next_wk"] = next_week_end(last)
    out["wk_today"] = last in week_ends(last, last)
    W = {**seed_weeks(seed), **(rec.get("weeks") or {})}   # 接手用到的幾週（10/22 以前）＋紀錄（10/30 起），日期不重疊
    wks = sorted(d for d, w in W.items() if S.LIST_BOOK in w and d <= last)
    _rules: dict = {}

    def why_of(wd: str, c: str) -> list[str]:
        y = int(wd[:4])
        if y not in _rules:
            try:
                _rules[y] = rules_for(y, S.LIST_BOOK, R)
            except Exception:                              # noqa: BLE001
                _rules[y] = None
        w = ((W.get(wd) or {}).get("why") or {}).get(S.LIST_BOOK) or {}
        return _why_lines(_rules[y], w.get(c))
    if wks:
        wd = wks[-1]
        L = W[wd][S.LIST_BOOK]
        out.update({"wk": wd, "n_list": len(L),
                    "list": [{"c": c, "n": nm.get(c, c), "rs": round(float(rs), 1), "why": why_of(wd, c)} for c, rs in L[:S.LIST_SHOW]]})
    bk, px = rec.get("_pbook" if n8 else "_book"), rec.get("_px") or {}
    if bk is None:
        return out
    eq = bk.eq_prev or 1.0
    out["cash"] = float(bk.cash / eq) if eq else 1.0
    out["nav"] = round(eq / float(rec.get("_pbase" if n8 else "_base") or T["capital"]), 6)
    i0 = rec.get("_i0")
    for c, q in sorted(bk.pos.items(), key=lambda x: (x[1]["ei"], x[0])):
        p = px[c]
        ei = q["ei"]
        cl = p["c"][i1] if _ok(p["c"][i1]) else p["cff"][i1]
        o = p["o"][ei]
        due, sell = exit_day(cal[ei], cal)
        sd = cal[q["si"]]
        rank = next((k + 1 for k, (cc, _) in enumerate((W.get(sd) or {}).get(S.LIST_BOOK) or []) if cc == c), None)
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
    cash = bk.cash + sum(q["k"] * (px[c]["c"][i1] if _ok(px[c]["c"][i1]) else px[c]["cff"][i1]) * (1 - T["sell_tax"])
                         for c, q in bk.pos.items() if q["pend"])
    nbuy = 0
    if wks and wks[-1] == last and (not n8 or last >= S.START4):   # 最後一天就是訊號日：明天開盤照名單買（Book 在最後一天不下單，這裡照它的規則列）
        if n8:
            hist = load_hist() if hist is None else hist
            rsd = {c: rs for c, rs in rec["weeks"][last][S.LIST_BOOK]}
            lists = prior_lists(last, rec.get("weeks") or {}, hist)
            cand = [(c, sc, run_len(c, lists)) for c, sc in n8_orders(last, rec.get("weeks") or {}, hist) if c not in bk.pos and c in px]
            cand = sorted(cand, key=lambda x: -x[1])
        else:
            cand = sorted(((c, rs, None) for c, rs in rec["weeks"][last][S.LIST_BOOK] if c not in bk.pos and c in px),
                          key=lambda x: -x[1])
        held = len(bk.pos) - len(out["sell"])
        for c, sc, wk in cand:
            if n8:
                free = T["slots"] - held - nbuy
                per = cash / free if free > 0 else 0.0
                fill = free > 0 and per >= T["min_slot"] * eq / T["slots"]
                amt = min(per, T["max_weight"] * eq)
            else:
                tgt = min(T["weight"], T["max_weight"]) * eq
                fill = cash >= 0.25 * tgt and held + nbuy < T["max_positions"]
                amt = min(tgt, cash)
            rs = rsd[c] if n8 else sc
            b = {"c": c, "n": nm.get(c, c), "rs": round(float(rs), 1), "fill": bool(fill), "why": why_of(last, c)}
            if wk is not None:
                b["wk"] = wk
            if fill:
                b["amt"] = float(amt / eq) if eq else None   # 估計買多少（占那本帳）
            out["buy"].append(b)
            if fill:
                nbuy += 1
                cash -= amt
    out["n_buy"] = nbuy
    return out


PICK_TOP = S.TRADE_N8["slots"]        # 選股頁「現在開始的話」列幾檔＝N8 的格數（docs/lab_boom_v2_plan.md 第 8、9 節）


def _fail_text(cond, v) -> str:
    from . import superx as SX
    k, op, _ = cond
    if op == "=":
        return f"不符合「{SX.SHORT.get(k, SX.FNAME.get(k, k))}」"
    return SX.cond_value_text(tuple(cond), v)


def pick_state(ctx: dict, last: str, W: dict, cur: list, cur_d: str, trial: bool, rules: list | None,
               why: dict | None = None, watch: dict | None = None, names: dict | None = None, hist: dict | None = None) -> dict:
    """選股頁新飆股卡片（docs/lab_boom_v2_plan.md 第 8、9 節；使用者：「我現在是空手，所以應該要以即刻推薦列出最強的前十名」）：
    cur＝最新的名單（全部，[[代號, 強度]]，強度高到低）：週五收盤後是那一週的正式名單、週中是到 last 收盤為止的試算；
    rows＝全部，照 N8 的順序（新上名單的先、同週數依強度；sxlivespec VER 4）；top＝從現金開始會買的檔數（前 top 列）。
    每一檔：符合哪一條、參考買點（sepa.plan_today，同原本的飆股名單）、上名單第幾週（連續幾個週末在名單上，試算的這一週也算一週）、收盤。
    watch＝原本的飆股名單（{代號: 標籤}）：不在 cur 上的寫差在哪幾個條件（那一年規則裡差最少的一條）。
    px＝全部股票 last 的收盤（頁面「我的」用；只存在使用者的瀏覽器）。只描述、不影響任何紀錄。"""
    from . import sepa as SP
    P = ctx["P"]
    cal = P.cal
    i = cal.index(last)
    nm = names or {}
    F = feats_at(ctx, i)
    lists = prior_lists(cur_d, W, load_hist() if hist is None else hist, incl=not trial)

    def weeks_on(c: str) -> int:
        return run_len(c, lists) + (1 if trial else 0)

    def raw(c):
        x = P.s[c]["c"][i] if c in P.s else None
        return float(x) if _ok(x) else None

    def plan(c: str) -> dict:
        try:
            px = ctx["pxs"][c]
            pl = SP.plan_today(px.h, px.l, px.c, px.v, P.s[c]["c"], i)
        except Exception:                                  # noqa: BLE001 —— 算不出來＝不寫買點
            return {}
        r = {"st": pl.get("st"), "piv": pl.get("piv"), "stop": pl.get("stop"), "hi": pl.get("hi52"), "m50": pl.get("ma50")}
        return {k: (round(float(v), 2) if isinstance(v, float) else v) for k, v in r.items() if v is not None}

    def row(c: str, rs) -> dict:
        w = (why or {}).get(c)
        return {"c": c, "n": nm.get(c, c), "rs": round(float(rs), 1), "why": _why_lines(rules, w), "wk": weeks_on(c),
                "pl": plan(c), "px": raw(c)}
    full = {c for c, _ in cur}
    order = sorted(cur, key=lambda x: -(float(x[1]) - 1000.0 * (max(1, weeks_on(x[0])) - 1)))   # N8 的順序（Book 同一套，穩定排序）
    rows = [row(c, rs) for c, rs in order]
    old = []
    for c, tags in sorted((watch or {}).items(), key=lambda x: -((F.get(x[0]) or {}).get("rs") or 0)):
        f = F.get(c) or {}
        o = {"c": c, "n": nm.get(c, c), "tags": list(tags or []), "rs": f.get("rs"), "px": raw(c), "on": c in full, "pl": plan(c)}
        if c not in full:
            if not f.get("el"):
                o["miss"] = ["不在新飆股挑的範圍（月底市值不到 40 億，或 20 日均成交值不到 1,000 萬）"]
            elif rules:
                fails = min(([cond for cond in r if not _cond_pred(cond)(f)] for r in rules), key=len)
                o["miss"] = [_fail_text(cond, f.get(cond[0])) for cond in fails]
        old.append(o)
    pxs = {c: round(float(P.s[c]["c"][i]), 2) for c in P.codes if _ok(P.s[c]["c"][i])}
    return {"d": cur_d, "last": last, "trial": bool(trial), "n": len(cur), "top": PICK_TOP, "rows": rows, "old": old, "px": pxs}


def _cond_pred(cond):
    from . import superx as SX
    return SX.rule_pred([tuple(cond)])


def trial_list(ctx: dict, d: str, R: dict | None = None, why: dict | None = None) -> list:
    """週中：到 d 收盤為止符合 LIST_BOOK（R60）那一年規則的股票（day_signals 同一套；只是試算、不記錄）。
    why（dict）＝另外填 {代號: {"k", "v"}}（符合哪幾條）。"""
    rules = rules_for(int(d[:4]), S.LIST_BOOK, R)
    if not rules or d not in ctx["P"].cal:
        return []
    wy: dict = {}
    out = day_signals(ctx["P"].cal.index(d), ctx, {S.LIST_BOOK: rules}, why=wy).get(S.LIST_BOOK) or []
    if why is not None:
        why.update(wy.get(S.LIST_BOOK) or {})
    return out


YTD_COL = {"R60": 0, "N8B": 6}        # nav 的哪一欄（ytd_part 用）


def ytd_part(rec: dict, ctx: dict, last: str | None, book: str | None = None) -> dict | None:
    """今年逐月、逐筆表（ytdspec）要的：那本帳接手以後每天的總資產與每一筆（元，那本帳自己的規模）。
    book＝R60（ytdspec VER 1）或 N8B（VER 2，預設）。
    → {"take", "e0"（接手那天收盤）, "eq": {日期: 總資產}, "closed": [[代號, 買進日, 賣出日, 報酬, 原因, 賺賠, 股數, 接手以來賺賠|None]],
       "open": [[代號, 買進日, 買進成本, 接手那天的市值|None, 最新市值, 股數, 買進價, 收盤]]}；沒有接手的狀態或還沒算＝None。
    買進價：接手時就拿著的用接手檔記的（回測引擎的買進價），之後買的用頁面那天的原始開盤。"""
    book = book or S.BT_BOOK
    bk, e0 = (rec.get("_bt"), rec.get("_btbase")) if book == S.BT_BOOK else (rec.get("_book"), rec.get("_base"))
    px = rec.get("_px")
    if bk is None or not e0 or not px or not last:
        return None
    cal = ctx["P"].cal
    i1 = cal.index(last)
    col = YTD_COL[book]
    eq = {d: round(v[col] / 100 * e0, 2) for d, v in (rec.get("nav") or {}).items() if v and len(v) > col and v[col] is not None}
    closed = []
    for t in bk.trades:
        c, si, ei, xi, r, why, sh, pnl, *tk = t
        closed.append([c, cal[ei], cal[xi], round(float(r), 6), why, round(float(pnl), 2), float(sh),
                       round(float(tk[1]), 2) if tk else None])
    opens = []
    for c, q in sorted(bk.pos.items(), key=lambda x: (x[1]["ei"], x[0])):
        p = px[c]
        v = q["k"] * (p["c"][i1] if _ok(p["c"][i1]) else p["cff"][i1])
        cl = p["c"][i1] if _ok(p["c"][i1]) else p["cff"][i1]
        opens.append([c, cal[q["ei"]], round(float(q["cin"]), 2), round(float(q["v0"]), 2) if q.get("v0") else None,
                      round(float(v), 2), float(q["sh"]), (q["epx"] if q.get("v0") and q.get("epx") else _raw(p, "o", q["ei"])),
                      (cl / p["f"][i1]) if _ok(cl) and _ok(p["f"][i1]) and p["f"][i1] else None])
    return {"book": book, "take": S.TAKE, "e0": round(float(e0), 2), "eq": eq, "closed": closed, "open": opens}


# ── 紀錄 ─────────────────────────────────────────────────────────────

KEEP_FROM = 3                         # 這一版起的每週紀錄沿用（VER 4 沒有改名單的記法，只多一本 N8）


def read() -> dict:
    doc = store.read_json(S.LOG_FILE, {}) or {}
    if not isinstance(doc, dict) or (doc.get("ver") or 0) < KEEP_FROM:
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


def update(DL, ctx: dict | None = None, now=None, write_file: bool | None = None, watch: dict | None = None) -> dict:
    """補記新的訊號週、重算成績；只有 CI 寫回。→ 紀錄（含 nav、trades、open、stats）。
    watch＝原本的飆股名單（{代號: 標籤}；company.market_table 的 watch），選股頁寫差在哪幾個條件。"""
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
                add_week(rec["weeks"], d, sg, t, r1v, why={b: v for b, v in wy.items() if b == S.LIST_BOOK})
        rec["last"] = last
        i0 = start_index(cal)
        if i0 is not None and i0 <= ix[last]:
            rec.update(perf(ctx, rec["weeks"], last, seed=seed, hist=load_hist(), seed_bt=load_seed_bt()))
    if write_file:
        write(rec)
    st = rec.get("stats") or {}
    plan = n8 = ytdp = None
    try:                                                   # 交易計畫（R60，VER 2～3）與選股頁（N8，VER 4）要的新飆股狀態；算不出來只少那一塊
        from . import company
        nm = company.names()
        hist = load_hist()
        tr, tfull, tw = [], [], {}
        rl = rules_for(int(last[:4]), S.LIST_BOOK, R) if last else None
        if last and last not in week_ends(last, last):      # 這一週還沒結束：試算到今天收盤為止符合的股票
            tfull = trial_list(ctx, last, R, why=tw)
            tr = [{"c": c, "n": nm.get(c, c), "rs": round(float(rs), 1), "why": _why_lines(rl, tw.get(c))}
                  for c, rs in tfull[:S.LIST_SHOW]]
        r2 = dict(rec, last=last)
        plan = plan_state(r2, ctx, nm, tr, R, seed, book=S.TAKE_BOOK, hist=hist)   # START 之前（資料停在 START 前一天）也要算下一次看名單的日子
        n8 = plan_state(r2, ctx, nm, tr, R, seed, book=S.PLAN_BOOK, hist=hist)
        try:                                               # 選股頁的新飆股卡片：最新的名單（週中＝試算）照 N8 會買的、新上名單、原本的飆股名單差在哪
            W = {**seed_weeks(seed), **(rec.get("weeks") or {})}
            if tfull:
                cur, cur_d, cw = tfull, last, tw
            else:
                wd = max((d for d, w in W.items() if S.LIST_BOOK in w and d <= last), default=None)
                cur, cur_d = ((W[wd][S.LIST_BOOK], wd) if wd else ([], None))
                cw = ((W.get(wd) or {}).get("why") or {}).get(S.LIST_BOOK) or {} if wd else {}
            if cur_d:
                n8["pick"] = pick_state(ctx, last, W, cur, cur_d, bool(tfull), rules_for(int(cur_d[:4]), S.LIST_BOOK, R),
                                        cw, watch, nm, hist)
        except Exception as e:                             # noqa: BLE001
            print(f"[sxlive] ⚠ 選股頁的新飆股名單算不出來：{type(e).__name__}: {e}")
        yp = ytd_part(rec, ctx, last)                      # 今年逐月、逐筆表（ytdspec VER 2）：接手以後 N8B 那本帳的錢
        if yp:
            ytdp = {"ytd": yp}
    except Exception as e:                                 # noqa: BLE001
        print(f"[sxlive] ⚠ 新飆股的狀態算不出來：{type(e).__name__}: {e}")
    for k in ("_book", "_px", "_base", "_i0", "_pbook", "_pbase", "_bt", "_btbase"):
        rec.pop(k, None)
    LAST.clear()
    LAST.update({"d": last, "start": S.START, "weeks": len(rec["weeks"]), "due": due(last), "miss": missing_year(last, R),
                 "v": {b: (st.get(b) or {}).get("ret") for b in (*S.BOOKS, "TR", "EW")}, "plan": plan, "n8": n8, "ytd": ytdp})
    return rec
