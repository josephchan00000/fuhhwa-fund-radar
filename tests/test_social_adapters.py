"""社群 adapter 共用件測試（M4，離線）：相關性過濾、baseline 分析與 LLM 接口。
2026-11-01 拿掉舊的本機流程（news、llm 兩個 adapter 與它們的測試一起拿掉）；臉書抓取留著，這裡測它用到的 filters、base。"""
from arm.connectors.social import filters
from arm.connectors.social import base as sbase


def test_filters_relevance_and_etf_extract():
    assert filters.extract_etfs("00991A 今天大漲") == ("00991A",)
    assert "00998A" in filters.extract_etfs("復華全球金融股 00998A 配息")
    assert filters.is_relevant("主動式ETF 規模創高")            # generic
    assert filters.is_relevant("統一00981A 績效亮眼")           # competitor
    assert filters.is_relevant("復華推出主動ETF")               # brand+主動
    assert not filters.is_relevant("台積電法說會逐字稿")        # 無關


def test_analyze_baseline_without_llm():
    m = sbase.SocialMention("news", "鉅亨", "2026-06-15",
                            "復華主動ETF 配息亮眼，殖利率高，業配合作", etfs=("00998A",))
    a = sbase.analyze(m, llm=None)
    assert a["sentiment"] in ("正面", "負面", "中性")
    assert "配息入息" in a["selling_points"] and a["suspected_ad"] is True


def test_analyze_llm_hook_merges():
    m = sbase.SocialMention("news", "鉅亨", "2026-06-15", "復華主動ETF", etfs=("00991A",))
    fake_llm = lambda mention, baseline: {"llm": True, "llm_summary": "看好主動選股",
                                          "sentiment": "正面"}
    a = sbase.analyze(m, llm=fake_llm)
    assert a["llm"] is True and a["llm_summary"] == "看好主動選股" and a["sentiment"] == "正面"
