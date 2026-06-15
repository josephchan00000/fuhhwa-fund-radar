"""想法引擎合規事後標注單元測試（M1-8）。"""
from arm import ideas


def test_annotate_flags_banned_words():
    notes = ideas.annotate("本檔保證獲利、必漲")
    spans = {n["span"] for n in notes if n["risk"] == "高"}
    assert "保證" in spans and "必漲" in spans


def test_annotate_skips_disclaimer_negation():
    """『非保證收益』是合規免責，不該被當成『保證』違規。"""
    notes = ideas.annotate("本基金並無保證收益及配息，過去績效不代表未來")
    assert all(n["span"] != "保證" for n in notes if n["risk"] == "高")


def test_annotate_perf_needs_disclaimer():
    notes = ideas.annotate("近一月報酬領先大盤 5%")
    assert any(n["risk"] == "中" for n in notes)               # 缺免責 → 中
    ok = ideas.annotate("近一月報酬領先 5%，過去績效不代表未來")
    assert all(n["risk"] != "中" for n in ok)
