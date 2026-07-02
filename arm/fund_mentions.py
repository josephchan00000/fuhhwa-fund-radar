"""基金動態雷達 —— 每日抓「復華各追蹤基金」的相關新聞／廣告／社群提及。

兩條資料來源合併呈現，每筆皆附發文時間與來源（可追溯）：
  1. 自動新聞：scripts/fetch_mentions.py 用 Google News RSS（arm/connectors/gnews，
     免金鑰、附 pubDate）逐檔基金＋公司層（復華投信）搜尋 → data/mentions/{market}.json。
  2. 社群／廣告：公開平台（PTT/Dcard/Mobile01/FB 粉專…）無免費 API，
     沿用 prompt-pack 哲學：scripts/gen_mentions.py 產提示包 → LLM 查證回填
     reports/mentions/{date}.json（kind ∈ social|ad|news，查不到就留空、不杜撰）。

本檔只放讀取器與合併邏輯（純函式、可單測，缺檔回空、不崩）。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTO_DIR = ROOT / "data" / "mentions"          # 自動新聞（fetch_mentions.py 產出）
SOCIAL_DIR = ROOT / "reports" / "mentions"     # 社群/廣告（LLM 查證回填）

KIND_LABEL = {"news": "新聞", "social": "社群", "ad": "廣告"}


def _read_json(fp: Path) -> dict | None:
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_auto(market: str) -> dict | None:
    """自動新聞：data/mentions/{market}.json
    → {fetched_at, market, company: [item…], funds: [{id, name, items: [item…]}]}"""
    return _read_json(AUTO_DIR / f"{market}.json")


def load_social() -> dict | None:
    """最新一份社群/廣告提及：reports/mentions/{date}.json
    → {date, items: [{fund_id?, fund?, kind, title, source, url?, date}]}"""
    if not SOCIAL_DIR.exists():
        return None
    for fp in sorted(SOCIAL_DIR.glob("????-??-??.json"), reverse=True):
        doc = _read_json(fp)
        if doc and isinstance(doc.get("items"), list):
            return doc
    return None


def merged(market: str, funds_cfg: list[dict]) -> dict:
    """依市場追蹤清單合併兩來源 → {as_of, company: [...], funds: [{id, name, items}]}。

    每筆 item 統一為 {kind, title, source, url?, date}；社群/廣告依 fund_id 對應到基金，
    對不到（或 fund_id 空）者归入 company 層。無任何資料時 company/funds 皆空。"""
    auto = load_auto(market)
    social = load_social()
    by_id: dict[str, list] = {str(f["id"]): [] for f in funds_cfg}
    company: list[dict] = []

    if auto:
        for it in auto.get("company") or []:
            company.append({**it, "kind": it.get("kind") or "news"})
        for f in auto.get("funds") or []:
            fid = str(f.get("id"))
            if fid in by_id:
                by_id[fid].extend({**it, "kind": it.get("kind") or "news"}
                                  for it in f.get("items") or [])
    if social:
        for it in social.get("items") or []:
            row = {"kind": it.get("kind") or "social", "title": it.get("title"),
                   "source": it.get("source"), "url": it.get("url"),
                   "date": it.get("date")}
            fid = str(it.get("fund_id") or "")
            if fid in by_id:
                by_id[fid].append(row)
            else:
                company.append(row)

    for items in by_id.values():
        items.sort(key=lambda x: x.get("date") or "", reverse=True)
    company.sort(key=lambda x: x.get("date") or "", reverse=True)
    as_of = (auto or {}).get("fetched_at") or (social or {}).get("date")
    return {"as_of": as_of,
            "company": company,
            "funds": [{"id": str(f["id"]), "name": f.get("name"),
                       "items": by_id[str(f["id"])]} for f in funds_cfg]}


def query_terms(fund_name: str) -> list[str]:
    """由基金全名產生搜尋關鍵字（去掉『基金/類別』尾綴，加引號精確比對）。"""
    short = (fund_name or "")
    for suf in ("A類型", "B類型", "TISA類型", "-新臺幣", "基金"):
        short = short.replace(suf, "")
    short = short.strip()
    out = []
    if short:
        out.append(f'"{short}"')
        if not short.startswith("復華"):
            out.append(f'"復華{short}"')
    if fund_name and fund_name != short:
        out.append(f'"{fund_name}"')
    return out
