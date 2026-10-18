#!/usr/bin/env python3
"""景氣溫度・美股版與台股泡沫面向的資料抓取（docs/lab_heat_us_plan.md 第 14、15 節）。只在 CI 跑：本容器的 proxy 擋這些站。

  每天（afterhours 每班、daily 06:35）：TZ=Asia/Taipei python3 scripts/fetch_heat_us.py
      指數與日資料：資料已經到最近一個收盤的美股交易日就不再打 Yahoo；
      週資料、月資料、季資料：每個來源一天成功抓一次（_state_us 記日期）；台灣季 GDP 只在新的一季該出來時才抓；
      LPPLS：有新的一週才算（要 numpy；沒裝就跳過、印原因）。
  回補（`.ping/lab` 第一行寫 usfill）：python3 scripts/fetch_heat_us.py --backfill
      全部來源從頭抓（Yahoo、DBnomics、CFTC、BLS 1947 起分 8 次、Shiller、WSTS…）；
      加權指數 1990～1998（證交所 FMTQIK 每月一請求，約 6 分鐘）。

每個來源各自失敗、各自降級（抓不到保留既有的檔）；最後印每個檔的筆數與日期範圍。
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import heat as H  # noqa: E402
from arm.lab import heatdata as HD  # noqa: E402
from arm.lab import heatfetch_us as U  # noqa: E402

NAMES = ["us_px_spx", "us_px_ixic", "us_px_ndx", "us_px_sox", "us_vxn", "us_vix3m", "us_dxy", "us_rsp", "us_spy",
         "us_h15", "us_h41", "us_m2", "us_z1", "us_gdp", "us_cftc_am", "us_cftc_vix", "us_cftc_big", "us_cftc_mini",
         "us_philly", "us_ads", "us_cli", "us_claims", "us_bls", "us_umich", "us_ebp", "us_shiller", "us_wsts",
         "taiex90", "twgdp"] + [f"us_lppls_{k}" for k in U.US_INDEX_SYM] + ["tw_lppls"]
YAHOO = [("us_px_spx", "^GSPC", "1927-01-01"), ("us_px_ixic", "^IXIC", "1971-01-01"),
         ("us_px_ndx", "^NDX", "1985-01-01"), ("us_px_sox", "^SOX", "1994-01-01"),
         ("us_vxn", "^VXN", "2001-01-01"), ("us_vix3m", "^VIX3M", "2006-01-01"), ("us_dxy", "DX-Y.NYB", "1971-01-01")]
ADJ = [("us_rsp", "RSP", "2003-01-01"), ("us_spy", "SPY", "1993-01-01")]


def log(msg: str) -> None:
    print(msg, flush=True)


def run(name: str, fn, *a, **kw) -> bool:
    t0 = time.time()
    try:
        n = fn(*a, **kw)
        log(f"[heat-us] {name}: {n} 筆新增或改動（{time.time() - t0:.0f}s）")
        return True
    except Exception as e:                                    # noqa: BLE001 —— 每個來源各自失敗
        log(f"[heat-us] {name} ✗ {type(e).__name__}: {str(e)[:200]}（{time.time() - t0:.0f}s）")
        return False


def lppls_update() -> None:
    """LPPLS 每週一次：有新的週末交易日才算（要 numpy）。整段歷史在研究時算好入庫（scripts/run_heat_us.py），
    這裡只補新的週；檔案還沒有的話跳過（整段在 CI 算要一個多小時）。"""
    try:
        from arm.lab import heatbubble as B
    except Exception as e:                                    # noqa: BLE001
        log(f"[heat-us] LPPLS 跳過：{type(e).__name__} {str(e)[:120]}")
        return
    for idx in U.US_INDEX_SYM:
        run(f"LPPLS {idx}", B.lppls_update, f"us_lppls_{idx}", HD.load(f"us_px_{idx}"))
    run("LPPLS 加權指數", B.lppls_update, "tw_lppls", B.taiex_daily())


def daily() -> None:
    today = date.today().isoformat()
    st = HD.load("_state_us")
    ok = dict(st)

    def once(key: str, fn, *a) -> None:                      # 一天成功一次
        if st.get(key) == today:
            return
        if run(key, fn, *a):
            ok[key] = today

    last = U.latest_us_close_day()
    for name, sym, start in YAHOO:
        have = HD.load(name)
        if have and max(have) >= last:
            continue
        a = start if not have else max(start, (date.fromisoformat(max(have)) - timedelta(days=10)).isoformat())
        run(name, U.yahoo_us, name, sym, a)
    for name, sym, start in ADJ:
        once(name, U.yahoo_us, name, sym, start, True)
    once("us_h15", U.h15)
    once("us_h41", U.h41)
    for name in U.CFTC_JOBS:
        have = HD.load(name)
        once(name, U.cftc, name, (max(have) if have else "1986-01-01")[:4] + "-01-01")
    for key, fn in (("us_philly", U.philly), ("us_ads", U.ads), ("us_cli", U.oecd_cli), ("us_claims", U.claims),
                    ("us_umich", U.umich), ("us_ebp", U.ebp), ("us_m2", U.m2), ("us_z1", U.z1), ("us_gdp", U.gdp),
                    ("us_shiller", U.shiller), ("us_wsts", U.wsts)):
        once(key, fn)
    once("us_bls", U.bls, date.today().year - 1)
    g = HD.load("twgdp")
    if not g or H.avail_date(next_quarter(max(g)), (1, 28)) <= today:
        once("twgdp", U.twgdp)
    lppls_update()
    if ok != st:
        HD.save("_state_us", "fetch_heat_us", ok)


def next_quarter(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + 3
    if m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}-{m:02d}"


def backfill() -> None:
    for name, sym, start in YAHOO:
        run(name, U.yahoo_us, name, sym, start)
    for name, sym, start in ADJ:
        run(name, U.yahoo_us, name, sym, start, True)
    run("us_h15", U.h15)
    run("us_h41", U.h41)
    run("us_m2", U.m2)
    run("us_z1", U.z1)
    run("us_gdp", U.gdp)
    for name in U.CFTC_JOBS:
        run(name, U.cftc, name)
    for key, fn in (("us_philly", U.philly), ("us_ads", U.ads), ("us_cli", U.oecd_cli), ("us_claims", U.claims),
                    ("us_umich", U.umich), ("us_ebp", U.ebp), ("us_shiller", U.shiller), ("us_wsts", U.wsts),
                    ("twgdp", U.twgdp)):
        run(key, fn)
    run("us_bls", U.bls, 1947)
    run("taiex90", U.taiex90)


def summary() -> None:
    for k in NAMES:
        d = HD.load(k)
        ks = sorted(d)
        log(f"[heat-us] 檔 {k:14s} {len(ks):6d} 筆  {ks[0] if ks else '—'} ～ {ks[-1] if ks else '—'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.backfill:
        backfill()
    else:
        daily()
    summary()
    log(f"[heat-us] 完成，{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
