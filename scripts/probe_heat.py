#!/usr/bin/env python3
"""景氣溫度頁 H0 探針（docs/lab_heat_plan.md 第 8 節）：逐一確認各資料來源能不能從 CI 抓、格式、歷史起點。

只在 CI 跑（本容器的 proxy 擋這些站）：`.ping/lab` 第一行寫 `probeheat`。
結果印進日誌，並寫 data/lab/heat_probe.json（lab_backfill.yml 會 commit 回分支）；合併前刪掉。
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.parse
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.http import get_bytes  # noqa: E402

OUT = ROOT / "data" / "lab" / "heat_probe.json"
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TODAY = date.today()
RES: dict[str, dict] = {}


def log(msg: str) -> None:
    print(msg, flush=True)


def rec(name: str, **kw) -> None:
    RES[name] = kw
    brief = {k: v for k, v in kw.items() if k not in ("head", "tail")}
    log(f"[heat-probe] {name}: {json.dumps(brief, ensure_ascii=False)[:600]}")
    for k in ("head", "tail"):
        if kw.get(k):
            log(f"    {k}: {str(kw[k])[:700]}")


def get(url: str, *, headers: dict | None = None, timeout: int = 60) -> bytes:
    return get_bytes(url, retries=1, timeout=timeout, use_cache=False, headers=headers)


def post(url: str, form: dict, *, timeout: int = 60) -> bytes:
    import ssl
    import urllib.request

    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), headers={
        **BROWSER, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def guard(name: str, fn) -> None:
    t0 = time.time()
    try:
        fn()
    except Exception as e:                                    # noqa: BLE001 —— 每個探針各自失敗
        rec(name, ok=False, err=f"{type(e).__name__}: {str(e)[:300]}")
    log(f"    （{time.time() - t0:.1f}s）")


# ---------- FinMind（免費、未登入每小時約 300 次） ----------
FM = "https://api.finmindtrade.com/api/v4/data?dataset={ds}{did}&start_date={a}&end_date={z}"


def finmind(name: str, ds: str, did: str = "", a: str = "2000-01-01", z: str | None = None) -> None:
    def run():
        url = FM.format(ds=ds, did=f"&data_id={did}" if did else "", a=a, z=z or TODAY.isoformat())
        doc = json.loads(get(url).decode("utf-8"))
        rows = doc.get("data") or []
        dates = sorted({str(r.get("date"))[:10] for r in rows if r.get("date")})
        rec(name, ok=bool(rows), status=doc.get("status"), msg=str(doc.get("msg"))[:120], n=len(rows),
            first=dates[0] if dates else None, last=dates[-1] if dates else None, days=len(dates),
            keys=list(rows[0].keys()) if rows else None,
            head=rows[:3], tail=rows[-3:])
    guard(name, run)


# ---------- 期交所（POST → Big5 CSV） ----------
def taifex(name: str, path: str, form: dict) -> None:
    def run():
        b = post(f"https://www.taifex.com.tw/cht/3/{path}", form)
        txt = b.decode("cp950", "replace")
        lines = [ln for ln in txt.splitlines() if ln.strip()]
        is_html = txt.lstrip()[:15].lower().startswith(("<!doctype", "<html"))
        dates = sorted({m.group(0) for ln in lines for m in [re.match(r"\d{4}/\d{1,2}/\d{1,2}", ln)] if m})
        rec(name, ok=bool(dates) and not is_html, bytes=len(b), html=is_html, lines=len(lines),
            first=dates[0] if dates else None, last=dates[-1] if dates else None, days=len(dates),
            head=lines[:4], tail=lines[-2:])
    guard(name, run)


def taifex_get(name: str, url: str, enc: str = "utf-8") -> None:
    def run():
        b = get(url, headers=BROWSER)
        txt = b.decode(enc, "replace")
        dates = sorted(set(re.findall(r"20\d\d[/-]\d{2}[/-]\d{2}", txt)))
        lines = [ln for ln in txt.splitlines() if ln.strip()]
        rec(name, ok=bool(dates), bytes=len(b), lines=len(lines),
            first=dates[0] if dates else None, last=dates[-1] if dates else None, days=len(dates),
            head=lines[:4], tail=lines[-3:])
    guard(name, run)


# ---------- 證交所／櫃買（GET JSON；證交所 www 端要放慢） ----------
def twse(name: str, url: str, want: str | None = None) -> None:
    def run():
        b = get(url, headers=BROWSER)
        time.sleep(3.5)
        doc = json.loads(b.decode("utf-8"))
        info = {"stat": doc.get("stat") if isinstance(doc, dict) else None, "bytes": len(b)}
        tabs = doc.get("tables") if isinstance(doc, dict) else None
        if tabs:
            info["tables"] = [(t.get("title"), len(t.get("data") or []), (t.get("fields") or [])[:8]) for t in tabs]
            if want:
                for t in tabs:
                    if want in str(t.get("title")):
                        info["want"] = {"fields": t.get("fields"), "data": (t.get("data") or [])[:8]}
        else:
            info["keys"] = list(doc.keys())[:12] if isinstance(doc, dict) else None
            info["fields"] = doc.get("fields") if isinstance(doc, dict) else None
            data = doc.get("data") if isinstance(doc, dict) else None
            info["n"] = len(data) if data else 0
            info["head"] = (data or [])[:3]
            info["tail"] = (data or [])[-2:]
        rec(name, ok=True, **info)
    guard(name, run)


def plain(name: str, url: str, *, headers: dict | None = None, enc: str = "utf-8") -> None:
    """CSV／JSON 純文字：印行數、頭尾、日期範圍。"""
    def run():
        b = get(url, headers=headers or BROWSER)
        txt = b.decode(enc, "replace").lstrip("﻿")
        lines = [ln for ln in txt.splitlines() if ln.strip()]
        dates = sorted(set(re.findall(r"(?:19|20)\d\d[-/]?\d{2}(?:[-/]?\d{2})?", txt)))
        rec(name, ok=bool(lines) and not txt.lstrip()[:15].lower().startswith(("<!doctype", "<html")),
            bytes=len(b), lines=len(lines), first=dates[0] if dates else None,
            last=dates[-1] if dates else None, head=lines[:4], tail=lines[-3:])
    guard(name, run)


def ndc_zip(name: str, url: str) -> None:
    def run():
        b = get(url, headers=BROWSER, timeout=90)
        zf = zipfile.ZipFile(io.BytesIO(b))
        info = {"bytes": len(b), "files": zf.namelist()}
        for fn in zf.namelist():
            raw = zf.read(fn)
            for enc in ("utf-8-sig", "cp950"):
                try:
                    txt = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    txt = None
            lines = [ln for ln in (txt or "").splitlines() if ln.strip()]
            info[fn] = {"lines": len(lines), "head": lines[:3], "tail": lines[-2:]}
        rec(name, ok=True, **info)
    guard(name, run)


def yahoo_long(name: str, sym: str) -> None:
    def run():
        p1 = int(datetime(1990, 1, 1).timestamp())
        p2 = int(time.time())
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
               f"?period1={p1}&period2={p2}&interval=1d")
        doc = json.loads(get(url, headers=BROWSER).decode("utf-8"))
        res = ((doc.get("chart") or {}).get("result") or [None])[0] or {}
        ts = res.get("timestamp") or []
        q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        ds = [datetime.fromtimestamp(t, timezone.utc).date().isoformat() for t in ts]
        rec(name, ok=bool(ts), n=len(ts), first=ds[0] if ds else None, last=ds[-1] if ds else None,
            gran=(res.get("meta") or {}).get("dataGranularity"),
            head=list(zip(ds[:3], (q.get("close") or [])[:3])), tail=list(zip(ds[-3:], (q.get("close") or [])[-3:])))
    guard(name, run)


def main() -> None:
    t0 = time.time()
    d_recent = "20261016"
    # FinMind
    finmind("FinMind 融資融券合計", "TaiwanStockTotalMarginPurchaseShortSale")
    finmind("FinMind 三大法人合計", "TaiwanStockTotalInstitutionalInvestors")
    finmind("FinMind 期貨法人 TX", "TaiwanFuturesInstitutionalInvestors", "TX")
    finmind("FinMind 期貨法人 MTX", "TaiwanFuturesInstitutionalInvestors", "MTX")
    finmind("FinMind 期貨法人 TMF", "TaiwanFuturesInstitutionalInvestors", "TMF")
    finmind("FinMind 選擇權法人 TXO", "TaiwanOptionInstitutionalInvestors", "TXO")
    finmind("FinMind 期貨日行情 MTX（2018-01）", "TaiwanFuturesDaily", "MTX", "2018-01-01", "2018-01-31")
    finmind("FinMind 期貨日行情 MTX（全期）", "TaiwanFuturesDaily", "MTX", "2005-01-01")
    finmind("FinMind 選擇權日行情 TXO（1 天）", "TaiwanOptionDaily", "TXO", "2026-10-15", "2026-10-15")
    finmind("FinMind 匯率 USD", "TaiwanExchangeRate", "USD")
    finmind("FinMind 利率 FED", "InterestRate", "FED")
    finmind("FinMind 報酬指數 TAIEX", "TaiwanStockTotalReturnIndex", "TAIEX")
    finmind("FinMind 景氣燈號（付費？）", "TaiwanBusinessIndicator")
    finmind("FinMind 台指 VIX（付費？）", "TaiwanOptionVix")
    finmind("FinMind CNN 恐懼貪婪（付費？）", "CnnFearGreedIndex")
    finmind("FinMind 融資維持率（付費？）", "TaiwanTotalExchangeMarginMaintenance")
    # 期交所：近期與舊日期（找出網站給的歷史窗）
    for a, z in (("2015/01/02", "2015/01/31"), ("2022/01/03", "2022/01/28"), ("2023/11/01", "2023/11/30"),
                 ("2026/10/01", "2026/10/16")):
        taifex(f"期交所 P/C {a[:7]}", "pcRatioDown", {"queryStartDate": a, "queryEndDate": z})
    for a, z in (("2018/01/02", "2018/01/31"), ("2023/11/01", "2023/11/30"), ("2026/10/01", "2026/10/16")):
        taifex(f"期交所 期貨法人 TXF {a[:7]}", "futContractsDateDown",
               {"queryStartDate": a, "queryEndDate": z, "commodityId": "TXF"})
    taifex("期交所 期貨法人 MXF 2026-10", "futContractsDateDown",
           {"queryStartDate": "2026/10/01", "queryEndDate": "2026/10/16", "commodityId": "MXF"})
    taifex("期交所 期貨法人 TMF 2026-10", "futContractsDateDown",
           {"queryStartDate": "2026/10/01", "queryEndDate": "2026/10/16", "commodityId": "TMF"})
    for a, z in (("2022/01/03", "2022/01/28"), ("2026/10/01", "2026/10/16")):
        taifex(f"期交所 選擇權買賣權法人 {a[:7]}", "callsAndPutsDateDown",
               {"queryStartDate": a, "queryEndDate": z, "commodityId": "TXO"})
    for a, z in (("2022/01/03", "2022/01/28"), ("2026/09/01", "2026/09/30")):
        taifex(f"期交所 小台日行情 {a[:7]}", "futDataDown",
               {"down_type": "1", "commodity_id": "MTX", "queryStartDate": a, "queryEndDate": z})
    taifex("期交所 大額交易人 2026-10", "largeTraderFutDown",
           {"queryStartDate": "2026/10/01", "queryEndDate": "2026/10/16"})
    taifex_get("期交所 台指 VIX 近 3 個月", "https://www.taifex.com.tw/cht/7/vixDaily3MNew")
    for ym in ("202609", "202606", "202501"):
        taifex_get(f"期交所 台指 VIX 月檔 {ym}",
                   f"https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{ym}new.txt", enc="cp950")
    # 證交所／櫃買
    twse("證交所 融資融券合計 近期", f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d_recent}&selectType=MS&response=json")
    twse("證交所 融資融券合計 2005", "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=20050103&selectType=MS&response=json")
    twse("證交所 漲跌家數 近期", f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={d_recent}&type=MS&response=json", want="漲跌")
    twse("證交所 漲跌家數 2005", "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20050103&type=MS&response=json", want="漲跌")
    twse("證交所 每日市場成交 2000-01", "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=20000101&response=json")
    twse("證交所 每日市場成交 近期", f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={d_recent}&response=json")
    twse("證交所 本益比殖利率 近期", f"https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={d_recent}&selectType=ALL&response=json")
    twse("證交所 三大法人金額 2005", "https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate=20050103&response=json")
    plain("櫃買 融資融券 近期", "https://www.tpex.org.tw/www/zh-tw/margin/balance?date=2026/10/16&response=json")
    plain("櫃買 市場概況 近期", "https://www.tpex.org.tw/www/zh-tw/afterTrading/highlight?date=2026/10/16&response=json")
    # 央行
    plain("央行 新台幣每日收盤", "https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day")
    plain("央行 M1B M2（EF15M01）", "https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=EF15M01")
    # 國發會
    ndc_zip("國發會 景氣指標與燈號 ZIP", "https://ws.ndc.gov.tw/Download.ashx?u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUvNTc4MS82MzkyL2VhMjM1YmQ5LWQwNTItNGE2OS1hYmZjLWQ1Yzc4NWQzZDBlMi56aXA%3d&n=5pmv5rCj5oyH5qiZ5Y%2bK54eI6JmfLnppcA%3d%3d&icon=.zip")
    plain("國發會 PMI CSV", "https://ws.ndc.gov.tw/Download.ashx?u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUvNTc4MS82MzkxL2JmOGE0ZWI3LTEwZmUtNGZhMC1iNjQ2LTMwZTg5MGQwMjE4YS5jc3Y%3d&n=6Ie654Gj5o6h6LO857aT55CG5Lq65oyH5pW4KHBtaeWPim5taSkuY3N2&icon=.csv")
    # 主計總處 CPI（憑證鏈可能缺中繼憑證：失敗就記下錯誤，不關掉驗證）
    plain("主計總處 CPI XML", "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml")
    # 經濟部外銷訂單、關務署出口
    plain("經濟部 外銷訂單 CSV", "https://service.moea.gov.tw/EE520/opendata/"
          + urllib.parse.quote("經濟部統計處_外銷訂單_按地區分.csv"))
    plain("關務署 出口 CSV", "https://opendata.customs.gov.tw/data/6053/csv.csv")
    # FRED（免金鑰 CSV）
    for sid in ("VIXCLS", "DFF", "CPIAUCSL", "T10Y2Y", "BAA10Y", "DEXTAUS", "BAMLH0A0HYM2"):
        plain(f"FRED {sid}", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}")
    # 加權指數長歷史
    yahoo_long("Yahoo ^TWII 1990 起", "^TWII")
    yahoo_long("Yahoo TWD=X 1990 起", "TWD=X")
    OUT.write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "res": RES},
                              ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ok = sum(1 for v in RES.values() if v.get("ok"))
    log(f"[heat-probe] 完成 {ok}/{len(RES)} 個成功，{time.time() - t0:.0f} 秒；寫 {OUT}")


if __name__ == "__main__":
    main()
