"""景氣溫度頁：各指標的組法（arm/lab/heatcalc.py；規格 heatspec VER 2，實作細節見規劃文件第 10.4 節）。"""
from arm.lab import heatcalc as C
from arm.lab import heatspec as S


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


def test_month_avg_and_yoy_helpers():
    ser = {f"2020-01-{d:02d}": 1.0 for d in range(1, 11)} | {f"2020-02-{d:02d}": 2.0 for d in range(1, 6)}
    assert C.month_avg(ser) == {"2020-01": 1.0}                    # 2 月只有 5 天
    assert C.ym_add("2020-01", -1) == "2019-12" and C.ym_add("2019-12", 13) == "2021-01"
    assert C.yoy({"2020-03": 110.0, "2019-03": 100.0}, "2020-03") == 10.000000000000009


def test_futures_options_items():
    futi = {"2026-10-16": {"TX": {"外資": [9812, 103487], "投信": [1, 2], "自營商": [3, 4]},
                           "MTX": {"外資": [4000, 8000], "投信": [100, 0], "自營商": [500, 600]},
                           "TMF": {"外資": [200, 0]}},
            "2018-06-05": {"TX": {"外資": [1000, 0]}}}                   # 小台缺：不算
    assert C.f1_foreign_fut(futi) == {"2026-10-16": (9812 - 103487) + (4000 - 8000) / 4 + 200 / 20}
    assert C.f2_retail_mtx(futi, {"2026-10-16": 50000}) == {"2026-10-16": 100.0 * ((8000 + 0 + 600) - (4000 + 100 + 500)) / 50000}
    opti = {"2026-10-16": {"買權": {"外資": [838170, 709347]}, "賣權": {"外資": [500000, 600000]}}}
    assert C.f3_foreign_opt(opti) == {"2026-10-16": ((838170 - 709347) - (500000 - 600000)) / 1e5}


def test_monthly_items_and_release_alignment():
    ndc = {C.ym_add("2000-01", i): [None, 100.0 + i, None, None, None, None, 20.0 + (i % 20), "綠"] for i in range(200)}
    M = C.raw_monthly({"ndc": ndc, "orders": {C.ym_add("2000-01", i): 100.0 + i for i in range(30)},
                       "money": {}, "twcpi": {}, "effr": {}, "uscpi": {}, "ust": {}, "pmi": {}})
    assert M["L2"]["2000-07"] == 6.0 and "2000-06" not in M["L2"]          # 和 6 個月前的差
    s_now = 100 + 14 + 100 + 13 + 100 + 12                                 # 2001-03＋02＋01
    s_ago = 100 + 2 + 100 + 1 + 100 + 0
    assert abs(M["L4"]["2001-03"] - 100 * (s_now / s_ago - 1)) < 1e-9
    assert S.RELEASE["L1"] == (2, 28)


def test_sample_idx_month_ends_for_long_line():
    cal = ["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-27", "2020-03-02"]
    assert C.sample_idx(cal, "long") == [1, 3, 4]
    assert C.sample_idx(cal, "short") == [0, 1, 2, 3, 4]


def test_evaluate_and_research_on_synthetic_market(monkeypatch):
    import random
    rnd = random.Random(3)
    n = 5300
    cal, px, d0 = [], [], __import__("datetime").date(2006, 1, 2)
    p = 100.0
    while len(cal) < n:
        if d0.weekday() < 5:
            cal.append(d0.isoformat())
            p *= 1 + rnd.gauss(0.0003, 0.01)
            px.append(p)
        d0 += __import__("datetime").timedelta(days=1)
    # 「熱度」＝之後 10 日漲跌的反向（熱了之後較弱），加雜訊
    x = []
    for i in range(n):
        j = min(n - 1, i + 11)
        x.append(max(0.0, min(100.0, 50 - 400 * (px[j] / px[min(n - 1, i + 1)] - 1) + rnd.gauss(0, 5))))
    from arm.lab import heat as H
    monkeypatch.setattr(H.spearman_ci, "__defaults__", (200, S.BOOT_SEED, S.CI))   # 測試只重抽 200 次
    ev = C.evaluate(x, px, cal, "short")
    assert ev[10]["verdict"] == "weak" and ev[10]["dir"] == -1 and ev[10]["block"] == 10
    assert ev[10]["is"]["a"] >= "2014-01-01" and ev[10]["oos"]["a"] >= "2020-01-01"
    assert ev[10]["is"]["bands"][-1]["band"] == "全部"
