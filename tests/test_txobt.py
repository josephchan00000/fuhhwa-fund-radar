"""選擇權日資料回測 O2、O3（arm/lab/txobt.py）：選契約、反推波動率、百分位、帳戶與成本、停損、聯準會行程頁解析。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from arm.lab import txobt as B
from arm.lab import txocalc as C
from arm.lab import txoevents as E
from arm.lab import txospec as S

ROOT = Path(__file__).resolve().parents[1]


def _mkt():
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    close = {d: 17500.0 for d in days}
    close["2024-01-03"] = 17620.0
    book = {}
    for d in days:
        book[d] = {
            # 週選：1/10 到期
            "202401W2": ("2024-01-10", {17500: [200, 205, 190, 195], 17600: [150, 152, 240, 238], 17700: [None, 110, 300, 301]}),
            # 月選：1/17 到期
            "202401": ("2024-01-17", {17500: [400, 401, 380, 381], 17600: [350, 352, 430, 431]}),
            # 月選：2/21 到期
            "202402": ("2024-02-21", {17500: [700, 701, 650, 651], 17600: [660, 661, 700, 701], 18400: [300, 301, None, 999]}),
        }
    return B.Mkt(days, book, close)


def test_price_falls_back_to_settlement():
    m = _mkt()
    assert m.price("2024-01-02", "202401W2", 17700, "C") == 110
    assert m.price("2024-01-02", "202401W2", 17500, "P") == 190
    assert m.price("2024-01-02", "202401W2", 17800, "C") is None


def test_td_between_inside_and_beyond_data():
    m = _mkt()
    assert m.td_between("2024-01-02", "2024-01-05") == 3
    # 1/8 是資料最後一天；之後用平日數估：1/9、1/10 兩天
    assert m.td_between("2024-01-05", "2024-01-10") == 3


def test_o2_pick_nearest_expiry_after_exit_and_atm():
    m = _mkt()
    p = B.o2_pick(m, "2024-01-03", "2024-01-04")
    assert p["exp"] == "202401W2"
    # 收盤 17620 → 離最近的 17600
    assert [leg[1] for leg in p["legs"]] == [17600, 17600]
    assert [leg[2] for leg in p["legs"]] == ["C", "P"]


def test_o3_pick_monthly_with_buffer_and_spread():
    m = _mkt()
    # 出場 1/5：1/17 的月選離出場不到 10 個交易日（資料外用平日估）→ 用 2 月
    p = B.o3_pick(m, "2024-01-02", "2024-01-05")
    assert p["exp"] == "202402" and p["legs"] == [("202402", 17500, "C", 1)]
    q = B.o3_pick(m, "2024-01-02", "2024-01-05", spread=0.05)
    assert q["legs"][1] == ("202402", 18400, "C", -1)


def test_straddle_iv_round_trip():
    days = ["2024-01-02", "2024-01-03"]
    s, k, n, vol = 17500.0, 17500, 6, 0.2
    t = n / 252
    c, p = C.bs("C", s, k, t, vol), C.bs("P", s, k, t, vol)
    book = {d: {"X": ("2024-01-10", {k: [c, c, p, p]})} for d in days}
    m = B.Mkt(days, book, {d: s for d in days})
    # 1/2 到 1/10：資料內 1 天＋資料外平日 5 天＝6 個交易日
    assert m.td_between("2024-01-02", "2024-01-10") == n
    assert B.straddle_iv(m, "2024-01-02") == pytest.approx(vol, abs=1e-3)


def test_iv_pct_needs_full_lookback_and_excludes_today():
    ser = [(f"d{i:03d}", float(i % 7)) for i in range(12)] + [("dx", None), ("dy", 3.5)]
    out = B.iv_pct(ser, lookback=10)
    assert "d009" not in out and "d010" in out
    # dy：過去 10 個有值的是 i＝2..11 → i%7＝2,3,4,5,6,0,1,2,3,4；比 3.5 低的有 2,3,0,1,2,3 共 6 個
    assert out["dy"] == pytest.approx(0.6)


def test_sim_costs_lots_and_pnl():
    t = {"d": "2024-01-02", "x": "2024-01-03", "legs": [("X", 17500, "C", 1), ("X", 17500, "P", 1)],
         "pin": [100.0, 100.0], "pout": [150.0, 60.0], "tag": "cpi"}
    res = B.sim([t], 0.03)
    r = res["rows"][0]
    per = 200 * S.MULT + 2 * S.side_cost(100.0)
    assert r["lots"] == int(S.ACCOUNT * 0.03 // per)
    unit = 10 * S.MULT - 2 * (S.side_cost(100.0, mult=2) + 0) - S.side_cost(150.0, mult=2) - S.side_cost(60.0, mult=2)
    assert r["pnl"] == pytest.approx(r["lots"] * unit, abs=0.1)
    assert res["final"] == pytest.approx(S.ACCOUNT + r["lots"] * unit, abs=0.1)


def test_sim_short_uses_long_basis_for_lots():
    legs = [("X", 17500, "C", 1), ("X", 17500, "P", 1)]
    t = {"d": "2024-01-02", "x": "2024-01-03", "legs": [(a, b, c, -1) for a, b, c, _ in legs], "basis_legs": legs,
         "basis_pin": [100.0, 100.0], "pin": [100.0, 100.0], "pout": [150.0, 60.0], "tag": "x"}
    r = B.sim([t], 0.03)["rows"][0]
    assert r["lots"] > 0 and r["pnl"] < 0          # 賣方：指數大動，賠


def test_sim_day_stop_blocks_same_day_entry():
    big = {"d": "2024-01-02", "x": "2024-01-03", "legs": [("X", 1, "C", 1)], "pin": [100.0], "pout": [1.0], "tag": "a"}
    nxt = {"d": "2024-01-03", "x": "2024-01-04", "legs": [("X", 1, "C", 1)], "pin": [100.0], "pout": [100.0], "tag": "b"}
    res = B.sim([big, nxt], 0.05)
    # 第一筆幾乎全賠 5% 帳戶 ≥ 一天 4% → 同一天（1/3）不再進場
    assert res["rows"][1].get("skip") == "day_stop"
    assert "pnl" in B.sim([big, {**nxt, "d": "2024-01-04", "x": "2024-01-05"}], 0.05)["rows"][1]


def test_metrics_and_judge():
    rows = [{"d": f"20{y}-01-02", "x": f"20{y}-01-03", "pnl": p, "ret": p / 1e4} for y, p in
            (("10", 500.0), ("11", -200.0), ("12", 300.0))]
    curve = [(None, S.ACCOUNT), ("a", S.ACCOUNT + 500), ("b", S.ACCOUNT + 300), ("c", S.ACCOUNT + 600)]
    mt = B.metrics({"rows": rows, "curve": curve, "final": S.ACCOUNT + 600})
    assert mt["n"] == 3 and mt["mean"] == pytest.approx(200.0) and mt["years_ok"] == pytest.approx(2 / 3, abs=1e-4)
    j = B.judge(mt, 0.01, "O3")
    assert j["verdict"].startswith("只列")            # O3 至少 10 筆
    j = B.judge({**mt, "n": 50}, 0.01, "O3")
    assert j["verdict"] == "過關"
    assert B.judge({**mt, "n": 50}, 0.2, "O3")["verdict"] == "沒過"


def test_fomc_parse_headings():
    hist = ("<h5>Jan/Feb 31-1 Meeting - 2017</h5><p>Statement</p><h5>March 2 (unscheduled) Meeting - 2017</h5><p>Statement</p>"
            "<h5>March 17-18 (cancelled) Meeting - 2017</h5><h5>September 15 Meeting - 2017</h5><p>Agenda</p>"
            "<h5>October 7 Conference Call - 2017</h5><p>Statement</p><h5>December 12-13 Meeting - 2017</h5><p>Statement</p>")
    rows = E.parse_hist(hist, 2017)
    got = {r["d"]: r["sched"] for r in rows}
    assert got == {"2017-02-01": True, "2017-03-02": False, "2017-03-18": False, "2017-09-15": False,
                   "2017-10-07": False, "2017-12-13": True}
    cal = ('2024 FOMC Meetings<div class="fomc-meeting__month x"><strong>Apr/May</strong></div>'
           '<div class="fomc-meeting__date x">30-1</div><div class="fomc-meeting__month x"><strong>August</strong></div>'
           '<div class="fomc-meeting__date x">22 (notation vote)</div>')
    assert [(r["d"], r["sched"]) for r in E.parse_cal(cal)] == [("2024-05-01", True), ("2024-08-22", False)]


def test_events_file_eight_scheduled_meetings_a_year():
    doc = json.loads((ROOT / "data/lab/txo_events.json").read_text("utf-8"))
    by = doc["by_year"]
    assert all(by[str(y)] == 8 for y in range(2002, 2027) if y != 2020)
    assert by["2020"] == 7                              # 2020-03 排定會議取消、改臨時會議
    assert "2020-03-15" not in doc["fomc"] and "2026-10-28" in doc["fomc"]
