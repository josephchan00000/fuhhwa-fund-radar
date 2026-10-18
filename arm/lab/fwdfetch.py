"""泡沫頁 VER 4「未來獲利」的資料抓取（docs/lab_risk_plan.md 第 11 節）。只在 CI 跑（本容器的 proxy 擋這些站）。

使用者 2026-10-18：股價反應的是未來獲利，要看未來獲利的成長，邊際成長放緩是警訊；那斯達克要有自己的基本面。
現在的等級用分析師預估，過去的驗證用替代資料（S&P 500 用專業預測者調查，真的預估）。

存檔（data/lab/heat/ 走 heatdata；美股預估另存 data/lab/fwd/）：
  us_spf       專業預測者調查 美國企業稅後獲利預測中位數  {"YYYY-Qq": [CPROF1～6, CPROFA, CPROFB]}  1968Q4 起（年度 1981Q3 起）
  us_tech_q    BEA 產業別企業獲利（季、年率、百萬美元）    {季底 YYYY-MM: {DBnomics 代碼: 值}}       1948 起（表 6.16B／C／D）
  us_tech_a    同上年資料（1998～2000 新舊分類重疊年用）   {"YYYY": {代碼: 值}}
  fwd_agg      每天的分析師預估加總（台股＋美股四個指數）  {日期: {市場: fwd.aggregate 的結果＋"ok"}}
  fwd/us       美股最新一份預估（每家公司各自的抓取日）    {"const", "q", "fx", "s": {代號: {"d", "y0", "y1"}}}
  fwd_w/{日期} fwd/us 每週封存一份

probe()／probe2()／probe3() 是寫規格前的探針（2026-10-18 跑過三輪，結果在規劃文件第 11.8 節）。
"""
from __future__ import annotations

import io
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from ..http import _CTX
from . import bubspec as BS
from . import fwd as FW
from . import heatdata as HD
from . import store
from .heatfetch import BROWSER, _get, _merge, parse_dbnomics
from .market import log

TZ = timezone(timedelta(hours=8))
SPF_CPROF_PAGE = "https://www.philadelphiafed.org/surveys-and-data/cprof"
DBN = "https://api.db.nomics.world/v22/series/{p}?observations=1&format=json"
WIKI_SP = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NQ_NDX = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
NQ_SCREEN = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=6000&exchange=NASDAQ&download=true"
SOX_W = "https://indexes.nasdaqomx.com/Index/WeightingData"
US_FILE = "us"                                       # store.write("fwd", "us", …)
US_KIND, US_ARCH = "fwd", "fwd_w"

SPF_PAGES = ("https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/median-forecasts",
             "https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/mean-forecasts",
             "https://www.philadelphiafed.org/surveys-and-data/cprof")
DBN_SEARCH = "https://api.db.nomics.world/v22/series/{p}?q={q}&observations=false&limit=80&format=json"
DBN_ONE = "https://api.db.nomics.world/v22/series/{p}?observations=1&format=json"
NASDAQ_HDR = {**BROWSER, "Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com",
              "Referer": "https://www.nasdaq.com/"}


def _p(tag: str, msg: str) -> None:
    log(f"[fwd-probe] {tag} {msg}")


def _try(tag: str, url: str, *, timeout: int = 60, headers: dict | None = None, n: int = 400) -> bytes | None:
    try:
        b = _get(url, timeout=timeout, headers=headers)
        _p(tag, f"OK {len(b)} bytes：{b[:n]!r}")
        return b
    except Exception as e:                                    # noqa: BLE001 —— 探針：印出原因、往下試
        _p(tag, f"✗ {type(e).__name__} {str(e)[:200]}")
        return None


def _post(tag: str, url: str, form: dict, *, headers: dict | None = None, timeout: int = 60, n: int = 400) -> bytes | None:
    try:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(),
                                     headers={**(headers or BROWSER), "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            b = r.read()
        _p(tag, f"OK {len(b)} bytes：{b[:n]!r}")
        return b
    except Exception as e:                                    # noqa: BLE001
        _p(tag, f"✗ {type(e).__name__} {str(e)[:200]}")
        return None


def _xlsx_peek(tag: str, b: bytes, want: str = "CPROF") -> None:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
    except Exception as e:                                    # noqa: BLE001
        _p(tag, f"xlsx 讀不開 {type(e).__name__} {str(e)[:160]}")
        return
    names = wb.sheetnames
    _p(tag, f"工作表 {len(names)} 個：{names[:60]}")
    ws = next((wb[s] for s in names if s.strip().upper() == want), None) or wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    _p(tag, f"工作表 {ws.title}：{len(rows)} 列")
    for r in rows[:4] + [["…"]] + rows[-4:]:
        _p(tag, f"  {r[:16]}")


def probe_spf() -> None:
    links: list[str] = []
    for page in SPF_PAGES:
        b = _try("SPF 頁", page, n=120)
        if not b:
            continue
        hrefs = re.findall(r'href="([^"]+\.xlsx[^"]*)"', b.decode("utf-8", "replace"), re.I)
        _p("SPF 頁", f"{page} 的 xlsx 連結 {len(hrefs)} 個：{[h[-90:] for h in hrefs[:30]]}")
        links += [urllib.parse.urljoin("https://www.philadelphiafed.org/", h.replace("&amp;", "&")) for h in hrefs]
    seen = set()
    for url in links:
        key = url.split("?")[0].lower()
        if key in seen or not re.search(r"(median|mean).?(level|growth)|cprof", key):
            continue
        seen.add(key)
        b = _try("SPF 檔", url, timeout=120, n=60)
        if b:
            _xlsx_peek("SPF 檔 " + key.rsplit("/", 1)[-1], b)


def probe_bea_tech() -> None:
    for ds in ("BEA/NIPA-T61600D", "BEA/NIPA-T61600C", "BEA/NIPA-T61600B"):
        for q in ("computer", "information", "electronic"):
            try:
                doc = json.loads(_get(DBN_SEARCH.format(p=ds, q=q), timeout=120).decode("utf-8"))
                docs = ((doc.get("series") or {}).get("docs")) or []
                _p("BEA", f"{ds} q={q}：{len(docs)} 條")
                for x in docs[:20]:
                    _p("BEA", f"   {x.get('series_code')}｜{str(x.get('series_name'))[:140]}")
            except Exception as e:                            # noqa: BLE001
                _p("BEA", f"{ds} q={q} ✗ {type(e).__name__} {str(e)[:160]}")


def probe_bea_series(codes: list[str]) -> None:
    for c in codes:
        try:
            doc = json.loads(_get(DBN_ONE.format(p=c), timeout=120).decode("utf-8"))
            d = ((doc.get("series") or {}).get("docs") or [{}])[0]
            per, val = d.get("period") or [], d.get("value") or []
            _p("BEA 序列", f"{c}：{len(per)} 期 {per[:2]}…{per[-2:]}，最後值 {val[-3:]}")
        except Exception as e:                                # noqa: BLE001
            _p("BEA 序列", f"{c} ✗ {type(e).__name__} {str(e)[:160]}")


def _wiki_tickers(tag: str, url: str) -> None:
    b = _try(tag, url, n=80)
    if not b:
        return
    html = b.decode("utf-8", "replace")
    m = re.search(r'<table[^>]*id="constituents".*?</table>', html, re.S)
    _p(tag, f"constituents 表 {'有' if m else '沒有'}；整頁表格 {len(re.findall(r'<table', html))} 個")
    seg = m.group(0) if m else html
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S)
    cells = [re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S) for r in rows]
    clean = [[re.sub(r"<[^>]+>", "", c).strip()[:30] for c in r] for r in cells if r]
    _p(tag, f"列數 {len(clean)}；前 4 列 {clean[:4]}；最後 2 列 {clean[-2:]}")


def probe_constituents() -> None:
    _wiki_tickers("維基 S&P 500", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    _wiki_tickers("維基 那斯達克 100", "https://en.wikipedia.org/wiki/Nasdaq-100")
    _wiki_tickers("維基 費半", "https://en.wikipedia.org/wiki/PHLX_Semiconductor_Sector")
    b = _try("SPY 持股", "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/"
             "holdings-daily-us-en-spy.xlsx", timeout=90, n=60)
    if b:
        _xlsx_peek("SPY 持股", b, want="HOLDINGS")
    _try("QQQ 持股", "https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0"
         "?audienceType=Investor&action=download&ticker=QQQ", timeout=90, n=500)
    _try("那斯達克 100 API", "https://api.nasdaq.com/api/quote/list-type/nasdaq100", headers=NASDAQ_HDR, n=500)
    b = _try("那斯達克篩選器", "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=6000&exchange=NASDAQ&download=true",
             headers=NASDAQ_HDR, timeout=120, n=300)
    if b:
        try:
            rows = (json.loads(b.decode("utf-8")).get("data") or {}).get("rows") or []
            _p("那斯達克篩選器", f"{len(rows)} 列；第一列 {rows[0] if rows else None}")
        except Exception as e:                                # noqa: BLE001
            _p("那斯達克篩選器", f"解析 ✗ {type(e).__name__} {str(e)[:120]}")
    _try("費半 指數頁", "https://indexes.nasdaq.com/Index/Weighting/SOX", n=300)
    _post("費半 權重 API", "https://indexes.nasdaqomx.com/Index/WeightingData",
          {"id": "SOX", "tradeDate": "2026-10-16T00:00:00.000", "timeOfDay": "SOD"}, n=600)
    _try("SOXX 持股", "https://www.ishares.com/us/products/239705/ishares-semiconductor-etf/1467271812596.ajax"
         "?fileType=csv&fileName=SOXX_holdings&dataType=fund", timeout=90, n=900)


def probe_yahoo_us() -> None:
    from . import fcst
    Y = fcst._Yahoo()
    if not Y.login():
        _p("Yahoo", "拿不到 crumb")
        return
    for sym in ("AAPL", "NVDA", "MSFT", "AVGO", "BRK-B"):
        st, rec = Y.one(sym)
        _p("Yahoo", f"{sym} {st}：{json.dumps(rec, ensure_ascii=False)[:700] if rec else None}")
    crumb = urllib.parse.quote(Y.crumb or "")
    st, b = Y.get(f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/AAPL?modules=price,defaultKeyStatistics"
                  f"&crumb={crumb}")
    _p("Yahoo price", f"{st} {b[:900]!r}")
    st, b = Y.get(f"https://query2.finance.yahoo.com/v7/finance/quote?symbols=AAPL,NVDA,MSFT,AMD,INTC&crumb={crumb}")
    _p("Yahoo 批次報價", f"{st} {b[:1200]!r}")


def probe() -> None:
    for fn in (probe_spf, probe_bea_tech, probe_constituents, probe_yahoo_us):
        try:
            fn()
        except Exception as e:                                # noqa: BLE001
            _p(fn.__name__, f"✗ {type(e).__name__} {str(e)[:200]}")


def probe2() -> None:
    """第二輪：BEA 序列期間、SIC 舊分類的機械與通訊、SPF 年度預測從哪一季開始、ADR 與外幣公司的 Yahoo 欄位。"""
    probe_bea_series(["BEA/NIPA-T61600D/N501RC-Q", "BEA/NIPA-T61600D/N502RC-Q",
                      "BEA/NIPA-T61600C/A410RC-Q", "BEA/NIPA-T61600B/A410RBC-Q"])
    for ds in ("BEA/NIPA-T61600C", "BEA/NIPA-T61600B"):
        for q in ("machinery", "communication", "telephone", "services"):
            try:
                doc = json.loads(_get(DBN_SEARCH.format(p=ds, q=q), timeout=120).decode("utf-8"))
                docs = ((doc.get("series") or {}).get("docs")) or []
                _p("BEA", f"{ds} q={q}：{len(docs)} 條")
                for x in docs[:12]:
                    _p("BEA", f"   {x.get('series_code')}｜{str(x.get('series_name'))[:140]}")
            except Exception as e:                            # noqa: BLE001
                _p("BEA", f"{ds} q={q} ✗ {type(e).__name__} {str(e)[:160]}")
    try:
        import openpyxl
        page = _get(SPF_PAGES[2], timeout=60).decode("utf-8", "replace")
        href = next(h for h in re.findall(r'href="([^"]+\.xlsx[^"]*)"', page, re.I) if "median_cprof_level" in h.lower())
        b = _get(urllib.parse.urljoin("https://www.philadelphiafed.org/", href.replace("&amp;", "&")), timeout=120)
        rows = [list(r) for r in openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True).worksheets[0]
                .iter_rows(values_only=True)]
        hdr = rows[0]
        ia, ib = hdr.index("CPROFA"), hdr.index("CPROFB")
        first_a = next((r[:2] for r in rows[1:] if isinstance(r[ia], (int, float))), None)
        first_b = next((r[:2] for r in rows[1:] if isinstance(r[ib], (int, float))), None)
        gaps = [r[:2] for r in rows[1:] if not isinstance(r[3], (int, float))]
        _p("SPF", f"CPROFA 從 {first_a}、CPROFB 從 {first_b}；CPROF2 缺值的季 {gaps[:20]}")
        for r in rows[1:]:
            if r[0] in (2005.0, 2006.0) or (r[0] == 1981.0):
                _p("SPF", f"  {r}")
    except Exception as e:                                    # noqa: BLE001
        _p("SPF", f"✗ {type(e).__name__} {str(e)[:200]}")
    from . import fcst
    Y = fcst._Yahoo()
    if not Y.login():
        _p("Yahoo", "拿不到 crumb")
        return
    for sym in ("TSM", "ASML", "PDD", "ARM", "AZN"):
        st, rec = Y.one(sym)
        _p("Yahoo", f"{sym} {st}：{json.dumps(rec, ensure_ascii=False)[:600] if rec else None}")
    crumb = urllib.parse.quote(Y.crumb or "")
    st, b = Y.get(f"https://query2.finance.yahoo.com/v7/finance/quote?symbols=TSM,ASML,PDD,ARM,AZN,AAPL&crumb={crumb}")
    try:
        res = json.loads(b.decode("utf-8"))["quoteResponse"]["result"]
        keys = ("symbol", "currency", "financialCurrency", "marketCap", "sharesOutstanding", "regularMarketPrice",
                "epsTrailingTwelveMonths", "trailingPE", "epsCurrentYear", "priceEpsCurrentYear", "epsForward", "forwardPE")
        for q in res:
            _p("Yahoo 批次", str({k: q.get(k) for k in keys}))
    except Exception as e:                                    # noqa: BLE001
        _p("Yahoo 批次", f"{st} ✗ {type(e).__name__} {str(e)[:120]} {b[:300]!r}")
    big = ",".join(["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "JPM"] * 15)
    st, b = Y.get(f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={big}&crumb={crumb}")
    _p("Yahoo 批次 150", f"{st} {len(b)} bytes")


def probe3() -> None:
    """第三輪：科技業獲利新舊分類有沒有重疊年（年資料）、6.16C 的通訊業代碼。"""
    probe_bea_series(["BEA/NIPA-T61600D/N501RC-A", "BEA/NIPA-T61600D/N502RC-A",
                      "BEA/NIPA-T61600C/A409RC-A", "BEA/NIPA-T61600C/A410RC-A", "BEA/NIPA-T61600C/A418RC-A",
                      "BEA/NIPA-T61600C/A418RC-Q", "BEA/NIPA-T61600B/A418RBC-Q", "BEA/NIPA-T61600B/A409RBC-Q",
                      "BEA/NIPA-T61600C/A409RC-Q"])
    for ds in ("BEA/NIPA-T61600C",):
        for q in ("communications", "transportation", "utilities"):
            try:
                doc = json.loads(_get(DBN_SEARCH.format(p=ds, q=q), timeout=120).decode("utf-8"))
                docs = ((doc.get("series") or {}).get("docs")) or []
                _p("BEA", f"{ds} q={q}：{len(docs)} 條")
                for x in docs[:12]:
                    _p("BEA", f"   {x.get('series_code')}｜{str(x.get('series_name'))[:140]}")
            except Exception as e:                            # noqa: BLE001
                _p("BEA", f"{ds} q={q} ✗ {type(e).__name__} {str(e)[:160]}")
    try:
        doc = json.loads(_get("https://api.db.nomics.world/v22/series/BEA/NIPA-T61600C?observations=false&limit=80&format=json",
                              timeout=120).decode("utf-8"))
        docs = ((doc.get("series") or {}).get("docs")) or []
        _p("BEA", f"6.16C 全部 {len(docs)} 條：" + "；".join(f"{x.get('series_code')} {str(x.get('series_name'))[:50]}"
                                                         for x in docs if str(x.get('series_code', '')).endswith('-Q')))
    except Exception as e:                                    # noqa: BLE001
        _p("BEA", f"6.16C 全部 ✗ {type(e).__name__} {str(e)[:160]}")



# ══ 正式抓取 ════════════════════════════════════════════════════════════════

# ── 專業預測者調查 ──────────────────────────────────────────────────────────

def spf() -> int:
    import openpyxl
    page = _get(SPF_CPROF_PAGE, timeout=90).decode("utf-8", "replace")
    href = next((h for h in re.findall(r'href="([^"]+\.xlsx[^"]*)"', page, re.I)
                 if BS.SPF_FILE.lower() in h.lower()), None)
    if not href:
        raise RuntimeError(f"找不到 {BS.SPF_FILE}.xlsx 的連結")
    b = _get(urllib.parse.urljoin("https://www.philadelphiafed.org/", href.replace("&amp;", "&")), timeout=120)
    rows = [list(r) for r in openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True).worksheets[0]
            .iter_rows(values_only=True)]
    d = FW.spf_parse(rows)
    if len(d) < 200:
        raise RuntimeError(f"專業預測者調查只解析到 {len(d)} 季")
    return _merge("us_spf", "philly_spf:" + BS.SPF_FILE, d)


# ── BEA 科技業獲利 ─────────────────────────────────────────────────────────

def _qkey(p: str) -> str | None:
    m = re.match(r"^(\d{4})-Q([1-4])$", p)
    return f"{m.group(1)}-{int(m.group(2)) * 3:02d}" if m else None


def tech() -> int:
    q: dict = {}
    a: dict = {}
    errs = []
    for code in BS.TECH_NAICS_Q + BS.TECH_SIC_C_Q + BS.TECH_SIC_B_Q:
        try:
            for p, v in parse_dbnomics(json.loads(_get(DBN.format(p=code), timeout=120).decode("utf-8"))).items():
                k = _qkey(p)
                if k:
                    q.setdefault(k, {})[code] = v
        except Exception as e:                                # noqa: BLE001 —— 一條失敗不影響其他條
            errs.append(f"{code}：{type(e).__name__} {str(e)[:80]}")
    for code in BS.TECH_NAICS_A + BS.TECH_SIC_C_A:
        try:
            for p, v in parse_dbnomics(json.loads(_get(DBN.format(p=code), timeout=120).decode("utf-8"))).items():
                if re.match(r"^\d{4}", p):
                    a.setdefault(p[:4], {})[code] = v
        except Exception as e:                                # noqa: BLE001
            errs.append(f"{code}：{type(e).__name__} {str(e)[:80]}")
    if errs:
        log(f"[fwd] 科技業獲利部分序列失敗：{'；'.join(errs)}")
    if not q:
        raise RuntimeError("科技業獲利都抓不到")
    old_q, old_a = HD.load("us_tech_q"), HD.load("us_tech_a")
    q = {k: {**(old_q.get(k) or {}), **v} for k, v in q.items()}    # 某一條這次失敗：保留舊值
    a = {k: {**(old_a.get(k) or {}), **v} for k, v in a.items()}
    n = _merge("us_tech_q", "bea_dbnomics_t616", q) + _merge("us_tech_a", "bea_dbnomics_t616", a)
    ts = FW.tech_series(HD.load("us_tech_q"), HD.load("us_tech_a"))
    log(f"[fwd] 科技業獲利接好 {len(ts)} 季：{min(ts) if ts else '—'}～{max(ts) if ts else '—'}")
    return n


# ── 美股成分股與分析師預估 ─────────────────────────────────────────────────

def _ysym(s: str) -> str:
    return s.strip().upper().replace(".", "-").replace("/", "-")


def parse_wiki_sp(html: str) -> list[str]:
    m = re.search(r'<table[^>]*id="constituents".*?</table>', html, re.S)
    if not m:
        return []
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if cells:
            sym = re.sub(r"<[^>]+>", "", cells[0]).strip()
            if re.match(r"^[A-Z][A-Z.\-]{0,6}$", sym):
                out.append(_ysym(sym))
    return out


def parse_nq_rows(doc: dict) -> list[tuple[str, float | None]]:
    d = doc.get("data") or {}
    rows = (d.get("data") or {}).get("rows") if isinstance(d.get("data"), dict) else None
    rows = rows if rows is not None else d.get("rows") or []
    out = []
    for r in rows:
        sym = str(r.get("symbol") or "").strip()
        if not re.match(r"^[A-Z][A-Z.\-/]{0,6}$", sym):
            continue
        cap = re.sub(r"[^0-9.]", "", str(r.get("marketCap") or ""))
        out.append((_ysym(sym), float(cap) if cap else None))
    return out


def parse_sox(doc: dict) -> list[str]:
    return [_ysym(x["Symbol"]) for x in (doc.get("aaData") or []) if x.get("Symbol")]


def constituents(day: str) -> dict:
    """{"spx", "ixic", "ndx", "sox"}：代號清單（Yahoo 格式）；ixic＝那斯達克篩選器市值前 EST_NQ_TOP 大，另附 "nq_cap"＝篩選器全部市值合計。"""
    out: dict = {}
    try:
        out["spx"] = parse_wiki_sp(_get(WIKI_SP, timeout=90).decode("utf-8", "replace"))
    except Exception as e:                                    # noqa: BLE001
        log(f"[fwd] S&P 500 成分股 ✗ {type(e).__name__} {str(e)[:120]}")
    try:
        out["ndx"] = [s for s, _ in parse_nq_rows(json.loads(_get(NQ_NDX, headers=NASDAQ_HDR, timeout=90).decode("utf-8")))]
    except Exception as e:                                    # noqa: BLE001
        log(f"[fwd] 那斯達克 100 成分股 ✗ {type(e).__name__} {str(e)[:120]}")
    try:
        rows = parse_nq_rows(json.loads(_get(NQ_SCREEN, headers=NASDAQ_HDR, timeout=150).decode("utf-8")))
        rows = [r for r in rows if r[1]]
        rows.sort(key=lambda r: -r[1])
        out["ixic"] = [s for s, _ in rows[:BS.EST_NQ_TOP]]
        out["nq_cap"] = sum(c for _, c in rows)
    except Exception as e:                                    # noqa: BLE001
        log(f"[fwd] 那斯達克篩選器 ✗ {type(e).__name__} {str(e)[:120]}")
    d = date.fromisoformat(day)
    for k in range(8):                                        # 權重表要給交易日：從最近一個美股收盤日往前試
        t = (d - timedelta(days=k))
        if t.weekday() >= 5:
            continue
        try:
            req = urllib.request.Request(SOX_W, data=urllib.parse.urlencode(
                {"id": "SOX", "tradeDate": f"{t.isoformat()}T00:00:00.000", "timeOfDay": "SOD"}).encode(),
                headers={**BROWSER, "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=60, context=_CTX) as r:
                syms = parse_sox(json.loads(r.read().decode("utf-8")))
            if len(syms) >= 20:
                out["sox"] = syms
                break
        except Exception as e:                                # noqa: BLE001
            log(f"[fwd] 費半成分股 {t} ✗ {type(e).__name__} {str(e)[:100]}")
    return out


def parse_v7(doc: dict) -> dict:
    """v7 報價 → {代號: [市值, 股數, 股價, 財報幣別]}；匯率代號（XXXUSD=X）→ {代號: [None, None, 價格, None]}。"""
    out = {}
    for q in ((doc.get("quoteResponse") or {}).get("result") or []):
        s = q.get("symbol")
        if s:
            out[s] = [q.get("marketCap"), q.get("sharesOutstanding"), q.get("regularMarketPrice"), q.get("financialCurrency")]
    return out


def _v7(Y, syms: list[str]) -> dict:
    crumb = urllib.parse.quote(Y.crumb or "")
    out = {}
    for i in range(0, len(syms), 150):
        chunk = ",".join(urllib.parse.quote(s) for s in syms[i:i + 150])
        st, b = Y.get(f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={chunk}&crumb={crumb}", timeout=60)
        if st == 200:
            try:
                out.update(parse_v7(json.loads(b.decode("utf-8"))))
            except Exception:                                 # noqa: BLE001
                pass
        else:
            log(f"[fwd] v7 報價 {i}～{i + 150} 狀態 {st}")
    return out


def _compact(rec: dict | None) -> dict | None:
    if not rec:
        return None
    out = {k: {"end": rec[k].get("end"), "e": rec[k].get("e"), "t": rec[k].get("t")} for k in ("y0", "y1") if rec.get(k)}
    return out or None


def load_us() -> dict:
    return store.read(US_KIND, US_FILE) or {"s": {}, "q": {}, "fx": {}, "const": {}}


def update_us(*, budget_s: float = 240, workers: int = 4, today: date | None = None) -> dict:
    """美股成分股的分析師預估：成分股＋報價＋匯率每次重抓；quoteSummary 先抓沒有的、再抓最舊的，到 budget_s 為止
    （沒抓完下一輪續抓）。每家公司記自己的抓取日；加總時超過 EST_STALE_DAYS 的不算。抓完算當天四個指數的加總寫進 fwd_agg。"""
    from . import fcst
    t0 = time.time()
    today = today or datetime.now(TZ).date()
    doc = load_us()
    const = constituents(today.isoformat())
    for k in ("spx", "ixic", "ndx", "sox"):
        if not const.get(k):
            const[k] = (doc.get("const") or {}).get(k) or []          # 這次抓不到：沿用上一份
            log(f"[fwd] {k} 成分股沿用上一份（{len(const[k])} 檔）")
    if not const.get("nq_cap"):
        const["nq_cap"] = (doc.get("const") or {}).get("nq_cap")
    syms = sorted({s for k in ("spx", "ixic", "ndx", "sox") for s in const[k]})
    Y = fcst._Yahoo()
    if not Y.login():
        return {"err": "拿不到 crumb"}
    q = _v7(Y, syms)
    if len(q) < 0.8 * len(syms):
        log(f"[fwd] v7 報價只拿到 {len(q)}／{len(syms)}，缺的沿用上一份")
        q = {**(doc.get("q") or {}), **q}
    curs = sorted({v[3] for v in q.values() if v and v[3] and v[3] != "USD"})
    fxq = _v7(Y, [f"{c}USD=X" for c in curs]) if curs else {}
    fx = {c: (fxq.get(f"{c}USD=X") or [None] * 3)[2] for c in curs}
    fx = {c: v for c, v in fx.items() if v} or {}
    fx = {**(doc.get("fx") or {}), **fx}
    s = dict(doc.get("s") or {})
    order = sorted(syms, key=lambda x: ((s.get(x) or {}).get("d") or "0000"))
    state = {"stop": False}

    def work(sym):
        if state["stop"] or time.time() - t0 > budget_s:
            return sym, "skip", None
        for k in range(3):
            st, rec = Y.one(sym)
            if st == "429":
                time.sleep(4 * (k + 1))
                continue
            if st == "401" and k == 0:
                Y.login()
                continue
            return sym, st, rec
        return sym, "429", None

    stat = {"ok": 0, "none": 0, "err": 0, "429": 0, "401": 0, "skip": 0}
    n429 = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for sym, st, rec in ex.map(work, order):
            n429 = n429 + 1 if st == "429" else 0
            if n429 >= 20:
                state["stop"] = True
            c = _compact(rec) if st == "ok" else None
            if c:
                s[sym] = {"d": today.isoformat(), **c}
                stat["ok"] += 1
            elif st in ("ok", "none"):
                s[sym] = {"d": today.isoformat()}                    # 查到沒有預估：記日期，免得每輪重抓
                stat["none"] += 1
            else:
                stat[st] = stat.get(st, 0) + 1
    keep = set(syms)
    s = {k: s[k] for k in sorted(s) if k in keep}
    out = {"d": today.isoformat(), "const": const, "q": {k: q[k] for k in sorted(q) if k in keep}, "fx": fx, "s": s}
    store.write(US_KIND, US_FILE, out)
    wk = today.isocalendar()[:2]
    if not any(date.fromisoformat(x).isocalendar()[:2] == wk for x in store.dates(US_ARCH)):
        store.write(US_ARCH, today.isoformat(), out)
    agg = us_aggregates(out, today)
    save_agg(today.isoformat(), agg)
    stat.update({"syms": len(syms), "s": round(time.time() - t0),
                 "agg": {k: (v.get("n"), None if v.get("cov") is None else round(v["cov"], 3)) for k, v in agg.items()}})
    log(f"[fwd] 美股預估：{stat}")
    return stat


def us_aggregates(doc: dict, today: date) -> dict:
    """fwd/us 一份 → {"spx", "ixic", "ndx", "sox": fwd.aggregate＋"d"}；每家公司的抓取日要在 EST_STALE_DAYS 天內。"""
    lim = (today - timedelta(days=BS.EST_STALE_DAYS)).isoformat()
    recs = {k: v for k, v in (doc.get("s") or {}).items() if v.get("d", "") >= lim and v.get("y0")}
    q, fx, const = doc.get("q") or {}, doc.get("fx") or {}, doc.get("const") or {}
    out = {}
    for mk in ("spx", "ixic", "ndx", "sox"):
        syms = const.get(mk) or []
        rows = FW.est_rows_us(recs, q, fx, syms)
        cap_all = const.get("nq_cap") if mk == "ixic" else sum((q.get(x) or [0])[0] or 0 for x in syms)
        a = FW.aggregate(rows, cap_all)
        a["d"] = today.isoformat()
        a["top"] = FW.top_contrib(rows)
        out[mk] = a
    return out


def save_agg(day: str, agg: dict) -> None:
    old = HD.load("fwd_agg")
    cur = dict(old.get(day) or {})
    cur.update(agg)
    old[day] = cur
    HD.save("fwd_agg", "fwdfetch", old)


# ── 台股：Yahoo 預估加總（每天一次，不連網） ─────────────────────────────────

def tw_shares_close() -> tuple[dict, dict, float]:
    """最新官方分片的發行股數、收盤、全部上市櫃普通股市值合計。"""
    sh, px = {}, {}
    for d in reversed(store.dates("mkt")[-15:]):
        doc = store.read("mkt", d) or {}
        tw, xt, tp = doc.get("q_tw") or {}, doc.get("x_tw") or {}, doc.get("q_tp") or {}
        if not (tw and xt and tp):
            continue
        for c, r in tw.items():
            if c not in px and r and len(r) > 3 and r[3]:
                px[c] = r[3]
        for c, r in xt.items():
            if c not in sh and r and len(r) > 1 and r[1]:
                sh[c] = r[1]
        for c, r in tp.items():
            if r and len(r) > 6 and r[6] and c not in sh:
                sh[c] = r[6]
            if c not in px and r and len(r) > 3 and r[3]:
                px[c] = r[3]
        break
    common = [c for c in sh if re.match(r"^[1-9]\d{3}$", c) and px.get(c)]
    return sh, px, sum(sh[c] * px[c] for c in common)


def update_tw_agg() -> dict | None:
    from . import fcst
    yh = fcst.load_yahoo()
    d = yh.get("d")
    if not d or not yh.get("s"):
        return None
    sh, px, cap_all = tw_shares_close()
    rows = FW.est_rows_tw(yh["s"], sh, px)
    a = FW.aggregate(rows, cap_all)
    a["d"] = d
    a["top"] = FW.top_contrib(rows)
    save_agg(d, {"tw": a})
    log(f"[fwd] 台股預估加總 {d}：{a['n']} 家，涵蓋 {None if a['cov'] is None else round(a['cov'], 3)}")
    return a
