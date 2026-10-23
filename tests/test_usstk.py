"""美股個股策略資料層（arm/lab/usstk.py）：解析與存檔格式。抓取只在 CI 跑，這裡不連網。"""
import math
from datetime import date

from arm.lab import usstk as U


def test_money_formats():
    assert U.money("$1.76") == 1.76
    assert U.money("($0.60)") == -0.60
    assert U.money("-$0.60") == -0.60
    assert U.money("$-0.60") == -0.60
    assert U.money("$1,234.50") == 1234.5
    assert U.money("N/A") is None
    assert U.money("") is None
    assert U.money(None) is None
    assert U.money(0.5) == 0.5


def test_earn_rows_parses_and_skips_missing_eps():
    doc = {"data": {"rows": [
        {"symbol": "AAPL", "eps": "$1.76", "epsForecast": "$1.61", "noOfEsts": "12", "fiscalQuarterEnding": "Dec/2007"},
        {"symbol": "bac", "eps": "($0.60)", "epsForecast": "($0.54)", "noOfEsts": "N/A", "fiscalQuarterEnding": "Dec/2009"},
        {"symbol": "XYZ", "eps": "", "epsForecast": "$0.10"},
    ]}}
    assert U.earn_rows(doc) == [["AAPL", 1.76, 1.61, 12, "Dec/2007"], ["BAC", -0.6, -0.54, None, "Dec/2009"]]
    assert U.earn_rows({"data": {"rows": None}}) == []          # 那天沒有公司＝查過
    assert U.earn_rows({"status": {"rCode": 400}}) is None      # 格式不對＝不算查過
    assert U.earn_rows("x") is None


def test_px_roundtrip_is_exact_to_1bp_and_does_not_drift():
    ser = {"2008-01-02": 10.0, "2008-01-03": 10.37, "2008-01-07": 9.81, "2008-02-01": 123.456, "2026-10-21": 0.987}
    rec = U.enc_px(ser)
    assert rec["d0"] == "2008-01-02" and rec["dd"][0] == 0 and rec["dd"][2] == 4
    ds, px = U.dec_px(rec)
    assert ds == sorted(ser)
    for d, p in zip(ds, px):
        assert abs(math.log(p / ser[d])) <= 0.5e-4 + 1e-12
    assert U.dec_px({}) == ([], [])


def test_parse_chart_adj_drops_weekend_and_live_bar():
    # 2026-10-23（五）13:30 UTC 開盤、20:00 收盤；現在 15:00 UTC＝交易中 → 當天不收
    off = -14400
    def ts(d, h=13, m=30):
        from datetime import datetime, timezone
        return int(datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc).timestamp())
    days = [date(2026, 10, 22), date(2026, 10, 24), date(2026, 10, 23)]
    doc = {"chart": {"result": [{
        "meta": {"gmtoffset": off, "currentTradingPeriod": {"regular": {"start": ts(days[2]), "end": ts(days[2], 20, 0)}}},
        "timestamp": [ts(d) for d in days],
        "indicators": {"adjclose": [{"adjclose": [100.0, 101.0, 102.0]}]},
    }]}}
    now = ts(days[2], 15, 0)
    assert U.parse_chart_adj(doc, now=now) == {"2026-10-22": 100.0}
    later = ts(days[2], 21, 0)
    assert U.parse_chart_adj(doc, now=later) == {"2026-10-22": 100.0, "2026-10-23": 102.0}


def test_weekdays_pending_and_until(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "DIR", tmp_path)
    assert U.weekdays("2026-10-23", "2026-10-26") == ["2026-10-23", "2026-10-26"]
    assert U.default_until(date(2026, 10, 23)) == "2026-10-20"
    monkeypatch.setattr(U, "EARN_START", "2026-10-19")
    assert U.earn_pending("2026-10-23") == ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
    U.save_earn(2026, {"done": ["2026-10-19", "2026-10-20"], "rows": {"2026-10-19": [["B", 1.0, 0.9, 3, "Sep/2026"],
                                                                                    ["A", 2.0, 2.1, 5, "Sep/2026"]]}})
    doc = U.load_earn(2026)
    assert doc["rows"]["2026-10-19"][0][0] == "A"               # 存檔排序（決定性）
    assert U.earn_pending("2026-10-23") == ["2026-10-21", "2026-10-22", "2026-10-23"]
    b1 = U.earn_path(2026).read_bytes()
    U.save_earn(2026, doc)
    assert U.earn_path(2026).read_bytes() == b1                 # 內容沒變不改寫


def test_spans_and_wanted():
    text = "ticker,start_date,end_date\nAAPL,1996-01-02,\nBRK.B,2010-02-16,\nOLD,1996-01-02,2005-03-01\nMID,1999-01-01,2012-06-01\n"
    sp = U.parse_spans(text)
    assert sp[1] == ["BRK-B", "2010-02-16", None]
    assert U.wanted(sp) == ["AAPL", "BRK-B", "MID"]            # 2008 年以前就離開的不抓


def test_status_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "DIR", tmp_path)
    monkeypatch.setattr(U, "EARN_START", "2026-10-19")
    U.save_meta({"spans": [["AAPL", "1996-01-02", None]], "px_done": {}})
    assert U.status("2026-10-20").startswith("LEFT 財報 2 天、股價 1 檔")
    U.save_meta({"spans": [["AAPL", "1996-01-02", None]], "px_done": {"AAPL": 4000}})
    U.save_earn(2026, {"done": ["2026-10-19", "2026-10-20"], "rows": {}})
    assert U.status("2026-10-20").startswith("DONE")


def test_backfill_marks_stuck_when_a_round_makes_no_progress(tmp_path, monkeypatch):
    """2026-10-23：最後 14 天每次都失敗（不到連續 25 次），job 原地重試 3.5 小時、時間到還會再派一輪。
    一整輪一天都沒查到＝STUCK，workflow 就停、不再派。"""
    import importlib.util
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("backfill_usstk", root / "scripts" / "backfill_usstk.py")
    B = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(B)
    monkeypatch.setattr(B, "STUCK", tmp_path / "stuck.txt")
    monkeypatch.setattr(B.usstk, "load_meta", lambda: {"spans": [["AAPL", "1996-01-02", None]], "px_done": {"AAPL": 1}})
    monkeypatch.setattr(B.usstk, "wanted", lambda spans: ["AAPL"])
    monkeypatch.setattr(B.usstk, "status", lambda: "LEFT 財報 14 天、股價 0 檔")
    runs = iter([{"todo": 14, "ok": 0, "err": 14, "left": 14, "stuck": False},
                 {"todo": 14, "ok": 3, "err": 11, "left": 11, "stuck": False}])
    monkeypatch.setattr(B.usstk, "backfill_earn", lambda budget_s: next(runs))
    monkeypatch.setattr(sys, "argv", ["backfill_usstk.py", "--budget-min", "5"])
    B.main()
    assert "還剩 14 天" in (tmp_path / "stuck.txt").read_text(encoding="utf-8")
    B.main()                                    # 有進展就不算卡住
    assert not (tmp_path / "stuck.txt").exists()
