"""下載排程：可中斷續傳、每日增量更新、資料集權限自動偵測。

執行順序：
  1. meta：股票清單、下市清單、交易日、指數 → 決定股票池
  2. 其他群組：以「股票」為外層迴圈，每檔把該群組的資料集抓齊再換下一檔，
     這樣下載到一半時，已完成的股票資料是完整的，可以先拿來做研究。
  3. 事件類資料集先試整批下載（按年份），免費帳號不允許就改回逐檔。

防呆：
  - 每次請求完成就寫入進度（SQLite），Ctrl-C 或斷線後重跑會從中斷處繼續。
  - 同一資料集連續 3 檔回應錯誤（多半是需付費）→ 本次停用該資料集，不浪費額度。
"""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from .config import Config
from .datasets import DatasetSpec, specs_for_groups
from .finmind_client import FinMindClient, FinMindError, QuotaExhausted, TransientError
from .storage import GLOBAL_KEY, Manifest, Store
from .universe import build_universe

log = logging.getLogger(__name__)

BREAKER_THRESHOLD = 3


class BudgetExhausted(Exception):
    pass


@dataclass
class Task:
    spec: DatasetSpec
    key: str
    data_id: str
    delist_date: pd.Timestamp | None = None


class Downloader:
    def __init__(self, cfg: Config, client: FinMindClient, store: Store, manifest: Manifest,
                 today: date | None = None):
        self.cfg = cfg
        self.client = client
        self.store = store
        self.manifest = manifest
        self.today = (today or date.today()).isoformat()
        self.stats: Counter = Counter()
        self._consecutive_fail: dict[str, int] = defaultdict(int)
        self._budget: int | None = None
        self._calls_at_start = 0
        self._started = time.monotonic()

    # ------------------------------------------------------------------ 公開介面
    def run(self, groups: list[str], mode: str = "initial", stocks: list[str] | None = None,
            max_calls: int | None = None) -> dict:
        if mode not in ("initial", "update"):
            raise ValueError("mode 必須是 initial 或 update")
        self._budget = max_calls
        self._calls_at_start = self.client.calls
        self._started = time.monotonic()
        specs = specs_for_groups(groups)
        stopped_reason = None
        try:
            for spec in [s for s in specs if s.group == "meta"]:
                self._run_meta(spec, mode)
            universe = self.universe(stocks)
            log.info("股票池：%s 檔（含下市 %s 檔）", len(universe), int(universe["is_delisted"].sum())
                     if not universe.empty else 0)
            others = [s for s in specs if s.group != "meta"]
            per_stock_specs = []
            for spec in others:
                if self._disabled(spec):
                    continue
                if spec.try_global and self._resolve_mode(spec) == "global":
                    self._run_global_chunks(spec, mode)
                else:
                    per_stock_specs.append(spec)
            self._run_per_stock(per_stock_specs, universe, mode)
        except BudgetExhausted:
            stopped_reason = f"已達本次請求上限 {self._budget} 次"
            log.info(stopped_reason)
        except QuotaExhausted as exc:
            stopped_reason = str(exc)
            log.error(stopped_reason)
        return {"calls": self.client.calls - self._calls_at_start, "stats": dict(self.stats),
                "stopped_reason": stopped_reason}

    def universe(self, stocks: list[str] | None = None) -> pd.DataFrame:
        info = self._read_global("TaiwanStockInfo")
        delisting = self._read_global("TaiwanStockDelisting")
        uni = build_universe(info, delisting, self.cfg.universe, self.cfg.start_date)
        if stocks:
            wanted = {str(s) for s in stocks}
            uni = uni[uni["stock_id"].isin(wanted)]
            missing = wanted - set(uni["stock_id"])
            if missing:
                log.warning("這些代號不在股票池內，略過：%s", sorted(missing))
        # 現行掛牌的先抓，下市的後抓
        return uni.sort_values(["is_delisted", "stock_id"]).reset_index(drop=True)

    def plan(self, groups: list[str], universe: pd.DataFrame) -> pd.DataFrame:
        """估計還要多少次請求（initial 模式、尚未完成的部分）。"""
        rows = []
        n_years = date.today().year - pd.Timestamp(self.cfg.start_date).year + 1
        for spec in specs_for_groups(groups):
            store = spec.store_name
            if spec.mode == "global":
                pending = 0 if self._is_complete(store, GLOBAL_KEY) else 1
            elif spec.mode == "per_index":
                pending = sum(not self._is_complete(store, k) for k in spec.ids)
            elif spec.try_global and self.manifest.get_mode(store) == "global":
                pending = sum(not self._is_complete(store, f"{GLOBAL_KEY}_{y}")
                              for y in range(date.today().year - n_years + 1, date.today().year + 1))
            else:
                pending = sum(not self._is_complete(store, sid) for sid in universe["stock_id"])
                if spec.try_global and self.manifest.get_mode(store) is None:
                    pending = f"{n_years}（若可整批）或 {pending}"
            rows.append({"group": spec.group, "dataset": store, "note": spec.note,
                         "pending_calls": pending,
                         "disabled": self.manifest.disabled_reason(store) or ""})
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ meta
    def _run_meta(self, spec: DatasetSpec, mode: str) -> None:
        if spec.mode == "per_index":
            for idx in spec.ids:
                self._fetch(Task(spec, idx, idx), mode)
            return
        row = self.manifest.get(spec.store_name, GLOBAL_KEY)
        if mode == "initial" and row and row["status"] == "done":
            return
        if mode == "update" and row and row["status"] == "done" and row["last_end"] == self.today:
            return
        self._check_budget()
        start = self.cfg.start_date if spec.use_dates else None
        end = self.today if spec.use_dates else None
        try:
            df = self.client.get(spec.name, start_date=start, end_date=end)
        except (FinMindError, TransientError) as exc:
            if isinstance(exc, QuotaExhausted):
                raise
            self.manifest.mark_failed(spec.store_name, GLOBAL_KEY, str(exc))
            self.stats["failed"] += 1
            log.error("%s 下載失敗：%s", spec.store_name, exc)
            return
        rows = self.store.merge_write(spec, GLOBAL_KEY, df, replace=True)
        self.manifest.mark_done(spec.store_name, GLOBAL_KEY, rows, start, self.today)
        self.stats["done"] += 1
        log.info("%s：%s 列", spec.store_name, rows)

    def _read_global(self, name: str) -> pd.DataFrame:
        spec = next(s for s in specs_for_groups(["meta"]) if s.store_name == name)
        df = self.store.read(spec, GLOBAL_KEY)
        return df if df is not None else pd.DataFrame()

    # ------------------------------------------------------------------ events 整批
    def _resolve_mode(self, spec: DatasetSpec) -> str:
        store = spec.store_name
        resolved = self.manifest.get_mode(store)
        if resolved:
            return resolved
        self._check_budget()
        probe_start = (pd.Timestamp(self.today) - pd.Timedelta(days=3 * 365)).date().isoformat()
        try:
            df = self.client.get(spec.name, start_date=probe_start, end_date=self.today)
            # 全市場 3 年內減資、分割、面額變更、除權息、處置都一定有幾十到幾千件；
            # 整批試抓卻是空的（或只有一檔）＝免費帳號不給整批，改逐檔，免得整個資料集默默變空
            ok = not df.empty and "stock_id" in df.columns and df["stock_id"].nunique() > 1
        except QuotaExhausted:
            raise
        except (FinMindError, TransientError) as exc:
            log.info("%s 不支援整批下載（%s），改為逐檔", store, exc)
            df, ok = pd.DataFrame(), False
        mode = "global" if ok else "per_stock"
        self.manifest.set_mode(store, mode)
        if ok and not df.empty:
            self.store.merge_write(spec, GLOBAL_KEY, df)
        log.info("%s 下載方式：%s", store, "整批（按年）" if ok else "逐檔")
        return mode

    def _run_global_chunks(self, spec: DatasetSpec, mode: str) -> None:
        store = spec.store_name
        first_year = pd.Timestamp(self.cfg.start_date).year
        this_year = pd.Timestamp(self.today).year
        refresh_from = (pd.Timestamp(self.today) - pd.Timedelta(days=spec.overlap_days)).year
        for year in range(first_year, this_year + 1):
            key = f"{GLOBAL_KEY}_{year}"
            row = self.manifest.get(store, key)
            complete = row is not None and row["status"] in ("done", "empty")
            if complete and (mode == "initial" or year < refresh_from):
                continue
            if mode == "update" and complete and row["last_end"] == self.today:
                continue
            self._check_budget()
            start = max(self.cfg.start_date, f"{year}-01-01")
            end = min(self.today, f"{year}-12-31")
            try:
                df = self.client.get(spec.name, start_date=start, end_date=end)
            except QuotaExhausted:
                raise
            except (FinMindError, TransientError) as exc:
                self.manifest.mark_failed(store, key, str(exc))
                self.stats["failed"] += 1
                continue
            if df.empty:
                self.manifest.mark_empty(store, key, start, end)
                self.stats["empty"] += 1
                continue
            self.store.merge_write(spec, GLOBAL_KEY, df)
            self.manifest.mark_done(store, key, len(df), start, end)
            self.stats["done"] += 1

    # ------------------------------------------------------------------ 逐檔
    def _run_per_stock(self, specs: list[DatasetSpec], universe: pd.DataFrame, mode: str) -> None:
        if not specs or universe.empty:
            return
        total = len(universe)
        for i, row in enumerate(universe.itertuples(index=False), start=1):
            delist = row.delist_date if bool(row.is_delisted) else None
            for spec in specs:
                if self._disabled(spec):
                    continue
                self._fetch(Task(spec, row.stock_id, row.stock_id,
                                 pd.Timestamp(delist) if delist is not None else None), mode)
            if i % 25 == 0 or i == total:
                self._log_progress(i, total, specs)

    def _fetch(self, task: Task, mode: str) -> str:
        spec, store = task.spec, task.spec.store_name
        row = self.manifest.get(store, task.key)
        complete = row is not None and row["status"] in ("done", "empty")
        if complete and mode == "initial":
            return "skip"
        if complete and row["last_end"] == self.today:
            return "skip"
        if complete and task.delist_date is not None and row["last_end"] \
                and pd.Timestamp(row["last_end"]) >= task.delist_date:
            return "skip"  # 已下市且資料已涵蓋到下市日，不會再有新資料

        start = self.cfg.start_date
        if row and row["last_end"]:
            back = pd.Timestamp(row["last_end"]) - pd.Timedelta(days=spec.overlap_days)
            start = max(self.cfg.start_date, back.date().isoformat())
        self._check_budget()
        try:
            df = self.client.get(spec.name, data_id=task.data_id,
                                 start_date=start if spec.use_dates else None,
                                 end_date=self.today if spec.use_dates else None)
        except QuotaExhausted:
            raise
        except TransientError as exc:
            self.manifest.mark_failed(store, task.key, str(exc))
            self.stats["failed"] += 1
            log.warning("%s %s 暫時失敗（下次重跑會再試）：%s", store, task.key, exc)
            return "failed"
        except FinMindError as exc:
            self.manifest.mark_failed(store, task.key, str(exc))
            self.stats["failed"] += 1
            self._register_failure(spec, exc)
            return "failed"

        self._consecutive_fail[store] = 0
        first_start = row["last_start"] if row and row["last_start"] else start
        if df.empty:
            if row and row["status"] == "done":
                self.manifest.mark_done(store, task.key, row["rows"], first_start, self.today)
            else:
                self.manifest.mark_empty(store, task.key, first_start, self.today)
            self.stats["empty"] += 1
            return "empty"
        rows = self.store.merge_write(spec, task.key, df)
        self.manifest.mark_done(store, task.key, rows, first_start, self.today)
        self.stats["done"] += 1
        return "done"

    # ------------------------------------------------------------------ 工具
    def _register_failure(self, spec: DatasetSpec, exc: FinMindError) -> None:
        store = spec.store_name
        self._consecutive_fail[store] += 1
        log.warning("%s 失敗（連續 %s 次）：%s", store, self._consecutive_fail[store], exc)
        if self._consecutive_fail[store] >= BREAKER_THRESHOLD:
            reason = f"連續 {BREAKER_THRESHOLD} 檔失敗，可能需付費或參數不符：{exc}"
            self.manifest.disable(store, reason)
            log.error("停用資料集 %s：%s（確認後可用 download --enable %s 重新啟用）",
                      store, reason, store)

    def _disabled(self, spec: DatasetSpec) -> bool:
        return bool(self.manifest.disabled_reason(spec.store_name))

    def _is_complete(self, store: str, key: str) -> bool:
        row = self.manifest.get(store, key)
        return row is not None and row["status"] in ("done", "empty")

    def _check_budget(self) -> None:
        if self._budget is not None and self.client.calls - self._calls_at_start >= self._budget:
            raise BudgetExhausted()

    def _log_progress(self, i: int, total: int, specs: list[DatasetSpec]) -> None:
        used = self.client.calls - self._calls_at_start
        remaining_calls = (total - i) * len([s for s in specs if not self._disabled(s)])
        per_hour = max(1, self.client.limiter.per_hour)
        eta_h = remaining_calls / per_hour
        log.info("進度 %s/%s 檔｜本次已用 %s 次請求｜預估剩餘約 %.1f 小時", i, total, used, eta_h)


def default_today() -> date:
    """台灣收盤後資料約 15:00–21:30 陸續更新；凌晨執行時以前一天為準避免抓到不完整資料。"""
    now = pd.Timestamp.now(tz="Asia/Taipei")
    return (now - timedelta(hours=6)).date()
