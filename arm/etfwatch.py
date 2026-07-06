"""ETF 數據追蹤 —— 台股被動／主動 ETF 週績效追蹤（儀表板第四分頁「ETF」的資料層）。

追蹤兩組清單（2026-07-06 使用者以週報圖表指定；異動只改 WATCHLIST）：
  · 被動 ETF：高股息（0056/00878/00919/00929）＋市值型（0050/006208）
  · 主動式 ETF：00980A 等 11 檔台股主動 ETF（含本家 00991A 主動復華未來50）
欄位對齊週報：規模(億)／成立日期／過去一週報酬／過去一月報酬／配息殖利率／收益分配頻率。
配息殖利率＝年化配息率：最新公布一次的配息金額 ÷ 最新市價 × 配息頻率次數
（月配×12／季配×4／半年配×2／年配×1），非 trailingYield 近12月回溯值。

資料來源（雙源、各自獨立降級）：
  · 規模(AUM)／年化配息率／配息頻率 ← arm/connectors/etfinfo（Tier B 第三方彙整）。
  · 過去一週／一月報酬 ← 多來源、單檔單請求取密序列（Yahoo 還原收盤＝總報酬口徑，與逐檔可點
    連結同源 → FinMind → TWSE 官方，依序取第一個歷史足夠密者），以最新交易日收盤對回推
    7／30 日曆日之前最後交易日收盤計算。序列太稀疏會產生錯值（曾見 ret_1w==ret_1m），故加
    「基準日須接近目標日」防呆，寧缺勿錯（不足即退回底稿並標基準日）。

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
    # 2026-07-06 加入熱門／新募集主動式 ETF（成立日期靜態值，經 WebSearch 逐檔查證投信官網／TWSE）：
    ("00988A", "主動統一全球創新", "active", "主動式", "2025/10/21"),  # 統一投信，年配，2026 規模衝上約 594 億
    ("00990A", "主動元大AI新經濟", "active", "主動式", "2025/12/22"),  # 元大投信，不配息，全球 AI 新經濟主題
    ("00403A", "主動統一台股升級50", "active", "主動式", "2026/04/28"),  # 統一投信，季配，募資破紀錄約 792 億
    ("00407A", "主動凱基台灣",     "active", "主動式", "2026/06/12"),  # 凱基投信，不配息，台灣首檔不配息主動台股 ETF
]

# 投信已公告之「當月預估配息」人工維護清單——etfinfo 只揭露已實際除息者、MOPS 端點又抓不到，
# 故投信官方公告（首配或當期預告，除息日未到）於此登錄，作為 est_div 的可靠 fallback。
# 格式 {code: {"amount": 每單位預估金額, "ex_date": "YYYY-MM-DD"}}；僅在「除息日=本月且未到期」時顯示，
# 過月自動失效。投信新公告時更新此處（來源：各投信官網／經濟日報等，除息公告後由 etfinfo 接手實際值）。
# 2026-07 已公告（除息日未到）——經 WebSearch 逐檔查證各投信官網/經濟日報等，跨來源核對。
# 本月除息者：季配(1/4/7/10) 0056/00984A/00992A、月配 00929、半年配 0050/006208、本家 00991A。
# 其餘檔本月非除息月（下次落在 8/9/12 月或 2027），故不列。
ANNOUNCED_EST: dict[str, dict] = {
    "0056":   {"amount": 1.35,  "ex_date": "2026-07-21"},  # 季配 Q3 擬配，創季配新高（元大投信/聯合）
    "00929":  {"amount": 0.38,  "ex_date": "2026-07-21"},  # 月配 7月，創掛牌新高、年化14.8%（復華/ETtoday）
    "0050":   {"amount": 0.6,   "ex_date": "2026-07-21"},  # 半年配 7月第一階段預估（7/17 定案）
    "006208": {"amount": 4.75,  "ex_date": "2026-07-16"},  # 半年配 7月，史上新高（富邦/Newtalk）
    "00984A": {"amount": 0.415, "ex_date": "2026-07-16"},  # 季配 7月，成立以來最高、年化9.9%（安聯/Newtalk）
    "00991A": {"amount": 0.77,  "ex_date": "2026-07-21"},  # 本家首配（復華投信/經濟日報）
    "00992A": {"amount": 0.47,  "ex_date": "2026-07-16"},  # 首配（群益投信/Newtalk）
}

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
    # 2026-07-06 新增（規模為查證概值、報酬待 CI 抓；抓不到時沿用此底稿，報酬留空由儀表板標「—」）：
    "00988A": {"aum_e8": 594.0, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "年配"},
    "00990A": {"aum_e8": None,  "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "不配息"},
    "00403A": {"aum_e8": 792.0, "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "季配"},
    "00407A": {"aum_e8": 78.7,  "ret_1w": None, "ret_1m": None, "yield_pct": None, "freq": "不配息"},
}

# 「待首次 CI 抓取」的新增檔：本環境（雲端 Claude proxy）抓不到乾淨報酬／規模，且無使用者週報底稿，
# 故報酬暫留空（儀表板標「—」），不杜撰數字；待 daily.yml（CI，不受 proxy 擋）首次抓取後由實際值補上。
# 這些檔暫不受「SEED 報酬一律非空」不變式約束（成立日期／頻率等靜態欄位仍必備）。
_SEED_PENDING: set[str] = {"00988A", "00990A", "00403A", "00407A"}

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


def _div_rows(divs) -> list[tuple[date, float, bool]]:
    """配息紀錄 → [(除息日, 每單位金額, 是否為預估)]，依除息日排序。

    預估旗標：etfinfo 常見多種寫法都認（estimated/isEstimate/type=estimate/status 含『預』）。"""
    out: list[tuple[date, float, bool]] = []
    for x in (divs or []):
        amt = _num(x.get("amount"))
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
                     str(x.get("exDate") or x.get("ex_date") or ""))
        if amt is None or not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        flag = " ".join(str(x.get(k) or "") for k in
                        ("estimated", "isEstimate", "estimate", "type", "status", "note"))
        est = bool(x.get("estimated")) or ("estimate" in flag.lower()) or ("預" in flag)
        out.append((d, amt, est))
    out.sort(key=lambda r: r[0])
    return out


def _latest_dividend(divs) -> float | None:
    """最近一次「已實際配發」（除息日已到、非預估）的每單位配息金額——年化殖利率用。"""
    last, _ld, _e, _ed = _dividend_split(divs)
    return last


def _dividend_split(divs, today: date | None = None) -> tuple:
    """拆成 (最近一次實際配息, 其除息日, 當月預估配息, 其除息日)。

    · 最近一次實際：除息日 ≤ 今天且非預估者中最新一筆。
    · 當月預估：投信於配息月 1 日公告的「預計配息金額」——取除息日在『本月且尚未除息』
      或明確標記為預估者中最近一筆。無則 (…, None, None)。"""
    today = today or clock.today_tw()
    rows = _div_rows(divs)
    actual = [r for r in rows if r[0] <= today and not r[2]]
    last_amt, last_d = (actual[-1][1], actual[-1][0].isoformat()) if actual else (None, None)
    est_cands = [r for r in rows
                 if (r[2] or r[0] > today) and r[0].year == today.year and r[0].month == today.month]
    est_amt, est_d = (est_cands[0][1], est_cands[0][0].isoformat()) if est_cands else (None, None)
    return last_amt, last_d, est_amt, est_d


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
    last_amt, last_d, est_amt, est_d = _dividend_split(d.get("dividends"))
    return {"aum_raw": lm.get("aum") or info.get("aum"),
            "close_px": _num(lm.get("price")),
            "yield_pct": _annualized_yield(d.get("dividends"), lm.get("price"), freq),
            "last_div": last_amt, "last_div_date": last_d,
            "est_div": est_amt, "est_div_date": est_d,
            "freq": freq, "mkt_date": lm.get("date")}


def _stooq_series(code: str) -> dict[str, float]:
    """stooq 日線 CSV（乾淨、每交易日一筆原始收盤，專為程式抓取）→ {iso_date: 收盤}。

    Yahoo 圖表 API 曾對個別檔回傳「不同日期同一收盤值」的髒資料（例 0056 6/5 與 6/29 都 51.8），
    改以 stooq 為第一來源交叉比對。抓不到或代碼不存在回 {}（退下一來源）。"""
    from .http import get_bytes
    url = f"https://stooq.com/q/d/l/?s={code.lower()}.tw&i=d"
    try:
        txt = get_bytes(url, cache_ttl=3600, retries=2).decode("utf-8", "ignore")
    except Exception:
        return {}
    out: dict[str, float] = {}
    for line in txt.splitlines()[1:]:                # 跳表頭 Date,Open,High,Low,Close,Volume
        p = line.split(",")
        if len(p) >= 5 and re.match(r"\d{4}-\d{2}-\d{2}$", p[0].strip()):
            c = _num(p[4])
            if c:
                out[p[0].strip()] = c
    if len(out) > 90:                                # 只留近 ~90 個交易日，夠算週/月報酬
        for k in sorted(out)[:-90]:
            del out[k]
    return out


def _yahoo_series(code: str) -> dict[str, float]:
    """Yahoo Finance 圖表 API → {iso_date: 收盤}。單一請求、涵蓋近3月逐日。

    取「原始收盤」(quote.close) 為主、adjClose 為輔——近月視窗內無除息時原始收盤即等於
    總報酬，且避開 adjClose 偶發的稀疏/還原偏差。取不到回 {}。"""
    from datetime import datetime

    from .http import get_json
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.TW"
           "?range=3mo&interval=1d")
    try:
        d = get_json(url, cache_ttl=3600)
    except Exception:
        return {}
    res = (((d or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return {}
    ts = res.get("timestamp") or []
    ind = res.get("indicators") or {}
    raw = ((ind.get("quote") or [{}])[0] or {}).get("close") or []
    adj = ((ind.get("adjclose") or [{}])[0] or {}).get("adjclose") or []
    out: dict[str, float] = {}
    for i, t in enumerate(ts):
        c = raw[i] if i < len(raw) and raw[i] is not None else \
            (adj[i] if i < len(adj) and adj[i] is not None else None)
        if c:
            iso = datetime.fromtimestamp(t, clock.TW_TZ).date().isoformat()
            out[iso] = float(c)
    return out


def _finmind_series(code: str, today: date) -> dict[str, float]:
    """FinMind TaiwanStockPrice（免金鑰，有 token 更寬鬆）→ {iso_date: 收盤}。單一請求涵蓋近75日。"""
    import os

    from .http import get_json
    start = (today - timedelta(days=75)).isoformat()
    token = os.environ.get("FINMIND_TOKEN", "")
    url = (f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice"
           f"&data_id={code}&start_date={start}&end_date={today.isoformat()}"
           + (f"&token={token}" if token else ""))
    try:
        d = get_json(url, cache_ttl=3600)
    except Exception:
        return {}
    if not isinstance(d, dict) or d.get("status") != 200:
        return {}
    return {r["date"]: float(r["close"]) for r in (d.get("data") or [])
            if r.get("date") and r.get("close")}


def _twse_series(code: str, today: date) -> dict[str, float]:
    """TWSE 官方每日收盤（權威）→ {iso_date: 收盤}。抓當月＋前兩月，涵蓋 30 日回推。
    註：TWSE 為價格收盤（未還原息），高股息 ETF 於除息日附近會低估總報酬。"""
    from .connectors import twse
    close: dict[str, float] = {}
    m0 = today.replace(day=1)
    for back in (0, 1, 2):
        d0 = m0
        for _ in range(back):
            d0 = (d0 - timedelta(days=1)).replace(day=1)
        for iso, c, _v in twse.fetch_month(code, d0.year, d0.month):
            if c:
                close[iso] = c
    return close


def _returns_from_series(close: dict[str, float]) -> dict:
    """由 {iso: close} 日序列算過去一週(7)/一月(30 日曆日)報酬。

    防呆：某週期的基準日必須「真的接近 N 天前」（在 target 前 12 天內）——資料太稀疏時
    基準會落在很早的孤點、把區間拉長算出錯值（曾見 ret_1w==ret_1m）；此時該週期不報（回 None、
    交由上層退回底稿），寧缺勿錯。"""
    dates = sorted(close)
    out: dict = {"ret_1w": None, "ret_1m": None, "perf_date": None,
                 "ret_1w_base": None, "ret_1m_base": None}
    if len(dates) < 2:
        return out
    last = dates[-1]
    last_d = date.fromisoformat(last)
    out["perf_date"] = last

    def _ret(days: int, tag: str):
        target = last_d - timedelta(days=days)
        prior = [d for d in dates if date.fromisoformat(d) <= target]
        if not prior:
            return None
        bd = prior[-1]
        if (target - date.fromisoformat(bd)).days > 12:      # 基準離目標日太遠＝大缺口 → 不報
            return None
        base = close[bd]
        out[f"{tag}_base"] = f"{bd}={base:g}"                 # 追查用：所用基準日與收盤
        return round((close[last] / base - 1) * 100, 2) if base else None

    out["ret_1w"] = _ret(7, "ret_1w")
    out["ret_1m"] = _ret(30, "ret_1m")
    return out


# 3 個月日線約 60 個交易日；序列夠密才信任（否則 1 個月基準會落孤點算出錯值）。
_MIN_SERIES = 25


def _is_degenerate(series: dict[str, float]) -> bool:
    """髒序列偵測：相異收盤值太少（<60% 交易日各異）＝疑似來源回傳重複值
    （曾見 Yahoo 對 0056 多日回同一 51.8）→ 不信任、換下一來源。"""
    n = len(series)
    return n >= 10 and len(set(series.values())) < n * 0.6


def _fetch_returns(code: str, today: date | None = None) -> dict:
    """過去一週／一月報酬 —— 多來源、單檔單請求，取第一個「乾淨且夠密」的序列。

    來源順序：stooq（乾淨日線）→ Yahoo → FinMind → TWSE。序列須 ≥ _MIN_SERIES 點且非「重複值
    髒序列」才採用；回傳 ret_src／ret_n／基準日供追查；全失敗回 None（上層退回底稿）。"""
    today = today or clock.today_tw()
    best = None
    for src, series in (("stooq", _stooq_series(code)),
                        ("yahoo", _yahoo_series(code)),
                        ("finmind", _finmind_series(code, today)),
                        ("twse", _twse_series(code, today))):
        n = len(series)
        if n < 5 or _is_degenerate(series):           # 太短或髒（重複值）→ 換下一來源
            continue
        r = _returns_from_series(series)
        r["ret_src"], r["ret_n"] = src, n
        # 註：一週==一月報酬是「該檔近月盤整（兩基準日同價）」的合理結果，非錯值——不再據此判髒
        # （2026-07-06 教訓：0056 6月盤整於 51.8，週≈月≈2.8% 是對的；曾誤攔正確資料）。
        if n >= _MIN_SERIES and (r["ret_1w"] is not None or r["ret_1m"] is not None):
            return r                                  # 乾淨且夠密即採用
        best = best or r                              # 太稀疏：暫存，後續來源皆不足才用
    return best or {"ret_1w": None, "ret_1m": None, "perf_date": None,
                    "ret_src": None, "ret_n": 0}


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
    today = clock.today_tw()
    try:                                                  # 當月預估配息 ← MOPS（一次抓全 ETF）
        from .connectors import mops
        mops_dist = mops.etf_distributions({c for c, *_ in WATCHLIST})
    except Exception as e:
        print(f"  ⚠ MOPS 收益分配抓取失敗（預估配息欄留空）：{e}")
        mops_dist = {}
    items, got_mkt, got_ret, got_est = [], 0, 0, 0
    for code, name, kind, cat, inception in WATCHLIST:
        old = prev.get(code) or {}
        base = SEED_PERF.get(code, {})
        item = {"code": code, "name": name, "kind": kind, "cat": cat,
                "inception": inception,                       # 靜態、永遠有值
                "aum_e8": _pick(old, base, "aum_e8"),
                "close_px": old.get("close_px"),              # 最新收盤價（etfinfo 市價）
                "ret_1w": _pick(old, base, "ret_1w"),
                "ret_1m": _pick(old, base, "ret_1m"),
                "last_div": old.get("last_div"),              # 最近一次「實際」配息金額
                "last_div_date": old.get("last_div_date"),
                "est_div": old.get("est_div"),                # 當月「預估」配息金額（投信公告，非正式）
                "est_div_date": old.get("est_div_date"),
                "yield_pct": _pick(old, base, "yield_pct"),
                "freq": _pick(old, base, "freq"),
                "as_of": old.get("as_of"),
                "perf_asof": old.get("perf_asof") or SEED_ASOF,  # 報酬數據基準日
                "ret_src": old.get("ret_src") or "seed",         # 報酬來源（yahoo/finmind/twse/seed）
                "src": old.get("src") or "seed"}
        # ① 規模／收盤價／配息（實際＋預估）／殖利率／頻率 ← etfinfo
        try:
            m = _fetch_market(code)
            aum = _norm_aum_e8(m.get("aum_raw"), item["aum_e8"])
            for k, v in (("aum_e8", aum), ("close_px", m.get("close_px")),
                         ("yield_pct", m.get("yield_pct")), ("freq", m.get("freq")),
                         ("last_div", m.get("last_div")), ("last_div_date", m.get("last_div_date"))):
                if v is not None:
                    item[k] = v
            item["est_div"] = m.get("est_div")                # 預估配息：無公告即清空（過月即消失）
            item["est_div_date"] = m.get("est_div_date")
            if any(v is not None for v in (aum, m.get("close_px"), m.get("yield_pct"), m.get("freq"))):
                item["src"] = "etfinfo+px"
                if m.get("mkt_date"):
                    item["as_of"] = str(m["mkt_date"])[:10]
                got_mkt += 1
        except Exception as e:                     # proxy 擋站/斷網 → 沿用 fallback 值
            print(f"  ⚠ {code} 規模／殖利率抓取失敗（沿用既有值／週報底稿）：{e}")

        # ② 過去一週／一月報酬 ← Yahoo 還原收盤／FinMind／TWSE（依序取密序列）自算
        try:
            r = _fetch_returns(code)
            if r.get("ret_1w") is not None:
                item["ret_1w"] = r["ret_1w"]
            if r.get("ret_1m") is not None:
                item["ret_1m"] = r["ret_1m"]
            if (r.get("ret_1w") is not None or r.get("ret_1m") is not None) and r.get("perf_date"):
                item["perf_asof"] = str(r["perf_date"])[:10]     # 報酬有更新才推進基準日
                item["ret_src"] = r.get("ret_src")               # 報酬取自哪個來源（追查用）
                item["ret_n"] = r.get("ret_n")                   # 序列點數（診斷稀疏度）
                item["ret_1w_base"] = r.get("ret_1w_base")       # 一週報酬所用基準日=收盤
                item["ret_1m_base"] = r.get("ret_1m_base")       # 一月報酬所用基準日=收盤
                got_ret += 1
        except Exception as e:
            print(f"  ⚠ {code} 報酬抓取失敗（沿用既有值／週報底稿）：{e}")

        # ③ 當月預估配息（僅取本月、除息日尚未到期者）：etfinfo 未揭露預告時，
        #    依序補 MOPS 公告 → 投信已公告人工清單 ANNOUNCED_EST（etfinfo/MOPS 皆抓不到時的可靠來源）。
        if item.get("est_div") is None:
            for src_name, cand in (("mops", mops_dist.get(code)),
                                   ("announced", ANNOUNCED_EST.get(code))):
                ex = (cand or {}).get("ex_date")
                amt = (cand or {}).get("amount")
                try:
                    exd = date.fromisoformat(ex) if ex else None
                except ValueError:
                    exd = None
                if (exd and exd.year == today.year and exd.month == today.month
                        and exd >= today and amt is not None):
                    item["est_div"], item["est_div_date"], item["est_src"] = amt, ex, src_name
                    got_est += 1
                    break

        # ④ 換算年化配息率：有當月預估配息時，改用「預估配息 × 年配息次數 ÷ 最新收盤價」（新聞口徑）
        #    並標記 yield_is_est；否則維持最近一次「實際」配息年化。
        n = _FREQ_PER_YEAR.get(item.get("freq") or "")
        if item.get("est_div") is not None and item.get("close_px") and n:
            item["yield_pct"] = round(item["est_div"] / item["close_px"] * n * 100, 2)
            item["yield_is_est"] = True
        else:
            item["yield_is_est"] = False

        items.append(item)
    got = got_mkt + got_ret
    as_of = max((i.get("as_of") or "" for i in items), default="") or \
        (load() or {}).get("as_of") or clock.today_tw().isoformat()
    est_note = f"；當月預估配息 ← 投信公告／MOPS（{got_est} 檔）" if got_est else ""
    if got_ret:
        src_note = ("規模／配息殖利率 ← etfinfo.tw（Tier B）；過去一週／一月報酬 ← Yahoo 還原收盤"
                    f"（總報酬口徑）／FinMind／TWSE 官方自算{est_note}。正式對外前以各投信官網核對")
    elif got_mkt:
        src_note = ("規模／配息殖利率 ← etfinfo.tw（Tier B）；報酬沿用最近可得週報底稿"
                    f"（報酬來源本次不可達）{est_note}。正式對外前以各投信官網核對")
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
