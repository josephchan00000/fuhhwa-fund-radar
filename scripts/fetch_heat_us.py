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
from arm.lab import bubindfetch as BF  # noqa: E402

NAMES = ["us_px_spx", "us_px_ixic", "us_px_ndx", "us_px_sox", "us_vxn", "us_vix3m", "us_dxy", "us_rsp", "us_spy",
         "us_h15", "us_h41", "us_m2", "us_z1", "us_gdp", "us_cp", "us_spf", "us_tech_q", "us_tech_a", "fwd_agg",
         "us_cftc_am", "us_cftc_vix", "us_cftc_big", "us_cftc_mini",
         "us_philly", "us_ads", "us_cli", "us_claims", "us_bls", "us_umich", "us_ebp", "us_shiller", "us_wsts",
         "taiex90", "twgdp"] + [f"us_lppls_{k}" for k in U.US_INDEX_SYM] + ["tw_lppls"] \
    + ["us_ff49x", "us_ff49n", "us_ff49s"] + [f"us_etf_{s}" for s in BF.etf_names()] \
    + [f"us_vol_{k}" for k in U.US_INDEX_SYM]
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
    from arm.lab import crashfetch as CF                     # 大跌風險研究：指數成交量（docs/lab_crash_plan.md）
    for k, (sym, start) in CF.US_VOL.items():
        name = f"us_vol_{k}"
        have = HD.load(name)
        if have and max(have) >= last:
            continue
        a = start if not have else max(start, (date.fromisoformat(max(have)) - timedelta(days=10)).isoformat())
        run(name, CF.yahoo_volume, name, sym, a)
    for sym in BF.etf_names():                               # 產業泡沫：類股 ETF 與 SPY 收盤（docs/lab_risk_plan.md 第 12 節）
        name = f"us_etf_{sym}"
        have = HD.load(name)
        if have and max(have) >= last:
            continue
        a = BF.BI.US_START if not have else (date.fromisoformat(max(have)) - timedelta(days=10)).isoformat()
        run(name, U.yahoo_us, name, sym, a)
    once("us_ff49", BF.ff49)
    once("us_h15", U.h15)
    once("us_h41", U.h41)
    for name in U.CFTC_JOBS:
        have = HD.load(name)
        once(name, U.cftc, name, (max(have) if have else "1986-01-01")[:4] + "-01-01")
    for key, fn in (("us_philly", U.philly), ("us_ads", U.ads), ("us_cli", U.oecd_cli), ("us_claims", U.claims),
                    ("us_umich", U.umich), ("us_ebp", U.ebp), ("us_m2", U.m2), ("us_z1", U.z1), ("us_gdp", U.gdp), ("us_cp", U.cp),
                    ("us_shiller", U.shiller), ("us_wsts", U.wsts)):
        once(key, fn)
    once("us_bls", U.bls, date.today().year - 1)
    fwd_daily(once)
    g = HD.load("twgdp")
    if not g or H.avail_date(next_quarter(max(g)), (1, 28)) <= today:
        once("twgdp", U.twgdp)
    lppls_update()
    if ok != st:
        HD.save("_state_us", "fetch_heat_us", ok)


def fwd_daily(once) -> None:
    """泡沫頁 VER 4 的未來獲利（docs/lab_risk_plan.md 第 11 節）：專業預測者調查、科技業獲利一天一次；
    美股成分股預估一天一次（沒抓完下一輪續抓）；台股預估加總每輪都算（不連網、內容沒變不改檔）。"""
    from arm.lab import fwdfetch as F
    once("us_spf", F.spf)
    once("us_tech", F.tech)
    once("fwd_us", F.update_us)
    run("fwd_tw", F.update_tw_agg)


def next_quarter(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + 3
    if m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}-{m:02d}"


def backfill(only: set | None = None) -> None:
    if only:                                                  # --only：只回補這幾個（例：us_cp）
        jobs = {"us_cp": U.cp, "us_z1": U.z1, "us_gdp": U.gdp, "us_wsts": U.wsts, "us_shiller": U.shiller}
        if only & {"us_spf", "us_tech", "fwd_us", "fwd_tw"}:              # 泡沫頁 VER 4 的未來獲利
            from arm.lab import fwdfetch as F
            jobs.update({"us_spf": F.spf, "us_tech": F.tech, "fwd_us": lambda: F.update_us(budget_s=900),
                         "fwd_tw": F.update_tw_agg})
        jobs.update({"ind_ff": BF.ff49, "ind_etf": BF.etf})            # 產業泡沫
        if "gics" in only:
            from arm.lab import fwdfetch as F
            jobs["gics"] = F.update_gics
        if "cp_probe" in only:
            U.probe_cp()
        if "fwd_probe" in only:                               # 泡沫頁 VER 4 未來獲利的來源探針
            from arm.lab import fwdfetch as F
            F.probe()
        if "fwd_probe2" in only:
            from arm.lab import fwdfetch as F
            F.probe2()
        if "fwd_probe3" in only:
            from arm.lab import fwdfetch as F
            F.probe3()
        for k in sorted(only & set(jobs)):
            run(k, jobs[k])
        return
    for name, sym, start in YAHOO:
        run(name, U.yahoo_us, name, sym, start)
    for name, sym, start in ADJ:
        run(name, U.yahoo_us, name, sym, start, True)
    run("us_h15", U.h15)
    run("us_h41", U.h41)
    run("us_m2", U.m2)
    run("us_z1", U.z1)
    run("us_gdp", U.gdp)
    run("us_cp", U.cp)
    for name in U.CFTC_JOBS:
        run(name, U.cftc, name)
    for key, fn in (("us_philly", U.philly), ("us_ads", U.ads), ("us_cli", U.oecd_cli), ("us_claims", U.claims),
                    ("us_umich", U.umich), ("us_ebp", U.ebp), ("us_shiller", U.shiller), ("us_wsts", U.wsts),
                    ("twgdp", U.twgdp)):
        run(key, fn)
    run("us_bls", U.bls, 1947)
    run("taiex90", U.taiex90)
    from arm.lab import fwdfetch as F
    run("us_spf", F.spf)
    run("us_tech", F.tech)
    run("fwd_us", F.update_us, budget_s=900)
    run("fwd_tw", F.update_tw_agg)
    run("ind_ff", BF.ff49)
    run("ind_etf", BF.etf)


def summary() -> None:
    for k in NAMES:
        d = HD.load(k)
        ks = sorted(d)
        log(f"[heat-us] 檔 {k:14s} {len(ks):6d} 筆  {ks[0] if ks else '—'} ～ {ks[-1] if ks else '—'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--only", default="", help="回補只跑這幾個（逗號分隔，例：us_cp,cp_probe）")
    a = ap.parse_args()
    t0 = time.time()
    if a.backfill:
        backfill({x.strip() for x in a.only.split(",") if x.strip()} or None)
    else:
        daily()
    summary()
    log(f"[heat-us] 完成，{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
