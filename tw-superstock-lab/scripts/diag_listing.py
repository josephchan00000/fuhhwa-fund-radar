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


def universe_vs_official(client: FinMindClient, cfg, off: pd.DataFrame) -> None:
    """股票池（FinMind 清單＋下市表）vs 官方現在上市櫃名單：被判下市的有幾檔其實還在官方名單上。"""
    from superstock.universe import build_universe, split_info
    info = client.get("TaiwanStockInfo")
    dl = client.get("TaiwanStockDelisting")
    uni = build_universe(info, dl, cfg.universe, cfg.start_date)
    current, stale = split_info(info, cfg.universe)
    o = set(off["stock_id"])
    listed = uni[~uni["is_delisted"]]
    de = uni[uni["is_delisted"]].copy()
    de["in_official"] = de["stock_id"].isin(o)
    de["year"] = pd.to_datetime(de["delist_date"]).dt.year
    de["src"] = de["stock_id"].isin(set(stale["stock_id"])).map({True: "清單停更", False: "只在下市表"})
    print(f"\n[股票池] 上市櫃 {len(listed)}（其中不在官方名單 {int((~listed.stock_id.isin(o)).sum())}）、"
          f"下市 {len(de)}（其中仍在官方名單 {int(de.in_official.sum())}）；官方名單 {len(o)} 檔"
          f"（不在股票池 {len(o - set(uni.stock_id))}）")
    print(de.groupby(["year", "src"])["in_official"].agg(["size", "sum"]).to_string())
    print("   仍在官方名單、卻被判下市（前 25）：", de[de.in_official][["stock_id", "stock_name", "delist_date", "src"]]
          .head(25).to_dict("records"))
    print("   官方名單有、股票池沒有（前 25）：", sorted(o - set(uni.stock_id))[:25])
    print("   上市櫃但不在官方名單（前 25）：", listed[~listed.stock_id.isin(o)][["stock_id", "stock_name", "market"]]
          .head(25).to_dict("records"))
    dl2 = dl.copy()
    dl2["year"] = pd.to_datetime(dl2["date"], errors="coerce").dt.year
    dl2["code4"] = dl2["stock_id"].astype(str).str.fullmatch(r"[1-9]\d{3}")
    print("   下市表各年筆數（4 碼普通股）：", dl2[dl2.code4].groupby("year").size().to_dict())
    st = stale.copy()
    st["year"] = pd.to_datetime(st["date"]).dt.year
    print("   清單停更各年檔數：", st.groupby("year").size().to_dict())
    # 停更的是什麼：同代號在清單裡的所有列（含興櫃列）、是否在下市表
    allinfo = info.copy()
    allinfo["stock_id"] = allinfo["stock_id"].astype(str)
    dlset = set(dl["stock_id"].astype(str))
    for y in (2024, 2026, 2023):
        sub = st[st["year"] == y].head(12)
        print(f"   ── 清單停更 {y} 年（前 12 檔）")
        for r in sub.itertuples(index=False):
            rows = allinfo[allinfo["stock_id"] == r.stock_id][["type", "industry_category", "date"]]
            print("     ", r.stock_id, r.stock_name, "| 下市表" if r.stock_id in dlset else "| 不在下市表",
                  "|", rows.to_dict("records"))
    return st


def main(argv: list[str]) -> None:
    detail = "--detail" in argv
    codes = [a for a in argv if not a.startswith("--")]
    cfg = load_config("config.yaml")
    client = FinMindClient(get_token(cfg), cfg.finmind)
    off = fetch_official(requests.Session())
    print(f"[官方] {len(off)} 檔有上市櫃日（twse {int((off.market == 'twse').sum())}、tpex {int((off.market == 'tpex').sum())}）")
    st = universe_vs_official(client, cfg, off)
    # 停更股票的日 K 型態：整段主板規則符合率（主板 ~99%、興櫃 0–33%）
    today0 = pd.Timestamp.now().date().isoformat()
    sample = list(st[st["year"] == 2024]["stock_id"].head(8)) + list(st[st["year"] == 2026]["stock_id"].head(8))
    for code in sample:
        p = client.get("TaiwanStockPrice", code, "2008-01-01", today0)
        if p.empty:
            print(f"   [停更日 K] {code}: 沒有日 K")
            continue
        p = p.sort_values("date")
        m = match_series(p["close"], p["spread"])
        _, inf = trim(p.rename(columns={"Trading_Volume": "volume"}).assign(stock_id=code), None)
        r = inf.iloc[0]
        print(f"   [停更日 K] {code}: {p['date'].iloc[0]}～{p['date'].iloc[-1]}（{len(p)} 筆）整段符合率 {pd.Series(m).mean():.2f}"
              f"、主板首日 {r.main_start}、主板末日 {r.main_end}")
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
