#!/usr/bin/env python3
"""景氣溫度頁 H0 第二輪探針：第一輪抓不到的來源試替代路徑（docs/lab_heat_plan.md 第 8 節）。

FRED（全部逾時）→ 拉長逾時再試、改用美國財政部殖利率 CSV、勞工統計局 CPI、紐約聯準銀行 EFFR、Yahoo；
主計總處 CPI（伺服器沒送中繼憑證）→ 從伺服器憑證的 AIA 欄位取中繼憑證（CA 發布的公開憑證），
加進信任清單後照常完整驗證（不關掉驗證）；台指 VIX → 月檔與近 3 個月頁面的格式；央行 M1B／M2 → 欄位名稱。
結果寫 data/lab/heat_probe2.json（lab_backfill.yml 會 commit 回分支）；合併前刪掉。
"""
from __future__ import annotations

import json
import re
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import certifi  # noqa: E402

from scripts.probe_heat import BROWSER, RES, get, guard, log, plain, rec, yahoo_long  # noqa: E402

OUT = ROOT / "data" / "lab" / "heat_probe2.json"


def fred(sid: str, cosd: str, timeout: int = 150) -> None:
    def run():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={cosd}"
        b = get(url, headers=BROWSER, timeout=timeout)
        lines = [ln for ln in b.decode("utf-8", "replace").splitlines() if ln.strip()]
        rec(f"FRED {sid} {cosd}", ok=len(lines) > 2, bytes=len(b), lines=len(lines), head=lines[:3], tail=lines[-2:])
    guard(f"FRED {sid} {cosd}", run)


def cbc_struct() -> None:
    def run():
        doc = json.loads(get("https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=EF15M01", headers=BROWSER).decode("utf-8"))
        info = {"top": list(doc.keys())}
        data = doc.get("data") or {}
        info["data_keys"] = list(data.keys())
        for k, v in data.items():
            if k != "dataSets":
                info[k] = json.dumps(v, ensure_ascii=False)[:1500]
        ds = data.get("dataSets") or []
        info["n"] = len(ds)
        info["last"] = ds[-1] if ds else None
        rec("央行 EF15M01 結構", ok=True, **info)
    guard("央行 EF15M01 結構", run)


def dgbas_with_aia() -> None:
    """主計總處 CPI：openssl 讀伺服器憑證 → AIA 的 CA Issuers 網址 → 抓中繼憑證 → certifi＋中繼憑證完整驗證。"""
    def run():
        host = "ws.dgbas.gov.tw"
        p = subprocess.run(["openssl", "s_client", "-connect", f"{host}:443", "-servername", host, "-showcerts"],
                           input=b"", capture_output=True, timeout=40)
        pem = re.findall(rb"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", p.stdout, re.S)
        info = {"server_certs": len(pem)}
        if not pem:
            rec("主計總處 CPI（AIA）", ok=False, err="openssl 沒拿到憑證", stderr=p.stderr.decode()[:300])
            return
        x = subprocess.run(["openssl", "x509", "-noout", "-text", "-issuer", "-subject"], input=pem[0],
                           capture_output=True, timeout=20).stdout.decode("utf-8", "replace")
        info["issuer"] = re.search(r"issuer=(.*)", x).group(1) if re.search(r"issuer=(.*)", x) else None
        aia = re.findall(r"CA Issuers - URI:(\S+)", x)
        info["aia"] = aia
        cadata = ""
        for u in aia:
            try:
                der = urllib.request.urlopen(urllib.request.Request(u, headers=BROWSER), timeout=30).read()
                if der.startswith(b"-----BEGIN"):
                    cadata += der.decode()
                else:
                    cadata += ssl.DER_cert_to_PEM_cert(der)
            except Exception as e:                        # noqa: BLE001
                info.setdefault("aia_err", []).append(f"{u}: {e}")
        info["intermediate_pem"] = cadata[:4000]
        ctx = ssl.create_default_context(cafile=certifi.where())
        if cadata:
            ctx.load_verify_locations(cadata=cadata)
        url = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml"
        with urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER), timeout=60, context=ctx) as r:
            b = r.read()
        txt = b.decode("utf-8", "replace")
        periods = sorted(set(re.findall(r"(\d{4}M\d{2})", txt)))
        rec("主計總處 CPI（AIA）", ok=True, bytes=len(b), first=periods[0] if periods else None,
            last=periods[-1] if periods else None, n=len(periods), head=txt[:900], **info)
    guard("主計總處 CPI（AIA）", run)


def vix_page() -> None:
    def run():
        txt = get("https://www.taifex.com.tw/cht/7/vixDaily3MNew", headers=BROWSER).decode("utf-8", "replace")
        i = txt.find("<table")
        snippet = re.sub(r"\s+", " ", txt[i:i + 3000]) if i >= 0 else txt[:1500]
        rows = re.findall(r"<td[^>]*>\s*([^<]{4,14})\s*</td>\s*<td[^>]*>\s*([\d.]+)\s*</td>", txt)
        rec("期交所 台指 VIX 近 3 個月（表格）", ok=bool(rows), rows=len(rows), first=rows[:3], last=rows[-3:],
            head=snippet[:1500])
    guard("期交所 台指 VIX 近 3 個月（表格）", run)


def main() -> None:
    t0 = time.time()
    for sid, cosd in (("DFF", "2024-01-01"), ("VIXCLS", "2024-01-01"), ("T10Y2Y", "1976-01-01"),
                      ("BAA10Y", "1986-01-01"), ("CPIAUCSL", "1947-01-01")):
        fred(sid, cosd)
    plain("FRED 文字檔 DFF", "https://fred.stlouisfed.org/data/DFF.txt")
    for y in (1990, 2010, 2026):
        plain(f"美國財政部 殖利率 {y}", "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
              f"daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
    plain("勞工統計局 CPI v1（2017–2026）", "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0?startyear=2017&endyear=2026")
    plain("勞工統計局 CPI v1（1996–2005）", "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0?startyear=1996&endyear=2005")
    plain("紐約聯準銀行 EFFR", "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2016-03-01&endDate=2026-10-17")
    plain("紐約聯準銀行 EFFR 最新", "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json")
    yahoo_long("Yahoo ^VIX 1990 起", "^VIX")
    yahoo_long("Yahoo ^TNX 1990 起", "^TNX")
    yahoo_long("Yahoo HYG", "HYG")
    yahoo_long("Yahoo IEF", "IEF")
    cbc_struct()
    dgbas_with_aia()
    plain("主計總處 SDMX CPI", "https://nstatdb.dgbas.gov.tw/dgbasall/webMain.aspx?sdmx/A030101015/1..M.&startTime=1981-M1&endTime=2026-M12")
    vix_page()
    for ym in ("202607", "202608", "202610"):
        plain(f"期交所 台指 VIX 月檔 {ym}", f"https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{ym}new.txt",
              enc="cp950")
    plain("證交所 每日市場成交 1999-01", "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=19990101&response=json")
    OUT.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "res": RES},
                              ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ok = sum(1 for v in RES.values() if v.get("ok"))
    log(f"[heat-probe2] 完成 {ok}/{len(RES)} 個成功，{time.time() - t0:.0f} 秒；寫 {OUT}")


if __name__ == "__main__":
    main()
