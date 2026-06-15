"""券商分點多日歷史（M3 延伸）—— 把每日 Histock 單日快照累積成「連續買超」可算的窗。

Histock「分公司進出」頁只有**最新交易日**、無歷史/日期參數，故與受益人(holders_history)、
NAV(nav_history) 同策略：**每日落一份快照**，再讀回最近 N 個交易日合併成多日 `TargetFlows`，
讓 `chips.consecutive_buy_days` 算出真實「連續買超天數」（隨系統每日累積而成長）。

快照存 `data/broker_history/{code}/{YYYY-MM-DD}.json`，與 db.py / M4 互不相干。
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import BrokerFlow, TargetFlows

STORE = Path(__file__).resolve().parents[3] / "data" / "broker_history"


def _dir(code: str) -> Path:
    return STORE / code


def record(code: str, date: str, flows: list[BrokerFlow]) -> None:
    """落一份單日分點快照（同日重跑覆寫，冪等）。"""
    if not date or not flows:
        return
    d = _dir(code)
    d.mkdir(parents=True, exist_ok=True)
    rows = [{"broker_id": f.broker_id, "broker_name": f.broker_name, "net": f.net} for f in flows]
    (d / f"{date}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def stored_dates(code: str) -> list[str]:
    """已落檔的交易日（遞增）。"""
    d = _dir(code)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("[0-9]*.json"))


def prune(code: str, keep: int = 90) -> None:
    """只保留最近 keep 個交易日快照，避免無限長大。"""
    files = sorted(_dir(code).glob("[0-9]*.json"))
    for p in files[:-keep]:
        p.unlink(missing_ok=True)


def load_window(code: str, *, days: int = 6, target_name: str | None = None) -> TargetFlows | None:
    """讀最近 days 個交易日的快照，合併成多日 `TargetFlows`；無快照回 None。"""
    dates = stored_dates(code)[-days:]
    flows: list[BrokerFlow] = []
    for dt in dates:
        try:
            rows = json.loads((_dir(code) / f"{dt}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows:
            flows.append(BrokerFlow(code, dt, str(r.get("broker_id") or r.get("broker_name", "")),
                                    r.get("broker_name", ""), int(r.get("net") or 0)))
    if not flows:
        return None
    return TargetFlows(code, target_name or code, flows, {}, as_of=dates[-1], tier="B")
