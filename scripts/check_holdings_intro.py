#!/usr/bin/env python3
"""持股「簡介覆蓋率」防呆閘門（2026-07-23 使用者需求：前十大簡介一再漏掉）。

掃所有 data/funds/*.json 的前十大持股，以及 data/etf_holdings.json 每檔 ETF 的完整持股
（2026-10-21 起：ETF 持股原本只有測試的 95% 門檻守，主動式 ETF 天天換股、滑到 97% 沒人發現），
比對 config/holding_profiles.json 是否都有 intro；把缺口寫進 data/holdings_intro_gap.json
（儀表板讀它顯示 ⚠ 警示章、CI 一併 commit），並印出可直接照著補的清單。
缺口檔 items：基金前十大 `src: "fund"`；ETF 持股 `src: "etf"`，另帶 `ticker`（補進 profiles 的代號）與 `etfs`；
美股三成（配置頁美股列的股票，2026-10-24 起）`src: "usqm"`，帶 `ticker`（name＝英文公司名，沒有就是代號）。

**根因**：持股在正式區 CI 抓（容器 proxy 擋），每月換持股時新標的只出現在 CI 產出，
容器端看不到 → 本地檢查抓不到、漏的簡介直接上線。故此檢查在 **daily.yml 建表後跑**
（即時抓到 CI 新持股的缺口），並列入每日 SOP（下一輪由 Claude WebSearch 補進 profiles）。

exit code：有缺口 → 1（供想當硬閘門處使用）；全覆蓋 → 0。CI 端以 `|| true` 收警示、不擋發佈。
用法：TZ=Asia/Taipei python3 scripts/check_holdings_intro.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock, fund_intro  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAP_FP = ROOT / "data" / "holdings_intro_gap.json"


def main() -> int:
    gaps = fund_intro.uncovered_top_holdings(10)
    egaps = fund_intro.uncovered_etf_holdings()
    ugaps = fund_intro.uncovered_us_qm()
    items = ([{"src": "fund", "name": g["name"], "sector": g.get("sector"),
               "count": g["count"],
               "funds": [f["short_name"] for f in g["funds"]]} for g in gaps]
             + [{"src": "etf", "name": g["name"], "ticker": g["ticker"],
                 "count": g["count"], "etfs": g["etfs"], "weight": g["weight"]} for g in egaps]
             + [{"src": "usqm", "name": g["name"], "ticker": g["ticker"]} for g in ugaps])
    GAP_FP.parent.mkdir(parents=True, exist_ok=True)
    GAP_FP.write_text(json.dumps(
        {"as_of": clock.stamp_tw(), "count": len(items),
         "fund_count": len(gaps), "etf_count": len(egaps), "usqm_count": len(ugaps), "items": items},
        ensure_ascii=False, indent=1), encoding="utf-8")
    if not items:
        print("[持股簡介] 🟢 基金前十大、ETF 持股、美股三成皆有簡介（0 缺口）")
        return 0
    if gaps:
        print(f"[前十大簡介] 🔴 {len(gaps)} 檔前十大持股缺簡介——請補進 config/holding_profiles.json：")
        for g in gaps:
            funds = "、".join(f'{f["short_name"]}({f["weight"]}%)' for f in g["funds"])
            print(f'  ✗ {g["name"]}（{g.get("sector") or ""}，出現於 {g["count"]} 檔：{funds}）')
    if egaps:
        print(f"[ETF 持股簡介] 🔴 {len(egaps)} 檔 ETF 持股缺簡介——請補進 config/holding_profiles.json：")
        for g in egaps:
            print(f'  ✗ {g["name"]}（代號 {g["ticker"]}，{"、".join(g["etfs"])}，權重最高 {g["weight"]:g}%）')
    if ugaps:
        print(f"[美股三成簡介] 🔴 {len(ugaps)} 檔配置頁美股列的股票缺簡介——請補進 config/holding_profiles.json：")
        for g in ugaps:
            print(f'  ✗ {g["name"]}（代號 {g["ticker"]}）')
    print("  補法：WebSearch 查證後，於 profiles 加 {name: {intro, ticker, country, verified}}"
          "（ETF 持股、美股三成的 ticker 用清單上的代號；美股簡介照「美國 公司名，本業；細節」寫，配置頁取第一段顯示）。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
