"""台指期早盤策略模擬引擎（arm/lab/futsim.py）：用手算得出來的逐筆路徑檢查每一條規則。"""
from __future__ import annotations

from arm.lab import futsim as S

D = 8 * 3600 + 59 * 60 + 30            # 08:59:30 決定
EOD = 13 * 3600 + 44 * 60


def T(hms: str, p: int) -> tuple[int, int, int, bool]:
    h, m, s = (int(x) for x in hms.split(":"))
    return (h * 3600 + m * 60 + s, p, 2, False)


def run(ticks, side="long", **kw):
    p = dict(stop=10, buf=2, clear=20, target=60, slip=1, exit_s=EOD, cost_side=lambda px: 0.5)
    p.update(kw)
    return S.simulate(ticks, side, D, **p)


def test_entry_is_first_trade_after_decision_with_slippage():
    tr = run([T("08:59:29", 99), T("08:59:31", 100), T("09:30:00", 105), T("13:44:00", 104)])
    assert tr.t_in == T("08:59:31", 0)[0] and tr.px_in == 101 and tr.stop0 == 91 and tr.target == 161
    assert tr.why == "eod" and tr.px_out == 103 and tr.gross == 2 and tr.net == 1


def test_fixed_stop_fills_at_trigger_trade_minus_slippage():
    tr = run([T("08:59:31", 100), T("09:00:05", 95), T("09:00:06", 88)])
    assert tr.why == "stop" and tr.px_out == 87 and tr.gross == -14 and tr.mae == -12


def test_target_needs_a_trade_through_the_price():
    ticks = [T("08:59:31", 100), T("09:01:00", 161), T("09:01:01", 160), T("09:01:02", 162)]
    tr = run(ticks)
    assert tr.why == "target" and tr.px_out == 161 and tr.t_out == T("09:01:02", 0)[0] and tr.gross == 60


def test_trailing_stop_moves_only_after_clearance_and_only_tighter():
    ticks = [
        T("08:59:31", 100),                                  # 進場 101、停損 91
        T("09:00:10", 106), T("09:00:40", 105),              # 09:00 這根低點 105
        T("09:01:10", 112), T("09:01:50", 110),              # 09:01 這根低點 110
        T("09:02:05", 122),                                  # 候選 105−2＝103；122 < 103＋20，不移
        T("09:02:06", 123),                                  # 123 ≥ 123：停損移到 103
        T("09:03:10", 130), T("09:03:30", 128),              # 移動後的 K 棒：09:02 那根（含 122、123）低點 122
        T("09:04:10", 145),                                  # 候選 min(122,128)−2＝120；145 ≥ 140：移到 120
        T("09:05:00", 119),                                  # 碰到 120 以下：出場 119−1
    ]
    tr = run(ticks)
    assert [m[1] for m in tr.moves] == [103, 120]
    assert tr.why == "trail" and tr.px_out == 118 and tr.gross == 17


def test_short_side_mirrors_long():
    ticks = [T("08:59:31", 100), T("09:00:10", 95), T("09:00:40", 96), T("09:01:30", 76), T("09:02:00", 38)]
    tr = run(ticks, side="short")
    assert tr.px_in == 99 and tr.stop0 == 109 and tr.target == 39
    assert tr.moves and tr.moves[0][1] == 98             # 09:00 那根最高 96 ＋ 2；76 ≤ 98 − 20
    assert tr.why == "target" and tr.gross == 60


def test_no_trade_after_decision_returns_none():
    assert run([T("08:59:10", 100), T("08:59:30", 100)]) is None


def test_last_le():
    ticks = [T("08:59:00", 1), T("08:59:30", 2), T("08:59:31", 3)]
    assert S.last_le(ticks, D) == 2 and S.last_le(ticks, D - 31) is None
