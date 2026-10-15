from __future__ import annotations

import pytest
import requests

from superstock.config import FinMindConfig
from superstock.finmind_client import (FinMindClient, FinMindError, QuotaExhausted, RateLimiter,
                                       TransientError)


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


class FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, text: str = ""):
        self.status_code = status
        self._payload = payload
        self.text = text or str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, data_responses: list, user_info: list | None = None):
        self.data_responses = list(data_responses)
        self.user_info = list(user_info or [])
        self.headers: dict = {}
        self.data_calls = 0

    def get(self, url, params=None, timeout=None):
        if "user_info" in url:
            return self.user_info.pop(0)
        self.data_calls += 1
        item = self.data_responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(session, clock=None, **cfg_kwargs) -> FinMindClient:
    clock = clock or FakeClock()
    cfg = FinMindConfig(**{"rate_limit_wait_sec": 600, "max_retries": 3, **cfg_kwargs})
    limiter = RateLimiter(600, 0.92, 0.0, clock=clock.now, sleep=clock.sleep)
    return FinMindClient("tok", cfg, session=session, limiter=limiter, sleep=clock.sleep)


def test_rate_limiter_caps_requests_per_window():
    clock = FakeClock()
    lim = RateLimiter(3, safety_margin=1.0, min_interval=0.0, clock=clock.now, sleep=clock.sleep,
                      window=100.0)
    for _ in range(3):
        assert lim.acquire() == 0.0
    waited = lim.acquire()  # 第 4 次必須等到第 1 次滑出視窗
    assert waited == pytest.approx(100.0)
    assert clock.t == pytest.approx(100.0)


def test_rate_limiter_min_interval():
    clock = FakeClock()
    lim = RateLimiter(1000, safety_margin=1.0, min_interval=2.0, clock=clock.now, sleep=clock.sleep)
    lim.acquire()
    assert lim.acquire() == pytest.approx(2.0)


def test_success_returns_dataframe_and_sets_token_header():
    session = FakeSession([FakeResponse(200, {"status": 200, "msg": "success",
                                              "data": [{"date": "2024-01-02", "stock_id": "2330"}]})])
    client = make_client(session)
    df = client.get("TaiwanStockPrice", "2330", "2024-01-01", "2024-01-31")
    assert list(df["stock_id"]) == ["2330"]
    assert session.headers["Authorization"] == "Bearer tok"
    assert client.calls == 1


def test_quota_exhausted_waits_then_resumes():
    clock = FakeClock()
    session = FakeSession(
        [FakeResponse(402, {"status": 402, "msg": "Requests reach the upper limit."}),
         FakeResponse(200, {"status": 200, "data": [{"x": 1}]})],
        user_info=[FakeResponse(200, {"user_count": 10, "api_request_limit": 600})],
    )
    client = make_client(session, clock)
    df = client.get("TaiwanStockPrice", "2330")
    assert len(df) == 1
    assert 600 in clock.slept  # 等了一輪額度


def test_quota_never_recovers_raises():
    clock = FakeClock()
    responses = [FakeResponse(402, {"status": 402, "msg": "upper limit"})]
    session = FakeSession(responses, user_info=[FakeResponse(200, {"user_count": 600, "api_request_limit": 600})] * 3)
    client = make_client(session, clock)
    client.max_quota_waits = 3
    with pytest.raises(QuotaExhausted):
        client.get("TaiwanStockPrice", "2330")


def test_server_error_retries_then_succeeds():
    session = FakeSession([FakeResponse(500, {"msg": "oops"}),
                           FakeResponse(200, {"status": 200, "data": []})])
    client = make_client(session)
    df = client.get("TaiwanStockPrice", "2330")
    assert df.empty and session.data_calls == 2


def test_network_error_exhausts_retries():
    session = FakeSession([requests.ConnectionError("down")] * 3)
    client = make_client(session)
    with pytest.raises(TransientError):
        client.get("TaiwanStockPrice", "2330")


def test_client_error_is_not_retried():
    session = FakeSession([FakeResponse(400, {"status": 400, "msg": "Your level is register"})])
    client = make_client(session)
    with pytest.raises(FinMindError) as exc:
        client.get("TaiwanStockPriceAdj", "2330")
    assert not isinstance(exc.value, TransientError)
    assert session.data_calls == 1
