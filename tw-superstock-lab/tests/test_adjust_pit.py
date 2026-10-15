from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from superstock.adjust import apply_adjustment, build_events, flag_limits
from superstock.pit import financial_available_date, revenue_available_date
from superstock.universe import build_universe
from superstock.config import UniverseConfig


def prices_frame(stock_id, closes, start="2020-07-01"):
    dates = pd.bdate_range(start, periods=len(closes))
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"stock_id": stock_id, "date": dates, "open": c, "high": c, "low": c, "close": c})


def test_cash_dividend_removes_fake_gap():
    p = prices_frame("2330", [100, 100, 95, 96])  # 第 3 天除息 5 元
    ev = build_events({"TaiwanStockDividendResult": pd.DataFrame(
        {"stock_id": ["2330"], "date": [p.date[2].strftime("%Y-%m-%d")],
         "before_price": [100.0], "after_price": [95.0]})})
    out = apply_adjustment(p, ev)
    assert out["adj_close"].tolist()[:2] == pytest.approx([95.0, 95.0])
    assert out["adj_close"].tolist()[2:] == pytest.approx([95.0, 96.0])
    assert out["ret"].iloc[2] == pytest.approx(0.0)  # 除息日沒有假下跌


def test_capital_reduction_and_multiple_events():
    p = prices_frame("1234", [10, 10, 20, 20, 19])
    ev = build_events({
        "TaiwanStockCapitalReductionReferencePrice": pd.DataFrame(
            {"stock_id": ["1234"], "date": [p.date[2].strftime("%Y-%m-%d")],
             "ClosingPriceonTheLastTradingDay": [10.0], "PostReductionReferencePrice": [20.0]}),
        "TaiwanStockDividendResult": pd.DataFrame(
            {"stock_id": ["1234"], "date": [p.date[4].strftime("%Y-%m-%d")],
             "before_price": [20.0], "after_price": [19.0]}),
    })
    out = apply_adjustment(p, ev)
    # 減資：之前價格 ×2；除息：之前價格 ×0.95
    assert out["adj_factor"].tolist() == pytest.approx([1.9, 1.9, 0.95, 0.95, 1.0])
    assert out["ret"].iloc[2] == pytest.approx(0.0)
    assert out["ret"].iloc[4] == pytest.approx(0.0)


def test_events_reject_bad_rows():
    ev = build_events({"TaiwanStockDividendResult": pd.DataFrame(
        {"stock_id": ["1", "2"], "date": ["2020-01-02", "2020-01-02"],
         "before_price": [0.0, 100.0], "after_price": [10.0, 99.0]})})
    assert ev["stock_id"].tolist() == ["2"]


def test_locked_limit_flags_respect_2015_rule():
    pre = prices_frame("A", [100, 107, 107], start="2015-05-25")       # 舊制 7%
    post = prices_frame("B", [100, 110, 110], start="2015-06-02")      # 新制 10%
    out = flag_limits(apply_adjustment(pd.concat([pre, post]), pd.DataFrame(
        columns=["stock_id", "date", "factor", "source"])))
    a = out[out.stock_id == "A"].reset_index(drop=True)
    b = out[out.stock_id == "B"].reset_index(drop=True)
    assert bool(a.locked_up[1]) and not bool(a.locked_up[2])
    assert bool(b.locked_up[1]) and not bool(b.locked_up[2])


@pytest.mark.parametrize("y,m,expected", [(2023, 12, "2024-01-10"), (2024, 1, "2024-02-10")])
def test_revenue_available(y, m, expected):
    assert revenue_available_date(y, m) == pd.Timestamp(expected)


@pytest.mark.parametrize("period,expected", [
    ("2024-03-31", "2024-05-15"), ("2024-06-30", "2024-08-14"), ("2024-09-30", "2024-11-14"),
    ("2023-12-31", "2024-03-31"), ("2011-06-30", "2011-08-31"), ("2012-12-31", "2013-04-30"),
])
def test_financial_available(period, expected):
    assert financial_available_date(pd.Timestamp(period)) == pd.Timestamp(expected)


def test_universe_handles_reused_code_and_cutoff():
    info = pd.DataFrame({"stock_id": ["2330", "1234"], "stock_name": ["a", "b"], "type": ["twse", "tpex"],
                         "industry_category": ["半導體業", "其他"]})
    delisting = pd.DataFrame({"date": ["2012-01-01", "2016-01-01", "2001-01-01"],
                              "stock_id": ["1234", "5555", "6666"], "stock_name": ["b", "c", "d"]})
    uni = build_universe(info, delisting, UniverseConfig(), "2008-01-01")
    assert set(uni.stock_id) == {"2330", "1234", "5555"}
    assert not bool(uni.loc[uni.stock_id == "1234", "is_delisted"].iloc[0])  # 仍掛牌（代號重用）
    assert bool(uni.loc[uni.stock_id == "5555", "is_delisted"].iloc[0])
