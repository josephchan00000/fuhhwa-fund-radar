"""景氣溫度頁（docs/lab_heat_plan.md）：規格鎖定＋計算核心。

規格是看任何結果之前寫定的（第三版＝四個面向，2026-10-17，規劃文件第 12.6、12.7 節）。要改就 VER＋1、
寫進規劃文件，不在舊版本上改——這支測試鎖住現行版本（VER 7：第六版的五個面向不變，加上泡沫面向；
VER 8：籌碼面向加法人 5、20 日買賣超 6 項；VER 9 拿掉、法人只當訊號，docs/lab_inst_plan.md）。"""
import random

from arm.lab import heat as H
from arm.lab import heatspec as S


def test_spec_v7_is_locked():
    assert S.VER == 9 and S.SPEC_DATE == "2026-10-20" and S.MARKET == "tw"
    # 第四版的計分規格（第五、六版沒有改分數；第七版只加泡沫面向）
    assert list(S.DIMS) == ["fund", "chip", "gliq", "tliq", "tech", "bubl"]
    assert {d: (v["fwd"], v["freq"]) for d, v in S.DIMS.items()} == {
        "fund": ((120, 250), "m"), "chip": ((10, 60), "d"), "gliq": ((60, 250), "d"), "tliq": ((60, 250), "d"),
        "tech": ((10, 60), "d"), "bubl": ((120, 250), "m")}
    assert S.ITEMS == {"fund": ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"],
                       "chip": ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"],
                       "gliq": ["G1", "G2", "G3", "G4", "G5"],
                       "tliq": ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"],
                       "tech": ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13"],
                       "bubl": ["X1", "X2", "X3", "X4", "X5", "X6", "X7"]}
    assert S.HOT == {"B1": 1, "B2": 1, "B3": 1, "B4": 1, "B5": 1, "B6": 1, "B7": 1, "B8": 1,
                     "C1": 1, "C2": 1, "C3": -1, "C4": 1, "C5": -1, "C6": -1, "C7": -1, "C8": 1,
                     "G1": -1, "G2": -1, "G3": -1, "G4": 1, "G5": 1,
                     "L1": 1, "L2": 1, "L3": 1, "L4": -1, "L5": 1, "L6": 1, "L7": 1, "L8": 1, "L9": -1, "L10": 1,
                     "T1": 1, "T2": 1, "T3": 1, "T4": 1, "T5": 1, "T6": 1, "T7": 1, "T8": -1, "T9": -1, "T10": -1,
                     "T11": 1, "T12": 1, "T13": 1, "X1": 1, "X2": 1, "X3": 1, "X4": 1, "X5": 1, "X6": 1, "X7": 1}
    assert [k for k in S.KEYS if S.FREQ_OF[k] == "m"] == ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "G5",
                                                           "L1", "L2", "L6", "L8", "L9", "L10", "X1", "X4", "X6", "X7"]
    assert S.RELEASE == {"B1": (2, 28), "B2": (2, 28), "B5": (2, 28), "B3": (1, 6), "B4": (1, 21), "B6": (1, 11),
                         "B7": (1, 10), "B8": (1, 16), "L1": (1, 27), "L2": (1, 27), "L8": (1, 27), "L9": (1, 27),
                         "L10": (1, 27), "L6": (1, 6), "G5": (1, 15), "X1": (1, 1), "X4": (1, 1), "X6": (1, 1), "X7": (1, 1)}
    assert set(S.RELEASE) == {k for k in S.KEYS if S.FREQ_OF[k] == "m"}     # 每個月資料都有公布時間差
    assert S.PCT_WIN == {"d": 750, "m": 120} and S.PCT_MIN == {"d": 375, "m": 60}
    assert S.DAILY_LAG == 1 and S.US == ("G1", "G2", "G3", "G4", "T9") and S.PROXY == {"T10": "T9"}
    assert S.DIRECT == {"T11": 6} and S.STALE == {"C8": 14, "L7": 10, "X5": 14} and S.AVAIL_DAYS == {"C8": 7}
    assert (S.MIN_AVAIL, S.CHG_DAYS, S.MIN_N) == (2 / 3, 5, {"d": 750, "m": 96})
    assert [H.need(len(v)) for v in S.ITEMS.values()] == [6, 6, 4, 7, 9, 5]  # 8 要 6、8 要 6（VER 9 回到 8 項）、5 要 4、10 要 7、13 要 9、7 要 5
    assert (S.BOOT_N, S.BOOT_SEED, S.CI) == (2000, 20261017, 0.95)
    assert S.SPLIT_REF == {"d": (("2014-01-01", "2019-12-31"), ("2020-01-01", None)),
                           "m": (("1999-01-01", "2012-12-31"), ("2013-01-01", None))}
    assert [b[2] for b in S.BANDS] == ["過冷", "偏冷", "中性", "偏熱", "過熱"]
    assert set(S.VERDICT) == {"weak", "strong", "none", "few"}
    # 關鍵價位與事件（第 13.3、13.9 節）
    assert S.MA_NS == (5, 10, 20, 60, 120, 240) and S.MA_LEVELS == (20, 60, 120, 240)
    assert (S.PIVOT_THR, S.EV_PRIOR, S.EV_CONF, S.DT_TOL, S.DT_GAP, S.HS_RATIO) == (0.05, 10, 3, 0.015, 22, 2.5)
    assert (S.EV_FWD, S.EV_MIN, S.EV_START, S.DEDUCT_N, S.LEVEL_PIVOTS) == ((10, 60), 20, 250, 5, 6)
    assert list(S.EVENTS) == ["ma20_dn", "ma20_up", "ma60_dn", "ma60_up", "ma240_dn", "ma240_up", "x_dead", "x_gold",
                              "s60_dn", "s60_up", "pv_dn", "pv_up", "dtop", "dbot", "hstop", "hsbot"]
    assert set(S.EV_VERDICT) == {"weak", "strong", "none", "few"}
    # 第五版（第 14.14 節）：只描述與驗證
    assert S.POS_WIN == {"d": (750, 2500), "m": (36, 120)} and S.POS_COVER == 0.8
    assert S.POS_ALL_MIN == {"d": 375, "m": 60} and S.POS_WIN["d"][0] == S.PCT_WIN["d"] and S.POS_WIN["m"][1] == S.PCT_WIN["m"]
    assert (S.REC_DAYS, S.REC_MONTHS, S.RANGE_YEARS, S.PP_UNITS) == ((91, 365), (3, 12), 10, ("%", "百分點"))
    assert (S.STRIP_WEEKS, S.STRIP_MID, S.STRIP_RUN_NOTE) == (52, (40, 60), 4)
    assert (S.CH_DAILY, S.CH_MAX, S.CH_RANGES, S.CH_DEFAULT_RANGE, S.CH_SHADE) == (260, 5, (1, 3, 10, None), 3, (80, 20))
    assert S.REL_H == (20, 60, 120, 250)
    assert (S.LL_H, S.LL_FOLLOW, S.WK_BLOCK_MIN) == ((5, 20, 60, 120, 250), (0.3, 2.0), 4)
    assert (S.GR_LAGS, S.GR_MAIN, S.GR_MIN, S.BH_Q) == ((1, 3, 6), 3, 96, 0.10)
    assert (S.ROLL_WEEKS, S.ROLL_STEP, S.ROLL_H, S.ROLL_MIN) == (260, 4, 60, 200)
    assert S.EVT == {"hot": (80, 20), "cold": (20, 20)} and S.EVT_FWD == (20, 60)
    assert (S.CPL_HOT, S.CPL_COLD, S.CPL_MIN_WEEKS, S.CPL_MIN_RUNS, S.CPL_BOOT, S.CPL_OVERLAP, S.CPL_DEFAULT_H) == \
        (60, 40, 26, 4, 1000, 0.7, 60)
    assert list(S.DERIV) == ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "L2", "C1", "C5", "G1", "G2"]   # 13 項
    assert S.DERIV["B1"] == {"kind": "level", "d1": "chg", "L1": 3, "L2": 3}
    assert S.DERIV["B3"] == {"kind": "pmi", "d1": "minus50", "L2": 3}
    assert all(S.DERIV[k] == {"kind": "growth", "d1": "self", "L2": 3} for k in ("B2", "B4", "B5", "B6", "L2"))
    assert all(S.DERIV[k] == {"kind": "cpi", "d1": "self", "L2": 3} for k in ("B7", "B8"))
    assert S.DERIV["C1"] == {"kind": "stock", "d1": "pct", "L1": 20, "L2": 20, "smooth": 5}
    assert S.DERIV["C5"] == {"kind": "level", "d1": "chg", "L1": 20, "L2": 20, "smooth": 5}
    assert S.DERIV["G1"] == {"kind": "rate", "d1": "self", "L2": 63} and S.DERIV["G2"] == {"kind": "rate", "d1": "self", "L2": 20}
    assert {v["kind"] for v in S.DERIV.values()} <= set(S.DERIV_WORDS) and all(len(w) == 4 for w in S.DERIV_WORDS.values())
    assert (S.DERIV_FLAT, S.DERIV_NOTE, S.DERIV_PCT_WIN, S.DERIV_PCT_MIN) == (
        "持平", {"C5": "下降＝淨空增加"}, {"d": 2500, "m": 120}, {"d": 1250, "m": 60})
    assert all(S.FREQ_OF[k] == ("m" if k[0] in "BL" else "d") for k in S.DERIV)
    # 第六版（第 15.11 節）：邊際變化的多層回歸，事前寫定
    assert (S.M6_LAG, S.M6_DELAY, S.M6_WIN, S.M6_CUM, S.M6_CTRL) == (1, (0, 3, 6, 9, 12, 15, 18, 21), 3, (1, 3, 6, 12, 18, 24), (1, 12))
    assert max(S.M6_DELAY) + S.M6_WIN == 24 == max(S.M6_CUM)                     # 最長 24 個月（使用者決定）
    assert (S.M6_VARIANTS, S.M6_MAIN_VARIANT) == (("v0", "v1", "v2"), "v0")
    assert S.M6_GROUPS == {"grow": ("B1", "B2", "B3", "B4", "B5", "B6", "L2"), "rate": ("B7", "B8", "G1", "G2"), "lev": ("C1", "C5")}
    assert sorted(k for g in S.M6_GROUPS.values() for k in g) == sorted(S.DERIV)  # 三組剛好是核心 13 項
    assert (S.M6_GROUP_MIN, S.M6_DI_MIN, S.M6_MA_MONTHS, S.M6_LEVEL_SPLIT, S.M6_INTER_AT) == \
        ({"grow": 4, "rate": 2, "lev": 1}, 7, 10, 50, (20, 50, 80))
    assert (S.M6_NW, S.M6_BLOCK_MIN, S.M6_BOOT, S.M6_SEED, S.M6_MIN_N, S.M6_STATE_MIN, S.M6_STATE_H) == \
        ((1.5, 6), 12, 2000, 20261018, 96, (24, 4), (6, 12, 24))
    assert S.M6_OOS_START == "2008-01" and S.M6_OOS_WINDOWS == ((0, 3), (3, 3), (6, 3), (9, 3), (12, 3), (0, 12), (6, 6), (0, 24))
    assert (S.M6_RIDGE_LAMBDA, S.M6_CV_FOLDS, S.M6_CW_ALPHA, S.M6_OOS_MIN_PRED) == ((0.1, 0.3, 1, 3, 10, 30, 100), 5, 0.05, 36)
    assert S.M6_RIDGE_X == ("GA_grow", "GA_rate", "LV_grow", "LV_rate", "DI", "BULL", "HIKE", "GA_grow*GA_rate",
                            "GA_grow*LV_grow", "GA_rate*LV_rate", "GA_grow*BULL", "GA_grow*HIKE")
    assert S.M6_TREE == {"depth": 2, "min_leaf": 36, "cuts": (10, 20, 30, 40, 50, 60, 70, 80, 90)}
    assert S.M6_TREE_X == ("GA_grow", "GA_rate", "LV_grow", "LV_rate", "DI", "BULL", "HIKE")
    assert (S.M6_EVENT_CONFIRM, S.M6_EVENT_PATH, S.M6_EVENT_MIN, S.M6_ALPHA, S.M6_EXT_SHIFT) == (2, 24, 20, 0.05, 1)
    assert {k: v[1] for k, v in S.M6_PRIMARY.items()} == {"H1": (6, 6), "H2": (0, 12), "H3": (0, 12), "H4": (6, 6)}
    assert (S.M6_HIKE, S.M6_EXT) == ("G1", True)
    # 第七版（docs/lab_heat_us_plan.md 第 15 節）：泡沫面向；美股規格匯入同一份
    assert S.DSHORT == {"fund": "基本面", "chip": "籌碼", "gliq": "全球資金", "tliq": "台灣資金", "tech": "技術", "bubl": "泡沫"}
    assert S.PRESCORED == ("X1", "X4", "X5") and S.PCT_WIN_ITEM == {"X2": (2500, 1250), "X3": (2500, 1250)}
    assert S.PSY == {"w0": 60, "lag": 0, "reps": 2000, "seed": 20261019, "nmax": 2100, "q": (0.5, 0.95), "map": (50, 80),
                     "cpi_lag": 1, "div_lag": 6}
    assert S.TREND == {"min": 240, "map": (50, 15)}
    L = S.LPPLS
    assert L["dt"] == (30, 650, 5) and len(range(L["dt"][1], L["dt"][0] - 1, -L["dt"][2])) == 125
    assert (len(L["m"]), len(L["w"]), len(L["tc"])) == (11, 30, 12)
    assert (L["m_ok"], L["w_ok"], L["tc_ok"], L["osc"], L["damp"], L["err"], L["map"]) == \
        ((0.1, 0.9), (2, 25), 0.2, 2.5, 1.0, 0.2, (50, 100))
    assert (S.RUNUP_DAYS, S.ACC_DAYS) == (504, 126)
    assert (S.BUB_HOT, S.BUB_DD, S.BUB_MIN_HOT, S.BUB_EPI_GAP, S.BUB_EPI_MIN, S.BUB_BLOCK, S.BUB_BOOT, S.BUB_SEED) == \
        (80, ((252, 0.20), (504, 0.40)), 12, 6, 4, 12, 2000, 20261019)
    assert set(S.BUB_VERDICT) == {"crash", "calm", "none", "few"} and S.BUB_EXT == ("X1", "X4") and S.VAL_START == {}
    assert [r[0] for r in S.REF] == ["Q1"]


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
