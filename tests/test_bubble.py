"""泡沫頁計算（arm/lab/bubble.py；規格 bubspec VER 1）：小工具與條件的單元測試（假資料，不碰網路）。"""
import math
import random

from arm.lab import bubble as BB
from arm.lab import bubspec as BS
from arm.lab import heatbubble as HB


def test_fill_cpi_geometric_and_gap_limit():
    out = BB.fill_cpi({"2025-09": 100.0, "2025-11": 104.04, "2025-12": 105.0})
    assert abs(out["2025-10"] - math.sqrt(100.0 * 104.04)) < 1e-9          # 只缺一個月＝前後兩個月的幾何平均
    two = BB.fill_cpi({"2020-01": 100.0, "2020-04": 103.0})
    assert abs(two["2020-02"] / 100.0 - (1.03) ** (1 / 3)) < 1e-12 and abs(two["2020-03"] / 100.0 - (1.03) ** (2 / 3)) < 1e-12
    far = BB.fill_cpi({"2020-01": 100.0, "2020-05": 104.0})               # 缺 3 個月：不補
    assert set(far) == {"2020-01", "2020-05"}


def test_expanding_pct_span_uses_months_not_rows():
    ser = {"2000-01": 1.0, "2000-04": 3.0, "2000-07": 2.0, "2000-10": 5.0}
    out = BB.expanding_pct_span(ser, 3)                                  # 季資料：3 個月的歷史從 2000-04 起
    assert out == {"2000-04": 100.0, "2000-07": 50.0, "2000-10": 100.0}
    assert BB.expanding_pct_span(ser, 9) == {"2000-10": 100.0}
    tie = BB.expanding_pct_span({"2000-01": 1.0, "2000-02": 1.0}, 1)
    assert tie == {"2000-02": 50.0}                                      # 相等算一半（同 heat.pct_series）


def test_cv_at_interpolates_and_clamps():
    T = {"grid": [0.0, 0.1, 0.2], "q50": [[0.0, 1.0], [0.0, 2.0], [0.0, 3.0]], "q95": [[0.0, 10.0], [0.0, 20.0], [0.0, 40.0]]}
    assert BB.cv_at(T, 1, 0.05) == (1.5, 15.0)
    assert BB.cv_at(T, 1, 0.15) == (2.5, 30.0)
    assert BB.cv_at(T, 1, -1.0) == (1.0, 10.0) and BB.cv_at(T, 1, 9.0) == (3.0, 40.0)
    assert BB.cv_at(T, 5, 0.1) == (None, None)


def test_p2_daily_needs_two_year_double_near_all_time_high():
    px = [100.0] * 10 + [50.0] * 500 + [100.0 + i for i in range(10)] + [210.0]
    ru, dist, flag = BB.p2_daily(px)
    i = len(px) - 1
    assert ru[i] is not None and ru[i] >= 100 and flag[i] is True        # 210 vs 504 天前 50（+320%）、而且在新高
    reb = [300.0] * 10 + [50.0] * 500 + [120.0] * 10                     # 從 50 漲到 120（+140%），但離高點 300 還很遠
    _, d2, f2 = BB.p2_daily(reb)
    assert f2[-1] is False and d2[-1] < -50
    assert BB.p2_daily([1.0] * 100)[2][-1] is None                        # 不到 504 天：算不出來


def test_psy_drift_flags_explosive_tail_and_run_rule():
    rnd = random.Random(3)
    y, v = [], 0.0
    for t in range(300):
        v += 0.004 + rnd.gauss(0, 0.04)
        y.append(v)
    for t in range(30):                                                  # 最後 30 個月爆發性上漲
        v = v * 1.0 + 0.08 + 0.02 * t
        y.append(v)
    months = []
    ym = "1990-01"
    for _ in y:
        months.append(ym)
        ym = BB._ym_add(ym, 1)
    M = dict(zip(months, y))
    cv = HB.psy_cv(60, 200, len(y), 11)
    T = {"grid": [0.0, 0.2], "q50": [cv["q50"], cv["q50"]], "q95": [cv["q95"], cv["q95"]]}
    R = BB.psy_drift(M, T)
    assert months[59] not in R and months[60] in R                       # 漂移要 60 個月變化才算
    assert R[months[-1]]["hit"] and R[months[-1]]["x"] == 100.0
    F = BB.p1_flags(R)
    assert F[months[-1]] is True
    k = next(m for m in months if (R.get(m) or {}).get("hit"))
    assert F[k] is False                                                 # 第一個超過臨界值的月份還沒連續 3 個月


def test_month_end_idx():
    cal = ["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02"]
    assert BB.month_end_idx(cal) == [1, 3, 4]


def test_validate_counts_hot_months_and_returns():
    rows, dates = [], []
    ym = "1990-01"
    for j in range(120):
        hot = 30 <= j < 45 or 80 <= j < 95
        rows.append({"d": f"{ym}-28", "P1": hot, "P2": hot, "P3": None, "E": (30 <= j < 45) if j >= 20 else None,
                     "V": None, "F": None, "L": BS.level2(hot, 30 <= j < 45, False, False),
                     "L1": BS.level(2 if hot else 0, False, False)})
        dates.append(f"{ym}-28")
        ym = BB._ym_add(ym, 1)
    dd = {252: [0.5 if r["P1"] else 0.05 for r in rows], 504: [0.6 if r["P1"] else 0.1 for r in rows]}
    fwd = {252: [-10.0 if r["P1"] else 8.0 for r in rows], 504: [-20.0 if r["P1"] else 15.0 for r in rows]}
    out = BB.validate(rows, dates, dd, fwd)
    assert out["P1"]["252"]["n_hot"] == 30 and out["P1"]["252"]["p_hot"] == 1.0
    assert abs(out["P1"]["252"]["ret_hot"] + 10.0) < 1e-9
    assert out["P3"] == {"n_hot": 0} and out["L4"] == {"n_hot": 0}       # 算不出來／從沒出現的條件
    assert out["L3v1"]["252"]["n_hot"] == 30                              # VER 1：兩個價格條件就到 3
    assert out["L3"]["252"]["n_hot"] == 15 and out["PF"]["252"]["n_hot"] == 15 and out["PN"]["252"]["n_hot"] == 15
    assert out["E"]["share"] == 15 / 100 * 100                            # E 前 20 個月算不出來，不算進分母
    assert abs(sum(out["dist"].values()) - 100.0) < 1e-9 and abs(sum(out["dist1"].values()) - 100.0) < 1e-9


def test_roll_and_asof_helpers():
    m = {f"2020-{k:02d}": float(k) for k in range(1, 13)}
    assert BB.roll_sum(m, 12) == {"2020-12": 78.0} and BB.roll_sum(m, 3)["2020-03"] == 6.0 and "2020-02" not in BB.roll_sum(m, 3)
    q = {"2020-03": 4.0, "2020-06": 8.0, "2020-09": 12.0, "2020-12": 16.0, "2021-06": 20.0}
    assert BB.roll_q_avg(q, 4) == {"2020-12": 10.0}                       # 2021-06 少了 2021-03：不算
    months = ["2021-01", "2021-02", "2021-03", "2021-04", "2022-05"]
    fa = BB.fund_asof({"2020-12": 1.0, "2021-01": 2.0}, months, (2, 10))  # 2021-01 那期 2021-03-10 才拿得到
    assert fa["2021-02"] == ("2020-12", 1.0) and fa["2021-03"] == ("2021-01", 2.0)
    assert "2021-01" not in fa                                            # 2020-12 那期 2021-02-10 才拿得到
    assert "2022-05" not in fa                                            # 最新一期比當月舊超過 12 個月：不算
    lr = BB.ratio_log({"2021-03": 10.0, "2021-04": 0.0}, {"2021-03": ("2021-01", 2.0), "2021-04": ("2021-01", 2.0)})
    assert abs(lr["2021-03"] - math.log(5.0)) < 1e-12 and "2021-04" not in lr


def test_e_flags_need_three_months_in_a_row():
    rnd = random.Random(5)
    y, v = [], 0.0
    for t in range(200):
        v += rnd.gauss(0, 0.03)
        y.append(v)
    for t in range(25):                                                   # 比值最後 25 個月爆發
        v += 0.06 + 0.01 * t
        y.append(v)
    months, ym = [], "1990-01"
    for _ in y:
        months.append(ym)
        ym = BB._ym_add(ym, 1)
    cv = HB.psy_cv(60, 200, len(y), 11)
    T = {"grid": [0.0, 0.2], "q50": [cv["q50"], cv["q50"]], "q95": [cv["q95"], cv["q95"]]}
    EF = BB.e_flags({"x": {"lr": dict(zip(months, y))}}, T)["x"]
    assert EF["f"][months[-1]] is True
    first = next(m for m in months if (EF["R"].get(m) or {}).get("hit"))
    assert EF["f"][first] is False
