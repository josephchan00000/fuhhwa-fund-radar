"""持股介紹（復華基金追蹤版本核心）—— 把 data/funds/{id}.json ＋ config/holding_profiles.json
合成一份『可讀的持股介紹』給 dashboard／報告使用。純讀取、可單測，缺檔即回空、不崩。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

ROOT = Path(__file__).resolve().parent.parent
FUNDS_DIR = ROOT / "data" / "funds"
PROFILES = ROOT / "config" / "holding_profiles.json"

GROUP_LABEL = {"global_equity": "全球股票型", "global_balanced": "全球平衡型"}


def _profiles() -> dict:
    if not PROFILES.exists():
        return {}
    try:
        return json.loads(PROFILES.read_text(encoding="utf-8")).get("profiles", {})
    except Exception:
        return {}


def load(fund_id: str) -> dict | None:
    """讀一檔基金快照，並把每檔持股的『重點標的簡介』掛上去（依原字串精確對應）。"""
    fp = FUNDS_DIR / f"{fund_id}.json"
    if not fp.exists():
        return None
    doc = json.loads(fp.read_text(encoding="utf-8"))
    profs = _profiles()
    for h in doc.get("top_holdings", []):
        p = profs.get(h.get("name")) or {}
        h["intro"] = p.get("intro")
        h["ticker"] = p.get("ticker")
        h["country"] = p.get("country")
    doc["group_label"] = GROUP_LABEL.get(doc.get("group"), doc.get("category") or "")
    return doc


def all_funds() -> list[dict]:
    """依 config/funds.json 的順序回傳所有已抓到的基金持股介紹。"""
    out = []
    for f in config.funds():
        doc = load(str(f["id"]))
        if doc:
            out.append(doc)
    return out


def summary_line(doc: dict) -> str:
    """一句話摘要：主要區域／首要產業／NAV。"""
    parts = []
    ca = doc.get("country_alloc") or []
    if ca:
        parts.append(f"{ca[0]['name']} {ca[0]['weight']:.1f}%")
    sa = doc.get("sector_alloc") or []
    if sa:
        parts.append(f"{sa[0]['name']} {sa[0]['weight']:.1f}%")
    if doc.get("nav") is not None:
        parts.append(f"NAV {doc['nav']}（{doc.get('nav_date') or '—'}）")
    return "｜".join(parts)


def top_concentration(doc: dict, n: int = 10) -> float | None:
    """前 n 大持股權重合計（%）。"""
    hs = doc.get("top_holdings") or []
    if not hs:
        return None
    return round(sum(h.get("weight") or 0 for h in hs[:n]), 1)
