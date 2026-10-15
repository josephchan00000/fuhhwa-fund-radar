"""診斷：FinMind 日 K 的興櫃（掛牌前）段，以及 listing.py 偵測到的主板首日 vs 官方上市櫃日（只印 CI 日誌）。

用法：python scripts/diag_listing.py [--detail] 6488 7769 ...
  預設：每檔一行（官方日、FinMind 第一筆、偵測到的主板首日、差幾個交易日、開頭 20 筆符合率）＋總結
  --detail：另列官方日前後幾列原始欄位（第一次調查用）
"""

from __future__ import annotations

import sys

import pandas as pd
import requests

from superstock.config import get_token, load_config
from superstock.finmind_client import FinMindClient
from superstock.listing import compare_official, fetch_official, match_series, trim


def main(argv: list[str]) -> None:
    detail = "--detail" in argv
    codes = [a for a in argv if not a.startswith("--")]
    cfg = load_config("config.yaml")
    client = FinMindClient(get_token(cfg), cfg.finmind)
    off = fetch_official(requests.Session())
    print(f"[官方] {len(off)} 檔有上市櫃日（twse {int((off.market == 'twse').sum())}、tpex {int((off.market == 'tpex').sum())}）")
    today = pd.Timestamp.now().date().isoformat()
    frames = []
    for code in codes:
        p = client.get("TaiwanStockPrice", code, "2008-01-01", today)
        if p.empty:
            print(f"== {code}: 沒有日 K")
            continue
        p = p.rename(columns={"Trading_Volume": "volume"}).sort_values("date").reset_index(drop=True)
        frames.append(p)
        if detail:
            o = off[off.stock_id == code]
            p["match"] = match_series(p["close"], p["spread"]) == 1.0
            k = int(p["date"].searchsorted(str(o["listing_date"].iloc[0].date()))) if len(o) else 0
            cols = ["date", "open", "max", "min", "close", "spread", "volume", "Trading_turnover", "match"]
            print(f"== {code}")
            print(p.iloc[max(0, k - 4):k + 3][cols].to_string(index=False))
    if not frames:
        return
    prices = pd.concat(frames, ignore_index=True)
    _, info = trim(prices, None)
    cal = pd.Series(sorted(pd.to_datetime(prices["date"]).unique()))
    m = info.merge(off, on="stock_id", how="left")
    print("\n代號  官方日      市場  FinMind第一筆  偵測主板首日  開頭符合率")
    for r in m.itertuples(index=False):
        det = "—" if pd.isna(r.main_start) else str(pd.Timestamp(r.main_start).date())
        offd = "—" if pd.isna(r.listing_date) else str(pd.Timestamp(r.listing_date).date())
        print(f"{r.stock_id}  {offd}  {r.market if isinstance(r.market, str) else '—':4s}  "
              f"{pd.Timestamp(r.first_raw).date()}  {det:12s}  {r.head_match:.2f}")
    res = compare_official(info, off, cal)
    print("\n[總結]", {k: v for k, v in res.items() if k != "examples"})
    for e in res.get("examples", []):
        print("   不一致：", e)


if __name__ == "__main__":
    main(sys.argv[1:])
