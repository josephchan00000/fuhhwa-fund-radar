#!/usr/bin/env python3
"""個股報告的官方文件探針（docs/lab_eq_docs_plan.md）：公開資訊觀測站的公司基本資料、法人說明會（簡報 PDF）、
重大訊息、股東會年報，公司官網。只印不寫資料，結果寫進 data/lab/_eqdocprobe.txt（lab_backfill 會 commit 回分支）。

容器擋觀測站（2026-10-30 實測 CONNECT 403），所以在 CI 跑（lab_backfill.yml，.ping/lab 第一行寫 eqdocprobe）。
每段各自 try，一段壞了不影響其他段；總時間上限 12 分鐘。"""
import html
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm.http import get_bytes  # noqa: E402
from arm.lab.market import _decode, post_bytes  # noqa: E402

CODES = [("6870", "騰雲"), ("7730", "暉盛-創"), ("5475", "德宏"), ("4958", "臻鼎-KY"), ("2330", "台積電")]
OV = "https://mopsov.twse.com.tw"
T0 = time.time()
OUT: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s, flush=True)


def text(h: str, n: int = 500) -> str:
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S | re.I)
    h = html.unescape(re.sub(r"<[^>]+>", " ", h))
    return re.sub(r"\s+", " ", h).strip()[:n]


def pdfs(h: str) -> list[str]:
    return sorted(set(re.findall(r"""['"(]([^'"()\s<>]*?\.pdf)['")]""", h, re.I)))


def run(name, fn):
    p(f"\n===== {name}（{time.time() - T0:.0f}s）=====")
    if time.time() - T0 > 720:
        p("超過時間上限，略過")
        return None
    try:
        return fn()
    except Exception as ex:                                   # noqa: BLE001
        p(f"✗ {type(ex).__name__}: {str(ex)[:300]}")
        return None


def mops(ep: str, form: dict, timeout: int = 40) -> str:
    b = post_bytes(f"{OV}/mops/web/ajax_{ep}", form, retries=1, timeout=timeout)
    return _decode(b)


def basic(code):
    """公司基本資料 t05st03：主要經營業務、公司網址、市場別。"""
    h = mops("t05st03", {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "queryName": "co_id",
                         "inpuType": "co_id", "TYPEK": "all", "co_id": code})
    t = text(h, 6000)
    p(f"{len(h)}B；", t[:900])
    m = re.search(r"https?://[^\s<>'\"]+", h.split("公司網址", 1)[-1]) if "公司網址" in h else None
    return m.group(0) if m else None


def confs(code):
    """法人說明會：舊站 ajax_t100sb07_1／t100sb02_1 幾種參數，印找到的 PDF 與前幾列文字。"""
    found = []
    tries = []
    for y in (115, 114):
        for ep, form in (
            ("t100sb07_1", {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "TYPEK": "all", "year": y,
                            "month": "all", "co_id": code}),
            ("t100sb02_1", {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "TYPEK": "all", "co_id": code,
                            "year": y}),
            ("t100sb07_1", {"encodeURIComponent": 1, "step": 1, "firstin": "true", "off": 1, "queryName": "co_id",
                            "inpuType": "co_id", "TYPEK": "all", "isnew": "false", "co_id": code, "year": y, "month": ""}),
        ):
            tries.append((ep, y, form))
    for ep, y, form in tries:
        if time.time() - T0 > 700:
            break
        try:
            h = mops(ep, form)
        except Exception as ex:                               # noqa: BLE001
            p(f"  {ep} {y} {list(form)[-3:]} ✗ {str(ex)[:160]}")
            continue
        fs = pdfs(h)
        p(f"  {ep} {y} keys={','.join(k for k in form if k not in ('encodeURIComponent', 'step', 'firstin', 'off'))}：{len(h)}B、"
          f"含代號 {code in h}、PDF {len(fs)} 個 {fs[:6]}")
        p("   文字：", text(h, 700))
        found += fs
        time.sleep(1.0)
    return sorted(set(found))


def new_api(code):
    """新版觀測站（mops.twse.com.tw/mops/#/web/...）的 API：猜幾個形狀，印狀態與開頭。"""
    for url, body in (
        ("https://mops.twse.com.tw/mops/api/t100sb07_1", {"companyId": code, "year": "114", "month": "all", "marketKind": "all"}),
        ("https://mops.twse.com.tw/mops/api/t100sb07_1", {"companyId": code, "year": "115"}),
        ("https://mops.twse.com.tw/mops/api/t05st01", {"companyId": code, "year": "115", "month": "all"}),
        ("https://mops.twse.com.tw/mops/api/t05st03", {"companyId": code}),
    ):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
                "User-Agent": "Mozilla/5.0", "Content-Type": "application/json", "Accept": "application/json",
                "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/"})
            import ssl

            import certifi
            with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context(cafile=certifi.where())) as r:
                b = r.read()
            s = b.decode("utf-8", "replace")
            p(f"  {url} {body} → {len(b)}B：{s[:600]}")
            for f in pdfs(s)[:5]:
                p("   pdf:", f)
        except Exception as ex:                               # noqa: BLE001
            p(f"  {url} {body} ✗ {str(ex)[:200]}")
        time.sleep(0.8)


def pdf_text(url: str):
    """下載一個 PDF：大小、頁數、前 8 頁每頁抽得到幾個字、樣本。"""
    b = get_bytes(url, retries=2, timeout=60, use_cache=False)
    p(f"  下載 {url}：{len(b) / 1024:.0f}KB、開頭 {b[:5]!r}")
    if not b.startswith(b"%PDF"):
        p("  不是 PDF：", text(_decode(b), 300))
        return
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(b))
    p(f"  頁數 {len(r.pages)}")
    for i, pg in enumerate(r.pages[:8]):
        try:
            t = re.sub(r"\s+", " ", pg.extract_text() or "").strip()
        except Exception as ex:                               # noqa: BLE001
            t = f"(抽字失敗 {ex})"
        p(f"   p{i + 1}: {len(t)} 字：{t[:220]}")


def news(code):
    """重大訊息 t05st01（今年＋去年）：筆數、最近幾筆主旨；試抓一筆內文。"""
    for y in (115, 114):
        h = mops("t05st01", {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "keyword4": "", "code1": "",
                             "TYPEK2": "", "checkbtn": "", "queryName": "co_id", "inpuType": "co_id", "TYPEK": "all",
                             "co_id": code, "year": y, "month": "", "b_date": "", "e_date": ""})
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S | re.I)
        subj = [text(r, 160) for r in rows if re.search(r"\d{3}/\d{2}/\d{2}", r)]
        p(f"  {y} 年：{len(h)}B、列 {len(rows)}、有日期的 {len(subj)}")
        for s in subj[:6]:
            p("   ·", s)
        ons = re.findall(r"""onclick=['"]([^'"]*seq_no[^'"]*)['"]""", h, re.I)
        if ons:
            p("   第一筆 onclick：", html.unescape(ons[0])[:400])
            kv = dict(re.findall(r"\.(\w+)\.value\s*=\s*['\"]?([^'\";]*)", html.unescape(ons[0])))
            if kv:
                form = {"encodeURIComponent": 1, "step": 2, "firstin": 1, "off": 1, "TYPEK": "all", "co_id": code, **kv}
                try:
                    d = mops("t05st01", form)
                    p(f"   內文（{len(d)}B）：", text(d, 900))
                except Exception as ex:                       # noqa: BLE001
                    p("   內文 ✗", str(ex)[:200])
        time.sleep(1.0)


def annual(code):
    """股東會年報（doc.twse.com.tw 電子書）：114、113 年度的檔案清單。"""
    for y in (114, 113):
        url = f"https://doc.twse.com.tw/server-java/t57sb01?step=1&colorchg=1&co_id={code}&year={y}&mtype=F&"
        b = get_bytes(url, retries=1, timeout=40, use_cache=False)
        h = _decode(b)
        files = re.findall(r"readfile2\(\s*['\"](\w)['\"]\s*,\s*['\"](\w+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", h)
        p(f"  {y}：{len(b)}B、檔案 {files[:8]}")
        p("   文字：", text(h, 400))
        time.sleep(1.0)


def site(url):
    if not url:
        p("  （沒有公司網址）")
        return
    b = get_bytes(url, retries=1, timeout=30, use_cache=False)
    h = _decode(b)
    ir = re.findall(r"""href=['"]([^'"]*(?:invest|ir|stakeholder|投資人)[^'"]*)['"]""", h, re.I)
    p(f"  {url}：{len(b)}B、投資人相關連結 {sorted(set(ir))[:8]}")


def main():
    for code, nm in CODES:
        p(f"\n################ {code} {nm} ################")
        web = run(f"{code} 公司基本資料", lambda: basic(code))
        fs = run(f"{code} 法人說明會（舊站）", lambda: confs(code)) or []
        run(f"{code} 新版觀測站 API", lambda: new_api(code))
        if fs:
            last = fs[-1]
            url = last if last.startswith("http") else OV + (last if last.startswith("/") else "/" + last)
            run(f"{code} 最新一份簡報 PDF", lambda: pdf_text(url))
        run(f"{code} 重大訊息", lambda: news(code))
        run(f"{code} 股東會年報", lambda: annual(code))
        run(f"{code} 公司官網", lambda: site(web))
    out = Path(__file__).resolve().parent.parent / "data" / "lab" / "_eqdocprobe.txt"
    out.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print(f"寫入 {out}（{time.time() - T0:.0f}s）")


if __name__ == "__main__":
    main()
