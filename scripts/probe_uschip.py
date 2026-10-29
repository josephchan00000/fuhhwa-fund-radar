#!/usr/bin/env python3
"""美股各指數自己的籌碼：資料探針（docs/lab_us_chip_plan.md；只在 CI 跑、只印不存檔）。

寫 heatspec_us VER 3 之前要知道實際拿得到什麼（只看資料長什麼樣、有幾筆、從哪天起，不算任何指標值）：
  1. CFTC：E-mini 那斯達克 100（209742）交易者分類報告、傳統報告；大型那斯達克 100（209741）傳統報告——起訖日、筆數、欄位。
  2. Yahoo：六檔槓桿 ETF（SPXL、SPXS、TQQQ、SQQQ、SOXL、SOXS）日線的起始日、有沒有成交量。
  3. 槓桿 ETF 每日發行份數的歷史：ProShares、Direxion 幾個可能的下載網址（HTTP 狀態、前幾行）。
  4. SEC 內部人資料：每季資料集（2006Q1、最新一季）的壓縮檔、裡面的檔名與表頭；
     每日索引（最近一個工作天）有幾筆 Form 4；一份 Form 4 XML 的重要欄位；產業代碼 3674 的公司清單第一頁。
聯絡 email 只從 SEC_CONTACT_EMAIL 讀（arm/lab/secfin.py），不印、不存。

  python3 scripts/probe_uschip.py        # lab_backfill.yml 的 uschipprobe 模式（.ping/lab 第一行 uschipprobe）
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import secfin as SF  # noqa: E402

UA_WEB = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def get(url: str, headers: dict | None = None, timeout: int = 60, limit: int | None = None) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA_WEB, "Accept": "*/*", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read() if limit is None else r.read(limit)
            return r.status, b, r.headers.get("Content-Type") or ""
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400] if hasattr(e, "read") else b"", ""
    except Exception as e:                                # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}".encode(), ""


def head(title: str) -> None:
    print("\n" + "=" * 8, title, "=" * 8, flush=True)


def cftc() -> None:
    head("1. CFTC 那斯達克 100")
    base = "https://publicreporting.cftc.gov/resource/{ds}.json"
    jobs = [("gpe5-46if", "209742", "asset_mgr_positions_long,asset_mgr_positions_short,lev_money_positions_long,lev_money_positions_short"),
            ("6dca-aqww", "209742", "noncomm_positions_long_all,noncomm_positions_short_all"),
            ("6dca-aqww", "209741", "noncomm_positions_long_all,noncomm_positions_short_all"),
            ("gpe5-46if", "20974+", "asset_mgr_positions_long,asset_mgr_positions_short"),
            ("6dca-aqww", "20974+", "noncomm_positions_long_all,noncomm_positions_short_all")]
    for ds, code, cols in jobs:
        where = urllib.parse.quote(f"cftc_contract_market_code='{code}'")
        sel = urllib.parse.quote(f"report_date_as_yyyy_mm_dd,market_and_exchange_names,open_interest_all,{cols}")
        url = base.format(ds=ds) + f"?$select={sel}&$where={where}&$order=report_date_as_yyyy_mm_dd&$limit=50000"
        st, b, _ = get(url, timeout=120)
        try:
            rows = json.loads(b.decode("utf-8")) if st == 200 else []
        except Exception:                                 # noqa: BLE001
            rows = []
        print(f"{ds} {code}: HTTP {st}, {len(rows)} 筆", flush=True)
        if rows:
            print("  起", rows[0].get("report_date_as_yyyy_mm_dd"), rows[0].get("market_and_exchange_names"))
            print("  迄", rows[-1].get("report_date_as_yyyy_mm_dd"), {k: rows[-1].get(k) for k in cols.split(",") + ["open_interest_all"]})
            names = sorted({r.get("market_and_exchange_names") for r in rows})
            print("  名稱", names[:6])
        elif st != 200:
            print("  ", b[:200])


def yahoo() -> None:
    head("2. Yahoo 槓桿 ETF 日線")
    for sym in ("SPXL", "SPXS", "UPRO", "SPXU", "TQQQ", "SQQQ", "SOXL", "SOXS"):
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=0&period2={int(time.time())}"
               "&interval=1d&events=split")
        for _ in range(4):
            st, b, _ = get(url, timeout=60)
            if st != 429:
                break
            time.sleep(8)
        try:
            res = json.loads(b.decode("utf-8"))["chart"]["result"][0]
            ts = res.get("timestamp") or []
            q = (res.get("indicators") or {}).get("quote", [{}])[0]
            vol = [v for v in (q.get("volume") or []) if v]
            first = date.fromtimestamp(ts[0]).isoformat() if ts else None
            last = date.fromtimestamp(ts[-1]).isoformat() if ts else None
            spl = sorted(((res.get("events") or {}).get("splits") or {}).values(), key=lambda x: x.get("date", 0))
            print(f"{sym}: HTTP {st}, {len(ts)} 根 {first}～{last}，有成交量 {len(vol)} 根，分割 {[(date.fromtimestamp(s['date']).isoformat(), s.get('splitRatio')) for s in spl]}")
        except Exception as e:                            # noqa: BLE001
            print(f"{sym}: HTTP {st} 解析失敗 {type(e).__name__}: {b[:160]!r}")
        time.sleep(3)


def shares() -> None:
    head("3. 槓桿 ETF 發行份數的歷史（只看拿不拿得到）")
    cands = [
        "https://accounts.profunds.com/etfdata/ByFund/TQQQ-historical_nav.csv",
        "https://accounts.profunds.com/etfdata/ByFund/TQQQ-psdlyhld.csv",
        "https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq",
        "https://www.direxion.com/product/daily-semiconductor-bull-bear-3x-etfs",
        "https://www.direxion.com/holdings/SOXL.csv",
        "https://www.direxion.com/uploads/SOXL_NAV_History.csv",
    ]
    for f in ("TQQQ", "SQQQ", "UPRO", "SPXU", "USD", "SSG"):
        st, b, ct = get(f"https://accounts.profunds.com/etfdata/ByFund/{f}-historical_nav.csv", timeout=120)
        rows = [ln for ln in b.decode("utf-8", "replace").splitlines() if re.match(r"\d{1,2}/\d{1,2}/\d{4},", ln)]
        print(f"ProShares {f}: HTTP {st}，{len(rows)} 天，最新 {rows[0][:80] if rows else None}，最舊 {rows[-1][:80] if rows else None}")
    for u in cands:
        st, b, ct = get(u, timeout=60, limit=200000)
        txt = b.decode("utf-8", "replace")
        hit = [m for m in ("Shares Outstanding", "SharesOutstanding", "shares outstanding", "Outstanding", "historical", "History")
               if m in txt]
        print(f"{u}\n  HTTP {st} {ct} {len(b)} bytes 字樣 {hit}")
        print("  前段", re.sub(r"\s+", " ", txt[:300]))
        for m in re.finditer(r'href="([^"]*(?:nav|NAV|histor|History|csv)[^"]*)"', txt):
            print("  連結", m.group(1)[:160])


def sec() -> None:
    head("4. SEC 內部人資料")
    email = SF.contact()
    if not email:
        print("沒有 SEC_CONTACT_EMAIL，跳過")
        return
    h = {"User-Agent": SF._ua(email)}
    bases = ["https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip",
             "https://www.sec.gov/files/structureddata/data/form-345-data-sets/{q}_form345.zip"]
    today = date.today()
    qs = ["2006q1", "2015q2"]
    y, q = today.year, (today.month - 1) // 3 + 1
    for _ in range(3):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        qs.append(f"{y}q{q}")
    st, b, _ = get("https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets", headers=h, timeout=60)
    t0 = b.decode("utf-8", "replace")
    links = sorted(set(re.findall(r'href="([^"]*form345\.zip)"', t0)))
    print(f"資料集頁：HTTP {st}，壓縮檔連結 {len(links)} 個，例 {links[:2]} … {links[-2:]}")
    base = None
    for bb in bases:
        st, b, _ = get(bb.format(q=qs[-1]), headers=h, timeout=60, limit=4)
        print(f"  試 {bb.format(q=qs[-1])}: HTTP {st}")
        if st == 200:
            base = bb
            break
    if links and not base:
        base = "https://www.sec.gov" + re.sub(r"\d{4}q\d", "{q}", links[-1]) if links[-1].startswith("/") else re.sub(r"\d{4}q\d", "{q}", links[-1])
        print("  用頁面上的連結格式", base)
    for qq in (qs if base else []):
        st, b, ct = get(base.format(q=qq), headers=h, timeout=300)
        print(f"{qq}: HTTP {st} {ct} {len(b)} bytes", flush=True)
        if st == 200 and b[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(b))
            for n in z.namelist():
                with z.open(n) as f:
                    lines = [f.readline().decode("utf-8", "replace").rstrip() for _ in range(3)]
                print("  ", n, z.getinfo(n).file_size, "|", lines[0][:400])
                if n.upper().startswith(("NONDERIV_TRANS", "SUBMISSION", "REPORTINGOWNER")):
                    print("     例", lines[1][:400])
            if qq == qs[0]:
                with z.open([n for n in z.namelist() if n.upper().startswith("NONDERIV_TRANS")][0]) as f:
                    hd = f.readline().decode().rstrip("\n").split("\t")
                    ic = hd.index("TRANS_CODE") if "TRANS_CODE" in hd else None
                    cnt: dict = {}
                    for i, ln in enumerate(f):
                        if ic is None or i > 300000:
                            break
                        c = ln.decode("utf-8", "replace").split("\t")[ic]
                        cnt[c] = cnt.get(c, 0) + 1
                    print("   交易代碼次數", sorted(cnt.items(), key=lambda x: -x[1])[:12])
        time.sleep(0.5)
    # 每日索引（最近一個平日）
    d = today - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    for k in range(5):
        dd = d - timedelta(days=k)
        if dd.weekday() >= 5:
            continue
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{dd.year}/QTR{(dd.month - 1) // 3 + 1}/form.{dd:%Y%m%d}.idx"
        st, b, _ = get(url, headers=h, timeout=120)
        txt = b.decode("latin-1")
        f4 = [ln for ln in txt.splitlines() if ln.startswith("4 ")]
        print(f"每日索引 {dd}: HTTP {st}，Form 4 {len(f4)} 行")
        if f4:
            print("   例", f4[0][:200])
            print("   例", f4[1][:200] if len(f4) > 1 else "")
            path = f4[0].split()[-1]
            m = re.search(r"edgar/data/(\d+)/([\d-]+)\.txt", path)
            if m:
                acc = m.group(2).replace("-", "")
                idx_url = f"https://www.sec.gov/Archives/edgar/data/{m.group(1)}/{acc}/index.json"
                st2, b2, _ = get(idx_url, headers=h, timeout=60)
                print("   目錄", st2, b2[:300])
                try:
                    items = json.loads(b2.decode())["directory"]["item"]
                    xml = [i["name"] for i in items if i["name"].endswith(".xml")]
                    if xml:
                        st3, b3, _ = get(f"https://www.sec.gov/Archives/edgar/data/{m.group(1)}/{acc}/{xml[0]}", headers=h, timeout=60)
                        t3 = b3.decode("utf-8", "replace")
                        for tag in ("issuerCik", "issuerTradingSymbol", "isDirector", "isOfficer", "isTenPercentOwner",
                                    "transactionCode", "transactionShares", "transactionAcquiredDisposedCode", "transactionDate"):
                            mm = re.search(rf"<{tag}>\s*(?:<value>)?\s*([^<]*)", t3)
                            print(f"     {tag}: {mm.group(1).strip() if mm else None}")
                except Exception as e:                    # noqa: BLE001
                    print("   XML 失敗", type(e).__name__, e)
            break
        time.sleep(0.3)
    # 產業代碼 3674
    allc = []
    for start in range(0, 2000, 100):
        url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC=3674&type=&dateb=&owner=include"
               f"&start={start}&count=100&output=atom")
        st, b, ct = get(url, headers=h, timeout=60)
        txt = b.decode("utf-8", "replace")
        ciks = re.findall(r"<cik>(\d+)</cik>", txt) or re.findall(r"CIK=(\d{10})", txt)
        allc += ciks
        if start == 0:
            print("   第一筆", re.sub(r"\s+", " ", txt[txt.find("<entry"):txt.find("<entry") + 600]))
        if len(ciks) < 100:
            break
        time.sleep(0.3)
    print(f"SIC 3674：共 {len(allc)} 個 CIK（不重複 {len(set(allc))}）")


def main() -> int:
    only = sys.argv[1:] or ["cftc", "yahoo", "shares", "sec"]
    for f in (cftc, yahoo, shares, sec):
        if f.__name__ not in only:
            continue
        try:
            f()
        except Exception as e:                            # noqa: BLE001
            print(f"[{f.__name__}] 例外 {type(e).__name__}: {e}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
