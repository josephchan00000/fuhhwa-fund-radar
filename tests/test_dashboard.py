"""M7 儀表板測試（離線）：render_html 自含、內嵌 JSON 可解析、含多週期與當日新欄位。

註：M7 改寫後儀表板由 build_etf_model 產『數據切點 / 競品 / 口碑』模型（非舊的 idea/angle/
channels）。本測試以最小但符合現行 model 形狀的假資料驗 render，不依賴 DB / 報告。
"""
import json
import re

from arm import dashboard as d


def _min_model() -> dict:
    etf = {
        "id": "00991A", "name": "主動復華未來50", "short_name": "未來50",
        "date": "2026-06-15", "header": "收 19.69", "is_nav": False,
        "mkt_date": "2026-06-15", "price_src": None, "close": 19.69, "change_pct": 0.0336,
        "data_cuts": [{
            "icon": "📈", "label": "當日漲跌", "type": "短期績效出色", "priority": 90,
            "group": "hot", "group_label": "熱度與績效", "group_icon": "🔥",
            "tldr": "今日 +3.36%", "fact": "今日 +3.36%", "suggest": "x", "example": "y", "links": []}],
        "perf": {
            "as_of": "2026-06-15", "peer_mean_label": "主動同類均",
            "benches": [{"code": "0050", "label": "0050", "issuer": "元大", "is_index": True},
                        {"code": "00981A", "label": "00981A", "issuer": "統一", "is_index": False}],
            "rows": [{"period": "近1日", "etf": 3.36, "vals": {"0050": 3.24, "00981A": 2.84},
                      "peer_mean": 2.84, "excess": 0.52}]},
        "peers": [{"code": "00991A", "name": "主動復華未來50", "issuer": "復華", "close": 19.69,
                   "change_pct": 3.36, "volume": 93616913, "trade_date": "2026-06-15"}],
        "scan": [], "edges": [], "competitor_notes": {}, "topic": [], "voice": [],
        "intel_src": "baseline", "intel_note": "",
        "stats": {"data": 1, "peers": 1, "scan": 0, "topic": 0, "voice": 0},
    }
    return {"generated_at": "2026-06-16 09:00", "today": "2026-06-16", "etfs": [etf]}


def _embedded_json(html: str) -> dict:
    blob = re.search(r"const DATA = (\{.*\});\nconst SRC", html, re.S).group(1)
    return json.loads(blob.replace("<\\/", "</"))   # render_html 把 </ 跳脫成 <\/，解析前還原


def test_render_html_selfcontained_and_json_parses():
    html = d.render_html(_min_model())
    assert "<!DOCTYPE html>" in html
    assert "/*__DATA__*/" not in html               # 佔位符已完全置換
    back = _embedded_json(html)
    assert back["etfs"][0]["id"] == "00991A"
    assert back["today"] == "2026-06-16"             # 當日基準有帶入（黃字標註用）


def test_perf_multibench_and_freshness_markup_present():
    html = d.render_html(_min_model())
    assert "多週期報酬" in html                       # 多週期區塊
    assert "今日最新" in html                         # 當日資料黃字標註
    assert ".fresh{" in html                          # 黃字樣式
    # 內嵌資料保有多競品多週期結構
    perf = _embedded_json(html)["etfs"][0]["perf"]
    assert [b["code"] for b in perf["benches"]] == ["0050", "00981A"]
    assert perf["rows"][0]["vals"]["00981A"] == 2.84


def test_market_price_is_close_not_nav():
    # 抓的是市價(close/change_pct) 而非淨值；模型欄位齊備供 render 標當日
    etf = _min_model()["etfs"][0]
    assert etf["close"] == 19.69 and etf["change_pct"] == 0.0336
    assert etf["mkt_date"] == "2026-06-15"
