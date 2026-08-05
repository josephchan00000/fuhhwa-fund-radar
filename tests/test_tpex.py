"""TPEx 連接器：openapi 每日收盤＋rwd dailyQuotes 備援（2026-08-05 openapi 整輪失敗踩坑）。"""
from arm.connectors import tpex


def test_openapi_rows_parse():
    rows = [{"SecuritiesCompanyCode": "5274", "CompanyName": "信驊", "Date": "1150805",
             "Close": "5,120.00", "Change": "+120.0", "TradingShares": "351,000"}]
    out = tpex._from_openapi(rows)
    assert out["5274"] == {"date": "2026-08-05", "name": "信驊", "close": 5120.0,
                           "change": 120.0, "volume": 351000}


def test_fallback_to_rwd_when_openapi_raises(monkeypatch):
    """openapi 掛掉 → 自動改走 rwd dailyQuotes，格式對齊（annotate 端無感）。"""
    from datetime import date
    rwd = {"tables": [{"data": [
        ["5274", "信驊", "5,120.00", "+120.0", "5,000", "5,150", "4,990", "5,060", "351,000", "x", "y"],
        ["720693", "永豐51購01", "1.00", "0.0", "", "", "", "", "10", "x", "y"],   # 權證 → 濾掉
    ]}]}
    def fake_get_json(url, **kw):
        if "openapi" in url:
            raise RuntimeError("GET 失敗 …: HTTP 503")
        return rwd
    monkeypatch.setattr(tpex, "get_json", fake_get_json)
    monkeypatch.setattr(tpex.clock if hasattr(tpex, "clock") else __import__("arm.clock", fromlist=["clock"]),
                        "today_tw", lambda: date(2026, 8, 5), raising=False)
    out = tpex.fetch_today_all()
    assert out["5274"]["close"] == 5120.0 and out["5274"]["change"] == 120.0
    assert out["5274"]["volume"] == 351000
    assert "720693" not in out                            # 非個股列不收


def test_rwd_rows_accepts_both_wrappings():
    assert tpex._rwd_rows({"tables": [{"data": [[1]]}]}) == [[1]]
    assert tpex._rwd_rows({"aaData": [[2]]}) == [[2]]
    assert tpex._rwd_rows({"stat": "ok"}) == []
    assert tpex._rwd_rows(None) == []


def test_openapi_zero_rows_falls_back(monkeypatch):
    """openapi 回空清單（曾見端點回 200 但空）→ 同樣走備援。"""
    from datetime import date
    calls = []
    def fake_get_json(url, **kw):
        calls.append(url)
        if "openapi" in url:
            return []
        return {"tables": [{"data": [["6223", "旺矽", "1,050", "-15", "", "", "", "", "2,000"]]}]}
    monkeypatch.setattr(tpex, "get_json", fake_get_json)
    import arm.clock as clock
    monkeypatch.setattr(clock, "today_tw", lambda: date(2026, 8, 5))
    out = tpex.fetch_today_all()
    assert out["6223"]["close"] == 1050.0 and out["6223"]["change"] == -15.0
    assert any("dailyQuotes" in u for u in calls)
