"""法人預估資料源探針（docs/lab_forward_plan.md F0；只印診斷，結果另寫 data/lab/probe_fcst.txt）。

探：鉅亨網 FactSet 快訊（搜尋／分類／個股新聞清單、內文格式、最早日期）、鉅亨個股頁與新聞頁的
API 路徑（從頁面與 JS 撈）、Yahoo quoteSummary（crumb）能不能讀台股的分析師預估。
本容器 proxy 擋 cnyes／yahoo，只在 CI 跑（.ping/lab 第一行 probefc）。
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi

OUT = Path(__file__).resolve().parent.parent / "data" / "lab" / "probe_fcst.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CTX = ssl.create_default_context(cafile=certifi.where())
CJ = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ),
                                     urllib.request.HTTPSHandler(context=CTX))
LOG: list[str] = []
T0 = time.time()


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def get(url, headers=None, timeout=20):
    h = {"User-Agent": UA, "Accept": "application/json, text/html, */*",
         "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
    h.update(headers or {})
    try:
        with OPENER.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, body, dict(e.headers or {})
    except Exception as e:
        return None, str(e).encode(), {}


def js(b):
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:
        return None


def shape(o, d=0, maxd=3):
    if d > maxd:
        return "…"
    if isinstance(o, dict):
        return "{" + ", ".join(f"{k}: {shape(v, d + 1, maxd)}" for k, v in list(o.items())[:25]) + "}"
    if isinstance(o, list):
        return f"[{len(o)}× " + (shape(o[0], d + 1, maxd) if o else "") + "]"
    if isinstance(o, str):
        return "str" + (f"({o[:40]!r})" if d >= 1 else "")
    return type(o).__name__ + (f"({o})" if isinstance(o, (int, float)) else "")


def find_items(o):
    """找第一個像新聞清單的 list（元素是含 newsId 或 title 的 dict）＋旁邊的分頁欄位。"""
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and ("newsId" in v[0] or "title" in v[0]):
                pg = {kk: o.get(kk) for kk in ("total", "per_page", "current_page", "last_page", "from", "to")
                      if kk in o}
                return v, pg
        for v in o.values():
            r = find_items(v)
            if r:
                return r
    return None


def ts(x):
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(x)))
    except Exception:
        return str(x)


def brief(it):
    return f"{it.get('newsId')} {ts(it.get('publishAt'))} [{it.get('categoryName') or it.get('categoryId')}] {str(it.get('title'))[:90]}"


def probe_list(name, url, show=6):
    st, b, h = get(url)
    o = js(b)
    say(f"\n## {name}\n{url}\n→ HTTP {st}, {len(b)} bytes, json={'是' if o is not None else '否'}")
    if o is None:
        say("  前 300 字：", b[:300].decode("utf-8", "replace").replace("\n", " "))
        return None
    say("  結構：", shape(o, maxd=2)[:600])
    r = find_items(o)
    if not r:
        return o
    items, pg = r
    say(f"  清單 {len(items)} 則，分頁 {pg}")
    say("  第一則欄位：", list(items[0].keys())[:40])
    for it in items[:show]:
        say("   ·", brief(it))
    fs = [it for it in items if "actset" in str(it.get("title", ""))]
    say(f"  其中 FactSet 快訊 {len(fs)} 則")
    for it in fs[:3]:
        say("   ★", brief(it))
        for k in ("summary", "content", "keyword", "market", "stock"):
            if k in it:
                say(f"     {k}：", str(it[k])[:400])
    return o


def search_url(base, q, page, limit=30):
    return base.format(q=urllib.parse.quote(q), page=page, limit=limit)


def oldest_by_bisect(base, q, last_page):
    """二分頁數，印最後幾頁的最早日期（搜尋結果依時間新到舊）。"""
    for p in sorted({1, 2, max(1, last_page // 4), max(1, last_page // 2), max(1, last_page - 1), last_page}):
        st, b, _ = get(search_url(base, q, p))
        o = js(b)
        r = find_items(o) if o is not None else None
        if not r:
            say(f"  第 {p} 頁：HTTP {st}，無清單")
            continue
        items, _ = r
        if items:
            say(f"  第 {p} 頁：{len(items)} 則，{ts(items[0].get('publishAt'))} ～ {ts(items[-1].get('publishAt'))}"
                f"｜{str(items[-1].get('title'))[:60]}")


def scan_paths(name, url, max_js=6):
    """從頁面 HTML 與 JS 撈 API 主機與路徑。"""
    st, b, _ = get(url, {"Accept": "text/html"})
    html = b.decode("utf-8", "replace")
    say(f"\n## {name}\n{url}\n→ HTTP {st}, {len(b)} bytes")
    pat = re.compile(r"(?:https?:)?//[a-z0-9.\-]*cnyes\.com(?:/[A-Za-z0-9_\-./{}:$]*)?|/(?:media|ess|mi|ws|fund|api)/api/v\d/[A-Za-z0-9_\-./{}:$]+")
    found = set(m.group(0) for m in pat.finditer(html))
    for kw in ("factset", "FactSet", "estimate", "consensus", "預估", "分析師", "targetPrice", "目標價"):
        i = html.find(kw)
        if i >= 0:
            say(f"  頁面含「{kw}」：…{html[max(0, i - 120):i + 160]!r}…")
    srcs = re.findall(r'<script[^>]+src="([^"]+\.js)"', html)
    say(f"  script {len(srcs)} 支：", [s.rsplit('/', 1)[-1][:40] for s in srcs][:30])
    seen = 0
    for s in srcs:
        if seen >= max_js:
            break
        u = urllib.parse.urljoin(url, s)
        st2, b2, _ = get(u, {"Accept": "*/*"})
        if not b2 or b2[:1] == b"<":
            continue
        seen += 1
        t = b2.decode("utf-8", "replace")
        for m in pat.finditer(t):
            found.add(m.group(0))
        for kw in ("factset", "estimate", "consensus", "symbolNews", "keyword"):
            for mm in list(re.finditer(kw, t))[:2]:
                say(f"  JS {u.rsplit('/', 1)[-1][:30]} 含「{kw}」：…{t[max(0, mm.start() - 160):mm.start() + 160]!r}…")
    api = sorted(x for x in found if "api" in x or "/v1/" in x)
    say(f"  API 字樣 {len(api)} 個：")
    for x in api[:80]:
        say("   ", x)


def probe_article(nid):
    for url in (f"https://api.cnyes.com/media/api/v1/news/{nid}",
                f"https://news.cnyes.com/api/v1/news/{nid}"):
        st, b, _ = get(url)
        o = js(b)
        say(f"\n## 內文 {nid}\n{url}\n→ HTTP {st}, {len(b)} bytes, json={'是' if o is not None else '否'}")
        if o is None:
            continue
        say("  結構：", shape(o, maxd=2)[:700])
        it = o.get("items", o) if isinstance(o, dict) else o
        if isinstance(it, dict):
            say("  標題：", it.get("title"), "｜", ts(it.get("publishAt")))
            for k in ("market", "stock", "keyword", "categoryName", "summary"):
                if k in it:
                    say(f"  {k}：", str(it[k])[:300])
            c = str(it.get("content", ""))
            say(f"  content {len(c)} 字（原文前 3500）：")
            say(c[:3500])
            return
    # 退回 HTML
    url = f"https://news.cnyes.com/news/id/{nid}"
    st, b, _ = get(url, {"Accept": "text/html"})
    t = b.decode("utf-8", "replace")
    i = t.find("FactSet")
    say(f"  HTML {url} → HTTP {st}, {len(b)} bytes；FactSet 位置 {i}")
    if i >= 0:
        say(t[max(0, i - 500):i + 3000])


def probe_yahoo():
    say("\n## Yahoo quoteSummary（crumb）")
    st, b, h = get("https://fc.yahoo.com", {"Accept": "text/html"})
    say(f"  fc.yahoo.com → HTTP {st}；cookie {len(list(CJ))} 個：{[c.name for c in CJ]}")
    crumb = None
    for host in ("query2", "query1"):
        st, b, _ = get(f"https://{host}.finance.yahoo.com/v1/test/getcrumb", {"Accept": "*/*"})
        say(f"  {host} getcrumb → HTTP {st}：{b[:60]!r}")
        if st == 200 and b and len(b) < 40 and b[:1] != b"{":
            crumb = b.decode().strip()
            break
    if not crumb:
        st, b, _ = get("https://finance.yahoo.com/quote/2330.TW", {"Accept": "text/html"})
        say(f"  finance.yahoo.com/quote → HTTP {st}, {len(b)} bytes；cookie {[c.name for c in CJ]}")
        st, b, _ = get("https://query2.finance.yahoo.com/v1/test/getcrumb", {"Accept": "*/*"})
        say(f"  重試 getcrumb → HTTP {st}：{b[:60]!r}")
        if st == 200 and b and len(b) < 40:
            crumb = b.decode().strip()
    mods = "earningsTrend,financialData,recommendationTrend,upgradeDowngradeHistory,earningsHistory"
    for sym in ("2330.TW", "6274.TW", "6488.TWO", "3017.TW", "8299.TWO", "2002.TW"):
        url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules={mods}"
               + (f"&crumb={urllib.parse.quote(crumb)}" if crumb else ""))
        st, b, _ = get(url)
        o = js(b)
        say(f"\n  {sym} → HTTP {st}, {len(b)} bytes")
        if not o:
            say("   ", b[:300])
            continue
        res = ((o.get("quoteSummary") or {}).get("result") or [None])[0]
        if not res:
            say("   ", str(o)[:400])
            continue
        fd = res.get("financialData") or {}
        g = lambda d, k: (d.get(k) or {}).get("raw") if isinstance(d.get(k), dict) else d.get(k)  # noqa: E731
        say(f"   financialData：分析師 {g(fd, 'numberOfAnalystOpinions')}、預估股價 平均 {g(fd, 'targetMeanPrice')} "
            f"中位 {g(fd, 'targetMedianPrice')} 高 {g(fd, 'targetHighPrice')} 低 {g(fd, 'targetLowPrice')}、"
            f"評等 {fd.get('recommendationKey')} {g(fd, 'recommendationMean')}、幣別 {fd.get('financialCurrency')}")
        for t in ((res.get("earningsTrend") or {}).get("trend") or [])[:4]:
            ee, re_ = t.get("earningsEstimate") or {}, t.get("revenueEstimate") or {}
            et, er = t.get("epsTrend") or {}, t.get("epsRevisions") or {}
            say(f"   trend {t.get('period')} {t.get('endDate')}：EPS 平均 {g(ee, 'avg')} 低 {g(ee, 'low')} 高 {g(ee, 'high')} "
                f"家數 {g(ee, 'numberOfAnalysts')} 成長 {g(ee, 'growth')}｜營收 平均 {g(re_, 'avg')} 家數 {g(re_, 'numberOfAnalysts')}｜"
                f"30 天前 {g(et, '30daysAgo')} 90 天前 {g(et, '90daysAgo')}｜30 天上修 {g(er, 'upLast30days')} 下修 {g(er, 'downLast30days')}")
        rt = ((res.get("recommendationTrend") or {}).get("trend") or [])[:1]
        say("   recommendationTrend：", rt)
        ud = ((res.get("upgradeDowngradeHistory") or {}).get("history") or [])[:3]
        say("   upgradeDowngradeHistory 前 3：", ud)
        time.sleep(0.6)


def main():
    q = "Factset 最新調查"
    bases = {
        "ess keyword": "https://ess.api.cnyes.com/ess/api/v1/news/keyword?q={q}&limit={limit}&page={page}",
        "media search": "https://api.cnyes.com/media/api/v1/search?q={q}&limit={limit}&page={page}",
        "media search news": "https://api.cnyes.com/media/api/v1/search/news?q={q}&limit={limit}&page={page}",
    }
    good = None
    for name, base in bases.items():
        o = probe_list(f"搜尋：{name}", search_url(base, q, 1))
        r = find_items(o) if o is not None else None
        if r and good is None:
            good = (base, r[1])
    if good:
        base, pg = good
        lp = int(pg.get("last_page") or 1)
        say(f"\n## 搜尋分頁：last_page={lp}、total={pg.get('total')}")
        oldest_by_bisect(base, q, lp)
        for q2 in ("Factset 最新調查 6274-TW", "鉅亨速報 Factset 台燿", "目標價調升 Factset -TW"):
            probe_list(f"搜尋「{q2}」", search_url(base, q2, 1), show=8)
    for cat in ("tw_stock", "tw_quo", "tw_stock_news", "headline", "us_stock"):
        probe_list(f"分類 {cat}", f"https://api.cnyes.com/media/api/v1/newslist/category/{cat}?limit=30&page=1", show=4)
    for u in ("https://api.cnyes.com/media/api/v1/newslist/TWS:6274:STOCK/symbolNews?limit=30&page=1",
              "https://ess.api.cnyes.com/ess/api/v1/news/symbol/TWS:6274:STOCK?limit=30&page=1",
              "https://api.cnyes.com/media/api/v1/newslist/TWS:6274:STOCK?limit=30&page=1",
              "https://news.cnyes.com/api/v3/news/category/tw_stock?limit=30"):
        probe_list("個股／其他清單", u, show=6)
    for nid in (6313513, 5139162, 6537409):
        probe_article(nid)
    scan_paths("新聞頁 HTML＋JS", "https://news.cnyes.com/news/id/6313513")
    scan_paths("個股頁 HTML＋JS", "https://www.cnyes.com/twstock/6274", max_js=8)
    probe_yahoo()
    say(f"\n探針結束，{time.time() - T0:.0f} 秒")


if __name__ == "__main__":
    try:
        main()
    finally:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(LOG) + "\n", encoding="utf-8")
        sys.exit(0)
