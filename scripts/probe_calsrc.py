#!/usr/bin/env python3
"""行事曆官方來源探針（docs/macrocal_fill_plan.md 第三段）：只印不寫補值用的序列。

容器擋官方站，所以在 CI 跑（lab_backfill.yml，.ping/lab 第一行寫 calprobe）；結果寫進 data/lab/_calprobe.txt
（lab_backfill 會 commit 回分支，讀檔比讀 CI 日誌省），看完記得從分支刪掉。2026-10-30 四輪的結論見規劃文件第 8 節：
勞工統計局、歐洲央行、主計總處接上；勞工部初領失業金（新聞稿 403、report.asp 晚三週）、財政部出口（只有新臺幣）、
普查局（要金鑰）不接。每段各自 try，一段壞了不影響其他段。"""
import html
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import calsrc  # noqa: E402
from arm.http import _CTX  # noqa: E402
from arm.lab.heatfetch import BROWSER, BLS, _get, _post_json, _twca_ctx  # noqa: E402


def sec(t):
    print(f"\n===== {t} =====", flush=True)


def text(b: bytes, n: int = 600) -> str:
    s = b.decode("utf-8", "replace")
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()[:n]


def run(name, fn):
    sec(name)
    try:
        fn()
    except Exception as ex:                                   # noqa: BLE001
        print(f"✗ {type(ex).__name__}: {str(ex)[:200]}")


def bls():
    """補值用的序列＋候選（核心 PPI 兩種定義、未季調時薪）各印最新三筆與全部。"""
    ids = list(calsrc.BLS_CAL) + ["WPSFD4131", "WPUFD4131", "WPSFD49116", "WPUFD49116", "CEU0500000003"]
    doc = _post_json(BLS, {"seriesid": ids, "startyear": "2025", "endyear": "2026"})
    print("status", doc.get("status"), str(doc.get("message"))[:200])
    for s in ((doc.get("Results") or {}).get("series")) or []:
        d = s.get("data") or []
        print(f"{s.get('seriesID'):24s} n={len(d):3d}  " + " ".join(f"{r.get('year')}{r.get('period')}={r.get('value')}" for r in d[:3]))
        print("   all:", " ".join(f"{r.get('year')}{r.get('period')}={r.get('value')}" for r in d))


def dol():
    """勞工部全國週資料（claims.asp 的 wkclaim 表單）：最後一個有季調值的週；2026-10-30 晚三週。"""
    form = {"level": "us", "final_yr": "2027", "strtdate": "2026", "enddate": "2026", "filetype": "xml", "submit": "Submit"}
    req = urllib.request.Request("https://oui.doleta.gov/unemploy/wkclaims/report.asp",
                                 data=urllib.parse.urlencode(form).encode(),
                                 headers={**BROWSER, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=90, context=_CTX) as r:
        x = r.read().decode("utf-8", "replace")
    wk = re.findall(r"<weekEnded>(.*?)</weekEnded>\s*<InitialClaims>\s*<NSA>(.*?)</NSA>\s*<SF>(.*?)</SF>\s*<SA>(.*?)</SA>", x)
    have = [w for w in wk if re.search(r"\d", w[3])]
    print("weeks", len(wk), "with SA", len(have), "last:", have[-2:] if have else None)


def ecb():
    dfr = calsrc.parse_dfr(_get(calsrc.ECB_DFR.format(a="2026-01-01"), timeout=60).decode("utf-8", "replace"))
    print("DFR", len(dfr), "days; last", sorted(dfr.items())[-2:])
    s = _get(calsrc.ECB_RSS, timeout=60).decode("utf-8", "replace")
    for it in re.findall(r"<item>(.*?)</item>", s, re.S):
        if re.search(r"<title>\s*Monetary policy decisions\s*</title>", it, re.I):
            link = re.search(r"<link>(.*?)</link>", it, re.S).group(1).strip().replace("//press", "/press")
            pub = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S).group(1).strip()
            print(pub, link, "→", calsrc.parse_ecb_text(text(_get(link, timeout=60), 10 ** 6)))
            break


def dgbas():
    req = urllib.request.Request("https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230912/na8103a1q.xml", headers=BROWSER)
    with urllib.request.urlopen(req, timeout=120, context=_twca_ctx()) as r:
        txt = r.read().decode("utf-8", "replace")
    from arm.lab import heatfetch_us as U
    yoy = U.parse_dgbas_real_yoy(txt)
    print("real GDP yoy", len(yoy), "quarters; last", sorted(yoy.items())[-3:])


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "lab" / "_calprobe.txt"
    with open(out, "w", encoding="utf-8") as fh:
        sys.stdout = fh
        run("勞工統計局（BLS v1）", bls)
        run("勞工部 週資料", dol)
        run("歐洲央行", ecb)
        run("主計總處 GDP XML", dgbas)
    sys.stdout = sys.__stdout__
    print("寫入", out, sum(1 for _ in open(out, encoding="utf-8")), "行")
