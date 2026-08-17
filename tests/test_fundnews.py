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


# ── YouTube 社群（2026-08-06 使用者需求）───────────────────────────────────────
def _yt_doc(vid, title, desc="", channel="測試頻道", pub="2026-08-05T10:00:00Z"):
    return {"id": {"videoId": vid},
            "snippet": {"title": title, "description": desc,
                        "channelTitle": channel, "publishedAt": pub}}


def test_parse_youtube_filters_dedupes_sorts():
    docs = [{"items": [
                _yt_doc("v1", "復華基金月配息實測", pub="2026-08-04T10:00:00Z"),
                _yt_doc("v2", "存股心得分享"),                    # 無「復華」也無自家代碼 → 濾除
                _yt_doc("v3", "台股ETF怎麼買", desc="含復華00991A比較"),  # 說明命中也算相關
                _yt_doc("v4", "勞動基金炒股案 搜索復華投信"),      # 負面司法 → 濾除
                _yt_doc("v5", "00929 8月配息出爐！"),              # 只寫自家 ETF 代碼 → 相關
            ]},
            {"items": [_yt_doc("v1", "復華基金月配息實測")]}]      # 跨查詢重複 → 去重
    out = fundnews.parse_youtube(docs, {"v1": {"views": 120, "sec": 45},
                                        "v3": {"views": 45678, "sec": 600}})
    assert [i["url"][-2:] for i in out] == ["v3", "v1", "v5"]     # 依觀看數新→舊
    assert out[0]["views"] == 45678 and out[0]["platform"] == "youtube"
    assert "short" not in out[0] and "/watch?v=v3" in out[0]["url"]
    assert out[1].get("short") is True and "/shorts/v1" in out[1]["url"]   # ≤3 分＝Shorts
    assert out[1]["date"] == "2026-08-04" and out[1]["channel"] == "測試頻道"
    assert fundnews.parse_youtube([], {}) == []


def test_youtube_three_tiers():
    """三層清單（2026-08-06 使用者規劃）：官方全收＋跨層去重＋同業熱門判準＋播放清單轉形。"""
    # _pl_docs：playlistItems → search 形狀、視窗外舊上傳剔除
    pl = {"items": [
        {"snippet": {"title": "復華金管家：經理人報告 EP12", "channelTitle": "復華投信",
                     "resourceId": {"videoId": "of1"}},
         "contentDetails": {"videoId": "of1", "videoPublishedAt": "2026-08-05T03:00:00Z"}},
        {"snippet": {"title": "半年前的舊片", "channelTitle": "復華投信",
                     "resourceId": {"videoId": "of2"}},
         "contentDetails": {"videoId": "of2", "videoPublishedAt": "2026-02-01T03:00:00Z"}},
    ]}
    docs = fundnews._pl_docs(pl, "2026-07-30T00:00:00Z")
    assert [i["id"]["videoId"] for i in docs["items"]] == ["of1"]
    # 官方層：不看「復華」相關性照收（標題可以只是「金管家教學」）、掛 official 章
    seen = set()
    official = fundnews.parse_youtube([docs], {"of1": {"views": 50, "sec": 400}},
                                      relevant=lambda t, d="": True,
                                      mark={"official": True}, seen=seen)
    assert official[0]["official"] is True and official[0]["channel"] == "復華投信"
    # 跨層去重：同支影片再出現在搜尋結果 → 不重複佔相關層名額
    dup = {"items": [_yt_doc("of1", "復華金管家：經理人報告 EP12")]}
    assert fundnews.parse_youtube([dup], {}, seen=seen) == []
    # 同業熱門判準：含同業代碼收、自家（復華/00929）不收、負面不收
    assert fundnews.yt_peer_relevant("0056 高股息還能買嗎？")
    assert not fundnews.yt_peer_relevant("00929 復華配息")          # 自家歸相關層
    assert not fundnews.yt_peer_relevant("0056 遭搜索調查")         # 負面照擋
    assert not fundnews.yt_peer_relevant("美股大盤 QQQ 分析")       # 無同業代碼


def test_view_renders_official_and_peer_pills():
    doc = {"as_of": "2026/08/06", "window_days": 7, "brand": [], "funds": [],
           "social": [{"platform": "youtube", "title": "復華金管家：台灣智能基金開箱",
                       "channel": "復華投信", "official": True,
                       "url": "https://www.youtube.com/watch?v=of1",
                       "date": "2026-08-05", "views": 50},
                      {"platform": "youtube", "title": "0056 vs 00878 怎麼選", "peer": True,
                       "channel": "同業頻道", "url": "https://www.youtube.com/watch?v=p1",
                       "date": "2026-08-05", "views": 9000},
                      {"platform": "youtube", "title": "月配息ETF總整理", "peer": True,
                       "cat": "高股息", "channel": "配息頻道",
                       "url": "https://www.youtube.com/watch?v=p2",
                       "date": "2026-08-05", "views": 88000}]}
    html = _fundnews_view(doc)
    assert ">官方</span>" in html and ">同業熱門</span>" in html   # 舊落檔無 cat＝原章
    assert ">熱門・高股息</span>" in html                          # 2026-08-14 擴編：分類章
    assert "復華投信・YouTube" in html


def test_yt_secs_and_code_relevance():
    assert fundnews._yt_secs("PT2M59S") == 179
    assert fundnews._yt_secs("PT1H2M3S") == 3723
    assert fundnews._yt_secs("PT45S") == 45
    assert fundnews._yt_secs("") == 0 and fundnews._yt_secs("垃圾") == 0
    assert fundnews.yt_relevant("00929 8月配息出爐！")            # 自家 ETF 代碼即相關
    assert fundnews.yt_relevant("高股息00929 vs 006208 比較")     # 前貼中文字照樣命中
    assert fundnews.yt_relevant("存股心得 #00929 配息")           # 獨立 hashtag 也算
    assert not fundnews.yt_relevant("0050 定期定額心得")          # 他家標的不收
    # 2026-08-06 實戰誤收：日文單字卡影片課號「L#00929」——編號式前綴不得命中
    assert not fundnews.yt_relevant("シン・フラッシュ英単語/高校1年/50問L#00929")
    assert not fundnews.yt_relevant("題庫100929號解析")           # 長數字內嵌不得命中


def test_yt_episode_number_and_no_cjk_guards():
    """2026-08-14 使用者回報誤收：可蘭經朗誦《Surah Rahman | Ep - 00929》——
    空白隔開的集數編號通過了獨立詞判準。兩道新防呆：①集數式前綴（Ep -／第…／No.）
    不算代碼命中；②純代碼命中（無品牌詞）另須含漢字。讀取端 sanitize 同步濾。"""
    bad = "Surah Rahman | Ep - 00929 By Qari Nadeem Yousuf | سورہ رحمٰن55 |Beautiful Recitation"
    assert not fundnews._code_hit(bad)                        # Ep - ＝集數編號
    assert not fundnews._code_hit("第00929集 完整版")
    assert not fundnews._code_hit("EP.00929 特輯")
    assert not fundnews.yt_relevant(bad)
    assert not fundnews.yt_relevant("00929 monthly dividend explained")   # 無漢字不收
    assert fundnews.yt_relevant("00929 8月配息出爐！")                     # 正常寫法不受影響
    assert fundnews.yt_relevant("存股心得 #00929 配息")                    # 獨立 hashtag 照收
    # 讀取端：黑名單 id＋非官方且無漢字標題 → sanitize 即滅（舊落檔不必等重抓）
    doc = {"brand": [], "funds": [], "highlights": [],
           "social": [{"platform": "youtube", "title": bad,
                       "url": "https://www.youtube.com/watch?v=D_pC9_q5spQ", "views": 1673},
                      {"platform": "youtube", "title": "高股息ETF入袋為安？",
                       "url": "https://www.youtube.com/shorts/okvid01", "views": 39915},
                      {"platform": "ptt", "title": "[心得] 存股", "url": "https://ptt/x"}]}
    out = fundnews.sanitize(doc)
    assert all("D_pC9_q5spQ" not in (s.get("url") or "") for s in out["social"])
    assert len(out["social"]) == 2                            # 中文影片與 PTT 保留


def test_yt_peer_expansion_topic_and_selection():
    """市場熱門擴編（2026-08-14 使用者：觀看數超級少、應有超多 ETF／基金影片）：
    主題詞路徑（無代碼）也收、純海外不收；yt_topic 分類；_select_peers＝
    同片去重＋觀看門檻＋分類配額。"""
    assert fundnews.yt_peer_relevant("高股息ETF獲利百萬，該入袋為安嗎？")   # 無代碼、主題詞收
    assert fundnews.yt_peer_relevant("債券ETF現在能買嗎")
    assert not fundnews.yt_peer_relevant("美股 ETF VOO 定期定額全攻略")     # 純海外不收
    assert not fundnews.yt_peer_relevant("Top 10 ETF to Buy Now")           # 無漢字不收
    assert not fundnews.yt_peer_relevant("台積電法說會重點")                # 無主題詞不收
    # 分類（優先序：債券＞高股息＞主動式＞市值型＞基金＞綜合）
    assert fundnews.yt_topic("00679B 美債ETF解析") == "債券"
    assert fundnews.yt_topic("高股息ETF月配息實測") == "高股息"
    # 2026-08-15 首輪實戰誤分：「除息大盤點」的「大盤」誤中市值型、高息/除息不在詞表
    assert fundnews.yt_topic("《8月高息ETF除息大盤點! 公股為何狂買它?》") == "高股息"
    assert fundnews.yt_topic("00981A 主動式ETF經理人操盤") == "主動式"
    assert fundnews.yt_topic("0050 市值型長期持有") == "市值型"
    assert fundnews.yt_topic("台股基金定期定額心得") == "基金"
    assert fundnews.yt_topic("台股ETF榜單曝光") == "綜合"

    def it(vid, title, views):
        return {"platform": "youtube", "title": title, "views": views, "peer": True,
                "url": f"https://www.youtube.com/watch?v={vid}"}
    items = [
        it("a1", "高股息ETF大解析", 90000),
        it("a2", "月配息ETF怎麼挑", 80000),
        it("a3", "高股息ETF退休實測", 70000),          # 高股息第 3 支 → 每類配額 2 擋下
        it("b1", "台股ETF榜單曝光｜三立財經iNEWS", 60000),
        it("b2", "台股ETF榜單曝光｜94要賺錢", 50000),   # 聯播同片異 id → 去重留觀看高者
        it("c1", "債券ETF進場時機", 40000),
        it("d1", "0050 市值型比較", 30000),
        it("e1", "ETF冷門小片", 800),                   # 未達 YT_PEER_MIN_VIEWS
    ]
    picked = fundnews._select_peers(items)
    titles = [p["title"] for p in picked]
    assert "高股息ETF退休實測" not in titles
    assert sum("台股ETF榜單曝光" in t for t in titles) == 1
    assert all("94要賺錢" not in t for t in titles)
    assert "ETF冷門小片" not in titles
    assert 0 < len(picked) <= fundnews.YT_PEER_LIMIT
    # cat 一律寫入（2026-08-15 起前端 data-fcat 也吃它）；綜合章由渲染端顯示素「熱門」
    assert picked[0]["cat"] == "高股息"
    assert [p for p in picked if "榜單" in p["title"]][0]["cat"] == "綜合"
    # 全數未達門檻（安靜週末）→ fallback 取前 2、不留白
    low = [it("z1", "ETF小眾討論", 900), it("z2", "基金週報", 500), it("z3", "存股日記", 400)]
    assert len(fundnews._select_peers(low)) == 2


def test_yt_trend_path_excludes_single_stock():
    """2026-08-15 使用者：「投資相關的（不要個股）」——市場趨勢路徑收大盤行情／總經／
    資產配置，個股本位（知名個股、個股操作詞、4 碼代號）在無產品面時不收。"""
    assert fundnews.yt_peer_relevant("阮慕驊：台股5萬點年底機率高！")        # 趨勢詞收
    assert fundnews.yt_peer_relevant("聯準會降息在即，資產配置怎麼調整？")
    assert fundnews.yt_peer_relevant("通膨降溫 股市多頭還能走多久")
    assert not fundnews.yt_peer_relevant("台積電還能買嗎？三大關鍵解析")      # 個股本位不收
    assert not fundnews.yt_peer_relevant("台股創新高！台積電領軍衝關")        # 趨勢＋個股仍不收
    assert not fundnews.yt_peer_relevant("當沖實戰教學：台股提款密技")        # 個股操作詞
    assert not fundnews.yt_peer_relevant("2330分析：目標價上看新高")          # 4 碼個股代號
    assert fundnews.yt_peer_relevant("台股大漲800點 站上24000點")             # 點數非代號
    assert fundnews.yt_peer_relevant("台股ETF買氣旺！台積電權重過半怎麼辦")   # 有產品面＝豁免
    # yt_topic：趨勢類（有產品字樣歸產品類，不搶）
    assert fundnews.yt_topic("聯準會降息 台股怎麼走") == "市場趨勢"
    assert fundnews.yt_topic("台股ETF榜單曝光") == "綜合"                     # 有 ETF 字樣
    assert fundnews.yt_topic("00929持有半年，每月領息又賺43％") == "高股息"   # 領息入詞表


def test_social_group_mapping():
    """social_group：五分組（etf/active/fund/trend/other）——熱門層用 cat、
    其他平台（官方/相關/PTT/強基金）用標題；渲染端每列掛 data-fcat 供 chips 篩選。"""
    g = fundnews.social_group
    assert g({"cat": "高股息", "title": "x"}) == "etf"
    assert g({"cat": "債券", "title": "x"}) == "etf"
    assert g({"cat": "主動式", "title": "x"}) == "active"
    assert g({"cat": "市場趨勢", "title": "x"}) == "trend"
    assert g({"title": "00409A主動復華全球50：未來投資搶答賽"}) == "active"   # 官方影片標題判
    assert g({"title": "[心得] 復華基金定期定額"}) == "fund"                  # PTT
    assert g({"title": "復華強勢通理財機器人再度調升現金比重"}) == "fund"     # 強基金
    assert g({"title": "00929持有半年，每月領息又賺43％"}) == "etf"
    assert g({"cat": "綜合", "title": "買ETF有哪些隱藏成本?"}) == "etf"       # 綜合→標題再判
    assert g({"cat": "綜合", "title": "台股陷盤整 多空怎麼看"}) == "trend"
    assert g({"title": "隨便聊聊"}) == "other"


def test_view_renders_social_filter_chips():
    """儀表板社群清單：篩選 chips（僅有項目的分組才渲染、帶數量）＋每列 data-fcat＋
    隱藏規則含 .fnit.fhide（2026-07-31 教訓：新工具列的 CSS 三處要一起加）。"""
    from arm.fund_dashboard import _CSS, _JS
    doc = {"as_of": "2026/08/15", "window_days": 7, "brand": [], "funds": [],
           "social": [{"platform": "youtube", "title": "月配息ETF總整理", "peer": True,
                       "cat": "高股息", "url": "https://www.youtube.com/watch?v=p1",
                       "date": "2026-08-14", "views": 88000},
                      {"platform": "youtube", "title": "台股5萬點機率高", "peer": True,
                       "cat": "市場趨勢", "url": "https://www.youtube.com/watch?v=p2",
                       "date": "2026-08-14", "views": 30000},
                      {"platform": "ptt", "title": "[心得] 復華基金定期定額",
                       "url": "https://ptt/x", "date": "8/14", "push": 10}]}
    html = _fundnews_view(doc)
    # 2026-08-15 使用者：「比照其他地方」——.fundbar 版式（🔍 搜尋框＋標準 chips、不帶數量）
    assert 'class="fundbar" id="socbar"' in html and 'id="ssearch"' in html
    assert 'data-f="all"' in html
    assert 'data-f="etf">ETF<' in html
    assert 'data-f="trend">市場趨勢<' in html
    assert 'data-f="fund">基金<' in html
    assert 'data-f="active"' not in html                           # 空分組不渲染 chip
    assert 'data-fcat="etf"' in html and 'data-fcat="trend"' in html
    assert 'data-fcat="fund"' in html
    assert ".fnit.fhide" in _CSS and "#ssearch" in _CSS            # 隱藏規則＋搜尋框樣式
    assert "socbar" in _JS and "ssearch" in _JS                    # JS 掛鉤（chips＋搜尋）
    # 新聞列同款工具列（2026-08-15 使用者核可「社群列＋新聞列都做」）：
    # data-ncat 可多組（同稿投信動態＋基金）、僅非空分組渲染 chip
    doc2 = {"as_of": "2026/08/15", "window_days": 7, "highlights": [],
            "brand": [{"title": "復華投信獲獎", "url": "https://n/1", "date": "2026-08-14",
                       "source": "工商時報"}],
            "funds": [{"base": "復華全球債券基金", "fund_ids": ["11"],
                       "items": [{"title": "復華投信獲獎", "url": "https://n/1",
                                  "date": "2026-08-14", "source": "工商時報"},
                                 {"title": "債券基金買氣升溫", "url": "https://n/2",
                                  "date": "2026-08-13", "source": "經濟日報"}]}],
            "social": []}
    h2 = _fundnews_view(doc2)
    assert 'class="fundbar" id="newsbar"' in h2 and 'id="nsearch"' in h2
    assert 'data-f="brand">投信動態<' in h2 and 'data-f="fund">基金<' in h2
    assert 'data-f="etf"' not in h2                                # 無 ETF 產品稿不渲染
    assert 'data-ncat="brand fund"' in h2                          # 同稿多組
    assert 'data-ncat="fund"' in h2
    assert "newsbar" in _JS and "nsearch" in _JS and "fnnews" in _JS
    # 綜合 cat → 素「熱門」章
    doc["social"] = [{"platform": "youtube", "title": "買ETF隱藏成本", "peer": True,
                      "cat": "綜合", "url": "https://www.youtube.com/watch?v=p3",
                      "date": "2026-08-14", "views": 10000}]
    assert ">熱門</span>" in _fundnews_view(doc)


def test_view_renders_youtube_social_alongside_ptt():
    doc = {"as_of": "2026/08/06", "window_days": 7, "brand": [], "funds": [],
           "social": [{"platform": "ptt", "title": "[心得] 復華基金定期定額",
                       "url": "https://ptt/x", "date": "8/05", "push": 25},
                      {"platform": "youtube", "title": "復華基金月配息實測",
                       "channel": "理財頻道", "url": "https://www.youtube.com/watch?v=v1",
                       "date": "2026-08-04", "views": 45678},
                      {"platform": "youtube", "title": "00929 配息 60 秒看懂", "short": True,
                       "channel": "短片頻道", "url": "https://www.youtube.com/shorts/v9",
                       "date": "2026-08-05", "views": 300}]}
    html = _fundnews_view(doc)
    assert "25 推" in html and "PTT 股票板" in html               # PTT 原樣
    assert "4.6萬" in html and "理財頻道・YouTube<" in html       # 一般影片不帶 Shorts 字樣
    assert "youtube.com/watch?v=v1" in html and "fnyt" in html
    assert "短片頻道・YouTube Shorts" in html and "youtube.com/shorts/v9" in html


def test_fmt_views():
    from arm.fund_dashboard import _fmt_views
    assert _fmt_views(0) == "—" and _fmt_views(None) == "—"
    assert _fmt_views(999) == "999" and _fmt_views(4567) == "4,567"
    assert _fmt_views(45678) == "4.6萬" and _fmt_views(120000) == "12萬"


def test_auto_highlights_includes_youtube():
    doc = {"window_days": 7, "brand": [], "funds": [],
           "social": [{"platform": "ptt", "title": "[心得] 復華", "push": 30},
                      {"platform": "youtube", "title": "復華月配息實測",
                       "channel": "理財頻道", "views": 45678}]}
    hls = fundnews.auto_highlights(doc)
    assert any("30 推" in h for h in hls)                         # PTT 聲量線不變
    assert any("YouTube 熱片" in h and "45,678 次觀看" in h for h in hls)


def test_seen_prune_keeps_recent_only():
    seen = {"舊": {"pub": "2026-05-01T00:00:00+08:00", "seen": "2026-05-01T00:00:00+08:00"},
            "新": {"pub": "2026-08-01T00:00:00+08:00", "seen": "2026-08-05T00:00:00+08:00"},
            "壞": {}}
    out = fundnews._seen_prune(seen, _NOW)
    assert "新" in out and "舊" not in out and "壞" in out   # 無日期條目以 now 計、先留著


def test_save_carries_stale_social_platform(tmp_path, monkeypatch):
    """單一平台本次全空 → 沿用既有落檔項目、看點跟著補；ISO 日期出窗者不沿用。
    2026-08-07 踩坑：CI 少帶 YOUTUBE_API_KEY 的一輪把前日 7 則社群洗成 0——
    整份「全空不覆寫」防呆擋不住「品牌有抓到、單一平台全空」。"""
    import json
    from datetime import datetime, timedelta

    monkeypatch.setattr(fundnews, "OUT", tmp_path / "fund_news.json")
    fresh = (datetime.now(fundnews.TW_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    stale = (datetime.now(fundnews.TW_TZ) - timedelta(days=30)).strftime("%Y-%m-%d")
    old = {"window_days": 7, "brand": [{"title": "舊品牌稿", "source": "經濟日報"}],
           "funds": [],
           "social": [{"platform": "youtube", "title": "昨日影片", "date": fresh,
                       "views": 999},
                      {"platform": "youtube", "title": "出窗影片", "date": stale,
                       "views": 5},
                      {"platform": "ptt", "title": "[心得] 復華討論", "date": "8/06",
                       "push": 12}]}
    fundnews.OUT.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")

    doc = {"window_days": 7, "brand": [{"title": "新品牌稿", "source": "經濟日報"}],
           "funds": [], "social": [], "highlights": []}
    _, saved = fundnews.save(doc)
    assert saved                                       # 整份非空，照常落檔
    got = json.loads(fundnews.OUT.read_text(encoding="utf-8"))
    titles = [s["title"] for s in got["social"]]
    assert "昨日影片" in titles and "[心得] 復華討論" in titles   # 兩平台都沿用
    assert "出窗影片" not in titles                              # 出窗即剔除
    assert any("YouTube 熱片" in h for h in got["highlights"])   # 看點重算補回

    doc2 = {"window_days": 7, "brand": [{"title": "新品牌稿", "source": "經濟日報"}],
            "funds": [],
            "social": [{"platform": "youtube", "title": "今日新片",
                        "date": fresh, "views": 1}], "highlights": []}
    fundnews.save(doc2)
    got2 = json.loads(fundnews.OUT.read_text(encoding="utf-8"))
    yt2 = [s["title"] for s in got2["social"] if s.get("platform") == "youtube"]
    assert yt2 == ["今日新片"]                          # 該平台有新值＝整批汰換、不混舊


def test_ptt_relevant_accepts_own_etf_code():
    """2026-08-07：比照 YouTube 層——自家 ETF 代碼獨立詞也算相關（00929 討論串
    常不寫「復華」）；編號式前綴（L#00929）與非自家代碼照樣排除。"""
    assert fundnews.ptt_relevant("[請益] 00929 抱緊處理還是出場？")
    assert not fundnews.ptt_relevant("日文單字卡 L#00929 課程筆記")
    assert not fundnews.ptt_relevant("[標的] 0050 定期定額請益")   # 非自家代碼


def test_fetch_ptt_dual_board(monkeypatch):
    """雙板抓取（2026-08-07 使用者需求）：Stock＋Fund 都抓、跨板同網址去重、
    項目帶 board；單板失敗不牽連另一板。"""
    def _ent(href, title, push, date=" 8/07"):
        # 尾端 mark div 仿真實 PTT 結構——date 的 </div> 才不會被 _PTT_ENT 的
        # 「</div></div>」終止樣式吃掉（真實頁 meta 內 date 後還有 mark 等 div）
        return (f'<div class="r-ent"><div class="nrec"><span class="hl">{push}</span></div>'
                f'<div class="title"><a href="{href}">{title}</a></div>'
                f'<div class="meta"><div class="date">{date}</div>'
                f'<div class="mark"></div></div></div>')

    stock = _ent("/bbs/Stock/M.1.A.html", "[標的] 00929 存股心得", "12")
    fund = (_ent("/bbs/Fund/M.2.A.html", "[請益] 復華全方位基金", "3")
            + _ent("/bbs/Stock/M.1.A.html", "[標的] 00929 存股心得", "12"))  # 跨板轉錄同文

    def fake_get_bytes(url, **kw):
        if "/bbs/Stock/" in url:
            return stock.encode("utf-8")
        if "/bbs/Fund/" in url:
            return fund.encode("utf-8")
        raise AssertionError(url)

    monkeypatch.setattr(fundnews, "get_bytes", fake_get_bytes)
    out = fundnews.fetch_ptt(pages=1)
    assert len(out) == 2                                   # 同網址去重
    assert {(i["board"], i["title"][:4]) for i in out} == {("Stock", "[標的]"), ("Fund", "[請益]")}
    assert out[0]["push"] >= out[1]["push"]                # 推文數排序

    def broken_stock(url, **kw):
        if "/bbs/Stock/" in url:
            raise OSError("blocked")
        return fund.encode("utf-8")

    monkeypatch.setattr(fundnews, "get_bytes", broken_stock)
    out2 = fundnews.fetch_ptt(pages=1)
    assert [i["board"] for i in out2] == ["Fund", "Stock"] or len(out2) == 2  # Fund 板照常
    assert any(i["board"] == "Fund" for i in out2)


# ── 2026-08-12 品質重規劃（使用者：股感 00409A 漏掉、清單全是基金平台頁／重複比較文）──

_STOCKFEEL_TITLE = "00409A 復華全球未來50主動式ETF｜成分股？配息？優缺點？募集時間？"


def test_platform_quote_pages_filtered_by_url():
    """實際踩坑樣本（2026-08-12 落檔實查）：鉅亨基金總覽/買賣訊號頁、MoneyDJ ETF 報酬
    走勢頁、CMoney 論壇比較文——URL 層一律剔除；股感專文與主流媒體真新聞保留。"""
    items = [
        {"title": "主動復華全球50-ETF報酬走勢", "source": "MoneyDJ",
         "url": "https://www.moneydj.com/etf/ea/et012001.djhtm?etfid=00409A.TW"},
        {"title": "復華全方位基金A類型 的總覽 | 鉅亨網", "source": "鉅亨網",
         "url": "https://invest.cnyes.com/funds/detail/x/A23015/r"},
        {"title": "復華傳家二號基金 的買賣訊號 | 鉅亨網 - 基金老司機", "source": "鉅亨網",
         "url": "https://invest.cnyes.com/funds/detail/x"},
        {"title": "規模破百億的科技巨獸：安聯台灣科技、復華全球物聯網與華人世紀該怎麼選？",
         "source": "CMoney", "url": "https://www.cmoney.tw/forum/article/181668024"},
        {"title": _STOCKFEEL_TITLE, "source": "股感 StockFeel",
         "url": "https://www.stockfeel.com.tw/00409a-etf/"},
        {"title": "挖掘全球AI產業贏家 主動復華全球50 00409A 8月12日開募", "source": "經濟日報",
         "url": "https://money.udn.com/money/story/5607/9624031"},
    ]
    out = fundnews._clean_items(items)
    assert [i["source"] for i in out] == ["股感 StockFeel", "經濟日報"]


def test_comparison_bait_is_farm_but_product_explainer_is_not():
    # CMoney 式比較誘餌（同稿掛多檔、無聊重複）——問句版與「答案在這」賣關子版都擋
    for t in ["規模破百億的科技巨獸：安聯台灣科技、復華全球物聯網與華人世紀該怎麼選？",
              "安聯台灣科技、復華全球物聯網、復華華人世紀該選哪一檔？答案在這 3 個維度"]:
        assert fundnews.is_farm_title(t), t
        assert not fundnews.is_news_title(t), t
    # 股感式產品解析文＝多段「主題？」羅列、不含誘餌詞——正是使用者要的內容，勿誤殺
    assert not fundnews.is_farm_title(_STOCKFEEL_TITLE)
    assert fundnews.is_news_title(_STOCKFEEL_TITLE)


def test_negative_market_titles_filtered():
    """2026-08-12 使用者重申「不要抓負面的文章」：司法之外補市況/績效負面詞。"""
    for t in ["00929 跌破發行價 投資人套牢慘賠", "某基金驚傳清算下市",
              "淨值重挫 基金規模縮水", "高股息ETF淨值腰斬 存股族大虧"]:
        assert fundnews.is_negative_title(t), t
        assert not fundnews.is_news_title(t), t
    assert not fundnews.ptt_relevant("[請益] 00929 套牢該加碼嗎")     # 社群同樣排除
    # 正面/中性報導不受影響
    for t in ["挖掘全球AI產業贏家 主動復華全球50 00409A 8月12日開募",
              "復華兩檔ETF配息出爐", "00929 8月配息維持0.11元"]:
        assert not fundnews.is_negative_title(t), t


def test_fh_products_covers_watchlist_and_upcoming(monkeypatch):
    """產品清單＝追蹤中＋即將登場（募集期的 00409A 型）；他牌不收、未派碼收名稱。"""
    from arm import etfwatch
    monkeypatch.setattr(etfwatch, "watch_tuples", lambda today=None: [
        ("00929", "復華台灣科技優息", "passive", "高股息", "2023/06/01"),
        ("0050", "元大台灣50", "passive", "市值型", "2003/06/25")])
    monkeypatch.setattr(etfwatch, "UPCOMING", [
        {"code": "00409A", "name": "主動復華全球未來50"},
        {"code": None, "name": "復華台美策略精準高息股債平衡ETF基金"},
        {"code": "009999", "name": "他牌新ETF"}])
    prods = fundnews.fh_products()
    assert [p["code"] for p in prods] == ["00929", "00409A", None]
    assert fundnews._fh_codes() == ("00929", "00409A")
    # 代碼同步進 PTT／YouTube 相關性（募集期討論串常只寫代碼）
    assert fundnews.ptt_relevant("[標的] 00409A 主動式ETF 開募討論")
    assert fundnews.yt_relevant("00409A 值得申購嗎？三分鐘看懂")


def test_code_mention_looser_than_code_hit():
    # 媒體標題常把代碼緊貼「ETF」（Yahoo 實例）——產品層要收，社群層嚴格版照舊擋
    t = "瑤池金母又有勁敵！主動式ETF00409A來了 1萬元買到全球前50強"
    assert fundnews._code_mention(t, "00409A")
    assert fundnews.product_item_relevant({"title": t}, "00409A")
    # 編號式前綴與長數字內嵌照樣擋
    assert not fundnews._code_mention("日文單字卡 L#00409A 課程筆記", "00409A")
    assert not fundnews._code_mention("題庫100409A1號解析", "00409A")


def test_fetch_etf_products_groups(monkeypatch):
    """每檔一次查詢（代碼 OR 產品名）；不相關結果濾除；群組帶 code、fund_ids 恆空。"""
    monkeypatch.setattr(fundnews, "fh_products",
                        lambda: [{"code": "00409A", "name": "主動復華全球未來50"}])

    def fake_search(q, days=7, limit=4):
        assert '"00409A" OR "主動復華全球未來50"' == q
        return [{"title": "挖掘全球AI產業贏家 主動復華全球50 00409A 8月12日開募",
                 "url": "https://money.udn.com/money/story/5607/9624031", "source": "經濟日報",
                 "date": "2026-08-11 10:00", "datetime": "2026-08-11T10:00:00+08:00"},
                {"title": "他牌基金廣告文", "url": "https://x/2", "source": "某站",
                 "date": "2026-08-11 09:00", "datetime": "2026-08-11T09:00:00+08:00"}]

    monkeypatch.setattr(fundnews.gnews, "search", fake_search)
    groups = fundnews.fetch_etf_products()
    assert len(groups) == 1
    g = groups[0]
    assert g["code"] == "00409A" and g["fund_ids"] == [] and g["base"] == "主動復華全球未來50"
    assert [i["title"] for i in g["items"]] == ["挖掘全球AI產業贏家 主動復華全球50 00409A 8月12日開募"]


def test_feed_relevant_and_routing_by_code(monkeypatch):
    """股感等全站 feed：代碼命中（不含「復華」字樣）也算相關，並分流進產品群組。"""
    monkeypatch.setattr(fundnews, "fh_products",
                        lambda: [{"code": "00929", "name": "復華台灣科技優息"}])
    assert fundnews.feed_relevant("00929 8月配息出爐")
    assert fundnews.feed_relevant(_STOCKFEEL_TITLE)          # 含「復華」
    assert not fundnews.feed_relevant("台積電法說會前瞻")
    groups = [{"base": "復華台灣科技優息", "code": "00929", "fund_ids": [], "items": []}]
    feeds = [{"title": "00929 8月配息出爐", "url": "https://www.stockfeel.com.tw/x",
              "source": "股感 StockFeel", "datetime": "2026-08-11T08:00:00+08:00"}]
    out = fundnews.route_feeds_to_funds(groups, feeds)
    assert [i["title"] for i in out[0]["items"]] == ["00929 8月配息出爐"]


def test_view_renders_etf_product_tag_without_fund_link():
    """產品群組（fund_ids 空）掛代碼章、不產生壞掉的 #fund- 連結。"""
    doc = {"as_of": "2026/08/12", "window_days": 7, "brand": [],
           "funds": [{"base": "主動復華全球未來50", "code": "00409A", "fund_ids": [],
                      "items": [{"title": "主動復華全球50 00409A 8月12日開募",
                                 "url": "https://money.udn.com/x", "source": "經濟日報",
                                 "date": "2026-08-11 10:00",
                                 "datetime": "2026-08-11T10:00:00+08:00"}]}],
           "social": []}
    html = _fundnews_view(doc)
    assert ">00409A</span>" in html and 'href="#fund-"' not in html
    assert "主動復華全球50 00409A 8月12日開募" in html


# ── 強基金 fundhot（2026-08-12 使用者需求：加入強基金論壇、含金複合等投資方法討論）──

_FUNDHOT_PAGE = """
<nav><a href="/forum/%E8%82%A1%E7%A5%A8%E5%9F%BA%E9%87%91">股票基金討論區</a></nav>
<a href="/forum/%E8%82%A1%E7%A5%A8%E5%9F%BA%E9%87%91/%E9%87%91%E8%A4%87%E5%90%88/7603">
  <span>復華傳家二號、中國新經濟A股、中小精選基金，該併成金複合？還是分開扣？</span></a>
<a href="https://fundhot.com/forum/%E5%85%B6%E4%BB%96/site-news/10688">✍️為何強基金要冒風險花大錢作新網站？</a>
<a href="/forum/%E8%82%A1%E7%A5%A8/00929-talk/9001">00929 配息討論串</a>
<a href="/forum/%E8%82%A1%E7%A5%A8/etf-0050/9002">0050 長期持有心得</a>
<a href="/forum/%E8%82%A1%E7%A5%A8%E5%9F%BA%E9%87%91/%E9%87%91%E8%A4%87%E5%90%88/7603">重複同話題</a>
"""

_FUNDHOT_ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title type="html"><![CDATA[金複合理財機器人進場訊號回測]]></title>
  <link href="https://forum.fundhot.com/viewtopic.php?t=7777"/>
  <category term="股票基金"/><updated>2026-08-11T02:00:00+00:00</updated></entry>
<entry><title>復華傳家二號、中國新經濟A股、中小精選基金，該併成金複合？還是分開扣？</title>
  <link href="https://forum.fundhot.com/viewtopic.php?t=7603"/>
  <updated>2026-08-10T05:00:00+00:00</updated></entry>
<entry><title>半年前的舊討論</title>
  <link href="https://forum.fundhot.com/viewtopic.php?t=100"/>
  <updated>2026-02-01T05:00:00+00:00</updated></entry>
</feed>"""


def test_parse_fundhot_page_extracts_topics():
    out = fundnews.parse_fundhot_page(_FUNDHOT_PAGE)
    # 分類頁連結（兩段、無數字 id）不誤入；同話題去重；board＝分類段解碼
    assert [i["url"][-4:] for i in out] == ["7603", "0688", "9001", "9002"]
    assert out[0]["board"] == "股票基金" and out[0]["platform"] == "fundhot"
    assert out[0]["title"].startswith("復華傳家二號")
    assert fundnews.parse_fundhot_page("") == []


def test_parse_fundhot_feed_window_and_cdata():
    items = fundnews.parse_fundhot_feed(_FUNDHOT_ATOM, days=7000)
    assert [i["url"][-4:] for i in items] == ["7777", "7603", "=100"]
    # 視窗剔除（cutoff 動態算到 2026-05-01，測試不隨執行日漂移）：8 月兩篇留、2 月舊文剔
    days = (datetime.now(timezone.utc) - datetime(2026, 5, 1, tzinfo=timezone.utc)).days
    items_w = fundnews.parse_fundhot_feed(_FUNDHOT_ATOM, days=days)
    assert [i["title"][:3] for i in items_w] == ["金複合", "復華傳"]
    assert items_w[0]["board"] == "股票基金" and items_w[0]["date"] == "2026-08-11"


def test_kinfuhe_brand_term_relevant():
    """金複合（復華投資法/理財機器人）討論常不寫「復華」——品牌詞層要收；
    PTT/YouTube/RSS 同判準。"""
    assert fundnews.ptt_relevant("金複合理財機器人進場訊號回測")
    assert fundnews.yt_relevant("金複合機器人設定教學")
    assert fundnews.feed_relevant("金複合投資法上手心得")
    assert not fundnews.yt_peer_relevant("金複合 vs 0056 比較")   # 自家內容不佔同業層
    assert not fundnews.ptt_relevant("複合材料產業展望")           # 無品牌詞/代碼不收


def test_fetch_fundhot_merges_sources(monkeypatch):
    def fake_get_bytes(url, **kw):
        if "feed.php" in url:
            return _FUNDHOT_ATOM.encode("utf-8")
        if "fundhot.com/forum" in url:
            return _FUNDHOT_PAGE.encode("utf-8")
        raise AssertionError(url)

    monkeypatch.setattr(fundnews, "get_bytes", fake_get_bytes)
    out = fundnews.fetch_fundhot(days=3650)
    titles = [i["title"] for i in out]
    # 新站：金複合話題＋00929 相關收、站務文/0050 不相關剔；feed：同標題跨源去重、新話題補進
    assert any(t.startswith("復華傳家二號") for t in titles)
    assert "00929 配息討論串" in titles
    assert "金複合理財機器人進場訊號回測" in titles
    assert all("新網站" not in t and "0050" not in t for t in titles)
    assert sum(1 for t in titles if t.startswith("復華傳家二號")) == 1

    def broken_page(url, **kw):                  # 新站被擋 → feed 照常（單源失敗不牽連）
        if "feed.php" in url:
            return _FUNDHOT_ATOM.encode("utf-8")
        raise OSError("blocked")

    monkeypatch.setattr(fundnews, "get_bytes", broken_page)
    out2 = fundnews.fetch_fundhot(days=3650)
    assert any(i["title"].startswith("金複合理財機器人") for i in out2)


def test_view_renders_fundhot_row():
    doc = {"as_of": "2026/08/12", "window_days": 7, "brand": [], "funds": [],
           "social": [{"platform": "fundhot", "board": "股票基金",
                       "title": "金複合理財機器人進場訊號回測",
                       "url": "https://fundhot.com/forum/x/y/7777", "date": "2026-08-11"}]}
    html = _fundnews_view(doc)
    assert "強基金・股票基金" in html and "金複合理財機器人進場訊號回測" in html
    assert "PTT・強基金・YouTube" in html          # 社群段標題含新平台
    assert "fundhot.com/forum/x/y/7777" in html


def test_carry_social_covers_fundhot(tmp_path, monkeypatch):
    """強基金來源異常（本次全空）→ 沿用既有項目，同 PTT/YouTube 防呆。"""
    import json
    monkeypatch.setattr(fundnews, "OUT", tmp_path / "fund_news.json")
    old = {"window_days": 7, "brand": [{"title": "舊稿", "source": "經濟日報"}], "funds": [],
           "social": [{"platform": "fundhot", "title": "金複合機器人討論", "board": "股票基金",
                       "url": "https://fundhot.com/forum/a/b/1"}]}
    fundnews.OUT.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    doc = {"window_days": 7, "brand": [{"title": "新稿", "source": "經濟日報"}],
           "funds": [], "social": [], "highlights": []}
    fundnews.save(doc)
    got = json.loads(fundnews.OUT.read_text(encoding="utf-8"))
    assert [s["title"] for s in got["social"]] == ["金複合機器人討論"]


def test_sanitize_scrubs_existing_junk_from_disk_doc():
    """讀取端同一套過濾：既有落檔裡的報價頁/論壇文（舊規則抓的）重建儀表板即消失。"""
    doc = {"window_days": 7,
           "brand": [{"title": "復華投信獲獎", "url": "https://money.udn.com/y",
                      "source": "經濟日報"}],
           "funds": [{"base": "復華全方位基金", "fund_ids": ["15"], "items": [
               {"title": "復華全方位基金A類型 的總覽 | 鉅亨網",
                "url": "https://invest.cnyes.com/funds/detail/x", "source": "鉅亨網"},
               {"title": "規模破百億的科技巨獸：復華全球物聯網與華人世紀該怎麼選？",
                "url": "https://www.cmoney.tw/forum/article/1", "source": "CMoney"}]}],
           "social": [{"platform": "ptt", "title": "[心得] 00929 套牢慘賠中", "push": 5}]}
    out = fundnews.sanitize(doc)
    assert out["brand"] and not out["funds"][0]["items"]
    assert out["social"] == []                               # 負面社群討論同步濾除


def test_stale_announcement_recrawl_filtered():
    """2026-08-17 使用者抓包：中租基智網民國111年「台灣好收益暫停銷售」公告被 Google
    重標成 08-16 上版。三層都要擋：ezfunds URL 整站、暫停銷售公告詞、標題自帶舊年代。"""
    from datetime import datetime
    from arm.clock import TW_TZ
    t = "「復華台灣好收益基金」自111年1月3日起至111年2月9日暫停銷售"
    assert not fundnews.is_news_title(t)                      # 公告詞＋舊年代雙殺
    assert fundnews._title_stale_year(t, datetime(2026, 8, 17, tzinfo=TW_TZ))
    assert fundnews._JUNK_URL.search(
        "https://www.ezfunds.com.tw/Article/AnnouncementDetail?RootId=7347")
    # 讀取端同一套：既有落檔的這則重建即消失
    doc = {"funds": [{"base": "復華台灣好收益", "items": [
        {"title": t, "url": "https://www.ezfunds.com.tw/Article/x", "source": "ezfunds.com.tw"}]}]}
    assert fundnews.sanitize(doc)["funds"][0]["items"] == []
    # 不誤殺：引述舊年份的當期新聞（年後非月份/年度）、正常帶今年月份的新聞
    now = datetime(2026, 8, 17, tzinfo=TW_TZ)
    for ok in ["台股創2020年以來最大單週漲幅 復華ETF受惠",
               "復華發達基金2026年7月報酬亮眼",
               "復華中小精選115年度配息出爐"]:
        assert not fundnews._title_stale_year(ok, now), ok
    # 民國/西元舊日期式樣都要認
    assert fundnews._title_stale_year("復華某基金2022年3月合併說明會", now)


def test_japanese_youtube_filtered():
    """2026-08-17 使用者回報：日文頻道「両学長」米国高配当株ETF 解說誤入市場熱門層——
    日文標題含漢字（_has_cjk 擋不住）又滿是主題詞。假名（「の」除外）＝日文、剔除；
    抓取端（yt_peer_relevant/yt_relevant）與讀取端（sanitize）都要擋。"""
    jp = "【保存版】学長が解説！米国高配当株ETFの基礎【お金の勉強 株式投資編】：（アニメ動画）第526回"
    assert fundnews._is_japanese(jp)
    assert not fundnews.yt_peer_relevant(jp)
    assert not fundnews.yt_relevant(jp + " 00929")            # 帶自家代碼的日文影片同樣不收
    # 指名黑名單＋讀取端：既有落檔沿用款重建即消失
    doc = {"social": [
        {"platform": "youtube", "title": jp, "channel": "両学長 リベラルアーツ大学",
         "url": "https://www.youtube.com/watch?v=FAkMraqLuko", "views": 99073, "peer": True},
        {"platform": "youtube", "title": "00929 高股息ETF 8月配息解析",
         "url": "https://www.youtube.com/watch?v=zzzzzzzzzzz", "views": 8000, "peer": True}]}
    out = fundnews.sanitize(doc)
    assert [s["title"] for s in out["social"]] == ["00929 高股息ETF 8月配息解析"]
    # 不誤殺：台灣標題（含商品名風格用字「の」；「・」「ー」是片假名區段的記號、
    # 台灣標題極常用——首版整段範圍誤殺、YouTube 從 14 支砍剩 1 支，此處鎖回歸）
    for ok in ["00929 高股息ETF 8月配息公告", "植物の優 代言人談定期定額",
               "台股ETF 台積電權重過半怎麼辦", "高股息ETF大解密・00919 vs 00929",
               "台股大盤解析ー AI供應鏈續強？", "存股族必看｜ETF月月配"]:
        assert not fundnews._is_japanese(ok), ok
    # 帶「・」「ー」的台灣影片要通過各層判準（誤殺回歸的實際受害路徑；
    # 00929 屬自家代碼歸相關層、0056/00878 同業歸熱門層）
    assert fundnews.yt_peer_relevant("高股息ETF大解密・0056 vs 00878")
    assert fundnews.yt_peer_relevant("台股大盤解析ー AI供應鏈續強？")
    assert fundnews.yt_relevant("復華00929解析・8月配息出爐")
