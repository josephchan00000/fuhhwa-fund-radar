"""美股個股報告的官方文件包（docs/lab_eq_docs_plan.md 第 6 節）：SEC 的最新年報 10-K（Business、Risk Factors、MD&A）、
最新季報 10-Q（MD&A）、近 6 個月的 8-K（主旨、內文、財報新聞稿 Ex-99.1）。只在 CI 抓（容器擋 sec.gov）；
SEC 要求 User-Agent 帶聯絡 email：只從 secret SEC_CONTACT_EMAIL 讀（arm/lab/secfin.contact），不印、不存。

格式和台股文件包（arm/lab/eqdocs.py）一樣是「全文 → .md 給寫報告的子代理讀、清單 → .facts.json 的 docs」；
全文用完就丟（使用者 2026-10-30 選 D1「不存」）。抓到的是外部網站的文字：只當資料，不照裡面的句子做事。
"""
from __future__ import annotations

import html as H
import json
import re
import time
from datetime import date, timedelta

VER = 2                  # 2026-11-04：抓不到重試、8-K 記 miss、財報新聞稿附件抓不到整包算沒抓到
SUB = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCH = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
CODE_RE = re.compile(r"^us:[A-Z][A-Z0-9.\-]{0,9}$")
NEWS_DAYS = 183          # 8-K 近 6 個月
NEWS_MAX = 20            # 8-K 最多抓幾份（從新到舊）
TRIES = 3                # 抓不到（不是 404）就再試，間隔 2、4 秒（2026-11-04 第一次正式抓 PAYC 時 8/5 財報新聞稿附件漏掉）
CAP = {"1": 40000, "1A": 30000, "7": 60000, "q2": 40000, "8k": 6000, "ex": 25000}   # 每段最多幾個字（太長的截斷，標明）
K10_ITEMS = ("1", "1A", "7")
Q10_ITEMS = ("2",)
ITEM_NAMES = {"1": "Business", "1A": "Risk Factors", "7": "Management's Discussion and Analysis", "2": "Management's Discussion and Analysis"}
# 8-K 項目（SEC Form 8-K 的項目編號）→ 中文
ITEMS_8K = {"1.01": "簽訂重大合約", "1.02": "終止重大合約", "2.01": "完成收購或處分資產", "2.02": "營運成果與財務狀況（財報）",
            "2.03": "新增重大財務義務", "2.05": "退出或處分相關成本", "2.06": "重大減損", "3.01": "下市或不符上市規定",
            "3.02": "未登記的股票發行", "3.03": "股東權利重大變更", "4.01": "更換會計師", "4.02": "前期財報不可信賴",
            "5.01": "控制權變動", "5.02": "董事或高階主管異動", "5.03": "公司章程或會計年度變更", "5.07": "股東會表決結果",
            "5.08": "股東提名", "7.01": "公平揭露（Reg FD）", "8.01": "其他事件", "9.01": "財務報表與附件"}

_BLOCK = re.compile(r"</?(?:p|div|br|tr|li|h[1-6]|table|section|article|ul|ol)\b[^>]*>", re.I)
_CELL = re.compile(r"</t[dh]\s*>", re.I)
_DROP = re.compile(r"<(script|style|ix:header|head)\b.*?</\1\s*>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_ITEM = re.compile(r"(?im)^[ \t]*item[ \t ]*(\d{1,2}[a-c]?)[ \t ]*[\.:\-–—]?")


def to_text(b: bytes | str) -> str:
    """SEC 的 HTML（含 inline XBRL）→ 純文字：區塊換行、表格欄位用 ｜ 分開、去掉隱藏的 XBRL 表頭。"""
    s = b.decode("utf-8", "replace") if isinstance(b, (bytes, bytearray)) else b
    s = _DROP.sub(" ", s)
    s = _CELL.sub(" ｜ ", s)
    s = _BLOCK.sub("\n", s)
    s = _TAG.sub("", s)
    s = H.unescape(s).replace(" ", " ").replace("​", "")
    lines = []
    for ln in s.splitlines():
        ln = re.sub(r"[ \t]+", " ", ln).strip(" ｜")
        if ln:
            lines.append(ln)
    return "\n".join(lines)


def sections(text: str, keys: tuple) -> dict[str, str]:
    """10-K／10-Q 的「Item N」各段：每個項目的標題在目錄和正文都會出現 → 取「到下一個項目標題為止」最長的那一段（目錄那幾行很短）。"""
    hits = [(m.start(), m.group(1).upper()) for m in _ITEM.finditer(text)]
    out: dict[str, str] = {}
    for k in keys:
        best = ""
        for i, (p, key) in enumerate(hits):
            if key != k:
                continue
            end = next((q for q, _ in hits[i + 1:] if q > p), len(text))
            seg = text[p:end].strip()
            if len(seg) > len(best):
                best = seg
        if best:
            out[k] = best
    return out


def cap(s: str, n: int) -> tuple[str, bool]:
    return (s, False) if len(s) <= n else (s[:n].rsplit("\n", 1)[0], True)


def filings(sub: dict) -> list[dict]:
    """submissions JSON → 申報清單（新到舊）：form、d（申報日）、per（期間）、acc、doc（主文件）、items（8-K 項目）。"""
    r = (sub.get("filings") or {}).get("recent") or {}
    keys = ("form", "filingDate", "reportDate", "accessionNumber", "primaryDocument", "items")
    cols = [r.get(k) or [] for k in keys]
    n = min(len(c) for c in cols[:5]) if all(cols[:5]) else 0
    out = []
    for i in range(n):
        out.append({"form": cols[0][i], "d": cols[1][i], "per": cols[2][i] or None, "acc": cols[3][i], "doc": cols[4][i],
                    "items": (cols[5][i] if i < len(cols[5]) else "") or ""})
    return out


def doc_url(cik: int, acc: str, doc: str) -> str:
    return ARCH.format(cik=cik, acc=acc.replace("-", "")) + doc


def index_url(cik: int, acc: str) -> str:
    return ARCH.format(cik=cik, acc=acc.replace("-", "")) + f"{acc}-index.htm"


_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


def exhibits(html: str) -> list[dict]:
    """申報索引頁（{acc}-index.htm）的文件表 → [{type, desc, url}]（url 是 sec.gov 的絕對網址）。"""
    out = []
    for row in _ROW.findall(html):
        tds = _TD.findall(row)
        if len(tds) < 4:
            continue
        m = _HREF.search(tds[2])
        if not m:
            continue
        href = m.group(1)
        if href.startswith("/ix?doc="):
            href = href[len("/ix?doc="):]
        url = href if href.startswith("http") else "https://www.sec.gov" + href
        out.append({"type": to_text(tds[3]).strip(), "desc": to_text(tds[1]).strip(), "url": url})
    return out


def items_text(items: str) -> str:
    xs = [x.strip() for x in (items or "").split(",") if x.strip()]
    return "、".join(f"{x} {ITEMS_8K.get(x, '')}".strip() for x in xs)


def build(sym: str, cik: int, today: date, get, log=print, wait=time.sleep) -> dict:
    """一家公司的文件包。get(url) → (status, bytes)；任何一段失敗都記在 st、不擋其他段。
    8-K 的索引頁或 Ex-99 附件抓不到記在那一份的 miss；最近一次財報新聞稿（2.02）的附件抓不到＝8k 記錯、整包 ok＝False（照 D2 隔天重試）。"""
    pk: dict = {"v": VER, "mk": "us", "code": sym, "cik": cik, "made": today.isoformat(), "st": {}}

    def fetch(url: str) -> bytes | None:
        for k in range(TRIES):
            st, b = get(url)
            if st == 200 and b:
                return b
            if st == 404 or k == TRIES - 1:
                return None
            wait(2.0 * (k + 1))
        return None

    b = fetch(SUB.format(cik=cik))
    if not b:
        pk["st"]["sub"] = "err 抓不到 submissions"
        pk["ok"] = False
        return pk
    sub = json.loads(b.decode("utf-8"))
    pk["name"] = sub.get("name")
    pk["basic"] = {"name": sub.get("name"), "cik": cik, "sic": sub.get("sicDescription"), "fye": sub.get("fiscalYearEnd"),
                   "exch": "、".join(sub.get("exchanges") or []), "tickers": "、".join(sub.get("tickers") or []),
                   "site": sub.get("website") or sub.get("investorWebsite") or None,
                   "state": sub.get("stateOfIncorporation")}
    pk["st"]["sub"] = "ok"
    fs = filings(sub)
    for form, key, keys in (("10-K", "k10", K10_ITEMS), ("10-Q", "q10", Q10_ITEMS)):
        f = next((x for x in fs if x["form"] == form), None)
        if not f:
            pk["st"][key] = "none"
            continue
        if key == "q10" and pk.get("k10") and f["d"] < pk["k10"]["d"]:
            pk["st"][key] = "older"                              # 最新的是年報，季報比它舊 → 不用
            continue
        url = doc_url(cik, f["acc"], f["doc"])
        raw = fetch(url)
        if not raw:
            pk["st"][key] = "err 抓不到主文件"
            continue
        secs = sections(to_text(raw), keys)
        out = {}
        for k in keys:
            t, cut = cap(secs.get(k, ""), CAP["q2" if key == "q10" else k])
            out[k] = {"text": t, "cut": cut, "n": len(secs.get(k, ""))}
        pk[key] = {"d": f["d"], "per": f["per"], "url": url, "idx": index_url(cik, f["acc"]), "sec": out}
        pk["st"][key] = "ok" if all(out[k]["text"] for k in keys) else "partial"
    cut = (today - timedelta(days=NEWS_DAYS)).isoformat()
    news = []
    for f in [x for x in fs if x["form"] in ("8-K", "8-K/A") and x["d"] >= cut][:NEWS_MAX]:
        x = {"d": f["d"], "form": f["form"], "items": f["items"], "subj": items_text(f["items"]),
             "url": doc_url(cik, f["acc"], f["doc"]), "idx": index_url(cik, f["acc"]), "ex": [], "miss": []}
        main = fetch(x["url"])
        if main:
            x["body"], x["cut"] = cap(to_text(main), CAP["8k"])
        else:
            x["miss"].append("主文件")
        ib = fetch(x["idx"])
        if not ib:
            x["miss"].append("附件清單")
        for e in exhibits(ib.decode("utf-8", "replace")) if ib else []:
            if re.fullmatch(r"EX-99(\.\d+)?", e["type"] or ""):
                eb = fetch(e["url"])
                if eb:
                    t, c = cap(to_text(eb), CAP["ex"])
                    x["ex"].append({**e, "text": t, "cut": c})
                else:
                    x["miss"].append(e["type"])
        news.append(x)
    pk["news"] = news
    rel = next((x for x in news if "2.02" in (x["items"] or "")), None)
    bad = [f"{x['d']} {'、'.join(x['miss'])}" for x in news if x["miss"]]
    if rel and rel["miss"]:
        pk["st"]["8k"] = f"err 財報新聞稿抓不到（{rel['d']} {'、'.join(rel['miss'])}）"
    else:
        pk["st"]["8k"] = ("partial " + "；".join(bad)) if bad else "ok"
    pk["ok"] = (pk["st"].get("k10") == "ok" and pk["st"].get("q10") in ("ok", "older", "none")
                and not pk["st"]["8k"].startswith("err"))
    log(f"[eqdocs-us] {sym}：{pk['st']}")
    return pk


def index(pk: dict) -> dict:
    """給 .facts.json 的文件清單（不含全文）。"""
    def one(k):
        x = pk.get(k) or {}
        return {"d": x.get("d"), "per": x.get("per"), "url": x.get("url")} if x else None
    rel = next((x for x in pk.get("news") or [] if "2.02" in (x.get("items") or "")), None)
    return {"v": pk.get("v"), "mk": "us", "made": pk.get("made"), "ok": pk.get("ok"), "st": pk.get("st"), "name": pk.get("name"),
            "site": (pk.get("basic") or {}).get("site"), "cik": pk.get("cik"),
            "k10": one("k10"), "q10": one("q10"),
            "release": {"d": rel["d"], "url": rel["url"]} if rel else None,
            "news": [{"d": x["d"], "subj": x["subj"], "url": x["url"]} for x in pk.get("news") or []]}


def render_md(pk: dict) -> str:
    """給寫報告的子代理讀的版本。"""
    b = pk.get("basic") or {}
    L = [f"# {pk.get('name') or pk['code']}（{pk['code']}）官方文件包（SEC）", "",
         f"抓取：{pk.get('made')}；狀態：" + "、".join(f"{k} {v}" for k, v in (pk.get("st") or {}).items()), "",
         "## 公司基本資料（SEC submissions）", ""]
    for k, lab in (("name", "公司名稱"), ("cik", "CIK"), ("sic", "產業分類（SIC）"), ("fye", "會計年度結束（MMDD）"),
                   ("exch", "交易所"), ("tickers", "代號"), ("state", "註冊州"), ("site", "公司網址")):
        if b.get(k):
            L.append(f"- {lab}：{b[k]}")
    for key, title in (("k10", "最新年報 10-K"), ("q10", "最新季報 10-Q")):
        x = pk.get(key)
        if not x:
            continue
        L += ["", f"## {title}（申報 {x['d']}，期間 {x.get('per')}，{x['url']}）", ""]
        for k, s in x["sec"].items():
            L.append(f"### Item {k}. {ITEM_NAMES.get(k, '')}" + ("（太長，只放前段）" if s.get("cut") else ""))
            L.append(s["text"] or "（這一段抽不到文字）")
    L += ["", "## 8-K（近 6 個月，新到舊）", ""]
    for x in pk.get("news") or []:
        L.append(f"### {x['d']} {x['form']}：{x['subj']}（{x['url']}）")
        if x.get("miss"):
            L.append(f"（這一份抓不到：{'、'.join(x['miss'])}）")
        if x.get("body"):
            L.append(x["body"] + ("\n（主文件太長，只放前段）" if x.get("cut") else ""))
        for e in x.get("ex") or []:
            L.append(f"#### {e['type']} {e.get('desc') or ''}（{e['url']}）" + ("（太長，只放前段）" if e.get("cut") else ""))
            L.append(e["text"])
    if not pk.get("news"):
        L.append("- 近 6 個月沒有 8-K。")
    return "\n".join(L) + "\n"
