"""新飆股買賣做法（W10）的規格鎖定：算任何一組之前寫定（arm/lab/sxfixspec.py、docs/lab_boom_v2_plan.md）。"""
from arm.lab import sepa
from arm.lab import sxfixspec as S


def test_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-29"
    assert S.SIZE == {"cur": {"weight": 0.125, "slots": None, "max_pos": 20},
                      "s10": {"weight": None, "slots": 10, "max_pos": 10},
                      "s8": {"weight": None, "slots": 8, "max_pos": 8}}
    assert S.MIN_SLOT == 0.5 and S.ORDER == ("rs", "new") and S.EXT == ("off", "on") and S.HOLD == ("h60", "renew")
    assert S.EXT_MA50 == 1.25 == sepa.EXT_MA50
    assert S.HOLD_N == 60 and S.HOLD_MAX == 250
    assert len(S.GRID) == 24 and S.GRID[0] == S.CURRENT == ("cur", "rs", "off", "h60")
    assert S.START == "2019-01-02" and S.HALVES == (("2019-01-01", "2022-12-31"), ("2023-01-01", "2100-12-31"))
    assert S.PASS == {"mdd_extra": 10.0}


def _r(a, h1, h2, dd, dd1):
    return {"cagr": {"all": a, "h1": h1, "h2": h2}, "mdd": {"all": dd, "h1": dd1}}


def test_pick_and_verdict():
    runs = {g: _r(0.40, 0.20, 0.60, 0.46, 0.37) for g in S.GRID}
    assert S.verdict(runs) == ("不換", S.CURRENT)                     # 全部一樣＝現行
    g = S.GRID[5]
    runs[g] = _r(0.45, 0.25, 0.62, 0.50, 0.40)
    assert S.pick(runs) == g and S.verdict(runs) == ("換", g)
    runs[g] = _r(0.45, 0.25, 0.55, 0.50, 0.40)                           # 後半輸
    assert S.verdict(runs) == ("不換", g)
    runs[g] = _r(0.45, 0.30, 0.62, 0.50, 0.50)                           # 前半回落深超過 10 點＝不能挑
    assert S.pick(runs) == S.CURRENT
    runs[g] = _r(0.45, 0.25, 0.62, 0.57, 0.40)                           # 整段回落深超過 10 點
    assert S.verdict(runs) == ("不換", g)
