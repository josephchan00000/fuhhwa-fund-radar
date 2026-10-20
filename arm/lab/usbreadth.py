"""美股漲跌家數（大神策略第三段，docs/lab_expert_plan.md 第 10 節）：S&P 500 成分股自算。

成分股：fja05680/sp500 的 sp500_ticker_start_end.csv（1996 起每一檔在指數裡的期間，代號是當時的代號）。
價格：Yahoo 日線（收盤與成交量已還原分割、沒還原股利）。已下市、改名的代號 Yahoo 多半沒有，所以早年只算得到
     現在還在交易的那些成分股（存活偏誤；有資料的檔數另外記，頁面寫明）。
每天記：上漲／下跌／平盤家數、上漲股與下跌股的成交金額（收盤 × 成交量，分割前後不變）、上漲點數與下跌點數
     （還原成當時的價格：收盤 × 之後的分割倍數）、有資料的成分股數、當天的成分股數。
之後每天：Yahoo 報價（v7，一次 150 檔）取現在的成分股（維基百科清單）當天的漲跌（盤中不收）。

  HD "us_breadth"：{日期: [上漲, 下跌, 平盤, 上漲成交金額, 下跌成交金額, 上漲點數, 下跌點數, 有資料檔數, 成分股數]}
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.parse
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from . import heatdata as HD
from .market import log

NAME = "us_breadth"
SPANS_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
START = "1995-12-01"                 # 成分股名單 1996-01-02 起；前一個交易日的收盤要有
MAX_GAP_DAYS = 7                     # 和前一筆收盤相隔超過一週（停牌、資料缺）就不算那一天
COLS = ("adv", "dec", "unch", "upval", "dnval", "uppts", "dnpts", "n", "members")


def ysym(s: str) -> str:
    return s.strip().upper().replace(".", "-").replace("/", "-")


def parse_spans(text: str) -> list[tuple[str, str, str | None]]:
    """sp500_ticker_start_end.csv → [(Yahoo 代號, 起日, 迄日或 None)]（迄日＝離開指數那天，當天不算）。"""
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        t, a, z = (r.get("ticker") or "").strip(), (r.get("start_date") or "").strip(), (r.get("end_date") or "").strip()
        if t and a:
            out.append((ysym(t), a[:10], z[:10] or None))
    return out


def parse_chart(doc: dict) -> dict[str, tuple[float, float, float]]:
    """chart API（含 events=split）→ {美東日期: (收盤, 成交量, 分割倍數)}；分割倍數＝這一天之後所有分割的乘積
    （當時的價格＝收盤 × 倍數）。只收收盤有值的日子。"""
    res = (((doc or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return {}
    off = int((res.get("meta") or {}).get("gmtoffset") or -18000)
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    cl, vo = q.get("close") or [], q.get("volume") or []
    sp = []
    for e in ((res.get("events") or {}).get("splits") or {}).values():
        try:
            r = float(e["numerator"]) / float(e["denominator"])
        except Exception:                                     # noqa: BLE001
            continue
        if r > 0:
            sp.append((datetime.fromtimestamp(int(e["date"]) + off, timezone.utc).date().isoformat(), r))
    sp.sort()
    out: dict[str, tuple[float, float, float]] = {}
    for i, t in enumerate(ts):
        c = cl[i] if i < len(cl) else None
        if c is None or c <= 0:
            continue
        d = datetime.fromtimestamp(int(t) + off, timezone.utc).date().isoformat()
        f = 1.0
        for sd, r in sp:
            if sd > d:
                f *= r
        v = vo[i] if i < len(vo) else None
        out[d] = (float(c), float(v or 0.0), f)
    return out


def aggregate(spans: list[tuple[str, str, str | None]], hist: dict[str, dict], cal: list[str]) -> dict[str, list]:
    """每個交易日（cal）的漲跌家數等（欄位見 COLS）。一檔股票只在成分股期間、而且前一個收盤在 MAX_GAP_DAYS 天內才算。"""
    idx = {d: i for i, d in enumerate(cal)}
    acc = [[0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0] for _ in cal]
    for sym, a, z in spans:
        for i in range(bisect_left(cal, a), bisect_left(cal, z) if z else len(cal)):     # 離開那天不算
            acc[i][8] += 1
        h = hist.get(sym)
        if not h:
            continue
        ds = sorted(h)
        for k in range(1, len(ds)):
            d, p = ds[k], ds[k - 1]
            i = idx.get(d)
            if i is None or d < a or (z and d >= z):
                continue
            if (date.fromisoformat(d) - date.fromisoformat(p)).days > MAX_GAP_DAYS:
                continue
            c1, v1, f1 = h[d]
            c0 = h[p][0]
            row = acc[i]
            row[7] += 1
            val = c1 * v1
            pts = (c1 - c0) * f1
            if c1 > c0:
                row[0] += 1
                row[3] += val
                row[5] += pts
            elif c1 < c0:
                row[1] += 1
                row[4] += val
                row[6] -= pts
            else:
                row[2] += 1
    return {d: [r[0], r[1], r[2], round(r[3]), round(r[4]), round(r[5], 2), round(r[6], 2), r[7], r[8]]
            for d, r in zip(cal, acc) if r[7]}


# ── 抓取（只在 CI 跑；本容器擋 Yahoo）────────────────────────────────────────

def _get(url: str, timeout: int = 60) -> bytes:
    from .heatfetch import _get as hget
    return hget(url, timeout=timeout)


def fetch_hist(sym: str) -> tuple[str, dict]:
    p1 = int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?period1={p1}&period2={int(time.time())}&interval=1d&events=split")
    for k in range(3):
        try:
            return sym, parse_chart(json.loads(_get(url, timeout=60).decode("utf-8")))
        except Exception as e:                                # noqa: BLE001
            s = str(e)
            if "404" in s or "Not Found" in s:
                return sym, {}
            if "429" in s:
                time.sleep(5 * (k + 1))
                continue
            return sym, {}
    return sym, {}


def backfill(workers: int = 4) -> int:
    """1996 起整段重算（約 1,200 個 Yahoo 請求、幾分鐘）。回傳改動的天數。"""
    t0 = time.time()
    spans = parse_spans(_get(SPANS_URL, timeout=60).decode("utf-8"))
    syms = sorted({s for s, _, _ in spans})
    hist: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for sym, h in ex.map(fetch_hist, syms):
            if h:
                hist[sym] = h
    cal = sorted(d for d in HD.load("us_px_spx") if d >= "1996-01-02")
    new = aggregate(spans, hist, cal)
    last = max(cal) if cal else None
    if last and last not in new:
        log(f"[breadth-us] {last} 沒有算到（Yahoo 可能還沒收盤）")
    log(f"[breadth-us] 成分股 {len(syms)} 檔、Yahoo 有資料 {len(hist)} 檔、{len(new)} 天（{time.time() - t0:.0f}s）")
    old = HD.load(NAME)
    n = sum(1 for k, v in new.items() if old.get(k) != v)
    if n and len(new) >= 0.9 * len(old):
        HD.save(NAME, "sp500+yahoo", {**old, **new})
    return n


def parse_quotes(doc: dict) -> dict[str, dict]:
    """v7 報價 → {代號: {"t": 美東日期, "chg": 漲跌, "px": 價格, "vol": 成交量, "st": marketState}}。"""
    out = {}
    for q in ((doc.get("quoteResponse") or {}).get("result") or []):
        s, t = q.get("symbol"), q.get("regularMarketTime")
        if not s or t is None or q.get("regularMarketChange") is None or not q.get("regularMarketPrice"):
            continue
        off = int((q.get("gmtOffSetMilliseconds") or -18000000) / 1000)
        out[s] = {"t": datetime.fromtimestamp(int(t) + off, timezone.utc).date().isoformat(),
                  "chg": float(q["regularMarketChange"]), "px": float(q["regularMarketPrice"]),
                  "vol": float(q.get("regularMarketVolume") or 0.0), "st": str(q.get("marketState") or "")}
    return out


def day_row(quotes: dict[str, dict], members: list[str], day: str) -> list | None:
    """現在的成分股當天的一列（欄位同 COLS）。只算報價時間是 day 的；盤中（REGULAR）一律不收。"""
    adv = dec = unch = n = 0
    upv = dnv = upp = dnp = 0.0
    for s in members:
        q = quotes.get(s)
        if not q or q["t"] != day or q["st"] == "REGULAR":
            continue
        n += 1
        val = q["px"] * q["vol"]
        if q["chg"] > 0:
            adv, upv, upp = adv + 1, upv + val, upp + q["chg"]
        elif q["chg"] < 0:
            dec, dnv, dnp = dec + 1, dnv + val, dnp - q["chg"]
        else:
            unch += 1
    if n < 0.9 * len(members):
        return None
    return [adv, dec, unch, round(upv), round(dnv), round(upp, 2), round(dnp, 2), n, len(members)]


def members_now() -> list[str]:
    from . import fwdfetch as F
    return list(((F.load_us().get("const") or {}).get("spx")) or [])


def daily() -> int:
    """最近一個美股交易日（us_px_spx 已經有、us_breadth 還沒有）用 v7 報價補一列。回傳 0 或 1。"""
    cal = HD.load("us_px_spx")
    have = HD.load(NAME)
    if not cal or not have:
        return 0
    last = max(cal)
    if last <= max(have):
        return 0
    mem = members_now()
    if len(mem) < 400:
        log(f"[breadth-us] 成分股只有 {len(mem)} 檔，跳過")
        return 0
    from . import fcst
    Y = fcst._Yahoo()
    if not Y.login():
        log("[breadth-us] 拿不到 crumb")
        return 0
    quotes: dict = {}
    crumb = urllib.parse.quote(Y.crumb or "")
    for i in range(0, len(mem), 150):
        chunk = ",".join(urllib.parse.quote(s) for s in mem[i:i + 150])
        st, b = Y.get(f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={chunk}&crumb={crumb}", timeout=60)
        if st == 200:
            try:
                quotes.update(parse_quotes(json.loads(b.decode("utf-8"))))
            except Exception:                                 # noqa: BLE001
                pass
    row = day_row(quotes, mem, last)
    if not row:
        log(f"[breadth-us] {last} 報價不齊（{len(quotes)}／{len(mem)}），跳過")
        return 0
    HD.save(NAME, "sp500+yahoo", {**have, last: row})
    return 1


def ratio_arrays(cal: list[str]) -> tuple[list, list, list, list, list, list]:
    """對到日曆的 (上漲, 下跌, 上漲成交金額, 下跌成交金額, 上漲點數, 下跌點數)；沒有＝nan。"""
    b = HD.load(NAME)
    nan = float("nan")
    cols = [[], [], [], [], [], []]
    for d in cal:
        r = b.get(d)
        vals = (r[0], r[1], r[3], r[4], r[5], r[6]) if r else (nan,) * 6
        for j in range(6):
            cols[j].append(float(vals[j]))
    return tuple(cols)


def gap_days(cal: list[str], b: dict) -> list[str]:
    """日曆上 us_breadth 缺的日子（給頁面寫資料缺口；最早一天以前不算）。"""
    if not b:
        return []
    a = min(b)
    return [d for d in cal if d >= a and d not in b]
