"""大跌風險研究的資料抓取（arm/lab/crashfetch.py）：解析函式不碰網路。"""
from __future__ import annotations

from arm.lab import crashfetch as CF


def test_parse_cbc_cube_stock_table_two_level():
    n1 = ["上市股票-公司家數", "上市股票-總面額", "上市股票-總市值", "上市股票-總成交值", "上市股票-日平均成交值", "加權平均股價指數"]
    n2 = ["原始值", "年增率"]
    rows = [["2026M08", "1085", "3.629", "7930012", "1.662", "150789163", "93.073", "18545407", "110.410", "883115",
             "110.410", "45124.96", "87.670"],
            ["1987M05", "130", "-", "242530", "-", "985607", "-", "203081", "-", "-", "-", "1814.28", "-"],
            ["說明", "x"]]
    out = CF.parse_cbc_cube(n1, n2, rows, CF.CBC_STOCK[1])
    assert out["2026-08"] == [1085.0, 7930012.0, 150789163.0, 18545407.0, 883115.0, 45124.96]
    assert out["1987-05"] == [130.0, 242530.0, 985607.0, 203081.0, None, 1814.28]
    assert set(out) == {"1987-05", "2026-08"}


def test_parse_cbc_cube_margin_table_three_level():
    """EG25M01：融資／融券 × 新增／償還／餘額六欄 × [原始值, 年增率]（2026-10-19 CI 探針看到的列）。"""
    n1 = ["融資", "融券"]
    n2 = ["新增-股數", "新增-金額", "償還-股數", "償還-金額", "餘額-股數", "餘額-金額"]
    r = ["2026M08", "9417", "9.02", "877600", "88.28", "9245", "12.22", "792190", "88.22", "11385", "23.29", "758931",
         "110.55", "748", "-4.47", "108402", "1", "700", "2", "100000", "3", "1079", "4", "120000", "5"]
    out = CF.parse_cbc_cube(n1, n2, [r], CF.CBC_MARGIN[1])
    assert out["2026-08"] == [758931.0, 11385.0, 1079.0, 120000.0]
    assert CF.parse_cbc_cube(n1, n2, [r], (("融資", "不存在"),)) == {}      # 找不到的格是 None，整列沒有值就不收


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
