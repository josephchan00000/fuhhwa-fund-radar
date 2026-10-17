"""景氣溫度頁（docs/lab_heat_plan.md）：規格鎖定＋計算核心。

規格是看驗證結果之前寫定的（heatspec.VER 1，2026-10-17）。要改就 VER＋1、寫進規劃文件第 10 節，不在舊版本上改——
這支測試鎖住 VER 1 的內容。"""
import random

from arm.lab import heat as H
from arm.lab import heatspec as S


def test_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-17"
    assert S.KEYS == ["S1", "S2", "S3", "S4", "S5", "S6", "F1", "F2", "F3", "F4", "F5",
                      "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8",
                      "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"]
    assert S.HOT == {"S1": 1, "S2": 1, "S3": 1, "S4": -1, "S5": -1, "S6": 1,
                     "F1": 1, "F2": 1, "F3": -1, "F4": 1, "F5": -1,
                     "M1": 1, "M2": 1, "M3": 1, "M4": 1, "M5": 1, "M6": -1, "M7": -1, "M8": -1,
                     "L1": 1, "L2": 1, "L3": 1, "L4": 1, "L5": 1, "L6": 1, "L7": 1, "L8": 1, "L9": -1, "L10": 1}
    assert {k: (v["fwd"], v["main"], v["freq"]) for k, v in S.LINES.items()} == {
        "short": ((5, 10), 10, "d"), "mid": ((20, 60), 60, "d"), "long": ((120, 250), 250, "m"), "fo": ((5, 10), 10, "d")}
    assert S.PCT_WIN == {"d": 750, "m": 120} and S.PCT_MIN == {"d": 375, "m": 60}
    assert S.RELEASE == {"L1": (2, 28), "L2": (2, 28), "L3": (1, 6), "L4": (1, 21), "L5": (1, 27),
                         "L6": (1, 10), "L8": (1, 16), "L10": (1, 15)}
    assert S.DAILY_LAG == 1
    assert S.SPLIT == {"d": {"is": ("2014-01-01", "2019-12-31"), "oos": ("2020-01-01", None)},
                       "m": {"is": ("1999-01-01", "2012-12-31"), "oos": ("2013-01-01", None)},
                       "fo": {"is": (None, "2021-12-31"), "oos": ("2022-01-01", None)}}
    assert S.MIN_SAMPLE == {"d": (750, 500), "m": (96, 60), "fo": (500, 500)}
    assert (S.BOOT_N, S.BOOT_SEED, S.CI, S.TIE_DIR, S.MIN_AVAIL) == (2000, 20261017, 0.95, -1, 2 / 3)
    assert [b[2] for b in S.BANDS] == ["過冷", "偏冷", "中性", "偏熱", "過熱"]


def test_percentile_uses_only_the_past():
    xs = [1, 2, 3, 4, 5]
    assert H.pct_rank(xs, 4, 10, 2) == 100.0              # 比過去都高
    assert H.pct_rank(xs, 1, 10, 2) is None               # 過去只有 1 筆
    assert H.pct_rank([3, 3, 3, 3], 3, 10, 2) == 50.0      # 同值算一半
    xs2 = [5, 1, 1, 1, 9]
    assert H.pct_rank(xs2, 4, 3, 2) == 100.0              # 視窗 3：只看 1,1,1，不看最前面的 5


def test_percentile_series_matches_pointwise():
    rnd = random.Random(1)
    xs = [None if rnd.random() < 0.1 else round(rnd.gauss(0, 1), 2) for _ in range(400)]
    fast = H.pct_series(xs, 60, 30)
    for i in range(len(xs)):
        a, b = fast[i], H.pct_rank(xs, i, 60, 30)
        assert (a is None and b is None) or abs(a - b) < 1e-9, i


def test_heat_orientation_and_composite_contrib():
    assert H.to_heat(80, 1) == 80 and H.to_heat(80, -1) == 20 and H.to_heat(None, 1) is None
    heats = {"A": 90, "B": 60, "C": None, "D": 30}
    inc = ["A", "B", "C"]
    assert H.need(3) == 2
    assert H.composite(heats, inc) == 75.0                 # (90＋60)/2；C 沒有值
    c = H.contrib(heats, inc)
    assert set(c) == {"A", "B"}
    assert abs(sum(v["pull"] for v in c.values()) + 50 - 75.0) < 1e-9     # 影響加起來＋50＝總分
    assert abs(sum(v["share"] for v in c.values()) - 100) < 1e-9
    assert H.composite({"A": 90, "B": None, "C": None}, inc) is None      # 3 項只有 1 項有值，不到 2/3


def test_forward_return_starts_next_day():
    px = [100, 110, 99, 121, 132]
    r, dd = H.fwd(px, 0, 2)                                # t＋1（110）到 t＋3（121）
    assert abs(r - 0.1) < 1e-9 and abs(dd - (99 / 110 - 1)) < 1e-9
    assert H.fwd(px, 2, 3) == (None, None)


def test_spearman_ci_is_deterministic_and_detects_relation():
    rnd = random.Random(7)
    x = [rnd.random() for _ in range(600)]
    y = [-v + rnd.gauss(0, 0.3) for v in x]                # 熱了之後較弱
    a = H.spearman_ci(x, y, 10, n_boot=300)
    b = H.spearman_ci(x, y, 10, n_boot=300)
    assert a == b and a[0] < 0 and a[2] < 0
    z = [rnd.random() for _ in range(600)]
    rho, lo, hi = H.spearman_ci(x, z, 10, n_boot=300)
    assert lo < 0 < hi


def test_verdict_and_selection_rules():
    assert H.verdict(-0.2, -0.3, -0.1, -0.05, 1000, 600, 750, 500) == "weak"
    assert H.verdict(-0.2, -0.3, -0.1, 0.05, 1000, 600, 750, 500) == "flip"
    assert H.verdict(0.2, 0.1, 0.3, 0.1, 1000, 600, 750, 500) == "strong"
    assert H.verdict(0.05, -0.1, 0.2, 0.1, 1000, 600, 750, 500) == "none"
    assert H.verdict(-0.2, -0.3, -0.1, -0.05, 700, 600, 750, 500) == "few"
    assert H.select({"A": -1, "B": -1, "C": 1, "D": 0}) == (-1, ["A", "B"])
    assert H.select({"A": 1, "B": -1}) == (-1, ["B"])                     # 一樣多取「熱了之後較弱」
    assert H.select({"A": 1, "B": 1, "C": -1}) == (1, ["A", "B"])
    assert H.select({"A": 0}) == (0, [])


def test_bands_cover_all_and_total_row():
    sc = [10, 30, 50, 70, 90, 95]
    r = [0.01, -0.02, 0.0, 0.03, -0.01, 0.02]
    dd = [-0.01] * 6
    out = H.bands(sc, r, dd)
    assert [b["band"] for b in out] == ["過冷", "偏冷", "中性", "偏熱", "過熱", "全部"]
    assert [b["n"] for b in out] == [1, 1, 1, 1, 2, 6]
    assert out[4]["avg"] == 0.5 and out[-1]["up"] == 50.0
