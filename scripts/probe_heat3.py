#!/usr/bin/env python3
"""景氣溫度頁第三階段的資料來源探針（docs/lab_heat_plan.md 第 13.2 節）：只在 CI 跑、印格式與歷史起點，不寫檔。
第三輪：證期局新聞稿能不能翻到舊月份、央行其他代碼有沒有超額準備。
合併前刪掉。`.ping/lab` 第一行寫 heatprobe 觸發。"""
from __future__ import annotations

import html as _html
import io
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab.heatfetch import BROWSER, _twca_ctx  # noqa: E402

CTX = _twca_ctx()


def q(url: str) -> str:
    return urllib.parse.quote(url, safe=":/?&=%#,+;~")


def get(url: str, timeout: int = 40, data: bytes | None = None, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(q(url), data=data, headers={**BROWSER, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def txt(url: str, **kw) -> str:
    return get(url, **kw).decode("utf-8", "replace")


def say(*a) -> None:
    print(*a, flush=True)


def sec(name: str, fn) -> None:
    say(f"\n===== {name} =====")
    t0 = time.time()
    try:
        fn()
    except Exception as e:                                    # noqa: BLE001
        say(f"✗ {type(e).__name__}: {str(e)[:300]}")
    say(f"（{time.time() - t0:.0f}s）")


def short(x, n=300) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    return s[:n]


def plain(h: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", h)))


def anchors(h: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r'<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', h, re.S | re.I):
        out.append((_html.unescape(m.group(1)), plain(m.group(2)).strip()))
    return out


def attrs(tag: str) -> dict:
    return {k.lower(): _html.unescape(v) for k, v in re.findall(r'([\w:$.-]+)\s*=\s*"([^"]*)"', tag)}


def pdf_text(raw: bytes) -> str:
    try:
        import pypdf
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pypdf"], check=False)
        import pypdf
    return "".join(pg.extract_text() or "" for pg in pypdf.PdfReader(io.BytesIO(raw)).pages)


# ── 第三輪：證期局新聞稿歷史、央行其他代碼 ─────────────────────────────

def sfb_hist() -> None:
    base = "https://www.sfb.gov.tw/ch/home.jsp?id=95&parentpath=0,2"
    h = txt(base)
    forms = re.findall(r"<form\b[^>]*>", h, re.I)
    say("form 標籤", [short(f, 200) for f in forms[:4]])
    js = re.findall(r"function\s+\w*[Pp]age\w*\s*\([^)]*\)\s*\{[^}]{0,300}", h)
    say("分頁 JS", [short(j, 300) for j in js[:3]])
    al = anchors(h)
    items = [(x, t) for x, t in al if "dataserno" in x or "news_view" in x]
    say("新聞項目連結數", len(items), [(t[:24], x[:150]) for x, t in items[:6]])
    for pg in re.findall(r"[^\n]{0,80}(?:page=|pagesize|頁)[^\n]{0,120}", h)[:6]:
        say("  含頁字樣", short(pg.strip(), 220))
    tries = [base + "&mcustomize=news_list.jsp&page=2",
             base + "&mcustomize=news_list.jsp&pagesize=100&page=1",
             base + "&mcustomize=news_list.jsp&keyword=外資新聞稿",
             base + "&mcustomize=news_list.jsp&keyword=外資及陸資投資國內證券情形&pagesize=100",
             "https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2&mcustomize=news_list.jsp&keyword=外資及陸資投資國內證券情形&pagesize=100"]
    for u in tries:
        try:
            t = txt(u)
            a = anchors(t)
            hits = [(tt, x) for x, tt in a if "外資" in tt]
            dates = re.findall(r"1[01][0-9]-[01][0-9]-[0-3][0-9]|20[12][0-9]-[01][0-9]-[0-3][0-9]", plain(t))
            say("試", u[-90:], len(t), "外資連結", len(hits), [(tt[:22], x[-70:]) for tt, x in hits[:5]], "日期", dates[:4], dates[-2:])
        except Exception as e:                                # noqa: BLE001
            say("試", u[-90:], "✗", type(e).__name__, str(e)[:120])
        time.sleep(1)


def cbc_more() -> None:
    t0 = time.time()
    codes = [f"EF{n:02d}M01" for n in range(41, 61)] + [f"EF{n:02d}M02" for n in range(1, 41)] + \
            [f"{p}{n:02d}M01" for p in ("EA", "EB", "EC", "ED", "EE", "EH") for n in range(1, 16)]
    for code in codes:
        if time.time() - t0 > 400:
            say("（時間到）")
            return
        try:
            doc = json.loads(get(f"https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={code}", timeout=25))
        except Exception as e:                                # noqa: BLE001
            if "404" not in str(e):
                say(code, "✗", type(e).__name__, str(e)[:60])
            continue
        data = doc.get("data") or {}
        names = [str((x or {}).get("data") or "") for x in ((data.get("structure") or {}).get("Table1") or [])]
        ds = data.get("dataSets") or []
        say(code, short((doc.get("meta") or {}).get("title"), 40), "｜", "、".join(names)[:300], "｜", len(ds), "列",
            (ds[0][0] if ds and ds[0] else None), "～", (ds[-1][0] if ds and ds[-1] else None))
        time.sleep(0.3)


def main() -> None:
    for name, fn in (("證期局新聞稿歷史", sfb_hist), ("央行其他代碼", cbc_more)):
        sec(name, fn)


if __name__ == "__main__":
    main()
