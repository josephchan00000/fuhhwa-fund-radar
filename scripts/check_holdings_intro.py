#!/usr/bin/env python3
"""前十大持股「簡介覆蓋率」防呆閘門（2026-07-23 使用者需求：前十大簡介一再漏掉）。

掃所有 data/funds/*.json 的前十大持股，比對 config/holding_profiles.json 是否都有 intro；
把缺口寫進 data/holdings_intro_gap.json（儀表板讀它顯示 ⚠ 警示章、CI 一併 commit），
並印出可直接照著補的清單。

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
    GAP_FP.parent.mkdir(parents=True, exist_ok=True)
    GAP_FP.write_text(json.dumps(
        {"as_of": clock.stamp_tw(), "count": len(gaps),
         "items": [{"name": g["name"], "sector": g.get("sector"),
                    "count": g["count"],
                    "funds": [f["short_name"] for f in g["funds"]]} for g in gaps]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    if not gaps:
        print("[前十大簡介] 🟢 全數基金前十大持股皆有簡介（0 缺口）")
        return 0
    print(f"[前十大簡介] 🔴 {len(gaps)} 檔前十大持股缺簡介——請補進 config/holding_profiles.json：")
    for g in gaps:
        funds = "、".join(f'{f["short_name"]}({f["weight"]}%)' for f in g["funds"])
        print(f'  ✗ {g["name"]}（{g.get("sector") or ""}，出現於 {g["count"]} 檔：{funds}）')
    print("  補法：WebSearch 查證後，於 profiles 加 {name: {intro, ticker, country, verified}}。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
