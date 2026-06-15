"""Facebook adapter（M4-2，使用者優先）—— Graph API；需 `FB_ACCESS_TOKEN`。

⚠️ 現實限制（必讀）：Facebook 自 2018 起**移除公開貼文/社團搜尋**，Graph API 只能讀
「你有權限的粉專（Page）」貼文。故本 adapter 監看**設定好的粉專清單**
（`config/social_fb_pages.json`：[{id|username, name}]，如復華投信官方粉專、財經媒體粉專），
用 `FB_ACCESS_TOKEN`（Page/User token，需 pages_read_engagement 權限）逐頁讀近期貼文。
個人/社團/他人貼文之爬取違反 FB 條款（M4-8），本系統不做。
未設 token 或無粉專清單 → 回 []（__init__ 不註冊）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ...http import get_bytes
from .base import SocialMention
from .filters import extract_etfs, is_relevant
from . import base as _b

GRAPH = "https://graph.facebook.com/v19.0"
PAGES_CFG = Path(__file__).resolve().parents[3] / "config" / "social_fb_pages.json"


def available() -> bool:
    return bool(os.environ.get("FB_ACCESS_TOKEN")) and PAGES_CFG.exists()


def _pages() -> list[dict]:
    if not PAGES_CFG.exists():
        return []
    try:
        data = json.loads(PAGES_CFG.read_text(encoding="utf-8"))
    except ValueError:
        return []
    return data.get("pages", data) if isinstance(data, (dict, list)) else []


def fetch(as_of: str | None = None, window_days: int = 7) -> list[SocialMention]:
    token = os.environ.get("FB_ACCESS_TOKEN")
    pages = _pages()
    if not token or not pages:
        return []
    lo = _b._minus_days(as_of, window_days) if as_of else None
    out: list[SocialMention] = []
    for pg in pages:
        pid, pname = pg.get("id") or pg.get("username"), pg.get("name", "")
        if not pid:
            continue
        url = (f"{GRAPH}/{pid}/posts?fields=message,created_time,permalink_url,"
               f"shares,reactions.summary(true)&limit=25&access_token={token}")
        try:
            data = json.loads(get_bytes(url, cache_ttl=3 * 3600).decode("utf-8", "ignore"))
        except Exception:
            continue
        for p in data.get("data", []):
            text = p.get("message", "")
            if not text or not is_relevant(text):
                continue
            d = (p.get("created_time") or "")[:10]
            if lo is not None and d and not (lo <= d <= as_of):
                continue
            reach = ((p.get("reactions") or {}).get("summary") or {}).get("total_count", 0)
            out.append(SocialMention(platform="fb", author=pname or str(pid), date=d or (as_of or ""),
                                     text=text[:300], url=p.get("permalink_url", ""),
                                     reach=int(reach or 0), etfs=extract_etfs(text)))
    return out
