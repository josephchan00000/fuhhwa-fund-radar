#!/usr/bin/env python3
"""景氣溫度頁第三階段的資料來源探針（docs/lab_heat_plan.md 第 13.2 節）第二輪：只在 CI 跑、印格式與歷史起點，不寫檔。
第一輪結果：OFR、證交所 MI_QFIIS_cat、央行 DataAPI 可用；ICI 403；證期局新聞稿 PDF 與投信公會 IN2615／IN2616 要再看格式。
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


# ── OFR、ICI ─────────────────────────────────────────────────────────

def ofr() -> None:
    d = json.loads(get("https://data.financialresearch.gov/v1/series/timeseries?mnemonic=MMF-MMF_TOT-M", timeout=60))
    say("MMF-MMF_TOT-M 筆數", len(d), "前", short(d[:2], 120), "後", short(d[-3:], 200))


def ici() -> None:
    for ua in ({"User-Agent": "Mozilla/5.0"}, {"User-Agent": "curl/8.5.0", "Accept": "*/*"}):
        try:
            t = txt("https://www.ici.org/research/stats/trends_07_26", headers=ua)
            say("ICI", ua["User-Agent"], len(t), re.findall(r"[^.]{0,120}liquidity ratio[^.]{0,160}\.", plain(t), re.I)[:1])
        except Exception as e:                                # noqa: BLE001
            say("ICI", ua["User-Agent"], "✗", type(e).__name__, str(e)[:120])


# ── 證期局 ────────────────────────────────────────────────────────────

def sfb() -> None:
    u = "https://www.sfb.gov.tw/uploaddowndoc?file=news/202610051620190.pdf&filedisplay=115年10月-外資新聞稿-中文.pdf&flag=doc"
    raw = get(u, timeout=60)
    say("新聞稿 PDF bytes", len(raw), raw[:8])
    if raw[:4] == b"%PDF":
        s = pdf_text(raw)
        say("pdf 文字", len(s))
        say(short(re.sub(r"\s+", " ", s), 2500))
    for p in ("https://www.sfb.gov.tw/ch/home.jsp?id=1024&parentpath=0,4,109",):
        h = txt(p)
        say("概況表頁", len(h))
        for x, t in anchors(h):
            if re.search(r"downdoc|\.ods|\.xls|\.pdf|\.csv", x, re.I):
                say("  下載", t[:80], "→", urllib.parse.urljoin(p, x)[:220])
        tb = re.findall(r"<table\b.*?</table>", h, re.S | re.I)
        say("  表格數", len(tb))
        for t in tb[:3]:
            say("  表格", short(plain(t), 1500))
    h = txt("https://www.sfb.gov.tw/ch/home.jsp?id=95&parentpath=0,2")
    pg = [(x, t) for x, t in anchors(h) if re.search(r"page=|pagesize|下一頁|最後|末頁", x + t, re.I)]
    say("新聞稿列表分頁連結", [(t[:10], x[:160]) for x, t in pg[:8]])
    news = [(x, t) for x, t in anchors(h) if "外資" in t and "新聞稿" in t]
    say("外資新聞稿連結", [(t[:30], x[:200]) for x, t in news[:5]])
    say("表單", sorted(set(re.findall(r'name="([^"]+)"', h)))[:40])


# ── 央行 ─────────────────────────────────────────────────────────────

def cbc() -> None:
    for sid in (6023, 16900, 7242):
        for ix in (0, 1, 2):
            try:
                raw = get(f"https://cpx.cbc.gov.tw/api/OpenData/DataSet?set_id={sid}&index={ix}", timeout=90)
                say(sid, ix, len(raw), short(raw[:400].decode("utf-8", "replace"), 400))
                say("   末段", short(raw[-300:].decode("utf-8", "replace"), 300))
            except Exception as e:                            # noqa: BLE001
                say(sid, ix, "✗", type(e).__name__, str(e)[:120])
            time.sleep(0.5)
    for code in ("EF25M01", "EF13M01", "EF11M01", "EF03M01", "EG05M01", "EG37D01", "EG37M01", "EF27M01", "EF35M01", "EF39M01"):
        try:
            doc = json.loads(get(f"https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={code}", timeout=90))
        except Exception as e:                                # noqa: BLE001
            say(code, "✗", type(e).__name__, str(e)[:120])
            continue
        data = doc.get("data") or {}
        st = data.get("structure") or {}
        names = [str((x or {}).get("data") or "") for x in (st.get("Table1") or [])]
        t2 = [str((x or {}).get("data") or "") for x in (st.get("Table2") or [])]
        t3 = [str((x or {}).get("data") or "") for x in (st.get("Table3") or [])]
        ds = data.get("dataSets") or []
        say(code, "meta", short(doc.get("meta"), 300))
        say("   Table1", len(names), "、".join(names)[:900])
        say("   Table2", t2, "Table3", t3, "列數", len(ds), "欄數", len(ds[-1]) if ds else 0)
        say("   末列", short(ds[-1] if ds else None, 400))
        time.sleep(0.5)


# ── 投信投顧公會 ──────────────────────────────────────────────────────

def _form(h: str) -> tuple[dict, list, list]:
    inputs = [attrs(m) for m in re.findall(r"<input\b[^>]*>", h, re.I)]
    form = {i["name"]: i.get("value", "") for i in inputs if i.get("name") and (i.get("type") or "").lower() == "hidden"}
    sels = []
    for sa, body in re.findall(r"<select\b([^>]*)>(.*?)</select>", h, re.S | re.I):
        a = attrs(sa)
        opts = [(attrs(oa).get("value", plain(ot).strip()), plain(ot).strip(), "selected" in oa.lower())
                for oa, ot in re.findall(r"<option\b([^>]*)>(.*?)</option>", body, re.S | re.I)]
        sels.append((a.get("name"), a.get("onchange", "")[:60], opts))
    subs = [i for i in inputs if (i.get("type") or "").lower() in ("submit", "button", "image")]
    return form, sels, subs


def sitca() -> None:
    for pid, page in (("IN22605_01", "IN2615"), ("IN22605_02", "IN2616")):
        u = f"https://www.sitca.org.tw/ROC/Industry/{page}.aspx?pid={pid}"
        h = txt(u)
        form, sels, subs = _form(h)
        say(page, len(h), "hidden", list(form)[:8], "按鈕", [(s.get("name"), s.get("value")) for s in subs][:6])
        for name, oc, opts in sels:
            say("  select", name, "onchange", oc, "選項數", len(opts), "前", opts[:4], "後", opts[-3:])
        p = plain(h)
        i = p.find("持股")
        say("  預設頁片段", p[max(0, i - 200): i + 1500])
        tb = re.findall(r"<table\b.*?</table>", h, re.S | re.I)
        say("  表格數", len(tb), [len(t) for t in tb])
        big = max(tb, key=len) if tb else ""
        rows = re.findall(r"<tr\b.*?</tr>", big, re.S | re.I)
        say("  最大表格列數", len(rows))
        for r in rows[:6] + rows[-3:]:
            say("   列", short(plain(r), 300))
        # 選最早的年月 POST 一次
        ym = next((s for s in sels if s[0] and re.search(r"YM|_Y$|Date|Week", s[0], re.I)), None)
        if ym and ym[2] and subs:
            val = ym[2][-1][0]
            f = dict(form)
            for name, _, opts in sels:
                if name and opts:
                    f[name] = next((o[0] for o in opts if o[2]), opts[0][0])
            f[ym[0]] = val
            b = subs[0]
            if b.get("name"):
                f[b["name"]] = b.get("value", "")
            try:
                r = txt(u, data=urllib.parse.urlencode(f).encode(), headers={"Content-Type": "application/x-www-form-urlencoded",
                                                                             "Referer": u})
                tb = re.findall(r"<table\b.*?</table>", r, re.S | re.I)
                big = max(tb, key=len) if tb else ""
                rows = re.findall(r"<tr\b.*?</tr>", big, re.S | re.I)
                say("  POST", ym[0], "=", val, "回應", len(r), "列數", len(rows))
                for rr in rows[:5] + rows[-3:]:
                    say("   列", short(plain(rr), 300))
            except Exception as e:                            # noqa: BLE001
                say("  POST ✗", type(e).__name__, str(e)[:160])
        time.sleep(1)


def main() -> None:
    for name, fn in (("OFR", ofr), ("ICI", ici), ("證期局", sfb), ("央行", cbc), ("投信投顧公會", sitca)):
        sec(name, fn)


if __name__ == "__main__":
    main()
