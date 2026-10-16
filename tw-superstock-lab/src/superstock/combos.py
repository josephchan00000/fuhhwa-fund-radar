"""P5（lab 面板先跑）：綜合策略族——《超級績效》SEPA × 現行飆股規則 × 月營收（reports/P5_plan.md，跑之前寫定）。

7 族 × 進場 2 種 × 出場 3 種 × 大盤 2 種＝84 組；訊號都在 t 日收盤判斷、t+1 開盤成交（引擎規則見 engine.py）。
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from . import engine as EN
from . import strategies as ST

FAMILIES = ("F0", "F1", "F2", "F3", "F4", "F5", "F6")
A_FAMILIES = ("F4", "F5")                         # 用到現行飆股 A 規則的族（IS／VAL 是樣本內）
FNAME = {"F0": "VCP 突破", "F1": "樣板突破", "F2": "樣板突破＋營收強", "F3": "VCP 突破＋營收強",
         "F4": "飆股候選＋樣板突破", "F5": "飆股候選＋站上 50 日線", "F6": "營收創新高＋樣板"}
ENTRIES = {"E1": "訊號隔天開盤買", "E2": "20 日內第一次拉回 20 日線再買"}
EXITS = {"X1": {"ma_exit": 50, "max_hold": None}, "X2": {"ma_exit": 20, "max_hold": None},
         "X3": {"ma_exit": None, "max_hold": 60}}
XNAME = {"X1": "跌破 50 日線", "X2": "跌破 20 日線", "X3": "持有 60 日"}
MARKETS = {"M1": True, "M0": False}
BASE = {"stop_pct": 0.08, "breakeven_r": 2.0, "vol": 1.5, "watch_weeks": 8, "rev_yoy": 0.20,
        "pull_days": 20, "pull_tol": 0.01}


def configs() -> list[tuple[str, str, str, str]]:
    return [(f, e, x, k) for f in FAMILIES for e in ENTRIES for x in EXITS for k in MARKETS]


def cname(f: str, e: str, x: str, k: str) -> str:
    return f"{f}_{e}_{x}_{k}"


# ---------------------------------------------------------------------------------------------- 背景資料
class Ctx:
    """一次算好的東西：均線、A 規則訊號與觀察名單、營收可得日、基本面查詢。"""

    def __init__(self, m: EN.Market, F: dict, fund, a_rows: list[tuple[str, str]], rev_days: list[tuple[int, str]]):
        self.m, self.F, self.fund = m, F, fund
        self._ma: dict[int, np.ndarray] = {50: F["ma50"]}
        self.week_ends = _week_ends(m.dates)
        self.asig = np.zeros(m.c.shape, dtype=bool)
        ix = {d: i for i, d in enumerate(m.dates)}
        for c, d in a_rows:
            j, i = m.col.get(c), ix.get(pd.Timestamp(d))
            if j is not None and i is not None:
                self.asig[i, j] = True
        self.rev_days = rev_days
        self._watch: dict[int, np.ndarray] = {}
        self._rev: dict[tuple, bool] = {}

    def ma(self, n: int) -> np.ndarray:
        if n not in self._ma:
            self._ma[n] = pd.DataFrame(self.m.c_ff).rolling(n, min_periods=n).mean().to_numpy()
        return self._ma[n]

    def watch(self, weeks: int) -> np.ndarray:
        """t 以前最近 weeks 個週末內符合過任一條 A 規則：週末 W_k 的訊號涵蓋 [W_k, W_{k+weeks})。"""
        if weeks not in self._watch:
            W = self.week_ends
            out = np.zeros(self.asig.shape, dtype=bool)
            for k, w in enumerate(W):
                hit = self.asig[w]
                if not hit.any():
                    continue
                end = W[k + weeks] if k + weeks < len(W) else self.m.n
                out[w:end] |= hit
            self._watch[weeks] = out
        return self._watch[weeks]

    def rev_strong(self, c: str, i: int, yoy: float) -> bool:
        k = (c, i, yoy)
        if k not in self._rev:
            f = self.fund(c, i)
            self._rev[k] = bool(f.get("rnh12") is True or (f.get("ry3") is not None and f["ry3"] >= yoy))
        return self._rev[k]


def _week_ends(dates: pd.DatetimeIndex) -> list[int]:
    iso = [d.isocalendar()[:2] for d in dates]
    return [i for i in range(len(dates)) if i + 1 == len(dates) or iso[i + 1] != iso[i]]


# ---------------------------------------------------------------------------------------------- 訊號
def family_mask(ctx: Ctx, fam: str, p: dict) -> np.ndarray:
    m, F = ctx.m, ctx.F
    el = F["elig"]
    if fam in ("F0", "F1", "F2", "F3", "F4"):
        spec = ST.spec_of("S01", vcp=fam in ("F0", "F3"), vol=p["vol"])
        mask = ST.s01_mask(m, F, spec)
        if fam in ("F2", "F3"):
            ii, jj = np.nonzero(mask)
            for i, j in zip(ii.tolist(), jj.tolist()):
                if not ctx.rev_strong(m.stocks[j], i, p["rev_yoy"]):
                    mask[i, j] = False
        if fam == "F4":
            mask &= ctx.watch(p["watch_weeks"])
        return mask
    if fam == "F5":
        with np.errstate(invalid="ignore"):
            return ctx.asig & (m.c > ctx.ma(50)) & el
    if fam == "F6":
        mask = np.zeros(m.c.shape, dtype=bool)
        tt = F["tt_pass"]
        for t, _ in ctx.rev_days:
            if not (0 <= t < m.n):
                continue
            for j in np.flatnonzero(tt[t] & el[t]).tolist():
                if ctx.fund(m.stocks[j], t).get("rnha") is True:
                    mask[t, j] = True
        return mask
    raise KeyError(fam)


def pullback(ctx: Ctx, mask: np.ndarray, p: dict) -> np.ndarray:
    """E2：訊號後 pull_days 個交易日內，第一個收盤 ≤ 20 日線 × (1+tol) 且收盤 > 50 日線的日子（只看之後的日子）。"""
    m = ctx.m
    c, ma20, ma50 = m.c, ctx.ma(20), ctx.ma(50)
    out = np.zeros(mask.shape, dtype=bool)
    L, tol = p["pull_days"], p["pull_tol"]
    for t, j in zip(*np.nonzero(mask)):
        for d in range(t + 1, min(t + L, m.n - 1) + 1):
            x = c[d, j]
            if x == x and ma20[d, j] == ma20[d, j] and ma50[d, j] == ma50[d, j] and x <= ma20[d, j] * (1 + tol) \
                    and x > ma50[d, j]:
                out[d, j] = True
                break
    return out


def signals_from(ctx: Ctx, mask: np.ndarray, stop_pct: float, tag: str) -> pd.DataFrame:
    m, rs = ctx.m, ctx.F["rs"]
    ii, jj = np.nonzero(mask)
    return pd.DataFrame({"date": m.dates[ii], "stock_id": np.array(m.stocks)[jj], "entry": "open",
                         "stop_pct": stop_pct, "score": np.nan_to_num(rs[ii, jj]), "tag": tag})


def build_signals(ctx: Ctx, fam: str, entry: str, p: dict | None = None) -> pd.DataFrame:
    p = {**BASE, **(p or {})}
    mask = family_mask(ctx, fam, p)
    if entry == "E2":
        mask = pullback(ctx, mask, p)
    return signals_from(ctx, mask, p["stop_pct"], f"{fam}_{entry}")


# ---------------------------------------------------------------------------------------------- 執行（同 engine.run_trades，大盤濾網與出場旗標先算好重用）
def exit_flags(ctx: Ctx, ma_exit: int | None) -> np.ndarray | None:
    if not ma_exit:
        return None
    with np.errstate(invalid="ignore"):
        return (ctx.m.c < ctx.ma(ma_exit)) & ~np.isnan(ctx.m.c)


def run(ctx: Ctx, sig: pd.DataFrame, *, market: bool, mf: np.ndarray, ma_exit: int | None, max_hold: int | None,
        stop_pct: float = 0.08, breakeven_r: float | None = 2.0, start=None, end=None,
        base: EN.EngineConfig | None = None) -> EN.Result:
    m = ctx.m
    cfg = replace(base or EN.EngineConfig(costs=EN.Costs()), breakeven_r=breakeven_r, market_filter=market,
                  block_disposition=False, max_hold_days=max_hold)
    mfu = mf if market else np.ones(m.n, dtype=bool)
    by_day: dict[int, list[EN.Order]] = {}
    ix = {d: i for i, d in enumerate(m.dates)}
    for d, c, sc in zip(sig["date"], sig["stock_id"], sig["score"]):
        i, s = ix.get(pd.Timestamp(d)), m.col.get(str(c))
        if i is None or s is None:
            continue
        by_day.setdefault(i, []).append(EN.Order(s, "open", stop_pct=stop_pct, score=float(sc)))

    def decide(i: int, sim: EN.Simulator) -> list[EN.Order]:
        if not mfu[i]:
            return []
        return [EN.Order(o.s, o.kind, stop_pct=o.stop_pct, score=o.score) for o in by_day.get(i, [])]

    sim = EN.Simulator(m, cfg, exit_flags=exit_flags(ctx, ma_exit), mf=mfu)
    return sim.run(decide, start, end)


def rev_days(cal: list[str]) -> list[tuple[int, str]]:
    """月營收可得日（fuhhwa superx.avail_index 同一套：每月 10 日當天或之後第一個交易日）→ [(日索引, 營收月)]。"""
    from . import labpanel as LP

    LP.arm()
    from arm.lab import superx as SX  # noqa: WPS433

    return list(SX.avail_index(cal)[1])


def random_signals(ctx: Ctx, sig: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """同一天、同數量，換成當天隨機一檔合格股票（不等於原股票）。"""
    m, el = ctx.m, ctx.F["elig"]
    ix = {d: i for i, d in enumerate(m.dates)}
    out = []
    for d, c in zip(sig["date"], sig["stock_id"]):
        i = ix[pd.Timestamp(d)]
        pool = np.flatnonzero(el[i])
        if len(pool) < 2:
            continue
        j = m.col[str(c)]
        k = j
        while k == j:
            k = int(pool[rng.integers(len(pool))])
        out.append((d, m.stocks[k]))
    r = pd.DataFrame(out, columns=["date", "stock_id"])
    r["entry"], r["stop_pct"], r["score"], r["tag"] = "open", float(sig["stop_pct"].iloc[0]) if len(sig) else 0.08, \
        rng.random(len(r)), "random"
    return r
