"""Google News RSS 連接器 —— 自動擷取『近一週、帶發文時間』的台灣財經新聞。

每次更新都要最新：本連接器讓新聞/輿論不靠人工，依關鍵字即時拉 Google News（台灣繁中），
解析 pubDate 過濾近 N 天、附來源與發文時間。免金鑰、走 certifi TLS 驗證。
"""
from __future__ import annotations

import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

RSS = "https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
UA = "Mozilla/5.0 (FH-ARM research bot; contact: marketing)"


def _ctx() -> ssl.SSLContext:
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


_CTX = _ctx()


def search(query: str, *, days: int = 7, limit: int = 6) -> list[dict]:
    """關鍵字 → 近 days 天的新聞 [{title, url, source, date, datetime}]，依時間新→舊。

    title 末端常帶『 - 來源』；source 以 <source> 標籤為準、無則由標題尾切出。取不到回 []。
    """
    url = RSS.format(q=urllib.parse.quote(query))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20, context=_CTX) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for it in root.iter("item"):
        pub = it.findtext("pubDate")
        try:
            dt = parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            continue
        if dt < cutoff:
            continue
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if not src and " - " in title:           # 退而求其次：標題尾即來源
            title, src = title.rsplit(" - ", 1)
        out.append({"title": title, "url": it.findtext("link") or "",
                    "source": src, "date": dt.astimezone().strftime("%Y-%m-%d %H:%M"),
                    "datetime": dt.astimezone().isoformat()})
    out.sort(key=lambda x: x["datetime"], reverse=True)
    return out[:limit]


def search_many(queries: list[str], *, days: int = 7, limit: int = 6) -> list[dict]:
    """多組關鍵字合併、依標題去重、依時間新→舊取前 limit。"""
    seen, merged = set(), []
    for q in queries:
        for it in search(q, days=days, limit=limit):
            key = it["title"][:24]
            if key in seen:
                continue
            seen.add(key)
            merged.append(it)
    merged.sort(key=lambda x: x["datetime"], reverse=True)
    return merged[:limit]
