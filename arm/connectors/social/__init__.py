"""社群 / KOL 情報來源層（M4-2/M4-3）。

各平台爬取涉 ToS / 個資 / 著作權（M4-8），且多為登入/SPA：無單一公開 live 源。
故與 M2 競品持股 / M3 分點同策略——先以 drop-in 檔承接（Tier B），逐家 adapter
（YouTube/PTT/Dcard/vocus/新聞）授權後補實，仍回傳同一個 `SocialMention`，創意引擎不動。

創意引擎只透過 `recent_mentions()` 取料，與來源徹底解耦。
"""
from __future__ import annotations

from . import base, dcard, facebook, llm, news, ptt, youtube
from .base import (NoData, SocialMention, analyze, curated_mentions)  # re-export


def default_analyzer():
    """M4-3：有 ANTHROPIC_API_KEY 時回傳 Claude 逐則深析 callable，否則 None（用 baseline）。"""
    return llm.claude_analyzer()

SOURCES: dict[str, str] = {
    "news": "鉅亨/Yahoo股市 RSS（免費，已接 news.py）",
    "ptt": "PTT 股票板（公開頁 over18，已接 ptt.py；沙箱可能擋）",
    "dcard": "Dcard 股票看板（公開 API，現多由 Cloudflare 擋→需 DCARD_COOKIE/合作金鑰）",
    "youtube": "YouTube Data API v3（需 YOUTUBE_API_KEY）",
    "fb": "Facebook Graph API 粉專貼文（需 FB_ACCESS_TOKEN + config/social_fb_pages.json）",
}

# 免費/公開來源：永遠註冊（抓不到時各 adapter 自己回 [] 誠實降級）。
LIVE_ADAPTERS: dict[str, callable] = {
    "news": news.fetch,
    "ptt": ptt.fetch,
    "dcard": dcard.fetch,
}
# 需金鑰的來源：有憑證才註冊（避免空打）。
if youtube.available():
    LIVE_ADAPTERS["youtube"] = youtube.fetch
if facebook.available():
    LIVE_ADAPTERS["fb"] = facebook.fetch


def recent_mentions(as_of: str | None = None, window_days: int = 7) -> list[SocialMention]:
    """窗內社群情報：先 live adapters（目前無，待授權接），再 drop-in；依日期新→舊、聲量大→小。"""
    out: list[SocialMention] = []
    for name, fetch in LIVE_ADAPTERS.items():
        try:
            out += fetch(as_of, window_days) or []
        except Exception:
            continue                           # 單一來源失敗不影響其他（誠實略過）
    out += curated_mentions(as_of, window_days)
    return sorted(out, key=lambda m: (m.date, m.reach), reverse=True)
