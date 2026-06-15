"""FinMind 券商分點 adapter（M3 外接・最完整源）—— 全分點 + 多日歷史 + 成交量。

FinMind `TaiwanStockTradingDailyReport`（券商分點進出）為 **API + 完整資料**：每檔每日**所有**
分點的買/賣（非 Histock 只有前 N 大）、可一次取**日期區間**（多日歷史→連續買超即時真實）、
含量（買超佔成交比可算）。屬 **付費 sponsor 級**資料：需 `FINMIND_TOKEN` 環境變數
（在 finmindtrade.com 註冊→贊助取得 token）。未設 token 時本 adapter 靜默停用，回退 Histock。

Tier B：身份仍經 broker_map 推估、標『推估・非確認』；數字以證交所為準待核對。
單位：dataset buy/sell 為「股」，本檔換算成「張」(÷1000) 與 Histock 一致。
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from ...http import get_json
from .base import BrokerFlow, NoData, TargetFlows

API = "https://api.finmindtrade.com/api/v4/data"
DATASET = "TaiwanStockTradingDailyReport"


def available() -> bool:
    return bool(os.environ.get("FINMIND_TOKEN"))


def _rows(code: str, start: str, end: str) -> list[dict]:
    token = os.environ.get("FINMIND_TOKEN", "")
    url = (f"{API}?dataset={DATASET}&data_id={code}"
           f"&start_date={start}&end_date={end}&token={token}")
    try:
        resp = get_json(url, cache_ttl=3 * 3600)
    except Exception as e:
        raise NoData(f"FinMind 取得失敗 {code}：{e}") from e
    if not isinstance(resp, dict) or resp.get("status") != 200:
        raise NoData(f"FinMind 回應非 200（{code}）：{(resp or {}).get('msg') if isinstance(resp, dict) else resp}")
    return resp.get("data") or []


def fetch(code: str, *, window_days: int = 6) -> TargetFlows:
    """取最近 window_days 個交易日的全分點進出 → 多日 TargetFlows（含 day_volume）。"""
    if not available():
        raise NoData("FINMIND_TOKEN 未設定")
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=window_days * 3 + 7)).isoformat()  # 寬抓再裁
    rows = _rows(code, start, end)
    if not rows:
        raise NoData(f"FinMind 無 {code} 分點資料")

    flows: list[BrokerFlow] = []
    day_buy_shares: dict[str, int] = {}
    for r in rows:
        d = r.get("date") or ""
        bid = str(r.get("securities_trader_id") or r.get("securities_trader") or "")
        name = r.get("securities_trader") or bid
        buy = int(r.get("buy") or 0)
        sell = int(r.get("sell") or 0)
        net_lots = round((buy - sell) / 1000)
        if d and bid:
            flows.append(BrokerFlow(code, d, bid, name, net_lots))
            day_buy_shares[d] = day_buy_shares.get(d, 0) + buy

    dates = sorted({f.date for f in flows})[-window_days:]
    flows = [f for f in flows if f.date in dates]
    day_volume = {d: round(day_buy_shares.get(d, 0) / 1000) for d in dates}   # 張（總買量≈當日成交）
    if not flows:
        raise NoData(f"FinMind {code} 視窗內無資料")
    return TargetFlows(code, code, flows, day_volume, as_of=dates[-1], tier="B")
