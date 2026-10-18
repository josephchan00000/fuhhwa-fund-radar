"""大跌風險研究的資料抓取（arm/lab/crashfetch.py）：解析函式不碰網路。"""
from __future__ import annotations

from arm.lab import crashfetch as CF


def test_parse_cbc_cols_takes_raw_column_of_each_item():
    names = ["上市股票-公司家數", "上市股票-總面額", "上市股票-總市值", "上市股票-總成交值", "上市股票-日平均成交值",
             "加權平均股價指數"]
    rows = [["1987M05", "130", "1.0", "2", "3.0", "4", "5", "6", "7", "8", "9", "1,020.5", "11"],
            ["2026M08", "1100", "", "", "", "800,000", "", "", "", "", "", "", ""],
            ["說明", "x"]]
    out = CF.parse_cbc_cols(names, 2, rows, CF.CBC_STOCK[1])
    assert out["1987-05"] == [130.0, 2.0, 4.0, 6.0, 8.0, 1020.5]
    assert out["2026-08"] == [1100.0, None, 800000.0, None, None, None]
    assert set(out) == {"1987-05", "2026-08"}


def test_parse_cbc_cols_missing_name_is_none_and_suffix_match():
    names = ["證券市場-融資", "證券市場-融券"]
    out = CF.parse_cbc_cols(names, 1, [["2001M01", "5", "6"]], ("融資", "融券", "不存在"))
    assert out == {"2001-01": [5.0, 6.0, None]}


def test_parse_yahoo_volume_skips_zero_weekend_and_open_day():
    day = 86400
    t0 = 1700438400                                          # 2023-11-20（週一）00:00 UTC
    doc = {"chart": {"result": [{
        "meta": {"gmtoffset": -18000, "currentTradingPeriod": {"regular": {"start": t0 + 4 * day + 14.5 * 3600,
                                                                            "end": t0 + 4 * day + 21 * 3600}}},
        "timestamp": [t0 + 14.5 * 3600 + k * day for k in range(7)],
        "indicators": {"quote": [{"volume": [100, 0, 300, None, 500, 600, 700]}]}}]}}
    now = t0 + 4 * day + 15 * 3600                          # 週五盤中
    out = CF.parse_yahoo_volume(doc, now)
    assert out == {"2023-11-20": 100.0, "2023-11-22": 300.0}


def test_crash_probe_and_jobs_are_wired():
    src = open("scripts/fetch_heat.py", encoding="utf-8").read()
    for k in ("twcap", "twmgn", "usvol"):
        assert f'("{k}"' in src
    assert 'monthly("twcap", CF.cbc_stock)' in src and 'monthly("twmgn", CF.cbc_margin)' in src
    us = open("scripts/fetch_heat_us.py", encoding="utf-8").read()
    assert "CF.yahoo_volume" in us and "us_vol_" in us
