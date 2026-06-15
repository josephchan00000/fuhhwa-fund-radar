"""統一社群 / KOL 情報介面（M4-2/M4-3）—— 創意情報層與來源解耦的接縫。

社群/KOL 賣點、聲量、疑似業配（§18.5）無單一乾淨公開 live 源，且各平台爬取涉
ToS / 個資 / 著作權（M4-8）：故比照 M2 競品持股、M3 分點，採 **source-agnostic** 設計
——不論 YouTube / PTT / Dcard / vocus / 新聞，全部歸一成 `SocialMention`，創意引擎只吃這個。

落檔即生效：把社群情報放成 `config/social_mentions/{date}.json` 引擎立即取用、不改碼。
Tier B：聲量 / 疑似業配 / 情緒一律為**推估**，標來源與 as-of，對外發布前人工核實。

逐則分析（情緒/賣點/疑似業配）先給**確定性 baseline**；`analyze(m, llm=...)` 預留 LLM 接口，
日後接 Claude 逐則深析（M4-3）時不動呼叫端。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

CFG = Path(__file__).resolve().parents[3] / "config"
DROP_DIR = CFG / "social_mentions"


class NoData(Exception):
    """該窗目前無可用社群來源（各平台爬取涉 ToS/個資，待授權 adapter 或 drop-in）。"""


@dataclass(frozen=True)
class SocialMention:
    platform: str                 # youtube / ptt / dcard / vocus / news / fb / threads...
    author: str                   # KOL / 帳號 / 媒體名
    date: str                     # 發布日 ISO
    text: str                     # 內文 / 標題 / 摘要
    url: str = ""
    etfs: tuple = ()              # 文中提及的 ETF 代號，如 ("00991A",)；空=泛論
    reach: int = 0               # 觸及 / 觀看 / 讚數（推估）
    tier: str = "B"


# ── 賣點詞庫（對齊本系統賣點面向）：命中即視為「社群在講這個賣點」 ──
SELLING_POINT_LEXICON = {
    "主動選股": ["主動", "選股", "active share", "主動度", "經理人"],
    "配息入息": ["配息", "月配", "季配", "殖利率", "月月領", "現金流", "領息", "息率"],
    "績效贏大盤": ["報酬", "績效", "贏", "0050", "alpha", "超額", "大漲"],
    "規模人氣": ["規模", "受益人", "破紀錄", "募集", "熱賣"],
    "題材順風": ["ai", "半導體", "金融股", "金融債", "題材", "護國"],
    "低門檻定額": ["定期定額", "銅板", "門檻", "小資", "1萬", "存"],
}
_POS = ["看好", "推薦", "值得", "亮眼", "強勢", "續抱", "加碼", "潛力", "噴", "甜甜價", "佈局", "讚"]
_NEG = ["雷", "避開", "別買", "套牢", "失望", "疑慮", "風險", "崩", "重挫", "出場", "貴", "泡沫"]
# 疑似業配訊號（→ 反推同業 KOL 投放）；一律標「疑似・推估」
_AD = ["業配", "合作", "sponsored", "廠商提供", "邀稿", "抽獎", "團購", "#廣告",
       "合作邀約", "贊助", "本影片由", "與.*合作"]


def analyze(m: SocialMention, llm=None) -> dict:
    """逐則分析（確定性 baseline）。回傳 selling_points / sentiment / suspected_ad / reach_bucket。

    `llm`（預留）：日後傳入 Claude 逐則深析 callable，覆蓋/增補 baseline；現未啟用。
    """
    tl = (m.text or "").lower()
    sp = [name for name, kws in SELLING_POINT_LEXICON.items()
          if any(k.lower() in tl for k in kws)]
    pos = sum(1 for w in _POS if w.lower() in tl)
    neg = sum(1 for w in _NEG if w.lower() in tl)
    sentiment = "正面" if pos > neg else ("負面" if neg > pos else "中性")
    ad_terms = [w for w in _AD if "*" not in w and w.lower() in tl]
    result = {
        "selling_points": sp,
        "sentiment": sentiment,
        "sentiment_score": pos - neg,
        "suspected_ad": bool(ad_terms),
        "ad_terms": ad_terms,
        "reach_bucket": "高" if m.reach >= 10000 else ("中" if m.reach >= 1000 else "低"),
    }
    if llm is not None:                        # 預留：LLM 逐則深析（M4-3）
        try:
            result.update(llm(m, result) or {})
        except Exception:
            pass
    return result


def _minus_days(iso: str, n: int) -> str:
    return (date.fromisoformat(iso) - timedelta(days=n)).isoformat()


def curated_mentions(as_of: str | None = None, window_days: int = 7) -> list[SocialMention]:
    """社群情報 drop-in（`config/social_mentions/*.json`）；`_` 開頭檔（如 _SAMPLE）不載入。

    每檔可為 mention 陣列，或 {as_of, provenance, mentions:[...]}。窗以 as_of 往回 window_days。
    """
    if not DROP_DIR.exists():
        return []
    lo = _minus_days(as_of, window_days) if as_of else None
    out: list[SocialMention] = []
    for path in sorted(DROP_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else (data.get("mentions") or [])
        for it in items:
            d = it.get("date", "")
            if lo is not None and d and not (lo <= d <= as_of):
                continue
            out.append(SocialMention(
                platform=it.get("platform", ""), author=it.get("author", ""),
                date=d, text=it.get("text", ""), url=it.get("url", ""),
                etfs=tuple(it.get("etfs") or ()), reach=int(it.get("reach") or 0),
                tier=it.get("tier", "B")))
    return out
