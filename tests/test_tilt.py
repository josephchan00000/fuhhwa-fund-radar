"""期貨加碼（arm/lab/tilt.py）：和逐筆直接算的版本比對。"""
import math
from datetime import date, timedelta

import numpy as np

from arm.lab import practsim as PS
from arm.lab import tilt as T
from arm.lab import tiltspec as S


def _cal(start: str, n: int) -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_div_tw_puts_gap_dividends_on_next_tr_day():
    px = np.array([100.0, 101.0, 99.0, 100.0, 102.0])
    tr = np.array([np.nan, 200.0, np.nan, 203.0, 206.0])
    d = T.div_tw(px, tr)
    assert d[0] == 0 and d[1] == 0 and d[2] == 0
    assert math.isclose(d[3], 203.0 / 200.0 - 100.0 / 101.0)
    assert math.isclose(d[4], 206.0 / 203.0 - 102.0 / 100.0)
    tot = PS.daily_ret(px) + d                            # 有連續報酬指數的日子＝報酬指數的漲跌
    assert math.isclose(tot[4], 206.0 / 203.0 - 1.0)


def test_asof_uses_previous_day_and_latest_available():
    cal = ["2020-01-30", "2020-01-31", "2020-02-03", "2020-03-02", "2020-04-01"]
    m = T.asof_monthly(cal, {"2020-01": 1.0, "2020-02": 2.0})
    assert np.isnan(m[0]) and m[1] == 1.0 and m[2] == 1.0 and m[3] == 2.0 and m[4] == 2.0
    d = T.asof_daily(cal, {"2020-01-30": 5.0, "2020-02-03": 6.0})
    assert np.isnan(d[0]) and d[1] == 5.0 and d[2] == 5.0 and d[3] == 6.0 and d[4] == 6.0


def test_div_spx_accrues_dp_by_calendar_days():
    cal = ["2020-01-30", "2020-01-31", "2020-02-03"]
    sh = {"2020-01": [100.0, 2.0, 5.0, 250.0, 2.0], "2020-02": [100.0, None, None, 250.0, 2.0]}
    d = T.div_spx(cal, sh)
    assert d[0] == 0 and math.isclose(d[1], 0.02 / 365) and math.isclose(d[2], 0.02 * 3 / 365)


def test_roll_flags_third_wednesday_tw_and_quarterly_third_friday_us():
    cal = _cal("2024-01-01", 200)
    tw = T.roll_flags("tw", cal)
    days = [cal[i] for i in np.nonzero(tw)[0]]
    assert days[:3] == ["2024-01-17", "2024-02-21", "2024-03-20"]
    us = [cal[i] for i in np.nonzero(T.roll_flags("spx", cal))[0]]
    assert us == ["2024-03-15", "2024-06-21", "2024-09-20"]
    cal2 = [d for d in cal if d != "2024-03-20"]          # 結算日休市 → 下一個交易日
    assert "2024-03-21" in [cal2[i] for i in np.nonzero(T.roll_flags("tw", cal2))[0]]


def test_day_ret_and_costs_match_direct_loop():
    rng = np.random.default_rng(1)
    n = 60
    cal = _cal("2021-01-04", n)
    px = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    Cy = {"tot": PS.daily_ret(px) + rng.uniform(0, 0.0003, n), "rate": rng.uniform(0, 0.05, n),
          "days": T.day_gaps(cal)}
    a = np.where(rng.uniform(size=n) > 0.6, S.ADD, 0.0)
    roll = T.roll_flags("tw", cal)
    a0, b = 5, n
    dr = T.day_ret(PS.daily_ret(px), Cy, a, T.costs(a, roll, a0), a0, b)
    nav = 1.0
    for k in range(a0 + 1, b):
        g = px[k] / px[k - 1] - 1 + a[k - 1] * (Cy["tot"][k] - Cy["rate"][k] * Cy["days"][k] / 365)
        c = abs(a[k] - a[k - 1]) * S.COST_FUT + (2 * S.COST_FUT * min(a[k - 1], a[k]) if roll[k] else 0.0)
        nav *= (1 + g) * (1 - c)
    assert math.isclose(float(np.prod(1 + dr)), nav, rel_tol=1e-12)


def test_compare_fixed_uses_average_and_only_roll_costs():
    rng = np.random.default_rng(2)
    n = 300
    cal = _cal("2015-01-01", n)
    px = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n))
    Cy = {"tot": PS.daily_ret(px), "rate": np.full(n, 0.02), "days": T.day_gaps(cal)}
    a = np.where(np.arange(n) % 7 < 2, S.ADD, 0.0)
    roll = T.roll_flags("spx", cal)
    a0 = 10
    c = T.compare(cal, PS.daily_ret(px), Cy, roll, a, a0, n)
    abar = float(np.mean(a[a0:n - 1]))
    assert math.isclose(c["abar"], abar)
    nav = 1.0
    for k in range(a0 + 1, n):
        g = px[k] / px[k - 1] - 1 + abar * (Cy["tot"][k] - 0.02 * Cy["days"][k] / 365)
        nav *= (1 + g) * (1 - (2 * S.COST_FUT * abar if roll[k] else 0.0))
    yrs = (date.fromisoformat(cal[-1]) - date.fromisoformat(cal[a0])).days / 365.25
    assert math.isclose(c["fix"]["cagr"], nav ** (1 / yrs) - 1, rel_tol=1e-9)
    assert math.isclose(c["bh"]["cagr"], (px[-1] / px[a0]) ** (1 / yrs) - 1, rel_tol=1e-9)
    assert math.isclose(c["rule"]["share"], float(np.mean(a[a0:n - 1] > 0)))


def test_verdict_rules():
    def x(rc, fc, rm=0.3, fm=0.3):
        return {"rule": {"cagr": rc, "mdd": rm}, "fix": {"cagr": fc, "mdd": fm}}
    assert T.verdict(x(0.1, 0.09), x(0.1, 0.09), x(0.1, 0.09)) == "better"
    assert T.verdict(x(0.1, 0.09, rm=0.31), x(0.1, 0.09), x(0.1, 0.09)) == "same"     # 回撤比較大
    assert T.verdict(x(0.1, 0.09), x(0.08, 0.09), x(0.1, 0.09)) == "same"
    assert T.verdict(x(0.08, 0.09), x(0.08, 0.09), x(0.08, 0.09)) == "worse"


def test_episodes_measure_nav_minus_index():
    cal = _cal("2020-01-06", 8)
    px = np.array([100, 101, 102, 100, 99, 100, 103, 104.0])
    a = np.array([0, 0.5, 0.5, 0, 0, 0.5, 0.5, 0.5])
    nv = np.array([1, 1.01, 1.03, 1.0, 0.99, 1.0, 1.05, 1.07])
    E = T.episodes(cal, px, a, nv, 0, 8)
    assert E["n"] == 1 and E["list"][0][:2] == [cal[1], cal[3]]
    assert math.isclose(E["list"][0][2], 1.0 / 1.01 - 100 / 101, abs_tol=1e-6)
    assert E["list"][1][4] is True and E["list"][1][:2] == [cal[5], cal[7]]


def test_any_on_uses_selection_of_each_year():
    cal = ["2019-12-30", "2019-12-31", "2020-01-02", "2020-01-03"]
    hp = {"x": np.array([1, 1, 1, 0.0]), "y": np.array([0, 0, 0, 1.0])}
    a = T.any_on(cal, hp, {2019: ["y"], 2020: ["x", "y"]})
    assert list(a) == [0.0, 0.0, S.ADD, S.ADD]
    assert list(T.any_on(cal, hp, {2020: []})) == [0.0] * 4


def test_start_index_takes_latest_date():
    cal = _cal("2000-01-03", 30)
    assert T.start_index(cal, ["2000-01-01", "2000-01-12", None]) is None
    i = T.start_index(cal, ["2000-01-01", "2000-01-08", "2000-01-05"])
    assert cal[i] == "2000-01-10"


def test_page_check_counts_judged_markets_only():
    res = {m: {"rules": {k: {"v": "better"} for k in S.RULES}} for m in S.MARKETS}
    res["ndx"]["rules"]["K1"]["v"] = "worse"
    pc = T.page_check(res)
    assert pc["K1"] == {"n": 3, "better": 2, "worse": 1, "ok": False}
    assert pc["K2"]["ok"] and not pc["K5"]["ok"]         # K5 只描述
