"""fuhhwa-fund-radar 的 data/lab 長歷史 → engine.Market（PROGRESS A8：FinMind 全量下載完成前，先用這份資料跑 P4）。

資料：上一層 repo 的 data/lab（官方＋Yahoo＋FinMind 已下市股，2013-01 起），由 fuhhwa 的 arm.lab.bt3d.Panel 整理：
  · 價格＝含息還原（向後還原、口徑連續化）。原始價＝v3px 的收盤（Yahoo 已還原股票股利、沒還原現金股利；
    FinMind 已下市股為原始價），只拿來算張數與成交值級距。
  · 成交值＝原始收盤 × 成交量（Yahoo）或成交金額（FinMind）。成交量 0 的日子當作沒交易（價格設成 NaN）。
  · 名單只收「曾經月底市值 ≥40 億」的股票（fuhhwa 的回補範圍），所以合格條件另加「最近月底市值 ≥40 億」：
    更小的股票只有日後長大的才在資料裡，不加這條等於用未來挑樣本。
  · 沒有處置股資料 → 不擋處置期間進場、不加處置滑價。
  · 一價到底漲停／跌停：開＝高＝低＝收，且漲跌幅 ≥ 漲跌停 − 1.5 個百分點（SPEC §3.4；2015-06-01 前 7%、之後 10%）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import Market

REPO = Path(__file__).resolve().parents[3]          # fuhhwa-fund-radar
CAP_MIN = 40e8                                      # 最近月底市值（元）


def arm():
    """fuhhwa 的 arm.lab 模組（純 Python，資料路徑寫在模組裡）。"""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from arm.lab import bt3d, store  # noqa: WPS433

    return bt3d, store


def limit_pct(dates: pd.DatetimeIndex) -> np.ndarray:
    return np.where(dates < pd.Timestamp("2015-06-01"), 0.07, 0.10)


def _col(xs, T: int) -> np.ndarray:
    return np.array([np.nan if x is None else float(x) for x in xs], dtype=float) if xs is not None else np.full(T, np.nan)


def locks(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, dates: pd.DatetimeIndex):
    """一價到底漲停／跌停（還原價；除權息日的前收在同一口徑，等於以參考價為基準）。"""
    prev = pd.DataFrame(c).ffill().shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        ret = c / prev - 1
    one = (o == h) & (h == l) & (l == c) & ~np.isnan(c)
    lim = limit_pct(dates)[:, None] - 0.015
    return one & (ret >= lim), one & (ret <= -lim)


def fundamentals(cal: list[str], codes: list[str]):
    """→ get(股票, 日索引) → 當天收盤時可得的最新一季與最新一個月的基本面（fuhhwa superx.Fund，同一套 PIT）：
    ey＝最新季 EPS 年增、ry＝最新月營收年增、c33＝Code 33 等。財報＝法定期限當天或之後第一個交易日、營收＝每月 10 日起。"""
    import bisect

    bt3d, _ = arm()
    from arm.lab import company, v3data  # noqa: WPS433
    from arm.lab import packtest as PT  # noqa: WPS433
    from arm.lab import superx as SX  # noqa: WPS433

    fs, eps, rev = v3data.load_fs(), bt3d.mops_quarterly(), PT.load_rev()
    funds = {c: SX.Fund(company.quarters(fs.get(c), eps.get(c)), rev.get(c) or {}) for c in codes}
    qs, rf = SX.avail_index(cal)
    qitems = sorted((t, q) for q, t in qs.items())
    rf_t = [t for t, _ in rf]

    def get(c: str, i: int) -> dict:
        fd = funds.get(c)
        if fd is None:
            return {}
        q = SX.latest_q(qitems, i)
        k = bisect.bisect_right(rf_t, i) - 1
        ym = rf[k][1] if k >= 0 else None
        f: dict = {}
        if ym and ym in fd.rv:
            f.update(fd.m_feats(ym))
        if q and q in fd.fq:
            f.update(fd.q_feats(q))
        return f

    return get


def load(start: str = "2013-01-01", codes: list[str] | None = None) -> tuple[Market, dict]:
    """→ (Market, extra)。extra：cap（月底市值，日期 × 股票）、src（資料來源）、cal（日期字串）。"""
    bt3d, store = arm()
    P = bt3d.Panel(start=start, codes=codes)
    cal = P.cal
    T = len(cal)
    stocks = list(P.codes)
    N = len(stocks)
    ix = {d: i for i, d in enumerate(cal)}
    O, H, L, C, V, RAW, VAL, CAP = (np.full((T, N), np.nan) for _ in range(8))
    for j, c in enumerate(stocks):
        s = P.s[c]
        o, h, l, cl = (_col(s[k], T) for k in ("o", "h", "l", "c"))
        v = np.array([np.nan if not x else float(x) for x in s["v"]], dtype=float)
        dead = np.isnan(v)                         # 沒成交量＝沒交易
        for a in (o, h, l, cl):
            a[dead] = np.nan
        O[:, j], H[:, j], L[:, j], C[:, j], V[:, j] = o, h, l, cl, v
        CAP[:, j] = _col(P.cap[c], T)
        doc = store.read("v3px", c) or {}
        raw = np.full(T, np.nan)
        val = np.full(T, np.nan)
        for k, d in enumerate(doc.get("t") or []):
            i = ix.get(d)
            if i is None:
                continue
            x = doc["c"][k]
            raw[i] = np.nan if x is None else float(x)
            if doc.get("src") != "yahoo" and doc.get("val"):
                y = doc["val"][k]
                val[i] = np.nan if y is None else float(y)
        if doc.get("src") == "yahoo":
            val = raw * v
        raw[dead] = np.nan
        val[dead] = np.nan
        RAW[:, j], VAL[:, j] = raw, val
    src = dict(P.src)
    idx = pd.Series([np.nan if x is None else float(x) for x in P.idx], index=pd.DatetimeIndex(cal))
    tr = pd.Series([np.nan if x is None else float(x) for x in P.tr], index=pd.DatetimeIndex(cal))
    del P
    dates = pd.DatetimeIndex(cal)
    with np.errstate(invalid="ignore", divide="ignore"):
        F = np.where((RAW > 0) & (C > 0), C / RAW, np.nan)
    F = pd.DataFrame(F).ffill().bfill().fillna(1.0).to_numpy()
    lu, ld = locks(O, H, L, C, dates)
    m = Market(dates, stocks, O, H, L, C, factor=F, value=VAL, volume=V, locked_up=lu, locked_down=ld,
               index_level=idx.dropna(), index_tr=tr.dropna())
    return m, {"cap": CAP, "src": src, "cal": cal}
