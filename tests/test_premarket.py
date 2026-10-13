"""盤前速覽：自台股新聞頭段抽出、改置「今日重點」的離線測試。"""
from arm.fund_dashboard import _extract_premarket, _premarket_card

_MD = """# 台股盤前重點（2026-07-03）

## 🔹盤前速覽

- **台指期夜盤**：約 45,668 點、下跌約 938 點（約 -2.01%）。
- **台積電 ADR**：再跌約 2.2%、約收 434.55 美元。

## 🔹盤前卡

### 某新聞卡（來源｜【新事件】｜重要度 7/10）
內文。
"""


def test_extract_premarket_pulls_section():
    body, rest = _extract_premarket(_MD)
    assert "台指期夜盤" in body and "台積電 ADR" in body
    assert "盤前速覽" not in rest            # 段落已移除，不再進新聞區收合塊
    assert "盤前卡" in rest and "某新聞卡" in rest


def test_extract_premarket_absent_returns_original():
    md = "## 🔹指數速覽\n\n- 加權指數收 28,000 點。"
    body, rest = _extract_premarket(md)
    assert body == "" and rest == md


def test_premarket_card_renders_and_empty_hides():
    body, _ = _extract_premarket(_MD)
    html = _premarket_card(body)
    assert "盤前速覽" in html and "台指期夜盤" in html
    assert _premarket_card("") == ""


# ── 段名行寫法漂移（2026-10-13 使用者：「印出來的昨夜美股總覽那欄都是空的」）──
# 版型只寫「🔹段名」，子代理寫成 ## 標題、### 標題、🔹**粗體行** 全憑運氣；舊解析只認 ##，
# 美股總覽 09-19 起整整三週在網頁與列印版消失、台股 8 月有 22 天速覽卡消失。

_US_HEAD = """# 昨夜美股公司與產業面速寫包（完整版）— 2026/10/13（週二；對應美股交易日 2026/10/12 週一）

🔹**前後24小時重大公司與產業事項總覽**

- 那斯達克收 **27,245.90 點**、跌 **0.44%**。
- 費半收 **12,236.79 點**、跌 **2.67%**。

**記憶體領跌、晶片股全面走弱**。中國長鑫存儲宣布新架構，美光收跌 **3.88%**。

---

### 1. 長鑫存儲宣布 4F² 伺服器 DRAM（CNBC，2026/10/13｜【新事件】｜重要度 8/10）
1. **新聞摘要**：內文。
"""


def test_section_label_accepts_every_observed_form():
    from arm import usnews
    for line in ("## 🔹前後 24 小時政策總覽", "### 🔹盤前速覽", "🔹**盤前速覽**",
                 "**🔹前後24小時重大公司與產業事項總覽**", "> 🔹**盤後速覽**：", "🔹盤前速覽"):
        assert usnews.section_label(line) in (
            "前後 24 小時政策總覽", "盤前速覽", "前後24小時重大公司與產業事項總覽", "盤後速覽"), line
    # 粗體開頭的正文段落、條列、長標題（新聞卡）都不是段名行
    assert usnews.section_label("**記憶體領跌、晶片股全面走弱**。中國長鑫存儲宣布…") is None
    assert usnews.section_label("- 那斯達克收 **27,245.90 點**") is None
    assert usnews.section_label("### 1. " + "很長的新聞卡標題" * 6 + "（重要度 8/10）") is None


def test_extract_overview_bold_label_form_and_stops_at_rule():
    from arm.fund_dashboard import _extract_overview
    from arm import usnews
    ov = _extract_overview(usnews.split_doc(_US_HEAD)[0])
    assert "那斯達克收" in ov and "記憶體領跌" in ov       # 條列＋解析段都要在
    assert "---" not in ov and "長鑫存儲宣布 4F²" not in ov  # 停在分隔線，不吃進新聞卡


def test_extract_premarket_bold_and_h3_forms():
    from arm.fund_dashboard import _premarket_title
    for label in ("🔹**盤前速覽**", "### 🔹盤前速覽"):
        md = (f"# 〈台股盤前重點〉\n\n{label}\n\n台指期夜盤收跌 **400 點**。\n\n"
              "🔹**盤前卡**\n\n### 1. 某卡（來源｜【新事件】｜重要度 7/10）\n內文。\n")
        body, rest = _extract_premarket(md)
        assert "台指期夜盤" in body and "盤前卡" not in body, label   # 停在下一個 🔹 段名
        assert "某卡" in rest and "台指期夜盤" not in rest, label
    assert _premarket_title("## 盤後速覽\n\n收盤。") == "盤後速覽"
    assert _premarket_title("## 🔹盤前速覽\n\n夜盤。") == "盤前速覽"


def test_overview_not_cut_by_plain_bold_line():
    """總覽正文裡獨立一行的「**市場解析**」（不帶 🔹）不可把小節提早切斷。"""
    from arm.fund_dashboard import _extract_overview
    head = "## 🔹前後 24 小時政策總覽\n\n第一段。\n\n**市場解析**\n\n第二段。\n"
    assert "第二段" in _extract_overview(head)


def test_real_us_report_overview_reaches_screen_and_print():
    """真實踩坑檔（粗體行段名）：螢幕版總覽卡與列印版 ③ 全球欄都要有內容。"""
    from pathlib import Path
    import pytest
    from arm import printview, usnews
    from arm.fund_dashboard import _extract_overview, _news_view
    p = Path(__file__).resolve().parent.parent / "reports/usnews/2026-10-13_v1.md"
    if not p.exists():
        pytest.skip("歷史報告檔不在")
    md = p.read_text(encoding="utf-8")
    ov = _extract_overview(usnews.split_doc(md)[0])
    assert "那斯達克" in ov
    assert "那斯達克" in _news_view(md, "", ("昨夜美股總覽", "副標"))
    col = printview.overview_block([("全球・昨夜美股總覽", ov, "2026-10-13", printview.us_trade_note(md))])
    assert "那斯達克" in col and "今日無此段" not in col
    assert "美股 10/12（一）" in col                          # 欄頭標出實際對應的美股交易日


def test_us_trade_note():
    from arm import printview
    assert printview.us_trade_note(_US_HEAD) == "美股 10/12（一）"
    assert printview.us_trade_note("# 標題沒有交易日") == ""
