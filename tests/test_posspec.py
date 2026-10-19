"""部位參考的規格（docs/lab_crash_plan.md 第 16 節）：規格鎖定。

規格是在算任何回測結果之前寫定的（VER 1，2026-10-19）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import hotdd
from arm.lab import posspec as X
from arm.lab import sigspec


def test_pos_spec_v1_is_locked():
    assert X.VER == 1 and X.SPEC_DATE == "2026-10-19"
    assert X.MARKETS == sigspec.MARKETS == ("tw", "spx", "ixic", "ndx", "sox")
    assert X.TR_FROM == {"tw": "2013-01-02"} and X.SPX_DIV is True
    assert (X.LAG, X.BAND) == (1, 0.10)
    assert X.COST == {"tw": 0.0005, "spx": 0.0001, "ixic": 0.0001, "ndx": 0.0001, "sox": 0.0001}
    assert (X.VOL_N, X.VOL_WARM, X.WARN_CAP, X.BUY_DAYS) == (20, 1250, 0.5, 60)
    assert X.VERSIONS == ("full", "v", "vw", "vwb", "vwbu") and X.MAIN == "vwb" and set(X.VERSION_NAMES) == set(X.VERSIONS)
    assert X.SIG_SRC == "sig_research.json"
    assert (X.BEAR, X.MDD_GAIN, X.CAGR_TOL, X.RECENT_YEARS) == (0.20, 0.05, 0.01, 10)
    assert X.VERDICTS == ("better", "trade", "none") and set(X.VERDICT_NAMES) == set(X.VERDICTS)


def test_pos_spec_refers_to_existing_definitions():
    """引用的其他規格與函式都還在：大跌段用 hotdd.declines（多空門檻法則），★ 清單用訊號總覽的判定。"""
    assert callable(hotdd.declines)
    assert sigspec.TIERS[0] == "good" and set(sigspec.DIRS) == {"up", "warn", "buy"}
