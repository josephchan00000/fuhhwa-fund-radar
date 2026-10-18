"""景氣溫度頁第五版描述層（arm/lab/heatpos.py；規劃文件第 14.14 節第 1、2、6 點）：歷史位置、新高新低、熱度色帶、邊際變化。"""
import random
from datetime import date, timedelta

from arm.lab import heat as H
from arm.lab import heatcalc as C
from arm.lab import heatpos as P
from arm.lab import heatspec as S


def _days(a: date, n: int):
    d, out = a, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _B(cal, raw=None, nat=None, mraw=None, ym=None, comp=None):
    """只放用得到的欄位；其他項目一律沒有值。"""
    T = len(cal)
    raw = dict(raw or {})
    for k in S.KEYS:
        raw.setdefault(k, [None] * T)
    return {"cal": cal, "raw": raw, "nat": nat or {}, "mraw": mraw or {}, "ym": ym or {},
            "comp": comp or {d: [None] * T for d in S.DIMS}}


def test_week_ends_last_trading_day_of_each_week():
    cal = ["2026-09-21", "2026-09-22", "2026-09-24", "2026-09-29", "2026-10-02", "2026-10-05", "2026-10-08", "2026-10-13"]
    assert [cal[i] for i in P.week_ends(cal)] == ["2026-09-24", "2026-10-02", "2026-10-08", "2026-10-13"]


def test_daily_percentiles_match_the_score_definition():
    rnd = random.Random(2)
    cal = _days(date(2014, 1, 1), 3000)
    xs = [None if rnd.random() < 0.03 else rnd.gauss(0, 1) for _ in cal]
    xs[-1] = 0.7
    nat = {"C3": {d: v for d, v in zip(cal, xs) if v is not None}}
    B = _B(cal, raw={"C3": xs}, nat=nat)
    pos = P.position(B, "C3")
    t = len(cal) - 1
    assert abs(pos["p3"] - H.pct_series(xs, 750, 375)[t]) < 1e-9            # 近 3 年＝分數用的百分位（方向前）
    past10 = [v for v in xs[t - 2500:t] if v is not None]
    exp = 100.0 * (sum(1 for v in past10 if v < 0.7) + 0.5 * sum(1 for v in past10 if v == 0.7)) / len(past10)
    assert abs(pos["p10"] - exp) < 1e-9
    assert pos["pall"] is not None and pos["from"] == cal[0]


def test_coverage_rule_hides_short_windows():
    cal = _days(date(2024, 1, 1), 800)
    xs = [None] * 300 + [float(i) for i in range(500)]                       # 近 3 年只有 500／750 筆 < 8 成
    B = _B(cal, raw={"C3": xs}, nat={"C3": {d: v for d, v in zip(cal, xs) if v is not None}})
    pos = P.position(B, "C3")
    assert pos["p3"] is None and pos["p10"] is None and pos["pall"] == 100.0


def test_record_kinds_daily():
    cal = _days(date(2020, 1, 1), 900)
    for back, kind, n in ((400, "since_y", 1), (120, "since", None), (40, None, None)):
        xs = [1.0] * len(cal)
        xs[-1 - back] = 5.0                         # 上一次更高在 back 個交易日前
        xs[-1] = 3.0
        r = P.record(cal, xs, True, "d")
        gap = (date.fromisoformat(cal[-1]) - date.fromisoformat(cal[-1 - back])).days
        assert r["kind"] == kind and r["d"] == cal[-1 - back], (back, r)
        if kind == "since_y":
            assert r["n"] == int(gap / 365.25)
    xs = [1.0, 3.0, 2.0, 3.0]                        # 沒有更高的、之前出現過同值 → 有資料以來最高（並列）
    r = P.record(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"], xs, True, "d")
    assert r["kind"] == "ath" and r["tie"] and r["d"] == "2020-01-01"
    r = P.record(["2020-01-01", "2020-01-02"], [5.0, 1.0], False, "d")       # 低的一邊
    assert r["side"] == "lo" and r["kind"] == "ath" and not r["tie"]


def test_record_kinds_monthly_and_years():
    ks = [C.ym_add("2000-01", k) for k in range(320)]
    vs = [1.0] * 320
    vs[0] = 9.0                                      # 2000-01 最高，之後都低
    vs[-1] = 8.0
    r = P.record(ks, vs, True, "m")
    assert r["kind"] == "since_y" and r["d"] == "2000-01" and r["n"] == P._months_between("2000-01", ks[-1]) // 12
    vs = [1.0] * 320
    vs[-3] = 9.0                                     # 2 個月前更高 → 不寫
    vs[-1] = 8.0
    assert P.record(ks, vs, True, "m")["kind"] is None


def test_value_range_distance_by_unit():
    cal = _days(date(2010, 1, 1), 4000)
    xs = [100.0 + i for i in range(len(cal))]
    xs[-500] = 99999.0                               # 近 10 年最高
    xs[-1] = 50000.0
    rg = P.value_range(cal, xs, "C1", True)          # 億：全部 > 0 → 百分比
    assert rg["how"] == "pct" and rg["hi"] == 99999.0 and rg["hi_d"] == cal[-500]
    assert abs(rg["dist"] - 100 * (50000 / 99999 - 1)) < 1e-9
    assert rg["a"] > P._years_back(cal[-1], 10)
    rg = P.value_range(cal, xs, "C2", True)          # %：差幾個百分點
    assert rg["how"] == "pp" and abs(rg["dist"] - (50000 - 99999)) < 1e-9
    ys = [v - 60000.0 for v in xs]                   # 有負值 → 原單位的差
    rg = P.value_range(cal, ys, "C5", False)
    a = P._years_back(cal[-1], 10)
    ext = min(v for d, v in zip(cal, ys) if d > a)
    assert rg["how"] == "abs" and rg["side"] == "lo" and rg["lo"] == ext and abs(rg["dist"] - (ys[-1] - ext)) < 1e-9


def test_strip_weeks_position_and_last_time():
    cal = _days(date(2025, 1, 6), 400)
    comp = [50.0] * 400
    for i in range(100, 120):
        comp[i] = 95.0                               # 過去一段比現在還熱
    for i in range(380, 400):
        comp[i] = 90.0                               # 現在過熱（最後 20 個交易日＝4 週）
    B = _B(cal, comp={d: (comp if d == "fund" else [None] * 400) for d in S.DIMS})
    st = P.strip(B, "fund")
    assert len(st["cells"]) == S.STRIP_WEEKS and st["cells"][-1][0] == cal[-1] and st["band"] == "過熱"
    assert st["weeks"] == 4
    past = comp[:399]
    assert st["pos"] == ("hot", 100.0 * sum(1 for v in past if v < 90) / len(past))
    assert st["last"] == ("hot", cal[119])
    B2 = _B(cal, comp={d: ([None] * 10 + [40.0] * 390 if d == "tech" else [None] * 400) for d in S.DIMS})
    st2 = P.strip(B2, "tech")
    assert st2["pos"][0] == "mid" and st2["last"] is None and st2["first"] == cal[10]


def test_summary_sentence():
    mk = lambda b, w: {"band": b, "weeks": w}          # noqa: E731
    s = P.summary({"fund": mk("過熱", 27), "chip": mk("過熱", 3), "gliq": mk("過冷", 6), "tliq": mk("中性", 4),
                   "tech": mk("中性", 1)})
    assert s == "基本面（27 週）、籌碼過熱；台灣資金、技術中性；全球資金（6 週）過冷"


def test_state_and_words():
    assert [P.state_of(*x) for x in ((1, 1), (1, -1), (-1, -1), (-1, 1), (0, 1), (1, 0), (None, 1))] == [1, 2, 3, 4, 0, 0, None]
    assert P.word("B5", 1) == "成長加速" and P.word("B3", 4) == "收縮收斂" and P.word("B7", 2) == "通膨趨緩"
    assert P.word("C1", 3) == "減少加速" and P.word("G1", 1) == "上升加速" and P.word("B1", 0) == "持平"


def test_monthly_derivative_definitions():
    M = {C.ym_add("2020-01", k): float(k * k) for k in range(12)}
    d1, d2 = P._monthly_d(M, S.DERIV["B1"])                               # 一階＝3 個月差、二階＝一階的 3 個月差
    assert d1["2020-04"] == 9.0 and d1["2020-07"] == 36.0 - 9.0 and d2["2020-07"] == 27.0 - 9.0
    d1, d2 = P._monthly_d({"2020-01": 52.0, "2020-04": 49.0}, S.DERIV["B3"])   # PMI：一階＝PMI − 50
    assert d1 == {"2020-01": 2.0, "2020-04": -1.0} and d2 == {"2020-04": -3.0}
    d1, d2 = P._monthly_d({"2020-01": 5.0, "2020-04": 8.0}, S.DERIV["B5"])     # 年增率：一階＝本身
    assert d1["2020-04"] == 8.0 and d2["2020-04"] == 3.0


def test_daily_derivative_definitions_and_no_lookahead():
    rnd = random.Random(4)
    ks = _days(date(2020, 1, 1), 300)
    N = {d: 1000 + i + rnd.gauss(0, 5) for i, d in enumerate(ks)}
    d1, d2 = P._daily_d(N, S.DERIV["C1"])
    vs = H.roll_mean([N[d] for d in ks], 5)
    i = 100
    assert abs(d1[ks[i]] - 100 * (vs[i] / vs[i - 20] - 1)) < 1e-12
    assert abs(d2[ks[i]] - (d1[ks[i]] - d1[ks[i - 20]])) < 1e-12
    cut = 200                                                             # 截在任何一天重算 = 完整資料截到那天
    c1, c2 = P._daily_d({d: N[d] for d in ks[:cut + 1]}, S.DERIV["C1"])
    assert c1 == {d: v for d, v in d1.items() if d <= ks[cut]} and c2 == {d: v for d, v in d2.items() if d <= ks[cut]}
    g1, g2 = P._daily_d(N, S.DERIV["G1"])                                 # self：一階＝本身、二階＝63 筆差
    assert g1[ks[100]] == N[ks[100]] and abs(g2[ks[100]] - (N[ks[100]] - N[ks[37]])) < 1e-12
    e1, e2 = P._daily_d(N, S.DERIV["C5"])                                 # chg：5 日平均的 20 筆差
    assert abs(e1[ks[100]] - (vs[100] - vs[80])) < 1e-9


def test_deriv_now_streak_and_release_lag():
    cal = _days(date(2021, 1, 4), 500)
    M = {C.ym_add("2010-01", k): 50 + (k % 7) for k in range(160)}       # PMI 月序列
    ym = H.asof_monthly(cal, {m: m for m in M}, S.RELEASE["B3"])
    B = _B(cal, raw={"B3": H.asof_monthly(cal, M, S.RELEASE["B3"])}, mraw={"B3": M}, ym={"B3": ym})
    D = P.deriv(B, "B3")
    now = P.deriv_now(B, "B3", D)
    cur = ym[-1]
    d1, d2 = P._monthly_d(M, S.DERIV["B3"])
    assert now["asof"] == cur and now["d1"] == d1[cur] and now["d2"] == d2[cur]
    ks = sorted(m for m in d2 if m <= cur)
    sg = (d2[cur] > 0) - (d2[cur] < 0)
    n = 0
    for m in reversed(ks):
        if ((d2[m] > 0) - (d2[m] < 0)) != sg:
            break
        n += 1
    assert now["streak"] == n
    assert all(v is None or v <= cur for v in ym)                       # 只用公布時間差之後拿得到的月份
