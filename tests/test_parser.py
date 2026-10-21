"""復華 assetsExcel 多資產解析器單元測試（M1-8）：股票/期貨/債券、外股 ticker、合計列排除。"""
from conftest import make_xlsx

from arm.connectors import fhtrust


def test_parse_face():
    assert fhtrust._parse_face("(USD)4,900,000") == (4900000.0, "USD")
    assert fhtrust._parse_face("(AUD)250,000") == (250000.0, "AUD")
    assert fhtrust._parse_face("1,234") == (1234.0, None)


def test_header_and_datarow_helpers():
    assert fhtrust._is_header(["證券代號", "證券名稱", "股數", "金額", "權重(%)"]) == "equity"
    assert fhtrust._is_header(["期貨代號", "期貨名稱", "口數", "金額", "權重(%)"]) == "future"
    assert fhtrust._is_header(["證券代碼", "證券名稱", "面額", "結算價格",
                               "應收利息", "債券市值", "權重(%)"]) == "bond"
    assert fhtrust._is_header(["隨便", "欄位"]) is None
    assert fhtrust._is_data_row(["C US", "花旗", "30,000", "1,000", "4.242%"], 5)
    assert not fhtrust._is_data_row(["合計", "", "", "", "100.00%"], 5)   # 中文代號 → 排除
    assert not fhtrust._is_data_row(["C US", "花旗", "30,000", "1,000", "x"], 5)


def test_fetch_equity_with_foreign_tickers(monkeypatch):
    xlsx = make_xlsx(
        "復華全球金融股票入息主動式ETF（00998A）", "2026/06/12",
        {"基金資產淨值": "16850", "基金在外流通單位數": "1000", "基金每單位淨值": "16.85"},
        [(["證券代號", "證券名稱", "股數", "金額", "權重(%)"],
          [["C US", "花旗集團", "30,000", "8,425", "50.000%"],
           ["7167 JP", "Mebuki金融", "280,000", "8,425", "48.580%"],
           ["合計", "", "", "16,850", "98.580%"]])])     # 合計列應被排除
    monkeypatch.setattr(fhtrust, "get_bytes", lambda *a, **k: xlsx)
    snap = fhtrust.fetch_holdings("ETF24", "2026-06-12")
    assert snap["nav"] == 16.85 and snap["units"] == 1000
    assert len(snap["holdings"]) == 2
    h = {x["stock_id"]: x for x in snap["holdings"]}
    assert h["C US"]["kind"] == "equity" and h["C US"]["shares"] == 30000
    assert h["7167 JP"]["weight"] == 48.58


def test_fetch_bond_fund_multi_section(monkeypatch):
    xlsx = make_xlsx(
        "復華全球金融債券入息主動式ETF（00986D）", "2026/06/12",
        {"基金資產淨值": "14880", "基金在外流通單位數": "1000", "基金每單位淨值": "14.88"},
        [(["期貨代號", "期貨名稱", "口數", "金額", "權重(%)"],
          [["US202609", "美國30年公債期", "100", "3,555", "14.380%"],
           ["XT202609", "澳洲10年公債期", "-10", "-21", "0.000%"]]),
         (["證券代碼", "證券名稱", "面額", "債券結算價格", "債券應收利息(NTD)",
           "債券市值 (NTD)", "權重(%)"],
          [["US06423AAJ25", "JPM 8 3/4", "(USD)4,900,000", "114.72", "3,799",
            "10,000", "60.000%"],
           ["US83368TBT43", "SOCGEN 7.367", "(USD)5,200,000", "107.09", "5,164",
            "6,500", "39.270%"]])])
    monkeypatch.setattr(fhtrust, "get_bytes", lambda *a, **k: xlsx)
    snap = fhtrust.fetch_holdings("ETF25", "2026-06-12")
    kinds = sorted(x["kind"] for x in snap["holdings"])
    assert kinds == ["bond", "bond", "future", "future"]
    fut = next(x for x in snap["holdings"] if x["stock_id"] == "XT202609")
    assert fut["shares"] == -10                      # 避險口數為負
    bond = next(x for x in snap["holdings"] if x["stock_id"] == "US06423AAJ25")
    assert bond["shares"] == 4900000 and bond["face_ccy"] == "USD"
    assert bond["market_value"] == 10000 and bond["weight"] == 60.0


def test_shared_strings_xml_entities_are_unescaped(monkeypatch):
    """sharedStrings 是 XML：`M&G` 在檔裡是 `M&amp;G`。2026-10-21 前沒還原，00998A 的
    「M&amp;G公開有限公司」帶著實體進落檔，網頁顯示成字面「&amp;」。"""
    xlsx = make_xlsx(
        "復華全球金融股票入息主動式ETF（00998A）", "2026/10/20",
        {"基金資產淨值": "16850", "基金在外流通單位數": "1000", "基金每單位淨值": "16.85"},
        [(["證券代號", "證券名稱", "股數", "金額", "權重(%)"],
          [["MNG LN", "M&G公開有限公司", "1,000,000", "8,425", "50.000%"],
           ["8725 JP", "MS&AD保險集團控股公司", "280,000", "8,425", "48.580%"]])])
    monkeypatch.setattr(fhtrust, "get_bytes", lambda *a, **k: xlsx)
    snap = fhtrust.fetch_holdings("ETF24", "2026-10-20")
    assert [h["stock_name"] for h in snap["holdings"]] == ["M&G公開有限公司", "MS&AD保險集團控股公司"]
