"""景氣溫度頁（docs/lab_heat_plan.md）：規格鎖定＋計算核心。

規格是看任何結果之前寫定的（第三版＝四個面向，2026-10-17，規劃文件第 12.6、12.7 節）。要改就 VER＋1、
寫進規劃文件，不在舊版本上改——這支測試鎖住 VER 3 的內容。"""
import random

from arm.lab import heat as H
from arm.lab import heatspec as S


def test_spec_v3_is_locked():
    assert S.VER == 3 and S.SPEC_DATE == "2026-10-17"
    assert list(S.DIMS) == ["fund", "chip", "liq", "tech"]
    assert {d: (v["fwd"], v["freq"]) for d, v in S.DIMS.items()} == {
        "fund": ((120, 250), "m"), "chip": ((10, 60), "d"), "liq": ((60, 250), "d"), "tech": ((10, 60), "d")}
    assert S.ITEMS == {"fund": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"],
                       "chip": ["C1", "C2", "C3", "C4", "C5", "C6", "C7"],
                       "liq": ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"],
                       "tech": ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]}
    assert S.HOT == {"B1": 1, "B2": 1, "B3": 1, "B4": 1, "B5": 1, "B6": 1, "B7": 1, "B8": 1,
                     "C1": 1, "C2": 1, "C3": -1, "C4": 1, "C5": -1, "C6": -1, "C7": -1,
                     "L1": 1, "L2": 1, "L3": 1, "L4": -1, "L5": 1, "L6": -1, "L7": -1, "L8": 1,
                     "T1": 1, "T2": 1, "T3": 1, "T4": 1, "T5": 1, "T6": 1, "T7": 1, "T8": -1, "T9": -1, "T10": -1}
    assert [k for k in S.KEYS if S.FREQ_OF[k] == "m"] == ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "L1", "L2", "L6"]
    assert S.RELEASE == {"B1": (2, 28), "B2": (2, 28), "B5": (2, 28), "B3": (1, 6), "B4": (1, 21), "B6": (1, 11),
                         "B7": (1, 10), "B8": (1, 16), "L1": (1, 27), "L2": (1, 27), "L6": (1, 1)}
    assert set(S.RELEASE) == {k for k in S.KEYS if S.FREQ_OF[k] == "m"}     # 每個月資料都有公布時間差
    assert S.PCT_WIN == {"d": 750, "m": 120} and S.PCT_MIN == {"d": 375, "m": 60}
    assert S.DAILY_LAG == 1 and S.US == ("L7", "L8", "T9") and S.PROXY == {"T10": "T9"}
    assert (S.MIN_AVAIL, S.CHG_DAYS, S.MIN_N) == (2 / 3, 5, {"d": 750, "m": 96})
    assert [H.need(len(v)) for v in S.ITEMS.values()] == [6, 5, 6, 7]     # 基本面 8 要 6、籌碼 7 要 5、資金 8 要 6、技術 10 要 7
    assert (S.BOOT_N, S.BOOT_SEED, S.CI) == (2000, 20261017, 0.95)
    assert S.SPLIT_REF == {"d": (("2014-01-01", "2019-12-31"), ("2020-01-01", None)),
                           "m": (("1999-01-01", "2012-12-31"), ("2013-01-01", None))}
    assert [b[2] for b in S.BANDS] == ["過冷", "偏冷", "中性", "偏熱", "過熱"]
    assert set(S.VERDICT) == {"weak", "strong", "none", "few"}


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


def test_verdict_needs_full_ci_and_both_halves():
    assert H.verdict(-0.2, -0.3, -0.1, -0.1, -0.05, 1000, 750) == "weak"
    assert H.verdict(-0.2, -0.3, -0.1, -0.1, 0.05, 1000, 750) == "none"          # 後一半方向相反
    assert H.verdict(0.2, 0.1, 0.3, 0.2, 0.1, 1000, 750) == "strong"
    assert H.verdict(0.05, -0.1, 0.2, 0.1, 0.1, 1000, 750) == "none"             # 信賴區間含 0
    assert H.verdict(-0.2, -0.3, -0.1, -0.1, -0.05, 700, 750) == "few"
    assert H.verdict(-0.2, None, None, -0.1, -0.05, 1000, 750) == "few"
    assert abs(H.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-12 and H.spearman([1, 2], [1, 2]) is None


def test_rsi_wilder():
    px = [10, 11, 12, 11, 13, 13]
    r = H.rsi(px, 3)
    assert r[:3] == [None, None, None]
    assert abs(r[3] - 100 * 2 / 3) < 1e-9                 # 漲 1、1，跌 1 → 平均漲 2/3、跌 1/3
    ag, al = (2 / 3 * 2 + 2) / 3, (1 / 3 * 2 + 0) / 3      # 之後「前值 × 2＋今天」÷ 3
    assert abs(r[4] - (100 - 100 / (1 + ag / al))) < 1e-9
    assert H.rsi([1, 2, 3, 4, 5], 3)[3] == 100.0          # 沒有跌 → 100
    assert H.rsi([1, None, 3, 4, 5, 6], 2)[2] is None      # 缺價格那天 None


def test_bands_cover_all_and_total_row():
    sc = [10, 30, 50, 70, 90, 95]
    r = [0.01, -0.02, 0.0, 0.03, -0.01, 0.02]
    dd = [-0.01] * 6
    out = H.bands(sc, r, dd)
    assert [b["band"] for b in out] == ["過冷", "偏冷", "中性", "偏熱", "過熱", "全部"]
    assert [b["n"] for b in out] == [1, 1, 1, 1, 2, 6]
    assert out[4]["avg"] == 0.5 and out[-1]["up"] == 50.0
