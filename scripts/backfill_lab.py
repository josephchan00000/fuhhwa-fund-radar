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
    ap.add_argument("--probe3", action="store_true")
    ap.add_argument("--growth", action="store_true",
                    help="長線成長股回測資料：Yahoo 擴大到市值 ≥30 億上市櫃股＋兩年投信買賣超（官方逐日）")
    ap.add_argument("--yahoo", action="store_true", help="以 Yahoo 逐檔補兩年歷史日線（官方逐日回補被限流時用）")
    ap.add_argument("--hd", action="store_true", help="高股息研究資料：證交所除權息逐年＋FinMind 單季 EPS／上櫃股利（可重跑續補）")
    ap.add_argument("--yhl", action="store_true",
                    help="高股息提前卡位研究：Yahoo 五年日線另存 data/lab/yhl＋證交所除權息 2018–2020（可重跑續補）")
    ap.add_argument("--rev-probe", action="store_true", help="月營收全市場歷史的來源探針（MOPS 彙總表、FinMind），只印不寫")
    ap.add_argument("--rev-mops", action="store_true", help="月營收全市場歷史（MOPS 彙總表，2020-01 起；可重跑續補）")
    ap.add_argument("--rev-fm", action="store_true", help="月營收全市場歷史備援：FinMind 逐檔（五年日線宇宙，2020-01 起）")
    ap.add_argument("--probe-v3", action="store_true", help="回測 v3 資料源探針（報酬指數、櫃買除權息、2012 起月營收、"
                    "Yahoo 長歷史與下市股、FinMind EPS／發行股數），只印不寫")
    a = ap.parse_args()
    today = clock.today_tw()

    if a.rev_probe:
        market.probe_rev()
        return
    if a.probe_v3:
        market.probe_v3()
        return
    if a.rev_mops:
        print(f"[lab] 月營收歷史：本輪新增 {collect.backfill_rev_mops(budget_s=a.budget_min * 60)} 個月")
        return
    if a.rev_fm:
        codes = [c for c in collect.yhl_codes() if len(c) == 4 and c.isdigit() and not c.startswith("00")]
        print(f"[lab] 月營收歷史（FinMind）：本輪新增 {collect.backfill_rev_finmind(codes, budget_s=a.budget_min * 60)} 檔")
        return

    if "--probe3" in sys.argv[1:]:
        market.probe3(collect.candidate_days(today, 7)[1])
        return
    if a.yahoo:
        collect.backfill_yahoo()
        return
    if a.yhl:
        collect.backfill_divtw((2018, 2019, 2020))
        print(f"[lab] Yahoo 長歷史：本輪新增 {collect.backfill_yahoo_long(budget_s=a.budget_min * 60)} 檔")
        return
    if a.hd:
        print(f"[lab] 高股息資料：{collect.backfill_hd(budget_s=a.budget_min * 60)}")
        return
    if a.growth:
        import time as _t
        t0 = _t.time()
        collect.backfill_yahoo(min_cap=30e8, budget_s=1200)
        left = a.budget_min * 60 - (_t.time() - t0)
        days = collect.candidate_days(today, 735)
        collect.update_revenue()
        st = collect.fill_market(days, lambda d: ["i_tp", "i_tw"], budget_s=max(left - 600, 60), today=today)
        print(f"[lab] 兩年投信買賣超回補：{st}")
        # 長線候選股（投信關＋動能關曾同時通過）才抓營收歷史，請求最少
        try:
            from arm.lab import analyze, growth
            P = growth.Panel(analyze.Data())
            bt = growth.backtest(P, {})
            print(f"[lab] 長線候選 {len(bt['cand_codes'])} 檔、篩選月份 {bt['months']}")
            collect.backfill_rev_hist(bt["cand_codes"], budget_s=max(a.budget_min * 60 - (_t.time() - t0), 60))
        except Exception as e:                            # noqa: BLE001
            print(f"[lab] 營收歷史步驟失敗：{type(e).__name__}: {e}")
        return
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
