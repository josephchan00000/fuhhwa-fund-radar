"""選擇權回測 O2 的事件日（docs/lab_txo_plan.md 第 16、18 節；txospec VER 1 的 O2_EVENTS）。

CPI 公布日已經有（data/lab/heat/reldates.json.gz 的 cpi，勞工統計局官方日期 2002 起）；這裡補 FOMC 聲明日：
  · 抓：聯準會網站的會議行程（今年與前幾年 fomccalendars.htm；更早的每年一頁 fomchistorical{年}.htm），原始網頁存進資料分支
    events/fomc/{頁名}.json.gz（{"url", "html"}），之後在容器裡解析、不必重抓。只在 CI 跑（fetch_txo.py --mode fomc）。
  · 解析：只收「事先排定」的會議（標題寫 Meeting、不是 Conference Call、沒有 unscheduled）——臨時會議前一天收盤時還不知道，
    不能事先進場（第 18 節，看任何成績之前寫定）。聲明日＝會議最後一天（1994 年起排定會議結束當天公布聲明）。
    同時列出頁面上所有聲明連結的日期（monetaryYYYYMMDDa），兩邊對不上的印出來檢查。
"""
from __future__ import annotations

import html as H
import re
from datetime import date
from pathlib import Path

FED = "https://www.federalreserve.gov/monetarypolicy/"
CAL = "fomccalendars.htm"
FIRST_YEAR = 2002
MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"), 1)}
_MON = "|".join(m.capitalize() for m in MONTHS)
_ABBR = {m[:3]: i for m, i in MONTHS.items()}


def log(*a) -> None:
    print("[fomc]", *a, flush=True)


def page_names(today: date) -> list[str]:
    return [CAL] + [f"fomchistorical{y}.htm" for y in range(FIRST_YEAR, today.year)]


def update_pages(root: Path, today: date) -> int:
    """抓行程頁存進資料分支（已存的歷史頁不重抓；行程頁每次重抓）。回傳寫了幾頁。"""
    from ..http import get_bytes
    from . import txodata as T
    from .heatfetch import BROWSER
    hdr = {**BROWSER, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"}
    n = 0
    for name in page_names(today):
        rel = f"events/fomc/{name}.json.gz"
        if name != CAL and (root / rel).exists():
            continue
        try:
            txt = get_bytes(FED + name, retries=2, timeout=60, use_cache=False, headers=hdr).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 —— 一頁失敗就跳過（太新的年份還沒有歷史頁）
            log(f"{name}：{type(e).__name__}: {str(e)[:100]}")
            continue
        if "FOMC" not in txt and "Federal Open Market Committee" not in txt:
            log(f"{name}：內容不像行程頁（{len(txt)} 字），不存")
            continue
        if T.write(root, rel, {"url": FED + name, "html": txt}):
            n += 1
        log(f"{name}：{len(txt):,} 字")
    return n


def load_pages(root: Path) -> dict[str, str]:
    from . import txodata as T
    out = {}
    for p in sorted((root / "events/fomc").glob("*.json.gz")):
        doc = T.read(root, f"events/fomc/{p.name}")
        if doc and doc.get("html"):
            out[p.name[:-len(".json.gz")]] = doc["html"]
    return out


def _text(chunk: str) -> str:
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", chunk))).strip()


def _mon(s: str) -> int | None:
    s = s.strip().lower().rstrip(".")
    return MONTHS.get(s) or _ABBR.get(s[:3])


def stmt_links(page: str) -> list[str]:
    """頁面上的聲明連結 → 日期（2006 年起 monetaryYYYYMMDDa.htm；更早 boarddocs/press/monetary/YYYY/YYYYMMDD/）。"""
    ds = set(re.findall(r"monetary(\d{8})a\.htm", page)) | set(re.findall(r"boarddocs/press/monetary/\d{4}/(\d{8})/", page))
    return sorted(f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in ds)


_HIST = re.compile(rf"({_MON})(?:/({_MON}))?\s+(\d{{1,2}})(?:\s*-\s*(?:({_MON})\s+)?(\d{{1,2}}))?\s+"
                   r"(Meeting|Conference Call)(\s*\(unscheduled\))?(?:\s*-\s*(\d{4}))?", re.I)


def parse_hist(page: str, year: int) -> list[dict]:
    """歷史頁（fomchistorical{年}.htm）：標題「January 29-30 Meeting - 2008」「April 30-May 1 Meeting」「March 10 Conference Call」。"""
    out, seen = [], set()
    for m in _HIST.finditer(_text(page)):
        m1, m1b, d1, m2, d2, kind, unsch, yy = m.groups()
        y = int(yy) if yy else year
        if y != year:
            continue
        mon = _mon(m2 or m1b or m1)
        day = int(d2 or d1)
        try:
            d = date(y, mon, day).isoformat()
        except (TypeError, ValueError):
            continue
        sched = kind.lower() == "meeting" and not unsch
        if (d, sched) not in seen:
            seen.add((d, sched))
            out.append({"d": d, "sched": sched, "how": _text(m.group(0))})
    return out


def parse_cal(page: str) -> list[dict]:
    """行程頁（fomccalendars.htm）：每年一塊「2025 FOMC Meetings」，每次會議一列 月份（January、Apr/May）＋日期（28-29、30-1*、
    15 (unscheduled)、notation vote）。"""
    out = []
    blocks = re.split(r"(\d{4})\s+FOMC\s+Meetings", page)
    for i in range(1, len(blocks) - 1, 2):
        y = int(blocks[i])
        body = blocks[i + 1]
        months = re.findall(r'fomc-meeting__month[^>]*>(.*?)</div>', body, re.S)
        dates = re.findall(r'fomc-meeting__date[^>]*>(.*?)</div>', body, re.S)
        for mt, dt in zip(months, dates):
            mt, dt = _text(mt), _text(dt)
            ms = [x for x in re.split(r"[/\-\s]+", mt) if x]
            ds = re.findall(r"\d{1,2}", dt.split("(")[0])
            if not ms or not ds:
                continue
            # 跨月（Apr/May 30-1）：最後一天在後一個月；其他情形在第一個月
            mon = _mon(ms[-1] if len(ms) > 1 and len(ds) > 1 and int(ds[-1]) < int(ds[0]) else ms[0])
            try:
                d = date(y, mon, int(ds[-1])).isoformat()
            except (TypeError, ValueError):
                continue
            low = dt.lower()
            sched = "unscheduled" not in low and "notation" not in low and "conference" not in low
            out.append({"d": d, "sched": sched, "how": f"{mt} {dt}"})
    return out


def parse_all(pages: dict[str, str]) -> dict:
    """所有頁 → {"sched": [排定會議的聲明日], "other": [臨時會議／電話會議], "stmt": [聲明連結日期], "by_year": {年: 排定場數}}。"""
    rows = []
    stmt = set()
    for name, page in pages.items():
        m = re.match(r"fomchistorical(\d{4})\.htm", name)
        rows += parse_hist(page, int(m.group(1))) if m else parse_cal(page)
        stmt |= set(stmt_links(page))
    sched = sorted({r["d"] for r in rows if r["sched"]})
    other = sorted({r["d"] for r in rows if not r["sched"]} - set(sched))
    by_year: dict[str, int] = {}
    for d in sched:
        by_year[d[:4]] = by_year.get(d[:4], 0) + 1
    return {"sched": sched, "other": other, "stmt": sorted(stmt), "by_year": by_year,
            "sched_no_stmt": [d for d in sched if d not in stmt and d >= f"{FIRST_YEAR}"]}


def summary(res: dict) -> None:
    log("每年排定會議場數：", res["by_year"])
    log(f"排定 {len(res['sched'])}、臨時 {len(res['other'])}、聲明連結 {len(res['stmt'])}")
    log("臨時會議：", res["other"][:40])
    log("排定但頁面沒有同一天的聲明連結：", res["sched_no_stmt"][:40])
