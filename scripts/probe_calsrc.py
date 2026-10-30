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


# ── 勞工部：季調初領失業金（第二輪：claims.asp 的 wkclaim 表單送到 wkclaims/report.asp） ─────────────

def dol_form():
    s = _get("https://oui.doleta.gov/unemploy/claims.asp", timeout=60).decode("utf-8", "replace")
    for m in re.finditer(r"strtdate|enddate", s):
        print("  ctx:", re.sub(r"\s+", " ", s[max(0, m.start() - 160):m.start() + 160])[:320])
        break
    for js in re.findall(r"<script[^>]*>(.*?)</script>", s, re.S | re.I):
        if re.search(r"strtdate|option|final_yr", js):
            print("  js:", re.sub(r"\s+", " ", js)[:500])
    url = "https://oui.doleta.gov/unemploy/wkclaims/report.asp"
    for ft in ("xml", "html"):
        form = {"level": "us", "final_yr": "2027", "strtdate": "2026", "enddate": "2026", "filetype": ft, "submit": "Submit"}
        try:
            r = post_form(url, form)
            print(f"POST {ft}", len(r), "bytes:", r[:200].decode("utf-8", "replace").replace("\n", " "))
            if ft == "xml":
                print("  tail:", r[-900:].decode("utf-8", "replace").replace("\n", " "))
            else:
                print("  text tail:", text(r, 100000)[-900:])
        except Exception as ex:                               # noqa: BLE001
            print(f"POST {ft} ✗", str(ex)[:150])


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
        b = _get(hit[0][1].replace("//press", "/press"), timeout=60)
        t = text(b, 10 ** 6)
        print("  page", len(b), "bytes, text", len(t))
        for m in list(re.finditer(r"[^.]*(?:deposit facility|interest rates? (?:unchanged|by)|decided to)[^.]*\.", t, re.I))[:4]:
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
            print("       first:", ln[1][:200] if len(ln) > 1 else "")
            for x in ln[-2:]:
                print("      ", x[:200])
    try:
        h = _get("https://opendata.customs.gov.tw/", timeout=60).decode("utf-8", "replace")
        print("customs home", len(h), "bytes")
        for m in re.finditer(r'href="([^"]+)"[^>]*>([^<]{0,80})<', h):
            if re.search(r"美元|出口|進出口|貿易|data/\\d+", m.group(1) + m.group(2)):
                print("   ", m.group(1)[:80], m.group(2).strip()[:50])
    except Exception as ex:                                   # noqa: BLE001
        print("customs home ✗", str(ex)[:150])
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
        for (it, tp), (tm, v) in seen.items():
            if re.search(r"合計|實質|GDP|國內生產毛額$", it) or "當期價格" not in it:
                print(f"   {it[:60]:60s} | {tp[:10]:10s} | {tm} = {v}")


# ── 普查局：零售銷售 ───────────────────────────────────────────────────────────────

def census():
    for q in ("get=cell_value,data_type_code,category_code,seasonally_adj,time_slot_id&for=us:*&time=from+2026-06",
              "get=cell_value,data_type_code,category_code,seasonally_adj&for=us:*&time=2026",
              "get=cell_value,data_type_code,category_code,seasonally_adj&time=2026"):
        try:
            b = _get(f"https://api.census.gov/data/timeseries/eits/marts?{q}", timeout=60)
            print(q[:40], "raw", len(b), "bytes:", b[:300].decode("utf-8", "replace").replace("\n", " "))
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
    run("勞工部 claims.asp 表單", dol_form)
    run("歐洲央行", ecb)
    run("財政部 出口（data.gov.tw）", mof)
    run("主計總處 GDP XML", dgbas)
    run("普查局 零售銷售", census)
