"""盤前價位第 4 段的模擬（arm/lab/pmlvl.py；規格 pmlvlspec VER 1）：用人造路徑檢查進場、出場、跳空不做、一次一筆。"""
import numpy as np

from arm.lab import pmlvl as L
from arm.lab import pmlvlspec as S


def _path(points: dict[int, float], base: float = 100.0, n: int = 3241) -> np.ndarray:
    """第 i 個點之後維持那個價（階梯）。"""
    p = np.full(n, base)
    for i in sorted(points):
        p[i:] = points[i]
    return p


def test_rev_sells_upper_level_and_hits_target():
    p = _path({S.OPEN_T: 100, 100: 110.2, 200: 104.0})             # 09:01 在 100，碰到 110（A＋1×em）再回落
    tr = L.day_trades(p, anchor=100, em=10, fam="rev", k=1.0, s=0.5, t=0.5)
    assert tr[0][:3] == (100, 110.2, -1)                           # 越過那一點的價格成交、賣
    assert tr[0][3:6] == (200, 104.0, "target")                    # 目標＝110.2 − 5


def test_brk_buys_breakout_and_stops():
    p = _path({S.OPEN_T: 100, 100: 105.5, 150: 102.0})
    tr = L.day_trades(p, anchor=100, em=10, fam="brk", k=0.5, s=0.25, t=1.0)
    assert tr[0][:3] == (100, 105.5, 1) and tr[0][5] == "stop" and tr[0][4] == 102.0


def test_gap_side_skipped_and_time_exit():
    p = _path({S.OPEN_T: 112, 300: 89.0})                          # 開盤已經在上方價位之上 → 上方不做；下方 90 被越過
    tr = L.day_trades(p, anchor=100, em=10, fam="brk", k=1.0, s=5.0, t=5.0)
    assert len(tr) == 1 and tr[0][6] == "d" and tr[0][2] == -1 and tr[0][5] == "time" and tr[0][3] == S.EXIT_T


def test_one_position_at_a_time_then_other_side():
    p = _path({S.OPEN_T: 100, 100: 105.1, 110: 107.6, 400: 100, 500: 94.9, 510: 92.4})
    tr = L.day_trades(p, anchor=100, em=10, fam="brk", k=0.5, s=0.25, t=0.25)
    assert [x[6] for x in tr] == ["u", "d"] and tr[0][5] == "target" and tr[1][0] == 500 and tr[1][5] == "target"


def test_no_entry_after_entry_last():
    p = _path({S.OPEN_T: 100, S.ENTRY_LAST + 1: 120})
    assert L.day_trades(p, anchor=100, em=10, fam="brk", k=0.5, s=0.25, t=0.25) == []


def test_pnl_uses_double_cost_and_judge():
    assert round(L.pnl(100, 110, 1), 1) == round(10 * 50 - 2 * (S.side_cost(100) + S.side_cost(110)), 1)
    rows = [{"d": f"20{19 + i // 40}-01-{i % 28 + 1:02d}", "pnl": 100.0, "pnl1": 120.0, "flip": -100.0, "pts": 2, "why": "target"}
            for i in range(120)]
    m = L.metrics(rows)
    pl = L.placebo(rows, n=200)
    j = L.judge(m, pl)
    assert m["n"] == 120 and m["years_ok"] == 1.0 and pl["p"] == 0.0 and j["verdict"] == "過關"
