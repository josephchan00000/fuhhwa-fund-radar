#!/usr/bin/env python3
"""美股景氣與泡沫模型的資料來源探針（docs/lab_heat_us_plan.md 第 10 節 U1）：只印診斷，不寫任何檔。

在 lab_backfill.yml 用 .ping/lab 第一行 `usprobe` 觸發；本容器擋這些站，結果只看 CI 日誌。
每一項印：成功與否、筆數、起訖日期或檔案大小、必要時印一小段原文，讓下一步一輪就能寫抓取程式。
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import heatfetch as F  # noqa: E402
from arm.lab.market import yahoo_hist_from  # noqa: E402


def show(tag: str, fn) -> None:
    t = time.time()
    try:
        msg = fn()
        print(f"✓ {tag}: {msg} （{time.time() - t:.1f} 秒）", flush=True)
    except Exception as e:                                   # noqa: BLE001
        print(f"✗ {tag}: {type(e).__name__} {str(e)[:300]} （{time.time() - t:.1f} 秒）", flush=True)


def get(url: str, timeout: int = 90, headers: dict | None = None) -> bytes:
    return F._get(url, timeout=timeout, headers=headers)


def snip(b: bytes, n: int = 240) -> str:
    return b[:n].decode("utf-8", "replace").replace("\n", "⏎ ")


# ── 1. Yahoo：指數與 ETF 的日線起點 ──────────────────────────────────────

def yh(sym: str) -> str:
    h = yahoo_hist_from(sym, "1900-01-01")
    ks = sorted(h)
    if not ks:
        return "0 筆"
    return f"{len(ks)} 筆 {ks[0]}～{ks[-1]} 末收 {h[ks[-1]][3]}；量 {h[ks[-1]][4]}"


# ── 2. CSV 類：印表頭、第一列、最後一列 ─────────────────────────────────

def csv_head_tail(url: str, headers: dict | None = None) -> str:
    raw = get(url, headers=headers)
    txt = raw.decode("utf-8-sig", "replace")
    rows = [r for r in csv.reader(io.StringIO(txt)) if any(c.strip() for c in r)]
    if not rows:
        return f"0 列（{len(raw)} bytes）{snip(raw)}"
    return f"{len(rows)} 列 {len(raw)} bytes｜表頭 {rows[0][:8]}｜第一列 {rows[1][:8] if len(rows) > 1 else '—'}｜最後 {rows[-1][:8]}"


# ── 3. CFTC Socrata ────────────────────────────────────────────────────

def cftc(dataset: str, code: str) -> str:
    base = f"https://publicreporting.cftc.gov/resource/{dataset}.json"
    w = urllib.parse.quote(f"cftc_contract_market_code='{code}'")
    last = json.loads(get(f"{base}?$limit=1&$order=report_date_as_yyyy_mm_dd%20DESC&$where={w}").decode("utf-8"))
    first = json.loads(get(f"{base}?$limit=1&$order=report_date_as_yyyy_mm_dd%20ASC&$where={w}").decode("utf-8"))
    cnt = json.loads(get(f"{base}?$select=count(*)&$where={w}").decode("utf-8"))
    if not last:
        return "0 列"
    keys = [k for k in last[0] if re.search(r"(asset_mgr|lev_money|noncomm|open_interest_all|market_and_exchange)", k)]
    return (f"{cnt[0] if cnt else '?'} 筆 {str(first[0].get('report_date_as_yyyy_mm_dd'))[:10]}～"
            f"{str(last[0].get('report_date_as_yyyy_mm_dd'))[:10]}｜{last[0].get('market_and_exchange_names')}｜"
            f"欄位 {keys[:14]}")


# ── 4. BLS v1 POST ──────────────────────────────────────────────────────

def bls(series: list[str]) -> str:
    doc = F._post_json(F.BLS, {"seriesid": series, "startyear": "2016", "endyear": "2025"})
    out = [str(doc.get("status"))]
    for s in ((doc.get("Results") or {}).get("series")) or []:
        d = s.get("data") or []
        out.append(f"{s.get('seriesID')} {len(d)} 筆 最新 {d[0].get('year')}-{d[0].get('period')}={d[0].get('value')}" if d else f"{s.get('seriesID')} 0 筆")
    return "｜".join(out)


# ── 5. DBnomics ────────────────────────────────────────────────────────

def dbn(path: str) -> str:
    doc = json.loads(get(F.DBN.format(p=path), timeout=120).decode("utf-8"))
    docs = ((doc.get("series") or {}).get("docs")) or []
    if not docs:
        return "沒有序列"
    s = docs[0]
    per = s.get("period") or []
    val = s.get("value") or []
    return f"{len(per)} 期 {per[0] if per else '—'}～{per[-1] if per else '—'} 末值 {val[-1] if val else '—'}｜{str(s.get('series_name'))[:90]}"


def dbn_search(q: str, provider: str = "FED") -> str:
    url = f"https://api.db.nomics.world/v22/search?q={urllib.parse.quote(q)}&limit=8"
    doc = json.loads(get(url, timeout=90).decode("utf-8"))
    hits = (doc.get("results") or {}).get("docs") or []
    out = [f"{h.get('provider_code')}/{h.get('code')} {str(h.get('name'))[:50]} ({h.get('nb_series')})"
           for h in hits if not provider or h.get("provider_code") == provider]
    return "；".join(out[:8]) or f"沒有 {provider} 的結果（全部 {len(hits)} 筆）"


def dbn_series_list(dataset: str, q: str) -> str:
    url = f"https://api.db.nomics.world/v22/series/{dataset}?q={urllib.parse.quote(q)}&observations=0&limit=10"
    doc = json.loads(get(url, timeout=120).decode("utf-8"))
    docs = ((doc.get("series") or {}).get("docs")) or []
    return "；".join(f"{d.get('series_code')} {str(d.get('series_name'))[:70]}" for d in docs[:10]) or "沒有序列"


# ── 6. 頁面裡找檔案連結再下載（Shiller、FINRA、WSTS） ───────────────────────

def page_file(page: str, pat: str, base: str = "") -> str:
    html = get(page, timeout=90).decode("utf-8", "replace")
    links = re.findall(pat, html, re.I)
    if not links:
        return f"頁面 {len(html)} 字，找不到檔案連結；片段：{html[:200]!r}"
    url = links[0] if links[0].startswith("http") else urllib.parse.urljoin(base or page, links[0])
    raw = get(url, timeout=120)
    magic = raw[:8].hex()
    kind = "xls(OLE2)" if magic.startswith("d0cf11e0") else "xlsx/zip" if raw[:2] == b"PK" else "其他"
    extra = ""
    if kind == "xls(OLE2)":
        try:
            import xlrd                                       # 只在探針用；正式抓取再決定
            wb = xlrd.open_workbook(file_contents=raw)
            sh = wb.sheet_by_index(0) if wb.nsheets == 1 else next(
                (wb.sheet_by_name(n) for n in wb.sheet_names() if n.lower() == "data"), wb.sheet_by_index(0))
            rows = [sh.row_values(i) for i in range(min(sh.nrows, 12))]
            extra = f"｜工作表 {wb.sheet_names()}｜{sh.nrows} 列｜前幾列 {[r[:6] for r in rows[5:10]]}｜最後 {sh.row_values(sh.nrows - 1)[:6]}"
        except Exception as e:                               # noqa: BLE001
            extra = f"｜xlrd 讀不了：{type(e).__name__} {str(e)[:120]}"
    return f"連結 {len(links)} 個，第一個 {url}｜{len(raw)} bytes {kind}{extra}"


# ── 7. 政府資料開放平台（台股 GDP） ───────────────────────────────────────

def datagov(did: int) -> str:
    doc = json.loads(get(f"https://data.gov.tw/api/v2/rest/dataset/{did}", timeout=60).decode("utf-8"))
    r = doc.get("result") or doc
    name = r.get("title") or r.get("name") or r.get("dataset_name")
    dist = r.get("distribution") or r.get("resources") or []
    urls = [f"{d.get('resourceFormat') or d.get('format')}:{d.get('resourceDownloadUrl') or d.get('url')}" for d in dist][:4]
    return f"{name}｜{urls}"


def main() -> None:
    print("== Yahoo 日線起點 ==", flush=True)
    for sym in ("^GSPC", "^IXIC", "^NDX", "^SOX", "^VIX", "^VXN", "^VIX3M", "DX-Y.NYB", "RSP", "SPY",
                "^SPXEW", "^W5000", "^FTW5000", "^NYA", "QQQ", "SOXX", "^TNX", "^IRX"):
        show(f"Yahoo {sym}", lambda s=sym: yh(s))

    print("== Cboe ==", flush=True)
    for sym in ("VIX", "VIX3M", "VXN", "VVIX", "SKEW"):
        show(f"Cboe {sym}", lambda s=sym: csv_head_tail(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{s}_History.csv"))

    print("== CFTC ==", flush=True)
    for ds, code, nm in (("gpe5-46if", "13874A", "TFF E-mini S&P"), ("gpe5-46if", "209742", "TFF E-mini NDX"),
                         ("6dca-aqww", "13874A", "Legacy E-mini S&P"), ("6dca-aqww", "138741", "Legacy S&P 大型"),
                         ("6dca-aqww", "209742", "Legacy E-mini NDX")):
        show(f"CFTC {nm}", lambda d=ds, c=code: cftc(d, c))

    print("== 美國總經 ==", flush=True)
    show("費城聯準 bos_dif", lambda: csv_head_tail(
        "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/MBOS/Historical-Data/Diffusion-Indexes/bos_dif.csv"))
    show("勞工部 初領 ar539", lambda: csv_head_tail("https://oui.doleta.gov/unemploy/csv/ar539.csv"))
    show("BLS 失業率／核心 CPI／非農", lambda: bls(["LNS14000000", "CUUR0000SA0L1E", "CES0000000001"]))
    show("密大消費者信心", lambda: csv_head_tail("https://www.sca.isr.umich.edu/files/tbmics.csv"))
    show("芝加哥聯準 NFCI", lambda: csv_head_tail("https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv"))
    show("芝加哥聯準 CFNAI", lambda: csv_head_tail("https://www.chicagofed.org/-/media/publications/cfnai/cfnai-data-series-csv.csv"))
    show("聯準會 EBP", lambda: csv_head_tail("https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv"))
    show("OECD CLI 美國", lambda: csv_head_tail(
        "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/USA.M.LI...AA...H"
        "?startPeriod=1950-01&format=csvfilewithlabels"))
    show("財政部 TGA", lambda: snip(get(
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
        "?sort=-record_date&page%5Bsize%5D=3"), 400))
    show("紐約聯準 逆回購", lambda: snip(get(
        "https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json?startDate=2024-01-02&endDate=2024-01-05"), 300))

    print("== DBnomics ==", flush=True)
    for p in ("FED/Z1/LM893064105.Q", "FED/Z1/LM103164103.Q", "FED/Z1/LM103164105.Q", "FED/Z1/FL102090005.Q",
              "BEA/NIPA-T10105/A191RC-Q", "FED/H15/RIFLGFCY10_N.B", "FED/H15/RIFLGFCM03_N.B", "FED/H15/RIFLGFCY10_N.M"):
        show(f"DBnomics {p}", lambda q=p: dbn(q))
    show("DBnomics 找 M2", lambda: dbn_search("M2 money stock"))
    show("DBnomics 找 H.4.1", lambda: dbn_search("H.4.1 factors affecting reserve balances"))
    show("DBnomics H6 序列", lambda: dbn_series_list("FED/H6", "M2"))
    show("DBnomics H41 序列（總資產）", lambda: dbn_series_list("FED/H41", "total assets"))
    show("DBnomics H41 序列（財政部存款）", lambda: dbn_series_list("FED/H41", "treasury general account"))
    show("DBnomics H41 序列（逆回購）", lambda: dbn_series_list("FED/H41", "reverse repurchase"))

    print("== 估值、融資、半導體 ==", flush=True)
    show("Shiller 資料檔", lambda: page_file("https://shillerdata.com/", r'href="([^"]+\.xls[^"]*)"'))
    show("FINRA 融資", lambda: page_file("https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics",
                                         r'href="([^"]+\.xlsx[^"]*)"', "https://www.finra.org/"))
    show("WSTS 半導體銷售", lambda: page_file("https://www.wsts.org/67/Historical-Billings-Report",
                                          r'href="([^"]+\.xlsx[^"]*)"', "https://www.wsts.org/"))

    print("== 台股 GDP（政府資料開放平台） ==", flush=True)
    for did in (6691, 6692, 6693, 6694, 6695, 6696, 6697, 6698, 6699, 6700):
        show(f"data.gov.tw {did}", lambda d=did: datagov(d))


if __name__ == "__main__":
    main()
