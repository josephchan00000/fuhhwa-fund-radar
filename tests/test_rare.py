"""少見但勝率高的策略（arm/lab/rare.py）：每一條規則和逐筆直接算的版本比對、篩選與去重、成績、判定。"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from arm.lab import rare as R
from arm.lab import rarespec as S
from arm.lab import xstrat as XT

LNY = {1990: "1990-01-27", 1991: "1991-02-15", 1992: "1992-02-04", 1993: "1993-01-23", 1994: "1994-02-10",
       1995: "1995-01-31", 1996: "1996-02-19", 1997: "1997-02-07", 1998: "1998-01-28", 1999: "1999-02-16",
       2000: "2000-02-05", 2001: "2001-01-24", 2002: "2002-02-12", 2003: "2003-02-01", 2004: "2004-01-22",
       2005: "2005-02-09", 2006: "2006-01-29", 2007: "2007-02-18", 2008: "2008-02-07", 2009: "2009-01-26",
       2010: "2010-02-14", 2011: "2011-02-03", 2012: "2012-01-23", 2013: "2013-02-10", 2014: "2014-01-31",
       2015: "2015-02-19", 2016: "2016-02-08", 2017: "2017-01-28", 2018: "2018-02-16", 2019: "2019-02-05",
       2020: "2020-01-25", 2021: "2021-02-12", 2022: "2022-02-01", 2023: "2023-01-22", 2024: "2024-02-10",
       2025: "2025-01-29", 2026: "2026-02-17"}


@pytest.fixture(scope="module")
def tw():
    return R.data("tw")


@pytest.fixture(scope="module")
def spx():
    return R.data("spx")


def test_election_days():
    e = R.election_days(1950, 2026)
    assert e[0] == "1950-11-07" and e[-1] == "2026-11-03" and len(e) == 20
    assert {"1962-11-06", "1986-11-04", "2018-11-06", "2022-11-08"} <= set(e)


def test_lny_closures_match_lunar_new_year(tw):
    cal = tw["cal"]
    lc = R.lny_close(cal)
    assert sorted(lc) == list(range(1990, 2027))
    for y, C in lc.items():
        assert cal[C] < LNY[y] < cal[C + 1], y                         # 休市期間包含農曆年初一
        assert R.days_between(cal[C], cal[C + 1]) >= R.LNY_MIN_GAP
    assert cal[lc[2026]] == "2026-02-11" and cal[lc[2026] + 1] == "2026-02-23"
    assert cal[lc[2025]] == "2025-01-22"
    # 資料剛好停在封關日：那一年看不到休市，先不算（不會挑到普通週末）
    cut = cal[:lc[2026] + 1]
    assert 2026 not in R.lny_close(cut)


def test_santa_window_real_calendar(spx):
    cal = spx["cal"]
    tr = R.tr_santa(cal, {"before": 5, "after": 2})
    got = {cal[b][:4]: (cal[b], cal[q]) for _, b, q in tr}
    assert got["2024"] == ("2024-12-23", "2025-01-03")
    assert got["2019"] == ("2019-12-23", "2020-01-03")
    for _, b, q in tr:                                                  # 7 個交易日：12 月最後 5 天＋1 月前 2 天
        assert q - b == 7 and cal[b][5:7] == "12" and cal[q][5:7] == "01"


def _naive_ath(px, gap):
    highs, out = [0], []                                                  # 資料第一天算第一個高點
    for t in range(1, len(px)):
        if px[t] > px[:t].max():
            if t - highs[-1] >= gap:
                out.append(t)
            highs.append(t)
    return out


def _naive_bull(px, th):
    out, bear, mx, lo = [], False, px[0], None
    for t in range(1, len(px)):
        if bear:
            lo = min(lo, px[t])
            if px[t] >= (1 + th) * lo:
                out.append(t)
                bear, mx = False, px[t]
            continue
        mx = max(mx, px[t])
        if px[t] <= (1 - th) * mx:
            bear, lo = True, px[t]
    return out


def test_ath_bull_vix_match_naive():
    rng = np.random.default_rng(7)
    for _ in range(6):
        px = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 600)))
        for gap in (5, 30, 80):
            assert R.ath_days(px, gap) == _naive_ath(px, gap)
        for th in (0.1, 0.2):
            assert R.bull_scan(px, th)[0] == _naive_bull(px, th)
        r = rng.uniform(0.8, 1.2, 600)
        r[rng.integers(0, 600, 30)] = np.nan
        naive = [t for t in range(10, 600) if np.isfinite(r[t]) and r[t] >= 1.0
                 and np.isfinite(r[t - 10:t]).all() and (r[t - 10:t] < 1.0).all()]
        assert R.vixinv_days(r, 1.0, 10) == naive


def test_jan_rule_synthetic():
    cal = ["2020-12-30", "2020-12-31", "2021-01-04", "2021-01-29", "2021-02-01", "2021-12-30", "2021-12-31",
           "2022-01-03", "2022-01-31", "2022-02-01", "2022-12-30", "2023-01-03"]
    px = np.array([100, 100, 101, 102, 103, 110, 111, 112, 99, 98, 90, 91.0])
    tr = R.tr_jan(cal, px, {"th": 0.0})
    assert tr == [(3, 4, 6)]                                            # 2021 一月漲（102 ＞ 100）：1/29 訊號、2/1 買、12/31 賣；2022 一月跌
    assert R.tr_jan(cal, px, {"th": 0.03}) == []
    # 12 月還沒走完：持有中（賣出日在資料之後）
    tr2 = R.tr_jan(cal[:6], px[:6], {"th": 0.0})
    assert tr2[0][:2] == (3, 4) and tr2[0][2] >= 6


def test_nsf_buy_days(tw):
    cal = tw["cal"]
    for d, _ in S.NSF:
        assert d in cal                                                 # 起始日都是交易日
    tr = R.raw_trades(tw, "nsf", {"H": 250})
    assert [cal[b] for _, b, _ in tr] == ["2000-03-17", "2000-10-04", "2004-05-21", "2008-09-22", "2011-12-22",
                                         "2015-08-26", "2020-03-23", "2022-07-14", "2025-04-10"]
    done, _ = R.select(tr, 0, None, 250, len(cal))
    assert "2000-10-04" not in [cal[b] for _, b, _ in done]              # 抱一年期間內的第二次不算新的一次
    done60, _ = R.select(tr, 0, None, 60, len(cal))
    assert "2000-10-04" in [cal[b] for _, b, _ in done60]


def test_select_filters_and_dedupes():
    tr = [(5, 6, 16), (8, 9, 19), (20, 21, 31), (40, 41, 51), (90, 91, 101)]
    done, op = R.select(tr, 6, None, 10, 95)
    assert done == [(5, 6, 16), (20, 21, 31), (40, 41, 51)] and op == [(90, 91, 101)]
    done, op = R.select(tr, 7, 30, None, 95)
    assert done == [(8, 9, 19), (20, 21, 31)] and op == []


def test_stats_and_base_match_direct():
    rng = np.random.default_rng(3)
    px = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 400)))
    tr = [(10, 11, 31), (60, 61, 81), (120, 121, 171), (200, 201, 221), (300, 301, 351)]
    c = 0.001
    s = R.stats(px, tr, 5, None, c)
    r = np.array([px[q] / px[b] * (1 - c) / (1 + c) - 1 for _, b, q in tr])
    assert s["n"] == 5 and s["win"] == pytest.approx((r > 0).mean()) and s["med"] == pytest.approx(np.median(r))
    srt = np.sort(r)
    assert s["trim"] == pytest.approx(srt[1:-1].mean())                 # 不到 20 次：去掉最好和最差各一次
    want = []
    for _, b, q in tr:
        h = q - b
        rr = [px[i + h] / px[i] * (1 - c) / (1 + c) - 1 for i in range(5, len(px) - h)]
        want.append(np.mean(np.array(rr) > 0))
    assert s["base"] == pytest.approx(np.mean(want))
    assert s["mae"] == pytest.approx(np.median([max(0, 1 - px[b + 1:q + 1].min() / px[b]) for _, b, q in tr]))
    # 區間版：買進日只到 hi
    s2 = R.stats(px, tr, 5, 150, c)
    want2 = [np.mean(np.array([px[i + (q - b)] / px[i] * (1 - c) / (1 + c) - 1 for i in range(5, min(150, len(px) - (q - b) - 1) + 1)]) > 0)
             for _, b, q in tr]
    assert s2["base"] == pytest.approx(np.mean(want2))


def test_ok_and_tier_match_macro_dip():
    base = {"n": 10, "win": 0.7, "base": 0.6, "med": 0.01, "trim": 0.01}
    assert R.ok(base)
    for k, v in (("win", 0.59), ("win", 0.55), ("med", 0.0), ("trim", -0.001)):
        assert not R.ok({**base, k: v})
    assert not R.ok({**base, "base": 0.71})
    for full_ok, rec, share, n in itertools.product((True, False), (True, False, None), (0.0, 0.5, 2 / 3, 1.0), (4, 5, 30)):
        mine = R.tier({"n": n, "ok": full_ok}, rec, share)
        assert mine == XT.tier("dip", full_ok, rec, share, n < S.N_MIN)


def test_binom_and_luck():
    assert R.binom_p(5, 5, 0.5) == pytest.approx(1 / 32)
    assert R.binom_p(10, 0, 0.3) == pytest.approx(1.0)
    assert R.binom_p(3, 2, 0.5) == pytest.approx(0.5)
    rng = np.random.default_rng(1)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 500)))
    tr = [(50, 51, 61), (150, 151, 161), (300, 301, 311)]
    a = R.luck(px, tr, 10, 0.001, "rare:x:y")
    assert 0 < a <= 1 and a == R.luck(px, tr, 10, 0.001, "rare:x:y")


def test_midterm_trades_on_spx(spx):
    M = R.Mkt("spx", spx)
    done, op = M.trades(S.BY_KEY["mid"], {"H": 250})
    cal = spx["cal"]
    # 1968 年以前 NYSE 選舉日休市：買在選舉日前最後一個交易日
    assert [cal[b] for _, b, _ in done][:3] == ["1950-11-06", "1954-11-01", "1958-11-03"]
    assert [cal[b] for _, b, _ in done][-3:] == ["2014-11-04", "2018-11-06", "2022-11-08"]
    assert len(done) == 19 and all(q - b == 250 for _, b, q in done)
    early, _ = M.trades(S.BY_KEY["mid"], {"H": 250}, lo=R.idx_ge(cal, "1928-01-01"), hi=R.idx_le(cal, "1949-12-31"))
    assert [cal[b][:4] for _, b, _ in early] == ["1930", "1934", "1938", "1942", "1946"]
    assert all(cal[b] <= e for (_, b, _), e in zip(done, R.election_days(1950, 2022)))


def test_now_schedules(spx, tw):
    m = R.evaluate(R.Mkt("spx", spx), S.BY_KEY["mid"])
    assert m["now"]["bd"] == "2026-11-03" and m["now"]["st"] in ("wait", "hold")
    s = R.evaluate(R.Mkt("spx", spx), S.BY_KEY["santa"])
    assert s["now"]["bd"][:7] == "2026-12" and s["now"]["qd"][:7] == "2027-01"
    lp = R.evaluate(R.Mkt("tw", tw), S.BY_KEY["lnypre"])
    assert lp["now"]["close"][:4] == "2027" and lp["now"]["approx"] is True
    assert lp["now"]["close"] < LNY_2027 < lp["now"]["reopen"]


LNY_2027 = "2027-02-06"
