#!/usr/bin/env python3
"""研究用網頁探針（只在 CI 跑；容器 proxy 擋多數外站）：用 headless Chrome 打開 .ping/web 列的網址，
存頁面文字、標題大綱、站內連結、分段截圖與 JSON 回應摘要到 .probe/web/，再由 workflow commit 回分支。

只讀公開頁面、每個網址開一次；結果只供分析版面架構，看完即刪（不進 main）。
"""
import json
import re
import sys
from pathlib import Path

OUT = Path(".probe/web")
CHUNK = 1800          # 每張截圖高度（px）
MAX_CHUNKS = 14


def slug(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1]).strip("_")[:80]


def main() -> int:
    from playwright.sync_api import sync_playwright

    urls = [u.strip() for u in Path(".ping/web").read_text(encoding="utf-8").splitlines()
            if u.strip().startswith("http")]
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            br = p.chromium.launch(channel="chrome")
        except Exception:                                  # noqa: BLE001
            br = p.chromium.launch()
        for url in urls:
            s = slug(url)
            ctx = br.new_context(viewport={"width": 1280, "height": 900}, locale="zh-TW",
                                 user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                            "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
            page = ctx.new_page()
            net = []

            def on_resp(r):
                try:
                    ct = r.headers.get("content-type", "")
                    if "json" in ct or "/api/" in r.url:
                        body = r.text()
                        net.append({"url": r.url, "status": r.status, "ct": ct, "n": len(body), "head": body[:4000]})
                except Exception:                          # noqa: BLE001
                    pass

            page.on("response", on_resp)
            try:
                page.goto(url, wait_until="networkidle", timeout=90000)
            except Exception as e:                         # noqa: BLE001
                print(f"[probe] {url} goto: {type(e).__name__}: {e}")
            # 慢慢捲到底，觸發延遲載入的區塊
            for _ in range(40):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(400)
            page.wait_for_timeout(2500)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(800)
            txt = page.evaluate("document.body.innerText")
            heads = page.evaluate("""[...document.querySelectorAll('h1,h2,h3,h4,[role=tab],button')]
                .map(e=>e.tagName+' | '+(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,90))
                .filter(x=>x.split(' | ')[1])""")
            links = page.evaluate("""[...new Set([...document.querySelectorAll('a[href]')]
                .map(a=>a.getAttribute('href')))]""")
            (OUT / f"{s}.txt").write_text(txt, encoding="utf-8")
            (OUT / f"{s}.heads.txt").write_text("\n".join(heads), encoding="utf-8")
            (OUT / f"{s}.links.txt").write_text("\n".join(x for x in links if x), encoding="utf-8")
            (OUT / f"{s}.net.json").write_text(json.dumps(net, ensure_ascii=False, indent=1), encoding="utf-8")
            html = page.content()
            (OUT / f"{s}.html").write_text(html, encoding="utf-8")
            h = page.evaluate("document.documentElement.scrollHeight")
            n = min(MAX_CHUNKS, (h + CHUNK - 1) // CHUNK)
            for i in range(n):
                page.screenshot(path=str(OUT / f"{s}.{i:02d}.png"), full_page=True,
                                clip={"x": 0, "y": i * CHUNK, "width": 1280, "height": min(CHUNK, h - i * CHUNK)})
            print(f"[probe] {url}: 文字 {len(txt)} 字、標題 {len(heads)}、連結 {len(links)}、JSON 回應 {len(net)}、"
                  f"頁高 {h}px → {n} 張截圖、HTML {len(html)} 字")
            ctx.close()
        br.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
