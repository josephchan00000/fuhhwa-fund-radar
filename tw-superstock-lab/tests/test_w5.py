"""W5：照書修正的 VCP（V3）與交易命中標籤（reports/W5_plan.md 第 3、4 節）。"""
import numpy as np
import pandas as pd

from superstock import engine as EN
from superstock import features as FT


def _p(*hl):
    return [(hi, lo, 10 * k, 10 * k + 5) for k, (hi, lo) in enumerate(hl)]


def test_v3_accepts_textbook_contraction():
    pairs = _p((100, 80), (96, 86), (95, 91))                       # 20% → 10% → 4%，低點墊高、最後一段在上半部
    for spec in (FT.VCP_V2, FT.VCP_V3):
        assert FT.vcp_check(pairs, 95.0, 94.0, 0.5, spec)


def test_v3_rejects_what_v2_lets_through():
    lower_low = _p((100, 80), (96, 78), (90, 86))                   # 第二段低點更低
    low_in_base = _p((100, 70), (85, 72), (80, 76))                 # 低點墊高，但最後一段在基底下半部
    deeper = _p((100, 93.0), (99, 91.6))                            # 7.0% → 7.5%：比前一段深，但在 1.1 倍以內
    for pairs, piv, close in ((lower_low, 90.0, 89.0), (low_in_base, 80.0, 79.0), (deeper, 99.0, 98.0)):
        assert FT.vcp_check(pairs, piv, close, 0.5, FT.VCP_V2)
        assert not FT.vcp_check(pairs, piv, close, 0.5, FT.VCP_V3)
    ok = _p((100, 80), (96, 86), (95, 91))
    assert FT.vcp_check(ok, 95.0, 96.0, 0.5, FT.VCP_V2)             # 收盤已在樞紐之上：V2 仍算成形
    assert not FT.vcp_check(ok, 95.0, 96.0, 0.5, FT.VCP_V3)         # V3 只算還沒突破
    assert FT.VCP_V3S["base_min"] == 15 and FT.VCP_V3["base_min"] == FT.VCP_V2["base_min"] == 30


def _mk(c, h, l):
    T = len(c)
    a = lambda x: np.asarray(x, dtype=float)[:, None]               # noqa: E731
    return EN.Market(pd.bdate_range("2015-01-01", periods=T), ["1234"], a(c), a(h), a(l), a(c),
                     value=a([1e8] * T), volume=a([1e6] * T))


def test_race_label():
    c = [100.0] * 12
    h = [100, 101, 105, 121, 100, 100, 100, 100, 100, 100, 100, 100]   # 第 3 天碰到 +20%
    l = [100, 99, 95, 99, 91, 100, 100, 100, 100, 100, 100, 100]
    y, und = FT.race(_mk(c, h, l), 0.20, 0.08, 5)
    assert y[0, 0] == 1.0 and y[3, 0] == 0.0                         # 第 0 天：先 +20%；第 3 天：之後先 −8%（91）
    h2 = [100, 121, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100]
    l2 = [100, 90, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100]
    y2, _ = FT.race(_mk(c, h2, l2), 0.20, 0.08, 5)
    assert y2[0, 0] == 0.0                                           # 同一天兩個都碰到 → 失敗
    flat = [100.0] * 12
    y3, und3 = FT.race(_mk(flat, flat, flat), 0.20, 0.08, 5)
    assert y3[0, 0] == 0.0 and und3[0, 0]                            # 5 日都沒碰到 → 0，另記
    assert np.isnan(y3[8, 0]) and not und3[8, 0]                     # 還沒走完 → 不知道
