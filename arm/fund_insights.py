"""跨基金洞察層（版面重新設計核心）—— 把 fund_intro 的逐檔資料合成「業務優先」視角：

  · overview_rows()：11 檔總覽表（報酬字串→數值，供排序與色階）。
  · movers()：今日 NAV 最強／最弱。
  · group_averages()：同組（全球股票型／全球平衡型）多期平均報酬。
  · news_fund_links()：昨夜新聞 × 持股 × 基金 三方連動（吃 config/holding_aliases.json）。
  · talk_script()：連動話術（中性事實模板＋禁用詞掃描）。
  · upcoming_distributions()：近期配息基準日提醒。

純函式、可單測；缺檔／缺欄位回空、不崩。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from . import fund_intro, usnews

ROOT = Path(__file__).resolve().parent.parent
ALIASES = ROOT / "config" / "holding_aliases.json"

RET_KEYS = [("ytd", "今年以來"), ("3m", "3月"), ("6m", "6月"),
            ("1y", "1年"), ("3y", "3年")]


def parse_pct(s) -> float | None:
    """'78.42%'／'-2.13%'／64.07 → float；'—'／None／解析不到 → None。"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", str(s))
    return float(m.group(1)) if m else None


def overview_rows(funds: list[dict]) -> list[dict]:
    """總覽表列資料：每檔基金一列，報酬／變動皆為數值（None＝缺）。"""
    rows = []
    for d in funds:
        ret = d.get("returns") or {}
        rows.append({
            "fund_id": str(d.get("fund_id")),
            "name": d.get("name") or "",
            "short_name": d.get("short_name") or d.get("name") or "",
            "group_label": d.get("group_label") or "",
            "nav": d.get("nav"),
            "nav_date": d.get("nav_date"),
            "chg": parse_pct(d.get("nav_change_pct")),
            "ytd": parse_pct(ret.get("ytd")),
            "y1": parse_pct(ret.get("1y")),
            "y3": parse_pct(ret.get("3y")),
            "size_e8": round(d["size_twd"] / 1e8, 1) if d.get("size_twd") else None,
            "conc": fund_intro.top_concentration(d),
            "risk": d.get("risk_level") or "—",
        })
    return rows


def movers(funds: list[dict]) -> tuple[dict | None, dict | None]:
    """(今日最強, 今日最弱)：依 NAV 日變動排序；同日缺數者剔除。至多一檔時最弱回 None。"""
    cands = [{"fund_id": str(d.get("fund_id")),
              "short_name": d.get("short_name") or d.get("name") or "",
              "chg": parse_pct(d.get("nav_change_pct"))}
             for d in funds]
    cands = [c for c in cands if c["chg"] is not None]
    if not cands:
        return None, None
    cands.sort(key=lambda c: c["chg"], reverse=True)
    best = cands[0]
    worst = cands[-1] if len(cands) > 1 else None
    return best, worst


def group_averages(funds: list[dict]) -> dict[str, dict[str, float]]:
    """{group_label: {期別key: 算術平均}}；某期任一檔缺值則以現有檔平均、全缺不出 key。"""
    acc: dict[str, dict[str, list[float]]] = {}
    for d in funds:
        g = d.get("group_label") or ""
        ret = d.get("returns") or {}
        for k, _ in RET_KEYS:
            v = parse_pct(ret.get(k))
            if v is not None:
                acc.setdefault(g, {}).setdefault(k, []).append(v)
    return {g: {k: round(sum(vs) / len(vs), 2) for k, vs in ks.items()}
            for g, ks in acc.items()}


def column_leaders(rows: list[dict], keys: tuple[str, ...] = ("chg", "ytd", "y1", "y3"),
                   top: int = 2) -> set[tuple[str, str]]:
    """總覽表色階：每組每欄取前 top 名（值須 >0 才算領先）。回 {(fund_id, key)}。"""
    out: set[tuple[str, str]] = set()
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group_label"], []).append(r)
    for rs in groups.values():
        for k in keys:
            ranked = sorted((r for r in rs if r.get(k) is not None and r[k] > 0),
                            key=lambda r: r[k], reverse=True)[:top]
            out.update((r["fund_id"], k) for r in ranked)
    return out


# ── 新聞 × 持股連動 ──────────────────────────────────────────

def _alias_map() -> dict:
    if not ALIASES.exists():
        return {}
    try:
        return json.loads(ALIASES.read_text(encoding="utf-8")).get("aliases", {})
    except Exception:
        return {}


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _patterns_for(name: str, ticker: str | None, alias_cfg: dict) -> list[str]:
    """一檔持股的比對樣式：別名 ＋（bare!=false 時）官方名 ＋ 長度≥4 的英文代號。"""
    cfg = alias_cfg.get(name) or {}
    pats = list(cfg.get("names") or [])
    if cfg.get("bare", True):
        pats.append(name)
    if ticker and _is_ascii(ticker) and len(ticker) >= 4 and not ticker.isdigit():
        pats.append(ticker)
    # 去重（保序）、去空
    seen: set[str] = set()
    return [p for p in pats if p and not (p.lower() in seen or seen.add(p.lower()))]


def _hit(text: str, text_lower: str, pat: str) -> bool:
    if _is_ascii(pat):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(pat.lower())}(?![A-Za-z0-9])",
                         text_lower) is not None
    return pat in text


def news_fund_links(funds: list[dict], news_md: str) -> list[dict]:
    """昨夜新聞卡 × 持股 × 基金 三方連動。

    回 [{title, oneline, matched: [{name, display, ticker,
        funds: [{fund_id, short_name, weight}]}]}]（含未命中的卡，matched=[]）。"""
    alias_cfg = _alias_map()
    # 持股 → 持有基金（權重高→低）；display 取別名首位（新聞用語較好讀）
    holders: dict[str, dict] = {}
    for d in funds:
        for h in d.get("top_holdings") or []:
            nm = h.get("name")
            if not nm:
                continue
            ent = holders.setdefault(nm, {"name": nm, "ticker": h.get("ticker"),
                                          "funds": []})
            ent["ticker"] = ent["ticker"] or h.get("ticker")
            ent["funds"].append({"fund_id": str(d.get("fund_id")),
                                 "short_name": d.get("short_name") or d.get("name") or "",
                                 "weight": h.get("weight") or 0})
    matchers = []
    for nm, ent in holders.items():
        pats = _patterns_for(nm, ent["ticker"], alias_cfg)
        if pats:
            cfg = alias_cfg.get(nm) or {}
            display = (cfg.get("names") or [nm])[0]
            matchers.append((nm, display, pats, ent))
    out = []
    for card in usnews.extract_cards(news_md or ""):
        text = card["title"] + "\n" + card["body"]
        tl = text.lower()
        matched = []
        for nm, display, pats, ent in matchers:
            if any(_hit(text, tl, p) for p in pats):
                matched.append({"name": nm, "display": display, "ticker": ent["ticker"],
                                "funds": sorted(ent["funds"],
                                                key=lambda f: f["weight"], reverse=True)})
        matched.sort(key=lambda m: m["funds"][0]["weight"], reverse=True)
        out.append({"title": card["title"], "oneline": card["oneline"], "matched": matched})
    return out


def talk_script(card: dict, as_of: str | None) -> tuple[str, list[str]]:
    """一張連動卡的可複製話術（中性事實模板）。回 (文字, 禁用詞命中)。命中≠可用。"""
    lead = card.get("oneline") or card.get("title") or ""
    parts = []
    for m in card.get("matched") or []:
        fs = "、".join(f"{f['short_name']} {f['weight']:.2f}%" for f in m["funds"])
        parts.append(f"{m['display']}：{fs}")
    body = "；".join(parts)
    text = (f"{lead}。本公司基金前十大持股含 {body}（持股基準 {as_of or '—'}，月度揭露）。"
            f"以上為公開資訊彙編，非投資建議；過去績效不代表未來表現。")
    return text, usnews.compliance_scan(text)


def fund_intro_copy(doc: dict) -> str:
    """單檔基金介紹的可複製純文字（貼 LINE／mail 用），文末附免責一行。"""
    ret = doc.get("returns") or {}
    rets = "／".join(f"{lab} {ret.get(k) or '—'}"
                     for k, lab in RET_KEYS + [("since", "成立以來")])
    top3 = "、".join(f"{h.get('name')} {h.get('weight') or 0:.2f}%"
                     for h in (doc.get("top_holdings") or [])[:3]) or "—"
    size = doc.get("size_twd")
    lines = [
        f"【{doc.get('name')}】{doc.get('category') or ''}",
        f"NAV {doc.get('nav') if doc.get('nav') is not None else '—'}"
        f"（{doc.get('nav_date') or '—'}，日變動 {doc.get('nav_change_pct') or '—'}）"
        f"｜規模 {f'{size / 1e8:.1f} 億元' if size else '—'}｜風險 {doc.get('risk_level') or '—'}",
        f"報酬：{rets}",
        f"前三大持股（基準 {doc.get('as_of') or '—'}）：{top3}",
    ]
    if doc.get("monthly_report"):
        lines.append(f"基金月報：{doc['monthly_report']}")
    lines.append("資料來源：復華投信官網。本內容為公開資訊彙編，非投資建議或招攬；"
                 "過去績效不代表未來表現，申購前應詳閱公開說明書／投資人須知。")
    return "\n".join(lines)


def upcoming_distributions(funds: list[dict], today: date | None = None,
                           days: int = 7) -> list[dict]:
    """dist_date 落在今日起 days 天內（含當日）的基金。回 [{short_name, dist_date}]。"""
    t = today or date.today()
    out = []
    for d in funds:
        ds = d.get("dist_date")
        if not ds:
            continue
        try:
            dd = datetime.strptime(str(ds), "%Y/%m/%d").date()
        except ValueError:
            continue
        if 0 <= (dd - t).days <= days:
            out.append({"short_name": d.get("short_name") or d.get("name") or "",
                        "dist_date": ds})
    return sorted(out, key=lambda x: x["dist_date"])
