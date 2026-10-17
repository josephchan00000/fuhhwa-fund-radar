#!/usr/bin/env python3
"""景氣溫度頁第三階段的資料來源探針（docs/lab_heat_plan.md 第 13.2 節）。只在 CI 跑一次、印格式與歷史起點，不寫檔。
合併前刪掉（同第二階段的探針）。`.ping/lab` 第一行寫 heatprobe 觸發。"""
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


def get(url: str, timeout: int = 40, data: bytes | None = None, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, data=data, headers={**BROWSER, **(headers or {})})
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


def try_get(label: str, url: str, timeout: int = 40, n: int = 300) -> str | None:
    try:
        t = txt(url, timeout=timeout)
        say(label, len(t), short(plain(t), n))
        return t
    except Exception as e:                                    # noqa: BLE001
        say(label, "✗", type(e).__name__, str(e)[:160])
        return None


# ── 美國貨幣基金：OFR、ICI ─────────────────────────────────────────────

def ofr() -> None:
    base = "https://data.financialresearch.gov/v1"
    m = json.loads(get(f"{base}/metadata/mnemonics?dataset=mmf", timeout=60))
    items = m if isinstance(m, list) else (m.get("data") if isinstance(m, dict) else []) or []
    say("型態", type(m).__name__, "筆數", len(items), "前幾筆", short(items[:3], 400))

    def nm(x):
        return (x.get("mnemonic"), x.get("series_name") or "") if isinstance(x, dict) else (str(x), "")
    tot = [nm(x) for x in items if re.search(r"TOT|total", " ".join(map(str, nm(x))), re.I)]
    for mn, sn in tot[:25]:
        say("  ", mn, "｜", short(sn, 110))
    for mn in [a for a, _ in tot[:5]] or ["MMF-MMF_TOT-M"]:
        try:
            d = json.loads(get(f"{base}/series/timeseries?mnemonic={mn}", timeout=60))
            rows = d if isinstance(d, list) else (d.get("data") if isinstance(d, dict) else None) or []
            say(mn, "筆數", len(rows), "前", short(rows[:2], 120), "後", short(rows[-2:], 120))
        except Exception as e:                                # noqa: BLE001
            say(mn, "✗", type(e).__name__, str(e)[:160])


def ici() -> None:
    u0 = "https://www.ici.org/research/stats/mmf"
    h = txt(u0)
    say("mmf 頁", len(h), re.findall(r"[^.<>]{0,80}\$\s?[0-9.,]+\s*trillion[^<]{0,160}", plain(h))[:2])
    for u, t in anchors(h):
        if re.search(r"\.(xlsx?|csv)(\?|$)|summary|historical", u, re.I):
            say("  連結", t[:60], "→", urllib.parse.urljoin(u0, u)[:200])
    for pg in ("trends_07_26", "trends_12_25", "trends_06_25", "trends_12_24", "trends_06_24", "trends_05_24",
               "trends_12_20", "trends_12_15", "trends_12_10"):
        try:
            t = txt(f"https://www.ici.org/research/stats/{pg}")
            m = re.findall(r"[^.]{0,160}liquidity ratio[^.]{0,200}\.", plain(t), re.I)
            xl = [u for u, _ in anchors(t) if re.search(r"\.(xlsx?|pdf)(\?|$)", u, re.I)]
            say(pg, len(t), m[:1], "附件", xl[:3])
        except Exception as e:                                # noqa: BLE001
            say(pg, "✗", type(e).__name__, str(e)[:120])
        time.sleep(1)


# ── 證期局／金管會外資匯入、證交所外資持股 ──────────────────────────────

def _pdf_text(raw: bytes) -> str:
    try:
        import pypdf
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pypdf"], check=False)
        import pypdf
    return "".join(pg.extract_text() or "" for pg in pypdf.PdfReader(io.BytesIO(raw)).pages)


def sfb() -> None:
    lists = ["https://www.sfb.gov.tw/ch/home.jsp?id=95&parentpath=0,2",
             "https://www.fsc.gov.tw/ch/home.jsp?id=96&parentpath=0,2",
             "https://www.sfb.gov.tw/ch/index.jsp"]
    hits, menu = [], []
    for p in lists:
        try:
            h = txt(p)
        except Exception as e:                                # noqa: BLE001
            say(p, "✗", type(e).__name__, str(e)[:160])
            continue
        al = anchors(h)
        say(p, len(h), "連結數", len(al), "表單欄位", sorted(set(re.findall(r'name="([^"]+)"', h)))[:15])
        for u, t in al:
            fu = urllib.parse.urljoin(p, u)
            if "外資" in t:
                hits.append((fu, t))
            elif re.search(r"統計|指標|新聞稿", t) and "home.jsp" in fu:
                menu.append((fu, t))
    for fu, t in hits[:8]:
        say("  外資連結", t[:90], "→", fu[:200])
    for fu, t in menu[:12]:
        say("  選單", t[:40], "→", fu[:200])
    for fu, t in menu[:6]:                                    # 第二層：統計／新聞稿頁裡的外資連結
        try:
            h = txt(fu)
            for u, tt in anchors(h):
                if "外資" in tt:
                    hits.append((urllib.parse.urljoin(fu, u), tt))
                    say("  第二層", t[:20], "｜", tt[:80], "→", urllib.parse.urljoin(fu, u)[:200])
        except Exception as e:                                # noqa: BLE001
            say("  第二層", t[:20], "✗", type(e).__name__)
        time.sleep(0.5)
    pick = next(((u, t) for u, t in hits if re.search(r"匯入|投資國內證券", t)), None)
    if not pick:
        say("沒有找到外資匯入新聞稿連結")
        return
    u, t = pick
    d = txt(u)
    say("內容頁", t[:80], len(d))
    say("淨匯入句子", re.findall(r"[^。]{0,80}淨匯[入出][^。]{0,120}。", plain(d))[:3])
    att = [urllib.parse.urljoin(u, x) for x, _ in anchors(d) if re.search(r"uploaddowndoc|\.pdf|\.odt|\.docx?", x, re.I)]
    say("附件", [a[:200] for a in att[:4]])
    for a in att[:2]:
        try:
            raw = get(a, timeout=60)
            say("附件 bytes", len(raw), raw[:8])
            if raw[:4] == b"%PDF":
                s = _pdf_text(raw)
                i = s.find("匯入")
                say("pdf 文字", len(s), short(s[max(0, i - 300):i + 600], 900))
        except Exception as e:                                # noqa: BLE001
            say("附件 ✗", type(e).__name__, str(e)[:160])


def twse_qfiis() -> None:
    for d in ("20040102", "20050103", "20100104", "20150105", "20200102", "20261016"):
        try:
            j = json.loads(get(f"https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS_cat?date={d}&response=json"))
            data = j.get("data") or []
            say(d, j.get("stat"), "欄", j.get("fields"), "列數", len(data), "末列", short(data[-1] if data else None, 200))
        except Exception as e:                                # noqa: BLE001
            say(d, "✗", type(e).__name__, str(e)[:160])
        time.sleep(3.5)


# ── 央行 ─────────────────────────────────────────────────────────────

def cbc_oas() -> None:
    """data.gov.tw 上央行資料集的 OAS 說明：6023 拆款、6533 準備貨幣、16900 準備金提存、6541／6535 存放款、7242 公開市場。"""
    for sid in (6023, 6533, 16900, 6541, 6535, 7242):
        try:
            o = json.loads(get(f"https://cpx.cbc.gov.tw/api/OpenData/OAS?set_id={sid}", timeout=60))
        except Exception as e:                                # noqa: BLE001
            say(sid, "OAS ✗", type(e).__name__, str(e)[:160])
            continue
        info = o.get("info") or {}
        servers = [s.get("url") for s in (o.get("servers") or []) if isinstance(s, dict)]
        host = o.get("host")
        base = (servers[0] if servers else (f"https://{host}{o.get('basePath') or ''}" if host else "https://cpx.cbc.gov.tw"))
        say(sid, short(info.get("title"), 80), "｜", short(info.get("description"), 160), "｜base", base)
        calls = []
        for path, ops in (o.get("paths") or {}).items():
            for meth, op in (ops or {}).items():
                if not isinstance(op, dict):
                    continue
                ps = [(p.get("name"), p.get("in"), p.get("required"), (p.get("schema") or {}).get("default") or p.get("default"))
                      for p in (op.get("parameters") or []) if isinstance(p, dict)]
                say("   ", meth.upper(), path, "參數", ps, short(op.get("summary") or op.get("description"), 80))
                if meth.lower() == "get":
                    calls.append(base.rstrip("/") + path)
        for u in calls[:2]:
            for q in ("", "?format=json"):
                try:
                    raw = get(u + q, timeout=90)
                    say("    GET", (u + q)[:160], len(raw), short(raw[:500].decode("utf-8", "replace"), 500))
                    try:
                        d = json.loads(raw)
                        rows = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])
                        say("    列數", len(rows), "首", short(rows[0] if rows else None, 260), "末", short(rows[-1] if rows else None, 260))
                    except ValueError:
                        pass
                    break
                except Exception as e:                        # noqa: BLE001
                    say("    GET", (u + q)[:160], "✗", type(e).__name__, str(e)[:120])
        time.sleep(1)


def cbc_dataapi() -> None:
    """央行統計資料庫 DataAPI（EF15M01＝貨幣總計數已在用）：列舉代碼找準備金、拆款、存放款。"""
    t0 = time.time()
    first = True
    for pre, kinds in (("EF", ("M01",)), ("EG", ("M01", "D01")), ("EF", ("D01",))):
        for n in range(1, 41):
            for k in kinds:
                if time.time() - t0 > 600:
                    say("（時間到，停止列舉）")
                    return
                code = f"{pre}{n:02d}{k}"
                try:
                    raw = get(f"https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={code}", timeout=25)
                except Exception as e:                        # noqa: BLE001
                    say(code, "✗", type(e).__name__, str(e)[:60])
                    continue
                try:
                    doc = json.loads(raw)
                except ValueError:
                    say(code, len(raw), "非 JSON", short(raw[:80].decode("utf-8", "replace"), 80))
                    continue
                data = doc.get("data") if isinstance(doc, dict) else None
                if not isinstance(data, dict):
                    say(code, len(raw), "無 data", short(doc, 120))
                    continue
                if first:
                    say("頂層鍵", list(doc), "data 鍵", list(data), "structure 鍵", list((data.get("structure") or {})))
                    say("非 dataSets 內容", short({k: v for k, v in data.items() if k != "dataSets"}, 600))
                    first = False
                names = [str((x or {}).get("data") or "").replace(" ", "") for x in ((data.get("structure") or {}).get("Table1") or [])]
                ds = data.get("dataSets") or []
                ttl = data.get("title") or doc.get("title") or (data.get("structure") or {}).get("title") or ""
                say(code, len(raw), short(ttl, 40), "｜", "、".join(names[:6])[:150], "｜", len(ds), "列",
                    (ds[0][0] if ds and ds[0] else None), "～", (ds[-1][0] if ds and ds[-1] else None))
                time.sleep(0.3)


# ── 投信投顧公會 ──────────────────────────────────────────────────────

def sitca() -> None:
    seeds = ["https://www.sitca.org.tw/ROC/Industry/IN2001.aspx", "https://www.sitca.org.tw/index_pc.aspx",
             "https://www.sitca.org.tw/ROC/Industry/IN2002.aspx?PGMID=IN0202", "https://www.sitca.org.tw/"]
    seen: dict[str, str] = {}
    for s in seeds:
        try:
            h = txt(s)
        except Exception as e:                                # noqa: BLE001
            say(s, "✗", type(e).__name__, str(e)[:160])
            continue
        al = anchors(h)
        say(s, len(h), "連結", len(al))
        for u, t in al:
            fu = urllib.parse.urljoin(s, u)
            if "sitca.org.tw" in fu and t:
                seen.setdefault(fu, t)
        time.sleep(0.5)
    hits = [(u, t) for u, t in seen.items() if re.search(r"持股|比率|類股|資產分|投資標的", t)]
    for u, t in hits[:25]:
        say("  ", t[:60], "→", u[:180])
    ind = [(u, t) for u, t in seen.items() if "/Industry/" in u]
    say("Industry 連結數", len(ind), "前 30", [f"{t[:14]}={u.rsplit('/', 1)[-1][:40]}" for u, t in ind[:30]])
    for u, t in hits[:4]:
        try:
            h = txt(u)
        except Exception as e:                                # noqa: BLE001
            say(t[:30], "✗", type(e).__name__, str(e)[:120])
            continue
        p = plain(h)
        i = p.find("持股")
        say(t[:30], len(h), "select", re.findall(r'<select[^>]*name="([^"]+)"', h)[:8], "table", h.count("<table"),
            "片段", p[max(0, i - 120): i + 420])
        time.sleep(0.5)


def main() -> None:
    for name, fn in (("OFR 貨幣基金", ofr), ("ICI", ici), ("證期局／金管會外資匯入", sfb), ("證交所外資持股", twse_qfiis),
                     ("央行 OAS", cbc_oas), ("央行 DataAPI 列舉", cbc_dataapi), ("投信投顧公會", sitca)):
        sec(name, fn)


if __name__ == "__main__":
    main()
