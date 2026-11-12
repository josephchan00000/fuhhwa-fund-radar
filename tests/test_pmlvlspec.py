"""盤前價位第 4 段規格（pmlvlspec VER 1）鎖定：改任何常數都要 VER＋1 並更新這裡（docs/lab_premarket_plan.md 第 15 節）。"""
from arm.lab import pmlvlspec as S


def test_spec_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-11-12"
    assert S.fingerprint() == "097c2297ca80dcea"


def test_grid_and_cost():
    g = S.grid()
    assert len(g) == 36 and g[0] == (0.25, 0.15, 0.25) and g[-1] == (1.0, 0.5, 1.0)
    assert S.FAMILIES == ("rev", "brk") and S.COST_MULT == 2
    assert round(S.side_cost(44000), 1) == 119.0                    # 25＋0.00002×44000×50＋50
    from arm.lab import premkt
    assert round(premkt.fut_cost(44000), 1) == round(S.side_cost(44000), 1)   # 同頁面的成本
