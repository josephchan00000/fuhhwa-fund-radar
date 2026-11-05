"""盤前作戰圖第 3 段驗證的小工具（arm/lab/pmval.py）。"""
import numpy as np

from arm.lab import pmval as V
from arm.lab import premktspec as S


def test_first_passage_hold_and_break():
    p = np.array([100, 101, 103, 104, 102, 99.0])
    assert V.first_passage(p, 103, "up", 2) == 1          # 碰到 103 之後先回到 101 以下
    p = np.array([100, 103, 104, 106, 101.0])
    assert V.first_passage(p, 103, "up", 2) == 0          # 碰到之後先到 105 以上
    p = np.array([100, 103, 104, 103.5])
    assert V.first_passage(p, 103, "up", 2) is None       # 到收盤都沒有
    assert V.first_passage(np.array([100, 101.0]), 103, "up", 2) == -1
    p = np.array([100, 97, 96, 99.5])
    assert V.first_passage(p, 97, "dn", 2) == 1           # 支撐：碰到 97 之後先回到 99 以上


def test_tercile_needs_history_and_excludes_today():
    assert V._tercile([1.0] * (S.RANK_N - 1), 5.0) == 0
    hist = [float(i) for i in range(S.RANK_N)]
    assert V._tercile(hist, 1e9) == 1
    assert V._tercile(hist, -1.0) == -1
    assert V._tercile(hist, S.RANK_N / 2) == 0


def test_categories_match_page_kinds():
    from arm.lab.premkt import KINDS
    assert set(V.CAT) == set(S.LEVEL_KINDS)
    assert set(V.CAT.values()) <= set(KINDS)


def test_diff_test_obvious_and_null():
    g = np.random.default_rng(1)
    assert V.diff_test([1] * 80 + [0] * 20, [1] * 20 + [0] * 80, g) <= 0.01
    assert V.diff_test([1, 0] * 50, [1, 0] * 50, g) > 0.3
