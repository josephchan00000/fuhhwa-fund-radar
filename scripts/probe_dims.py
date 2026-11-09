#!/usr/bin/env python3
"""面向指標盤查：新資料來源探針（docs/lab_dims_plan.md；只在 CI 跑、只印不存檔、不算任何指標值或成績）。

使用者 2026-11-08：「你的投資面向分數我覺得不夠完整，像是籌碼面應該還要加入融資維持率之類的吧？幫我深度盤查各面向應該要加入什麼指標」。
寫規格之前先知道哪些來源拿得到、從哪天起、多久一次：每個網址印 HTTP 狀態、大小、前幾行或欄位、找得到的最早／最晚日期。

  python3 scripts/probe_dims.py            # lab_backfill.yml 的 dimsprobe 模式（.ping/lab 第一行 dimsprobe）
  python3 scripts/probe_dims.py tw us      # 只跑某幾組
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TWCA = ROOT / "config" / "certs" / "twca_ssl_ca.pem"


def _ctx(tw: bool) -> ssl.SSLContext | None:
    if not tw:
        return None
    try:
        import certifi
        c = ssl.create_default_context(cafile=certifi.where())
        if TWCA.exists():
            c.load_verify_locations(cafile=str(TWCA))
        return c
    except Exception:                                     # noqa: BLE001
        return None


def get(url: str, tw: bool = False, timeout: int = 60, data: bytes | None = None, headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx(tw)) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()[:300]
        except Exception:                                 # noqa: BLE001
            return e.code, b""
    except Exception as e:                                # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}".encode()


DATE_RE = re.compile(rb"(19[5-9]\d|20[0-3]\d)[-/.]?(0[1-9]|1[0-2])(?:[-/.]?(0[1-9]|[12]\d|3[01]))?")
ROC_RE = re.compile(r"\b(\d{2,3})/(\d{2})/(\d{2})\b")


def show(title: str, url: str, tw: bool = False, n: int = 300, data: bytes | None = None, headers: dict | None = None) -> bytes:
    st, b = get(url, tw=tw, data=data, headers=headers)
    ds = sorted({m.group(0).decode()[:7].replace("/", "-").replace(".", "-") for m in DATE_RE.finditer(b[:5_000_000])})
    print(f"\n--- {title}\n    {url}\n    狀態 {st}，{len(b):,} bytes，年月 {ds[0] if ds else '—'} ～ {ds[-1] if ds else '—'}（{len(ds)} 個）", flush=True)
    txt = b[:n].decode("utf-8", "replace") if not b[:4] in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0") else f"(二進位檔 {b[:4]!r})"
    print("    " + txt.replace("\n", " ⏎ ")[:n], flush=True)
    return b


def head(t: str) -> None:
    print("\n" + "=" * 10, t, "=" * 10, flush=True)


def tw() -> None:
    head("台股：籌碼、資金、基本面的新來源")
    # 證交所 OpenAPI 目錄：找當沖、開戶、借券、本益比、投資人類別
    st, b = get("https://openapi.twse.com.tw/v1/swagger.json", tw=True)
    print(f"\n--- 證交所 OpenAPI 目錄 狀態 {st}，{len(b):,} bytes")
    try:
        doc = json.loads(b.decode("utf-8"))
        for p, v in (doc.get("paths") or {}).items():
            s = json.dumps(v, ensure_ascii=False)
            if any(k in s for k in ("當沖", "開戶", "借券", "本益比", "投資人", "自然人", "融資", "週轉", "市值")):
                summ = next((x.get("summary") for x in v.values() if isinstance(x, dict)), "")
                print(f"    {p}  {summ}")
    except Exception as e:                                # noqa: BLE001
        print("    解析失敗", e)
    for d in ("20140106", "20170502", "20261106"):
        show(f"證交所 當日沖銷交易統計 TWTB4U {d}", f"https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?date={d}&selectType=All&response=json", tw=True, n=500)
    for d in ("20050103", "20160104", "20261106"):
        show(f"證交所 融券借券賣出餘額 TWT93U {d}", f"https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date={d}&response=json", tw=True, n=400)
    show("證交所 融資融券彙總 MI_MARGN 2001-01-03（全市場）", "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=20010103&selectType=MS&response=json", tw=True, n=500)
    # 期交所：三大法人期貨、選擇權的最早一天；大額交易人
    for a, z in (("2007/07/02", "2007/07/31"), ("2012/01/02", "2012/01/31")):
        show(f"期交所 三大法人 期貨（臺指期）{a}", f"https://www.taifex.com.tw/cht/3/futContractsDateDown?queryStartDate={a}&queryEndDate={z}&commodityId=TXF", tw=True, n=400)
        show(f"期交所 三大法人 選擇權（臺指選）{a}", f"https://www.taifex.com.tw/cht/3/callsAndPutsDateDown?queryStartDate={a}&queryEndDate={z}&commodityId=TXO", tw=True, n=400)
    for a in ("2004/07/01", "2010/01/04", "2026/11/06"):
        show(f"期交所 大額交易人未沖銷部位（期貨）{a}", f"https://www.taifex.com.tw/cht/3/largeTraderFutDown?queryStartDate={a}&queryEndDate={a}", tw=True, n=500)
    # 國發會 PMI 檔：看裡面有沒有非製造業 NMI
    from arm.lab import heatfetch as HF
    show("國發會 PMI／NMI 下載檔", HF.NDC_PMI, tw=True, n=800)
    # 櫃買指數（Yahoo）
    show("Yahoo ^TWOII 櫃買指數", "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWOII?range=max&interval=1mo", n=300)
    # 央行統計資料庫：列舉表名找「劃撥」「證券」「交割」「重貼現」
    head("央行統計資料庫 DataAPI 表名")
    for pre, rng in (("EF", range(1, 81)), ("EG", range(1, 61)), ("EH", range(1, 21))):
        for i in rng:
            f = f"{pre}{i:02d}M01"
            st, b = get(f"https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={f}", tw=True, timeout=40)
            if st != 200 or len(b) < 50:
                continue
            t = b[:4000].decode("utf-8", "replace")
            names = re.findall(r'"(?:TableName|Title|title|Name)"\s*:\s*"([^"]+)"', t)[:2]
            hit = any(k in t for k in ("劃撥", "交割", "證券", "重貼現", "利率", "股價"))
            if hit or names:
                cols = re.findall(r'"([^"]{2,30})"', t)[:14]
                print(f"    {f}  {'★' if hit else ' '} {' / '.join(names)}  欄：{' | '.join(cols)[:220]}", flush=True)


def us() -> None:
    head("美股：情緒籌碼、資金、基本面的新來源")
    show("FINRA 融資餘額頁", "https://www.finra.org/finra-data/browse-catalog/margin-statistics", n=200)
    st, b = get("https://www.finra.org/finra-data/browse-catalog/margin-statistics")
    for u in sorted(set(re.findall(rb'href="([^"]+\.xlsx?)"', b)))[:5]:
        u = u.decode()
        u = u if u.startswith("http") else "https://www.finra.org" + u
        show("FINRA 融資餘額 Excel", u, n=120)
    show("AAII 散戶情緒調查 Excel", "https://www.aaii.com/files/surveys/sentiment.xls", n=120)
    st, b = get("https://naaim.org/programs/naaim-exposure-index/")
    print(f"\n--- NAAIM 頁 狀態 {st}，{len(b):,} bytes")
    for u in sorted(set(re.findall(rb'href="([^"]+\.(?:xlsx?|csv))"', b)))[:5]:
        show("NAAIM 經理人持股水位", u.decode(), n=120)
    show("CBOE 股票選擇權 P/C（2006～2019 檔）", "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv", n=300)
    show("CBOE 全部 P/C（檔）", "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/totalpc.csv", n=200)
    show("CBOE 每日市場統計 2026-11-06", "https://www.cboe.com/us/options/market_statistics/daily/?dt=2026-11-06", n=200)
    for s in ("%5ESKEW", "%5EVVIX", "%5EVIX9D"):
        show(f"Yahoo {s}", f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=max&interval=1mo", n=200)
    show("芝加哥聯準銀行 NFCI 金融情勢", "https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv", n=300)
    for sid in ("NFCI", "PERMIT", "PAYEMS", "BAMLH0A0HYM2", "DRTSCILM", "BOGZ1FL663067003Q", "TOTBKCR"):
        show(f"FRED {sid}", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", n=160)
    show("Baker–Wurgler 投資人情緒", "https://pages.stern.nyu.edu/~jwurgler/data/Investor_Sentiment_Data_20190327_POST.xlsx", n=80)
    show("DBnomics FED 搜尋 margin", "https://api.db.nomics.world/v22/search?q=margin%20debt&limit=5", n=600)


def nfci() -> None:
    """NFCI CSV 只到 2026-04-24（2026-11-09 回補看到）：找現行的下載檔、試加參數避開快取。"""
    import time as _t
    head("芝加哥聯準銀行 NFCI 現行下載檔")
    base = "https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv"
    for u in (base, f"{base}?v={int(_t.time())}", base.replace("-csv.csv", "-xlsx.xlsx"),
              "https://www.chicagofed.org/-/media/publications/nfci/nfci-indexes-recent.csv"):
        b = show("NFCI 檔", u, n=120)
        if b[:4] != b"PK\x03\x04":
            t = b.decode("utf-8", "replace").strip().splitlines()
            print("    最後兩列：", " ⏎ ".join(t[-2:])[:200], flush=True)
    for page in ("https://www.chicagofed.org/research/data/nfci/current-data",
                 "https://www.chicagofed.org/research/data/nfci/background",
                 "https://www.chicagofed.org/publications/nfci/index"):
        st, b = get(page)
        links = sorted(set(re.findall(rb'href="([^"]*(?:nfci|NFCI)[^"]*\.(?:csv|xlsx?|txt)[^"]*)"', b)))
        print(f"\n--- 頁 {page} 狀態 {st}，{len(b):,} bytes，連結 {len(links)} 個", flush=True)
        # 第 2 輪（2026-11-09）：頁面上沒有 href 連結 → 印出所有提到 nfci、csv、xlsx 的字串（含 JSON 裡的路徑）
        bits = sorted(set(re.findall(rb'[\w/\-.:%]*(?:nfci|NFCI)[\w/\-.:%?=&]*\.(?:csv|xlsx?|txt|json)[\w?=&.%-]*', b)))
        bits += sorted(set(re.findall(rb'/-/media/[\w/\-.%]+', b)))[:20]
        for x in bits[:30]:
            print("    字串：", x.decode("utf-8", "replace")[:160], flush=True)
        for m in re.findall(rb'(?:[A-Z][a-z]+ \d{1,2}, 20\d\d)', b)[:6]:
            print("    日期字樣：", m.decode(), flush=True)
        for u in links[:8]:
            u = u.decode()
            u = u if u.startswith("http") else "https://www.chicagofed.org" + u
            bb = show("  連結", u, n=80)
            if bb[:4] != b"PK\x03\x04":
                t = bb.decode("utf-8", "replace").strip().splitlines()
                print("    最後一列：", (t[-1] if t else "")[:160], flush=True)
    # 第 3 輪：頁面靠 fedrelease.js 載入資料 → 印出 JS 裡的網址與路徑
    st, b = get("https://www.chicagofed.org/-/media/admin/scripts/fedrelease/fedrelease.js")
    print(f"\n--- fedrelease.js 狀態 {st}，{len(b):,} bytes", flush=True)
    for x in sorted(set(re.findall(rb'(?:https?://[\w.\-/%?=&]+|/(?:api|-/media|data|research)[\w.\-/%?=&{}$]*)', b)))[:40]:
        print("    路徑：", x.decode("utf-8", "replace")[:160], flush=True)
    for m in re.finditer(rb'(?:ajax|fetch|getJSON|url)\s*[:(]\s*[^,;]{0,160}', b):
        print("    呼叫：", m.group(0).decode("utf-8", "replace")[:180], flush=True)
    show("DBnomics 搜尋 NFCI", "https://api.db.nomics.world/v22/search?q=NFCI&limit=5", n=800)
    show("DBnomics 搜尋 national financial conditions", "https://api.db.nomics.world/v22/search?q=national%20financial%20conditions&limit=5", n=800)


def nfci_browser() -> None:
    """第 4 輪（2026-11-09，使用者同意）：一般下載找不到現行資料 → 用無頭瀏覽器（runner 內建 Chrome）開現行網頁，
    記下它載入的每個資料請求（網址、狀態、類型、大小），內容提到 NFCI 或像資料表的印前面一段。只印不存。"""
    from playwright.sync_api import sync_playwright
    pages = ("https://www.chicagofed.org/research/data/nfci/current-data",
             "https://www.chicagofed.org/research/data/nfci/background")
    skip = re.compile(r"\.(?:png|jpe?g|gif|svg|woff2?|ttf|ico|css)(?:\?|$)|google|doubleclick|analytics|siteimprove|facebook|twitter|linkedin", re.I)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        for url in pages:
            print(f"\n=== 無頭瀏覽器開 {url}", flush=True)
            pg = b.new_page(user_agent=UA)
            seen = []

            def on_resp(r, seen=seen):
                if skip.search(r.url):
                    return
                ct = (r.headers or {}).get("content-type", "")
                try:
                    body = r.body() if r.request.resource_type in ("xhr", "fetch", "document", "other", "script") else b""
                except Exception:                         # noqa: BLE001
                    body = b""
                seen.append((r.url, r.status, ct, r.request.resource_type, body))
            pg.on("response", on_resp)
            try:
                pg.goto(url, wait_until="networkidle", timeout=90_000)
                pg.wait_for_timeout(8_000)
            except Exception as e:                        # noqa: BLE001
                print("  開頁失敗：", repr(e)[:300], flush=True)
            for u, st, ct, rt, body in seen:
                print(f"  {st} {rt:8s} {ct[:40]:40s} {len(body):>9,}  {u[:180]}", flush=True)
            for u, st, ct, rt, body in seen:
                t = body[:200_000].decode("utf-8", "replace")
                if rt in ("xhr", "fetch", "other") or re.search(r"(?i)nfci", u) or ("json" in ct or "csv" in ct):
                    if re.search(r"(?i)nfci|anfci|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}", t):
                        dates = re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}", t)
                        print(f"\n--- {u[:200]}（{len(body):,} bytes，日期 {len(dates)} 個，"
                              f"最早 {dates[0] if dates else '—'}、最後 {dates[-1] if dates else '—'}）", flush=True)
                        print("   ", t[:700].replace("\n", " | "), flush=True)
            try:
                txt = pg.inner_text("body")
                i = max(0, txt.find("NFCI") - 200)
                print("\n  頁面文字：", re.sub(r"\s+", " ", txt[i:i + 1500]), flush=True)
            except Exception as e:                        # noqa: BLE001
                print("  讀頁面文字失敗：", repr(e)[:200], flush=True)
            pg.close()
        b.close()


def main(argv: list[str]) -> int:
    groups = argv or ["tw", "us"]
    if "nfci" in groups:
        nfci()
    if "nfcib" in groups:
        nfci_browser()
    if "tw" in groups:
        tw()
    if "us" in groups:
        us()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
