"""大跌中的強落底訊號（arm/lab/bottombox.py；sigspec 第 5.5 節 VER 30）：哪些算、多強、大跌中、判定。"""
from __future__ import annotations

import numpy as np

from arm.lab import bottom as BO
from arm.lab import bottombox as BB
from arm.lab import bottomspec as BS
from arm.lab import sigspec as S


def _px() -> np.ndarray:
    """200 天 100 → 5 天跌到 92（5 日急跌、沒有跌 10%）→ 平 120 天 → 再跌到 85（跌 10% 以上）→ 回到 99。"""
    a = [100.0] * 200 + [98, 96, 95, 93, 92] + [92.0] * 120 + [90, 88, 86, 85] + [85.0] * 30 + [95, 99] + [99.0] * 40
    return np.asarray(a, dtype=float)


def test_side_of_bottom_types():
    assert BB.side_of({"cat": "buy"}) == "buy"
    assert BB.side_of({"cat": "heat", "sig": "cold", "H": 20}) == "up"
    assert BB.side_of({"cat": "bd", "sig": "cold_in", "H": 60}) == "up"
    assert BB.side_of({"cat": "heat", "sig": "cold", "H": 250}) is None          # 看 12 個月的景氣數字不算
    assert BB.side_of({"cat": "heat", "sig": "hot", "H": 20}) is None
    assert BB.side_of({"cat": "inst", "sig": "sell_run10", "H": 20}) == "up"
    assert BB.side_of({"cat": "inst", "sig": "cold", "H": 60}) is None             # 法人大買超不算
    assert BB.side_of({"cat": "scen", "var": "SC3", "H": 60}) == "up"
    assert BB.side_of({"cat": "scen", "var": "SC4", "H": 60}) is None
    assert BB.side_of({"cat": "tech", "sig": "ev", "H": 20}) is None


def test_strong_threshold():
    assert BB.strong({"n": 5, "hit": 0.70, "base": 0.60})                          # 剛好 10 點
    assert not BB.strong({"n": 5, "hit": 0.6999, "base": 0.60})
    assert not BB.strong({"n": 4, "hit": 1.0, "base": 0.60})
    assert not BB.strong({"n": 9, "hit": None, "base": 0.6})
    assert not BB.strong(None)


def test_drop_days_matches_drop_now_every_day():
    px = _px()
    g = BB.drop_days(px, "tw")
    for t in range(60, len(px)):
        assert g[t] == (BB.drop_now(px[:t + 1], "tw") is not None), t
    te = BO.events_e5(px, BS.E5_TH["tw"])[0]                                         # 5 日急跌那天（5 天跌 ≥ 6%）
    assert 200 <= te <= 204
    assert g[te] and g[te + BS.SIG_WIN] and not g[te + BS.SIG_WIN + 1] and not g[te - 1]
    assert g[330] and not g[-1]                                                      # 跌 10% 那一段，回到離高點 5% 以內就結束


def test_buy_active_stops_when_drop_ends():
    px = _px()
    T = len(px)
    te = BO.events_e5(px, BS.E5_TH["tw"])[0]
    sd0 = {"ev": "E5", "buys": [(te, te + 6, {}, {})]}
    a = BB.buy_active(sd0, px, "tw", T)
    s = te + 6 - S.LAG
    assert a[s] and not a[s - 1]
    assert a.sum() == min(S.H_BUY, te + BS.SIG_WIN + 1 - s)


def test_verdict():
    box = {"up": 0.66, "dd": 0.40}
    assert BB.verdict(box, {"up": 0.61, "dd": 0.48}, 5) == "ok"
    assert BB.verdict(box, {"up": 0.61, "dd": 0.48}, 4) == "few"
    assert BB.verdict(box, {"up": 0.62, "dd": 0.48}, 9) == "no"                    # 只高 4 點
    assert BB.verdict(box, {"up": 0.60, "dd": 0.39}, 9) == "no"                    # 大回撤比較多


def test_fair_html(monkeypatch):
    """研究紀錄「偏多、警示的強弱」（sigspec 第 5.7 節，VER 32）：兩個研究檔都沒有就不列；有就列兩張表、結論從資料來、名稱有跳脫。"""
    from arm.lab import sigpage as P
    from arm.lab import thermocal as TC
    monkeypatch.setattr(BB, "load", lambda: None)
    monkeypatch.setattr(TC, "level_load", lambda: None)
    assert P.fair_html() == ""
    g = {"n": 10, "up": 0.66, "dd": 0.4}
    monkeypatch.setattr(BB, "load", lambda: {"mk": {"tw": {"box": g, "drop": {"n": 20, "up": 0.6, "dd": 0.48}, "ep": 9, "v": "ok"},
                                                    "spx": {"box": g, "drop": {"n": 20, "up": 0.7, "dd": 0.3}, "ep": 9, "v": "no"}}})
    c = {"up": {"s": [0.8, 200], "w": [0.7, 200], "d": 0.1, "v": "ok"}, "warn": {"s": [0.3, 200], "w": [0.3, 200], "d": 0.0, "v": "no"}}
    monkeypatch.setattr(TC, "level_load", lambda: {"mk": {"spx": {"cmp": {"short": c}}}})
    h = P.fair_html()
    assert "台股分得出" in h and "S&amp;P 500分不出" in h and "S&P" not in h.replace("S&amp;P", "")
    assert "差到 5 點的只有S&amp;P 500短線" in h and "+10.0" in h
