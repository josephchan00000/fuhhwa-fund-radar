"""台指選擇權規格 txospec 鎖定（docs/lab_txo_plan.md 第 16、19 節）：算任何成績之前寫定，改任何常數都要 VER＋1。
VER 2（2026-11-11）只新增 O1 對照與 O4，VER 1 的常數不動（fingerprint_v1）。"""
from arm.lab import txospec as S


def test_locked():
    assert S.VER == 2 and S.SPEC_DATE == "2026-11-11"
    assert S.fingerprint() == "08cb9f75d39f1748"


def test_ver1_constants_untouched():
    assert S.fingerprint_v1() == S.V1_FP == "95b3382fa1b170ae"          # O1～O3 的 VER 1 結果照用


def test_settle_price_official_formula():
    # 期交所：13:00（不含）～13:25（含）每 5 秒＋最後一筆收盤，簡單平均（301 個）
    idx = [float(k) for k in range(3241)]
    want = round((sum(range(2881, 3181)) + 3240) / 301, 2)
    assert S.settle_price(idx) == want
    assert (S.SETTLE_K, S.CLOSE_K, S.SETTLE_N) == ((2881, 3180), 3240, 301)
    assert 9 * 3600 + 5 * S.SETTLE_K[0] == 13 * 3600 + 5 and 9 * 3600 + 5 * S.SETTLE_K[1] == 13 * 3600 + 25 * 60


def test_ver2_decisions():
    # 使用者 2026-11-11：E1 兩條都做（O1 照 VER 1 跑、O4 新寫）、E2 O1 加兩個對照（同時買兩檔、抱到結算）
    assert S.O1_ALT == ("two", "hold") and S.TWO_GAP == 2
    assert S.O4_CHECKS == ("13:05", "13:10", "13:15", "13:20", "13:25") and S.O4_FROM == "2026-09-17"
    assert (S.O4_EDGE, S.O4_MAX_DAY, S.O4_CAP_EACH, S.O4_MIN_N, S.O4_MIN_DAYS, S.O4_TOP_DAY) == (2.0, 3, 0.01, 40, 15, 0.5)


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
