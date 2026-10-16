"""fund_insights（跨基金洞察層）＋ usnews/twnews 結構化萃取 ＋ 新版儀表板 render 單測（離線）。"""
from datetime import date

from arm import fund_dashboard, fund_insights, fund_intro, twnews, usnews


# ── 假資料 ───────────────────────────────────────────────────
def _funds():
    return [
        {"fund_id": "1", "name": "復華甲基金-新臺幣", "short_name": "甲新臺幣",
         "group_label": "全球股票型", "nav": 50.0, "nav_date": "2026/07/01",
         "nav_change_pct": "-3.43%", "size_twd": 5.3e9, "risk_level": "RR4",
         "returns": {"ytd": "69.73%", "3m": "65.28%", "6m": "69.73%",
                     "1y": "101.02%", "3y": "154.28%", "since": "372.20%"},
         "as_of": "2026/05/31", "dist_date": "2026/07/05",
         "top_holdings": [{"name": "MICRON TECHNOLOGY INC", "weight": 3.63},
                          {"name": "大量", "weight": 2.0}]},
        {"fund_id": "2", "name": "復華乙基金", "short_name": "乙",
         "group_label": "全球股票型", "nav": 20.0, "nav_date": "2026/07/01",
         "nav_change_pct": "+0.44%", "size_twd": None, "risk_level": "RR5",
         "returns": {"ytd": "106.30%", "1y": "184.30%", "3y": "—"},
         "as_of": "2026/05/31",
         "top_holdings": [{"name": "台積電", "weight": 8.0}]},
    ]


_NEWS = """## 🔹Top 3 新聞卡

### 卡 1｜美光財報優於預期，記憶體族群大漲（來源：Reuters｜2026/07/01｜【新消息】）
1. **新聞摘要**：Micron 公布財報，DRAM 需求強勁；此外市場出現大量買盤。
2. **一句話重點**：記憶體景氣回溫。

### 卡 2｜TSMC 先進製程滿載（來源：Bloomberg｜2026/07/01｜【新消息】）
1. **新聞摘要**：台積電 CoWoS 產能滿載。
2. **一句話重點**：先進封裝供不應求。

---

## 🔹次級觀察摘要
- **雜訊**：這段不是新聞卡，提到 AMD 也不應被計入卡片。
"""


# ── parse / overview / movers / averages ─────────────────────
def test_parse_pct():
    assert fund_insights.parse_pct("78.42%") == 78.42
    assert fund_insights.parse_pct("-2.13%") == -2.13
    assert fund_insights.parse_pct(64.07) == 64.07
    assert fund_insights.parse_pct("—") is None
    assert fund_insights.parse_pct(None) is None


def test_overview_rows_numeric_and_missing():
    rows = fund_insights.overview_rows(_funds())
    assert rows[0]["chg"] == -3.43 and rows[0]["ytd"] == 69.73
    assert rows[0]["size_e8"] == 53.0 and rows[0]["conc"] == 5.6
    assert rows[1]["y3"] is None and rows[1]["size_e8"] is None   # '—'／缺規模 → None


def test_movers_best_worst():
    best, worst = fund_insights.movers(_funds())
    assert best["fund_id"] == "2" and worst["fund_id"] == "1"
    assert fund_insights.movers([]) == (None, None)
    # 僅一檔有值 → 最弱為 None（不重複同一檔）
    one, none = fund_insights.movers(_funds()[:1])
    assert one["fund_id"] == "1" and none is None


def test_group_averages_skips_missing():
    g = fund_insights.group_averages(_funds())["全球股票型"]
    assert g["ytd"] == round((69.73 + 106.30) / 2, 2)
    assert g["3y"] == 154.28                          # 乙的 3y 為 '—'，只平均現有值


def test_column_extremes_marks_four_kinds():
    rows = [
        {"fund_id": "a", "group_label": "G", "chg": 5.0},
        {"fund_id": "b", "group_label": "G", "chg": 1.2},
        {"fund_id": "c", "group_label": "G", "chg": 3.0},
        {"fund_id": "d", "group_label": "G", "chg": -4.0},
        {"fund_id": "e", "group_label": "G", "chg": -0.5},
        {"fund_id": "f", "group_label": "G", "chg": None},
    ]
    m = fund_insights.column_extremes(rows, keys=("chg",))
    assert m[("a", "chg")] == "ld-up1"        # 漲最多
    assert m[("b", "chg")] == "ld-up0"        # 漲最少
    assert m[("d", "chg")] == "ld-dn1"        # 跌最多
    assert m[("e", "chg")] == "ld-dn0"        # 跌最少
    assert ("c", "chg") not in m and ("f", "chg") not in m


def test_column_extremes_single_value_no_double_mark():
    rows = [{"fund_id": "a", "group_label": "G", "chg": 5.0},
            {"fund_id": "b", "group_label": "G", "chg": -1.0}]
    m = fund_insights.column_extremes(rows, keys=("chg",))
    assert m == {("a", "chg"): "ld-up1", ("b", "chg"): "ld-dn1"}   # 各僅一檔→不再標「最少」


def test_inception_ret_pct_new_fund_from_issue_price():
    from arm import clock
    y = clock.today_tw().year
    d = {"nav": 9.47, "inception": f"{y}/06/30", "returns": {"ytd": "—"}}
    assert fund_insights.inception_ret_pct(d) == -5.3              # (9.47/10−1)×100
    # 官網已揭露 ytd → 不啟用；非今年成立 → 不啟用；缺 NAV → 不啟用
    assert fund_insights.inception_ret_pct({**d, "returns": {"ytd": "3.1%"}}) is None
    assert fund_insights.inception_ret_pct({**d, "inception": f"{y-1}/06/30"}) is None
    assert fund_insights.inception_ret_pct({**d, "nav": None}) is None


def test_overview_rows_ytd_falls_back_to_inception():
    from arm import clock
    y = clock.today_tw().year
    funds = [{"fund_id": "9", "name": "復華丙指數基金", "short_name": "丙",
              "group_label": "國內股票型", "nav": 9.47, "nav_date": f"{y}/07/21",
              "nav_change_pct": "+1.00%", "inception": f"{y}/06/30",
              "returns": {"ytd": "—", "since": "—"}, "risk_level": "RR4"}]
    r = fund_insights.overview_rows(funds)[0]
    assert r["ytd"] == -5.3 and r["ytd_est"] is True


# ── usnews 結構化萃取 ────────────────────────────────────────
def test_extract_indices():
    md = ("- **那斯達克綜合指數（Nasdaq）**：指數約收 26,040.03、下跌約 0.66%（來源）。\n"
          "- **費城半導體指數（SOX）**：全日重挫，指數約收 13,478.45、下跌約 5.39%。\n"
          "- **標普 500 指數（S&P 500）**：小幅收低，約收 7,483.23、下跌約 0.22%。\n"
          "- **市場解析（主題動能）**：資金輪動，無指數數字。\n")
    ix = usnews.extract_indices(md)
    assert [i["label"] for i in ix] == ["Nasdaq", "費半 SOX", "S&P 500"]
    assert ix[1]["pct"] == 5.39 and ix[1]["up"] is False
    assert usnews.extract_indices("") == []


def test_extract_cards_v1_and_v2():
    cards = usnews.extract_cards(_NEWS)
    assert len(cards) == 2                            # 次級觀察不是卡
    assert cards[0]["title"].startswith("美光財報優於預期")   # 尾端（來源…）已去除
    assert cards[0]["oneline"] == "記憶體景氣回溫"
    v2 = "## 一、Meta 建雲端業務（來源：Bloomberg，2026/07/01）\n2. **一句話**：算力變現。\n"
    c2 = usnews.extract_cards(v2)
    assert c2[0]["title"] == "Meta 建雲端業務" and c2[0]["oneline"] == "算力變現"


def test_extract_cards_move_field():
    # 「漲跌分析」欄（2026-08-19 使用者需求：每卡加一欄大漲/大跌歸因）→ move
    md = ("### 卡 1｜台積電法說（來源：經濟日報｜2026/08/20｜【新事件】｜重要度 8/10）\n"
          "1. **新聞摘要**：略。\n"
          "3. **漲跌分析**：台積電大漲 **4.2%**，主因法說上修財測；次因外資回補。\n"
          "4. **對持股／族群影響**：略。\n")
    c = usnews.extract_cards(md)[0]
    assert c["move"].startswith("台積電大漲") and "主因" in c["move"]
    # 舊報告無此欄 → 空字串、其餘欄位不受影響（向後相容）
    old = usnews.extract_cards("### 卡 1｜舊卡（來源：X｜2026/07/02）\n1. **新聞摘要**：略。\n")[0]
    assert old["move"] == "" and old["summary"] == "略。"


# ── 新聞 × 持股連動 ──────────────────────────────────────────
def test_news_fund_links_alias_and_bare_false():
    links = fund_insights.news_fund_links(_funds(), _NEWS)
    assert len(links) == 2
    m1 = {m["name"] for m in links[0]["matched"]}
    assert m1 == {"MICRON TECHNOLOGY INC"}           # 別名 Micron 命中；『大量』(bare=false) 不因常用詞誤中
    m2 = {m["name"] for m in links[1]["matched"]}
    assert m2 == {"台積電"}                           # TSMC 與『台積電』別名皆可
    f = links[0]["matched"][0]["funds"][0]
    assert f["fund_id"] == "1" and f["weight"] == 3.63


def test_news_fund_links_ascii_word_boundary():
    funds = [{"fund_id": "9", "short_name": "丙", "group_label": "全球股票型",
              "top_holdings": [{"name": "ADVANCED MICRO DEVICES", "weight": 2.9}]}]
    md = "### 卡 1｜XAMDX 不是 AMD（來源）\n1. **新聞摘要**：字串 SAMD、AMDS 均不應命中。\n"
    hits = fund_insights.news_fund_links(funds, md)[0]["matched"]
    assert {m["name"] for m in hits} == {"ADVANCED MICRO DEVICES"}   # 只有獨立字 AMD 命中


def test_stock_url_all_markets_clickable():
    # 每個市場都要能產出可點的外部行情頁（Yahoo Finance）——不再「有些有連結、有些沒有」
    assert fund_insights.stock_url("AAPL", "美國") == "https://finance.yahoo.com/quote/AAPL"
    assert fund_insights.stock_url("2891", "臺灣") == "https://tw.stock.yahoo.com/quote/2891"
    assert fund_insights.stock_url("5347", "台灣") == "https://tw.stock.yahoo.com/quote/5347"
    assert fund_insights.stock_url("6981", "日本") == "https://finance.yahoo.com/quote/6981.T"
    assert fund_insights.stock_url("285A", "日本") == "https://finance.yahoo.com/quote/285A.T"  # 新制英數碼
    assert fund_insights.stock_url("005930", "韓國") == "https://finance.yahoo.com/quote/005930.KS"
    assert fund_insights.stock_url("600183", "中國") == "https://finance.yahoo.com/quote/600183.SS"
    assert fund_insights.stock_url("300308", "中國") == "https://finance.yahoo.com/quote/300308.SZ"
    assert fund_insights.stock_url("688012", "中國") == "https://finance.yahoo.com/quote/688012.SS"
    # 有代號但市場格式不確定 → 退回搜尋頁（仍可點）
    assert "lookup" in fund_insights.stock_url("XYZ", "泰國")
    # 缺代號但有名稱 → 以名稱搜尋（保證可點）
    assert "lookup" in fund_insights.stock_url(None, "美國", "SOME CORP")
    # 全缺才回 None
    assert fund_insights.stock_url(None, None) is None


def test_upcoming_distributions_window():
    fs = _funds()
    assert fund_insights.upcoming_distributions(fs, today=date(2026, 7, 2)) == \
        [{"short_name": "甲新臺幣", "dist_date": "2026/07/05"}]
    assert fund_insights.upcoming_distributions(fs, today=date(2026, 7, 6)) == []   # 已過不提醒
    assert fund_insights.upcoming_distributions(fs, today=date(2026, 6, 20)) == []  # 太遠不提醒


# ── twnews（台股盤後）─────────────────────────────────────────
def test_twnews_extract_indices_tw_labels():
    md = ("- **加權指數（TAIEX）**：終場收 46,744.16、下跌約 0.58%（-274.83 點）。\n"
          "- **櫃買指數（OTC）**：逆勢收 439.51、上漲約 1.92%（+8.28 點）。\n")
    ix = twnews.extract_indices(md)
    assert [i["label"] for i in ix] == ["加權指數", "櫃買指數"]
    assert ix[0]["up"] is False and ix[1]["pct"] == 1.92


def test_twnews_load_latest_shape():
    tw = twnews.load_latest()
    if tw is not None:                                 # repo 內有產出時驗形狀與合規
        assert tw["date"] and tw["md"]
        assert tw["mode"] in ("pre", "post") and tw["label"]
        assert isinstance(tw["banned_hits"], list) and not tw["banned_hits"]


def test_twnews_session_mode():
    from datetime import datetime
    tz = twnews.TW_TZ
    assert twnews.session_mode(datetime(2026, 7, 3, 8, 30, tzinfo=tz)) == "pre"    # 開盤前
    assert twnews.session_mode(datetime(2026, 7, 3, 11, 0, tzinfo=tz)) == "pre"    # 盤中
    assert twnews.session_mode(datetime(2026, 7, 3, 14, 0, tzinfo=tz)) == "post"   # 收盤後
    assert twnews.session_mode(datetime(2026, 7, 4, 10, 0, tzinfo=tz)) == "post"   # 週六
    assert twnews.spec_for("pre") == twnews.SPEC_PRE and "盤前" in twnews.SPEC_PRE
    assert twnews.spec_for("post") == twnews.SPEC_POST


def test_twnews_mode_from_title():
    assert twnews._mode_of("# 〈台股盤前重點〉\n") == "pre"
    assert twnews._mode_of("# 〈台股盤後重點〉\n") == "post"


def test_tw_group_labels_present():
    for g in ("tw_equity", "tw_balanced", "tw_fof"):
        assert g in fund_intro.GROUP_LABEL


def test_pending_funds_have_group_label():
    for p in fund_intro.pending_funds():               # 待抓取者必有組別標籤（總覽分組用）
        assert p["fund_id"] and p["group_label"]


# ── 儀表板 render（吃 repo 內真實資料，離線） ──────────────────
def test_render_sections_order_and_taiwan_colors():
    html = fund_dashboard.render()
    secs = ['id="brief"', 'id="news"',
            'id="overview"', 'id="details"']
    idx = [html.find(s) for s in secs]
    assert all(i >= 0 for i in idx)
    assert idx == sorted(idx)                          # 順序：今日重點→新聞→總覽→詳情
    assert 'id="newslinks"' not in html                # 當日焦點個股區已移除（2026-07-15）
    assert 'id="newsdigest"' not in html               # 新聞重點與全文已合併為單一「新聞」區
    assert 'class="newsone"' in html                   # 逐則新聞收合塊（合併後）
    assert html.count("<details") >= 3                 # 每則新聞各一收合塊（預設收合）
    assert 'class="ngpts"' in html                     # 展開內含影響分析條列
    assert 'class="nglink' in html                     # 展開內含原文連結
    assert "--gain:#d33a34" in html and "--loss:#1f9d57" in html    # 紅漲綠跌（保留台灣慣例）
    assert "--bg:#ffffff" in html                                   # 富途式扁平白底（2026-07-22 去卡片框）
    assert ".section{background:none;border:0" in html              # 區塊不再是卡片、內容全寬
    assert 'class="topbar"' in html          # 列印功能已整組移除（2026-07-20 使用者指示）
    assert 'th class="sk"' in html                     # 可排序表頭
    assert "data-copy=" not in html                    # 複製基金介紹鈕已移除（2026-07-22 使用者指示）
    assert 'class="openbtn2"' in html                  # 逐則展開/收合按鈕（可點性）
    assert "--hl:#153a7a" in html and "--hlbg:#dce7fa" in html  # 新聞重點藍色標注（2026-07-22 使用者指示由紅色系改回原藍）


def test_render_market_views():
    html = fund_dashboard.render()
    assert 'class="mkswitch"' in html                  # 左上台股/全球切換
    assert html.count('data-mkt="tw"') >= 5 and html.count('data-mkt="gl"') >= 5  # 焦點個股區移除後少一組雙視圖
    assert 'id="mkt-tw" checked' in html and 'id="mkt-gl"' in html   # 純 CSS radio（JS 停用也能切）
    assert '#mkt-gl:checked ~ * .mkt[data-mkt="tw"]{display:none}' in html
    assert 'class="nglink"' in html or "無原文連結" in html   # 新聞重點卡的來源連結
    assert "可講素材" not in html                       # 話術已移除
    assert "當日焦點個股" not in html                   # 焦點個股區已移除（2026-07-15）


def test_scrub_removes_invisible():
    assert usnews.scrub("a​b‏ c﻿") == "ab c"
    cards = usnews.extract_cards("### 卡 1｜標題（來源：X｜2026/07/02）\n"
                                 "1. **新聞摘要**：內容 [媒體](https://x.tw/a)。\n")
    assert cards[0]["meta"].startswith("來源：X")
    assert cards[0]["summary"].startswith("內容")
    assert cards[0]["links"] == [("媒體", "https://x.tw/a")]


def test_render_short_name_strips_suffix():
    assert fund_dashboard._short("復華美國新星基金-新臺幣") == "美國新星基金"
    assert fund_dashboard._short({"short_name": "全球平衡新臺幣"}) == "全球平衡"
    assert fund_dashboard._short("復華復華基金") == "復華基金"      # 只去品牌前綴一次


def test_pct_span_taiwan_convention():
    assert 'class="gain"' in fund_dashboard._pct_span(1.5)          # 漲＝gain（紅）
    assert 'class="loss"' in fund_dashboard._pct_span(-1.5)         # 跌＝loss（綠）
    assert "—" in fund_dashboard._pct_span(None)


def test_holdings_table_prefers_profile_url_for_funds():
    # 基金型持有無掛牌代號，Yahoo 名稱搜尋必落空（2026-08-12 使用者：「點進去沒東西」）
    # → profile 的 url（鉅亨基金資訊頁）優先於 ticker/country 產的 Yahoo 連結
    doc = {"group": "tw_fof", "top_holdings": [
        {"name": "統一黑馬證券投資信託基金", "weight": 6.08, "sector": None,
         "url": "https://fund.cnyes.com/detail/x/A09003", "ticker": None, "country": "臺灣"},
        {"name": "元大台灣50", "weight": 8.75, "sector": None,
         "url": None, "ticker": "0050", "country": "臺灣"}]}
    out = fund_dashboard._holdings_table(doc, set())
    assert 'href="https://fund.cnyes.com/detail/x/A09003"' in out    # 基金 → 鉅亨頁
    assert "Anue鉅亨" in out
    assert 'href="https://tw.stock.yahoo.com/quote/0050"' in out     # ETF → 照舊 Yahoo 直連


def test_fund_card_alloc_blocks_fof_vs_regular():
    # 組合型：只有資產配置 → 渲染「資產配置」且不留懸空的空產業配置
    doc_fof = {"fund_id": "22", "group": "global_fof", "group_label": "全球組合型",
               "asset_alloc": [{"name": "股票型基金", "weight": 62.4}],
               "country_alloc": [], "sector_alloc": [], "top_holdings": [], "returns": {}}
    out = fund_dashboard._fund_card(doc_fof, {}, set())
    assert "資產配置" in out and "股票型基金" in out
    assert "產業配置" not in out
    # 一般海外基金：國家＋產業照舊、無資產配置標題
    doc_reg = {"fund_id": "47", "group": "global_equity", "group_label": "全球股票型",
               "country_alloc": [{"name": "美國", "weight": 60.8}],
               "sector_alloc": [{"name": "資訊技術", "weight": 50.0}],
               "top_holdings": [], "returns": {}}
    out2 = fund_dashboard._fund_card(doc_reg, {}, set())
    assert "國家配置" in out2 and "產業配置" in out2 and "資產配置" not in out2
