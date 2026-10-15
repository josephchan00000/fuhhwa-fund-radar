"""把原始資料整理成研究用的乾淨資料表（data/processed/）。

輸出：
  universe.parquet       股票池（含下市）
  calendar.parquet       交易日
  index.parquet          加權／櫃買指數與報酬指數
  events.parquet         還原事件（因子）
  prices.parquet         日 K：原始價、還原價、還原日報酬、漲跌停鎖死旗標
  revenue.parquet        月營收＋可用日（point-in-time）
  financials.parquet     綜合損益表（長表）＋可用日
  institutional.parquet  三大法人買賣超（寬表，單位：股）
  margin.parquet         融資融券餘額
  disposition.parquet    處置股期間
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .adjust import EVENT_SOURCES, apply_adjustment, build_events, flag_limits
from .config import Config
from .datasets import get_spec
from .pit import add_financial_availability, add_revenue_availability
from .storage import GLOBAL_KEY, Store
from .universe import build_universe

log = logging.getLogger(__name__)

PRICE_RENAME = {"max": "high", "min": "low", "Trading_Volume": "volume",
                "Trading_money": "value", "Trading_turnover": "trades"}

INSTITUTION_NAMES = {
    "Foreign_Investor": "foreign",
    "Foreign_Dealer_Self": "foreign_dealer",
    "Investment_Trust": "trust",
    "Dealer_self": "dealer_self",
    "Dealer_Hedging": "dealer_hedge",
}


def _read(store: Store, store_name: str) -> pd.DataFrame:
    return store.read_all(get_spec(store_name))


def _write(df: pd.DataFrame, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return len(df)


def build_prices(store: Store, universe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = _read(store, "TaiwanStockPrice")
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame()
    prices = raw.rename(columns=PRICE_RENAME)
    prices["stock_id"] = prices["stock_id"].astype(str)
    prices = prices[prices["stock_id"].isin(universe["stock_id"])].copy()
    prices["date"] = pd.to_datetime(prices["date"])
    for col in ("open", "high", "low", "close"):
        num = pd.to_numeric(prices[col], errors="coerce").astype(float)
        # 無成交日 FinMind 可能給 0 價；視為缺值，避免算出 -100% 報酬
        prices[col] = num.where(num > 0)
    prices = prices.dropna(subset=["close"])

    frames = {name: _read(store, name) for name in EVENT_SOURCES}
    events = build_events(frames)
    adjusted = apply_adjustment(prices, events)
    adjusted = flag_limits(adjusted)
    keep = ["date", "stock_id", "open", "high", "low", "close", "volume", "value", "trades",
            "adj_factor", "adj_open", "adj_high", "adj_low", "adj_close", "ret",
            "locked_up", "locked_down"]
    adjusted = adjusted[[c for c in keep if c in adjusted.columns]]
    return adjusted, events


def build_institutional(store: Store) -> pd.DataFrame:
    raw = _read(store, "TaiwanStockInstitutionalInvestorsBuySell")
    if raw.empty:
        return raw
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["net"] = pd.to_numeric(df["buy"], errors="coerce") - pd.to_numeric(df["sell"], errors="coerce")
    df["who"] = df["name"].map(INSTITUTION_NAMES).fillna(df["name"])
    wide = df.pivot_table(index=["date", "stock_id"], columns="who", values="net",
                          aggfunc="sum").reset_index()
    wide.columns.name = None
    wide = wide.rename(columns={c: f"net_{c}" for c in wide.columns if c not in ("date", "stock_id")})
    return wide.sort_values(["stock_id", "date"]).reset_index(drop=True)


def build_margin(store: Store) -> pd.DataFrame:
    raw = _read(store, "TaiwanStockMarginPurchaseShortSale")
    if raw.empty:
        return raw
    cols = ["date", "stock_id", "MarginPurchaseTodayBalance", "MarginPurchaseLimit",
            "ShortSaleTodayBalance", "ShortSaleLimit", "MarginPurchaseBuy", "MarginPurchaseSell"]
    df = raw[[c for c in cols if c in raw.columns]].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.rename(columns={"MarginPurchaseTodayBalance": "margin_balance",
                              "MarginPurchaseLimit": "margin_limit",
                              "ShortSaleTodayBalance": "short_balance",
                              "ShortSaleLimit": "short_limit",
                              "MarginPurchaseBuy": "margin_buy",
                              "MarginPurchaseSell": "margin_sell"})


def build_index(store: Store) -> pd.DataFrame:
    level = _read(store, "IndexPrice")
    tri = _read(store, "TaiwanStockTotalReturnIndex")
    frames = []
    if not level.empty:
        lv = level.rename(columns=PRICE_RENAME)[["date", "stock_id", "close"]].copy()
        lv = lv.rename(columns={"stock_id": "index_id", "close": "level"})
        frames.append(lv)
    if not tri.empty:
        tr = tri.rename(columns={"stock_id": "index_id", "price": "total_return"})
        tr = tr[[c for c in ("date", "index_id", "total_return") if c in tr.columns]]
        frames.append(tr)
    if not frames:
        return pd.DataFrame()
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on=["date", "index_id"], how="outer")
    out["date"] = pd.to_datetime(out["date"])
    return out.sort_values(["index_id", "date"]).reset_index(drop=True)


def build_all(cfg: Config) -> dict[str, int]:
    store = Store(cfg.raw_dir)
    out_dir = cfg.processed_dir
    counts: dict[str, int] = {}

    info_spec, del_spec = get_spec("TaiwanStockInfo"), get_spec("TaiwanStockDelisting")
    info = store.read(info_spec, GLOBAL_KEY)
    delisting = store.read(del_spec, GLOBAL_KEY)
    if info is None or info.empty:
        raise RuntimeError("找不到股票清單，請先執行 download（meta 群組）")
    universe = build_universe(info, delisting, cfg.universe, cfg.start_date)
    counts["universe"] = _write(universe, out_dir / "universe.parquet")

    cal = store.read(get_spec("TaiwanStockTradingDate"), GLOBAL_KEY)
    if cal is not None and not cal.empty:
        cal = cal.assign(date=pd.to_datetime(cal["date"]))[["date"]].drop_duplicates().sort_values("date")
        counts["calendar"] = _write(cal, out_dir / "calendar.parquet")

    index = build_index(store)
    if not index.empty:
        counts["index"] = _write(index, out_dir / "index.parquet")

    prices, events = build_prices(store, universe)
    if not events.empty:
        counts["events"] = _write(events, out_dir / "events.parquet")
    if not prices.empty:
        counts["prices"] = _write(prices, out_dir / "prices.parquet")
        log.info("prices：%s 列、%s 檔", len(prices), prices["stock_id"].nunique())

    rev = _read(store, "TaiwanStockMonthRevenue")
    if not rev.empty:
        rev = add_revenue_availability(rev)
        keep = ["stock_id", "period", "revenue_year", "revenue_month", "revenue", "available_date"]
        counts["revenue"] = _write(rev[[c for c in keep if c in rev.columns]], out_dir / "revenue.parquet")

    fin = _read(store, "TaiwanStockFinancialStatements")
    if not fin.empty:
        fin = add_financial_availability(fin)
        keep = ["stock_id", "period_end", "type", "value", "origin_name", "available_date"]
        counts["financials"] = _write(fin[[c for c in keep if c in fin.columns]],
                                      out_dir / "financials.parquet")

    inst = build_institutional(store)
    if not inst.empty:
        counts["institutional"] = _write(inst, out_dir / "institutional.parquet")

    margin = build_margin(store)
    if not margin.empty:
        counts["margin"] = _write(margin, out_dir / "margin.parquet")

    disp = _read(store, "TaiwanStockDispositionSecuritiesPeriod")
    if not disp.empty:
        counts["disposition"] = _write(disp, out_dir / "disposition.parquet")

    return counts
