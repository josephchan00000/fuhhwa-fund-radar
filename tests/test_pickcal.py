"""選股頁的進場行事曆（arm/lab/pickcal.py；docs/lab_pick_page_plan.md 第 2.2 節）。"""
from arm.lab import pickcal as PC


def test_horizon_is_end_of_third_month_after():
    assert PC.horizon("2026-10-28") == "2027-01-31"
    assert PC.horizon("2026-12-01") == "2027-03-31"
    assert PC.horizon("2026-01-31", 1) == "2026-02-28"


def test_week_and_month_ends_follow_official_holidays():
    w = PC.week_ends("tw", "2026-10-28", "2026-11-30")
    assert w[0] == "2026-10-30" and "2026-11-06" in w and all(d > "2026-10-28" for d in w)
    # 2026-10-23 颱風休市（ADHOC）：那一週的最後一個交易日是 10/22
    assert PC.week_ends("tw", "2026-10-19", "2026-10-25") == ["2026-10-22"]
    m = PC.month_ends("tw", "2026-10-28", "2027-01-31")
    assert m == ["2026-10-30", "2026-11-30", "2026-12-31", "2027-01-29"]
    # 美股：感恩節 11/26 休市，那一週週五照常開市
    assert "2026-11-27" in PC.week_ends("spx", "2026-11-20", "2026-11-30")


def _P():
    return {"d": "2026-10-28", "next": "2026-10-29", "wk": "2026-10-22", "hold_n": 60,
            "hold": [{"c": "2330", "n": "台積電", "ent": "2026-08-24", "out": "2026-11-24"},
                     {"c": "2303", "n": "聯電", "ent": "2026-08-24", "out": "2026-11-24"},
                     {"c": "3037", "n": "欣興", "ent": "2026-09-07", "out": "2026-12-08"}],
            "buy": [{"c": "2454", "n": "聯發科", "fill": True}, {"c": "1101", "n": "台泥", "fill": False}]}


def test_boom_events_known_and_weekly_projection():
    ev = PC.boom_events(_P(), "2026-11-30")
    sells = [e for e in ev if e["act"] == "賣出"]
    assert {e["d"] for e in sells} == {"2026-11-24", "2026-12-08"}
    s1 = next(e for e in sells if e["d"] == "2026-11-24")
    assert [i["c"] for i in s1["items"]] == ["2330", "2303"] and not s1["proj"]
    buy = [e for e in ev if e["act"] == "買進" and e["d"] == "2026-10-29"]
    assert len(buy) == 1 and [i["c"] for i in buy[0]["items"]] == ["2454"]          # 現金不夠的不列
    lists = [e["d"] for e in ev if e["act"] == "名單"]
    assert lists[:3] == ["2026-10-30", "2026-11-06", "2026-11-13"]
    for d in lists:                                                                    # 名單隔一個交易日開盤買（推算）
        b = PC.next_day("tw", d)
        assert any(e["act"] == "買進" and e["d"] == b and e["proj"] for e in ev)


def test_v3_projection_sells_on_60th_trading_day():
    live = {"v3l": {"next": {"d": "2026-11-16", "ent": "2026-11-17", "q": "2026-09-30"}}}
    ev = PC.v3_events("v3l", live, "2026-10-28", "2027-06-30", [])
    acts = [(e["d"], e["act"]) for e in ev]
    assert ("2026-11-16", "名單") in acts and ("2026-11-17", "買進") in acts
    sell = PC.nth_day("tw", "2026-11-17", 59)                  # 含買進那天抱 60 個交易日（advice：8/17 買 → 11/13 賣）
    assert ("2026-11-17" < sell) and (sell, "賣出") in acts
    assert PC.nth_day("tw", "2026-08-17", 59) == "2026-11-13"
    assert ("2027-03-31", "名單") in acts                       # 年報：3/31 期限


def test_v7_monthly_swap_and_buy():
    live = {"v7l": {"next": {"d": "2026-11-10", "ent": "2026-11-11"}}}
    ev = PC.v7_events("v7l", live, "2026-10-28", "2027-01-31", [])
    acts = [(e["d"], e["act"]) for e in ev]
    assert ("2026-11-10", "換股") in acts and ("2026-11-11", "買進") in acts
    assert ("2026-12-10", "換股") in acts and ("2027-01-11", "換股") in acts       # 1/10 週日 → 1/11


def test_adv_events_pending_adds_list_day():
    A = {"cal": [{"d": "2026-11-17", "at": "開盤", "k": "v3l", "act": "買進", "items": [], "pending": True, "fix": "2026-11-16"},
                 {"d": "2026-11-13", "at": "收盤", "k": "v3l", "act": "賣出", "items": [{"c": "2330", "n": "台積電"}], "note": "8/17 買進的"},
                 {"d": "2026-11-02", "at": "開盤", "k": "zz", "act": "買進", "items": []}]}
    ev = PC.adv_events(A, {"v3l"})
    assert [(e["d"], e["act"]) for e in ev] == [("2026-11-16", "名單"), ("2026-11-17", "買進"), ("2026-11-13", "賣出")]
    assert ev[0]["proj"] and ev[1]["proj"] and not ev[2]["proj"]


def test_tw_events_dedupe_sort_and_range():
    A = {"last": "2026-10-28", "cal": [
        {"d": "2026-11-10", "at": "收盤", "k": "v7l", "act": "換股", "items": [{"c": "2345", "n": "智邦"}]},
        {"d": "2026-11-11", "at": "開盤", "k": "v7l", "act": "買進", "items": [], "pending": True, "fix": "2026-11-10"}],
        "v3": {"live": {"v7l": {"next": {"d": "2026-11-10", "ent": "2026-11-11"}}}}}
    T = PC.tw_events(A, _P(), None, ["boom", "v7l"], "2026-10-28")
    ev = T["ev"]
    assert T["end"] == "2027-01-31" and all("2026-10-28" < e["d"] <= T["end"] for e in ev)
    assert not any(e["d"] == "2026-11-10" and e["k"] == "v7l" and e["act"] == "名單" for e in ev)   # 換股那天不另列名單
    sw = [e for e in ev if e["d"] == "2026-11-10" and e["act"] == "換股"]
    assert len(sw) == 1 and sw[0]["items"]                                                         # 有股票的那一筆留下
    keys = [(e["d"], {"開盤": 0, "": 1, "收盤": 2}[e["at"]]) for e in ev]
    assert keys == sorted(keys)


def test_us_events_sells_buys_lists_and_earnings():
    G = {"d": "2026-10-27", "nms": {}, "rows": [{"c": "VLO", "sell": "2026-10-28", "trig": "2026-10-27"},
                                              {"c": "FTNT", "sell": None}],
         "todo": [{"c": "PAYC", "d": "2026-10-28", "w": 0.12}, {"c": "QLYS", "d": "2026-10-28", "w": 0.0}]}
    card = {"s": {"FTNT": {"an": {"ed": ["2026-11-05"], "ede": False}}, "PAYC": {"an": {"ed": ["2026-11-04"], "ede": True}}}}
    T = PC.us_events(G, card, "2026-10-28")
    ev = T["ev"]
    assert any(e["act"] == "賣出" and e["d"] == "2026-10-28" and e["items"][0]["c"] == "VLO" for e in ev)
    b = [e for e in ev if e["act"] == "買進" and e["d"] == "2026-10-28"]
    assert len(b) == 1 and [i["c"] for i in b[0]["items"]] == ["PAYC"]
    assert ("2026-10-30", "名單") in [(e["d"], e["act"]) for e in ev]
    assert ("2026-11-02", "買進") in [(e["d"], e["act"]) for e in ev]
    ern = [e for e in ev if e["act"] == "財報"]
    assert {e["d"] for e in ern} == {"2026-11-04", "2026-11-05"} and all(e["k"] == "ern" for e in ern)
    assert "Yahoo" in next(e for e in ern if e["d"] == "2026-11-04")["note"]


def test_us_events_without_record_is_empty():
    assert PC.us_events({"d": None}, None)["ev"] == []
