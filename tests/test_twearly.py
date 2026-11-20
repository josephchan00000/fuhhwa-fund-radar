"""台股早年官方每日行情（arm/lab/twearly.py；docs/lab_earnings_plan.md 第 14 節第 1 段）。假資料照證交所、櫃買 rwd 的格式。"""
from arm.lab import store
from arm.lab import twearly as E


def _mi(rows):
    return {"tables": [{"fields": ["證券代號", "證券名稱", "成交股數", "收盤價", "漲跌(+/-)", "漲跌價差"], "data": rows}]}


def test_parse_tw_signs_and_x():
    q = E.parse_tw(_mi([["2330", "台積電", "1,000", "60.50", "<p style= color:red>+</p>", "1.50"],
                        ["2317", "鴻海", "1,000", "120.00", "<p style= color:green>-</p>", "2.00"],
                        ["1101", "台泥", "1,000", "20.00", "<p> </p>", "0.00"],
                        ["2002", "中鋼", "1,000", "30.00", "<p>X</p>", "0.00"],
                        ["0050", "元大台灣50", "1,000", "--", "", ""]]))
    assert q == {"2330": [60.5, 1.5], "2317": [120.0, -2.0], "1101": [20.0, 0.0], "2002": [30.0, None]}


def test_parse_tp_with_and_without_header():
    q = E.parse_tp({"tables": [{"fields": ["代號", "名稱", "收盤", "漲跌", "開盤", "發行股數"],
                                "data": [["5347", "世界", "50.10", "+0.60", "49.5", "1,000,000"], ["6488", "環球晶", "---", "0", "", ""]]}]})
    assert q == {"5347": [50.1, 0.6, 1000000]}
    q2 = E.parse_tp({"aaData": [["5347", "世界", "50.10", "-0.40", "49.5"]]})
    assert q2 == {"5347": [50.1, -0.4, None]}


def test_put_keeps_columns_aligned():
    doc = {"t": [], "c": {}, "g": {}, "sh": {}, "miss": [], "err": {}}
    E._put(doc, "2004-02-12", {"2330": [60.0, 1.0]})
    E._put(doc, "2004-02-11", {"2330": [59.0, 0.5], "2317": [100.0, None]})
    assert doc["t"] == ["2004-02-11", "2004-02-12"]
    assert doc["c"] == {"2330": [59.0, 60.0], "2317": [100.0, None]} and doc["g"]["2317"] == [None, None]


def test_run_resumes_and_records_month_end(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(E, "TW_START", "2004-02-26")
    monkeypatch.setattr(E, "END", "2004-03-02")
    calls = []

    def ftw(d):
        calls.append(d)
        return ({f"{1000 + k}": [10.0 + k, 0.1] for k in range(120)}, "ok") if d != "2004-03-01" else (None, "nodata")
    monkeypatch.setattr(E, "fetch_tw", ftw)
    monkeypatch.setattr(E, "fetch_tw_shares", lambda d: ({"1000": 5_000_000}, "ok"))
    st = E.run(mkts=("tw",))
    assert st["tw"] == {"ok": 3, "miss": 1, "err": 0, "left": 0}         # 2/26、2/27、3/2；3/1 查無＝休市
    doc = store.read(E.KIND, "tw-2004")
    assert doc["t"] == ["2004-02-26", "2004-02-27", "2004-03-02"] and len(doc["c"]["1000"]) == 3
    assert list(doc["sh"]) == ["2004-02-27", "2004-03-02"] and doc["miss"] == ["2004-03-01"]   # 範圍內兩個月都齊了
    n = len(calls)
    E.run(mkts=("tw",))
    assert len(calls) == n                                            # 抓過的不再抓
    cov = E.coverage()
    assert cov["tw-2004"]["days"] == 3 and cov["tw-2004"]["me"] == 2 and cov["tw-2004"]["miss"] == 1


def test_month_end_uses_last_trading_day_when_last_weekday_is_closed():
    doc = {"t": ["2004-04-28", "2004-04-29"], "miss": ["2004-04-30"], "sh": {}}
    days = ["2004-04-28", "2004-04-29", "2004-04-30"]
    assert E.month_ends(doc, days) == {"2004-04": "2004-04-29"}
    assert E.month_ends({"t": ["2004-04-28"], "miss": [], "sh": {}}, days) == {}        # 還沒齊
