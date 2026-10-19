"""產業泡沫規格（docs/lab_risk_plan.md 第 12 節）：規格鎖定。

規格是看任何產業結果之前寫定的（VER 1，2026-10-19）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。
VER 2（同日，docs/lab_crash_plan.md 第 21.2 節）只加「已下市公司的產業別」，VER 1 的數字都不動。
VER 3（同日，第 21.5 節）只加「台股細分族群」（櫃買產業鏈平台、現在的成員往回算、只描述），前面的都不動。"""
from arm.lab import bubindspec as I
from arm.lab import bubspec as B


def test_industry_spec_v3_is_locked():
    assert I.VER == 3 and I.SPEC_DATE == "2026-10-19"
    assert (I.IND_HIST_START, I.IND_HIST_FILE) == (2013, "indsnap.json")
    assert I.IND_HIST_TYPES[0] == "01" and I.IND_HIST_TYPES[-1] == "39" and len(I.IND_HIST_TYPES) == 39
    assert I.IND_HIST_AGG == ("07", "13")
    assert I.GROUPS == ("tw", "us", "ff", "tg")
    assert (I.TW_CAP_MIN, I.TW_MIN_N, I.TW_START, I.TW_SKIP) == (40e8, 3, "2013-01-01", ("其他",))
    assert sorted(I.US_ETF) == ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
    assert (I.US_MKT, I.US_START) == ("SPY", "1998-12-01")
    assert sorted(I.GICS_ETF.values()) == sorted(I.US_ETF)
    assert len(I.FF49) == 49 and len(set(I.FF49)) == 49 and set(I.FF_NAMES) == set(I.FF49)
    assert (I.FF_SKIP, I.FF_MISSING) == (("Other",), -99.99)
    assert I.FF_FILES == ("49_Industry_Portfolios_CSV.zip", "49_Industry_Portfolios_Wout_Div_CSV.zip")
    assert (I.NET_PP, I.RUN2_MONTHS) == (50.0, 24)
    assert (I.E_SKIP, I.E_SUM) == (("金融保險",), 12)
    assert (I.G1_BACK, I.R_BACK, I.REV_REL) == (6, 3, (1, 10))
    assert I.F_MIN_MONTHS == {"tw": 120, "ff": 240}
    assert I.DD_MONTHS == ((12, 0.20), (24, 0.40))
    assert I.TESTS == {"ff": ("P1", "P2", "P3", "F", "PX", "P2F"), "tw": ("P1", "P2", "E", "G", "F", "PX", "L3"),
                       "us": ("P1", "P2", "P3", "PX"), "tg": ("P1", "P2", "E", "G", "F", "PX", "L3")}
    assert I.JUDGE == ("ff",) and I.PRIMARY == ("ff", "P2", 24)


def test_finer_groups_v3_are_locked():
    assert (I.TG_FILE, I.TG_REFRESH_DAYS, I.TG_MIN_MEMBERS) == ("icchain.json", 30, 5)
    assert [k for k, _, _ in I.TG_GROUPS] == ["pcb", "pcbm", "passive", "conn", "thermal", "server", "power", "chassis", "ipc",
                                              "optical", "netcom", "icd", "foundry", "osat", "semieq", "memory", "ai"]
    G = {k: src for k, _, src in I.TG_GROUPS}
    assert G["optical"] == (("I000", "光通訊設備(如光纖電纜、光傳輸設備)", None), ("D000", "IC設計", "光通訊IC"))
    assert G["thermal"] == (("F000", "散熱片、風扇馬達、散熱模組", None), ("5400", "冷卻設備", None))
    assert G["memory"] == (("D000", "IC設計", "記憶體IC"), ("D000", "IC設計", "記憶體控制IC"), ("F000", "記憶體", None))
    assert G["passive"] == (("J000", "*", None),) and G["ai"] == (("5300", "*", None),)
    assert len(G["pcbm"]) == 6 and all(ic == "L000" for ic, _, _ in G["pcbm"])
    assert I.TG_NAMES["optical"] == "光通訊（含 CPO 相關）"
    assert "tg" not in I.JUDGE and I.TESTS["tg"] == I.TESTS["tw"]


def test_shared_with_market_level():
    """門檻、臨界值、分級、重抽的規則和市場層級（bubspec VER 4）同一份，不另寫一套。"""
    assert I.level4 is B.level4 and I.LEVELS is B.LEVELS
    assert (I.RUN2_PCT, I.RUN2_ATH, I.TREND_Z, I.PSY_RUN, I.E_RUN, I.DIR_MONTHS, I.FUEL_PCT) == \
        (B.RUN2_PCT, B.RUN2_ATH, B.TREND_Z, B.PSY_RUN, B.E_RUN, B.DIR_MONTHS, B.FUEL_PCT)
    assert I.PSY is B.PSY and I.TREND is B.TREND
    assert (I.BUB_BLOCK, I.BUB_BOOT, I.BUB_SEED, I.BUB_MIN_HOT, I.BUB_EPI_MIN, I.BUB_EPI_GAP) == \
        (B.BUB_BLOCK, B.BUB_BOOT, B.BUB_SEED, B.BUB_MIN_HOT, B.BUB_EPI_MIN, B.BUB_EPI_GAP)
    assert [t for _, t in I.DD_MONTHS] == [t for _, t in B.BUB_DD]
    assert (I.G_PRICE_MONTHS, I.G_PRICE_DAYS, I.EST_COVER_MIN, I.EST_STALE_DAYS) == \
        (B.G_PRICE_MONTHS, B.G_PRICE_DAYS, B.EST_COVER_MIN, B.EST_STALE_DAYS)
