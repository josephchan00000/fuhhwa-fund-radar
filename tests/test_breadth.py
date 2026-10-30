"""寬度與深度的算法（arm/lab/breadth.py；規格 breadthspec VER 1）：小資料驗算。"""
import random

import numpy as np

from arm.lab import breadth as BR
from arm.lab import breadthspec as S


def test_tw_ewgap_and_ma200_on_small_matrices():
    cal = [f"2020-01-{d:02d}" for d in range(1, 7)]
    C = np.array([[10, 11, 12, 13, 14, 15], [10, 10, 10, 10, 10, 20], [10, np.nan, 10, 10, 10, 10]], dtype=float)
    E = np.ones_like(C, dtype=bool) & ~np.isnan(C)
    tr = {d: 100.0 + 10 * i for i, d in enumerate(cal)}
    g = BR.ewgap_tw(cal, C, E, tr, lb=2, min_n=2)
    # 1/3：指數 120/100−1＝20%；三檔 20%、0%、0% → 平均 6.67% → 差 13.33 個百分點
    assert round(g["2020-01-03"], 6) == round(20 - 20 / 3, 6)
    # 1/4：指數 130/110−1；第三檔 1/2 沒收盤不算 → 兩檔平均
    assert round(g["2020-01-04"], 6) == round(100 * ((130 / 110 - 1) - (13 / 11 - 1) / 2), 6)
    m = BR.ma200_tw(cal, C, E, n=3, min_n=2)
    assert "2020-01-02" not in m and "2020-01-03" in m           # 近 3 天都要有收盤；第三檔 1/2 缺價，1/3 只剩兩檔
    # 1/6：第一檔 15 ÷ 14 − 1、第二檔 20 ÷ (40/3) − 1、第三檔 10 ÷ 10 − 1 → 中位數＝第一檔
    assert round(m["2020-01-06"], 6) == round(100 * (15 / 14 - 1), 6)


def test_us_adv_upv_and_ewgap():
    br = {f"2020-01-{d:02d}": [d, 10 - d, 0, 2 * d, 10, 0, 0, 10, 10] for d in range(1, 5)}
    adv, upv = BR.us_adv(br, w=2)
    assert "2020-01-01" not in adv and round(adv["2020-01-02"], 6) == round(100 * 3 / 20, 6)
    assert round(upv["2020-01-04"], 6) == round(100 * 14 / 34, 6)
    cw = {"a": 100.0, "b": 110.0, "c": 121.0}
    ew = {"a": 100.0, "b": 100.0, "c": 100.0, "d": 90.0}
    g = BR.ewgap_us(cw, ew, lb=2)                                        # 只用兩檔都有收盤的日子
    assert list(g) == ["c"] and round(g["c"], 9) == 21.0


def test_heat100_never_looks_ahead(monkeypatch):
    from arm.lab import heatspec as HS
    monkeypatch.setitem(HS.PCT_WIN, "d", 10)
    monkeypatch.setitem(HS.PCT_MIN, "d", 3)
    cal = [str(i) for i in range(30)]
    raw = {d: float(i % 7) for i, d in enumerate(cal)}
    a = BR.heat100(cal, raw)
    raw2 = dict(raw, **{cal[29]: 1e9, cal[28]: -1e9})                # 改最後兩天，前面的 0～100 不變
    b = BR.heat100(cal, raw2)
    assert np.allclose(a[:28], b[:28], equal_nan=True) and np.isnan(a[:3]).all()


def test_breadth_series_depth_and_forward_drawdown():
    Lv = {"A": {"2000-01": 2, "2000-02": 0}, "B": {"2000-01": 0, "2000-02": 3}, "C": {"2000-02": 4}}
    caps = {"A": {"2000-01": 30.0}, "B": {"2000-01": 70.0, "2000-02": 10.0}, "C": {"2000-02": 90.0}}
    s = BR.breadth_series(Lv, caps)
    assert s["2000-01"] == [1, 2, 0.5, 0.3] and s["2000-02"][:3] == [2, 3, 2 / 3] and abs(s["2000-02"][3] - 1.0) < 1e-12
    me = {f"2001-{m:02d}": v for m, v in zip(range(1, 13), [100, 120, 90, 95, 100, 101, 102, 103, 104, 105, 106, 107])}
    me.update({"2002-01": 108.0, "2002-02": 109.0})
    dd = BR.fwd_dd(me, h=12)
    assert abs(dd["2001-01"] - 0.25) < 1e-12 and dd["2001-03"] is None    # 1 月：高點 120 → 90；3 月之後沒走完 12 個月
    gap = dict(me)
    del gap["2001-06"]
    assert BR.fwd_dd(gap, h=12)["2001-01"] is None                       # 中間缺月不算


def test_tests_one_and_two_use_spec_rules():
    ms = [f"{1931 + i // 12}-{i % 12 + 1:02d}" for i in range(240)]
    ev = {m: (i % 40) < 6 for i, m in enumerate(ms)}                   # 6 段事件
    dd = {m: (0.3 if ((i % 40) < 6 or i % 9 == 0) else 0.05) for i, m in enumerate(ms)}
    one = BR.test_one(ev, dd, random.Random(S.SEED))
    assert one["n_ev"] == 36 and one["epi"] == 6 and one["p_ev"] == 1.0 and one["diff"] > S.EDGE
    assert one["lo"] is not None and one["lo"] > 0 and one["pass"]
    again = BR.test_one(ev, dd, random.Random(S.SEED))
    assert (again["lo"], again["hi"]) == (one["lo"], one["hi"])         # 固定種子：每次一樣
    lv = {m: (2 if i % 2 == 0 else 0) for i, m in enumerate(ms)}
    two = BR.test_two(ev, lv, dd, random.Random(S.SEED))
    assert two["n_g"] == 120 and two["p_ev"] == 1.0 and two["epi_ev"] >= 3 and two["diff"] > 0
