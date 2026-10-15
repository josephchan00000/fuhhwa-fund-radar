"""回測 v3 長歷史面板（docs/backtest_v3_plan.md 第 10 節）：把 v3px／v3me／除權息組成 bt3 引擎用的面板。

口徑：
  · 價格＝還原權息（含息總報酬）。Yahoo 來源：o／h／l／c 已還原股票股利，乘上「還原收盤 ÷ 收盤」補現金股利；
    FinMind（已下市）原始價：除權息表「參考價 ÷ 前收」由新往舊累乘（現金與配股都在內）。最後再做口徑連續化
    （相鄰兩日收盤比 >1.8 倍＝面額變更）。這個口徑下除權息日的漲停判斷剛好以參考價為基準（同交易所規則）。
  · 市值＝最近一個月底（含當天）的官方收盤 × 發行股數；20 日均成交值＝收盤 × 成交量（Yahoo，對還原不敏感）
    或成交金額（FinMind）。
  · 名單＝當天有價、有月底市值的股票，含之後下市者（下市後沒有價格，自然退出）。
"""
from __future__ import annotations

import bisect

from . import packtest as PT
from . import store
from .v3data import stock


def events() -> dict[str, list[tuple]]:
    """除權息事件 {代號: [(除權息日, 參考價 ÷ 前收, 現金部分倍數或 None)]}。
    上市 divtw：只有「息」知道現金部分（＝整體倍數），「權」「權息」的現金金額表上沒有 → None；
    上櫃 v3div：現金股利與配股分列 → 現金部分＝1 − 現金股利 ÷ 前收。"""
    ev: dict[str, list] = {}
    for _, doc in store.load("divtw"):
        for r in doc.get("rows") or []:
            d, c, typ, before, ref = r[0], r[1], r[3], r[4], r[5]
            if before and ref and 0 < ref < before:
                ev.setdefault(c, []).append((d, ref / before, ref / before if typ == "息" else None))
    for _, doc in store.load("v3div"):
        for r in doc.get("rows") or []:
            d, c, before, ref, cash = r[0], r[1], r[2], r[3], r[4]
            if before and ref and 0 < ref < before:
                fc = 1 - cash / before if cash and 0 < cash < before else 1.0
                ev.setdefault(c, []).append((d, ref / before, fc))
    return {c: sorted(set(v), key=lambda x: (x[0], x[1])) for c, v in ev.items()}


def month_end_caps() -> list[tuple[str, dict]]:
    """[(月底日, {代號: 市值})]，上市＋上櫃同月合併，依日期排序。"""
    by: dict[str, tuple[str, dict]] = {}
    for kind in ("v3me_tw", "v3me_tp"):
        for ym, doc in store.load(kind):
            d0, m0 = by.get(ym, ("", {}))
            caps = {c: px * sh for c, (px, sh) in (doc.get("s") or {}).items() if px and sh}
            by[ym] = (max(d0, doc.get("d") or ""), {**m0, **caps})
    return sorted(by.values())


def factor_yahoo(cal: list[str], c: list, a: list, ev: list[tuple]) -> list[float]:
    """Yahoo 價（已還原股票股利）的現金股利還原倍數：官方知道現金部分的用官方（純現金股利、上櫃全部），
    上市「權」「權息」用 Yahoo 還原收盤在當天隱含的倍數。2026-10-15 比對 1.1 萬筆現金股利：Yahoo 與官方差 >1%
    的約 2.5%（金額不同 119、沒扣 39、扣在別天 28），所以以官方為主。"""
    T = len(cal)
    ix = {d: i for i, d in enumerate(cal)}

    def yf(i):
        if 0 < i < T and c[i - 1] and a[i - 1] and c[i] and a[i]:
            return (a[i - 1] / c[i - 1]) / (a[i] / c[i])
        return 1.0
    fs = []
    for d, _, fc in ev:
        i = ix.get(d)
        if i is None:
            continue
        fs.append((d, fc if fc is not None else yf(i)))
    return factor_events(cal, fs)


def factor_events(cal: list[str], ev: list[tuple[str, float]]) -> list[float]:
    """原始價的還原倍數：F[i]＝所有除權息日 > cal[i] 的「參考價 ÷ 前收」連乘。"""
    T = len(cal)
    F = [1.0] * T
    f, k = 1.0, len(ev) - 1
    for i in range(T - 1, -1, -1):
        while k >= 0 and ev[k][0] > cal[i]:
            f *= ev[k][1]
            k -= 1
        F[i] = f
    return F


class Panel(PT.Px):
    """packtest.Px 介面（s、cap、liq、elig、win…），資料來自 v3 長歷史。"""

    def __init__(self, start: str = "2013-01-01", codes: list[str] | None = None, min_days: int = 60):
        tw = store.read("v3px", "TWII") or {}
        cal = [d for d in tw.get("t") or [] if d >= start]
        self.cal, self.T = cal, len(cal)
        self.ix = {d: i for i, d in enumerate(cal)}
        T, ix = self.T, self.ix
        self.idx, self.idx_o = [None] * T, [None] * T
        for d, o, c in zip(tw.get("t") or [], tw.get("o") or [], tw.get("c") or []):
            if d in ix:
                self.idx[ix[d]], self.idx_o[ix[d]] = c, o
        trq = (store.read_json("v3_tr.json", {}) or {}).get("q") or {}
        self.tr = [trq.get(d) for d in cal]
        snaps = month_end_caps()
        sd = [d for d, _ in snaps]
        kof = [bisect.bisect_right(sd, d) - 1 for d in cal]           # 每天用的月底快照
        ev = events()
        codes = codes if codes is not None else [c for c in store.dates("v3px") if stock(c)]
        self.s, self.cap, self.liq, self.src = {}, {}, {}, {}
        for c in codes:
            doc = store.read("v3px", c)
            if not doc or not doc.get("t"):
                continue
            o, h, l, cl, v, x = ([None] * T for _ in range(6))
            ex = doc.get("a") if doc.get("src") == "yahoo" else doc.get("val")
            for k, d in enumerate(doc["t"]):
                i = ix.get(d)
                if i is None or not doc["c"][k]:
                    continue
                o[i], h[i], l[i], cl[i], v[i] = doc["o"][k], doc["h"][k], doc["l"][k], doc["c"][k], doc["v"][k]
                x[i] = ex[k] if ex else None
            if sum(1 for y in cl if y) < min_days:
                continue
            if doc.get("src") == "yahoo":
                F = factor_yahoo(cal, cl, x, ev.get(c) or [])
                val = [cc * vv if cc and vv else None for cc, vv in zip(cl, v)]
            else:
                F = factor_events(cal, [(d, f) for d, f, _ in ev.get(c) or []])
                val = x
            tr = [None if y is None else y * F[i] for i, y in enumerate(cl)]
            B = PT._basis(tr)
            adj = lambda xs: [None if y is None else y * F[i] / B[i] for i, y in enumerate(xs)]
            self.s[c] = {"o": adj(o), "h": adj(h), "l": adj(l), "c": [None if y is None else y / B[i] for i, y in enumerate(tr)],
                         "v": v}
            self.cap[c] = [snaps[k][1].get(c) if k >= 0 else None for k in kof]
            self.liq[c] = PT._rmean(val, 20, 10)
            self.src[c] = doc.get("src")
        self.codes = sorted(self.s)
        self.lock_n = 0
        self._el: dict = {}
        self._win: dict = {}


QEND = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def mops_quarterly() -> dict[str, dict]:
    """綜合損益表彙總（當年累計 EPS）→ 單季 {代號: {季底: EPS}}：Q1＝累計、Qn＝累計(n) − 累計(n−1)；前一季缺就不算。"""
    cum: dict[str, dict] = {}
    for key, doc in store.load("v3isq"):
        y, q = int(key[:4]), int(key[5])
        for m in ("sii", "otc"):
            for c, v in (doc.get(m) or {}).items():
                cum.setdefault(c, {})[(y, q)] = v
    out: dict[str, dict] = {}
    for c, d in cum.items():
        e = {}
        for (y, q), v in d.items():
            if q == 1:
                e[f"{y}-{QEND[q]}"] = v
            elif (y, q - 1) in d:
                e[f"{y}-{QEND[q]}"] = round(v - d[(y, q - 1)], 4)
        if e:
            out[c] = e
    return out


def load_eps() -> dict[str, dict]:
    """單季 EPS {代號: {季底: EPS}}：公開資訊觀測站彙總表（官方，2013 起）為主，FinMind（v3eps，2012 起）補缺的季。"""
    out: dict[str, dict] = {}
    for c in store.dates("v3eps"):
        e = (store.read("v3eps", c) or {}).get("eps") or {}
        if e:
            out[c] = dict(e)
    for c, e in mops_quarterly().items():
        out[c] = {**out.get(c, {}), **e}
    return out
