"""股票池：上市＋上櫃普通股，含研究期間內下市櫃的股票。"""

from __future__ import annotations

import re

import pandas as pd

from .config import UniverseConfig

# 4 碼代號已排除 00 開頭 ETF、權證、特別股；產業別再擋一層保險
_EXCLUDED_INDUSTRY_KEYWORDS = ("ETF", "ETN", "指數", "受益證券", "存託憑證", "Index", "大盤")


def build_universe(info: pd.DataFrame, delisting: pd.DataFrame | None,
                   cfg: UniverseConfig, start_date: str) -> pd.DataFrame:
    """回傳欄位：stock_id, stock_name, market, industry, is_delisted, delist_date。"""
    pattern = re.compile(cfg.stock_id_pattern)
    cols = ["stock_id", "stock_name", "market", "industry", "is_delisted", "delist_date"]

    listed = pd.DataFrame(columns=cols)
    if info is not None and not info.empty:
        df = info.copy()
        df["stock_id"] = df["stock_id"].astype(str).str.strip()
        df = df[df["stock_id"].map(lambda s: bool(pattern.match(s)))]
        if "type" in df.columns:
            df = df[df["type"].isin(cfg.markets)]
        industry = df.get("industry_category", pd.Series("", index=df.index)).fillna("").astype(str)
        mask = ~industry.map(lambda s: any(k in s for k in _EXCLUDED_INDUSTRY_KEYWORDS))
        df = df[mask]
        if "date" in df.columns:
            df = df.sort_values("date", kind="stable")
        df = df.drop_duplicates("stock_id", keep="last")
        listed = pd.DataFrame({
            "stock_id": df["stock_id"].values,
            "stock_name": df.get("stock_name", pd.Series("", index=df.index)).values,
            "market": df.get("type", pd.Series("unknown", index=df.index)).values,
            "industry": df.get("industry_category", pd.Series("", index=df.index)).values,
            "is_delisted": False,
            "delist_date": pd.NaT,
        })

    if not cfg.include_delisted or delisting is None or delisting.empty:
        return listed.sort_values("stock_id").reset_index(drop=True)

    d = delisting.copy()
    d["stock_id"] = d["stock_id"].astype(str).str.strip()
    d = d[d["stock_id"].map(lambda s: bool(pattern.match(s)))]
    d["delist_date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d[d["delist_date"] >= pd.Timestamp(start_date)]
    d = d.sort_values("delist_date").drop_duplicates("stock_id", keep="last")
    # 代號仍在現行清單裡的（代號被重新使用，或清單尚未更新）不重複加入；品質檢查會另外列出
    d = d[~d["stock_id"].isin(listed["stock_id"])]
    delisted = pd.DataFrame({
        "stock_id": d["stock_id"].values,
        "stock_name": d.get("stock_name", pd.Series("", index=d.index)).values,
        "market": "unknown",
        "industry": "",
        "is_delisted": True,
        "delist_date": d["delist_date"].values,
    })
    frames = [f for f in (listed, delisted) if not f.empty]
    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    out["is_delisted"] = out["is_delisted"].astype(bool)
    return out.sort_values("stock_id").reset_index(drop=True)


def reused_codes(info: pd.DataFrame, delisting: pd.DataFrame | None, start_date: str) -> list[str]:
    """同時出現在現行清單與（研究期間內）下市清單的代號，可能是代號重複使用。"""
    if delisting is None or delisting.empty or info is None or info.empty:
        return []
    d = delisting.copy()
    d["delist_date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d[d["delist_date"] >= pd.Timestamp(start_date)]
    both = set(d["stock_id"].astype(str)) & set(info["stock_id"].astype(str))
    return sorted(both)
