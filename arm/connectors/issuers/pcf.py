"""ETF 每日持股（申購買回清單 PCF／持股明細）抓取層。

主動式 ETF 依規定每日揭露完整持股，但**沒有跨投信的統一官方端點**（2026-07-29 查證：
證交所／櫃買／政府開放平台皆無彙總 API，各投信自行在官網揭露）→ 只能一家一個 adapter。

因此本模組刻意做成「候選來源清單 + 通用解析 + 探針」三件套：

  · SOURCES  ：每檔 ETF 一組**候選** URL（依投信官網型態推導）。同一檔可列多個候選，
               依序試、第一個解析出持股就用。
  · 通用解析 ：JSON（任意巢狀陣列找持股欄）／HTML 表格／xlsx（重用 fhtrust._parse_xlsx）。
  · probe()  ：印出每個候選的 HTTP 狀態、content-type、內容前段。

**為什麼要探針**：本 Claude 容器 proxy 擋掉所有投信站（CONNECT 403），無法在此驗證任何
URL；正式區 CI 才連得上。盲寫十家 scraper 只會十家一起錯，改成「候選＋探針」後，
一次 CI 就能把實際回應收進日誌，再據以收斂各家 adapter——與 cnyesfund.py 當初
歷經 6 輪 CI 收斂的做法相同（見 CLAUDE.md）。

抓不到的檔：安靜降級（該 ETF 就沒有展開明細），絕不影響其餘欄位與其他 ETF。
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Callable

from ..fhtrust import _parse_xlsx

_TIMEOUT = 20
_UA = {"User-Agent": "Mozilla/5.0 (fuhhwa-fund-radar; etf-holdings)",
       "Accept": "application/json,text/html,*/*"}

# 股票代號：台股 4 碼數字（含 4 碼＋1 英文的特別股／KY 等）
_SID = re.compile(r"^[0-9]{4}[A-Z]?$")


class Probe:
    """單一候選來源的抓取結果＋診斷（CI 日誌用）。"""

    def __init__(self, name: str, url: str):
        self.name, self.url = name, url
        self.status: int | None = None
        self.ctype: str = ""
        self.nbytes: int = 0
        self.head: str = ""
        self.error: str = ""
        self.n_holdings: int = 0
        self.hints: list[str] = []          # SPA 外殼時，從 HTML／JS 撈出的疑似 API 端點

    def line(self) -> str:
        if self.error:
            return f"{self.name} ✗ {self.error}｜{self.url}"
        return (f"{self.name} HTTP {self.status} {self.ctype} {self.nbytes}B "
                f"→ 持股 {self.n_holdings} 檔｜{self.url}"
                + (f"｜首段：{self.head}" if not self.n_holdings else "")
                + (f"｜疑似 API：{' , '.join(self.hints)}" if self.hints else ""))


def _get(url: str, probe: Probe) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            raw = r.read()
            probe.status = getattr(r, "status", None)
            probe.ctype = (r.headers.get("Content-Type") or "").split(";")[0]
        probe.nbytes = len(raw)
        probe.head = re.sub(r"\s+", " ", raw[:400].decode("utf-8", "replace"))[:220]
        return raw
    except Exception as e:                              # noqa: BLE001 —— 每來源獨立降級
        probe.error = f"{type(e).__name__}: {str(e)[:120]}"
        return None


# ── 通用解析（三種版式；各自回 [{stock_id,name,shares,weight}]） ──────────

# 欄名關鍵字：比對方式為「候選字串是否為正規化欄名的子字串」，故短字串（代號／名稱）
# 必須列進來——各家 PCF 表頭常只寫「代號／名稱／股數／比重」（2026-07-29 測試補強）。
_KEY_ID = ("stockid", "stockno", "stockcode", "code", "id", "symbol", "ticker",
           "代號", "代碼", "商品代號", "股票代號", "證券代號")
_KEY_NM = ("stockname", "name", "名稱", "商品名稱", "股票名稱", "證券名稱")
_KEY_SH = ("shares", "share", "qty", "quantity", "amount", "股數", "數量", "庫存股數")
_KEY_WT = ("weight", "ratio", "percent", "pct", "權重", "比重", "比例")


def _norm_key(k: str) -> str:
    return re.sub(r"[\s_\-()（）%％]", "", str(k)).lower()


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return None


def _row_from_mapping(d: dict) -> dict | None:
    """任意 dict → 持股列（靠欄名關鍵字比對，容忍各家命名差異）。"""
    keys = {_norm_key(k): k for k in d}

    def pick(cands):
        for c in cands:
            for nk, orig in keys.items():
                if c in nk:
                    return d.get(orig)
        return None

    sid = str(pick(_KEY_ID) or "").strip().upper()
    if not _SID.match(sid):
        return None
    return {"stock_id": sid, "name": str(pick(_KEY_NM) or "").strip(),
            "shares": (lambda v: int(v) if v is not None else None)(_num(pick(_KEY_SH))),
            "weight": _num(pick(_KEY_WT))}


def parse_json(raw: bytes) -> list[dict]:
    """任意巢狀 JSON：遞迴找出「看起來是持股清單」的 dict 陣列，取最長的一組。"""
    try:
        doc = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return []
    best: list[dict] = []

    def walk(node):
        nonlocal best
        if isinstance(node, list):
            rows = [r for r in (_row_from_mapping(x) for x in node if isinstance(x, dict)) if r]
            if len(rows) > len(best):
                best = rows
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)

    walk(doc)
    return best


_TAG = re.compile(r"<[^>]+>")
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)


def _cells(html: str) -> list[list[str]]:
    out = []
    for tr in _TR.findall(html):
        cells = [_TAG.sub("", c).replace("&nbsp;", " ").strip() for c in _TD.findall(tr)]
        if cells:
            out.append(cells)
    return out


def _rows_from_table(rows: list[list[str]]) -> list[dict]:
    """表格列（含表頭）→ 持股列。表頭認得出欄位就用表頭，否則靠「代號欄＋數字欄」推斷。"""
    if not rows:
        return []
    header = next((r for r in rows[:5] if any(_norm_key(c) and any(
        k in _norm_key(c) for k in _KEY_ID) for c in r)), None)
    out: list[dict] = []
    if header:
        for r in rows:
            if r is header or len(r) != len(header):
                continue
            got = _row_from_mapping(dict(zip(header, r)))
            if got:
                out.append(got)
        if out:
            return out
    # 無可辨識表頭：找出代號欄位置，名稱取其右、股數取最大整數欄、權重取 0–100 的小數欄
    for r in rows:
        idx = next((i for i, c in enumerate(r) if _SID.match(c.strip().upper())), None)
        if idx is None:
            continue
        # 只看代號欄「右側」的數字：左側常是序號欄，1、2、3… 會被誤判成權重（實測踩到）
        nums = [(i, _num(c)) for i, c in enumerate(r) if i > idx and _num(c) is not None]
        shares = max((v for _i, v in nums if v is not None and v >= 1000), default=None)
        weight = next((v for _i, v in nums if v is not None and 0 < v <= 100), None)
        out.append({"stock_id": r[idx].strip().upper(),
                    "name": (r[idx + 1].strip() if len(r) > idx + 1 else ""),
                    "shares": int(shares) if shares is not None else None,
                    "weight": weight})
    return out


def parse_html(raw: bytes) -> list[dict]:
    for enc in ("utf-8", "big5"):
        try:
            return _rows_from_table(_cells(raw.decode(enc)))
        except UnicodeDecodeError:
            continue
    return []


def parse_xlsx(raw: bytes) -> list[dict]:
    try:
        return _rows_from_table(_parse_xlsx(raw))
    except Exception:
        return []


def parse_embedded_json(raw: bytes) -> list[dict]:
    """從 HTML／內嵌 JS 的狀態物件抽持股（**不猜嵌入格式**，平衡物件掃描）。

    2026-07-29 第 2 輪 CI 的關鍵發現：元大 `tradeInfo/pcf/{code}` 回的是 **1.07 MB HTML**
    （不是空殼），但表格解析 0 檔 —— 資料是內嵌在 script 裡的 JSON，不是 `<table>`。
    這與 cnyesfund 當初「頁面無 __NEXT_DATA__、狀態以他形內嵌」完全同型，故沿用同一招：
    對每個「看起來像持股代號欄」的鍵出現點，往回逐層試 `{` 起點 raw_decode，
    原文與反跳脫版（JSON-in-JSON）各試一次。

    只認**帶權重或股數**的物件（沒有數量資訊算不出貢獻，且正是導覽連結的長相）。
    """
    try:
        html = raw.decode("utf-8", "replace")
    except Exception:
        return []
    dec = json.JSONDecoder()
    # 鍵名先粗篩：頁面必須真的出現「像持股欄」的鍵，否則整份掃描純浪費
    # 錨點鍵名放寬（2026-07-29 第 3 輪：元大頁面 stockNo/stockId/stockCode 全 0 次，
    # 代號欄顯然叫別的名字）。寧可多掃幾個起點——_row_from_mapping 與 is_plausible 會過濾誤抓。
    anchor = re.compile(
        r'"(?:[Ss]tock(?:No|Id|Code|Symbol)|secId|secNo|symbol|ticker|code|id)"\s*:'
        r'|"(?:商品代號|股票代號|證券代號|代號)"')
    for text in (html, html.replace('\\"', '"')):
        out, seen = [], set()
        for m in anchor.finditer(text):
            pos = m.start()
            for _ in range(6):                        # 由內往外最多試 6 層 '{'
                pos = text.rfind("{", 0, pos)
                if pos < 0:
                    break
                try:
                    obj, _end = dec.raw_decode(text[pos:pos + 60000])
                except json.JSONDecodeError:
                    continue
                row = _row_from_mapping(obj) if isinstance(obj, dict) else None
                if row and (row["weight"] is not None or row["shares"] is not None):
                    if row["stock_id"] not in seen:
                        seen.add(row["stock_id"])
                        out.append(row)
                break
        if out:
            return out
    return []


def parse_auto(raw: bytes, probe: Probe) -> list[dict]:
    """依 content-type／位元組特徵選解析器（各家常改格式 → 全部試一遍取最長）。"""
    cands: list[Callable[[bytes], list[dict]]] = []
    if raw[:2] == b"PK":                                  # xlsx/zip 魔數
        cands = [parse_xlsx]
    elif "json" in probe.ctype or raw.lstrip()[:1] in (b"{", b"["):
        cands = [parse_json, parse_html, parse_embedded_json]
    else:
        # HTML：先試表格，再試「內嵌 JSON 狀態」——元大等站是後者（1MB HTML、資料在 script 裡）
        cands = [parse_html, parse_embedded_json, parse_json]
    best: list[dict] = []
    for fn in cands:
        got = fn(raw)
        if len(got) > len(best):
            best = got
    return best


# 詞界很重要：舊版無界的 "api" 會匹配到 c-api-tal（群益 capitalfund），
# 讓整排 hint 都是無用的導覽連結（2026-07-29 第 2 輪 CI 實測）。
_API_HINT = re.compile(
    r"""["'(]((?:https?://[\w.\-]+)?/[\w./\-]*(?:\bapi\b|/api/|pcf|holding|constituent|"""
    r"""component|portfolio|fundData|etfData)[\w./\-]*(?:\.json|\.ashx|\.aspx)?)["')]""", re.I)
_HINT_SKIP = re.compile(r"\.(js|css|png|jpg|svg|woff2?|ico)$", re.I)


def _api_hints(raw: bytes, limit: int = 6) -> list[str]:
    """SPA 外殼（持股由 JS 動態載入）時，從 HTML／內嵌 JS 撈出疑似資料端點。

    2026-07-29 首輪 CI：野村 500、統一 302 迴圈，群益／安聯／證交所 ETFortune 全回
    Angular 類 SPA 外殼 —— 靜態 HTML 裡沒有持股，真正的清單在 XHR 後面。與其一輪只換
    一個猜測網址，不如讓探針把頁面裡的候選端點直接列進 CI 日誌，一輪就能收斂。"""
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:
        return []
    seen, out = set(), []
    for m in _API_HINT.finditer(text):
        u = m.group(1)
        if u in seen or _HINT_SKIP.search(u) or len(u) > 120:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit:
            break
    return out


_PROBE_KEYS = ("stockNo", "stockId", "stockCode", "stockName", "shares",
               "商品代號", "股票代號", "證券代號", "股數", "權重", "比重", "成分股", "持股")
# 資料錨字：出現在「真的有持股資料」附近的中文詞。用來抓上下文片段（見 _key_hits）。
_ANCHOR_WORDS = ("成分股", "權重", "股數", "證券代號", "股票代號", "比重")
_FONT_WEIGHT = re.compile(r"font-weight", re.I)


_SCRIPT_SRC = re.compile(r"""<script[^>]+src=["']([^"']+)["']""", re.I)
_BUNDLE_HINT = re.compile(r"(main|app|runtime|vendor|chunk|index)[.\-][\w.\-]*\.js$", re.I)
# bundle 內的 API 路徑字面值：以引號包住、含 /api/ 或持股相關字樣的路徑
_BUNDLE_API = re.compile(
    r"""["'`](/(?:[\w.\-]+/)*(?:api|pcf|holding|constituent|component|portfolio)"""
    r"""[\w./\-{}$]*)["'`]""", re.I)
_bundle_cache: dict[str, list[str]] = {}   # host → 掃出的 API 路徑（每 run 每站只掃一次）
_bundle_log: dict[str, list[str]] = {}     # host → bundle 抓取診斷（與路徑分開存，見下）


def _bundle_api_hints(raw: bytes, page_url: str, max_bundles: int = 6) -> list[str]:
    """從 SPA 的 **JS bundle** 撈真正的資料端點。

    2026-07-29 第 4 輪 CI 定案：元大／群益的 HTML 裡「成分股」「證券代號」全是文案與公告內文，
    **持股資料不在頁面裡、全靠 XHR** —— 掃 HTML 這條路是死路。但 SPA 呼叫的 API 路徑
    一定寫在它的 JS bundle 裡，所以改抓 bundle 再找路徑字面值。

    節流：每個站台（host）每次執行只掃一次、最多 3 支 bundle —— 23 檔 ETF 若逐檔重掃，
    會對投信站發出上百個不必要的請求。"""
    from urllib.parse import urljoin, urlparse
    host = urlparse(page_url).netloc
    if host in _bundle_cache:
        return _bundle_cache[host]
    _bundle_log[host] = []
    try:
        html = raw.decode("utf-8", "replace")
    except Exception:
        return []
    all_srcs = [urljoin(page_url, s) for s in _SCRIPT_SRC.findall(html)]
    srcs = [s for s in all_srcs if _BUNDLE_HINT.search(s)] or \
           [s for s in all_srcs if ".js" in s]                # 命名不合慣例時退回全部 .js
    found: list[str] = []
    log: list[str] = []
    if not all_srcs:
        log.append("頁面無 <script src>（bundle 內聯或由 loader 動態插入）")
    log.append(f"頁面 script 共 {len(all_srcs)} 支："
               + ", ".join(s.rsplit("/", 1)[-1] for s in all_srcs[:12]))
    for src in srcs[:max_bundles]:
        p = Probe("bundle", src)
        js = _get(src, p)
        if not js:
            log.append(f"{src.rsplit('/', 1)[-1]}✗{p.error[:40]}")
            continue
        # SPA 的 catch-all 路由會把 index.html 原封回給任何路徑——位元組數與頁面相同、
        # 內容是 <!doctype html>。當成 JS 掃只會得到 +0，而且看不出原因
        #（2026-07-29 第 6 輪：群益 424450B、安聯 9437B 的「bundle」都與頁面同大小）。
        if js[:200].lstrip()[:1] == b"<" or len(js) == len(raw):
            log.append(f"{src.rsplit('/', 1)[-1]} 回 HTML 外殼（catch-all 路由，非真 bundle）")
            continue
        text = js.decode("utf-8", "replace")
        n0 = len(found)
        for m in _BUNDLE_API.finditer(text):
            u = m.group(1)
            if u not in found and len(u) <= 120:
                found.append(u)
                # 呼叫脈絡：端點字面值前後的程式碼，看得出 method 與 body 參數名
                # （元大掃到 /api/bridge 這種通用閘道時，光有路徑還打不出正確請求）
                if len(found) <= 3:
                    i = m.start()
                    frag = re.sub(r"\s+", " ", text[max(0, i - 160): i + 200])
                    log.append(f"呼叫脈絡[{u}]：{frag}")
            if len(found) >= 8:
                break
        log.append(f"{src.rsplit('/', 1)[-1]} {len(js)}B → +{len(found) - n0} 路徑")
        if len(found) >= 8:
            break
    # 路徑與診斷**分開存**：診斷字串若混進路徑清單，日後把路徑餵進 _cands() 就會炸
    #（且診斷片段裡本來就可能含 .png 之類的無關字串，混在一起連測試都難寫）
    _bundle_cache[host] = found
    _bundle_log[host] = [f"〔bundle 診斷〕{' ｜ '.join(log)}"] if log else []
    return found


def _key_hits(raw: bytes, min_bytes: int = 100_000, ctx: int = 260) -> list[str]:
    """大頁面卻一列都沒解析出來時的定位診斷。

    第 3 輪 CI 的教訓：只印「鍵名命中次數」還不夠決斷 —— 元大回
    `{'weight': 191, '成分股': 63, '權重': 59, ...}` 但 stockNo/stockId/stockCode **全 0**，
    只知道「代號欄叫別的名字」，再猜一輪還是猜。而且 `weight` 那 191 次多半是 CSS 的
    `font-weight`（假訊號，已扣除）。

    因此除了次數，**直接印出資料錨字附近的原始片段** —— 一輪就能看出到底是
    HTML 表格、內嵌 JSON、還是只有樣板文字（資料在 XHR）。小頁面不做（純噪音）。
    """
    if len(raw) < min_bytes:
        return []
    text = raw.decode("utf-8", "replace")
    hits = {k: text.count(k) for k in _PROBE_KEYS}
    hits["weight"] = text.count("weight") - len(_FONT_WEIGHT.findall(text))   # 扣掉 CSS 假訊號
    hits = {k: v for k, v in hits.items() if v > 0}
    out = [f"鍵名命中={hits or '全無（判為 SPA 外殼、資料在 XHR）'}"]
    # 命中最多的錨字取其最後一次出現（樣板通常在前段、資料在後段）的上下文
    best = max((w for w in _ANCHOR_WORDS if w in text),
               key=lambda w: text.count(w), default=None)
    if best:
        i = text.rfind(best)
        frag = re.sub(r"\s+", " ", text[max(0, i - ctx // 2): i + ctx // 2])
        out.append(f"「{best}」末次上下文：{frag}")
    return out


# ── 候選來源清單（依投信官網型態推導；由 CI 探針逐檔證實後收斂） ─────────
#
# 已證實可用的網址型態：
#   · 元大 www.yuantaetfs.com/tradeInfo/pcf/{code}         （2026-07-29 WebSearch 逐檔命中）
#   · 復華 www.fhtrust.com.tw/api/assetsExcel/{id}/{ymd}   （既有基金持股同一站，ETF 代碼待證）
# 其餘為同型態推導的候選，探針證實前一律當「未知」——抓不到就沒有展開明細，不影響其他欄位。
def _cands(code: str, issuer: str) -> list[tuple[str, str]]:
    """回 [(來源名, URL)]，依序嘗試。"""
    out: list[tuple[str, str]] = []
    if issuer == "元大":
        out.append(("元大PCF", f"https://www.yuantaetfs.com/tradeInfo/pcf/{code}"))
        out.append(("元大PCF-api", f"https://www.yuantaetfs.com/api/pcf/{code}"))
    elif issuer == "復華":
        out.append(("復華PCF", f"https://www.fhtrust.com.tw/ETF/PCF/{code}"))
        out.append(("復華ETF頁", f"https://www.fhtrust.com.tw/etf/{code}/holdings"))
    elif issuer == "國泰":
        out.append(("國泰PCF", f"https://www.cathaysite.com.tw/ETF/purchase?code={code}"))
    elif issuer == "富邦":
        out.append(("富邦PCF", f"https://websys.fsit.com.tw/FubonETF/Trade/Pcf.aspx?fundid={code}"))
    elif issuer == "群益":
        out.append(("群益PCF", f"https://www.capitalfund.com.tw/ETF/PCF/{code}"))
    elif issuer == "統一":
        out.append(("統一PCF", f"https://www.ezmoney.com.tw/ETF/PCF/{code}"))
    elif issuer == "野村":
        out.append(("野村PCF", f"https://www.nomurafunds.com.tw/ETF/PCF/{code}"))
    elif issuer == "安聯":
        out.append(("安聯PCF", f"https://etf.allianzgi.com.tw/api/pcf/{code}"))
    elif issuer == "中信":
        out.append(("中信PCF", f"https://www.ctbcinvestments.com.tw/ETF/PCF/{code}"))
    elif issuer == "台新":
        out.append(("台新PCF", f"https://www.tsit.com.tw/ETF/PCF/{code}"))
    elif issuer == "第一金":
        out.append(("第一金PCF", f"https://www.fsitc.com.tw/ETF/PCF/{code}"))
    elif issuer == "凱基":
        out.append(("凱基PCF", f"https://www.kgifsitc.com.tw/ETF/PCF/{code}"))
    # 全檔通用候選：證交所官方 ETF 資訊頁（若含成分股即為最佳來源——跨投信統一、Tier A）
    out.append(("證交所ETFortune", f"https://www.twse.com.tw/zh/ETFortune/etfInfo/{code}"))
    return out


_MIN_HOLDINGS = 10        # 有效持股清單的最少檔數（主動股票 ETF 動輒 30–50 檔）


def is_plausible(rows: list[dict]) -> bool:
    """這份清單真的是「持股」嗎？—— 2026-07-29 首輪 CI 踩到的假陽性防呆。

    當時證交所 ETFortune 是 SPA 外殼，通用解析從頁面上的**其他 ETF 推薦連結**
    刮到 `0050 元大台灣50／0056 元大高股息／0052 富邦科技`，權重與股數全 None，
    卻仍通過舊的「≥5 列」門檻，讓兩檔 ETF 上線了完全錯誤的展開明細。三道驗證：

      ① 檔數 ≥ _MIN_HOLDINGS（推薦連結、導覽列這類雜訊通常只有個位數）。
      ② **過半列必須帶權重或股數** —— 沒有數量資訊就算不出貢獻，本來就不能用。
      ③ 不可「整份都是 ETF 代碼」（台股 ETF 代碼以 0 開頭、個股不會）——
         這正是推薦連結清單的長相。只排除「全部」而非「任一」，才不會誤殺
         真的持有其他 ETF 的組合型基金。
    """
    return not implausible_reason(rows)


def implausible_reason(rows: list[dict]) -> str:
    """回「不像持股清單」的具體理由；通過則回 ""。

    2026-07-29 瀏覽器首跑：復華攔到 **30 檔**的 XHR、元大 6 檔，卻只看得到「未通過持股驗證」
    —— 不知道是被哪一條擋、那些列長什麼樣，就沒辦法判斷「該放寬規則」還是「該換來源」。
    把理由與樣本列進日誌，一輪就能決斷。"""
    n = len(rows)
    if n < _MIN_HOLDINGS:
        return f"僅 {n} 檔（門檻 {_MIN_HOLDINGS}）"
    with_qty = sum(1 for r in rows if r.get("weight") is not None or r.get("shares") is not None)
    if with_qty * 2 < n:
        return f"{n} 檔中僅 {with_qty} 檔帶權重／股數（過半才算持股清單）"
    if all(str(r.get("stock_id", "")).startswith("0") for r in rows):
        return f"{n} 檔全為 0 開頭的 ETF 代碼（導覽／推薦清單的長相）"
    return ""


def sample_rows(rows: list[dict], k: int = 4) -> str:
    """列出前 k 筆的代號/名稱/權重/股數，供 CI 日誌判讀來源對不對。"""
    return " ; ".join(
        f"{r.get('stock_id')}{r.get('name') or ''}"
        f"(w={r.get('weight')},s={r.get('shares')})" for r in rows[:k])


def fetch_one(code: str, issuer: str) -> tuple[list[dict], str, list[Probe]]:
    """單檔 ETF：依序試候選來源，回 (持股列, 來源名, 全部探針)。"""
    probes: list[Probe] = []
    for name, url in _cands(code, issuer):
        p = Probe(name, url)
        probes.append(p)
        raw = _get(url, p)
        if not raw:
            continue
        rows = _normalize(parse_auto(raw, p))
        p.n_holdings = len(rows)
        if is_plausible(rows):
            return rows, name, probes
        if rows:
            p.head = (f"[判為非持股清單：{len(rows)} 檔、"
                      f"帶量 {sum(1 for r in rows if r.get('weight') is not None or r.get('shares') is not None)} 檔] "
                      + ", ".join(f"{r['stock_id']}{r.get('name') or ''}" for r in rows[:6]))
            p.n_holdings = 0                      # 不算命中，讓 line() 印出上面的判定說明
        else:
            # 一列都沒解析出來 → 兩種可能，日誌要分得出來：
            #   ①真的是 SPA 外殼（資料在 XHR）→ 列出疑似端點
            #   ②資料其實內嵌在頁面裡、只是鍵名和我猜的不同 → 列出鍵名命中次數
            # 第 4 輪定案：HTML 裡的「成分股／證券代號」都是文案與公告內文，資料全靠 XHR
            # → 主力改成掃 JS bundle 找真正的 API 路徑；鍵名／上下文診斷退為輔助。
            from urllib.parse import urlparse
            bundle = _bundle_api_hints(raw, url)
            p.hints = ([f"bundle API：{' , '.join(bundle)}"] if bundle else []) \
                + _bundle_log.get(urlparse(url).netloc, []) \
                + _api_hints(raw) + _key_hits(raw)
    return [], "", probes


def _normalize(rows: list[dict]) -> list[dict]:
    """同代號合併、權重補算（僅有股數時不硬算價值權重——缺價格資料，寧缺勿錯）。"""
    merged: dict[str, dict] = {}
    for r in rows:
        sid = r["stock_id"]
        cur = merged.setdefault(sid, {"stock_id": sid, "name": r.get("name") or "",
                                      "shares": None, "weight": None})
        for k in ("shares", "weight"):
            if r.get(k) is not None:
                cur[k] = (cur[k] or 0) + r[k] if cur[k] is not None else r[k]
        if r.get("name") and not cur["name"]:
            cur["name"] = r["name"]
    return sorted(merged.values(), key=lambda h: -(h.get("weight") or 0))
