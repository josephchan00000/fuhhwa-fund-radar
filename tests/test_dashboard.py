"""M7 儀表板測試（離線）：資料模型、5 大創意切角策展、HTML 自含與 JSON 可解析。"""
import json
import re

from arm import dashboard as d
from arm.copy.parse import parse_text

_REPORT = """# 每日想法組合 — 復華台灣未來50主動式ETF（00991A）  資料日 2026-06-15
> 收盤 19.69　折溢價 +0.15%　AUM 612億　績效基準：NAV 含息總報酬

### 1. [績效] 🟡
- **想法**：成立以來超額報酬 +33.9%，主動贏 0050
- 佐證：本檔 +103.9% / 基準 +70.0%
- 內容形式：vs 0050 對比動圖

### 2. [題材] 🟡
- **想法**：搭【AI載板】熱題：本檔押 23.1%
- 佐證：題材熱度 100
- 內容形式：題材連連看

### 3. [績效] 🟢
- **想法**：成立以來淨值翻倍
- 佐證：+103.9%
- 內容形式：戰報卡

### 4. [籌碼] 🟢
- **想法**：經理人新建倉 臻鼎-KY +2,000張
- 佐證：權重 1.93%
- 內容形式：換股快報

### 5. [配息時程] 🟢
- **想法**：距配息評價日剩 15 天
- 佐證：每年6月底評價
- 內容形式：倒數限動

### 6. [資金流] 🟡
- **想法**：近一週規模成長 +7.7%
- 佐證：現約 612 億
- 內容形式：成長曲線
"""


def _model():
    doc = parse_text(_REPORT)
    from arm import copy as cp
    results = cp.generate_doc(doc)
    ideas = [d._idea_model(r) for r in results]
    return doc, ideas


def test_idea_model_has_angle_and_channels():
    _, ideas = _model()
    m = ideas[0]
    assert m["angle_label"] == "翻倍實證"           # 績效 → 創意框架
    assert set(m["channels"]) == {"punchy", "line", "ig", "sales"}
    assert m["channels"]["punchy"]["source"] == "baseline"
    assert m["allowed"]                              # 有可用數字


def test_top5_are_distinct_angles():
    _, ideas = _model()
    top = d.top5_angles(ideas)
    assert len(top) == 5
    cats = [next(m["category"] for m in ideas if m["idx"] == i) for i in top]
    assert len(set(cats)) == 5                       # 五個不同面向（創意切角）


def test_top5_fills_to_five_when_few_categories():
    # 只有 2 種面向 → 仍補滿 5（不足面向時用剩餘想法填）
    ideas = [{"idx": i, "category": "績效" if i % 2 else "籌碼"} for i in range(1, 8)]
    assert len(d.top5_angles(ideas)) == 5


def test_all_known_categories_have_angle():
    for cat in ["績效", "資金流", "同類排名", "籌碼", "分點推敲", "持股差異化",
                "題材", "配息時程", "逆向誠實", "同業招數", "社群KOL", "成交量"]:
        assert cat in d.CREATIVE_ANGLE


def test_render_html_selfcontained_and_json_parses():
    doc, ideas = _model()
    model = {"generated_at": "2026-06-16 09:00", "etfs": [{
        "id": doc.etf_id, "name": doc.name, "short_name": "復華台灣未來50",
        "date": doc.date, "header": doc.header, "ideas": ideas,
        "top5": d.top5_angles(ideas), "enhanced_src": "baseline",
        "stats": {"ideas": len(ideas), "fabricated": 0, "banned": 0}}]}
    html = d.render_html(model)
    assert "<!DOCTYPE html>" in html and "今日 5 大創意切角" in html
    assert "http://" not in html and "https://" not in html   # 零外部依賴
    blob = re.search(r"const DATA = (\{.*\});\nconst CH", html, re.S).group(1)
    back = json.loads(blob)                          # 內嵌資料可被瀏覽器 JSON 解析
    assert back["etfs"][0]["id"] == "00991A"
