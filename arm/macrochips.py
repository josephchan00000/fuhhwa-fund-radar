"""總經・籌碼數據「市場溫度計」（2026-07-23 使用者需求）—— 總經分頁的官方數據層。

兩組指標、各自獨立降級：
  · 全球市場溫度計 ← Yahoo 圖表 API（^VIX／^TNX／DXY／TWD=X／BZ=F／GC=F；CI 可達，
    factcheck.yahoo_index_series 同一端點）——每次抓近 1 個月日線整段合併。
  · 台股籌碼 ← TWSE／TAIFEX 官方 API（三大法人買賣超＝factcheck.twse_inst_flows 重用；
    融資融券餘額＝MI_MARGN；外資台指期淨部位／選擇權 P/C 比＝期交所下載端點，
    支援日期區間、一次補齊近兩週史料）。

資料層 data/macro_chips.json（**必須入庫**當 fallback——同 etf_watch 的坑）：
  {"as_of": 抓取時戳, "series": {key: {ISO日期: 值}}, "src": {key: {...}}}
合併鐵則（同專案慣例）：本次抓到的「非 None」值才寫入；某指標整段抓不到 → 保留既有
序列原封不動，**絕不把非空序列洗成空**。序列每指標保留最近 _KEEP 筆。

本 Claude 容器 proxy 擋 twse/taifex/yahoo —— 抓取只在正式區 CI 跑（daily_fund.sh）；
容器內只讀落檔（含 WebSearch 查證的種子值）建儀表板。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from . import clock, factcheck

ROOT = Path(__file__).resolve().parent.parent
DATA_FP = ROOT / "data" / "macro_chips.json"

_TIMEOUT = 12
_UA = {"User-Agent": "Mozilla/5.0 (macrochips; fuhhwa-fund-radar)"}
_KEEP = 45            # 每指標保留筆數（30 日走勢圖＋緩衝）
_BACKFILL_DAYS = 14   # TWSE 逐日端點往回補抓的日曆日窗

# ── 指標規格（key, 中文名, 來源, Yahoo 代碼或 None） ─────────────────────
#   group: gl=全球溫度計 / tw=台股籌碼
GLOBAL_SPECS: list[tuple[str, str, str]] = [
    ("vix",    "VIX 恐慌指數",          "^VIX"),
    ("us10y",  "美國 10 年期公債殖利率", "^TNX"),      # ^TNX：Yahoo chart 有時回百分比本身(4.66)、
                                                      # 有時×10(46.6)——_norm_yield 依量級自動正規化
    ("dxy",    "美元指數 DXY",          "DX-Y.NYB"),
    ("usdtwd", "美元兌新台幣",          "TWD=X"),
    ("brent",  "布蘭特原油",            "BZ=F"),
    ("gold",   "黃金期貨",              "GC=F"),
]
TW_KEYS = ("inst_total", "inst_foreign", "inst_trust", "inst_dealer", "tx_foreign_net",
           "margin_bal", "short_bal", "pc_ratio")
ALL_KEYS = tuple(k for k, *_ in GLOBAL_SPECS) + TW_KEYS


# ── 來源層（每源獨立；回 {} ＝不可得，上層沿用既有序列） ────────────────

def _norm_yield(v: float) -> float:
    """^TNX 殖利率正規化：Yahoo chart 端點有時回百分比本身（如 4.66），有時回 ×10（46.6）。
    10 年期殖利率合理量級 0–20%，>20 一律視為 ×10 → ÷10。防 2026-07-23 踩的坑：
    寫死 ÷10 讓 4.657 變 0.4657（線上顯示 0.47%）。"""
    return round(v / 10.0, 4) if v > 20 else round(v, 4)


def _yahoo_series(sym: str, norm=None) -> dict[str, float]:
    """Yahoo 圖表 API 近 1 個月日線 → {ISO日期: 收盤}。norm＝逐值正規化函式（如殖利率）。失敗回 {}。"""
    try:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(sym)}?range=1mo&interval=1d")
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            doc = json.loads(r.read().decode("utf-8"))
        res = doc["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
    except Exception:
        return {}
    from datetime import datetime, timezone
    out: dict[str, float] = {}
    for t, c in zip(ts, closes):
        if c is None:
            continue
        iso = datetime.fromtimestamp(t, timezone.utc).date().isoformat()
        val = float(c)
        out[iso] = norm(val) if norm else round(val, 4)
    return out


def _twse_inst_all(d: date) -> dict | None:
    """TWSE BFI82U（三大法人買賣金額）→ {'foreign','trust','dealer','total'}（億元，買超為正）。
    自營商＝自行買賣＋避險合計；外資＝外資及陸資（不含外資自營商）。整段抓不到回 None。"""
    doc = factcheck._get_json(f"https://www.twse.com.tw/rwd/zh/fund/BFI82U"
                              f"?type=day&dayDate={d:%Y%m%d}&response=json")
    if not isinstance(doc, dict) or doc.get("stat") != "OK":
        return None
    out = {"foreign": None, "trust": 0.0, "dealer": 0.0, "total": None}
    got_dealer = got_trust = False
    try:
        for row in doc.get("data") or []:
            name = str(row[0])
            diff = float(str(row[3]).replace(",", "")) / 1e8      # 官方單位元 → 億
            # 外資列名為「外資及陸資(不含外資自營商)」——含「自營」字樣，故以獨有的「陸資」二字辨識，
            # 不可用「自營 not in name」（會誤殺，factcheck 舊版同坑）。「外資自營商」不含「陸資」→ 不誤收。
            if "陸資" in name:
                out["foreign"] = round((out["foreign"] or 0.0) + diff, 2)
            elif "投信" in name:
                out["trust"] = round(out["trust"] + diff, 2); got_trust = True
            elif "自營商" in name and "外資" not in name:          # 自行買賣＋避險兩列（不含外資自營商）
                out["dealer"] = round(out["dealer"] + diff, 2); got_dealer = True
            elif name.strip() == "合計":
                out["total"] = round(diff, 2)
    except Exception:
        return None
    if not got_trust:
        out["trust"] = None
    if not got_dealer:
        out["dealer"] = None
    return out if any(v is not None for v in out.values()) else None


def _twse_margin(d: date) -> tuple[float, float] | None:
    """TWSE MI_MARGN（上市信用交易統計，selectType=MS）→ (融資餘額(億), 融券餘額(張))。
    官方融資金額單位＝仟元 → ÷1e5 轉億；融券單位＝交易單位（張）。"""
    doc = factcheck._get_json(
        "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
        f"?date={d:%Y%m%d}&selectType=MS&response=json")
    if not isinstance(doc, dict) or doc.get("stat") != "OK":
        return None
    tables = doc.get("tables") or [doc]          # RWD 端點歷有 tables 包裝與否兩版
    fin = short = None
    for t in tables:
        for row in (t.get("data") or []):
            try:
                name = str(row[0])
                nums = [float(str(c).replace(",", "")) for c in row[1:]
                        if re.fullmatch(r"-?[\d,]+(?:\.\d+)?", str(c).strip())]
                if not nums:
                    continue
                # 欄序：買進/賣出/償還/前日餘額/今日餘額 → 今日餘額＝最後一欄
                if "融資金額" in name:
                    fin = round(nums[-1] / 1e5, 1)
                elif name.strip().startswith("融券") and "金額" not in name:
                    short = round(nums[-1])
            except Exception:
                continue
    if fin is None and short is None:
        return None
    return fin, short


def _taifex_csv(url: str, body: str) -> list[list[str]]:
    """期交所下載端點（POST → CSV，big5）→ 逐列 cells。失敗回 []。"""
    try:
        req = urllib.request.Request(
            url, data=body.encode(),
            headers={**_UA, "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            text = r.read().decode("big5", errors="replace")
        return [[c.strip().strip('"') for c in line.split(",")]
                for line in text.splitlines() if line.strip()]
    except Exception:
        return []


_ROW_DATE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")


def _cell_date(cell: str) -> str | None:
    m = _ROW_DATE.match(cell.strip())
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _taifex_tx_foreign(start: date, end: date) -> dict[str, float]:
    """外資台指期(TX)未平倉多空淨額口數（區間一次抓）→ {ISO日期: 口數（淨空為負）}。
    解析同 factcheck.taifex_tx_foreign_net：外資列取倒數第 2 個整數欄＝未平倉淨額口數。"""
    rows = _taifex_csv(
        "https://www.taifex.com.tw/cht/3/futContractsDateDown",
        f"queryStartDate={start:%Y/%m/%d}&queryEndDate={end:%Y/%m/%d}&commodityId=TXF")
    out: dict[str, float] = {}
    for cells in rows:
        if len(cells) <= 12 or not any("外資" in c and "自營" not in c for c in cells[:4]):
            continue
        iso = next((d for d in (_cell_date(c) for c in cells[:2]) if d), None)
        if not iso:
            continue
        nums = [c.replace(",", "") for c in cells
                if re.fullmatch(r"-?\d+", c.replace(",", ""))]
        if len(nums) >= 2:
            val = float(nums[-2])
            if val != 0:                                  # 0＝今日盤中未結算／無資料的哨兵，跳過
                out[iso] = val                            # （踩過：CI 於 7/23 盤中把外資淨部位讀成 0）
    return out


def _taifex_pc_ratio(start: date, end: date) -> dict[str, float]:
    """台指選擇權「買賣權未平倉量比率%」（P/C ratio，區間一次抓）→ {ISO日期: %}。
    官方 CSV 欄序：日期,賣權成交量,買權成交量,成交量比率%,賣權未平倉,買權未平倉,未平倉量比率% 。"""
    rows = _taifex_csv(
        "https://www.taifex.com.tw/cht/3/pcRatioDown",
        f"queryStartDate={start:%Y/%m/%d}&queryEndDate={end:%Y/%m/%d}")
    out: dict[str, float] = {}
    for cells in rows:
        iso = _cell_date(cells[0]) if cells else None
        if not iso or len(cells) < 7:
            continue
        try:
            val = float(cells[6].replace(",", ""))
        except ValueError:
            continue
        if val != 0:                                      # 0＝未結算，跳過（P/C 比不會為 0）
            out[iso] = val
    return out


# ── 資料層（載入／欄位級合併／存檔） ─────────────────────────────────

def load() -> dict | None:
    try:
        return json.loads(DATA_FP.read_text(encoding="utf-8"))
    except Exception:
        return None


def _merge(old: dict[str, float], new: dict[str, float]) -> dict[str, float]:
    """序列合併：新值（官方）覆蓋同日舊值（種子），整段抓不到＝保留舊序列；
    只留最近 _KEEP 筆。值為 None 一律不寫入（絕不洗空）。"""
    s = {k: v for k, v in (old or {}).items() if v is not None}
    s.update({k: v for k, v in (new or {}).items() if v is not None})
    return dict(sorted(s.items())[-_KEEP:])


def _missing_weekdays(series: dict[str, float], today: date) -> list[date]:
    """近 _BACKFILL_DAYS 內、序列缺的平日（TWSE 逐日端點補抓用；假日端點會快速回非 OK）。"""
    out = []
    for i in range(1, _BACKFILL_DAYS + 1):
        d = today - timedelta(days=i)
        if d.weekday() < 5 and d.isoformat() not in (series or {}):
            out.append(d)
    return out


def fetch() -> dict:
    """全指標抓取＋欄位級合併 → 新 doc（不落檔；落檔用 save）。每來源獨立降級。"""
    prev = load() or {}
    series: dict[str, dict] = {k: dict((prev.get("series") or {}).get(k) or {})
                               for k in ALL_KEYS}
    src: dict[str, dict] = dict(prev.get("src") or {})
    today = clock.today_tw()
    stamp = clock.stamp_tw()

    def _note(key, n, name):
        if n:
            src[key] = {"src": name, "fetched": stamp, "n": n}
        print(f"  {'✓' if n else '⚠'} {key}: {name} {'+' + str(n) + ' 筆' if n else '不可得（沿用既有序列）'}")

    # ① 全球溫度計 ← Yahoo（^TNX 為殖利率×10）
    for key, _label, sym in GLOBAL_SPECS:
        new = _yahoo_series(sym, norm=_norm_yield if key == "us10y" else None)
        series[key] = _merge(series[key], new)
        _note(key, len(new), f"yahoo:{sym}")

    # ② 三大法人買賣超（TWSE BFI82U，逐日補缺）：合計＋外資／投信／自營商分項
    n_flow = 0
    for d in _missing_weekdays(series["inst_total"], today):
        flows = _twse_inst_all(d)
        if flows:
            iso = d.isoformat()
            for key, fk in (("inst_total", "total"), ("inst_foreign", "foreign"),
                            ("inst_trust", "trust"), ("inst_dealer", "dealer")):
                if flows.get(fk) is not None:
                    series[key] = _merge(series[key], {iso: round(flows[fk], 1)})
            n_flow += 1
    _note("inst_total", n_flow, "twse:BFI82U")
    if n_flow:                                            # 分項與合計同源
        for k in ("inst_foreign", "inst_trust", "inst_dealer"):
            src[k] = src["inst_total"]

    # ③ 融資融券餘額（TWSE MI_MARGN，逐日補缺）
    n_mar = 0
    for d in _missing_weekdays(series["margin_bal"], today):
        m = _twse_margin(d)
        if m:
            iso = d.isoformat()
            fin, short = m
            if fin is not None:
                series["margin_bal"] = _merge(series["margin_bal"], {iso: fin})
            if short is not None:
                series["short_bal"] = _merge(series["short_bal"], {iso: short})
            n_mar += 1
    _note("margin_bal", n_mar, "twse:MI_MARGN")
    if n_mar:
        src["short_bal"] = src["margin_bal"]

    # ④ 外資台指期淨部位＋選擇權 P/C 比（期交所，區間一次抓）
    start = today - timedelta(days=_BACKFILL_DAYS)
    new = _taifex_tx_foreign(start, today)
    series["tx_foreign_net"] = _merge(series["tx_foreign_net"], new)
    _note("tx_foreign_net", len(new), "taifex:futContractsDate")
    new = _taifex_pc_ratio(start, today)
    series["pc_ratio"] = _merge(series["pc_ratio"], new)
    _note("pc_ratio", len(new), "taifex:pcRatio")

    return {"as_of": stamp, "series": series, "src": src}


def save(doc: dict) -> None:
    """落檔防呆：新 doc 某指標序列為空而既有落檔非空 → 不可能（_merge 保舊），
    但仍守「絕不把非空落檔洗成全空」的最後防線。"""
    old = load()
    if old and not any((doc.get("series") or {}).get(k) for k in ALL_KEYS) \
            and any((old.get("series") or {}).get(k) for k in ALL_KEYS):
        print("  ⚠ 本次全指標皆空、既有落檔非空 → 不覆寫")
        return
    DATA_FP.parent.mkdir(parents=True, exist_ok=True)
    DATA_FP.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


# ── 儀表板取數（最新值／日變化／N 日變化・累計／走勢點列） ─────────────

def _sorted_items(doc: dict | None, key: str) -> list[tuple[str, float]]:
    s = ((doc or {}).get("series") or {}).get(key) or {}
    return sorted((k, v) for k, v in s.items() if v is not None)

def latest(doc: dict | None, key: str) -> tuple[str, float] | None:
    items = _sorted_items(doc, key)
    return items[-1] if items else None


def day_change(doc: dict | None, key: str) -> float | None:
    """最新值 − 前一筆值（相鄰交易日）。序列不足 2 筆回 None。"""
    items = _sorted_items(doc, key)
    return round(items[-1][1] - items[-2][1], 4) if len(items) >= 2 else None


def change_n(doc: dict | None, key: str, n: int = 5) -> float | None:
    """最新值 − 往回第 n 筆值（近 n 個交易日變化）。史料不足回 None。"""
    items = _sorted_items(doc, key)
    return round(items[-1][1] - items[-1 - n][1], 4) if len(items) > n else None


def sum_n(doc: dict | None, key: str, n: int = 5) -> float | None:
    """最近 n 筆合計（買賣超金額「近 5 日累計」用）。不足 n 筆回 None（不以偏概全）。"""
    items = _sorted_items(doc, key)
    return round(sum(v for _, v in items[-n:]), 1) if len(items) >= n else None


def points(doc: dict | None, key: str, n: int = 30) -> list[float]:
    """走勢圖點列（最近 n 筆、依日期序）。"""
    return [v for _, v in _sorted_items(doc, key)[-n:]]


def vix_level(v: float | None) -> tuple[str, str] | None:
    """VIX 狀態標籤（中性敘述、非多空建議）→ (文字, css class)。"""
    if v is None:
        return None
    if v < 15:
        return "平靜", "calm"
    if v < 20:
        return "正常", "norm"
    if v < 30:
        return "偏高", "elev"
    return "恐慌", "panic"
