#!/usr/bin/env python3
"""美國月／季資料的官方實際公布日（docs/lab_signal_quality_plan.md 第 11.2 節，A-3b）→ data/lab/heat/reldates.json.gz。

只在 CI 跑（lab_backfill.yml 的 relfill 模式；本容器的 proxy 擋這些站）。抓到什麼存什麼，抓不到的來源記在 _src、不擋其他來源；
每抓完一個來源就存一次（那一步有時間上限）：
  · 勞工統計局新聞稿（CPI、就業報告）：bls.gov 本身擋 CI，改讀網際網路檔案館（web.archive.org）——
    ① CDX 索引列出存過的新聞稿網址（archives/cpi_MMDDYYYY.htm），公布日在檔名裡 → {"cdx_cpi": [公布日…], "cdx_empsit": […]}。
       只收檔案館真的存到（狀態 200）的網址、平日、而且第一次存到的時間不早於檔名日期（2026-10-31 第一輪沒有過濾，
       混進了沒有公布過的網址：例 2020-01-03 的就業報告其實 1/10 才公布、還有週末日期）。
    ② 新聞稿檔案頁（www.bls.gov/bls/news-release/cpi.htm、empsit.htm 的存檔）：每一則寫明資料月份 → {"cpi": {資料月: 公布日}, "empsit": {…}}。
    ③ 2000 年以前的官方公布日表 www.bls.gov/bls/histreleasedates.pdf（存檔）→ 抽出文字 {"hist_txt": …}（格式在使用端解析）。
  · 聯準會 Z.1（www.federalreserve.gov/releases/z1/release-dates.htm）：每一期的網址帶公布日 → {"z1": [公布日…]}
    （哪一季由使用端照「公布日往前 60 天以前最近的季底」對應）。
  · ALFRED（聖路易聯準銀行）2026-10-31 兩輪在 CI 都逾時，不再試。

  python3 scripts/fetch_reldates.py
"""
from __future__ import annotations

import html
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.http import get_bytes  # noqa: E402
from arm.lab import heatdata as HD  # noqa: E402
from arm.lab.heatfetch import BROWSER  # noqa: E402

MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"), 1)}
BLS_PAGES = {"cpi": "https://www.bls.gov/bls/news-release/cpi.htm",
             "empsit": "https://www.bls.gov/bls/news-release/empsit.htm"}
Z1_PAGES = ("https://www.federalreserve.gov/releases/z1/", "https://www.federalreserve.gov/releases/z1/release-dates.htm")
HDRS = {**BROWSER, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"}


def _get(url: str, timeout: int = 60) -> str:
    return get_bytes(url, retries=2, timeout=timeout, use_cache=False, headers=HDRS).decode("utf-8", "replace")


def _get_backoff(url: str, waits=(20, 60, 120), timeout: int = 90) -> str:
    """網際網路檔案館常回 429（太多請求）：等一下再試。"""
    err = None
    for w in (0, *waits):
        time.sleep(w)
        try:
            return _get(url, timeout)
        except Exception as e:                              # noqa: BLE001
            err = e
            print(f"[reldates]   {url[:90]}… 失敗（{type(e).__name__}: {str(e)[:80]}），{'再等' if w != waits[-1] else '放棄'}", flush=True)
    raise RuntimeError(f"{url}: {err}")


def parse_cdx(txt: str, name: str) -> list[str]:
    """CDX 索引 → 公布日（YYYY-MM-DD，去重排序）。每一行「網址 [存檔時間 YYYYMMDDhhmmss] [狀態]」：
    有狀態的只收 200；只收平日；有存檔時間的，存檔日要不早於檔名日期（不可能在公布前就存到）。"""
    out = set()
    pat = re.compile(rf"archives/{name}_(\d{{2}})(\d{{2}})(\d{{4}})\.(?:htm|pdf)")
    for line in txt.splitlines():
        parts = line.split()
        if not parts:
            continue
        m = pat.search(parts[0])
        if not m:
            continue
        d = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        try:
            wd = date.fromisoformat(d).weekday()
        except ValueError:
            continue
        if wd >= 5 or not ("1990" <= d[:4] <= "2100"):
            continue
        if len(parts) >= 3 and parts[2] != "200":
            continue
        if len(parts) >= 2 and re.fullmatch(r"\d{8,14}", parts[1]):
            cap = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:8]}"
            if cap < d:
                continue
        out.add(d)
    return sorted(out)


def _text(chunk: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", chunk))


def parse_bls(page: str, name: str) -> dict[str, str]:
    """新聞稿檔案頁 → {資料月 YYYY-MM: 公布日 YYYY-MM-DD}。一則新聞稿一個 <li>：網址 archives/{name}_MMDDYYYY 帶公布日、
    文字裡的「Month YYYY」是資料月份；同一個資料月有好幾則（更正）取最早的。"""
    out: dict[str, str] = {}
    pat = re.compile(rf"archives/{name}_(\d{{2}})(\d{{2}})(\d{{4}})\.(?:htm|pdf)", re.I)
    for chunk in re.split(r"<li[\s>]", page, flags=re.I):
        m = pat.search(chunk)
        if not m:
            continue
        rel = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        mm = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)"
                       r"\s+(\d{4})", _text(chunk), re.I)
        if not mm:
            continue
        ym = f"{int(mm.group(2)):04d}-{MONTHS[mm.group(1).lower()]:02d}"
        if ym < rel[:7] and (ym not in out or rel < out[ym]):
            out[ym] = rel
    return out


def parse_z1(page: str) -> list[str]:
    """Z.1 頁面 → 每一期的公布日（網址 /releases/z1/YYYYMMDD/）。"""
    ds = {f"{a}-{b}-{c}" for a, b, c in re.findall(r"/releases/z1/(\d{4})(\d{2})(\d{2})/", page)}
    return sorted(d for d in ds if "1990" <= d[:4] <= "2100")


def z1_quarter(rel: str) -> str:
    """Z.1 公布日 → 那一期的季底月（公布日往前 60 天以前最近的季底）。"""
    d = date.fromisoformat(rel) - timedelta(days=60)
    q = (d.month - 1) // 3 * 3          # 那一季開始前的月數
    y, m = (d.year, q) if q else (d.year - 1, 12)
    return f"{y:04d}-{m:02d}"


def _save(d: dict, src: dict) -> None:
    """每抓完一個來源就存一次（CI 那一步有時間上限，後面的來源逾時也不會連前面的一起丟掉）。"""
    d["_src"] = dict(src)
    d["_asof"] = date.today().isoformat()
    HD.save("reldates", "bls,frb,alfred", d)


WAYBACK = ("2026", "2025")
HIST_PDF = "https://www.bls.gov/bls/histreleasedates.pdf"


def _pdf_text(raw: bytes) -> str:
    """PDF → 文字（pypdf；CI 有裝）。只抽文字，不執行任何內容。"""
    import io
    from pypdf import PdfReader
    return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(raw)).pages)


def main() -> None:
    d: dict = dict(HD.load("reldates"))
    src: dict[str, str] = {k: v for k, v in (d.get("_src") or {}).items() if not k.startswith("alfred")}
    for k in [k for k in d if k.startswith("alfred_")]:
        d.pop(k)
    for name in BLS_PAGES:                              # ① CDX 索引（只收存到的 200、平日、存檔日不早於檔名日）
        u = ("https://web.archive.org/cdx/search/cdx?url=bls.gov/news.release/archives/"
             f"{name}_&matchType=prefix&fl=original,timestamp,statuscode&filter=statuscode:200&collapse=urlkey&output=txt")
        try:
            got = parse_cdx(_get_backoff(u), name)
            src[f"cdx_{name}"] = f"{u}：{len(got)} 天"
            if got:
                d[f"cdx_{name}"] = got                  # 整份換掉（第一輪沒過濾的不留）
        except Exception as e:                          # noqa: BLE001 —— 一個來源失敗不擋其他來源
            src[f"cdx_{name}"] = f"{type(e).__name__} {e}"[:200]
        print(f"[reldates] cdx_{name}：{src[f'cdx_{name}'][-60:]}；例 {(d.get(f'cdx_{name}') or [])[-3:]}", flush=True)
        _save(d, src)
    z1: set[str] = set(d.get("z1") or [])               # Z.1
    for v in Z1_PAGES:
        try:
            got = parse_z1(_get(v))
            z1 |= set(got)
            src[f"z1:{v}"] = f"{len(got)} 期"
        except Exception as e:                          # noqa: BLE001
            src[f"z1:{v}"] = f"{type(e).__name__} {e}"[:200]
        print(f"[reldates] Z.1 {v}：{src[f'z1:{v}']}", flush=True)
    if z1:
        d["z1"] = sorted(z1)
    _save(d, src)
    for ts in WAYBACK:                                  # ③ 2000 年以前的官方公布日表（PDF）
        v = f"https://web.archive.org/web/{ts}id_/{HIST_PDF}"
        try:
            raw = get_bytes(v, retries=2, timeout=120, use_cache=False, headers=HDRS)
            txt = _pdf_text(raw)
            src["hist"] = f"{v}：{len(raw)} bytes、{len(txt)} 字"
            if len(txt) > 1000:
                d["hist_txt"] = txt
                break
        except Exception as e:                          # noqa: BLE001
            src["hist"] = f"{v}：{type(e).__name__} {e}"[:200]
        print(f"[reldates] hist：{src['hist'][-120:]}", flush=True)
        time.sleep(20)
    print(f"[reldates] hist：{src.get('hist', '')[-120:]}", flush=True)
    _save(d, src)
    for name, url in BLS_PAGES.items():                 # ② 新聞稿檔案頁（寫明資料月份）
        for ts in WAYBACK:
            v = f"https://web.archive.org/web/{ts}id_/{url}"
            try:
                got = parse_bls(_get_backoff(v), name)
                src[name] = f"{v}：{len(got)} 期"
                if got:
                    d[name] = got
                if len(got) >= 100:
                    break
            except Exception as e:                      # noqa: BLE001
                src[name] = f"{v}：{type(e).__name__} {e}"[:200]
            print(f"[reldates] {name}：{src[name][-160:]}", flush=True)
        _save(d, src)
    print("[reldates] 寫入 data/lab/heat/reldates.json.gz：" +
          "、".join(f"{k} {len(v)}" for k, v in sorted(d.items()) if not k.startswith("_")), flush=True)


if __name__ == "__main__":
    main()
