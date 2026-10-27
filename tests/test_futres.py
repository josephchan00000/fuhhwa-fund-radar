"""台指期早盤策略的研究（arm/lab/futres.py）：門檻流程、亂選方向對照、判定、追上統計。"""
from __future__ import annotations

import pytest

from arm.lab import futdata as F
from arm.lab import futres as R
from arm.lab import futsig as G
from arm.lab import futspec as P
from arm.lab import store

D = P.DECIDE_S
DAYS = [f"2026-09-{x:02d}" for x in range(1, 15)]           # 14 天（測試用，不管是不是交易日）
# 前 10 天 |E| = 10, 20, …, 100（正負交錯），第 11 天 +95、第 12 天 −30、第 13 天 −80
ES = [10, -20, 30, -40, 50, -60, 70, -80, 90, -100, 95, -30, -80]


def _ticks():
    # 決定前最後一筆 1000；之後一路漲到 1062：做多碰到停利（1001＋60＝1061，要有一筆 ≥ 1062），做空停損
    return [(D - 10, 1000, 2, False), (D + 1, 1000, 2, False), (D + 20, 1030, 2, False),
            (D + 40, 1062, 2, False), (9 * 3600 + 400, 1062, 2, False)]


@pytest.fixture
def fake(monkeypatch):
    have = DAYS[:1] + DAYS[1:1 + len(ES)]                     # 第一天只當「前一天」
    monkeypatch.setattr(store, "dates", lambda kind: list(have) if kind in (F.KIND_TX, F.KIND_IDX) else [])
    monkeypatch.setattr(R, "prev_trading_day", lambda d: DAYS[DAYS.index(d) - 1] if DAYS.index(d) else "2026-08-31")
    est = {d: 1000 + e for d, e in zip(DAYS[1:], ES)}
    monkeypatch.setattr(G, "day_inputs", lambda d, dp: {"c": "202611", "ticks": _ticks(), "basis": 0.0,
                                                        "div": 0.0, "i_close": P.SCALE_BASE})
    monkeypatch.setattr(G, "open_full", lambda d, dp, ip, cov: est.get(d))
    return have


def test_threshold_flow_and_sides(fake):
    la = R.days_lookahead()
    assert la[0]["skip"] == "前一個交易日沒有資料"
    rows = [r for r in la if "e" in r]
    assert [r["e"] for r in rows] == ES
    assert all(r["th"] is None and r["side"] is None for r in rows[:10])    # 不到 10 天不做
    assert rows[10]["th"] == 60 and rows[10]["side"] == "long"               # 10 天：排第 5 個（0 起算）＝60
    assert rows[11]["th"] == 70 and rows[11]["side"] is None                 # 11 天：第 6 個＝70，|−30| 不到
    assert rows[12]["th"] == 60 and rows[12]["side"] == "short"              # 12 天：第 6 個＝60
    r = rows[10]
    assert r["pts"] == [10, 2, 20, 60]                                       # 前一天收盤＝換算基準 → 原點數
    assert len(r["L"]) == len(R.SIM_COLS)
    assert r["L"][R.SIM_COLS.index("why")] == "target" and r["S"][R.SIM_COLS.index("why")] == "stop"
    assert r["mv"] == [62, 62, 62, 62, 62]                                   # 決定價 1000 → 之後都是 1062


def test_skip_reasons(fake, monkeypatch):
    monkeypatch.setattr(G, "open_full", lambda d, dp, ip, cov: None if d == DAYS[3] else 1000.0)
    monkeypatch.setattr(G, "day_inputs", lambda d, dp: None if d == DAYS[5] else
                        {"c": "202611", "ticks": _ticks(), "basis": 0.0, "div": 0.0, "i_close": P.SCALE_BASE})
    la = {r["d"]: r for r in R.days_lookahead()}
    assert la[DAYS[3]]["skip"] == "缺個股開盤價"
    assert la[DAYS[5]]["skip"] == "缺逐筆或指數"


def test_run_summary_and_compare(fake):
    doc = R.run()
    la = doc["lookahead"]
    assert doc["spec_ver"] == P.VER and doc["cols"] == list(R.SIM_COLS)
    assert la["n_days"] == len(ES) and la["verdict"] == "wait"
    m = la["main"]
    assert m["n"] == 2 and m["win"] == 0.5                                   # 第 11 天做多賺、第 13 天做空賠
    assert la["compare"]["always_long"]["n"] == len(ES) and la["compare"]["always_long"]["win"] == 1.0
    assert la["compare"]["raw_points"]["n"] == 2
    assert doc["realtime"]["verdict"] == "wait" and doc["realtime"]["days"] == []
    c = la["catchup"]["all"][0]
    assert c["n"] == len(ES) and c["agree"] == pytest.approx(6 / 13, abs=1e-4)   # 一路往上，E 是正的有 6 天


def test_placebo_bounds():
    rows = [{"side": "long", "L": [0, 0, 0, 0, "x", 10.0, 0, 0, 0], "S": [0, 0, 0, 0, "x", 10.0, 0, 0, 0]}] * 5
    assert R.placebo(rows, 10.0) == 1.0                                      # 多空一樣 → 亂選都不比它差
    best = [{"side": "long", "L": [0, 0, 0, 0, "x", 50.0, 0, 0, 0], "S": [0, 0, 0, 0, "x", -20.0, 0, 0, 0]}] * 12
    p = R.placebo(best, 50.0)
    assert p < 0.01                                                          # 12 天都要亂選中才追得上
    assert R.placebo(best, 50.0) == p                                        # 固定種子
    assert R.placebo([{"side": None}], 0.0) is None


def test_judgments():
    assert R.judge_lookahead(59, {"n": 30, "mean": -5}) == "wait"
    assert R.judge_lookahead(60, {"n": 30, "mean": -5}) == "out"
    assert R.judge_lookahead(60, {"n": 0}) == "out"
    assert R.judge_lookahead(60, {"n": 30, "mean": 0.1}) == "upper_ok"
    ok = {"n": 30, "mean": 3, "half1": 1, "half2": 2}
    assert R.judge_realtime(59, ok, 0.01) == "wait"
    assert R.judge_realtime(60, {**ok, "n": 29}, 0.01) == "wait"
    assert R.judge_realtime(60, ok, 0.01) == "pass"
    assert R.judge_realtime(60, ok, 0.2) == "fail"
    assert R.judge_realtime(60, {**ok, "half1": -1}, 0.01) == "fail"
    assert R.judge_realtime(60, {**ok, "mean": 0}, 0.01) == "fail"


def test_summarize_halves():
    s = R.summarize([1.0, 2.0, 3.0, 10.0, -4.0])
    assert s["n"] == 5 and s["half1"] == 1.5 and s["half2"] == 3.0 and s["win"] == 0.8
    assert R.summarize([]) == {"n": 0}
