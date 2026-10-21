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


def test_second_round_exchange_codes():
    """第一輪 CI 實測漏掉的 5 檔（2026-08-05）：中國 A 股 CH、韓股 KP、Aviva 尾斜線。"""
    assert yahooq.to_yahoo("300408 CH") == "300408.SZ"    # 深圳創業板
    assert yahooq.to_yahoo("301377 CH") == "301377.SZ"
    assert yahooq.to_yahoo("600519 CH") == "600519.SS"    # 6 開頭＝上海
    assert yahooq.to_yahoo("005930 KP") == "005930.KS"    # 彭博 KP＝KOSPI
    assert yahooq.to_yahoo("AV/ LN") == "AV.L"            # 尾斜線剝掉，非 'AV-.L'
    assert yahooq.to_yahoo("BRK/B US") == "BRK-B"         # 中段斜線仍轉 '-'
    assert yahooq.to_yahoo("/ LN") is None                # 剝完空字串不出手


# ── 指定日期、已收盤（2026-10-21 使用者：「漲跌幅是錯的」；只用已收盤、對齊台股最新交易日） ──

from datetime import datetime, timedelta, timezone

_ET, _TP, _AU = -4 * 3600, 8 * 3600, 11 * 3600


def _ts(y, m, d, hh, mm, off):
    return int(datetime(y, m, d, hh, mm, tzinfo=timezone(timedelta(seconds=off))).timestamp())


def _res(days, closes, off, reg_day, open_hm, close_hm, rmt=None, rmp=None, ccy="USD"):
    y, m = 2026, 10
    return {"meta": {"gmtoffset": off, "currency": ccy,
                     "currentTradingPeriod": {"regular": {
                         "start": _ts(y, m, reg_day, *open_hm, off), "end": _ts(y, m, reg_day, *close_hm, off)}},
                     "regularMarketTime": rmt, "regularMarketPrice": rmp},
            "timestamp": [_ts(y, m, d, *open_hm, off) for d in days],
            "indicators": {"quote": [{"close": closes}]}}


def _us(closes, reg_day, **kw):
    return _res([15, 16, 19, 20][:len(closes)], closes, _ET, reg_day, (9, 30), (16, 0), **kw)


def test_close_on_skips_intraday_bar():
    """22:31（美東 10:31）那根是盤中價——舊碼照收（NVDA 218.135、+0.48%）。"""
    r = _us([217.24, 214.13, 217.09, 218.135], 20)
    assert yahooq.close_on(r, "2026-10-20", _ts(2026, 10, 20, 22, 31, _TP)) == ("pend", None, None)


def test_close_on_just_closed_bar_null_uses_regular_market_price():
    """台北早上（美東前一晚）剛收盤那根收盤是空值——舊碼跳過、拿到前兩個交易日的漲跌
    （10/21 08:36 NVDA 顯示 10/19 的 +1.38%）。改用 regularMarketPrice（時戳在當天時段內）。"""
    r = _us([217.24, 214.13, 217.09, None], 20, rmt=_ts(2026, 10, 20, 16, 0, _ET), rmp=219.5)
    assert yahooq.close_on(r, "2026-10-20", _ts(2026, 10, 21, 8, 36, _TP)) == ("ok", 219.5, 217.09)
    # 最後成交已是隔天（那天的收盤無從得知）→ 不用，當作查無
    r2 = _us([217.24, 214.13, 217.09, None], 21, rmt=_ts(2026, 10, 21, 10, 0, _ET), rmp=219.9)
    assert yahooq.close_on(r2, "2026-10-20", _ts(2026, 10, 21, 22, 0, _TP))[0] == "none"


def test_close_on_european_null_bar_after_period_rolled_over():
    """2026-10-21 CI 探針實況：歐股 10/20 那根到台北中午還是空值，時段資訊已換到 10/21；
    最後成交 10/20 17:35（ABN.AS 收盤競價）、倫敦 16:49（收盤後 19 分）——都是 10/20 的收盤價。"""
    cest, bst, now = 2 * 3600, 1 * 3600, _ts(2026, 10, 21, 11, 54, _TP)
    abn = _res([16, 19, 20], [40.99, 40.30, None], cest, 21, (9, 0), (17, 30),
               rmt=_ts(2026, 10, 20, 17, 35, cest), rmp=40.33, ccy="EUR")
    assert yahooq.close_on(abn, "2026-10-20", now) == ("ok", 40.33, 40.30)
    sdlf = _res([16, 19, 20], [911.0, 911.5, None], bst, 21, (8, 0), (16, 30),
                rmt=_ts(2026, 10, 20, 16, 49, bst), rmp=909.0, ccy="GBp")
    assert yahooq.close_on(sdlf, "2026-10-20", now) == ("ok", 909.0, 911.5)


def test_close_on_pending_before_the_session_ends():
    r = _us([217.24, 214.13, 217.09], 20)            # 台北 19:00＝美東 07:00，10/20 還沒開盤
    assert yahooq.close_on(r, "2026-10-20", _ts(2026, 10, 20, 19, 0, _TP))[0] == "pend"
    r_old = _us([217.24, 214.13, 217.09], 19)        # 時段資訊還停在前一天 → 目標日在它之後，仍是待收盤
    assert yahooq.close_on(r_old, "2026-10-20", _ts(2026, 10, 20, 19, 0, _TP))[0] == "pend"


def test_close_on_earlier_day_and_holiday():
    r = _us([217.24, 214.13, 217.09, 219.0], 20)
    now = _ts(2026, 10, 21, 8, 36, _TP)
    assert yahooq.close_on(r, "2026-10-19", now) == ("ok", 217.09, 214.13)
    assert yahooq.close_on(r, "2026-10-17", now) == ("none", None, None)   # 週六沒有那一根


def test_close_on_local_date_uses_exchange_offset():
    """澳洲夏令 10:00 開盤＝UTC 前一天 23:00——用 UTC 日期會錯一天，必須用 gmtoffset 換當地日期。"""
    r = _res([19, 20], [50.0, 51.0], _AU, 21, (10, 0), (16, 0), ccy="AUD")
    assert datetime.fromtimestamp(r["timestamp"][1], timezone.utc).date().isoformat() == "2026-10-19"
    assert yahooq.close_on(r, "2026-10-20", _ts(2026, 10, 21, 8, 36, _TP)) == ("ok", 51.0, 50.0)


def test_close_on_prev_must_be_the_adjacent_bar():
    """前一根是空值 → 前收 None（不可跨兩天相減）。"""
    r = _us([217.24, None, 217.09, 219.0], 20)
    assert yahooq.close_on(r, "2026-10-19", _ts(2026, 10, 21, 8, 36, _TP)) == ("ok", 217.09, None)


def test_fetch_foreign_on_reports_closed_pending_and_failures(monkeypatch):
    now = _ts(2026, 10, 20, 19, 2, _TP)              # 台北 19:02：日股已收盤、美股還沒開
    jp = _res([16, 19, 20], [6900.0, 6797.0, 6643.0], 9 * 3600, 20, (9, 0), (15, 30), ccy="JPY")
    us = _us([217.24, 214.13, 217.09], 20)

    def fake_get_json(url, **kw):
        if "/chart/6981.T?" in url:
            return {"chart": {"result": [jp]}}
        if "/chart/NVDA?" in url:
            return {"chart": {"result": [us]}}
        raise RuntimeError("HTTP 404")
    monkeypatch.setattr(yahooq, "get_json", fake_get_json)
    out, pend, st = yahooq.fetch_foreign_on({"6981 JP", "NVDA US", "LITE US", "2330"}, "2026-10-20", now)
    assert out["6981 JP"] == {"close": 6643.0, "change": -154.0, "ccy": "JPY", "name": "", "volume": 0,
                              "date": "2026-10-20"}
    assert pend == {"NVDA US"} and "NVDA US" not in out
    assert st == {"ok": 1, "pend": 1, "none": 0, "fail": 1}            # LITE 抓不到；台股代號不在範圍
