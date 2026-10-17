"""景氣溫度頁的資料抓取（docs/lab_heat_plan.md 第 7 節；來源由 CI 探針確認，結果見規劃文件第 10 節）。

只在 CI 跑（本容器的 proxy 擋這些站）。每個來源各自失敗、各自降級：抓不到就保留既有的檔，不把有值的檔洗成空。
存檔都走 heatdata.save()：data/lab/heat/{名稱}.json.gz，{"src", "d": {日期或 YYYY-MM: 值}}。

  margin    FinMind 融資融券合計（上市）       {日期: [融資金額(元), 融資張數, 融券張數]}           2001 起
  inst      FinMind 三大法人買賣金額合計       {日期: {名稱: 買賣超(元)}}                          2004 起
  futi      FinMind 期貨法人未平倉（TX/MTX/TMF）{日期: {契約: {身份: [多單口數, 空單口數]}}}         2018-06 起
  opti      FinMind 選擇權法人未平倉（TXO）    {日期: {買權/賣權: {身份: [多單金額, 空單金額](千元)}}} 2018-06 起
  mtxoi     FinMind 小台日行情                 {日期: 一般時段全部月份未平倉合計}                    2005 起
  pcr       期交所 P/C 比                       {日期: [賣權量, 買權量, 量比%, 賣權未平倉, 買權未平倉, 未平倉比%]}
  vixtw     期交所 台指 VIX 月檔                {日期: 收盤}（免費只保留近幾個月，從現在開始累積）
  taiex     Yahoo ^TWII                        {日期: 收盤}                                         1997-07 起
  vix       Yahoo ^VIX                         {日期: 收盤}
  turnover  證交所 FMTQIK                      {日期: [成交金額(元), 加權指數]}                      2000 起（每月一請求）
  usdtwd    央行 新台幣每日收盤                 {日期: 匯率}                                         2008 起
  ndc       國發會 景氣指標與燈號（最新修正值）  {YYYY-MM: [領先, 領先不含趨勢, 同時, 同時不含趨勢, 落後, 落後不含趨勢, 分數, 燈號]}
  ndc_first 國發會 景氣分數「第一次看到」的值    {YYYY-MM: [分數, 看到的日期]}（從開始抓那天起累積，日後可驗證修正幅度）
  pmi       國發會 製造業 PMI                   {YYYY-MM: PMI}                                       2012-07 起
  orders    經濟部 外銷訂單金額（百萬美元）       {YYYY-MM: 金額}                                      1984 起
"""
from __future__ import annotations

import io
import json
import re
import time
import urllib.parse
import zipfile
from datetime import date, timedelta

from ..http import get_bytes
from . import heatdata as HD
from .market import log, post_bytes

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
FM = "https://api.finmindtrade.com/api/v4/data?dataset={ds}{did}&start_date={a}&end_date={z}"


def _get(url: str, *, timeout: int = 60, headers: dict | None = None) -> bytes:
    return get_bytes(url, retries=2, timeout=timeout, use_cache=False, headers=headers or BROWSER)


def _merge(name: str, src: str, new: dict) -> int:
    """新值覆蓋同日舊值；值為 None 不寫；本次什麼都沒抓到就不動檔。回傳新增或改動的筆數。"""
    new = {k: v for k, v in new.items() if v is not None}
    if not new:
        return 0
    old = HD.load(name)
    n = sum(1 for k, v in new.items() if old.get(k) != v)
    if n:
        HD.save(name, src, {**old, **new})
    return n


def _finmind(ds: str, did: str, a: str, z: str | None = None) -> list[dict]:
    url = FM.format(ds=ds, did=f"&data_id={did}" if did else "", a=a, z=z or date.today().isoformat())
    doc = json.loads(_get(url, timeout=120).decode("utf-8"))
    if str(doc.get("status")) != "200":
        raise RuntimeError(f"FinMind {ds} {did} status={doc.get('status')} {str(doc.get('msg'))[:80]}")
    return doc.get("data") or []


# ── FinMind ──────────────────────────────────────────────────────────

def fm_margin(a: str) -> int:
    out: dict = {}
    for r in _finmind("TaiwanStockTotalMarginPurchaseShortSale", "", a):
        d, nm, v = str(r.get("date"))[:10], r.get("name"), r.get("TodayBalance")
        if v is None:
            continue
        k = {"MarginPurchaseMoney": 0, "MarginPurchase": 1, "ShortSale": 2}.get(nm)
        if k is not None:
            out.setdefault(d, [None, None, None])[k] = v
    return _merge("margin", "finmind", {d: v for d, v in out.items() if v[0] is not None})


def fm_inst(a: str) -> int:
    out: dict = {}
    for r in _finmind("TaiwanStockTotalInstitutionalInvestors", "", a):
        d, nm = str(r.get("date"))[:10], r.get("name")
        if nm and r.get("buy") is not None and r.get("sell") is not None:
            out.setdefault(d, {})[nm] = r["buy"] - r["sell"]
    return _merge("inst", "finmind", out)


def fm_futi(a: str) -> int:
    out: dict = {}
    for fid in ("TX", "MTX", "TMF"):
        for r in _finmind("TaiwanFuturesInstitutionalInvestors", fid, a):
            d, who = str(r.get("date"))[:10], r.get("institutional_investors")
            lo, sh = r.get("long_open_interest_balance_volume"), r.get("short_open_interest_balance_volume")
            if who and lo is not None and sh is not None:
                out.setdefault(d, {}).setdefault(fid, {})[who] = [lo, sh]
        time.sleep(1)
    return _merge("futi", "finmind", out)


def fm_opti(a: str) -> int:
    out: dict = {}
    for r in _finmind("TaiwanOptionInstitutionalInvestors", "TXO", a):
        d, cp, who = str(r.get("date"))[:10], r.get("call_put"), r.get("institutional_investors")
        lo, sh = r.get("long_open_interest_balance_amount"), r.get("short_open_interest_balance_amount")
        if cp and who and lo is not None and sh is not None:
            out.setdefault(d, {}).setdefault(cp, {})[who] = [lo, sh]
    return _merge("opti", "finmind", out)


def fm_mtxoi(a: str) -> int:
    """小台全市場未平倉：一般時段（position）、單一月份（不含價差 a/b）的未平倉合計。"""
    out: dict = {}
    for r in _finmind("TaiwanFuturesDaily", "MTX", a):
        if r.get("trading_session") != "position" or "/" in str(r.get("contract_date")):
            continue
        d, oi = str(r.get("date"))[:10], r.get("open_interest")
        if oi:
            out[d] = out.get(d, 0) + int(oi)
    return _merge("mtxoi", "finmind", out)


# ── 期交所 ───────────────────────────────────────────────────────────

def _months(a: date, z: date):
    y, m = a.year, a.month
    while (y, m) <= (z.year, z.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def taifex_pcr(a: date, z: date | None = None, budget_s: float = 600) -> int:
    z = z or date.today()
    out: dict = {}
    t0 = time.time()
    for y, m in _months(a, z):
        if time.time() - t0 > budget_s:
            log("[heat] P/C 回補時間到，下一輪續補")
            break
        s = date(y, m, 1)
        e = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        try:
            txt = post_bytes("https://www.taifex.com.tw/cht/3/pcRatioDown",
                             {"queryStartDate": f"{s:%Y/%m/%d}", "queryEndDate": f"{min(e, z):%Y/%m/%d}"},
                             timeout=60, retries=2).decode("cp950", "replace")
        except Exception as ex:                           # noqa: BLE001
            log(f"[heat] P/C {y}-{m:02d} ✗ {str(ex)[:80]}")
            continue
        for ln in txt.splitlines():
            c = [x.strip() for x in ln.split(",")]
            mm = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", c[0]) if c else None
            if not mm or len(c) < 7:
                continue
            try:
                vals = [float(x.replace("%", "")) for x in c[1:7]]
            except ValueError:
                continue
            out[f"{int(mm.group(1)):04d}-{int(mm.group(2)):02d}-{int(mm.group(3)):02d}"] = vals
        time.sleep(0.5)
    return _merge("pcr", "taifex", out)


def taifex_vix(months: int = 4) -> int:
    """台指 VIX 月檔（只保留近幾個月；更早的回 404 頁）。欄位：日期、時間、指數、收盤前 1 分鐘平均。"""
    out: dict = {}
    t = date.today()
    for k in range(months):
        y, m = t.year, t.month - k
        while m <= 0:
            y, m = y - 1, m + 12
        url = f"https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{y}{m:02d}new.txt"
        try:
            txt = _get(url, timeout=40).decode("cp950", "replace")
        except Exception as ex:                           # noqa: BLE001
            log(f"[heat] 台指 VIX {y}{m:02d} ✗ {str(ex)[:80]}")
            continue
        if "<html" in txt[:300].lower():
            continue
        for ln in txt.splitlines():
            c = [x for x in ln.split("\t") if x.strip()]
            if len(c) >= 3 and re.match(r"^\d{8}$", c[0]):
                try:
                    v = float(c[2])
                except ValueError:
                    continue
                out[f"{c[0][:4]}-{c[0][4:6]}-{c[0][6:]}"] = v
    return _merge("vixtw", "taifex", out)


# ── Yahoo ────────────────────────────────────────────────────────────

def yahoo(name: str, sym: str, start: str) -> int:
    from .market import yahoo_hist_from
    h = yahoo_hist_from(sym, start)
    return _merge(name, "yahoo", {d: row[3] for d, row in h.items() if row and row[3]})


# ── 證交所 ───────────────────────────────────────────────────────────

def twse_turnover(a: date, z: date | None = None, budget_s: float = 1500) -> int:
    """FMTQIK：每月一請求，每日成交金額與加權指數（民國日期）。"""
    z = z or date.today()
    out: dict = {}
    t0 = time.time()
    have: dict[str, int] = {}
    for k in HD.load("turnover"):
        have[k[:7]] = have.get(k[:7], 0) + 1
    cur = (z.year, z.month)
    prev = (z.year - (z.month == 1), (z.month - 2) % 12 + 1)
    for y, m in _months(a, z):
        if time.time() - t0 > budget_s:
            log("[heat] 成交金額回補時間到，下一輪續補")
            break
        if (y, m) not in (cur, prev) and have.get(f"{y:04d}-{m:02d}", 0) >= 15:
            continue                                      # 已有整月（本月與上月每次重抓）
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={y}{m:02d}01&response=json"
        try:
            doc = json.loads(_get(url, timeout=40).decode("utf-8"))
        except Exception as ex:                           # noqa: BLE001
            log(f"[heat] FMTQIK {y}-{m:02d} ✗ {str(ex)[:80]}")
            time.sleep(3.5)
            continue
        for r in doc.get("data") or []:
            mm = re.match(r"^\s*(\d{2,3})/(\d{2})/(\d{2})", str(r[0]))
            if not mm:
                continue
            d = f"{int(mm.group(1)) + 1911:04d}-{mm.group(2)}-{mm.group(3)}"
            try:
                out[d] = [float(str(r[2]).replace(",", "")), float(str(r[4]).replace(",", ""))]
            except (ValueError, IndexError):
                continue
        time.sleep(3.5)
    return _merge("turnover", "twse", out)


# ── 央行 ─────────────────────────────────────────────────────────────

def cbc_usdtwd() -> int:
    rows = json.loads(_get("https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day").decode("utf-8"))
    out = {}
    for r in rows or []:
        d, v = str(r.get("日期") or ""), r.get("NTD_USD")
        if re.match(r"^\d{8}$", d) and v not in (None, "", "-"):
            out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = float(v)
    return _merge("usdtwd", "cbc", out)


# ── 國發會、經濟部 ────────────────────────────────────────────────────

NDC_ZIP = ("https://ws.ndc.gov.tw/Download.ashx?u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUvNTc4MS82MzkyL2VhMjM1YmQ5LWQwNTItNGE2OS1hYmZjLWQ1Yzc4NWQzZDBlMi56aXA%3d"
           "&n=5pmv5rCj5oyH5qiZ5Y%2bK54eI6JmfLnppcA%3d%3d&icon=.zip")
NDC_PMI = ("https://ws.ndc.gov.tw/Download.ashx?u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUvNTc4MS82MzkxL2JmOGE0ZWI3LTEwZmUtNGZhMC1iNjQ2LTMwZTg5MGQwMjE4YS5jc3Y%3d"
           "&n=6Ie654Gj5o6h6LO857aT55CG5Lq65oyH5pW4KHBtaeWPim5taSkuY3N2&icon=.csv")


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return None


def ndc() -> int:
    zf = zipfile.ZipFile(io.BytesIO(_get(NDC_ZIP, timeout=90)))
    fn = next(n for n in zf.namelist() if n == "景氣指標與燈號.csv")
    txt = zf.read(fn).decode("utf-8-sig")
    out: dict = {}
    for ln in txt.splitlines()[1:]:
        c = [x.strip().strip('"') for x in ln.split(",")]
        if len(c) < 9 or not re.match(r"^\d{6}$", c[0]):
            continue
        ym = f"{c[0][:4]}-{c[0][4:]}"
        out[ym] = [_num(x) for x in c[1:8]] + [c[8] if c[8] not in ("-", "") else None]
    n = _merge("ndc", "ndc", out)
    first = HD.load("ndc_first")
    if not first:      # 第一次抓：現有月份都已是修正後的值，記成「回補」、不當作第一次公布的值
        _merge("ndc_first", "ndc", {ym: [None, "回補"] for ym in out})
    else:
        today = date.today().isoformat()
        _merge("ndc_first", "ndc", {ym: [v[6], today] for ym, v in out.items() if v[6] is not None and ym not in first})
    return n


def ndc_pmi() -> int:
    txt = _get(NDC_PMI, timeout=60).decode("utf-8-sig", "replace")
    out = {}
    for ln in txt.splitlines()[1:]:
        c = [x.strip() for x in ln.split(",")]
        if len(c) >= 2 and re.match(r"^\d{6}$", c[0]) and _num(c[1]) is not None:
            out[f"{c[0][:4]}-{c[0][4:]}"] = _num(c[1])
    return _merge("pmi", "ndc", out)


def moea_orders() -> int:
    url = "https://service.moea.gov.tw/EE520/opendata/" + urllib.parse.quote("經濟部統計處_外銷訂單_按地區分.csv")
    txt = _get(url, timeout=90).decode("utf-8-sig", "replace")
    out = {}
    for ln in txt.splitlines()[1:]:
        c = [x.strip() for x in ln.split(",")]
        if len(c) < 5 or c[1] != "00" or not re.match(r"^\d{5}$", c[3]):
            continue
        y, m = int(c[3][:3]) + 1911, int(c[3][3:])
        v = _num(c[4])
        if v is not None:
            out[f"{y:04d}-{m:02d}"] = v
    return _merge("orders", "moea", out)
