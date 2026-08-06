"""基金相關新聞・社群聲量 —— 復華基金雷達專屬的情報層（新增區塊、不動既有模組）。

與 ETF 產品線的 arm/connectors/social 完全分離（不共用過濾詞彙、不改其程式）：
  · 新聞：Google News RSS（免金鑰，直接引用 arm.connectors.gnews）
      - 品牌層：「復華投信」動態（公告／配息／得獎／人事）
      - 基金層：每檔以「基金基底名」搜尋；同基金的 A／B／TISA 類別合併一次查詢
  · 財經媒體 RSS 直抓（鉅亨網台股／頭條、Yahoo股市）：留標題含「復華」者，
      補 Google News 漏收或排序沉掉的稿——命中特定基金者同時補進該基金清單
  · 社群：PTT 股票板公開索引頁標題（留含「復華」者；推文數為聲量 proxy；
      禮貌抓取、只存標題＋連結，不落全文）＋ YouTube 相關影片（2026-08-06 使用者需求；
      Data API v3、金鑰走 Actions secret `YOUTUBE_API_KEY`——v0.12 ETF 產品線時代使用者
      已設過的同一把，daily.yml 重新帶入；無金鑰誠實降級回 []）。
      Dcard／FB 涉反爬或授權，本層仍不碰（同 arm/connectors/social 的授權註記）。

落檔 data/fund_news.json；儀表板以「基金相關新聞・社群」區塊呈現。
任一來源抓不到一律誠實降級（空清單照落檔、標 as-of），不影響其他區塊。
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta
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
                   "extra.rakuya.com.tw"}   # 房產站轉貼區，非新聞來源
# 註：「鉅亨買基金」不列黑名單（使用者指示：鉅亨的新聞內容仍要收）；
#     其平台頁/開戶頁等非新聞連結由 is_news_title() 的標題特徵過濾即可。

# 內容農場來源（2026-07 使用者回饋：這些會把舊文更新日期反覆重貼，冒充新聞佔版面，要排除）：
# 「CMoney投資網誌」＝部落格農場（非即時新聞）。CMoney 若有真新聞另計，靠 is_farm_title 標題特徵過濾。
FARM_SOURCES = {"CMoney投資網誌"}
# SEO 農場點閱誘餌標題特徵：績效／規模「誇飾＋問句／揭密」句式，
# 例「同樣是科技基金，為什麼近一年能漲超過 200%？」「單月規模暴增58億的背後秘密是什麼？」。
_FARM_HYPE = re.compile(r"為什麼|為何|憑什麼|究竟|背後|祕密|秘密|狂增|暴增|漲破|漲超過|"
                        r"稱霸|同類第一|百萬變|發生了什麼")

# 負面／司法／醜聞新聞：本工具為「復華內部溝通」用途，不宜在儀表板呈現自家的司法／弊案／
# 負面報導（2026-07 使用者要求排除；品牌與各基金、PTT 皆適用）。命中司法/弊案/操縱字眼即剔除。
# 例「勞動基金炒股案第3波　搜索復華投信」「投資長移送！經理人喊冤」。
_NEGATIVE = re.compile(
    r"炒股|炒作|操縱|坑殺|內線|掏空|違約交割|"
    r"弊案|官商|貪污|貪瀆|收賄|賄賂|圖利|洗錢|不法|違法|犯罪|醜聞|"
    r"搜索|搜查|約談|傳喚|移送|起訴|偵辦|檢調|地檢|檢方|調查局|廉政|"
    r"收押|羈押|交保|判刑|求刑|定讞|起底|喊冤|裁罰|開罰|罰鍰|送辦")

# 「非新聞頁面」標題特徵——搜尋/RSS 常混入基金介紹頁、文章列表頁、平台頁、討論牆、
# 淨值表等非新聞連結，佔版面又無資訊量，一律剔除（2026-07-04 使用者回饋：我要新聞）。
# 「公開說明書／信託契約」＝基金平台的例行修訂公告轉貼（2026-08-06 使用者抓包：中租基智網
# 一年前的公告被 Google 標成近期日期、同一則掛滿 6 檔基金卡）——公告類非新聞，一律剔除。
_JUNK_TITLE = re.compile(
    r"推薦文章|新聞資訊與消息|討論牆|一覽表|淨值表|交易平台|基金介紹|基金檔案|"
    r"基金專區|歷史淨值|基金列表|條款|開戶|公開說明書|信託契約")

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
    """來源黑名單：BLOCKED_SOURCES＋FARM_SOURCES 內的媒體一律不收。"""
    return (item.get("source") or "").strip() not in (BLOCKED_SOURCES | FARM_SOURCES)


def is_farm_title(title: str | None) -> bool:
    """SEO 內容農場的點閱誘餌標題偵測（舊文常改標題／更新日期反覆重貼）。

    · 以問號收尾且帶績效／規模誇飾字眼（「…為什麼近一年能漲超過 200%？」）；
    · 或明確的揭密／致富句式（「背後秘密」「22年百萬變七百萬」「還能稱霸」）。"""
    t = (title or "").strip()
    if not t:
        return False
    if t.endswith("？") and _FARM_HYPE.search(t):
        return True
    return bool(re.search(r"背後(?:的)?(?:祕密|秘密)|百萬變[^，。]{0,6}萬|還能稱霸", t))


def is_negative_title(title: str | None) -> bool:
    """負面／司法／醜聞新聞偵測（復華內部溝通用途，自家負面報導不上儀表板）。"""
    return bool(_NEGATIVE.search(title or ""))


def is_news_title(title: str | None) -> bool:
    """是不是「一篇（正面/中性的）新聞」標題：剔除列表頁/介紹頁/平台頁、
    SEO 農場點閱誘餌、以及自家司法/負面報導。

    · 命中 _JUNK_TITLE 特徵 → 非新聞；
    · 命中農場（is_farm_title）或負面（is_negative_title）→ 剔除；
    · 標題就只是基金名本身（如「復華傳家二號基金」，可帶幣別/類別尾綴）＝基金介紹頁。"""
    t = (title or "").strip()
    if not t or _JUNK_TITLE.search(t):
        return False
    if is_farm_title(t) or is_negative_title(t):
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


# ── Google News「有效日期」防線（2026-08-06 使用者抓包「很多都是舊的」）────────
# pubDate 會把舊文標成近期（Google re-crawl 時間）：傘型ETF 4/15 掛牌稿標 08-01、
# 基智網去年公告標 08-04，各掛版整週。台帳 data/fund_news_seen.json（必須入庫）記
# 每標題「最早見過的日期」＋CI 解原文頁驗得的真實刊出日，兩者都拉不進視窗就剔除。

SEEN_OUT = ROOT / "data" / "fund_news_seen.json"
VERIFY_BUDGET = 16       # 每輪最多解幾篇原文（台帳沒驗過的新項目才消耗；容器端網路被擋＝0 成本）
SEEN_KEEP_DAYS = 60      # 台帳條目最後一次見到後保留天數（涵蓋反覆重貼週期，防無限膨脹）


def _seen_load() -> dict:
    try:
        return json.loads(SEEN_OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _seen_save(seen: dict) -> None:
    SEEN_OUT.parent.mkdir(parents=True, exist_ok=True)
    SEEN_OUT.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")


def _from_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=TW_TZ)


def _seen_prune(seen: dict, now: datetime) -> dict:
    def last(e: dict) -> datetime:
        return _from_iso(e.get("seen") or "") or _from_iso(e.get("pub") or "") or now
    return {k: e for k, e in seen.items() if (now - last(e)).days <= SEEN_KEEP_DAYS}


def date_verify(items: list[dict], seen: dict, state: dict, *,
                days: int = WINDOW_DAYS, now: datetime | None = None,
                verifier=None) -> list[dict]:
    """Google News 項目逐則算「有效日期」＝min(本次 pubDate, 台帳最早見過值, 原文頁刊出日)。

    · 台帳鍵＝標題前 24 字（與去重鍵一致）；每則更新 pub（最早 pubDate）與 seen（最後見到）。
    · 原文驗證（gnews.verify_published）每輪至多 state["budget"] 篇、結果入台帳 v 不重驗
      （v=""＝驗過但查無日期，沿用 pubDate）；解到原文 URL 一併存 u。
    · 有效日期落出視窗 → 剔除（CI 日誌印明）；在窗內但早於 pubDate → 改標有效日期，
      有原文 URL 就換上（連結直達媒體、不繞 Google 轉址）。
    · 鉅亨/Yahoo RSS 直抓不經此路——pubDate 出自發布者、可信。"""
    now = now or datetime.now(TW_TZ)
    if verifier is None:
        verifier = lambda u: gnews.verify_published(u)  # noqa: E731
    cutoff = now - timedelta(days=days)
    out: list[dict] = []
    for i in items or []:
        title = i.get("title") or ""
        k = title[:24]
        claimed = _from_iso(i.get("datetime") or "")
        if not k or claimed is None:
            out.append(i)
            continue
        ent = seen.get(k) or {}
        earliest = min([claimed] + [d for d in [_from_iso(ent.get("pub") or "")] if d])
        if "v" not in ent and state.get("budget", 0) > 0 \
                and "news.google.com" in (i.get("url") or ""):
            state["budget"] = state["budget"] - 1
            real, pub = verifier(i.get("url") or "")
            ent["v"] = pub.isoformat() if pub else ""
            if real:
                ent["u"] = real
            print(f"[fundnews] 驗刊出日:「{k}」pubDate={claimed:%m-%d} → "
                  + (f"實際 {pub:%Y-%m-%d}" if pub else "查無日期（沿用 pubDate）"))
        vd = _from_iso(ent.get("v") or "")
        eff = min([earliest] + [d for d in [vd] if d])
        ent["pub"], ent["seen"] = earliest.isoformat(), now.isoformat()
        seen[k] = ent
        if eff < cutoff:
            print(f"[fundnews] 舊聞剔除:「{title[:36]}」Google 標 {claimed:%m-%d}、"
                  f"實為 {eff:%Y-%m-%d}")
            continue
        if eff < claimed:
            i = {**i, "date": eff.astimezone(TW_TZ).strftime("%Y-%m-%d %H:%M"),
                 "datetime": eff.astimezone(TW_TZ).isoformat()}
        if ent.get("u"):
            i = {**i, "url": ent["u"]}
        out.append(i)
    return out


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
    """PTT 標題是否與復華基金相關：含品牌名即留（基金討論幾乎都帶「復華」二字）；
    但司法/醜聞討論串（is_negative_title）一律排除（內部溝通用途）。"""
    t = title or ""
    return "復華" in t and not is_negative_title(t)


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


# ── YouTube 相關影片（2026-08-06 使用者需求：社群討論加入 YouTube）──────────────
# 與 ETF 產品線的 arm/connectors/social/youtube.py 分離（該層查主動式ETF、回 SocialMention）；
# 本層查品牌／基金、回社群項目 dict。金鑰同一把：env YOUTUBE_API_KEY（Actions secret）
# 或 ~/.fh_youtube_key（本機慣例，同 arm/dashboard._youtube_voice）。

YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YT_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
# search.list 每次 100 單位（日限 10000）；四組≈每輪 400、日多輪仍 <3000（2026-08-06 使用者
# 要求擴大「復華投信相關」涵蓋——含自家 ETF 討論度最高的 00929；勿再隨意加組）。
YT_QUERIES = ["復華投信", "復華 基金", "復華 ETF", "00929"]
YT_LIMIT = 8
_YT_SHORT_SEC = 180          # YouTube Shorts 上限 3 分鐘（2024-10 起）；≤此秒數標為短片
_YT_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _yt_key() -> str:
    key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if key:
        return key
    kp = Path.home() / ".fh_youtube_key"
    try:
        return kp.read_text(encoding="utf-8").strip() if kp.exists() else ""
    except OSError:
        return ""


def _fh_codes() -> tuple[str, ...]:
    """復華自家 ETF 代碼（名稱含「復華」者，動態取自 etfwatch 追蹤清單）——標題只寫代碼
    不寫「復華」的影片（00929 常見）也算相關。取不到時退回已知靜態清單。"""
    try:
        from . import etfwatch
        codes = tuple(t[0] for t in etfwatch.watch_tuples() if "復華" in (t[1] or ""))
        if codes:
            return codes
    except Exception:
        pass
    return ("00929", "00991A", "00998A", "00986D")


def _code_hit(text: str) -> bool:
    """自家 ETF 代碼是否以「獨立詞」出現。防呆（2026-08-06 實戰誤收）：日文單字卡影片
    標題帶課號「L#00929」被純子字串比對誤判——代碼前後不得緊貼英數，也不得是
    「英數+#」的編號式前綴；獨立 hashtag（空格後的 #00929）仍算相關。"""
    for c in _fh_codes():
        if re.search(rf"(?<![0-9A-Za-z])(?<![0-9A-Za-z][#＃]){re.escape(c)}(?![0-9A-Za-z])",
                     text):
            return True
    return False


def yt_relevant(title: str, desc: str = "") -> bool:
    """標題或說明含「復華」或自家 ETF 代碼（獨立詞）才算相關（查詢會回同名他牌/
    無關影片）；負面司法題材同 PTT 排除。"""
    text = f"{title} {desc}"
    if is_negative_title(title):
        return False
    return "復華" in text or _code_hit(text)


def _yt_secs(iso: str) -> int:
    """ISO8601 時長（PT1H2M3S）→ 秒；解析不出回 0。"""
    m = _YT_DUR.fullmatch((iso or "").strip())
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def parse_youtube(search_docs: list[dict], stats: dict | None = None) -> list[dict]:
    """search.list 回應（多組查詢）＋{videoId: {views, sec}} → 社群項目。純函式可單測。
    相關性過濾、videoId 去重；時長 ≤3 分標 Shorts（連結走 /shorts/、儀表板另標）；
    依觀看數→日期新→舊排序、取前 YT_LIMIT。"""
    stats = stats or {}
    out, seen = [], set()
    for doc in search_docs or []:
        for it in (doc or {}).get("items") or []:
            vid = (it.get("id") or {}).get("videoId")
            sn = it.get("snippet") or {}
            title = (sn.get("title") or "").strip()
            if not vid or vid in seen or not yt_relevant(title, sn.get("description") or ""):
                continue
            seen.add(vid)
            st = stats.get(vid) or {}
            if isinstance(st, int):              # 舊呼叫形（純觀看數）相容
                st = {"views": st}
            sec = int(st.get("sec") or 0)
            short = 0 < sec <= _YT_SHORT_SEC
            item = {"platform": "youtube", "title": title,
                    "channel": (sn.get("channelTitle") or "").strip(),
                    "url": (f"https://www.youtube.com/shorts/{vid}" if short
                            else f"https://www.youtube.com/watch?v={vid}"),
                    "date": (sn.get("publishedAt") or "")[:10],
                    "views": int(st.get("views") or 0)}
            if short:
                item["short"] = True
            out.append(item)
    out.sort(key=lambda x: (x.get("views") or 0, x.get("date") or ""), reverse=True)
    return out[:YT_LIMIT]


def fetch_youtube(days: int = WINDOW_DAYS) -> list[dict]:
    """近 days 天的復華相關 YouTube 影片。無金鑰／被擋回 []（誠實降級，不影響 PTT）。
    search.list 抓片單（order=date 配 publishedAfter）→ videos.list 一次補觀看數（1 單位）。"""
    from datetime import timezone

    key = _yt_key()
    if not key:
        return []
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    docs: list[dict] = []
    for q in YT_QUERIES:
        url = (f"{YT_SEARCH}?part=snippet&type=video&order=date&maxResults=10"
               f"&regionCode=TW&relevanceLanguage=zh-Hant&publishedAfter={after}"
               f"&q={urllib.parse.quote(q)}&key={key}")
        try:
            docs.append(json.loads(get_bytes(url, cache_ttl=1800).decode("utf-8", "ignore")))
        except Exception:
            continue
    vids = [v for d in docs for it in d.get("items") or []
            if (v := (it.get("id") or {}).get("videoId"))]
    stats: dict[str, dict] = {}
    if vids:
        try:
            ids = list(dict.fromkeys(vids))[:50]     # videos.list 單次上限 50 支
            data = json.loads(get_bytes(
                f"{YT_VIDEOS}?part=statistics,contentDetails&id={','.join(ids)}&key={key}",
                cache_ttl=1800).decode("utf-8", "ignore"))
            for it in data.get("items") or []:
                stats[it.get("id") or ""] = {
                    "views": int((it.get("statistics") or {}).get("viewCount") or 0),
                    "sec": _yt_secs((it.get("contentDetails") or {}).get("duration") or ""),
                }
        except Exception:
            pass
    return parse_youtube(docs, stats)


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
        hl.append(f"近 {win} 天有專屬報導的基金：{names}{more}（詳下方基金新聞標籤）")
    focus = next((i for i in doc.get("brand") or []
                  if "旗下各基金" not in (i.get("title") or "")), None)
    if focus:
        hl.append(f"品牌焦點：{focus['title']}（{focus.get('source') or '—'}）")
    soc = doc.get("social") or []
    ptts = [s for s in soc if (s.get("platform") or "ptt") != "youtube"]
    if ptts:
        top = max(ptts, key=lambda s: s.get("push") or 0)
        hl.append(f"社群聲量最高：{top['title']}（{top.get('push') or 0} 推）")
    yts = [s for s in soc if (s.get("platform") or "") == "youtube"]
    if yts:
        top = max(yts, key=lambda s: s.get("views") or 0)
        who = f"{top.get('channel')}・" if top.get("channel") else ""
        hl.append(f"YouTube 熱片：{top['title']}（{who}{top.get('views') or 0:,} 次觀看）")
    return hl


def assemble(funds: list[dict], days: int = WINDOW_DAYS) -> dict:
    """抓齊三類情報 → 可落檔的 doc。任一來源失敗該類為空、不互相牽連。
    Google News 項目先過 date_verify（pubDate 會把舊文標成近期，見該函式 docstring）。"""
    seen, state = _seen_load(), {"budget": VERIFY_BUDGET}
    feeds = _clean_items(fetch_feeds(days=days))
    brand = merge_news(date_verify(fetch_brand(days=days), seen, state, days=days), feeds)
    fund_groups = fetch_funds(funds, days=days)
    for g in fund_groups:
        g["items"] = date_verify(g["items"], seen, state, days=days)
    fund_groups = route_feeds_to_funds(fund_groups, feeds)
    _seen_save(_seen_prune(seen, datetime.now(TW_TZ)))
    doc = {
        "as_of": stamp_tw("%Y/%m/%d %H:%M"),
        "window_days": days,
        "source": "Google News（台灣繁中）＋鉅亨網/Yahoo股市 RSS＋PTT 股票板公開標題"
                  "＋YouTube 影片・自動擷取",
        "brand": brand,
        "funds": fund_groups,
        "social": fetch_ptt() + fetch_youtube(days),
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


def sanitize(doc: dict | None) -> dict | None:
    """讀取時再過一次農場／負面過濾：即使既有落檔是舊規則抓的（含 CMoney投資網誌 農場文、
    復華司法/醜聞報導），儀表板顯示時也一律濾掉——不必等下次重抓。純過濾、不新增內容。"""
    if not doc:
        return doc
    doc["brand"] = _clean_items(doc.get("brand") or [])
    for g in doc.get("funds") or []:
        g["items"] = _clean_items(g.get("items") or [])
    doc["social"] = [s for s in (doc.get("social") or [])
                     if not is_negative_title(s.get("title") or "")]
    # 舊落檔的看點措辭指向已移除的「各基金新聞」分卡區 → 讀取時改寫成合併版措辭
    doc["highlights"] = [h.replace("（詳下方各基金新聞）", "（詳下方基金新聞標籤）")
                         for h in doc.get("highlights") or []]
    return doc


def load() -> dict | None:
    """儀表板用：讀最近一次落檔並過濾農場／負面新聞；無檔回 None（區塊顯示提示、不壞版）。"""
    try:
        return sanitize(json.loads(OUT.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
