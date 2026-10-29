"""美股個股報告資料包（arm/lab/eqfacts_us.py；評等規格 eqspec VER 3 的美股口徑）。用假資料逐項驗算。"""
import pytest

from arm.lab import eqfacts_us as U
from arm.lab import eqspec as S


def _fq():
    q, sh = [], []
    ends = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    files = ["2024-05-01", "2024-08-01", "2024-11-01", "2025-02-20", "2025-05-01", "2025-08-01", "2025-11-01", "2026-02-20"]
    for i, (e, fd) in enumerate(zip(ends, files)):
        rev, ni = 1000.0 + 100 * i, 100.0 + 10 * i                      # 百萬美元
        q.append([e, fd, rev, rev * 0.8, rev * 0.3, ni, ni / (60 - i), 2000.0 - 100 * i])
        sh.append([e, fd, 60.0 - i])                                      # 一直買回：股數每季少 1 百萬股
    return {"q": q, "sh": sh, "peer": {"ind": "Software", "n": 5, "rows": [
        ["ME", 120.0, 0.1, 0.3, 0.4, 25.0, 0.2], ["A", 300.0, 0.05, 0.4, 0.5, 20.0, 0.1], ["B", 90.0, 0.12, 0.2, 0.2, 30.0, 0.3],
        ["C", 40.0, 0.07, 0.1, 0.1, 15.0, 0.0], ["D", 30.0, 0.15, 0.1, 0.02, 150.0, 0.4]]}}


def test_quarters_use_net_income_over_current_shares():
    qs = U.quarters(_fq())
    o = qs[-1]
    ni4 = sum(100.0 + 10 * i for i in range(4, 8))
    assert o["ni4"] == round(ni4 / 100, 2)                               # 億美元
    assert o["eps4"] == round(ni4 / (60 - 7), 2)                         # 近四季淨利 ÷ 公布那時的股數（VER 3）
    assert o["eps4r"] == round(sum((100.0 + 10 * i) / (60 - i) for i in range(4, 8)), 2)   # 財報 EPS 加總只給人看
    assert o["eps4"] > o["eps4r"]                                         # 買回股票時兩者不同，這正是要分開的原因
    assert o["rev_yoy"] == pytest.approx((1700 / 1300 - 1) * 100, abs=0.05)
    assert o["roe4"] == round(ni4 / ((1300 + 1700) / 2) * 100, 1)
    assert o["gm"] == 80.0 and o["om"] == 30.0


def test_bands_price_times_shares_over_ni4():
    fq = _fq()
    qs = U.quarters(fq)
    px = [("2026-01-30", 100.0), ("2026-02-27", 110.0), ("2026-03-31", 120.0)]
    b = U.bands(px, qs, fq["sh"], "2026-03")
    rows = {r[0]: r for r in b["rows"]}
    ni4_jan = sum(100.0 + 10 * i for i in range(3, 7))                  # 1 月底：第四季（2/20 公布）還沒出來
    assert rows["2026-01"][2] == round(ni4_jan / (60 - 6), 2)
    ni4_feb = sum(100.0 + 10 * i for i in range(4, 8))
    assert rows["2026-02"][2] == round(ni4_feb / (60 - 7), 2)
    assert dict(b["pe"]["ser"])["2026-02"] == round(110.0 / round(ni4_feb / 53, 2), 1)


def test_f12m_uses_fiscal_year_end():
    an = {"y0": {"e": [8.8, 8.0, 9.0, 30, 7.5], "end": "2026-09-30"}, "y1": {"e": [9.6, 9.0, 10.0, 30, 8.8], "end": "2027-09-30"}}
    f = U.f12m_eps(an, "2026-10-30")
    assert f["eps"] == 9.6 and f["w"] == 0                               # 今年已結束還沒公布 → 只用明年
    an2 = {"y0": {"e": [10.0, 9, 11, 21, 9], "end": "2026-12-31"}, "y1": {"e": [12.0, 11, 13, 21, 10], "end": "2027-12-31"}}
    assert U.f12m_eps(an2, "2026-10-30")["eps"] == round(S.f12m("2026-10-30", 10.0, 12.0, "2026-12-31"), 2)
    an3 = {"y0": {"e": [10.0, 9, 11, 2, 9], "end": "2026-12-31"}, "y1": {"e": [12.0, 11, 13, 2, 10], "end": "2027-12-31"}}
    assert U.f12m_eps(an3, "2026-10-30") == {"eps": None, "src": "none"}   # 分析師不到 3 位


def test_implied_uses_adjusted_actuals_only():
    an = {"y0": {"e": [12.0, 11, 13, 21, 9.0], "end": "2026-12-31"},
          "eh": [["2025-09-30", 1.9, 1.8], ["2025-12-31", 2.5, 2.4], ["2026-03-31", 3.1, 3.0], ["2026-06-30", 2.8, 2.4]]}
    imp = U.implied(an, 12, "2026-06-30")
    assert imp["eps_ytd"] == 5.9 and imp["eps_rest"] == 6.1 and imp["eps_rest_ly"] == 4.4
    assert imp["eps_rest_x"] == round(6.1 / 4.4, 1) and imp["adj"] is True
    assert U.implied(an, 12, "2026-09-30") == {}                          # 財報比預估資料新 → 不算（不混）


def test_annual_by_fiscal_year_and_slug():
    qs = U.quarters(_fq())
    ys = U.annual(qs, 12, [["2025-03-01", 0.5], ["2025-06-01", 0.5]])
    assert [y["y"] for y in ys] == ["2024", "2025"] and ys[1]["dps"] == 1.0
    assert U.fy_of("2025-10-31", 1) == 2026 and U.fy_of("2026-01-31", 1) == 2026
    assert U.slug("Human Resource & Employment Services") == "us-human-resource-and-employment-service"


def test_pick_info_from_qm():
    qm = {"now": {"list": [{"c": "X"}, {"c": "ME"}], "met": {"ME": [97.0, -0.002, 0.317, 0.411, 1.238e10]}, "buy": ["ME"],
                  "next": "2026-10-26", "wk": "2026-10-23", "n_list": 57, "hold": []},
          "rule": {"qm": {"rs": 80.0, "d52h": -0.25, "om": 0.1, "roe": 0.15, "cap": 2e9}, "slots": 8, "exit": {"ma": 50}}}
    p = U.pick_info("ME", qm)
    assert p["rank"] == 2 and p["buy"] and p["om"] == 31.7 and p["cap"] == 123.8 and p["rule"]["cap"] == 20
    assert U.pick_info("ZZ", qm) == {}
