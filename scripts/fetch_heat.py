#!/usr/bin/env python3
"""景氣溫度頁的資料抓取（docs/lab_heat_plan.md 第 7、10 節）。只在 CI 跑：本容器的 proxy 擋這些站。

  每天（afterhours 每班、daily 06:35）：TZ=Asia/Taipei python3 scripts/fetch_heat.py
      日資料只抓最近一段；月資料每個來源一天成功抓一次（主計總處 15MB 的 XML 只在新月份該出來時才抓）；
      官方分片有新的交易日才重算廣度。
  回補（`.ping/lab` 第一行寫 heatfill）：python3 scripts/fetch_heat.py --backfill --budget-min 45
      各來源從頭抓；期交所 P/C、證交所成交金額每月一請求，時間到就停、下一輪續補（已有整月的跳過）。
      只抓某幾個：第一行寫 heatfill:ndc,pmi（冒號後面＝--only，用回補清單的鍵名；ndc 會連出口一起抓）。

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
from arm.lab import heatfetch as F  # noqa: E402

NAMES = ["margin", "inst", "futi", "opti", "mtxoi", "pcr", "vixtw", "taiex", "vix", "hyg", "ief", "turnover",
         "usdtwd", "money", "ndc", "ndc_first", "exports", "pmi", "orders", "twcpi", "effr", "fedtgt", "uscpi", "ust",
         "breadth"]
# 月資料「新的一個月該出來了」的最早日子（第 m＋1 個月的第幾天）：只用來決定要不要抓，不影響驗證（驗證用 heatspec.RELEASE）
DUE = {"twcpi": (1, 5)}


def log(msg: str) -> None:
    print(msg, flush=True)


def run(name: str, fn, *a, **kw) -> None:
    t0 = time.time()
    try:
        n = fn(*a, **kw)
        log(f"[heat] {name}: {n} 筆新增或改動（{time.time() - t0:.0f}s）")
    except Exception as e:                                    # noqa: BLE001 —— 每個來源各自失敗
        log(f"[heat] {name} ✗ {type(e).__name__}: {str(e)[:200]}（{time.time() - t0:.0f}s）")


def since(name: str, days: int, floor: str) -> str:
    d = HD.load(name)
    if not d:
        return floor
    return (date.fromisoformat(max(d)[:10]) - timedelta(days=days)).isoformat()


def due_month(name: str, today: date) -> bool:
    d = HD.load(name)
    if not d:
        return True
    rel = DUE[name]
    y, m = today.year, today.month
    for _ in range(3):                                        # 最近一個「應該已公布」的月份
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        ym = f"{y:04d}-{m:02d}"
        if H.avail_date(ym, rel) <= today.isoformat():
            return max(d) < ym
    return False


def daily() -> None:
    today = date.today()
    st = HD.load("_state")
    ok = dict(st)

    def monthly(key: str, fn, *a) -> None:                   # 一天成功一次
        if st.get(key) == today.isoformat():
            return
        t0 = time.time()
        try:
            n = fn(*a)
            ok[key] = today.isoformat()
            log(f"[heat] {key}: {n} 筆新增或改動（{time.time() - t0:.0f}s）")
        except Exception as e:                                # noqa: BLE001
            log(f"[heat] {key} ✗ {type(e).__name__}: {str(e)[:200]}")

    tw = today.isoformat()

    def tw_run(name: str, key: str, fn, *a) -> None:      # 台灣日資料：已有今天的就不再打來源站（一天好幾班）
        if (max(HD.load(key)) if HD.load(key) else "") >= tw:
            return
        run(name, fn, *a)

    tw_run("融資", "margin", F.fm_margin, since("margin", 10, "2001-01-01"))
    tw_run("三大法人", "inst", F.fm_inst, since("inst", 10, "2004-01-01"))
    tw_run("期貨法人", "futi", F.fm_futi, since("futi", 10, "2018-01-01"))
    tw_run("選擇權法人", "opti", F.fm_opti, since("opti", 10, "2018-01-01"))
    tw_run("小台未平倉", "mtxoi", F.fm_mtxoi, since("mtxoi", 10, "2005-01-01"))
    first = date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1)
    tw_run("P/C 比", "pcr", F.taifex_pcr, first)
    tw_run("台指 VIX", "vixtw", F.taifex_vix, 2)
    tw_run("加權指數", "taiex", F.yahoo, "taiex", "^TWII", since("taiex", 10, "1997-01-01"))
    run("美國 VIX", F.yahoo, "vix", "^VIX", since("vix", 10, "1990-01-01"))
    run("HYG", F.yahoo_adj, "hyg", "HYG", "2007-01-01")
    run("IEF", F.yahoo_adj, "ief", "IEF", "2002-01-01")
    tw_run("成交金額", "turnover", F.twse_turnover, first)
    tw_run("新台幣", "usdtwd", F.cbc_usdtwd)
    run("有效聯邦基金利率", F.nyfed_effr, since("effr", 15, F.NYFED_START))
    run("美國公債殖利率", F.treasury, today.year - (today.month == 1))
    monthly("ndc", F.ndc)
    monthly("pmi", F.ndc_pmi)
    monthly("orders", F.moea_orders)
    monthly("money", F.cbc_money)
    monthly("uscpi", F.bls_cpi, today.year - 1)
    if due_month("twcpi", today):
        monthly("twcpi", F.dgbas_cpi)
    run("廣度", F.breadth_update)
    if ok != st:
        HD.save("_state", "fetch_heat", ok)


def backfill(budget_min: float, only: set[str] | None) -> None:
    t_end = time.time() + budget_min * 60

    def want(k: str) -> bool:
        return not only or k in only

    jobs = [
        ("margin", "融資", F.fm_margin, ("2001-01-01",)),
        ("inst", "三大法人", F.fm_inst, ("2004-01-01",)),
        ("futi", "期貨法人", F.fm_futi, ("2018-01-01",)),
        ("opti", "選擇權法人", F.fm_opti, ("2018-01-01",)),
        ("mtxoi", "小台未平倉", F.fm_mtxoi, ("2005-01-01",)),
        ("taiex", "加權指數", F.yahoo, ("taiex", "^TWII", "1997-01-01")),
        ("vix", "美國 VIX", F.yahoo, ("vix", "^VIX", "1990-01-01")),
        ("hyg", "HYG", F.yahoo_adj, ("hyg", "HYG", "2007-01-01")),
        ("ief", "IEF", F.yahoo_adj, ("ief", "IEF", "2002-01-01")),
        ("usdtwd", "新台幣", F.cbc_usdtwd, ()),
        ("money", "M1B／M2", F.cbc_money, ()),
        ("ndc", "景氣指標", F.ndc, ()),
        ("pmi", "PMI", F.ndc_pmi, ()),
        ("orders", "外銷訂單", F.moea_orders, ()),
        ("twcpi", "台灣 CPI", F.dgbas_cpi, ()),
        ("uscpi", "美國 CPI", F.bls_cpi, (1985,)),
        ("ust", "美國公債殖利率", F.treasury, (1990,)),
        ("effr", "聯邦基金利率（H.15）", F.dbn_effr, ()),
        ("effr", "聯邦基金利率（紐約聯準銀行）", F.nyfed_effr, (F.NYFED_START,)),
        ("vixtw", "台指 VIX", F.taifex_vix, (4,)),
        ("breadth", "廣度", F.breadth_update, (True,)),
    ]
    for key, name, fn, a in jobs:
        if want(key):
            run(name, fn, *a)
    if want("pcr"):
        run("P/C 比", F.taifex_pcr, date(2002, 1, 1), None, max(60.0, min(900.0, t_end - time.time() - 60)))
    if want("turnover"):
        run("成交金額", F.twse_turnover, date(1999, 1, 1), None, max(60.0, t_end - time.time() - 60))


def summary() -> None:
    for k in NAMES:
        d = HD.load(k)
        ks = sorted(d)
        log(f"[heat] 檔 {k:9s} {len(ks):6d} 筆  {ks[0] if ks else '—'} ～ {ks[-1] if ks else '—'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--budget-min", type=float, default=45)
    ap.add_argument("--only", default="", help="只跑這些檔（逗號分隔，回補用）")
    a = ap.parse_args()
    t0 = time.time()
    if a.backfill:
        backfill(a.budget_min, {x for x in a.only.split(",") if x} or None)
    else:
        daily()
    summary()
    log(f"[heat] 完成，{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
