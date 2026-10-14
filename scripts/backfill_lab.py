#!/usr/bin/env python3
"""籌碼雷達一次性回補（CI 手動觸發；可重跑——已有的部件不重抓）。

  python3 scripts/backfill_lab.py --pos-git              # 從 git 歷史回補 ETF 部位（需完整 clone）
  python3 scripts/backfill_lab.py --px-days 380 --flow-days 95 --budget-min 40
  python3 scripts/backfill_lab.py --probe                # 只抓最近一個交易日、逐部件印診斷、不寫檔
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock  # noqa: E402
from arm.lab import collect, market  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pos-git", action="store_true")
    ap.add_argument("--px-days", type=int, default=0, help="價量回補日曆天數")
    ap.add_argument("--flow-days", type=int, default=0, help="籌碼回補日曆天數")
    ap.add_argument("--budget-min", type=float, default=40)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--probe2", action="store_true", help="第二階段資料源探針（股利、EPS、殖利率）")
    a = ap.parse_args()
    today = clock.today_tw()

    if a.probe2:
        market.probe2(collect.candidate_days(today, 7)[1])
        return
    if a.probe:
        for d in collect.candidate_days(today, 7)[:2]:
            for p in market.ALL_PARTS:
                data, st, extra = market.fetch_part(p, d)
                n = len(data) if data else 0
                smp = {k: data[k] for k in ("2330", "2454", "6488", "3105") if data and k in data}
                print(f"[probe] {d} {p}: {st} {n} 檔 {extra or ''} 樣本={smp}")
        iso, td = market.fetch_tdcc()
        print(f"[probe] TDCC {iso}: {len(td)} 檔 樣本={ {k: td[k] for k in ('2330', '6488') if k in td} }")
        return

    if a.pos_git:
        collect.backfill_pos_from_git()
    collect.update_pos_from_current()

    span = max(a.px_days, a.flow_days)
    if span:
        cut_flow = (today.toordinal() - a.flow_days)
        days = collect.candidate_days(today, span)

        def parts(d):
            from datetime import date
            if date.fromisoformat(d).toordinal() >= cut_flow:
                return list(market.ALL_PARTS)
            return list(market.PX_PARTS)
        st = collect.fill_market(days, parts, budget_s=a.budget_min * 60, today=today,
                                 verbose=False)
        print(f"[lab] 回補統計：{st}")
    try:
        collect.update_tdcc()
    except Exception as e:                                # noqa: BLE001
        print(f"[lab] TDCC 失敗：{e}")


if __name__ == "__main__":
    main()
