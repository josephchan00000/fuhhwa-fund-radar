"""台指選擇權規格 txospec VER 1 鎖定（docs/lab_txo_plan.md 第 16 節）：算任何成績之前寫定，改任何常數都要 VER＋1。"""
from arm.lab import txospec as S


def test_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-11-05"
    assert S.fingerprint() == "95b3382fa1b170ae"


def test_user_decisions():
    # 使用者 2026-11-04：每筆上限 O1 2%／O2 3%／O3 5%，一天 4%、一個月 12%，手續費 25 元另試 50 元
    assert S.CAP == {"O1": 0.02, "O2": 0.03, "O3": 0.05}
    assert (S.DAY_STOP, S.MONTH_STOP, S.FEE, S.FEE_ALT) == (0.04, 0.12, 25, 50)


def test_tick_and_cost():
    assert [S.tick(p) for p in (9.9, 10, 49.5, 50, 499, 500, 999, 1000)] == [0.1, 0.5, 0.5, 1, 1, 5, 5, 10]
    assert S.side_cost(20) == 25 + 0.001 * 20 * 50 + 0.5 * 50
    assert S.side_cost(20, mult=2) == 2 * S.side_cost(20)
    assert S.lots(1_000_000, 0.02, 20) == 19 and S.lots(1_000, 0.02, 20) == 0


def test_grid_and_rules():
    g = S.grid_o1()
    assert len(g) == 12 and len({tuple(sorted(x.items())) for x in g}) == 12
    assert S.O3_RULES == ("lnypre", "santa") and S.O2_EVENTS == ("cpi", "fomc")
