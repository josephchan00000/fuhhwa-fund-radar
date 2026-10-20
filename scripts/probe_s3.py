#!/usr/bin/env python3
"""大神策略第三段的資料探針（docs/lab_expert_plan.md 第 10 節；只印診斷、不寫檔，CI 跑）：

  台股融資維持率：FinMind 逐檔融資餘額與原始收盤能回到哪一年、已下市公司有沒有、單位和官方分片對不對得起來、
                  每個請求要多久；證交所／櫃買的終止上市櫃名單有幾檔。
  美股漲跌家數：NYSE 漲跌家數現成檔、維基 S&P 500 成分股、Yahoo 長歷史、歷史成分股資料集。

  python3 scripts/probe_s3.py
"""
from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.http import get_bytes  # noqa: E402

FM = "https://api.finmindtrade.com/api/v4/data?dataset={ds}{did}&start_date={a}&end_date={z}"


def p(*a) -> None:
    print("[s3]", *a, flush=True)


def get(url: str, timeout: int = 60, headers: dict | None = None) -> tuple[bytes | None, float, str]:
    t0 = time.time()
    try:
        b = get_bytes(url, retries=1, timeout=timeout, use_cache=False, headers=headers)
        return b, time.time() - t0, "ok"
    except Exception as e:                                    # noqa: BLE001
        return None, time.time() - t0, f"{type(e).__name__}: {str(e)[:160]}"


def fm(ds: str, code: str | None, a: str, z: str) -> list | None:
    did = f"&data_id={code}" if code else ""
    b, dt, st = get(FM.format(ds=ds, did=did, a=a, z=z), timeout=90)
    if b is None:
        p(f"FinMind {ds} {code or '（全部）'} {a}～{z} ✗ {st}（{dt:.1f}s）")
        return None
    try:
        doc = json.loads(b.decode("utf-8"))
    except Exception as e:                                    # noqa: BLE001
        p(f"FinMind {ds} {code} 不是 JSON：{e}；開頭 {b[:200]!r}")
        return None
    rows = doc.get("data") or []
    p(f"FinMind {ds} {code or '（全部）'} {a}～{z}：status={doc.get('status')} msg={str(doc.get('msg'))[:80]} "
      f"{len(rows)} 列（{dt:.1f}s，{len(b) // 1024} KB）")
    return rows


def span(rows: list | None, key: str = "date") -> str:
    if not rows:
        return "—"
    ds = sorted(str(r.get(key)) for r in rows if r.get(key))
    return f"{ds[0]}～{ds[-1]}" if ds else "—"


def finmind_part() -> None:
    p("── FinMind ──")
    r = fm("TaiwanStockMarginPurchaseShortSale", "2330", "2000-01-01", "2001-03-31")
    if r:
        p("融資 2330 最早：", span(r), "欄位：", sorted(r[0].keys()))
        p("第一列：", json.dumps(r[0], ensure_ascii=False)[:400])
    r = fm("TaiwanStockMarginPurchaseShortSale", "2330", "2026-10-13", "2026-10-20")
    shard = ROOT / "data/lab/mkt/2026-10-20.json.gz"
    off = None
    if shard.exists():
        j = json.loads(gzip.open(shard).read())
        off = (j.get("m_tw") or {}).get("2330")
    if r:
        last = sorted(r, key=lambda x: x["date"])[-1]
        p("融資 2330 10/20 FinMind：", {k: last.get(k) for k in ("date", "MarginPurchaseTodayBalance", "MarginPurchaseYesterdayBalance",
                                                                "ShortSaleTodayBalance")}, "｜官方分片 m_tw[2330]＝", off)
    r = fm("TaiwanStockPrice", "2330", "2001-01-01", "2001-01-31")
    if r:
        p("股價 2330 2001-01：", span(r), "欄位：", sorted(r[0].keys()), "第一列：", json.dumps(r[0], ensure_ascii=False)[:300])
    r = fm("TaiwanStockPrice", "2330", "1994-01-01", "2000-12-31")
    if r:
        p("股價 2330 最早：", span(r))
    dl = fm("TaiwanStockDelisting", None, "1990-01-01", "2026-10-21")
    if dl:
        p("下市櫃表欄位：", sorted(dl[0].keys()), "日期範圍：", span(dl))
        p("前 3 列：", json.dumps(dl[:3], ensure_ascii=False)[:500])
        by_y: dict = {}
        for x in dl:
            y = str(x.get("date") or "")[:4]
            by_y[y] = by_y.get(y, 0) + 1
        p("每年下市櫃檔數：", dict(sorted(by_y.items())))
    info = fm("TaiwanStockInfo", None, "1990-01-01", "2026-10-21")
    if info:
        ty: dict = {}
        for x in info:
            ty[str(x.get("type"))] = ty.get(str(x.get("type")), 0) + 1
        ids = {str(x.get("stock_id")) for x in info}
        four = [i for i in ids if len(i) == 4 and i.isdigit()]
        p("台股總覽欄位：", sorted(info[0].keys()), "type 分布：", ty, "不重複代號", len(ids), "四碼數字", len(four))
    for code in ("2325", "3474", "2311", "1262"):
        m = fm("TaiwanStockMarginPurchaseShortSale", code, "2001-01-01", "2026-10-21")
        px = fm("TaiwanStockPrice", code, "2001-01-01", "2026-10-21")
        p(f"已下市 {code}：融資 {len(m or [])} 列 {span(m)}；股價 {len(px or [])} 列 {span(px)}")
    tot = fm("TaiwanStockTotalMarginPurchaseShortSale", None, "2026-10-20", "2026-10-20")
    if tot:
        p("融資融券合計 10/20：", json.dumps(tot, ensure_ascii=False)[:800])
    one = fm("TaiwanStockMarginPurchaseShortSale", None, "2026-10-20", "2026-10-20")
    p("不帶代號、只抓一天：", len(one or []), "列")
    t0, n = time.time(), 0
    for code in ("2317", "2454", "2303"):
        if fm("TaiwanStockMarginPurchaseShortSale", code, "2001-01-01", "2026-10-21") is not None:
            n += 1
    p(f"逐檔全部歷史 3 檔：{time.time() - t0:.1f}s（成功 {n}）")


def official_lists() -> None:
    p("── 證交所／櫃買終止上市櫃名單 ──")
    for lbl, url in (("證交所終止上市", "https://www.twse.com.tw/rwd/zh/company/suspendListing?response=json"),
                     ("櫃買終止上櫃", "https://www.tpex.org.tw/www/zh-tw/company/suspendListing?response=json")):
        b, dt, st = get(url)
        if b is None:
            p(lbl, "✗", st)
            continue
        try:
            doc = json.loads(b.decode("utf-8"))
        except Exception:                                     # noqa: BLE001
            p(lbl, "不是 JSON，開頭", b[:200])
            continue
        rows = doc.get("data") or (doc.get("tables") or [{}])[0].get("data") or []
        p(lbl, f"{len(rows)} 列（{dt:.1f}s）欄位：", doc.get("fields") or (doc.get("tables") or [{}])[0].get("fields"),
          "前 2 列：", json.dumps(rows[:2], ensure_ascii=False)[:300], "最後 2 列：", json.dumps(rows[-2:], ensure_ascii=False)[:300])


def us_part() -> None:
    p("── 美股漲跌家數 ──")
    for f in ("NYSE_advn.csv", "NYSE_decln.csv", "NYSE_unchn.csv", "NYSE_upvol.csv", "NYSE_dnvol.csv"):
        b, dt, st = get("https://unicorn.us.com/advdec/" + f)
        if b is None:
            p("unicorn", f, "✗", st)
        else:
            lines = b.decode("utf-8", "replace").splitlines()
            p("unicorn", f, f"{len(lines)} 行", "開頭", lines[:3], "結尾", lines[-2:])
    from arm.lab import fwdfetch as FF
    try:
        html = FF._get(FF.WIKI_SP, timeout=90).decode("utf-8", "replace")
        sp = FF.parse_wiki_sp(html)
        p("維基 S&P 500 成分股：", len(sp), sp[:5])
    except Exception as e:                                    # noqa: BLE001
        p("維基 S&P 500 ✗", e)
    for sym in ("AAPL", "KO", "BRK-B", "GE"):
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
               f"?period1=631152000&period2={int(time.time())}&interval=1d")
        b, dt, st = get(url, timeout=60)
        if b is None:
            p("Yahoo", sym, "✗", st)
            continue
        try:
            res = json.loads(b.decode("utf-8"))["chart"]["result"][0]
            ts = res.get("timestamp") or []
            p("Yahoo", sym, f"{len(ts)} 天", time.strftime("%Y-%m-%d", time.gmtime(ts[0])) if ts else "—", f"（{dt:.1f}s）")
        except Exception as e:                                # noqa: BLE001
            p("Yahoo", sym, "解析 ✗", e)
    b, dt, st = get("https://api.github.com/repos/fja05680/sp500/contents", headers={"Accept": "application/vnd.github+json"})
    if b is None:
        p("fja05680/sp500 ✗", st)
    else:
        try:
            names = [x.get("name") for x in json.loads(b.decode("utf-8"))]
            p("fja05680/sp500 檔案：", names)
        except Exception as e:                                # noqa: BLE001
            p("fja05680/sp500 解析 ✗", e)


def main() -> None:
    for fn in (finmind_part, official_lists, us_part):
        try:
            fn()
        except Exception as e:                                # noqa: BLE001
            p(fn.__name__, "✗", type(e).__name__, e)


if __name__ == "__main__":
    main()
