"""社群 / KOL 情報來源層。

2026-11-01 拿掉舊的本機流程時，這裡只留臉書粉專（facebook.py）和共用的 base、filters（使用者決定留著）：
docs/social_api_plan.md 第二階段「FB 自家粉專」打算沿用。基金的 PTT、YouTube 社群由 arm/fundnews.py 負責，和這裡無關。
各平台爬取涉 ToS / 個資 / 著作權：一律回傳同一個 `SocialMention`，呼叫端只透過 `recent_mentions()` 取料。
"""
from __future__ import annotations

from . import base, facebook
from .base import (NoData, SocialMention, analyze, curated_mentions)  # re-export

SOURCES: dict[str, str] = {
    "fb": "Facebook Graph API 粉專貼文（需 FB_ACCESS_TOKEN + config/social_fb_pages.json）",
}

# 需金鑰的來源：有憑證才註冊（避免空打）。
LIVE_ADAPTERS: dict[str, callable] = {}
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
