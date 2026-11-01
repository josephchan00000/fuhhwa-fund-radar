#!/usr/bin/env python3
"""預估配息與隔年休市表的來源探針（使用者 2026-11-01：「不可能手動補啦要抓公告 不然就是抓新聞因為投信都會買新聞」）。

容器擋證交所／櫃買／Google，所以在 CI 跑（lab_backfill.yml，.ping/lab 第一行寫 divprobe）。結果印出、也寫進
data/lab/_divprobe.txt（lab_backfill 會 commit 回分支，讀檔比讀日誌省），看完從分支刪掉。只讀不寫落檔；每段各自 try，
一段壞了不影響其他段。看的東西：
  1. 證交所「除權除息預告表」（上市 ETF）：哪個網址抓得到、欄位、追蹤清單裡的 ETF 有沒有在上面、金額與除息日；
  2. 櫃買的同一張表（上櫃 ETF）：同上；證交所／櫃買 OpenAPI 目錄裡名字有除權息的端點也試一次；
  3. 公開資訊觀測站（arm/connectors/mops.etf_distributions，現在就在用、常抓不到）：這一輪抓不抓得到；
  4. 新聞：「代號＋配息」的 Google 新聞標題，標題裡抓不抓得到金額；
  5. 證交所休市表：能不能直接抓到「明年」那一張（2027 年還在用辦公日曆暫代，12/1 起測試會紅）。
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm import clock  # noqa: E402
from arm.http import get_bytes  # noqa: E402

OUT = ROOT / "data" / "lab" / "_divprobe.txt"
LINES: list[str] = []
CODES: list[str] = []
AMT = re.compile(r"(?:擬配|配息|配發|每單位配|配)\s*([0-9]+(?:\.[0-9]+)?)\s*元")


def p(*a) -> None:
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LINES.append(s)


def sec(t: str) -> None:
    p(f"\n===== {t} =====")


def run(name: str, fn) -> None:
    sec(name)
    try:
        fn()
    except Exception as ex:                                   # noqa: BLE001
        p(f"✗ {type(ex).__name__}: {str(ex)[:200]}")


def fetch(url: str, *, sleep: float = 3.5, timeout: int = 25) -> bytes | None:
    t0 = time.time()
    try:
        b = get_bytes(url, retries=1, timeout=timeout, use_cache=False)
    except Exception as ex:                                   # noqa: BLE001
        p(f"  {url}\n    ✗ {type(ex).__name__}: {str(ex)[:160]}（{time.time() - t0:.1f}s）")
        time.sleep(sleep)
        return None
    time.sleep(sleep)
    p(f"  {url}\n    {len(b)}B（{time.time() - t0:.1f}s）開頭 {b[:120].decode('utf-8', 'replace')!r}")
    return b


def as_json(b: bytes | None):
    if not b:
        return None
    try:
        return json.loads(b.decode("utf-8", "replace").strip())
    except ValueError:
        return None


def _tables(d) -> list[tuple[str, list, list]]:
    """回應 → [(標題, 欄位, 列)]：證交所新版 {tables:[{title,fields,data}]}、舊版 {fields,data}、
    櫃買 {aaData}／{tables}、OpenAPI 的 [ {欄: 值} ]。"""
    out = []
    if isinstance(d, list):
        if d and isinstance(d[0], dict):
            keys = list(d[0].keys())
            out.append(("(OpenAPI 列表)", keys, [[r.get(k) for k in keys] for r in d]))
        return out
    if not isinstance(d, dict):
        return out
    for t in d.get("tables") or []:
        if isinstance(t, dict):
            out.append((t.get("title") or "", t.get("fields") or [], t.get("data") or []))
    if d.get("data") is not None and d.get("fields") is not None:
        out.append((d.get("title") or "", d.get("fields") or [], d.get("data") or []))
    if d.get("aaData") is not None:
        out.append((d.get("reportTitle") or "", d.get("fields") or [], d.get("aaData") or []))
    return out


def dump(d, *, show_etf: int = 15) -> None:
    if isinstance(d, dict):
        p(f"    stat={d.get('stat')!r} title={str(d.get('title') or d.get('reportTitle') or '')[:80]!r} 鍵={list(d.keys())[:12]}")
    tabs = _tables(d)
    if not tabs:
        p("    （找不到表格）")
        return
    cs = set(CODES)
    for title, fields, rows in tabs:
        p(f"    表「{str(title)[:60]}」欄位 {fields}，{len(rows)} 列")
        for r in rows[:3]:
            p(f"      樣本 {r}")
        hit = [r for r in rows if any(str(c).strip() in cs for c in (r if isinstance(r, list) else []))]
        p(f"      追蹤清單裡的 ETF 在表上：{len(hit)} 列")
        for r in hit:
            p(f"      ★ {r}")
        etf = [r for r in rows if isinstance(r, list) and any(re.fullmatch(r"00\d{2,4}[A-Z]?", str(c).strip()) for c in r)]
        p(f"      代號像 ETF（00 開頭）的列：{len(etf)}")
        for r in etf[:show_etf]:
            p(f"      · {r}")


def tracked() -> None:
    from arm.etfwatch import watch_tuples
    CODES.extend(t[0] for t in watch_tuples())
    p(f"  {len(CODES)} 檔：{' '.join(CODES)}")


def twse_pre() -> None:
    today = clock.today_tw()
    end = today + timedelta(days=90)
    for u in ("https://www.twse.com.tw/rwd/zh/exRight/TWT48U?response=json",
              f"https://www.twse.com.tw/rwd/zh/exRight/TWT48U?startDate={today:%Y%m%d}&endDate={end:%Y%m%d}&response=json",
              "https://www.twse.com.tw/exchangeReport/TWT48U?response=json",
              "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL"):
        d = as_json(fetch(u))
        if d is not None:
            dump(d)


def _openapi_paths(url: str, words: tuple[str, ...], *, sleep: float) -> list[str]:
    d = as_json(fetch(url, sleep=sleep, timeout=40))
    if not isinstance(d, dict):
        return []
    hits = []
    for path, ops in (d.get("paths") or {}).items():
        txt = path + " " + json.dumps(ops, ensure_ascii=False)
        if any(w.lower() in txt.lower() for w in words):
            summ = next((str(o.get("summary") or o.get("description") or "")[:60]
                         for o in (ops or {}).values() if isinstance(o, dict)), "")
            hits.append(path)
            p(f"    目錄 {path}  {summ}")
    base = (d.get("servers") or [{}])[0].get("url") if d.get("servers") else None
    base = base or d.get("basePath") or ""
    p(f"    目錄共 {len(d.get('paths') or {})} 個端點，符合 {len(hits)} 個；base={base!r}")
    return [(base.rstrip("/") + h) if base.startswith("http") else h for h in hits]


def twse_openapi() -> None:
    for path in _openapi_paths("https://openapi.twse.com.tw/v1/swagger.json", ("TWT48U", "除權", "除息", "Dividend"),
                               sleep=3.5)[:4]:
        u = path if path.startswith("http") else "https://openapi.twse.com.tw/v1" + path
        d = as_json(fetch(u))
        if d is not None:
            dump(d)


def tpex_pre() -> None:
    for u in ("https://www.tpex.org.tw/web/stock/exright/preAnnounce/prepost_result.php?l=zh-tw&o=json",
              "https://www.tpex.org.tw/web/stock/exright/preAnnounce/PrePost_result.php?l=zh-tw&o=json",
              "https://www.tpex.org.tw/www/zh-tw/bulletin/exRight?response=json"):
        d = as_json(fetch(u, sleep=1.6))
        if d is not None:
            dump(d)


def tpex_openapi() -> None:
    for path in _openapi_paths("https://www.tpex.org.tw/openapi/swagger.json", ("exright", "除權", "除息", "dividend"),
                               sleep=1.6)[:4]:
        u = path if path.startswith("http") else "https://www.tpex.org.tw/openapi/v1" + path
        d = as_json(fetch(u, sleep=1.6))
        if d is not None:
            dump(d)


def mops_dist() -> None:
    from arm.connectors import mops
    t0 = time.time()
    d = mops.etf_distributions(set(CODES))
    p(f"  回 {len(d)} 檔（{time.time() - t0:.1f}s）")
    for c in CODES:
        if c in d:
            p(f"  ★ {c} {d[c]}")


def news() -> None:
    from arm.connectors import gnews
    f0 = gnews.FAILS
    for c in CODES:
        items = gnews.search(f"{c} 配息", days=21, limit=8)
        own = [it for it in items if c in (it.get("title") or "")]
        p(f"  {c}：{len(items)} 則，標題有代號 {len(own)} 則")
        for it in own[:6]:
            t = it.get("title") or ""
            p(f"    {it.get('date', '')} [{it.get('source', '')}] {t[:100]}  → 金額 {AMT.findall(t)}")
    p(f"  查詢出錯 {gnews.FAILS - f0} 次")


def holidays() -> None:
    for u in ("https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
              "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?response=json",
              "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?date=20270101&response=json",
              "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?queryYear=116&response=json",
              "https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=json&queryYear=116"):
        d = as_json(fetch(u))
        if d is None:
            continue
        s = json.dumps(d, ensure_ascii=False)
        roc = Counter(m for m in re.findall(r"(?<!\d)(1\d{2})(?:\d{4})(?!\d)", s))
        ad = Counter(m for m in re.findall(r"(?<!\d)(20\d{2})[-/]?\d{2}[-/]?\d{2}(?!\d)", s))
        p(f"    民國年份出現次數 {dict(roc)}；西元年份 {dict(ad)}")
        tabs = _tables(d)
        for title, fields, rows in tabs:
            p(f"    表「{str(title)[:60]}」欄位 {fields}，{len(rows)} 列；前三列 {rows[:3]}")


def main() -> int:
    t0 = time.time()
    try:
        for name, fn in (("追蹤清單", tracked), ("1. 證交所除權除息預告表", twse_pre),
                         ("1b. 證交所 OpenAPI 目錄裡的除權息端點", twse_openapi),
                         ("2. 櫃買除權除息預告", tpex_pre), ("2b. 櫃買 OpenAPI 目錄裡的除權息端點", tpex_openapi),
                         ("3. 公開資訊觀測站（現有連接器）", mops_dist), ("4. 新聞標題", news),
                         ("5. 證交所休市表能不能抓明年", holidays)):
            run(name, fn)
    finally:
        p(f"\n總共 {time.time() - t0:.0f} 秒；{clock.stamp_tw()}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
