"""期貨加碼的規格（docs/lab_tilt_plan.md）：規格鎖定。

規格是在算任何加碼結果之前寫定的（VER 1，2026-10-23）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import hotdd
from arm.lab import practsim
from arm.lab import practspec
from arm.lab import tiltspec as X
from arm.lab import xstrat
from arm.lab import xstratspec


def test_tilt_spec_v1_is_locked():
    assert X.VER == 1 and X.SPEC_DATE == "2026-10-23"
    assert X.MARKETS == xstratspec.MARKETS == practspec.MARKETS
    assert X.JUDGED == ("tw", "spx", "ndx") and X.REF == ("ixic", "sox")
    assert set(X.JUDGED) | set(X.REF) == set(X.MARKETS) and not set(X.JUDGED) & set(X.REF)
    assert set(X.NAMES) == set(X.FUT) == set(X.MARKETS)
    assert all(X.FUT[m] for m in X.JUDGED) and all(X.FUT[m] is None for m in X.REF)
    assert X.DAY_COUNT == 365
    assert X.COST_FUT == 0.00005 == xstratspec.COST_FUT
    assert (X.ROLL_TW, X.ROLL_US, X.ROLL_NTH) == (("monthly", 2), ("quarterly", 4), 3)
    assert (X.ADD, X.LAG, X.MA_N) == (0.5, 1, 200)
    assert X.RULES == {
        "K1": {"name": "短線買點加碼（RSI(2)、VIX 衝刺）", "src": "xs", "grps": ("short",)},
        "K2": {"name": "落底買點加碼", "src": "xs", "grps": ("bottom",)},
        "K3": {"name": "策略頁的買點全部加碼（短線、落底、季節性）", "src": "xs", "grps": ("short", "bottom", "season")},
        "K4": {"name": "200 日均線上加碼", "src": "ma"},
        "K5": {"name": "溫度計短線偏多多就加碼", "src": "thermo"},
    }
    assert X.XS_TIERS == ("good", "ref") == practspec.STRAT_RULES["M2"]["tiers"]
    assert (X.RECENT_YEARS, X.BEAR, X.BOOT_BLOCK, X.BOOT_DRAWS, X.BOOT_SEED) == (10, 0.20, 250, 1000, 20261024)
    assert X.VERDICTS == ("better", "same", "worse") and set(X.VERDICT_NAMES) == set(X.VERDICTS)
    assert (X.PAGE_RULES, X.PAGE_MIN_BETTER, X.PAGE_MAX_WORSE) == (("K1", "K2", "K3", "K4"), 2, 0)
    assert "K5" not in X.PAGE_RULES


def test_tilt_spec_refers_to_existing_definitions():
    """引用的分組、函式都還在：總經策略的分組與逐年判定、200 日均線、溫度計 B1 的決定、大跌段。"""
    grps = {s["grp"] for s in xstratspec.STRATS}
    for R in X.RULES.values():
        for g in R.get("grps", ()):
            assert g in grps and g != "risk"
    assert {s["k"] for s in xstratspec.STRATS if s["grp"] == "short"} == {"rsi2", "vixs"}
    assert practspec.THERMO_RULES["B1"]["side"] == "u" and practspec.THERMO_RULES["B1"]["hz"] == ("short",)
    assert practspec.LAG == X.LAG and xstratspec.LAG == X.LAG
    for f in (practsim.xs_tiers, practsim.xs_first_year, practsim.thermo_positions, practsim.decide,
              xstrat.held_pos, xstrat.pos_daily_ma, xstrat.data, hotdd.declines):
        assert callable(f)


def test_backfill_tr_fills_old_months_and_skips_done(monkeypatch, tmp_path):
    """加權報酬指數往前回補：每個月一請求、已完成的月份不再打、查無（報酬指數 2003 年才開始）也標完成、抓不到的下一輪再試。"""
    import json
    from arm.lab import market, store, v3data
    monkeypatch.setattr(store, "LAB", tmp_path)
    (tmp_path / "v3_tr.json").write_text(json.dumps({"q": {"2013-01-02": 11164.55}, "m": ["2013-01", "2002-12"]}),
                                         encoding="utf-8")
    calls = []

    def fake(y, m):
        calls.append((y, m))
        if (y, m) == (2003, 2):
            return None                                   # 這一輪抓不到
        if y == 2002:
            return {}                                     # 查無
        return {f"{y:04d}-{m:02d}-03": 5000.0 + m}
    monkeypatch.setattr(market, "twse_tr_month", fake)
    monkeypatch.setattr(market, "log", lambda *a, **k: None)
    n = v3data.backfill_tr(2002, 2003)
    assert (2002, 12) not in calls and len(calls) == 23
    doc = json.loads((tmp_path / "v3_tr.json").read_text(encoding="utf-8"))
    assert n == 11 and doc["q"]["2013-01-02"] == 11164.55 and doc["q"]["2003-03-03"] == 5003.0
    assert "2003-02" not in doc["m"] and "2002-05" in doc["m"] and "2003-12" in doc["m"]
    calls.clear()
    assert v3data.backfill_tr(2002, 2003) == 0 and calls == [(2003, 2)]
