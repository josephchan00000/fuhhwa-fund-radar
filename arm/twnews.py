"""台股新聞（復華台股基金追蹤版本｜D1(b)）—— 兩版型：台股盤後重點 ＋ 盤前美股影響。

與海外版「昨夜美股」(arm/usnews.py) 平行的台股專用版型；共用同一套 prompt-pack 哲學與
禁用詞合規掃描（直接沿用 usnews.BANNED / compliance_scan，不重複維護）：
  · scripts/gen_twnews.py 產『可貼進 Claude 的提示包』（reports/twnews/prompts/{date}.md），
    內含兩版型完整規格＋台北日期＋今日台股交易日＋昨夜美股交易日；
  · Claude 產兩份 markdown 回存 reports/twnews/{date}_v1.md（台股盤後重點）與 _v2.md（盤前美股影響）；
  · dashboard 讀「最新一份」呈現並標合規燈。

本檔只放：規格文字、讀取器、揭露段（純函式、可單測）。合規掃描沿用 usnews。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from . import usnews
from .usnews import BANNED, compliance_scan  # noqa: F401 （沿用同一套禁用詞與掃描）

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "reports" / "twnews"

# 版型切換鈕顯示名（dashboard 用）
V1_LABEL = "台股盤後重點"
V2_LABEL = "盤前美股影響"

# 新聞區塊尚無產出時的提示
EMPTY_HINT = ("尚無台股新聞。請執行 <code>python scripts/gen_twnews.py</code> 產提示包，"
              "再由 Claude 產出兩版型（台股盤後重點＋盤前美股影響）。")

ATTRIBUTION_HINT = usnews.ATTRIBUTION_HINT

# 台股（國內）基金揭露段：不涉境外/匯率語，改列平衡型債券利率風險。
DISCLOSURE = (
    "本資料僅供參考，非屬投資建議或招攬；本文所載資料多引自公開來源，已於文末列示出處，"
    "本公司不保證其完整、即時或正確，亦不負損益責任。基金投資有風險，申購前應詳閱公開說明書／"
    "投資人須知；過去績效不代表未來表現，淨值可能因市場變動而上下。投資人申購本基金係持有基金"
    "受益憑證，非本文提及之個股或投資標的；平衡型基金另涉債券之利率與信用風險。"
)

# 版型一：台股盤後重點（完整版）
SPEC_V1 = """【版型一：台股盤後重點（完整版）】
範圍：只收台股上市櫃「公司與產業面」動因（個股重大訊息：財報/財測/月營收、法說會、接單/擴產、
資本支出、併購、策略合作、人事、監管/法律；產業鏈：半導體/AI 伺服器/PCB/被動元件/光通訊/
機殼散熱/金融/傳產…；三大法人（外資/投信/自營）買賣超與資金流向；外資券商評等/目標調整——
以『該機構表示／認為／估測（日期）』轉述、不直接標目標價數字為投資建議）。排除單純加權指數
漲跌與總經/利率解讀。時間：最近一個台股交易日收盤後。每則附來源與日期（例：2026/07/02）。
Top 3 列入須至少符合四項中三項：(1) 見於主要財經媒體（經濟日報／工商時報／鉅亨 Anue／
MoneyDJ 或 Reuters/Bloomberg 台股報導）頭條或焦點；(2) 三大法人明顯偏多／偏空或單日大額
買賣超；(3) 對相關個股造成單日 ±3% 以上或成交爆量；(4) 具產業鏈結構性影響（>3 個月）。
僅符合 1–2 項→次級觀察摘要。
分類：【新消息】首次曝光／【事件更新】既有事件新進展／【延伸】二度報導或專欄（註明非首發）。新→舊。
版面：
  🔹台股盤後總覽（加權指數／櫃買指數／半導體類股 各 1 句 ＋ 三大法人買賣超與資金流向 1 句
     ＋ 1 句盤面解析：類股輪動與資金主題）
  🔹Top 3 個股／產業新聞卡（每則 120–180 字）：
     標題（來源＋日期｜消息屬性）
     1. 新聞摘要（2–3 句聚焦事實） 2. 一句話重點 3. 對公司影響
     4. 對供應鏈／競爭者影響 5. 對盤面情緒與股價影響 6. 參考資料（逐條列來源與機構評論日期）
  🔹次級觀察摘要（不足三則時補延伸觀察：法說會效應／分析師報告／族群輪動）
  I. 合規揭露（附完整揭露段）
用語合規：僅市場資訊彙編／教育用途、非投資建議；禁用詞見 BANNED；機構觀點以
『該機構表示／認為／估測（日期）』呈現；不預測報酬、不以過去績效推未來。
若查無足量或無法查證，誠實加「資料侷限說明」，切勿杜撰。"""

# 版型二：盤前美股影響（精簡版）—— 昨夜美股對今日台股盤前之傳導
SPEC_V2 = """【版型二：盤前美股影響（精簡版）】
聚焦「昨夜美股 → 今日台股盤前」的傳導鏈，供盤前參考（非買賣建議）。收：
  · 費城半導體（SOX）／Nasdaq／AI 晶片鏈美股（NVIDIA、AMD、美光、博通、台積電 ADR…）
    的走勢與公司／產業動因；
  · 台廠 ADR（台積電 ADR、聯電 ADR、日月光 ADR、中華電 ADR 等）漲跌；
  · 與台股權值股及供應鏈的連動（台積電、聯發科、鴻海、AI 伺服器鏈、PCB、被動元件、光通訊…）。
排除單純 Fed／利率／美股大盤指數漲跌解讀。
每則輸出：
  標題（來源＋日期｜消息屬性）
  1. 昨夜美股摘要（聚焦公司／產業事實） 2. 濃縮成一句話 3. 對應台股受惠／受壓族群
  4. 台廠 ADR 與盤前氛圍 5. 今日台股盤前觀察（中性描述，非買賣建議）
末尾附合規短語（非投資建議）；不預測報酬、不以過去績效推未來。"""


def tw_session_date(today: date | None = None) -> date:
    """回傳最近一個台股交易日（今日為工作日取今日，否則回推至上一個工作日）。

    以星期粗判，實際國定假日／颱風假由提示包請 Claude 查證。"""
    d = today or date.today()
    while d.weekday() >= 5:      # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def us_session_date(today: date | None = None) -> date:
    """盤前美股影響對應的最近美股交易日（沿用 usnews 之邏輯：台北 D 早上收的美股＝美東 D-1）。"""
    return usnews.us_session_date(today)


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
    """dashboard 用：最新一份台股新聞（含兩版型內容與合規掃描結果）。"""
    p = _latest_pair()
    if not p:
        return None
    p["banned_hits"] = compliance_scan((p.get("v1") or "") + (p.get("v2") or ""))
    return p
