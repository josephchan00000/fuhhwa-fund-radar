"""台指期早盤策略（股票期貨人生）的資料層：期交所每筆成交＋證交所每 5 秒指數（docs/lab_fut_plan.md）。

期交所只公開「最近 30 個交易日」的每筆成交，更早的要付費申請（2026-10-27 探針：45 天前的還在、70 天前的已拿不到）
——所以每天都要抓、只增不改，晚一天就少一天。

落檔（一天一檔，`arm/lab/store.py` 慣例；不在任何 prune 清單裡，舊檔永遠保留）：

  data/lab/fut/tx/{日期}.json.gz
      {"d": 日期, "src": "taifex", "c": {到期月份: {"t": [...], "p": [...], "q": [...], "a": [...]}}}
      只收 TX（大台）單一月份契約、當天一般時段（08:45:00～13:45:00）的每一筆，順序照期交所檔案（同一秒內的先後也保留）。
      t＝當天第幾秒（第一筆是絕對值，之後是和前一筆的差）、p＝成交價（同樣差分）、q＝成交數量（B+S，買賣各算一次，2＝1 口）、
      a＝開盤集合競價那幾筆的位置（檔案「開盤集合競價」欄是 *）。夜盤不收（策略只做日盤）。
      一天約 4～5 萬筆、壓縮後約 60～100 KB。

  data/lab/fut/idx/{日期}.json.gz
      {"d": 日期, "src": "twse", "v": [...]}：證交所每 5 秒加權指數（MI_5MINS_INDEX），09:00:00 起到 13:30:00 共 3,241 個，
      單位＝0.01 點、差分存。09:00:00 那一個是前一天收盤，09:00:05 才是開盤（2026-10-27 探針三個年代都是這樣）。

python3 scripts/fetch_fut.py 每天補（afterhours_refresh.yml）；lab_backfill.yml mode=futfill 一次補完清單上的 30 天。
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
import zipfile
from datetime import date

from ..http import get_bytes
from . import store

TFX = "https://www.taifex.com.tw"
LIST_URL = TFX + "/cht/3/dlFutPrevious30DaysSalesData"
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
KIND_TX = "fut/tx"
KIND_IDX = "fut/idx"
DAY_FROM = 8 * 3600 + 45 * 60          # 08:45:00
DAY_TO = 13 * 3600 + 45 * 60           # 13:45:00
IDX_N = 3241                           # 09:00:00～13:30:00 每 5 秒


def log(*a) -> None:
    print("[fut]", *a, flush=True)


def _get(url: str, timeout: int = 120) -> bytes:
    return get_bytes(url, retries=2, timeout=timeout, use_cache=False, headers=BROWSER)


def tick_url(d: date) -> str:
    return f"{TFX}/file/taifex/Dailydownload/DailydownloadCSV/Daily_{d:%Y_%m_%d}.zip"


def list_days() -> list[date]:
    """期交所清單頁上「現在拿得到」的日子（最近 30 個交易日）。"""
    txt = _get(LIST_URL, timeout=90).decode("utf-8", "replace")
    out = {date(int(y), int(m), int(d)) for y, m, d in re.findall(r"Daily_(\d{4})_(\d{2})_(\d{2})\.zip", txt)}
    return sorted(out)


def sec(hms: str) -> int:
    hms = hms.strip().zfill(6)
    return int(hms[:2]) * 3600 + int(hms[2:4]) * 60 + int(hms[4:6])


def parse_csv(txt: str, d: date) -> dict[str, list[tuple[int, int, int, bool]]]:
    """期交所每筆成交 CSV → {到期月份: [(秒, 價, 量, 是否開盤集合競價)]}（只留 TX 單一月份、當天日盤，順序不變）。"""
    want = f"{d:%Y%m%d}"
    out: dict[str, list] = {}
    rd = csv.reader(io.StringIO(txt))
    head = next(rd, None)
    if not head or "成交日期" not in head[0]:
        raise ValueError(f"表頭不對：{head!r}")
    for r in rd:
        if len(r) < 6 or r[1].strip() != "TX" or r[0].strip() != want:
            continue
        exp = r[2].strip()
        if not re.fullmatch(r"\d{6}", exp):
            continue
        s = sec(r[3])
        if not DAY_FROM <= s <= DAY_TO:
            continue
        px = float(r[4])
        q = int(float(r[5]))
        out.setdefault(exp, []).append((s, int(round(px)), q, len(r) > 8 and r[8].strip() == "*"))
    for exp, rows in out.items():
        # 檔案本來就照時間排；保險起見做穩定排序（同一秒內的先後不動）
        if any(rows[i][0] < rows[i - 1][0] for i in range(1, len(rows))):
            rows.sort(key=lambda x: x[0])
    return out


def encode(rows: list[tuple[int, int, int, bool]]) -> dict:
    t, p, q, a = [], [], [], []
    ps = pp = 0
    for i, (s, px, qty, auc) in enumerate(rows):
        t.append(s - ps)
        p.append(px - pp)
        q.append(qty)
        ps, pp = s, px
        if auc:
            a.append(i)
    return {"t": t, "p": p, "q": q, "a": a}


def decode(c: dict) -> list[tuple[int, int, int, bool]]:
    out = []
    s = px = 0
    auc = set(c.get("a") or [])
    for i, (dt, dp, q) in enumerate(zip(c["t"], c["p"], c["q"])):
        s += dt
        px += dp
        out.append((s, px, q, i in auc))
    return out


def fetch_day(d: date) -> dict | None:
    b = _get(tick_url(d), timeout=180)
    if b[:2] != b"PK":
        log(f"每筆成交 {d}：不是 zip（{b[:60]!r}），可能已超過 30 個交易日或還沒公布")
        return None
    z = zipfile.ZipFile(io.BytesIO(b))
    raw = z.read(z.namelist()[0])
    try:
        txt = raw.decode("cp950")
    except UnicodeDecodeError:
        txt = raw.decode("cp950", "replace")
    rows = parse_csv(txt, d)
    if not rows:
        log(f"每筆成交 {d}：沒有 TX 日盤成交（休市？）")
        return None
    return {"d": d.isoformat(), "src": "taifex", "c": {k: encode(v) for k, v in sorted(rows.items())}}


def load_day(d: str) -> dict[str, list[tuple[int, int, int, bool]]] | None:
    doc = store.read(KIND_TX, d)
    if not doc:
        return None
    return {k: decode(v) for k, v in doc["c"].items()}


def fetch_idx(d: date) -> dict | None:
    url = f"https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_INDEX?date={d:%Y%m%d}&response=json"
    doc = json.loads(_get(url, timeout=60).decode("utf-8"))
    rows = doc.get("data") or []
    if doc.get("stat") != "OK" or not rows:
        log(f"5 秒指數 {d}：{doc.get('stat')}（{len(rows)} 列）")
        return None
    want = [f"{(9 * 3600 + 5 * k) // 3600:02d}:{(9 * 3600 + 5 * k) % 3600 // 60:02d}:{(9 * 3600 + 5 * k) % 60:02d}"
            for k in range(IDX_N)]
    got = {r[0].strip(): r[1] for r in rows if r and len(r) > 1}
    if len(got) < IDX_N * 0.98 or "09:00:05" not in got:
        log(f"5 秒指數 {d}：只有 {len(got)} 個時點（要 {IDX_N}），不存")
        return None
    v, prev, last = [], 0, None
    for t in want:
        x = got.get(t)
        if x is not None:
            last = int(round(float(str(x).replace(",", "")) * 100))
        if last is None:
            return None
        v.append(last - prev)
        prev = last
    return {"d": d.isoformat(), "src": "twse", "v": v}


def load_idx(d: str) -> list[float] | None:
    doc = store.read(KIND_IDX, d)
    if not doc:
        return None
    out, x = [], 0
    for dv in doc["v"]:
        x += dv
        out.append(x / 100)
    return out


def update(budget_s: float = 240, days: list[date] | None = None) -> dict:
    """清單上還沒存的日子補進來（只增不改），再補這些日子的 5 秒指數。回傳 {"tx": 新增天數, "idx": 新增天數}。"""
    t0 = time.time()
    n_tx = n_idx = 0
    if days is None:
        try:
            days = list_days()
        except Exception as e:                            # noqa: BLE001
            log(f"清單頁抓不到：{str(e)[:160]}")
            days = []
    have = set(store.dates(KIND_TX))
    log(f"期交所清單 {len(days)} 天（{days[0] if days else '—'}～{days[-1] if days else '—'}），已存 {len(have)} 天")
    for d in days:
        if time.time() - t0 > budget_s:
            log("時間到，下一輪續補")
            break
        if d.isoformat() in have:
            continue
        try:
            doc = fetch_day(d)
        except Exception as e:                            # noqa: BLE001
            log(f"每筆成交 {d} ✗ {str(e)[:160]}")
            continue
        if doc and store.write(KIND_TX, d.isoformat(), doc):
            n = sum(len(c["t"]) for c in doc["c"].values())
            log(f"每筆成交 {d}：存 {n} 筆（{', '.join(f'{k} {len(c['t'])}' for k, c in doc['c'].items())}）")
            n_tx += 1
        time.sleep(1)
    have_idx = set(store.dates(KIND_IDX))
    for d in sorted(set(store.dates(KIND_TX)) - have_idx):
        if time.time() - t0 > budget_s:
            break
        try:
            doc = fetch_idx(date.fromisoformat(d))
        except Exception as e:                            # noqa: BLE001
            log(f"5 秒指數 {d} ✗ {str(e)[:160]}")
            doc = None
        if doc and store.write(KIND_IDX, d, doc):
            n_idx += 1
        time.sleep(3)                                     # 證交所 www 端有頻率限制
    log(f"新增：每筆成交 {n_tx} 天、5 秒指數 {n_idx} 天")
    return {"tx": n_tx, "idx": n_idx}


def near(d: str, contracts: dict) -> str | None:
    """當天的近月契約＝還沒到期（到期月份 ≥ 當月）裡最近的那一個；結算日當天就是要結算的那一個。"""
    ym = d[:4] + d[5:7]
    cs = sorted(k for k in contracts if k >= ym)
    return cs[0] if cs else None
