"""美股飆股的資金帳戶（arm/lab/ussxbook.py；ussxspec VER 1）：用手算得出來的小例子驗證買賣時點、成本、閒置放指數、出場條件。"""
from __future__ import annotations

import numpy as np
import pytest

from arm.lab import ussxbook as BK


def _mk(closes, opens=None):
    C = np.array(closes, dtype=float)
    if C.ndim == 1:
        C = C[:, None]
    O = C.copy() if opens is None else np.array(opens, dtype=float).reshape(C.shape)
    last = np.array([max(i for i in range(len(C)) if np.isfinite(C[i, j])) for j in range(C.shape[1])])
    return O, C, last


def test_fixed_hold_buy_next_open_sell_after_n_days_with_costs():
    O, C, last = _mk([10, 10, 11, 12, 13, 14, 15, 16])
    idle_r = np.array([0, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01])
    r = BK.run(O, C, C, last, {1: [(0, 90)]}, 0, 8, idle_r, ex={"hold": 3}, weight=0.5, max_weight=1.0, capital=1000.0,
               c_stk=0.001, c_idx=0.0005)
    eq = r["eq"]
    # 第 1 天收盤：閒置 1000 × 1.01；第 2 天開盤用前一天總資產的 50% 買
    e1 = 1000 * 1.01
    x = 0.5 * e1
    idle = e1 - x * 1.001 / 0.9995
    k = x / 11
    idle *= 1.01
    assert eq[1] == pytest.approx(e1)
    assert eq[2] == pytest.approx(idle + k * 11)
    idle *= 1.01
    assert eq[3] == pytest.approx(idle + k * 12)
    idle *= 1.01
    assert eq[4] == pytest.approx(idle + k * 13)
    idle *= 1.01
    assert eq[5] == pytest.approx(idle + k * 14)         # 第 5 天收盤＝買進後第 3 天 → 標記，第 6 天開盤賣
    idle += k * 15 * 0.999 * 0.9995
    idle *= 1.01
    assert eq[6] == pytest.approx(idle)
    t = r["trades"][0]
    assert t[2] == 2 and t[3] == 6 and t[5] == "time" and t[4] == pytest.approx(15 * 0.999 / (11 * 1.001) - 1)
    assert r["stk"][6] == 0 and r["n"][4] == 1


def test_trend_exit_trailing_and_ma_cross_rule():
    closes = [10, 10, 10, 12, 15, 20, 18, 14, 13, 12]
    O, C, last = _mk(closes)
    MA = np.full_like(C, 11.0)
    r = BK.run(O, C, C, last, {1: [(0, 90)]}, 0, 10, np.zeros(10), ex={"trail": 0.30, "ma": 200, "hold": 100},
               style="trend", MA=MA, weight=1.0, max_weight=1.0, capital=100.0, c_stk=0.0, c_idx=0.0)
    t = r["trades"][0]
    assert t[2] == 2 and t[5] == "trail" and t[3] == 8                 # 第 7 天收盤 14 ≤ 20 × 0.7 → 第 8 天開盤賣
    # 買進時在均線下面：要先站上去再跌破才算
    closes = [10, 10, 9, 9, 12, 13, 10.5, 10]
    O, C, last = _mk(closes)
    MA = np.full_like(C, 11.0)
    r = BK.run(O, C, C, last, {1: [(0, 90)]}, 0, 8, np.zeros(8), ex={"trail": 0.9, "ma": 200, "hold": 100},
               style="trend", MA=MA, weight=1.0, max_weight=1.0, capital=100.0, c_stk=0.0, c_idx=0.0)
    t = r["trades"][0]
    assert t[5] == "ma" and t[3] == 7                                     # 第 6 天收盤 10.5 < 11（之前站上過）


def test_w8_style_plain_ma_and_stop():
    closes = [10, 10, 10, 9.0, 8.0]
    O, C, last = _mk(closes)
    MA = np.full_like(C, 9.5)
    r = BK.run(O, C, C, last, {1: [(0, 90)]}, 0, 5, np.zeros(5), ex={"ma": 50}, style="w8", MA=MA, weight=1.0,
               capital=100.0, c_stk=0.0, c_idx=0.0)
    assert r["trades"][0][5] == "ma" and r["trades"][0][3] == 4
    r = BK.run(O, C, C, last, {1: [(0, 90)]}, 0, 5, np.zeros(5), ex={"stop": 0.05}, style="w8", weight=1.0,
               capital=100.0, c_stk=0.0, c_idx=0.0)
    assert r["trades"][0][5] == "stop" and r["trades"][0][3] == 4


def test_max_positions_rank_order_idle_limit_and_delisting():
    nan = np.nan
    C = np.array([[10, 10, 10, 10],
                  [10, 10, 10, 10],
                  [10, 10, 10, 10],
                  [10, 10, 10, nan],
                  [10, 10, 10, nan],
                  [10, 10, 10, nan]], dtype=float)
    O, _, last = _mk(C)
    Cf = C.copy()
    Cf[3:, 3] = 10
    sig = {1: [(3, 99), (1, 80), (0, 70), (2, 60)]}
    r = BK.run(O, Cf, C, last, sig, 0, 6, np.zeros(6), ex={"hold": 100}, weight=0.4, max_weight=1.0, max_pos=3, capital=100.0,
               c_stk=0.0, c_idx=0.0)
    held = {t[0] for t in r["trades"]}
    assert held == {3, 1, 0}                                              # RS 高到低、最多 3 檔、第三檔只剩 20%
    t3 = next(t for t in r["trades"] if t[0] == 3)
    assert t3[5] == "delisted" and t3[3] == 3                             # 第 2 天之後沒有資料 → 第 3 天用最後一天收盤賣
    t0 = next(t for t in r["trades"] if t[0] == 0)
    assert t0[6] == pytest.approx(20.0) and t0[5] == "open"
    assert r["eq"][-1] == pytest.approx(100.0)


def test_stats_helpers():
    cal = ["2020-01-01", "2020-07-01", "2021-01-01"]
    r = np.array([0.0, 0.1, 0.1])
    st = BK.curve_stats(cal, r, 0, 3)
    assert st["m"] == pytest.approx(1.21) and st["cagr"] == pytest.approx(1.21 ** (365.25 / 366) - 1)
    assert BK.mdd(np.array([1.0, 2.0, 1.0, 1.5])) == pytest.approx(0.5)
    assert BK.halves(0, 10) == ((0, 6), (5, 10))
