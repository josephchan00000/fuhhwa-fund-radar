#!/usr/bin/env python3
"""抓「復華各追蹤基金」的相關新聞提及 → data/mentions/{market}.json（基金動態雷達自動源）。

用 Google News RSS（arm/connectors/gnews：免金鑰、附發文時間 pubDate、近 N 天過濾），
逐檔基金＋公司層（復華投信）搜尋；每筆皆帶 title/url/source/date，可追溯。

用法：
  python scripts/fetch_mentions.py                # 海外版 → data/mentions/global.json
  python scripts/fetch_mentions.py --market tw    # 台股版 → data/mentions/tw.json
  python scripts/fetch_mentions.py --market all   # 兩市場都抓
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import config, fund_mentions  # noqa: E402
from arm.connectors import gnews       # noqa: E402

OUT_DIR = fund_mentions.AUTO_DIR

COMPANY_QUERIES = ['"復華投信"', '"復華基金"']


def run(market: str, days: int = 7, per_fund: int = 3) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    funds = config.funds(market)
    print(f"[基金動態雷達 ← Google News｜市場 {market}]　{datetime.now():%Y-%m-%d %H:%M}")
    company = gnews.search_many(COMPANY_QUERIES, days=days, limit=6)
    print(f"  公司層（復華投信）：{len(company)} 則")
    fund_rows = []
    for f in funds:
        terms = fund_mentions.query_terms(f.get("name") or "")
        items = gnews.search_many(terms, days=days, limit=per_fund) if terms else []
        fund_rows.append({"id": str(f["id"]), "name": f.get("name"), "items": items})
        if items:
            print(f"  ✓ {f['id']} {f.get('name', '')[:16]}：{len(items)} 則"
                  f"（最新 {items[0]['date']}）")
    doc = {"fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "market": market, "days": days,
           "company": company, "funds": fund_rows}
    (OUT_DIR / f"{market}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    total = len(company) + sum(len(r["items"]) for r in fund_rows)
    print(f"  共 {total} 則 → data/mentions/{market}.json")
    return doc


def main() -> None:
    market = "global"
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--market" and i + 1 < len(argv):
            market = argv[i + 1]
        elif a.startswith("--market="):
            market = a.split("=", 1)[1]
    for m in (("global", "tw") if market == "all" else (market,)):
        run(m)


if __name__ == "__main__":
    main()
