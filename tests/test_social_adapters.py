"""社群 live adapter 測試（M4，離線）：相關性過濾、RSS 解析、LLM 深析 gating。"""
from arm.connectors.social import filters, llm, news
from arm.connectors.social import base as sbase


def test_filters_relevance_and_etf_extract():
    assert filters.extract_etfs("00991A 今天大漲") == ("00991A",)
    assert "00998A" in filters.extract_etfs("復華全球金融股 00998A 配息")
    assert filters.is_relevant("主動式ETF 規模創高")            # generic
    assert filters.is_relevant("統一00981A 績效亮眼")           # competitor
    assert filters.is_relevant("復華推出主動ETF")               # brand+主動
    assert not filters.is_relevant("台積電法說會逐字稿")        # 無關


def test_news_parses_rss_and_filters(monkeypatch):
    rss = """<rss><channel>
      <item><title>復華投信再推主動式ETF</title><description>規模成長</description>
            <link>https://x/1</link><pubDate>Mon, 15 Jun 2026 08:00:00 +0800</pubDate></item>
      <item><title>某無關個股新聞</title><description>與ETF無關</description>
            <link>https://x/2</link><pubDate>Mon, 15 Jun 2026 08:00:00 +0800</pubDate></item>
    </channel></rss>"""
    monkeypatch.setattr(news, "get_bytes", lambda url, **kw: rss.encode("utf-8"))
    ms = news.fetch("2026-06-16", window_days=10)
    assert len(ms) == 1 and ms[0].platform == "news"
    assert ms[0].date == "2026-06-15" and "復華" in ms[0].text


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


def test_llm_available_gating(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.available() is False and llm.claude_analyzer() is None
