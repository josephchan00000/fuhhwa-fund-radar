"""訊號總覽的計算（arm/lab/sigcat.py）：和逐筆直接算的版本比對。"""
import numpy as np

from arm.lab import sigcat as G
from arm.lab import sigspec as S


def _px(T=400, seed=1):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, T)))


def test_outcomes_match_direct_loop():
    px = _px()
    for H, th in ((20, 0.08), (60, 0.10)):
        up, wn = G.outcomes(px, H, th)
        for t in range(len(px)):
            e = t + S.LAG
            if e + H > len(px) - 1:
                assert np.isnan(up[t]) and np.isnan(wn[t])
                continue
            assert up[t] == float(px[e + H] > px[e])
            assert wn[t] == float(min(px[e + 1:e + H + 1]) <= px[e] * (1 - th))


def test_dedupe_skips_repeats_within_horizon():
    assert G.dedupe([5, 10, 25, 26, 47, 100], 20) == [5, 26, 47, 100]
    assert G.dedupe([], 20) == []


def test_episodes_gap_rule():
    # 中斷的樣本數 < gap 算同一段
    assert G.episodes([0, 1, 2, 10, 30, 31], 20) == [[0, 1, 2, 10, 30, 31]]     # 中斷 19 天
    assert G.episodes([0, 1, 2, 10, 31, 32], 20) == [[0, 1, 2, 10], [31, 32]]   # 中斷 20 天
    assert G.episodes([3, 4, 6], 1) == [[3, 4], [6]]


def test_state_stat_is_mean_of_episode_rates():
    T = 300
    Yu = np.array([float(i % 3 == 0) for i in range(T)])
    Yw = 1 - Yu
    Yu[-5:] = np.nan
    Yw[-5:] = np.nan
    samp = np.arange(T)
    state = np.zeros(T, dtype=bool)
    state[10:20] = True                    # 一段
    state[100:105] = True                  # 一段
    state[110:112] = True                  # 中斷 4 天 < 20 → 同一段
    state[297:300] = True                  # 窗口都不完整 → 不算
    R = G.st_stat(state, samp, Yu, Yw, 20, 150)
    e1 = Yu[10:20].mean()
    e2 = np.concatenate([Yu[100:105], Yu[110:112]]).mean()
    assert R["up"]["n"] == 2 and abs(R["up"]["hit"] - (e1 + e2) / 2) < 1e-12
    assert abs(R["up"]["base"] - np.nanmean(Yu)) < 1e-12
    assert R["up"]["n10"] == 0 and R["up"]["hit10"] is None
    assert abs(R["up"]["base10"] - np.nanmean(Yu[150:])) < 1e-12
    assert [o[:3] for o in R["occ"]] == [[10, 19, 10], [100, 111, 7]]


def test_event_stat_counts_and_recent():
    T = 300
    Yu = np.array([float(i % 2 == 0) for i in range(T)])
    Yw = np.zeros(T)
    Yu[-10:] = np.nan
    Yw[-10:] = np.nan
    samp = np.arange(50, T)
    R = G.ev_stat([10, 60, 70, 100, 200, 295], Yu, Yw, samp, 20, 150)   # 10 不在樣本、70 在 60 之後 20 天內、295 窗口不完整
    assert [o[0] for o in R["occ"]] == [60, 100, 200]
    assert R["up"]["n"] == 3 and R["up"]["hit"] == 1.0
    assert R["up"]["n10"] == 1 and R["up"]["hit10"] == 1.0
    assert abs(R["up"]["base"] - np.nanmean(Yu[50:])) < 1e-12


def test_tier_rules():
    st = {"n": 12, "hit": 0.72, "base": 0.60, "n10": 3, "hit10": 0.2, "base10": 0.6}
    assert G.tier(st, "up") == "good"                      # 近 10 年不到 5 次：不檢查
    st.update(n10=6)
    assert G.tier(st, "up") == "ref"                       # 近 10 年沒過 → 差 ≥ 5 點 → 可參考
    st.update(hit10=0.75, base10=0.62)
    assert G.tier(st, "up") == "good"
    assert G.tier({"n": 12, "hit": 0.58, "base": 0.40, "n10": 0}, "up") == "ref"     # 命中率不到 60%
    assert G.tier({"n": 12, "hit": 0.52, "base": 0.40, "n10": 0}, "warn") == "good"  # 警示門檻 50%
    assert G.tier({"n": 12, "hit": 0.63, "base": 0.60, "n10": 0}, "up") == "none"
    assert G.tier({"n": 9, "hit": 0.9, "base": 0.1, "n10": 0}, "up") == "few"


def test_best_direction():
    dirs = {"up": {"tier": "ref", "hit": 0.6, "base": 0.5}, "warn": {"tier": "good", "hit": 0.6, "base": 0.3}}
    assert G.best(dirs) == ("good", ["warn"])
    dirs["up"]["tier"] = "good"
    assert G.best(dirs) == ("good", ["warn", "up"])
    assert G.best({"up": {"tier": "few", "hit": None, "base": None}, "warn": {"tier": "few", "hit": 0.5, "base": 0.4}})[0] == "few"


def test_write_stock_never_writes_partial_data(tmp_path):
    p = tmp_path / "s.json"
    assert G.write_stock({}, {}, p) is False and not p.exists()                    # 沒有個股資料
    assert G.write_stock({"adv": {"trades": {}}}, {"D": object()}, p) is False and not p.exists()
