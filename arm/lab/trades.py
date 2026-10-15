"""籌碼雷達：每條策略的逐筆歷史交易（docs/lab_trades_plan.md；2026-10-15 使用者：「我希望每個策略都會有像是 0050 策略的
逐筆歷史交易，我才能去驗證」）。

兩張表，全部由回測當下的買賣紀錄產生（bt3.account(log=...)，加紀錄前後每期數字完全相同）：
  · 每期表（定期換股的策略）：決定日、買進日、本期名單（新買／續抱）、開盤賣出、本期報酬（資金帳戶）、同期大盤。
    表上每期報酬的平均、中位、正的比例＝策略頁「每月（季）平均」等數字的來源。
  · 逐筆表：每一檔從買進到賣出（續抱的股票不重複買賣，一筆可能跨好幾期）——買賣日期、當時的實際價格、
    期間除權息、報酬（含息、扣來回成本）、同期大盤（加權報酬指數）、入選依據。
價格口徑：回測用含息還原價（股利再投入）；表上顯示當時的實際價格（Raw），股利另列，所以
  報酬 ≈（賣出價 ＋ 期間除權息）÷ 買進價 − 1 − 來回成本（精確值以還原價計，會差一點點）。
"""
from __future__ import annotations

import bisect
import statistics
from datetime import date

from . import bt3, store

BASE = date(2013, 1, 1)          # 頁面日期編碼：2013-01-01 起第幾天（緊湊陣列）
K_TOL = 0.004                    # 換算倍數「相同」的容許誤差（官方收盤兩位小數、Yahoo 四捨五入）


def dnum(d: str | None) -> int | None:
    return None if not d else (date.fromisoformat(d[:10]) - BASE).days


# ── 當時的實際價格 ────────────────────────────────────────────────────

def tick(p: float) -> float:
    """台股升降單位（股票；2013 起）。"""
    return 0.01 if p < 10 else 0.05 if p < 50 else 0.1 if p < 100 else 0.5 if p < 500 else 1.0 if p < 1000 else 5.0


def on_tick(p: float | None) -> bool:
    if not p:
        return False
    r = p / tick(p)
    return abs(r - round(r)) < 0.12


def exact_tick(p: float | None) -> bool:
    """存下來的價格本身就是當時成交價（剛好落在升降單位上，沒有零頭）。Yahoo 換算過的舊價格多半有零頭（例 300.9524）。"""
    if not p:
        return False
    r = p / tick(p)
    return abs(r - round(r)) < 1e-6


def snap(p: float) -> float:
    """落在升降單位附近的價格對齊到升降單位（Yahoo 調整後的價格乘回來會有極小零頭）。"""
    t = tick(p)
    return round(round(p / t) * t, 2)


class Raw:
    """回測長歷史的「當時價格」。

    · FinMind 來源（已下市）＝原始價，直接用。
    · Yahoo 來源：開高低收已依配股、減資、分割調整過（不是當時價），而且是分批抓的（每批的調整基準可能不同）
      → 乘上換算倍數 K。K＝官方收盤 ÷ Yahoo 同日收盤；量測點＝每月底（證交所、櫃買月底快照）與除權息前一天
      （除權息表的前收）。當時價一定落在升降單位上（K 用錯的日子價格會有零頭），用它在候選 K 之間挑：
      前後量測點差不到 0.4%（同一段）→ 依序試「之後最近的、之前最近的、1」，取當天開盤與收盤都落在升降單位上的；
      差得多（中間股數變了）→ 用升降單位找切換日，分不出來時中間只有一個除權息日就從那天切開；
      都不行才取較近的量測點並標「約」。和前後都不一樣、前後彼此一樣的單一月底點視為雜訊（官方快照日與 Yahoo 對不上）剔除。
    """

    def __init__(self):
        self.me: dict[str, list[tuple[str, float]]] = {}
        for kind in ("v3me_tw", "v3me_tp"):
            for _, doc in store.load(kind):
                d = doc.get("d")
                for c, v in (doc.get("s") or {}).items():
                    if d and v and v[0]:
                        self.me.setdefault(c, []).append((d, float(v[0])))
        self.ev: dict[str, list[tuple]] = {}             # 代號 → [(除權息日, 前收, 參考價, 類別, 值, 現金, 每仟股配股)]
        for _, doc in store.load("divtw"):
            for r in doc.get("rows") or []:
                d, c, val, typ, before, ref = r[0], r[1], r[2], r[3], r[4], r[5]
                if before and ref and 0 < ref < before:
                    self.ev.setdefault(c, []).append((d, before, ref, typ, val if val else before - ref,
                                                      val if typ == "息" else None, None))
        for _, doc in store.load("v3div"):
            for r in doc.get("rows") or []:
                d, c, before, ref, cash, stk = r[0], r[1], r[2], r[3], r[4], r[5]
                if before and ref and 0 < ref < before:
                    typ = "權息" if cash and stk else "權" if stk else "息"
                    self.ev.setdefault(c, []).append((d, before, ref, typ, before - ref, cash or None, stk or None))
        for c in self.ev:
            self.ev[c].sort()
        self._doc: dict[str, dict | None] = {}
        self._k: dict[str, tuple] = {}
        self._sw: dict[tuple, str | None] = {}

    def doc(self, c: str) -> dict | None:
        if c not in self._doc:
            d = store.read("v3px", c)
            if d and d.get("t"):
                d["_ix"] = {x: i for i, x in enumerate(d["t"])}
            self._doc[c] = d if d and d.get("t") else None
        return self._doc[c]

    def _meas(self, c: str) -> tuple[list[str], list[float], list[str]]:
        """→ (量測日, K, 除權息日)。"""
        if c in self._k:
            return self._k[c]
        doc = self.doc(c)
        t, cl, ix = doc["t"], doc["c"], doc["_ix"]
        m: dict[str, list] = {}
        for d, px in self.me.get(c) or []:
            i = ix.get(d)
            if i is not None and cl[i]:
                m.setdefault(d, [[], False])[0].append(px / cl[i])
        exs = []
        for ev in self.ev.get(c) or []:
            ex, before = ev[0], ev[1]
            i = bisect.bisect_left(t, ex) - 1          # 除權息日前一個（Yahoo 有資料的）交易日
            if i >= 0 and cl[i] and t[i] < ex:
                v = m.setdefault(t[i], [[], False])
                v[0].append(before / cl[i])
                v[1] = True                            # 除權息前收：官方數字，不當雜訊剔除
            exs.append(ex)
        pts = sorted((d, statistics.median(v[0]), v[1]) for d, v in m.items())
        keep = []
        for n, (d, k, ev) in enumerate(pts):
            if not ev and 0 < n < len(pts) - 1:
                a, b = pts[n - 1][1], pts[n + 1][1]
                if abs(a / b - 1) <= K_TOL and abs(k / b - 1) > K_TOL:
                    continue
            keep.append((d, k))
        out = ([d for d, _ in keep], [k for _, k in keep], sorted(set(exs)))
        self._k[c] = out
        return out

    def factor(self, c: str, d: str) -> tuple[float, bool]:
        """(K, 是否為約略值)。"""
        ds, ks, exs = self._meas(c)
        n = bisect.bisect_left(ds, d)                    # 第一個 ≥ d 的量測點
        if n < len(ds) and ds[n] == d:
            return ks[n], False
        k1 = ks[n] if n < len(ds) else 1.0               # 最後一個量測點之後：之後沒有再調整過＝1
        k0 = ks[n - 1] if n > 0 else None
        if k0 is None or abs(k0 / k1 - 1) <= K_TOL:
            doc = self.doc(c)
            i = doc["_ix"].get(d)
            o, cl = (doc["o"][i], doc["c"][i]) if i is not None else (None, None)
            for k in [x for x in (k1, k0, 1.0) if x is not None]:
                if cl and on_tick(cl * k) and (not o or on_tick(o * k)):
                    return k, False
            return k1, n >= len(ds) and bool(ds) and abs(ks[-1] - 1) > K_TOL
        d0 = ds[n - 1]
        d1 = ds[n] if n < len(ds) else self.doc(c)["t"][-1]
        sw = self._switch(c, d0, d1, k0, k1)
        if sw:
            return (k0 if d < sw else k1), False
        ex = [e for e in exs if d0 < e <= d1]
        if len(ex) == 1:
            return (k0 if d < ex[0] else k1), False
        near = k1 if (date.fromisoformat(d1) - date.fromisoformat(d)) <= (date.fromisoformat(d) - date.fromisoformat(d0)) else k0
        return near, True

    def _switch(self, c: str, d0: str, d1: str, k0: float, k1: float) -> str | None:
        """d0（K＝k0）與 d1（K＝k1）之間 K 在哪一天換：當時價一定落在升降單位上，試每個切換日，
        取「切換日之前 ×k0、之後 ×k1 都在升降單位上」的天數最多者；九成以上的日子對得上、且兩個 K 分得出來才採用。"""
        key = (c, d0, d1)
        if key in self._sw:
            return self._sw[key]
        doc = self.doc(c)
        t, cl = doc["t"], doc["c"]
        a, z = bisect.bisect_right(t, d0), bisect.bisect_right(t, d1)
        days = [i for i in range(a, z) if cl[i]]
        out = None
        if days:
            g0 = [on_tick(cl[i] * k0) for i in days]
            g1 = [on_tick(cl[i] * k1) for i in days]
            best, hit = 0, -1
            for n in range(len(days) + 1):               # 切在 days[n]（之前的用 k0）
                h = sum(g0[:n]) + sum(g1[n:])
                if h > hit:
                    best, hit = n, h
            sep = sum(1 for x, y in zip(g0, g1) if x != y)
            if hit >= 0.9 * len(days) and sep >= max(2, len(days) // 3) and 0 < best <= len(days):
                out = t[days[best]] if best < len(days) else None
        self._sw[key] = out
        return out

    def px(self, c: str, d: str, opn: bool) -> tuple[float | None, bool]:
        """(當時的開盤或收盤價, 是否為約略值)；沒有資料回 (None, False)。"""
        doc = self.doc(c)
        if not doc:
            return None, False
        i = doc["_ix"].get(d)
        if i is None:
            return None, False
        v = doc["o" if opn else "c"][i]
        if not v:
            return None, False
        if doc.get("src") != "yahoo":
            return round(v, 2), False
        k, ap = self.factor(c, d)
        if on_tick(v * k):
            return snap(v * k), ap
        ds, ks, _ = self._meas(c)                         # 有零頭＝K 不對（Yahoo 單日資料有誤或切換日判斷錯）→ 試附近的 K
        n = bisect.bisect_left(ds, d)
        for k2 in [*ks[max(0, n - 2):n + 2], 1.0]:
            if on_tick(v * k2):
                return snap(v * k2), False
        return round(v * k, 2), True

    def divs(self, c: str, d0: str, d1: str) -> list[list]:
        """持有期間的除權息：除權息日在「買進日之後、賣出日當天或之前」（持有到除權息日開盤＝有領）。
        → [[除權息日, 類別, 每股值（除權息前收 − 參考價）, 除權息前收, 參考價]]"""
        return [[e[0], e[3], round(e[4], 2), e[1], e[2]] for e in self.ev.get(c) or [] if d0 < e[0] <= d1]


# ── 帳戶紀錄 → 買到賣 ────────────────────────────────────────────────

def trips(log: list) -> tuple[list[dict], list[dict]]:
    """bt3.account 的 log → (每一筆買到賣, 沒買到的)。
    買到賣：{c, k0 買進那一期, j 買進日, o 買進價, k1 賣出那一期, i 賣出日, p 賣出價, op 開盤賣?, how 賣出原因}；
    帳戶結束時還沒賣的 k1／i／p＝None（持有中）。沒買到：{c, k, j, why}。"""
    pos: dict[str, dict] = {}
    out, skip = [], []
    for e in log:
        if e[0] == "b":
            pos[e[2]] = {"c": e[2], "k0": e[1], "j": e[3], "o": e[4]}
        elif e[0] == "s":
            b = pos.pop(e[2], None)
            if b:
                out.append({**b, "k1": e[1], "i": e[3], "p": e[4], "op": e[5], "how": e[6]})
        elif e[0] == "x":
            skip.append({"c": e[2], "k": e[1], "j": e[3], "why": e[4]})
    for b in pos.values():
        out.append({**b, "k1": None, "i": None, "p": None, "op": None, "how": "open"})
    out.sort(key=lambda x: (x["j"], x["c"]))
    return out, skip


def trip_ret(o: float, p: float, b: str) -> float:
    """單筆報酬（%）：同 bt3.account 的成本算法——買進花「金額 ×（1＋買進成本）」、賣出拿「股數 × 價 ×（1－賣出成本）」。"""
    return ((p / o) * (1 - bt3.side_cost(b, True)) / (1 + bt3.side_cost(b, False)) - 1) * 100


def trv(tr: list, i: int | None) -> float | None:
    """加權報酬指數：第 i 個交易日或之前最近一個有值的日子（同 bt3l._trv）。"""
    if i is None:
        return None
    for k in range(i, max(i - 10, -1), -1):
        if 0 <= k < len(tr) and tr[k]:
            return tr[k]
    return None


def mk_ret(tr: list, j: int, i: int, op: bool) -> float | None:
    """同期大盤（%）：買進前一天收盤 → 賣出日收盤（開盤賣出則到前一天收盤）。指數沒有開盤價。"""
    a, b = trv(tr, j - 1), trv(tr, i - 1 if op else i)
    return round((b / a - 1) * 100, 2) if a and b else None


def build(cal: list[str], periods: list, units: list[dict], log: list, b: str, tr: list, *,
          raw: Raw | None = None, px=None, scores: dict | None = None, info=None, fw_from: str | None = None,
          roll: bool = False) -> dict:
    """一條定期換股策略的逐筆交易。

    cal＝交易日曆；periods＝account 用的 [(t, x, picks)]；units＝account 的 units（同 periods 的 t）；log＝account 的紀錄；
    tr＝加權報酬指數（與 cal 對齊）；raw＝長歷史實際價（Raw）；px(c, i, opn)＝沒有 raw 時的價格（每日資料本來就是當時價）；
    scores＝{t: {代號: 分數}}（名次、宇宙檔數）；info(c, t)＝入選依據的附加數字（月營收年增、EPS）；
    fw_from＝起算日（之後決定的期別標前瞻）；roll＝期期相連的策略（月營收）：資料最後一期的「期末收盤全部賣」是回測
    結束的結算、不是規則上的賣出（實際上會續抱或換股）→ 每期表 end＝2、逐筆的賣出原因 bt。
    逐筆另給「還原倍數」mul＝（還原價賣出 ÷ 還原價買進）÷（實際賣出價 ÷ 實際買進價）：報酬＝賣出價 ÷ 買進價 × mul × 成本 − 1，
    可以逐筆驗算。mul 和期間除權息（前收 ÷ 參考價連乘）對不上的標 kc：1＝差 15% 以上（減資、分割等股數變動，
    例 3532 2018 減資一半、2408 2014 減資九成）；2＝差 1～15%（Yahoo 分批抓取的調整基準不同，回測價格在這段期間
    和官方除權息有出入；2013～2026 四條策略共約 5 筆）。
    → {"per": [每期], "tr": [每筆], "chk": 核對統計, "n_ap": 約略價格筆數}"""
    by_t = {u["t"]: u for u in units}
    tp, skips = trips(log)
    picks_k = {k: set(p[2]) for k, p in enumerate(periods)}
    ev_k: dict[int, dict[str, list]] = {}
    for e in log:
        if e[0] == "b":
            ev_k.setdefault(e[1], {}).setdefault("new", []).append(e[2])
        elif e[0] == "s" and e[5]:
            ev_k.setdefault(e[1], {}).setdefault("drop", []).append(e[2])
        elif e[0] == "x":
            ev_k.setdefault(e[1], {}).setdefault("skip", []).append(e[2])
    order: dict[int, dict[str, int]] = {}

    def rank(t, c):
        sc = (scores or {}).get(t) or {}
        if c not in sc:
            return None, len(sc) or None, None
        if t not in order:
            order[t] = {z: n + 1 for n, z in enumerate(sorted(sc, key=lambda z: (-sc[z], z)))}
        return order[t][c], len(sc), sc[c]

    per = []
    for k, (t, x, picks) in enumerate(periods):
        u = by_t.get(t)
        if not u or u.get("r") is None:
            continue
        e = ev_k.get(k) or {}
        nxt = periods[k + 1][0] if k + 1 < len(periods) else None
        a, z = trv(tr, t), trv(tr, x)
        scs = [rank(t, c)[2] for c in picks]
        per.append({"d": cal[t], "bd": cal[t + 1] if t + 1 < len(cal) else None, "ed": cal[x], "r": round(u["r"], 3),
                    "mk": round((z / a - 1) * 100, 2) if a and z else None,
                    "pk": list(picks), "new": e.get("new") or [], "drop": e.get("drop") or [], "skip": e.get("skip") or [],
                    "sc": [None if v is None else round(v, 1) for v in scs],
                    "end": 2 if roll and nxt is None else nxt != x, "nu": len((scores or {}).get(t) or {}) or None,
                    "fw": bool(fw_from and cal[t] >= fw_from)})
    last_k = len(periods) - 1

    def price(c, i, opn):
        if i is None:
            return None, False
        if raw is not None:
            return raw.px(c, cal[i], opn)
        v = px(c, i, opn) if px else None
        return (round(v, 2) if v else None), False

    rows, n_ap = [], 0
    for q in tp:
        if q["i"] is None:
            continue                                      # 帳戶結束時還沒賣（研究與前瞻都只跑已到期的期別，不會發生）
        t = periods[q["k0"]][0]
        bp, ap1 = price(q["c"], q["j"], True)
        sp, ap2 = price(q["c"], q["i"], q["op"])
        n_ap += bool(ap1 or ap2)
        last_pick = max((k for k in range(q["k0"], q["k1"] + 1) if q["c"] in picks_k.get(k, ())), default=q["k0"])
        rk, nu, sc = rank(t, q["c"])
        dv = raw.divs(q["c"], cal[q["j"]], cal[q["i"]]) if raw is not None else []
        mul, kc = None, 0
        if bp and sp and q["o"] and q["p"]:
            mul = (q["p"] / q["o"]) / (sp / bp)
            dm = 1.0
            for x in dv:
                dm *= x[3] / x[4]
            g = abs(mul / dm - 1)
            kc = 1 if g >= 0.15 else 2 if g > 0.01 else 0
        rows.append({"c": q["c"], "d": cal[t], "bd": cal[q["j"]], "bp": bp, "sd": cal[q["i"]], "sp": sp, "so": q["op"],
                     "np": sum(1 for k in range(q["k0"], last_pick + 1) if q["c"] in picks_k.get(k, ())),
                     "hd": q["i"] - q["j"] + (0 if q["op"] else 1), "dv": [x[:3] for x in dv],
                     "mul": None if mul is None else round(mul, 4), "kc": kc,
                     "r": round(trip_ret(q["o"], q["p"], b), 2), "mk": mk_ret(tr, q["j"], q["i"], q["op"]),
                     "how": "bt" if roll and q["k1"] == last_k and q["how"] in ("end", "endlock") else q["how"],
                     "ap": bool(ap1 or ap2), "rk": rk, "nu": nu, "sc": None if sc is None else round(sc, 2),
                     "info": info(q["c"], t) if info else None, "fw": bool(fw_from and cal[t] >= fw_from), "st": "closed"})
    for sk in skips:
        t = periods[sk["k"]][0]
        rk, nu, sc = rank(t, sk["c"])
        bp, _ = price(sk["c"], sk["j"], True)
        rows.append({"c": sk["c"], "d": cal[t], "bd": cal[sk["j"]], "bp": bp, "st": "skip", "why": sk["why"], "rk": rk, "nu": nu,
                     "sc": None if sc is None else round(sc, 2), "info": info(sk["c"], t) if info else None,
                     "fw": bool(fw_from and cal[t] >= fw_from)})
    rows.sort(key=lambda r: (r["bd"], r["c"]))
    return {"per": per, "tr": rows, "chk": check(per, rows), "n_ap": n_ap}


def check(per: list[dict], rows: list[dict]) -> dict:
    """核對統計（頁面一句話＋測試）：每期報酬的平均、中位、正的比例；逐筆平均、正的比例。"""
    rs = [p["r"] for p in per if p.get("r") is not None]
    ts = [r["r"] for r in rows if r.get("st") == "closed" and r.get("r") is not None]
    out = {"np": len(rs), "nt": len(ts)}
    if rs:
        out.update({"avg": round(statistics.mean(rs), 2), "med": round(statistics.median(rs), 2),
                    "win": round(100 * sum(1 for x in rs if x > 0) / len(rs))})
    if ts:
        out.update({"tavg": round(statistics.mean(ts), 2), "twin": round(100 * sum(1 for x in ts if x > 0) / len(ts))})
    return out


# ── 頁面緊湊陣列 ──────────────────────────────────────────────────────

PER_COLS = ["d", "bd", "ed", "r", "mk", "pk", "new", "drop", "skip", "sc", "end", "nu"]
# 常用的在前、少用的在後，尾端空值省略（頁面讀不到＝null）。st：c 已出場／o 持有中／s 沒進場。
# how（賣出原因）：月營收、財報驚喜用代碼 d＝不在新名單開盤賣、l＝鎖跌停順延、e＝期末收盤賣、el＝期末遇鎖跌停順延、
# bt＝回測資料最後一期的結算（期期相連的策略才有）；其他策略是文字。
# 前瞻（起算日之後決定）由頁面用決定日 ≥ since 判斷，不另存。
TR_COLS = ["c", "d", "bd", "bp", "sd", "sp", "r", "mk", "st", "hd", "how", "so", "np", "rk", "sc", "info", "dv", "mul", "kc", "ap",
           "why", "g"]
_HOW = {"drop": "d", "lock": "l", "end": "e", "endlock": "el"}
_ST = {"closed": "c", "open": "o", "skip": "s"}


def _trim(row: list) -> list:
    while row and row[-1] in (None, [], 0, False) and not (row[-1] == 0 and len(row) <= 8):
        row.pop()
    return row


def pack(doc: dict) -> dict:
    """→ {"per": [[...PER_COLS]], "tr": [[...TR_COLS]]}，日期改成 2013-01-01 起第幾天（頁面 tnD() 還原）。"""
    def per_row(p):
        return [dnum(p["d"]), dnum(p["bd"]), dnum(p["ed"]), p["r"], p["mk"], p["pk"], p["new"], p["drop"], p["skip"],
                p["sc"], int(p["end"] or 0), p["nu"]]

    def tr_row(r):
        dv = [[dnum(x[0]), x[1], x[2]] for x in r.get("dv") or []]
        mul = r.get("mul")
        return _trim([r["c"], dnum(r["d"]), dnum(r.get("bd")), r.get("bp"), dnum(r.get("sd")), r.get("sp"), r.get("r"),
                      r.get("mk"), _ST.get(r.get("st"), r.get("st")), r.get("hd"), _HOW.get(r.get("how"), r.get("how")),
                      1 if r.get("so") else 0, r.get("np"), r.get("rk"), r.get("sc"), r.get("info"), dv,
                      None if mul is None or abs(mul - 1) < 0.0005 else mul, r.get("kc") or 0, 1 if r.get("ap") else 0,
                      r.get("why"), r.get("g")])
    out = {"per": [per_row(p) for p in doc.get("per") or []], "tr": [tr_row(r) for r in doc.get("tr") or []],
           "chk": doc.get("chk"), "n_ap": doc.get("n_ap")}
    if doc.get("cur"):                                 # 目前這一期（還沒到出場日）：決定日與可選股票數，給「持有中」列的名次
        out["cur"] = [dnum(doc["cur"]["d"]), doc["cur"].get("nu")]
    return out


# ── 入選依據（頁面「依據」欄） ──────────────────────────────────────────

def info_p7(cal: list[str]):
    """月營收驚喜：(代號, 決定日索引) → [年增率 %]（官方彙總表；營收月份＝決定日的上一個月；分數＝標準差倍數另存 sc）。"""
    from . import packtest as PT
    ym_of = dict(PT.rev_forms(cal))
    docs: dict[str, dict] = {}

    def f(c, t):
        ym = ym_of.get(t)
        if not ym:
            return None
        if ym not in docs:
            docs[ym] = (store.read("rev", ym) or {}).get("s") or {}
        v = docs[ym].get(c)
        return None if not v or v[1] is None else [round(v[1], 1)]
    return f


def info_p3(cal: list[str], eps: dict):
    """財報驚喜：(代號, 決定日索引) → [季底, 當季 EPS, 去年同季 EPS]。"""
    from . import packtest as PT
    q_of = {}
    for q in sorted({q for e in eps.values() for q in e}):
        t = PT.form_after_deadline(cal, PT.deadline(q))
        if t is not None:
            q_of.setdefault(t, q)

    def f(c, t):
        q = q_of.get(t)
        e = eps.get(c) or {}
        if not q or q not in e:
            return None
        py = PT._prev_year(q)
        return [q, round(e[q], 2), None if py not in e else round(e[py], 2)]
    return f


# ── 既有策略（共識加碼、臺灣50、長線、高股息）的逐筆交易 → 同一種緊湊陣列 ─────────────────

def pack_simple(trs: list[dict], since: str | None, *, grp: str | None = None, info=None) -> dict:
    """既有策略的交易紀錄（strategy／tw50study／growth 的 dict：c, d, bd, sd, entry, exit|now, held|hd, r, x, why, st…）
    → pack() 同格式。同期大盤＝r − x（原本就對加權指數算的超額）；grp＝分組欄位（臺灣50＝審核）；info(t)＝依據欄。
    這幾條的成績本來就由逐筆交易算（每筆或每次審核平均），逐筆表就是原始資料。"""
    rows = []
    for t in trs:
        st = t.get("st")
        if st not in ("closed", "open", "skip"):
            continue
        r = t.get("r")
        rows.append({"c": t.get("c"), "d": t.get("d"), "bd": t.get("bd"), "bp": t.get("entry"),
                     "sd": t.get("sd") if st == "closed" else None,
                     "sp": t.get("exit") if st == "closed" else t.get("now"), "so": bool(t.get("so")),
                     "hd": t.get("hd") if t.get("hd") is not None else t.get("held"),
                     "r": r, "mk": None if r is None or t.get("x") is None else round(r - t["x"], 2),
                     "how": t.get("why") if st != "skip" else None, "why": t.get("why") if st == "skip" else None,
                     "st": st, "fw": bool(since and (t.get("d") or "") >= since), "g": t.get(grp) if grp else None,
                     "info": info(t) if info else None, "kc": 0})
    rows.sort(key=lambda x: (x.get("bd") or x.get("d") or "", x["c"] or ""))
    return {"per": [], "tr": pack({"tr": rows})["tr"]}


def reprice(packed: dict | None, raw: Raw) -> dict:
    """既有策略（共識加碼、臺灣50、長線、高股息）的逐筆價格換回當時的實際價格。
    這幾條用每日資料回測，官方分片缺的日子用 Yahoo 補，而 Yahoo 的舊價格已依之後的配股、減資換算過（例：京元電子
    2026-02-24 開盤 Yahoo 301.9、實際 317）→ 價格不在升降單位上的，用 Raw 換回實際價；報酬照回測不動，
    買賣兩邊換算不一樣時把差異寫進還原倍數（mul）並標 kc＝2，報酬＝賣出價 ÷ 買進價 × mul − 1 − 成本仍可驗算。
    換不回來的標「約」（ap）。→ {"fixed": 換回幾個價格, "approx": 幾筆約略}"""
    if not packed:
        return {"fixed": 0, "approx": 0}
    I = {c: k for k, c in enumerate(TR_COLS)}
    fixed = approx = 0
    for row in packed.get("tr") or []:
        st = row[I["st"]] if len(row) > I["st"] else None
        if st not in ("c", "o"):
            continue
        row += [None] * (len(TR_COLS) - len(row))
        c = row[I["c"]]
        olds = {}
        for pk, dk, opn in (("bp", "bd", True), ("sp", "sd", not row[I["so"]] == 0 and bool(row[I["so"]]))):
            v, d = row[I[pk]], row[I[dk]]
            if v is None or d is None or exact_tick(v):
                continue
            nv, ap = raw.px(c, (BASE.fromordinal(BASE.toordinal() + d)).isoformat(), opn if pk == "sp" else True)
            if nv and exact_tick(nv) and not ap:
                olds[pk] = v
                row[I[pk]] = nv
                fixed += 1
            else:
                row[I["ap"]] = 1
                approx += 1
        if olds and st == "c" and row[I["bp"]] and row[I["sp"]]:
            ob, os_ = olds.get("bp", row[I["bp"]]), olds.get("sp", row[I["sp"]])
            mul = (os_ / ob) / (row[I["sp"]] / row[I["bp"]])
            if abs(mul - 1) >= 0.0005:
                row[I["mul"]], row[I["kc"]] = round(mul, 4), 2
        if st == "c" and row[I["bd"]] is not None and row[I["sd"]] is not None:   # 持有期間除權息（這幾條的報酬不含股利，列出來供對照）
            iso = lambda n: (BASE.fromordinal(BASE.toordinal() + n)).isoformat()
            dv = raw.divs(c, iso(row[I["bd"]]), iso(row[I["sd"]]))
            if dv:
                row[I["dv"]] = [[dnum(x[0]), x[1], x[2]] for x in dv]
        _trim(row)
    return {"fixed": fixed, "approx": approx}
