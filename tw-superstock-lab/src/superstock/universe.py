"""股票池：上市＋上櫃普通股，含研究期間內下市櫃的股票。

FinMind TaiwanStockInfo 的 date＝該列最後更新日（2026-10 實測：2020-06-03～今天）。仍掛牌的股票每天更新，
已下市的股票停在下市前後——所以「現在掛牌」＝最後更新日接近整張表的最新日；更新日停在過去的是已下市，
下市日優先用 TaiwanStockDelisting，沒有就用最後更新日（2026-10-15 實測：原本把這些都當成上市，
股票池 2,225 檔裡只認得 81 檔下市，另有 238 檔被誤報成「代號重複使用」）。
"""

from __future__ import annotations

import re

import pandas as pd

from .config import UniverseConfig

# 4 碼代號已排除 00 開頭 ETF、權證、特別股；產業別再擋一層保險
_EXCLUDED_INDUSTRY_KEYWORDS = ("ETF", "ETN", "指數", "受益證券", "存託憑證", "Index", "大盤")
# 最後更新日距整張表最新日在幾天內仍算「現在掛牌」（停牌幾天的不會被誤判成下市）
STALE_DAYS = 10
COLS = ["stock_id", "stock_name", "market", "industry", "is_delisted", "delist_date"]


def _filter_info(info: pd.DataFrame | None, cfg: UniverseConfig) -> pd.DataFrame:
    if info is None or info.empty:
        return pd.DataFrame(columns=["stock_id", "stock_name", "type", "industry_category", "date"])
    pattern = re.compile(cfg.stock_id_pattern)
    df = info.copy()
    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    df = df[df["stock_id"].map(lambda s: bool(pattern.match(s)))]
    if "type" in df.columns:
        df = df[df["type"].isin(cfg.markets)]
    industry = df.get("industry_category", pd.Series("", index=df.index)).fillna("").astype(str)
    df = df[~industry.map(lambda s: any(k in s for k in _EXCLUDED_INDUSTRY_KEYWORDS))].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce") if "date" in df.columns else pd.NaT
    # 同一檔有多列（多個產業別、換市場）：留最後更新的一列
    return df.sort_values("date", kind="stable").drop_duplicates("stock_id", keep="last")


def _filter_delisting(delisting: pd.DataFrame | None, cfg: UniverseConfig, start_date: str) -> pd.DataFrame:
    if delisting is None or delisting.empty:
        return pd.DataFrame(columns=["stock_id", "stock_name", "delist_date"])
    pattern = re.compile(cfg.stock_id_pattern)
    d = delisting.copy()
    d["stock_id"] = d["stock_id"].astype(str).str.strip()
    d = d[d["stock_id"].map(lambda s: bool(pattern.match(s)))]
    d["delist_date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d[d["delist_date"] >= pd.Timestamp(start_date)]
    return d.sort_values("delist_date").drop_duplicates("stock_id", keep="last")


def split_info(info: pd.DataFrame | None, cfg: UniverseConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """（現在掛牌, 已不再更新＝已下市）兩張表。"""
    df = _filter_info(info, cfg)
    if df.empty or df["date"].isna().all():
        return df, df.iloc[0:0]
    latest = df["date"].max()
    current = df["date"] >= latest - pd.Timedelta(days=STALE_DAYS)
    return df[current], df[~current]


def build_universe(info: pd.DataFrame, delisting: pd.DataFrame | None,
                   cfg: UniverseConfig, start_date: str) -> pd.DataFrame:
    """回傳欄位：stock_id, stock_name, market, industry, is_delisted, delist_date。"""
    current, stale = split_info(info, cfg)
    listed = pd.DataFrame({
        "stock_id": current["stock_id"].values,
        "stock_name": current.get("stock_name", pd.Series("", index=current.index)).values,
        "market": current.get("type", pd.Series("unknown", index=current.index)).values,
        "industry": current.get("industry_category", pd.Series("", index=current.index)).values,
        "is_delisted": False,
        "delist_date": pd.NaT,
    })
    if not cfg.include_delisted:
        return listed.sort_values("stock_id").reset_index(drop=True)

    d = _filter_delisting(delisting, cfg, start_date)
    d_date = dict(zip(d["stock_id"], d["delist_date"]))
    # ① 清單裡已不再更新的：下市日用下市表（要在最後更新日附近或之後），否則用最後更新日
    rows = []
    for r in stale.itertuples(index=False):
        dd = d_date.get(r.stock_id)
        if dd is None or pd.isna(dd) or dd < r.date - pd.Timedelta(days=60):
            dd = r.date
        if pd.isna(dd) or dd < pd.Timestamp(start_date):
            continue
        rows.append({"stock_id": r.stock_id, "stock_name": getattr(r, "stock_name", ""),
                     "market": getattr(r, "type", "unknown"), "industry": getattr(r, "industry_category", ""),
                     "is_delisted": True, "delist_date": dd})
    from_stale = pd.DataFrame(rows, columns=COLS)
    # ② 只在下市表、不在股票清單的（多半是 2020 年以前下市）
    known = set(current["stock_id"]) | set(stale["stock_id"])
    only = d[~d["stock_id"].isin(known)]
    from_delisting = pd.DataFrame({
        "stock_id": only["stock_id"].values,
        "stock_name": only.get("stock_name", pd.Series("", index=only.index)).values,
        "market": "unknown", "industry": "", "is_delisted": True,
        "delist_date": only["delist_date"].values,
    })
    frames = [f for f in (listed, from_stale, from_delisting) if not f.empty]
    if not frames:
        return pd.DataFrame(columns=COLS)
    out = pd.concat(frames, ignore_index=True)
    out["is_delisted"] = out["is_delisted"].astype(bool)
    out["delist_date"] = pd.to_datetime(out["delist_date"])
    return out.sort_values("stock_id").reset_index(drop=True)


def reused_codes(info: pd.DataFrame, delisting: pd.DataFrame | None, start_date: str,
                 cfg: UniverseConfig | None = None) -> list[str]:
    """現在掛牌、卻在研究期間內有下市紀錄的普通股代號（代號被重新使用，或下市後重新上市）。"""
    cfg = cfg or UniverseConfig()
    current, _ = split_info(info, cfg)
    d = _filter_delisting(delisting, cfg, start_date)
    return sorted(set(current["stock_id"]) & set(d["stock_id"]))
