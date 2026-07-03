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
    assert "【新事件】" in usnews.SPEC_V1 and "至少 6 則" in usnews.SPEC_V1   # 多找、標事件屬性
    assert usnews.BANNED and "保證" in usnews.BANNED


def test_macro_spec_and_section():
    from arm import macronews, fund_dashboard as fd
    # 政策面規格：含三大範圍＋新標準（重要度/新事件/多找）
    s = macronews.SPEC_MACRO
    assert "川普" in s and "聯準會" in s and "重要度" in s and "【新事件】" in s and "至少 6 則" in s
    # 儀表板有「總經・政策」獨立區塊與導覽（不隨台股/全球切換）
    html = fd.render()
    assert 'id="macro"' in html and '<a href="#macro">總經</a>' in html and "🏛️ 總經・政策" in html


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
    assert "🆕 新事件" in html and "↪ 延伸" not in html      # 事件屬性徽章（延伸那則<6已濾掉）


# ── fund_intro 組裝 ──────────────────────────────────────────
def _fake_doc():
    return {
        "fund_id": "99", "group": "global_equity", "category": "跨國投資股票型",
        "nav": 47.58, "nav_date": "2026/07/01",
        "country_alloc": [{"name": "美國", "weight": 60.76}, {"name": "臺灣", "weight": 16.71}],
        "sector_alloc": [{"name": "資訊技術", "weight": 85.97}],
        "top_holdings": [{"name": "A", "weight": 4.58}, {"name": "B", "weight": 3.78}],
    }


def test_summary_line_and_concentration():
    d = _fake_doc()
    s = fund_intro.summary_line(d)
    assert "美國 60.8%" in s and "資訊技術 86.0%" in s and "47.58" in s
    assert fund_intro.top_concentration(d) == 8.4


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
