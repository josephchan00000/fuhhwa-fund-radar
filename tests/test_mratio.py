"""台股大盤融資維持率（arm/lab/mratio.py）：逐檔合計、官方分片、涵蓋率與回補流程（假的 FinMind 回應）。"""
import json

import pytest

from arm.lab import mratio as M


def test_contrib_window_stale_and_missing_prices():
    mg = {"2020-01-02": 10, "2020-01-03": 12, "2020-01-06": 0, "2020-01-07": 8, "2020-01-08": 5, "2020-01-09": 3}
    px = {"2020-01-03": 20.0, "2020-01-07": 21.0, "2020-01-09": 0}
    rows, miss, stale = M.contrib(mg, px, start="2020-01-03", end="2020-01-09", last="2020-01-08")
    # 01-02 在上市日之前、01-06 張數 0、01-09 超過 last → 不算；01-08 沒有收盤 → 用 01-07 的收盤
    assert rows == {"2020-01-03": (12 * 1000 * 20.0, 12), "2020-01-07": (8 * 1000 * 21.0, 8),
                    "2020-01-08": (5 * 1000 * 21.0, 5)}
    assert (miss, stale) == (0, 1)
    rows, miss, stale = M.contrib({"2020-01-02": 4}, {"2020-01-03": 10.0}, start=None, end=None, last="2030-01-01")
    assert rows == {} and miss == 1                               # 之前完全沒有收盤：不算


def test_add_keeps_stocks_and_etfs_apart():
    agg = {}
    M.add(agg, {"2020-01-03": (100.0, 1)}, etf=False)
    M.add(agg, {"2020-01-03": (50.0, 2)}, etf=True)
    M.add(agg, {"2020-01-03": (10.0, 1), "2020-01-06": (5.0, 1)}, etf=False)
    assert agg == {"2020-01-03": [110.0, 2, 2, 50.0, 2, 1], "2020-01-06": [5.0, 1, 1, 0.0, 0, 0]}
    assert M.is_etf("0050") and M.is_etf("00878") and not M.is_etf("2330") and not M.is_etf("9105")


def test_official_day_and_ratio():
    doc = {"m_tw": {"2330": [10, 1], "0050": [20, 0], "1234": [5, 0], "9999": [0, 3]},
           "q_tw": {"2330": [1, 1, 1, 100.0], "0050": [1, 1, 1, 50.0], "9999": [1, 1, 1, 9.0]}}
    v, n, k = M.official_day(doc)                                 # 1234 沒有收盤：不算
    assert (v, n, k) == (10 * 1000 * 100.0 + 20 * 1000 * 50.0, 30, 2)
    r, cov = M.ratio(v, n, money=1_200_000.0, total_n=31)
    assert cov == pytest.approx(30 / 31)
    assert r == pytest.approx(v / 30 * 31 / 1_200_000.0 * 100)    # 每張平均市值 × 官方張數 ÷ 融資金額
    assert M.ratio(v, n, money=1.0, total_n=100) is None           # 涵蓋率 0.3：不算
    assert M.official_day({"m_tw": {}, "q_tw": {}}) is None


def test_build_series_switches_to_official_after_end():
    agg_doc = {"end": "2026-07-14", "d": {"2026-07-13": [900.0, 9, 3, 100.0, 1, 1], "2026-07-14": [1000.0, 10, 3, 0, 0, 0]}}
    margin = {"2026-07-13": [600.0, 10, 0], "2026-07-14": [500.0, 10, 0], "2026-07-15": [400.0, 4, 0],
              "2026-07-16": [400.0, 4, 0]}
    shards = {"2026-07-15": {"m_tw": {"2330": [4, 0]}, "q_tw": {"2330": [0, 0, 0, 0.2]}}}
    s = M.build_series(agg_doc, margin, shards)
    assert s["2026-07-13"] == [round(1000.0 / 600 * 100, 2), 1.0, 0]
    assert s["2026-07-14"] == [200.0, 1.0, 0]
    assert s["2026-07-15"] == [200.0, 1.0, 1]                       # 4 張 × 1000 × 0.2 ＝ 800 ÷ 400
    assert "2026-07-16" not in s                                   # 分片沒有：不算


def test_pacer_spaces_requests():
    t = [0.0]
    slept = []

    def clock():
        return t[0]

    def sleep(dt):
        slept.append(dt)
        t[0] += dt

    p = M.Pacer(per_hour=360, clock=clock, sleep=sleep)            # 每 10 秒一個
    p.wait()
    t[0] += 3.0
    p.wait()
    t[0] += 12.0
    p.wait()
    assert slept == [pytest.approx(7.0)] and p.n == 3


def _fake_get(table, calls):
    def get(url):
        calls.append(url)
        ds = url.split("dataset=")[1].split("&")[0]
        code = url.split("data_id=")[1].split("&")[0]
        v = table.get((ds, code))
        if isinstance(v, Exception):
            raise v
        return json.dumps({"status": 200, "msg": "success", "data": v or []}).encode()
    return get


def test_backfill_resumes_and_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(M.store, "LAB", tmp_path)
    mgr = "TaiwanStockMarginPurchaseShortSale"
    table = {
        (mgr, "2330"): [{"date": "2020-01-02", "MarginPurchaseTodayBalance": 10},
                        {"date": "2020-01-03", "MarginPurchaseTodayBalance": 12}],
        ("TaiwanStockPrice", "2330"): [{"date": "2020-01-02", "close": 300.0}, {"date": "2020-01-03", "close": 310.0}],
        (mgr, "0050"): [{"date": "2020-01-03", "MarginPurchaseTodayBalance": 5}],
        ("TaiwanStockPrice", "0050"): [{"date": "2020-01-03", "close": 90.0}],
        (mgr, "9105"): [],                                            # 沒有融資：只花一個請求、記 skip
        (mgr, "1234"): RuntimeError("GET 失敗：HTTP Error 402: Payment Required"),
    }
    calls = []
    uni = [("2330", "2020-01-03", None), ("9105", None, None), ("0050", None, None), ("1234", None, None)]
    st = M.backfill(uni, end="2020-01-03", budget_s=60, per_hour=10 ** 9, get=_fake_get(table, calls), today="2020-01-05")
    assert st["done"] == 2 and st["empty"] == 1 and st["quota"] and st["left"] == 1
    agg, done = M.load_agg(), M.load_done()
    assert agg["end"] == "2020-01-03"
    assert agg["d"] == {"2020-01-03": [12 * 1000 * 310, 12, 1, 5 * 1000 * 90, 5, 1]}   # 2330 上市日 01-03 之前不算
    assert set(done["codes"]) == {"2330", "0050"} and "9105" in done["skip"]
    # 第二輪：做過的不再請求
    table[(mgr, "1234")] = [{"date": "2020-01-03", "MarginPurchaseTodayBalance": 1}]
    table[("TaiwanStockPrice", "1234")] = [{"date": "2020-01-03", "close": 10.0}]
    calls.clear()
    st = M.backfill(uni, end="2020-01-03", budget_s=60, per_hour=10 ** 9, get=_fake_get(table, calls), today="2020-01-05")
    assert st["done"] == 1 and st["left"] == 0 and all("data_id=1234" in u for u in calls)
    assert M.load_agg()["d"]["2020-01-03"] == [12 * 1000 * 310 + 10000, 13, 2, 5 * 1000 * 90, 5, 1]
    with pytest.raises(ValueError):
        M.backfill(uni, end="2020-02-01", budget_s=60, get=_fake_get(table, calls))     # 截止日不能中途改


def test_universe_live_delisted_transfer_and_order():
    """規則照 2026-10-21 探針看到的 FinMind 總覽：日期不可靠，上市中以官方分片為準。"""
    info = [
        {"stock_id": "2330", "type": "twse", "industry_category": "半導體業", "date": "2026-10-21"},
        {"stock_id": "3008", "type": "twse", "industry_category": "光電業", "date": "2026-10-21"},   # 上櫃轉上市
        {"stock_id": "0050", "type": "twse", "industry_category": "ETF", "date": "2026-10-21"},
        {"stock_id": "9105", "type": "twse", "industry_category": "存託憑證", "date": "2024-12-04"},  # 還在上市、總覽日期舊
        {"stock_id": "6488", "type": "tpex", "industry_category": "半導體業", "date": "2026-10-21"},  # 上櫃：不算
        {"stock_id": "2325", "type": "twse", "industry_category": "半導體業", "date": "2026-07-12"},  # 已終止上市
        {"stock_id": "020011", "type": "twse", "industry_category": "ETN", "date": "2026-10-21"},     # ETN：不算
        {"stock_id": "TAIEX", "type": "twse", "industry_category": "Index", "date": "2026-10-21"},
    ]
    dl = [{"stock_id": "2325", "date": "2018-04-30"}, {"stock_id": "00732", "date": "2023-04-21"}]
    m_tw = {"2330": [34401, 14], "0050": [24187, 0], "3008": [500, 0], "9105": [44911, 0]}
    off = {"2325": "2018-04-30", "2019": "2001-01-20"}                # 證交所終止上市名單（2019 不在總覽裡也要算）
    u = M.universe(info, dl, off, listed={"2330": "1994-09-05", "3008": "2002-03-11"}, m_tw=m_tw, today="2026-10-21")
    assert u["codes"] == [["9105", None, None], ["2330", "1994-09-05", None], ["0050", None, None],
                          ["3008", "2002-03-11", None], ["2019", None, "2001-01-20"], ["2325", None, "2018-04-30"]]
    assert (u["n"], u["n_live"], u["n_off"]) == (6, 4, 2)


def test_twse_delisted_parses_roc_dates():
    doc = {"stat": "OK", "fields": ["終止上市日期", "公司名稱", "上市編號"],
           "data": [["107/04/30", "矽品", "2325"], ["105/12/06", "華亞科", "3474"], ["115/01/02", "<b>某ETF</b>", "00123A"]]}
    got = M.twse_delisted(get=lambda url: json.dumps(doc).encode())
    assert got == {"2325": "2018-04-30", "3474": "2016-12-06", "00123A": "2026-01-02"}
    assert M.twse_delisted(get=lambda url: (_ for _ in ()).throw(RuntimeError("403"))) == {}


def test_backfill_waits_out_quota_then_continues(tmp_path, monkeypatch):
    monkeypatch.setattr(M.store, "LAB", tmp_path)
    mgr = "TaiwanStockMarginPurchaseShortSale"
    state = {"n": 0}

    def get(url):
        if "data_id=2330" in url and mgr in url and state["n"] == 0:
            state["n"] += 1
            return json.dumps({"status": 402, "msg": "Requests reach the upper limit."}).encode()
        if mgr in url:
            return json.dumps({"status": 200, "data": [{"date": "2020-01-03", "MarginPurchaseTodayBalance": 2}]}).encode()
        return json.dumps({"status": 200, "data": [{"date": "2020-01-03", "close": 5.0}]}).encode()

    slept = []
    st = M.backfill([("2330", None, None)], end="2020-01-03", budget_s=10_000, per_hour=10 ** 9, get=get,
                    today="2020-01-05", quota_wait=900, sleep=slept.append)
    assert slept == [900] and st["quota"] and st["done"] == 1 and st["left"] == 0
    assert M.load_agg()["d"]["2020-01-03"] == [10000, 2, 1, 0, 0, 0]
