"""fundnews（基金相關新聞・社群）離線測試：命名合併、PTT 過濾、儀表板區塊渲染。"""
from arm import fundnews
from arm.fund_dashboard import _fundnews_view


def test_base_name_strips_class_and_currency():
    assert fundnews.base_name("復華全方位基金TISA類型") == "復華全方位基金"
    assert fundnews.base_name("復華台灣科技高股息基金A類型") == "復華台灣科技高股息基金"
    assert fundnews.base_name("復華美國新星基金-新臺幣") == "復華美國新星基金"
    assert fundnews.base_name("復華高成長基金") == "復華高成長基金"
    assert fundnews.base_name(None) == ""


def test_fund_query_groups_merges_share_classes():
    funds = [
        {"fund_id": "122", "name": "復華台灣科技高股息基金A類型", "short_name": "台灣科技高股息A"},
        {"fund_id": "123", "name": "復華台灣科技高股息基金B類型", "short_name": "台灣科技高股息B"},
        {"fund_id": "03", "name": "復華高成長基金", "short_name": "高成長"},
    ]
    groups = fundnews.fund_query_groups(funds)
    assert [g["base"] for g in groups] == ["復華台灣科技高股息基金", "復華高成長基金"]
    assert groups[0]["fund_ids"] == ["122", "123"]


def test_fund_item_relevant_filters_noise():
    base = "復華美國新星基金"
    assert fundnews.fund_item_relevant({"title": "復華美國新星基金 6 月績效"}, base)
    assert fundnews.fund_item_relevant({"title": "基金特蒐／美國新星 分批進場"}, base)
    # 放寬搜尋回的他牌同類基金
    assert not fundnews.fund_item_relevant(
        {"title": "柏瑞環球基金-柏瑞美國研究增值核心股票基金 A 的總覽"}, base)
    # 品牌層系列文（每檔基金都會命中）歸品牌動態、不進各基金
    assert not fundnews.fund_item_relevant(
        {"title": "基金：復華投信旗下各基金7/2淨值漲跌一覽表"}, base)
    assert not fundnews.fund_item_relevant({"title": ""}, base)


def test_blocked_sources_filtered():
    items = [{"title": "基金：復華投信旗下各基金7/2淨值漲跌一覽表", "source": "富聯網"},
             {"title": "復華高成長基金創高", "source": "鉅亨網"}]
    out = fundnews._clean_items(items)
    assert [i["source"] for i in out] == ["鉅亨網"]


def test_strip_source_suffix():
    assert fundnews.strip_source_suffix("復華高成長基金創高 - 鉅亨網", "鉅亨網") == "復華高成長基金創高"
    assert fundnews.strip_source_suffix("標題沒有尾綴", "鉅亨網") == "標題沒有尾綴"
    assert fundnews.strip_source_suffix("標題 - 別家", "鉅亨網") == "標題 - 別家"
    assert fundnews.strip_source_suffix(None, None) == ""


def test_ptt_relevant_requires_brand():
    assert fundnews.ptt_relevant("[標的] 復華高成長基金怎麼看")
    assert not fundnews.ptt_relevant("[請益] 高成長股票推薦")
    assert not fundnews.ptt_relevant("")


_RSS_FIXTURE = """<rss><channel>
<item><title><![CDATA[復華高成長基金規模創高]]></title>
  <link>https://news.cnyes.com/1</link>
  <pubDate>Thu, 02 Jul 2026 08:00:00 +0800</pubDate></item>
<item><title><![CDATA[台積電法說會前瞻]]></title>
  <link>https://news.cnyes.com/2</link>
  <pubDate>Thu, 02 Jul 2026 09:00:00 +0800</pubDate></item>
<item><title><![CDATA[復華投信舊聞（超過視窗）]]></title>
  <link>https://news.cnyes.com/3</link>
  <pubDate>Mon, 01 Jun 2026 09:00:00 +0800</pubDate></item>
</channel></rss>"""


def test_parse_rss_keeps_recent_fuhhwa_only():
    items = fundnews.parse_rss(_RSS_FIXTURE, "鉅亨網", days=7000)  # 放大視窗只驗過濾
    titles = [i["title"] for i in items]
    assert "復華高成長基金規模創高" in titles and "台積電法說會前瞻" not in titles
    assert all(i["source"] == "鉅亨網" for i in items)
    assert fundnews.parse_rss("", "鉅亨網") == []


def test_merge_news_dedups_and_sorts():
    a = [{"title": "復華高成長基金規模創高", "datetime": "2026-07-02T08:00:00+08:00"}]
    b = [{"title": "復華高成長基金規模創高", "datetime": "2026-07-02T07:00:00+08:00"},
         {"title": "復華投信配息公告", "datetime": "2026-07-03T09:00:00+08:00"}]
    out = fundnews.merge_news(a, b)
    assert [i["title"] for i in out] == ["復華投信配息公告", "復華高成長基金規模創高"]


def test_route_feeds_to_funds_matches_core_name():
    groups = [{"base": "復華高成長基金", "items": []},
              {"base": "復華神盾基金", "items": []}]
    feeds = [{"title": "復華高成長基金規模創高", "url": "https://x/1",
              "source": "鉅亨網", "datetime": "2026-07-02T08:00:00+08:00"}]
    out = fundnews.route_feeds_to_funds(groups, feeds)
    assert len(out[0]["items"]) == 1
    assert out[1]["items"] == []


def test_view_without_doc_shows_hint():
    html = _fundnews_view(None)
    assert "fetch_fund_news.py" in html


def test_view_renders_brand_funds_social():
    doc = {
        "as_of": "2026/07/03 08:00", "window_days": 7, "source": "測試來源",
        "highlights": ["品牌焦點：復華投信宣布配息（測試報）"],
        "brand": [{"title": "復華投信宣布配息", "url": "https://x/1",
                   "source": "測試報", "date": "2026-07-02 10:00"}],
        "funds": [
            {"base": "復華高成長基金", "fund_ids": ["03"],
             "items": [{"title": "高成長基金奪獎", "url": "https://x/2",
                        "source": "測試報", "date": "2026-07-01 09:00",
                        "summary": "測試摘要一句話。"}]},
            {"base": "復華神盾基金", "fund_ids": ["13"], "items": []},
        ],
        "social": [{"platform": "ptt", "title": "[心得] 復華基金定期定額",
                    "url": "https://ptt/x", "date": "7/02", "push": 25}],
    }
    html = _fundnews_view(doc)
    assert "本週看點" in html and "品牌焦點" in html
    assert "復華投信宣布配息" in html and "https://x/1" in html
    assert "復華高成長基金" in html and "1 則" in html and "#fund-03" in html
    assert "測試摘要一句話。" in html          # 摘要行
    assert "復華神盾基金" in html              # 無新聞者列於「其餘」摘要行
    assert "25 推" in html and "[心得] 復華基金定期定額" in html
    assert "非投資建議" in html


def test_auto_highlights_from_doc():
    doc = {"window_days": 7,
           "brand": [{"title": "基金：復華投信旗下各基金7/2淨值漲跌一覽表", "source": "富聯網"},
                     {"title": "復華兩檔ETF配息出爐", "source": "Newtalk新聞"}],
           "funds": [{"base": "復華高成長基金", "items": [{"title": "x"}]},
                     {"base": "復華神盾基金", "items": []}],
           "social": [{"title": "[心得] 復華", "push": 30}]}
    hls = fundnews.auto_highlights(doc)
    assert any("高成長" in h for h in hls)
    assert any("復華兩檔ETF配息出爐" in h for h in hls)   # 跳過系列文、取第一則焦點
    assert any("30 推" in h for h in hls)


def test_view_social_empty_degrades():
    doc = {"as_of": "2026/07/03", "window_days": 7, "brand": [], "funds": [], "social": []}
    html = _fundnews_view(doc)
    assert "無品牌新聞" in html and "無相關討論" in html
