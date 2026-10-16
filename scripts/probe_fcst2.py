"""法人預估探針第 2 輪（F0）：鉅亨台股新聞清單能不能依日期回溯、FactSet 快訊內文格式、搜尋 API 能回溯多久。
結果寫 data/lab/probe_fcst2.txt。只在 CI 跑（.ping/lab 第一行 probefc2）。"""
from __future__ import annotations

import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_fcst as P  # noqa: E402

P.OUT = Path(__file__).resolve().parent.parent / "data" / "lab" / "probe_fcst2.txt"
TZ = timezone(timedelta(hours=8))


def day_ts(d: str):
    t0 = datetime.fromisoformat(d).replace(tzinfo=TZ)
    return int(t0.timestamp()), int((t0 + timedelta(days=1)).timestamp()) - 1


def cat_day(cat, d, limit=30, page=1):
    a, b = day_ts(d)
    url = f"https://api.cnyes.com/media/api/v1/newslist/category/{cat}?startAt={a}&endAt={b}&limit={limit}&page={page}"
    st, body, _ = P.get(url)
    o = P.js(body)
    r = P.find_items(o) if o is not None else None
    return st, url, (r[0] if r else []), ((o or {}).get("items") or {}) if isinstance(o, dict) else {}


def main():
    say = P.say
    # 1. 台股清單依日期回溯
    for d in ("2026-10-15", "2025-06-10", "2024-06-11", "2023-06-12", "2022-06-13"):
        st, url, items, meta = cat_day("tw_stock", d)
        fs = [it for it in items if "actset" in str(it.get("title"))]
        rng = (P.ts(items[-1].get("publishAt")), P.ts(items[0].get("publishAt"))) if items else None
        say(f"\n## tw_stock {d}：HTTP {st}，{len(items)} 則（total {meta.get('total')}、last_page {meta.get('last_page')}），"
            f"時間 {rng}，FactSet {len(fs)} 則")
        for it in fs[:3]:
            say("   ★", P.brief(it))
    # 2. limit 上限
    for lim in (100, 50):
        st, url, items, meta = cat_day("tw_stock", "2026-10-15", limit=lim)
        say(f"\n## limit={lim}：回 {len(items)} 則、per_page {meta.get('per_page')}")
    # 3. 一天的 FactSet 台股快訊全數（翻頁）
    d = "2026-10-15"
    allfs, p = [], 1
    while p <= 20:
        st, url, items, meta = cat_day("tw_stock", d, limit=30, page=p)
        allfs += [it for it in items if "actset" in str(it.get("title")) and "-TW)" in str(it.get("title"))]
        if p >= int(meta.get("last_page") or 1):
            break
        p += 1
    say(f"\n## {d} tw_stock 共 {p} 頁，FactSet 台股快訊 {len(allfs)} 則")
    for it in allfs[:40]:
        say("   ·", P.brief(it))
    # 4. 內文格式（各一則：EPS、預估股價）
    shown = set()
    for it in allfs:
        t = str(it.get("title"))
        k = "e" if "EPS" in t else "t"
        if k in shown:
            continue
        shown.add(k)
        c = html.unescape(str(it.get("content") or ""))
        say(f"\n## 內文（{k}）{it.get('newsId')} {t}\n{c[:6000]}")
        say("  keyword：", it.get("keyword"), "｜market：", it.get("market"), "｜stock：", it.get("stock"))
    # 5. 搜尋 API 回溯深度
    base = "https://api.cnyes.com/media/api/v1/search?q=Factset%20%E6%9C%80%E6%96%B0%E8%AA%BF%E6%9F%A5&limit=20&page={p}"
    for p in (1, 10, 50, 100, 200, 300, 400, 455, 456):
        st, body, _ = P.get(base.format(p=p))
        o = P.js(body)
        r = P.find_items(o) if o is not None else None
        items = r[0] if r else []
        if items:
            tw = sum(1 for it in items if it.get("categoryName") == "台股預估")
            say(f"  搜尋第 {p} 頁：{P.ts(items[0].get('publishAt'))} ～ {P.ts(items[-1].get('publishAt'))}，台股 {tw}/{len(items)}")
        else:
            say(f"  搜尋第 {p} 頁：HTTP {st}，無清單")
        time.sleep(0.3)
    # 6. 分類代號猜測（台股預估 categoryId 911）
    for cat in ("anue_live", "tw_stock_estimate", "tw_estimate", "estimate", "tw_forecast", "tw_stock_forecast"):
        url = f"https://api.cnyes.com/media/api/v1/newslist/category/{cat}?limit=30&page=1"
        st, body, _ = P.get(url)
        o = P.js(body)
        r = P.find_items(o) if o is not None else None
        items = r[0] if r else []
        fs = sum(1 for it in items if "actset" in str(it.get("title")))
        say(f"\n## 分類 {cat}：HTTP {st}，{len(items)} 則，FactSet {fs}；total {((o or {}).get('items') or {}).get('total') if isinstance(o, dict) and isinstance(o.get('items'), dict) else None}")
        for it in items[:3]:
            say("   ·", P.brief(it))
    say(f"\n探針結束，{time.time() - P.T0:.0f} 秒")


if __name__ == "__main__":
    try:
        main()
    finally:
        P.OUT.write_text("\n".join(P.LOG) + "\n", encoding="utf-8")
