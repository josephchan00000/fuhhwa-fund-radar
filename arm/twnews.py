"""台股重點（復華基金追蹤版本）—— 盤前／盤後自適應版型規格 ＋ 產出讀取 ＋ 合規掃描。

與 usnews 同一套 prompt-pack 哲學：
  · scripts/gen_twnews.py 依「現在時間」自動判定盤前/盤後模式，產對應提示包
    （reports/twnews/prompts/{date}.md）；
  · 會上網查證的 LLM 產一份 markdown 回存 reports/twnews/{date}.md；
  · dashboard 讀「最新一份」呈現、跑合規掃描、萃取加權／櫃買指數進今日重點。

盤前（開盤前／盤中）＝聚焦昨夜美股影響、台指期夜盤、盤前焦點個股、法人與題材預期；
盤後（收盤後）＝聚焦當日收盤數據、三大法人籌碼、族群輪動與重大公司事件。
讀取器／萃取／禁用詞掃描皆沿用 arm/usnews（純函式、可單測）。
"""
from __future__ import annotations

import re
from datetime import datetime, time
from pathlib import Path

from . import usnews
from .clock import TW_TZ                       # 台北時間 UTC+8（單一來源）

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "reports" / "twnews"
MARKET_CLOSE = time(13, 30)                    # 台股集中市場收盤

# 台股指數標籤（給 usnews.extract_indices 用）；brief 取前兩項
IDX_LABELS = [(("加權指數", "TAIEX", "集中市場"), "加權指數"),
              (("櫃買", "OTC", "上櫃"), "櫃買指數")]

# 盤後（收盤後）
SPEC_POST = f"""【版型：台股盤後重點】
範圍：當日台股（集中＋櫃買）之「公司與產業動因」＋盤面結構（權值/中小型輪動、
三大法人動向、除權息與重大公司事件）。聚焦：半導體/AI 供應鏈、電子權值、
題材族群輪動、法人籌碼；排除純技術線型喊盤與個股目標價。

【數量與門檻】**至少 4 則、上不封頂**，收錄所有「重要度 6 分以上」的當日台股公司/族群事件。
排序：先依重要度高→低，同分再新→舊。
{usnews.SRC_RULE_TW}

{usnews.ETYPE_RULE}
{usnews.SEV_RUBRIC}
{usnews.HILITE_RULE}
{usnews.BRIEF_STYLE}
{usnews.READ_RULE}
{usnews.LABEL_RULE}
{usnews.depth_note(180)}
{usnews.move_note('tw_post')}
{usnews.pick_note('tw_post')}

版面：
  ## 🔹盤後速覽
     ↑ 段名行原樣照抄（含 ##；儀表板與列印版只認「盤前／盤後速覽」）；內容：（加權指數、櫃買指數各 1 句：收盤點位＋漲跌幅、大漲大跌時加一句主因歸因
     （量能／權值股貢獻／法人籌碼）；可補電子/金融類股；
     末加 1 句市場解析：權值 vs 中小型、輪動或避險）
  🔹盤後卡（每則 180–300 字，依「分析深度」要求寫滿因果鏈；≥4 則）：
     標題（來源＋日期｜【新事件】或【延伸】｜重要度 N/10）  ← 括注三段缺一不可，供儀表板解析徽章
     1. 新聞摘要 2. 一句話重點 3. 漲跌分析 4. 對持股／族群影響 5. 對市場情緒影響
     6. 參考連結（每卡至少 1 條 [來源標題](URL) markdown 可點連結；
        指數/法人數字以證交所、櫃買中心官方為準）
  {usnews.DEEP_RULE.format(src="經濟日報（money.udn.com）產業/專題、工商時報、中央社專題、財訊／今周刊等台灣財經媒體深度文")}
  🔹資料侷限說明（指數/法人數字以證交所、櫃買中心官方為準）
  I. 合規揭露（附完整揭露段）
用語合規：僅市場資訊彙編/教育用途、非投資建議；禁用詞同 usnews.BANNED；
不預測報酬、不以過去績效推未來；勿杜撰數字，查不到誠實註明。"""

# 盤前（開盤前／盤中）—— 市場尚未收盤，抓「最新盤前重要新聞」
SPEC_PRE = f"""【版型：台股盤前重點】
情境：台股尚未收盤（開盤前或盤中），請彙整「最新、最重要」的盤前情報。
範圍：①昨夜美股與費半／台積電 ADR 對台股電子權值的影響；②台指期夜盤走勢與方向；
③盤前焦點個股與族群（半導體/AI 供應鏈、記憶體、電子權值、題材股）之最新消息、
法人動向與外資買賣超預期；④當日除權息、法說會、重大公司公告與國際事件。
排除純技術線型喊盤與個股目標價喊價（機構目標價調整可中性陳述、附日期）。

【數量與門檻】**至少 4 則、上不封頂**，收錄所有「重要度 6 分以上」的盤前重要情報。
排序：先依重要度高→低，同分再新→舊。
{usnews.SRC_RULE_TW}

{usnews.ETYPE_RULE}
{usnews.SEV_RUBRIC}
{usnews.HILITE_RULE}
{usnews.BRIEF_STYLE}
{usnews.READ_RULE}
{usnews.LABEL_RULE}
{usnews.depth_note(180)}
{usnews.move_note('tw_pre')}
{usnews.pick_note('tw_pre')}

版面：
  ## 🔹盤前速覽
     ↑ 段名行原樣照抄（含 ##）；內容：（台指期夜盤點位＋漲跌、台積電 ADR、費半昨夜表現各 1 句，
     大漲大跌時各加一句主因；末加 1 句盤前研判：預期開盤方向與資金焦點——中性陳述、不作漲跌預測）
  🔹盤前卡（每則 180–300 字，依「分析深度」要求寫滿因果鏈；≥4 則）：
     標題（來源＋日期｜【新事件】或【延伸】｜重要度 N/10）  ← 括注三段缺一不可，供儀表板解析徽章
     1. 新聞摘要 2. 一句話重點 3. 漲跌分析 4. 對持股／族群影響 5. 對盤前市場情緒影響
     6. 參考連結（每卡至少 1 條 [來源標題](URL) markdown 可點連結）
  {usnews.DEEP_RULE.format(src="經濟日報（money.udn.com）產業/專題、工商時報、中央社專題、財訊／今周刊等台灣財經媒體深度文")}
  🔹資料侷限說明（盤前資訊變動快，開盤後以實際成交為準）
  I. 合規揭露（附完整揭露段）
用語合規：僅市場資訊彙編/教育用途、非投資建議；禁用詞同 usnews.BANNED；
不預測報酬、不以過去績效推未來、不對開盤漲跌作預測性喊話；勿杜撰數字，查不到誠實註明。"""

# 向後相容：預設別名指向盤後版型
SPEC = SPEC_POST


def session_mode(now: datetime | None = None) -> str:
    """依台北時間判定台股新聞模式：收盤（13:30）前＝'pre'（盤前/盤中），之後＝'post'（盤後）。

    週末視為 'post'（延用最近一個交易日的盤後視角）。"""
    n = now or datetime.now(TW_TZ)
    if n.weekday() >= 5:                       # 週六日
        return "post"
    return "pre" if n.time() < MARKET_CLOSE else "post"


def spec_for(mode: str) -> str:
    """回對應模式的版型規格（'pre'→盤前、其餘→盤後）。"""
    return SPEC_PRE if mode == "pre" else SPEC_POST


def _mode_of(md: str) -> str:
    """由 md 標題判定盤前/盤後（〈台股盤前重點〉→'pre'）；判不出回 'post'。"""
    head = (md or "")[:60]
    return "pre" if "盤前" in head else "post"


def load_latest() -> dict | None:
    """dashboard 用：最新一份台股重點 {date, md, mode, label, banned_hits}。"""
    if not NEWS_DIR.exists():
        return None
    dates = sorted({m.group(1) for f in NEWS_DIR.glob("*.md")
                    if (m := re.match(r"(\d{4}-\d{2}-\d{2})\.md$", f.name))}, reverse=True)
    if not dates:
        return None
    d = dates[0]
    md = (NEWS_DIR / f"{d}.md").read_text(encoding="utf-8")
    mode = _mode_of(md)
    return {"date": d, "md": md, "mode": mode,
            "label": "台股盤前重點" if mode == "pre" else "台股盤後重點",
            "banned_hits": usnews.compliance_scan(md)}


def extract_indices(md: str) -> list[dict]:
    """台股加權／櫃買指數速覽（沿用 usnews 萃取器、換台股標籤）。"""
    return usnews.extract_indices(md, labels=IDX_LABELS)
