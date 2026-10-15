from __future__ import annotations

import numpy as np
import pandas as pd

from superstock.listing import (compare_official, iso_date, main_board_start, match_series, parse_official, trim)


def emerging_then_listed(n_em=40, n_main=60, quiet_run=0, seed=0):
    """興櫃 n_em 筆（價差對「前日均價」→ 多半對不上）→ 掛牌日爆量 → 主板 n_main 筆（價差對前一日收盤）。"""
    rng = np.random.default_rng(seed)
    rows, prev = [], 50.0
    for i in range(n_em):
        if i < quiet_run:                     # 冷門興櫃：價格不動、價差 0（剛好「符合」）
            close, spread, vol = prev, 0.0, 1_000
        else:
            close = round(prev * (1 + rng.normal(0, 0.03)), 2)
            spread, vol = round(close - prev * 1.01, 2), 10_000
        rows.append((close, spread, vol))
        prev = close
    close = round(prev * 1.05, 2)
    rows.append((close, round(close - 48.0, 2), 500_000))      # 掛牌日：價差對承銷價
    prev = close
    for _ in range(n_main):
        close = round(prev * (1 + rng.normal(0, 0.02)), 2)
        rows.append((close, round(close - prev, 2), 100_000))
        prev = close
    dates = pd.bdate_range("2014-01-02", periods=len(rows))
    df = pd.DataFrame(rows, columns=["close", "spread", "volume"])
    df["date"] = dates
    return df


def test_match_series_main_board_vs_emerging():
    df = emerging_then_listed()
    m = match_series(df["close"], df["spread"])
    assert np.nanmean(m[41:]) == 1.0 and np.nanmean(m[1:40]) < 0.2


def test_detects_listing_day():
    df = emerging_then_listed()
    got = main_board_start(df["date"], df["close"], df["spread"], df["volume"])
    assert got == df["date"].iloc[40]


def test_main_board_history_has_no_cut():
    df = emerging_then_listed().iloc[41:].reset_index(drop=True)
    assert main_board_start(df["date"], df["close"], df["spread"], df["volume"]) is None


def test_quiet_emerging_run_does_not_trigger_early():
    # 興櫃前 25 筆價格不動（符合率 100%）但沒有爆量 → 不能誤判成掛牌
    df = emerging_then_listed(n_em=60, quiet_run=0)
    df.loc[10:34, "spread"] = 0.0
    df.loc[10:34, "close"] = df.loc[9, "close"]
    df.loc[10:34, "volume"] = 1_000
    df.loc[35, "spread"] = 1.5                # 第 35 筆恢復成興櫃的對不上
    got = main_board_start(df["date"], df["close"], df["spread"], df["volume"])
    assert got == df["date"].iloc[60]


def main_then_emerging(n_main=60, n_em=30, seed=1):
    """主板 n_main 筆 → 下市後轉興櫃 n_em 筆（價差改對均價）。"""
    rng = np.random.default_rng(seed)
    rows, prev = [], 80.0
    for _ in range(n_main):
        close = round(prev * (1 + rng.normal(0, 0.02)), 2)
        rows.append((close, round(close - prev, 2), 50_000))
        prev = close
    for _ in range(n_em):
        close = round(prev * (1 + rng.normal(0, 0.04)), 2)
        rows.append((close, round(close - prev * 0.98, 2), 3_000))
        prev = close
    df = pd.DataFrame(rows, columns=["close", "spread", "volume"])
    df["date"] = pd.bdate_range("2016-01-04", periods=len(rows))
    return df


def test_trim_drops_pre_listing_and_post_delisting():
    a = emerging_then_listed().assign(stock_id="7000")
    b = main_then_emerging().assign(stock_id="2000")
    # 股票池的下市日（例如清單停更日）只記錄、不拿來切：真的切點由資料判斷
    uni = pd.DataFrame({"stock_id": ["7000", "2000"], "is_delisted": [True, True],
                        "delist_date": [a["date"].iloc[60], b["date"].iloc[20]]})
    kept, info = trim(pd.concat([a, b]), uni)
    info = info.set_index("stock_id")
    assert info.loc["7000", "dropped_pre"] == 40 and info.loc["7000", "main_start"] == a["date"].iloc[40]
    assert info.loc["7000", "dropped_post"] == 0 and pd.isna(info.loc["7000", "main_end"])
    assert info.loc["2000", "main_end"] == b["date"].iloc[59] and info.loc["2000", "dropped_post"] == 30
    assert pd.isna(info.loc["2000", "main_start"]) and info.loc["2000", "head_match"] == 1.0
    assert kept[kept.stock_id == "7000"]["date"].min() == a["date"].iloc[40]
    assert kept[kept.stock_id == "2000"]["date"].max() == b["date"].iloc[59]


def test_official_parse_and_compare():
    assert iso_date("1040925") == "2015-09-25" and iso_date("20150925") == "2015-09-25"
    assert iso_date("114/11/27") == "2025-11-27" and iso_date("") is None
    twse = [{"公司代號": "7000", "上市日期": "20140228"}, {"公司代號": "2059", "上市日期": "0970625"}]
    tpex = [{"SecuritiesCompanyCode": "6488", "DateOfListing": "1040925"}]
    off = pd.concat([parse_official(twse, "twse"), parse_official(tpex, "tpex")])
    assert set(off.stock_id) == {"7000", "2059", "6488"}
    a = emerging_then_listed().assign(stock_id="7000")
    official = pd.DataFrame({"stock_id": ["7000"], "listing_date": [a["date"].iloc[40]], "market": ["twse"]})
    _, info = trim(a, None)
    cmp = compare_official(info, official, a["date"])
    assert cmp["compared"] == 1 and cmp["within_1_day"] == 1 and cmp["missed"] == 0


def test_false_switch_inside_emerging_period_is_skipped():
    """3661 世芯型：興櫃中段一段價格不動、某天又爆量 → 看起來像轉換點；要取最後一個（真正的掛牌日）。"""
    df = emerging_then_listed(n_em=80, seed=3)
    df.loc[30:52, "spread"] = 0.0
    df.loc[30:52, "close"] = df.loc[29, "close"]
    df.loc[29, "volume"] = 200_000                  # 假轉換點：爆量、之後 20 筆都「符合」
    df.loc[53, "spread"] = 2.0
    got = main_board_start(df["date"], df["close"], df["spread"], df["volume"])
    assert got == df["date"].iloc[80]


def test_no_trade_rows_before_listing_are_not_evidence():
    """6901 型：興櫃最後幾天沒成交（價格沿用、價差 0、量 0）→ 不能把最後一個興櫃日當掛牌日。"""
    df = emerging_then_listed(n_em=50, seed=5)
    df.loc[46, "volume"] = 300_000               # 最後一個有成交的興櫃日也爆量
    for k in (47, 48, 49):
        df.loc[k, ["close", "spread", "volume"]] = [df.loc[46, "close"], 0.0, 0]
    got = main_board_start(df["date"], df["close"], df["spread"], df["volume"])
    assert got == df["date"].iloc[50]
