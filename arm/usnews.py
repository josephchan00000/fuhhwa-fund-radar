"""昨夜美股新聞（復華基金追蹤版本）—— 兩版型規格常數 ＋ 產出讀取 ＋ 合規掃描。

即時新聞需要「會上網查證的 LLM」，純 Python 無法自動生成 → 沿用本專案 prompt-pack 哲學：
  · scripts/gen_usnews.py 產一份『可貼進 Claude 的提示包』（reports/usnews/prompts/{date}.md），
    內含兩版型完整規格＋當日日期＋昨夜美股交易日；
  · Claude 產兩份 markdown 回存 reports/usnews/{date}_v1.md（Top3 速寫包）與 _v2.md（精簡版）；
  · dashboard / 報告讀「最新一份」呈現，並跑合規掃描標注。

本檔只放：規格文字、讀取器、合規禁用詞掃描（純函式、可單測）。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "reports" / "usnews"

# 版型切換鈕顯示名（dashboard 用；與 twnews 對稱以便通用分派）
V1_LABEL = "Top 3 速寫包"
V2_LABEL = "精簡版"

# 新聞區塊尚無產出時的提示
EMPTY_HINT = ("尚無昨夜美股新聞。請執行 <code>python scripts/gen_usnews.py</code> 產提示包，"
              "再由 Claude 產出兩版型。")

# 新聞版型硬性禁用詞（用戶規格 F ＋ compliance 絕對化字眼）
BANNED = ["保證", "穩賺", "必賺", "包賺", "唯一", "建議買賣", "建議買", "建議賣",
          "目標價", "零風險", "無風險", "穩賺不賠"]

# 機構觀點須以此類語氣呈現（提醒用）
ATTRIBUTION_HINT = "該機構表示／認為／估測（日期）"

DISCLOSURE = (
    "本資料僅供參考，非屬投資建議或招攬；本文所載資料多引自公開來源，已於文末列示出處，"
    "本公司不保證其完整、即時或正確，亦不負損益責任。基金投資有風險，申購前應詳閱公開說明書／"
    "投資人須知；過去績效不代表未來表現，淨值可能因市場變動而上下。境外基金涉及匯率與國際市場"
    "風險；使用衍生性商品者另涉及槓桿、流動性與對手風險。"
)

# 版型一：〈昨夜美股公司與產業面 Top 3 速寫包〉（完整版）
SPEC_V1 = """【版型一：昨夜美股公司與產業面 Top 3 速寫包】
範圍：只收「公司與產業動因」（AI/晶片/雲端/電動車/通訊/製造鏈；企業合作、併購、
產品發表、重大投資/資本支出；財報/財測/營收預告、公司聲明；供應鏈調整、人事異動；
具實質營運影響的監管/法律事件）。排除單純 Fed/利率/大盤漲跌。
主要訊源 Reuters/Bloomberg/WSJ/FT，可各補 ≤1 段 JPMorgan/Goldman Sachs/Morgan Stanley/
BlackRock 當日評論（附日期）。每則附來源連結與台北時間戳（例：2026/07/02 05:30 TST）。
Top 3 列入須至少符合四項中三項：(1) 同現於 Reuters/Bloomberg/WSJ/FT 首頁或 Most Read/Lead；
(2) 被 ≥2 家主要外資機構評論引用/延伸；(3) 對 Nasdaq/費半/S&P500 任一成分股造成隔夜 ±2% 以上；
(4) 具結構性影響（產業鏈或營運前景 >3 個月）。僅符合 1–2 項→次級觀察摘要。
分類：【新消息】首次曝光／【事件更新】既有事件新進展／【延伸】二度報導或專欄（註明非首發）。新→舊。
版面：
  🔹前後 24 小時重大公司與產業事項總覽（Nasdaq／費半／S&P500 各 1 句 ＋ 1 句市場解析：主題動能與板塊輪動）
  🔹Top 3 新聞卡（每則 120–180 字）：
     標題（來源＋日期＋TST｜消息屬性）
     1. 新聞摘要（2–3 句聚焦事實） 2. 一句話重點 3. 對公司影響
     4. 對競爭者／合作方影響 5. 對市場情緒與股價影響 6. 參考資料（逐條列來源與機構評論日期）
  🔹次級觀察摘要（不足三則時補延伸觀察：法說會效應／分析師報告／行業趨勢）
  I. 合規揭露（附完整揭露段）
用語合規：僅市場資訊彙編/教育用途、非投資建議；禁用詞見 BANNED；機構觀點以
『該機構表示／認為／估測（日期）』呈現；不預測報酬、不以過去績效推未來。
若查無足量或無法查證，誠實加「資料侷限說明」，切勿杜撰。"""

# 版型二：昨夜美股重點（精簡版）
SPEC_V2 = """【版型二：昨夜美股重點（精簡版）】
聚焦 Nasdaq／費城半導體／S&P500，只收公司行為或產業動因（AI 投資、企業合作、併購、
產品發表、產業鏈合作、財報/財測、重大投資/資本支出、供應鏈調整、人事異動、監管/法律事件），
不含單純 Fed/利率/大盤漲跌。
消息屬性：先確認事件首發日期——過去 24 小時首發＝【新消息】；對數日前事件的延伸/二度報導/專欄＝
【延伸】（若只是重複舊聞加註「（專欄/二次報導，非首發）」）；既有事件新進展（簽約/金額確定/正式聲明）＝【事件更新】。
排序：【新消息】最前、依首發日期近→遠；【延伸】/【事件更新】其後。
每則輸出：
  新聞標題（來源 + 日期｜消息屬性）
  1. 新聞摘要 2. 濃縮成一句話（簡短有力） 3. 對公司影響 4. 對競爭者/合作方影響 5. 對市場情緒與股價影響
末尾附合規短語（非投資建議）。"""


def us_session_date(today: date | None = None) -> date:
    """給定台北日期，回傳『昨夜美股』對應的美股交易日（最近一個美股工作日）。

    台北 D 日早上收的美股＝美東 D-1；週一早上對應的最近美股交易日為上週五（略過假日，
    提示包會請 Claude 自行以實際交易日查證）。"""
    d = (today or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:      # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


# 否定詞：緊鄰禁用詞前方者視為合規揭露語（沿用 arm/copy/compliance.py 的 _NEG 慣例）。
_NEG = ("非", "不", "無", "未", "免")


def compliance_scan(text: str) -> list[str]:
    """回傳文中出現的禁用詞（去重）。空＝乾淨。

    命中禁用詞時，若其前兩字內含否定詞（非／不／無／未／免），視為合規揭露語（如『並非保證』
    『並非無風險』『非零風險』『不保證』），不計入違規；避免把必附揭露或否定句誤判為違規。"""
    t = text or ""
    hits: set[str] = set()
    for w in BANNED:
        i = t.find(w)
        while i != -1:
            prev = t[max(0, i - 2):i]
            if not any(n in prev for n in _NEG):
                hits.add(w)
                break                      # 出現一次未被否定即算違規
            i = t.find(w, i + 1)           # 此處被否定，繼續找下一個同詞
    return sorted(hits)


def _latest_pair() -> dict | None:
    """找最新一組 {date}_v1.md / _v2.md。回 {date, v1, v2}（缺的那版為 None）。"""
    if not NEWS_DIR.exists():
        return None
    dates = sorted({m.group(1) for f in NEWS_DIR.glob("*_v*.md")
                    if (m := re.match(r"(\d{4}-\d{2}-\d{2})_v[12]\.md", f.name))}, reverse=True)
    if not dates:
        return None
    d = dates[0]
    rd = lambda v: (NEWS_DIR / f"{d}_{v}.md").read_text(encoding="utf-8") \
        if (NEWS_DIR / f"{d}_{v}.md").exists() else None
    return {"date": d, "v1": rd("v1"), "v2": rd("v2")}


def load_latest() -> dict | None:
    """dashboard 用：最新一份昨夜美股新聞（含兩版型內容與合規掃描結果）。"""
    p = _latest_pair()
    if not p:
        return None
    p["banned_hits"] = compliance_scan((p.get("v1") or "") + (p.get("v2") or ""))
    return p
