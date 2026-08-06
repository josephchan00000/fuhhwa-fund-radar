"""Google News RSS 連接器 —— 自動擷取『近一週、帶發文時間』的台灣財經新聞。

每次更新都要最新：本連接器讓新聞/輿論不靠人工，依關鍵字即時拉 Google News（台灣繁中），
解析 pubDate 過濾近 N 天、附來源與發文時間。免金鑰、走 certifi TLS 驗證。
"""
from __future__ import annotations

import base64
import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from ..clock import TW_TZ

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


# ── 真實刊出日驗證（2026-08-06 使用者抓包「基金新聞很多都是舊的」）──────────────
# Google News RSS 的 pubDate 不可信：Google 重新收錄舊頁時會把 pubDate 標成 re-crawl
# 時間——實例：傘型ETF 4/15 掛牌稿（工商時報 4/14）標 08-01、中租基智網一年前的
# 公告標 08-04，各以「新聞」姿態掛版整週。這裡提供「解原文 URL → 讀原文頁刊出日」
# 工具；剔除策略（台帳／視窗）在 arm/fundnews.date_verify()。
# 任何一步失敗一律 fail-open 回 None（呼叫端沿用 pubDate）——resolve 走 Google 內部
# batchexecute 端點、版式會漂移，失效時 CI 日誌印原因、只修這層解析，策略層不動。

_ART_ID = re.compile(r"news\.google\.com/(?:rss/)?articles/([A-Za-z0-9_-]+)")
_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def _get_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "zh-TW,zh;q=0.9",
                                               "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.read().decode("utf-8", "ignore")


def _decoded_direct_url(art_id: str) -> str | None:
    """舊式文章 id 的 base64 內嵌原文 URL 直解；新式（AU_yq… 不含 URL）回 None。"""
    try:
        raw = base64.urlsafe_b64decode(art_id + "=" * (-len(art_id) % 4))
    except Exception:
        return None
    m = re.search(rb"https?://[!-~]+", raw)     # URL 至第一個非可印字元（protobuf 分隔）止
    if not m:
        return None
    url = m.group(0).decode("utf-8", "ignore")
    return None if "news.google.com" in url else url


def _batch_payload(art_id: str, ts: str, sg: str) -> bytes:
    """batchexecute 的 garturlreq 表單體（參數樣板來自已知可用的解碼流程）。"""
    inner = json.dumps(["garturlreq",
                        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
                          None, None, None, None, None, 0, 1],
                         "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                        art_id, int(ts), sg])
    return urllib.parse.urlencode(
        {"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]])}).encode()


def url_from_batch(raw: str) -> str | None:
    """batchexecute 回應 → 原文 URL。結構解析優先，版式漂移時退回「第一個非 Google 網域
    URL」的字面掃描。純函式可單測。"""
    raw = (raw or "").replace("\\/", "/")
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("[["):
            continue
        try:
            payload = json.loads(json.loads(line)[0][2])
            url = payload[1]
            if isinstance(url, str) and url.startswith("http"):
                return url
        except Exception:
            continue
    for m in re.finditer(r"https?://[^\"'\\\s<>]+", raw):
        host = urllib.parse.urlsplit(m.group(0)).netloc
        if host and "google" not in host and "gstatic" not in host:
            return m.group(0)
    return None


def resolve(url: str, *, timeout: int = 12) -> str | None:
    """news.google.com 文章連結 → 原文 URL；已是原文者原樣回傳。解不出回 None。"""
    m = _ART_ID.search(url or "")
    if not m:
        return url if url and "news.google.com" not in url else None
    art_id = m.group(1)
    direct = _decoded_direct_url(art_id)
    if direct:
        return direct
    try:
        page = _get_text(f"https://news.google.com/rss/articles/{art_id}"
                         "?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", timeout)
        sg = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sg and ts):
            print(f"[gnews] resolve: 文章頁無 sg/ts 屬性（Google 版面變了？）id={art_id[:16]}…")
            return None
        req = urllib.request.Request(
            _BATCH_URL, data=_batch_payload(art_id, ts.group(1), sg.group(1)),
            headers={"User-Agent": UA,
                     "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return url_from_batch(r.read().decode("utf-8", "ignore"))
    except Exception as e:
        print(f"[gnews] resolve 失敗 id={art_id[:16]}…: {type(e).__name__}: {e}")
        return None


_JSONLD_PUB = re.compile(r'"datePublished"\s*:\s*"([^"]{8,40})"')
_META_PUB_TAG = re.compile(
    r"<meta[^>]+?(?:property|name|itemprop)\s*=\s*[\"'](?:article:published_time|"
    r"datePublished|pubdate|publishdate|publish-date|dc\.date(?:\.issued)?)[\"'][^>]*>",
    re.I)
_ATTR_CONTENT = re.compile(r"content\s*=\s*[\"']([^\"']+)[\"']", re.I)
_TIME_TAG = re.compile(r"<time[^>]+?datetime\s*=\s*[\"']([^\"']+)[\"']", re.I)
_URL_DATE8 = re.compile(r"(20[12]\d)([01]\d)([0-3]\d)")
_URL_DATE_SEP = re.compile(r"(20[12]\d)[-/]([01]?\d)[-/]([0-3]?\d)(?!\d)")
_ISO_ISH = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})")


def _plausible(dt: datetime | None) -> datetime | None:
    if dt and 2000 <= dt.year <= datetime.now().year + 1:
        return dt
    return None


def _parse_meta_dt(s: str) -> datetime | None:
    """meta/JSON-LD 的日期字串 → aware datetime（ISO／RFC822 都收；無時區視為台北）。"""
    s = (s or "").strip()
    if not s:
        return None
    dt = None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            m = _ISO_ISH.match(s) or re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
            if m:
                dt = datetime(*(int(x) for x in m.groups()))
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TW_TZ)
    return _plausible(dt)


def _date_from_url(url: str) -> datetime | None:
    """原文 URL 路徑內的日期（工商 /news/20260414700256、華視 /202608/20260803…）。
    只看 path、月日須合法——最後一道退路，metadata 都沒有才用。"""
    path = urllib.parse.urlsplit(url or "").path
    for pat in (_URL_DATE_SEP, _URL_DATE8):
        for m in pat.finditer(path):
            y, mo, d = (int(x) for x in m.groups())
            if 1 <= mo <= 12 and 1 <= d <= 31:
                try:
                    return _plausible(datetime(y, mo, d, tzinfo=TW_TZ))
                except ValueError:
                    continue
    return None


def published_from_html(html: str, url: str = "") -> datetime | None:
    """原文頁 → 刊出日：JSON-LD datePublished → meta 發布時間 → <time datetime> →
    URL 路徑日期。都沒有回 None（呼叫端沿用 RSS pubDate）。純函式可單測。"""
    html = html or ""
    m = _JSONLD_PUB.search(html)
    if m:
        dt = _parse_meta_dt(m.group(1))
        if dt:
            return dt
    for tag in _META_PUB_TAG.finditer(html):
        c = _ATTR_CONTENT.search(tag.group(0))
        dt = _parse_meta_dt(c.group(1)) if c else None
        if dt:
            return dt
    m = _TIME_TAG.search(html)
    if m:
        dt = _parse_meta_dt(m.group(1))
        if dt:
            return dt
    return _date_from_url(url)


def verify_published(url: str, *, timeout: int = 12) -> tuple[str | None, datetime | None]:
    """Google News 連結 → (原文 URL, 真實刊出日)，各自可 None（fail-open）。
    只在 CI 端呼叫——本容器 proxy 擋 news.google.com 與各媒體站，會直接走例外路徑。"""
    real = resolve(url, timeout=timeout)
    if not real:
        return None, None
    try:
        page = _get_text(real, timeout)
    except Exception as e:
        print(f"[gnews] 原文頁抓取失敗 {real[:60]}: {type(e).__name__}")
        return real, None
    return real, published_from_html(page, real)
