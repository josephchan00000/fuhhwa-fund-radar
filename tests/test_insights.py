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


def test_column_leaders_positive_only():
    rows = fund_insights.overview_rows(_funds())
    leads = fund_insights.column_leaders(rows, keys=("chg",), top=1)
    assert ("2", "chg") in leads and ("1", "chg") not in leads   # 負值不算領先


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


def test_talk_script_clean_and_neutral():
    links = fund_insights.news_fund_links(_funds(), _NEWS)
    text, hits = fund_insights.talk_script(links[0], "2026/05/31")
    assert hits == []                                 # 模板不得踩禁用詞
    assert "非投資建議" in text and "過去績效不代表未來" in text
    assert "Micron" in text and "3.63%" in text and "2026/05/31" in text


def test_fund_intro_copy_fields():
    txt = fund_insights.fund_intro_copy(_funds()[0])
    assert "復華甲基金-新臺幣" in txt and "NAV 50.0" in txt
    assert "MICRON TECHNOLOGY INC 3.63%" in txt
    assert "非投資建議" in txt                         # 免責必附


def test_futu_url_markets():
    assert fund_insights.futu_url("MU", "美國") == "https://www.futunn.com/stock/MU-US"
    assert fund_insights.futu_url("600183", "中國") == "https://www.futunn.com/stock/600183-SH"
    assert fund_insights.futu_url("300308", "中國") == "https://www.futunn.com/stock/300308-SZ"
    assert fund_insights.futu_url("688498", "中國") == "https://www.futunn.com/stock/688498-SH"
    assert fund_insights.futu_url("000660", "韓國") is None    # 韓/日/台格式不確定 → 不亂連
    assert fund_insights.futu_url("2330", "臺灣") is None
    assert fund_insights.futu_url(None, "美國") is None


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
    assert "--bg:#eef1f6" in html                                   # 專業冷色調主題（2026-07-18 去米色）
    assert 'class="topbar"' in html          # 列印功能已整組移除（2026-07-20 使用者指示）
    assert 'th class="sk"' in html                     # 可排序表頭
    assert "data-copy=" in html                        # 複製鈕
    assert 'class="openbtn2"' in html                  # 逐則展開/收合按鈕（可點性）
    assert "--hl:#153a7a" in html and "--hlbg:#dce7fa" in html  # 新聞重點藍色標注（專業配色）


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
