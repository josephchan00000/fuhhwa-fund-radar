"""美股財報季（arm/lab/earnusdata.py 抓、arm/lab/earnus.py 算；規格 arm/lab/ernusspec.py VER 1）。
假資料照 2026-11-20 資料探針（scripts/probe_earnus.py）印出來的 Yahoo、那斯達克格式。"""
import json
from datetime import datetime, timezone

from arm.lab import earnus as E
from arm.lab import earnusdata as D
from arm.lab import ernusspec as S


def _ts(s):                                                   # 美東時間字串 → Yahoo 的 {"raw": 秒}
    from zoneinfo import ZoneInfo
    return {"raw": int(datetime.fromisoformat(s).replace(tzinfo=ZoneInfo("America/New_York")).timestamp())}


def _qs():
    """CROX 的樣子：第三季 10/29 盤前 07:00 公布。"""
    ch = [{"date": "4Q2025", "actual": {"raw": 2.29}, "estimate": {"raw": 1.91358}, "periodEndDate": {"fmt": "2025-12-31"},
           "reportedDate": _ts("2026-02-12T07:00")},
          {"date": "3Q2026", "actual": {"raw": 3.69}, "estimate": {"raw": 3.30948}, "periodEndDate": {"fmt": "2026-09-30"},
           "reportedDate": _ts("2026-10-29T07:00")}]
    fc = [{"date": "4Q2025", "revenue": {"raw": 957640000}, "earnings": {"raw": 105165000}},
          {"date": "3Q2026", "revenue": {"raw": 1042583000}, "earnings": {"raw": 216755000}}]
    return {"quoteSummary": {"result": [{
        "earnings": {"earningsChart": {"quarterly": ch}, "financialsChart": {"quarterly": fc}},
        "earningsHistory": {"history": [{"quarter": {"fmt": "2026-06-30"}, "epsActual": {"raw": 4.55}, "epsEstimate": {"raw": 4.34798}}]},
        "earningsTrend": {"trend": [{"period": "0q", "endDate": "2026-12-31",
                                     "earningsEstimate": {"avg": {"raw": 3.39596}, "numberOfAnalysts": {"raw": 13}},
                                     "revenueEstimate": {"avg": {"raw": 1033356450}, "numberOfAnalysts": {"raw": 12}}}]},
        "calendarEvents": {"earnings": {"earningsDate": [{"fmt": "2027-02-11"}], "isEarningsDateEstimate": True}},
        "incomeStatementHistoryQuarterly": {"incomeStatementHistory": [
            {"endDate": {"fmt": "2026-06-30"}, "totalRevenue": {"raw": 1179468000}, "grossProfit": {"raw": 0}}]}}]}}


def test_parse_quote_summary():
    o = D.parse_qs(_qs())
    q = o["q"]
    assert q["2026-09-30"] == {"rt": "2026-10-29T07:00", "ea": 3.69, "ee": 3.3095, "rev": 1042583000, "ni": 216755000}
    assert q["2026-06-30"] == {"ea": 4.55, "ee": 4.348, "rev": 1179468000}       # earningsHistory 補 EPS、損益表補營收
    assert o["q0"] == {"end": "2026-12-31", "e": 3.396, "en": 13, "r": 1033356450, "rn": 12}
    assert o["ed"] == ["2027-02-11"] and o["ede"] is True


def test_parse_timeseries_and_merge():
    ts = D.parse_ts({"timeseries": {"result": [
        {"meta": {"type": ["quarterlyTotalRevenue"]}, "quarterlyTotalRevenue": [
            {"asOfDate": "2025-09-30", "periodType": "3M", "reportedValue": {"raw": 996301000.0}}, None]},
        {"meta": {"type": ["quarterlyNetIncome"]}, "quarterlyNetIncome": [
            {"asOfDate": "2025-09-30", "periodType": "3M", "reportedValue": {"raw": 145816000.0}},
            {"asOfDate": "2025-12-31", "periodType": "3M", "reportedValue": {"raw": 999.0}}]}]}})
    assert ts == {"2025-09-30": {"rev": 996301000.0, "ni": 145816000.0}, "2025-12-31": {"ni": 999.0}}
    m = D.merge_q({"2025-06-30": {"rev": 1}}, D.parse_qs(_qs())["q"], ts)
    assert m["2025-12-31"]["ni"] == 105165000                 # 季資料只補缺的
    assert list(m)[0] == "2025-06-30" and len(m) == 5


def test_snapshot_freezes_after_report():
    q0 = {"end": "2026-12-31", "e": 3.4, "en": 13, "r": 1.03e9, "rn": 12}
    sn = D.snapshot({}, {}, q0, "2026-11-19", "2026-11-20T05:00")
    assert sn["2026-12-31"]["r"] == 1.03e9 and sn["2026-12-31"]["d"] == "2026-11-19"
    q = {"2026-12-31": {"rt": "2027-02-11T07:00"}}
    sn2 = D.snapshot(sn, q, dict(q0, r=1.1e9), "2027-02-11", "2027-02-11T08:00")
    assert sn2["2026-12-31"]["r"] == 1.03e9                    # 公布時間過了：不改


def test_events_window_and_p1m():
    ds = [f"2026-10-{d:02d}" for d in (23, 24, 27, 28, 29, 30)] + ["2026-11-02", "2026-11-03"]
    cs = [100, 101, 102, 119.69, 150.52, 151, 150, 149]
    q = {"2026-09-30": {"rt": "2026-10-29T07:00"}}
    ev = D.events({}, q, ds, cs)
    assert ev["2026-09-30"][0] == ["2026-10-24", 101] and ev["2026-09-30"][-1] == ["2026-11-03", 149]
    assert D.events(ev, q, ds[:2], cs[:2]) == ev              # 後面湊齊了：不再改
    assert D.p1m(ds, cs) is None and D.p1m(list(range(30)), list(range(1, 31)))[1] == [8, 9]


def test_nq_need_and_keep():
    S_ = {"CROX": {"q": {"2026-09-30": {"rt": "2026-10-29T07:00"}}}}
    assert D.nq_need(S_, {}, [], "2026-11-20") == ["2026-10-29", "2026-10-30"]
    assert D.nq_need(S_, {}, ["2026-10-29", "2026-10-30"], "2026-11-20") == []
    assert D.nq_need(S_, {"2026-10-29": {"CROX": [None, 3.3, 9, "Sep/2026"]}}, ["2026-10-29", "2026-10-30"], "2026-10-31") == ["2026-10-29"]
    assert D.nq_keep([["BRK/B", 1.0, 0.9, 3, "Sep/2026"], ["XYZ", 1, 1, 1, ""]], {"BRK.B"}) == {"BRK.B": [1.0, 0.9, 3, "Sep/2026"]}


def test_update_writes_once_per_close(tmp_path):
    p = tmp_path / "raw.json"
    now = datetime(2026, 11, 20, 0, 30, tzinfo=timezone.utc)                       # 美東 11/19 19:30，收盤後
    calls = []

    def fetch(Y, c, at, now_):
        calls.append(c)
        return c, {"qs": D.parse_qs(_qs()), "ts": {}, "ds": ["2026-10-28", "2026-10-29"], "cs": [119.69, 150.52]}, "ok"

    def nq(d):
        return d, ([["CROX", 3.69, 3.31, 9, "Sep/2026"]] if d == "2026-10-29" else []), "ok"
    st = D.update(["CROX"], now=now, Y=object(), fetch=fetch, nq_fetch=nq, path=p, made="2026-11-20")
    assert st["ok"] == 1 and st["changed"] and calls == ["CROX"]
    doc = json.loads(p.read_text())
    assert doc["at"] == "2026-11-19" and doc["nq"] == {"2026-10-29": {"CROX": [3.69, 3.31, 9, "Sep/2026"]}}
    assert "2026-12-31" in doc["s"]["CROX"]["snap"] and doc["s"]["CROX"]["ev"]["2026-09-30"][-1] == ["2026-10-29", 150.52]
    st2 = D.update(["CROX"], now=now, Y=object(), fetch=fetch, nq_fetch=nq, path=p, made="2026-11-20")
    assert "skip" in st2 and calls == ["CROX"]                 # 同一個收盤不再抓


def test_quarter_mapping_and_season():
    assert E.cq("2026-10-31") == "2026-09-30" and E.cq("2026-01-31") == "2025-12-31" and E.cq("2026-12-31") == "2026-12-31"
    assert E.season("2026-11-20") == "2026-09-30" and E.season("2027-01-10") == "2026-09-30" and E.season("2027-01-15") == "2026-12-31"


def test_beat_two_sources():
    assert E.beat(3.69, 3.31) == "hi" and E.beat(0.46, 0.52) == "lo" and E.beat(1.34, 1.33) == "ok" and E.beat(0.10, 0.105) == "ok"
    raw = {"q": {"2026-09-30": {"rt": "2026-10-29T07:00", "ea": 3.69, "ee": 3.31, "rev": 1042.6, "ni": 216.8},
                 "2025-09-30": {"rev": 996.3, "ni": 145.8}},
           "snap": {"2026-09-30": {"r": 1000.0, "d": "2026-10-28"}},
           "ev": {"2026-09-30": [["2026-10-27", 102], ["2026-10-28", 119.69], ["2026-10-29", 150.52], ["2026-10-30", 151]]},
           "p1m": [["2026-11-19", 157.31], ["2026-10-21", 110.0]]}
    r = E.company("CROX", raw, {"2026-10-29": {"CROX": [3.69, 3.30, 9, "Sep/2026"]}}, "2026-09-30", "2026-11-19T20:00")
    assert r["in"] and r["eps"]["k"] == "hi" and r["eps"]["src"] == "both"
    assert r["revb"] == {"k": "hi", "p": 4.3, "est": 1000.0, "d": "2026-10-28"}
    assert r["rev_yoy"] == 4.6 and r["ni_yoy"] == 48.7 and E.growth(r) == "up"
    assert r["react"] == {"f": "2026-10-28", "t": "2026-10-29", "p": 25.8, "k": "pre"}          # 盤前：前一天收盤 → 當天收盤
    assert r["px1m"] == 43.0
    r2 = E.company("CROX", raw, {"2026-10-29": {"CROX": [3.30, 3.31, 9, "Sep/2026"]}}, "2026-09-30", "2026-11-19T20:00")
    assert r2["eps"]["k"] == "mix" and r2["eps"]["n"][:2] == [3.30, 3.31]                      # 兩家不一致：寫兩邊
    r3 = E.company("CROX", dict(raw, snap={}), {}, "2026-09-30", "2026-11-19T20:00")
    assert r3["eps"]["src"] == "yahoo" and r3["revb"] == {"k": "nosnap"}
    r4 = E.company("CROX", raw, {}, "2026-12-31", "2026-11-19T20:00")
    assert r4["in"] is False and r4["last"][0] == "2026-09-30"


def test_react_after_close_and_loss_text():
    ev = [["2026-11-18", 140.0], ["2026-11-19", 145.98], ["2026-11-20", 150.0]]
    assert E.react(ev, "2026-11-19T16:20") == {"f": "2026-11-19", "t": "2026-11-20", "p": 2.8, "k": "post"}
    assert E.react(ev, "2026-11-19T12:00")["f"] == "2026-11-18"
    assert E.react(ev[:2], "2026-11-19T16:20") is None                                        # 隔天還沒收盤
    assert E.ni_yoy(5, -1) == (None, "轉盈") and E.ni_yoy(-1, 5) == (None, "轉虧") and E.ni_yoy(-1, -2) == (None, "虧損")


def test_members_exclude_etfs_and_merge_share_classes(tmp_path):
    import shutil
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "funds").mkdir(parents=True)
    prof = {"profiles": {
        "ALPHABET A": {"country": "美國", "ticker": "GOOGL", "intro": "美國 Alphabet，搜尋"},
        "ALPHABET C": {"country": "美國", "ticker": "GOOG", "intro": "美國 Alphabet，搜尋"},
        "iShares ACWI ETF": {"country": "美國", "ticker": "ACWI", "intro": "iShares MSCI ACWI ETF（ACWI），追蹤"},
        "BLACKROCK": {"country": "美國", "ticker": "BLK", "intro": "美國貝萊德（BlackRock），資產管理；旗下 iShares ETF"},
        "台積電": {"country": "台灣", "ticker": "2330", "intro": "台灣台積電，晶圓代工"}}}
    (tmp_path / "config" / "holding_profiles.json").write_text(json.dumps(prof, ensure_ascii=False))
    f = {"short_name": "某基金", "top_holdings": [{"name": n, "weight": 3.0} for n in prof["profiles"]]}
    (tmp_path / "data" / "funds" / "x.json").write_text(json.dumps(f, ensure_ascii=False))
    (tmp_path / "data" / "etf_holdings.json").write_text(json.dumps({"etfs": {}}))
    M = E.members(tmp_path)
    assert "GOOG" not in M and "ACWI" not in M and "BLK" in M and "2330" not in M
    assert M["GOOGL"]["who"][0] == ["某基金", 6.0]                                           # 兩種股別比重相加
    shutil.rmtree(tmp_path / "config")


def test_summary_counts():
    rows = {"A": {"in": True, "eps": {"k": "hi"}, "revb": {"k": "nosnap"}, "ni_yoy": 20.0, "react": {"p": 3.0}},
            "B": {"in": True, "eps": {"k": "mix"}, "revb": {"k": "lo"}, "ni_txt": "轉虧", "react": {"p": -5.0}},
            "C": {"in": False, "ed": ["2026-11-25"], "ede": False}, "D": {"in": False, "ed": ["2027-02-01"]}}
    s = E.summary(rows, "2026-11-20")
    assert s["in"] == 2 and s["eps"]["hi"] == 1 and s["eps"]["mix"] == 1 and s["rev"]["lo"] == 1 and s["rev"]["nosnap"] == 1
    assert s["g"] == {"up": 1, "flat": 0, "dn": 1, "na": 0} and s["rx"] == {"up": 1, "dn": 1, "n": 2, "med": -1.0}
    assert s["upcoming"] == [["2026-11-25", "C", False]]
    assert S.VER == 1


def _usdoc():
    raw = {"q": {"2026-09-30": {"rt": "2026-10-29T07:00", "ea": 3.69, "ee": 3.31, "rev": 1042583000, "ni": 216755000},
                 "2025-09-30": {"rev": 996301000, "ni": 145816000}},
           "ev": {"2026-09-30": [["2026-10-28", 119.69], ["2026-10-29", 150.52]]}, "p1m": [["2026-11-19", 157.31], ["2026-10-21", 118.0]]}
    rows = {"CROX": E.company("CROX", raw, {"2026-10-29": {"CROX": [3.30, 3.31, 9, "Sep/2026"]}}, "2026-09-30", "2026-11-19T20:00"),
            "WMT": {"q": "2026-09-30", "in": False, "ed": ["2026-11-25"], "ede": False, "last": ["2026-07-31", "2026-08-20T07:00"]}}
    rows["CROX"].update({"n": "卡駱馳", "ind": "休閒鞋品牌商", "who": [["美股強勢品質股", None]]})
    rows["WMT"].update({"n": "沃爾瑪", "ind": "零售", "who": [["某基金", 2.0], ["00409A", 1.0]]})
    return {"q": "2026-09-30", "made": "2026-11-20", "at": "2026-11-19", "rows": rows, "sum": E.summary(rows, "2026-11-20")}


def test_page_us_pane_and_switch():
    from arm.lab import earnpage as P
    tw = {"q": "2026-09-30", "made": "2026-11-20", "rows": {"2881": {"n": "富邦金", "q": "2026-09-30", "in": False, "who": [["復華", 3.0]]}},
          "sum": {"n": 1, "in": 0, "out": ["2881"], "eps": {"up": 0, "flat": 0, "dn": 0, "na": 0}, "fy": {"lo": 0, "ok": 0, "hi": 0, "na": 0},
                  "decel": 0, "stale": 0, "suspect": [], "med_rev": None}}
    h = P.block(tw, _usdoc())
    assert h.count('id="ern-root"') == 1 and 'class="ern-mkt"' in h and '<div class="ern-pane" data-m="us" hidden>' in h
    assert "財報季・2026 第三季（美股）" in h and "美股 11/19 收盤的資料" in h and "已公布 1 家、還沒公布 1 家" in h
    assert "接下來兩週：沃爾瑪 11/25" in h and "EPS 兩家不一致</span>" in h and "那斯達克實際 <b>3.30</b>" in h
    assert "10/29（四）盤前公布" in h and "財報後股價（10/28 收盤 → 10/29 收盤）" in h and "+26%" in h
    assert "沒有公布前的營收預估紀錄" in h and "第三季還沒公布；下次財報 11/25（三）" in h and "上一次公布是 8/20" in h
    for i in ("ern-grp", "ern-q", "ern-n", "ern-fs"):                     # 兩個市場的控制項 id 不重複
        assert h.count(f'id="{i}"') == 1 and h.count(f'id="{i}-us"') == 1
    for w in ("保證", "必漲", "必跌", "建議買", "建議賣", "目標價", "會漲", "會跌"):
        assert w not in h
    only = P.block(tw)                                                    # 沒有美股：只有台股、沒有切換
    assert 'class="ern-mkt"' not in only and 'data-m="tw"' in only
    assert "querySelectorAll('.ern-pane')" in P.JS and "ernMk" in P.JS
