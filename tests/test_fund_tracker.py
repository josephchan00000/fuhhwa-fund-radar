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
    # 2026-08-31 Warsh 案：時窗內最重大事件即使無新進展也必須成卡重收，
    # 保底規則優先於已報導清單的「略過」（否則週一報告會把週五最大事件整個蓋掉）
    assert "週末最重大事件保底" in n and "必須成卡重收" in n and "週末綜整" in n
    # 2026-08-31 伊朗案（反向風險）：週日／今晨才發生的事最容易漏——錨定序列還沒反映
    assert "週日與今晨才發生的事最容易整個漏掉" in n and "錨定沒旗標" in n
    # 週日：涵蓋週五晚間＋週六；週六：涵蓋週五晚間起（保底段週末三日都要有）
    assert "週六全日" in usnews.weekend_note(date(2026, 7, 5))
    assert "週末最重大事件保底" in usnews.weekend_note(date(2026, 7, 5))
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
    # 2026-08-31 Warsh 案：略過規則須明載「週末最重大事件保底」例外，避免週一壓掉週五大事
    assert "週末最重大事件保底" in block
    # 沒有更早檔案時回空、prior_block 回空字串（提示包會略過）
    assert usnews.prior_titles(tmp_path, date(2026, 7, 4)) == []
    assert usnews.prior_block([]) == ""
    assert usnews.weekend_note(date(2026, 7, 3)) == ""


def test_cal_spec_covers_regions_and_earnings():
    # 行事曆版型須涵蓋美／歐／中／日與重要企業財報（2026-07-05 使用者需求）
    from arm import macronews
    s = macronews.SPEC_CAL
    assert "歐" in s and "ECB" in s and "中" in s and "日銀" in s and "財報" in s
    assert "美：／歐：／中：／日：" in s and "財報：" in s      # 2026-10-13 起分三區列（全球／台灣／海外財報）
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
    assert "海外財報／法說" in html and "達美航空" in html      # 財報獨立子表（2026-10-13 改名：台股另立子表）
    # 財報列不掛地區徽章、且不在主表（子表位於「海外財報／法說」標題之後）
    assert html.index("達美航空") > html.index("海外財報／法說")


# ── 行事曆台股公司法說・財報（2026-10-13 使用者：「行事曆是不是也要把台股的重要公司法說或是財報公布都加進去」）──

_TW_PROFILES = {"台積電": {"ticker": "2330", "country": "臺灣"}, "大立光": {"ticker": "3008", "country": "台灣"},
                "大立光電": {"ticker": "3008", "country": "台灣"}, "元大台灣50": {"ticker": "0050", "country": "臺灣"},
                "NVIDIA": {"ticker": "NVDA", "country": "美國"}}
_TW_FUNDS = [{"top_holdings": [{"name": "台積電"}, {"name": "大立光"}, {"name": "元大台灣50"}, {"name": "NVIDIA"}]},
             {"top_holdings": [{"name": "台積電"}]}]
_TW_EH = {"etfs": {"0050": {"holdings": [{"stock_id": "2330", "name": "台積電", "weight": 56.0},
                                         {"stock_id": "2317", "name": "鴻海", "weight": 3.0}]},
                   "00991A": {"holdings": [{"stock_id": "2330", "name": "台灣積體", "weight": 13.0},
                                           {"stock_id": "AAPL US", "name": "Apple", "weight": 9.0}]}}}


def test_tw_watch_from_holdings():
    from arm import macronews
    w = macronews.tw_watch(_TW_FUNDS, _TW_EH, _TW_PROFILES)
    by = {r["code"]: r for r in w}
    assert set(by) == {"2330", "3008", "2317"}             # ETF（0050）與海外股（NVDA／AAPL）不算台股公司
    assert by["2330"]["funds"] == 2 and "00991A" in by["2330"]["etfs"] and by["2330"]["cap"]
    assert by["2330"]["name"] == "台積電" and by["3008"]["name"] == "大立光"   # 多來源取最短＝常用簡稱
    assert by["2317"]["cap"] and not by["2317"]["funds"] and not by["2317"]["etfs"]
    assert [r["code"] for r in w] == ["2330", "3008", "2317"]   # 復華持有越多越前、純權值龍頭殿後
    assert set(macronews.tw_held(w)) == {"2330", "3008"}
    block = macronews.tw_watch_block(w)
    assert "台積電（2330）［基金×2、00991A］" in block and "權值龍頭" in block and "鴻海（2317）" in block
    assert macronews.tw_watch_block([]) == ""                 # 落檔讀不到 → 整段略過


def test_tw_region_prefix_and_legacy_retag():
    from arm import macronews
    md = ("| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n|---|---|---|---|---|---|\n"
          "| 10/15 | 台股：聯發科（2454）、日月光投控（3711）法說會 | — | — | — | 未公布 |\n"
          "| 10/15 | 財報：台積電（2330）Q3法說會 | — | — | — | 未公布 |\n"
          "| 10/16 | 財報：東京威力科創（8035）財報 | — | — | — | 未公布 |\n")
    rows = macronews.retag_tw(macronews._parse_cal_rows(md), {"2330", "2454"})
    assert rows[0]["region"] == "台股" and rows[0]["item"].startswith("聯發科")
    assert macronews.tw_codes(rows[0]["item"]) == ["2454", "3711"]
    assert rows[1]["region"] == "台股"                      # 舊版型寫在「財報：」的台股公司 → 改歸台股
    assert rows[2]["region"] == "財報"                      # 日股代號也是 4 碼，不在清單內就不動


def test_macro_cal_view_tw_subtable_with_holding_chip():
    # 台灣區＝「台：」官方數據＋「台股：」公司法說財報合一張表（2026-10-13：台灣資訊集中一處、不零散）
    from arm import fund_dashboard as fd
    row = lambda d, item, reg: {"date": d, "item": item, "region": reg, "cons": "—", "actual": "—",
                               "prev": "—", "status": "未公布"}
    cal = {"date": "2026-10-13", "note": "", "rows": [
        row("10/14", "9月CPI", "美"), row("10/15", "台積電（2330）Q3法說會", "台股"),
        row("10/16", "鴻海（2317）法說會", "台股"), row("10/16", "9月外銷訂單（年增）", "台"),
        row("10/14", "ASML Q3財報", "財報")]}
    held = {"2330": {"code": "2330", "name": "台積電", "funds": 13, "etfs": ["00991A"], "cap": True}}
    html = fd._macro_cal_view(cal, held)
    i_data, i_tw, i_os = html.index("9月CPI"), html.index("台灣：經濟數據・法說財報"), html.index("海外財報／法說")
    assert i_data < i_tw < html.index("台積電") < i_os < html.index("ASML")   # 全球數據 → 台灣 → 海外
    assert i_tw < html.index("9月外銷訂單") < i_os           # 台灣官方數據與公司事件在同一張表
    assert html.count('<table class="caltbl">') == 3         # 新增台灣數據不多開表：仍是三張
    assert html.count('class="chold"') == 1                 # 只有復華持有的台積電掛章、鴻海不掛
    assert "基金前十大 13 檔、00991A" in html and "1 項為復華持股" in html
    assert "台股：" not in html and "台：" not in html
    assert "台灣：經濟數據" not in fd._macro_cal_view({**cal, "rows": cal["rows"][:1]}, held)  # 無台灣列不出子表
    only_data = fd._macro_cal_view({**cal, "rows": [cal["rows"][0], cal["rows"][3]]}, held)
    assert "台灣：經濟數據" in only_data and "復華持股" not in only_data   # 只有官方數據也成表、不掛持股章


def test_print_calendar_tw_badge_and_holding_mark():
    from arm import printview
    cal = {"date": "2026-10-13", "note": "", "rows": [
        {"date": "10/15", "item": "台積電（2330）Q3法說會", "region": "台股", "cons": "—", "actual": "—",
         "prev": "—", "status": "未公布"}]}
    html = printview.calendar_block(cal, {"2330": {}})
    assert '<span class="pr-reg tw">台股</span>' in html and 'class="pr-hold"' in html
    data = {**cal, "rows": [{**cal["rows"][0], "item": "9月出口（年增）", "region": "台"}]}
    assert '<span class="pr-reg tw">台</span>' in printview.calendar_block(data, {"2330": {}})
    assert "前十大持股內" in html                           # 表底說明「持股」章意義
    assert 'class="pr-hold"' not in printview.calendar_block(cal, {})


def test_cal_spec_tw_data_and_slim_rules():
    # 2026-10-13：加台灣數據的同時把精簡上限寫進版型（總列數／口徑合併／只收排定事件／引言三段）
    from arm import macronews
    s = macronews.SPEC_CAL
    assert "台：" in s and "台灣區" in s and "至多 4 列" in s and "台：本週無台灣重點經濟數據" in s
    assert "總列數 ≤ 30" in s and "併一列" in s and "事先排定" in s and "本週焦點" in s
    assert "昨夜重點不寫" in s
    # 2026-10-16：Fed 主席沃許曼谷談話漏列——央行首長排定談話必列，底稿不是清單上限
    assert "央行首長排定談話必列" in s and "Fed 主席" in s and "日銀總裁" in s
    assert "底稿只是起點" in macronews.CAL_CARRY_RULE
    rows = macronews._parse_cal_rows("| 07/08 | 台：6月出口（年增） | — | — | +38.6% | 未公布 |\n"
                                     "| 07/16 | 台股：台積電（2330）Q2法說會 | — | — | — | 未公布 |\n")
    assert [r["region"] for r in rows] == ["台", "台股"]       # 「台股」不被「台」吃掉前兩字


def test_cal_prompt_carries_tw_watchlist(monkeypatch):
    import sys
    from datetime import date
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import gen_macronews
    from arm import macronews
    real = macronews.tw_watch
    monkeypatch.setattr(macronews, "tw_watch", lambda *a, **k: real(_TW_FUNDS, _TW_EH, _TW_PROFILES))
    p = gen_macronews.build_cal_prompt(date(2026, 10, 13))
    assert "【台股公司觀察清單" in p and "台積電（2330）" in p and "台股：" in p
    assert "台股：本週無觀察清單內公司法說／財報" in p           # 無事件時的必寫註記（QA 閘門據此判斷有查）


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


def test_deep_card_why_field_renders():
    # 2026-08-19 試跑發現：【深度】精選的「為什麼值得讀」寫在報告裡卻沒被解析、
    # 整行在儀表板消失（深度精選最有價值的一句）——解析成 why 並渲染成紫色塊
    from arm import fund_dashboard as fd, usnews
    md = ("### 【深度】產業鏈專題（來源：工商時報｜2026/08/20｜【深度】｜重要度 7/10）\n"
          "1. **新聞摘要**：摘要文。\n"
          "2. **為什麼值得讀**：把漲價潮的擴散路徑拆到材料端。\n"
          "3. **對持股／族群影響**：影響文。\n"
          "4. **參考連結**：[a](https://example.com/a)\n")
    c = usnews.extract_cards(md)[0]
    assert c["why"] == "把漲價潮的擴散路徑拆到材料端。"
    html = fd._news_view(md, "無")
    assert 'class="ngwhy"' in html and "擴散路徑拆到材料端" in html
    assert html.index("摘要文") < html.index("擴散路徑") < html.index("影響文")
    # 無編號前綴的寫法（子代理常見）也要收；一般事件卡無此欄＝不渲染
    bare = usnews.extract_cards("### 【深度】X（來源：Y｜2026/08/20｜【深度】｜重要度 7/10）\n"
                                "**為什麼值得讀**：無編號也要收。\n")[0]
    assert bare["why"] == "無編號也要收。"
    assert "ngwhy" not in fd._news_view(
        "### 卡 1｜甲（來源：X｜2026/08/20｜【新事件】｜重要度 7/10）\n"
        "1. **新聞摘要**：略。\n", "無")


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


# ── 分頁內各段（2026-09-01 改「一次一段」；2026-09-24 使用者：「要點才會出現對應資訊
#    不是很好用」→ 改回整頁全部顯示，頂欄標籤＝跳段目錄＋捲動自動標亮）──────────────

_SECS = [("brief", "secf"), ("news", "secf"), ("fnews", "secf"), ("over", "secf"),
         ("det", "secf"), ("mcal", "secm"), ("mov", "secm"), ("mnews", "secm"),
         ("mdata", "secm"), ("eup", "sece"), ("ewatch", "sece"), ("edet", "sece")]


def test_second_level_sections_wrap_every_block():
    """每個區塊都包在 .sec 裡、每段都有對應 radio（標亮用），且三個分頁各有一個預設段。"""
    from arm import fund_dashboard as fd
    html = fd.render()
    for name, group in _SECS:
        assert f'<div class="sec" data-sec="{name}">' in html, name
        assert f'id="sec-{name}"' in html, name
    for g in ("secf", "secm", "sece"):
        checked = [n for n, gg in _SECS if gg == g
                   and f'name="{g}" id="sec-{n}" checked' in html]
        assert len(checked) == 1, (g, checked)      # 每組剛好一個預設選中
    assert '<div class="rprog"' in html             # 閱讀進度條


def test_sections_all_visible_and_subnav_jumps():
    """各段不得再被 radio 隱藏（使用者不要「點了才出現」）；目錄標籤對得上 .sec，
    點了捲到該段、捲動時自動標亮。"""
    from arm import fund_dashboard as fd
    import re
    html = fd.render()
    fors = re.findall(r'<label class="sl" for="(sec-[\w-]+)"', html)
    assert len(fors) == len(_SECS) and set(fors) == {"sec-" + n for n, _ in _SECS}
    assert ".sec{display:none}" not in fd._CSS
    for name, _ in _SECS:
        assert f'#sec-{name}:checked ~ * .sec[data-sec="{name}"]' not in fd._CSS
    assert "function spy(" in fd._JS and "function markSec(" in fd._JS
    assert "addEventListener('scroll',spy" in fd._JS
    assert "showSec" not in fd._JS                   # 舊「先切段再捲」機制已不需要


def test_header_compact_and_news_meta_dedup():
    """頁首瘦身（2026-09-24）：拿掉品牌橫幅、網頁更新時間壓成細條；
    新聞卡灰字不再重複【屬性】／重要度（已有徽章）；指數卡缺時不印流程字句。"""
    from arm import fund_dashboard as fd
    html = fd.render()
    assert 'class="hero"' not in html
    assert 'class="section freshbar" id="freshness"' in html
    assert "指數收盤點位以官方為準" not in html
    assert fd._meta_clean("經濟日報／工商時報，2026/09/23｜【新事件】｜重要度9/10") == "經濟日報／工商時報，2026/09/23"
    assert fd._meta_clean("Reuters，2026/09/23 05:30 TST｜【延伸】｜重要度 7/10") == "Reuters，2026/09/23 05:30 TST"
    assert fd._meta_clean("中央社，2026/09/23") == "中央社，2026/09/23"


def test_chg_cell_序列落後時不以舊漲跌冒充當日():
    """ETF 當日漲跌與收盤價出自不同來源，序列落後時不得並排顯示（2026-09-03）。

    事故：當日漲跌取自報酬序列末兩點（perf_asof），收盤價走 etfinfo 市價（as_of）。
    2026-09-02 全表 31 檔序列缺當日 bar，末兩點退成「9/1 vs 8/31」，卻與 9/2 的收盤價
    並排——0050 顯示 +2.07%，而它 9/2 實際跌約 1.5%，**方向完全相反**。
    gen 端「算不出就保留既有值」與 CI 完整性斷言都不覆蓋此型，屬完全靜默的錯位。
    """
    from arm import fund_dashboard as fd

    # ① 序列落後（perf_asof < as_of）→ 不顯示數字、標出序列基準日
    stale = fd._chg_cell({"chg_pct": 2.07, "chg_amt": 2.2, "prev_close": 106.25,
                          "prev_date": "2026-08-31",
                          "as_of": "2026-09-02", "perf_asof": "2026-09-01"})
    assert "2.07%" not in stale                      # 誤導數字不得出現
    assert "mdstale" in stale and "基準 2026-09-01" in stale
    assert "2026-09-02" in stale                     # tooltip 要講清楚收盤價是哪天

    # ② 兩者同日 → 正常顯示，不掛過期章
    ok = fd._chg_cell({"chg_pct": -1.52, "chg_amt": -1.65, "prev_close": 108.45,
                       "prev_date": "2026-09-01",
                       "as_of": "2026-09-02", "perf_asof": "2026-09-02"})
    assert "-1.52%" in ok and "mdstale" not in ok

    # ③ 缺日期資訊 → fail-open（照顯示，不因判不出而整欄空白）
    assert "1.00%" in fd._chg_cell({"chg_pct": 1.0, "as_of": None, "perf_asof": None})

    # ④ chg 本來就沒有 → 維持既有「—」行為
    assert "—" in fd._chg_cell({"chg_pct": None})


# ── 當日漲跌：「落後」與「日期根本不可能」要分開呈現（2026-09-21 使用者回報） ──────
# 「當日漲跌全部變成 ⚠ 基準 2026-09-20，週末當然沒有，你這樣不就全部都是錯誤了嗎」

def _vis(html: str) -> str:
    """讀者實際看得到的文字（剝掉標籤與 tooltip）——版面類斷言不可拿 title 當代理指標。"""
    import re
    return re.sub(r"<[^>]*>", "", re.sub(r'title="[^"]*"', "", html))


def test_chg_trust_三態判定():
    from arm import fund_dashboard as fd
    assert fd.chg_trust({"as_of": "2026-09-18", "chg_asof": "2026-09-18"})[0] == "ok"
    assert fd.chg_trust({"as_of": "2026-09-02", "chg_asof": "2026-09-01"})[0] == "lag"
    assert fd.chg_trust({"as_of": "2026-09-18", "chg_asof": "2026-09-20"})[0] == "bad"  # 週日
    assert fd.chg_trust({"as_of": "2026-09-18", "chg_asof": "2026-09-21"})[0] == "bad"  # 超前
    assert fd.chg_trust({"as_of": None, "chg_asof": None})[0] == "ok"            # fail-open
    assert fd.chg_trust({"as_of": "2026-09-18", "chg_asof": "壞值"})[0] == "bad"  # 解析不了


def test_不可能的日期不得出現在畫面上():
    """首版一律印「⚠ 基準 {日期}」，假 bar 那輪整表 36 列掛「⚠ 基準 2026-09-20」＝週日。
    把不可能的日期當「基準」印給讀者，等於宣告系統把週日當交易日。
    改為只印 —⚠，該日期僅留在 tooltip 供診斷。"""
    from arm import fund_dashboard as fd
    i = {"chg_pct": -7.15, "as_of": "2026-09-18", "chg_asof": "2026-09-20"}
    html = fd._chg_cell(i)
    assert "2026-09-20" not in _vis(html)        # 讀者看不到那個週日日期
    assert "基準" not in _vis(html)
    assert _vis(html).strip() == "—⚠"
    assert "-7.15" not in html                   # 更不可顯示那個錯數字
    assert "2026-09-20" in html                  # 但 tooltip 要留著供追查


def test_真落後仍印基準日因為對讀者有資訊價值():
    """lag 與 bad 的差別＝那個日期有沒有意義：數字確實來自某個較早「交易日」時，
    印出它讀者才知道「這格晚一天」；週末／未收盤的日期則沒有任何資訊價值。"""
    from arm import fund_dashboard as fd
    html = fd._chg_cell({"chg_pct": 2.07, "as_of": "2026-09-02", "chg_asof": "2026-09-01"})
    assert "⚠ 基準 2026-09-01" in _vis(html) and "2.07" not in html


def test_列印版與螢幕版共用同一支判定():
    """兩邊規則漂移過一次（2026-09-21 前列印版自己寫一套）——現統一走 fd.chg_trust。"""
    from arm import printview as pv
    for i in ({"chg_pct": -7.15, "as_of": "2026-09-18", "chg_asof": "2026-09-20"},
              {"chg_pct": 2.07, "as_of": "2026-09-02", "chg_asof": "2026-09-01"}):
        assert "⚠" in pv._etf_chg(i) and "—" in pv._etf_chg(i)
    ok = pv._etf_chg({"chg_pct": 1.67, "as_of": "2026-09-18", "chg_asof": "2026-09-18"})
    assert "+1.67%" in ok and "⚠" not in ok
