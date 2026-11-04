#!/usr/bin/env python3
"""美股官方文件包（arm/lab/eqdocs_us.py）的探針：幾家公司實際抓一次 SEC 的 10-K、10-Q、8-K，印每一段抽到幾個字、開頭與結尾一小段，
確認段落切得對（docs/lab_eq_docs_plan.md 第 6 節）。只在 CI 跑（容器擋 sec.gov）；結果寫 data/lab/_secdocs.txt（只有統計與每段前後
幾十個字，不存全文）。聯絡 email 只從 SEC_CONTACT_EMAIL 讀（arm/lab/secfin.py），不印、不存。

  python3 scripts/probe_secdocs.py PAYC NVDA CELH        # lab_backfill.yml 的 secdocsprobe 模式（.ping/lab 第一行 secdocsprobe）
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.clock import today_tw  # noqa: E402
from arm.lab import eqdocs_us as U  # noqa: E402
from arm.lab import secfin as SF  # noqa: E402

OUT = ROOT / "data" / "lab" / "_secdocs.txt"
RATE = 5.0


def main() -> int:
    syms = [s.upper() for s in sys.argv[1:]] or ["PAYC", "NVDA", "CELH"]
    email = SF.contact()
    lines: list[str] = []

    def say(*a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        lines.append(s)

    if not email:
        say("沒有 SEC_CONTACT_EMAIL，跳過")
        OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    from arm.http import _CTX
    last = [0.0]
    stats = {"n": 0, "bytes": 0}

    def get(url: str) -> tuple[int, bytes]:
        w = last[0] + 1.0 / RATE - time.time()
        if w > 0:
            time.sleep(w)
        last[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": SF._ua(email), "Accept": "*/*"})
        stats["n"] += 1
        try:
            with urllib.request.urlopen(req, timeout=120, context=_CTX) as r:
                b = r.read()
                stats["bytes"] += len(b)
                return r.status, b
        except urllib.error.HTTPError as e:
            return e.code, b""
        except Exception as e:                                         # noqa: BLE001
            say(f"  ! {type(e).__name__} {url[-60:]}")
            return 0, b""

    tick = SF.fetch_tickers(email)

    def peek(s: str, n: int = 90) -> str:
        s = s.replace("\n", " ⏎ ")
        return f"「{s[:n]}」…「{s[-n:]}」" if len(s) > 2 * n else f"「{s}」"

    for sym in syms:
        cik = tick.get(sym)
        say(f"\n=== {sym} CIK {cik}")
        if not cik:
            continue
        t0 = time.time()
        n0, b0 = stats["n"], stats["bytes"]
        pk = U.build(sym, cik, today_tw(), get, log=say)
        say(f"  {pk.get('name')}；st={pk.get('st')}；ok={pk.get('ok')}；請求 {stats['n'] - n0} 次、{(stats['bytes'] - b0) / 1e6:.1f} MB、{time.time() - t0:.0f}s")
        say(f"  基本：{pk.get('basic')}")
        for key in ("k10", "q10"):
            x = pk.get(key)
            if not x:
                continue
            say(f"  {key} 申報 {x['d']} 期間 {x['per']} {x['url']}")
            for k, s in x["sec"].items():
                say(f"    Item {k}：全長 {s['n']:,} 字{'（截斷）' if s['cut'] else ''} {peek(s['text'])}")
        for x in pk.get("news") or []:
            ex = "；".join(f"{e['type']} {len(e['text']):,} 字{'（截斷）' if e['cut'] else ''} {peek(e['text'], 60)}" for e in x["ex"])
            say(f"  8-K {x['d']} [{x['items']}] 主文件 {len(x.get('body') or ''):,} 字；附件：{ex or '無'}")
        md = U.render_md(pk)
        say(f"  .md 共 {len(md):,} 字；文件清單：{U.index(pk)['release']}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
