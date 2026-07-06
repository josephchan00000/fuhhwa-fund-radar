"""ETF 數據追蹤 —— 台股被動／主動 ETF 週績效追蹤（儀表板第四分頁「ETF」的資料層）。

追蹤兩組清單（2026-07-06 使用者以週報圖表指定；異動只改 WATCHLIST）：
  · 被動 ETF：高股息（0056/00878/00919/00929）＋市值型（0050/006208）
  · 主動式 ETF：00980A 等 11 檔台股主動 ETF（含本家 00991A 主動復華未來50）
欄位對齊週報：規模(億)／成立日期／過去一週報酬／過去一月報酬／配息殖利率／收益分配頻率。
配息殖利率＝年化配息率：最新公布一次的配息金額 ÷ 最新市價 × 配息頻率次數
（月配×12／季配×4／半年配×2／年配×1），非 trailingYield 近12月回溯值。

資料來源與防呆（同專案鐵則）：
  · 抓取走 arm/connectors/etfinfo（Tier B 第三方彙整；雲端 Claude 容器的 proxy 會擋
    etfinfo.tw 與 TWSE——抓不到就沿用既有落檔，GitHub Actions 每日自動補抓）。
  · 逐檔「欄位級合併」：本次抓不到的欄位保留既有值（種子值來自使用者提供之週報圖表），
    不會把已有數字洗成空白；整批全空 → 不覆寫既有落檔（同 fundnews 2026-07-04 教訓）。
  · 數字屬「先給可能值、上線前以投信官網核對」（Tier B），儀表板註記來源與 as-of。

落檔 data/etf_watch.json；arm/fund_dashboard 以「ETF 數據追蹤」分頁呈現。
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "etf_watch.json"

# (code, name, kind, cat)：kind＝passive/active；cat＝表內「性質」欄（高股息/市值型/主動式）
WATCHLIST: list[tuple[str, str, str, str]] = [
    ("0056",   "元大高股息",       "passive", "高股息"),
    ("00878",  "國泰永續高股息",   "passive", "高股息"),
    ("00919",  "群益台灣精選高息", "passive", "高股息"),
    ("00929",  "復華台灣科技優息", "passive", "高股息"),
    ("0050",   "元大台灣50",       "passive", "市值型"),
    ("006208", "富邦台灣50",       "passive", "市值型"),
    ("00980A", "主動野村臺灣優選", "active", "主動式"),
    ("00982A", "主動群益台灣強棒", "active", "主動式"),
    ("00981A", "主動統一台股增長", "active", "主動式"),
    ("00984A", "主動安聯台灣高息", "active", "主動式"),
    ("00985A", "主動野村台灣50",   "active", "主動式"),
    ("00991A", "主動復華未來50",   "active", "主動式"),
    ("00992A", "主動群益科技創新", "active", "主動式"),
    ("00987A", "主動台新優勢成長", "active", "主動式"),
    ("00994A", "主動第一金台股優", "active", "主動式"),
    ("00995A", "主動中信台灣卓越", "active", "主動式"),
    ("00993A", "主動安聯台灣",     "active", "主動式"),
]

# 收益分配頻率的英文 → 表內中文（etfinfo dividendFrequency 兩種寫法都見過，中文直接放行）
_FREQ_MAP = {"monthly": "月配", "quarterly": "季配", "semiannual": "半年配",
             "semi-annual": "半年配", "semiannually": "半年配", "biannual": "半年配",
             "annual": "年配", "annually": "年配", "yearly": "年配", "none": "不配息"}

# 收益分配頻率（中文）→ 一年配息次數（年化配息率＝單次配息率 × 次數）
_FREQ_PER_YEAR = {"月配": 12, "季配": 4, "半年配": 2, "年配": 1}


def _num(v) -> float | None:
    """字串/數字 → float；'+3.32%'、'2兆2413億' 這類顯示字串也盡量救。None/'N/A' 回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else None
    s = str(v).strip().replace(",", "").replace("％", "%")
    if not s or s.upper() in ("N/A", "NA", "—", "-"):
        return None
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)兆(?:(\d+(?:\.\d+)?)億?)?$", s)   # 「2兆2413億」→ 億
    if m:
        return float(m.group(1)) * 1e4 + (float(m.group(2)) if m.group(2) else 0.0)
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)億?%?$", s)
    return float(m.group(1)) if m else None


def _norm_aum_e8(v, prev_e8: float | None) -> float | None:
    """規模正規化成「億元」。etfinfo 的 aum 單位未定（元／百萬／億都有可能），
    有既有值時挑「與既有值數量級最接近」的候選（規模週變動不會差 5 倍）；
    無既有值用門檻猜：≥5e7 視為元、≥1e5 視為百萬、其餘視為已是億。"""
    x = _num(v)
    if x is None or x <= 0:
        return None
    cands = [x, x / 100.0, x / 1e5, x / 1e8]      # 億／百萬／千元／元 → 億
    if prev_e8 and prev_e8 > 0:
        return min(cands, key=lambda c: abs(math.log(c / prev_e8)) if c > 0 else 99)
    if x >= 5e7:
        return x / 1e8
    if x >= 1e5:
        return x / 100.0
    return x


_WEEK_KEYS = ("week", "1w", "w1", "oneWeek", "weekly", "近1週", "近一週", "一週", "1週")
_MONTH_KEYS = ("month", "1m", "m1", "oneMonth", "monthly", "近1月", "近一月", "一月", "1月")


def _ret_from_stats(stats, keys: tuple[str, ...]) -> float | None:
    """returnStats 形狀未定（dict 或 [{period,value}]）——兩種都試，取 % 數字。"""
    if isinstance(stats, dict):
        for k in keys:
            if k in stats:
                return _num(stats[k])
        return None
    if isinstance(stats, list):
        for row in stats:
            if not isinstance(row, dict):
                continue
            label = str(row.get("period") or row.get("label") or row.get("name") or "")
            if any(k.lower() in label.lower() for k in keys):
                return _num(row.get("value") if "value" in row else row.get("return"))
    return None


def _inception(info: dict) -> str | None:
    for k in ("listedDate", "listingDate", "inceptionDate", "establishDate",
              "establishedDate", "setupDate", "listed_date", "established"):
        v = info.get(k)
        if v and re.search(r"\d{4}", str(v)):
            return str(v).replace("-", "/")
    return None


def _freq(info: dict) -> str | None:
    v = str(info.get("dividendFrequency") or info.get("dividend_frequency") or "").strip()
    if not v:
        return None
    return _FREQ_MAP.get(v.lower(), v if re.search(r"[配息]", v) else None)


def _latest_dividend(divs) -> float | None:
    """配息紀錄中「最新一次」的每單位配息金額（依除息日排序取最近）。"""
    rows = [x for x in (divs or [])
            if _num(x.get("amount")) is not None and (x.get("exDate") or x.get("ex_date"))]
    if not rows:
        return None
    rows.sort(key=lambda x: str(x.get("exDate") or x.get("ex_date")), reverse=True)
    return _num(rows[0].get("amount"))


def _annualized_yield(divs, price, freq: str | None) -> float | None:
    """年化配息率＝最新一次配息金額 ÷ 最新市價 × 一年配息次數 ×100%。
    缺配息／市價／頻率任一 → None（由 merge 保留既有值）。"""
    amt, p = _latest_dividend(divs), _num(price)
    n = _FREQ_PER_YEAR.get(freq or "")
    if amt is None or not p or p <= 0 or not n:
        return None
    return round(amt / p * n * 100, 2)


def _fetch_one(code: str) -> dict:
    """單檔抓取 → 欄位字典（抓不到的欄位為 None，由 merge 保留既有值）。

    殖利率一律「年化配息率」：最新公布一次的配息金額 ÷ 最新市價 × 配息頻率次數，
    而非 etfinfo 的 trailingYield（近12月回溯值）——反映當下配息水準。"""
    from .connectors import etfinfo
    d = etfinfo.fetch_etf(code, cache_ttl=600)
    info = d.get("info") or {}
    lm = d.get("latestMarket") or {}
    freq = _freq(info)
    return {
        "aum_raw": lm.get("aum") or info.get("aum"),
        "inception": _inception(info),
        "ret_1w": _ret_from_stats(d.get("returnStats"), _WEEK_KEYS),
        "ret_1m": _ret_from_stats(d.get("returnStats"), _MONTH_KEYS),
        "yield_pct": _annualized_yield(d.get("dividends"), lm.get("price"), freq),
        "freq": freq,
        "mkt_date": lm.get("date"),
    }


def fetch() -> dict:
    """全清單抓取，與既有落檔逐檔「欄位級合併」→ 新 doc（不落檔；落檔用 save）。"""
    prev = {i.get("code"): i for i in (load() or {}).get("items", [])}
    items, got = [], 0
    for code, name, kind, cat in WATCHLIST:
        old = prev.get(code) or {}
        item = {"code": code, "name": name, "kind": kind, "cat": cat,
                "aum_e8": old.get("aum_e8"), "inception": old.get("inception"),
                "ret_1w": old.get("ret_1w"), "ret_1m": old.get("ret_1m"),
                "yield_pct": old.get("yield_pct"), "freq": old.get("freq"),
                "src": old.get("src") or "seed"}
        try:
            f = _fetch_one(code)
        except Exception as e:                     # proxy 擋站/斷網 → 整檔沿用既有值
            print(f"  ⚠ {code} 抓取失敗（沿用既有值）：{e}")
            items.append(item)
            continue
        aum = _norm_aum_e8(f.get("aum_raw"), old.get("aum_e8"))
        fresh = {"aum_e8": aum, "inception": f.get("inception"),
                 "ret_1w": f.get("ret_1w"), "ret_1m": f.get("ret_1m"),
                 "yield_pct": f.get("yield_pct"), "freq": f.get("freq")}
        hit = any(v is not None for v in fresh.values())
        for k, v in fresh.items():
            if v is not None:
                item[k] = v
        if hit:
            item["src"] = "etfinfo"
            if f.get("mkt_date"):
                item["as_of"] = str(f["mkt_date"])
            got += 1
        items.append(item)
    as_of = max((i.get("as_of") or "" for i in items), default="") or \
        (load() or {}).get("as_of") or clock.today_tw().isoformat()
    return {
        "as_of": str(as_of)[:10],
        "fetched_at": clock.stamp_tw("%Y/%m/%d %H:%M"),
        "source": ("etfinfo.tw 第三方彙整（Tier B，上線前以各投信官網核對）"
                   if got else "沿用既有落檔（本次來源不可達）"),
        "items": items,
    }


def is_empty(doc: dict | None) -> bool:
    """全部項目連「規模／週報酬」都沒有 → 視為來源異常，不是真的沒資料。"""
    if not doc or not doc.get("items"):
        return True
    return not any(i.get("aum_e8") is not None or i.get("ret_1w") is not None
                   for i in doc["items"])


def save(doc: dict) -> tuple[Path, bool]:
    """落檔。防呆：本次全空且既有落檔非空 → 保留舊檔不覆寫（回 saved=False）。"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if is_empty(doc) and not is_empty(load()):
        return OUT, False
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUT, True


def load() -> dict | None:
    """儀表板用：讀最近一次落檔；無檔回 None（分頁顯示提示、不壞版）。"""
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
