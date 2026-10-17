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
        # 第三版 B5：同時指標構成項目的海關出口值（CI 探針實際拿到的表頭與資料列）
        z.writestr("同時指標構成項目.csv", "﻿\"Date\",\"工業生產指數(Index2021=100)\",\"電力(企業)總用電量(十億度)\","
                   "\"製造業銷售量指數(Index2021=100)\",\"批發、零售及餐飲業營業額(十億元)\",\"工業及服務業加班工時(小時)\","
                   "\"海關出口值(十億元)\",\"機械及電機設備進口值(十億元)\"\n"
                   "198201,,2.22,12.32,,9.9,65.56,\n"
                   "202607,143.32,15.87,126.08,2266.591161,8.9,2409.368,1240.669\n"
                   "202608,145.97,,,2361.956097,,2655.817,1266.488\n"
                   "202609,,,,,,,\n")
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
    assert HD.load("exports") == {"1982-01": 65.56, "2026-07": 2409.368, "2026-08": 2655.817}   # 空白月份不收
    assert F.ndc_pmi() == 2 and HD.load("pmi") == {"2012-07": 47.1, "2026-09": 63.4}
    assert F.moea_orders() == 1 and HD.load("orders") == {"1984-01": 2627.0}   # 只取地區別總計
    assert F.cbc_usdtwd() == 2 and HD.load("usdtwd")["2026-10-16"] == 32.428


def test_cbc_money_finds_m1b_m2_by_name(lab, monkeypatch):
    names = ["貨幣機構以外各部門持有通貨"] + [f"項目{i}" for i in range(11)] + ["貨幣總計數 -Ｍ１Ａ", "貨幣總計數 -Ｍ１Ｂ", "貨幣總計數 -Ｍ２"]
    row = ["2026M08"] + ["1", "-"] * 12 + ["12827146", "8.86", "30750789", "6.65", "70677981", "6.79"]
    old = ["1987M05"] + ["1", "-"] * 12 + ["724916", "-", "1255199", "-", "3432119", "-"]
    doc = {"meta": {}, "data": {"structure": {"Table1": [{"data": n} for n in names],
                                              "Table2": [{"data": "原始值"}, {"data": "年增率"}]},
                                "dataSets": [old, row]}}
    monkeypatch.setattr(F, "_get", lambda url, **kw: json.dumps(doc).encode())
    assert F.cbc_money() == 2
    assert HD.load("money") == {"1987-05": [1255199.0, None, 3432119.0, None],
                                "2026-08": [30750789.0, 6.65, 70677981.0, 6.79]}


def test_dgbas_cpi_xml_takes_headline_index_and_yoy():
    xml = ("<root><Obs><Item>總指數(指數基期：民國110年=100)</Item><TIME_PERIOD>1981M01</TIME_PERIOD><FREQ>M</FREQ>"
           "<TYPE>原始值</TYPE><Item_VALUE>52.95</Item_VALUE></Obs>"
           "<Obs><Item>總指數(指數基期：民國110年=100)</Item><TIME_PERIOD>2026M09</TIME_PERIOD><FREQ>M</FREQ>"
           "<TYPE>年增率(%)</TYPE><Item_VALUE>2.31</Item_VALUE></Obs>"
           "<Obs><Item>總指數(指數基期：民國110年=100)</Item><TIME_PERIOD>2026M09</TIME_PERIOD><FREQ>M</FREQ>"
           "<TYPE>原始值</TYPE><Item_VALUE>110.5</Item_VALUE></Obs>"
           "<Obs><Item>總指數不含蔬菜水果</Item><TIME_PERIOD>2026M09</TIME_PERIOD><FREQ>M</FREQ>"
           "<TYPE>年增率(%)</TYPE><Item_VALUE>9.9</Item_VALUE></Obs>"
           "<Obs><Item>食物類</Item><TIME_PERIOD>2026M09</TIME_PERIOD><FREQ>M</FREQ>"
           "<TYPE>年增率(%)</TYPE><Item_VALUE>8.8</Item_VALUE></Obs></root>")
    assert F.parse_dgbas_cpi(xml) == {"1981-01": [52.95, None], "2026-09": [110.5, 2.31]}


def test_treasury_csv_columns_by_header():
    t1990 = ('Date,"3 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","30 Yr"\n'
             "12/31/1990,6.63,6.73,6.82,7.15,7.40,7.68,8.00,8.08,8.26\n")
    t2026 = ('Date,"1 Mo","1.5 Month","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"\n'
             "10/16/2026,4.12,4.14,4.17,4.26,4.32,4.34,4.46,4.74,4.82,4.89,4.98,5.09,5.47,5.43\n"
             "10/15/2026,4.17,,4.19,,4.35,4.35,4.49,4.77,4.85,4.91,5.00,5.10,5.48,5.43\n")
    assert F.parse_treasury(t1990) == {"1990-12-31": [6.63, 7.15, 8.08]}
    assert F.parse_treasury(t2026) == {"2026-10-16": [4.26, 4.74, 5.09], "2026-10-15": [None, 4.77, 5.10]}


def test_bls_post_chunks_of_ten_years(lab, monkeypatch):
    calls = []

    def fake(url, body, timeout=60):
        calls.append((body["startyear"], body["endyear"]))
        y = body["startyear"]
        return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"seriesID": "CUUR0000SA0", "data": [
            {"year": y, "period": "M12", "value": "168.3"}, {"year": y, "period": "M13", "value": "167.0"},
            {"year": y, "period": "M01", "value": "127.4"}]}]}}
    monkeypatch.setattr(F, "_post_json", fake)
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    assert F.bls_cpi(1990, 2012) == 6
    assert calls == [("1990", "1999"), ("2000", "2009"), ("2010", "2012")]
    assert HD.load("uscpi")["1990-12"] == 168.3 and "1990-13" not in HD.load("uscpi")   # 年平均（M13）不收


def test_effr_dbnomics_before_2016_then_nyfed(lab, monkeypatch):
    dbn = {"series": {"docs": [{"period": ["1954-07-01", "2016-02-29", "2016-03-01", "2016-03-02"],
                                "value": [1.13, 0.37, 0.36, "NA"]}]}}
    ny = {"refRates": [{"effectiveDate": "2026-10-15", "type": "EFFR", "percentRate": 3.88,
                        "targetRateFrom": 3.75, "targetRateTo": 4.00}]}
    monkeypatch.setattr(F, "_get", lambda url, **kw: json.dumps(dbn if "db.nomics" in url else ny).encode())
    assert F.dbn_effr() == 2                                             # 2016-03 起留給紐約聯準銀行
    assert F.nyfed_effr() == 1
    assert HD.load("effr") == {"1954-07-01": 1.13, "2016-02-29": 0.37, "2026-10-15": 3.88}
    assert HD.load("fedtgt") == {"2026-10-15": [3.75, 4.0]}


def test_yahoo_adjclose_replaces_whole_history_but_not_on_partial(lab, monkeypatch):
    from arm.lab import market
    full = {f"2020-01-{d:02d}": [1, 1, 1, 100.0 + d, 10, 90.0 + d] for d in range(1, 21)}
    monkeypatch.setattr(market, "yahoo_hist_from", lambda sym, start, adj=False: full)
    assert F.yahoo_adj("hyg", "HYG", "2007-01-01") == 20
    assert HD.load("hyg")["2020-01-05"] == 95.0                          # 用還原收盤
    shifted = {d: [1, 1, 1, r[3], 10, r[5] * 0.99] for d, r in full.items()}   # 新配息：整段歷史改寫
    monkeypatch.setattr(market, "yahoo_hist_from", lambda sym, start, adj=False: shifted)
    F.yahoo_adj("hyg", "HYG", "2007-01-01")
    assert abs(HD.load("hyg")["2020-01-05"] - 95.0 * 0.99) < 1e-9
    part = dict(list(shifted.items())[:5])                               # 只拿到一小段：只補不換
    monkeypatch.setattr(market, "yahoo_hist_from", lambda sym, start, adj=False: part)
    F.yahoo_adj("hyg", "HYG", "2007-01-01")
    assert len(HD.load("hyg")) == 20


def test_ndc_exports_header_by_name_and_missing_column_raises():
    t = "Date,海關出口值(十億元),其他\n198201,65.56,1\n198202,-,2\n"
    assert F.parse_ndc_exports(t) == {"1982-01": 65.56}
    with pytest.raises(ValueError):
        F.parse_ndc_exports("Date,工業生產指數\n198201,1\n")


# ── 第三階段（規劃文件第 13 節）：樣本是 CI 探針實際拿到的格式 ─────────────────

def test_ofr_mmf_month_end_to_month(lab, monkeypatch):
    body = json.dumps([["2010-11-30", 3076353570850.39], ["2026-09-30", 8396822287018.74], ["bad", 1]]).encode()
    monkeypatch.setattr(F, "_get", lambda url, **kw: body)
    assert F.ofr_mmf() == 2
    assert HD.load("mmf") == {"2010-11": 3076353570850.39, "2026-09": 8396822287018.74}


def test_qfiis_sums_all_industries_or_uses_total_row():
    fields = ["產業別", "家數", "總發行股數", "僑外資及陸資持有總股數", "僑外資及陸資持股比率"]
    doc = {"stat": "OK", "fields": fields, "data": [["水泥工業", 7, "1,000", "100", "10.00"],
                                                    ["其他", 34, "10,939,540,635", "935,024,162", "8.55"]]}
    assert F.parse_qfiis(doc) == [935024262.0, 10939541635.0]
    doc["data"].append(["合計", 41, "20,000,000,000", "8,000,000,000", "40.00"])
    assert F.parse_qfiis(doc) == [8e9, 2e10]
    assert F.parse_qfiis({"stat": "很抱歉，沒有符合條件的資料!"}) is None
    cal = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"]
    assert F.qfii_days(cal, {}, recent=1) == ["2026-10-16", "2026-10-19"]          # 每週最後一天＋最近 1 天
    assert F.qfii_days(cal, {"2026-10-16": [1, 2]}, recent=1) == ["2026-10-19"]


def test_cbc_bank_columns_by_name_and_keeps_old_when_one_table_fails(lab, monkeypatch):
    tables = {
        "EF25M01": (["國外負債", "央行發行單券-國庫券", "央行發行單券-定期存單"], 2,
                    [["2026M08", "-", "-", "1", "2", "6573670", "-12.09"]]),
        "EF03M01": (["貨幣機構存款-合計", "貨幣機構存款-活期性存款"], 2, [["2026M08", "700723", "7.67", "1", "2"]]),
        "EF35M01": (["資產淨額=負債權益淨額", "國外資產", "放款-計", "放款-政府機關"], 2,
                    [["2026M08", "1", "9.34", "2", "8.24", "47737620", "10.49", "3", "2.76"]]),
        "EG37M01": (["隔夜-加權平均", "隔夜-最高"], 1, [["2026M08", "0.822", "0.830"], ["2026M07", "-", "1"]]),
    }
    monkeypatch.setattr(F, "_cbc_table", lambda code: tables[code])
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    assert F.cbc_bank() == 1
    assert HD.load("cbcbank")["2026-08"] == [6573670.0, 7.67, 10.49, 0.822]

    def boom(code):
        if code == "EF03M01":
            raise RuntimeError("timeout")
        return tables[code]
    tables["EG37M01"] = (["隔夜-加權平均"], 1, [["2026M08", "0.9"]])
    monkeypatch.setattr(F, "_cbc_table", boom)
    F.cbc_bank()
    assert HD.load("cbcbank")["2026-08"] == [6573670.0, 7.67, 10.49, 0.9]       # 存款那欄保留舊值


SITCA_HTML = """<table><tr><td>類型</td><td>代號</td><td>基金名稱</td><td>投資國內股市比例小計(%)</td></tr>
<tr><td>第1週<br>2026/10/3</td><td>第2週<br>2026/10/10</td><td>第3週<br>2026/10/17</td></tr>
<tr><td>AA1</td><td>兆豐第一基金</td><td>95.70</td><td>96.35</td><td>-</td></tr>
<tr><td colspan="3">合計</td><td>96.46</td><td>96.26</td><td>0.00</td></tr></table>"""


def test_sitca_week_total_row_and_form():
    assert F.parse_sitca_week(SITCA_HTML) == {"2026-10-03": 96.46, "2026-10-10": 96.26}
    page = ('<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="abc" />'
            '<select name="ctl00$ContentPlaceHolder1$ddlQ_YM"><option value="202609">x</option></select>'
            '<select name="ctl00$ContentPlaceHolder1$ddlQ_Class"><option value="">所有</option></select>'
            '<input type="submit" name="ctl00$ContentPlaceHolder1$BtnQuery" value="查詢" />')
    f = F._sitca_form(page, "202110")
    assert f["__VIEWSTATE"] == "abc" and f["ctl00$ContentPlaceHolder1$ddlQ_YM"] == "202110"
    assert f["ctl00$ContentPlaceHolder1$ddlQ_Class"] == "" and f["ctl00$ContentPlaceHolder1$BtnQuery"] == "查詢"
    assert F.months_from("2021-10", F.date(2022, 1, 5)) == ["2021-10", "2021-11", "2021-12", "2022-01"]


SFB_TXT = ("三、 外資及陸資投資國內資金匯出入情況： （一）外資及陸資 115 年 9 月份淨匯(出)入情形： 金額單位：美元/億元 "
           "115 年 9 月份 115 年累計至 9 月底 境 外 外 國 機 構 投 資 人 、 華僑及外國自然人 累積淨匯(出)入 178.46 1,081.77 "
           "陸資累積淨匯(出)入 0.24 2.13 合計 178.70 1,083.90 （二）外資及陸資累計淨匯(出)入情形： 金額單位：美元/億元 "
           "截至 115 年 9 月底止 截至 115 年 8 月底止 增(減) 金額 境 外 外 國 機 構 投 資 人 、 華僑及外國自然人 累積淨匯(出)入 "
           "4,282.66 4,104.20 178.46 陸資累積淨匯(出)入 2.87 2.63 0.24 合計 4,285.53 4,106.83 178.70 聯絡單位")


def test_sfb_flow_pdf_text_month_and_cumulative():
    assert F.parse_sfb_flow(SFB_TXT) == {"2026-09": [178.70, 4285.53], "2026-08": [None, 4106.83]}
    neg = SFB_TXT.replace("合計 178.70 1,083.90", "合計 (29.26) 738.55").replace("（一）外資及陸資 115 年 9 月份",
                                                                               "（一）外資及陸資 116 年 1 月份")
    r = F.parse_sfb_flow(neg)
    assert r["2027-01"][0] == -29.26 and r["2026-12"] == [None, 4106.83]       # 括號＝匯出；一月的前一個月是去年 12 月
    assert F.parse_sfb_flow("沒有表") == {}
