"""NAV 含息總報酬骨幹（M1-4）。

為什麼用 NAV 當績效主軸：
  - 00998A/00986D 是全球股票/債券，本身在 TWSE 無收盤序列（不像 00991A），
    價格報酬無從算起；唯一權威的每日績效來源是復華官網 NAV。
  - NAV 本就是「淨值」，配上配息再投入＝含息總報酬，比價格報酬更貼近投資人實得。

流程：
  1. 由交易日曆（0050 序列）取得 [inception, latest] 的交易日。
  2. 對缺漏日逐日抓 assetsExcel 取 NAV/AUM/單位數 → 落地 nav_history（冪等）。
  3. total_return_series() 把配息再投入，產出含息總報酬指數；無配息時等同 NAV。
"""
from __future__ import annotations

import time

from . import db
from .connectors import fhtrust


def backfill(conn, etf_id: str, fund_id: str, days: list[str],
             *, throttle: float = 0.0, verbose: bool = False) -> int:
    """補齊 nav_history：days 內尚未入庫者逐日抓取。回傳新增筆數。"""
    have = {r[0] for r in conn.execute(
        "SELECT trade_date FROM nav_history WHERE etf_id=?", (etf_id,))}
    missing = [d for d in days if d not in have]
    added = 0
    for d in missing:
        try:
            snap = fhtrust.fetch_holdings(fund_id, d)
        except fhtrust.NoData:
            continue                      # 該交易日無揭露（成立前／尚未公告）
        db.upsert(conn, "nav_history", {
            "etf_id": etf_id, "trade_date": d,
            "nav": snap["nav"], "aum": snap["aum"], "units": snap["units"]})
        added += 1
        if verbose and added % 20 == 0:
            print(f"    …{etf_id} 已補 {added}/{len(missing)}")
        if throttle:
            time.sleep(throttle)
    if added:
        conn.commit()
    return added


def load_nav(conn, etf_id: str) -> list[tuple[str, float]]:
    """回傳 [(trade_date, nav)] 遞增。"""
    rows = conn.execute(
        "SELECT trade_date, nav FROM nav_history WHERE etf_id=? AND nav IS NOT NULL "
        "ORDER BY trade_date", (etf_id,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def load_aum(conn, etf_id: str) -> list[tuple[str, float]]:
    rows = conn.execute(
        "SELECT trade_date, aum FROM nav_history WHERE etf_id=? AND aum IS NOT NULL "
        "ORDER BY trade_date", (etf_id,)).fetchall()
    return [(r[0], r[1]) for r in rows]


def total_return_series(nav_rows: list[tuple[str, float]],
                        dividends: dict[str, float] | None = None
                        ) -> list[tuple[str, float, int]]:
    """把 [(date, nav)] 轉成含息總報酬序列 [(date, tr_index, 0)]（可直接餵 metrics.multi_period）。

    配息再投入：除息日當天 NAV 已扣息，用每單位配息 C 以當日 NAV 加買單位數
    → units *= (nav + C) / nav；無配息時 tr_index == nav（與純 NAV 報酬一致）。
    """
    divs = dividends or {}
    units = 1.0
    out: list[tuple[str, float, int]] = []
    for d, nav in nav_rows:
        c = divs.get(d)
        if c and nav:
            units *= (nav + c) / nav
        out.append((d, units * nav, 0))
    return out
