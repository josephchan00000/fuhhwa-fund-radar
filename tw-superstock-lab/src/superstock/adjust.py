"""還原價：用除權息、減資、分割、面額變更事件自行計算還原因子。

做法（向後還原，最新價格不變）：
  每個事件在「事件日（恢復交易／除權息交易日）」有一個因子 f = 事件後參考價 ÷ 事件前收盤價。
  某日的還原價 = 原始價 × 所有「晚於該日」事件因子的乘積。
  現金股利 f < 1（過去價格往下調）；彌補虧損減資 f > 1（過去價格往上調）。
  這樣算出的日報酬 = 含息總報酬，事件日不會出現假跳空。

漲跌停鎖死判斷：
  一價到底（開＝高＝低＝收）且當日還原報酬接近漲跌幅上限。
  上限：2015-06-01 前 7%，之後 10%。新股上市前 5 日無漲跌幅，品質檢查另外處理。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 資料集 → (事件前價格欄位, 事件後參考價欄位)
EVENT_SOURCES: dict[str, tuple[str, str]] = {
    "TaiwanStockDividendResult": ("before_price", "after_price"),
    "TaiwanStockCapitalReductionReferencePrice": ("ClosingPriceonTheLastTradingDay",
                                                  "PostReductionReferencePrice"),
    "TaiwanStockSplitPrice": ("before_price", "after_price"),
    "TaiwanStockParValueChange": ("before_close", "after_ref_close"),
}

LIMIT_CHANGE_DATE = pd.Timestamp("2015-06-01")
FACTOR_MIN, FACTOR_MAX = 0.05, 20.0


def build_events(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """回傳 stock_id, date, factor, source；同一天多個事件會相乘。"""
    rows = []
    for source, (before_col, after_col) in EVENT_SOURCES.items():
        df = frames.get(source)
        if df is None or df.empty or before_col not in df.columns or after_col not in df.columns:
            continue
        before = pd.to_numeric(df[before_col], errors="coerce")
        after = pd.to_numeric(df[after_col], errors="coerce")
        factor = after / before
        ok = (before > 0) & (after > 0) & factor.between(FACTOR_MIN, FACTOR_MAX)
        part = pd.DataFrame({
            "stock_id": df.loc[ok, "stock_id"].astype(str).values,
            "date": pd.to_datetime(df.loc[ok, "date"], errors="coerce").values,
            "factor": factor[ok].values,
            "source": source,
        })
        part = part.dropna(subset=["date"])
        part = part.drop_duplicates(subset=["stock_id", "date", "source"], keep="last")
        rows.append(part)
    if not rows:
        return pd.DataFrame(columns=["stock_id", "date", "factor", "source"])
    events = pd.concat(rows, ignore_index=True)
    events = (events.groupby(["stock_id", "date"], as_index=False)
              .agg(factor=("factor", "prod"), source=("source", lambda s: "+".join(sorted(set(s))))))
    return events.sort_values(["stock_id", "date"]).reset_index(drop=True)


def apply_adjustment(prices: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """prices 需有 stock_id, date(datetime64), open, high, low, close。
    新增 adj_factor, adj_open, adj_high, adj_low, adj_close, ret（還原日報酬）。"""
    if prices.empty:
        return prices.assign(adj_factor=[], adj_open=[], adj_high=[], adj_low=[],
                             adj_close=[], ret=[])
    prices = prices.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)
    factor = np.ones(len(prices))
    ev_by_stock = {sid: g for sid, g in events.groupby("stock_id")} if not events.empty else {}
    stock_ids = prices["stock_id"].to_numpy()
    dates = prices["date"].to_numpy(dtype="datetime64[ns]")
    # 依股票切段（prices 已排序）
    boundaries = np.flatnonzero(stock_ids[1:] != stock_ids[:-1]) + 1
    starts = np.concatenate([[0], boundaries])
    ends = np.concatenate([boundaries, [len(prices)]])
    for s, e in zip(starts, ends):
        ev = ev_by_stock.get(stock_ids[s])
        if ev is None or ev.empty:
            continue
        ev = ev.sort_values("date")
        ev_dates = ev["date"].to_numpy(dtype="datetime64[ns]")
        f = ev["factor"].to_numpy(dtype=float)
        suffix = np.append(np.cumprod(f[::-1])[::-1], 1.0)  # suffix[i] = f[i]*...*f[n-1]
        idx = np.searchsorted(ev_dates, dates[s:e], side="right")  # 第一個「晚於該日」的事件
        factor[s:e] = suffix[idx]
    out = prices.copy()
    out["adj_factor"] = factor
    for col in ("open", "high", "low", "close"):
        out[f"adj_{col}"] = out[col].astype(float) * factor
    prev = out.groupby("stock_id", sort=False)["adj_close"].shift(1)
    out["ret"] = out["adj_close"] / prev - 1.0
    return out


def limit_pct(dates: pd.Series) -> np.ndarray:
    return np.where(pd.to_datetime(dates) < LIMIT_CHANGE_DATE, 0.07, 0.10)


def flag_limits(prices: pd.DataFrame, tolerance: float = 0.015) -> pd.DataFrame:
    """新增 locked_up / locked_down（一價到底的漲停／跌停，當天實際上幾乎無法成交）。"""
    out = prices.copy()
    one_price = (out["open"] == out["high"]) & (out["high"] == out["low"]) & (out["low"] == out["close"])
    lim = limit_pct(out["date"])
    ret = out["ret"].to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        out["locked_up"] = one_price.to_numpy() & (ret >= lim - tolerance)
        out["locked_down"] = one_price.to_numpy() & (ret <= -(lim - tolerance))
    return out
