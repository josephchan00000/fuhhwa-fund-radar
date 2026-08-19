"""復華基金追蹤版本新模組單測：fhfund 解析（純函式）、usnews 合規/日期、fund_intro 組裝。"""
from datetime import date

import pytest

from arm import fund_dashboard, fund_intro, usnews
from arm.connectors import fhfund


# ── fhfund 純解析 ─────────────────────────────────────────────
def test_pct_and_num():
    assert fhfund._pct("4.58%") == 4.58
    assert fhfund._pct("60.76 %") == 60.76
    assert fhfund._pct("—") is None
    assert fhfund._num("5,296,363,360.00") == 5296363360.0


def test_holdings_table_parse():
    html = """
    <h3>十大持有標的</h3>
    <table class="fundTable"><thead><tr><th>類型</th><th>名稱</th><th>投資比例</th></tr></thead>
    <tbody>
      <tr><td>資訊技術</td><td>SANDISK CORP</td><td><span>4.58%</span></td></tr>
      <tr><td>資訊技術</td><td>聯發科</td><td><span>3.78%</span></td></tr>
    </tbody></table>"""
    rows = fhfund._rows_of_table_after(html, "十大持有標的")
    assert rows[0][1] == "SANDISK CORP"
    assert rows[1][2].startswith("3.78")


def test_fof_holdings_table_parse(monkeypatch):
    # 組合型頁面：標題措辭不同（十大持有基金）且無產業欄（2 欄：名稱｜比例）
    # ——2026-08-12 使用者反映組合型抓不到，舊版只認「十大持有標的」＋3 欄
    html = """
    <h3>十大持有基金</h3>
    <table class="fundTable"><thead><tr><th>基金名稱</th><th>投資比例</th></tr></thead>
    <tbody>
      <tr><td>復華全球大趨勢基金</td><td><span>18.50%</span></td></tr>
      <tr><td>iShares 安碩核心標普500 ETF</td><td><span>12.30%</span></td></tr>
    </tbody></table>
    <div>資料日期：<span>2026/06/30</span></div>"""
    monkeypatch.setattr(fhfund, "get_bytes", lambda *a, **k: html.encode("utf-8"))
    out = fhfund.fetch_holdings("22")
    assert [h["name"] for h in out["top_holdings"]] == \
        ["復華全球大趨勢基金", "iShares 安碩核心標普500 ETF"]
    assert out["top_holdings"][0]["weight"] == 18.5
    assert out["top_holdings"][0]["sector"] is None      # 組合型無產業欄
    # 一般基金的 3 欄表仍走原路（標題優先序在前，不互相干擾）
    html2 = """
    <h3>十大持有標的</h3>
    <table class="fundTable"><tbody>
      <tr><td>資訊技術</td><td>聯發科</td><td>3.78%</td></tr>
    </tbody></table>"""
    monkeypatch.setattr(fhfund, "get_bytes", lambda *a, **k: html2.encode("utf-8"))
    out2 = fhfund.fetch_holdings("06")
    assert out2["top_holdings"] == [{"sector": "資訊技術", "name": "聯發科", "weight": 3.78}]


def test_svg_alloc_pairs():
    # 值先、標籤後（平行對位），比照官網 server-rendered SVG
    html = ('國家配置'
            '<text>60.76 %​60.76 %</text><text>16.71 %​16.71 %</text>'
            '<text>美國</text><text>臺灣</text>'
            '產業配置 十大持有標的')
    pairs = fhfund._svg_pairs(html, "國家配置", "產業配置")
    assert pairs == [{"name": "美國", "weight": 60.76}, {"name": "臺灣", "weight": 16.71}]


# ── usnews 合規 / 日期 ────────────────────────────────────────
def test_compliance_flags_banned():
    assert "目標價" in usnews.compliance_scan("這檔的目標價很高")
    assert usnews.compliance_scan("績效說明") == []


def test_compliance_allows_disclosure_negation():
    # 強制揭露段含「不保證」不應被判為違規
    assert usnews.compliance_scan(usnews.DISCLOSURE) == []


def test_us_session_skips_weekend():
    # 2026-07-06 是週一 → 昨夜美股對應到上週五 2026-07-03
    assert usnews.us_session_date(date(2026, 7, 6)) == date(2026, 7, 3)
    # 週四 → 前一日週三
    assert usnews.us_session_date(date(2026, 7, 2)) == date(2026, 7, 1)


def test_specs_present():
    assert "重要度" in usnews.SPEC_V1 and "精簡版" in usnews.SPEC_V2
    assert "【新事件】" in usnews.SPEC_V1 and "至少 4 則" in usnews.SPEC_V1   # 多找、標事件屬性
    assert usnews.BANNED and "保證" in usnews.BANNED


def test_macro_spec_and_section():
    from arm import macronews, fund_dashboard as fd
    # 政策面規格：含三大範圍＋新標準（重要度/新事件/多找）
    s = macronews.SPEC_MACRO
    assert "川普" in s and "聯準會" in s and "重要度" in s and "【新事件】" in s and "至少 4 則" in s
    # 儀表板：總經為左上三分頁之一（總經/台股/全球），內含政策區塊
    html = fd.render()
    assert 'id="mkt-macro"' in html and 'for="mkt-macro">總經' in html   # 三分頁切換鈕
    assert 'class="macroview"' in html and 'class="fundview"' in html    # 分頁視圖容器
    assert 'id="macro"' in html and "政策新聞" in html
    assert 'id="macro-ov"' in html and "政策總覽" in html   # 總覽/新聞拆兩區塊（2026-07-15）
    # 總經頁含「本週行事曆」子區塊與總經專屬導覽（非死按鈕）
    assert 'id="macro-cal"' in html and 'tb-nav-macro' in html and "本週行事曆" in html


def test_weekend_note_merged_window():
    # 2026-07-06（一）：須綜合週五晚間＋週六＋週日整個週末
    n = usnews.weekend_note(date(2026, 7, 6))
    assert "週一" in n and "週六與週日" in n and "綜合整理" in n
    # 週日：涵蓋週五晚間＋週六；週六：涵蓋週五晚間起
    assert "週六全日" in usnews.weekend_note(date(2026, 7, 5))
    assert usnews.weekend_note(date(2026, 7, 4)).startswith("【週末合併時窗】")
    # 平日（週二~週五）不加註
    assert usnews.weekend_note(date(2026, 7, 7)) == ""


def test_calendar_anchor_states_weekday_and_holiday():
    # 週二 07/07：明確錨定今日星期二、對應昨夜美股為週一 07/06（正常交易日）
    a = usnews.calendar_anchor(date(2026, 7, 7))
    assert "2026/07/07（週二）" in a and "2026/07/06（週一）" in a
    # 週一 07/06：us_session_date 給週五 07/03，但 07/03 為國慶補假休市，
    # 錨定須往回指到真實交易日 07/02（週四）並註明 07/03 休市
    b = usnews.calendar_anchor(date(2026, 7, 6))
    assert "2026/07/02（週四）" in b and "07/03" in b and "休市" in b


def test_prior_block_lists_reported_titles(tmp_path):
    # prior_titles 讀『日期 < today』最新一份、抽卡標題；prior_block 格式化成「勿重收」清單
    (tmp_path / "2026-07-05.md").write_text(
        "# 報告\n\n### 卡 1｜台積電營收創高（來源：X｜2026/07/05｜【新事件】｜重要度 8/10）\n"
        "1. **新聞摘要**：略。\n", encoding="utf-8")
    titles = usnews.prior_titles(tmp_path, date(2026, 7, 7))
    assert titles == ["台積電營收創高"]
    block = usnews.prior_block(titles, "前一日測試")
    assert "勿原樣重收" in block and "台積電營收創高" in block and "【延伸】" in block
    # 沒有更早檔案時回空、prior_block 回空字串（提示包會略過）
    assert usnews.prior_titles(tmp_path, date(2026, 7, 4)) == []
    assert usnews.prior_block([]) == ""
    assert usnews.weekend_note(date(2026, 7, 3)) == ""


def test_cal_spec_covers_regions_and_earnings():
    # 行事曆版型須涵蓋美／歐／中／日與重要企業財報（2026-07-05 使用者需求）
    from arm import macronews
    s = macronews.SPEC_CAL
    assert "歐" in s and "ECB" in s and "中" in s and "日銀" in s and "財報" in s
    assert "美：／歐：／中：／日：／財報：" in s
    assert "本週重點財經行事曆" in s


def test_macro_calendar_parsing():
    from arm import macronews
    md = (
        "# 本週重點財經行事曆（06/29–07/03）\n"
        "> 更新：2026/07/03；美股 7/3 因國慶假期休市\n\n"
        "| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n"
        "|---|---|---|---|---|---|\n"
        "| 07/02 | 美：6月非農就業 | +11.5萬 | +5.7萬 | +14.4萬 | 已公布 |\n"
        "| 07/03 | 美股國慶假期休市 | — | — | — | 休市 |\n"
        "| 07/08 | 歐：歐元區5月零售銷售 | +0.2% | — | +0.1% | 未公布 |\n"
        "| 07/09 | 財報：台積電 Q2 法說 | — | — | — | 未公布 |\n"
    )
    rows = macronews._parse_cal_rows(md)
    assert [r["status"] for r in rows] == ["已公布", "休市", "未公布", "未公布"]  # 表頭/分隔列不計入
    # 地區前綴 → region 欄；item 去前綴（儀表板顯示徽章用）
    assert rows[0]["item"] == "6月非農就業" and rows[0]["region"] == "美" and rows[0]["actual"] == "+5.7萬"
    assert rows[1]["region"] == ""                       # 休市列無前綴
    assert rows[2]["region"] == "歐" and rows[3]["region"] == "財報"
    assert "休市" in macronews._cal_note(md)


def test_market_status_chips_two_views():
    # 「市況」段 → 台股視圖只列台股本身、全球視圖列美股＋日韓陸港（2026-07-22 使用者需求）
    from arm import fund_dashboard as fd
    note = ("更新：2026/07/22；市況：台股 正常交易｜美股 正常交易｜日股 7/20 海之日休市｜"
            "韓股 正常交易｜陸股 正常交易｜港股 正常交易；已公布：中國 7 月 LPR 續持")
    tw, gl = fd._market_status(note)
    assert tw == "本週台股正常交易、無國定假日休市"
    assert gl == "本週日股 7/20 海之日休市；美股、韓股、陸股、港股正常交易"
    # 台股有休市時直接列休市日；全市場正常時句尾補「無國定假日休市」（比照原美股句式）
    tw3, gl3 = fd._market_status("市況：台股 9/28 因教師節休市｜美股 正常交易｜日股 正常交易")
    assert tw3 == "本週台股 9/28 因教師節休市"
    assert gl3 == "本週美股、日股正常交易、無國定假日休市"
    assert "已公布" not in gl                       # 市況 chip 不夾帶其餘引言
    # 舊格式（無市況段）回退：取含「休市」短句（去括注），兩視圖同句
    tw2, gl2 = fd._market_status("更新：2026/07/03；美股 7/3 因國慶假期休市（提前收盤另計）")
    assert tw2 == gl2 == "美股 7/3 因國慶假期休市"
    assert fd._market_status("更新：2026/07/03") == ("", "")


def test_macro_cal_view_region_badges_and_earnings_split():
    # 地區以彩色小徽章呈現（非「美：」文字）；財報獨立成子表（2026-07-05 使用者需求）
    from arm import fund_dashboard as fd
    cal = {"date": "2026-07-05", "note": "", "title": "本週重點財經行事曆（07/06–07/10）",
           "rows": [
               {"date": "07/06", "item": "6月ISM服務業", "region": "美",
                "cons": "—", "actual": "—", "prev": "—", "status": "未公布"},
               {"date": "07/09", "item": "6月CPI", "region": "中",
                "cons": "—", "actual": "—", "prev": "—", "status": "未公布"},
               {"date": "07/10", "item": "達美航空 Q2 財報", "region": "財報",
                "cons": "—", "actual": "—", "prev": "—", "status": "未公布"},
           ]}
    html = fd._macro_cal_view(cal)
    assert '<span class="creg us">美</span>' in html and '<span class="creg cn">中</span>' in html
    assert "美：" not in html and "財報：" not in html          # 前綴文字不得出現
    assert "重要財報／法說" in html and "達美航空" in html      # 財報獨立子表
    # 財報列不掛地區徽章、且不在主表（子表位於「重要財報／法說」標題之後）
    assert html.index("達美航空") > html.index("重要財報／法說")


def test_card_importance_and_etype_parsing():
    md = (
        "### 卡 1｜輝達新財測（來源：Reuters｜2026/07/02｜【新事件】｜重要度 9/10）\n"
        "1. **新聞摘要**：略。\n2. **一句話重點**：AI 需求續強。\n\n"
        "### 卡 2｜某舊聞續追（來源：CNBC｜2026/07/02｜【延伸】｜重要度 6/10）\n"
        "1. **新聞摘要**：略。\n"
    )
    cards = usnews.extract_cards(md)
    assert [c["importance"] for c in cards] == [9, 6]
    assert [c["etype"] for c in cards] == ["new", "ext"]
    # 無括注者不炸、欄位為 None
    plain = usnews.extract_cards("### 卡 1｜無標注（來源：X｜2026/07/02）\n1. **新聞摘要**：略。\n")
    assert plain[0]["importance"] is None and plain[0]["etype"] is None


def test_news_view_filters_below_6_and_sorts_by_importance():
    from arm import fund_dashboard as fd
    md = (
        "### 卡 1｜低分事件（來源：X｜2026/07/02｜【延伸】｜重要度 4/10）\n1. **一句話重點**：低。\n\n"
        "### 卡 2｜中分事件（來源：Y｜2026/07/02｜【新事件】｜重要度 7/10）\n1. **一句話重點**：中。\n\n"
        "### 卡 3｜高分事件（來源：Z｜2026/07/02｜【新事件】｜重要度 10/10）\n1. **一句話重點**：高。\n"
    )
    html = fd._news_view(md, "無")
    assert "低分事件" not in html                    # <6 被隱藏
    assert "重要度 10" in html and "重要度 7" in html  # 徽章顯示
    assert html.index("高分事件") < html.index("中分事件")   # 依重要度高→低排序
    assert 'netype new">新事件' in html and 'netype ext' not in html      # 事件屬性徽章（延伸那則<6已濾掉）


def test_news_view_deep_card_goes_last_and_no_serial_numbers():
    # 2026-08-16 使用者：「全球的新聞順序很奇怪」——①依重要度重排後，報告檔的撰寫流水號
    # （1./2./3.）留在標題上會變成錯亂編號；②【深度】精選依分數混排會插在事件卡中間。
    from arm import fund_dashboard as fd
    md = (
        "### 1. 甲事件（來源：X・2026/08/15｜【新事件】｜重要度 7/10）\n1. **一句話重點**：甲。\n\n"
        "### 2. 乙事件（來源：Y・2026/08/15｜【新事件】｜重要度 8/10）\n1. **一句話重點**：乙。\n\n"
        "### 3. 丙事件（來源：Z・2026/08/15｜【新事件】｜重要度 6/10）\n1. **一句話重點**：丙。\n\n"
        "### 【深度】丁專題（來源：W・2026/08/15｜【深度】｜重要度 7/10）\n1. **一句話重點**：丁。\n"
    )
    html = fd._news_view(md, "無")
    assert ">1. 甲事件" not in html and ">2. 乙事件" not in html      # 流水號已剝除
    assert html.index("乙事件") < html.index("甲事件") < html.index("丙事件")   # 重要度高→低
    assert html.index("丙事件") < html.index("丁專題")               # 深度排在事件卡之後


def test_news_view_renders_move_block():
    # 「漲跌分析」欄（2026-08-19）：金色 .ngmv 塊、置於摘要與影響分析之間；無此欄的舊卡不渲染
    from arm import fund_dashboard as fd
    md = ("### 卡 1｜甲事件（來源：X｜2026/08/20｜【新事件】｜重要度 7/10）\n"
          "1. **新聞摘要**：摘要文。\n"
          "3. **漲跌分析**：台積電大漲 **4.2%**，主因外資回補。\n"
          "4. **對持股／族群影響**：影響文。\n"
          "6. **參考資料**：[a](https://example.com/a)\n")
    html = fd._news_view(md, "無")
    assert 'class="ngmv"' in html and "主因外資回補" in html
    assert html.index("摘要文") < html.index("主因外資回補") < html.index("影響文")
    old = fd._news_view("### 卡 1｜舊卡（來源：X｜2026/07/02｜【新事件】｜重要度 7/10）\n"
                        "1. **新聞摘要**：略。\n", "無")
    assert "ngmv" not in old


def test_extract_cards_keeps_numeric_leading_title():
    # 剝流水號不可誤傷數字開頭的真標題（數字後須接標點才算序號）
    cards = usnews.extract_cards(
        "### 10年期公債殖利率飆升（來源：X・2026/08/15｜【新事件】｜重要度 7/10）\n"
        "1. **新聞摘要**：略。\n")
    assert cards[0]["title"] == "10年期公債殖利率飆升"


# ── fund_intro 組裝 ──────────────────────────────────────────
def _fake_doc():
    return {
        "fund_id": "99", "group": "global_equity", "category": "跨國投資股票型",
        "nav": 47.58, "nav_date": "2026/07/01",
        "country_alloc": [{"name": "美國", "weight": 60.76}, {"name": "臺灣", "weight": 16.71}],
        "sector_alloc": [{"name": "資訊技術", "weight": 85.97}],
        "top_holdings": [{"name": "A", "weight": 4.58}, {"name": "B", "weight": 3.78}],
    }


def test_top_concentration():
    # summary_line 一句話摘要已整行移除（2026-07-22 使用者指示：區域/產業/NAV 皆與卡內既有資訊重複）
    assert fund_intro.top_concentration(_fake_doc()) == 8.4


def test_group_label_mapping():
    assert fund_intro.GROUP_LABEL["global_balanced"] == "全球平衡型"


def test_all_funds_reads_config(tmp_path, monkeypatch):
    # 至少不報錯，且回傳 list（實際內容依 data/funds 是否已抓）
    assert isinstance(fund_intro.all_funds(), list)


def test_load_handles_corrupt_json():
    # 空檔/壞 JSON 應視同缺檔回 None（不讓整份儀表板崩）
    p = fund_intro.FUNDS_DIR / "999999.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    try:
        assert fund_intro.load("999999") is None
    finally:
        p.unlink(missing_ok=True)


# ── 回歸：review 修正 ─────────────────────────────────────────
def test_md_bold_can_contain_italic():
    out = fund_dashboard._inline("**a *b* c**")
    assert "<b>a <i>b</i> c</b>" in out              # 粗體內含斜體不再殘留字面 **
    assert fund_dashboard._inline("**x** and **y**").count("<b>") == 2


def test_md_escapes_html():
    assert "<script>" not in fund_dashboard._inline("<script>alert(1)</script>")


def test_md_ordered_list_and_badge():
    # 新聞卡 1.~6. 條列應成有序清單；【消息屬性】應成徽章
    out = fund_dashboard._md("1. 摘要\n2. 重點\n\n【新消息】標題")
    assert out.count("<ol>") == 1 and out.count("<li>") == 2
    assert '<span class="tag">【新消息】</span>' in out


def test_compliance_negation_not_flagged():
    for ok in ["本文並非保證獲利", "投資並非無風險", "非零風險", "不保證最低收益"]:
        assert usnews.compliance_scan(ok) == [], ok
    # 真正違規（前方無否定詞）仍要抓到
    assert "保證" in usnews.compliance_scan("本檔保證獲利")
    assert "目標價" in usnews.compliance_scan("目標價 100 元")


# ── /api/fundNav 髒回應容錯（2026-07-21 CI 實測：Extra data／開頭垃圾） ──

def test_parse_first_json_clean_and_trailing_garbage():
    assert fhfund._parse_first_json('{"result": [1]}') == {"result": [1]}
    # 有效 JSON 後黏多餘資料（實際 25/29 檔的失敗型態）
    assert fhfund._parse_first_json('{"result": [1]}{"x": 2}garbage') == {"result": [1]}
    # BOM＋前置空白
    assert fhfund._parse_first_json('﻿  {"a": 1}') == {"a": 1}


def test_parse_first_json_leading_garbage():
    assert fhfund._parse_first_json('oops<html>{"result": []}tail') == {"result": []}
    try:
        fhfund._parse_first_json("完全不是 JSON")
        assert False, "應 raise NoData"
    except fhfund.NoData:
        pass


def test_fetch_nav_history_dirty_response(monkeypatch):
    payload = ('{"result": [{"navDate": "2026/07/17", "pnav": "26.19"},'
               '{"navDate": "2026/07/16", "pnav": "26.45"},'
               '{"navDate": "2026/01/05", "pnav": "20.00"}]}EXTRA-JUNK')
    monkeypatch.setattr(fhfund, "get_bytes", lambda url, **kw: payload.encode())
    out = fhfund.fetch_nav_history("101", days=90)
    assert out == {"2026/07/17": 26.19, "2026/07/16": 26.45}   # 90 天截斷丟 01/05


def test_fetch_nav_history_retry_then_fail(monkeypatch):
    calls = []

    def bad(url, **kw):
        calls.append(url)
        return b"<html>error</html>"

    monkeypatch.setattr(fhfund, "get_bytes", bad)
    try:
        fhfund.fetch_nav_history("101")
        assert False, "應 raise NoData"
    except fhfund.NoData:
        pass
    assert len(calls) == 2                                     # 解析失敗會重抓一次


def test_fof_asset_alloc_parse(monkeypatch):
    # 組合型頁面：資產配置（無國家/產業配置）＋十大持有基金——2026-08-12 使用者指出
    html = """
    <h3>資產配置</h3>
    <svg><text>62.4 %</text><text>31.2 %</text>
    <text>股票型基金</text><text>債券型基金</text></svg>
    <h3>十大持有基金</h3>
    <table class="fundTable"><tbody>
      <tr><td>復華全球大趨勢基金</td><td>18.50%</td></tr>
    </tbody></table>"""
    monkeypatch.setattr(fhfund, "get_bytes", lambda *a, **k: html.encode("utf-8"))
    out = fhfund.fetch_holdings("22")
    assert out["asset_alloc"] == [{"name": "股票型基金", "weight": 62.4},
                                  {"name": "債券型基金", "weight": 31.2}]
    assert out["top_holdings"][0]["name"] == "復華全球大趨勢基金"
    # 一般基金頁（無資產配置段）→ asset_alloc 空、國家/產業照舊
    html2 = ('國家配置<text>60.76 %</text><text>美國</text>'
             '產業配置<text>50.0 %</text><text>資訊技術</text>十大持有標的')
    monkeypatch.setattr(fhfund, "get_bytes", lambda *a, **k: html2.encode("utf-8"))
    out2 = fhfund.fetch_holdings("47")
    assert out2["asset_alloc"] == []
    assert out2["country_alloc"] == [{"name": "美國", "weight": 60.76}]
