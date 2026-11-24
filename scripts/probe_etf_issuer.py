#!/usr/bin/env python3
"""探針：etfinfo 固定晚一個交易日的主動式台股 ETF，投信官網當天晚上有沒有完整持股（只印、不落檔）。

使用者 2026-11-24 選「先試一輪抓官網」（推翻 2026-07-29「不抓官網、用彙整站」之前的一輪探測；wiki/main/etf-holdings.md）。
只在 CI 跑（本容器擋投信官網）：.github/workflows/etf_holdings.yml 探針模式。每一檔印一行：
  官網拿到幾檔、從哪個網址（XHR 就是之後可以改純 HTTP 的 API）、頁面上看得到的最新日期、
  和目前落檔（etfinfo）那一份比：共同幾檔、股數不同幾檔（不同＝官網比較新）。
另外替本家 00409A 找復華官網 assetsExcel 的基金代號（config/products.json 只有 ETF23～25）。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock                                    # noqa: E402
from arm.connectors.issuers import pcf                   # noqa: E402

import fetch_etf_holdings_browser as B                   # noqa: E402  —— 同資料夾；重用列表頁自尋、導頁與攔截

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {"00980A": "野村", "00985A": "野村", "00999A": "野村", "00982A": "群益", "00992A": "群益",
           "00984A": "安聯", "00993A": "安聯", "00987A": "台新", "00994A": "第一金", "00408A": "第一金"}
_D_AD = re.compile(r"(20\d{2})[/\-.年](\d{1,2})[/\-.月](\d{1,2})")
_D_ROC = re.compile(r"(?<!\d)(1[01]\d)[/\-.年](\d{1,2})[/\-.月](\d{1,2})")


def latest_date(texts: list[str], today: date) -> str | None:
    """文字裡看得到的日期（西元或民國），只收今天往前 30 天內的，回最新的。"""
    best = None
    for t in texts:
        for rx, off in ((_D_AD, 0), (_D_ROC, 1911)):
            for m in rx.finditer(t):
                try:
                    d = date(int(m.group(1)) + off, int(m.group(2)), int(m.group(3)))
                except ValueError:
                    continue
                if today - timedelta(days=30) <= d <= today and (best is None or d > best):
                    best = d
    return best.isoformat() if best else None


def compare(rows: list[dict], cur: dict | None) -> str:
    """官網拿到的持股和目前落檔那一份比：共同幾檔、共同的裡面股數不同幾檔。"""
    if not cur:
        return "落檔沒有這一檔"
    old = {str(h.get("stock_id")): h.get("shares") for h in cur.get("holdings") or []}
    new = {str(r.get("stock_id")): r.get("shares") for r in rows}
    both = [c for c in new if c in old]
    diff = [c for c in both if new[c] is not None and old[c] is not None and abs(float(new[c]) - float(old[c])) > 0.5]
    return f"和落檔（{cur.get('src')} {cur.get('date')}）比：共同 {len(both)}／{len(new)} 檔、股數不同 {len(diff)} 檔"


def _open(page, url: str) -> tuple[list[dict], str, list[str], list[str]]:
    """B._from_page 加上：攔到的文字與渲染後頁面文字（找日期用）。"""
    texts: list[str] = []

    def keep(resp):
        try:
            ct = (resp.headers or {}).get("content-type", "")
            if "json" in ct or "text" in ct:
                texts.append(resp.body().decode("utf-8", "replace")[:400_000])
        except Exception:                                 # noqa: BLE001
            pass

    page.on("response", keep)
    rows, how, log = B._from_page(page, url)
    try:
        texts.append(page.inner_text("body")[:200_000])
    except Exception:                                     # noqa: BLE001
        pass
    return rows, how, log, texts


def browser_round(today: date, cur: dict) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠ 沒有 playwright，略過官網探測")
        return
    names = {}
    try:
        from arm import etfwatch
        names = {c: n for c, n, *_ in etfwatch.WATCHLIST}
    except Exception:                                     # noqa: BLE001
        pass
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--disable-dev-shm-usage"])
        for code, issuer in TARGETS.items():
            urls = [u for _n, u in pcf._cands(code, issuer)]
            home = B.ISSUER_HOME.get(issuer)
            got, how, logs, texts, used = [], "", [], [], ""
            if home:
                ctx = br.new_context(user_agent=pcf._UA["User-Agent"], viewport={"width": 1280, "height": 900})
                found = B._discover(ctx.new_page(), home, code, names.get(code, ""), issuer)
                ctx.close()
                logs.append(f"自尋 {home} → {len(found)} 個連結")
                urls += [u for u in found if u not in urls]
            for url in urls[:5]:
                ctx = br.new_context(user_agent=pcf._UA["User-Agent"], viewport={"width": 1280, "height": 900})
                rows, h, log, tx = _open(ctx.new_page(), url)
                ctx.close()
                logs += [f"[{url[:80]}] {x}" for x in log]
                texts += tx
                if rows:
                    got, how, used = rows, h, url
                    break
            d = latest_date(texts, today)
            if got:
                print(f"  ✓ {code}（{issuer}）官網 {len(got)} 檔｜{how[:140]}｜頁面 {used[:100]}｜頁面上最新日期 {d}｜{compare(got, cur.get(code))}")
                print(f"      樣本：{pcf.sample_rows(got)}")
            else:
                print(f"  ✗ {code}（{issuer}）官網拿不到完整持股｜頁面上最新日期 {d}")
                for x in logs[:8]:
                    print(f"      · {x[:300]}")
        br.close()


def fhtrust_scan(today: date, cur: dict) -> None:
    """本家 00409A 主動復華全球未來50：在 ETF20～ETF40 裡找持股和落檔那一份最像的基金代號。"""
    from arm.connectors import fhtrust
    ref = {str(h.get("stock_id")) for h in (cur.get("00409A") or {}).get("holdings") or []}
    print(f"[復華官網] 找 00409A 的基金代號（落檔那一份 {len(ref)} 檔）")
    days = [today - timedelta(days=k) for k in range(0, 6)]
    for n in range(20, 41):
        fid = f"ETF{n}"
        for d in days:
            try:
                r = fhtrust.fetch_holdings(fid, d.isoformat())
            except Exception as e:                        # noqa: BLE001
                last = f"{type(e).__name__}: {str(e)[:60]}"
                continue
            ids = {str(h.get("stock_id")) for h in r.get("holdings") or []}
            hit = len(ids & ref)
            print(f"  {fid}：{d}｜檔案日 {r.get('date')}｜{len(ids)} 列｜和 00409A 共同 {hit} 檔｜前 3：{sorted(ids)[:3]}")
            break
        else:
            print(f"  {fid}：近 6 天都拿不到（{last}）")


def main() -> int:
    today = clock.today_tw()
    try:
        cur = json.loads((ROOT / "data" / "etf_holdings.json").read_text(encoding="utf-8")).get("etfs") or {}
    except Exception:                                     # noqa: BLE001
        cur = {}
    print(f"[官網探針] {clock.now_tw():%Y-%m-%d %H:%M}，{len(TARGETS)} 檔＋00409A")
    for c in list(TARGETS) + ["00409A"]:
        e = cur.get(c) or {}
        print(f"  落檔 {c}：{e.get('src')} {e.get('date')}")
    fhtrust_scan(today, cur)
    browser_round(today, cur)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
