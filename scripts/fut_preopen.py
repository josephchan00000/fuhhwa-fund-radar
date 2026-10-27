"""台指期早盤策略：每天盤前取樣（arm/lab/futpre.py；.github/workflows/fut_preopen.yml 凌晨三班排程叫它）。

  交易日才做（證交所官方休市表，含颱風臨時休市）；今天的檔已經有了、或已經過了 09:00:15 → 直接結束。
  否則等到 08:58:00，每 5 秒取樣到 09:00:15，存 data/lab/fut/pre/{今天}.json.gz（workflow 接著 commit 進 main）。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm import clock  # noqa: E402
from arm import twholidays as H  # noqa: E402
from arm.lab import futpre as P  # noqa: E402
from arm.lab import futres as R  # noqa: E402
from arm.lab import store  # noqa: E402


def now_s() -> float:
    n = clock.now_tw()
    return n.hour * 3600 + n.minute * 60 + n.second + n.microsecond / 1e6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只取樣、不寫檔")
    a = ap.parse_args()
    d = clock.today_tw()
    if H.is_closed(d) is True:
        P.log(f"{d} 休市，不取樣")
        return 0
    ds = d.isoformat()
    if store.read(P.KIND, ds):
        P.log(f"{ds} 已經取樣過了")
        return 0
    if now_s() > P.END_S:
        P.log(f"{ds} 已經過了 09:00:15（{clock.now_tw():%H:%M:%S}），今天沒取到")
        return 0
    dp = R.prev_trading_day(ds)
    mk = [x for x in store.dates("mkt") if x <= dp]
    if not mk:
        P.log("沒有前一個交易日的行情分片，不取樣")
        return 0
    if mk[-1] != dp:
        P.log(f"前一個交易日 {dp} 的行情分片還沒有，比重改用 {mk[-1]}")
    wait = P.START_S - now_s()
    if wait > 0:
        P.log(f"{ds}：等到 08:58:00（{wait / 60:.1f} 分鐘）")
    doc = P.sample(ds, mk[-1], now_s=now_s, sleep=lambda s: time.sleep(max(0.0, s)))
    if not doc:
        P.log("一次都沒抓到，不存")
        return 0
    if a.dry:
        P.log(f"試跑：{len(doc['s'])} 筆，不寫檔")
        return 0
    P.log("寫檔" if P.save(doc) else "已經有了，不覆寫")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
