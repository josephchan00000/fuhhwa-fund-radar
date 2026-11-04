"""策略熔斷與改版觀察期的規格（ksspec VER 1）鎖住：要改就 VER＋1、寫進 docs/lab_killswitch_plan.md。
這裡只用手寫的小數列測公式，不碰任何策略的成績。"""
import pytest

from arm.lab import ksspec as K


def test_ksspec_v1_is_locked():
    assert (K.VER, K.SPEC_DATE) == (1, "2026-11-04")
    assert K.SLICES == ("tw_boom", "tw_star", "us_qm")
    assert K.BENCH == {"tw": "加權報酬指數（含息）", "us": "S&P 500 含息"}
    assert K.LIVE_FROM == {"tw_boom": "2026-10-23", "us_qm": "2026-10-23", "tw_star": "2026-10-15"}
    assert (K.DD_MULT, K.UW_MULT, K.ACT_LAG) == (1.5, 1.5, 1)
    assert (K.AUTO_RESUME, K.RESUME_RESET, K.UW_PAUSES, K.EPS) == (True, True, False, 1e-9)
    assert (K.QUAR_DAYS, K.QUAR_GATE) == (63, None)
    assert K.PLAN_RULES == ("corespec", "sxlivespec.PLAN_BOOK", "ussxspec.QM", "tw_star")
    assert K.FIX_KINDS == ("資料錯", "用到未來的資料", "程式和規格不一致")


def test_relative_lag_ignores_the_market_moving_together():
    s = [100, 90, 60, 66, 99]            # 策略跟著大盤一起跌 40%
    b = [10, 9, 6, 6.6, 9.9]
    rel = K.rel_series(s, b)
    assert rel == pytest.approx([1.0] * 5)
    dd, uw = K.lag(rel)
    assert dd == pytest.approx([0.0] * 5) and uw == [0] * 5


def test_lag_and_days_behind_with_gaps():
    rel = [1.0, 1.1, None, 0.99, 1.045, 1.1, 1.2]
    dd, uw = K.lag(rel)
    assert dd[2] is None and uw[2] is None
    assert dd[3] == pytest.approx(0.1) and uw[3] == 1 and uw[4] == 2
    assert dd[5] == 0 and uw[5] == 0 and dd[6] == 0                   # 回到最高點（含相等）就歸零
    assert K.rel_series([None, 2, 4], [None, 1, 1]) == [None, 1.0, 2.0]


def test_bounds_from_backtest():
    b = K.bounds([1.0, 0.9, 0.95, 1.0, 0.8, 0.9])                     # 最深 20%、最長 4 天沒創新高（0.8、0.9 都在 1.0 下面）
    assert b["dd_bt"] == pytest.approx(0.2) and b["dd"] == pytest.approx(0.3)
    assert b["uw_bt"] == 2 and b["uw"] == 3                           # 第 3 天回到 1.0 算創新高 → 之後只落後 2 天；2×1.5＝3


def test_walk_pause_auto_resume_and_restart():
    bd = {"dd": 0.3, "uw": 100}
    rel = [1.0, 0.9, 0.69, 0.6, 0.65, 0.69, 0.7, 0.5, 0.48]
    ev = K.walk(rel, bd)
    assert ev[0] == {"i": 2, "k": "pause"}                           # 落後 31% > 30%
    assert ev[1] == {"i": 5, "k": "resume"}                          # 紙上回到觸發那天的 0.69
    assert ev[2] == {"i": 8, "k": "pause"}                           # 恢復後從 0.69 重新量：0.48 落後約 30.4%
    assert len(ev) == 3


def test_walk_slow_only_notifies_once_per_stretch():
    bd = {"dd": 0.5, "uw": 2}
    rel = [1.0, 0.99, 0.98, 0.97, 0.96, 1.01, 1.0, 0.99, 0.98]
    ev = K.walk(rel, bd)
    assert ev == [{"i": 3, "k": "slow"}, {"i": 8, "k": "slow"}]       # 1.01 創新高之後才會再推；不暫停
