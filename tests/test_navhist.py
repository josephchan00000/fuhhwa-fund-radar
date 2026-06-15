"""NAV 含息總報酬單元測試（M1-8）：配息再投入的數學正確性。"""
from arm import metrics, navhist


def test_total_return_no_dividend_equals_nav():
    rows = [("2026-04-01", 10.0), ("2026-05-01", 10.5), ("2026-06-01", 11.0)]
    tr = navhist.total_return_series(rows)
    assert [round(v, 6) for _, v, _ in tr] == [10.0, 10.5, 11.0]


def test_total_return_reinvests_dividend():
    # 5/01 除息每單位 0.5（當日 NAV 已是除息後 10.0）→ 用息加買單位
    rows = [("2026-04-01", 10.0), ("2026-05-01", 10.0), ("2026-06-01", 10.0)]
    tr = navhist.total_return_series(rows, {"2026-05-01": 0.5})
    vals = [v for _, v, _ in tr]
    assert round(vals[0], 6) == 10.0
    # units *= (10+0.5)/10 = 1.05 → 之後指數 = 1.05 * 10 = 10.5
    assert round(vals[1], 6) == 10.5
    assert round(vals[2], 6) == 10.5
    # 含息總報酬 > 純價格報酬（純 NAV 報酬為 0）
    si = metrics.si_return([(d, v, 0) for d, v, _ in tr])
    assert round(si, 6) == 0.05


def test_total_return_feeds_multi_period():
    rows = [("2026-06-08", 10.0), ("2026-06-09", 10.1), ("2026-06-10", 10.2),
            ("2026-06-11", 10.3), ("2026-06-12", 10.4)]
    tr = navhist.total_return_series(rows)
    mp = metrics.multi_period(tr, {"1d": 1, "si": None}, 2026)
    assert round(mp["1d"], 6) == round(10.4 / 10.3 - 1, 6)
    assert round(mp["si"], 6) == round(10.4 / 10.0 - 1, 6)
