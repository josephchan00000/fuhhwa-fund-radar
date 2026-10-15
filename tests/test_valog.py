"""籌碼雷達 v4：推薦順序、機會卡、後台自我驗證紀錄（docs/lab_ia_v4_plan.md 第 4、5 節）。"""
import json
from datetime import datetime

import pytest

from arm.lab import advice, store, v3live, valog


def _g(k, grade, oos=None, ev=None):
    return {"k": k, "grade": grade, "name": k, "has_oos": bool(oos), "oos": oos, "why": ["x"]}


def test_rank_order_reason_and_skip_c_and_hd():
    """推薦順序＝評級總表順序，只排 A、B（高股息不排）；理由只講資料多長、有沒有事後驗證，不出現 t 值。"""
    G = [_g("v3l", "B", {"n": 30, "xe": 8.7, "t": 1.46, "d0": "2014-05-15"}),
         _g("v7l", "B", {"n": 98, "xe": 0.3, "t": 0.67, "d0": "2013-08-12"}),
         _g("s3", "B"), _g("s1", "B"), _g("v3m", "C", {"n": 30, "xe": 0.4, "t": 0.2}), _g("hd", "C")]
    live = {"v3l": {"res": {"all": {"d0": "2014-05-15"}}}, "v7l": {"res": {"all": {"d0": "2013-08-12"}}}}
    old = {"s3": {"event": True, "n": 8, "d0": "2024-10"}, "s1": {"event": False, "n": 42, "d0": "2026-07"}}
    r = advice.rank(G, "2026-10-15", live, old)
    assert r == {"v3l": (1, "12 年資料，事後驗證也贏"), "v7l": (2, "13 年資料，事後驗證偏弱"),
                 "s3": (3, "資料只有 8 次（2024 年起），還沒有事後驗證"), "s1": (4, "資料只有 3 個月，還沒有事後驗證")}
    assert not any("t" in w.replace("st", "") and "值" in w for _, w in r.values())


def test_opps_cards_states_and_capital_dedup():
    """機會卡：待買進／持有中／等名單；摘要的資金不重複計同一檔（取較大部位）。"""
    bk = [{"k": "v3l", "rank": 1, "rank_why": "12 年資料", "name": "財報", "grade": "B", "unit": "次", "exp": {"n": 49},
           "all": {"cagr": 49.5, "tr_cagr": 19.1}},
          {"k": "s3", "rank": 2, "name": "臺灣50", "grade": "B", "unit": "次", "exp": {"n": 8}},
          {"k": "v3m", "rank": None, "name": "財報中型", "grade": "C"}]
    cal = [{"k": "s3", "d": "2026-10-19", "at": "開盤", "act": "買進", "items": [{"c": "1301", "n": "台塑"}, {"c": "2330", "n": "台積電"}]},
           {"k": "v3l", "d": "2026-11-12", "at": "收盤", "act": "賣出", "held": True, "ent": "2026-08-17",
            "items": [{"c": "2330", "n": "台積電", "now_r": 1.2}]},
           {"k": "v3l", "d": "2026-11-17", "at": "開盤", "act": "買進", "items": [], "pending": True, "fix": "2026-11-16"}]
    picks = [{"k": "s3", "c": "1301", "grade": "B", "size": {"pct": 2.0}}, {"k": "s3", "c": "2330", "grade": "B", "size": {"pct": 1.5}},
             {"k": "v3l", "c": "2330", "grade": "B", "size": None}, {"k": "v3m", "c": "2392", "grade": "C", "size": None}]
    o = advice.opps(bk, cal, picks)
    assert [c["k"] for c in o["cards"]] == ["v3l", "s3"]
    v, s = o["cards"]
    assert v["state"] == "持有中" and v["next"]["fix"] == "2026-11-16" and v["all"]["cagr"] == 49.5
    assert s["state"] == "待買進" and s["next"] is None and s["all"] is None
    assert (o["n"], o["nb"], o["nh"], o["fb"]) == (2, 2, 1, "2026-10-19")
    assert o["cap"] == 4          # 台塑 2%＋台積電取大者 2%（s3 1.5%、v3l 沒有部位資料→B 級上限 2%）


def _adv(**kw):
    a = {"last": "2026-10-15", "nxt": "2026-10-16",
         "grades3": [{"k": "v3l", "grade": "B", "rank": 1, "name": "財報驚喜", "why": ["前瞻 0 次"], "fwd": {"n": 0}},
                     {"k": "s1", "grade": "B", "rank": 2, "name": "共識加碼", "why": ["y"], "fwd": {"n": 0}},
                     {"k": "hd", "grade": "C"}],
         "grades": [{"k": "s1", "fwd": {"n": 0}}],
         "book": [{"k": "v3l", "unit": "次", "exp": {"lo": -28.2}, "name": "財報驚喜"},
                  {"k": "s1", "unit": "檔", "exp": {"lo": -13.5}, "name": "共識加碼"}],
         "v3": {"live": {"v3l": {"src": "p3", "fwd": {"units": []}, "due": {"d": "2026-08-14", "ok": True}}}},
         "opp": {"cards": [{"k": "v3l", "held": [{"ent": "2026-08-17", "items": [{"n": "聯電", "now_r": 9.9}, {"n": "台光電", "now_r": -17.0}]}],
                            "buy": []},
                           {"k": "s1", "held": [{"ent": "2026-10-15", "items": [{"n": "國巨", "now_r": -2.9}]}], "buy": []}]},
         "cal": [{"d": "2026-10-16", "at": "開盤", "act": "買進", "k": "s3", "sname": "臺灣50", "items": [{"n": "台塑"}], "tent": True},
                 {"d": "2026-10-16", "at": "收盤", "act": "賣出", "k": "s1", "sname": "共識加碼", "items": [{"n": "國巨"}]},
                 {"d": "2026-10-19", "at": "開盤", "act": "買進", "k": "s5", "sname": "長線", "items": [{"n": "中砂"}]}]}
    a.update(kw)
    return a


def test_snapshot_records_forward_held_and_need():
    st = valog.snapshot(_adv())
    assert set(st) == {"v3l", "s1"}                                   # 高股息不記
    assert st["v3l"]["need"] == 2 and st["s1"]["need"] == 10          # 財報驚喜（p3）＝事件型
    assert st["v3l"]["hn"] == 2 and st["v3l"]["hr"] == pytest.approx(-3.55) and st["v3l"]["deep"] == []
    assert st["s1"]["u"] == "檔" and st["s1"]["miss"] is None


def test_events_transitions_and_stale_every_day():
    adv = _adv()
    cur = valog.snapshot(adv)
    prev = json.loads(json.dumps(cur))
    assert valog.events(cur, prev, "2026-10-15", 0) == []
    # 評級變動、前瞻滿額、前瞻落後、虧損超過歷史最差、該出名單沒出
    cur["v3l"].update(g="C", why="樣本外反向", fn=2, fxe=-1.2, fr=3.0, fmk=4.1, deep=[["8/17 買進的 5 檔平均", -30.0]],
                      miss="2026-11-16")
    ev = valog.events(cur, prev, "2026-11-17", 0)
    assert [e["ty"] for e in ev] == ["grade", "full", "lag", "deep", "miss"]
    assert ev[0]["txt"] == "財報驚喜：評級 B → C（樣本外反向）"
    assert "比同一批股票低 1.20%" in ev[1]["txt"] and "同期大盤 +4.1%" in ev[1]["txt"]
    # 同樣的狀態隔天不再記（只記第一次出現）；資料過期每天都記
    nxt = valog.events(cur, json.loads(json.dumps(cur)), "2026-11-18", 3)
    assert [e["ty"] for e in nxt] == ["stale"] and "3 個交易日" in nxt[0]["txt"]
    # 逐檔計的策略：個別持股跌破歷史最差就記
    cur2 = valog.snapshot(_adv(opp={"cards": [{"k": "s1", "held": [{"items": [{"n": "國巨", "now_r": -15.0}]}], "buy": []}]}))
    e2 = valog.events(cur2, prev, "2026-10-15", 0)
    assert [e["ty"] for e in e2] == ["deep"] and "國巨 −15.0%" in e2[0]["txt"]


def test_lag_days_counts_trading_days_after_close():
    assert valog.lag_days("2026-10-15", datetime(2026, 10, 16, 6, 40)) == 0     # 清晨：最新收盤日＝昨天
    assert valog.lag_days("2026-10-15", datetime(2026, 10, 16, 15, 0)) == 1     # 收盤後：今天算
    assert valog.lag_days("2026-10-15", datetime(2026, 10, 20, 15, 0)) == 3     # 週末不算


def test_push_lines_today_actions_and_events():
    rec = {"todo": valog.todo(_adv()), "ev": []}
    assert valog.push_lines(rec) == ["10/16（五）開盤買進 臺灣50 台塑（試算名單）；收盤賣出 共識加碼 國巨。"]
    rec["ev"] = [{"txt": "資料過期：最新資料 10/15"}]
    assert valog.push_lines(rec)[1] == "策略驗證：資料過期：最新資料 10/15。"
    assert valog.push_lines({"todo": {"d": "2026-10-16", "items": []}}) == ["10/16（五）沒有排定的買賣。"]


def test_update_writes_only_in_ci_one_line_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    now = datetime(2026, 10, 16, 6, 40)
    v = valog.update({"adv": _adv()}, now=now)
    assert not (tmp_path / valog.FP).exists()                          # 本機不寫
    assert v["today"]["push"][0].startswith("10/16（五）") and v["since"] == "2026-10-15"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    valog.update({"adv": _adv()}, now=now)
    txt = (tmp_path / valog.FP).read_text(encoding="utf-8")
    assert txt.count("\n") == 3 and json.loads(txt)["days"]["2026-10-15"]["t"] == "2026-10-16 06:40"
    valog.update({"adv": _adv()}, now=datetime(2026, 10, 16, 7, 15))   # 內容沒變：檔案與時間戳都不動
    assert (tmp_path / valog.FP).read_text(encoding="utf-8") == txt
    # 隔天：和前一天比，評級變了要記
    a2 = _adv(last="2026-10-16", nxt="2026-10-19")
    a2["grades3"][0]["grade"] = "A"
    v2 = valog.update({"adv": a2}, now=datetime(2026, 10, 16, 15, 40))
    assert [e["ty"] for e in v2["today"]["ev"]] == ["grade"] and v2["gh"]["v3l"] == [["2026-10-15", "B"], ["2026-10-16", "A"]]
    doc = json.loads((tmp_path / valog.FP).read_text(encoding="utf-8"))
    assert list(doc["days"]) == ["2026-10-15", "2026-10-16"]


def test_update_keeps_last_n_days(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(valog, "KEEP", 2)
    for d in ("2026-10-13", "2026-10-14", "2026-10-15"):
        valog.update({"adv": _adv(last=d)}, write_file=True, now=datetime(2026, 10, 16, 6, 40))
    assert list(valog.read()["days"]) == ["2026-10-14", "2026-10-15"]


def test_update_reports_missing_advice():
    assert valog.update({"adv": {"err": "boom"}}, write_file=False)["err"] == "boom"


def test_v3live_due_detects_missing_formation():
    cal = ["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14"]
    assert v3live._due("p7", cal, [(2, None, {})]) == {"d": "2026-10-12", "ok": True}
    assert v3live._due("p7", cal, [(0, None, {})]) == {"d": "2026-10-12", "ok": False}
    assert v3live._due("p7", cal[:3], []) is None                      # 形成日當天還沒過一個交易日：不判
    cal3 = ["2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18"]
    assert v3live._due("p3", cal3, [(1, None, {})]) == {"d": "2026-08-14", "ok": True}


def test_v3live_tr_ret_same_period_market():
    cal = ["2026-10-01", "2026-10-02", "2026-10-05"]
    assert v3live._tr_ret({"2026-10-01": 100.0, "2026-10-05": 103.0}, cal, 0, 2) == 3.0
    assert v3live._tr_ret({"2026-10-01": 100.0, "2026-10-02": 102.0}, cal, 0, 2) == 2.0    # 缺值往前找
    assert v3live._tr_ret({}, cal, 0, 2) is None


def test_update_tr_recent_zero_requests_when_current(tmp_path, monkeypatch):
    from arm.lab import market, v3data
    monkeypatch.setattr(store, "LAB", tmp_path)
    store.write("mkt", "2026-10-15", {"q_tw": {}})
    store.write_json("v3_tr.json", {"q": {"2026-10-15": 1.0}, "m": ["2026-09"]})
    monkeypatch.setattr(market, "twse_tr_month", lambda y, m: pytest.fail("不該發請求"))
    assert v3data.update_tr_recent() == 0
    store.write_json("v3_tr.json", {"q": {"2026-10-14": 1.0}, "m": ["2026-09"]})
    calls = []
    monkeypatch.setattr(market, "twse_tr_month", lambda y, m: calls.append((y, m)) or {"2026-10-15": 2.0})
    assert v3data.update_tr_recent() == 1 and calls == [(2026, 10)]   # 上個月已完成，只查本月
