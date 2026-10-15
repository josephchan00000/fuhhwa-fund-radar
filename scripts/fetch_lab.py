#!/usr/bin/env python3
"""籌碼雷達每日落檔（CI 用；本容器 proxy 擋 twse/tpex/tdcc，在此跑只會全數失敗）。

  python3 scripts/fetch_lab.py            # ETF 部位快照＋近幾個交易日缺的官方部件＋集保週表
  python3 scripts/fetch_lab.py --pos-only # 只把 data/etf_holdings.json 寫進 pos 分片（零網路）

冪等：資料齊的日子零請求；抓不到沿用既有分片。失敗一律不擋呼叫端（exit 0）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock  # noqa: E402
from arm.lab import collect, market  # noqa: E402

RECENT_CAL_DAYS = 10     # 每輪檢查最近 10 個日曆天（含連假後補抓）


def main() -> None:
    n = collect.update_pos_from_current()
    print(f"[lab] pos 分片更新 {n} 檔")
    if "--extra" in sys.argv[1:]:
        # 擴充 ETF 只在持股班次跑（etf_holdings.yml）：以已追蹤 ETF 的最新揭露日為基準，到位者跳過
        import json
        try:
            hd = json.loads(collect.HOLD_FP.read_text(encoding="utf-8"))
            ref = max((e.get("date") or "" for e in (hd.get("etfs") or {}).values()), default=None)
        except Exception:                                 # noqa: BLE001
            ref = None
        collect.update_extra_etfs(ref)
    if "--pos-only" in sys.argv[1:] or "--extra" in sys.argv[1:]:
        return
    today = clock.today_tw()
    days = collect.candidate_days(today, RECENT_CAL_DAYS)
    st = collect.fill_market(days, lambda d: list(market.ALL_PARTS), budget_s=240, today=today)
    print(f"[lab] 官方市場分片：{st}")
    try:
        collect.update_tdcc()
    except Exception as e:                                # noqa: BLE001
        print(f"[lab] TDCC 失敗：{e}")
    try:
        collect.update_revenue()
    except Exception as e:                                # noqa: BLE001
        print(f"[lab] 月營收失敗：{e}")
    try:                                                  # 回測 v3：財報驚喜用的綜合損益表彙總（每季一次）、月底市值快照
        from arm.lab import v3data
        print(f"[lab] 綜合損益彙總補 {v3data.update_isq()} 季、月底市值快照補 {v3data.me_from_mkt()} 筆")
    except Exception as e:                                # noqa: BLE001
        print(f"[lab] 回測 v3 每日維護失敗：{e}")
    collect.prune_all(today)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                                # noqa: BLE001 —— 不擋呼叫端
        print(f"[lab] fetch_lab 失敗（不影響其他步驟）：{type(e).__name__}: {e}")
