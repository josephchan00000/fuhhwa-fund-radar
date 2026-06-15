"""baseline 模板文案（M6 設計決策 ①：LLM-agnostic 基線）。

不需要任何 LLM 即可產出**四通路**文案（line / ig / sales / punchy）。
純粹重組想法與佐證、不自創數字 → 通過「數字不得杜撰」檢查（恆 0 違規）。
LLM（自動 API 或 prompt-pack）只是**選用覆寫層**，未接時系統照常出基線稿。

通路：
  line   — LINE/推播短文，emoji + CTA
  ig     — IG/社群貼文，含 hashtag
  sales  — 理專/業務話術，完整脈絡
  punchy — 一句 hook / 標題
"""
from __future__ import annotations

import re

from .parse import Idea, ReportDoc

CHANNELS = ("punchy", "line", "ig", "sales")

# 依面向的行動呼籲（CTA）；刻意溫和，觸發合規者由標注層補揭露。
_CTA = {
    "績效": "定期定額，參與主動式ETF",
    "資金流": "定期定額，參與主動式ETF",
    "同類排名": "定期定額，參與主動式ETF",
    "籌碼": "鎖定經理人換股動向",
    "分點推敲": "觀察法人籌碼動向",
    "持股差異化": "了解這檔的選股邏輯",
    "題材": "掌握題材順風",
    "配息時程": "留意配息評價日時程",
    "逆向誠實": "逢回分批、理性參與",
}
_CTA_DEFAULT = "了解更多 復華主動式ETF"

# 依面向的 hashtag
_TAGS = {
    "績效": ["績效", "主動式ETF"],
    "資金流": ["資金流", "人氣ETF"],
    "同類排名": ["排行榜", "主動式ETF"],
    "籌碼": ["經理人換股", "主動操作"],
    "分點推敲": ["法人籌碼", "聰明錢"],
    "持股差異化": ["選股", "主動式ETF"],
    "題材": ["題材", "AI半導體"],
    "配息時程": ["配息", "現金流"],
    "逆向誠實": ["逆向思考", "定期定額"],
}


def short_name(name: str) -> str:
    """『復華台灣未來50主動式ETF』→『復華台灣未來50』（去掉通用尾綴，利於版面）。"""
    return re.sub(r"(主動式)?ETF$", "", name).strip() or name


def _hook(headline: str) -> str:
    """從想法萃取一句 hook：優先取『：』前的標語，否則取第一個逗號前的子句。"""
    for sep in ("：", ":"):
        if sep in headline:
            head = headline.split(sep, 1)[0].strip()
            if 2 <= len(head) <= 18:
                return head
    for sep in ("，", ",", "、"):
        if sep in headline:
            head = headline.split(sep, 1)[0].strip()
            if head:
                return head
    return headline.strip()


def render(idea: Idea, doc: ReportDoc) -> dict[str, str]:
    """回傳 {channel: core_text}（未含揭露語；揭露由 __init__.generate 依合規補上）。"""
    sn = short_name(doc.name)
    cta = _CTA.get(idea.category, _CTA_DEFAULT)
    tags = " ".join(f"#{t}" for t in (_TAGS.get(idea.category, []) + [sn]))
    hl, ev, fmt = idea.headline, idea.evidence, idea.content_format

    punchy = _hook(hl)
    line = f"【{sn}｜{idea.category}】{hl}\n📊 {ev}\n👉 {cta}"
    ig = f"{hl}\n\n📊 {ev}\n\n{tags}"
    sales = (f"{sn}（{doc.etf_id}）今日觀察〔{idea.category}〕：{hl}。"
             f"佐證：{ev}。" + (f"建議以「{fmt}」呈現。" if fmt else ""))
    return {"punchy": punchy, "line": line, "ig": ig, "sales": sales}
