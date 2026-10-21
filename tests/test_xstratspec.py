"""大神策略的規格（docs/lab_expert_plan.md 第 4.1、6 節；arm/lab/xstratspec.py）：規格鎖定。

VER 1（2026-10-20）在算正式成績之前寫定；VER 2（2026-10-21，台股短線改台指期＋當天收盤）也在重算成績之前寫定；
VER 3（2026-10-21，第二段落底型）在算落底型的正式成績之前寫定；VER 4（2026-10-21，第三段新資料）在讀回補資料之前寫定；
VER 5（2026-10-22，落底型加看「賺多少」）在重算判定之前寫定（記憶體試算看過的數字寫在規劃第 11 節）。
要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from datetime import date

from arm.lab import sigspec as SS
from arm.lab import xstratspec as X

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


def test_xstrat_spec_v4_is_locked():
    assert X.VER == 5 and X.SPEC_DATE == "2026-10-22" and X.SPEC_DATE_V1 == "2026-10-20"
    assert X.MARKETS == SS.MARKETS and X.NAMES == SS.NAMES
    assert X.EVAL_START == {"tw": "1991-07-01", "spx": "1990-01-01", "ixic": "1990-01-01", "ndx": "1990-01-01",
                            "sox": "1995-10-01"}
    assert X.WARMUP_MONTHS == 17 and X.RECENT_YEARS == SS.RECENT_YEARS == 10
    assert X.COST == {"tw": 0.001, "spx": 0.00025, "ixic": 0.00025, "ndx": 0.00025, "sox": 0.00025}
    assert (X.LAG, X.LAG_REF) == (1, 0)
    assert X.GROUP_ORDER == ("short", "bottom", "season", "risk") and set(X.GROUPS) == set(X.GROUP_ORDER)
    assert X.KINDS == {"trade": "交易型", "dip": "落底型", "alloc": "進出型"}
    assert X.KEYS == ("rsi2", "vixs", "tom", "coppock", "vix40", "zweig", "ftd", "dev60", "mmr", "mflush", "lowry",
                      "hal", "faber", "ma200", "mom12")
    assert (X.TR_N_MIN, X.TR_N10, X.TR_WIN, X.TR_EDGE) == (30, 10, 0.60, 0.05)
    assert (X.AL_MDD, X.AL_YEARS_MIN, X.GRID_OK) == (2 / 3, 5, 2 / 3)
    assert X.TIERS == ("good", "ref", "none", "few") and set(X.TIER_NAMES) == set(X.TIER_MARK) == set(X.TIERS)
    assert X.TIER_NAMES == SS.STRAT_TIER_NAMES                         # 和個股策略同一套說法
    assert (X.LUCK_DRAWS, X.LUCK_SEED, X.LUCK_SHIFT) == (400, 20261020, (0.15, 0.85))
    assert X.BOARD_UP == ("buy", "hold", "sell", "turn_in", "near") and X.BOARD_WARN == ("out", "turn_out")
    assert set(X.STATE_NAMES) == {"buy", "hold", "sell", "wait", "near", "in", "out", "turn_in", "turn_out"}
    assert X.NEAR == 0.015


def test_v2_taiwan_short_term_uses_futures_and_same_day_close():
    """VER 2（使用者選「台指期＋收盤前下單」）：只改台股 RSI(2)、月底月初；美股與台股進出型照 VER 1。"""
    assert X.COST_FUT == 0.00005
    assert X.FUT == (("tw", "rsi2"), ("tw", "tom")) and X.SAME_DAY == (("tw", "rsi2"),)
    for s in X.STRATS:
        for mk in s["mk"]:
            fut = (mk, s["k"]) in X.FUT
            assert X.cost(mk, s["k"]) == (X.COST_FUT if fut else X.COST[mk])
            same = (mk, s["k"]) in X.SAME_DAY
            assert X.lag(mk, s["k"]) == (0 if same else X.LAG)
            assert X.ref_lag(mk, s["k"]) == (X.LAG if same else X.LAG_REF)
            assert X.lag(mk, s["k"]) != X.ref_lag(mk, s["k"])          # 參考列一定是另一種時點


def test_strategy_params_are_the_original_authors():
    P = {s["k"]: s["p"] for s in X.STRATS}
    assert P["rsi2"] == {"ma": 200, "rsi_n": 2, "rsi_max": 10, "exit_ma": 5}                 # Connors
    assert P["vixs"] == {"ma": 200, "vix_ma": 10, "stretch": 0.05, "days": 3, "exit_rsi": 65}
    assert P["tom"] == {"before": 1, "after": 3}                                             # Lakonishok & Smidt
    assert P["hal"] == {"start": 11, "months": 6}                                            # Bouman & Jacobsen
    assert P["faber"] == {"n": 10} and P["ma200"] == {"n": 200} and P["mom12"] == {"n": 12}
    G = {s["k"]: s["grid"] for s in X.STRATS}
    assert G["rsi2"] == {"rsi_max": (5, 10, 15, 20), "exit_ma": (3, 5, 10)}
    assert G["vixs"] == {"stretch": (0.03, 0.05, 0.10), "exit_rsi": (55, 65, 75)}
    assert G["tom"] == {"before": (0, 1, 2), "after": (2, 3, 4)}
    assert G["hal"] == {"start": (10, 11, 12)} and G["faber"] == {"n": (8, 10, 12)}
    assert G["ma200"] == {"n": (150, 200, 250)} and G["mom12"] == {"n": (9, 12, 15)}
    for s in X.STRATS:                                   # 參數鄰近一定包含主參數
        for k, vs in s["grid"].items():
            assert s["p"][k] in vs
        assert s["grp"] in X.GROUPS and s["kind"] in X.KINDS
        assert set(s["mk"]) <= set(X.MARKETS) and s["name"] and s["who"] and s["src"] and s["logic"]
    assert {s["k"] for s in X.STRATS if s["kind"] == "trade"} == {"rsi2", "vixs", "tom"}
    assert X.BY_KEY["vixs"]["mk"] == ("spx", "ixic", "ndx", "sox")                          # VIX 衝刺只有美股
    only = {"vixs": X.US, "ftd": ("tw", "spx", "ixic", "ndx"), "dev60": ("tw",), "mmr": ("tw",), "mflush": ("tw",),
            "lowry": X.US}
    assert all(X.BY_KEY[k]["mk"] == only.get(k, X.MARKETS) for k in X.KEYS)
    # VER 3 落底型：原作者或常見說法的參數、抱的天數
    assert P["coppock"] == {"r1": 14, "r2": 11, "wma": 10} and X.BY_KEY["coppock"]["H"] == 250       # Coppock（月線）
    assert P["vix40"] == {"level": 40, "reset": 60} and X.BY_KEY["vix40"]["H"] == 60
    assert P["zweig"] == {"ema": 10, "lo": 0.40, "hi": 0.615, "days": 10} and X.BY_KEY["zweig"]["H"] == 120   # Zweig
    assert P["ftd"] == {"corr": 0.10, "up": 0.0125, "day": 4} and X.BY_KEY["ftd"]["H"] == 60         # O'Neil
    assert P["dev60"] == {"ma": 60, "th": -0.15} and X.BY_KEY["dev60"]["H"] == 20
    assert G["coppock"] == {"wma": (8, 10, 12)} and G["vix40"] == {"level": (35, 40, 45)}
    assert G["zweig"] == {"lo": (0.38, 0.40, 0.42), "hi": (0.60, 0.615, 0.63)}
    assert G["ftd"] == {"corr": (0.08, 0.10, 0.12), "up": (0.01, 0.0125, 0.017)} and G["dev60"] == {"th": (-0.12, -0.15, -0.18)}
    # VER 4 第三段：融資維持率、融資去化、Lowry 90% 日；Zweig 擴到美股
    assert P["mmr"] == {"level": 140, "reset": 60} and X.BY_KEY["mmr"]["H"] == 250 and G["mmr"] == {"level": (130, 140, 150)}
    assert P["mflush"] == {"dd": 0.10, "k": 1.0, "win": 120} and X.BY_KEY["mflush"]["H"] == 60
    assert G["mflush"] == {"dd": (0.08, 0.10, 0.12)}
    assert P["lowry"] == {"th": 0.90, "th2": 0.80, "win": 5} and X.BY_KEY["lowry"]["H"] == 120
    assert G["lowry"] == {"th": (0.85, 0.90, 0.95), "win": (3, 5, 10)}
    assert X.BY_KEY["zweig"]["mk"] == X.MARKETS
    assert {s["k"] for s in X.STRATS if s["kind"] == "dip"} == {"coppock", "vix40", "zweig", "ftd", "dev60", "mmr", "mflush",
                                                                "lowry"}
    assert all(s["grp"] == "bottom" for s in X.STRATS if s["kind"] == "dip")
    assert (X.DIP_N_MIN, X.DIP_N10, X.DIP_WIN, X.DIP_EDGE) == (5, 5, 0.60, 0.10)
    assert (X.DIP_MED_X, X.DIP_MED_ADD) == (1.5, 0.03)                    # VER 5：賺得比較多也算過關
    assert X.DIP_HS == (20, 60, 120, 250) and (X.BREADTH_MIN, X.FTD_HIGH, X.FTD_RESET) == (100, 252, 0.999)


def test_no_banned_words_in_strategy_text():
    for s in X.STRATS:
        for f in ("name", "logic", "src", "who", "pnote"):
            assert not any(w in s.get(f, "") for w in BANNED), (s["k"], f)
    for v in list(X.STATE_NAMES.values()) + list(X.TIER_NAMES.values()) + list(X.GROUPS.values()):
        assert not any(w in v for w in BANNED)


def test_eval_start_leaves_warmup_in_real_data():
    """評估起點之前至少 WARMUP_MONTHS 個月的資料（最長的參數鄰近是 15 個月動能、250 日均線；月底決定、隔天才買賣，再多 2 個月）。"""
    from arm.lab import heatbubble as BB
    from arm.lab import heatdata as HD
    first = {"tw": min(d for d, v in BB.taiex_daily().items() if v)}
    for mk in X.MARKETS[1:]:
        first[mk] = min(d for d, v in HD.load(f"us_px_{mk}").items() if v)
    for mk, d0 in first.items():
        a, b = date.fromisoformat(d0), date.fromisoformat(X.EVAL_START[mk])
        assert (b.year - a.year) * 12 + (b.month - a.month) >= X.WARMUP_MONTHS, mk
    vix0 = min(d for d, v in HD.load("vix").items() if v)
    assert vix0 <= "1990-01-02" and all(X.EVAL_START[mk] >= "1990-01-01" for mk in X.BY_KEY["vixs"]["mk"])
