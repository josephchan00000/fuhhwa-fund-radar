#!/usr/bin/env python3
"""美股個股策略的資料探針（docs/lab_core70_plan.md；只印診斷、不寫檔，CI 跑）：

  財報：那斯達克財報行事曆（實際 EPS、市場預估、驚喜幅度）往回能查到哪一年；單一公司的驚喜紀錄有幾季。
  股價：已下市／被併購的 S&P 500 舊成分股，Yahoo、Stooq、FinMind 有沒有歷史日線。
  財報（官方）：SEC EDGAR 不帶 email 的 User-Agent 會不會被擋（只試一個請求）。

  python3 scripts/probe_usstk.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.http import get_bytes  # noqa: E402
from arm.lab.fwdfetch import NASDAQ_HDR  # noqa: E402


def p(*a) -> None:
    print("[usstk]", *a, flush=True)


def get(url: str, timeout: int = 60, headers: dict | None = None) -> tuple[bytes | None, float, str]:
    t0 = time.time()
    try:
        b = get_bytes(url, retries=1, timeout=timeout, use_cache=False, headers=headers)
        return b, time.time() - t0, "ok"
    except Exception as e:                                    # noqa: BLE001
        return None, time.time() - t0, f"{type(e).__name__}: {str(e)[:160]}"


def earnings_calendar() -> None:
    for d in ("2003-01-23", "2008-01-22", "2010-01-20", "2012-04-24", "2014-01-21", "2016-04-20", "2019-07-23",
              "2022-10-25", "2026-10-21"):
        b, dt, st = get(f"https://api.nasdaq.com/api/calendar/earnings?date={d}", headers=NASDAQ_HDR, timeout=60)
        if b is None:
            p(f"財報行事曆 {d} ✗ {st}（{dt:.1f}s）")
            continue
        try:
            doc = json.loads(b.decode("utf-8"))
            rows = ((doc.get("data") or {}).get("rows")) or []
        except Exception as e:                                # noqa: BLE001
            p(f"財報行事曆 {d} 不是 JSON：{e}；開頭 {b[:160]!r}")
            continue
        p(f"財報行事曆 {d}：{len(rows)} 家（{dt:.1f}s）" + (f" 欄位 {sorted(rows[0])}" if rows else ""))
        for r in rows[:3]:
            p("   ", {k: r.get(k) for k in ("symbol", "name", "eps", "epsForecast", "surprise", "time", "fiscalQuarterEnding")})
        time.sleep(1.5)
    for sym in ("AAPL", "XOM"):
        b, dt, st = get(f"https://api.nasdaq.com/api/company/{sym}/earnings-surprise", headers=NASDAQ_HDR)
        if b is None:
            p(f"{sym} 驚喜紀錄 ✗ {st}")
            continue
        try:
            doc = json.loads(b.decode("utf-8"))
            rows = (((doc.get("data") or {}).get("earningsSurpriseTable")) or {}).get("rows") or []
            p(f"{sym} 驚喜紀錄：{len(rows)} 季；{rows[:2]}")
        except Exception as e:                                # noqa: BLE001
            p(f"{sym} 驚喜紀錄 不是 JSON：{e}；開頭 {b[:200]!r}")


GONE = ("LEH", "WAMUQ", "TWX", "CELG", "MON", "XLNX", "ATVI", "TIF", "EK", "YHOO", "DOW", "GE")


def delisted_prices() -> None:
    for s in GONE:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=946684800&period2={int(time.time())}"
               f"&interval=1mo")
        b, dt, st = get(url, timeout=40)
        if b is None:
            p(f"Yahoo {s} ✗ {st}")
        else:
            try:
                r = json.loads(b.decode("utf-8"))["chart"]["result"][0]
                ts = r.get("timestamp") or []
                p(f"Yahoo {s}：{len(ts)} 個月" + (f"（{time.strftime('%Y-%m', time.gmtime(ts[0]))}～"
                                                f"{time.strftime('%Y-%m', time.gmtime(ts[-1]))}）" if ts else ""))
            except Exception as e:                            # noqa: BLE001
                p(f"Yahoo {s} 解析失敗：{e}")
        b, dt, st = get(f"https://stooq.com/q/d/l/?s={s.lower()}.us&i=m", timeout=40)
        if b is None:
            p(f"Stooq {s} ✗ {st}")
        else:
            lines = b.decode("utf-8", "replace").strip().splitlines()
            p(f"Stooq {s}：{len(lines) - 1} 列" + (f"（{lines[1][:10]}～{lines[-1][:10]}）" if len(lines) > 2 else f" 開頭 {lines[:2]}"))
        time.sleep(0.8)
    for s in ("AAPL", "TWX", "CELG"):
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=USStockPrice&data_id={s}&start_date=1995-01-01&end_date=2026-10-01"
        b, dt, st = get(url, timeout=90)
        if b is None:
            p(f"FinMind {s} ✗ {st}")
            continue
        try:
            rows = json.loads(b.decode("utf-8")).get("data") or []
            p(f"FinMind {s}：{len(rows)} 天" + (f"（{rows[0].get('date')}～{rows[-1].get('date')}）" if rows else ""))
        except Exception as e:                                # noqa: BLE001
            p(f"FinMind {s} 解析失敗：{e}")


def sec_edgar() -> None:
    hdr = {"User-Agent": "fuhhwa-fund-radar research (+https://github.com/josephchan00000/fuhhwa-fund-radar)",
           "Accept": "application/json"}
    b, dt, st = get("https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/EarningsPerShareDiluted.json",
                    headers=hdr, timeout=60)
    if b is None:
        p(f"SEC EDGAR（不帶 email）✗ {st}")
        return
    try:
        doc = json.loads(b.decode("utf-8"))
        rows = (doc.get("units") or {}).get("USD/shares") or []
        fy = sorted({r.get("fy") for r in rows if r.get("fy")})
        p(f"SEC EDGAR（不帶 email）✓ {len(rows)} 筆，年度 {fy[:1]}～{fy[-1:]}；第一筆 {rows[:1]}")
    except Exception as e:                                    # noqa: BLE001
        p(f"SEC EDGAR 解析失敗：{e}；開頭 {b[:200]!r}")


def main() -> None:
    earnings_calendar()
    delisted_prices()
    sec_edgar()


if __name__ == "__main__":
    main()
