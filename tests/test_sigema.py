"""EMA 賣壓的程式（arm/lab/sigema.py；emaspec VER 1）。用造出來的資料，不讀落檔。"""
import numpy as np

from arm.lab import emaspec as E
from arm.lab import sigema as M


def test_ema_ratio_recursion_warmup_and_gaps():
    cal = [f"2020-01-{d:02d}" for d in range(1, 13)]
    a = {d: (10.0 if i % 2 else -10.0) for i, d in enumerate(cal)}
    b = {d: 100.0 for d in cal}
    a.pop(cal[3])                                   # 少一天：不更新、不出值
    out = M.ema_ratio(cal, a, b, 5)
    assert cal[3] not in out and min(out) == cal[5]  # 更新滿 5 次（第 0、1、2、4、5 天）才有值
    al = E.alpha(5)
    ea = -10.0
    for d in cal[1:]:
        if d in a:
            ea = al * a[d] + (1 - al) * ea
            if d in out:
                assert abs(out[d] - ea) < 1e-12      # 成交金額固定 100 → 比值就是 EMA(a)
    assert M.ema_ratio(cal, {}, b, 5) == {}


def test_one_small_buy_does_not_reset():
    """連續賣超中間一天小買：連續天數歸零，EMA 賣壓只小降。"""
    cal = [f"2020-02-{d:02d}" for d in range(1, 26)]
    a = {d: -100.0 for d in cal}
    a[cal[15]] = 5.0
    b = {d: 1000.0 for d in cal}
    out = M.ema_ratio(cal, a, b, 5)
    assert out[cal[14]] < 0 and out[cal[15]] < 0 and out[cal[15]] > out[cal[14]]
    assert out[cal[15]] < out[cal[14]] * 0.5         # 還是賣壓（負的），只比前一天小一些


def test_listed_metrics_and_diff_ci():
    recs = [{"id": "a", "d": "up", "yr": y, "n": 9, "e": 0.08, "o": 0.05 + 0.01 * (y % 2)} for y in range(2010, 2020)]
    recs += [{"id": "b", "d": "warn", "yr": 2012, "n": 9, "e": 0.01, "o": 0.5}]       # 沒過門檻：不算
    m = M.metrics(recs)
    assert m["all"]["n"] == 10 and abs(m["all"]["mean"] - 0.055) < 1e-12 and m["all"]["pos"] == 1.0 and m["warn"]["n"] == 0
    other = [{**r, "o": r["o"] - 0.02} for r in recs]
    d = M.diff_ci(recs, other, draws=200)
    assert abs(d["d"] - 0.02) < 1e-12 and d["lo"] > 0 and d["years"] == 10
    assert M.diff_ci(recs[:1], other[:1])["d"] is None
