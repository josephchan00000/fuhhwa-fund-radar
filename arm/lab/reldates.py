"""月／季資料「實際拿得到的日子」（heatspec VER 12、heatspec_us VER 5、bubspec VER 5；docs/lab_signal_quality_plan.md 第 11.2 節，A-3b）。

和公布時間差（RELEASE）取晚的那一張表（heat.asof_monthly 的 late）：
  · official(name)：官方實際公布日（data/lab/heat/reldates.json.gz，scripts/fetch_reldates.py 在 CI 抓）→ {資料月: 公布日}。
      cpi／empsit＝勞工統計局新聞稿：新聞稿檔案頁（寫明資料月份）優先，其次 2000 年以前的官方公布日表（hist_*），
      都沒有的才用網際網路檔案館索引的檔名公布日（資料月＝公布月的前一個月；同一個公布月有兩則以上取最晚的，寧可晚用）。
      z1＝聯準會 Z.1：公布日往前 60 天以前最近的季底就是那一季。
  · fill(months, table, skip)：表的範圍內缺的、表開始之前的期 → 同一個月份（1～12 月；季資料＝季底月）歷年最晚的公布
      （skip＝政府停擺改期那幾期，不算）；表最後一期之後的不補（那些期在資料檔裡出現時就已經公布了，照 RELEASE）。
  · plus_days(t, n)：美國 8:30（美東）公布的資料，台股要隔天收盤才用得到（台北晚上才公布）。
  · deadline(ym, day, cal)：台股月營收「次月 day 日前申報、遇假日順延到下一個營業日」——第一個 ≥ day 的交易日的下一天才拿得到全部。
  · merge(*tables)：同一期取最晚的。
讀不到檔就是空表（＝只用公布時間差）。
"""
from __future__ import annotations

import bisect
from datetime import date, timedelta

from . import heatdata as HD

FILE = "reldates"
START_M, START_Q = "1940-01", "1940-03"            # fill 的起點（比所有月／季資料都早）


def _prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) - 1
    return f"{y - 1:04d}-12" if m == 0 else f"{y:04d}-{m:02d}"


def _quarter(rel: str) -> str:
    d = date.fromisoformat(rel) - timedelta(days=60)
    q = (d.month - 1) // 3 * 3
    return f"{d.year:04d}-{q:02d}" if q else f"{d.year - 1:04d}-12"


def official(name: str, doc: dict | None = None) -> dict[str, str]:
    """name：cpi、empsit（勞工統計局，月）、z1（聯準會，季底月）→ {資料月: 官方公布日}。"""
    D = HD.load(FILE) if doc is None else doc
    out: dict[str, str] = {}
    if name == "z1":
        for rel in D.get("z1") or []:
            q = _quarter(rel)
            if q not in out or rel < out[q]:
                out[q] = rel
        return out
    last: dict[str, str] = {}
    for rel in D.get(f"cdx_{name}") or []:          # 檔案館索引：同一個公布月有兩則以上取最晚的
        k = rel[:7]
        if k not in last or rel > last[k]:
            last[k] = rel
    for k, rel in last.items():
        out[_prev_month(k)] = rel
    for src in (f"hist_{name}", name):              # 2000 年以前的官方公布日表、新聞稿檔案頁（寫明資料月份）優先
        for ym, rel in (D.get(src) or {}).items():
            out[ym] = rel
    return out


def _mdiff(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def period_latest(table: dict[str, str], skip=()) -> dict[str, tuple[int, int]]:
    """官方表 {期 YYYY-MM: 公布日} → {期的月份 MM: (月數, 日)}：同一個月份歷年最晚的公布（月數＝公布月 − 期的月）。skip 的期不算。"""
    out: dict[str, tuple[int, int]] = {}
    for ym, rel in table.items():
        if ym in skip or not rel:
            continue
        k = (_mdiff(ym, rel[:7]), int(rel[8:10]))
        if ym[5:7] not in out or k > out[ym[5:7]]:
            out[ym[5:7]] = k
    return out


def fill(months, table: dict[str, str], skip=()) -> dict[str, str]:
    """{期: 拿得到的日子}：表裡有的照官方；表最後一期以前、表裡沒有的期照同一個月份歷年最晚的公布（period_latest）；
    表最後一期之後的不補（照 RELEASE）。"""
    from . import heat as H
    if not table:
        return {}
    per, end = period_latest(table, skip), max(table)
    out = {}
    for ym in months:
        ym = str(ym)[:7]
        if ym in table:
            out[ym] = table[ym]
        elif ym < end and ym[5:7] in per:
            out[ym] = H.avail_date(ym, per[ym[5:7]])
    return out


def months_between(a: str, b: str, step: int = 1) -> list[str]:
    """a 到 b（含）每 step 個月一期（YYYY-MM）。"""
    out, y, m = [], int(a[:4]), int(a[5:7])
    while f"{y:04d}-{m:02d}" <= b:
        out.append(f"{y:04d}-{m:02d}")
        m += step
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return out


def table(name: str, skip=(), start: str | None = None) -> dict[str, str]:
    """官方表＋沒有官方日期的期（fill）：cpi、empsit 從 START_M 起每個月，z1 從 START_Q 起每季底月。"""
    t = official(name)
    if not t:
        return {}
    step = 3 if name == "z1" else 1
    return fill(months_between(start or (START_Q if step == 3 else START_M), max(t), step), t, skip)


def plus_days(t: dict[str, str], n: int) -> dict[str, str]:
    return {k: (date.fromisoformat(v) + timedelta(days=n)).isoformat() for k, v in t.items()}


def merge(*ts: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in ts:
        for k, v in (t or {}).items():
            if v and (k not in out or v > out[k]):
                out[k] = v
    return out


def tw_calendar(extra_days: int = 70) -> list[str]:
    """台股交易日（heatcalc.calendar：證交所，沒有才用 Yahoo）＋最後一天之後 extra_days 天內的平日（扣掉證交所休市表與颱風停市）。
    申報期限要知道「下一個交易日」：假日表事先公布，不是偷看未來；落檔被截斷時也用這一份完整的日曆（截斷重建和每天建頁同一套）。"""
    from . import heatcalc as HC
    from .. import twholidays as TH
    cal, _, _ = HC.calendar({"turnover": HD.load("turnover"), "taiex": HD.load("taiex")})
    if not cal:
        return []
    d = date.fromisoformat(cal[-1])
    out = list(cal)
    for _ in range(extra_days):
        d += timedelta(days=1)
        if d.weekday() < 5 and not TH.is_closed(d):
            out.append(d.isoformat())
    return out


def deadline(ym: str, day: int, cal: list[str]) -> str | None:
    """ym 的資料在次月 day 日前申報（遇非交易日順延到下一個交易日）→ 申報期限的下一天（YYYY-MM-DD）。
    cal＝台股交易日（排好）；超出 cal 範圍就回 None（只用公布時間差）。"""
    y, m = int(ym[:4]), int(ym[5:7]) + 1
    if m == 13:
        y, m = y + 1, 1
    d0 = f"{y:04d}-{m:02d}-{day:02d}"
    i = bisect.bisect_left(cal, d0)
    if i >= len(cal) or not cal or d0 < cal[0]:
        return None
    return (date.fromisoformat(cal[i]) + timedelta(days=1)).isoformat()


def deadlines(months, day: int, cal: list[str]) -> dict[str, str]:
    out = {}
    for ym in months:
        d = deadline(ym, day, cal)
        if d:
            out[ym] = d
    return out
