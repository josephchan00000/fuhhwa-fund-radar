"""跨基金洞察層（版面重新設計核心）—— 把 fund_intro 的逐檔資料合成「業務優先」視角：

  · overview_rows()：11 檔總覽表（報酬字串→數值，供排序與色階）。
  · movers()：今日 NAV 最強／最弱。
  · group_averages()：同組（全球股票型／全球平衡型）多期平均報酬。
  · news_fund_links()：昨夜新聞 × 持股 × 基金 三方連動（吃 config/holding_aliases.json）。
  · upcoming_distributions()：近期配息基準日提醒。

純函式、可單測；缺檔／缺欄位回空、不崩。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from . import clock, fund_intro, fundnav, usnews

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


def parse_period_pct(s) -> float | None:
    """期間報酬（ytd/3m/…/3y/since）：官網對成立未滿之期間以「0.00%」佔位，
    一律視為缺值回 None，避免被誤讀成「報酬為零」（真實期間報酬恰為 0.00% 幾無可能）。"""
    v = parse_pct(s)
    return None if v == 0 else v


def _daily_ret(d: dict, key: str) -> float | None:
    """returns_daily（鉅亨、每日基準）取值；缺鍵回 None（勿用 get(default)——CLAUDE.md 坑）。"""
    v = (d.get("returns_daily") or {}).get(key)
    if v is None:
        return None
    return float(v) if isinstance(v, (int, float)) else parse_period_pct(str(v))


def inception_ret_pct(d: dict) -> float | None:
    """成立於今年、官網多期報酬尚未揭露的新基金：以發行價起算的成立以來報酬率
    （國內開放式基金每受益權單位發行面額一律 10 元）。當年度成立 → 此值語意上同時就是 YTD。
    官網已揭露 ytd 就不啟用（2026-07-22 使用者指示，首例：台灣菁英50指數基金）。"""
    nav, inc = d.get("nav"), str(d.get("inception") or "")
    if nav is None or len(inc) < 4:
        return None
    try:
        if int(inc[:4]) != clock.today_tw().year:
            return None
    except ValueError:
        return None
    if parse_period_pct((d.get("returns") or {}).get("ytd")) is not None:
        return None
    return round((nav / 10.0 - 1) * 100, 2)


def overview_rows(funds: list[dict]) -> list[dict]:
    """總覽表列資料：每檔基金一列，報酬／變動皆為數值（None＝缺）。
    多期報酬逐欄 fallback：鉅亨每日基準（returns_daily）→ 官網月底基準（returns）；
    1週/1月再多一層 → arm/fundnav 的 NAV 序列自算（史料不足回 None）；
    YTD 再多一層 → 今年新成立基金以發行價 10 元起算（inception_ret_pct，列標 ytd_est）。"""
    hist = fundnav.load()
    rows = []
    for d in funds:
        ret = d.get("returns") or {}
        ser = hist.get(str(d.get("fund_id"))) or {}

        def pick(daily_key: str, official_key: str | None = None,
                 self_calc: float | None = None) -> float | None:
            v = _daily_ret(d, daily_key)
            if v is None and official_key:
                v = parse_period_pct(ret.get(official_key))
            return v if v is not None else self_calc

        rows.append({
            "fund_id": str(d.get("fund_id")),
            "name": d.get("name") or "",
            "short_name": d.get("short_name") or d.get("name") or "",
            "group_label": d.get("group_label") or "",
            "nav": d.get("nav"),
            "nav_date": d.get("nav_date"),
            "chg": parse_pct(d.get("nav_change_pct")),
            "w1": pick("1w", None,
                       fundnav.ret_pct(ser, d.get("nav_date"), d.get("nav"), 7, tol=5)),
            "m1": pick("1m", None,
                       fundnav.ret_pct(ser, d.get("nav_date"), d.get("nav"), 30, tol=10)),
            "ytd": pick("ytd", "ytd", inception_ret_pct(d)),
            "ytd_est": (pick("ytd", "ytd") is None
                        and inception_ret_pct(d) is not None),
            "y1": pick("1y", "1y"),
            "y3": pick("3y", "3y"),
            "size_e8": round(d["size_twd"] / 1e8, 1) if d.get("size_twd") else None,
            "conc": fund_intro.top_concentration(d),
            "risk": d.get("risk_level") or "—",
        })
    return rows


def full_company_name(name: str | None) -> str:
    """官網持股名稱以固定字數截斷（如「成都新易盛通信技術股份有限公」），補回缺字避免誤讀。"""
    n = name or ""
    if n.endswith("股份有限公"):
        return n + "司"
    if n.endswith("股份有"):
        return n + "限公司"
    return n


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
            v = parse_period_pct(ret.get(k))
            if v is not None:
                acc.setdefault(g, {}).setdefault(k, []).append(v)
    return {g: {k: round(sum(vs) / len(vs), 2) for k, vs in ks.items()}
            for g, ks in acc.items()}


def column_extremes(rows: list[dict],
                    keys: tuple[str, ...] = ("chg", "w1", "m1", "ytd", "y1", "y3"),
                    ) -> dict[tuple[str, str], str]:
    """總覽表極值標示（2026-07-22 使用者指示，取代舊「前兩名紅底」）：每組每欄標
    漲最多（ld-up1 深紅）／漲最少（ld-up0 淡紅）／跌最多（ld-dn1 深綠）／跌最少（ld-dn0 淡綠）。
    正值僅一檔時只標「漲最多」（不重複標同一檔）；負值同理。回 {(fund_id, key): css class}。"""
    out: dict[tuple[str, str], str] = {}
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group_label"], []).append(r)
    for rs in groups.values():
        for k in keys:
            pos = sorted((r for r in rs if r.get(k) is not None and r[k] > 0),
                         key=lambda r: r[k], reverse=True)
            neg = sorted((r for r in rs if r.get(k) is not None and r[k] < 0),
                         key=lambda r: r[k])          # 最負在前
            if pos:
                out[(pos[0]["fund_id"], k)] = "ld-up1"
            if len(pos) > 1:
                out[(pos[-1]["fund_id"], k)] = "ld-up0"
            if neg:
                out[(neg[0]["fund_id"], k)] = "ld-dn1"
            if len(neg) > 1:
                out[(neg[-1]["fund_id"], k)] = "ld-dn0"
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
                                          "country": h.get("country"), "funds": []})
            ent["ticker"] = ent["ticker"] or h.get("ticker")
            ent["country"] = ent["country"] or h.get("country")
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
                                "country": ent.get("country"),
                                "funds": sorted(ent["funds"],
                                                key=lambda f: f["weight"], reverse=True)})
        matched.sort(key=lambda m: m["funds"][0]["weight"], reverse=True)
        out.append({"title": card["title"], "oneline": card["oneline"], "matched": matched})
    return out


def stock_url(ticker: str | None, country: str | None,
              name: str | None = None) -> str | None:
    """前十大持股的外部行情頁連結（Yahoo Finance），涵蓋各市場——確保「每一檔都可點」。

    以 Yahoo Finance 為統一入口，逐市場產出正確代碼格式：
      · 台灣（上市／上櫃皆可，僅憑代碼即可查）→ Yahoo奇摩股市 tw.stock.yahoo.com/quote/{代碼}
      · 美國（字母代號，含 . − 者）→ finance.yahoo.com/quote/{T}
      · 日本（3–4 碼數字，或末碼英字的新制代號如 285A，TSE）→ …/quote/{代碼}.T
      · 韓國（6 碼數字，KOSPI 大型股）→ …/quote/{代碼}.KS
      · 中國 A 股（6 碼數字，6／9 開頭滬市 .SS，其餘深市 .SZ）→ …/quote/{代碼}.SS/.SZ
    代號格式與市場不確定、或缺代號時，退回 Yahoo Finance「依名稱／代號搜尋」頁，
    仍保證持股可點（不再出現「有些有連結、有些沒有」）。缺代號又缺名稱才回 None。
    """
    t = str(ticker).strip() if ticker else ""
    c = country or ""
    if t:
        tu = t.upper()
        if c == "美國" and re.fullmatch(r"[A-Z][A-Z.\-]*", tu):
            return f"https://finance.yahoo.com/quote/{tu}"
        if c in ("臺灣", "台灣") and re.fullmatch(r"\d{4,6}[A-Z]?", tu):
            return f"https://tw.stock.yahoo.com/quote/{tu}"
        if c == "日本" and re.fullmatch(r"\d{3,4}[A-Z]?", tu):
            return f"https://finance.yahoo.com/quote/{tu}.T"
        if c == "韓國" and re.fullmatch(r"\d{6}", tu):
            return f"https://finance.yahoo.com/quote/{tu}.KS"
        if c == "中國" and re.fullmatch(r"\d{6}", tu):
            return f"https://finance.yahoo.com/quote/{tu}.{'SS' if tu[0] in '69' else 'SZ'}"
        return f"https://finance.yahoo.com/lookup/?s={quote(t)}"    # 有代號、格式不明 → 搜尋
    if name:
        return f"https://finance.yahoo.com/lookup/?s={quote(str(name))}"
    return None


def upcoming_distributions(funds: list[dict], today: date | None = None,
                           days: int = 7) -> list[dict]:
    """dist_date 落在今日起 days 天內（含當日）的基金。回 [{short_name, dist_date}]。"""
    t = today or clock.today_tw()
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
