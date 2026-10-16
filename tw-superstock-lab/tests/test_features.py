"""features（趨勢樣板、RS、VCP 3% 轉折、標籤）與 S01 訊號：人造價格驗證。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from superstock import features as FT
from superstock import strategies as ST
from superstock.engine import Market


def _path(points: list[tuple[int, float]]) -> np.ndarray:
    """(天數, 價) 的轉折點之間線性內插 → 每日收盤。"""
    xs, ys = zip(*points)
    return np.interp(np.arange(xs[-1] + 1), xs, ys)


def _market(closes: np.ndarray, vol: np.ndarray | None = None, wiggle: float = 0.004) -> Market:
    c = np.asarray(closes, dtype=float)[:, None]
    h, l = c * (1 + wiggle), c * (1 - wiggle)
    v = np.full_like(c, 1e6) if vol is None else np.asarray(vol, dtype=float)[:, None]
    dates = pd.bdate_range("2014-01-01", periods=len(c))
    return Market(dates, ["1234"], c, h, l, c, value=c * v, volume=v)


def _vcp_closes() -> np.ndarray:
    """250 天往上走（100→200）＝第二階段；之後基底：高點 200 → −24% → 196 → −12% → 194 → −5% → 回到 193。"""
    return _path([(0, 100), (250, 200), (275, 152), (300, 196), (320, 172.5), (340, 194), (352, 184.3), (365, 193)])


def test_zigzag_finds_textbook_contractions():
    c = _vcp_closes()
    m = _market(c, wiggle=0.0)
    zz = FT.ZigZag(m.h[:, 0], m.l[:, 0], 250, 0.03)
    zz.advance(365)
    pairs, pivot = zz.contractions()
    ds = [round(1 - lo / hi, 3) for hi, lo, _, _ in pairs]
    assert ds == [0.24, 0.12, 0.05]
    assert pivot == 194.0
    assert FT.vcp_check(pairs, pivot, 193.0, 0.6)
    assert not FT.vcp_check(pairs, pivot, 193.0, 0.8)            # 量沒縮
    assert not FT.vcp_check(pairs[:1], pivot, 193.0, 0.6)        # 只有一段


def test_vcp_rejects_expanding_and_deep_bases():
    exp = _path([(0, 100), (250, 200), (270, 186), (290, 198), (315, 160), (340, 194)])   # 7% 之後 19%：放大
    m = _market(exp, wiggle=0.0)
    zz = FT.ZigZag(m.h[:, 0], m.l[:, 0], 250, 0.03)
    zz.advance(340)
    pairs, pivot = zz.contractions()
    assert not FT.vcp_check(pairs, pivot, 194.0, 0.5)
    deep = _path([(0, 100), (250, 200), (280, 120), (310, 190), (330, 178), (345, 188)])  # 第一段 40% > 35%
    m = _market(deep, wiggle=0.0)
    zz = FT.ZigZag(m.h[:, 0], m.l[:, 0], 250, 0.03)
    zz.advance(345)
    pairs, pivot = zz.contractions()
    assert not FT.vcp_check(pairs, pivot, 188.0, 0.5)


def test_zigzag_state_uses_no_future():
    """任一天的轉折狀態只看到那天為止：在第 t 天停下來，和之後才停的結果在 t 天的樣子一致。"""
    c = _vcp_closes()
    m = _market(c, wiggle=0.0)
    for t in (280, 305, 330, 360):
        a = FT.ZigZag(m.h[:, 0], m.l[:, 0], 250, 0.03)
        a.advance(t)
        trunc = _market(c[: t + 1], wiggle=0.0)
        b = FT.ZigZag(trunc.h[:, 0], trunc.l[:, 0], 250, 0.03)
        b.advance(t)
        assert a.contractions() == b.contractions()


def _breakout_market():
    """VCP 之後第 366 天放量突破樞紐 194。"""
    c = np.concatenate([_vcp_closes(), [199.0, 203.0, 206.0, 208.0]])
    vol = np.full(len(c), 1e6)
    vol[355:366] = 4e5                                           # 最後一段量縮
    vol[366] = 2.5e6                                             # 突破日放量
    return _market(c, vol, wiggle=0.002)


def test_s01_signal_on_breakout_day_only():
    m = _breakout_market()
    F = FT.compute(m)
    F["tt_pass"] = F["elig"].copy()                              # 一檔股票排不出 RS，這裡只驗 VCP＋突破＋量
    sig = ST.signals(m, F, ST.spec_of("S01"))
    assert list(sig["date"]) == [m.dates[366]]
    assert float(F["vcp_pivot"][365, 0]) > 190                   # 突破前一天的樞紐


def test_s01_signal_identical_when_future_changes():
    """把突破日之後的資料改掉，突破日當天的訊號不變（沒有用到未來）。"""
    m = _breakout_market()
    F = FT.compute(m)
    F["tt_pass"] = F["elig"].copy()
    c2 = m.c.copy()
    c2[367:] = 120.0
    m2 = Market(m.dates, m.stocks, c2, c2 * 1.002, c2 * 0.998, c2, value=c2 * m.vol, volume=m.vol)
    F2 = FT.compute(m2)
    F2["tt_pass"] = F2["elig"].copy()
    a = ST.signals(m, F, ST.spec_of("S01"))
    b = ST.signals(m2, F2, ST.spec_of("S01"))
    assert list(a["date"]) == list(b["date"])


def test_trend_template_and_rs_rank():
    T = 400
    up = _path([(0, 100), (T - 1, 260)])
    down = _path([(0, 260), (T - 1, 100)])
    c = np.stack([up, down, _path([(0, 100), (T - 1, 150)])], axis=1)
    v = np.full_like(c, 1e6)
    dates = pd.bdate_range("2014-01-01", periods=T)
    m = Market(dates, ["1111", "2222", "3333"], c, c * 1.003, c * 0.997, c, value=c * v, volume=v)
    el = FT.eligible(m)
    tr = FT.trend(m, el)
    assert tr["tt_pass"][T - 1, 0] and not tr["tt_pass"][T - 1, 1]
    assert tr["rs"][T - 1, 1] < tr["rs"][T - 1, 0]


def test_label_uses_next_n_days_only():
    c = np.concatenate([np.full(100, 100.0), np.full(20, 160.0), np.full(100, 100.0)])
    m = _market(c, wiggle=0.0)
    y = FT.label(m, 60, 0.5)
    assert y[60, 0] == 1.0 and y[40, 0] == 1.0 and y[39, 0] == 0.0   # 第 100 天漲上去：第 40 天的「之後 60 天」剛好含到
    assert np.isnan(y[-1, 0])                                        # 尾端未來還沒發生


def test_variants_only_touch_declared_keys():
    for name, d in ST.VARIANTS.items():
        assert set(d) <= set(ST.S01), name
    assert ST.S01 == {"entry": "open", "vol": 1.5, "stop_pct": 0.08, "breakeven_r": 2.0, "ma_exit": 50,
                      "market": True, "tt": True, "vcp": True, "fund": None, "max_hold": None}
    assert FT.VCP == {"thr": 0.03, "win": 260, "base_min": 30, "n_min": 2, "n_max": 6, "grow": 1.1,
                      "d1_max": 0.35, "dn_max": 0.10, "near": 0.9, "dry": 0.7}
