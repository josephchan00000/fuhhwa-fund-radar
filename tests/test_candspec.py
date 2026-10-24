"""新策略候選的框架規格（arm/lab/candspec.py；docs/lab_ia_v5_plan.md 第 24 節）：規格鎖定。

VER 1、VER 2（2026-10-24，打亂之後的價格）都在任何一條候選算出來之前寫定。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import candspec as S
from arm.lab import xstratspec as X

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


def test_candspec_v2_is_locked():
    assert S.VER == 2 and S.SPEC_DATE == "2026-10-24"
    assert S.ID_RE == r"^c\d{3}$"
    assert S.ENGINES == {"index": ("trade", "dip", "alloc"), "tw_stock": ("per",), "us_stock": ("book",)}
    assert S.MARKETS == {"index": ("tw", "spx", "ixic", "ndx", "sox"), "tw_stock": ("tw",), "us_stock": ("us",)}
    assert S.FIELDS == ("id", "found", "name", "mk", "engine", "kind", "how", "src", "why")
    assert S.PROGRAM == ("p", "grid", "sha")
    assert S.NEED_BY == {"dip": ("H",), "per": ("b", "pick"), "book": ("ex",)}
    assert S.TW_BUCKETS == ("L", "M") and S.PICK_KEYS == ("top", "nmin", "umin", "asc", "event")
    assert S.US_EX_KEYS == ("slots", "hold", "ma", "trail", "stop")
    assert (S.GRID_MAX, S.NAME_MAX) == (9, 24)
    assert S.GRID_OK == X.GRID_OK == 2 / 3                   # 和總經策略同一個參數鄰近門檻
    assert (S.TW_N_MIN, S.US_Y0, S.US_EVAL, S.US_YEARS_MIN) == (10, 2010, 2014, 5)
    assert S.TIERS == X.TIERS == ("good", "ref", "none", "few")
    assert S.VERDICT == {"good": "過關", "ref": "部分過關", "none": "沒過", "few": "次數不夠",
                         "need": "需要資料", "err": "沒算出來", "peek": "用到未來的資料"}
    assert S.CUTS == (0.70, 0.85, 0.97) and S.REV_DAY == 10
    assert (S.PEEK_SIGMA, S.PEEK_SEED) == (0.08, 20261024)
    assert S.PLAN_OF == {"tw": ("tw",), "spx": ("spx",), "ndx": ("ndx",), "us": ("spx", "ndx")}
    assert (S.STAR_N_DEFAULT, S.PLAN_MDD_MORE) == (3, 0.10)
    assert S.DECISIONS == {"trial": "試用", "adopt": "納入", "reject": "不納入"}
    assert S.DEC_STATUS == {"trial": "obs", "adopt": "obs", "reject": "out"}
    assert S.TRIAL_CHECK == 63
    assert (S.MAX_NEW, S.MAX_OPEN, S.WEEKLY_HM, S.ROUTINE_HM) == (2, 10, "19:00", "20:00")
    assert (S.SPEC_FILE, S.PROG_DIR, S.RES_FILE, S.LIVE_FILE) == (
        "config/strategy_candidates.json", "arm/lab/cands", "cands_research.json", "cands_live.json")


def test_spec_markets_and_plans_are_consistent():
    for eng, kinds in S.ENGINES.items():
        assert eng in S.MARKETS and eng in S.ENGINE_NAMES
        for k in kinds:
            assert k in X.KINDS or k in S.NEED_BY or k == "per"
    for mks in S.MARKETS.values():
        for m in mks:
            assert m in S.MK_NAMES
    for m, plans in S.PLAN_OF.items():
        assert m in S.MK_NAMES and set(plans) <= {"tw", "spx", "ndx"}       # 有交易計畫的市場（corespec.MARKETS）
    assert set(S.DEC_STATUS) == set(S.DECISIONS)


def test_spec_text_has_no_banned_words():
    import inspect
    txt = inspect.getsource(S)
    for w in BANNED:
        assert w not in txt, w
