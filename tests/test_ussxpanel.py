"""美股飆股研究的面板與存活偏誤量法（arm/lab/ussxpanel.py、ussxsurv.py；ussxspec VER 1）。不連網、不用真的資料。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from arm.lab import ussxdata as UD
from arm.lab import ussxpanel as UP
from arm.lab import ussxspec as X
from arm.lab import ussxsurv as SV


def _days(n: int, start: str = "2020-01-02") -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_split_mult_applies_to_days_before_the_split():
    ds = _days(5)
    assert list(UP.split_mult(ds, [[ds[2], 2.0]])) == [2.0, 2.0, 1.0, 1.0, 1.0]
    assert list(UP.split_mult(ds, [[ds[1], 0.1], [ds[3], 3.0]])) == pytest.approx([0.3, 3.0, 3.0, 1.0, 1.0])
    assert list(UP.split_mult(ds, [])) == [1.0] * 5


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    monkeypatch.setenv("USSX_DIR", str(tmp_path))
    ds = _days(30)
    def put(sym, closes, vols, divs=(), spl=(), days=None):
        d = days or ds
        s = {"d": d, "c": closes, "o": [x * 0.99 for x in closes], "h": [x * 1.02 for x in closes],
             "l": [x * 0.97 for x in closes], "v": vols, "div": [list(x) for x in divs], "spl": [list(x) for x in spl]}
        UD._write(UD.px_path(sym), UD.enc_px(s, "2026-10-23"))
    put("SPY", [100.0 + k for k in range(30)], [1e6] * 30)
    put("AAA", [10.0] * 10 + [5.0] * 20, [1000.0] * 30, divs=[(ds[5], 0.5)], spl=[(ds[10], 2.0)])
    put("BBB", [50.0] * 12, [200.0] * 12, days=ds[:12])       # 第 12 天以後沒有資料
    UD.save_meta({"px_done": {"SPY": 30, "AAA": 30, "BBB": 12}, "fail": {}, "screen": "2026-10-23"})
    return ds


def test_load_builds_total_return_raw_price_and_dollar_volume(fake):
    ds = fake
    P = UP.load(etfs=("SPY",))
    assert P["cal"] == ds and P["sym"] == ["AAA", "BBB", "SPY"] and list(P["etf"]) == [False, False, True]
    j = P["col"]["AAA"]
    c = P["C"][:, j]
    # 第 5 天除息 0.5（前一天收盤 10）→ 第 5 天以前的含息價乘 0.95，當天與之後不變
    assert c[4] == pytest.approx(10.0 * 0.95, rel=2e-4) and c[5] == pytest.approx(10.0, rel=2e-4)
    # 第 10 天 2:1 分割：分割還原價 10→5 不變，實際成交價分割前是 20
    assert P["RAW"][9, j] == pytest.approx(20.0, rel=2e-4) and P["RAW"][10, j] == pytest.approx(5.0, rel=2e-4)
    assert P["DV"][0, j] == pytest.approx(10.0 * 1000.0, rel=0.01)               # 分割還原收盤 × 分割還原量
    b = P["col"]["BBB"]
    assert P["first"][b] == 0 and P["last"][b] == 11 and np.isnan(P["C"][12, b]) and P["DV"][12, b] == 0.0
    assert P["H"][3, j] / P["C"][3, j] == pytest.approx(1.02, rel=3e-4)


def test_dv20_age_and_eligible(fake, monkeypatch):
    P = UP.load(etfs=("SPY",))
    D20 = UP.dv20(P, n=5)
    j = P["col"]["AAA"]
    assert np.isnan(D20[3, j]) and D20[4, j] == pytest.approx(np.mean(P["DV"][0:5, j]))
    b = P["col"]["BBB"]
    assert D20[14, b] == pytest.approx(np.sum(P["DV"][10:15, b]) / 5)          # 沒成交的日子算 0
    A = UP.age(P)
    assert A[0, j] == 0 and A[29, j] == 29
    monkeypatch.setattr(X, "AGE_MIN", 3)
    monkeypatch.setattr(X, "PX_MIN", 4.0)
    monkeypatch.setattr(X, "EPS_RECENT", 4)
    rep = {"AAA": [2, 20], "BBB": [], "SPY": [0]}
    el = UP.eligible(P, liq=1000.0, rep=rep, D20=D20, A=A)
    assert not el[:, P["col"]["SPY"]].any()                                     # ETF 不算
    assert not el[:, b].any()                                                   # 沒有財報
    assert not el[3, j]                                                          # 有股價還不到 3 天以後…第 3 天剛滿但成交值 nan
    assert el[4, j] and el[6, j] and not el[7, j]                                # 財報在第 2 天，4 天以後就太舊
    assert not el[19, j] and el[20, j] and el[24, j] and not el[25, j]


def test_report_days_and_last_report():
    cal = _days(10)
    earn = {"AAA": [[cal[2], 1.0], [cal[2], 1.0], ["2019-12-28", 0.5], [cal[9], 2.0]]}
    rep = UP.report_days(cal, ["AAA", "ZZZ"], earn)
    assert rep == {"AAA": [0, 3], "ZZZ": []}                                     # 公布日的下一個交易日；最後一天公布＝資料裡還拿不到
    assert list(UP.last_report(6, rep["AAA"])) == [0, 0, 0, 3, 3, 3]


# ── 存活偏誤 ─────────────────────────────────────────────────────────────────

def _panel():
    cal = _days(70, "2008-12-01")
    T, N = len(cal), 4
    rng = np.random.default_rng(1)
    C = np.cumprod(1 + rng.normal(0, 0.01, (T, N)), axis=0) * 20
    C[40:, 3] = np.nan                                                          # 第 4 檔第 40 天以後下市
    D20 = np.tile(np.array([4e7, 3e7, 2e7, 1e7]), (T, 1))
    P = {"cal": cal, "sym": ["A", "B", "C", "E"], "col": {"A": 0, "B": 1, "C": 2, "E": 3}, "etf": np.array([False] * 3 + [True]),
         "C": C, "RAW": np.full((T, N), 20.0, dtype=np.float32)}
    return P, D20, np.full((T, N), 100)


def test_periods_and_group_returns_match_brute_force():
    P, D20, A = _panel()
    cal = P["cal"]
    pers = SV.periods(cal, "2009-01-01")
    assert cal[pers[0][0]] == "2008-12-31" and pers[-1][1] == len(cal) - 1
    P["etf"] = np.array([False] * 4)
    gr = SV.group_returns(P, pers, {"top": (1, 2), "low": (3, 4)}, D20, A)
    C = P["C"]
    for k, (a, b) in enumerate(pers):
        top = np.mean([C[b, 0] / C[a, 0] - 1, C[b, 1] / C[a, 1] - 1])
        assert gr["ret"]["top"][k] == pytest.approx(top)
        if np.isfinite(C[a, 3]):
            last = max(i for i in range(a, b + 1) if np.isfinite(C[i, 3]))     # 下市：用最後一天收盤
            low = np.mean([C[b, 2] / C[a, 2] - 1, C[last, 3] / C[a, 3] - 1])
            assert gr["n"]["low"][k] == 2
        else:
            low = C[b, 2] / C[a, 2] - 1
            assert gr["n"]["low"][k] == 1
        assert gr["ret"]["low"][k] == pytest.approx(low)


def test_etf_returns_add_back_fee_and_cagr():
    P, D20, A = _panel()
    cal = P["cal"]
    pers = SV.periods(cal, "2009-01-01")
    er = SV.etf_returns(P, pers, "A", 0.0365)
    C = P["C"]
    a, b = pers[0]
    days = (date.fromisoformat(cal[b]) - date.fromisoformat(cal[a])).days
    assert er[0] == pytest.approx(C[b, 0] / C[a, 0] - 1 + 0.0365 * days / 365.25)
    v = np.prod([1 + r for r in er])
    yrs = (date.fromisoformat(cal[pers[-1][1]]) - date.fromisoformat(cal[pers[0][0]])).days / 365.25
    assert SV.cagr(er, cal, pers) == pytest.approx(v ** (1 / yrs) - 1)
    assert SV.cagr([0.1, float("nan")], cal, pers[:2]) is None


def test_stop_rule_uses_pit_and_small_groups():
    assert X.SURV["stop"] == ("PIT", "S", "R") and X.PASS["surv_max"] == 2.0


# ── 換一個指數 ────────────────────────────────────────────────────────────────

def test_swap_judge_and_etf_daily():
    from arm.lab import ussxswap as SW
    cur = {"plan": {"m": 10.0, "mdd": 0.40}, "halves": [{"plan": {"m": 2.0}}, {"plan": {"m": 5.0}}]}
    ok = {"plan": {"m": 11.0, "mdd": 0.49}, "halves": [{"plan": {"m": 2.0}}, {"plan": {"m": 5.5}}]}
    assert SW.judge(ok, cur) == {"money": True, "halves": True, "mdd": True, "pass": True}
    deep = {"plan": {"m": 11.0, "mdd": 0.51}, "halves": [{"plan": {"m": 2.1}}, {"plan": {"m": 5.5}}]}
    assert SW.judge(deep, cur)["mdd"] is False and SW.judge(deep, cur)["pass"] is False
    half = {"plan": {"m": 11.0, "mdd": 0.40}, "halves": [{"plan": {"m": 1.9}}, {"plan": {"m": 6.0}}]}
    assert SW.judge(half, cur)["halves"] is False
    P = {"cal": ["2020-01-02", "2020-01-03", "2020-01-07"], "col": {"QQQ": 0},
         "C": np.array([[100.0], [101.0], [99.99]])}
    r = SW.etf_daily(P, "QQQ", ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"])
    assert r[0] == 0.0 and r[1] == 0.0 and r[2] == pytest.approx(0.01) and r[3] == 0.0 and r[4] == pytest.approx(-0.01)
