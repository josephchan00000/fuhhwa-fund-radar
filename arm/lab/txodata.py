"""台指選擇權資料（docs/lab_txo_plan.md 第 10、15 節）。只在 CI 跑（容器連不到期交所、證交所）。

資料寫進資料分支 claude/txo-data（**絕不合併進 main**，同 claude/ussx-data）：`.github/workflows/txo_data.yml` 把它 checkout 到
txodata/，`scripts/fetch_txo.py --root txodata` 寫入、再 commit 回去。路徑都相對於資料分支的根目錄：

  bars/{年}/{日期}.json.gz  期交所「前 30 個交易日選擇權每筆成交」（只留 30 個交易日，從現在起每天存）→ TXO 日盤每分鐘一根。
      只留到期日在 EXP_DAYS 天內、履約價在前一天加權指數 ±BAND 以內的契約：
      {"d": 日期, "ref": 前一天加權指數收盤（沒有就用成交量最大那檔的履約價）, "exp": {到期別: 到期日},
       "c": {"到期別|C或P|履約價": [[分鐘差, 開, 高−開, 開−低, 收−開, 量], ...]}}
      分鐘＝08:45 起第幾分鐘；價格 ×10 取整數（0.1 點）；量＝檔案的「成交數量(B or S)」加總（買賣各算一次，2＝1 口）。
  day/{年-月}.json.gz       期交所「選擇權每日交易行情」（optDataDown，一次最多查一個月；2002 年起）只留日盤（一般）、
      有成交或有未平倉或有結算價的列：{"m": 年-月, "cols": COLS, "rows": [[...], ...]}。
  idx/{年}/{日期}.json.gz   證交所每 5 秒加權指數（同 data/lab/fut/idx 的格式：0.01 點、差分存；futdata.fetch_idx）。
  state.json                {"idx_none": [證交所說沒有資料的日子]}（休市等，不再重抓）

輸出決定性（排序、gzip mtime＝0）：內容沒變時位元組相同，git 不會有空 commit。
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import re
import time
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

TFX = "https://www.taifex.com.tw"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
DAY_FROM = 8 * 3600 + 45 * 60           # 08:45:00
DAY_TO = 13 * 3600 + 45 * 60            # 13:45:00
EXP_DAYS = 45                           # 逐筆只留到期日在這麼多天（日曆天）以內的契約
BAND = 0.08                             # 逐筆只留履約價在前一天加權指數 ±8% 以內的契約
STEP = 1                                # 幾分鐘一根
COLS = ["d", "exp", "k", "cp", "o", "h", "l", "c", "v", "s", "oi", "bid", "ask", "xd"]   # 日行情存的欄位
IDX_FIRST = date(2016, 1, 4)            # 證交所每 5 秒指數：2016-01-04 已有完整 3,241 點（2012 年只有約 1,081 點，不收）


def log(*a) -> None:
    print("[txo]", *a, flush=True)


# ── 共用：抓取、寫檔 ──────────────────────────────────────────────────────────

def _get(url: str, data: dict | None = None, timeout: int = 180) -> bytes:
    from ..http import get_bytes
    if data is None:
        return get_bytes(url, retries=2, timeout=timeout, use_cache=False, headers=UA)
    import urllib.parse
    import urllib.request
    from ..http import _CTX  # noqa: PLC2701 —— 同一套 TLS 設定（certifi）
    body = urllib.parse.urlencode(data).encode()
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def dump(doc) -> bytes:
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw)
    return buf.getvalue()


def write(root: Path, rel: str, doc) -> bool:
    """寫一檔；內容沒變就不動。回傳有沒有寫。"""
    p = root / rel
    b = dump(doc)
    if p.exists() and p.read_bytes() == b:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(b)
    tmp.replace(p)
    return True


def read(root: Path, rel: str):
    p = root / rel
    if not p.exists():
        return None
    return json.loads(gzip.decompress(p.read_bytes()))


# ── 到期別 ────────────────────────────────────────────────────────────────────

def exp_date(code: str) -> date:
    """到期別 → 照規則推的到期日：YYYYMM＝第三個週三；YYYYMMWn＝第 n 個週三；YYYYMMFn＝第 n 個週五。
    遇到假日期交所會順延，有日行情的「契約到期日」時以它為準（day 檔的 xd 欄）。"""
    code = code.strip()
    y, m, tail = int(code[:4]), int(code[4:6]), code[6:].strip()
    if not tail:
        wd, n = 2, 3
    else:
        wd, n = (2 if tail[0] == "W" else 4), int(tail[1:])
    first = date(y, m, 1)
    return first + timedelta(days=(wd - first.weekday()) % 7 + 7 * (n - 1))


# ── 逐筆 → 分 K ───────────────────────────────────────────────────────────────

def _sec(t: str) -> int:
    t = t.strip().zfill(6)
    return int(t[:2]) * 3600 + int(t[2:4]) * 60 + int(t[4:6])


def parse_ticks(lines, d: date) -> dict[tuple[str, str, int], list[tuple[int, float, int]]]:
    """期交所選擇權每筆成交 CSV（一行一筆，第一行表頭）→ {(到期別, C/P, 履約價): [(秒, 價, 量)]}，只留 TXO、當天日盤。"""
    want = f"{d:%Y%m%d}"
    out: dict = defaultdict(list)
    rd = csv.reader(lines)
    head = next(rd, None)
    if not head or "成交日期" not in head[0]:
        raise ValueError(f"表頭不對：{head!r}")
    for r in rd:
        if len(r) < 8 or r[1].strip() != "TXO" or r[0].strip() != want:
            continue
        s = _sec(r[5])
        if not DAY_FROM <= s <= DAY_TO:
            continue
        try:
            k = int(round(float(r[2])))
            p = float(r[6])
            q = int(float(r[7]))
        except ValueError:
            continue
        out[(r[3].strip(), r[4].strip(), k)].append((s, p, q))
    return out


def to_bars(trades: list[tuple[int, float, int]], step: int = STEP) -> list[list[int]]:
    """一個契約的逐筆 → [[分鐘差, 開, 高−開, 開−低, 收−開, 量]]（價格 ×10 取整數）。"""
    cur: dict[int, list[int]] = {}
    for s, p, q in trades:
        m = (s - DAY_FROM) // (60 * step)
        pi = int(round(p * 10))
        b = cur.get(m)
        if b is None:
            cur[m] = [pi, pi, pi, pi, q]
        else:
            b[1] = max(b[1], pi)
            b[2] = min(b[2], pi)
            b[3] = pi
            b[4] += q
    rows, prev = [], 0
    for m in sorted(cur):
        o, h, lo, c, v = cur[m]
        rows.append([m - prev, o, h - o, o - lo, c - o, v])
        prev = m
    return rows


def from_bars(rows: list[list[int]], step: int = STEP) -> list[tuple[int, float, float, float, float, int]]:
    """to_bars 的反向：→ [(那一根開始的秒數, 開, 高, 低, 收, 量)]。"""
    out, m = [], 0
    for dm, o, dh, dl, dc, v in rows:
        m += dm
        out.append((DAY_FROM + m * 60 * step, o / 10, (o + dh) / 10, (o - dl) / 10, (o + dc) / 10, v))
    return out


def bars_doc(d: date, ticks: dict, ref: float | None, step: int = STEP) -> dict:
    """當天的逐筆 → bars 檔內容（只留到期日在 EXP_DAYS 天內、履約價在 ref ±BAND 內的契約）。"""
    if ref is None:                                   # 沒有前一天收盤：用成交量最大那檔的履約價當中心
        vol: dict[int, int] = defaultdict(int)
        for (_, _, k), tr in ticks.items():
            vol[k] += sum(q for _, _, q in tr)
        ref = float(max(vol, key=vol.get)) if vol else 0.0
    exps = {}
    for e in {k[0] for k in ticks}:
        try:
            xd = exp_date(e)
        except (ValueError, IndexError):
            continue
        if d <= xd <= d + timedelta(days=EXP_DAYS):
            exps[e] = xd.isoformat()
    c = {}
    for (e, cp, k), tr in ticks.items():
        if e in exps and abs(k - ref) <= ref * BAND and tr:
            c[f"{e}|{cp}|{k}"] = to_bars(tr, step)
    return {"d": d.isoformat(), "src": "taifex", "ref": round(ref, 2), "step": step, "exp": exps, "c": c}


def tick_url(d: date) -> str:
    return f"{TFX}/file/taifex/Dailydownload/OptionsDailydownloadCSV/OptionsDaily_{d:%Y_%m_%d}.zip"


def tick_days() -> list[date]:
    """期交所清單上現在拿得到的日子（最近 30 個交易日）。"""
    txt = _get(TFX + "/cht/3/dlOptPrevious30DaysSalesData", timeout=90).decode("utf-8", "replace")
    return sorted({date(int(y), int(m), int(dd)) for y, m, dd in re.findall(r"OptionsDaily_(\d{4})_(\d{2})_(\d{2})\.zip", txt)})


def fetch_bars(d: date, ref: float | None) -> dict | None:
    b = _get(tick_url(d), timeout=300)
    if b[:2] != b"PK":
        log(f"逐筆 {d}：不是 zip（{b[:60]!r}），可能已超過 30 個交易日或還沒公布")
        return None
    z = zipfile.ZipFile(io.BytesIO(b))
    with z.open(z.namelist()[0]) as f:
        ticks = parse_ticks(io.TextIOWrapper(f, encoding="cp950", errors="replace", newline=""), d)
    if not ticks:
        log(f"逐筆 {d}：沒有 TXO 日盤成交（休市？）")
        return None
    return bars_doc(d, ticks, ref)


# ── 日行情 ────────────────────────────────────────────────────────────────────

def _num(x: str):
    x = (x or "").strip().replace(",", "")
    if x in ("", "-"):
        return None
    try:
        v = float(x)
    except ValueError:
        return None
    return int(v) if v == int(v) else v


def parse_day(txt: str) -> list[list]:
    """選擇權每日交易行情 CSV → [[d, exp, k, cp, o, h, l, c, v, s, oi, bid, ask, xd]]（只留日盤、有成交或未平倉或結算價的 TXO）。"""
    lines = [x for x in txt.splitlines() if x.strip()]
    if not lines or "交易日期" not in lines[0]:
        raise ValueError(f"表頭不對：{lines[:1]!r}")
    head = [h.strip() for h in next(csv.reader([lines[0]]))]

    def ix(name: str) -> int | None:
        return next((i for i, h in enumerate(head) if h.startswith(name)), None)
    I = {k: ix(n) for k, n in (("d", "交易日期"), ("pid", "契約"), ("exp", "到期月份"), ("k", "履約價"), ("cp", "買賣權"),
                                ("o", "開盤價"), ("h", "最高價"), ("l", "最低價"), ("c", "收盤價"), ("v", "成交量"),
                                ("s", "結算價"), ("oi", "未沖銷契約數"), ("bid", "最後最佳買價"), ("ask", "最後最佳賣價"),
                                ("sess", "交易時段"), ("xd", "契約到期日"))}
    out = []
    for r in csv.reader(lines[1:]):
        def g(k):
            i = I.get(k)
            return r[i].strip() if i is not None and i < len(r) else ""
        if g("pid") != "TXO" or (g("sess") and g("sess") != "一般"):
            continue
        row = {k: _num(g(k)) for k in ("o", "h", "l", "c", "v", "s", "oi", "bid", "ask")}
        if not ((row["v"] or 0) > 0 or (row["oi"] or 0) > 0 or (row["s"] or 0) > 0):
            continue
        cp = "C" if g("cp") in ("買權", "C", "Call") else "P"
        xd = g("xd")
        out.append([g("d").replace("/", "-"), g("exp").replace(" ", ""), int(round(float(g("k") or 0))), cp,
                    row["o"], row["h"], row["l"], row["c"], row["v"], row["s"], row["oi"], row["bid"], row["ask"],
                    f"{xd[:4]}-{xd[4:6]}-{xd[6:8]}" if len(xd) == 8 and xd.isdigit() else None])
    return out


def fetch_day_month(y: int, m: int, today: date) -> dict | None:
    a = date(y, m, 1)
    z = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    z = min(z, today)
    b = _get(TFX + "/cht/3/optDataDown", {"down_type": "1", "commodity_id": "TXO", "commodity_id2": "",
                                          "queryStartDate": f"{a:%Y/%m/%d}", "queryEndDate": f"{z:%Y/%m/%d}"})
    txt = b.decode("cp950", "replace")
    if "交易日期" not in txt[:200]:
        log(f"日行情 {y}-{m:02d}：回應不是 CSV（{txt[:80]!r}）")
        return None
    rows = parse_day(txt)
    return {"m": f"{y}-{m:02d}", "src": "taifex", "cols": COLS, "rows": rows}


# ── 主程式用：更新 ────────────────────────────────────────────────────────────

def ref_close(root: Path, main_root: Path, d: date) -> float | None:
    """d 的前一天加權指數收盤：先找資料分支的 idx、再找 main 的 data/lab/fut/idx（第 0 個值＝前一天收盤）。"""
    for p in (root / f"idx/{d.year}/{d.isoformat()}.json.gz", main_root / f"data/lab/fut/idx/{d.isoformat()}.json.gz"):
        if p.exists():
            v = json.loads(gzip.decompress(p.read_bytes())).get("v") or []
            if v:
                return v[0] / 100
    return None


def update_bars(root: Path, main_root: Path, deadline: float) -> int:
    n = 0
    for d in tick_days():
        rel = f"bars/{d.year}/{d.isoformat()}.json.gz"
        if (root / rel).exists() or time.time() > deadline:
            continue
        doc = fetch_bars(d, ref_close(root, main_root, d))
        if doc:
            write(root, rel, doc)
            n += 1
            log(f"逐筆 {d}：{len(doc['c'])} 個契約、{sum(len(v) for v in doc['c'].values()):,} 根")
    return n


def update_day(root: Path, start: str, today: date, deadline: float) -> int:
    """日行情：start（年-月）起每個月一檔；已存的月份跳過，但這個月與上個月一定重抓（月中還在長）。"""
    y, m = int(start[:4]), int(start[5:7])
    keep = {f"{today.year}-{today.month:02d}", f"{(today.replace(day=1) - timedelta(days=1)):%Y-%m}"}
    n = 0
    while (y, m) <= (today.year, today.month):
        tag = f"{y}-{m:02d}"
        rel = f"day/{tag}.json.gz"
        if time.time() > deadline:
            break
        if not (root / rel).exists() or tag in keep:
            doc = fetch_day_month(y, m, today)
            if doc and doc["rows"]:
                if write(root, rel, doc):
                    n += 1
                    log(f"日行情 {tag}：{len(doc['rows']):,} 列")
            time.sleep(1.0)
        y, m = (y + (m == 12), m % 12 + 1)
    return n


def update_idx(root: Path, start: date, today: date, deadline: float, pause: float = 2.0) -> int:
    from . import futdata
    st = read_state(root)
    none = set(st.get("idx_none") or [])
    n, d = 0, start
    while d <= today and time.time() < deadline:
        rel = f"idx/{d.year}/{d.isoformat()}.json.gz"
        if d.weekday() < 5 and not (root / rel).exists() and d.isoformat() not in none:
            try:
                doc = futdata.fetch_idx(d)
            except Exception as e:  # noqa: BLE001 —— 一天失敗就跳過，下次再補
                log(f"5 秒指數 {d}：{type(e).__name__}: {e}")
                doc = False
            if doc:
                write(root, rel, doc)
                n += 1
            elif doc is None and d < today:
                none.add(d.isoformat())
            time.sleep(pause)
        d += timedelta(days=1)
    st["idx_none"] = sorted(none)
    write_state(root, st)
    return n


def read_state(root: Path) -> dict:
    p = root / "state.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def write_state(root: Path, st: dict) -> None:
    (root / "state.json").write_text(json.dumps(st, ensure_ascii=False, sort_keys=True, indent=1) + "\n", "utf-8")


# ── 台指期每日行情（日盤＋夜盤；盤前作戰圖第 3 段驗證用，docs/lab_premarket_plan.md 第 11 節）────────────

FUT_COLS = ["d", "exp", "sess", "o", "h", "l", "c", "v", "s", "oi"]   # sess：D＝一般（日盤）、N＝盤後（夜盤，交易日期記下一個交易日）
FUT_FIRST = "2017-05"                                                  # 夜盤 2017-05-15 開始


def parse_futday(txt: str) -> list[list]:
    """期貨每日交易行情 CSV（futDataDown，契約 TX）→ 單一月份契約的列（價差單不收）。"""
    lines = [x for x in txt.splitlines() if x.strip()]
    if not lines or "交易日期" not in lines[0]:
        raise ValueError(f"表頭不對：{lines[:1]!r}")
    head = [h.strip() for h in next(csv.reader([lines[0]]))]

    def ix(name: str) -> int | None:
        return next((i for i, h in enumerate(head) if h.startswith(name)), None)
    I = {k: ix(n) for k, n in (("d", "交易日期"), ("pid", "契約"), ("exp", "到期月份"), ("o", "開盤價"), ("h", "最高價"),
                                ("l", "最低價"), ("c", "收盤價"), ("v", "成交量"), ("s", "結算價"), ("oi", "未沖銷契約數"),
                                ("sess", "交易時段"))}
    out = []
    for r in csv.reader(lines[1:]):
        if len(r) <= max(v for v in I.values() if v is not None):
            continue
        if r[I["pid"]].strip() != "TX":
            continue
        exp = r[I["exp"]].strip()
        if "/" in exp or not exp:
            continue
        sess = r[I["sess"]].strip() if I["sess"] is not None else "一般"
        d = r[I["d"]].strip().replace("/", "-")
        out.append([d, exp, "N" if sess == "盤後" else "D", _num(r[I["o"]]), _num(r[I["h"]]), _num(r[I["l"]]),
                    _num(r[I["c"]]), _num(r[I["v"]]) or 0, _num(r[I["s"]]), _num(r[I["oi"]])])
    return sorted(out)


def fetch_futday_month(y: int, m: int, today: date) -> dict | None:
    a = date(y, m, 1)
    z = min(date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1), today)
    b = _get(TFX + "/cht/3/futDataDown", {"down_type": "1", "commodity_id": "TX", "commodity_id2": "",
                                          "queryStartDate": f"{a:%Y/%m/%d}", "queryEndDate": f"{z:%Y/%m/%d}"})
    txt = b.decode("cp950", "replace")
    if "交易日期" not in txt[:200]:
        log(f"期貨日行情 {y}-{m:02d}：回應不是 CSV（{txt[:80]!r}）")
        return None
    return {"m": f"{y}-{m:02d}", "src": "taifex", "cols": FUT_COLS, "rows": parse_futday(txt)}


def update_futday(root: Path, start: str, today: date, deadline: float) -> int:
    """futday/{年-月}.json.gz：start 起每個月一檔；已存的跳過，這個月與上個月一定重抓。"""
    y, m = int(start[:4]), int(start[5:7])
    keep = {f"{today.year}-{today.month:02d}", f"{(today.replace(day=1) - timedelta(days=1)):%Y-%m}"}
    n = 0
    while (y, m) <= (today.year, today.month) and time.time() < deadline:
        tag = f"{y}-{m:02d}"
        rel = f"futday/{tag}.json.gz"
        if not (root / rel).exists() or tag in keep:
            try:
                doc = fetch_futday_month(y, m, today)
            except Exception as e:  # noqa: BLE001 —— 一個月失敗就跳過，下次再補
                log(f"期貨日行情 {tag}：{type(e).__name__}: {e}")
                doc = None
            if doc and doc["rows"] and write(root, rel, doc):
                n += 1
                log(f"期貨日行情 {tag}：{len(doc['rows']):,} 列")
            time.sleep(1.0)
        y, m = (y + (m == 12), m % 12 + 1)
    return n
