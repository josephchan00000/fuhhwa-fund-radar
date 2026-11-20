"""美股財報季的資料探針（docs/lab_earnings_plan.md 第 11.2 節）：只印、不寫檔。只在 CI 跑（本容器擋 Yahoo、那斯達克）。

看四件事：
  1. Yahoo quoteSummary 的 earningsTrend（0q／+1q：單季 EPS 與營收預估）、earningsHistory、calendarEvents、
     earnings（financialsChart／earningsChart：單季實際營收）、incomeStatementHistoryQuarterly 長什麼樣子
  2. Yahoo fundamentals-timeseries 的單季營收、稀釋 EPS、淨利（季底日期、數字）
  3. 那斯達克財報行事曆一天的欄位（time、eps、epsForecast、noOfEsts、lastYearEPS、fiscalQuarterEnding…）
  4. 日線抓得到幾天
用法：python3 scripts/probe_earnus.py [代號 ...]（預設 NVDA MSFT CROX MANH）
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SYMS = sys.argv[1:] or ["NVDA", "MSFT", "CROX", "MANH"]
MODS = "earningsTrend,earningsHistory,calendarEvents,earnings,incomeStatementHistoryQuarterly"
TS = ("https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}"
      "?type=quarterlyTotalRevenue,quarterlyDilutedEPS,quarterlyNetIncome&period1={p1}&period2={p2}")


def _cut(x, n=1200) -> str:
    return json.dumps(x, ensure_ascii=False)[:n]


def yahoo(Y, sym: str) -> None:
    url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(sym)}"
           f"?modules={MODS}&crumb={urllib.parse.quote(Y.crumb or '')}")
    st, b = Y.get(url)
    print(f"\n== {sym} quoteSummary HTTP {st}，{len(b or b'')} bytes")
    try:
        res = ((json.loads((b or b"{}").decode("utf-8")).get("quoteSummary") or {}).get("result") or [None])[0] or {}
    except Exception as e:                                    # noqa: BLE001
        print("  解析失敗", type(e).__name__)
        return
    for t in (res.get("earningsTrend") or {}).get("trend") or []:
        if t.get("period") in ("0q", "+1q"):
            print(f"  earningsTrend {t.get('period')} endDate={t.get('endDate')}")
            print("    earningsEstimate", _cut(t.get("earningsEstimate"), 400))
            print("    revenueEstimate ", _cut(t.get("revenueEstimate"), 400))
    print("  earningsHistory", _cut((res.get("earningsHistory") or {}).get("history"), 1500))
    print("  calendarEvents ", _cut((res.get("calendarEvents") or {}).get("earnings"), 600))
    e = res.get("earnings") or {}
    print("  earnings.financialsChart.quarterly", _cut((e.get("financialsChart") or {}).get("quarterly"), 1200))
    print("  earnings.earningsChart", _cut(e.get("earningsChart"), 1200))
    ih = (res.get("incomeStatementHistoryQuarterly") or {}).get("incomeStatementHistory") or []
    print(f"  incomeStatementHistoryQuarterly {len(ih)} 筆；第一筆", _cut(ih[:1], 800))


def timeseries(Y, sym: str) -> None:
    p2 = int(time.time())
    url = TS.format(sym=urllib.parse.quote(sym), p1=p2 - 800 * 86400, p2=p2)
    st, b = Y.get(url)
    print(f"  timeseries HTTP {st}，{len(b or b'')} bytes")
    try:
        for r in (json.loads((b or b"{}").decode("utf-8")).get("timeseries") or {}).get("result") or []:
            k = (r.get("meta") or {}).get("type", ["?"])[0]
            pts = [(x.get("asOfDate"), (x.get("reportedValue") or {}).get("raw"), x.get("periodType"))
                   for x in r.get(k) or [] if x]
            print(f"    {k}: {pts[-6:]}")
    except Exception as e:                                    # noqa: BLE001
        print("    解析失敗", type(e).__name__, (b or b"")[:200])


def nasdaq(d: str) -> None:
    from arm.lab import usstk
    from arm.lab.fwdfetch import NASDAQ_HDR
    try:
        o = json.loads(usstk._get(usstk.EARN_URL.format(d=d), headers=NASDAQ_HDR, timeout=60).decode("utf-8"))
    except Exception as e:                                    # noqa: BLE001
        print(f"\n== 那斯達克 {d} 失敗 {type(e).__name__}: {str(e)[:160]}")
        return
    rows = ((o.get("data") or {}).get("rows")) or []
    print(f"\n== 那斯達克 {d}：{len(rows)} 列；欄位 {sorted(rows[0]) if rows else None}")
    for r in rows:
        if str(r.get("symbol") or "").upper() in set(SYMS) | {"NVDA", "WMT", "TGT", "LOW", "TJX", "PANW"}:
            print("   ", _cut(r, 500))


def chart(sym: str) -> None:
    from arm.lab import ussxdata as UD
    from datetime import date, timedelta
    _, s, msg = UD.fetch_since(sym, (date.today() - timedelta(days=120)).isoformat(), timeout=20)
    d = (s or {}).get("d") or []
    print(f"  日線 {msg}：{len(d)} 天，{d[:1]}～{d[-1:]}，最後收盤 {((s or {}).get('c') or [None])[-1]}")


def main() -> None:
    from arm.lab import fcst
    Y = fcst._Yahoo()
    print("Yahoo crumb", "有" if Y.login() else "沒有")
    for s in SYMS:
        yahoo(Y, s)
        timeseries(Y, s)
        chart(s)
        time.sleep(1)
    for d in ("2026-11-19", "2026-11-18", "2026-10-28"):
        nasdaq(d)


if __name__ == "__main__":
    main()
