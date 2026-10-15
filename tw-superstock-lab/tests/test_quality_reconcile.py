from __future__ import annotations

import pandas as pd

from superstock.quality import Check, check_jumps, check_price_integrity, write_report
from superstock.reconcile import parse_twse_stock_day, roc_to_date


def test_jump_detection_skips_ipo_days_and_flags_missing_event():
    dates = pd.bdate_range("2020-01-01", periods=10)
    ret = [None, 0.5, 0.01, 0.0, 0.0, 0.0, -0.45, 0.0, 0.0, 0.0]  # 第 2 天在新股豁免期；第 7 天異常
    prices = pd.DataFrame({"stock_id": "9999", "date": dates, "ret": ret, "close": 10.0,
                           "high": 11.0, "low": 9.0, "volume": 1})
    c = check_jumps(prices)
    assert c.metrics["count"] == 1 and c.examples[0]["date"] == str(dates[6].date())
    assert c.status in ("WARN", "FAIL")


def test_integrity_flags_duplicates():
    df = pd.DataFrame({"stock_id": ["1", "1"], "date": pd.to_datetime(["2020-01-02"] * 2),
                       "high": [10.0, 10.0], "low": [9.0, 9.0], "close": [9.5, 9.5], "volume": [1, 1]})
    assert check_price_integrity(df).status == "FAIL"


def test_report_written(tmp_path):
    path = write_report([Check("C1", "測試", "WARN", "摘要")], tmp_path, generated_at="2026-10-15 20:00")
    text = path.read_text(encoding="utf-8")
    assert "有條件通過" in text and (tmp_path / "data_quality.json").exists()


def test_parse_twse_stock_day():
    payload = {"stat": "OK", "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價",
                                        "漲跌價差", "成交筆數"],
               "data": [["113/01/02", "26,059,058", "15,445,580,876", "590.00", "593.00", "589.00",
                         "593.00", "+0.00", "19,862"]]}
    df = parse_twse_stock_day(payload)
    assert df.loc[0, "date"] == pd.Timestamp("2024-01-02")
    assert df.loc[0, "close"] == 593.0 and df.loc[0, "volume"] == 26059058
    assert roc_to_date("104/06/01") == pd.Timestamp("2015-06-01")
