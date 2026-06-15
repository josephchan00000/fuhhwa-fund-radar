"""SQLite 落地層（Phase 0）。schema 對應 docs/SPEC.md §5，正式版可換 PostgreSQL。

所有事實表以 (代號, 日期[, 個股]) 為主鍵 → upsert 冪等，同日重跑不重複。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "arm.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS etf_daily (
    etf_id TEXT, trade_date TEXT,
    close REAL, change_pct REAL, nav REAL, premium_disc REAL,
    aum REAL, units REAL, volume INTEGER,
    src_price TEXT, src_nav TEXT,         -- 來源標記（稽核用）
    PRIMARY KEY (etf_id, trade_date)
);
CREATE TABLE IF NOT EXISTS holdings_daily (
    etf_id TEXT, trade_date TEXT, stock_id TEXT, stock_name TEXT,
    shares INTEGER, market_value REAL, weight REAL,
    PRIMARY KEY (etf_id, trade_date, stock_id)
);
CREATE TABLE IF NOT EXISTS price_history (
    code TEXT, trade_date TEXT, close REAL, volume INTEGER,
    PRIMARY KEY (code, trade_date)
);
CREATE TABLE IF NOT EXISTS nav_history (    -- NAV 含息總報酬骨幹（權威：復華 assetsExcel）
    etf_id TEXT, trade_date TEXT,
    nav REAL, aum REAL, units REAL,
    PRIMARY KEY (etf_id, trade_date)
);
CREATE TABLE IF NOT EXISTS holders_history (  -- 受益人數週快照（權威：集保 TDCC 股權分散）
    etf_id TEXT, data_date TEXT, holders INTEGER,
    PRIMARY KEY (etf_id, data_date)
);
CREATE TABLE IF NOT EXISTS signals (
    etf_id TEXT, trade_date TEXT, detector TEXT,
    strength REAL, score REAL, headline TEXT, evidence TEXT,
    PRIMARY KEY (etf_id, trade_date, detector)
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    cols = ",".join(row)
    ph = ",".join("?" * len(row))
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({ph})",
        list(row.values()),
    )
