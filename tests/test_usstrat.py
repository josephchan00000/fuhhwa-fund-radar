"""美股個股策略（arm/lab/usstrat.py；規格 usstratspec VER 1）的算法檢查（合成資料）。"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import usstrat as US  # noqa: E402
from arm.lab import usstratspec as S  # noqa: E402


def _cal(n=80, start="2020-01-01"):
    from datetime import date, timedelta
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_period_ends_and_history():
    cal = _cal(30)
    me = US.period_ends(cal, "m")
    assert [cal[i] for i in me] == ["2020-01-31", "2020-02-11"]          # 最後一天也算（資料尾端）
    we = US.period_ends(cal, "w")
    assert cal[we[0]] == "2020-01-03" and cal[we[1]] == "2020-01-10"
    C = np.ones((10, 2))
    C[4, 1] = np.nan
    H = US.history_ok(C, 3)
    assert H[:, 0].tolist() == [False] * 3 + [True] * 7
    assert H[:, 1].tolist() == [False, False, False, True, False, False, False, False, True, True]


def test_surprise_formula():
    assert US.surprise(1.10, 1.00) == 0.10000000000000009 or abs(US.surprise(1.10, 1.00) - 0.10) < 1e-12
    assert abs(US.surprise(0.08, 0.03) - 0.5) < 1e-12              # 預估太小 → 分母用 0.10
    assert abs(US.surprise(-0.2, -0.5) - 0.6) < 1e-12


def test_run_month_rebalances_equal_weight_with_turnover_cost():
    """兩檔：月底選第 0 檔、下個月底改選第 1 檔；只有換掉的部位算成本、隔天收盤換股。"""
    cal = _cal(45)
    T = len(cal)
    C = np.ones((T, 2))
    C[:, 0] = np.linspace(10, 20, T)                                  # 第 0 檔一路漲
    C[:, 1] = 50.0                                                    # 第 1 檔不動
    P = {"cal": cal, "C": C, "M": np.ones((T, 2), dtype=bool), "sym": ["AAA", "BBB"]}
    me = US.period_ends(cal, "m")                                     # 1/31、2/28、資料尾端
    pick = lambda m: [0] if m == me[0] else [1]                       # noqa: E731
    i0 = me[0]                                                        # 1/31 收盤開始（現金），2/3 收盤買第 0 檔
    r = US.run_month(P, pick, i0)
    nav = r["nav"]
    a = me[0] + 1
    assert nav[i0] == 1.0 and abs(nav[a] - (1 - S.COST)) < 1e-12      # 買進那天只扣成本
    b = me[1] + 1                                                     # 3/2 收盤換成第 1 檔
    v_before = (1 - S.COST) * C[b, 0] / C[a, 0]
    assert abs(nav[b] - v_before * (1 - 2 * S.COST)) < 1e-9           # 賣掉＋買進兩邊的成本
    assert abs(nav[-1] - nav[b]) < 1e-12                               # 第 1 檔不動


def test_book_buys_at_next_close_and_sells_after_hold():
    cal = _cal(30)
    T = len(cal)
    C = np.full((T, 1), 100.0)
    C[10:, 0] = 110.0
    P = {"cal": cal, "C": C, "M": np.ones((T, 1), dtype=bool), "sym": ["AAA"], "col": {"AAA": 0}}
    ev = {4: [("AAA", 0.5)]}
    r = US.run_u1(P, ev, 0, weight=0.5, hold=5)
    t = r["trades"]
    assert len(t) == 1 and t[0][2] == 5 and t[0][3] == 11                  # 第 5 天收盤買、第 10 天收盤標到期、第 11 天收盤賣
    assert abs(t[0][4] - (110 * (1 - S.COST)) / (100 * (1 + S.COST)) + 1) < 1e-9
