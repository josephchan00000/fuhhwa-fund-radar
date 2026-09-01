"""基金相關新聞・社群聲量 —— 復華基金雷達專屬的情報層（新增區塊、不動既有模組）。

與 ETF 產品線的 arm/connectors/social 完全分離（不共用過濾詞彙、不改其程式）：
  · 新聞：Google News RSS（免金鑰，直接引用 arm.connectors.gnews）
      - 品牌層：「復華投信」動態（公告／配息／得獎／人事）
      - 產品層（2026-08-12 使用者抓包「股感 00409A 開募文全漏」後新增）：自家 ETF
        逐檔以「代碼＋產品名」搜尋——追蹤中＋「即將登場」募集中檔（fh_products()，
        清單動態取自 etfwatch，掛牌/募集狀態變化零維護跟上）
      - 基金層：每檔以「基金基底名」搜尋；同基金的 A／B／TISA 類別合併一次查詢
  · 財經媒體 RSS 直抓（鉅亨網台股／頭條、Yahoo股市、股感 StockFeel）：留標題含
      「復華」或自家 ETF 代碼者，補 Google News 漏收或排序沉掉的稿——命中特定
      基金／產品者同時補進該清單
  · 社群：PTT 股票板公開索引頁標題（留自家相關者；推文數為聲量 proxy；
      禮貌抓取、只存標題＋連結，不落全文）＋ 強基金 fundhot 討論區（2026-08-12 使用者
      需求；台灣最大共同基金討論社群，金複合等復華投資方法討論的主場）＋ YouTube
      相關影片（2026-08-06 使用者需求；Data API v3、金鑰走 Actions secret
      `YOUTUBE_API_KEY`——v0.12 ETF 產品線時代使用者已設過的同一把，daily.yml 重新帶入；
      無金鑰誠實降級回 []）。
      Dcard／FB 涉反爬或授權，本層仍不碰（同 arm/connectors/social 的授權註記）。

落檔 data/fund_news.json；儀表板以「復華新聞・社群」區塊呈現（2026-08-12 使用者指示
改名，原「基金相關新聞・社群」）。
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
# 品牌詞（社群/RSS 相關性判準共用）：公司名之外，自家投資方法／服務的討論常不寫「復華」
# ——「金複合」＝復華金複合投資法/金複合理財機器人（2026-08-12 使用者點名強基金上這類
# 討論也要收）。詞要夠獨特才進清單（「金管家」他行也在用、易誤收，靠「復華金管家」寫法
# 自然命中「復華」即可）。
BRAND_TERMS = ("復華", "金複合")
BLOCKED_SOURCES = {"富聯網",          # 使用者指定排除的新聞來源（品牌與各基金皆不收）
                   "extra.rakuya.com.tw"}   # 房產站轉貼區，非新聞來源
# 註：「鉅亨買基金」不列黑名單（使用者指示：鉅亨的新聞內容仍要收）；
#     其平台頁/開戶頁等非新聞連結由 is_news_title() 的標題特徵過濾即可。

# 內容農場來源（2026-07 使用者回饋：這些會把舊文更新日期反覆重貼，冒充新聞佔版面，要排除）：
# 「CMoney投資網誌」＝部落格農場（非即時新聞）。CMoney 若有真新聞另計，靠 is_farm_title 標題特徵過濾。
FARM_SOURCES = {"CMoney投資網誌"}
# SEO 農場點閱誘餌標題特徵：績效／規模「誇飾＋問句／揭密」句式，
# 例「同樣是科技基金，為什麼近一年能漲超過 200%？」「單月規模暴增58億的背後秘密是什麼？」。
# 「該怎麼選／該選哪一檔」比較誘餌（2026-08-12 使用者：CMoney 論壇同稿掛多檔基金、無聊重複）
# 也算——注意股感式產品解析文「00409A…｜成分股？配息？優缺點？」是多段「主題？」羅列、
# 不含這些誘餌詞，不受影響（那正是使用者要的內容，勿誤殺）。
_FARM_HYPE = re.compile(r"為什麼|為何|憑什麼|究竟|背後|祕密|秘密|狂增|暴增|漲破|漲超過|"
                        r"稱霸|同類第一|百萬變|發生了什麼|該怎麼選|該選哪|選哪一檔|怎麼挑")

# 負面／司法／醜聞新聞：本工具為「復華內部溝通」用途，不宜在儀表板呈現自家的司法／弊案／
# 負面報導（2026-07 使用者要求排除；品牌與各基金、PTT 皆適用）。命中司法/弊案/操縱字眼即剔除。
# 例「勞動基金炒股案第3波　搜索復華投信」「投資長移送！經理人喊冤」。
# 2026-08-12 使用者重申「不要抓負面的文章」→ 補市況/績效負面詞（慘賠/套牢/跌破/清算…）：
# 標題級過濾、品牌與各基金/產品/社群全適用。
_NEGATIVE = re.compile(
    r"炒股|炒作|操縱|坑殺|內線|掏空|違約交割|"
    r"弊案|官商|貪污|貪瀆|收賄|賄賂|圖利|洗錢|不法|違法|犯罪|醜聞|"
    r"搜索|搜查|約談|傳喚|移送|起訴|偵辦|檢調|地檢|檢方|調查局|廉政|"
    r"收押|羈押|交保|判刑|求刑|定讞|起底|喊冤|裁罰|開罰|罰鍰|送辦|"
    r"慘賠|慘虧|大虧|虧損|套牢|重挫|暴跌|崩盤|腰斬|跌破|墊底|吊車尾|"
    r"贖回潮|規模縮水|下市|清算|申誡|糾正|內控缺失")

# 「非新聞頁面」標題特徵——搜尋/RSS 常混入基金介紹頁、文章列表頁、平台頁、討論牆、
# 淨值表等非新聞連結，佔版面又無資訊量，一律剔除（2026-07-04 使用者回饋：我要新聞）。
# 「公開說明書／信託契約」＝基金平台的例行修訂公告轉貼（2026-08-06 使用者抓包：中租基智網
# 一年前的公告被 Google 標成近期日期、同一則掛滿 6 檔基金卡）——公告類非新聞，一律剔除。
# 「的總覽／的買賣訊號／報酬走勢」＝鉅亨・MoneyDJ 的基金報價頁標題式樣（2026-08-12
# 使用者：「跳到基金網頁沒有實質幫助」）。
_JUNK_TITLE = re.compile(
    r"推薦文章|新聞資訊與消息|討論牆|一覽表|淨值表|交易平台|基金介紹|基金檔案|"
    r"基金專區|歷史淨值|基金列表|條款|開戶|公開說明書|信託契約|"
    r"暫停(?:銷售|申購|受理)|恢復(?:銷售|申購|受理)|停止受理|"
    r"的總覽|的買賣訊號|的基本資料|的配息紀錄|的持股狀況|報酬走勢|淨值及折溢價")

# 舊公告被 Google 重標日期的「標題自帶年代」防呆（2026-08-17 使用者抓包：中租基智網
# 民國111年「台灣好收益暫停銷售」公告以 08-16 姿態上版——與 2026-08-06 ezfunds 同型，
# 但這次標題是「暫停銷售」公告、junk 詞舊清單沒涵蓋，且台帳首見日就是重收日、驗證預算
# 也擋不到）。通用規則：標題內出現「年＋月／年度」日期式樣（民國 1xx年 → +1911；西元
# 20xx年），取最大年份，早於「前年」＝內容講的就是那個年代的事 → 舊文重收、剔除。
# 只認日期式樣，「創2020年以來新高」這類引述舊年份的當期新聞不受影響（年後接「以來」非月份）。
_TITLE_YEAR = re.compile(r"(?<!\d)(1[0-4]\d|20[0-4]\d)年(?=\d{1,2}月|度)")


def _title_stale_year(title: str, now: datetime | None = None) -> bool:
    """標題自帶的最近年份早於前年 → 舊公告重收。無日期式樣回 False。"""
    ys = [int(y) + (1911 if int(y) < 1000 else 0) for y in _TITLE_YEAR.findall(title or "")]
    return bool(ys) and max(ys) < (now or datetime.now(TW_TZ)).year - 1

# 「基金報價／平台頁」URL 特徵（2026-08-12 使用者抓包主力）：Google News 會收錄鉅亨
# invest.cnyes 基金總覽・買賣訊號頁、MoneyDJ ETF 報價頁、鉅亨基金詳情頁——標題不一定
# 帶上面的 junk 詞，URL 才是決定性特徵。CMoney 論壇文（cmoney.tw/forum/）＝部落格比較文
# 農場（「該怎麼選？」同稿掛多檔），整個路徑不收；cmoney.tw/notes 等真新聞路徑不受影響。
_JUNK_URL = re.compile(
    r"invest\.cnyes\.com/funds|fund\.cnyes\.com/detail|"
    r"moneydj\.com/etf/|moneydj\.com/funddj/yb|"
    # 中租基智網（ezfunds）＝基金銷售平台，其被 Google 收錄的內容全是例行公告轉貼，
    # 且屢次被重標成近期日期（2026-08-06 公開說明書公告、2026-08-17 民國111年暫停銷售
    # 公告皆此站）——整站剔除；真新聞本來就會在正規媒體出現，損失為零。
    r"ezfunds\.com\.tw|"
    r"cmoney\.tw/forum/|tw\.stock\.yahoo\.com/quote/", re.I)

# 財經媒體 RSS 直抓（免金鑰）——與 Google News 互補；站台全站 feed、本層只留「復華」相關
NEWS_FEEDS = [
    ("鉅亨網", "https://news.cnyes.com/rss/v1/news/category/tw_stock"),
    ("鉅亨網", "https://news.cnyes.com/rss/v1/news/category/headline"),
    ("Yahoo股市", "https://tw.stock.yahoo.com/rss"),
    # 股感 StockFeel（2026-08-12 使用者點名：00409A 專文出處）——WordPress 全站 /feed/，
    # 本層只留「復華／自家代碼」相關（feed_relevant）。容器 proxy 擋 stockfeel（實測
    # EGRESS_BLOCKED）＝本地跑必空；CI 可達性以首輪日誌驗證，失敗 fail-open 只損失此源。
    ("股感 StockFeel", "https://www.stockfeel.com.tw/feed/"),
]
_RSS_ITEM = re.compile(r"<item>(.*?)</item>", re.S | re.I)
_RSS_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_RSS_HTML = re.compile(r"<[^>]+>")

PTT_BASE = "https://www.ptt.cc"
# 2026-08-07 使用者需求：股票板之外也要找基金板（Fund 板基金討論密度高）
PTT_BOARDS = ("Stock", "Fund")
PTT_INDEX = PTT_BASE + "/bbs/{board}/index{n}.html"
_PTT_ENT = re.compile(r'<div class="r-ent">(.*?)</div>\s*</div>', re.S)
_PTT_TITLE = re.compile(r'<div class="title">\s*(?:<a href="([^"]+)">(.*?)</a>)?', re.S)
_PTT_PUSH = re.compile(r'<div class="nrec">(?:<span[^>]*>(.*?)</span>)?', re.S)
_PTT_DATE = re.compile(r'<div class="date">\s*(.*?)\s*</div>', re.S)
_PTT_PREV = re.compile(r'href="/bbs/\w+/index(\d+)\.html"[^>]*>.*?上頁', re.S)


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

    · 以問號收尾且帶績效／規模誇飾或比較誘餌字眼（「…為什麼近一年能漲超過 200%？」
      「…該怎麼選？」）；
    · 或明確的揭密／致富／賣關子句式（「背後秘密」「22年百萬變七百萬」「答案在這」）。"""
    t = (title or "").strip()
    if not t:
        return False
    if t.endswith("？") and _FARM_HYPE.search(t):
        return True
    return bool(re.search(r"背後(?:的)?(?:祕密|秘密)|百萬變[^，。]{0,6}萬|還能稱霸|答案在這", t))


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
    if _title_stale_year(t):
        return False
    if is_farm_title(t) or is_negative_title(t):
        return False
    if re.fullmatch(r"復華[\w・]{1,14}基金(?:[-‑–]?(?:新臺幣|美元|人民幣|[AB]|TISA)[^，,。]{0,6})?", t):
        return False
    return True


def _clean_items(items: list[dict]) -> list[dict]:
    """統一清理：剔除黑名單來源＋非新聞頁面（標題與 URL 兩層），剝標題尾的來源名。
    所有新聞路徑（品牌/產品/各基金/RSS）都經過這裡；sanitize() 讀取端同一套——
    既有落檔裡的報價頁連結下輪重建即消失，不必等重抓。"""
    out = []
    for i in items:
        if not source_ok(i):
            continue
        if _JUNK_URL.search(i.get("url") or ""):
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
        if not feed_relevant(title):
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


def _brand_hit(text: str | None) -> bool:
    """品牌詞命中：「復華」或自家投資方法詞（金複合……見 BRAND_TERMS）。"""
    t = text or ""
    return any(b in t for b in BRAND_TERMS)


def feed_relevant(title: str | None) -> bool:
    """全站 feed／RSS 只留自家相關：標題含品牌詞或自家 ETF 代碼（獨立詞，含即將
    掛牌檔——00409A 開募文常只寫代碼不寫全名）。"""
    t = title or ""
    return _brand_hit(t) or _code_hit(t)


def fetch_feeds(days: int = WINDOW_DAYS) -> list[dict]:
    """財經媒體 RSS 直抓（鉅亨網／Yahoo股市／股感），留自家相關。單一 feed 失敗誠實
    略過並印 CI 日誌（來源被擋時日誌是唯一除錯管道）。"""
    out: list[dict] = []
    for source, url in NEWS_FEEDS:
        try:
            xml = get_bytes(url, cache_ttl=1800).decode("utf-8", "ignore")
        except Exception as e:
            print(f"[fundnews] RSS 直抓失敗 {source}: {type(e).__name__}")
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
VERIFY_BUDGET = 24       # 每輪最多解幾篇原文（台帳沒驗過的新項目才消耗；容器端網路被擋＝0 成本；
                         # 2026-08-12 產品層加入後項目變多，16→24）
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


# ── 自家 ETF 產品層（2026-08-12 使用者抓包：股感 00409A 開募文全漏）──────────────
# 新聞查詢過去只有「品牌＋基金基底名」——自家 ETF（00929/00991A/…）與募集中新檔
# （00409A）完全不在查詢清單，經濟日報／聯合／股感的開募報導一則都收不到。
# 產品清單動態取自 etfwatch：追蹤中（watch_tuples 名稱含「復華」）＋「即將登場」
# （UPCOMING 名稱含「復華」，含未派碼檔）——募集→掛牌→轉正全程零維護跟上。


def fh_products() -> list[dict]:
    """自家 ETF 產品清單 [{code, name}]（新聞層查詢＋社群相關性共用）。
    未派碼者 code=None（僅名稱查詢）；etfwatch 取不到時退回靜態清單。"""
    try:
        from . import etfwatch
        out: list[dict] = []
        seen: set[str] = set()
        for t in etfwatch.watch_tuples():
            if "復華" in (t[1] or ""):
                out.append({"code": t[0], "name": t[1]})
                seen.add(t[0])
        for u in etfwatch.UPCOMING:
            if "復華" in (u.get("name") or "") and (u.get("code") or "") not in seen:
                out.append({"code": u.get("code"), "name": u["name"]})
        if out:
            return out
    except Exception:
        pass
    return [{"code": c, "name": n} for c, n in
            (("00929", "復華台灣科技優息"), ("00991A", "主動復華未來50"),
             ("00998A", "主動復華金融股息"), ("00986D", "主動復華金融債息"))]


def _code_mention(text: str, code: str) -> bool:
    """產品層的代碼比對：比 _code_hit 寬——允許「主動式ETF00409A來了」這種代碼緊貼
    英文字的媒體標題（Yahoo 實例），仍擋數字緊貼（題庫100929）與編號式前綴（L#00929）。"""
    return bool(re.search(rf"(?<![0-9])(?<![0-9A-Za-z][#＃]){re.escape(code)}(?![0-9A-Za-z])",
                          text or ""))


def product_item_relevant(item: dict, code: str | None) -> bool:
    """產品層留哪些：標題含「復華」或該檔代碼（_code_mention 寬鬆版）。查詢已用引號
    片語縮小範圍，這裡只擋放寬搜尋帶回的無關結果。"""
    t = item.get("title") or ""
    return "復華" in t or bool(code and _code_mention(t, code))


def fetch_etf_products(days: int = WINDOW_DAYS, per_limit: int = 4) -> list[dict]:
    """產品層新聞：每檔自家 ETF 一次 Google News 查詢（「代碼」OR「產品名」）。
    群組形狀同 fetch_funds（base/fund_ids/short_names/items）＋ code 欄；fund_ids 恆空
    ——渲染端據此改掛代碼章（無基金詳情卡可跳）。無新聞的檔 items 為 []。"""
    out = []
    for p in fh_products():
        code, name = p.get("code"), p.get("name") or ""
        if not name:
            continue
        q = f'"{code}" OR "{name}"' if code else f'"{name}"'
        items = gnews.search(q, days=days, limit=per_limit)
        if not items and code:                   # 引號片語沒中 → 放寬用純代碼再試一次
            items = gnews.search(code, days=days, limit=per_limit)
        kept, seen = [], set()
        for i in items:
            if not product_item_relevant(i, code):
                continue
            key = (i.get("title") or "")[:24]    # 同標題（多家轉載）只留最新一則
            if key in seen:
                continue
            seen.add(key)
            kept.append(i)
        out.append({"base": name, "code": code, "fund_ids": [],
                    "short_names": [code] if code else [], "items": _clean_items(kept)})
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
    """社群標題（PTT／強基金共用判準）是否與復華相關：含品牌詞（復華/金複合），
    或自家 ETF 代碼以獨立詞出現（2026-08-07 比照 YouTube 層——00929 這類討論串常只寫
    代碼不寫「復華」；獨立詞判定同 _code_hit，避免「L#00929」式編號誤收）；
    負面/司法討論串（is_negative_title）一律排除（內部溝通用途）。"""
    t = title or ""
    return (_brand_hit(t) or _code_hit(t)) and not is_negative_title(t)


def fetch_ptt(pages: int = 3, boards: tuple[str, ...] = PTT_BOARDS) -> list[dict]:
    """PTT 股票板＋基金板近幾頁標題，留與復華相關者（2026-08-07 使用者需求：
    「也找股票版不要只找基金版」→ 兩板都抓）。單板被擋／網路失敗該板回空、
    不互相牽連（誠實降級）；跨板轉錄同文以網址去重；項目帶 board 供渲染標板名。"""
    out: list[dict] = []
    seen: set[str] = set()
    for board in boards:
        url = f"{PTT_BASE}/bbs/{board}/index.html"
        for _ in range(max(1, pages)):
            try:
                html = get_bytes(url, cache_ttl=1800,
                                 headers={"Cookie": "over18=1"}).decode("utf-8", "ignore")
            except Exception as e:               # 靜默 break 會讓「被擋」與「查無相關
                print(f"[ptt] {board} 板抓取失敗: {e}")   # 討論」在日誌上長得一模一樣
                break
            for blk in _PTT_ENT.findall(html):
                mt = _PTT_TITLE.search(blk)
                if not mt or not mt.group(2):
                    continue
                title = re.sub(r"<[^>]+>", "", mt.group(2)).strip()
                if not ptt_relevant(title) or mt.group(1) in seen:
                    continue
                seen.add(mt.group(1))
                push = (_PTT_PUSH.search(blk) or [None, ""]).group(1) or ""
                date = (_PTT_DATE.search(blk) or [None, ""]).group(1) or ""
                out.append({"platform": "ptt", "board": board, "title": title,
                            "url": PTT_BASE + mt.group(1), "date": date.strip(),
                            "push": _ptt_reach(push)})
            mp = _PTT_PREV.search(html)
            if not mp:
                break
            url = PTT_INDEX.format(board=board, n=mp.group(1))
    out.sort(key=lambda x: x["push"], reverse=True)
    return out


# ── 強基金 fundhot 討論（2026-08-12 使用者需求：加入強基金論壇——台灣最大共同基金
#    討論社群，金複合理財機器人等復華投資方法討論的主場）─────────────────────────
# 兩套站並存：新站 fundhot.com/forum/{分類}/{slug}/{話題id}（現行主站）＋舊 phpBB
# forum.fundhot.com（viewtopic.php；有標準 feed.php 端點、mode=topics 給主題流）。
# 容器 proxy 擋 fundhot（WebFetch 實測 EGRESS_BLOCKED，同 PTT 型）——真正抓取在 CI；
# 兩源皆 fail-open、單源失敗不牽連，新站解析 0 筆時印「結構探針」原文片段
# （repo 慣例：印上下文片段才能一輪定位，別只印次數）。

FUNDHOT_BASE = "https://fundhot.com"
# ⚠ 2026-09-01 使用者回報「強基金都沒有在更新」的根因之一：舊種子清單裡的
# `/forum/股票` 是**舊 phpBB 的版名**，新站沒有這個分類 → CI 每天抓它必失敗，
# 三頁只剩總覽頁一頁在跑（且當時錯誤只印 type(e).__name__＝「RuntimeError」，
# 看不出是 404 還是被擋，連續數週沒人發現）。修法三道：種子改用實際存在的分類、
# 分類清單由總覽頁話題連結**自尋**補上（版面改名不會整批失效）、失敗印訊息本體。
FUNDHOT_PAGES = [                       # 新站討論區列表頁（總覽＋復華討論密度高的分類）
    FUNDHOT_BASE + "/forum",
    FUNDHOT_BASE + "/forum/" + urllib.parse.quote("股票基金"),
    FUNDHOT_BASE + "/forum/ETF",
    FUNDHOT_BASE + "/forum/" + urllib.parse.quote("資產配置"),
]
FUNDHOT_MAX_PAGES = 6                   # 含自尋分類的抓取上限（禮貌抓取、不無限展開）
FUNDHOT_FEED = "https://forum.fundhot.com/feed.php?mode=topics"   # phpBB 標準 Atom
# 舊站「最新討論」HTML 頁：feed.php 對訪客常被關閉（實測 CI 每天失敗），此為備援；
# phpBB 標準版式 `<a class="topictitle" href="./viewtopic.php?...t=NNN">`＋列內 <time>。
FUNDHOT_ACTIVE = "https://forum.fundhot.com/search.php?search_id=active_topics"
# ⚠ 2026-09-01 CI 實證（錯誤訊息一改印本體，一輪就定位）：`/forum` 總覽頁 **200**，
# 但**每一支分類頁（股票基金／ETF／資產配置／其他／天使）與舊站兩支端點全部 403**
# ——所以不是網址寫錯（本來猜是 404 死連結），是站方對「不像瀏覽器」的請求擋動態路由。
# 先試不涉及偽裝身分的作法：補齊瀏覽器一定會送、爬蟲常漏的標頭（Accept／
# Accept-Language／Referer），UA 仍誠實標示研究用途；本層每輪最多 6 個請求。
# 下一輪日誌若仍 403 → 就是 IP／WAF 層擋機房，屆時要嘛放棄此來源、要嘛另想辦法，
# **不要再往「多加幾支網址」的方向修**（那已被本輪證偽）。
FUNDHOT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": FUNDHOT_BASE + "/forum",
}
# 話題連結＝ /forum/{分類}/{slug}/{數字id}（分類/slug 常為 URL 編碼中文）；
# 分類頁連結只有兩段、不帶數字尾＝不會誤入。
_FUNDHOT_LINK = re.compile(
    r'<a[^>]+href="(?:https?://(?:www\.)?fundhot\.com)?(/forum/([^"/]+)/[^"/]+/(\d+))[^"]*"'
    r'[^>]*>(.*?)</a>', re.S | re.I)
_ATOM_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S | re.I)
_ATOM_LINK = re.compile(r'<link[^>]+href="([^"]+)"', re.I)
_HTML_TIME = re.compile(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})', re.I)
# 強基金新站列表頁沒有 <time datetime>，時間是**相對字串**（2026-09-01 加寬探針才看到：
# `<span class="text-auxiliary …">10小時前</span>`，緊接在標題 </a> 之後、作者連結之前）。
# 這是本來「日期整欄空白」的根因——有了它，強基金項目才有真日期可老化與顯示。
_REL_TIME = re.compile(r"(\d+)\s*(分鐘|小時|天|週|周|個月|月|年)前")
_REL_UNIT = {"分鐘": 1 / 1440, "小時": 1 / 24, "天": 1, "週": 7, "周": 7,
             "個月": 30, "月": 30, "年": 365}


def _rel_date(text: str) -> str:
    """「10小時前」「3天前」「1個月前」→ ISO 日期（台北時區）；認不出回空字串。
    月／年用 30／365 天近似——出了時窗就是舊文，差幾天不影響用途。"""
    m = _REL_TIME.search(text or "")
    if not m:
        return ""
    days = _REL_UNIT[m.group(2)] * int(m.group(1))
    return (datetime.now(TW_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")


def parse_fundhot_page(html: str) -> list[dict]:
    """新站列表頁 → [{platform, board, title, url, date?}]。純函式可單測；不做相關性
    與時窗過濾（fetch_fundhot 統一過）。board＝URL 分類段解碼（股票基金／其他…）；
    date 取標題後的 <time datetime>，沒有就解析相對時間（「10小時前」＝現行版式）。

    ⚠ 判定窗口切在**下一個 `<a `** 之前：時間標籤就在標題 `</a>` 與作者連結之間，
    這樣切既拿得到本列時間，也不會抓到下一列的（猜錯日期比沒日期更糟）。"""
    from html import unescape

    out, seen = [], set()
    text = html or ""
    for m in _FUNDHOT_LINK.finditer(text):
        path, cat, _tid, raw = m.groups()
        title = unescape(_RSS_HTML.sub("", raw)).strip()
        if len(title) < 4:                       # 導覽箭頭/「繼續閱讀」式短字連結
            continue
        url = FUNDHOT_BASE + path
        if url in seen:
            continue
        seen.add(url)
        it = {"platform": "fundhot", "board": urllib.parse.unquote(cat),
              "title": title, "url": url}
        nxt = text.find("<a ", m.end())
        win = text[m.end():min(nxt if nxt > 0 else len(text), m.end() + 700)]
        mt = _HTML_TIME.search(win)
        d = mt.group(1) if mt else _rel_date(win)
        if d:
            it["date"] = d
        out.append(it)
    return out


# phpBB 話題列（舊站最新討論頁）：`<a href="./viewtopic.php?…t=123" class="topictitle">`；
# class 與 href 的先後在佈景主題間會互換，故兩種順序都認。⚠ href 內的參數分隔字元是
# **HTML 實體 `&amp;`**（`?f=25&amp;t=13950`）——只寫 [?&]t= 會整批漏掉多參數的話題列。
_T_PARAM = r'(?:[?&]|&amp;)t=(\d+)'
_PHPBB_TOPIC = re.compile(
    rf'<a[^>]+(?:href="([^"]*viewtopic\.php[^"]*?{_T_PARAM}[^"]*)"[^>]*class="[^"]*topictitle'
    rf'|class="[^"]*topictitle[^"]*"[^>]*href="([^"]*viewtopic\.php[^"]*?{_T_PARAM}[^"]*)")'
    r'[^>]*>(.*?)</a>', re.S | re.I)


def parse_phpbb_topics(html: str, days: int = WINDOW_DAYS) -> list[dict]:
    """舊站「最新討論」HTML → [{platform, board, title, url, date?}]。純函式可單測。
    日期取話題連結後 600 字內的 <time datetime>（phpBB 列內「最後發表」時戳）；
    有日期才做時窗過濾，沒有的照留（由 first_seen 負責老化）。"""
    from html import unescape

    cutoff = (datetime.now(TW_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    out, seen = [], set()
    text = html or ""
    for m in _PHPBB_TOPIC.finditer(text):
        href, tid = m.group(1) or m.group(3), m.group(2) or m.group(4)
        title = unescape(_RSS_HTML.sub("", m.group(5))).strip()
        if not href or len(title) < 4 or tid in seen:
            continue
        seen.add(tid)
        # 網址正規化成 viewtopic.php?t={id}：原始 href 帶 sid（每次抓都不同）、相對路徑
        # 兩種形式，直接沿用會讓 first_seen 台帳與去重永遠對不上同一篇。
        it = {"platform": "fundhot", "board": "", "title": title,
              "url": f"https://forum.fundhot.com/viewtopic.php?t={tid}"}
        mt = _HTML_TIME.search(text[m.end():m.end() + 600])
        if mt:
            if mt.group(1) < cutoff:
                continue
            it["date"] = mt.group(1)
        out.append(it)
    return out


def parse_fundhot_feed(xml_text: str, days: int = WINDOW_DAYS) -> list[dict]:
    """phpBB Atom（mode=topics）→ 近 days 天 [{platform, board, title, url, date, datetime}]。
    純函式可單測。<updated> 出窗即略過；title 可能是 CDATA 或實體轉義，兩種都清。"""
    from datetime import timezone
    from html import unescape

    def _tag(t: str, blk: str) -> str:
        m = re.search(rf"<{t}[^>]*>(.*?)</{t}>", blk, re.S | re.I)
        return m.group(1) if m else ""

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for blk in _ATOM_ENTRY.findall(xml_text or ""):
        raw_t = _tag("title", blk)
        mcd = _RSS_CDATA.search(raw_t)
        title = unescape(_RSS_HTML.sub("", mcd.group(1) if mcd else raw_t)).strip()
        try:
            dt = datetime.fromisoformat(_tag("updated", blk).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < cutoff or not title:
            continue
        ml = _ATOM_LINK.search(blk)
        mc = re.search(r'<category[^>]+term="([^"]*)"', blk)
        out.append({"platform": "fundhot", "board": unescape(mc.group(1)) if mc else "",
                    "title": title, "url": unescape(ml.group(1)) if ml else "",
                    "date": dt.astimezone(TW_TZ).strftime("%Y-%m-%d"),
                    "datetime": dt.astimezone(TW_TZ).isoformat()})
    return out


def fetch_fundhot(days: int = WINDOW_DAYS, limit: int = 8) -> list[dict]:
    """強基金討論：新站列表頁（總覽＋分類，分類清單自尋）＋舊站 feed／最新討論頁並抓，
    同標題（前 24 字）跨源去重，留自家相關者（ptt_relevant 同判準：品牌詞/金複合/
    自家代碼、負面排除）。新站在前（現行主站）、舊站補漏；單源失敗不牽連。

    抓取用 retries=1／timeout=12：整站被擋時 3 retries×25s 會讓每頁空轉逾一分鐘
    （每日 routine 全長也才 ~80 秒），而這裡本來就是 fail-open 的加分來源。"""
    out: list[dict] = []
    seen: set[str] = set()

    cutoff = (datetime.now(TW_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")

    def _add(items: list[dict]) -> None:
        for it in items:
            k = (it.get("title") or "")[:24]
            if not k or k in seen or not ptt_relevant(it["title"]):
                continue
            d = it.get("date") or ""             # 有日期就照日期老化：站上長掛的舊討論
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and d < cutoff:
                continue                         # 不再以「新討論」姿態佔版面
            seen.add(k)
            out.append(it)

    def _get(url: str) -> str:
        return get_bytes(url, cache_ttl=1800, retries=1, timeout=12,
                         headers=FUNDHOT_HEADERS).decode("utf-8", "ignore")

    queue, done, probed = list(FUNDHOT_PAGES), set(), False
    pages_ok, new_n, new_dated = set(), 0, 0
    while queue and len(done) < FUNDHOT_MAX_PAGES:
        url = queue.pop(0)
        if url in done:
            continue
        done.add(url)
        try:
            page = _get(url)
        except Exception as e:                   # 印訊息本體（含 HTTP 狀態）：只印
            print(f"[fundhot] 列表頁抓取失敗: {e}")   # type name 看不出 404／被擋
            continue
        pages_ok.add(url)
        topics = parse_fundhot_page(page)
        new_n += len(topics)
        new_dated += sum(1 for t in topics if t.get("date"))
        if not topics:                           # 結構探針：一輪定位版式（repo 慣例）
            i = page.find("/forum/")
            print(f"[fundhot] {url} 解析 0 筆話題——探針："
                  + (repr(page[max(0, i - 80):i + 240]) if i >= 0
                     else f"頁面無 /forum/ 連結（{len(page)} bytes）"))
        elif not probed and not any(t.get("date") for t in topics):
            probed = True                        # 版式若其實帶日期，一輪即可收斂
            i = page.find(topics[0]["url"].replace(FUNDHOT_BASE, ""))
            # 窗口要夠寬才看得到「標題之後」有沒有日期欄（2026-09-01 首輪只印到 +320，
            # 剛好停在 <h3> 標題結束處、看不出下一格是什麼）。
            print("[fundhot] 列表頁無 <time datetime>（項目改以首見日老化）——探針："
                  + repr(page[max(0, i - 120):i + 700]))
        for t in topics:                         # 自尋分類頁：版面改名不會整批失效
            cand = FUNDHOT_BASE + "/forum/" + urllib.parse.quote(t.get("board") or "")
            if (t.get("board") and cand not in done and cand not in queue
                    and len(done) + len(queue) < FUNDHOT_MAX_PAGES):
                queue.append(cand)
        _add(topics)

    old: list[dict] = []
    try:
        old = parse_fundhot_feed(_get(FUNDHOT_FEED), days=days)
    except Exception as e:
        print(f"[fundhot] phpBB feed 抓取失敗: {e}")
    if not old:                     # feed 對訪客關閉時的備援＝舊站「最新討論」HTML 頁
        try:
            html = _get(FUNDHOT_ACTIVE)
            old = parse_phpbb_topics(html, days=days)
            if not old:
                print("[fundhot] 舊站最新討論頁解析 0 筆——探針："
                      + repr(html[:240]))
        except Exception as e:
            print(f"[fundhot] 舊站最新討論頁抓取失敗: {e}")
    _add(old)
    # 一行收支帳（每輪固定印）：抓到幾頁、解析幾篇、其中幾篇有日期、最後留幾篇。
    # 2026-09-01 需要它的理由：相對時間解析上線後，落檔裡的強基金項目**仍然沒有日期**，
    # 而從落檔分不出是「取得的那幾篇本來就沒時間標」（總覽頁的熱門/精選區塊）還是
    # 「整頁沒抓到、_carry_social 沿用舊項目」——這兩者的下一步差很多。
    print(f"[fundhot] 新站 {len(pages_ok)}/{len(done)} 頁 OK、解析 {new_n} 篇"
          f"（有日期 {new_dated} 篇）｜舊站 {len(old)} 篇 → 相關留用 {len(out[:limit])} 篇")
    return out[:limit]


# ── YouTube 相關影片（2026-08-06 使用者需求：社群討論加入 YouTube）──────────────
# 與 ETF 產品線的 arm/connectors/social/youtube.py 分離（該層查主動式ETF、回 SocialMention）；
# 本層查品牌／基金、回社群項目 dict。金鑰同一把：env YOUTUBE_API_KEY（Actions secret）
# 或 ~/.fh_youtube_key（本機慣例，同 arm/dashboard._youtube_voice）。

YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YT_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
YT_PLAYLIST = "https://www.googleapis.com/youtube/v3/playlistItems"
YT_CHANNELS = "https://www.googleapis.com/youtube/v3/channels"
# search.list 每次 100 單位（日限 10000）：相關 4 組＋市場熱門 5 組＝9 組×100
# ＋playlistItems 2＋channels 1＋videos.list 分批數單位 ≈ 每輪 907、日多輪仍 <3000
#（2026-08-14 使用者要求擴編市場熱門；勿再隨意加組——加組前先算這筆帳）。
YT_QUERIES = ["復華投信", "復華 基金", "復華 ETF", "00929"]
# 三層清單（2026-08-06 使用者規劃；2026-08-14 第三層擴編）：官方全收／相關（非官方）
# 取 3／市場熱門依分類配額取至多 6。
# 官方頻道是「兩個」（使用者提供 2026-08-06）：@fhifund 主頻道（金管家系列在此）＋
# @fhetf ETF 專屬頻道。鍵可填 UC 頻道 id（直接用）或 @handle（執行期 channels.list
# forHandle 解析、1 單位）；未來新官方頻道在此加一行即可。
YT_OFFICIAL_CHANNELS = {
    "UCD3J90bNoHykt6Eru8YxUmQ": "復華投信",   # @fhifund 主頻道
    "@fhetf": "復華ETF",                      # ETF 專屬頻道
}
YT_UNOFFICIAL_LIMIT = 3
# 市場熱門層（2026-08-14 使用者：「同業熱門的觀看數超級少……應該會有超級多討論 ETF
# 等等基金類的影片」；2026-08-15 再擴「投資相關（不要個股）」＋前端分類篩選）
# ——由「單一查詢＋硬性同業代碼」擴編為主題桶多查詢＋分類配額：
YT_PEER_QUERIES = ["台股 ETF", "高股息 ETF", "ETF 投資", "債券 ETF", "基金 投資",
                   "主動式 ETF", "台股"]   # 後兩組 2026-08-15 加：主動桶＋市場趨勢桶
YT_PEER_LIMIT = 10           # 總上限（2→6→10）——版面有分類篩選 chips 後允許長一點
YT_PEER_CAT_LIMIT = 2        # 每類配額——viewCount 排序易被單一題材（高股息）洗版
YT_PEER_MIN_VIEWS = 5000     # 熱門門檻（使用者抱怨兩三千觀看）；全數未達才 fallback 取 2
YT_PEER_FRESH_DAYS = 5       # 2→3→5 天：使用者要求略微擴大時間軸，讓觀看數有時間累積
YT_SEARCH_MAX = 25           # search.list 成本與 10 筆同為 100 單位——放大 pool 零額度成本
# 指名剔除的影片 id（sanitize 讀取端過濾，舊落檔／_carry_social 沿用款立即生效）：
YT_BLOCK_IDS = {
    "D_pC9_q5spQ",   # 可蘭經朗誦《Surah Rahman | Ep - 00929》（2026-08-14 使用者回報誤收）
    "FAkMraqLuko",   # 日文頻道「両学長」米国高配当株ETF 解說（2026-08-17 使用者回報誤收）
}
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
    """復華自家 ETF 代碼（fh_products：追蹤中＋即將登場，動態取自 etfwatch）——標題只寫
    代碼不寫「復華」的影片／討論串（00929 常見；募集期的 00409A 同型）也算相關。"""
    return tuple(p["code"] for p in fh_products() if p.get("code"))


def _peer_codes() -> tuple[str, ...]:
    """同業 ETF 代碼（etfwatch 追蹤清單中名稱不含「復華」者）——同業熱門層的判準。"""
    try:
        from . import etfwatch
        codes = tuple(t[0] for t in etfwatch.watch_tuples() if "復華" not in (t[1] or ""))
        if codes:
            return codes
    except Exception:
        pass
    return ("0050", "0056", "00878", "00919", "006208")


# 集數式編號前綴（Ep - 00929／EP.00929／第00929集／No.00929）：可蘭經朗誦影片
# 《Surah Rahman | Ep - 00929》曾以獨立詞命中 00929 誤收（2026-08-14 使用者回報），
# 「L#00929」型防呆擋不住空白隔開的集數寫法。
_EP_PREFIX = r"(?i)(?:\bep(?:isode)?|\bno|第)\s*[.\-–—:：#＃]*\s*"
_CJK_RE = re.compile(r"[一-鿿]")


def _has_cjk(text: str) -> bool:
    """含漢字才可能是台股受眾內容——relevanceLanguage=zh-Hant 只是「偏好」非過濾，
    純外語標題（可蘭經朗誦《Ep - 00929》型）要靠這層擋。"""
    return bool(_CJK_RE.search(text or ""))


# 日文假名「字母」（平假名 ぁ-ゖ＋片假名 ァ-ヺ）——「含漢字」擋不住日文（日文本來就用漢字：
# 2026-08-17 使用者回報両学長「米国高配当株ETFの基礎」誤入市場熱門層，標題滿是主題詞
# ETF／高配当，海外排除又只認「美股/美國 ETF」不認「米国」）。台股受眾標題不會有假名字母；
# 排除「の」（台灣商品名偶見的風格用字，單獨出現不足以判日文）。
# ⚠ 只認字母、不可含記號區（同日踩坑：首版用 [ぁ-ゟ゠-ヿ] 整段，把 U+30FB「・」與
# U+30FC「ー」——台灣標題極常用的全形間隔號/長音符——當日文，抓取端整批誤殺，
# YouTube 從 14 支砍到剩 1 支；_carry_social 只擋「全空」、剩 1 支不觸發沿用）。
_KANA_RE = re.compile(r"[ぁ-ゖァ-ヺ](?<!の)")


def _is_japanese(text: str) -> bool:
    """帶假名（「の」除外）＝日文內容、非台股受眾。"""
    return bool(_KANA_RE.search(text or ""))


def _code_hit(text: str, codes: tuple[str, ...] | None = None) -> bool:
    """ETF 代碼是否以「獨立詞」出現（預設查自家代碼）。防呆（2026-08-06 實戰誤收）：
    日文單字卡影片標題帶課號「L#00929」被純子字串比對誤判——代碼前後不得緊貼英數，
    也不得是「英數+#」的編號式前綴；獨立 hashtag（空格後的 #00929）仍算相關。
    2026-08-14 再補：集數式前綴（Ep -／第…）的代碼＝影片編號、不算命中。"""
    for c in codes if codes is not None else _fh_codes():
        if not re.search(rf"(?<![0-9A-Za-z])(?<![0-9A-Za-z][#＃]){re.escape(c)}(?![0-9A-Za-z])",
                         text):
            continue
        if re.search(_EP_PREFIX + re.escape(c), text):
            continue
        return True
    return False


def yt_relevant(title: str, desc: str = "") -> bool:
    """相關層：標題或說明含品牌詞（復華/金複合）或自家 ETF 代碼（獨立詞）才算相關
    （查詢會回同名他牌/無關影片）；負面司法題材同 PTT 排除。
    純代碼命中（無品牌詞）另須含漢字——00929 這種五碼數字在全外語影片裡多半是編號。"""
    text = f"{title} {desc}"
    if is_negative_title(title) or _is_japanese(title):
        return False
    if _brand_hit(text):
        return True
    return _code_hit(text) and _has_cjk(text)


# 市場熱門層主題詞與海外排除（2026-08-14 擴編）：本區是台股同業／市場動態，
# 純美股 ETF 內容（無任何台股代碼）不收；單獨「美國／美股」字樣不排除——
# 「美國降息 台股ETF受惠」式新聞標題是常態。
_YT_TOPIC = re.compile(r"ETF|高股息|市值型|存股|定期定額|債券|配息|基金", re.I)
_YT_OFFSHORE = re.compile(
    r"(?<![0-9A-Za-z])(?:VOO|QQQ|SPY|VTI|VT|IVV|SCHD|JEPI|JEPQ|TLT|VYM|BND|SGOV)"
    r"(?![0-9A-Za-z])|美股\s*ETF|美國\s*ETF", re.I)
_TW_ETF_CODE = re.compile(r"(?<![0-9A-Za-z])00\d{2,4}[A-Z]?(?![0-9A-Za-z])")
# 市場趨勢詞（2026-08-15 使用者：「投資相關的（不要個股）」——大盤行情／總經政策／
# 資產配置層級的投資內容也收進熱門層，個股本位的不要）：
_YT_TREND = re.compile(
    r"台股|大盤|加權指數|行情|盤勢|走勢|多頭|空頭|牛市|熊市|崩盤|回檔|反彈|萬點|"
    r"創新高|總經|景氣|通膨|降息|升息|聯準會|央行|資產配置|投資組合|股市|理財")
# 個股本位訊號（只驗標題）：知名個股名／個股操作詞／非 00 開頭的 4 碼代號
#（年份「2026年」與點數「4000點」以尾綴排除；00 開頭是 ETF、不在此列）。
_STOCK_FOCUS = re.compile(
    r"台積電|鴻海|聯發科|廣達|緯創|緯穎|大立光|聯電|日月光|長榮|陽明|萬海|中鋼|台塑|"
    r"國泰金|富邦金|中信金|開發金|玉山金|台達電|個股|飆股|選股|當沖|漲停|"
    r"(?<![0-9])[1-9]\d{3}(?![0-9年點])")


def yt_peer_relevant(title: str, desc: str = "") -> bool:
    """市場熱門層（2026-08-14 由「同業熱門」擴編；2026-08-15 再擴市場趨勢）：
    自家內容（品牌詞/自家代碼）歸相關層（不重複）、負面司法題材照樣排除、標題須含漢字；
    三條路徑任一即收——①含同業 ETF 代碼（獨立詞，原判準）；②ETF・基金主題詞或台股
    ETF 代碼（高觀看的泛 ETF 討論多不寫代碼）；③市場趨勢詞（大盤行情/總經/資產配置）。
    個股本位防呆（使用者：不要個股）：**無任何產品面（主題詞/台股 ETF 代碼）**時，
    標題命中知名個股/個股操作詞/4 碼個股代號 → 不收（「台積電還能買嗎」型）；
    有產品面則不受影響（ETF 成分股討論常點名個股）。純海外照舊不收。"""
    text = f"{title} {desc}"
    if is_negative_title(title) or _brand_hit(text) or _code_hit(text):
        return False
    if not _has_cjk(title) or _is_japanese(title):
        return False
    if _code_hit(text, _peer_codes()):
        return True
    etfish = bool(_YT_TOPIC.search(text) or _TW_ETF_CODE.search(text))
    if not etfish and not _YT_TREND.search(text):
        return False
    if _YT_OFFSHORE.search(text) and not _TW_ETF_CODE.search(text):
        return False
    return etfish or not _STOCK_FOCUS.search(title)


_FUND_WORDS = re.compile(r"基金|金複合|理財機器人|投資法")


def yt_topic(title: str) -> str:
    """市場熱門影片主題分類（儀表板章「熱門・{類別}」；配額避免單一題材洗版）。
    優先序：債券 > 高股息 > 主動式 > 市值型 > 基金 > 市場趨勢 > 綜合。"""
    t = title or ""
    if "債" in t:
        return "債券"
    if re.search(r"高股息|高息|配息|除息|息收|領息|月配|季配|殖利率", t):
        return "高股息"
    if re.search(r"主動式|主動型|主動\s*ETF", t) or re.search(
            r"(?<![0-9A-Za-z])00\d{2,4}A(?![0-9A-Za-z])", t):
        return "主動式"
    # 「大盤」不得吃掉「大盤點」（2026-08-15 實戰誤分：《高息ETF除息大盤點》被標市值型）
    if re.search(r"市值型|大盤(?!點)|指數化|指數型", t) or re.search(
            r"(?<![0-9A-Za-z])(?:0050|006208|00922|00923)(?![0-9A-Za-z])", t):
        return "市值型"
    # 基金詞含理財機器人/金複合（「理財」單獨是趨勢詞，機器人組合是基金產品）
    if _FUND_WORDS.search(t) and not re.search(r"ETF", t, re.I):
        return "基金"
    # 市場趨勢（2026-08-15）＝有趨勢詞、又沒有任何產品字樣（有 ETF/基金/代碼的歸上面各類）
    if _YT_TREND.search(t) and not re.search(r"ETF|基金", t, re.I) \
            and not _TW_ETF_CODE.search(t):
        return "市場趨勢"
    return "綜合"


def social_group(item: dict) -> str:
    """社群項目 → 前端「分類篩選」分組鍵（2026-08-15 使用者：太長了要可點分類篩選）。
    回 etf／active／fund／trend／other；儀表板每列掛 data-fcat、chips 依此篩
    （other 只在「全部」顯示）。熱門層優先用選片時算好的 cat；官方／相關／PTT／
    強基金項目就標題分類（同一套 yt_topic＋關鍵詞）。"""
    t = item.get("title") or ""
    cat = item.get("cat") or yt_topic(t)
    if cat == "主動式":
        return "active"
    if cat == "基金":
        return "fund"
    if cat == "市場趨勢":
        return "trend"
    if cat in ("債券", "高股息", "市值型"):
        return "etf"
    if re.search(r"ETF", t, re.I) or _TW_ETF_CODE.search(t):
        return "etf"
    if _FUND_WORDS.search(t):
        return "fund"
    if _YT_TREND.search(t):
        return "trend"
    return "other"


def _norm_yt_title(t: str) -> str:
    """正規化標題供跨頻道同片去重：聯播節目（三立財經iNEWS／94要賺錢曾同片異 id
    各佔一格）標題只差尾端「｜頻道名」段——去尾段＋去空白後相同即視為同一支內容。"""
    t = re.sub(r"[｜|][^｜|]{1,20}$", "", t or "")
    return re.sub(r"\s+", "", t)


def _select_peers(items: list[dict]) -> list[dict]:
    """市場熱門選片（2026-08-14 擴編）：同片去重 → 觀看門檻 YT_PEER_MIN_VIEWS →
    分類配額（每類 YT_PEER_CAT_LIMIT、總 YT_PEER_LIMIT）。輸入已依觀看數排序
    （parse_youtube）。全數未達門檻（安靜週末）→ 退而取前 2、不留白。
    類別一律寫進 item["cat"]（含「綜合」——渲染端綜合章顯示素「熱門」，
    2026-08-15 起前端分類篩選 data-fcat 也吃這個欄位）。"""
    pool: list[dict] = []
    seen_t: set[str] = set()
    for it in items:
        k = _norm_yt_title(it.get("title") or "")
        if k and k in seen_t:
            continue
        seen_t.add(k)
        pool.append(it)

    def _tag(it: dict) -> dict:
        it["cat"] = yt_topic(it.get("title") or "")
        return it

    picked: list[dict] = []
    cat_n: dict[str, int] = {}
    for it in pool:
        if len(picked) >= YT_PEER_LIMIT:
            break
        if (it.get("views") or 0) < YT_PEER_MIN_VIEWS:
            continue
        cat = yt_topic(it.get("title") or "")
        if cat_n.get(cat, 0) >= YT_PEER_CAT_LIMIT:
            continue
        cat_n[cat] = cat_n.get(cat, 0) + 1
        picked.append(_tag(it))
    return picked if picked else [_tag(it) for it in pool[:2]]


def _yt_secs(iso: str) -> int:
    """ISO8601 時長（PT1H2M3S）→ 秒；解析不出回 0。"""
    m = _YT_DUR.fullmatch((iso or "").strip())
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def parse_youtube(search_docs: list[dict], stats: dict | None = None, *,
                  relevant=None, mark: dict | None = None,
                  seen: set | None = None) -> list[dict]:
    """search.list 形狀的回應（多組）＋{videoId: {views, sec}} → 社群項目。純函式可單測。
    `relevant`＝相關性判準（預設 yt_relevant；官方層傳恆真）；`mark`＝附加欄位
    （官方 {"official":True}／同業 {"peer":True}）；`seen` 傳共用集合可跨層去重
    （官方先解析，同支影片就不再佔相關／同業層名額）。時長 ≤3 分標 Shorts
    （連結走 /shorts/）；依觀看數→日期新→舊排序，上限由呼叫端各層自取。"""
    stats = stats or {}
    relevant = relevant or yt_relevant
    seen = seen if seen is not None else set()
    out: list[dict] = []
    for doc in search_docs or []:
        for it in (doc or {}).get("items") or []:
            vid = (it.get("id") or {}).get("videoId")
            sn = it.get("snippet") or {}
            title = (sn.get("title") or "").strip()
            if not vid or vid in seen or not relevant(title, sn.get("description") or ""):
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
                    "views": int(st.get("views") or 0), **(mark or {})}
            if short:
                item["short"] = True
            out.append(item)
    out.sort(key=lambda x: (x.get("views") or 0, x.get("date") or ""), reverse=True)
    return out


def _pl_docs(data: dict, after_iso: str) -> dict:
    """playlistItems.list 回應 → search.list 形狀（沿用同一套 parse_youtube）。
    濾掉視窗外的舊上傳（官方頻道久未發片時，uploads 前 10 支可能是幾個月前的）。"""
    items = []
    for it in (data or {}).get("items") or []:
        sn = it.get("snippet") or {}
        cd = it.get("contentDetails") or {}
        vid = cd.get("videoId") or (sn.get("resourceId") or {}).get("videoId")
        pub = cd.get("videoPublishedAt") or sn.get("publishedAt") or ""
        if not vid or (after_iso and pub and pub < after_iso):
            continue
        items.append({"id": {"videoId": vid}, "snippet": {**sn, "publishedAt": pub}})
    return {"items": items}


def fetch_youtube(days: int = WINDOW_DAYS) -> list[dict]:
    """三層 YouTube 清單（2026-08-06 使用者規劃；2026-08-14 第三層擴編）。
    無金鑰／被擋回 []（誠實降級，不影響 PTT）：
    ①官方＝YT_OFFICIAL_CHANNELS 各頻道近窗全部上傳（uploads 播放清單、每頻道 1 單位），
      依日期新→舊、不限支數（「有發都納進去」）；
    ②相關＝關鍵字搜尋＋yt_relevant，依觀看數取前 YT_UNOFFICIAL_LIMIT；
    ③市場熱門＝YT_PEER_QUERIES 主題桶各近 YT_PEER_FRESH_DAYS 天依觀看數搜尋，
      yt_peer_relevant 過濾後交 _select_peers（門檻／同片去重／分類配額）。
    三層共用 seen 去重（官方優先），各層失敗不互相牽連。"""
    from datetime import timezone

    key = _yt_key()
    if not key:
        return []

    def _get_json(url: str) -> dict:
        return json.loads(get_bytes(url, cache_ttl=1800).decode("utf-8", "ignore"))

    now = datetime.now(timezone.utc)
    after = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    official_docs: list[dict] = []
    for ckey in YT_OFFICIAL_CHANNELS:
        try:
            cid = ckey
            if ckey.startswith("@"):           # @handle → 頻道 id（channels.list、1 單位）
                items = _get_json(f"{YT_CHANNELS}?part=id"
                                  f"&forHandle={urllib.parse.quote(ckey)}"
                                  f"&key={key}").get("items") or []
                cid = (items[0] or {}).get("id") or ""
            if not cid.startswith("UC"):
                print(f"[fundnews] YouTube 官方頻道 handle 解析失敗 {ckey}")
                continue
            official_docs.append(_pl_docs(_get_json(   # uploads 播放清單 id＝UC→UU（官方慣例）
                f"{YT_PLAYLIST}?part=snippet,contentDetails&maxResults=10"
                f"&playlistId=UU{cid[2:]}&key={key}"), after))
        except Exception as e:
            print(f"[fundnews] YouTube 官方頻道抓取失敗 {ckey}: {type(e).__name__}")

    # 搜尋層錯誤不可靜默吞（2026-08-17 踩坑：日限 10,000 單位被單日 ~10 輪 CI 重跑燒完，
    # search 全 403 quotaExceeded 卻只見「相關 0・同業 0」，diagnosis 得逆推——每層印一次原因；
    # 配額於太平洋時間午夜（台北 15:00/16:00）重置，隔輪自癒）。
    def _search_all(queries, order, published_after, label):
        out, err = [], None
        for q in queries:
            try:
                out.append(_get_json(
                    f"{YT_SEARCH}?part=snippet&type=video&order={order}"
                    f"&maxResults={YT_SEARCH_MAX}&regionCode=TW&relevanceLanguage=zh-Hant"
                    f"&publishedAfter={published_after}&q={urllib.parse.quote(q)}&key={key}"))
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:120]}"
        if err and not out:
            print(f"[fundnews] YouTube {label}層搜尋全數失敗（{err}）"
                  "——常見原因＝日配額耗盡（403 quotaExceeded，台北 15~16 時重置）")
        elif err:
            print(f"[fundnews] YouTube {label}層部分搜尋失敗（{err}）")
        return out

    docs = _search_all(YT_QUERIES, "date", after, "相關")
    p_after = (now - timedelta(days=YT_PEER_FRESH_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    peer_docs = _search_all(YT_PEER_QUERIES, "viewCount", p_after, "熱門")

    vids = [v for grp in (official_docs, docs, peer_docs) for d in grp
            for it in d.get("items") or []
            if (v := (it.get("id") or {}).get("videoId"))]
    stats: dict[str, dict] = {}
    ids = list(dict.fromkeys(vids))
    for i in range(0, len(ids), 50):    # videos.list 單次上限 50 支 → 分批（每批 1 單位）。
        try:                            # 舊版只取前 50、其餘靜默 0 觀看沉底＝永遠選不進。
            data = _get_json(f"{YT_VIDEOS}?part=statistics,contentDetails"
                             f"&id={','.join(ids[i:i + 50])}&key={key}")
            for it in data.get("items") or []:
                stats[it.get("id") or ""] = {
                    "views": int((it.get("statistics") or {}).get("viewCount") or 0),
                    "sec": _yt_secs((it.get("contentDetails") or {}).get("duration") or ""),
                }
        except Exception:
            continue

    seen: set = set()
    official = parse_youtube(official_docs, stats, relevant=lambda t, d="": True,
                             mark={"official": True}, seen=seen)
    official.sort(key=lambda x: x.get("date") or "", reverse=True)   # 官方＝公告流、日期序
    related = parse_youtube(docs, stats, seen=seen)[:YT_UNOFFICIAL_LIMIT]
    peer = _select_peers(parse_youtube(peer_docs, stats, relevant=yt_peer_relevant,
                                       mark={"peer": True}, seen=seen))
    return official + related + peer


def route_feeds_to_funds(fund_groups: list[dict], feeds: list[dict]) -> list[dict]:
    """RSS 直抓中命中特定基金核心名（或產品代碼——股感 00409A 專文只寫代碼）者，
    補進該群組清單（同標題去重、時間新→舊）。"""
    for g in fund_groups:
        code = g.get("code")
        core = (g.get("base") or "").replace("復華", "").replace("基金", "").strip()
        if not (core or code):
            continue
        extra = [i for i in feeds
                 if (core and core in (i.get("title") or ""))
                 or (code and _code_mention(i.get("title") or "", code))]
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
        names = "、".join(g.get("code")                       # 產品群組以代碼呈現（較短）
                          or (g.get("base") or "").replace("復華", "").replace("基金", "")
                          for g in hit[:6])
        more = f" 等 {len(hit)} 檔" if len(hit) > 6 else ""
        hl.append(f"近 {win} 天有專屬報導的基金／ETF：{names}{more}（詳下方新聞標籤）")
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
    Google News 項目先過 date_verify（pubDate 會把舊文標成近期，見該函式 docstring）。
    群組順序＝產品（自家 ETF）在前、基金在後——募集/掛牌動態是當前讀者重點。"""
    seen, state = _seen_load(), {"budget": VERIFY_BUDGET}
    feeds = _clean_items(fetch_feeds(days=days))
    brand_feeds = [f for f in feeds if "復華" in (f.get("title") or "")]  # 代碼命中者歸產品層
    brand = merge_news(date_verify(fetch_brand(days=days), seen, state, days=days),
                       brand_feeds)
    groups = fetch_etf_products(days=days) + fetch_funds(funds, days=days)
    for g in groups:
        g["items"] = date_verify(g["items"], seen, state, days=days)
    groups = route_feeds_to_funds(groups, feeds)
    _seen_save(_seen_prune(seen, datetime.now(TW_TZ)))
    doc = {
        "as_of": stamp_tw("%Y/%m/%d %H:%M"),
        "window_days": days,
        "source": "Google News（品牌＋自家ETF＋各基金）＋鉅亨網/Yahoo股市/股感 RSS"
                  "＋PTT 股票板/基金板＋強基金討論區＋YouTube 影片・自動擷取",
        "brand": brand,
        "funds": groups,
        "social": fetch_ptt() + fetch_fundhot(days) + fetch_youtube(days),
    }
    doc["highlights"] = auto_highlights(doc)
    return doc


def is_empty(doc: dict | None) -> bool:
    """三類情報（品牌／各基金／PTT）全空 → True。全空多半是網路被擋，不是真的沒新聞。"""
    if not doc:
        return True
    return not (doc.get("brand") or doc.get("social")
                or any(g.get("items") for g in doc.get("funds") or []))


def _social_in_window(s: dict, cutoff: str) -> bool:
    """社群項目是否還在時窗內（_carry_social 沿用判準）：ISO 日期照日期比；PTT 短日期
    無年份、不做窗檢（隨下次成功抓取整批汰換）；**無日期者改比首見日**——沒有這條，
    強基金新站列表頁那種無日期項目會永遠豁免窗檢、來源掛掉時原地凍結（2026-09-01）。
    連首見日都沒有的舊落檔項目 fail-open 留著，下次 save 就會被 _stamp_first_seen 補上。"""
    d = s.get("date") or ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return d >= cutoff
    if d:
        return True
    fs = s.get("first_seen") or ""
    return fs >= cutoff if fs else True


def _stamp_first_seen(doc: dict, prev: dict | None) -> None:
    """無日期的社群項目補「首見日」：同 url 沿用既有值（不因每天重抓而變新），
    新項目記今天。用途有二——①老化（見 _social_in_window）②儀表板標「首見 M/D」，
    讓「站上還掛著的舊討論」一眼看得出不是今天的新討論。有 date 者不動
    （date＝發文日，first_seen 只是替代品）。"""
    old = {s.get("url"): s.get("first_seen") for s in (prev or {}).get("social") or []}
    today = datetime.now(TW_TZ).strftime("%Y-%m-%d")
    for s in doc.get("social") or []:
        if not s.get("date"):
            s["first_seen"] = old.get(s.get("url")) or today


def _carry_social(doc: dict, prev: dict | None) -> None:
    """社群「來源級」防呆：本次某平台（ptt／fundhot／youtube）全空而既有落檔該平台非空 →
    沿用既有項目（來源異常≠查無討論），並印 CI 日誌讓異常可見。

    2026-08-07 踩坑：push 觸發的 CI 用了舊分支的 daily.yml（無 YOUTUBE_API_KEY env），
    fetch_youtube 回 []，整份防呆只看 brand/funds/social「全空」——品牌新聞有抓到就照樣
    落檔，把前日 7 則社群洗成 0。平台判定同 auto_highlights（platform 缺值視為 ptt）；
    ISO 日期項目出 window_days 窗即不再沿用（PTT 短日期格式無年份、不做窗檢，
    其項目本就隨下次成功抓取整批汰換）。"""
    old = (prev or {}).get("social") or []
    if not old:
        return
    cur = doc.get("social") or []
    win = doc.get("window_days") or WINDOW_DAYS
    cutoff = (datetime.now(TW_TZ) - timedelta(days=win)).strftime("%Y-%m-%d")

    def plat(s: dict) -> str:
        p = s.get("platform") or "ptt"
        return p if p in ("youtube", "fundhot") else "ptt"

    carried: list[dict] = []
    for p in ("ptt", "fundhot", "youtube"):
        if any(plat(s) == p for s in cur):
            continue
        keep = [s for s in old if plat(s) == p and _social_in_window(s, cutoff)]
        if keep:
            print(f"[fundnews] 社群 {p} 本次全空、沿用既有 {len(keep)} 則"
                  f"（來源異常≠查無討論）")
            carried += keep
    if carried:
        doc["social"] = cur + carried
        doc["highlights"] = auto_highlights(doc)


def save(doc: dict) -> tuple[Path, bool]:
    """落檔。防呆：本次擷取全空且既有落檔非空 → 保留舊檔不覆寫（回 saved=False）；
    單一社群平台全空而既有非空 → 該平台沿用既有項目（_carry_social）。

    2026-07-04 教訓：雲端環境 Google News/PTT 被 proxy 政策擋下時，曾把非空的
    fund_news.json 覆寫成全空。全空結果一律視為「來源異常」而非「查無新聞」。"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prev = load()
    if is_empty(doc) and not is_empty(prev):
        return OUT, False
    _carry_social(doc, prev)
    _stamp_first_seen(doc, prev)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUT, True


def _yt_vid(url: str) -> str:
    """YouTube 連結 → 影片 id（watch?v=／shorts/ 兩形；解析不出回空字串）。"""
    m = re.search(r"(?:[?&]v=|/shorts/)([\w-]{6,})", url or "")
    return m.group(1) if m else ""


def _social_ok(s: dict) -> bool:
    """社群項目讀取端防呆（sanitize 用）：負面題材全平台濾；YouTube 另擋
    ①指名黑名單 YT_BLOCK_IDS、②非官方且標題無漢字（可蘭經朗誦《Ep - 00929》型
    誤收）、③非官方且標題帶假名（日文財經影片「米国高配当株ETF」型誤收，2026-08-17）
    ——舊落檔與 _carry_social 沿用款不必等重抓即消失。"""
    if is_negative_title(s.get("title") or ""):
        return False
    if (s.get("platform") or "") != "youtube":
        return True
    if _yt_vid(s.get("url") or "") in YT_BLOCK_IDS:
        return False
    t = s.get("title") or ""
    return bool(s.get("official")) or (_has_cjk(t) and not _is_japanese(t))


def sanitize(doc: dict | None) -> dict | None:
    """讀取時再過一次農場／負面過濾：即使既有落檔是舊規則抓的（含 CMoney投資網誌 農場文、
    復華司法/醜聞報導），儀表板顯示時也一律濾掉——不必等下次重抓。純過濾、不新增內容。
    YouTube 項另做同片去重（聯播節目同片異 id；落檔順序官方在前、同層依觀看序，
    先到者即該留者）。"""
    if not doc:
        return doc
    doc["brand"] = _clean_items(doc.get("brand") or [])
    for g in doc.get("funds") or []:
        g["items"] = _clean_items(g.get("items") or [])
    soc, seen_yt = [], set()
    for s in doc.get("social") or []:
        if not _social_ok(s):
            continue
        if (s.get("platform") or "") == "youtube":
            k = _norm_yt_title(s.get("title") or "")
            if k and k in seen_yt:
                continue
            seen_yt.add(k)
        soc.append(s)
    doc["social"] = soc
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
