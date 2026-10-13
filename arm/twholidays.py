"""台股官方休市表——「今天台股有沒有開」的唯一權威（證交所公告）。

2026-10-13 使用者：「你抓資料要確認資料的可信度還有穩定度」。盤查發現台股休市日原本是從
**子代理每天寫的行事曆「市況」段文字**推出來的，而且被系統拿去做決定：
  · `scripts/check_afterhours_fresh.py` 的 `is_trading_day()`——盤後完整性看門狗據以判斷
    「今天該不該有三大法人／融資融券」：漏寫休市＝當天誤報紅燈＋推播；誤寫休市＝缺資料靜默放行；
  · `fund_dashboard._tw_closed_days()`——NAV／ETF 持股等「以交易日計」的鮮度判定。
一個由搜尋摘要寫成、每天重寫的文字段在驅動控制面，是本專案「靜默失敗」的典型溫床。

現在改為：**證交所官方表優先**（`openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule`，
年度公告；CI 每日抓入 `data/tw_holidays.json`），行事曆文字只在官方表未涵蓋的年份當後備。
容器 proxy 擋 twse——抓取只在 CI；為了不必等 CI 首輪，2026 年以兩來源核對過的種子 `SEED`
內建（官方表抓到後以官方為準，兩者不一致時 CI 日誌會印出差異）。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "tw_holidays.json"
API = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
MIN_ROWS_PER_YEAR = 5          # 官方表一年至少有這麼多個平日休市才採信（防半截回應洗掉種子）

# 證交所「115 年有價證券集中交易市場開（休）市日期」中**無交易的平日**（含「無交易、僅辦理
# 結算交割」日）。週末不列（本來就不交易）；「最後交易日／開始交易日」是交易日、不列。
SEED: dict[int, dict[str, str]] = {
    2026: {
        "2026-01-01": "開國紀念日",
        "2026-02-12": "農曆春節前（無交易）",
        "2026-02-13": "農曆春節前（無交易）",
        "2026-02-16": "農曆除夕",
        "2026-02-17": "春節",
        "2026-02-18": "春節",
        "2026-02-19": "春節",
        "2026-02-20": "春節補假",
        "2026-02-27": "和平紀念日補假",
        "2026-04-03": "兒童節補假",
        "2026-04-06": "清明節補假",
        "2026-05-01": "勞動節",
        "2026-06-19": "端午節",
        "2026-09-25": "中秋節",
        "2026-09-28": "孔子誕辰紀念日暨教師節",
        "2026-10-09": "國慶日補假",
        "2026-10-26": "臺灣光復暨金門古寧頭大捷紀念日補假",
        "2026-12-25": "行憲紀念日",
    },
}

_OPEN_MARK = re.compile(r"開始交易|最後交易")      # 這兩種列是「交易日」的註記、不是休市
_NO_TRADE = re.compile(r"無交易")


def _to_date(v) -> date | None:
    """官方表日期欄可能是民國緊湊式 1150101、民國斜線 115/01/01、西元 2026-01-01／20260101。"""
    s = str(v or "").strip()
    try:
        if re.fullmatch(r"\d{7}", s):
            return date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:7]))
        if m := re.fullmatch(r"(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})", s):
            return date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))
        if m := re.fullmatch(r"(\d{4})[/-]?(\d{1,2})[/-]?(\d{1,2})", s):
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return None


def parse_api(rows: list) -> dict[str, str]:
    """官方回應 → {ISO 日期: 名稱}（只留無交易的平日）。欄名不寫死：日期取第一個解析得了的值，
    名稱／說明取其餘文字欄——證交所 OpenAPI 欄名改過不只一次（Explanation／Description）。"""
    out: dict[str, str] = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        d = next((x for x in (_to_date(v) for v in r.values()) if x), None)
        if not d or d.weekday() >= 5:
            continue
        texts = [str(v) for v in r.values() if isinstance(v, str) and not _to_date(v)]
        blob = "".join(texts)
        if _OPEN_MARK.search(blob) and not _NO_TRADE.search(blob):
            continue
        name = str(r.get("Name") or r.get("name") or (texts[0] if texts else "休市")).strip()
        out[d.isoformat()] = name
    return out


def _read_file() -> dict:
    try:
        doc = json.loads(PATH.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def load() -> dict[int, dict[str, str]]:
    """{年: {ISO: 名稱}}——每年取官方落檔（CI 抓的）優先，落檔沒有的年份用內建種子。"""
    years: dict[int, dict[str, str]] = {y: dict(v) for y, v in SEED.items()}
    for y, v in ((_read_file().get("years") or {}).items()):
        if isinstance(v, dict) and len(v) >= MIN_ROWS_PER_YEAR:
            years[int(y)] = dict(v)
    return years


def is_closed(d: date, years: dict | None = None) -> bool | None:
    """官方表涵蓋該年 → True／False（週末一律 True）；未涵蓋 → None（呼叫端自行退回後備判斷）。"""
    years = load() if years is None else years
    if d.year not in years:
        return None
    return d.weekday() >= 5 or d.isoformat() in years[d.year]


def closed_days(years: dict | None = None) -> dict[date, str]:
    years = load() if years is None else years
    return {date.fromisoformat(k): n for v in years.values() for k, n in v.items()}


def covers(d: date) -> bool:
    return d.year in load()


def upcoming(today: date, days: int = 10) -> list[tuple[date, str]]:
    """today 起 days 天內的官方休市平日（提示包用）。"""
    cd = closed_days()
    return sorted((d, n) for d, n in cd.items() if today <= d < today + timedelta(days=days))


def fetch_and_save(log=print) -> bool:
    """CI 用：抓證交所官方表、依年份合併進落檔。抓不到／解析過少＝不覆寫（fail-open）；
    與內建種子不一致時印差異（以官方為準，種子日後再修）。回傳是否寫檔。"""
    from .http import get_json
    try:
        rows = get_json(API, retries=1, timeout=12)
    except Exception as e:                       # 不吞原因：被擋還是格式變了要看得出來
        log(f"[台股休市表] 官方表抓取失敗、沿用既有：{e}")
        return False
    got = parse_api(rows)
    by_year: dict[int, dict[str, str]] = {}
    for k, n in got.items():
        by_year.setdefault(int(k[:4]), {})[k] = n
    doc = _read_file()
    years = dict(doc.get("years") or {})
    wrote = False
    for y, v in sorted(by_year.items()):
        if len(v) < MIN_ROWS_PER_YEAR:
            log(f"[台股休市表] {y} 年只解析出 {len(v)} 天、不採信（可能是半截回應或版式改了）")
            continue
        if y in SEED and set(SEED[y]) != set(v):
            log(f"[台股休市表] ⚠ {y} 官方表與內建種子不一致——僅官方：{sorted(set(v) - set(SEED[y]))}"
                f"；僅種子：{sorted(set(SEED[y]) - set(v))}（以官方為準）")
        years[str(y)] = dict(sorted(v.items()))
        wrote = True
    if not wrote:
        log(f"[台股休市表] 官方表解析 0 個可用年份（共 {len(got)} 筆）、沿用既有")
        return False
    from . import clock
    PATH.write_text(json.dumps({"as_of": clock.stamp_tw(), "source": API, "years": years},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"[台股休市表] 已更新：{', '.join(f'{y} 年 {len(v)} 天' for y, v in sorted(years.items()))}")
    return True
