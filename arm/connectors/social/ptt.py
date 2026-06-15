"""PTT 股票板 adapter（M4-2）—— 免費、公開頁；over18 cookie，禮貌抓取。

抓 Stock 板索引頁標題 + 推文數（聲量 proxy），留與復華主角/競品/主動ETF 相關者。
公開討論串標題；爬取遵守 robots/限速，內文不全文落地（著作權，§18.5/M4-8）。
失敗（板規/反爬/網路）→ 回 []（誠實降級，不影響其他來源）。
"""
from __future__ import annotations

import re

from ...http import get_bytes
from .base import SocialMention
from .filters import extract_etfs, is_relevant
from . import base as _b

BASE = "https://www.ptt.cc"
INDEX = BASE + "/bbs/Stock/index.html"
_ENT = re.compile(r'<div class="r-ent">(.*?)</div>\s*</div>', re.S)
_TITLE = re.compile(r'<div class="title">\s*(?:<a href="([^"]+)">(.*?)</a>)?', re.S)
_PUSH = re.compile(r'<div class="nrec">(?:<span[^>]*>(.*?)</span>)?', re.S)
_DATE = re.compile(r'<div class="date">\s*(.*?)\s*</div>', re.S)


def _reach(push: str) -> int:
    if not push:
        return 0
    if push == "爆":
        return 100
    try:
        return int(push)
    except ValueError:
        return 0


def fetch(as_of: str | None = None, window_days: int = 7, pages: int = 2) -> list[SocialMention]:
    year = (as_of or "2026")[:4]
    out: list[SocialMention] = []
    try:
        html = get_bytes(INDEX, cache_ttl=1800,
                         headers={"Cookie": "over18=1"}).decode("utf-8", "ignore")
    except Exception:
        return out                              # PTT 抓不到 → 誠實略過
    for blk in _ENT.findall(html):
        mt = _TITLE.search(blk)
        if not mt or not mt.group(2):
            continue
        href, title = mt.group(1), re.sub(r"<[^>]+>", "", mt.group(2)).strip()
        if not is_relevant(title):
            continue
        push = (_PUSH.search(blk) or [None, ""]).group(1) or ""
        md = (_DATE.search(blk) or [None, ""]).group(1) or ""   # 格式 "M/DD"
        d = ""
        if "/" in md:
            mm, dd = md.split("/")
            d = f"{year}-{int(mm):02d}-{int(dd.strip()):02d}"
        out.append(SocialMention(platform="ptt", author="PTT_Stock", date=d or (as_of or ""),
                                 text=title, url=(BASE + href) if href else INDEX,
                                 reach=_reach(push), etfs=extract_etfs(title)))
    lo = _b._minus_days(as_of, window_days) if as_of else None
    return [m for m in out if not (lo and m.date and not (lo <= m.date <= as_of))]
