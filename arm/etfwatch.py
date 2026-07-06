"""ETF 數據追蹤 —— 台股被動／主動 ETF 週績效追蹤（儀表板第四分頁「ETF」的資料層）。

追蹤兩組清單（2026-07-06 使用者以週報圖表指定；異動只改 WATCHLIST）：
  · 被動 ETF：高股息（0056/00878/00919/00929）＋市值型（0050/006208）
  · 主動式 ETF：00980A 等 11 檔台股主動 ETF（含本家 00991A 主動復華未來50）
欄位對齊週報：規模(億)／成立日期／過去一週報酬／過去一月報酬／配息殖利率／收益分配頻率。
配息殖利率＝年化配息率：最新公布一次的配息金額 ÷ 最新市價 × 配息頻率次數
（月配×12／季配×4／半年配×2／年配×1），非 trailingYield 近12月回溯值。

資料來源（雙源、各自獨立降級）：
  · 規模(AUM)／年化配息率／配息頻率 ← arm/connectors/etfinfo（Tier B 第三方彙整）。
  · 過去一週／一月報酬 ← arm/connectors/twse 官方每日收盤自算（權威、免金鑰）：
    以最新交易日收盤對回推 7／30 日曆日之前最後交易日收盤計算，反映真實近週／近月漲跌。

防呆（同專案鐵則）：
  · 雲端 Claude 容器的 proxy 會擋 etfinfo.tw 與 TWSE——抓不到就沿用既有落檔，
    GitHub Actions（不受 proxy 擋）每日自動補抓。
  · 逐檔「欄位級合併」，fallback 鏈：本次新值 → 既有落檔 → 內建 SEED_PERF 週報底稿；
    成立日期一律取 WATCHLIST 靜態值。本次抓不到的欄位保留既有值、絕不洗成空白／null；
    整批全空 → 不覆寫既有落檔（同 fundnews 2026-07-04 教訓）。
  · 報酬標 perf_asof 基準日、規模／殖利率標 as_of 抓取日，儀表板分別註記。
  · etfinfo 數字屬「先給可能值、上線前以投信官網核對」（Tier B）。

落檔 data/etf_watch.json；arm/fund_dashboard 以「ETF 數據追蹤」分頁呈現。
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "etf_watch.json"

# (code, name, kind, cat, inception)：kind＝passive/active；cat＝表內「性質」欄；
# inception＝成立日期（固定值，不會變、不需抓、永不空白——避免來源缺欄時整片留空）。
WATCHLIST: list[tuple[str, str, str, str, str]] = [
    ("0056",   "元大高股息",       "passive", "高股息", "2007/12/13"),
    ("00878",  "國泰永續高股息",   "passive", "高股息", "2020/07/10"),
    ("00919",  "群益台灣精選高息", "passive", "高股息", "2022/10/13"),
    ("00929",  "復華台灣科技優息", "passive", "高股息", "2023/06/01"),
    ("0050",   "元大台灣50",       "passive", "市值型", "2003/06/30"),
    ("006208", "富邦台灣50",       "passive", "市值型", "2012/06/22"),
    ("00980A", "主動野村臺灣優選", "active", "主動式", "2025/04/22"),
    ("00982A", "主動群益台灣強棒", "active", "主動式", "2025/05/13"),
    ("00981A", "主動統一台股增長", "active", "主動式", "2025/05/15"),
    ("00984A", "主動安聯台灣高息", "active", "主動式", "2025/07/03"),
    ("00985A", "主動野村台灣50",   "active", "主動式", "2025/07/08"),
    ("00991A", "主動復華未來50",   "active", "主動式", "2025/12/09"),
    ("00992A", "主動群益科技創新", "active", "主動式", "2025/12/16"),
    ("00987A", "主動台新優勢成長", "active", "主動式", "2025/12/16"),
    ("00994A", "主動第一金台股優", "active", "主動式", "2025/12/26"),
    ("00995A", "主動中信台灣卓越", "active", "主動式", "2026/01/13"),
    ("00993A", "主動安聯台灣",     "active", "主動式", "2026/01/20"),
]

# 內建週報基準底稿（來源全倒／JSON 被清空時的最後 fallback，永不整片留空）。
# 值取自使用者提供之週報圖表；ret_1w/ret_1m＝該基準日的近1週／近1月報酬（%）。
SEED_ASOF = "2026-07-03"
SEED_PERF: dict[str, dict] = {
    "0056":   {"aum_e8": 7270.42, "ret_1w": 3.32, "ret_1m": 15.17, "yield_pct": 7.5,  "freq": "季配"},
    "00878":  {"aum_e8": 6257.30, "ret_1w": 2.90, "ret_1m": 19.89, "yield_pct": 7.84, "freq": "季配"},
    "00919":  {"aum_e8": 5542.20, "ret_1w": 2.23, "ret_1m": 18.15, "yield_pct": 13.2, "freq": "季配"},
    "00929":  {"aum_e8": 1448.10, "ret_1w": 4.03, "ret_1m": 17.57, "yield_pct": 9.97, "freq": "月配"},
    "0050":   {"aum_e8": 22413.0, "ret_1w": 3.06, "ret_1m": 12.70, "yield_pct": 1.87, "freq": "半年配"},
    "006208": {"aum_e8": 4658.56, "ret_1w": 3.07, "ret_1m": 12.71, "yield_pct": 3.59, "freq": "半年配"},
    "00980A": {"aum_e8": 180.24, "ret_1w": 1.62, "ret_1m": 8.18,  "yield_pct": 7.85,  "freq": "季配"},
    "00982A": {"aum_e8": 540.03, "ret_1w": 3.03, "ret_1m": 9.06,  "yield_pct": 10.41, "freq": "季配"},
    "00981A": {"aum_e8": 2948.01, "ret_1w": 2.72, "ret_1m": 7.72, "yield_pct": 8.05,  "freq": "季配"},
    "00984A": {"aum_e8": 79.19,  "ret_1w": 3.44, "ret_1m": 10.49, "yield_pct": 6.4,   "freq": "季配"},
    "00985A": {"aum_e8": 109.85, "ret_1w": 1.76, "ret_1m": 5.76,  "yield_pct": None,  "freq": "年配"},
    "00991A": {"aum_e8": 651.97, "ret_1w": 2.81, "ret_1m": 10.46, "yield_pct": None,  "freq": "半年配"},
    "00992A": {"aum_e8": 465.97, "ret_1w": 2.26, "ret_1m": 3.71,  "yield_pct": None,  "freq": "季配"},
    "00987A": {"aum_e8": 31.94,  "ret_1w": 1.50, "ret_1m": 2.08,  "yield_pct": None,  "freq": "年配"},
    "00994A": {"aum_e8": 56.42,  "ret_1w": -0.93, "ret_1m": 2.20, "yield_pct": None,  "freq": "季配"},
    "00995A": {"aum_e8": 57.44,  "ret_1w": 1.61, "ret_1m": 5.95,  "yield_pct": None,  "freq": "季配"},
    "00993A": {"aum_e8": 115.73, "ret_1w": 2.50, "ret_1m": 8.64,  "yield_pct": None,  "freq": "年配"},
}

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


def _fetch_market(code: str) -> dict:
    """etfinfo（Tier B）：規模(AUM)／年化配息率／配息頻率／市價日。

    殖利率一律「年化配息率」：最新公布一次的配息金額 ÷ 最新市價 × 配息頻率次數，
    而非 etfinfo 的 trailingYield（近12月回溯值）——反映當下配息水準。"""
    from .connectors import etfinfo
    d = etfinfo.fetch_etf(code, cache_ttl=600)
    info = d.get("info") or {}
    lm = d.get("latestMarket") or {}
    freq = _freq(info)
    return {"aum_raw": lm.get("aum") or info.get("aum"),
            "yield_pct": _annualized_yield(d.get("dividends"), lm.get("price"), freq),
            "freq": freq, "mkt_date": lm.get("date")}


def _fetch_returns(code: str, today: date | None = None) -> dict:
    """TWSE 官方每日收盤（權威、免金鑰）→ 過去一週(7 日曆日)／一月(30 日曆日)報酬。

    以「最新交易日收盤」對回推日之前最後一個交易日收盤算報酬，反映真實近週／近月漲跌。
    抓當月＋前一月兩份逐日收盤即足夠涵蓋 30 日回推。取不到（休市初／上櫃檔／斷網）回 None。"""
    from .connectors import twse
    today = today or clock.today_tw()
    prev1 = today.replace(day=1) - timedelta(days=1)          # 前一月任一天
    close: dict[str, float] = {}
    for y, m in ((prev1.year, prev1.month), (today.year, today.month)):
        for iso, c, _v in twse.fetch_month(code, y, m):
            if c:
                close[iso] = c
    dates = sorted(close)
    if len(dates) < 2:
        return {"ret_1w": None, "ret_1m": None, "perf_date": None}
    last = dates[-1]

    def _ret(days: int) -> float | None:
        target = date.fromisoformat(last) - timedelta(days=days)
        prior = [d for d in dates if date.fromisoformat(d) <= target]
        if not prior:
            return None
        base = close[prior[-1]]
        return round((close[last] / base - 1) * 100, 2) if base else None

    return {"ret_1w": _ret(7), "ret_1m": _ret(30), "perf_date": last}


def _pick(old: dict, base: dict, key: str):
    """欄位級 fallback：既有落檔值（非 None）優先，否則用內建週報底稿 base。
    注意用『值是否為 None』判斷，不用 key 是否存在——CI 曾把欄位寫成顯式 null，
    dict.get(key, default) 會回傳那個 null 而非 default，反而把資料洗空。"""
    v = old.get(key)
    return v if v is not None else base.get(key)


def fetch() -> dict:
    """全清單抓取，與既有落檔／內建週報底稿逐檔「欄位級合併」→ 新 doc（不落檔；落檔用 save）。

    雙來源、各自獨立降級：規模／年化配息率／頻率 ← etfinfo；過去一週／一月報酬 ← TWSE 官方收盤自算。
    fallback 鏈（每欄位獨立）：本次新值 → 既有落檔值 → 內建 SEED_PERF 週報底稿。
    成立日期一律取 WATCHLIST 靜態值（永不空白）。抓不到的欄位絕不留空／不洗成 null。
    """
    prev = {i.get("code"): i for i in (load() or {}).get("items", [])}
    items, got_mkt, got_ret = [], 0, 0
    for code, name, kind, cat, inception in WATCHLIST:
        old = prev.get(code) or {}
        base = SEED_PERF.get(code, {})
        item = {"code": code, "name": name, "kind": kind, "cat": cat,
                "inception": inception,                       # 靜態、永遠有值
                "aum_e8": _pick(old, base, "aum_e8"),
                "ret_1w": _pick(old, base, "ret_1w"),
                "ret_1m": _pick(old, base, "ret_1m"),
                "yield_pct": _pick(old, base, "yield_pct"),
                "freq": _pick(old, base, "freq"),
                "as_of": old.get("as_of"),
                "perf_asof": old.get("perf_asof") or SEED_ASOF,  # 報酬數據基準日
                "src": old.get("src") or "seed"}
        # ① 規模／殖利率／頻率 ← etfinfo
        try:
            m = _fetch_market(code)
            aum = _norm_aum_e8(m.get("aum_raw"), item["aum_e8"])
            for k, v in (("aum_e8", aum), ("yield_pct", m.get("yield_pct")),
                         ("freq", m.get("freq"))):
                if v is not None:
                    item[k] = v
            if any(v is not None for v in (aum, m.get("yield_pct"), m.get("freq"))):
                item["src"] = "etfinfo+twse"
                if m.get("mkt_date"):
                    item["as_of"] = str(m["mkt_date"])[:10]
                got_mkt += 1
        except Exception as e:                     # proxy 擋站/斷網 → 沿用 fallback 值
            print(f"  ⚠ {code} 規模／殖利率抓取失敗（沿用既有值／週報底稿）：{e}")

        # ② 過去一週／一月報酬 ← TWSE 官方每日收盤自算（權威）
        try:
            r = _fetch_returns(code)
            if r.get("ret_1w") is not None:
                item["ret_1w"] = r["ret_1w"]
            if r.get("ret_1m") is not None:
                item["ret_1m"] = r["ret_1m"]
            if (r.get("ret_1w") is not None or r.get("ret_1m") is not None) and r.get("perf_date"):
                item["perf_asof"] = str(r["perf_date"])[:10]     # 報酬有更新才推進基準日
                got_ret += 1
        except Exception as e:
            print(f"  ⚠ {code} 報酬（TWSE）抓取失敗（沿用既有值／週報底稿）：{e}")

        items.append(item)
    got = got_mkt + got_ret
    as_of = max((i.get("as_of") or "" for i in items), default="") or \
        (load() or {}).get("as_of") or clock.today_tw().isoformat()
    if got_ret:
        src_note = ("規模／配息殖利率 ← etfinfo.tw（Tier B）；過去一週／一月報酬 ← TWSE 官方每日收盤自算。"
                    "正式對外前以各投信官網核對")
    elif got_mkt:
        src_note = ("規模／配息殖利率 ← etfinfo.tw（Tier B）；報酬沿用最近可得週報底稿"
                    "（TWSE 本次不可達）。正式對外前以各投信官網核對")
    else:
        src_note = "沿用既有落檔／週報底稿（本次來源皆不可達）"
    return {
        "as_of": str(as_of)[:10],
        "perf_asof": max((i.get("perf_asof") or "" for i in items), default="") or SEED_ASOF,
        "fetched_at": clock.stamp_tw("%Y/%m/%d %H:%M"),
        "source": src_note,
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
