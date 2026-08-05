"""Yahoo 海外個股報價補源（2026-08-05 使用者：海外持股的當日漲跌也要補）。"""
from arm.connectors import yahooq
from arm import etfholdings as eh


def test_bloomberg_to_yahoo_symbol_mapping():
    assert yahooq.to_yahoo("NVDA US") == "NVDA"
    assert yahooq.to_yahoo("BRK/B US") == "BRK-B"
    assert yahooq.to_yahoo("6981 JP") == "6981.T"
    assert yahooq.to_yahoo("285A JP") == "285A.T"
    assert yahooq.to_yahoo("009150 KS") == "009150.KS"
    assert yahooq.to_yahoo("IFX GY") == "IFX.DE"
    assert yahooq.to_yahoo("LLOY LN") == "LLOY.L"
    assert yahooq.to_yahoo("GLE FP") == "GLE.PA"
    assert yahooq.to_yahoo("ABN NA") == "ABN.AS"
    assert yahooq.to_yahoo("TPEIR GA") == "TPEIR.AT"
    # 不符樣式／未知交易所 → None（債券 ISIN、台股 4 碼、期貨都不會誤收）
    assert yahooq.to_yahoo("US83368TBT43") is None
    assert yahooq.to_yahoo("2330") is None
    assert yahooq.to_yahoo("202609US") is None
    assert yahooq.to_yahoo("NVDA XX") is None


def test_fetch_foreign_quotes_builds_change_from_last_two_closes(monkeypatch):
    charts = {"NVDA": ([180.0, 185.5], "USD"), "6981.T": ([2500.0, 2450.0], "JPY")}
    def fake_get_json(url, **kw):
        for sym, (closes, ccy) in charts.items():
            if f"/chart/{sym}?" in url:
                return {"chart": {"result": [{"meta": {"currency": ccy},
                        "indicators": {"quote": [{"close": closes}]}}]}}
        raise RuntimeError("HTTP 404")
    monkeypatch.setattr(yahooq, "get_json", fake_get_json)
    out = yahooq.fetch_foreign_quotes({"NVDA US", "6981 JP", "US83368TBT43", "LITE US"})
    assert out["NVDA US"]["close"] == 185.5 and out["NVDA US"]["change"] == 5.5
    assert out["NVDA US"]["ccy"] == "USD"
    assert out["6981 JP"]["change"] == -50.0 and out["6981 JP"]["ccy"] == "JPY"
    assert "US83368TBT43" not in out and "LITE US" not in out   # 抓不到就跳過、不補假值


def test_foreign_quote_fills_chg_but_not_treemap_amount():
    """海外報價補上漲跌％／貢獻；但外幣收盤不得算成方塊圖金額（跨幣別面積不可比）——
    面積照舊退回股數口徑。"""
    r1 = [{"stock_id": "NVDA US", "name": "NVIDIA", "shares": 10000, "weight": 8.0},
          {"stock_id": "MU US", "name": "Micron", "shares": 20000, "weight": 5.0}]
    r2 = [dict(r1[0], shares=12000), dict(r1[1])]
    merged = eh.merge_one({"date": "d1", "src": "etfinfo", "holdings": r1},
                          {"date": "d2", "src": "etfinfo", "holdings": r2})
    q = {"NVDA US": {"close": 185.5, "change": 5.5, "ccy": "USD"}}
    det = eh.contributions(merged, q)
    by = {r["stock_id"]: r for r in det["all"]}
    assert by["NVDA US"]["chg_pct"] == round(5.5 / 180.0 * 100, 2)   # 3.06%
    assert by["NVDA US"]["contrib"] == round(8.0 * by["NVDA US"]["chg_pct"] / 100, 3)
    assert by["NVDA US"]["close"] == 185.5 and by["NVDA US"]["ccy"] == "USD"
    mv = {m["stock_id"]: m for m in det["moves"]}
    assert mv["NVDA US"]["amount"] is None                # 外幣不算金額
    assert det["amount_basis"] == "shares"


def test_domestic_amount_math_unchanged():
    """台股（無 ccy）金額計算不受影響——回歸保護。"""
    r1 = [{"stock_id": "2330", "name": "台積電", "shares": 1000, "weight": 20.0},
          {"stock_id": "2317", "name": "鴻海", "shares": 500, "weight": 10.0}]
    r2 = [dict(r1[0], shares=1200), dict(r1[1])]
    merged = eh.merge_one({"date": "d1", "src": "etfinfo", "holdings": r1},
                          {"date": "d2", "src": "etfinfo", "holdings": r2})
    det = eh.contributions(merged, {"2330": {"close": 1100.0, "change": 10.0}})
    mv = {m["stock_id"]: m for m in det["moves"]}
    assert mv["2330"]["amount"] == 220000 and det["amount_basis"] == "amount"
