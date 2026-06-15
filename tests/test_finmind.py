"""FinMind 券商分點 adapter 測試（離線，monkeypatch HTTP + token）。

FinMind TaiwanStockTradingDailyReport 為付費 sponsor 資料，無 token 時 adapter 須靜默停用；
有 token 時把『股』換算『張』、多日合併、算 day_volume。樣本仿 FinMind v4 回應形狀。
"""
import os

from arm.connectors.brokers import finmind
from arm.connectors.brokers.base import NoData

SAMPLE = {"msg": "success", "status": 200, "data": [
    {"date": "2026-06-11", "securities_trader_id": "1470", "securities_trader": "台灣摩根士丹利",
     "stock_id": "2330", "buy": 900000, "sell": 100000, "price": 1100},
    {"date": "2026-06-12", "securities_trader_id": "1470", "securities_trader": "台灣摩根士丹利",
     "stock_id": "2330", "buy": 1500000, "sell": 300000, "price": 1110},
    {"date": "2026-06-12", "securities_trader_id": "9200", "securities_trader": "凱基-台北",
     "stock_id": "2330", "buy": 200000, "sell": 700000, "price": 1108},
]}


def test_available_reflects_token(monkeypatch):
    monkeypatch.delenv("FINMIND_TOKEN", raising=False)
    assert finmind.available() is False
    monkeypatch.setenv("FINMIND_TOKEN", "x")
    assert finmind.available() is True


def test_fetch_without_token_raises(monkeypatch):
    monkeypatch.delenv("FINMIND_TOKEN", raising=False)
    try:
        finmind.fetch("2330")
        assert False, "should raise NoData"
    except NoData:
        pass


def test_fetch_converts_shares_to_lots_and_multiday(monkeypatch):
    monkeypatch.setenv("FINMIND_TOKEN", "x")
    monkeypatch.setattr(finmind, "get_json", lambda url, **kw: SAMPLE)
    tf = finmind.fetch("2330", window_days=6)
    assert sorted({f.date for f in tf.flows}) == ["2026-06-11", "2026-06-12"]
    mer = [f for f in tf.flows if f.broker_id == "1470"]
    # 2026-06-12: (1,500,000-300,000)/1000 = 1200 張
    assert any(f.date == "2026-06-12" and f.net == 1200 for f in mer)
    # day_volume（總買量/1000）：6/12 = (1,500,000+200,000)/1000 = 1700 張
    assert tf.day_volume["2026-06-12"] == 1700


def test_error_response_raises(monkeypatch):
    monkeypatch.setenv("FINMIND_TOKEN", "x")
    monkeypatch.setattr(finmind, "get_json",
                        lambda url, **kw: {"msg": "Your level is free.", "status": 400})
    try:
        finmind.fetch("2330")
        assert False
    except NoData:
        pass
