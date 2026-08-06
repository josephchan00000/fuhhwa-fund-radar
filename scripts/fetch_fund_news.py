#!/usr/bin/env python3
"""抓「基金相關新聞＋社群聲量」→ data/fund_news.json（儀表板「基金相關新聞・社群」區塊）。

來源：Google News RSS（品牌「復華投信」＋每檔基金基底名）＋ PTT 股票板公開標題。
免金鑰；任一來源抓不到誠實降級為空清單，照樣落檔（標 as-of），不影響儀表板其他區塊。

用法：
  python3 scripts/fetch_fund_news.py          # 全部（品牌＋各基金＋PTT）
  之後重跑 python3 scripts/gen_fund_dashboard.py 讓內容入板。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import fund_intro, fundnews  # noqa: E402


def main() -> None:
    funds = fund_intro.all_funds()
    doc = fundnews.assemble(funds)
    path, saved = fundnews.save(doc)
    if not saved:
        prev = fundnews.load() or {}
        print(f"[基金新聞・社群] ⚠ 本次擷取全空（多為網路被擋/來源異常），"
              f"保留前次落檔不覆寫（更新 {prev.get('as_of') or '—'}）")
        return
    n_fund = sum(1 for g in doc["funds"] if g["items"])
    yts = [s for s in doc["social"] if (s.get("platform") or "") == "youtube"]
    n_of = sum(1 for s in yts if s.get("official"))
    n_peer = sum(1 for s in yts if s.get("peer"))
    print(f"[基金新聞・社群] 已寫入 {path}")
    print(f"  品牌新聞 {len(doc['brand'])} 則｜有專屬新聞的基金 {n_fund}/{len(doc['funds'])} 檔"
          f"｜PTT 討論 {len(doc['social']) - len(yts)} 則"
          f"｜YouTube {len(yts)} 支（官方 {n_of}・相關 {len(yts) - n_of - n_peer}・同業 {n_peer}）"
          + ("" if yts or fundnews._yt_key() else "（未設 YOUTUBE_API_KEY）"))


if __name__ == "__main__":
    main()
