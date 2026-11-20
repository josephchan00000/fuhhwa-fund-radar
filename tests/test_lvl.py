"""價位補充規則（arm/lab/heattech.fill_levels；規格 arm/lab/lvlspec.py VER 1）。"""
from arm.lab import heattech as TT


def _series(path):
    px, p = [], 100.0
    for step, n in path:
        for _ in range(n):
            p *= 1 + step
            px.append(round(p, 4))
    return px, [f"D{i:05d}" for i in range(len(px))]


def test_support_falls_back_to_older_pivots():
    # 先漲、回檔做出一組較早的高低點；再大漲到高檔、來回震盪做出很多轉折點；最後一路跌到所有近期轉折點下面
    top = [(-0.008, 8), (0.008, 8)] * 5
    px, cal = _series([(0.01, 50), (-0.01, 10), (0.01, 80)] + top + [(-0.015, 45)])
    lv = TT.levels(px, cal)
    out = TT.fill_levels(px, cal, lv)
    pv = TT.confirmed(TT.pivots(px), len(px) - 1)
    assert lv["sup"] is None and len([x for x in pv if x["p"] > px[-1]]) >= 6        # 原規則找不到
    old_below = max((x for x in pv if x["p"] < px[-1]), key=lambda x: x["p"])
    assert out["sup"]["old"] and out["sup"]["v"] == old_below["p"] and out["sup"]["dist"] < 0
    assert out["leg"]["k"] == "L" and out["leg"]["p"] == px[-1] and out["leg"]["p"] < out["lo"]["p"]
    assert lv is not out and "leg" not in lv                         # 原規則的結果不改


def test_nothing_below_says_none():
    px, cal = _series([(0.01, 80), (-0.02, 60)])                    # 一直跌到最低：近 3 年沒有更低的轉折點
    out = TT.fill_levels(px, cal, dict(TT.levels(px, cal), sup=None))
    assert out["sup"] == {"none": True}


def test_untouched_when_rule_finds_levels():
    px, cal = _series([(0.01, 60), (-0.01, 12), (0.01, 40)])
    lv = TT.levels(px, cal)
    out = TT.fill_levels(px, cal, lv)
    if lv["sup"] is not None:
        assert out["sup"] == lv["sup"]
