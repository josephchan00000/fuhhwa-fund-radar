"""景氣溫度頁第五版研究（arm/lab/heatrel.py；規劃文件第 14.14 節第 4、6 點）：重抽、迴歸、檢定與判定。"""
import math
import random

from arm.lab import heat as H
from arm.lab import heatrel as R
from arm.lab import heatspec as S


def _direct_corr_ci(rx, ry, L, n_boot, seed):
    """逐筆重抽（heat.spearman_ci 的抽法：抽區塊湊滿 n 筆、最後截斷），只回信賴區間。"""
    rnd = random.Random(seed)
    n = len(rx)
    reps = []
    for _ in range(n_boot):
        bx, by = [], []
        while len(bx) < n:
            s = rnd.randrange(n - L + 1)
            bx.extend(rx[s:s + L])
            by.extend(ry[s:s + L])
        r = H._pearson(bx[:n], by[:n])
        if r is not None:
            reps.append(r)
    return R._q(reps)


def test_block_moment_bootstrap_equals_direct_resampling():
    rnd = random.Random(7)
    x = [rnd.gauss(0, 1) for _ in range(203)]
    y = [0.3 * a + rnd.gauss(0, 1) for a in x]
    rx, ry = H._rank(x), H._rank(y)
    for L in (4, 12, 50):
        lo, hi = R.boot_corr(rx, ry, L, n_boot=300, seed=11)
        a, b = _direct_corr_ci(rx, ry, L, 300, 11)
        assert abs(lo - a) < 1e-9 and abs(hi - b) < 1e-9, L
    assert R.boot_corr(rx[:20], ry[:20], 4) == (None, None)


def test_boot_partial_equals_direct_and_p_value():
    rnd = random.Random(8)
    z = [rnd.gauss(0, 1) for _ in range(150)]
    x = [a + rnd.gauss(0, 1) for a in z]
    y = [a + rnd.gauss(0, 1) for a in z]                   # x、y 只透過 z 相關 → 偏相關接近 0
    rx, ry, rz = H._rank(x), H._rank(y), H._rank(z)
    lo, hi, p = R.boot_partial(rx, ry, rz, 6, n_boot=300, seed=3)
    rnd2 = random.Random(3)
    reps = []
    for _ in range(300):
        bx, by, bz = [], [], []
        while len(bx) < 150:
            s = rnd2.randrange(150 - 6 + 1)
            bx.extend(rx[s:s + 6]); by.extend(ry[s:s + 6]); bz.extend(rz[s:s + 6])
        bx, by, bz = bx[:150], by[:150], bz[:150]
        reps.append(R.partial(H._pearson(bx, by), H._pearson(bx, bz), H._pearson(by, bz)))
    a, b = R._q(reps)
    assert abs(lo - a) < 1e-9 and abs(hi - b) < 1e-9
    exp_p = min(1.0, 2 * min(sum(1 for v in reps if v <= 0) / 300, sum(1 for v in reps if v >= 0) / 300))
    assert abs(p - exp_p) < 1e-12 and p > 0.05
    assert abs(R.partial_spearman(x, y, z)) < 0.25 and H.spearman(x, y) > 0.3


def test_chi2_survival_matches_known_critical_values():
    for x, k in ((3.841458820694124, 1), (5.991464547107979, 2), (7.814727903251178, 3), (12.591587243743977, 6)):
        assert abs(R.chi2_sf(x, k) - 0.05) < 1e-9, k
    assert abs(R.chi2_sf(10.0, 2) - math.exp(-5.0)) < 1e-12
    assert abs(R.chi2_sf(0.5, 1) - math.erfc(math.sqrt(0.25))) < 1e-12
    assert R.chi2_sf(0.0, 3) == 1.0


def test_ols_hc1_simple_regression_closed_form():
    rnd = random.Random(1)
    x = [rnd.gauss(0, 1) for _ in range(120)]
    y = [1.0 + 2.0 * a + rnd.gauss(0, 1 + abs(a)) for a in x]
    beta, V = R.ols_hc1([[1.0, a] for a in x], y)
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    b1 = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    b0 = my - b1 * mx
    e = [b - b0 - b1 * a for a, b in zip(x, y)]
    hc0 = sum((a - mx) ** 2 * u * u for a, u in zip(x, e)) / sxx ** 2
    assert abs(beta[0] - b0) < 1e-9 and abs(beta[1] - b1) < 1e-9
    assert abs(V[1][1] - hc0 * n / (n - 2)) < 1e-9
    w, p = R.wald(beta, V, [1])
    assert abs(w - beta[1] ** 2 / V[1][1]) < 1e-9 and p < 1e-6


def test_granger_detects_lead_and_not_noise():
    rnd = random.Random(5)
    n = 300
    x = [50.0]
    for _ in range(n - 1):
        x.append(max(0.0, min(100.0, 0.8 * x[-1] + 10 + rnd.gauss(0, 10))))
    r = [None] + [0.002 * (x[m - 1] - 50) + rnd.gauss(0, 0.04) for m in range(1, n)]
    g = R.granger(r, x, 3)
    assert g["A"]["n"] >= S.GR_MIN and g["A"]["p"] < 1e-4 and g["A"]["sum"] > 0
    noise = [None] + [rnd.gauss(0, 0.04) for _ in range(1, n)]
    g2 = R.granger(noise, x, 3)
    assert g2["A"]["p"] > 0.05
    short = R.granger(r[:60], x[:60], 3)
    assert short["A"]["p"] is None and R.gr_verdict(short["A"], None) == "few"


def test_gr_verdict_needs_q_and_both_halves_same_sign():
    e = {"p": 0.001, "sum": 0.5, "s1": 0.2, "s2": 0.4}
    assert R.gr_verdict(e, 0.05) == "strong"
    assert R.gr_verdict({**e, "sum": -0.5, "s1": -0.2, "s2": -0.1}, 0.05) == "weak"
    assert R.gr_verdict({**e, "s2": -0.1}, 0.05) == "none"
    assert R.gr_verdict(e, 0.2) == "none"


def test_bh_q_values():
    q = R.bh([0.01, 0.04, None, 0.03, 0.5])
    assert q[2] is None
    assert [round(v, 6) for v in (q[0], q[3], q[1], q[4])] == [0.04, 0.053333, 0.053333, 0.5]


def test_heat_events_need_twenty_clean_days_before():
    x = [50.0] * 30 + [85.0] + [70.0] * 5 + [90.0] + [50.0] * 30 + [10.0]
    assert R.heat_events(x, "hot") == [30]                   # 第 36 天又過 80，但前 20 天裡有 85 → 不算
    assert R.heat_events(x, "cold") == [len(x) - 1]
    y = [50.0] * 25 + [None] + [50.0] * 5 + [85.0]
    assert R.heat_events(y, "hot") == []                     # 前 20 天有缺值 → 不算


def test_event_vs_mask_compares_with_masked_days():
    px = [100.0 * (1.001 ** i) for i in range(400)]
    f = [H.fwd(px, i, 20)[0] for i in range(400)]
    mask = [i >= 100 for i in range(400)]
    e = R.event_vs_mask(px, [f"d{i}" for i in range(400)], [50, 150, 250], 20, mask, f)
    assert e["n"] == 2 and abs(e["diff"]) < 1e-12               # 第 50 天不在 mask 裡
    assert e["verdict"] == "few"


def test_group_stats_runs_halves_and_verdict():
    rnd = random.Random(9)
    ret = [rnd.gauss(0, 0.01) for _ in range(400)]
    flag = [False] * 400
    for a in (10, 60, 120, 200, 260, 330):
        for i in range(a, a + 6):
            flag[i] = True
            ret[i] += 0.05                                     # 這幾段之後明顯較強
    g = R.group_stats(ret, flag, [f"2020-{i:04d}" for i in range(400)], 4)
    assert g["n"] == 36 and g["runs"] == 6 and g["verdict"] == "strong" and g["lo"] > 0
    few = R.group_stats(ret, [i < 30 for i in range(400)], [f"2020-{i:04d}" for i in range(400)], 4)
    assert few["runs"] == 1 and few["verdict"] == "few"


def test_leadlag_follow_and_lead_rules():
    rnd = random.Random(3)
    px = [100.0]
    for _ in range(2600):
        px.append(px[-1] * (1 + rnd.gauss(0.0003, 0.01)))
    we = list(range(300, 2500, 5))
    past = [px[i] / px[i - 60] - 1 for i in we]
    x = [100 * H._rank(past)[k] / len(past) for k in range(len(past))]   # 0～100＝之前 60 日漲跌的排名
    ll = R.leadlag(x, we, px)
    assert ll["follow"] and ll["follow_h"] == 60 and ll["past"][60]["rho"] > 0.95
    fut = [H.fwd(px, i, 60)[0] for i in we]
    ok = [k for k, v in enumerate(fut) if v is not None]
    xs = [None] * len(we)
    rk = H._rank([fut[k] for k in ok])
    for j, k in enumerate(ok):
        xs[k] = 100 * rk[j] / len(ok)                                    # 0～100＝之後 60 日漲跌的排名（只在測試裡偷看）
    ll2 = R.leadlag(xs, we, px)
    assert ll2["lead"] == 60 and ll2["fut"][60]["verdict"] == "strong" and not ll2["follow"]
