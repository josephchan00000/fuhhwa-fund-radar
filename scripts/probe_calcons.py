#!/usr/bin/env python3
"""行事曆「預期」欄（市場共識）的自動來源探針（使用者 2026-11-03：「你主頁的行事曆的預估值都沒東西欸，是不是要修一下」）。

預期值現在只靠早上子代理上網找，未公布的數據列只有 2～4 成有值。這支在 CI 試兩個免費、不用金鑰的財經日曆：
  1. ForexFactory 週曆 JSON（nfs.faireconomy.media，本週／下週）：title、country、date、impact、forecast、previous；
  2. Nasdaq 經濟日曆（api.nasdaq.com/api/calendar/economicevents?date=）：country、eventName、consensus、previous、actual；
並把本週行事曆（reports/macrocal 最新一份）還沒公布的數據列印出來，兩邊同一天、同一國的候選放在一起看，
方便決定對照表與數字格式。容器擋這些站，所以在 CI 跑（lab_backfill.yml，.ping/lab 第一行寫 calcons）。
結果印出、也寫進 data/lab/_calcons.txt（lab_backfill 會 commit 回分支），看完從分支刪掉。只讀不寫落檔。
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm import clock  # noqa: E402
from arm.http import get_bytes  # noqa: E402

OUT = ROOT / "data" / "lab" / "_calcons.txt"
LINES: list[str] = []
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
CTRY = {"美": ("USD", "United States"), "歐": ("EUR", "Euro Zone", "GBP", "United Kingdom"), "中": ("CNY", "China"),
        "日": ("JPY", "Japan")}


def p(*a) -> None:
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LINES.append(s)


def run(name: str, fn) -> None:
    p(f"\n===== {name} =====")
    try:
        fn()
    except Exception as ex:                                   # noqa: BLE001
        p(f"✗ {type(ex).__name__}: {str(ex)[:300]}")


def fetch(url: str, *, sleep: float = 1.5, headers: dict | None = None) -> bytes | None:
    t0 = time.time()
    try:
        b = get_bytes(url, retries=1, timeout=30, use_cache=False, headers=headers)
    except Exception as ex:                                   # noqa: BLE001
        p(f"  {url}\n    ✗ {type(ex).__name__}: {str(ex)[:200]}（{time.time() - t0:.1f}s）")
        time.sleep(sleep)
        return None
    time.sleep(sleep)
    p(f"  {url}\n    {len(b)}B（{time.time() - t0:.1f}s）開頭 {b[:140].decode('utf-8', 'replace')!r}")
    return b


FF: list[dict] = []
NQ: list[dict] = []


def ff() -> None:
    for wk in ("thisweek", "nextweek", "lastweek"):
        for ext in ("json",):
            b = fetch(f"https://nfs.faireconomy.media/ff_calendar_{wk}.{ext}", sleep=3)
            if not b:
                continue
            try:
                rows = json.loads(b.decode("utf-8", "replace"))
            except ValueError:
                p("    （不是 JSON）")
                continue
            p(f"    {wk}：{len(rows)} 則；欄位 {list(rows[0]) if rows else []}")
            for r in rows:
                r["_wk"] = wk
            FF.extend(rows)
    keep = [r for r in FF if r.get("country") in ("USD", "EUR", "CNY", "JPY", "GBP") and r.get("impact") in ("High", "Medium")]
    p(f"  美歐中日英、影響中高：{len(keep)} 則；有 forecast 的 {sum(1 for r in keep if r.get('forecast'))} 則")
    for r in keep[:120]:
        p(f"    {r.get('_wk')} {str(r.get('date'))[:16]} {r.get('country')} [{r.get('impact')}] {r.get('title')}"
          f" ｜預期 {r.get('forecast')!r} 前值 {r.get('previous')!r}")


def nasdaq() -> None:
    today = clock.today_tw()
    mon = today - timedelta(days=today.weekday())
    days = [mon + timedelta(days=i) for i in range(-7, 12) if (mon + timedelta(days=i)).weekday() < 5]
    for d in days:
        b = fetch(f"https://api.nasdaq.com/api/calendar/economicevents?date={d:%Y-%m-%d}", headers=UA)
        if not b:
            continue
        try:
            j = json.loads(b.decode("utf-8", "replace"))
        except ValueError:
            p("    （不是 JSON）")
            continue
        rows = ((j.get("data") or {}).get("rows")) or []
        if rows and d == days[0]:
            p(f"    欄位 {list(rows[0])}")
        p(f"    {d}：{len(rows)} 則")
        for r in rows:
            r["_d"] = d.isoformat()
        NQ.extend(rows)
    keep = [r for r in NQ if r.get("country") in ("United States", "Euro Zone", "China", "Japan", "United Kingdom")]
    p(f"  美歐中日英：{len(keep)} 則；有 consensus 的 {sum(1 for r in keep if (r.get('consensus') or '').strip() not in ('', '-'))} 則")
    for r in keep[:160]:
        p(f"    {r.get('_d')} {r.get('gmt')} {r.get('country')} {r.get('eventName')} ｜預期 {r.get('consensus')!r}"
          f" 前值 {r.get('previous')!r} 實際 {r.get('actual')!r}")


def match_week() -> None:
    from arm import calfill as CF
    lat = CF.latest(ROOT / "reports" / "macrocal", clock.today_tw())
    if not lat:
        p("  找不到行事曆")
        return
    path, fd = lat
    md = path.read_text(encoding="utf-8")
    p(f"  行事曆 {path.name}")
    for _i, c, r, end in CF._rows(md, fd):
        reg = r.get("region")
        if reg not in CTRY:
            continue
        p(f"\n  ● {c[0]} {c[1]} ｜預期 {c[2]} 實際 {c[3]} 前值 {c[4]} {c[5]}")
        d = end.isoformat() if end else ""
        ff_c = [x for x in FF if str(x.get("date", ""))[:10] == d and x.get("country") in CTRY[reg]]
        nq_c = [x for x in NQ if x.get("_d") == d and x.get("country") in CTRY[reg]]
        for x in ff_c:
            p(f"      FF {x.get('title')} ｜{x.get('forecast')!r}／{x.get('previous')!r}")
        for x in nq_c:
            p(f"      NQ {x.get('eventName')} ｜{x.get('consensus')!r}／{x.get('previous')!r}／{x.get('actual')!r}")


def main() -> int:
    t0 = time.time()
    try:
        for name, fn in (("1. ForexFactory 週曆", ff), ("2. Nasdaq 經濟日曆", nasdaq), ("3. 本週行事曆各列的候選", match_week)):
            run(name, fn)
    finally:
        p(f"\n總共 {time.time() - t0:.0f} 秒；{clock.stamp_tw()}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
