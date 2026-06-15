"""Dcard 股票看板 adapter（M4-2，使用者優先）—— 公開 API；現多由 Cloudflare 保護。

Dcard v2 公開 API（`/service/api/v2/forums/stock/posts`）近年加上 Cloudflare 驗證，未帶
合法憑證多回 403。本 adapter：
  - 預設嘗試公開 API（瀏覽器式標頭）；被擋（403/非 JSON）→ 回 []（誠實降級）。
  - 若設 `DCARD_COOKIE`（使用者登入後的 Cloudflare/驗證 cookie）或未來官方合作金鑰，帶上再試。
留與復華主角/競品/主動ETF 相關貼文 → SocialMention(platform="dcard")，reach=按讚數。
著作權/個資（M4-8）：只存標題+摘要+連結，內文不全文落地。
"""
from __future__ import annotations

import json
import os

from ...http import get_bytes
from .base import SocialMention
from .filters import extract_etfs, is_relevant
from . import base as _b

API = "https://www.dcard.tw/service/api/v2/forums/stock/posts?popular=false&limit=100"


def fetch(as_of: str | None = None, window_days: int = 7) -> list[SocialMention]:
    headers = {"Accept": "application/json", "Referer": "https://www.dcard.tw/f/stock"}
    cookie = os.environ.get("DCARD_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    try:
        raw = get_bytes(API, cache_ttl=1800, headers=headers).decode("utf-8", "ignore")
        posts = json.loads(raw)
    except Exception:
        return []                               # Cloudflare 擋 / 非 JSON → 誠實略過（待合作金鑰）
    if not isinstance(posts, list):
        return []
    lo = _b._minus_days(as_of, window_days) if as_of else None
    out: list[SocialMention] = []
    for p in posts:
        text = f"{p.get('title', '')}。{p.get('excerpt', '')}".strip("。")
        if not is_relevant(text):
            continue
        d = (p.get("createdAt") or "")[:10]
        if lo is not None and d and not (lo <= d <= as_of):
            continue
        pid = p.get("id")
        out.append(SocialMention(platform="dcard", author=f"Dcard匿名#{pid}", date=d or (as_of or ""),
                                 text=text[:300], url=f"https://www.dcard.tw/f/stock/p/{pid}" if pid else "",
                                 reach=int(p.get("likeCount") or 0), etfs=extract_etfs(text)))
    return out
