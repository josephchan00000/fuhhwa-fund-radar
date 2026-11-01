#!/usr/bin/env python3
"""預估配息金額的來源探針（使用者 2026-11-01：「預估是在正式配息前投信會提早公告一個金額 可能不跟實際不同但還是會提前講 你找不到嗎」）。

證交所／櫃買的除權除息預告表要等投信第二階段公告（確定金額）才填金額；預估金額在第一階段公告裡（00400A 6/18 就公告預估 0.12、
7/9 除息）。容器擋觀測站、證交所、集保，所以在 CI 跑（lab_backfill.yml，.ping/lab 第一行寫 divest）。結果印出、也寫進
data/lab/_divest.txt（lab_backfill 會 commit 回分支），看完從分支刪掉。只讀不寫落檔；每段各自 try。看的東西：
  1. 公開資訊觀測站重大訊息（ajax_t05st01，個股報告文件包 arm/lab/eqdocs 已在用）：以 ETF 代號查今年，近 60 天主旨有
     收益分配／配息／除息的抓內文，找「預估…元」與除息日；
  2. 證交所 ETF 收益分配頁（/zh/ETF/etfDiv）背後的 JSON；
  3. 集保 ETF 觀測站（fundclear.com.tw/etf）：首頁與頁面裡看得到的 API 路徑。
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm import clock  # noqa: E402
from arm.http import get_bytes  # noqa: E402

OUT = ROOT / "data" / "lab" / "_divest.txt"
LINES: list[str] = []
DAYS = 60
DETAIL_MAX = 45
KEY = re.compile(r"收益分配|配息|除息|分配金額")
AMT = [re.compile(r"預估[^。；\n]{0,60}?([0-9]+\.[0-9]+|[0-9]+)\s*元"),
       re.compile(r"每(?:一)?受益權單位[^。；\n]{0,40}?([0-9]+\.[0-9]+)\s*元"),
       re.compile(r"([0-9]+\.[0-9]+)\s*元")]
EXD = re.compile(r"除息(?:交易)?日[^0-9]{0,12}(\d{2,3}[/年.]\d{1,2}[/月.]\d{1,2})")


def p(*a) -> None:
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LINES.append(s)


def run(name: str, fn) -> None:
    p(f"\n===== {name} =====")
    try:
        fn()
    except Exception as ex:                                   # noqa: BLE001
        p(f"✗ {type(ex).__name__}: {str(ex)[:300]}")


def fetch(url: str, *, sleep: float = 2.0, timeout: int = 30) -> bytes | None:
    t0 = time.time()
    try:
        b = get_bytes(url, retries=1, timeout=timeout, use_cache=False)
    except Exception as ex:                                   # noqa: BLE001
        p(f"  {url}\n    ✗ {type(ex).__name__}: {str(ex)[:160]}（{time.time() - t0:.1f}s）")
        time.sleep(sleep)
        return None
    time.sleep(sleep)
    p(f"  {url}\n    {len(b)}B（{time.time() - t0:.1f}s）開頭 {b[:160].decode('utf-8', 'replace')!r}")
    return b


def mops() -> None:
    from arm.etfwatch import exchange_distributions, watch_tuples
    from arm.lab import eqdocs as E
    from arm.lab.market import _decode, post_bytes

    today = clock.today_tw()
    codes = [t[0] for t in watch_tuples()]
    exch, ok = exchange_distributions(set(codes), today)
    p(f"  交易所預告表（今天以後）：{ {c: v for c, v in exch.items()} }（兩邊都抓到 {ok}）")
    lo = (today - timedelta(days=DAYS)).isoformat()

    def post(form: dict) -> str:
        return _decode(post_bytes(f"{E.OV}/mops/web/ajax_t05st01", form, timeout=60, retries=2))

    # 交易所表上有日期的排前面，其餘照追蹤清單
    order = sorted(codes, key=lambda c: (c not in exch, codes.index(c)))
    hits, details = [], 0
    for code in order:
        form = {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "keyword4": "", "code1": "", "TYPEK2": "",
                "checkbtn": "", "queryName": "co_id", "inpuType": "co_id", "TYPEK": "all", "co_id": code,
                "year": E.roc(today.year), "month": "", "b_date": "", "e_date": ""}
        try:
            html = post(form)
        except Exception as ex:                               # noqa: BLE001
            p(f"  {code} 列表 ✗ {type(ex).__name__}: {str(ex)[:120]}")
            time.sleep(1.5)
            continue
        time.sleep(1.2)
        items = [x for x in E.parse_news_list(html, code) if x["d"] >= lo]
        rel = [x for x in items if KEY.search(x["subj"])]
        p(f"  {code}：近 {DAYS} 天重大訊息 {len(items)} 則、收益分配相關 {len(rel)} 則（列表 {len(html)} 字）")
        if not items and len(html) < 400:
            p(f"    回應：{re.sub(r'<[^>]+>', ' ', html)[:200]!r}")
        for x in rel[:4]:
            p(f"    {x['d']} {x['t']} {x['subj'][:120]}")
        for x in rel[:3]:
            if details >= DETAIL_MAX or not x["form"]:
                continue
            f = {"encodeURIComponent": 1, "firstin": "true", "off": 1, "step": 2, "TYPEK": "all", "co_id": code,
                 "year": E.roc(int(x["d"][:4])), "month": "all", "e_month": "all", "b_date": "", "e_date": "", "type": "",
                 "MEETING_STEP": "", "MODEL": "", "ITEM": "", **x["form"]}
            try:
                body = E.parse_news_detail(post(f))
            except Exception as ex:                           # noqa: BLE001
                p(f"      內文 ✗ {type(ex).__name__}: {str(ex)[:120]}")
                time.sleep(1.5)
                continue
            details += 1
            time.sleep(1.2)
            flat = re.sub(r"\s+", " ", body)
            amts = [m.group(1) for rx in AMT[:2] for m in rx.finditer(flat)]
            exd = EXD.findall(flat)
            i = flat.find("預估")
            p(f"      內文 {len(flat)} 字；預估類金額 {amts[:4]}；除息日 {exd[:2]}")
            p(f"      「預估」附近：{flat[max(0, i - 60):i + 160] if i >= 0 else '（沒有預估兩字）'}")
            if i < 0:
                p(f"      內文開頭：{flat[:260]}")
            hits.append((code, x["d"], x["subj"][:40], amts[:2], exd[:1]))
    p(f"\n  總結：抓了 {details} 則內文；有預估類金額的：")
    for h in hits:
        if h[3]:
            p(f"    {h}")


def twse_etfdiv() -> None:
    today = clock.today_tw()
    a, b = today - timedelta(days=40), today + timedelta(days=40)
    for u in ("https://www.twse.com.tw/rwd/zh/ETF/etfDiv?response=json",
              f"https://www.twse.com.tw/rwd/zh/ETF/etfDiv?startDate={a:%Y%m%d}&endDate={b:%Y%m%d}&response=json",
              "https://www.twse.com.tw/rwd/zh/ETF/etfDiv?stkNo=00400A&response=json",
              "https://www.twse.com.tw/zh/ETF/etfDiv"):
        x = fetch(u)
        if not x:
            continue
        try:
            d = json.loads(x.decode("utf-8", "replace"))
        except ValueError:
            api = sorted(set(re.findall(r"""["'](/rwd/[^"']+|/api/[^"']+)["']""", x.decode("utf-8", "replace"))))
            p(f"    （不是 JSON）頁面裡的 API 路徑：{api[:20]}")
            continue
        if isinstance(d, dict):
            p(f"    stat={d.get('stat')!r} title={str(d.get('title'))[:60]!r} 鍵={list(d)[:12]} 欄位={d.get('fields')}")
            rows = d.get("data") or []
            p(f"    {len(rows)} 列；前 5 列：{rows[:5]}")
            mine = [r for r in rows if any(str(c).strip() in ("00400A", "00401A", "00406A", "00929", "00986D") for c in r)]
            p(f"    追蹤的幾檔：{mine[:8]}")


def fundclear() -> None:
    x = fetch("https://www.fundclear.com.tw/etf", sleep=1.5)
    if not x:
        return
    s = x.decode("utf-8", "replace")
    api = sorted(set(re.findall(r"""["']((?:https://[^"']*fundclear[^"']*)?/api/[^"'\s]+)["']""", s)))
    js = re.findall(r"""<script[^>]+src=["']([^"']+\.js)["']""", s)
    p(f"    頁面 API 路徑 {api[:30]}；script {js[:8]}")
    found = set()
    for src in js[:6]:
        u = src if src.startswith("http") else "https://www.fundclear.com.tw" + (src if src.startswith("/") else "/" + src)
        b = fetch(u, sleep=1.0)
        if not b:
            continue
        t = b.decode("utf-8", "replace")
        for m in re.finditer(r"""["'`]((?:/|https://)[^"'`\s]{0,80}(?:api|Api|API)[^"'`\s]{0,80})["'`]""", t):
            found.add(m.group(1))
    hint = sorted(u for u in found if re.search(r"div|Div|配息|收益|income|Income|distrib", u))
    p(f"    JS 裡的 API 共 {len(found)} 個；和配息有關的：{hint[:30]}")
    p(f"    其他前 40 個：{sorted(found)[:40]}")


def main() -> int:
    t0 = time.time()
    try:
        for name, fn in (("1. 公開資訊觀測站重大訊息（ETF 代號）", mops),
                         ("2. 證交所 ETF 收益分配頁", twse_etfdiv),
                         ("3. 集保 ETF 觀測站", fundclear)):
            run(name, fn)
    finally:
        p(f"\n總共 {time.time() - t0:.0f} 秒；{clock.stamp_tw()}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
