"""研究方法檢查（arm/lab/fairchk.py；sigspec 第 5.9 節 VER 33）的小工具與第二套大跌判斷。"""
from __future__ import annotations

import numpy as np

from arm.lab import bottombox as BB
from arm.lab import fairchk as FC
from arm.lab import sigspec as S


def _px() -> np.ndarray:
    a = [100.0] * 200 + [98, 96, 95, 93, 92] + [92.0] * 120 + [90, 88, 86, 85] + [85.0] * 30 + [95, 99] + [99.0] * 40
    rng = np.random.default_rng(7)
    b = list(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 600))))
    return np.asarray(a + b, dtype=float)


def test_drop2_matches_drop_days():
    px = _px()
    for mk in ("tw", "spx", "sox"):
        assert (FC.drop2(px, mk)[0] == BB.drop_days(px, mk)).all()


def test_rate_and_seg_rate():
    t = np.arange(8)
    Y = np.array([1, 0, 1, 1, np.nan, 0, 0, 1], dtype=float)
    m = np.array([1, 1, 0, 1, 1, 0, 1, 1], dtype=bool)
    assert FC.rate(m, t, Y) == [3 / 5, 5]
    assert FC.seg_rate(m, t, Y) == [(0.5 + 1.0 + 0.5) / 3, 3]                 # 三段：[1,0]、[1,nan]、[0,1]
    assert FC.seg_rate(np.zeros(8, dtype=bool), t, Y) == [None, 0]


def test_wmedian():
    assert FC.wmedian(np.array([1.0, 2.0, 3.0]), np.array([1, 0, 3])) == 3.0
    assert FC.wmedian(np.array([np.nan, 2.0]), np.array([5, 1])) == 2.0
    assert FC.wmedian(np.array([1.0]), np.array([0])) is None


def test_verdicts():
    assert FC.vbox([0.66, 9], [0.60, 9], [0.40, 9], [0.48, 9], 5) == "ok"
    assert FC.vbox([0.66, 9], [0.60, 9], [0.50, 9], [0.48, 9], 5) == "no"
    assert FC.vbox([0.66, 9], [0.60, 9], None, None, 5) == "ok"                # 只比上漲
    assert FC.vbox([0.66, 9], [0.60, 9], [0.40, 9], [0.48, 9], 4) == "few"
    assert FC.vlevel([0.80, S.CAL_MIN_WEEKS], [0.70, 500]) == "ok"
    assert FC.vlevel([0.80, S.CAL_MIN_WEEKS - 1], [0.70, 500]) == "few"
    assert FC.vlevel([0.74, 500], [0.70, 500]) == "no"


def test_flips():
    B = {"tw": {"main": {"v": "ok"}, "B1": {"v": "no"}, "B2": {"v": "ok"}, "B3": {"20": {"v": "few"}}, "B4": {"0.05": {"v": "ok"}}}}
    L = {"tw": {"main": {"long": {"up": {"v": "ok"}}}, "L1": {"long": {"up": {"v": "no"}}}, "L2": {"0.2": {"long": {"up": {"v": "ok"}}}}}}
    assert FC.flips(B, L) == [["tw:B1", "ok", "no"], ["tw:L1:long:up", "ok", "no"]]


def test_tally_and_research_text(monkeypatch):
    """研究紀錄「③ 換算法再算一次」的數字都由研究檔算（fairchk.tally → sigpage._fair_chk）。"""
    from arm.lab import sigpage as P
    g = lambda u, d: {"up": u, "dd": d, "n": 100}                                   # noqa: E731
    bx = {"main": {"box": g(0.66, 0.4), "drop": g(0.60, 0.48), "v": "ok"},
          "B1": {"box": [[0.66, 9], [0.4, 9]], "base": [[0.65, 9], [0.3, 9]], "v": "no"},
          "B2": {"box": [[0.70, 9], [0.3, 9]], "base": [[0.68, 9], [0.4, 9]], "v": "no"},
          "B3": {"120": {"box": [0.73, 9], "base": [0.67, 9], "v": "ok"}},
          "B4": {"0.05": {"box": g(0.64, 0.4), "drop": g(0.60, 0.5), "v": "no"}}, "B6": {"ok": True}}
    lv = {"s": [0.8, 500], "w": [0.7, 500], "v": "ok"}
    L = {"tw": {"main": {"long": {"up": lv, "warn": lv}}, "L1": {"long": {"up": lv, "warn": lv}},
                "L2": {"0.15": {"long": {"up": lv, "warn": lv}}}, "L4": {"ok": True}}}
    R = {"ver": S.CHK_VER, "bottom": {"tw": bx}, "level": L}
    T = FC.tally(R)
    assert T["bottom"]["tw"] == {"n": 5, "pos": 5, "lo": T["bottom"]["tw"]["lo"], "hi": T["bottom"]["tw"]["hi"], "ok": 2}
    assert abs(T["bottom"]["tw"]["lo"] - 0.01) < 1e-9 and abs(T["bottom"]["tw"]["hi"] - 0.06) < 1e-9
    assert T["level"]["up"]["n"] == 3 and T["level"]["up"]["ok"] == 3 and T["second"] == {"bottom": True, "level": True}
    monkeypatch.setattr(FC, "load", lambda: R)
    h = P._fair_chk()
    assert "台股 5 種算法裡 5 種" in h and "到 5 點的 2 種" in h and "數字完全一樣" in h
    monkeypatch.setattr(FC, "load", lambda: None)
    assert P._fair_chk() == ""
