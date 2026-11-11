"""選擇權結算日 O1／O4 的程式（arm/lab/txo1.py；docs/lab_txo_plan.md 第 19.7 節）：只用假資料測規則照規格做，不看任何真實成績。"""
import math

import numpy as np

from arm.lab import txo1 as X
from arm.lab import txocalc as C
from arm.lab import txospec as S


def test_time_index():
    assert X.kof("09:00") == 0 and X.kof("09:30") == 360 and X.K_EXIT == 2880 and X.K_CLOSE == 3240
    assert len(X.K_ENTRY) == 37 and X.K_ENTRY[0] == 360 and X.K_ENTRY[-1] == X.kof("12:30")
    assert X.O4_K == [2940, 3000, 3060, 3120, 3180] and X.sec_of(3180) == 13 * 3600 + 25 * 60
    assert abs(float(X.t_left(X.K_EXIT)) - 30 / (300 * 252)) < 1e-12 and float(X.t_left(X.K_CLOSE)) == 0.0


def test_pricing_matches_reference():
    xs = np.linspace(-4, 4, 41)
    assert np.max(np.abs(X.ncdf(xs) - np.array([0.5 * (1 + math.erf(x / math.sqrt(2))) for x in xs]))) < 1e-6
    s = np.array([42000.0, 43000.0, 44000.0])
    for cp in "CP":
        got = X.bs_vec(cp, s, 43000.0, np.array([1 / 252] * 3), 0.3)
        ref = [C.bs(cp, x, 43000.0, 1 / 252, 0.3) for x in s]
        assert np.max(np.abs(got - ref)) < 0.01
    assert X.bs_vec("C", np.array([43100.0]), 43000.0, np.array([0.0]), 0.3)[0] == 100.0
    assert X.intrinsic("P", 42900, 43000) == 100 and X.intrinsic("C", 42900, 43000) == 0


def test_strike_pick():
    assert X._strike(43724, "C", 1) == 43750 and X._strike(43724, "C", 0) == 43700
    assert X._strike(43724, "P", 2) == 43600 and X._strike(43725, "C", 0) == 43750


class _Dy:
    def __init__(self, v):
        self.v = np.asarray(v, dtype=float)
        n = len(self.v)
        self.up = np.full(n, 100.0)
        self.lo = np.full(n, 90.0)
        self.avg = np.full(n, 95.0)


def _path(points):
    v = np.full(X.N_IDX, 100.0)
    for k, x in points:
        v[k:] = x
    return v


def test_exit_stop_by_index():
    v = _path([(360, 43200.0), (400, 43300.0), (500, 42900.0)])
    dy = _Dy(v)
    dy.up[:] = 43100.0
    dy.avg[:] = 43000.0
    st = X.stop1_of(dy, "C", 360)
    r = X.exit_path(dy, "C", 360, 43250.0, 0.3, st)
    assert r["parts"][0][0] == "all" and r["parts"][0][2] == 500 and r["parts"][0][3] == "stop"


def test_exit_half_then_trail():
    # 一路漲 → 價格翻倍先賣一半 → 指數回吐超過三分之一 → 剩下的出
    v = _path([(360, 43200.0), (420, 43500.0), (480, 43800.0), (600, 43550.0)])
    dy = _Dy(v)
    dy.up[:] = 43100.0
    dy.avg[:] = 43000.0
    r = X.exit_path(dy, "C", 360, 43250.0, 0.3, X.stop1_of(dy, "C", 360))
    kinds = [p[0] for p in r["parts"]]
    assert kinds == ["half", "rest"] and r["parts"][0][3] == "tp" and r["parts"][0][1] >= 2 * r["p0"]
    assert r["parts"][1][2] == 600 and r["parts"][1][3] == "trail"


def test_exit_time_and_hold_variant():
    v = _path([(360, 43200.0)])
    dy = _Dy(v)
    dy.up[:] = 43100.0
    dy.avg[:] = 43000.0
    r = X.exit_path(dy, "C", 360, 43000.0, 0.3, X.stop1_of(dy, "C", 360))     # 價內：時間價值少、不會跌一半
    assert r["parts"] == [["all", r["parts"][0][1], X.K_EXIT, "time"]]
    t = {"cp": "C", "kx": 43000.0, "F": 43230.0, "parts": r["parts"]}
    h = X.hold_variant(t)
    assert h["parts"][0][1] == 230.0 and h["parts"][0][3] == "settle" and t["parts"][0][3] == "time"
    r2 = X.exit_path(dy, "C", 360, 43250.0, 0.3, X.stop1_of(dy, "C", 360))    # 價外：時間價值掉一半 → ②
    assert r2["parts"][0][3] == "stop" and r2["parts"][0][2] < X.K_EXIT and r2["parts"][0][1] <= r2["p0"] * S.STOP_PREM


def test_sim_half_lots_costs_and_month_stop():
    t = {"d": "2026-01-07", "k": 360, "kx": 1.0, "p0": 10.0, "w": 1.0,
         "parts": [["half", 20.0, 400, "tp"], ["rest", 5.0, 500, "stop"]]}
    r = X.sim([t], 0.02, cm=1.0)["rows"][0]
    lots = int(1_000_000 * 0.02 // (10 * 50 + S.side_cost(10)))
    half = lots // 2
    want = -lots * S.side_cost(10) + half * (10 * 50 - S.side_cost(20)) + (lots - half) * (-5 * 50 - S.side_cost(5))
    assert r["lots"] == lots and abs(r["pnl"] - want) < 0.2
    # 一個月虧到 12% 以後同月不再進場
    big = [{"d": f"2026-02-{d:02d}", "k": 360, "kx": 1.0, "p0": 10.0, "w": 1.0, "parts": [["all", 0.0, 500, "stop"]]} for d in range(2, 12)]
    rows = X.sim(big, 0.02)["rows"]
    assert any(r.get("skip") == "month_stop" for r in rows)
    st = X.sim([{**t, "parts": [["all", 0.0, X.K_CLOSE, "settle"]]}], 0.02, cm=1.0)["rows"][0]
    assert abs(st["pnl"] - (-st["lots"] * (10 * 50 + S.side_cost(10) + S.FEE))) < 0.2      # 結算那一邊沒有滑價


def test_walk_forward_uses_only_past_years():
    grid = [{"vol_min": 0, "k": 1, "otm": 1}, {"vol_min": 0, "k": 1, "otm": 2}]
    rows0 = [{"d": f"{y}-03-01", "pnl": 10.0} for y in (2016, 2017) for _ in range(15)] + [{"d": "2018-03-01", "pnl": -999.0}] * 30 + [{"d": "2019-03-01", "pnl": 1.0}]
    rows1 = [{"d": f"{y}-03-01", "pnl": 5.0} for y in (2016, 2017) for _ in range(15)] + [{"d": "2018-03-01", "pnl": 999.0}] * 30 + [{"d": "2019-03-01", "pnl": 1.0}]
    pick = X.walk_forward(grid, {0: {"rows": rows0}, 1: {"rows": rows1}})
    assert pick[2018] == 0                      # 2018 只看 2016～2017
    assert pick[2019] == 1                      # 2019 看到 2018 才換


def test_settle_bounds():
    v = np.full(X.N_IDX, 43000.0)
    lo, hi = X.bounds(v, 3060, 0.0)
    assert abs(lo - 43000) < 1e-9 and abs(hi - 43000) < 1e-9
    lo, hi = X.bounds(v, 3060, 50.0)
    rest = S.SETTLE_K[1] - 3060 + 1
    assert abs(hi - 43000 - rest * 50 / 301) < 1e-9 and abs(43000 - lo - rest * 50 / 301) < 1e-9
    assert X.bounds(v, 3180, 50.0)[1] - 43000 < 0.2       # 13:25 只剩收盤一個


def test_settle_days_pick_last_appearance():
    days = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
    last = {"202611W1": "2026-11-04", "202611F1": "2026-11-06", "202611": "2026-11-06"}
    idx = {d: None for d in days}
    out = X.settle_days(days, last, idx, start="2026-11-01")
    assert out == {"2026-11-04": "202611W1", "2026-11-06": "202611F1"}   # 資料最後一天：是到期日才算（月選 11/18 才到期，不算）
