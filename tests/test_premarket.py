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
