"""新聞 RSS adapter（M4-2）—— 免費、無需金鑰；鉅亨/Yahoo 股市等財經 RSS。

抓 RSS、留與復華主角/競品/主動ETF 相關者 → SocialMention(platform="news")。
新聞屬公開標題/摘要，著作權風險低（只存標題+連結+摘要、標來源）。
"""
from __future__ import annotations

import re
from email.utils import parsedate_to_datetime

from ...http import get_bytes
from .base import SocialMention
from .filters import extract_etfs, is_relevant
from . import base as _b  # window helper

FEEDS = [
    ("鉅亨網", "https://news.cnyes.com/rss/v1/news/category/tw_stock"),
    ("鉅亨網", "https://news.cnyes.com/rss/v1/news/category/headline"),
    ("Yahoo股市", "https://tw.stock.yahoo.com/rss"),
]
_ITEM = re.compile(r"<item>(.*?)</item>", re.S | re.I)
_TAG = lambda t, s: (re.search(rf"<{t}[^>]*>(.*?)</{t}>", s, re.S | re.I) or [None, ""])[1]
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_HTML = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    m = _CDATA.search(s or "")
    s = m.group(1) if m else (s or "")
    return _HTML.sub("", s).strip()


def _iso(pub: str) -> str:
    try:
        return parsedate_to_datetime(pub).date().isoformat()
    except (TypeError, ValueError):
        return ""


def fetch(as_of: str | None = None, window_days: int = 7) -> list[SocialMention]:
    lo = _b._minus_days(as_of, window_days) if as_of else None
    out: list[SocialMention] = []
    seen: set[str] = set()
    for source, url in FEEDS:
        try:
            xml = get_bytes(url, cache_ttl=1800).decode("utf-8", "ignore")
        except Exception:
            continue
        for raw in _ITEM.findall(xml):
            title = _clean(_TAG("title", raw))
            desc = _clean(_TAG("description", raw))
            link = _clean(_TAG("link", raw))
            text = f"{title}。{desc}".strip("。")
            if not is_relevant(text) or link in seen:
                continue
            d = _iso(_TAG("pubDate", raw))
            if lo is not None and d and not (lo <= d <= as_of):
                continue
            seen.add(link)
            out.append(SocialMention(platform="news", author=source, date=d or (as_of or ""),
                                     text=text[:300], url=link, etfs=extract_etfs(text)))
    return out
