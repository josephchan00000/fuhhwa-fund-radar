"""景氣溫度・美股版（docs/lab_heat_us_plan.md 第 15 節）：規格鎖定。

規格是看任何美股結果之前寫定的（VER 1，2026-10-18）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import heat as H
from arm.lab import heatspec as S
from arm.lab import heatspec_us as U


def test_us_spec_v1_is_locked():
    assert U.VER == 1 and U.SPEC_DATE == "2026-10-18" and U.MARKET == "us"
    assert list(U.INDICES) == list(U.INDEX_ORDER) == ["spx", "ixic", "ndx", "sox"]
    assert {k: v["sym"] for k, v in U.INDICES.items()} == {"spx": "^GSPC", "ixic": "^IXIC", "ndx": "^NDX", "sox": "^SOX"}
    assert U.IVOL == {"spx": "vix", "ixic": "vxn", "ndx": "vxn", "sox": "vix"}
    assert U.VAL_START == {"spx": "1950-01-01", "ixic": None, "ndx": None, "sox": None}
    assert list(U.DIMS) == ["fund", "sent", "liq", "tech", "bubl"]
    assert {d: (v["fwd"], v["freq"]) for d, v in U.DIMS.items()} == {
        "fund": ((120, 250), "m"), "sent": ((10, 60), "d"), "liq": ((60, 250), "d"), "tech": ((10, 60), "d"),
        "bubl": ((120, 250), "m")}
    hot = {k: h for k, _, _, _, h, _, _ in U.IND}
    assert hot == {"F1": 1, "F2": 1, "F3": 1, "F4": -1, "F5": -1, "F6": 1, "F7": 1, "F8": 1, "F9": 1, "F10": 1, "F11": 1,
                   "S1": 1, "S2": 1, "S3": -1, "S4": -1, "S5": 1,
                   "R1": -1, "R2": -1, "R3": -1, "R4": 1, "R5": 1, "R6": -1, "R7": 1, "R8": 1, "R9": -1, "R10": 1,
                   "T1": 1, "T2": 1, "T3": 1, "T4": 1, "T8": -1, "T9": -1, "T11": 1, "T12": 1, "T13": 1, "T14": 1,
                   "X1": 1, "X2": 1, "X3": 1, "X4": 1, "X5": 1, "X6": 1, "X7": -1, "X8": 1, "X9": 1, "X10": 1, "X11": 1}
    freq = {k: f for k, _, _, _, _, f, _ in U.IND}
    assert [k for k in freq if freq[k] == "m"] == ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11",
                                                   "S5", "R6", "R7", "R10", "X1", "X4", "X6", "X7", "X8", "X9", "X10"]
    assert set(U.RELEASE) == {k for k in freq if freq[k] == "m"}             # 每個月資料都有公布時間差
    assert U.RELEASE == {"F1": (0, 22), "F2": (1, 1), "F9": (1, 1), "F3": (1, 15), "F4": (1, 15), "F5": (1, 8),
                         "F6": (1, 16), "F7": (1, 16), "F8": (6, 1), "F10": (2, 10), "F11": (1, 11), "S5": (3, 15),
                         "R6": (1, 20), "R7": (1, 28), "R10": (1, 15), "X1": (1, 1), "X4": (1, 1), "X6": (1, 1),
                         "X7": (1, 1), "X8": (1, 1), "X9": (1, 1), "X10": (1, 1)}
    assert U.ONLY == {"F10": ("sox",), "F11": ("sox",), "T14": ("ixic", "ndx", "sox"), "X10": ("spx",),
                      "X11": ("ixic", "ndx", "sox")}
    assert U.DIRECT == {"T11": 6} and U.PRESCORED == ("X1", "X4", "X5", "X10")
    assert U.PCT_WIN_ITEM == {"X2": (2500, 1250), "X3": (2500, 1250), "X11": (2500, 1250), "S5": (40, 20)}
    assert U.US == ("R1",) and U.PROXY == {}
    assert U.STALE == {"S1": 14, "S2": 14, "S3": 14, "R8": 14, "X5": 14} and U.AVAIL_DAYS == {"S1": 4, "S2": 4, "S3": 4, "R8": 2}
    assert U.SPLIT_REF == {"d": ((None, "1999-12-31"), ("2000-01-01", None)), "m": ((None, "1999-12-31"), ("2000-01-01", None))}
    assert [r[0] for r in U.REF] == ["Q1", "Q2", "Q3"]
    assert U.DSHORT == {"fund": "基本面", "sent": "情緒籌碼", "liq": "資金", "tech": "技術", "bubl": "泡沫"}
    # 第六版（美股核心 14 項）
    assert list(U.DERIV) == ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "R7", "S1", "S2", "R1", "R2"]
    assert U.DERIV["F1"] == {"kind": "pmi", "d1": "self", "L2": 3}
    assert all(U.DERIV[k] == {"kind": "level", "d1": "chg", "L1": 3, "L2": 3} for k in ("F3", "F9"))
    assert all(U.DERIV[k] == {"kind": "level", "d1": "chg", "L1": 4, "L2": 4} for k in ("S1", "S2"))
    assert all(U.DERIV[k] == {"kind": "growth", "d1": "self", "L2": 3} for k in ("F2", "F8", "R7"))
    assert all(U.DERIV[k] == {"kind": "cpi", "d1": "self", "L2": 3} for k in ("F6", "F7"))
    assert U.DERIV["F4"] == {"kind": "stock", "d1": "self", "L2": 3} and U.DERIV["F5"] == {"kind": "level", "d1": "self", "L2": 3}
    assert U.DERIV["R1"] == {"kind": "rate", "d1": "self", "L2": 63} and U.DERIV["R2"] == {"kind": "rate", "d1": "self", "L2": 20}
    assert {v["kind"] for v in U.DERIV.values()} <= set(U.DERIV_WORDS)
    assert U.M6_GROUPS == {"grow": ("F1", "F2", "F3", "F4", "F5", "F8", "F9", "R7"), "rate": ("F6", "F7", "R1", "R2"),
                           "lev": ("S1", "S2")}
    assert sorted(k for g in U.M6_GROUPS.values() for k in g) == sorted(U.DERIV)   # 三組剛好是核心 14 項
    assert (U.M6_GROUP_MIN, U.M6_DI_MIN, U.M6_OOS_START, U.M6_HIKE, U.M6_EXT, U.M6_MAIN_INDEX) == \
        ({"grow": 4, "rate": 2, "lev": 1}, 7, "1990-01", "R1", False, "spx")


def test_us_shares_default_bound_constants_with_taiwan():
    """當成函式預設參數的常數（heat.fwd、spearman_ci、heatrel、heattech.mas、heatreg 的模型設定）兩邊一定要一樣，
    否則換規格後預設參數還是台股的值。直接從 heatspec 匯入，這裡守住。"""
    for nm in ("DAILY_LAG", "BOOT_N", "BOOT_SEED", "CI", "MA_NS", "M6_VARIANTS", "M6_MAIN_VARIANT", "M6_RIDGE_LAMBDA",
               "M6_CV_FOLDS", "M6_TREE", "M6_ALPHA", "PCT_WIN", "PCT_MIN", "MIN_AVAIL", "BANDS", "PSY", "TREND", "LPPLS",
               "BUB_DD", "BUB_HOT", "RUNUP_DAYS", "ACC_DAYS"):
        assert getattr(U, nm) is getattr(S, nm), nm


def test_spec_for_each_index():
    want = {"spx": {"fund": 9, "sent": 5, "liq": 10, "tech": 9, "bubl": 10},
            "ixic": {"fund": 9, "sent": 5, "liq": 10, "tech": 10, "bubl": 10},
            "ndx": {"fund": 9, "sent": 5, "liq": 10, "tech": 10, "bubl": 10},
            "sox": {"fund": 11, "sent": 5, "liq": 10, "tech": 10, "bubl": 10}}
    for idx, n in want.items():
        sp = U.spec_for(idx)
        assert {d: len(v) for d, v in sp["ITEMS"].items()} == n
        assert sp["INDEX"] == idx and sp["KEYS"] == U.keys_for(idx)
        assert set(sp["HOT"]) == set(sp["KEYS"]) == set(sp["DIM_OF"]) == set(sp["FREQ_OF"])
        assert set(sp["RELEASE"]) == {k for k in sp["KEYS"] if sp["FREQ_OF"][k] == "m"}
        assert set(sp["PRESCORED"]) <= set(sp["KEYS"]) and set(sp["PCT_WIN_ITEM"]) <= set(sp["KEYS"])
    assert "X10" in U.keys_for("spx") and "X11" not in U.keys_for("spx") and "T14" not in U.keys_for("spx")
    assert "X11" in U.keys_for("sox") and "F10" in U.keys_for("sox") and "F10" not in U.keys_for("ndx")
    assert [H.need(n) for n in (9, 5, 10, 11)] == [6, 4, 7, 8]


def test_use_switches_and_restores():
    tw = (S.VER, S.MARKET, list(S.KEYS), dict(S.ITEMS), S.US, S.DSHORT)
    with S.use(U.spec_for("ndx")):
        assert (S.VER, S.MARKET, S.INDEX) == (1, "us", "ndx")
        assert S.ITEMS["tech"][-1] == "T14" and S.US == ("R1",) and S.band(85) == "過熱"
    assert (S.VER, S.MARKET, list(S.KEYS), dict(S.ITEMS), S.US, S.DSHORT) == tw
    assert not hasattr(S, "INDEX") and not hasattr(S, "INDICES")      # 美股才有的名稱離開時拿掉
    try:
        with S.use(U.spec_for("spx")):
            raise RuntimeError("x")
    except RuntimeError:
        pass
    assert S.VER == 9 and S.MARKET == "tw"                             # 中途出錯也換回來
