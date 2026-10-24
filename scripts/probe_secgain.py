#!/usr/bin/env python3
"""SEC 財報裡「一次性利得／損失」項目的探針（美股三成營益率的一次性收入研究，2026-10-24；只在 CI 跑、只印不存檔）。

背景：美股強勢品質股的營益率＝最近一季營業利益 ÷ 營收。CareDx（CDNA）2026 年第 2 季賣掉實驗室產品部門，利得算進營業利益，
營益率跳到 85.8%（前幾季都在 0% 上下）。要扣掉這類利得，得先知道公司在 XBRL 裡用哪些項目、多少公司有寫。

印兩段：
  1. 幾家公司（現在名單上的 13 檔）近兩年每一季、名稱像「利得／處分／出售／減損／重組／其他營業」的項目與數值；
  2. 全部有代號的公司：這類項目各有幾家公司寫過「單季」的數字（2010 年起），以及數值超過那一季營收 5% 的次數。
聯絡 email 只從 SEC_CONTACT_EMAIL 讀（arm/lab/secfin.py），不印、不存。

  python3 scripts/probe_secgain.py        # lab_backfill.yml 的 secprobe 模式（.ping/lab 第一行 secprobe）
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import secfin as SF  # noqa: E402

SAMPLE = ["CDNA", "INSW", "VLO", "DINO", "MPC", "ANF", "ILMN", "FTNT", "PAYC", "QLYS", "HALO", "NTAP", "LPG"]
PAT = re.compile(r"Gain|Disposal|Divest|SaleOf|Impairment|Restructuring|OtherOperating|Litigation|Settlement|Insurance", re.I)
REV = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet")
CIK_FILE = re.compile(r"CIK(\d{10})\.json$")


def _days(s: str, e: str) -> int:
    return (date.fromisoformat(e) - date.fromisoformat(s)).days


def quarters(rows: list, since: str) -> dict[str, float]:
    """單季（80～100 天）、10-Q／10-K 的數字：{迄日: 數值}（同一季取第一次公布的）。"""
    best: dict[str, tuple] = {}
    for r in rows or []:
        if r.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A"):
            continue
        s, e, v, fd = r.get("start"), r.get("end"), r.get("val"), r.get("filed") or ""
        if not s or not e or v is None or e < since:
            continue
        try:
            if not 80 <= _days(s, e) <= 100:
                continue
        except ValueError:
            continue
        if e not in best or fd < best[e][0]:
            best[e] = (fd, float(v))
    return {e: v for e, (_, v) in best.items()}


def usd(units: dict) -> list:
    return (units or {}).get("USD") or []


def sample(email: str, tick: dict) -> None:
    print("== 1. 名單上的公司：近兩年每一季的相關項目（百萬美元） ==", flush=True)
    for s in SAMPLE:
        cik = tick.get(s)
        if not cik:
            print(f"{s}: 找不到 CIK")
            continue
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        try:
            with SF._open(url, email, timeout=60) as r:
                doc = json.loads(r.read().decode("utf-8"))
        except Exception as e:                                  # noqa: BLE001
            print(f"{s}: 抓不到（{type(e).__name__}: {str(e)[:120]}）")
            continue
        g = (doc.get("facts") or {}).get("us-gaap") or {}
        rev = {}
        for t in REV:
            for e, v in quarters(usd((g.get(t) or {}).get("units")), "2024-07-01").items():
                rev.setdefault(e, v)
        oi = quarters(usd((g.get("OperatingIncomeLoss") or {}).get("units")), "2024-07-01")
        print(f"-- {s}（CIK {cik}）營收 {', '.join(f'{e[:7]} {v / 1e6:,.0f}' for e, v in sorted(rev.items())[-4:])}")
        print(f"   營業利益 {', '.join(f'{e[:7]} {v / 1e6:,.0f}' for e, v in sorted(oi.items())[-4:])}")
        for tag in sorted(g):
            if not PAT.search(tag):
                continue
            q = quarters(usd((g[tag] or {}).get("units")), "2024-07-01")
            if q:
                print(f"   {tag}: " + ", ".join(f"{e[:7]} {v / 1e6:,.1f}" for e, v in sorted(q.items())[-4:]))
        time.sleep(0.2)


def bulk(email: str, tick: dict) -> None:
    print("== 2. 全部有代號的公司：這類項目寫過單季數字的家數（2010 年起）＋超過那一季營收 5% 的次數 ==", flush=True)
    ciks = set(tick.values())
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        zp = Path(td) / "companyfacts.zip"
        size = SF.download_bulk(email, zp)
        print(f"companyfacts.zip {size / 1e6:.0f} MB（{time.time() - t0:.0f}s）", flush=True)
        firms: Counter = Counter()
        big: Counter = Counter()
        n_co = n_q = n_extreme = n_extreme_tag = 0
        ex_tags: Counter = Counter()
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                m = CIK_FILE.search(name)
                if not m or int(m.group(1)) not in ciks:
                    continue
                try:
                    g = (json.loads(z.read(name).decode("utf-8")).get("facts") or {}).get("us-gaap") or {}
                except Exception:                               # noqa: BLE001
                    continue
                rev: dict = {}
                for t in REV:
                    for e, v in quarters(usd((g.get(t) or {}).get("units")), "2010-01-01").items():
                        rev.setdefault(e, v)
                if not rev:
                    continue
                n_co += 1
                oi = quarters(usd((g.get("OperatingIncomeLoss") or {}).get("units")), "2010-01-01")
                tagq = {}
                for tag in g:
                    if not PAT.search(tag):
                        continue
                    q = quarters(usd((g[tag] or {}).get("units")), "2010-01-01")
                    if not q:
                        continue
                    firms[tag] += 1
                    tagq[tag] = q
                    for e, v in q.items():
                        r = rev.get(e)
                        if r and r > 0 and abs(v) > 0.05 * r:
                            big[tag] += 1
                for e, o in oi.items():                         # 營益率 50% 以上的季：同一季有沒有寫這類項目
                    r = rev.get(e)
                    if not r or r <= 0:
                        continue
                    n_q += 1
                    if o / r >= 0.5:
                        n_extreme += 1
                        hit = [t for t, q in tagq.items() if e in q and q[e] and abs(q[e]) > 0.05 * r]
                        if hit:
                            n_extreme_tag += 1
                            ex_tags.update(hit)
                if n_co % 2000 == 0:
                    print(f"  …{n_co} 家（{time.time() - t0:.0f}s）", flush=True)
    print(f"有營收單季數字的公司 {n_co} 家、公司季 {n_q:,} 個（{time.time() - t0:.0f}s）")
    print(f"營益率 ≥ 50% 的公司季 {n_extreme:,} 個；同一季有這類項目超過營收 5% 的 {n_extreme_tag:,} 個")
    print("那些季最常見的項目：" + "、".join(f"{t} {n}" for t, n in ex_tags.most_common(15)))
    print("寫過的家數前 40：")
    for t, n in firms.most_common(40):
        print(f"  {t}: {n} 家，超過營收 5% 的季 {big[t]:,} 次")


def main() -> None:
    email = SF.contact()
    if not email:
        print(f"沒有設 {SF.ENV}（GitHub secret），探針跳過")
        return
    tick = SF.fetch_tickers(email)
    print(f"代號對照 {len(tick)} 筆", flush=True)
    sample(email, tick)
    bulk(email, tick)


if __name__ == "__main__":
    main()
