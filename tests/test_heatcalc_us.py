"""景氣溫度・美股版的組資料（arm/lab/heatcalc_us.py；docs/lab_heat_us_plan.md 第 15 節）：用造出來的資料測，不讀真實檔。"""
import math
import random
from datetime import date, timedelta

import pytest

from arm.lab import heatcalc as C
from arm.lab import heatcalc_us as CU
from arm.lab import heatspec as S
from arm.lab import heatspec_us as U


def _bdays(a: date, b: date) -> list[str]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _months(a: str, n: int) -> list[str]:
    out = [a]
    while len(out) < n:
        out.append(C.ym_add(out[-1], 1))
    return out


def _walk(days: list[str], p0: float, seed: int, vol: float = 0.01) -> dict:
    rnd = random.Random(seed)
    out, p = {}, p0
    for d in days:
        p *= math.exp(rnd.gauss(0.0003, vol))
        out[d] = round(p, 4)
    return out


def fake_D() -> dict:
    """1995～2012 的每日資料、1975 起的月資料、1960 起的 Shiller（夠把每一項都算出值）。"""
    days = _bdays(date(1995, 1, 2), date(2012, 12, 31))
    rnd = random.Random(1)
    D = {n: {} for n in CU.FILES}
    D["us_px_spx"] = _walk(days, 500, 1)
    D["us_px_ixic"] = _walk(days, 800, 2, 0.015)
    D["us_px_ndx"] = _walk(days, 400, 3, 0.017)
    D["us_px_sox"] = _walk(days, 200, 4, 0.02)
    for n, s in (("vix", 5), ("us_vxn", 6), ("us_vix3m", 7)):
        D[n] = {d: 15 + 5 * math.sin(i / 50 + s) for i, d in enumerate(days)}
    D["us_dxy"] = _walk(days, 90, 8, 0.004)
    D["us_rsp"], D["us_spy"] = _walk(days, 20, 9), _walk(days, 40, 10)
    D["hyg"], D["ief"] = _walk(days, 50, 11, 0.003), _walk(days, 60, 12, 0.003)
    D["effr"] = {d: 3 + math.sin(i / 300) for i, d in enumerate(days)}
    D["us_h15"] = {d: [2 + math.sin(i / 200), 2.1 + math.sin(i / 200), 3 + math.cos(i / 250), 4 + math.cos(i / 400)]
                   for i, d in enumerate(days)}
    wed = [d for d in days if date.fromisoformat(d).weekday() == 2]
    tue = [d for d in days if date.fromisoformat(d).weekday() == 1]
    D["us_h41"] = {d: [800000 + 500 * i, 50000 + 10 * i, 1000.0] for i, d in enumerate(wed)}
    for n in ("us_cftc_am", "us_cftc_vix", "us_cftc_big", "us_cftc_mini"):
        D[n] = {d: [1000 + rnd.random() * 500, 800 + rnd.random() * 500, 5000.0] for d in tue}
    sat = [d for d in (date(1995, 1, 7) + timedelta(days=7 * k) for k in range(940)) if d <= date(2012, 12, 31)]
    D["us_claims"] = {d.isoformat(): 300000 + 20000 * math.sin(k / 20) for k, d in enumerate(sat)}
    D["us_ads"] = {d: math.sin(i / 100) for i, d in enumerate(days)}
    ms = _months("1975-01", 456)
    for n, f in (("us_philly", lambda j: 10 * math.sin(j / 7)), ("us_cli", lambda j: 100 + math.sin(j / 9)),
                 ("us_umich", lambda j: 90 + 5 * math.sin(j / 11)), ("us_m2", lambda j: 1000 * 1.005 ** j),
                 ("us_wsts", lambda j: 1e6 * 1.01 ** j * (1 + 0.1 * math.sin(j / 5))), ("mmf", lambda j: 3e12 + 1e10 * j)):
        D[n] = {ym: f(j) for j, ym in enumerate(ms)}
    D["us_ebp"] = {ym: [1.0, 0.2 * math.sin(j / 13)] for j, ym in enumerate(ms)}
    D["us_bls"] = {ym: [5 + math.sin(j / 30), 100 * 1.003 ** j, 100 * 1.0025 ** j] for j, ym in enumerate(ms)}
    qe = [ym for ym in ms if ym[5:7] in ("03", "06", "09", "12")]
    D["us_z1"] = {ym: [1e6 * 1.02 ** j, 9e5 * 1.012 ** j, 1e4 * 1.03 ** j] for j, ym in enumerate(qe)}
    D["us_gdp"] = {ym: 5e6 * 1.015 ** j for j, ym in enumerate(qe)}
    sm = _months("1960-01", 636)
    D["us_shiller"] = {ym: [50 * 1.006 ** j, 2 * 1.004 ** j, 4 * 1.005 ** j, 30 * 1.003 ** j, 5 + math.sin(j / 40)]
                       for j, ym in enumerate(sm)}
    D["tsmc"] = {ym: [1e8 * 1.01 ** j, 1e8 * 1.01 ** (j - 12)] for j, ym in enumerate(_months("2004-01", 108))}
    return D


@pytest.fixture(scope="module")
def built():
    D = fake_D()
    SH = CU.shared(D)
    return D, SH, {k: CU.build(k, D, SH) for k in U.INDEX_ORDER}


def test_build_all_indices_and_spec_restored(built):
    D, SH, BS = built
    assert S.MARKET == "tw" and S.VER == 10                                    # 算完換回台股規格
    for idx, B in BS.items():
        keys = U.keys_for(idx)
        assert B["idx"] == idx and set(B["comp"]) == set(U.DIMS)
        assert set(B["hc"]) >= set(keys)
        assert B["cal"][0] == "1995-01-02" and len(B["px"]) == len(B["cal"])
        for dim in U.DIMS:                                                    # 造的資料只有 18 年：泡沫面向的
            if dim != "bubl":                                                 # 20 年趨勢項目與 LPPLS 算不出來
                assert any(v is not None for v in B["comp"][dim]), (idx, dim)
        for k in ("X1", "X2", "X3", "X6", "X7"):
            assert any(v is not None for v in B["hc"][k]), (idx, k)
    assert "T14" in BS["ixic"]["hc"] and "T14" not in BS["spx"]["hc"]
    assert "X10" in BS["spx"]["hc"] and "X10" not in BS["sox"]["hc"]
    assert "F11" in BS["sox"]["hc"] and "F11" not in BS["ndx"]["hc"]
    assert BS["spx"]["hc"]["T9"] != BS["ixic"]["hc"]["T9"]                    # 那斯達克用 VXN


def test_research_wiring_under_us_spec(built, monkeypatch):
    """研究流程接線：統計本身（等級相關、單項分析、多層回歸）在台股頁的測試已逐項比對，這裡換成記錄呼叫的假函式，
    確認是在美股規格下呼叫、S&P 500 有從 1950 起切樣本、算完換回台股規格。"""
    from arm.lab import heatrel, heatreg
    D, SH, BS = built
    seen = {}

    def ev(x, px, cal, dim):
        seen.setdefault("ev", set()).add((S.MARKET, dim))
        return {"n": len(cal)}
    monkeypatch.setattr(C, "evaluate", ev)
    monkeypatch.setattr(heatrel, "run", lambda V: seen.update(rel=(S.MARKET, V["cal"][0])) or {"wk": [], "rel": {}})
    monkeypatch.setattr(heatrel, "deriv_all", lambda V: {"m": S.MARKET})
    monkeypatch.setattr(heatreg, "run", lambda V, A=None: {"hike": S.M6_HIKE, "ext": A, "items": sorted(S.DERIV)})
    monkeypatch.setattr(CU.TT, "all_events", lambda px: {k: [] for k in S.EVENTS})
    monkeypatch.setattr(CU.TT, "event_study", lambda px, cal, idx, h, start=0, f=None: {"n": 0})
    R = CU.research("ndx", BS["ndx"])
    assert R["ver"] == U.VER and R["idx"] == "ndx" and set(R["dims"]) == set(U.DIMS)
    bubl = {k for k, d, *_ in U.IND if d == "bubl" and k in U.keys_for("ndx")}
    assert set(R["bub"]) == bubl | {"comp"}
    assert R["m6"] == {"hike": "R1", "ext": None, "items": sorted(U.DERIV)}
    assert seen["ev"] == {("us", d) for d in U.DIMS} and seen["rel"][0] == "us"
    assert S.MARKET == "tw" and S.M6_HIKE == "G1"
    monkeypatch.setattr(CU, "trim", lambda B, start: seen.update(start=start) or B)
    CU.research("spx", BS["spx"])
    assert seen["start"] == "1950-01-01"


def test_trim_validation_start(built):
    D, SH, BS = built
    B = BS["spx"]
    V = CU.trim(B, "2000-01-01")
    i0 = B["cal"].index(V["cal"][0])
    assert V["cal"][0] >= "2000-01-01" and B["cal"][i0 - 1] < "2000-01-01"
    assert V["hc"]["T1"] == B["hc"]["T1"][i0:] and V["comp"]["tech"] == B["comp"]["tech"][i0:]
    assert V["nat"] is B["nat"] and CU.trim(B, None) is B


def test_s2_combines_emini_at_one_fifth():
    D = {n: {} for n in CU.FILES}
    D["us_cftc_big"] = {"2010-01-05": [600.0, 400.0, 1000.0]}
    D["us_cftc_mini"] = {"2010-01-05": [3000.0, 1000.0, 10000.0], "2022-01-04": [3000.0, 2000.0, 8000.0]}
    D["tsmc"] = {}
    N = CU.shared(D)["N"]
    big_net, mini_net = 200.0, 2000.0 / 5
    assert N["S2"]["2010-01-09"] == pytest.approx(100 * (big_net + mini_net) / (1000 + 10000 / 5))   # 週二＋4 天
    assert N["S2"]["2022-01-08"] == pytest.approx(100 * 1000 / 8000)                                 # 大型契約下市後


def test_f4_complete_months_and_f5_sahm():
    D = {n: {} for n in CU.FILES}
    D["tsmc"] = {}
    sats = [date(1987, 1, 3) + timedelta(days=7 * k) for k in range(120)]
    D["us_claims"] = {d.isoformat(): 1000.0 * (1.1 if d.year == 1988 else 1.0) for d in sats if d.isoformat() != "1988-03-12"}
    ur = [4.0] * 14 + [4.3, 4.6, 4.9]
    D["us_bls"] = {ym: [u, None, None] for ym, u in zip(_months("1990-01", len(ur)), ur)}
    M = CU.shared(D)["M"]
    assert M["F4"]["1988-01"] == pytest.approx(10.0) and "1988-03" not in M["F4"]   # 那個月少一週
    assert CU.sat_count("1988-03") == 4 and CU.sat_count("1988-04") == 5
    # 1991-05：3 個月平均 (4.3＋4.6＋4.9)/3＝4.6；之前 12 個月 3 個月平均最低＝4.0；1991-03：(4.0＋4.0＋4.3)/3 − 4.0＝0.1
    # （3 個月平均從 1990-03 起，再要之前 12 個月＝1991-03 起才有值）
    assert M["F5"]["1991-05"] == pytest.approx(0.6) and M["F5"]["1991-03"] == pytest.approx(0.1)
    assert min(M["F5"]) == "1991-03"


def test_cape_ecy_and_z1_extrapolation():
    L = {"p": {}, "cpi": {}, "e": {}, "d": {}, "y10": {}, "spx_me": {}}
    for ym in _months("1990-01", 200):
        L["p"][ym], L["cpi"][ym], L["e"][ym], L["y10"][ym] = 200.0, 100.0, 10.0, 5.0
    cp = CU.cape(L)
    first = C.ym_add("1990-01", S.PSY["div_lag"] + 119)
    assert min(cp) == first and cp[first] == pytest.approx(20.0)              # 實質價格 2 ÷ 平均實質盈餘 0.1
    ec = CU.ecy(L, cp)
    assert min(ec) == first and all(v == pytest.approx(0.0) for v in ec.values())   # 通膨 0、殖利率 5、1/CAPE＝5%
    D = {"us_z1": {"2000-03": [100.0, 50.0, 1.0]}, "us_gdp": {"2000-03": 400.0}}
    L2 = {"spx_me": {"2000-03": 1000.0, "2000-05": 1050.0, "2000-06": 1100.0, "2000-07": 1210.0}}
    bf, tq = CU.z1_ratios(D, L2)
    assert "2000-05" not in bf                                                 # Z.1 第一季 6/15 才拿得到（5 月的值 6/1 用）
    assert bf["2000-06"] == pytest.approx(100 * 1.1 / 400) and tq["2000-06"] == pytest.approx(100 * 1.1 / 50)
    assert bf["2000-07"] == pytest.approx(100 * 1.21 / 400)

def test_r4_uses_bill_before_1981_09():
    D = {n: {} for n in CU.FILES}
    D["tsmc"] = {}
    D["us_h15"] = {"1981-08-31": [15.0, None, None, 14.0], "1981-09-01": [15.0, 16.0, None, 14.5]}
    N = CU.shared(D)["N"]
    assert N["R4"] == {"1981-08-31": pytest.approx(-1.0), "1981-09-01": pytest.approx(-1.5)}
