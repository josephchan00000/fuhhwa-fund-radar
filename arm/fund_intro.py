"""持股介紹（復華基金追蹤版本核心）—— 把 data/funds/{id}.json ＋ config/holding_profiles.json
合成一份『可讀的持股介紹』給 dashboard／報告使用。純讀取、可單測，缺檔即回空、不崩。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config, markets

ROOT = Path(__file__).resolve().parent.parent
FUNDS_DIR = ROOT / "data" / "funds"          # 海外版預設資料夾（向後相容）
PROFILES = ROOT / "config" / "holding_profiles.json"

GROUP_LABEL = {
    "global_equity": "全球股票型", "global_balanced": "全球平衡型",
    "domestic_equity": "國內股票型", "domestic_balanced": "國內平衡型",
    "fof": "組合型",
}


def funds_dir(market: str = "global") -> Path:
    """某市場的持股快照資料夾（data/{market.data}）。"""
    return ROOT / "data" / markets.get(market)["data"]


def _profiles() -> dict:
    if not PROFILES.exists():
        return {}
    try:
        return json.loads(PROFILES.read_text(encoding="utf-8")).get("profiles", {})
    except Exception:
        return {}


def load(fund_id: str, market: str = "global") -> dict | None:
    """讀一檔基金快照，並把每檔持股的『重點標的簡介』掛上去（依原字串精確對應）。"""
    fp = funds_dir(market) / f"{fund_id}.json"
    if not fp.exists():
        return None
    try:                                    # 空檔/半寫入的壞 JSON 視同缺檔，跳過該檔、不讓整份儀表板崩
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None
    profs = _profiles()
    for h in doc.get("top_holdings", []):
        p = profs.get(h.get("name")) or {}
        h["intro"] = p.get("intro")
        h["detail"] = p.get("detail")        # 選配：2–3 句深入介紹（業務結構/客戶/供應鏈地位）
        h["ticker"] = p.get("ticker")
        h["country"] = p.get("country")
    doc["group_label"] = GROUP_LABEL.get(doc.get("group"), doc.get("category") or "")
    return doc


def all_funds(market: str = "global") -> list[dict]:
    """依該市場追蹤清單的順序回傳所有已抓到的基金持股介紹。"""
    out = []
    for f in config.funds(market):
        doc = load(str(f["id"]), market)
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
