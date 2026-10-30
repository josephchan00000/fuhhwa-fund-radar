"""個股報告每天晚上的名單（arm/lab/eqqueue.py；docs/lab_eq_request_plan.md 第 3.3 節）：
申請的排最前、再補接下來 2 個交易日要買的、週六才有季更新；做過又沒有新財報的不做；每班最多 3 家。"""
import json

from arm.lab import eqinbox as I
from arm.lab import eqqueue as Q


def _report(src, mk, code, made, q):
    d = src / mk / code
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{made}.facts.json").write_text(json.dumps({"q": [{"q": q}]}), encoding="utf-8")
    (d / f"{made}.md").write_text("x", encoding="utf-8")


def _root(tmp_path):
    lab = tmp_path / "data" / "lab"
    lab.mkdir(parents=True)
    (lab / "ussx_fin.json").write_text(json.dumps({"s": {"PAYC": {}, "ZZZ": {}}}), encoding="utf-8")
    (lab / "ussx_card.json").write_text(json.dumps({"s": {"PAYC": {}}}), encoding="utf-8")
    return tmp_path


def test_queue_order_cap_and_skips(tmp_path, monkeypatch):
    src, root = tmp_path / "eq", _root(tmp_path)
    _report(src, "tw", "1111", "2026-10-01", "2026-06-30")          # 做過、沒有新財報 → 不做
    _report(src, "tw", "2222", "2026-06-01", "2026-03-31")          # 做過、出了新財報 → 要做
    monkeypatch.setattr(Q, "latest_quarter", lambda mk, c: "2026-06-30")
    cands = [{"mk": "tw", "code": "1111", "src": "申請 #5"},
             {"mk": "us", "code": "ZZZ", "src": "申請 #6"},              # 美股資料包做不出來（沒有個股卡）
             {"mk": "tw", "code": "3333", "src": "申請 #7"},
             {"mk": "us", "code": "PAYC", "src": "11/2 要買（強勢品質股）"},
             {"mk": "tw", "code": "3333", "src": "11/2 要買（新飆股）"},     # 同一家只算一次（申請那一筆在前）
             {"mk": "tw", "code": "2222", "src": "季更新"},
             {"mk": "tw", "code": "4444", "src": "11/3 要買（長線）"}]
    r = Q.queue("2026-10-31", 3, src, cands, root)
    assert r["max"] == Q.EQ_RUN_MAX == 3
    assert [(c["code"], c["src"]) for c in r["todo"]] == [("3333", "申請 #7"), ("PAYC", "11/2 要買（強勢品質股）"), ("2222", "季更新")]
    sk = {c["code"]: c["skip"] for c in r["skip"]}
    assert "還沒有新一季財報" in sk["1111"] and "做不出來" in sk["ZZZ"] and "明天再排" in sk["4444"]
    assert Q.need("tw", "2222", "2026-10-31", src)[0] and "財報" in Q.need("tw", "2222", "2026-10-31", src)[1]


def _page(ev, ks=(("boom", "新飆股", 1, 1), ("s5", "長線", 4, 1), ("s1", "共識加碼", 0, 0))):
    pick = {"tw": {"d": "2026-10-30", "ks": [list(k) for k in ks], "ev": ev}, "us": {"ev": []}}
    other = {"d": "2026-10-28", "rows": []}                          # 頁面裡別的 "pick"（研究紀錄的名單）不能被當成選股頁
    return "const D=" + json.dumps({"x": {"pick": other}, "pick": pick}, ensure_ascii=False, separators=(",", ":")) + ";"


def test_upcoming_two_trading_days_main_strategies_and_us():
    ev = [["2026-11-02", "開盤", "boom", "買進", [["6870", "騰雲"], ["4958", "臻鼎-KY"]], "", 0],
          ["2026-11-03", "開盤", "s5", "買進", [["1560", "中砂"]], "", 0],
          ["2026-11-04", "開盤", "s5", "買進", [["2330", "台積電"]], "", 0],       # 第 3 個交易日：太遠
          ["2026-11-02", "開盤", "s1", "買進", [["2317", "鴻海"]], "", 0],         # 不是主要策略
          ["2026-11-02", "收盤", "boom", "賣出", [["3008", "大立光"]], "", 0],
          ["2026-11-03", "開盤", "boom", "買進", [], "新名單", 1]]                 # 還不知道是哪幾檔
    qm = {"now": {"buy": ["PAYC"], "next": "2026-11-02"}}
    got = Q.upcoming("2026-10-30", _page(ev), qm)                               # 週五晚上：接下來＝11/2（一）、11/3（二）
    assert [(c["mk"], c["code"], c["src"]) for c in got] == [
        ("tw", "6870", "11/2 要買（新飆股）"), ("tw", "4958", "11/2 要買（新飆股）"), ("tw", "1560", "11/3 要買（長線）"),
        ("us", "PAYC", "11/2 要買（強勢品質股）")]
    assert [c["code"] for c in Q.upcoming("2026-10-31", _page(ev), qm)] == ["6870", "4958", "1560", "PAYC"]   # 週六一樣
    assert [c["code"] for c in Q.upcoming("2026-11-02", _page(ev), {"now": {"buy": ["PAYC"], "next": "2026-10-26"}})] == ["1560", "2330"]
    assert Q.upcoming("2026-10-30", "沒有選股頁", {}) == []


def test_requests_and_saturday_only_updates(tmp_path, monkeypatch):
    f = tmp_path / "eq_requests.json"
    f.write_text(json.dumps({"items": [{"mk": "tw", "code": "6669", "name": "緯穎", "issue": 12, "at": "2026-10-30", "owner": False}]}),
                 encoding="utf-8")
    assert Q.requests(f) == [{"mk": "tw", "code": "6669", "name": "緯穎", "src": "申請 #12"}]
    calls = []
    monkeypatch.setattr(Q, "requests", lambda path=None: [])
    monkeypatch.setattr(Q, "upcoming", lambda today, *a, **k: [])
    monkeypatch.setattr(Q, "updates", lambda today, src=Q.SRC: calls.append(today) or [])
    Q.queue("2026-10-30")                                                       # 週五：不看季更新
    Q.queue("2026-10-31")                                                       # 週六
    assert calls == ["2026-10-31"]


def test_inbox_and_queue_agree_on_us_coverage(tmp_path):
    root = _root(tmp_path)
    assert I.known("us", "PAYC", root) and not I.known("us", "ZZZ", root)
