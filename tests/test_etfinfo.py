"""etfinfo.tw 第三方彙整連接器單元測試（離線，monkeypatch get_json）。

驗證正規化：競品持股 code/name → stock_id/stock_name、保留 as-of/source；配息與殖利率；
主動ETF籌碼 meta/items 拆解。實際 API 形狀以 2026-06-15 實測回應為樣本。
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


def test_dividends_and_yield(monkeypatch):
    monkeypatch.setattr(etfinfo, "fetch_etf", lambda code: SAMPLE_ETF)
    divs, ty = etfinfo.dividends("00981A")
    assert ty == 3.3 and len(divs) == 2
    assert divs[0] == {"ex_date": "2026-06-16", "amount": 0.63}


def test_active_flow_splits_meta_items(monkeypatch):
    payload = {"date": "2026-06-12", "side": "buy", "snapshotRangeDays": 30,
               "items": [{"stockCode": "2327", "stockName": "國巨*"}]}
    monkeypatch.setattr(etfinfo, "get_json", lambda url, **kw: payload)
    meta, items = etfinfo.active_flow("buy")
    assert meta["date"] == "2026-06-12" and "items" not in meta
    assert len(items) == 1 and items[0]["stockCode"] == "2327"
