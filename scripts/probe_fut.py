#!/usr/bin/env python3
"""台指期早盤策略（股票期貨人生）的資料探針（docs/lab_fut_plan.md；只印診斷、不寫檔，CI 跑）：

  期交所：近 30 個交易日每筆成交（CSV zip）——清單頁有哪幾天、一天多大、欄位、台指期近月幾筆、
          08:45～09:05 的成交長怎樣、夜盤怎麼標日期；更早的日子拿不拿得到。
          每日行情（futDataDown）能回到哪一年。
  證交所：每 5 秒指數（MI_5MINS_INDEX）能回到哪一年、09:00:00 那一列是什麼；每日加權指數開高低收。
  即時報價：證交所 MIS（加權指數、權值股）、期交所 MIS（台指期）回應的欄位（盤後跑只看得到格式）。
  FinMind：期貨逐筆、期貨日行情，免費會員拿不拿得到。

  python3 scripts/probe_fut.py           # 全部（盤後跑）
  python3 scripts/probe_fut.py --pre     # 只抓即時報價：每 5 秒一次，到台北 09:02（盤前試撮）
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.http import _CTX, get_bytes  # noqa: E402
from arm.lab.market import post_bytes  # noqa: E402

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TFX = "https://www.taifex.com.tw"
FM = "https://api.finmindtrade.com/api/v4/data?dataset={ds}{did}&start_date={a}{z}"


def p(*a) -> None:
    print("[fut]", *a, flush=True)


def get(url: str, timeout: int = 60) -> tuple[bytes | None, float, str]:
    t0 = time.time()
    try:
        b = get_bytes(url, retries=1, timeout=timeout, use_cache=False, headers=BROWSER)
        return b, time.time() - t0, "ok"
    except Exception as e:                                    # noqa: BLE001
        return None, time.time() - t0, f"{type(e).__name__}: {str(e)[:200]}"


def post_json(url: str, body: dict, timeout: int = 30) -> tuple[bytes | None, float, str]:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
            **BROWSER, "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://mis.taifex.com.tw", "Referer": "https://mis.taifex.com.tw/futures/"})
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return r.read(), time.time() - t0, f"HTTP {r.status}"
    except Exception as e:                                    # noqa: BLE001
        return None, time.time() - t0, f"{type(e).__name__}: {str(e)[:200]}"


def tw_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=8)


# ── 期交所：近 30 個交易日每筆成交 ──────────────────────────────────────────

def tick_dates() -> list[date]:
    out: set[date] = set()
    for path in ("/cht/3/futPrevious30DaysSalesData", "/cht/3/dlFutPrevious30DaysSalesData"):
        b, dt, st = get(TFX + path, timeout=60)
        if b is None:
            p(f"清單頁 {path} ✗ {st}（{dt:.1f}s）")
            continue
        txt = b.decode("utf-8", "replace")
        ds = re.findall(r"Daily_(\d{4})_(\d{2})_(\d{2})\.zip", txt)
        csvs = len(re.findall(r"DailydownloadCSV", txt))
        p(f"清單頁 {path}：{len(b) // 1024} KB、{dt:.1f}s、檔名 {len(ds)} 個、CSV 連結 {csvs} 個")
        if not ds:
            p("  開頭：", re.sub(r"\s+", " ", txt[:400]))
            links = sorted(set(re.findall(r'href="([^"]+\.zip)"', txt)))[:10]
            p("  .zip 連結：", links)
        for y, m, d in ds:
            out.add(date(int(y), int(m), int(d)))
    ds = sorted(out)
    if ds:
        p(f"可下載的日子 {len(ds)} 天：{ds[0]}～{ds[-1]}")
    return ds


def tick_url(d: date, kind: str = "csv") -> str:
    if kind == "csv":
        return f"{TFX}/file/taifex/Dailydownload/DailydownloadCSV/Daily_{d:%Y_%m_%d}.zip"
    return f"{TFX}/file/taifex/Dailydownload/Daily_{d:%Y_%m_%d}.zip"


def read_zip(b: bytes) -> tuple[str, str] | None:
    try:
        z = zipfile.ZipFile(io.BytesIO(b))
    except zipfile.BadZipFile:
        return None
    names = z.namelist()
    p(f"  zip 內 {len(names)} 個檔：{names[:5]}")
    raw = z.read(names[0])
    for enc in ("cp950", "big5", "utf-8-sig"):
        try:
            return names[0], raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return names[0], raw.decode("cp950", "replace")


def sec(hms: str) -> int:
    hms = hms.strip().zfill(6)
    return int(hms[:2]) * 3600 + int(hms[2:4]) * 60 + int(hms[4:6])


def tick_day(d: date) -> None:
    url = tick_url(d)
    b, dt, st = get(url, timeout=180)
    if b is None:
        p(f"每筆成交 {d} ✗ {st}（{dt:.1f}s）")
        return
    p(f"每筆成交 {d}：{len(b) / 1e6:.1f} MB（{dt:.1f}s），開頭 {b[:4]!r}")
    got = read_zip(b)
    if got is None:
        p("  不是 zip：", b[:300])
        return
    name, txt = got
    lines = txt.splitlines()
    p(f"  {name}：{len(lines)} 行；表頭 {lines[0][:200]!r}")
    for ln in lines[1:4]:
        p("   ", ln[:200])
    rows = list(csv.reader(lines[1:]))
    prods: dict[str, int] = {}
    for r in rows:
        if len(r) > 1:
            prods[r[1].strip()] = prods.get(r[1].strip(), 0) + 1
    top = sorted(prods.items(), key=lambda kv: -kv[1])[:12]
    p(f"  商品 {len(prods)} 種，筆數最多：{top}")
    tx = [r for r in rows if len(r) > 5 and r[1].strip() == "TX"]
    months: dict[str, int] = {}
    for r in tx:
        months[r[2].strip()] = months.get(r[2].strip(), 0) + 1
    p(f"  TX {len(tx)} 筆，到期月份：{sorted(months.items(), key=lambda kv: -kv[1])[:6]}")
    if not tx:
        return
    near = max(months.items(), key=lambda kv: kv[1])[0]
    nx = [r for r in tx if r[2].strip() == near]
    dates: dict[str, int] = {}
    for r in nx:
        dates[r[0].strip()] = dates.get(r[0].strip(), 0) + 1
    p(f"  近月 {near!r} {len(nx)} 筆；成交日期欄：{dates}")
    day = [r for r in nx if 8 * 3600 + 30 * 60 <= sec(r[3]) <= 13 * 3600 + 45 * 60]
    night = [r for r in nx if not (8 * 3600 <= sec(r[3]) <= 14 * 3600)]
    p(f"  一般時段 {len(day)} 筆（{day[0][3] if day else '—'}～{day[-1][3] if day else '—'}）、"
      f"夜盤 {len(night)} 筆（{night[0][3] if night else '—'}～{night[-1][3] if night else '—'}）")
    for lo, hi, lab in ((8 * 3600 + 44 * 60, 8 * 3600 + 45 * 60 + 5, "08:44～08:45:05"),
                        (8 * 3600 + 58 * 60 + 55, 8 * 3600 + 59 * 60 + 5, "08:58:55～08:59:05"),
                        (8 * 3600 + 59 * 60 + 55, 9 * 3600 + 5, "08:59:55～09:00:05"),
                        (13 * 3600 + 44 * 60 + 55, 13 * 3600 + 46 * 60, "13:44:55～13:46")):
        seg = [r for r in day if lo <= sec(r[3]) <= hi]
        p(f"  {lab}：{len(seg)} 筆")
        for r in seg[:4] + (seg[-2:] if len(seg) > 6 else []):
            p("     ", [x.strip() for x in r])
    # 一秒內筆數、時間解析度
    secs: dict[int, int] = {}
    for r in day:
        secs[sec(r[3])] = secs.get(sec(r[3]), 0) + 1
    p(f"  一般時段有成交的秒數 {len(secs)}，同一秒最多 {max(secs.values())} 筆；時間欄樣式 {sorted({len(r[3].strip()) for r in day})}")
    # 存成精簡格式要多大：每筆（秒、價、量），gzip
    comp = "\n".join(f"{sec(r[3])},{r[4].strip()},{r[5].strip()}" for r in day).encode()
    p(f"  一般時段近月精簡（秒,價,量）{len(comp) // 1024} KB，gzip 後 {len(gzip.compress(comp, 9)) // 1024} KB")
    bars: dict[int, list] = {}
    for r in day:
        m = sec(r[3]) // 60
        px = float(r[4])
        q = int(float(r[5]))
        b1 = bars.setdefault(m, [px, px, px, px, 0])
        b1[1], b1[2], b1[3], b1[4] = max(b1[1], px), min(b1[2], px), px, b1[4] + q
    one = json.dumps({k: v for k, v in sorted(bars.items())}).encode()
    p(f"  一分 K {len(bars)} 根，gzip 後 {len(gzip.compress(one, 9)) // 1024} KB")


def tick_old() -> None:
    """清單以外的日子拿不拿得到。"""
    today = tw_now().date()
    for back in (45, 70, 200, 800):
        d = today - timedelta(days=back)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        for kind in ("csv", "rpt"):
            b, dt, st = get(tick_url(d, kind), timeout=60)
            if b is None:
                p(f"每筆成交 {d}（{kind}，{back} 天前）✗ {st}（{dt:.1f}s）")
            else:
                p(f"每筆成交 {d}（{kind}，{back} 天前）：{len(b) // 1024} KB，開頭 {b[:4]!r}"
                  f"{'（zip）' if b[:2] == b'PK' else '（不是 zip）'}")


def fut_daily() -> None:
    for a, z in (("2026/10/01", "2026/10/27"), ("2017/05/15", "2017/05/19"),
                 ("2010/01/04", "2010/01/08"), ("1998/07/21", "1998/07/31")):
        try:
            t0 = time.time()
            b = post_bytes(f"{TFX}/cht/3/futDataDown",
                           {"down_type": "1", "commodity_id": "TX", "commodity_id2": "",
                            "queryStartDate": a, "queryEndDate": z}, timeout=60, retries=2)
            txt = b.decode("cp950", "replace")
            ls = [ln for ln in txt.splitlines() if ln.strip()]
            p(f"每日行情 TX {a}～{z}：{len(ls)} 行（{time.time() - t0:.1f}s）")
            for ln in ls[:4]:
                p("   ", ln[:220])
        except Exception as e:                                # noqa: BLE001
            p(f"每日行情 TX {a}～{z} ✗ {str(e)[:160]}")


# ── 證交所：每 5 秒指數、每日加權指數 ─────────────────────────────────────

def twse_5s() -> None:
    today = tw_now().date()
    d0 = today if today.weekday() < 5 else today - timedelta(days=today.weekday() - 4)
    for d in (d0, date(2025, 12, 31), date(2020, 3, 23), date(2020, 3, 20), date(2017, 1, 3),
              date(2010, 1, 4), date(2004, 10, 15)):
        for url in (f"https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_INDEX?date={d:%Y%m%d}&response=json",
                    f"https://www.twse.com.tw/exchangeReport/MI_5MINS_INDEX?response=json&date={d:%Y%m%d}"):
            b, dt, st = get(url, timeout=60)
            if b is None:
                p(f"5 秒指數 {d} ✗ {st}（{dt:.1f}s）{url[:60]}")
                continue
            try:
                doc = json.loads(b.decode("utf-8"))
            except Exception:                                 # noqa: BLE001
                p(f"5 秒指數 {d} 不是 JSON：{b[:160]!r}")
                continue
            rows = doc.get("data") or []
            p(f"5 秒指數 {d}：stat={doc.get('stat')} {len(rows)} 列（{dt:.1f}s，{len(b) // 1024} KB）"
              f" 欄位 {doc.get('fields', [])[:3]}")
            for r in rows[:3] + rows[-2:]:
                p("   ", r[:3])
            break
        time.sleep(3)


def twse_hist() -> None:
    for d in (date(2026, 10, 1), date(2020, 3, 1), date(2017, 1, 1)):
        url = f"https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={d:%Y%m%d}&response=json"
        b, dt, st = get(url, timeout=60)
        if b is None:
            p(f"每日加權 {d:%Y-%m} ✗ {st}")
            continue
        try:
            doc = json.loads(b.decode("utf-8"))
        except Exception:                                     # noqa: BLE001
            p(f"每日加權 {d:%Y-%m} 不是 JSON：{b[:160]!r}")
            continue
        rows = doc.get("data") or []
        p(f"每日加權 {d:%Y-%m}：{len(rows)} 列，欄位 {doc.get('fields')}；{rows[:2]}")
        time.sleep(3)


# ── 即時報價 ──────────────────────────────────────────────────────────────

MIS_SYMS = "tse_t00.tw|tse_2330.tw|tse_2317.tw|tse_2454.tw|tse_2308.tw|otc_o00.tw"


def mis_twse(show: bool = True) -> list[dict]:
    url = (f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={MIS_SYMS}"
           f"&json=1&delay=0&_={int(time.time() * 1000)}")
    b, dt, st = get(url, timeout=20)
    if b is None:
        if show:
            p(f"證交所 MIS ✗ {st}（{dt:.1f}s）")
        return []
    try:
        doc = json.loads(b.decode("utf-8"))
    except Exception:                                         # noqa: BLE001
        if show:
            p(f"證交所 MIS 不是 JSON：{b[:200]!r}")
        return []
    arr = doc.get("msgArray") or []
    if show:
        p(f"證交所 MIS：{len(arr)} 檔（{dt:.1f}s）rtcode={doc.get('rtcode')} 其他鍵 {sorted(k for k in doc if k != 'msgArray')}")
        for m in arr:
            p("   ", json.dumps(m, ensure_ascii=False)[:600])
    return arr


def mis_taifex(show: bool = True) -> list[dict]:
    body = {"MarketType": "0", "SymbolType": "F", "KindID": "1", "CID": "TXF", "ExpireMonth": "",
            "RowSize": "全部", "PageNo": "", "SortColumn": "", "AscDesc": "A"}
    b, dt, st = post_json("https://mis.taifex.com.tw/futures/api/getQuoteList", body)
    if b is None:
        if show:
            p(f"期交所 MIS ✗ {st}（{dt:.1f}s）")
        return []
    try:
        doc = json.loads(b.decode("utf-8"))
    except Exception:                                         # noqa: BLE001
        if show:
            p(f"期交所 MIS 不是 JSON（{st}）：{b[:300]!r}")
        return []
    arr = (doc.get("RtData") or {}).get("QuoteList") or []
    if show:
        p(f"期交所 MIS：{st}（{dt:.1f}s）頂層鍵 {list(doc)[:8]}；{len(arr)} 列")
        for m in arr[:4]:
            p("   ", json.dumps(m, ensure_ascii=False)[:600])
    return arr


TOP = ("2330 2317 2454 2308 2382 2412 2881 2882 3711 2891 2303 1216 2886 2357 2884 3231 2885 2892 "
       "2603 6669 2345 3008 2207 2002 1301 1303 2880 5880 2887 3045 4904 2890 2379 3034 2395 6505 "
       "1101 2912 2327 3017").split()


def mis_batch(syms: list[str]) -> tuple[list[dict], float]:
    ex = "|".join(f"tse_{c}.tw" for c in syms)
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex}&json=1&delay=0&_={int(time.time() * 1000)}"
    b, dt, st = get(url, timeout=20)
    if b is None:
        p(f"  批次 {len(syms)} 檔 ✗ {st}（{dt:.1f}s）")
        return [], dt
    try:
        return json.loads(b.decode("utf-8")).get("msgArray") or [], dt
    except Exception:                                         # noqa: BLE001
        p(f"  批次不是 JSON：{b[:200]!r}")
        return [], dt


def _stk(m: dict) -> str:
    a = str(m.get("a", "")).split("_")[0]
    b = str(m.get("b", "")).split("_")[0]
    return (f"{m.get('c')} z={m.get('z')} pz={m.get('pz')} y={m.get('y')} o={m.get('o')} a1={a} b1={b} "
            f"ts={m.get('ts')} ip={m.get('ip')} it={m.get('it')} t={m.get('t')} %={m.get('%')} oa={m.get('oa')} ob={m.get('ob')} ot={m.get('ot')}")


def _tfx(m: dict) -> str:
    return (f"{m.get('SymbolID')} last={m.get('CLastPrice')} t={m.get('CTime')} test={m.get('CTestPrice')}@{m.get('CTestTime')} "
            f"bid={m.get('CBidPrice1')} ask={m.get('CAskPrice1')} open={m.get('COpenPrice')} ref={m.get('CRefPrice')} st={m.get('Status')}")


DUMP_AT = ("08:31:00", "08:45:00", "08:55:00", "08:59:00", "08:59:30", "08:59:55", "09:00:10")


def pre_loop(start: str = "08:29:30", until: str = "09:02:00", max_min: float = 40) -> None:
    """盤前每 5 秒抓一次：看試撮時段 MIS 給什麼（加權指數、權值股、台指期）。"""
    now = tw_now()
    tgt = now.replace(hour=int(start[:2]), minute=int(start[3:5]), second=int(start[6:8]), microsecond=0)
    wait = (tgt - now).total_seconds()
    if 0 < wait < 3 * 3600:
        p(f"等到 {start}（{wait / 60:.1f} 分鐘）")
        time.sleep(wait)
    t_end = time.time() + max_min * 60
    first, done = True, set()
    while time.time() < t_end:
        now = tw_now()
        hms = now.strftime("%H:%M:%S")
        if hms >= until:
            break
        tw = mis_twse(show=first)
        tf = mis_taifex(show=first)
        first = False
        line = [hms] + [_stk(m) if m.get("c") not in ("t00", "o00") else
                        f"{m.get('c')} z={m.get('z')} o={m.get('o')} y={m.get('y')} t={m.get('t')} %={m.get('%')} h={m.get('h')} l={m.get('l')}"
                        for m in tw] + [_tfx(m) for m in tf[:2]]
        p(" | ".join(line))
        due = [x for x in DUMP_AT if x <= hms and x not in done]
        if due:
            done.update(due)
            arr, dt = mis_batch(TOP)
            p(f"  {hms} 權值股 {len(arr)}／{len(TOP)} 檔（{dt:.2f}s）")
            for m in arr:
                p("   ", _stk(m))
            if hms >= "08:59:00" and hms < "08:59:05":
                for m in tw[:2]:
                    p("    全文", json.dumps(m, ensure_ascii=False))
                for m in tf[:2]:
                    p("    全文", json.dumps(m, ensure_ascii=False))
        time.sleep(max(0.5, 5 - (time.time() % 5)))


# ── FinMind ───────────────────────────────────────────────────────────────

def finmind() -> None:
    for ds, did, a, z in (("TaiwanFuturesTick", "TX", "2026-10-23", ""),
                          ("TaiwanFuturesDaily", "TX", "2017-05-15", "2017-05-19"),
                          ("TaiwanFuturesDaily", "TX", "1998-07-21", "1998-08-05"),
                          ("TaiwanStockKBar", "2330", "2026-10-23", "")):
        url = FM.format(ds=ds, did=f"&data_id={did}", a=a, z=f"&end_date={z}" if z else "")
        b, dt, st = get(url, timeout=90)
        if b is None:
            p(f"FinMind {ds} ✗ {st}（{dt:.1f}s）")
            continue
        try:
            doc = json.loads(b.decode("utf-8"))
        except Exception:                                     # noqa: BLE001
            p(f"FinMind {ds} 不是 JSON：{b[:200]!r}")
            continue
        rows = doc.get("data") or []
        p(f"FinMind {ds} {a}～{z or a}：status={doc.get('status')} msg={str(doc.get('msg'))[:120]} "
          f"{len(rows)} 列（{dt:.1f}s）")
        for r in rows[:2] + rows[-1:]:
            p("   ", json.dumps(r, ensure_ascii=False)[:300])
        time.sleep(2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", action="store_true")
    ap.add_argument("--start", default="08:29:30")
    ap.add_argument("--until", default="09:02:00")
    ap.add_argument("--max-min", type=float, default=40)
    a = ap.parse_args()
    p(f"開始 台北 {tw_now():%F %T}")
    if a.pre:
        pre_loop(a.start, a.until, a.max_min)
        return
    ds = tick_dates()
    if ds:
        tick_day(ds[-1])
        if len(ds) > 1:
            tick_day(ds[0])
    else:
        d = tw_now().date() - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        tick_day(d)
    tick_old()
    fut_daily()
    twse_5s()
    twse_hist()
    mis_twse()
    mis_taifex()
    finmind()
    p(f"完成 台北 {tw_now():%F %T}")


if __name__ == "__main__":
    main()
