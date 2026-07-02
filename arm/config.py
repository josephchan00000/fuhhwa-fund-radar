"""設定載入（Phase 0 用 JSON，避免 PyYAML 依賴；config/products.yaml 為人類可讀版）。"""
from __future__ import annotations

import json
from pathlib import Path

CFG_DIR = Path(__file__).resolve().parent.parent / "config"
CFG = CFG_DIR / "products.json"
DIST = CFG_DIR / "distributions.json"
FUNDS = CFG_DIR / "funds.json"


def load() -> dict:
    return json.loads(CFG.read_text(encoding="utf-8"))


def funds() -> list[dict]:
    """復華基金追蹤版本的追蹤清單（config/funds.json:funds）；每筆含 id/name/group。"""
    if not FUNDS.exists():
        return []
    return json.loads(FUNDS.read_text(encoding="utf-8")).get("funds", [])


def fund(fund_id: str) -> dict:
    for f in funds():
        if str(f.get("id")) == str(fund_id):
            return f
    raise KeyError(f"funds.json 找不到 {fund_id}")


def product(etf_id: str) -> dict:
    for p in load()["fh_products"]:
        if p["id"] == etf_id:
            return p
    raise KeyError(f"products.json 找不到 {etf_id}")


def distributions(etf_id: str) -> dict[str, float]:
    """官方配息紀錄 {除息日: 每單位金額}；無資料回 {}（不臆測，純 NAV 報酬）。"""
    if not DIST.exists():
        return {}
    data = json.loads(DIST.read_text(encoding="utf-8"))
    return {k: float(v) for k, v in (data.get(etf_id) or {}).items()
            if not k.startswith("_")}
