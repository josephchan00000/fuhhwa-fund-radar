"""統一持股介面（M2-2）—— 跨家差異化引擎與資料源解耦的接縫。

不論復華自家(live assetsExcel)、0050 基準(快照)、競品(drop-in/未來 adapter)，
全部歸一成 `Holding(fund_id, date, stock_id, weight, shares)`，差異化引擎只吃這個。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CFG = Path(__file__).resolve().parents[3] / "config"
DROP_DIR = CFG / "competitor_holdings"
BENCH_FILE = CFG / "benchmark_0050.json"


class NoData(Exception):
    """該基金當前無可用持股來源（競品 live 為 SPA，待 adapter 或 drop-in）。"""


@dataclass(frozen=True)
class Holding:
    fund_id: str
    date: str
    stock_id: str
    stock_name: str
    weight: float          # 權重 %（與 holdings_daily 一致，0–100）
    shares: int = 0
    kind: str = "equity"   # equity / future / bond


def from_fhtrust_dict(fund_code: str, iso_date: str, raw_holdings: list[dict]) -> list[Holding]:
    """把復華 assetsExcel 解析出的 holdings dict 轉成統一 Holding（只取 equity）。"""
    out: list[Holding] = []
    for h in raw_holdings:
        if h.get("kind", "equity") != "equity":
            continue
        out.append(Holding(
            fund_code, iso_date, h["stock_id"], h.get("stock_name", ""),
            float(h.get("weight") or 0.0), int(h.get("shares") or 0)))
    return out


def _load_json_holdings(path: Path) -> tuple[list[Holding], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    fund_id = data.get("fund_id", path.stem)
    asof = data.get("as_of", "")
    hs = [Holding(fund_id, asof, r["stock_id"], r.get("stock_name", ""),
                  float(r.get("weight") or 0.0), int(r.get("shares") or 0),
                  r.get("kind", "equity"))
          for r in data.get("holdings", [])]
    return hs, data


def benchmark_holdings() -> tuple[list[Holding], str | None]:
    """0050 成分快照（M2-5）。回傳 (holdings, as_of)；無檔案回 ([], None)。"""
    if not BENCH_FILE.exists():
        return [], None
    hs, data = _load_json_holdings(BENCH_FILE)
    return hs, data.get("as_of")


def curated_holdings(fund_id: str) -> list[Holding] | None:
    """競品 drop-in 持股（config/competitor_holdings/{fund_id}.json）；無則 None。"""
    path = DROP_DIR / f"{fund_id}.json"
    if not path.exists():
        return None
    hs, _ = _load_json_holdings(path)
    return hs
