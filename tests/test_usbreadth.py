"""美股漲跌家數（arm/lab/usbreadth.py）：成分股期間、分割還原、成交金額與點數、報價補當天（盤中不收）。"""
import pytest

from arm.lab import usbreadth as U


def test_parse_spans():
    text = "ticker,start_date,end_date\nAAL,1996-01-02,1997-01-15\nBRK.B,2010-02-16,\nA,2000-06-05,\n"
    assert U.parse_spans(text) == [("AAL", "1996-01-02", "1997-01-15"), ("BRK-B", "2010-02-16", None),
                                   ("A", "2000-06-05", None)]


def _chart(days, closes, vols, splits=None, off=-14400):
    import calendar
    ts = [calendar.timegm(tuple(int(x) for x in d.split("-")) + (13, 30, 0)) for d in days]
    ev = {}
    for d, num, den in (splits or []):
        t = calendar.timegm(tuple(int(x) for x in d.split("-")) + (13, 30, 0))
        ev[str(t)] = {"date": t, "numerator": num, "denominator": den}
    return {"chart": {"result": [{"meta": {"gmtoffset": off}, "timestamp": ts,
                                  "events": {"splits": ev} if ev else {},
                                  "indicators": {"quote": [{"close": closes, "volume": vols}]}}]}}


def test_parse_chart_split_factor():
    doc = _chart(["2020-08-28", "2020-08-31", "2020-09-01"], [125.0, 129.0, None], [100, 200, 300],
                 splits=[("2020-08-31", 4, 1)])
    h = U.parse_chart(doc)
    assert h == {"2020-08-28": (125.0, 100.0, 4.0), "2020-08-31": (129.0, 200.0, 1.0)}   # 分割當天以後倍數 1


def test_aggregate_membership_gap_and_values():
    cal = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-20"]
    spans = [("A", "2020-01-03", None), ("B", "2020-01-02", "2020-01-07"), ("C", "2020-01-02", None)]
    hist = {
        "A": {"2020-01-02": (10.0, 5, 1.0), "2020-01-03": (11.0, 5, 1.0), "2020-01-06": (11.0, 5, 1.0),
              "2020-01-07": (10.0, 10, 1.0), "2020-01-20": (12.0, 1, 1.0)},
        "B": {"2020-01-02": (20.0, 1, 2.0), "2020-01-03": (19.0, 2, 2.0), "2020-01-06": (21.0, 3, 2.0),
              "2020-01-07": (22.0, 4, 2.0)},
    }
    out = U.aggregate(spans, hist, cal)
    # 01-03：A 上漲（成分股從今天起）、B 下跌；01-06：A 平盤、B 上漲；01-07：A 下跌（B 已離開）；01-20：和前一筆隔 13 天 → 不算
    assert out["2020-01-03"] == [1, 1, 0, 55, 38, 1.0, 2.0, 2, 3]       # B 點數＝(19−20)×2
    assert out["2020-01-06"] == [1, 0, 1, 63, 0, 4.0, 0.0, 2, 3]
    assert out["2020-01-07"] == [0, 1, 0, 0, 100, 0.0, 1.0, 1, 2]
    assert "2020-01-02" not in out and "2020-01-20" not in out          # 沒有前一天／隔太久


def test_day_row_skips_intraday_and_thin():
    q = {"A": {"t": "2026-10-19", "chg": 1.0, "px": 10.0, "vol": 5, "st": "POST"},
         "B": {"t": "2026-10-19", "chg": -2.0, "px": 20.0, "vol": 1, "st": "PRE"},
         "C": {"t": "2026-10-19", "chg": 0.0, "px": 5.0, "vol": 2, "st": "CLOSED"}}
    assert U.day_row(q, ["A", "B", "C"], "2026-10-19") == [1, 1, 1, 50, 20, 1.0, 2.0, 3, 3]
    q["A"]["st"] = "REGULAR"
    assert U.day_row(q, ["A", "B", "C"], "2026-10-19") is None          # 盤中：A 不算，只剩 2/3 不到九成
    assert U.day_row(q, ["A", "B", "C"], "2026-10-20") is None


def test_parse_quotes():
    doc = {"quoteResponse": {"result": [
        {"symbol": "AAPL", "regularMarketTime": 1792526400, "gmtOffSetMilliseconds": -14400000,
         "regularMarketChange": 1.5, "regularMarketPrice": 250.0, "regularMarketVolume": 1000, "marketState": "POST"},
        {"symbol": "X", "regularMarketTime": None}]}}
    q = U.parse_quotes(doc)
    assert set(q) == {"AAPL"} and q["AAPL"]["chg"] == pytest.approx(1.5) and q["AAPL"]["st"] == "POST"
    assert q["AAPL"]["t"] == "2026-10-20"                                   # 美東 10/20 16:00
