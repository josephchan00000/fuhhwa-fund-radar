"""美股個股卡的每天資料（arm/lab/uscard.py；docs/lab_cfg_v2_plan.md 第 4 節）：用假的 Yahoo 回應驗證——
最近收盤日（紐約時間、NYSE 休市表）、和 50 日線檢查共用同一次抓取、50 日線和檢查同一條、財報日、
同一個收盤只抓一次、抓不到沿用舊的、這一批以外的拿掉。不連網。"""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from arm import fund_intro as FI
from arm.lab import uscard as UC
from arm.lab import ussxqm as QM
from arm.usnews import _US_MKT_HOLIDAYS

UTC = timezone.utc


def _cal(a: str, b: str) -> list[str]:
    d, out = date.fromisoformat(a), []
    while d <= date.fromisoformat(b):
        if d.weekday() < 5 and d not in _US_MKT_HOLIDAYS:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _series(ds, base=100.0, step=0.5, div=None):
    cs = [base + step * k for k in range(len(ds))]
    return {"d": list(ds), "c": cs, "o": cs, "h": cs, "l": cs, "v": [1.0] * len(cs), "div": div or [], "spl": []}


def _qs(n=18, ed=("2026-10-28",), est=False, cal=True):
    """假的 quoteSummary 回應（欄位照 Yahoo v10）。"""
    tr = {"period": "0y", "endDate": "2026-12-31",
          "earningsEstimate": {"avg": {"raw": 61.1}, "low": {"raw": 55.0}, "high": {"raw": 66.0}, "numberOfAnalysts": {"raw": 15},
                               "yearAgoEps": {"raw": 40.0}, "growth": {"raw": 0.5275}},
          "revenueEstimate": {"avg": {"raw": 1.3e11}, "low": {"raw": 1.2e11}, "high": {"raw": 1.4e11},
                              "numberOfAnalysts": {"raw": 12}, "yearAgoRevenue": {"raw": 1.25e11}, "growth": {"raw": 0.04}},
          "epsTrend": {"current": {"raw": 61.1}, "7daysAgo": {"raw": 60.0}, "30daysAgo": {"raw": 50.0},
                       "60daysAgo": {"raw": 40.0}, "90daysAgo": {"raw": 35.24}},
          "epsRevisions": {"upLast7days": {"raw": 3}, "upLast30days": {"raw": 10}, "downLast7Days": {"raw": 0},
                           "downLast30days": {"raw": 1}}}
    res = {"financialData": {"numberOfAnalystOpinions": {"raw": n}, "targetMeanPrice": {"raw": 210.5},
                             "targetMedianPrice": {"raw": 212.0}, "targetHighPrice": {"raw": 250.0},
                             "targetLowPrice": {"raw": 160.0}, "recommendationMean": {"raw": 1.9}, "financialCurrency": "USD"},
           "recommendationTrend": {"trend": [{"period": "0m", "strongBuy": 5, "buy": 8, "hold": 4, "sell": 1, "strongSell": 0}]},
           "earningsTrend": {"trend": [tr, {**tr, "period": "+1y", "endDate": "2027-12-31"}]}}
    if cal:
        res["calendarEvents"] = {"earnings": {"earningsDate": [{"raw": 0, "fmt": d} for d in ed], "isEarningsDateEstimate": est}}
    return {"quoteSummary": {"result": [res], "error": None}}


class _Y:
    """假的 fcst._Yahoo：get(url) 依代號回 (狀態, 內容)。"""

    def __init__(self, resp):
        self.crumb, self.resp, self.calls, self.urls, self.logins = "abc", resp, [], [], 0

    def get(self, url, timeout=20, accept="application/json"):
        sym = url.split("/quoteSummary/")[1].split("?")[0]
        self.calls.append(sym)
        self.urls.append(url)
        st, o = self.resp.get(sym, (404, None))
        return st, (json.dumps(o).encode() if o is not None else b"")

    def login(self):
        self.logins += 1
        return True


def test_last_close_new_york_time_and_nyse_holidays():
    ny = lambda y, m, d, hh, mm: datetime(y, m, d, hh, mm, tzinfo=UC._ny())
    assert UC.last_close(ny(2026, 10, 24, 5, 30)) == "2026-10-23"          # 週六 → 週五
    assert UC.last_close(ny(2026, 10, 23, 15, 0)) == "2026-10-22"          # 週五盤中 → 週四
    assert UC.last_close(ny(2026, 10, 23, 16, 30)) == "2026-10-23"         # 週五收盤以後
    assert UC.last_close(ny(2026, 10, 26, 9, 0)) == "2026-10-23"           # 週一開盤前 → 上週五
    assert UC.last_close(ny(2026, 11, 27, 10, 0)) == "2026-11-25"          # 感恩節（11/26 休市）隔天盤中
    assert UC.last_close(ny(2026, 11, 26, 20, 0)) == "2026-11-25"          # 休市那天晚上
    assert UC.last_close(datetime(2026, 10, 24, 9, 30, tzinfo=UTC)) == "2026-10-23"    # 台北週六 17:30


def test_cached_fetch_shared_with_watch_and_floor():
    calls = []

    def fake(sym, st):
        calls.append((sym, st))
        if sym == "BAD":
            return sym, None, "HTTPError 500"
        return sym, _series(_cal(st, "2026-10-23")), "ok"

    f = UC.cached(fetch=fake, today=date(2026, 10, 24))
    assert f.floor == "2025-08-10"
    c, s, msg = f("VLO", "2026-04-01")                                      # 50 日線檢查要的比較晚 → 照 floor 抓
    assert c == "VLO" and msg == "ok" and calls == [("VLO", "2025-08-10")]
    f("VLO", f.floor)                                                       # 個股卡要的：用同一次抓的
    assert len(calls) == 1
    f("VLO", "2025-01-01")                                                  # 要的更早 → 重抓
    assert calls[-1] == ("VLO", "2025-01-01") and len(calls) == 2
    f("BRK.B", f.floor)                                                     # Yahoo 的寫法
    assert calls[-1][0] == "BRK-B"
    assert f("BAD", f.floor)[1] is None and f("BAD", f.floor)[1] is None    # 沒抓到的下一次再試
    assert sum(1 for x in calls if x[0] == "BAD") == 2


def test_chart_window_and_ma_same_line_as_watch():
    ds = _cal("2025-06-02", "2026-10-23")
    s = _series(ds, div=[["2026-03-02", 1.5], ["2026-09-01", 2.0]])
    ch = UC.chart(s)
    pts = ch["pts"]
    assert min(pts) > "2025-10-23" and max(pts) == "2026-10-23"
    # 和 50 日線檢查（ussxqm.watch_one）同一條線
    w = QM.watch_one({"c": "AAA", "above": True}, "2026-10-01", s)
    assert pts["2026-10-23"][1] == pytest.approx(w["ma"], abs=0.006) and pts["2026-10-23"][0] == pytest.approx(w["px"])
    # 自己算：最近 50 個交易日的含息收盤平均，換成那天的價格
    from arm.lab import ussxdata as UD
    tr = UD.total_return_close(s)
    k = ds.index("2026-05-01")
    assert pts["2026-05-01"][1] == pytest.approx(sum(tr[k - 49:k + 1]) / 50 * s["c"][k] / tr[k], abs=0.006)
    # 不到 50 個交易日的那幾天沒有 50 日線
    s2 = _series(_cal("2026-09-01", "2026-10-23"))
    assert all(v[1] is None for d, v in UC.chart(s2)["pts"].items() if d < "2026-11-01")
    assert UC.chart({"d": []}) is None and UC.chart(None) is None


def test_parse_cal_dates_and_estimate_flag():
    assert UC.parse_cal(_qs(ed=("2026-11-05", "2026-11-03"), est=True)) == {"ed": ["2026-11-03", "2026-11-05"], "ede": True}
    o = _qs(cal=False)
    o["quoteSummary"]["result"][0]["calendarEvents"] = {
        "earnings": {"earningsDate": [{"raw": 1761681600}], "isEarningsDateEstimate": {"raw": False}}}
    assert UC.parse_cal(o) == {"ed": ["2025-10-28"], "ede": False}           # 只有時間戳：換成紐約的日期
    assert UC.parse_cal(_qs(cal=False)) == {} and UC.parse_cal({}) == {}


def test_analyst_record_with_eps_trend_target_and_earnings_date():
    Y = _Y({"VLO": (200, _qs()), "TINY": (200, _qs(n=0, cal=True)), "SLOW": (429, None)})
    st, rec = UC.analyst(Y, "VLO")
    assert st == "ok" and rec["n"] == 18 and rec["tp"] == [210.5, 212.0, 250.0, 160.0]
    assert rec["y0"]["t"] == [61.1, 60.0, 50.0, 40.0, 35.24] and rec["y1"]["end"] == "2027-12-31"
    assert rec["ed"] == ["2026-10-28"] and rec["ede"] is False and rec["rc"] == [5, 8, 4, 1, 0]
    assert UC.analyst(Y, "SLOW") == ("429", None) and UC.analyst(Y, "NONE") == ("none", None)
    u = Y.urls[0]
    assert "/quoteSummary/VLO?modules=" in u and "calendarEvents" in u and "earningsTrend" in u and u.endswith("&crumb=abc")
    assert UC.analyst(Y, "BRK.B")[0] == "none" and Y.calls[-1] == "BRK-B"     # Yahoo 的寫法


def _live(hold=("VLO", "INSW"), buy=("FTNT",), lst=("VLO", "MPC", "FTNT", "PAYC", "QLYS", "HALO", "NTAP", "CON")):
    return {"now": {"d": "2026-10-23", "hold": [{"c": c, "ent": "2026-08-31", "above": True} for c in hold], "buy": list(buy),
                    "list": [{"c": c, "rs": 90} for c in lst]}}


def test_update_once_per_close_keeps_old_on_failure_and_drops_others(tmp_path):
    p = tmp_path / "card.json"
    L = _live()
    codes, _ = FI.qm_codes(L)
    assert codes == ["VLO", "INSW", "FTNT", "MPC", "PAYC", "QLYS", "HALO", "NTAP"]
    data = {"end": "2026-10-23"}

    def fake(sym, st):
        return sym, _series(_cal(st, data["end"]), base=50 + len(sym)), "ok"

    Y = _Y({c: (200, _qs()) for c in codes})
    sat = datetime(2026, 10, 24, 9, 30, tzinfo=UTC)                         # 台北週六 17:30＝紐約週六清晨
    st = UC.update(L, fetch=UC.cached(fetch=fake, today=date(2026, 10, 24)), now=sat, Y=Y, path=p, made="2026-10-24")
    assert st["want"] == "2026-10-23" and st["chart"] == 8 and st["an"] == 8 and st["saved"] and not st["err"]
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["d"] == "2026-10-23" and doc["codes"] == codes and doc["made"] == "2026-10-24"
    assert doc["cal"][-1] == "2026-10-23" and doc["cal"][0] > "2025-10-23"
    for c in codes:
        r = doc["s"][c]
        assert len(r["c"]) == len(doc["cal"]) == len(r["m"]) and r["at"] == "2026-10-23" and r["an_at"] == "2026-10-23"
        assert r["an"]["ed"] == ["2026-10-28"] and r["an"]["y0"]["t"][-1] == 35.24
    # 同一個收盤再跑一次：不抓
    n = len(Y.calls)
    st2 = UC.update(L, fetch=UC.cached(fetch=lambda s, t: pytest.fail("不該再抓")), now=sat, Y=Y, path=p)
    assert "已經有 2026-10-23" in st2["skip"] and len(Y.calls) == n
    # 下一個收盤（10/26 週一）：一檔日線抓不到、一檔分析師被限流 → 沿用舊的、記原因
    data["end"] = "2026-10-26"

    def fake2(sym, st):
        return (sym, None, "HTTPError 500") if sym == "INSW" else fake(sym, st)

    Y.resp["MPC"] = (500, None)
    mon = datetime(2026, 10, 26, 21, 0, tzinfo=UTC)                          # 紐約 17:00
    st3 = UC.update(L, fetch=UC.cached(fetch=fake2, today=date(2026, 10, 27)), now=mon, Y=Y, path=p, made="2026-10-27")
    assert st3["want"] == "2026-10-26" and st3["chart"] == 7 and st3["an"] == 7
    assert any("INSW" in e for e in st3["err"]) and any("MPC" in e for e in st3["err"])
    doc = json.loads(p.read_text(encoding="utf-8"))
    ins = doc["s"]["INSW"]
    assert doc["cal"][-1] == "2026-10-26" and ins["c"][-1] is None and ins["c"][-2] is not None
    assert ins["at"] == "2026-10-23" and ins["err"].startswith("日線")
    assert doc["s"]["MPC"]["an_at"] == "2026-10-23" and doc["s"]["MPC"]["an"]["n"] == 18 and doc["s"]["MPC"]["aerr"] == "err"
    assert doc["s"]["VLO"]["at"] == "2026-10-26" and "err" not in doc["s"]["VLO"]
    # 下一輪：只補沒抓到的那兩項
    Y.resp["MPC"] = (200, _qs(n=20))
    calls0 = len(Y.calls)
    st4 = UC.update(L, fetch=UC.cached(fetch=fake, today=date(2026, 10, 27)), now=mon, Y=Y, path=p, made="2026-10-27")
    assert st4["chart"] == 1 and st4["an"] == 1 and Y.calls[calls0:] == ["MPC"]
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["s"]["INSW"]["at"] == "2026-10-26" and doc["s"]["MPC"]["an"]["n"] == 20 and "aerr" not in doc["s"]["MPC"]
    # 名單換了：不在這一批的拿掉、新的抓進來
    L2 = _live(hold=("VLO",), buy=(), lst=("VLO", "MPC", "PAYC", "QLYS", "HALO", "DOCU"))
    st5 = UC.update(L2, fetch=UC.cached(fetch=fake, today=date(2026, 10, 27)), now=mon, Y=Y, path=p, made="2026-10-27")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert sorted(doc["s"]) == sorted(["VLO", "MPC", "PAYC", "QLYS", "HALO", "DOCU"]) and st5["chart"] == 1


def test_update_force_budget_and_no_live(tmp_path):
    p = tmp_path / "card.json"
    assert UC.update({"now": None}, path=p)["skip"] == "還沒有每週紀錄" and not p.exists()
    L = _live(hold=("VLO",), buy=(), lst=("VLO",))
    fake = lambda sym, st: (sym, _series(_cal(st, "2026-10-23")), "ok")
    Y = _Y({"VLO": (200, _qs())})
    sat = datetime(2026, 10, 24, 9, 30, tzinfo=UTC)
    UC.update(L, fetch=UC.cached(fetch=fake, today=date(2026, 10, 24)), now=sat, Y=Y, path=p, made="2026-10-24")
    st = UC.update(L, fetch=UC.cached(fetch=fake, today=date(2026, 10, 24)), now=sat, Y=Y, path=p, force=True, made="x")
    assert st["chart"] == 1 and st["an"] == 1 and len(Y.calls) == 2           # force：不管抓過沒有
    st = UC.update(L, fetch=UC.cached(fetch=fake, today=date(2026, 10, 24)), now=sat, Y=Y, path=p, force=True,
                   budget_s=-1, made="y")
    assert st["skip_n"] == 2 and st["chart"] == 0                             # 時間到：不抓、沿用舊的
    assert json.loads(p.read_text(encoding="utf-8"))["s"]["VLO"]["at"] == "2026-10-23"


def test_watch_and_card_share_one_fetch_per_ticker(tmp_path):
    """50 日線檢查與個股卡共用：手上的股票一檔只抓一次日線；卡片的 50 日線最後一天＝檢查的 50 日線。"""
    calls = []

    def fake(sym, st):
        calls.append(sym)
        return sym, _series(_cal(st, "2026-10-23"), base=40.0, div=[["2026-06-01", 0.8]]), "ok"

    L = _live(hold=("VLO", "INSW"), buy=(), lst=("VLO", "INSW", "PAYC"))
    L["now"]["d"] = "2026-10-16"
    f = UC.cached(fetch=fake, today=date(2026, 10, 24))
    W = QM.watch(L, fetch=f, made="2026-10-24")
    UC.update(L, fetch=f, now=datetime(2026, 10, 24, 9, 30, tzinfo=UTC), Y=_Y({}), path=tmp_path / "c.json", made="2026-10-24")
    assert sorted(calls) == ["INSW", "PAYC", "VLO"]
    doc = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    for w in W["hold"]:
        assert doc["s"][w["c"]]["m"][-1] == pytest.approx(w["ma"], abs=0.006)


def test_fetch_script_and_workflows_wired():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sc = (root / "scripts" / "fetch_ussx_watch.py").read_text(encoding="utf-8")
    assert "UC.cached()" in sc and "QM.watch(L, fetch=fetch)" in sc and "--card-force" in sc
    ah = (root / ".github" / "workflows" / "afterhours_refresh.yml").read_text(encoding="utf-8")
    sh = (root / "scripts" / "daily_fund.sh").read_text(encoding="utf-8")
    for t in (ah, sh):
        assert "timeout 300 python3 scripts/fetch_ussx_watch.py" in t and "timeout 180 python3 scripts/fetch_ussx_watch.py" not in t
    lb = (root / ".github" / "workflows" / "lab_backfill.yml").read_text(encoding="utf-8")
    assert '"${MODE#uscard}"' in lb and "fetch_ussx_watch.py --card-force" in lb
    wk = (root / ".github" / "workflows" / "ussx_weekly.yml").read_text(encoding="utf-8")
    assert "live_only" in wk and wk.count("if: ${{ !inputs.live_only }}") == 2
