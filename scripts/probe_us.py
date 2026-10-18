#!/usr/bin/env python3
"""美股景氣與泡沫模型的資料來源探針（docs/lab_heat_us_plan.md 第 10 節 U1；第二輪：芝加哥聯準銀行新位置、序列代碼、檔案欄位、台灣季 GDP）：只印診斷，不寫任何檔。

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


def links(page: str, pat: str = r'href="([^"]+)"', keep: str = r"(csv|xlsx?|amazonaws|cloudfront|s3\.|\.json)") -> str:
    html = get(page, timeout=90).decode("utf-8", "replace")
    ls = sorted({x for x in re.findall(pat, html, re.I) if re.search(keep, x, re.I)})
    return f"{len(html)} 字｜{len(ls)} 個：" + "；".join(ls[:14])


def tail_csv(url: str, n: int = 3) -> str:
    raw = get(url, timeout=90)
    txt = raw.decode("utf-8-sig", "replace")
    rows = [r for r in csv.reader(io.StringIO(txt)) if any(c.strip() for c in r)]
    return f"{len(rows)} 列｜表頭 {rows[0][:9] if rows else '—'}｜最後 {[r[:9] for r in rows[-n:]]}"


def oecd_cli() -> str:
    raw = get("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/USA.M.LI...AA...H"
              "?startPeriod=1950-01&format=csvfilewithlabels", timeout=120)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace"))))
    if not rows:
        return "0 列"
    tp = sorted((r.get("TIME_PERIOD"), r.get("OBS_VALUE")) for r in rows if r.get("TIME_PERIOD"))
    return f"{len(rows)} 列｜欄位 {list(rows[0])[:30]}｜{tp[:2]} … {tp[-3:]}"


def dbn_list(dataset: str, q: str, n: int = 30, w: int = 110) -> str:
    url = (f"https://api.db.nomics.world/v22/series/{dataset}?q={urllib.parse.quote(q)}&observations=0&limit={n}"
           if q else f"https://api.db.nomics.world/v22/series/{dataset}?observations=0&limit={n}")
    doc = json.loads(get(url, timeout=120).decode("utf-8"))
    docs = ((doc.get("series") or {}).get("docs")) or []
    tot = (doc.get("series") or {}).get("num_found")
    return f"共 {tot}｜" + "；".join(f"{d.get('series_code')}＝{str(d.get('series_name'))[:w]}" for d in docs[:n])


def shiller() -> str:
    html = get("https://shillerdata.com/", timeout=90).decode("utf-8", "replace")
    url = re.findall(r'href="([^"]+\.xls[^"]*)"', html, re.I)[0]
    import xlrd
    wb = xlrd.open_workbook(file_contents=get(url, timeout=120))
    sh = wb.sheet_by_name("Data")
    head = [sh.row_values(i)[:24] for i in range(0, 8)]
    last = [sh.row_values(i)[:24] for i in range(sh.nrows - 16, sh.nrows)]
    return f"{sh.nrows} 列｜前 8 列 {head}｜最後 16 列 {last}"


def wsts() -> str:
    html = get("https://www.wsts.org/67/Historical-Billings-Report", timeout=90).decode("utf-8", "replace")
    href = re.findall(r'href="([^"]+\.xlsx[^"]*)"', html, re.I)[0]
    url = href if href.startswith("http") else urllib.parse.urljoin("https://www.wsts.org/", href)
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(get(url, timeout=120)), read_only=True, data_only=True)
    out = [f"{url}｜工作表 {wb.sheetnames}"]
    for ws in wb.worksheets[:3]:
        rows = [list(r)[:16] for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c not in (None, "") for c in r)]
        out.append(f"[{ws.title}] {len(rows)} 列｜前 14 列 {rows[:14]}｜最後 3 列 {rows[-3:]}")
    return "｜".join(out)


def bls2(series: list[str], a: int, z: int) -> str:
    doc = F._post_json(F.BLS, {"seriesid": series, "startyear": str(a), "endyear": str(z)})
    out = [str(doc.get("status")), str(doc.get("message"))[:120]]
    for s in ((doc.get("Results") or {}).get("series")) or []:
        d = s.get("data") or []
        out.append(f"{s.get('seriesID')} {len(d)} 筆 {d[-1].get('year')}-{d[-1].get('period')}～{d[0].get('year')}-{d[0].get('period')}={d[0].get('value')}"
                   if d else f"{s.get('seriesID')} 0 筆")
    return "｜".join(out)


def dgbas(name: str) -> str:
    import urllib.request
    url = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230912/" + name
    req = urllib.request.Request(url, headers=F.BROWSER)
    with urllib.request.urlopen(req, timeout=120, context=F._twca_ctx()) as r:
        txt = r.read().decode("utf-8", "replace")
    obs = re.findall(r"<Obs>(.*?)</Obs>", txt, re.S)
    items = sorted({m for b in obs for m in re.findall(r"<Item>(.*?)</Item>", b)})
    tps = sorted({m for b in obs for m in re.findall(r"<TIME_PERIOD>(.*?)</TIME_PERIOD>", b)})
    types = sorted({m for b in obs for m in re.findall(r"<TYPE>(.*?)</TYPE>", b)})
    return (f"{len(txt)} 字 {len(obs)} 筆｜期間 {tps[:2]}…{tps[-2:]}｜TYPE {types[:8]}｜項目 {items[:16]}"
            f"｜第一筆 {obs[0][:300] if obs else txt[:300]!r}")


def fmtqik(ymd: str) -> str:
    doc = json.loads(get(f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={ymd}&response=json", timeout=40).decode("utf-8"))
    d = doc.get("data") or []
    return f"stat={doc.get('stat')}｜{len(d)} 列｜{d[:2]}"


def main() -> None:
    print("== 第二輪：芝加哥聯準銀行新下載位置 ==", flush=True)
    for pg in ("https://www.chicagofed.org/research/data/nfci/current-data-aws",
               "https://www.chicagofed.org/research/data/nfci/current-data",
               "https://www.chicagofed.org/research/data/cfnai/current-data",
               "https://www.chicagofed.org/research/data/cfnai/current-data-preview",
               "https://www.chicagofed.org/research/data/cfnai/cfnai-historical-data-preview",
               "https://www.chicagofed.org/research/data/index-live"):
        show(f"頁面 {pg.split('chicagofed.org')[1]}", lambda u=pg: links(u))
    for u in ("https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv",
              "https://www.chicagofed.org/-/media/publications/cfnai/cfnai-data-series-csv.csv",
              "https://www.chicagofed.org/-/media/publications/cfnai/cfnai-realtime-3-csv.csv"):
        show(f"舊 CSV 末列 {u.rsplit('/', 1)[1]}", lambda x=u: tail_csv(x))

    print("== OECD CLI 欄位 ==", flush=True)
    show("OECD CLI", oecd_cli)

    print("== DBnomics 序列代碼 ==", flush=True)
    show("H6 M2 資料集", lambda: dbn_list("FED/H6_H6_M2", "", 40, 90))
    show("H41 total assets", lambda: dbn_list("FED/H41", "Total assets", 30))
    show("H41 general account", lambda: dbn_list("FED/H41", "General Account", 20))
    show("H41 reverse repurchase", lambda: dbn_list("FED/H41", "Reverse repurchase agreements Wednesday level", 20))
    for p in ("FED/H15/RIFLGFCY02_N.B", "FED/H15/RIFSGFSM03_N.B", "FED/H15/RIFLGFCM03_N.B", "FED/Z1/LM793164105.Q",
              "FED/Z1/FL153067005.Q"):
        show(f"DBnomics {p}", lambda q=p: dbn(q))
    show("Z1 security credit", lambda: dbn_list("FED/Z1", "security credit", 30))
    show("Z1 margin", lambda: dbn_list("FED/Z1", "margin", 20))

    print("== Shiller 與 WSTS 檔案內容 ==", flush=True)
    show("Shiller", shiller)
    show("WSTS", wsts)

    print("== BLS 年份 ==", flush=True)
    show("BLS 2017–2026", lambda: bls2(["LNS14000000", "CUUR0000SA0L1E", "CUUR0000SA0"], 2017, 2026))
    show("BLS 1947–1956", lambda: bls2(["CUUR0000SA0", "LNS14000000", "CUUR0000SA0L1E"], 1947, 1956))

    print("== FINRA 直接檔案 ==", flush=True)
    for u in ("https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx",
              "https://www.finra.org/sites/default/files/Industry_Margin_Statistics.xlsx"):
        show(f"FINRA {u.rsplit('/', 1)[1]}", lambda x=u: f"{len(get(x, timeout=40))} bytes")

    print("== 台灣季 GDP（主計總處 XML） ==", flush=True)
    for nm in ("na8101a1q.xml", "na8101a2q.xml", "na8102a1q.xml", "na8104a1q.xml", "na8105a1q.xml",
               "na8101a8q.xml", "na8103a1q.xml"):
        show(f"DGBAS {nm}", lambda x=nm: dgbas(x))
    for did in range(6682, 6691):
        show(f"data.gov.tw {did}", lambda d=did: datagov(d))

    print("== 證交所 FMTQIK 最早 ==", flush=True)
    for ymd in ("19900101", "19950101", "19870101"):
        show(f"FMTQIK {ymd}", lambda x=ymd: fmtqik(x))
        time.sleep(3.5)


if __name__ == "__main__":
    main()
