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


def test_farm_content_filtered():
    # SEO 內容農場點閱誘餌（舊文改標題/更新日期重貼）——來源與標題兩層都要擋
    farm_titles = [
        "復華亞太神龍科技基金-新臺幣，同樣是科技基金，為什麼近一年能漲超過 200%？",
        "復華全球平衡基金-新臺幣，這幾天規模暴增兩成，究竟發生了什麼事？",
        "復華華人世紀基金，單月規模暴增58億的背後秘密是什麼？",
        "復華全球平衡基金-新臺幣，老牌基金為何還能稱霸？22年百萬變七百萬。",
    ]
    for t in farm_titles:
        assert fundnews.is_farm_title(t), t
        assert not fundnews.is_news_title(t), t
    # CMoney投資網誌 整個來源都排除
    assert not fundnews.source_ok({"source": "CMoney投資網誌"})
    # 真新聞（陳述句、非誇飾問句）不受影響
    for t in ["績效翻倍海外基金熱 復華全球物聯網、統一全球新科技等今年表現佳",
              "投信海外基金規模、績效翻倍"]:
        assert not fundnews.is_farm_title(t), t
        assert fundnews.is_news_title(t), t


def test_negative_scandal_news_filtered():
    # 復華自家司法/醜聞報導——內部溝通用途，不上儀表板
    for t in ["勞動基金炒股案第3波　搜索復華投信！再傳官員",
              "勞動基金官商炒「遠百」　復華投信投資長移送！經理人喊冤",
              "復華投信經理人涉內線交易遭起訴"]:
        assert fundnews.is_negative_title(t), t
        assert not fundnews.is_news_title(t), t
        assert not fundnews.ptt_relevant("[新聞] " + t)   # PTT 討論串同樣排除
    # 正常績效/規模新聞不被誤殺
    assert not fundnews.is_negative_title("績效翻倍海外基金熱 復華全球物聯網等今年表現佳")
    # _clean_items 端到端：農場＋負面剔除、真新聞保留
    items = [{"title": "復華亞太神龍科技基金，為什麼近一年能漲超過 200%？", "source": "CMoney投資網誌"},
             {"title": "勞動基金炒股案　搜索復華投信", "source": "三立新聞"},
             {"title": "績效翻倍海外基金熱 復華全球物聯網表現佳", "source": "經濟日報"}]
    assert [i["title"] for i in fundnews._clean_items(items)] == \
        ["績效翻倍海外基金熱 復華全球物聯網表現佳"]


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
    assert "投信動態" in html                  # 品牌新聞併入單一清單、以標籤註記
    assert "#fund-03" in html and ">高成長</a>" in html   # 基金標籤可點跳詳情卡
    assert "測試摘要一句話。" in html          # 摘要行
    assert "復華神盾基金" not in html          # 已合併：無專屬新聞的基金不再整串列名
    assert "25 推" in html and "[心得] 復華基金定期定額" in html
    assert "非投資建議" in html


def test_view_merges_and_dedups_across_groups():
    """同一篇報導同時命中品牌與多檔基金 → 合併清單只列一次、標籤齊備。"""
    it = {"title": "規模百億基金比一比：復華物聯網、華人世紀怎麼選", "url": "https://x/9",
          "source": "測試報", "date": "2026-07-20 10:00"}
    doc = {"as_of": "2026/07/22", "window_days": 7,
           "brand": [dict(it)],
           "funds": [{"base": "復華全球物聯網科技基金", "fund_ids": ["08"], "items": [dict(it)]},
                     {"base": "復華華人世紀基金", "fund_ids": ["02"], "items": [dict(it)]}],
           "social": []}
    html = _fundnews_view(doc)
    assert html.count("規模百億基金比一比") == 1
    assert "投信動態" in html and "#fund-08" in html and "#fund-02" in html
    assert ">全球物聯網科技</a>" in html and ">華人世紀</a>" in html


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
    assert "無相關新聞" in html and "無相關討論" in html


# ── Google News「有效日期」防線（2026-08-06 使用者抓包「很多都是舊的」）────────
from datetime import datetime, timedelta, timezone  # noqa: E402

_TW = timezone(timedelta(hours=8))
_NOW = datetime(2026, 8, 6, 8, 0, tzinfo=_TW)


def _gitem(title, iso, url="https://news.google.com/rss/articles/xyz?oc=5"):
    dt = datetime.fromisoformat(iso)
    return {"title": title, "url": url, "source": "測試報",
            "date": dt.strftime("%Y-%m-%d %H:%M"), "datetime": dt.isoformat()}


def test_prospectus_announcements_are_junk():
    # 中租基智網等平台的例行修訂公告轉貼（實際踩坑：一年前公告被標成近期、掛滿 6 檔基金卡）
    for t in ["復華投信數檔基金公開說明書修訂",
              "「復華亞太成長基金」等三檔基金修訂公開說明書",
              "復華投信3檔基金修訂信託契約及公開說明書"]:
        assert not fundnews.is_news_title(t), t
    # 真新聞不受影響
    assert fundnews.is_news_title("復華金融股債雙收傘型ETF上櫃掛牌 櫃買債券ETF突破百檔")


def test_date_verify_drops_redated_old_article():
    """實際案例：4/14 掛牌稿被 Google 標 08-01 → 原文驗出真實刊出日 → 剔除＋台帳記錄。"""
    seen, state, called = {}, {"budget": 5}, []

    def fake_verify(url):
        called.append(url)
        return ("https://www.ctee.com.tw/news/20260414700256-439901",
                datetime(2026, 4, 14, tzinfo=_TW))

    items = [_gitem("復華金融股債雙收傘型 ETF 上櫃掛牌 櫃買債券 ETF 突破百檔",
                    "2026-08-01T17:00:00+08:00")]
    out = fundnews.date_verify(items, seen, state, now=_NOW, verifier=fake_verify)
    assert out == [] and len(called) == 1 and state["budget"] == 4
    ent = seen[items[0]["title"][:24]]
    assert ent["v"].startswith("2026-04-14") and ent["u"].startswith("https://www.ctee")
    # 台帳已有驗證結果 → 第二輪不再耗預算、照樣剔除（verifier 不得被呼叫）
    out2 = fundnews.date_verify(items, seen, {"budget": 5}, now=_NOW,
                                verifier=lambda u: (_ for _ in ()).throw(AssertionError))
    assert out2 == [] and len(called) == 1


def test_date_verify_ledger_blocks_resurrection_without_network():
    """台帳記過的最早日期擋復活：Google 把同標題重標新日期、驗證又失效時，仍以最早值計。"""
    t = "復華投信獲頒基金金鑽獎肯定"
    seen = {t[:24]: {"pub": "2026-07-20T10:00:00+08:00", "seen": "2026-07-20T10:00:00+08:00"}}
    items = [_gitem(t, "2026-08-05T09:00:00+08:00")]     # Google 重標成新日期
    out = fundnews.date_verify(items, seen, {"budget": 0}, now=_NOW,
                               verifier=lambda u: (None, None))
    assert out == []                                      # 07-20 已出 7 天窗 → 剔除
    assert seen[t[:24]]["pub"].startswith("2026-07-20")   # 最早值不被新日期洗掉


def test_date_verify_keeps_fresh_and_rewrites_date_url():
    seen, state = {}, {"budget": 5}
    # 查無日期 → fail-open 沿用 pubDate、項目保留
    fresh = _gitem("復華投信配息公告出爐", "2026-08-05T09:00:00+08:00")
    out = fundnews.date_verify([fresh], seen, state, now=_NOW, verifier=lambda u: (None, None))
    assert len(out) == 1 and out[0]["datetime"] == fresh["datetime"]
    assert seen[fresh["title"][:24]]["v"] == ""
    # 驗到窗內較早日期 → 改標有效日期＋連結換原文（不繞 Google 轉址）
    it = _gitem("復華發行新基金開募", "2026-08-05T09:00:00+08:00")
    out = fundnews.date_verify([it], seen, state, now=_NOW,
                               verifier=lambda u: ("https://money.udn.com/x",
                                                   datetime(2026, 8, 2, 10, 0, tzinfo=_TW)))
    assert out[0]["date"].startswith("2026-08-02") and out[0]["url"] == "https://money.udn.com/x"
    # 非 Google 連結不驗、不耗預算（RSS 直抓的 pubDate 出自發布者、可信）
    b = state["budget"]
    direct = _gitem("復華高成長基金規模創高", "2026-08-05T12:00:00+08:00",
                    url="https://news.cnyes.com/news/id/1")
    out = fundnews.date_verify([direct], seen, state, now=_NOW,
                               verifier=lambda u: (_ for _ in ()).throw(AssertionError))
    assert len(out) == 1 and state["budget"] == b


def test_seen_prune_keeps_recent_only():
    seen = {"舊": {"pub": "2026-05-01T00:00:00+08:00", "seen": "2026-05-01T00:00:00+08:00"},
            "新": {"pub": "2026-08-01T00:00:00+08:00", "seen": "2026-08-05T00:00:00+08:00"},
            "壞": {}}
    out = fundnews._seen_prune(seen, _NOW)
    assert "新" in out and "舊" not in out and "壞" in out   # 無日期條目以 now 計、先留著
