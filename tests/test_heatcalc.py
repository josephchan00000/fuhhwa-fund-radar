"""景氣溫度頁：各項的組法（arm/lab/heatcalc.py；規格 heatspec VER 3，實作細節見規劃文件第 12.7 節）。"""
import random
from datetime import date, timedelta

from arm.lab import heat as H
from arm.lab import heatcalc as C
from arm.lab import heatspec as S


def _days(n, start=date(2006, 1, 2)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_calendar_official_first_yahoo_for_missing_months():
    D = {"turnover": {"2020-01-02": [1e11, 12100.0], "2020-01-03": [1e11, 12000.0]},
         "taiex": {"2019-12-31": 11997.0, "2020-01-02": 12100.5, "2020-01-03": 12000.0, "2020-01-06": 11900.0}}
    cal, px, info = C.calendar(D)
    assert cal == ["2019-12-31", "2020-01-02", "2020-01-03"]      # 官方有的月份只用官方日子
    assert px == [11997.0, 12100.0, 12000.0]
    assert info["official"] == 2 and info["yahoo_vs_official_max_pct"] == round(100 * (12100.5 / 12100 - 1), 3)


def test_ratio_sum_uses_days_present_in_both():
    cal = [f"d{i}" for i in range(6)]
    a = {f"d{i}": 1.0 for i in range(6)}
    b = {f"d{i}": 10.0 for i in range(6) if i != 3}
    out = C.ratio_sum(cal, a, b, 5)
    assert out[:4] == [None] * 4
    assert out[4] is None                     # 5 天缺 1 天 → 不到 5 天（k＝5 要滿 5 天）
    big = C.ratio_sum([f"e{i}" for i in range(60)], {f"e{i}": 2.0 for i in range(60)},
                      {f"e{i}": 4.0 for i in range(60) if i not in (7, 9)}, 60)
    assert big[-1] == 50.0                    # 60 天缺 2 天仍算（至少 58 天）


def test_helpers_month_avg_yoy_yoy3_ma_ratio():
    ser = {f"2020-01-{d:02d}": 1.0 for d in range(1, 11)} | {f"2020-02-{d:02d}": 2.0 for d in range(1, 6)}
    assert C.month_avg(ser) == {"2020-01": 1.0}                    # 2 月只有 5 天
    assert C.ym_add("2020-01", -1) == "2019-12" and C.ym_add("2019-12", 13) == "2021-01"
    assert C.yoy({"2020-03": 110.0, "2019-03": 100.0}, "2020-03") == 10.000000000000009
    m = {C.ym_add("2000-01", i): 100.0 + i for i in range(16)}
    y3 = C.yoy3(m)
    assert set(y3) == {"2001-03", "2001-04"}                     # 6 個月都要有值
    assert abs(y3["2001-03"] - 100 * ((114 + 113 + 112) / (102 + 101 + 100) - 1)) < 1e-9
    r = C.ma_ratio([1.0] * 4 + [2.0], 2, 4)
    assert r[:3] == [None] * 3 and r[3] == 0.0 and abs(r[4] - 100 * (1.5 / 1.25 - 1)) < 1e-9


def test_futures_options_items():
    futi = {"2026-10-16": {"TX": {"外資": [9812, 103487], "投信": [1, 2], "自營商": [3, 4]},
                           "MTX": {"外資": [4000, 8000], "投信": [100, 0], "自營商": [500, 600]},
                           "TMF": {"外資": [200, 0]}},
            "2018-06-05": {"TX": {"外資": [1000, 0]}}}                   # 小台缺：不算
    assert C.f1_foreign_fut(futi) == {"2026-10-16": (9812 - 103487) + (4000 - 8000) / 4 + 200 / 20}
    assert C.f2_retail_mtx(futi, {"2026-10-16": 50000}) == {"2026-10-16": 100.0 * ((8000 + 0 + 600) - (4000 + 100 + 500)) / 50000}
    opti = {"2026-10-16": {"買權": {"外資": [838170, 709347]}, "賣權": {"外資": [500000, 600000]}}}
    assert C.f3_foreign_opt(opti) == {"2026-10-16": ((838170 - 709347) - (500000 - 600000)) / 1e5}


def test_rev_sums_use_reported_yoy_and_skip_financials():
    shards = [("2013-01", {"s": {"1101": [9134465.0, 28.2, 28.2],      # 2013 合併營收：去年同期用公布的年增率換算
                                 "2330": [100.0, 0.0, 0.0],
                                 "2881": [500.0, 50.0, 50.0],          # 金融保險不算
                                 "9999": [10.0, None, None],           # 沒有年增率（新上市）不算
                                 "8888": [10.0, -100.0, -100.0],       # −100% 不算
                                 "7777": [0.0, 5.0, 5.0]}})]          # 營收 0 不算
    out = C.rev_sums(shards, {"2881"})
    a, b, n = out["2013-01"]
    assert n == 2 and a == 9134465.0 + 100.0
    assert abs(b - (9134465.0 / 1.282 + 100.0)) < 1e-6


def test_native_daily_chip_liq_tech_items():
    cal = _days(300)
    px = [100.0 + i for i in range(300)]
    D = {"margin": {d: [1e10 * (1 + i / 100), 1000 + i, 50] for i, d in enumerate(cal)},
         "turnover": {d: [1e11 * (2 if i >= 280 else 1), px[i]] for i, d in enumerate(cal)},
         "ust": {d: [1.0, 2.0, 3.0 + i / 100] for i, d in enumerate(cal)}}
    N = C.native_daily(D, cal, px)
    d = cal[-1]
    assert N["C1"][d] == 1e10 * (1 + 299 / 100) / 1e8                  # 億元
    assert abs(N["C2"][d] - 100 * ((1 + 299 / 100) / (1 + 279 / 100) - 1)) < 1e-9
    assert abs(N["C3"][d] - 100 * 50 / 1299) < 1e-9                     # 融券 ÷ 融資張數
    assert abs(N["L5"][d] - 100 * (2.0 / ((230 * 1 + 20 * 2) / 250) - 1)) < 1e-9
    assert abs(N["L7"][d] - 0.6) < 1e-9                                 # 60 個交易日前的差（百分點）
    assert abs(N["T2"][d] - 100 * (px[-1] / (sum(px[-60:]) / 60) - 1)) < 1e-9
    assert cal[238] not in N["T3"] and cal[239] in N["T3"]                 # 240 日平均要滿 240 天
    assert N["T4"][d] == 100.0                                         # 一路上漲
    assert set(C.BREADTH) <= set(N) and N["T10"] == {}


def test_monthly_items_and_release_alignment():
    ndc = {C.ym_add("2000-01", i): [None, 100.0 + i, None, None, None, None, 20.0 + (i % 20), "綠"] for i in range(200)}
    rev = {C.ym_add("2013-01", i): [110.0, 100.0, 5] for i in range(5)}
    M = C.raw_monthly({"ndc": ndc, "orders": {C.ym_add("2000-01", i): 100.0 + i for i in range(30)},
                       "exports": {C.ym_add("1982-01", i): 50.0 + i for i in range(20)}, "rev": rev,
                       "money": {"2001-01": [10.0, 6.5, 30.0, 4.0]}, "twcpi": {}, "effr": {}, "uscpi": {}, "pmi": {}})
    assert M["B2"]["2000-07"] == 6.0 and "2000-06" not in M["B2"]          # 和 6 個月前的差
    s_now = 100 + 14 + 100 + 13 + 100 + 12                                 # 2001-03＋02＋01
    s_ago = 100 + 2 + 100 + 1 + 100 + 0
    assert abs(M["B4"]["2001-03"] - 100 * (s_now / s_ago - 1)) < 1e-9
    assert abs(M["B5"]["1983-03"] - 100 * ((64 + 63 + 62) / (52 + 51 + 50) - 1)) < 1e-9
    assert set(M["B6"]) == {"2013-03", "2013-04", "2013-05"} and abs(M["B6"]["2013-03"] - 10.0) < 1e-9
    assert M["L1"] == {"2001-01": 2.5} and M["L2"] == {"2001-01": 6.5}
    assert S.RELEASE["B5"] == (2, 28) and S.RELEASE["B6"] == (1, 11)


def test_sample_idx_month_ends_for_fund():
    cal = ["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-27", "2020-03-02"]
    assert C.sample_idx(cal, "m") == [1, 3, 4]
    assert C.sample_idx(cal, "d") == [0, 1, 2, 3, 4]


def test_build_proxy_for_tw_vix_and_composite_needs_two_thirds():
    rnd = random.Random(5)
    cal = _days(800)
    px, p = [], 10000.0
    for _ in cal:
        p *= 1 + rnd.gauss(0.0003, 0.01)
        px.append(p)
    D = {"turnover": {d: [1e11, px[i]] for i, d in enumerate(cal)},
         "vix": {d: 15 + rnd.random() * 10 for d in cal},
         "vixtw": {d: 20 + rnd.random() * 10 for d in cal[-20:]}}
    B = C.build(D)
    i = len(cal) - 1
    assert B["proxy"]["T10"][i] and B["heat"]["T10"][i] == B["heat"]["T9"][i]     # 歷史不夠：用美國 VIX 的 0～100
    assert B["hc"]["T10"][i] is None                                              # 不算進總分
    have = [k for k in S.ITEMS["tech"] if B["hc"][k][i] is not None]
    assert have == ["T1", "T2", "T3", "T4", "T8", "T9"]
    assert B["comp"]["tech"][i] is None                                           # 6 項 < 10 項的 2/3
    assert not B["proxy"]["T10"][i - 25] and B["heat"]["T10"][i - 25] is None     # 沒有台指 VIX 的日子不代替
    assert B["vixcorr"]["n"] == 20 and B["vixcorr"]["a"] == cal[-20]
    four = {k: B["hc"][k][i] for k in ("T1", "T2", "T3", "T4")}
    assert H.composite(four | {"T8": 50.0, "T9": 50.0, "T5": 50.0}, S.ITEMS["tech"]) is not None   # 7 項就給分


def test_evaluate_on_synthetic_market(monkeypatch):
    rnd = random.Random(3)
    n = 5300
    cal = _days(n)
    px, p = [], 100.0
    for _ in cal:
        p *= 1 + rnd.gauss(0.0003, 0.01)
        px.append(p)
    # 「熱度」＝之後 10 日漲跌的反向（熱了之後較弱），加雜訊
    x = [max(0.0, min(100.0, 50 - 400 * (px[min(n - 1, i + 11)] / px[min(n - 1, i + 1)] - 1) + rnd.gauss(0, 5)))
         for i in range(n)]
    monkeypatch.setattr(H.spearman_ci, "__defaults__", (200, S.BOOT_SEED, S.CI))   # 測試只重抽 200 次
    ev = C.evaluate(x, px, cal, "tech")
    e = ev[10]
    assert e["verdict"] == "weak" and e["block"] == 10 and e["hi"] < 0
    assert e["h1"]["rho"] < 0 and e["h2"]["rho"] < 0 and e["h1"]["n"] + e["h2"]["n"] == e["n"]
    assert e["h1"]["z"] < e["h2"]["a"]                                         # 前一半在前
    assert [r["n"] > 0 for r in e["ref"]] == [True, True]                      # 第一階段切分（2014–2019／2020 起）
    assert e["bands"][-1]["band"] == "全部" and e["bands"][-1]["n"] == e["n"]
    assert ev[60]["block"] == 60
    fund = C.evaluate(x, px, cal, "fund")                                      # 每月一個樣本，區塊＝月數
    assert fund[250]["block"] == 12 and fund[120]["block"] == 6 and fund[250]["n"] < 260
