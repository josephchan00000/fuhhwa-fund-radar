#!/usr/bin/env python3
"""行事曆官方來源探針（docs/macrocal_fill_plan.md 第三段）：只印不寫。

容器擋官方站，所以在 CI 跑（lab_backfill.yml，.ping/lab 第一行寫 calprobe）。逐一印出抓不抓得到、格式、最新幾筆，
看過再決定哪些接進 arm/calfill.py：勞工統計局多幾條序列、勞工部季調初領失業金、歐洲央行利率、財政部出口、
主計總處 GDP 年增、普查局零售銷售。每段各自 try，一段壞了不影響其他段。"""
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm.http import _CTX  # noqa: E402
from arm.lab.heatfetch import BROWSER, BLS, _get, _post_json, _twca_ctx  # noqa: E402


def sec(t):
    print(f"\n===== {t} =====", flush=True)


def text(b: bytes, n: int = 600) -> str:
    s = b.decode("utf-8", "replace")
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()[:n]


def post_form(url: str, form: dict, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), headers={
        **BROWSER, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.read()


def run(name, fn):
    sec(name)
    try:
        fn()
    except Exception as ex:                                   # noqa: BLE001
        print(f"✗ {type(ex).__name__}: {str(ex)[:200]}")


# ── 勞工統計局：非農、時薪、季調 CPI、PPI、JOLTS、ECI ─────────────────────────────

BLS_TRY = ["CES0000000001", "CES0500000003", "CUSR0000SA0", "CUSR0000SA0L1E",
           "WPSFD4", "WPUFD4", "WPSFD4131", "WPUFD4131", "WPSFD49116", "WPUFD49116",
           "JTS000000000000000JOL", "CIS1010000000000Q", "CIU1010000000000A", "CIS1020000000000Q"]


def bls():
    doc = _post_json(BLS, {"seriesid": BLS_TRY, "startyear": "2025", "endyear": "2026"})
    print("status", doc.get("status"), str(doc.get("message"))[:200])
    for s in ((doc.get("Results") or {}).get("series")) or []:
        d = s.get("data") or []
        last = [f"{r.get('year')}{r.get('period')}={r.get('value')}"
                f"{'(' + ','.join(f.get('code', '') for f in r.get('footnotes') or [] if f) + ')' if any(r.get('footnotes') or []) else ''}"
                for r in d[:3]]
        print(f"{s.get('seriesID'):24s} n={len(d):3d}  {' '.join(last)}")


# ── 勞工部：季調初領失業金 ─────────────────────────────────────────────────────────

def dol_form():
    b = _get("https://oui.doleta.gov/unemploy/claims.asp", timeout=60)
    s = b.decode("utf-8", "replace")
    print("claims.asp", len(b), "bytes")
    for f in re.findall(r"<form[^>]*>", s, re.I)[:4]:
        print("FORM", f[:200])
    for m in re.finditer(r"<(input|select)[^>]*>", s, re.I):
        print("  ", m.group(0)[:160])
    for m in re.finditer(r"<select[^>]*name=\"?([\w]+)\"?[^>]*>(.*?)</select>", s, re.I | re.S):
        opts = re.findall(r"<option[^>]*value=\"?([^\">]*)\"?", m.group(2), re.I)
        print("  select", m.group(1), opts[:3], "…", opts[-3:])
    links = sorted(set(re.findall(r"href=\"([^\"]+\.(?:csv|xml|xls|xlsx|pdf|asp)[^\"]*)\"", s, re.I)))
    print("links", links[:30])
    act = re.search(r"<form[^>]*action=\"([^\"]+)\"", s, re.I)
    if not act:
        return
    url = urllib.parse.urljoin("https://oui.doleta.gov/unemploy/claims.asp", act.group(1))
    form = {}
    for m in re.finditer(r"<input[^>]*>", s, re.I):
        tag = m.group(0)
        nm = re.search(r"name=\"?([\w]+)", tag, re.I)
        val = re.search(r"value=\"?([^\" >]*)", tag, re.I)
        tp = (re.search(r"type=\"?(\w+)", tag, re.I) or [None, "text"])[1].lower()
        if not nm:
            continue
        v = val.group(1) if val else ""
        if tp == "radio":
            cur = form.get(nm.group(1))
            if cur is None or re.search(r"xml|US|nation", v, re.I):
                form[nm.group(1)] = v
        elif tp in ("hidden", "submit", "text"):
            form.setdefault(nm.group(1), v)
    for m in re.finditer(r"<select[^>]*name=\"?([\w]+)\"?[^>]*>(.*?)</select>", s, re.I | re.S):
        opts = re.findall(r"<option[^>]*value=\"?([^\">]*)\"?", m.group(2), re.I)
        if opts:
            form[m.group(1)] = "2026" if "2026" in opts else opts[-1]
    print("POST", url, form)
    r = post_form(url, form)
    print("resp", len(r), "bytes:", r[:300].decode("utf-8", "replace"))
    print("text:", text(r, 900))


def dol_catalog():
    u = ("https://catalog.data.gov/api/3/action/package_show?id="
         "historical-unemployment-insurance-seasonally-adjusted-and-unadjusted-weekly-claims-data")
    doc = json.loads(_get(u, timeout=60).decode("utf-8"))
    res = ((doc.get("result") or {}).get("resources")) or []
    for r in res[:6]:
        print("res", r.get("format"), r.get("url"), str(r.get("name"))[:60])
    for r in res[:2]:
        if r.get("url"):
            try:
                b = _get(r["url"], timeout=90)
                print("  ", r["url"], len(b), "bytes:", b[:300].decode("utf-8", "replace").replace("\n", " | "))
            except Exception as ex:                           # noqa: BLE001
                print("  ✗", r["url"], str(ex)[:120])


def dol_pdf():
    from pypdf import PdfReader
    b = _get("https://www.dol.gov/ui/data.pdf", timeout=90)
    t = re.sub(r"\s+", " ", PdfReader(io.BytesIO(b)).pages[0].extract_text() or "")
    print("data.pdf", len(b), "bytes")
    for m in re.finditer(r"In the week ending [^.]{0,40}, the advance figure for seasonally adjusted initial claims[^.]*\.[^.]*\.", t):
        print("  ", m.group(0)[:400])
    print("  head:", t[:300])


# ── 歐洲央行：存款利率 ─────────────────────────────────────────────────────────────

def ecb():
    for key in ("FM/B.U2.EUR.4F.KR.DFR.LEV", "FM/D.U2.EUR.4F.KR.DFR.LEV"):
        try:
            b = _get(f"https://data-api.ecb.europa.eu/service/data/{key}?format=csvdata&startPeriod=2025-01-01", timeout=60)
            lines = b.decode("utf-8", "replace").strip().splitlines()
            hdr = lines[0].split(",")
            i, j = hdr.index("TIME_PERIOD"), hdr.index("OBS_VALUE")
            print(key, len(lines) - 1, "rows; last:", [(r.split(",")[i], r.split(",")[j]) for r in lines[-4:]])
        except Exception as ex:                               # noqa: BLE001
            print(key, "✗", str(ex)[:150])
    s = _get("https://www.ecb.europa.eu/rss/press.html", timeout=60).decode("utf-8", "replace")
    items = re.findall(r"<item>(.*?)</item>", s, re.S)
    print("rss items", len(items))
    hit = []
    for it in items:
        t = html.unescape((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1])
        if re.search(r"monetary policy decision", t, re.I):
            hit.append((t.strip(), (re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1].strip(),
                        (re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or [None, ""])[1].strip()))
    for h in hit[:3]:
        print("  ", h)
    if hit:
        t = text(_get(hit[0][1], timeout=60), 6000)
        for m in re.finditer(r"[^.]*(?:deposit facility|key ECB interest rates)[^.]*\.", t, re.I):
            print("  >", m.group(0).strip()[:300])


# ── 財政部：出口（美元） ───────────────────────────────────────────────────────────

def mof():
    doc = json.loads(_get("https://data.gov.tw/api/v2/rest/dataset/6053", timeout=60).decode("utf-8"))
    res = (doc.get("result") or doc).get("distribution") or []
    print("6053", str((doc.get("result") or doc).get("title"))[:60], "dist", len(res))
    for r in res[:6]:
        u = r.get("resourceDownloadUrl") or r.get("downloadURL")
        print("  ", r.get("resourceFormat"), u, str(r.get("resourceDescription"))[:80])
        if u and str(r.get("resourceFormat", "")).upper() == "CSV":
            b = _get(u, timeout=90)
            for enc in ("utf-8-sig", "big5", "cp950"):
                try:
                    ln = b.decode(enc).strip().splitlines()
                    break
                except UnicodeDecodeError:
                    continue
            print("     ", len(ln), "lines; head:", ln[0][:200])
            for x in ln[-2:]:
                print("      ", x[:200])
    try:
        q = urllib.parse.quote("出口")
        s = _get(f"https://data.gov.tw/api/v2/rest/dataset?q={q}&limit=100", timeout=60).decode("utf-8", "replace")
        print("search", len(s), "bytes:", s[:200])
        for m in re.finditer(r'"(?:identifier|title)"\s*:\s*"([^"]*)"', s):
            if re.search(r"出口|進出口|貿易", m.group(1)) or m.group(1).isdigit():
                print("   ", m.group(1)[:60])
    except Exception as ex:                                   # noqa: BLE001
        print("search ✗", str(ex)[:150])


# ── 主計總處：GDP（實質、年增） ─────────────────────────────────────────────────────

def dgbas():
    base = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230912/"
    for fn in ("na8103a1q.xml", "na8101a1q.xml", "na8102a1q.xml", "na8104a1q.xml", "na8105a1q.xml", "na8106a1q.xml"):
        try:
            req = urllib.request.Request(base + fn, headers=BROWSER)
            with urllib.request.urlopen(req, timeout=120, context=_twca_ctx()) as r:
                txt = r.read().decode("utf-8", "replace")
        except Exception as ex:                               # noqa: BLE001
            print(fn, "✗", str(ex)[:120])
            continue
        seen: dict = {}
        for blk in re.findall(r"<Obs>(.*?)</Obs>", txt, re.S):
            it = (re.search(r"<Item>(.*?)</Item>", blk) or [None, "?"])[1].strip()
            tp = (re.search(r"<TYPE>(.*?)</TYPE>", blk) or [None, "?"])[1].strip()
            tm = (re.search(r"<TIME_PERIOD>(.*?)</TIME_PERIOD>", blk) or [None, "?"])[1].strip()
            v = (re.search(r"<Item_VALUE>(.*?)</Item_VALUE>", blk) or [None, "?"])[1].strip()
            k = (it, tp)
            if k not in seen or tm > seen[k][0]:
                seen[k] = (tm, v)
        print(fn, len(txt), "bytes;", len(seen), "item×type")
        for (it, tp), (tm, v) in list(seen.items())[:40]:
            print(f"   {it[:46]:46s} | {tp[:10]:10s} | {tm} = {v}")


# ── 普查局：零售銷售 ───────────────────────────────────────────────────────────────

def census():
    for q in ("get=cell_value,data_type_code,category_code,seasonally_adj,time_slot_id&for=us:*&time=from+2026-06",
              "get=cell_value,data_type_code,category_code,seasonally_adj&time=from+2026-06"):
        try:
            b = _get(f"https://api.census.gov/data/timeseries/eits/marts?{q}", timeout=60)
            rows = json.loads(b.decode("utf-8"))
            print(q[:40], "rows", len(rows), "hdr", rows[0])
            h = rows[0]
            keep = [r for r in rows[1:] if r[h.index("category_code")] == "44X72"]
            print("   data_type_codes", sorted({r[h.index("data_type_code")] for r in rows[1:]})[:20])
            for r in sorted(keep, key=lambda r: r[h.index("time")] if "time" in h else "")[-8:]:
                print("   ", r)
            break
        except Exception as ex:                               # noqa: BLE001
            print(q[:40], "✗", str(ex)[:150])


if __name__ == "__main__":
    run("勞工統計局（BLS v1）", bls)
    run("勞工部 claims.asp 表單", dol_form)
    run("勞工部 data.gov 目錄", dol_catalog)
    run("勞工部 data.pdf", dol_pdf)
    run("歐洲央行", ecb)
    run("財政部 出口（data.gov.tw）", mof)
    run("主計總處 GDP XML", dgbas)
    run("普查局 零售銷售", census)
