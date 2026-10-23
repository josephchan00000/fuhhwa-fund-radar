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
颱風停止交易不在年度表上（2026-10-23 薔琵颱風踩坑）→ 查證過的日子寫進 `ADHOC`，任何呼叫端都算休市。
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

# **暫代層**：證交所隔年表公告前（2026 年表是 2025-10-29 才公告），先放行政院人事行政總處
# 已核定的「政府行政機關辦公日曆表」平日放假日。語意是「**已知必休**」——政府放假日證交所
# 一定休市，但證交所另有自己加的休市日（春節前「無交易、僅辦理結算交割」那兩天，2026 是
# 2/12、2/13），辦公日曆上不會有。所以暫代年份的其他平日一律回「未知」（is_closed→None），
# 交給呼叫端的後備判斷——**不把猜測寫成官方**。證交所表一到（CI 落檔或補進 SEED）即整年取代；
# `tests/test_twholidays.py` 守著：隔年 12/1 前還沒換成證交所表 → 紅。
# 2027（116 年）：人事行政總處 2026-05-21 核定，全年放假 121 天、無補行上班日；
# 週末 104 天＋平日 17 天＝121（自洽）。來源：dgpa.gov.tw 新聞稿（pid=12983）、中央社 2026-05-21。
PROVISIONAL: dict[int, dict[str, str]] = {
    2027: {
        "2027-01-01": "開國紀念日",
        "2027-02-04": "除夕前一日",
        "2027-02-05": "除夕",
        "2027-02-08": "春節",
        "2027-02-09": "春節補假",
        "2027-02-10": "春節補假",
        "2027-03-01": "和平紀念日補假",
        "2027-04-05": "清明節",
        "2027-04-06": "兒童節補假",
        "2027-04-30": "勞動節補假",
        "2027-06-09": "端午節",
        "2027-09-15": "中秋節",
        "2027-09-28": "孔子誕辰紀念日暨教師節",
        "2027-10-11": "國慶日補假",
        "2027-10-25": "臺灣光復暨金門古寧頭大捷紀念日",
        "2027-12-24": "行憲紀念日補假",
        "2027-12-31": "開國紀念日補假（2028-01-01 逢週六）",
    },
}

# **臨時休市**（颱風停止交易）：證交所年度表（holidaySchedule）只列事先排定的假日，颱風停止交易**不會**
# 出現在表上——2026-10-23 薔琵颱風當天實測：12:06 抓的官方表沒有這一天，看門狗把休市當交易日、盤後班當掉。
# 這裡逐筆寫入查證過的日子（證交所／櫃買公告，兩家以上主流媒體）；任何年份、任何呼叫端都一律休市。
# 還沒補進來的颱風日，看門狗與行事曆閘門另認市況段明寫「M/D 因颱風休市」（typhoon_said）。
ADHOC: dict[str, str] = {
    # 雙北停止上班，證交所、櫃買、期交所、外匯同步休市；經濟日報／工商時報／鉅亨 2026-07-09～10；
    # 官方收盤表該日查無（data/lab/mkt_nodata.json）
    "2026-07-10": "巴威颱風停止交易",
    # 證交所 10/22 公告全日休市（櫃買、期貨、外匯同步）；經濟日報 money.udn.com/money/story/5607/9832123、
    # 工商時報 ctee.com.tw/news/20261022702278-430201；10/26 光復節補假，連休到 10/27
    "2026-10-23": "薔琵颱風停止交易",
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


def provisional(years: dict | None = None) -> dict[int, dict[str, str]]:
    """證交所表尚未涵蓋、只有暫代層（人事行政總處辦公日曆）的年份。"""
    years = load() if years is None else years
    return {y: v for y, v in PROVISIONAL.items() if y not in years}


def is_closed(d: date, years: dict | None = None) -> bool | None:
    """證交所表涵蓋該年 → True／False（週末一律 True）；只有暫代層 → 辦公日曆放假日 True、
    其餘平日 None（證交所可能另加休市日，不猜）；都沒有 → None。None＝呼叫端自行退回後備判斷。
    臨時休市（ADHOC，颱風）任何情況都回 True。"""
    if d.isoformat() in ADHOC:
        return True
    years = load() if years is None else years
    if d.weekday() >= 5 and (d.year in years or d.year in PROVISIONAL):
        return True
    if d.year in years:
        return d.isoformat() in years[d.year]
    if d.isoformat() in PROVISIONAL.get(d.year, {}):
        return True
    return None


def closed_days(years: dict | None = None, with_provisional: bool = False) -> dict[date, str]:
    years = load() if years is None else years
    out = {date.fromisoformat(k): n for v in years.values() for k, n in v.items()}
    if with_provisional:
        out.update({date.fromisoformat(k): n for v in provisional(years).values() for k, n in v.items()})
    out.update({date.fromisoformat(k): n for k, n in ADHOC.items()})
    return out


_TYPHOON = re.compile(r"颱風")


def typhoon_said(clause: str | None, d: date) -> bool:
    """行事曆市況段的台股欄明寫 d 那天因颱風休市（例「10/23 因颱風休市」）。颱風停止交易不在年度表上，
    還沒補進 ADHOC 之前看門狗與行事曆閘門用它；**只認颱風**——其他理由的休市文字照舊以官方表為準。"""
    s = clause or ""
    if "休市" not in s or not _TYPHOON.search(s):
        return False
    return (d.month, d.day) in {(int(a), int(b)) for a, b in re.findall(r"(\d{1,2})/(\d{1,2})", s)}


def covers(d: date) -> bool:
    """證交所表（種子或 CI 落檔）完整涵蓋該年。"""
    return d.year in load()


def covers_partly(d: date) -> bool:
    """至少有暫代層（只知道一定休市的日子）。"""
    return covers(d) or d.year in PROVISIONAL


def upcoming(today: date, days: int = 10) -> list[tuple[date, str, bool]]:
    """today 起 days 天內的休市平日（提示包用）：(日期, 名稱, 是否為證交所表)。
    暫代層的日子以 False 標示，呼叫端要註明「證交所年度表未公告」。"""
    years = load()
    off = closed_days(years)
    prov = closed_days(years, with_provisional=True)
    return sorted((d, n, d in off) for d, n in prov.items()
                  if today <= d < today + timedelta(days=days))


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
        elif y in PROVISIONAL:                   # 暫代層被取代：印出證交所自己加的休市日供核對
            log(f"[台股休市表] {y} 證交所表已公告、取代人事行政總處暫代層——證交所另加："
                f"{sorted(set(v) - set(PROVISIONAL[y]))}；辦公日曆有而證交所沒有："
                f"{sorted(set(PROVISIONAL[y]) - set(v))}")
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
