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


def events() -> dict[str, list[tuple[str, float]]]:
    """除權息事件 {代號: [(除權息日, 參考價 ÷ 前收)]}：上市 divtw、上櫃 v3div。"""
    ev: dict[str, list] = {}
    for _, doc in store.load("divtw"):
        for r in doc.get("rows") or []:
            d, c, before, ref = r[0], r[1], r[4], r[5]
            if before and ref and 0 < ref < before:
                ev.setdefault(c, []).append((d, ref / before))
    for _, doc in store.load("v3div"):
        for r in doc.get("rows") or []:
            d, c, before, ref = r[0], r[1], r[2], r[3]
            if before and ref and 0 < ref < before:
                ev.setdefault(c, []).append((d, ref / before))
    return {c: sorted(set(v)) for c, v in ev.items()}


def month_end_caps() -> list[tuple[str, dict]]:
    """[(月底日, {代號: 市值})]，上市＋上櫃同月合併，依日期排序。"""
    by: dict[str, tuple[str, dict]] = {}
    for kind in ("v3me_tw", "v3me_tp"):
        for ym, doc in store.load(kind):
            d0, m0 = by.get(ym, ("", {}))
            caps = {c: px * sh for c, (px, sh) in (doc.get("s") or {}).items() if px and sh}
            by[ym] = (max(d0, doc.get("d") or ""), {**m0, **caps})
    return sorted(by.values())


def factor_yahoo(c: list, a: list) -> list[float]:
    """還原收盤 ÷ 收盤（缺值用下一個有效值，因為兩次除息之間是常數；最後缺就 1）。"""
    T = len(c)
    F = [1.0] * T
    nxt = 1.0
    for i in range(T - 1, -1, -1):
        if c[i] and a[i]:
            nxt = a[i] / c[i]
        F[i] = nxt
    return F


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
                F = factor_yahoo(cl, x)
                val = [cc * vv if cc and vv else None for cc, vv in zip(cl, v)]
            else:
                F = factor_events(cal, ev.get(c) or [])
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


def load_eps() -> dict[str, dict]:
    """v3eps（2012 起單季 EPS）→ {代號: {季底: EPS}}。"""
    out = {}
    for c in store.dates("v3eps"):
        e = (store.read("v3eps", c) or {}).get("eps") or {}
        if e:
            out[c] = e
    return out
