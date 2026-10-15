"""FinMind API 用戶端：限流、重試、額度用完自動等待。

API 介面依 FinMind 2.0.11 套件原始碼：
  GET {api_url}?dataset=...&data_id=...&start_date=...&end_date=...
  Header: Authorization: Bearer <token>
  回應：{"msg": ..., "status": 200, "data": [...]}
  額度查詢：GET {user_info_url} → {"user_count": 已用次數, "api_request_limit": 上限}

待本機首次執行時確認（程式已做寬鬆判斷）：
  - 額度用完時的回應格式。預期 HTTP 402 且 msg 含 "upper limit"；429 也一併當成額度用完。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Callable

import pandas as pd
import requests

from .config import FinMindConfig

log = logging.getLogger(__name__)


class FinMindError(Exception):
    """非暫時性錯誤（例如資料集需付費、參數錯誤、token 無效）。"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class TransientError(FinMindError):
    """重試多次仍失敗的暫時性錯誤（網路、5xx）。下次執行會再試。"""


class QuotaExhausted(FinMindError):
    """額度用完且等待超過上限。"""


class RateLimiter:
    """滑動視窗限流：任一小時內最多 capacity 次，且兩次請求至少間隔 min_interval 秒。"""

    def __init__(
        self,
        max_per_hour: int,
        safety_margin: float = 0.92,
        min_interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        window: float = 3600.0,
    ):
        self.window = window
        self.min_interval = min_interval
        self.safety_margin = safety_margin
        self._clock = clock
        self._sleep = sleep
        self._stamps: deque[float] = deque()
        self._last: float | None = None
        self.capacity = 1
        self.set_limit(max_per_hour)

    def set_limit(self, max_per_hour: int) -> None:
        self.capacity = max(1, int(max_per_hour * self.safety_margin))

    @property
    def per_hour(self) -> int:
        return self.capacity

    def _evict(self, now: float) -> None:
        while self._stamps and now - self._stamps[0] >= self.window:
            self._stamps.popleft()

    def acquire(self) -> float:
        """取得一次請求的配額；回傳實際等待秒數。"""
        waited = 0.0
        while True:
            now = self._clock()
            self._evict(now)
            wait = 0.0
            if len(self._stamps) >= self.capacity:
                wait = self.window - (now - self._stamps[0])
            if self._last is not None and now - self._last < self.min_interval:
                wait = max(wait, self.min_interval - (now - self._last))
            if wait <= 0:
                self._stamps.append(now)
                self._last = now
                return waited
            self._sleep(wait)
            waited += wait


def _is_quota_message(msg: Any) -> bool:
    text = str(msg).lower()
    return "upper limit" in text or "上限" in text


class FinMindClient:
    def __init__(
        self,
        token: str,
        cfg: FinMindConfig,
        session: requests.Session | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_quota_waits: int = 12,
    ):
        self.cfg = cfg
        self.session = session or requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.has_token = bool(token)
        self.limiter = limiter or RateLimiter(
            cfg.requests_per_hour, cfg.safety_margin, cfg.min_interval_sec
        )
        self._sleep = sleep
        self.max_quota_waits = max_quota_waits
        self.calls = 0  # 實際送出的資料請求次數（含失敗）

    # ---------- 額度 ----------
    def user_info(self) -> dict[str, Any]:
        resp = self.session.get(self.cfg.user_info_url, timeout=self.cfg.timeout_sec)
        if resp.status_code != 200:
            raise FinMindError(f"user_info 失敗：HTTP {resp.status_code} {resp.text[:200]}",
                               resp.status_code)
        return resp.json()

    def sync_limit(self) -> dict[str, Any] | None:
        """依帳號實際上限調整限流器；失敗時沿用設定檔數值。"""
        try:
            info = self.user_info()
        except Exception as exc:  # noqa: BLE001 — 查不到額度不影響下載
            log.warning("查詢 FinMind 額度失敗，沿用設定值 %s/小時：%s",
                        self.cfg.requests_per_hour, exc)
            return None
        limit = int(info.get("api_request_limit") or 0)
        if limit > 0:
            self.limiter.set_limit(limit)
        return info

    def _wait_for_quota(self) -> None:
        for attempt in range(1, self.max_quota_waits + 1):
            log.warning("FinMind 額度已用完，等待 %s 秒後再試（第 %s/%s 次）",
                        self.cfg.rate_limit_wait_sec, attempt, self.max_quota_waits)
            self._sleep(self.cfg.rate_limit_wait_sec)
            try:
                info = self.user_info()
                used = int(info.get("user_count") or 0)
                limit = int(info.get("api_request_limit") or 0)
                if limit and used < limit * 0.9:
                    log.info("額度恢復：已用 %s / 上限 %s", used, limit)
                    return
            except Exception as exc:  # noqa: BLE001
                log.warning("查詢額度失敗：%s", exc)
        raise QuotaExhausted("等待額度恢復超過上限，請稍後重新執行（進度已保存）")

    # ---------- 資料 ----------
    def get(
        self,
        dataset: str,
        data_id: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        params: dict[str, str] = {"dataset": dataset}
        if data_id:
            params["data_id"] = data_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        attempt = 0
        quota_waits = 0
        while True:
            attempt += 1
            self.limiter.acquire()
            try:
                resp = self.session.get(self.cfg.api_url, params=params,
                                        timeout=self.cfg.timeout_sec)
            except (requests.ConnectionError, requests.Timeout,
                    requests.exceptions.ChunkedEncodingError) as exc:
                self.calls += 1
                if attempt >= self.cfg.max_retries:
                    raise TransientError(f"{dataset} {data_id}: 網路錯誤 {exc}") from exc
                self._sleep(min(60.0, 2.0 ** attempt))
                continue

            self.calls += 1
            status = resp.status_code
            try:
                payload = resp.json()
            except ValueError:
                payload = {}
            msg = payload.get("msg") or payload.get("detail") or resp.text[:200]
            body_status = payload.get("status")

            quota_hit = (
                status in (402, 429)
                or body_status in (402, 429)
                or (status != 200 and _is_quota_message(msg))
            )
            if quota_hit:
                quota_waits += 1
                if quota_waits > self.max_quota_waits:
                    raise QuotaExhausted(f"{dataset} {data_id}: 額度持續不足")
                self._wait_for_quota()
                attempt -= 1  # 額度等待不算重試次數
                continue

            if status >= 500:
                if attempt >= self.cfg.max_retries:
                    raise TransientError(f"{dataset} {data_id}: HTTP {status} {msg}", status)
                self._sleep(min(60.0, 2.0 ** attempt))
                continue

            if status != 200 or (body_status not in (None, 200)):
                raise FinMindError(f"{dataset} {data_id}: HTTP {status} {msg}", status)

            data = payload.get("data")
            if data is None:
                raise FinMindError(f"{dataset} {data_id}: 回應沒有 data 欄位：{msg}", status)
            return pd.DataFrame(data)
