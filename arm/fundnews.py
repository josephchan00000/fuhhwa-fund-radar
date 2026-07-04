"""基金相關新聞・社群聲量 —— 復華基金雷達專屬的情報層（新增區塊、不動既有模組）。

與 ETF 產品線的 arm/connectors/social 完全分離（不共用過濾詞彙、不改其程式）：
  · 新聞：Google News RSS（免金鑰，直接引用 arm.connectors.gnews）
      - 品牌層：「復華投信」動態（公告／配息／得獎／人事）
      - 基金層：每檔以「基金基底名」搜尋；同基金的 A／B／TISA 類別合併一次查詢
  · 財經媒體 RSS 直抓（鉅亨網台股／頭條、Yahoo股市）：留標題含「復華」者，
      補 Google News 漏收或排序沉掉的稿——命中特定基金者同時補進該基金清單
  · 社群：PTT 股票板公開索引頁標題（留含「復華」者；推文數為聲量 proxy；
      禮貌抓取、只存標題＋連結，不落全文）。Dcard／YouTube／FB 涉金鑰或反爬，
      本層不碰（同 arm/connectors/social 的授權註記）。

落檔 data/fund_news.json；儀表板以「基金相關新聞・社群」區塊呈現。
任一來源抓不到一律誠實降級（空清單照落檔、標 as-of），不影響其他區塊。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .clock import TW_TZ, stamp_tw
from .connectors import gnews
from .http import get_bytes

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fund_news.json"

WINDOW_DAYS = 7
BRAND_QUERIES = ["復華投信", "復華投信 基金"]
BRAND_LIMIT = 12
BLOCKED_SOURCES = {"富聯網",          # 使用者指定排除的新聞來源（品牌與各基金皆不收）
                   "鉅亨買基金",       # 基金銷售平台頁，非新聞媒體
                   "extra.rakuya.com.tw"}   # 房產站轉貼區，非新聞來源

# 「非新聞頁面」標題特徵——搜尋/RSS 常混入基金介紹頁、文章列表頁、平台頁、討論牆、
# 淨值表等非新聞連結，佔版面又無資訊量，一律剔除（2026-07-04 使用者回饋：我要新聞）。
_JUNK_TITLE = re.compile(
    r"推薦文章|新聞資訊與消息|討論牆|一覽表|淨值表|交易平台|基金介紹|基金檔案|"
    r"基金專區|歷史淨值|基金列表|條款|開戶")

# 財經媒體 RSS 直抓（免金鑰）——與 Google News 互補；站台全站 feed、本層只留「復華」相關
NEWS_FEEDS = [
    ("鉅亨網", "https://news.cnyes.com/rss/v1/news/category/tw_stock"),
    ("鉅亨網", "https://news.cnyes.com/rss/v1/news/category/headline"),
    ("Yahoo股市", "https://tw.stock.yahoo.com/rss"),
]
_RSS_ITEM = re.compile(r"<item>(.*?)</item>", re.S | re.I)
_RSS_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_RSS_HTML = re.compile(r"<[^>]+>")

PTT_BASE = "https://www.ptt.cc"
PTT_INDEX = PTT_BASE + "/bbs/Stock/index{n}.html"
_PTT_ENT = re.compile(r'<div class="r-ent">(.*?)</div>\s*</div>', re.S)
_PTT_TITLE = re.compile(r'<div class="title">\s*(?:<a href="([^"]+)">(.*?)</a>)?', re.S)
_PTT_PUSH = re.compile(r'<div class="nrec">(?:<span[^>]*>(.*?)</span>)?', re.S)
_PTT_DATE = re.compile(r'<div class="date">\s*(.*?)\s*</div>', re.S)
_PTT_PREV = re.compile(r'href="/bbs/Stock/index(\d+)\.html"[^>]*>.*?上頁', re.S)


def base_name(name: str | None) -> str:
    """基金基底名：去幣別尾綴與 A／B／TISA 類別，供搜尋與同名合併。
    「復華全方位基金TISA類型」→「復華全方位基金」；「復華美國新星基金-新臺幣」→「復華美國新星基金」。"""
    n = (name or "").strip()
    n = re.sub(r"[-‑–][^-‑–]*$", "", n) if re.search(r"[-‑–](新臺幣|美元|人民幣)", n) else n
    n = re.sub(r"(?:[AB]|TISA)類型$", "", n)
    return n.strip()


def fund_query_groups(funds: list[dict]) -> list[dict]:
    """依基底名合併類別：[{base, fund_ids, short_names}]，維持輸入順序。"""
    order: list[str] = []
    acc: dict[str, dict] = {}
    for d in funds:
        b = base_name(d.get("name"))
        if not b:
            continue
        if b not in acc:
            acc[b] = {"base": b, "fund_ids": [], "short_names": []}
            order.append(b)
        acc[b]["fund_ids"].append(str(d.get("fund_id")))
        sn = d.get("short_name") or ""
        if sn and sn not in acc[b]["short_names"]:
            acc[b]["short_names"].append(sn)
    return [acc[b] for b in order]


def strip_source_suffix(title: str | None, source: str | None) -> str:
    """Google News 標題尾常帶「 - 來源名」，與另列的來源欄重複——剝掉。"""
    t = (title or "").strip()
    s = (source or "").strip()
    if s and t.endswith(f" - {s}"):
        t = t[: -len(s) - 3].rstrip()
    return t


def source_ok(item: dict) -> bool:
    """來源黑名單：BLOCKED_SOURCES 內的媒體一律不收。"""
    return (item.get("source") or "").strip() not in BLOCKED_SOURCES


def is_news_title(title: str | None) -> bool:
    """是不是「一篇新聞」的標題：剔除列表頁/介紹頁/平台頁等非新聞連結。

    · 命中 _JUNK_TITLE 特徵 → 非新聞；
    · 標題就只是基金名本身（如「復華傳家二號基金」，可帶幣別/類別尾綴）＝基金介紹頁。"""
    t = (title or "").strip()
    if not t or _JUNK_TITLE.search(t):
        return False
    if re.fullmatch(r"復華[\w・]{1,14}基金(?:[-‑–]?(?:新臺幣|美元|人民幣|[AB]|TISA)[^，,。]{0,6})?", t):
        return False
    return True


def _clean_items(items: list[dict]) -> list[dict]:
    """統一清理：剔除黑名單來源＋非新聞頁面，剝標題尾的來源名。
    所有新聞路徑（品牌/各基金/RSS）都經過這裡。"""
    out = []
    for i in items:
        if not source_ok(i):
            continue
        t = strip_source_suffix(i.get("title"), i.get("source"))
        if not is_news_title(t):
            continue
        out.append({**i, "title": t})
    return out


def fetch_brand(days: int = WINDOW_DAYS, limit: int = BRAND_LIMIT) -> list[dict]:
    """品牌層新聞：復華投信動態（Google News）。抓不到回 []。"""
    return _clean_items(gnews.search_many(BRAND_QUERIES, days=days, limit=limit))


def parse_rss(xml_text: str, source: str, days: int = WINDOW_DAYS) -> list[dict]:
    """RSS → 近 days 天、標題含「復華」的 [{title,url,source,date,datetime}]。純函式可單測。"""
    from datetime import timedelta, timezone
    from email.utils import parsedate_to_datetime

    def _clean(s: str) -> str:
        m = _RSS_CDATA.search(s or "")
        s = m.group(1) if m else (s or "")
        return _RSS_HTML.sub("", s).strip()

    def _tag(t: str, blk: str) -> str:
        m = re.search(rf"<{t}[^>]*>(.*?)</{t}>", blk, re.S | re.I)
        return m.group(1) if m else ""

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for blk in _RSS_ITEM.findall(xml_text or ""):
        title = _clean(_tag("title", blk))
        if "復華" not in title:
            continue
        try:
            dt = parsedate_to_datetime(_clean(_tag("pubDate", blk)))
        except (TypeError, ValueError):
            continue
        if dt < cutoff:
            continue
        desc = _clean(_tag("description", blk))
        it = {"title": title, "url": _clean(_tag("link", blk)), "source": source,
              "date": dt.astimezone(TW_TZ).strftime("%Y-%m-%d %H:%M"),
              "datetime": dt.astimezone(TW_TZ).isoformat()}
        if desc and desc != title:               # RSS 摘要（鉅亨網等有全文摘要；截 100 字）
            it["summary"] = desc[:100] + ("…" if len(desc) > 100 else "")
        out.append(it)
    return out


def fetch_feeds(days: int = WINDOW_DAYS) -> list[dict]:
    """財經媒體 RSS 直抓（鉅亨網／Yahoo股市），留「復華」相關。單一 feed 失敗誠實略過。"""
    out: list[dict] = []
    for source, url in NEWS_FEEDS:
        try:
            xml = get_bytes(url, cache_ttl=1800).decode("utf-8", "ignore")
        except Exception:
            continue
        out.extend(parse_rss(xml, source, days=days))
    return out


def merge_news(*lists: list[dict], limit: int = BRAND_LIMIT) -> list[dict]:
    """多來源合併：同標題（前 24 字）去重、依時間新→舊、取前 limit。"""
    seen: set[str] = set()
    merged: list[dict] = []
    for items in lists:
        for i in items or []:
            k = (i.get("title") or "")[:24]
            if not k or k in seen:
                continue
            seen.add(k)
            merged.append(i)
    merged.sort(key=lambda x: x.get("datetime") or x.get("date") or "", reverse=True)
    return merged[:limit]


def fund_item_relevant(item: dict, base: str) -> bool:
    """留與該基金明確相關者：標題含「復華」或基金核心名（去「復華」「基金」後的特徵詞）。
    兩類噪音濾掉：Google 放寬搜尋回的同類他牌基金（如搜「復華美國新星基金」回柏瑞美國
    研究基金）；「旗下各基金淨值一覽表」這類品牌層系列文（每檔都命中、歸品牌動態就好）。"""
    t = item.get("title") or ""
    if "旗下各基金" in t:
        return False
    core = (base or "").replace("復華", "").replace("基金", "").strip()
    return ("復華" in t) or bool(core and core in t)


def fetch_funds(funds: list[dict], days: int = WINDOW_DAYS, per_limit: int = 4) -> list[dict]:
    """基金層新聞：每個基底名一次 Google News 查詢。不相關標題濾除、同稿多家轉載去重。
    無新聞的基金 items 為 []。"""
    out = []
    for g in fund_query_groups(funds):
        items = gnews.search(f'"{g["base"]}"', days=days, limit=per_limit)
        if not items:                            # 精確片語沒中 → 放寬一次
            items = gnews.search(g["base"], days=days, limit=per_limit)
        kept, seen = [], set()
        for i in items:
            if not fund_item_relevant(i, g["base"]):
                continue
            key = (i.get("title") or "")[:24]    # 同標題（多家轉載）只留最新一則
            if key in seen:
                continue
            seen.add(key)
            kept.append(i)
        out.append({**g, "items": _clean_items(kept)})
    return out


def _ptt_reach(push: str) -> int:
    if not push:
        return 0
    if push == "爆":
        return 100
    try:
        return int(push)
    except ValueError:
        return 0


def ptt_relevant(title: str) -> bool:
    """PTT 標題是否與復華基金相關：含品牌名即留（基金討論幾乎都帶「復華」二字）。"""
    return "復華" in (title or "")


def fetch_ptt(pages: int = 3) -> list[dict]:
    """PTT 股票板近幾頁標題，留與復華相關者。板擋／網路失敗回 []（誠實降級）。"""
    out: list[dict] = []
    url = PTT_BASE + "/bbs/Stock/index.html"
    for _ in range(max(1, pages)):
        try:
            html = get_bytes(url, cache_ttl=1800,
                             headers={"Cookie": "over18=1"}).decode("utf-8", "ignore")
        except Exception:
            break
        for blk in _PTT_ENT.findall(html):
            mt = _PTT_TITLE.search(blk)
            if not mt or not mt.group(2):
                continue
            title = re.sub(r"<[^>]+>", "", mt.group(2)).strip()
            if not ptt_relevant(title):
                continue
            push = (_PTT_PUSH.search(blk) or [None, ""]).group(1) or ""
            date = (_PTT_DATE.search(blk) or [None, ""]).group(1) or ""
            out.append({"platform": "ptt", "title": title,
                        "url": PTT_BASE + mt.group(1), "date": date.strip(),
                        "push": _ptt_reach(push)})
        mp = _PTT_PREV.search(html)
        if not mp:
            break
        url = PTT_INDEX.format(n=mp.group(1))
    out.sort(key=lambda x: x["push"], reverse=True)
    return out


def route_feeds_to_funds(fund_groups: list[dict], feeds: list[dict]) -> list[dict]:
    """RSS 直抓中命中特定基金核心名者，補進該基金清單（同標題去重、時間新→舊）。"""
    for g in fund_groups:
        core = (g.get("base") or "").replace("復華", "").replace("基金", "").strip()
        if not core:
            continue
        extra = [i for i in feeds if core in (i.get("title") or "")]
        if extra:
            g["items"] = merge_news(g.get("items") or [], extra, limit=6)
    return fund_groups


def auto_highlights(doc: dict) -> list[str]:
    """「本週看點」自動摘要（純標題彙整、不外推）：有專屬報導的基金＋最新品牌焦點＋社群聲量。
    僅為 fallback；晨間 Claude 可用更好的人工摘要覆寫 doc["highlights"]（落檔即生效）。"""
    hl: list[str] = []
    win = doc.get("window_days") or WINDOW_DAYS
    hit = [g for g in doc.get("funds") or [] if g.get("items")]
    if hit:
        names = "、".join((g.get("base") or "").replace("復華", "").replace("基金", "")
                          for g in hit[:6])
        more = f" 等 {len(hit)} 檔" if len(hit) > 6 else ""
        hl.append(f"近 {win} 天有專屬報導的基金：{names}{more}（詳下方各基金新聞）")
    focus = next((i for i in doc.get("brand") or []
                  if "旗下各基金" not in (i.get("title") or "")), None)
    if focus:
        hl.append(f"品牌焦點：{focus['title']}（{focus.get('source') or '—'}）")
    soc = doc.get("social") or []
    if soc:
        top = max(soc, key=lambda s: s.get("push") or 0)
        hl.append(f"社群聲量最高：{top['title']}（{top.get('push') or 0} 推）")
    return hl


def assemble(funds: list[dict], days: int = WINDOW_DAYS) -> dict:
    """抓齊三類情報 → 可落檔的 doc。任一來源失敗該類為空、不互相牽連。"""
    feeds = _clean_items(fetch_feeds(days=days))
    brand = merge_news(fetch_brand(days=days), feeds)
    fund_groups = route_feeds_to_funds(fetch_funds(funds, days=days), feeds)
    doc = {
        "as_of": stamp_tw("%Y/%m/%d %H:%M"),
        "window_days": days,
        "source": "Google News（台灣繁中）＋鉅亨網/Yahoo股市 RSS＋PTT 股票板公開標題・自動擷取",
        "brand": brand,
        "funds": fund_groups,
        "social": fetch_ptt(),
    }
    doc["highlights"] = auto_highlights(doc)
    return doc


def is_empty(doc: dict | None) -> bool:
    """三類情報（品牌／各基金／PTT）全空 → True。全空多半是網路被擋，不是真的沒新聞。"""
    if not doc:
        return True
    return not (doc.get("brand") or doc.get("social")
                or any(g.get("items") for g in doc.get("funds") or []))


def save(doc: dict) -> tuple[Path, bool]:
    """落檔。防呆：本次擷取全空且既有落檔非空 → 保留舊檔不覆寫（回 saved=False）。

    2026-07-04 教訓：雲端環境 Google News/PTT 被 proxy 政策擋下時，曾把非空的
    fund_news.json 覆寫成全空。全空結果一律視為「來源異常」而非「查無新聞」。"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if is_empty(doc) and not is_empty(load()):
        return OUT, False
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUT, True


def load() -> dict | None:
    """儀表板用：讀最近一次落檔；無檔回 None（區塊顯示提示、不壞版）。"""
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
