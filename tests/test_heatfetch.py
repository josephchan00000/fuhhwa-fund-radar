"""景氣溫度頁的資料抓取：用 CI 探針實際拿到的格式當樣本（docs/lab_heat_plan.md 第 10 節），不打網路。"""
import io
import json
import zipfile

import pytest

from arm.lab import heatdata as HD
from arm.lab import heatfetch as F
from arm.lab import store


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LAB", tmp_path)
    return tmp_path


def test_finmind_margin_inst_futures_options_mtx(lab, monkeypatch):
    rows = {
        ("TaiwanStockTotalMarginPurchaseShortSale", ""): [
            {"TodayBalance": 12486038, "date": "2001-01-03", "name": "MarginPurchase"},
            {"TodayBalance": 189485743000, "date": "2001-01-03", "name": "MarginPurchaseMoney"},
            {"TodayBalance": 528495, "date": "2001-01-03", "name": "ShortSale"}],
        ("TaiwanStockTotalInstitutionalInvestors", ""): [
            {"buy": 19406793770, "date": "2004-04-07", "name": "total", "sell": 14768680195},
            {"buy": 1833097110, "date": "2004-04-07", "name": "Investment_Trust", "sell": 3016452186}],
        ("TaiwanFuturesInstitutionalInvestors", "TX"): [
            {"date": "2026-10-16", "institutional_investors": "外資", "long_open_interest_balance_volume": 9812,
             "short_open_interest_balance_volume": 103487}],
        ("TaiwanFuturesInstitutionalInvestors", "MTX"): [],
        ("TaiwanFuturesInstitutionalInvestors", "TMF"): [],
        ("TaiwanOptionInstitutionalInvestors", "TXO"): [
            {"date": "2026-10-16", "call_put": "賣權", "institutional_investors": "外資",
             "long_open_interest_balance_amount": 838170, "short_open_interest_balance_amount": 709347}],
        ("TaiwanFuturesDaily", "MTX"): [
            {"date": "2018-01-02", "contract_date": "201801W1", "open_interest": 284, "trading_session": "position"},
            {"date": "2018-01-02", "contract_date": "201801W1", "open_interest": 0, "trading_session": "after_market"},
            {"date": "2018-01-02", "contract_date": "201801", "open_interest": 34871, "trading_session": "position"},
            {"date": "2018-01-02", "contract_date": "201802/201803", "open_interest": 5, "trading_session": "position"}],
    }
    monkeypatch.setattr(F, "_finmind", lambda ds, did, a, z=None: rows[(ds, did)])
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    assert F.fm_margin("2001-01-01") == 1
    assert HD.load("margin") == {"2001-01-03": [189485743000, 12486038, 528495]}
    assert F.fm_inst("2004-01-01") == 1
    assert HD.load("inst")["2004-04-07"] == {"total": 4638113575, "Investment_Trust": -1183355076}
    assert F.fm_futi("2018-01-01") == 1 and HD.load("futi")["2026-10-16"] == {"TX": {"外資": [9812, 103487]}}
    assert F.fm_opti("2018-01-01") == 1 and HD.load("opti")["2026-10-16"] == {"賣權": {"外資": [838170, 709347]}}
    assert F.fm_mtxoi("2005-01-01") == 1 and HD.load("mtxoi") == {"2018-01-02": 35155}   # 不含盤後、不含價差
    assert F.fm_margin("2001-01-01") == 0                                                 # 同樣的資料不改檔


def test_taifex_pcr_and_vix(lab, monkeypatch):
    csv = ("日期,賣權成交量,買權成交量,買賣權成交量比率%,賣權未平倉量,買權未平倉量,買賣權未平倉量比率%\n"
           "2015/01/30,278957,262655,106.21,537451,481923,111.52,\n").encode("cp950")
    monkeypatch.setattr(F, "post_bytes", lambda url, form, **kw: csv)
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    from datetime import date
    assert F.taifex_pcr(date(2015, 1, 1), date(2015, 1, 31)) == 1
    assert HD.load("pcr") == {"2015-01-30": [278957.0, 262655.0, 106.21, 537451.0, 481923.0, 111.52]}
    txt = ("交易日期\t時間(時/分/秒/毫秒)\t臺指選擇權波動率指數\t收盤前1分鐘平均指數\n--------\t---\n"
           "20260901\t13450000\t\t\t24.91\t\t24.92\n20260930\t13450000\t\t\t23.04\t\t23.04\n").encode("cp950")
    page404 = b"<HTML  xmlns='http://www.w3.org/1999/xhtml'><title>404</title></HTML>"
    monkeypatch.setattr(F, "_get", lambda url, **kw: txt if "202609" in url else page404)
    monkeypatch.setattr(F, "date", type("D", (), {"today": staticmethod(lambda: date(2026, 10, 17))}))
    assert F.taifex_vix(2) == 2
    assert HD.load("vixtw") == {"2026-09-01": 24.91, "2026-09-30": 23.04}


def test_ndc_pmi_orders_usdtwd(lab, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("景氣指標與燈號.csv", "﻿\"Date\",\"領先指標綜合指數\",\"領先指標不含趨勢指數\",\"同時指標綜合指數\","
                   "\"同時指標不含趨勢指數\",\"落後指標綜合指數\",\"落後指標不含趨勢指數\",\"景氣對策信號綜合分數\",\"景氣對策信號\"\n"
                   "198201,12.28,100.34,13.11,107.10,13.08,106.92,-,-\n"
                   "202608,140.58,104.40,143.36,106.47,142.33,105.70,41,紅\n")
    pmi = "Date,PMI,NMI\n201207,47.1,-\n202609,63.4,56.9\n".encode()
    orders = ("統計項目,地區代碼,地區別,資料期(民國年),統計值(金額),計量單位\n"
              "外銷訂單金額_美元,00,地區別總計,07301,2627,百萬美元\n"
              "外銷訂單金額_美元,18,其他地區,11507,8482,百萬美元\n").encode()
    fx = json.dumps([{"日期": "20080102", "NTD_USD": "32.443"}, {"日期": "20261016", "NTD_USD": "32.428"}]).encode()

    def fake(url, **kw):
        if "Download.ashx" in url and "zip" in url:
            return buf.getvalue()
        if "Download.ashx" in url:
            return pmi
        if "moea" in url:
            return orders
        return fx
    monkeypatch.setattr(F, "_get", fake)
    assert F.ndc() == 2
    assert HD.load("ndc")["2026-08"] == [140.58, 104.40, 143.36, 106.47, 142.33, 105.70, 41.0, "紅"]
    assert HD.load("ndc")["1982-01"][6] is None
    assert HD.load("ndc_first")["2026-08"] == [None, "回補"]                # 第一次抓不算「第一次公布」
    assert F.ndc_pmi() == 2 and HD.load("pmi") == {"2012-07": 47.1, "2026-09": 63.4}
    assert F.moea_orders() == 1 and HD.load("orders") == {"1984-01": 2627.0}   # 只取地區別總計
    assert F.cbc_usdtwd() == 2 and HD.load("usdtwd")["2026-10-16"] == 32.428
