#!/usr/bin/env python3
"""自動擷取每檔『近一週、帶發文時間』的新聞 → data/fast/news_{code}.json（儀表板口碑區自動更新）。

每次更新都要最新：新聞不靠人工，依各檔關鍵字即時拉 Google News（台灣繁中）、過濾近 7 天、
附來源與發文時間。儀表板「本檔話題＋口碑」會把這些自動列入並標日期。落檔即生效、引擎不動。

用法：
  python scripts/fetch_news.py            # 全主角
  python scripts/fetch_news.py 00991A     # 指定
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import config  # noqa: E402
from arm.connectors import gnews  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAST_DIR = ROOT / "data" / "fast"

# 各檔新聞關鍵字（含本檔代號/名稱 + 題材/同類，抓到的偏向相關）
QUERIES = {
    "00991A": ["復華台灣未來50 OR 00991A", "主動式ETF 台股", "記憶體 南亞科 OR 華邦電"],
    "00998A": ["復華金融股息 OR 00998A", "金融股 ETF 配息 OR 除息", "ETF 除息 高股息", "全球金融股 投資"],
    "00986D": ["金融債 OR 投資級債 ETF", "債券ETF 配息 OR 除息", "美債 降息 殖利率", "00986D OR 復華金融債息"],
}


def fetch(code: str) -> dict:
    qs = QUERIES.get(code) or [code]
    items = gnews.search_many(qs, days=7, limit=6)
    doc = {
        "etf": code, "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "window": "近 7 天", "source": "Google News（台灣繁中）自動擷取，發文時間為來源 pubDate",
        "items": items,
    }
    FAST_DIR.mkdir(parents=True, exist_ok=True)
    (FAST_DIR / f"news_{code}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def main() -> None:
    codes = sys.argv[1:] or [p["id"] for p in config.load()["fh_products"]]
    print(f"[自動新聞 ← Google News 近7天]　{datetime.now():%Y-%m-%d %H:%M}")
    for code in codes:
        try:
            doc = fetch(code)
        except Exception as e:
            print(f"  ✗ {code}：新聞擷取失敗（{type(e).__name__}：{e}）")
            continue
        print(f"  ✓ {code}：{len(doc['items'])} 則近一週新聞")
        for it in doc["items"][:4]:
            print(f"      [{it['date']}] {it['source']}｜{it['title'][:42]}")


if __name__ == "__main__":
    main()
