"""YouTube adapter（M4-2）—— YouTube Data API v3；需 `YOUTUBE_API_KEY`。

對復華主角/品牌關鍵字做 search.list（近 window 天、依日期），回傳影片標題+頻道+連結。
未設金鑰 → available()=False、fetch 回 []（__init__ 不註冊）。觀看數需另呼叫 videos.list，
為省額度預設不取（reach=0）；要更準可後續擴充。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from ...http import get_bytes
from .base import SocialMention
from .filters import extract_etfs

SEARCH = "https://www.googleapis.com/youtube/v3/search"
# 控制查詢數＝控制 API 額度（search.list 每次 100 單位/日上限 10000）；4 組已涵蓋主角，避免額度用盡。
QUERIES = ["復華 主動式 ETF", "00991A", "00998A 復華", "00986D 復華"]


def available() -> bool:
    return bool(os.environ.get("YOUTUBE_API_KEY"))


def fetch(as_of: str | None = None, window_days: int = 7) -> list[SocialMention]:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return []
    after = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[SocialMention] = []
    seen: set[str] = set()
    for q in QUERIES:
        url = (f"{SEARCH}?part=snippet&type=video&order=date&maxResults=10"
               f"&publishedAfter={after}&q={q.replace(' ', '%20')}&key={key}")
        try:
            data = json.loads(get_bytes(url, cache_ttl=3 * 3600).decode("utf-8", "ignore"))
        except Exception:
            continue
        for it in data.get("items", []):
            vid = (it.get("id") or {}).get("videoId")
            sn = it.get("snippet") or {}
            if not vid or vid in seen:
                continue
            seen.add(vid)
            text = f"{sn.get('title', '')}。{sn.get('description', '')}".strip("。")
            out.append(SocialMention(platform="youtube", author=sn.get("channelTitle", ""),
                                     date=(sn.get("publishedAt") or "")[:10], text=text[:300],
                                     url=f"https://www.youtube.com/watch?v={vid}",
                                     etfs=extract_etfs(text)))
    return out
