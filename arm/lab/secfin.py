"""美股財報（SEC XBRL；docs/lab_us_sleeve_plan.md 第 3、8 節；只在 CI 跑，本容器擋 sec.gov）。

SEC 要求每個請求的 User-Agent 帶聯絡方式（防止有人狂抓，不收費、不用註冊）。聯絡 email 只從環境變數
SEC_CONTACT_EMAIL（GitHub secret）讀——程式、日誌、存檔都不出現；沒有設就整段跳過。

來源（一共兩個請求）：
  company_tickers.json：今天的代號 → CIK（已下市的公司不在裡面，同股價的存活偏誤）
  companyfacts.zip   ：每家公司全部 XBRL 數字（一個檔一千多 MB），只取下面 TAGS 的幾個項目
每一個期間（起日、迄日）只留**第一次公布**的那個數字與公布日（10-Q／10-K 原始申報優先於修正申報）——回測只能用
公布日以後的數字，之後才修正的不算。

存檔（資料根目錄同 ussxdata.data_dir()）：
  sec/{代號}.json.gz：{"cik": CIK, "f": {項目: [[起日, 迄日, 數值, 公布日, 表單], ...]}}（起日空字串＝時點數字，例如股東權益、流通股數）
  sec_meta.json.gz  ：{"asof": 抓的日期, "n": 有資料的家數, "miss": 代號在 SEC 找不到 CIK 的家數}
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

from . import ussxdata as UD

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
BULK_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
ENV = "SEC_CONTACT_EMAIL"
START = "2006-01-01"
FORMS = {"10-Q", "10-K", "10-QT", "10-KT"}
FORMS_A = {f + "/A" for f in FORMS}
# (分類, 項目): 單位。營收的寫法 2018 年（ASC 606）前後不同，研究時再依期間挑有值的那一個。
TAGS = {
    ("us-gaap", "Revenues"): "USD",
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"): "USD",
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"): "USD",
    ("us-gaap", "SalesRevenueNet"): "USD",
    ("us-gaap", "SalesRevenueGoodsNet"): "USD",
    ("us-gaap", "SalesRevenueServicesNet"): "USD",
    ("us-gaap", "RevenuesNetOfInterestExpense"): "USD",
    ("us-gaap", "CostOfRevenue"): "USD",
    ("us-gaap", "CostOfGoodsAndServicesSold"): "USD",
    ("us-gaap", "CostOfGoodsSold"): "USD",
    ("us-gaap", "CostOfServices"): "USD",
    ("us-gaap", "GrossProfit"): "USD",
    ("us-gaap", "OperatingIncomeLoss"): "USD",
    ("us-gaap", "NetIncomeLoss"): "USD",
    ("us-gaap", "StockholdersEquity"): "USD",
    ("us-gaap", "EarningsPerShareDiluted"): "USD/shares",
    ("dei", "EntityCommonStockSharesOutstanding"): "shares",
}
_CIK_FILE = re.compile(r"CIK(\d{10})\.json$")


def contact() -> str | None:
    e = (os.environ.get(ENV) or "").strip()
    return e if ("@" in e and 3 < len(e) < 200 and " " not in e) else None


def _ua(email: str) -> str:
    return f"FuhhwaFundRadar research {email}"


def _log(*a) -> None:
    print("[sec]", *a, flush=True)


def sec_path(sym: str) -> Path:
    return UD.data_dir() / "sec" / f"{sym}.json.gz"


def load_meta() -> dict:
    return UD._read(UD.data_dir() / "sec_meta.json.gz") or {}


def load(sym: str) -> dict:
    return UD._read(sec_path(sym)) or {}


# ── 解析 ───────────────────────────────────────────────────────────────────────

def ticker_map(doc: dict) -> dict[str, int]:
    """company_tickers.json → {Yahoo 寫法的代號: CIK}。"""
    out = {}
    for r in (doc or {}).values():
        try:
            out[UD.ysym(str(r["ticker"]))] = int(r["cik_str"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _rank(form: str, filed: str) -> tuple:
    return (filed, 1 if form in FORMS_A else 0)


def extract(doc: dict, start: str = START) -> dict[str, list]:
    """companyfacts 一家公司 → {項目: [[起日, 迄日, 數值, 公布日, 表單], ...]}（同一期間只留第一次公布的）。"""
    facts = (doc or {}).get("facts") or {}
    out = {}
    for (tax, tag), unit in TAGS.items():
        rows = ((((facts.get(tax) or {}).get(tag) or {}).get("units")) or {}).get(unit) or []
        best: dict[tuple, tuple] = {}
        for r in rows:
            form, filed, end, val = r.get("form"), r.get("filed"), r.get("end"), r.get("val")
            if form not in FORMS and form not in FORMS_A:
                continue
            if not filed or not end or val is None or end < start:
                continue
            s = r.get("start") or ""
            key = (s, end)
            rk = _rank(form, filed)
            if key not in best or rk < best[key][0]:
                best[key] = (rk, [s, end, val, filed, form])
        if best:
            out[tag] = sorted(v for _, v in best.values())
    return out


# ── 抓取（只在 CI）─────────────────────────────────────────────────────────────

def _open(url: str, email: str, timeout: int = 120):
    from ..http import _CTX
    req = urllib.request.Request(url, headers={"User-Agent": _ua(email), "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX)


def fetch_tickers(email: str) -> dict[str, int]:
    with _open(TICKERS_URL, email, timeout=60) as r:
        return ticker_map(json.loads(r.read().decode("utf-8")))


def download_bulk(email: str, path: Path, chunk: int = 1 << 20) -> int:
    n = 0
    with _open(BULK_URL, email, timeout=300) as r, open(path, "wb") as f:
        while True:
            b = r.read(chunk)
            if not b:
                break
            f.write(b)
            n += len(b)
    return n


def run(syms: list[str] | None = None) -> dict:
    """抓一次（同一天抓過就跳過）。沒有設 SEC_CONTACT_EMAIL＝跳過。回傳統計。"""
    email = contact()
    if not email:
        _log(f"沒有設 {ENV}（GitHub secret），SEC 這一段跳過")
        return {"skip": "no-secret"}
    meta = load_meta()
    today = date.today().isoformat()
    if meta.get("asof") == today:
        return {"skip": "today"}
    t0 = time.time()
    syms = syms if syms is not None else UD.calendar_symbols()
    try:
        tick = fetch_tickers(email)
    except Exception as e:                                    # noqa: BLE001
        _log(f"代號對照抓不到：{type(e).__name__}: {str(e)[:160]}")
        return {"err": "tickers"}
    want: dict[int, list[str]] = {}
    miss = 0
    for s in syms:
        c = tick.get(s)
        if c is None:
            miss += 1
            continue
        want.setdefault(c, []).append(s)
    _log(f"代號對照 {len(tick)} 筆；我們的 {len(syms)} 檔有 CIK 的 {len(syms) - miss} 檔（{len(want)} 家公司）")
    with tempfile.TemporaryDirectory() as td:
        zp = Path(td) / "companyfacts.zip"
        try:
            size = download_bulk(email, zp)
        except Exception as e:                                # noqa: BLE001
            _log(f"companyfacts.zip 抓不到：{type(e).__name__}: {str(e)[:160]}")
            return {"err": "bulk"}
        _log(f"companyfacts.zip {size / 1e6:.0f} MB（{time.time() - t0:.0f}s）")
        n_ok = n_empty = 0
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                m = _CIK_FILE.search(name)
                if not m:
                    continue
                cik = int(m.group(1))
                if cik not in want:
                    continue
                try:
                    f = extract(json.loads(z.read(name).decode("utf-8")))
                except Exception as e:                        # noqa: BLE001
                    _log(f"CIK {cik} 解析失敗：{type(e).__name__}: {str(e)[:120]}")
                    continue
                if not f:
                    n_empty += 1
                    continue
                for s in want[cik]:
                    UD._write(sec_path(s), {"cik": cik, "f": f})
                n_ok += 1
    st = {"asof": today, "n": n_ok, "empty": n_empty, "miss": miss}
    UD._write(UD.data_dir() / "sec_meta.json.gz", st)
    _log(f"SEC：{n_ok} 家有資料、{n_empty} 家沒有要的項目、{miss} 檔找不到 CIK（{time.time() - t0:.0f}s）")
    return st


def status() -> str:
    m = load_meta()
    if not m.get("asof"):
        return "SEC 還沒抓" + ("" if contact() else f"（沒有設 {ENV}）")
    return f"SEC {m['asof']}：{m.get('n', 0)} 家有資料、{m.get('miss', 0)} 檔找不到 CIK"
