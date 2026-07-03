"""基金相關新聞・社群聲量 —— 復華基金雷達專屬的情報層（新增區塊、不動既有模組）。

與 ETF 產品線的 arm/connectors/social 完全分離（不共用過濾詞彙、不改其程式）：
  · 新聞：Google News RSS（免金鑰，直接引用 arm.connectors.gnews）
      - 品牌層：「復華投信」動態（公告／配息／得獎／人事）
      - 基金層：每檔以「基金基底名」搜尋；同基金的 A／B／TISA 類別合併一次查詢
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

from .connectors import gnews
from .http import get_bytes

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fund_news.json"

WINDOW_DAYS = 7
BRAND_QUERIES = ["復華投信", "復華投信 基金"]

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


def _clean_items(items: list[dict]) -> list[dict]:
    return [{**i, "title": strip_source_suffix(i.get("title"), i.get("source"))} for i in items]


def fetch_brand(days: int = WINDOW_DAYS, limit: int = 10) -> list[dict]:
    """品牌層新聞：復華投信動態。抓不到回 []。"""
    return _clean_items(gnews.search_many(BRAND_QUERIES, days=days, limit=limit))


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


def assemble(funds: list[dict], days: int = WINDOW_DAYS) -> dict:
    """抓齊三類情報 → 可落檔的 doc。任一來源失敗該類為空、不互相牽連。"""
    return {
        "as_of": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "window_days": days,
        "source": "Google News（台灣繁中）＋ PTT 股票板公開標題・自動擷取",
        "brand": fetch_brand(days=days),
        "funds": fetch_funds(funds, days=days),
        "social": fetch_ptt(),
    }


def save(doc: dict) -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUT


def load() -> dict | None:
    """儀表板用：讀最近一次落檔；無檔回 None（區塊顯示提示、不壞版）。"""
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
