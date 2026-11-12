#!/usr/bin/env python3
"""08:45 台指期開盤後重估 09:01（arm/lab/pm850.py；docs/lab_premarket_plan.md 第 16 節；.github/workflows/fut_preopen.yml 叫它）。

  --wait       等到 08:45:15（休市、或已經過了 START_LAST 就馬上結束）
  --fetch OUT  抓期交所 MIS 日盤報價，開盤價出來就算重估，寫到 OUT（不動 repo；沒算出來就不寫 OUT）
  --apply IN   把 IN 的重估掛進 data/lab/premkt.json（只有那份是今天的才掛）、記到 data/lab/fut/e850.json、重建選擇權頁
08:57 之後不開始（讓給 08:58 的盤前取樣）；09:01 之後重估就沒有用了。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm import clock  # noqa: E402
from arm import fileio  # noqa: E402
from arm import twholidays as H  # noqa: E402
from arm.lab import pm850 as E  # noqa: E402

START = 8 * 3600 + 45 * 60 + 15        # 08:45:15 開始問
POLL_END = 8 * 3600 + 56 * 60          # 08:56:00 還沒有開盤價就放棄
START_LAST = 8 * 3600 + 57 * 60        # 08:57:00 之後不開始
STEP = 10


def log(*a) -> None:
    print("[08:46 重估]", *a, flush=True)


def now_s() -> float:
    n = clock.now_tw()
    return n.hour * 3600 + n.minute * 60 + n.second + n.microsecond / 1e6


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def skip_today() -> str | None:
    d = clock.today_tw()
    if H.is_closed(d) is True:
        return f"{d} 休市"
    if now_s() > START_LAST:
        return f"已經 {clock.now_tw():%H:%M:%S}，過了 08:57（讓給 08:58 取樣）"
    return None


def wait() -> int:
    why = skip_today()
    if why:
        log(why, "，不等")
        return 0
    w = START - now_s()
    if w > 0:
        log(f"等到 08:45:15（{w / 60:.1f} 分鐘）")
        time.sleep(w)
    return 0


def fetch(out: Path) -> int:
    from arm.lab import futpre as P
    from arm.lab import premkt as PM
    why = skip_today()
    if why:
        log(why)
        return 0
    today = clock.today_tw().isoformat()
    pm = _read(PM.OUT)
    if not pm or pm.get("next") != today:
        log(f"盤前作戰圖不是今天的（{(pm or {}).get('next')}），不重估")
        return 0
    if (E.cur(pm) or {}).get("d") == today:
        log("今天已經重估過了")
        return 0
    research = _read(E.RES)
    if not E.ok_research(research):
        log("研究檔不是這一版或沒過關，不重估")
        return 0
    while True:
        quotes, st = P._get_tf()
        e = E.estimate(pm, quotes or [], research, clock.now_tw().strftime("%H%M%S"), today) if quotes else None
        if e:
            fileio.write_text(out, json.dumps(e, ensure_ascii=False) + "\n")
            log(f"{e['sym']} 開盤 {e['open']:,.0f}（{e['ref_src']} {e['ref']:,.0f}）→ 預估 09:01 約 {e['est']:,}"
                f"（清晨估 {e['early']:,}），八成在 ±{e['p80']}")
            return 0
        if now_s() >= POLL_END:
            log(f"到 08:56 還沒有今天的開盤價（最後一次：{st}），不重估")
            return 0
        time.sleep(STEP)


def apply(src: Path) -> int:
    from arm.lab import premkt as PM
    from arm.lab import txopage
    e = _read(src)
    pm = _read(PM.OUT)
    if not e or not pm:
        log("沒有重估或盤前作戰圖")
        return 0
    lg = _read(E.LOG) or {}
    if not E.apply(pm, e, lg):
        log(f"盤前作戰圖是 {pm.get('next')} 的、重估是 {e.get('d')} 的，不掛")
        return 0
    fileio.write_text(PM.OUT, json.dumps(pm, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    fileio.write_text(E.LOG, json.dumps(lg, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    log("選擇權頁", "已更新" if txopage.build() else "沒變")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--wait", action="store_true")
    g.add_argument("--fetch", metavar="OUT")
    g.add_argument("--apply", metavar="IN")
    a = ap.parse_args()
    if a.wait:
        return wait()
    if a.fetch:
        return fetch(Path(a.fetch))
    return apply(Path(a.apply))


if __name__ == "__main__":
    raise SystemExit(main())
