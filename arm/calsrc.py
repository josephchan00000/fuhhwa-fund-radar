"""行事曆官方來源（docs/macrocal_fill_plan.md 第三段）：只有行事曆補值（arm/calfill.py）用得到的官方序列。

景氣頁的序列照舊由 fetch_heat*.py 每天抓；這裡的只在「最新一份行事曆有列等著它」的時候才抓（calfill.wanted，
scripts/run_calfill.py 先抓再補）——那一期抓到了就不再抓。存法同景氣頁（data/lab/heat/，CI 的 commit 已包含）：
  · 勞工統計局（API v1，不用金鑰，一次一個請求）：非農、平均時薪、季調 CPI、PPI、JOLTS、ECI → us_bls_cal
  · 歐洲央行：決議新聞稿（RSS 找最新的「Monetary policy decisions」）＋存款利率每日序列（會前水準）→ ecb_dec
  · 主計總處：實質 GDP 年增（和景氣頁 twgdp 同一支 XML，heatfetch_us.twgdp 一起存）→ twgdp_yoy
探針（scripts/probe_calsrc.py，2026-10-30）確認抓不到或對不上的不接：勞工部初領失業金（新聞稿 403、資料檔晚三週）、
財政部出口（開放資料只有新臺幣、晚一個半月）、普查局零售銷售（要金鑰）。
"""
from __future__ import annotations

import html
import re
import time
from datetime import date, datetime, timedelta

from .http import get_bytes
from .lab import heatdata as HD
from .lab.heatfetch import BLS, BROWSER, _merge, _post_json

BUDGET_S = 120          # 開始抓下一個來源之前已經花了這麼久就先不抓（CI 那一步 timeout 300 秒，不能讓抓取吃掉補值）


def _get(url: str) -> bytes:
    return get_bytes(url, retries=1, timeout=30, use_cache=False, headers=BROWSER)

# 序列代號：非農（季調，千人）、平均時薪（季調；年增也用季調，和新聞稿一致）、CPI／核心 CPI（季調，算月增）、
# PPI 最終需求（季調算月增、未季調算年增）、JOLTS 職缺（季調，千）、ECI 季增（季調）、ECI 年增（未季調）
BLS_CAL = ("CES0000000001", "CES0500000003", "CUSR0000SA0", "CUSR0000SA0L1E", "WPSFD4", "WPUFD4",
           "JTS000000000000000JOL", "CIS1010000000000Q", "CIU1010000000000A")


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_bls(doc: dict) -> dict:
    """→ {YYYY-MM 或 YYYY-Qn: {序列代號: 值}}（年平均 M13 不收）。"""
    out: dict = {}
    for s in ((doc.get("Results") or {}).get("series")) or []:
        sid = s.get("seriesID")
        if sid not in BLS_CAL:
            continue
        for r in s.get("data") or []:
            p, v = str(r.get("period") or ""), _num(r.get("value"))
            m, q = re.match(r"^M(0[1-9]|1[0-2])$", p), re.match(r"^Q0([1-4])$", p)
            k = f"{r.get('year')}-{m.group(1)}" if m else f"{r.get('year')}-Q{q.group(1)}" if q else None
            if k and v is not None:
                out.setdefault(k, {})[sid] = v
    return out


def bls_cal(today: date) -> int:
    doc = _post_json(BLS, {"seriesid": list(BLS_CAL), "startyear": str(today.year - 1), "endyear": str(today.year)})
    if doc.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS {doc.get('status')} {str(doc.get('message'))[:120]}")
    old = HD.load("us_bls_cal")
    return _merge("us_bls_cal", "bls", {k: {**(old.get(k) or {}), **v} for k, v in parse_bls(doc).items()})


# ── 歐洲央行 ─────────────────────────────────────────────────────────────────────

ECB_RSS = "https://www.ecb.europa.eu/rss/press.html"
ECB_DFR = ("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
           "?format=csvdata&startPeriod={a}")
_FAC = re.compile(r"deposit facility|main refinancing operations|marginal lending facility", re.I)
_VERB = re.compile(r"will (remain unchanged at|be (?:increased|raised|decreased|lowered|reduced|cut) to)", re.I)


def parse_ecb_text(t: str) -> tuple[float, str] | None:
    """新聞稿全文 → (存款利率, 'hold'|'up'|'down')。三種利率的順序照句子裡的寫法對（2024 年以前先寫主要再融資）。"""
    for m in re.finditer(r"interest rates on the ", t):
        seg = t[m.end():m.end() + 400]
        v = _VERB.search(seg)
        if not v:
            continue
        names = [x.lower() for x in _FAC.findall(seg[:v.start()])]
        rates = re.findall(r"(-?\d+(?:\.\d+)?)\s*%", seg[v.end():v.end() + 80])[:3]
        if len(names) != 3 or len(rates) != 3 or "deposit facility" not in names:
            continue
        w = v.group(1).lower()
        kind = "hold" if "unchanged" in w else "up" if re.search(r"increased|raised", w) else "down"
        return float(rates[names.index("deposit facility")]), kind
    return None


def parse_dfr(csv: str) -> dict:
    lines = csv.strip().splitlines()
    if not lines:
        return {}
    h = lines[0].split(",")
    i, j = h.index("TIME_PERIOD"), h.index("OBS_VALUE")
    out = {}
    for ln in lines[1:]:
        c = ln.split(",")
        v = _num(c[j]) if len(c) > j else None
        if v is not None:
            out[c[i]] = v
    return out


def ecb_decision(text_: str, day: str, dfr: dict) -> list | None:
    """新聞稿＋存款利率序列 → [會後存款利率, 變動（百分點）]；兩邊對不上（維持卻和會前不同、方向不符、不是 1 碼倍數）→ None。"""
    got = parse_ecb_text(text_)
    pre = [dfr[k] for k in sorted(dfr) if k <= day]
    if not got or not pre:
        return None
    rate, kind = got
    chg = round(rate - pre[-1], 4)
    if (kind == "hold") != (chg == 0) or (kind == "up" and chg <= 0) or (kind == "down" and chg >= 0):
        return None
    if abs(chg / 0.25 - round(chg / 0.25)) > 1e-6:
        return None
    return [rate, chg]


def ecb(today: date) -> int:
    s = _get(ECB_RSS).decode("utf-8", "replace")
    dfr = parse_dfr(_get(ECB_DFR.format(a=(today - timedelta(days=120)).isoformat())).decode("utf-8", "replace"))
    new = {}
    for it in re.findall(r"<item>(.*?)</item>", s, re.S):
        title = html.unescape((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1])
        if not re.search(r"^\s*monetary policy decisions\s*$", title, re.I):
            continue
        link = (re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1].strip().replace("//press", "/press")
        pub = (re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or [None, ""])[1].strip()
        try:
            day = datetime.strptime(pub[:16], "%a, %d %b %Y").date().isoformat()
        except ValueError:
            continue
        page = html.unescape(re.sub(r"<[^>]+>", " ", _get(link).decode("utf-8", "replace")))
        got = ecb_decision(re.sub(r"\s+", " ", page), day, dfr)
        if got:
            new[day] = got
        break                                                   # 只看最新一次決議
    return _merge("ecb_dec", "ecb", new)


def twgdp(today: date) -> int:
    from .lab import heatfetch_us as U
    return U.twgdp(timeout=90)


FETCH = {"bls_cal": bls_cal, "ecb": ecb, "twgdp": twgdp}


def fetch(keys, today: date) -> list[str]:
    """抓這幾個來源；每個各自 try，失敗只記一行（不擋補值、不擋發佈）。"""
    log, t0 = [], time.time()
    for k in sorted(keys):
        if time.time() - t0 > BUDGET_S:
            log.append(f"{k} 略過（時間到，下一班再抓）")
            continue
        try:
            log.append(f"{k} ✓ {FETCH[k](today)} 筆更新")
        except Exception as ex:                                 # noqa: BLE001
            log.append(f"{k} ✗ {type(ex).__name__}: {str(ex)[:120]}")
    return log
