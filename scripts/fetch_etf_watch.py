#!/usr/bin/env python3
"""抓「ETF 數據追蹤」分頁資料（台股被動／主動 ETF 週績效）→ data/etf_watch.json。

追蹤清單與欄位定義見 arm/etfwatch.py（被動 6 檔＋主動 11 檔；規模／成立日期／
過去一週・一月報酬／配息殖利率／收益分配頻率）。來源 etfinfo.tw（Tier B）。

防呆（同專案鐵則）：來源不可達或欄位缺漏 → 逐檔沿用既有落檔的值；整批全空
→ 不覆寫既有非空落檔。雲端 Claude 容器 proxy 會擋 etfinfo.tw／TWSE——本腳本
在該環境跑等於 no-op，由 GitHub Actions（台北週一~六 06:50）自動補抓。

用法：TZ=Asia/Taipei python3 scripts/fetch_etf_watch.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import etfwatch  # noqa: E402


def main() -> None:
    print(f"[ETF 數據追蹤] 抓取 {len(etfwatch.WATCHLIST)} 檔"
          "（規模／殖利率←etfinfo.tw；週／月報酬←TWSE 官方收盤）…")
    doc = etfwatch.fetch()
    fresh = sum(1 for i in doc["items"] if str(i.get("src")).startswith("etfinfo"))
    path, saved = etfwatch.save(doc)
    if saved:
        print(f"  ✓ 落檔 {path}（{len(doc['items'])} 檔，{fresh} 檔有新值，"
              f"規模基準 {doc['as_of']}／報酬基準 {doc.get('perf_asof')}）")
    else:
        print(f"  ⚠ 本次擷取全空、既有落檔非空 → 保留舊檔不覆寫（{path}）")


if __name__ == "__main__":
    main()
