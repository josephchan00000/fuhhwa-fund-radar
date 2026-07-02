"""市場註冊表（多市場參數化核心）。

同一套引擎（fhfund 連接器、fund_intro、fund_dashboard、usnews）可服務多個市場；
每個市場只是一組「設定來源／資料夾／輸出檔名／標題／新聞來源」的參數。新增市場＝新增一筆，
不改動既有市場（如 global 海外版）的行為。

欄位：
  funds  ── config/ 下的追蹤清單 JSON 檔名
  data   ── data/ 下的持股快照資料夾名（fetch_holdings 寫入、fund_intro 讀取）
  out    ── dashboard/ 下的輸出 HTML 檔名（gen_fund_dashboard 產出）
  title  ── 儀表板主標題
  subtitle ── 主標題旁英文小字
  news   ── 新聞來源鍵；"us"→arm/usnews、"tw"→arm/twnews
  news_label ── 新聞區塊標題（顯示用）
  tab_label ── 整合頁（render_combined）上層市場切換鈕顯示名
"""
from __future__ import annotations

MARKETS: dict[str, dict] = {
    "global": {
        "funds": "funds.json",
        "data": "funds",
        "out": "index.html",
        "title": "復華基金追蹤版本",
        "subtitle": "Fuh Hwa Fund Radar",
        "news": "us",
        "news_label": "昨夜美股重大新聞（公司與產業面）",
        "tab_label": "海外",
    },
    "tw": {
        "funds": "funds_tw.json",
        "data": "funds_tw",
        "out": "tw.html",
        "title": "復華台股基金追蹤版本",
        "subtitle": "Fuh Hwa Taiwan Fund Radar",
        "news": "tw",     # D1(b)：台股專用版型（台股盤後重點 ＋ 盤前美股影響），見 arm/twnews.py
        "news_label": "台股盤後重點 ＋ 盤前美股影響",
        "tab_label": "台股",
    },
}

DEFAULT = "global"


def get(market: str | None = None) -> dict:
    """回傳市場設定；未知市場拋 KeyError（呼叫端可回退 DEFAULT）。"""
    key = market or DEFAULT
    if key not in MARKETS:
        raise KeyError(f"未知市場 {key!r}；已註冊：{', '.join(MARKETS)}")
    return MARKETS[key]
