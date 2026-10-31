"""個股報告的官方文件包（docs/lab_eq_docs_plan.md）。

2026-10-30 使用者看到排程回報「三家都沒讀到公司法說會簡報或觀測站原文」：「這不應該發生吧？」。容器擋觀測站，
所以由 CI 抓（scripts/fetch_eqdocs.py，eq_docs.yml）：公開資訊觀測站的公司基本資料、法說會（最近一場簡報逐頁文字）、
近 6 個月重大訊息（內文）、股東會年報「營運概況」整章。全文只放在臨時分支、報告寫完就刪（使用者選「不存」）；
報告旁的 .facts.json 只記文件清單（index()）。送出、等待、讀、刪：scripts/eq_docs_req.py。

這裡只有解析與組裝（不連網）；抓網頁的函式由呼叫的人傳進來（post(url, form)→str、get(url)→bytes），測試用存下來的樣本。"""
from __future__ import annotations

import html as H
import io
import re
import time
from collections import Counter
from datetime import date, timedelta

VER = 1
OV = "https://mopsov.twse.com.tw"
DOC = "https://doc.twse.com.tw"
DECK_DAYS = 365          # 最近一場法說會在 12 個月內才讀簡報
CONF_DAYS = 730          # 法說會清單列近 24 個月
NEWS_DAYS = 183          # 重大訊息近 6 個月
NEWS_MAX = 40            # 內文最多抓幾則（從新到舊）
IMG_MIN = 30             # 一頁抽不到 30 個字＝那一頁是圖
ANNUAL_MAX = 25          # 年報營運概況最多幾頁
CODE_RE = re.compile(r"^tw:\d{4}$")
ID_RE = re.compile(r"^\d{8}-\d{4}-[0-9a-f]{6}$")
TMP_PREFIX = "claude/eqdocs-tmp/"

_TAG = re.compile(r"<[^>]+>")
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_ROC = re.compile(r"(\d{2,3})/(\d{1,2})/(\d{1,2})")
_CHAP = re.compile(r"[壹貳參肆伍陸柒捌玖拾]\s*、")
_EMP = re.compile(r"三\s*、\s*(?:最近二年度)?[^、。]{0,24}?從業員工")


def clean(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = H.unescape(_TAG.sub(" ", s)).replace("\xa0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def one_line(s: str) -> str:
    """觀測站主旨會在中文中間斷行（「…辦理 \n變更登記完成」）：中文兩邊直接接起來，英文之間留一個空白。"""
    s = re.sub(r"(?<=[^\x00-\x7f])[ \t]*\n\s*|[ \t]*\n\s*(?=[^\x00-\x7f])", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def roc_date(s: str) -> str | None:
    """'115/09/17'、'1150917'、'2026-09-17' → '2026-09-17'。"""
    s = (s or "").strip()
    m = _ROC.search(s) or re.fullmatch(r"(\d{3})(\d{2})(\d{2})", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.search(r"(20\d\d)[-/](\d{1,2})[-/](\d{1,2})", s)
        if not m:
            return None
        y, mo, d = (int(x) for x in m.groups())
    if y < 1911:
        y += 1911
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def rows(html: str) -> list[tuple[str, list[str]]]:
    """表格每一列 → (原始 HTML, [格子文字])。"""
    return [(tr, [clean(c) for c in _TD.findall(tr)]) for tr in _TR.findall(html or "")]


# ── 公司基本資料（觀測站 t05st03）─────────────────────────────────────────

BASIC = {"產業類別": "ind", "公司名稱": "full", "董事長": "chair", "總經理": "ceo", "發言人": "spoke", "發言人職稱": "spoke_t",
         "主要經營業務": "biz", "公司成立日期": "founded", "上市日期": "listed", "上櫃日期": "otc", "興櫃日期": "emg",
         "公司網址": "site", "實收資本額": "capital"}


def parse_basic(html: str) -> dict:
    cells = [c for _, cs in rows(html) for c in cs]
    out: dict = {}
    for i, c in enumerate(cells[:-1]):
        k = BASIC.get(c)
        if k and k not in out and cells[i + 1] and cells[i + 1] not in BASIC:
            out[k] = cells[i + 1]
    for k in ("founded", "listed", "otc", "emg"):
        if k in out:
            out[k] = roc_date(out[k]) or out[k]
    m = re.search(r"本資料由\s*\((上市|上櫃|興櫃|公開發行)公司\)", clean(html))
    if m:
        out["board"] = m.group(1)
    if out.get("site"):                                   # 有的公司只填「www.xxx.com.tw」→ 補 http://
        m = re.search(r"https?://[^\s<>\"']+", out["site"]) or re.search(r"\b[\w-]+(?:\.[\w-]+)+(?:/[^\s<>\"']*)?", out["site"])
        out["site"] = (m.group(0) if m.group(0).startswith("http") else "http://" + m.group(0)) if m else None
    return out


# ── 法說會（觀測站 t100sb02_1：依代號、年度列出全部場次）────────────────────

def parse_confs(html: str, code: str) -> list[dict]:
    out = []
    for tr, cs in rows(html):
        if len(cs) < 6 or cs[0] != code:
            continue
        d = next((roc_date(c) for c in cs[2:4] if roc_date(c)), None)
        if not d:
            continue
        zh = re.findall(rf"({code}\d{{8}}M\d{{3}}\.pdf)", tr)
        en = re.findall(rf"({code}\d{{8}}E\d{{3}}\.pdf)", tr)
        tds = _TD.findall(tr)                             # 第 10 格＝影音連結資訊（證交所或公司自己的影音站）
        vid = re.findall(r"https?://[^\s<>\"']+", tds[9] if len(tds) > 9 else "") or \
            re.findall(r"https?://irconference\.twse\.com\.tw/[^\s<>\"']+", tr, re.I)
        t = next((c for c in cs if re.fullmatch(r"\d{1,2}:\d{2}", c)), "")
        ix = cs.index(t) if t else 3
        out.append({"d": d, "t": t, "where": one_line(cs[ix + 1]) if ix + 1 < len(cs) else "",
                    "note": one_line(cs[ix + 2]) if ix + 2 < len(cs) else "",
                    "pdf": f"{OV}/nas/STR/{zh[0]}" if zh else None, "pdf_en": f"{OV}/nas/STR/{en[0]}" if en else None,
                    "video": vid[0] if vid else None})
    seen, uniq = set(), []
    for c in sorted(out, key=lambda x: (x["d"], x["pdf"] or "")):
        key = (c["d"], c["pdf"])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


# ── 重大訊息（觀測站 t05st01）────────────────────────────────────────────

_ONCLICK = re.compile(r"""onclick\s*=\s*(?:'([^']*)'|"([^"]*)")""", re.I)
_ASSIGN = re.compile(r"""\.(\w+)\.value\s*=\s*(?:"([^"]*)"|'([^']*)'|([\w./:-]+))""")


def parse_news_list(html: str, code: str) -> list[dict]:
    """→ [{d, t, subj, form}]；form＝「詳細資料」按鈕帶的欄位（拿來查內文）。"""
    out = []
    for tr, cs in rows(html):
        if code not in cs:
            continue
        d = next((roc_date(c) for c in cs if _ROC.fullmatch(c.strip())), None)
        if not d:
            continue
        t = next((c for c in cs if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", c)), "")
        subj = one_line(max((c for c in cs if c not in (code, t) and not _ROC.fullmatch(c.strip()) and c != "詳細資料"),
                            key=len, default=""))
        form = {}
        for m in _ONCLICK.finditer(tr):
            js = H.unescape(m.group(1) or m.group(2) or "")
            for a in _ASSIGN.finditer(js):
                form[a.group(1)] = next(x for x in a.groups()[1:] if x is not None)
        out.append({"d": d, "t": t, "subj": subj, "form": form})
    return out


def parse_news_detail(html: str) -> str:
    cells = [c for _, cs in rows(html) for c in cs]
    for i, c in enumerate(cells[:-1]):
        if c in ("說明", "說 明"):
            return cells[i + 1]
    pre = re.findall(r"<pre[^>]*>(.*?)</pre>", html or "", re.S | re.I)
    return clean(pre[-1]) if pre else ""


# ── 股東會年報（doc.twse 電子書）──────────────────────────────────────────

def parse_annual_list(html: str) -> list[str]:
    """清單頁 → 年報檔名（F04＝中文年報；先列最新的）。"""
    fs = re.findall(r"readfile2\(\s*['\"]F['\"]\s*,\s*['\"]\w+['\"]\s*,\s*['\"]([^'\"]+F04\.pdf)['\"]", html or "")
    return sorted(set(fs), reverse=True)


def parse_step9(html: str) -> str | None:
    m = re.search(r"""href\s*=\s*['"]([^'"]+\.pdf)['"]""", html or "", re.I)
    if not m:
        return None
    u = m.group(1)
    return u if u.startswith("http") else DOC + (u if u.startswith("/") else "/" + u)


# ── PDF ────────────────────────────────────────────────────────────────────

def pdf_pages(b: bytes) -> list[str]:
    """PDF → 每頁文字。每頁都出現的字（範本、頁首頁尾）拿掉；一頁抽不到字就回空字串。"""
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(b))
    raw = []
    for pg in r.pages:
        try:
            raw.append([ln.strip() for ln in (pg.extract_text() or "").splitlines() if ln.strip()])
        except Exception:                                 # noqa: BLE001
            raw.append([])
    return drop_template(raw)


def drop_template(pages: list[list[str]]) -> list[str]:
    n = len(pages)
    cnt = Counter(ln for p in pages for ln in set(p))
    rep = {ln for ln, k in cnt.items() if n >= 4 and k >= max(3, n * 0.5) and not re.fullmatch(r"\d{1,3}", ln)}
    out = []
    for p in pages:
        t = " ".join(ln for ln in p if ln not in rep)
        out.append(re.sub(r"\s+", " ", t).strip())
    return out


def annual_section(pages: list[str]) -> list[tuple[int, str]]:
    """年報 → 「營運概況」的「一、業務內容」「二、市場及產銷概況」[(頁碼, 文字)]：從章名那頁到「三、（最近二年度）從業員工」
    之前（後面的員工、環保、勞資、資安、重要契約不收）；沒有那個小標就到下一章「財務概況」前一頁。最多 ANNUAL_MAX 頁。
    目錄頁（一頁出現好幾個「X、」章名）跳過；找不到章名就用有「營業比重」的那頁前後。"""
    def chap_page(i, word):
        t = pages[i]
        return (re.search(rf"[壹貳參肆伍陸柒捌玖拾]\s*、\s*{word}", t) and len(_CHAP.findall(t)) <= 2)
    start = next((i for i in range(3, len(pages)) if chap_page(i, "營運概況") and re.search(r"業務內容|業務範圍", pages[i])), None)
    if start is None:
        hit = next((i for i in range(3, len(pages)) if "營業比重" in pages[i]), None)
        if hit is None:
            return []
        return [(i + 1, pages[i]) for i in range(max(0, hit - 1), min(len(pages), hit + 6)) if pages[i]]
    end = next((j for j in range(start + 1, len(pages)) if chap_page(j, "財務(概況|狀況)")), len(pages))
    out = [(i + 1, pages[i]) for i in range(start, min(end, start + ANNUAL_MAX)) if pages[i]]
    for k, (pg, t) in enumerate(out):
        m = _EMP.search(t)
        if m:
            head = t[:m.start()].strip()
            return out[:k] + ([(pg, head)] if head else [])
    return out


# ── 組裝 ───────────────────────────────────────────────────────────────────

def roc(y: int) -> int:
    return y - 1911


def build(code: str, today: date, post, get, log=print, pause: float = 0.8) -> dict:
    """抓一家（台股）。post(ep, form)→str 打觀測站 ajax；get(url)→bytes。每一段各自 try，失敗寫進 st。"""
    pk: dict = {"v": VER, "mk": "tw", "code": code, "made": today.isoformat(), "st": {}, "basic": {}, "confs": [],
                "deck": None, "news": [], "annual": None}

    def sec(name, fn):
        try:
            fn()
        except Exception as ex:                           # noqa: BLE001
            pk["st"][name] = f"err: {type(ex).__name__}: {str(ex)[:160]}"
            log(f"[eqdocs] {code} {name} ✗ {pk['st'][name]}")

    def basic():
        h = post("t05st03", {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "queryName": "co_id",
                             "inpuType": "co_id", "TYPEK": "all", "co_id": code})
        pk["basic"] = parse_basic(h)
        pk["name"] = pk["basic"].get("full")
        pk["st"]["basic"] = "ok" if pk["basic"].get("biz") else "err: 沒有主要經營業務"

    def confs():
        cs = []
        for y in (today.year, today.year - 1):
            cs += parse_confs(post("t100sb02_1", {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1,
                                                   "TYPEK": "all", "co_id": code, "year": roc(y)}), code)
            time.sleep(pause)
        lo = (today - timedelta(days=CONF_DAYS)).isoformat()
        pk["confs"] = sorted({(c["d"], c["pdf"]): c for c in cs if c["d"] >= lo}.values(), key=lambda c: c["d"])
        pk["st"]["confs"] = "ok" if pk["confs"] else "none"

    def deck():
        lo = (today - timedelta(days=DECK_DAYS)).isoformat()
        last = next((c for c in reversed(pk["confs"]) if c["pdf"] and lo <= c["d"] <= today.isoformat()), None)
        if not last:
            pk["st"]["deck"] = "none"
            return
        pages = pdf_pages(get(last["pdf"]))
        pk["deck"] = {"d": last["d"], "url": last["pdf"], "pages": pages, "img": [i + 1 for i, t in enumerate(pages) if len(t) < IMG_MIN]}
        pk["st"]["deck"] = "ok"

    def news():
        lo = (today - timedelta(days=NEWS_DAYS)).isoformat()
        items = []
        for y in sorted({today.year, (today - timedelta(days=NEWS_DAYS)).year}, reverse=True):
            items += parse_news_list(post("t05st01", {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "keyword4": "",
                                                       "code1": "", "TYPEK2": "", "checkbtn": "", "queryName": "co_id",
                                                       "inpuType": "co_id", "TYPEK": "all", "co_id": code, "year": roc(y),
                                                       "month": "", "b_date": "", "e_date": ""}), code)
            time.sleep(pause)
        items = sorted((x for x in items if lo <= x["d"] <= today.isoformat()), key=lambda x: (x["d"], x["t"]), reverse=True)
        bad = 0
        for k, x in enumerate(items):
            body = ""
            if k < NEWS_MAX and x["form"]:
                f = {"encodeURIComponent": 1, "firstin": "true", "off": 1, "step": 2, "TYPEK": "all", "co_id": code,
                     "year": roc(int(x["d"][:4])), "month": "all", "e_month": "all", "b_date": "", "e_date": "", "type": "",
                     "MEETING_STEP": "", "MODEL": "", "ITEM": "", **x["form"]}
                try:
                    body = parse_news_detail(post("t05st01", f))
                except Exception as ex:                   # noqa: BLE001
                    bad += 1
                    log(f"[eqdocs] {code} 重大訊息內文 ✗ {x['d']} {str(ex)[:120]}")
                time.sleep(pause)
            pk["news"].append({"d": x["d"], "t": x["t"], "subj": x["subj"], "body": body})
        pk["st"]["news"] = ("ok" if pk["news"] else "none") + (f"（{bad} 則內文沒抓到）" if bad else "")

    def annual():
        for y in (today.year, today.year - 1):
            url = f"{DOC}/server-java/t57sb01?step=1&colorchg=1&co_id={code}&year={roc(y)}&mtype=F&"
            fs = parse_annual_list(_dec(get(url)))
            if fs:
                break
            time.sleep(pause)
        else:
            pk["st"]["annual"] = "none"
            return
        fn = fs[0]
        p9 = parse_step9(_dec(get(f"{DOC}/server-java/t57sb01?step=9&kind=F&co_id={code}&filename={fn}")))
        if not p9:
            raise RuntimeError(f"年報 {fn} 拿不到下載連結")
        pages = pdf_pages(get(p9))
        sec_pages = annual_section(pages)
        m = re.match(r"(\d{4})_", fn)
        pk["annual"] = {"fy": int(m.group(1)) if m else None, "file": fn, "url": url, "pp": len(pages), "pages": sec_pages}
        pk["st"]["annual"] = "ok" if sec_pages else "err: 年報找不到營運概況"

    for name, fn in (("basic", basic), ("confs", confs), ("deck", deck), ("news", news), ("annual", annual)):
        sec(name, fn)
    pk["ok"] = all(not str(v).startswith("err") for v in pk["st"].values())
    return pk


def _dec(b: bytes) -> str:
    for enc in ("utf-8", "cp950", "big5"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def index(pk: dict) -> dict:
    """給 .facts.json 的文件清單（不含全文）：每份文件的日期、標題、官方網址，與抓取狀態。"""
    d = pk.get("deck") or {}
    a = pk.get("annual") or {}
    return {"v": pk.get("v"), "made": pk.get("made"), "ok": pk.get("ok"), "st": pk.get("st"), "name": pk.get("name"),
            "site": (pk.get("basic") or {}).get("site"),
            "confs": [{k: c.get(k) for k in ("d", "pdf", "video")} for c in pk.get("confs") or []],
            "deck": {"d": d.get("d"), "url": d.get("url"), "n": len(d.get("pages") or [])} if d else None,
            "news": [{"d": x["d"], "subj": x["subj"]} for x in pk.get("news") or []],
            "annual": {"fy": a.get("fy"), "url": a.get("url"), "pages": [p for p, _ in a.get("pages") or []]} if a else None}


# ── 抓取紀錄與「隔天重試」（使用者 2026-10-30 選 D2：抓不到當天不寫、隔天重試，連兩天抓不到才照寫並寫明）────────

LOG_KEEP = 10            # 每家留最近幾次抓取


def _why(st: dict | None) -> str:
    bad = [f"{k} {v}" for k, v in (st or {}).items() if str(v).startswith("err")]
    return "；".join(bad)[:200] or "沒抓到"


def log_update(log: dict, idx: dict) -> dict:
    """data/eq_docs_log.json（CI 寫回 main）：每家每天最後一次抓取的結果 [日期, "ok" 或錯誤原因]，留 LOG_KEEP 筆；
    順手把每家「連續沒抓到的日子」寫進文件清單（fails，最新的在前），排程與檢查都看它。"""
    day = str(idx.get("at") or "")[:10]
    codes = log.setdefault("codes", {})
    for c, x in (idx.get("codes") or {}).items():
        hist = [h for h in codes.get(c, []) if h[0] != day]            # 同一天抓好幾次：留最後一次
        hist.append([day, "ok" if x.get("ok") else _why(x.get("st"))])
        codes[c] = hist[-LOG_KEEP:]
        x["fails"] = fails(codes[c])
    log["v"] = 1
    return log


def fails(hist: list) -> list[str]:
    """從最近一次往回數，連續沒抓到的日子（不同天）；最近一次抓到＝[]。"""
    out = []
    for d, s in reversed(hist or []):
        if s == "ok":
            break
        out.append(d)
    return out


def d2(x: dict) -> str:
    """一家文件包的處理：ok＝照常寫；retry＝今天不寫、明天名單還會有它；write＝連兩天沒抓到，照寫並在資料侷限寫明。"""
    if x.get("ok"):
        return "ok"
    return "write" if len(x.get("fails") or []) >= 2 else "retry"


def for_facts(idx: dict, code: str) -> dict | None:
    """文件清單（.eqdocs/{編號}/index.json）→ 報告旁 .facts.json 的 docs（只有日期、主旨、官方網址與抓取狀態，沒有全文）。"""
    x = (idx.get("codes") or {}).get(f"tw:{code}")
    if not x:
        return None
    return {**x, "id": idx.get("id"), "at": idx.get("at")}


def render_md(pk: dict) -> str:
    """給寫報告的子代理讀的版本（同一份資料，換成好讀的格式）。"""
    b = pk.get("basic") or {}
    L = [f"# {pk.get('name') or pk['code']}（{pk['code']}）官方文件包", "",
         f"抓取：{pk.get('made')}；狀態：" + "、".join(f"{k} {v}" for k, v in (pk.get("st") or {}).items()), "",
         "## 公司基本資料（公開資訊觀測站）", ""]
    for k, lab in (("biz", "主要經營業務"), ("ind", "產業類別"), ("board", "市場"), ("listed", "上市日期"), ("otc", "上櫃日期"),
                   ("chair", "董事長"), ("ceo", "總經理"), ("spoke", "發言人"), ("site", "公司網址")):
        if b.get(k):
            L.append(f"- {lab}：{b[k]}".replace("\n", "；"))
    L += ["", "## 法說會（近 24 個月，公開資訊觀測站）", ""]
    for c in pk.get("confs") or []:
        L.append(f"- {c['d']} {c.get('t') or ''}：{(c.get('note') or '').rstrip('。')}" + (f"；簡報 {c['pdf']}" if c.get("pdf") else "")
                 + (f"；影音 {c['video']}" if c.get("video") else ""))
    if not pk.get("confs"):
        L.append("- 近 24 個月沒有法說會紀錄。")
    d = pk.get("deck")
    if d:
        L += ["", f"## 最近一次法說會簡報（{d['d']}，{d['url']}）", ""]
        for i, t in enumerate(d["pages"]):
            L.append(f"### 第 {i + 1} 頁" + ("（這一頁是圖，沒有文字）" if len(t) < IMG_MIN else ""))
            if t:
                L.append(t)
    L += ["", "## 重大訊息（近 6 個月，公開資訊觀測站，新到舊）", ""]
    for x in pk.get("news") or []:
        L.append(f"### {x['d']} {x['t']} {x['subj']}")
        if x.get("body"):
            L.append(x["body"])
    if not pk.get("news"):
        L.append("- 近 6 個月沒有重大訊息。")
    a = pk.get("annual")
    if a:
        L += ["", f"## 股東會年報 {a.get('fy')} 年度「營運概況」的業務內容與市場及產銷概況（全本 {a.get('pp')} 頁；{a.get('url')}）", ""]
        for p, t in a.get("pages") or []:
            L.append(f"### 年報第 {p} 頁")
            L.append(t)
    return "\n".join(L) + "\n"
