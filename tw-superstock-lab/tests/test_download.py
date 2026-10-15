from __future__ import annotations

from datetime import date

import pandas as pd

from conftest import FakeClient, daily_prices, raise_error
from superstock.download import Downloader
from superstock.storage import GLOBAL_KEY, Manifest, Store
from superstock.datasets import get_spec

INFO = pd.DataFrame({
    "stock_id": ["2330", "6488", "0050", "9999", "2881A"],
    "stock_name": ["台積電", "環球晶", "元大台灣50", "興櫃股", "特別股"],
    "type": ["twse", "tpex", "twse", "emerging", "twse"],
    "industry_category": ["半導體業", "半導體業", "ETF", "其他", "金融保險業"],
    "date": ["2026-10-14"] * 5,
})
DELISTING = pd.DataFrame({"date": ["2015-05-05", "2005-01-03"], "stock_id": ["1234", "1111"],
                          "stock_name": ["下市A", "太早下市"]})


def by_range(make):
    def handler(data_id, start, end):
        df = make(data_id)
        if df.empty:
            return df
        d = pd.to_datetime(df["date"])
        return df[(d >= pd.Timestamp(start or "1900-01-01")) & (d <= pd.Timestamp(end or "2100-01-01"))]
    return handler


def dividend_global(data_id, start, end):
    if data_id:  # 逐檔
        return pd.DataFrame({"date": ["2020-07-01"], "stock_id": [data_id], "before_price": [100.0],
                             "after_price": [97.0]})
    rows = pd.DataFrame({"date": ["2014-08-01", "2015-07-01", "2015-08-03"],
                         "stock_id": ["2330", "2330", "6488"],
                         "before_price": [90.0, 100.0, 50.0], "after_price": [88.0, 97.0, 48.0]})
    d = pd.to_datetime(rows["date"])
    return rows[(d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))]


def capital_reduction(data_id, start, end):
    if not data_id:
        raise raise_error("data_id is required")()
    return pd.DataFrame()


def handlers():
    return {
        "TaiwanStockInfo": lambda *_: INFO,
        "TaiwanStockDelisting": lambda *_: DELISTING,
        "TaiwanStockTradingDate": by_range(lambda _: pd.DataFrame(
            {"date": pd.bdate_range("2014-01-01", "2016-01-01").strftime("%Y-%m-%d")})),
        "TaiwanStockPrice": by_range(lambda sid: daily_prices(sid, "2014-01-01", "2016-01-01")),
        "TaiwanStockTotalReturnIndex": by_range(lambda sid: pd.DataFrame(
            {"date": ["2015-01-05"], "stock_id": [sid], "price": [20000.0]})),
        "TaiwanStockMonthRevenue": lambda sid, s, e: pd.DataFrame(
            {"date": ["2015-02-01"], "stock_id": [sid], "revenue_year": [2015], "revenue_month": [1],
             "revenue": [1000]}),
        "TaiwanStockFinancialStatements": lambda *_: pd.DataFrame(),
        "TaiwanStockInstitutionalInvestorsBuySell": lambda *_: pd.DataFrame(),
        "TaiwanStockMarginPurchaseShortSale": raise_error(),
        "TaiwanStockDividendResult": dividend_global,
        "TaiwanStockCapitalReductionReferencePrice": capital_reduction,
        "TaiwanStockSplitPrice": lambda *_: pd.DataFrame(),
        "TaiwanStockParValueChange": lambda *_: pd.DataFrame(),
        "TaiwanStockDispositionSecuritiesPeriod": lambda sid, s, e: pd.DataFrame(
            {"date": ["2015-03-02", "2015-04-01"], "stock_id": ["2330", "6488"],
             "period_start": ["2015-03-03", "2015-04-02"], "period_end": ["2015-03-16", "2015-04-15"]}),
    }


def make(cfg, client, today="2016-01-01"):
    return Downloader(cfg, client, Store(cfg.raw_dir), Manifest(cfg.manifest_path),
                      today=date.fromisoformat(today))


def test_initial_run_builds_universe_and_downloads(cfg):
    client = FakeClient(handlers())
    dl = make(cfg, client)
    result = dl.run(["meta", "core", "events"])
    uni = dl.universe()
    assert set(uni["stock_id"]) == {"2330", "6488", "1234"}  # ETF、興櫃、特別股、太早下市都排除
    assert bool(uni.loc[uni.stock_id == "1234", "is_delisted"].iloc[0])

    store = Store(cfg.raw_dir)
    price = store.read(get_spec("TaiwanStockPrice"), "2330")
    assert price is not None and len(price) > 400

    m = dl.manifest
    # 融資融券連續 3 檔錯誤 → 自動停用
    assert m.disabled_reason("TaiwanStockMarginPurchaseShortSale")
    # 除權息可整批下載；減資不行 → 逐檔
    assert m.get_mode("TaiwanStockDividendResult") == "global"
    assert m.get_mode("TaiwanStockCapitalReductionReferencePrice") == "per_stock"
    div = store.read(get_spec("TaiwanStockDividendResult"), GLOBAL_KEY)
    assert set(div["stock_id"]) >= {"2330", "6488"}
    assert result["stats"]["done"] > 0


def test_rerun_initial_makes_no_new_requests(cfg):
    client = FakeClient(handlers())
    make(cfg, client).run(["meta", "core", "events"])
    before = client.calls
    make(cfg, client).run(["meta", "core", "events"])
    assert client.calls == before


def test_update_requests_only_recent_window(cfg):
    client = FakeClient(handlers())
    make(cfg, client, today="2015-12-01").run(["meta", "core"])
    client.requests.clear()
    make(cfg, client, today="2016-01-01").run(["meta", "core"], mode="update")
    price_reqs = [r for r in client.requests if r[0] == "TaiwanStockPrice" and r[1] == "2330"]
    assert price_reqs, "更新模式應該重抓 2330 的日 K"
    start = pd.Timestamp(price_reqs[-1][2])
    assert start == pd.Timestamp("2015-12-01") - pd.Timedelta(days=10)


def test_budget_stops_and_resumes(cfg):
    client = FakeClient(handlers())
    result = make(cfg, client).run(["meta", "core"], max_calls=8)
    assert result["stopped_reason"]
    assert result["calls"] <= 8
    make(cfg, client).run(["meta", "core"])
    store = Store(cfg.raw_dir)
    assert store.read(get_spec("TaiwanStockPrice"), "1234") is not None


def test_empty_global_probe_falls_back_to_per_stock(cfg):
    """整批試抓回空的（免費帳號可能不給整批但也不報錯）→ 改逐檔，不能讓整個事件資料集默默變空。"""
    client = FakeClient(handlers())
    dl = make(cfg, client)
    dl.run(["meta", "events"])
    assert dl.manifest.get_mode("TaiwanStockSplitPrice") == "per_stock"
    assert dl.manifest.get_mode("TaiwanStockDividendResult") == "global"
    split_reqs = [r for r in client.requests if r[0] == "TaiwanStockSplitPrice" and r[1]]
    assert {r[1] for r in split_reqs} == {"2330", "6488", "1234"}
