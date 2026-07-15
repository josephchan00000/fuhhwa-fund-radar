"""鉅亨網基金（fund.cnyes.com）連接器 —— 每日基準多期報酬覆蓋層（Tier B）。

為什麼需要：復華官網 /api/fund 的多期報酬（roiY2D/roi3m/roi1y…）為**月底基準**
——2026-07-15 以 git 歷史實測：NAV 天天動、YTD/3m/1y 十四天紋風不動（皆 06/30 值）。
使用者要「最新每日」的績效 → 以鉅亨基金搜尋 API 的每日更新欄位覆蓋；
鉅亨缺值時儀表板逐欄回退官網值，整層失敗則完全不影響既有流程（同 etfinfo 慣例）。

端點（正式區 CI 驗證；本 Claude 容器 proxy 擋 cnyes、只能離線測 parser）：
  GET https://fund.api.cnyes.com/fund/api/v2/search/funds?keyword=復華&page=N
回傳格式**防禦式解析**：items 位置與欄位名逐候選嘗試；解析不到時把首筆 keys
印進 stdout——CI 日誌即真實 schema，供下輪迭代（get_job_logs 可讀）。

名稱對映：以正規化名稱（去空白、統一連字號）比對官網基金名；比對結果落
data/cnyes_fund_map.json（入庫）供稽核與手動覆寫（該檔某 fund_id 若已填
cnyesId 則優先採用、不再名稱比對）。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from ..http import get_bytes

ROOT = Path(__file__).resolve().parent.parent.parent
MAP_PATH = ROOT / "data" / "cnyes_fund_map.json"

# 取數路線（CI 實測收斂史）：
#   第 1~2 輪：fund.api.cnyes.com 全路徑 404、fund.cnyes.com/api 404
#   第 3 輪：gfe-fund.cnyes.com 對任何路徑都回同一張 XHTML 舊頁（catch-all，非 API）
#   第 4 輪（本版）：**放棄猜 API，改抓搜尋頁 HTML**（fund.cnyes.com/search/ 為真實
#     存在頁）：解析頁內 __NEXT_DATA__（Next.js SSR JSON）遞迴挖「像基金」的物件；
#     找不到時把 pageProps keys／頁內 cnyes API URL 線索／App-Router flight 標記
#     印進日誌，一輪即可決定下一步（schema 微調或寫 flight 解析）
SEARCH_PAGES = (
    "https://fund.cnyes.com/search/?keyword={kw}",
    "https://fund.cnyes.com/search/?q={kw}",
)
# cnyes API 可能擋非瀏覽器 UA／缺 Referer 的請求
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": "https://fund.cnyes.com/",
    "Accept": "application/json, text/plain, */*",
}

_TW = timezone(timedelta(hours=8))

# 我方鍵 → 來源候選鍵（依序取第一個非 None；cnyes 命名不確定，寧多列勿漏）
_RET_KEYS: dict[str, tuple[str, ...]] = {
    "1w": ("return1W", "return1w", "returnWeek", "return7D", "return7d"),
    "1m": ("return1M", "return1m", "returnMonth"),
    "3m": ("return3M", "return3m"),
    "6m": ("return6M", "return6m"),
    "ytd": ("returnYTD", "returnYtd", "returnY2D", "returnThisYear"),
    "1y": ("return1Y", "return1y"),
    "2y": ("return2Y", "return2y"),
    "3y": ("return3Y", "return3y"),
}
_ID_KEYS = ("cnyesId", "cnyesID", "fundId", "fundID", "id")
_NAME_KEYS = ("displayNameLocal", "displayNameLocalWithKwd", "displayName",
              "nameLocal", "fundName", "name")
_NAV_KEYS = ("nav", "latestNav", "navPrice", "price")
_NAVDATE_KEYS = ("navDate", "navdate", "priceDate", "lastUpdate", "updateDate")
_CHG_KEYS = ("changePercent", "changePct", "navChangePercent", "change_pct")


def _pick(d: dict, keys: tuple[str, ...]):
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return None


def _num(v) -> float | None:
    """'12.34%' / '12.34' / 12.34 → 12.34；None/怪值 → None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+\.?\d*", str(v).replace(",", ""))
    return float(m.group()) if m else None


def _date(v) -> str | None:
    """epoch 秒 / 'YYYY-MM-DD' / 'YYYY/MM/DD'（含時間尾綴）→ 'YYYY/MM/DD'。"""
    if v is None:
        return None
    if isinstance(v, (int, float)) and v > 1e8:            # epoch 秒
        return datetime.fromtimestamp(int(v), tz=_TW).strftime("%Y/%m/%d")
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", str(v))
    return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}" if m else None


def _items(payload) -> list[dict]:
    """在常見包裝（items.data / items / data.data / data）裡找出第一個 dict 清單。"""
    def as_list(x):
        if isinstance(x, list) and (not x or isinstance(x[0], dict)):
            return x
        return None
    if not isinstance(payload, dict):
        return as_list(payload) or []
    for path in (("items", "data"), ("items",), ("data", "data"), ("data",)):
        node = payload
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
            if node is None:
                break
        got = as_list(node)
        if got is not None:
            return got
    return []


def norm_name(s: str | None) -> str:
    """基金名稱正規化：去空白、統一各式連字號為 '-'、全形轉半形括號。"""
    s = (s or "").strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[‐‑–—―−﹣－]", "-", s)
    return s.replace("（", "(").replace("）", ")")


_NEXT_RE = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_API_RE = re.compile(r"https://[a-z0-9.-]+\.cnyes\.com/[^\"'\\\s<>]*api[^\"'\\\s<>]*",
                     re.I)
DETAIL_PAGE = "https://fund.cnyes.com/detail/x/{cid}/"   # name 段不驗證（實測 undefined 也通）

# 報酬鍵別名（lowercase 完整鍵名 → 我方期別；第 5 輪 CI 實測搜尋頁 schema 用
# 長駝峰式 return1Month → 一併收錄長短兩式）
_RET_ALIASES = {
    "return1w": "1w", "returnweek": "1w", "return7d": "1w", "return1week": "1w",
    "return1m": "1m", "return1month": "1m",
    "return3m": "3m", "return3month": "3m",
    "return6m": "6m", "return6month": "6m",
    "returnytd": "ytd", "returny2d": "ytd", "returnthisyear": "ytd",
    "return1y": "1y", "return1year": "1y",
    "return2y": "2y", "return2year": "2y",
    "return3y": "3y", "return3year": "3y",
}


def _returns_from(item: dict) -> dict:
    out: dict[str, float] = {}
    for k, v in item.items():
        tag = _RET_ALIASES.get(str(k).lower())
        n = _num(v)
        if tag and n is not None and tag not in out:
            out[tag] = n
    return out


def _objects_from_html(html: str) -> list[dict]:
    """從任意 HTML/JS 內嵌狀態抽出含 "cnyesId" 的平衡 JSON 物件（不猜嵌入格式）。
    對每個 "cnyesId" 出現點往回逐層試 '{' 起點 raw_decode；原文與反跳脫版各試一次。
    2026-07-15 第 4 輪 CI：搜尋頁無 __NEXT_DATA__ 但 HTML 含 cnyesId×23 → 走此路。"""
    dec = json.JSONDecoder()
    for text in (html, html.replace('\\"', '"')):
        out, seen = [], set()
        for m in re.finditer(r'"cnyesId"', text):
            pos = m.start()
            for _ in range(6):                       # 由內往外最多試 6 層 '{'
                pos = text.rfind("{", 0, pos)
                if pos < 0:
                    break
                try:
                    obj, _end = dec.raw_decode(text[pos:pos + 60000])
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "cnyesId" in obj:
                    key = (str(obj.get("cnyesId")), str(_pick(obj, _NAME_KEYS)))
                    if key not in seen:
                        seen.add(key)
                        out.append(obj)
                    break
        if out:
            return out
    return []


def _walk_items(node, out: list[dict]) -> None:
    """遞迴掃 JSON：凡「有名稱鍵、且有 NAV 或任一報酬鍵」的 dict 視為基金物件。
    泛型走法不綁死 schema——items 藏在哪一層都挖得到；誤抓由名稱比對層過濾。"""
    if isinstance(node, dict):
        if (_pick(node, _NAME_KEYS) is not None
                and (_pick(node, _NAV_KEYS) is not None
                     or any(_pick(node, c) is not None for c in _RET_KEYS.values()))):
            out.append(node)
        for v in node.values():
            _walk_items(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_items(v, out)


def search_all(keyword: str = "復華", max_pages: int = 0) -> list[dict]:
    """抓搜尋頁 HTML → __NEXT_DATA__ → 遞迴挖基金物件。失敗時印足夠診斷：
    pageProps keys／頁內 cnyes API URL 線索／flight（App Router）標記／資料鍵出現次數。"""
    for tmpl in SEARCH_PAGES:
        url = tmpl.format(kw=quote(keyword))
        try:
            html = get_bytes(url, retries=1, cache_ttl=3600,
                             headers=_HEADERS).decode("utf-8-sig", errors="replace")
        except Exception as e:
            print(f"  [cnyes 頁面] ✗ {url}（{e}）")
            continue
        apis = sorted(set(_API_RE.findall(html)))[:8]
        m = _NEXT_RE.search(html)
        if not m:
            found = _objects_from_html(html)     # 第 5 輪：不猜嵌入格式、直接掃平衡物件
            if found:
                print(f"  [cnyes 頁面] ✓ {url} 平衡物件掃描挖到 {len(found)} 筆；"
                      f"首筆 keys={sorted(map(str, found[0].keys()))[:24]}")
                return found
            flight = "self.__next_f" in html
            hits = {k: html.count(k) for k in
                    ("cnyesId", "displayNameLocal", "returnYTD", "nav")}
            print(f"  [cnyes 頁面] △ {url} 無 __NEXT_DATA__、物件掃描零筆"
                  f"（flight={flight}；資料鍵出現次數={hits}；API 線索={apis}）")
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            print(f"  [cnyes 頁面] △ {url} __NEXT_DATA__ 非 JSON（{e.msg}）")
            continue
        found: list[dict] = []
        _walk_items(data, found)
        if found:
            print(f"  [cnyes 頁面] ✓ {url} 挖到 {len(found)} 筆基金物件")
            return found
        pp = ((data.get("props") or {}).get("pageProps") or {})
        print(f"  [cnyes 頁面] △ {url} 有 __NEXT_DATA__ 但無基金列；"
              f"pageProps keys={sorted(pp.keys())[:12]}；API 線索={apis}")
    return []


def fetch_detail(cid, debug: bool = False) -> dict:
    """抓基金詳情頁、抽含 cnyesId／return 鍵的物件合併成 profile（報酬在詳情頁，
    搜尋頁只有名稱/NAV——第 4 輪 CI 實測 returnYTD 於搜尋頁出現 0 次）。"""
    url = DETAIL_PAGE.format(cid=quote(str(cid)))
    try:
        html = get_bytes(url, retries=1, cache_ttl=3600,
                         headers=_HEADERS).decode("utf-8-sig", errors="replace")
    except Exception as e:
        if debug:
            print(f"  [cnyes 詳情] ✗ {url}（{e}）")
        return {}
    objs = _objects_from_html(html)
    # 也收「無 cnyesId 但含 return 鍵」的物件（績效表可能獨立存放）
    dec = json.JSONDecoder()
    for m in re.finditer(r'"return[0-9A-Za-z]{1,12}"', html):
        pos = m.start()
        for _ in range(4):
            pos = html.rfind("{", 0, pos)
            if pos < 0:
                break
            try:
                obj, _end = dec.raw_decode(html[pos:pos + 60000])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                objs.append(obj)
            break
    profile: dict = {}
    objs.sort(key=lambda o: -sum(1 for k in o if str(k).lower().startswith("return")))
    for o in objs:
        for k, v in o.items():
            if v is not None:
                profile.setdefault(k, v)
    if debug:
        retkeys = sorted({k for k in profile if str(k).lower().startswith("return")})
        navkeys = [k for k in profile if str(k).lower() in
                   ("nav", "navdate", "navprice", "pricedate", "lastupdate", "change",
                    "changepercent")]
        # 複合鍵 "returns" 內可能藏 2年/3年等期別（第 6 輪 CI 見到但未展開）——
        # 印出其結構供未來補每日 3 年值（目前 3 年回退官網月底值）
        comp = profile.get("returns")
        comp_desc = (sorted(map(str, comp.keys()))[:15] if isinstance(comp, dict)
                     else str(comp)[:120])
        print(f"  [cnyes 詳情] {url} 物件 {len(objs)} 筆；return 鍵={retkeys[:20]}；"
              f"nav 鍵={navkeys}；returns 複合鍵={comp_desc}")
    return profile


def overlay_from_item(item: dict) -> dict:
    """單筆基金物件 → 覆蓋層欄位（值可能為 None，呼叫端逐欄判斷）。"""
    rets = dict(_returns_from(item))
    for k, cands in _RET_KEYS.items():
        if k not in rets:
            v = _num(_pick(item, cands))
            if v is not None:
                rets[k] = v
    rets = {k: v for k, v in rets.items() if v is not None}
    return {
        "cnyes_id": _pick(item, _ID_KEYS),
        "cnyes_name": _pick(item, _NAME_KEYS),
        "nav": _num(_pick(item, _NAV_KEYS)),
        "nav_date": _date(_pick(item, _NAVDATE_KEYS)),
        "chg_pct": _num(_pick(item, _CHG_KEYS)),
        "returns_daily": {k: v for k, v in rets.items() if v is not None},
    }


def _load_map() -> dict:
    if not MAP_PATH.exists():
        return {}
    try:
        d = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def apply_overlay(docs: list[dict], out_dir: Path) -> int:
    """對每檔基金 doc 覆蓋鉅亨每日欄位並重寫 JSON。回傳成功覆蓋檔數。

    覆蓋規則（防清史、逐欄）：
      · returns_daily／returns_daily_asof：鉅亨有值才寫（儀表板逐欄回退官網 returns）
      · nav/nav_date/nav_change_pct：僅當鉅亨 NAV 日**較新**才覆蓋並標 nav_src="cnyes"
    """
    if not docs:
        return 0
    fmap = _load_map()
    # 搜尋頁 SSR 不吃 query（第 5 輪 CI 實測：任何 keyword 都回同 20 筆熱門清單），
    # 主要靠 data/cnyes_fund_map.json 釘選 cnyesId 直取詳情頁；搜尋頁僅供無釘選者碰運氣
    _search_cache: list[dict] | None = None

    def lazy_items() -> list[dict]:
        nonlocal _search_cache
        if _search_cache is None:
            _search_cache = search_all()
        return _search_cache

    n = 0
    dbg = True
    for doc in docs:
        fid = str(doc.get("fund_id"))
        pin = (fmap.get(fid) or {}).get("cnyesId")
        item = None
        if pin:                              # 釘選 ID → 直取詳情頁（主要路徑）
            profile = fetch_detail(pin, debug=dbg)
            dbg = False
            if profile:
                profile.setdefault("cnyesId", pin)
                item = profile
        if item is None:
            items = lazy_items()
            by_name = {norm_name(_pick(it, _NAME_KEYS)): it for it in items}
            wanted = {norm_name(doc.get("name")), norm_name(doc.get("short_name"))}
            item = next((by_name[w] for w in wanted if w in by_name), None)
            if item is not None:
                cid = _pick(item, _ID_KEYS)
                if cid is not None:          # 報酬在詳情頁（搜尋頁只有名稱/NAV/1月）
                    profile = fetch_detail(cid, debug=dbg)
                    dbg = False
                    item = {**item, **{k: v for k, v in profile.items()
                                       if v is not None}}
        if item is None:
            continue
        ov = overlay_from_item(item)
        if not ov["returns_daily"] and ov["nav"] is None:
            continue
        if ov["returns_daily"]:
            doc["returns_daily"] = ov["returns_daily"]
            doc["returns_daily_asof"] = ov["nav_date"]
        newer = (ov["nav"] is not None and ov["nav_date"] and
                 str(ov["nav_date"]) > str(doc.get("nav_date") or ""))
        if newer:
            doc["nav"], doc["nav_date"], doc["nav_src"] = ov["nav"], ov["nav_date"], "cnyes"
            if ov["chg_pct"] is not None:
                doc["nav_change_pct"] = f"{ov['chg_pct']:+.2f}%"
        old = fmap.get(fid) or {}
        fmap[fid] = {"cnyesId": ov["cnyes_id"] or old.get("cnyesId"),
                     "name": ov["cnyes_name"] or old.get("name")}
        (out_dir / f"{fid}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        n += 1
    if n:
        MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        MAP_PATH.write_text(json.dumps(fmap, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(f"  [cnyes] 每日報酬覆蓋 {n}/{len(docs)} 檔"
          + ("" if n else "（零命中——請在 data/cnyes_fund_map.json 釘 cnyesId 或看日誌診斷）"))
    return n
