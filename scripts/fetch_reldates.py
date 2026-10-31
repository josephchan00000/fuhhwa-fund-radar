#!/usr/bin/env python3
"""美國月／季資料的官方實際公布日（docs/lab_signal_quality_plan.md 第 11.2 節，A-3b）→ data/lab/heat/reldates.json.gz。

只在 CI 跑（lab_backfill.yml 的 relfill 模式；本容器的 proxy 擋這些站）。抓到什麼存什麼，抓不到的來源記在 src、不擋其他來源：
  · 勞工統計局新聞稿檔案頁（www.bls.gov/bls/news-release/cpi.htm、empsit.htm）：每一則新聞稿的網址帶公布日
    （archives/cpi_MMDDYYYY.htm），文字帶資料月份 → {"cpi": {資料月: 公布日}, "empsit": {…}}；
    被擋時改讀網際網路檔案館的同一頁（web.archive.org，id_ 原樣內容）。
  · 聯準會 Z.1（www.federalreserve.gov/releases/z1/）：每一期的網址帶公布日 /releases/z1/YYYYMMDD/ → {"z1": [公布日…]}
    （哪一季由使用端照「公布日往前 60 天以前最近的季底」對應）。
  · ALFRED（alfred.stlouisfed.org/release/downloaddates?rid=…）：聖路易聯準銀行記下的每一次公布日，當第二來源核對
    （rid 10＝CPI、50＝就業報告、53＝GDP、52＝Z.1）→ {"alfred_cpi": [日期…], …}。
  · 勞工統計局的頁面在 CI 被擋時：網際網路檔案館的 CDX 索引列出存過的每一個新聞稿網址（archives/cpi_MMDDYYYY.htm），
    公布日就在檔名裡 → {"cdx_cpi": [公布日…], "cdx_empsit": […]}（哪一個資料月份由使用端照「公布月的前一個月」對，
    政府停擺那幾個月另有官方改期表 heatspec.CPI_LATE、heatspec_us.JOBS_LATE 取晚的）。

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
ALFRED = {"alfred_cpi": 10, "alfred_empsit": 50, "alfred_gdp": 53, "alfred_z1": 52}
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
    """CDX 索引（一行一個原始網址）→ 公布日（YYYY-MM-DD，去重排序）。"""
    out = set()
    for a, b, c in re.findall(rf"archives/{name}_(\d{{2}})(\d{{2}})(\d{{4}})\.(?:htm|pdf)", txt):
        out.add(f"{c}-{a}-{b}")
    return sorted(d for d in out if "1990" <= d[:4] <= "2100")


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


def parse_dates(txt: str) -> list[str]:
    """ALFRED 公布日清單（文字檔或網頁）→ 日期（YYYY-MM-DD，去重排序）。"""
    return sorted(set(re.findall(r"(?<!\d)((?:19|20)\d{2}-\d{2}-\d{2})(?!\d)", txt)))


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


def main() -> None:
    d: dict = dict(HD.load("reldates"))
    src: dict[str, str] = dict(d.get("_src") or {})
    for name, url in BLS_PAGES.items():
        u = ("https://web.archive.org/cdx/search/cdx?url=bls.gov/news.release/archives/"
             f"{name}_&matchType=prefix&fl=original&collapse=urlkey&output=txt")
        try:                                            # ① CDX 索引：公布日在檔名裡
            got2 = parse_cdx(_get_backoff(u), name)
            src[f"cdx_{name}"] = f"{u}：{len(got2)} 天"
            if got2:
                d[f"cdx_{name}"] = sorted(set(d.get(f"cdx_{name}") or []) | set(got2))
        except Exception as e:                          # noqa: BLE001 —— 一個來源失敗不擋其他來源
            src[f"cdx_{name}"] = f"{type(e).__name__} {e}"[:200]
        print(f"[reldates] cdx_{name}：{src[f'cdx_{name}']}；例 {(d.get(f'cdx_{name}') or [])[-3:]}", flush=True)
        _save(d, src)
        urls = [url] + ([] if len(d.get(f"cdx_{name}") or []) >= 100 else ["https://web.archive.org/web/2026id_/" + url])
        for v in urls:                                  # ② 新聞稿檔案頁（帶資料月份）
            try:
                got = parse_bls(_get(v) if v == url else _get_backoff(v), name)
                src[name] = f"{v}：{len(got)} 期"
                if got:
                    d[name] = {**(d.get(name) or {}), **got}
                if len(got) >= 100:
                    break
            except Exception as e:                      # noqa: BLE001
                src[name] = f"{v}：{type(e).__name__} {e}"[:200]
            print(f"[reldates] {name}：{src[name][-160:]}", flush=True)
        _save(d, src)
    z1: set[str] = set(d.get("z1") or [])
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
    for key, rid in ALFRED.items():                     # ③ ALFRED：只試一次、45 秒（2026-10-31 第一輪在 CI 每次都逾時）
        if d.get(key):
            continue
        v = f"https://alfred.stlouisfed.org/release/downloaddates?rid={rid}&ff=txt"
        try:
            got = parse_dates(get_bytes(v, retries=1, timeout=45, use_cache=False, headers=HDRS).decode("utf-8", "replace"))
            src[key] = f"{v}：{len(got)} 天"
            if got:
                d[key] = got
        except Exception as e:                          # noqa: BLE001
            src[key] = f"{type(e).__name__} {e}"[:200]
        print(f"[reldates] {key}：{src[key][-120:]}", flush=True)
        _save(d, src)
    print("[reldates] 寫入 data/lab/heat/reldates.json.gz：" +
          "、".join(f"{k} {len(v)}" for k, v in sorted(d.items()) if not k.startswith("_")), flush=True)


if __name__ == "__main__":
    main()
