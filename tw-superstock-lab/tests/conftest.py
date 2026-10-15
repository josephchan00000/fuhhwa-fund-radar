from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from superstock.config import Config  # noqa: E402
from superstock.finmind_client import FinMindError  # noqa: E402


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    c = Config()
    c.start_date = "2014-01-01"
    c.data_dir = tmp_path / "data"
    c.reports_dir = tmp_path / "reports"
    return c


class FakeLimiter:
    per_hour = 552


class FakeClient:
    """模擬 FinMindClient.get：handlers[dataset](data_id, start, end) → DataFrame 或丟例外。"""

    def __init__(self, handlers: dict):
        self.handlers = handlers
        self.calls = 0
        self.requests: list[tuple] = []
        self.limiter = FakeLimiter()
        self.has_token = True

    def get(self, dataset, data_id="", start_date=None, end_date=None):
        self.calls += 1
        self.requests.append((dataset, data_id, start_date, end_date))
        handler = self.handlers.get(dataset)
        if handler is None:
            return pd.DataFrame()
        return handler(data_id, start_date, end_date)


def daily_prices(stock_id: str, start: str, end: str, base: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    n = len(dates)
    close = [base + (i % 5) * 0.5 for i in range(n)]
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"), "stock_id": stock_id,
        "Trading_Volume": [1_000_000] * n, "Trading_money": [100_000_000] * n,
        "open": close, "max": [c + 1 for c in close], "min": [c - 1 for c in close],
        "close": close, "spread": [0.0] * n, "Trading_turnover": [500] * n,
    })


def raise_error(msg: str = "Your level is register, please update"):
    def handler(*_):
        raise FinMindError(msg, 400)
    return handler
