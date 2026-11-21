"""大盤修正中的領導股（arm/lab/leaders.py；規格 arm/lab/leadspec.py VER 1）。"""
from arm.lab import leaders as L


def test_market_correction_and_ma():
    idx = [100.0] * 300 + [72.0]
    m = L.market(idx, len(idx) - 1)
    assert m["corr"] and abs(m["dd"] + 0.28) < 1e-9 and m["below200"] and m["vs50"] < 0
    assert not L.market([100.0] * 300 + [90.0], 300)["corr"]                     # 跌 10%：不算修正


def test_passes_three_conditions():
    mk = {"corr": True, "dd": -0.28}
    tt = [True, True, True, True, False, True, True, True]
    ok = {"el": True, "d52h": -0.10, "rs": 95, "tt": tt}
    assert L.passes(ok, mk)
    assert not L.passes(dict(ok, d52h=-0.15), mk)                                # 跌超過指數的一半
    assert not L.passes(dict(ok, rs=89), mk)
    assert not L.passes(dict(ok, tt=[False] + tt[1:]), mk)                       # 收盤不在 150／200 日線上
    assert not L.passes(dict(ok, tt=tt[:2] + [False] + tt[3:]), mk)              # 200 日線沒上揚
    assert not L.passes(ok, {"corr": False, "dd": -0.10})                        # 不在修正中不列
    assert not L.passes(dict(ok, el=False), mk)


def test_three_gates():
    assert L.three_gates({"ey": 0.56, "ry3": 0.43, "eacc": 0.1}) is True
    assert L.three_gates({"ey": 3.0, "ry3": 1.5, "eacc": -0.1, "racc": -0.2}) is False
    assert L.three_gates({"ey": None, "ry3": 0.3}) is None
