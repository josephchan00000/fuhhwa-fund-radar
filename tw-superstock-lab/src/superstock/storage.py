"""本機儲存：原始資料（每個資料集一個資料夾、每檔股票一個 Parquet）與下載進度（SQLite）。"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .datasets import DatasetSpec

GLOBAL_KEY = "_global"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, raw_dir: Path):
        self.raw_dir = Path(raw_dir)

    def dir(self, spec: DatasetSpec) -> Path:
        return self.raw_dir / spec.store_name

    def path(self, spec: DatasetSpec, key: str) -> Path:
        return self.dir(spec) / f"{key}.parquet"

    def read(self, spec: DatasetSpec, key: str) -> pd.DataFrame | None:
        p = self.path(spec, key)
        if not p.exists():
            return None
        return pd.read_parquet(p)

    def keys(self, spec: DatasetSpec) -> list[str]:
        d = self.dir(spec)
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.parquet"))

    def read_all(self, spec: DatasetSpec, keys: list[str] | None = None) -> pd.DataFrame:
        frames = []
        for key in keys if keys is not None else self.keys(spec):
            df = self.read(spec, key)
            if df is not None and not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        return _dedupe(out, spec)

    def merge_write(self, spec: DatasetSpec, key: str, new: pd.DataFrame,
                    replace: bool = False) -> int:
        """把新資料併入既有檔案（依去重鍵保留最新一筆），原子寫入。回傳總列數。"""
        existing = None if replace else self.read(spec, key)
        frames = [f for f in (existing, new) if f is not None and not f.empty]
        if not frames:
            return 0
        combined = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        combined = _dedupe(combined, spec)
        target = self.path(spec, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        combined.to_parquet(tmp, index=False)
        os.replace(tmp, target)
        return len(combined)


def _dedupe(df: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    keys = [c for c in ("stock_id",) + spec.key_cols if c in df.columns]
    has_all_keys = spec.key_cols and all(c in df.columns for c in spec.key_cols)
    if has_all_keys:
        df = df.drop_duplicates(subset=keys, keep="last")
    else:
        df = df.drop_duplicates(keep="last")
    sort_cols = [c for c in ("stock_id", "date", "revenue_year", "revenue_month") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, kind="stable")
    return df.reset_index(drop=True)


class Manifest:
    """記錄每個（資料集, 股票）的下載狀態，讓下載可以中斷後續傳、每日增量更新。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                store TEXT NOT NULL,
                key TEXT NOT NULL,
                status TEXT NOT NULL,          -- done | empty | failed
                rows INTEGER DEFAULT 0,
                last_start TEXT,
                last_end TEXT,
                updated_utc TEXT,
                error TEXT,
                attempts INTEGER DEFAULT 0,
                PRIMARY KEY (store, key)
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS datasets (
                store TEXT PRIMARY KEY,
                resolved_mode TEXT,
                disabled_reason TEXT,
                updated_utc TEXT
            )"""
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- tasks ----
    def get(self, store: str, key: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT status, rows, last_start, last_end, updated_utc, error, attempts "
            "FROM tasks WHERE store=? AND key=?", (store, key))
        row = cur.fetchone()
        if row is None:
            return None
        cols = ["status", "rows", "last_start", "last_end", "updated_utc", "error", "attempts"]
        return dict(zip(cols, row))

    def _upsert(self, store: str, key: str, status: str, rows: int, start: str | None,
                end: str | None, error: str | None) -> None:
        prev = self.get(store, key)
        attempts = (prev["attempts"] if prev else 0) + 1
        self.conn.execute(
            """INSERT INTO tasks (store, key, status, rows, last_start, last_end, updated_utc, error, attempts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(store, key) DO UPDATE SET
                 status=excluded.status, rows=excluded.rows, last_start=excluded.last_start,
                 last_end=excluded.last_end, updated_utc=excluded.updated_utc,
                 error=excluded.error, attempts=excluded.attempts""",
            (store, key, status, rows, start, end, _utc_now(), error, attempts))
        self.conn.commit()

    def mark_done(self, store: str, key: str, rows: int, start: str | None, end: str | None) -> None:
        self._upsert(store, key, "done", rows, start, end, None)

    def mark_empty(self, store: str, key: str, start: str | None, end: str | None) -> None:
        self._upsert(store, key, "empty", 0, start, end, None)

    def mark_failed(self, store: str, key: str, error: str) -> None:
        prev = self.get(store, key)
        # 失敗時保留上次成功的區間（連續失敗也不覆蓋），增量更新才知道從哪裡接
        start = prev["last_start"] if prev else None
        end = prev["last_end"] if prev else None
        rows = prev["rows"] if prev else 0
        self._upsert(store, key, "failed", rows, start, end, error[:500])

    # ---- datasets ----
    def get_mode(self, store: str) -> str | None:
        row = self.conn.execute("SELECT resolved_mode FROM datasets WHERE store=?", (store,)).fetchone()
        return row[0] if row else None

    def set_mode(self, store: str, mode: str) -> None:
        self.conn.execute(
            """INSERT INTO datasets (store, resolved_mode, updated_utc) VALUES (?, ?, ?)
               ON CONFLICT(store) DO UPDATE SET resolved_mode=excluded.resolved_mode,
               updated_utc=excluded.updated_utc""", (store, mode, _utc_now()))
        self.conn.commit()

    def disable(self, store: str, reason: str) -> None:
        self.conn.execute(
            """INSERT INTO datasets (store, disabled_reason, updated_utc) VALUES (?, ?, ?)
               ON CONFLICT(store) DO UPDATE SET disabled_reason=excluded.disabled_reason,
               updated_utc=excluded.updated_utc""", (store, reason[:500], _utc_now()))
        self.conn.commit()

    def enable(self, store: str) -> None:
        self.conn.execute("UPDATE datasets SET disabled_reason=NULL WHERE store=?", (store,))
        self.conn.commit()

    def disabled_reason(self, store: str) -> str | None:
        row = self.conn.execute("SELECT disabled_reason FROM datasets WHERE store=?", (store,)).fetchone()
        return row[0] if row else None

    # ---- reports ----
    def summary(self) -> pd.DataFrame:
        df = pd.read_sql_query(
            "SELECT store, status, COUNT(*) AS n, SUM(rows) AS rows FROM tasks GROUP BY store, status",
            self.conn)
        if df.empty:
            return df
        return df.pivot_table(index="store", columns="status", values="n", fill_value=0,
                              aggfunc="sum").reset_index()

    def failures(self, limit: int = 50) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT store, key, error, attempts, updated_utc FROM tasks WHERE status='failed' "
            "ORDER BY updated_utc DESC LIMIT ?", self.conn, params=(limit,))

    def datasets_table(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM datasets ORDER BY store", self.conn)
