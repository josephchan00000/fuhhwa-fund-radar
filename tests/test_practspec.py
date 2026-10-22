"""實戰模擬的規格（docs/lab_practical_plan.md 第 11 節）：規格鎖定。

規格是在算任何結果之前寫定的（VER 1，2026-10-22）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import hotdd
from arm.lab import practspec as X
from arm.lab import sigspec
from arm.lab import thermocal
from arm.lab import xstrat
from arm.lab import xstratspec


def test_practice_spec_v1_is_locked():
    assert X.VER == 1 and X.SPEC_DATE == "2026-10-22"
    assert X.MARKETS == sigspec.MARKETS == xstratspec.MARKETS == ("tw", "spx", "ixic", "ndx", "sox")
    assert set(X.NAMES) == set(X.MARKETS)
    assert (X.LAG, X.FULL, X.HALF) == (1, 1.0, 0.5)
    assert X.THERMO_RULES == {
        "A1": {"name": "短線警示多 → 降到一半", "side": "w", "hz": ("short",), "need": 1, "on": 0.5, "off": 1.0},
        "A2": {"name": "中線警示多 → 降到一半", "side": "w", "hz": ("mid",), "need": 1, "on": 0.5, "off": 1.0},
        "A3": {"name": "長線警示多 → 降到一半", "side": "w", "hz": ("long",), "need": 1, "on": 0.5, "off": 1.0},
        "A4": {"name": "三支溫度計兩支以上警示多 → 降到一半", "side": "w", "hz": ("short", "mid", "long"), "need": 2,
               "on": 0.5, "off": 1.0},
        "B1": {"name": "短線偏多多 → 加碼（其他時候一半）", "side": "u", "hz": ("short",), "need": 1, "on": 1.0, "off": 0.5},
        "D1": {"name": "偏多全部照做（有偏多就全部，沒有就空手）", "side": "u", "hz": ("short",), "any": True, "on": 1.0, "off": 0.0},
    }
    assert X.A4_NEED == 2 == X.THERMO_RULES["A4"]["need"]
    assert X.STRAT_RULES == {"M1": {"name": "總經策略 ★ 照做", "tiers": ("good",)},
                             "M2": {"name": "總經策略 ★＋● 照做（策略頁列出來的）", "tiers": ("good", "ref")}}
    assert X.RULES == ("A1", "A2", "A3", "A4", "B1", "D1", "M1", "M2")
    assert X.XS_WARM_Y == 10
    assert (X.RECENT_YEARS, X.BEAR, X.BOOT_BLOCK, X.BOOT_DRAWS, X.BOOT_SEED) == (10, 0.20, 250, 1000, 20261023)
    assert X.VERDICTS == ("better", "same", "worse") and set(X.VERDICT_NAMES) == set(X.VERDICTS)
    assert (X.PAGE_RULES, X.PAGE_MIN_BETTER, X.PAGE_MAX_WORSE) == (("A1", "B1", "M2"), 3, 0)


def test_practice_spec_refers_to_existing_definitions():
    """引用的其他規格與函式都還在：票數與位置沿用 thermocal（VER 23），判定沿用總經策略，大跌段用 hotdd.declines。"""
    assert sigspec.CAL_VER >= 23 and tuple(sigspec.THERMO_H) == ("short", "mid", "long")
    assert (sigspec.CAL_RANK_W, sigspec.CAL_RANK_MIN, sigspec.CAL_TERC) == (520, 260, (1 / 3, 2 / 3))
    for f in (thermocal.vote, thermocal.stats_before, thermocal.active, thermocal.rank, thermocal.group, thermocal.first_year):
        assert callable(f)
    assert thermocal.group(2 / 3) == "hi" and thermocal.group(0.5) == "mid"
    assert callable(xstrat.has_data) and callable(xstrat.strategy) and callable(xstrat.data)
    assert xstratspec.TIERS[:2] == ("good", "ref") and xstratspec.RECENT_YEARS == X.RECENT_YEARS
    assert xstratspec.COST["tw"] == 0.001 and xstratspec.cost("tw", "rsi2") == xstratspec.COST_FUT
    assert callable(hotdd.declines)
