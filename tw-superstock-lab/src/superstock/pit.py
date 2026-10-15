"""Point-in-time：每筆基本面資料「最早什麼時候看得到」。

一律用法定公告期限（保守做法）：實際公告常比期限早，但回測用期限可確保沒有偷看未來。
  月營收：次月 10 日前公告 → 可用日 = 次月 10 日
  財報（2013 年起，IFRS 與證交法 36 條修正後）：
      Q1 → 5/15、Q2 → 8/14、Q3 → 11/14、年報 → 次年 3/31
  財報（2012 年以前的舊制，取較晚者以保守）：
      Q1 → 4/30、Q2（半年報）→ 8/31、Q3 → 10/31、年報 → 次年 4/30
訊號在「可用日當天收盤後」計算，最早下一個交易日進場；交易日對齊在回測引擎處理。
"""

from __future__ import annotations

import pandas as pd

IFRS_CUTOVER = pd.Timestamp("2013-01-01")


def revenue_available_date(revenue_year: int, revenue_month: int) -> pd.Timestamp:
    year, month = int(revenue_year), int(revenue_month) + 1
    if month == 13:
        year, month = year + 1, 1
    return pd.Timestamp(year=year, month=month, day=10)


def financial_available_date(period_end: pd.Timestamp) -> pd.Timestamp:
    p = pd.Timestamp(period_end)
    y, m = p.year, p.month
    if p < IFRS_CUTOVER:
        table = {3: (y, 4, 30), 6: (y, 8, 31), 9: (y, 10, 31), 12: (y + 1, 4, 30)}
    else:
        table = {3: (y, 5, 15), 6: (y, 8, 14), 9: (y, 11, 14), 12: (y + 1, 3, 31)}
    if m in table and p.is_month_end:
        yy, mm, dd = table[m]
        return pd.Timestamp(year=yy, month=mm, day=dd)
    # 非季底日期（資料異常）：保守給 120 天，並由品質檢查列出
    return p + pd.Timedelta(days=120)


def add_revenue_availability(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["available_date"] = [
        revenue_available_date(y, m) for y, m in zip(out["revenue_year"], out["revenue_month"])
    ]
    out["period"] = [pd.Timestamp(year=int(y), month=int(m), day=1)
                     for y, m in zip(out["revenue_year"], out["revenue_month"])]
    return out


def add_financial_availability(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["period_end"] = pd.to_datetime(out["date"], errors="coerce")
    out["available_date"] = [
        financial_available_date(d) if pd.notna(d) else pd.NaT for d in out["period_end"]
    ]
    return out
