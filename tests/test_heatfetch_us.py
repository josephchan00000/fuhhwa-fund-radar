"""景氣溫度・美股版的資料解析（arm/lab/heatfetch_us.py）：用 CI 探針看到的格式測，不碰網路。"""
from datetime import datetime, timezone

from arm.lab import heatfetch_us as U


def _ts(d: str, hh: int = 13, mm: int = 30) -> int:
    """美東 09:30（UTC 13:30／14:30）那根日線的時間戳。"""
    return int(datetime.fromisoformat(d).replace(hour=hh, minute=mm, tzinfo=timezone.utc).timestamp())


def _yahoo(days: list[str], closes: list, reg: tuple[int, int] | None, adj: list | None = None) -> dict:
    meta = {"gmtoffset": -14400}
    if reg:
        meta["currentTradingPeriod"] = {"regular": {"start": reg[0], "end": reg[1]}}
    ind = {"quote": [{"close": closes}]}
    if adj is not None:
        ind["adjclose"] = [{"adjclose": adj}]
    return {"chart": {"result": [{"meta": meta, "timestamp": [_ts(d) for d in days], "indicators": ind}]}}


def test_yahoo_drops_bar_while_session_open_and_weekends():
    days = ["2026-10-15", "2026-10-16", "2026-10-17", "2026-10-19"]   # 10-17 是星期六
    start, end = _ts("2026-10-19", 13, 30), _ts("2026-10-19", 20, 0)
    doc = _yahoo(days, [100.0, 101.0, 102.0, 103.0], (start, end))
    during = U.parse_yahoo(doc, now=start + 3600)                      # 10-19 盤中
    assert during == {"2026-10-15": 100.0, "2026-10-16": 101.0}
    after = U.parse_yahoo(doc, now=end + U.CLOSE_MARGIN_S + 60)          # 收盤後 15 分鐘以後才收
    assert after == {"2026-10-15": 100.0, "2026-10-16": 101.0, "2026-10-19": 103.0}
    assert U.parse_yahoo(doc, now=end + 60) == during                   # 剛收盤 1 分鐘：還不收
    adj = U.parse_yahoo(_yahoo(days, [1, 2, 3, 4], None, adj=[1.5, None, 3.5, 4.5]), now=end + 10 ** 6, adj=True)
    assert adj == {"2026-10-15": 1.5, "2026-10-19": 4.5}


def test_month_key_and_combine():
    assert U.month_key("1959-01-31") == "1959-01" and U.month_key("2026-08") == "2026-08"
    assert U.month_key("1947-Q1") == "1947-03" and U.month_key("2026-Q4") == "2026-12" and U.month_key("x") is None
    c = U.combine([{"2026-01-31": 1.0, "2026-02-28": 2.0}, {"2026-02-28": 5.0}], U.month_key)
    assert c == {"2026-01": [1.0, None], "2026-02": [2.0, 5.0]}


def test_cftc_rows():
    rows = [{"report_date_as_yyyy_mm_dd": "2026-10-13T00:00:00.000", "open_interest_all": "2000000",
             "asset_mgr_positions_long": "900000", "asset_mgr_positions_short": "100,000"},
            {"report_date_as_yyyy_mm_dd": "2026-10-06T00:00:00.000", "open_interest_all": "0",
             "asset_mgr_positions_long": "1", "asset_mgr_positions_short": "1"}]
    assert U.parse_cftc(rows, "asset_mgr_positions_long", "asset_mgr_positions_short") == {
        "2026-10-13": [900000.0, 100000.0, 2000000.0]}                  # 未平倉 0 的列不收


def test_philly_umich_ebp_oecd():
    ph = "DATE,GAC,NOC\nMay-68,32.2,30.6\nOct-26,20.9,4.3\nDec-99,1.0,2\n"
    assert U.parse_philly(ph) == {"1968-05": 32.2, "2026-10": 20.9, "1999-12": 1.0}
    um = "Month,YYYY,ICS_ALL\nNovember,1952,86.2\nSeptember,2026,48.1\n"
    assert U.parse_umich(um) == {"1952-11": 86.2, "2026-09": 48.1}
    eb = "date,gz_spread,ebp,est_prob\n1973-01-01,1.13,-0.0476,0.18\n2026-09-01,0.926,-0.392,0.09\n"
    assert U.parse_ebp(eb) == {"1973-01": [1.13, -0.0476], "2026-09": [0.926, -0.392]}
    oe = "STRUCTURE,TIME_PERIOD,OBS_VALUE\nDATAFLOW,1955-01,101.4682\nDATAFLOW,2026-09,100.9993\n"
    assert U.parse_oecd(oe) == {"1955-01": 101.4682, "2026-09": 100.9993}


def test_ar539_sums_states_by_week():
    txt = ("st,rptdate,c1,c2,c3,c4\nAK,1986-02-15,6,1986-02-08,2048,8\nAL,1986-02-15,6,1986-02-08,10000,1\n"
           "WY,2026-10-10,40,2026-10-03,391,1\n")
    assert U.parse_ar539(txt) == {"1986-02-15": 12048.0, "2026-10-10": 391.0}


def test_ads_rows():
    rows = [["Date", "ADS_Index", "RECBARS"], ["1960:03:01", -0.5817, 0], ["2026:10:10", 0.1218, 0],
            [datetime(2026, 10, 11), 0.12, 0], ["x", 1, 0]]
    assert U.parse_ads(rows) == {"1960-03-01": -0.5817, "2026-10-10": 0.1218, "2026-10-11": 0.12}


def test_bls_three_series():
    doc = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [
        {"seriesID": "LNS14000000", "data": [{"year": "2026", "period": "M09", "value": "4.2"},
                                             {"year": "2026", "period": "M13", "value": "9"}]},
        {"seriesID": "CUUR0000SA0", "data": [{"year": "2026", "period": "M09", "value": "336.940"}]},
        {"seriesID": "CUUR0000SA0L1E", "data": [{"year": "2026", "period": "M08", "value": "339.287"}]}]}}
    assert U.parse_bls(doc) == {"2026-09": [4.2, 336.94, None], "2026-08": [None, None, 339.287]}


def test_shiller_dates_and_rows():
    assert U.shiller_month(1871.01) == "1871-01" and U.shiller_month(2025.1) == "2025-10"
    assert U.shiller_month(2025.12) == "2025-12" and U.shiller_month("") is None
    rows = [["Date", "P", "D", "E", "CPI", "Fraction", "Rate GS10"],
            [1871.01, 4.44, 0.26, 0.4, 12.46, 1871.04, 5.32],
            [2026.07, 7481.34, "", "", 333.918, 2026.54, 4.6],
            ["", "Oct price is Oct 2nd close", "", "", "", "", ""]]
    assert U.parse_shiller(rows) == {"1871-01": [4.44, 0.26, 0.4, 12.46, 5.32], "2026-07": [7481.34, None, None, 333.918, 4.6]}


def test_wsts_worldwide_rows():
    rows = [["36 Years WSTS Blue Book Data", None], [None, "January", "February"], [1986] + [None] * 13,
            ["Americas", 555850, 633465] + [None] * 11, ["Worldwide", 1645914, 1901342, 2206315] + [None] * 11,
            [2026] + [None] * 13, ["Worldwide", 83041428, 104007524] + [None] * 10 + [1043024817, 305711694, 416289471]]   # 第 14 欄起是合計
    out = U.parse_wsts(rows)
    assert out["1986-01"] == 1645914 and out["1986-03"] == 2206315 and out["2026-02"] == 104007524
    assert "1986-04" not in out and "2026-12" not in out


def test_fmtqik_and_dgbas_gdp():
    doc = {"data": [[" 79/01/04", "1,134,514,582", "121,774,345,167", "351,190", "9,853.15", "0.00"],
                    [" 87/12/31", "1", "2", "3", "6,418.43", "1"]]}
    assert U.parse_fmtqik(doc) == {"1990-01-04": 9853.15, "1998-12-31": 6418.43}
    xml = ("<Obs><Item>國內生產毛額_當期價格(新臺幣百萬元)、GDP</Item><TIME_PERIOD>2026Q2</TIME_PERIOD><TYPE>原始值</TYPE>"
           "<Item_VALUE>8040214</Item_VALUE></Obs>"
           "<Obs><Item>國內生產毛額_當期價格(新臺幣百萬元)、GDP</Item><TIME_PERIOD>2026Q2</TIME_PERIOD><TYPE>年增率(%)</TYPE>"
           "<Item_VALUE>5.1</Item_VALUE></Obs>"
           "<Obs><Item>國內生產毛額_當期價格(新臺幣百萬元)、C.製造業</Item><TIME_PERIOD>2026Q2</TIME_PERIOD><TYPE>原始值</TYPE>"
           "<Item_VALUE>1</Item_VALUE></Obs>")
    assert U.parse_dgbas_gdp(xml) == {"2026-06": 8040214.0}


def test_latest_us_close_day():
    assert U.latest_us_close_day(datetime(2026, 10, 18, 4, tzinfo=timezone.utc)) == "2026-10-16"     # 週日
    assert U.latest_us_close_day(datetime(2026, 10, 19, 20, tzinfo=timezone.utc)) == "2026-10-16"    # 週一盤中
    assert U.latest_us_close_day(datetime(2026, 10, 19, 22, tzinfo=timezone.utc)) == "2026-10-19"    # 週一收盤後
