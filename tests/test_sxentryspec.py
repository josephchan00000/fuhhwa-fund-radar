"""新飆股「到條件才買」（W11）的規格鎖定：算任何一組報酬之前寫定（arm/lab/sxentryspec.py、docs/lab_pick_arch_plan.md 第 7 節）。"""
from arm.lab import sxentryspec as S
from arm.lab import sxfixspec as F


def test_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-30"
    assert S.BASE == ("s8", "new", "off", "h60") and S.BASE in F.GRID          # W10 挑出來的那一組
    assert S.ENTRY == ("E0", "E1", "E2", "E3", "E4") and S.DESCRIBE == ("E0r",)
    assert (S.E1_DAYS, S.E2_DAYS, S.E2_MA, S.E3_DAYS, S.E3_HIGH) == (5, 10, 10, 10, 20)
    assert S.E4_MIX == ("E0", "E2", 0.5)
    assert S.START == F.START == "2019-01-02" and S.HALVES == F.HALVES
    assert S.PASS == {"mdd_pick": 10.0, "mdd_extra": 0.0}
    assert [S.window(e) for e in ("E0r", "E1", "E2", "E3")] == [1, 5, 11, 11]
    assert set(S.NAMES) == set(S.ENTRY) | set(S.DESCRIBE)


def _r(a, h1, h2, dd, dd1):
    return {"cagr": {"all": a, "h1": h1, "h2": h2}, "mdd": {"all": dd, "h1": dd1}}


def test_pick_and_verdict():
    runs = {e: _r(0.50, 0.34, 0.70, 0.42, 0.42) for e in S.ENTRY}
    assert S.verdict(runs) == ("不換", "E0")                               # 全部一樣＝現在的做法
    runs["E2"] = _r(0.52, 0.36, 0.72, 0.40, 0.40)
    assert S.pick(runs) == "E2" and S.verdict(runs) == ("換", "E2")
    runs["E2"] = _r(0.52, 0.36, 0.72, 0.43, 0.40)                          # 整段回落比 E0 深一點點就不換（mdd_extra＝0）
    assert S.verdict(runs) == ("不換", "E2")
    runs["E2"] = _r(0.52, 0.36, 0.65, 0.40, 0.40)                          # 2023 年起輸
    assert S.verdict(runs) == ("不換", "E2")
    runs["E2"] = _r(0.52, 0.40, 0.72, 0.40, 0.53)                          # 前半回落深超過 10 點＝不能挑
    assert S.pick(runs) == "E0"
    runs["E3"] = _r(0.55, 0.36, 0.75, 0.30, 0.30)
    runs["E1"] = _r(0.55, 0.36, 0.75, 0.30, 0.30)                          # 同分取前面的
    assert S.pick(runs) == "E1"
