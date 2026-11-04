"""選擇權資料探針（docs/lab_options_plan.md 第 4 節）：只看期交所的資料長什麼樣子、今天（週選結算日）的價格怎麼走，
不算任何策略的成績。CI 跑（容器連不到期交所），結果只印在日誌、不寫任何檔。

看四件事：
  ① 前 30 個交易日選擇權每筆成交（OptionsDaily_*.zip）：清單上有哪幾天、檔案多大、欄位、一天幾筆、有哪些到期別。
  ② 指定那天（預設今天）臺指選擇權每個到期別的成交量；當天到期那一個（週三或週五）各履約價的價格路徑：
     09:01 前後、最低、最高（含時間）、最後一筆——看「翻幾倍」是怎麼來的、拿到收盤又剩多少。
  ③ 選擇權每日交易行情（optDataDown，日資料）：查一天的欄位與筆數（歷史回測要用的那一份）。
  ④ 用 data/lab/fut/idx 的 5 秒加權指數算當天 13:00～13:30 的平均（約等於最後結算價），算當天到期的履約價最後值多少。
"""
from __future__ import annotations

import csv
import gzip
import io
import itertools
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

TFX = "https://www.taifex.com.tw"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
ROOT = Path(__file__).resolve().parent.parent


def get(url: str, data: dict | None = None, timeout: int = 120) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data else None
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def hms(s: int) -> str:
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def sec(t: str) -> int:
    t = t.strip().zfill(6)
    return int(t[:2]) * 3600 + int(t[2:4]) * 60 + int(t[4:6])


def idx_path(d: date):
    f = ROOT / f"data/lab/fut/idx/{d.isoformat()}.json.gz"
    if not f.exists():
        return None
    v = json.loads(gzip.decompress(f.read_bytes()))["v"]
    return [x / 100 for x in itertools.accumulate(v)]          # 09:00:00 起每 5 秒；第 0 個＝前一天收盤


def main() -> None:
    d = date.fromisoformat(os.environ.get("PROBE_DAY") or datetime.now().date().isoformat())
    print(f"== 探針日 {d}（{'一二三四五六日'[d.weekday()]}）")

    # ① 清單
    lst = get(TFX + "/cht/3/dlOptPrevious30DaysSalesData").decode("utf-8", "replace")
    names = sorted(set(re.findall(r"OptionsDaily_(\d{4}_\d{2}_\d{2})\.zip", lst)))
    print(f"① 清單上的每筆成交檔 {len(names)} 天：{names[:2]} … {names[-3:]}")
    links = sorted(set(re.findall(r'href="([^"]*OptionsDaily_[^"]*)"', lst)))[:3]
    print("   連結樣式：", links)
    url = f"{TFX}/file/taifex/Dailydownload/OptionsDailydownloadCSV/OptionsDaily_{d:%Y_%m_%d}.zip"
    t0 = time.time()
    raw = get(url, timeout=300)
    print(f"   下載 {url} {len(raw) / 1e6:.1f} MB，{time.time() - t0:.0f} 秒")
    zf = zipfile.ZipFile(io.BytesIO(raw))
    for zi in zf.infolist():
        print(f"   檔內 {zi.filename} 解壓 {zi.file_size / 1e6:.1f} MB")
    member = zf.infolist()[0]
    txt = zf.read(member).decode("big5", "replace")
    rd = csv.reader(io.StringIO(txt))
    head = next(rd)
    print("   表頭：", [h.strip() for h in head])
    rows = [r for r in rd if r]
    print(f"   總筆數 {len(rows):,}；前 3 筆：")
    for r in rows[:3]:
        print("     ", [x.strip() for x in r])
    # 欄位位置（照表頭找，找不到就用常見順序）
    H = [h.strip() for h in head]

    def col(*keys, default=None):
        for i, h in enumerate(H):
            if any(k in h for k in keys):
                return i
        return default
    c_day, c_prod, c_k, c_exp, c_cp = col("成交日期", default=0), col("商品代號", default=1), col("履約價", default=2), \
        col("到期月份", "週別", default=3), col("買賣權", default=4)
    c_t, c_p, c_q, c_open = col("成交時間", default=5), col("成交價格", default=6), col("成交數量", default=7), col("開盤集合競價")
    print(f"   欄位：日{c_day} 商品{c_prod} 履約價{c_k} 到期{c_exp} 買賣權{c_cp} 時間{c_t} 價{c_p} 量{c_q} 開盤競價{c_open}")

    want = f"{d:%Y%m%d}"
    prods = defaultdict(int)
    vol = defaultdict(int)
    path: dict[tuple, list] = defaultdict(list)
    night = 0
    for r in rows:
        if len(r) <= max(c_t, c_p, c_q):
            continue
        prods[r[c_prod].strip()] += 1
        if r[c_prod].strip() != "TXO":
            continue
        if r[c_day].strip() != want:
            night += 1
            continue
        s = sec(r[c_t])
        if not (8 * 3600 + 45 * 60 <= s <= 13 * 3600 + 45 * 60):
            night += 1
            continue
        exp, cp = r[c_exp].strip(), r[c_cp].strip()
        try:
            k = float(r[c_k]); p = float(r[c_p]); q = int(float(r[c_q]))
        except ValueError:
            continue
        vol[exp] += q
        path[(exp, cp, k)].append((s, p, q))
    print(f"② 商品筆數（前 8）：{sorted(prods.items(), key=lambda x: -x[1])[:8]}；TXO 非當天日盤的筆數 {night:,}")
    print("   TXO 日盤成交量（單邊口數÷2 前）依到期別：", sorted(vol.items(), key=lambda x: -x[1])[:8])

    px = idx_path(d)
    fsp = None
    if px:
        lo = min(px[1:]); hi = max(px[1:])
        print(f"   加權指數 昨收 {px[0]:,.2f}；高 {hi:,.2f}@{hms(9*3600+5*px[1:].index(hi)+5)}；低 {lo:,.2f}@{hms(9*3600+5*px[1:].index(lo)+5)}；13:30 {px[-1]:,.2f}")
        a = [v for i, v in enumerate(px) if 13 * 3600 <= 9 * 3600 + 5 * i <= 13 * 3600 + 30 * 60]
        fsp = sum(a) / len(a)
        print(f"   13:00～13:30 平均（約等於最後結算價）{fsp:,.2f}（{len(a)} 個值）")

    # 當天到期的那一個：成交量最大的到期別裡，名稱含 W 或 F 的週選，否則月選
    exps = sorted(vol, key=lambda x: -vol[x])
    for exp in exps[:4]:
        ks = sorted({k for (e, cp, k) in path if e == exp})
        print(f"\n   到期別 {exp}：履約價 {len(ks)} 個（{ks[0]:,.0f}～{ks[-1]:,.0f}），成交量 {vol[exp]:,}")
        if not px:
            continue
        mid = round(px[0] / 100) * 100
        pick = [k for k in ks if abs(k - mid) <= 2600 and k % 500 == 0]
        for cp in ("P", "C", "賣權", "買權"):
            keys = [(exp, cp, k) for k in pick if (exp, cp, k) in path]
            if not keys:
                continue
            print(f"     {cp}：履約價｜09:01 後第一筆｜最低(時間)｜最高(時間)｜最後一筆(時間)｜最高÷09:01｜結算時值")
            for key in keys:
                tr = path[key]
                after = [x for x in tr if x[0] >= 9 * 3600 + 60]
                if not after:
                    continue
                f0 = after[0]
                mn = min(tr, key=lambda x: x[1]); mx = max(after, key=lambda x: x[1]); ls = tr[-1]
                if fsp is not None:
                    iv = max(0.0, (fsp - key[2]) if cp in ("C", "買權") else (key[2] - fsp))
                else:
                    iv = float("nan")
                mult = mx[1] / f0[1] if f0[1] > 0 else float("nan")
                print(f"       {key[2]:>8,.0f}｜{f0[1]:>7.1f}@{hms(f0[0])}｜{mn[1]:>7.1f}@{hms(mn[0])}｜{mx[1]:>7.1f}@{hms(mx[0])}｜"
                      f"{ls[1]:>7.1f}@{hms(ls[0])}｜{mult:>6.1f}x｜{iv:>7.1f}")

    # ③ 日資料（選擇權每日交易行情）
    try:
        b = get(TFX + "/cht/3/optDataDown", {"down_type": "1", "commodity_id": "TXO", "commodity_id2": "",
                                           "queryStartDate": f"{d:%Y/%m/%d}", "queryEndDate": f"{d:%Y/%m/%d}"})
        t = b.decode("big5", "replace")
        lines = [x for x in t.splitlines() if x.strip()]
        print(f"\n③ 每日交易行情 {len(b) / 1e3:.0f} KB、{len(lines)} 行；表頭：{lines[0][:300] if lines else ''}")
        for x in lines[1:4]:
            print("     ", x[:300])
    except Exception as e:  # noqa: BLE001
        print("③ 每日交易行情失敗：", e)


if __name__ == "__main__":
    main()
