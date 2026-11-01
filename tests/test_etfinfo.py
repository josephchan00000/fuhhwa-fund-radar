"""etfinfo.tw 第三方彙整連接器單元測試（離線，monkeypatch get_json）。

驗證正規化：持股 code/name → stock_id/stock_name、保留 as-of/source；期貨列帶 kind。
實際 API 形狀以 2026-06-15 實測回應為樣本。（配息、主動ETF籌碼兩個函式 2026-11-01 隨舊本機流程拿掉，測試一起拿掉。）
"""
from arm.connectors import etfinfo

SAMPLE_ETF = {
    "info": {"issuer": "統一", "name": "主動統一台股增長", "dividendFrequency": "quarterly"},
    "latestMarket": {"date": "2026-06-15", "aum": 1.0e10, "beneficiaries": 12345},
    "holdings": {
        "snapshotDate": "2026-06-15", "etfCode": "00981A", "source": "issuer-official",
        "stocks": [
            {"code": "2330", "name": "台積電", "weight": 9.67, "shares": 11960000, "unit": "股"},
            {"code": "2454", "name": "聯發科", "weight": 7.4, "shares": 4861000, "unit": "股"},
        ],
    },
    "dividends": [{"exDate": "2026-06-16", "code": "00981A", "amount": 0.63},
                  {"exDate": "2026-03-17", "code": "00981A", "amount": 0.41}],
    "trailingYield": 3.3,
}


def test_holdings_normalizes_to_drop_in_shape(monkeypatch):
    monkeypatch.setattr(etfinfo, "fetch_etf", lambda code: SAMPLE_ETF)
    hs, meta = etfinfo.holdings("00981A")
    assert hs[0] == {"stock_id": "2330", "stock_name": "台積電", "weight": 9.67, "shares": 11960000}
    assert meta["issuer"] == "統一" and meta["as_of"] == "2026-06-15"
    assert meta["source"] == "issuer-official"      # provenance 可追溯


def test_future_rows_carry_kind(monkeypatch):
    """期貨列（API assetType="future"）帶 kind="future"——抓取端據此另存「期貨部位」；
    股票列格式不變（2026-10-21 CI 探針：00986D `US202612`、00987D `UB:2026-12:B`）。"""
    doc = {"holdings": {"stocks": [
        {"code": "US912810UW61", "name": "T 5 1/8 08/15/56", "weight": 59.66, "shares": 15920000,
         "unit": "股", "assetType": "bond"},
        {"code": "UB:2026-12:B", "name": "超長美債", "weight": 36.55, "shares": 87,
         "unit": "口", "assetType": "future"}]}}
    monkeypatch.setattr(etfinfo, "fetch_etf", lambda code: doc)
    hs, _meta = etfinfo.holdings("00987D")
    assert "kind" not in hs[0]
    assert hs[1] == {"stock_id": "UB:2026-12:B", "stock_name": "超長美債", "weight": 36.55,
                     "shares": 87, "kind": "future"}
