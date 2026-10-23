"""美股個股策略的資料（docs/lab_core70_plan.md 第 8.3～8.4、9 節；抓取只在 CI 跑，本容器擋 nasdaq／yahoo）。

財報：那斯達克財報行事曆（api.nasdaq.com/api/calendar/earnings?date=），每一天公布的實際 EPS、市場預估、預估家數，
     2008 年起（2003 年回 0 家）。代號與公司名稱是「現在的」（2012 年的聯合技術寫成 RTX），已下市、被併購的公司
     多半不在裡面（存活偏誤）。公布時間（盤前／盤後）歷史資料一律 time-not-supplied → 研究一律用公布日的下一個交易日
     收盤進場（盤前、盤後公布都看得到）。
股價：Yahoo 日線的還原收盤（分割與股利都還原），2008 年以後還在 S&P 500 裡的歷史成分股（fja05680/sp500 的
     sp500_ticker_start_end.csv，代號是當時的代號）。已下市、改名的代號 Yahoo 多半沒有（404）→ 早年只有現在還在交易、
     代號沒改的公司（存活偏誤；有股價的比例另外記）。

存檔（data/lab/usstk/，必須入庫）：
  earn/{年}.json.gz ：{"done": [查過的日期], "rows": {日期: [[代號, 實際 EPS, 預估 EPS, 預估家數, 財報季度], ...]}}
  px/{代號}.json.gz ：{"d0": 第一天, "dd": [和前一筆相隔幾個日曆天], "lp": [round(10000 × ln 還原收盤) 和前一筆的差]}
                      （lp 第一個是本身；還原後的價格精度 1bp、不會累積誤差）
  meta.json.gz      ：{"spans": [[代號, 起日, 迄日或 null]], "px_done": {代號: 抓到幾天（0＝Yahoo 沒有）}}
"""
from __future__ import annotations

import gzip
import io
import json
import math
import re
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "data" / "lab" / "usstk"

EARN_START = "2008-01-01"            # 那斯達克財報行事曆 2008 年起才有資料（2003 年 0 家）
PX_START = "2006-01-01"              # 動能、52 週新高要往回看一年以上
MEMBER_FROM = "2008-01-01"           # 只抓這天以後還在 S&P 500 裡的成分股
SPANS_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
EARN_URL = "https://api.nasdaq.com/api/calendar/earnings?date={d}"


# ── 存檔 ───────────────────────────────────────────────────────────────────────

def _dump(doc) -> bytes:
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw)
    return buf.getvalue()


def _write(p: Path, doc) -> bool:
    data = _dump(doc)
    if p.exists() and p.read_bytes() == data:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return True


def _read(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))
    except Exception:                                         # noqa: BLE001 —— 壞檔視同不存在
        return None


def earn_path(year: int | str) -> Path:
    return DIR / "earn" / f"{year}.json.gz"


def load_earn(year: int | str) -> dict:
    doc = _read(earn_path(year)) or {}
    return {"done": sorted(set(doc.get("done") or [])), "rows": dict(doc.get("rows") or {})}


def save_earn(year: int | str, doc: dict) -> bool:
    rows = {d: sorted(v, key=lambda r: str(r[0])) for d, v in (doc.get("rows") or {}).items() if v}
    return _write(earn_path(year), {"done": sorted(set(doc.get("done") or [])), "rows": rows})


def px_path(sym: str) -> Path:
    return DIR / "px" / f"{sym}.json.gz"


def load_meta() -> dict:
    doc = _read(DIR / "meta.json.gz") or {}
    return {"spans": list(doc.get("spans") or []), "px_done": dict(doc.get("px_done") or {})}


def save_meta(doc: dict) -> bool:
    return _write(DIR / "meta.json.gz", {"spans": doc.get("spans") or [], "px_done": doc.get("px_done") or {}})


# ── 解析 ───────────────────────────────────────────────────────────────────────

_MONEY = re.compile(r"^\(?\s*-?\$?\s*-?([0-9][0-9,]*\.?[0-9]*)\s*\)?$")


def money(s) -> float | None:
    """'$1.76' → 1.76；'($0.60)' → −0.60；'-$0.60'、'$-0.60' → −0.60；'N/A'、'' → None。"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s) if math.isfinite(float(s)) else None
    t = str(s).strip()
    m = _MONEY.match(t)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    neg = t.startswith("(") or "-" in t
    return -v if neg else v


def earn_rows(doc: dict) -> list[list] | None:
    """財報行事曆一天的回應 → [[代號, 實際 EPS, 預估 EPS, 預估家數, 財報季度]]（實際 EPS 沒有的不收）。
    回應格式不對（不是 dict、沒有 data）→ None（不算查過）。data.rows 是 null＝那天沒有公司（算查過）。"""
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), dict):
        return None
    out = []
    for r in doc["data"].get("rows") or []:
        sym = str(r.get("symbol") or "").strip().upper()
        eps = money(r.get("eps"))
        if not sym or eps is None:
            continue
        try:
            n = int(str(r.get("noOfEsts") or "").strip())
        except ValueError:
            n = None
        out.append([sym, eps, money(r.get("epsForecast")), n, str(r.get("fiscalQuarterEnding") or "").strip()])
    return out


def ysym(s: str) -> str:
    return s.strip().upper().replace(".", "-").replace("/", "-")


def parse_spans(text: str) -> list[list]:
    """sp500_ticker_start_end.csv → [[Yahoo 代號, 起日, 迄日或 None]]（迄日＝離開指數那天）。"""
    import csv
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        t, a, z = (r.get("ticker") or "").strip(), (r.get("start_date") or "").strip(), (r.get("end_date") or "").strip()
        if t and a:
            out.append([ysym(t), a[:10], z[:10] or None])
    return out


def wanted(spans: list[list]) -> list[str]:
    """MEMBER_FROM 以後還在指數裡的代號。"""
    return sorted({s for s, a, z in spans if z is None or z > MEMBER_FROM})


def parse_chart_adj(doc: dict, now: float | None = None) -> dict[str, float]:
    """Yahoo chart（日線）→ {美東日期: 還原收盤}。週末、還在交易中的那一天不收。"""
    res = (((doc or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return {}
    meta = res.get("meta") or {}
    off = int(meta.get("gmtoffset") or -18000)
    ts = res.get("timestamp") or []
    adj = ((((res.get("indicators") or {}).get("adjclose")) or [{}])[0] or {}).get("adjclose") or []
    reg = ((meta.get("currentTradingPeriod") or {}).get("regular")) or {}
    now = time.time() if now is None else now
    live = None
    try:
        if int(reg.get("start") or 0) <= now < int(reg.get("end") or 0):
            live = datetime.fromtimestamp(int(reg["start"]) + off, timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        live = None
    out: dict[str, float] = {}
    for i, t in enumerate(ts):
        v = adj[i] if i < len(adj) else None
        if v is None or not (v > 0) or not math.isfinite(v):
            continue
        dd = datetime.fromtimestamp(int(t) + off, timezone.utc).date()
        if dd.weekday() >= 5:
            continue
        d = dd.isoformat()
        if d == live:
            continue
        out[d] = float(v)
    return out


def enc_px(series: dict[str, float]) -> dict:
    ds = sorted(series)
    if not ds:
        return {"d0": None, "dd": [], "lp": []}
    lps = [round(10000.0 * math.log(series[d])) for d in ds]
    d0 = date.fromisoformat(ds[0])
    dd, prev = [], d0
    for d in ds:
        x = date.fromisoformat(d)
        dd.append((x - prev).days)
        prev = x
    lp = [lps[0]] + [lps[i] - lps[i - 1] for i in range(1, len(lps))]
    return {"d0": ds[0], "dd": dd, "lp": lp}


def dec_px(rec: dict) -> tuple[list[str], list[float]]:
    if not rec or not rec.get("d0"):
        return [], []
    d = date.fromisoformat(rec["d0"])
    ds, px, acc = [], [], 0
    for k, (g, x) in enumerate(zip(rec["dd"], rec["lp"])):
        d = d + timedelta(days=g) if k else d
        acc = x if k == 0 else acc + x
        ds.append(d.isoformat())
        px.append(math.exp(acc / 10000.0))
    return ds, px


def load_px(sym: str) -> tuple[list[str], list[float]]:
    return dec_px(_read(px_path(sym)) or {})


def weekdays(a: str, b: str) -> list[str]:
    """a～b（含）之間的週一到週五。"""
    x, z, out = date.fromisoformat(a), date.fromisoformat(b), []
    while x <= z:
        if x.weekday() < 5:
            out.append(x.isoformat())
        x += timedelta(days=1)
    return out


def default_until(today: date | None = None) -> str:
    """回補查到哪一天：3 天前（盤後公布的財報隔天才進行事曆，太近的日子先不標成查過）。"""
    return ((today or date.today()) - timedelta(days=3)).isoformat()


def earn_pending(until: str) -> list[str]:
    """EARN_START～until 之間還沒查過的週一到週五。"""
    out = []
    for y in range(int(EARN_START[:4]), int(until[:4]) + 1):
        done = set(load_earn(y)["done"])
        a = max(EARN_START, f"{y}-01-01")
        b = min(until, f"{y}-12-31")
        out += [d for d in weekdays(a, b) if d not in done]
    return out


# ── 抓取（只在 CI）─────────────────────────────────────────────────────────────

def _log(*a) -> None:
    print("[usstk]", *a, flush=True)


def _get(url: str, *, timeout: int = 60, headers: dict | None = None) -> bytes:
    from ..http import get_bytes
    return get_bytes(url, retries=2, timeout=timeout, use_cache=False, headers=headers)


def fetch_earn_day(d: str) -> tuple[str, list | None, str]:
    from .fwdfetch import NASDAQ_HDR
    try:
        b = _get(EARN_URL.format(d=d), headers=NASDAQ_HDR, timeout=60)
        rows = earn_rows(json.loads(b.decode("utf-8")))
        return d, rows, "ok" if rows is not None else f"格式不對：{b[:120]!r}"
    except Exception as e:                                    # noqa: BLE001
        return d, None, f"{type(e).__name__}: {str(e)[:160]}"


def fetch_px(sym: str) -> tuple[str, dict | None, str]:
    p1 = int(datetime.fromisoformat(PX_START).replace(tzinfo=timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?period1={p1}&period2={int(time.time())}&interval=1d&events=div%2Csplit")
    for k in range(3):
        try:
            return sym, parse_chart_adj(json.loads(_get(url, timeout=60).decode("utf-8"))), "ok"
        except Exception as e:                                # noqa: BLE001
            s = str(e)
            if "404" in s or "Not Found" in s:
                return sym, {}, "404"
            if "429" in s:
                time.sleep(5 * (k + 1))
                continue
            return sym, None, f"{type(e).__name__}: {s[:160]}"
    return sym, None, "429"


def backfill_px(*, workers: int = 4, refresh: bool = False) -> dict:
    """成分股名單＋每檔股價（已抓過的跳過，refresh＝全部重抓）。回傳統計。"""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    meta = load_meta()
    try:
        meta["spans"] = parse_spans(_get(SPANS_URL, timeout=60).decode("utf-8"))
    except Exception as e:                                    # noqa: BLE001
        _log(f"成分股名單抓不到：{type(e).__name__}: {str(e)[:160]}（沿用既有 {len(meta['spans'])} 筆）")
    syms = wanted(meta["spans"])
    todo = [s for s in syms if refresh or s not in meta["px_done"]]
    st = {"members": len(syms), "todo": len(todo), "ok": 0, "none": 0, "err": 0}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for sym, ser, why in ex.map(fetch_px, todo):
            if ser is None:
                st["err"] += 1
                if st["err"] <= 8:
                    _log(f"股價 {sym} ✗ {why}")
                continue
            if ser:
                _write(px_path(sym), enc_px(ser))
                st["ok"] += 1
            else:
                st["none"] += 1
            meta["px_done"][sym] = len(ser)
    save_meta(meta)
    have = sum(1 for s in syms if meta["px_done"].get(s))
    _log(f"股價：成分股 {len(syms)} 檔、這次抓 {len(todo)} 檔（有 {st['ok']}、Yahoo 沒有 {st['none']}、失敗 {st['err']}）；"
         f"累計有股價 {have} 檔（{time.time() - t0:.0f}s）")
    return st


def backfill_earn(*, until: str | None = None, budget_s: float = 2700, workers: int = 2, pause: float = 0.4) -> dict:
    """財報行事曆逐日回補（已查過的日子跳過）。時間到就存檔結束；連續失敗 25 次＝停（STUCK）。"""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    until = until or default_until()
    todo = earn_pending(until)
    st = {"todo": len(todo), "ok": 0, "err": 0, "rows": 0, "stuck": False}
    by_year: dict[str, dict] = {}

    def doc_for(d: str) -> dict:
        y = d[:4]
        if y not in by_year:
            by_year[y] = load_earn(y)
        return by_year[y]

    def flush() -> None:
        for y, doc in by_year.items():
            save_earn(y, doc)

    fails, last_flush = 0, time.time()
    for i in range(0, len(todo), workers * 4):
        if time.time() - t0 > budget_s:
            break
        chunk = todo[i:i + workers * 4]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(fetch_earn_day, chunk))
        for d, rows, why in res:
            if rows is None:
                st["err"] += 1
                fails += 1
                if st["err"] <= 8:
                    _log(f"財報 {d} ✗ {why}")
                continue
            fails = 0
            doc = doc_for(d)
            doc["done"].append(d)
            if rows:
                doc["rows"][d] = rows
            st["ok"] += 1
            st["rows"] += len(rows)
        if fails >= 25:
            st["stuck"] = True
            _log("財報：連續失敗 25 次，停")
            break
        if time.time() - last_flush > 300:
            flush()
            last_flush = time.time()
        time.sleep(pause)
    flush()
    left = len(earn_pending(until))
    st["left"] = left
    _log(f"財報：要查 {len(todo)} 天、這次查了 {st['ok']} 天（{st['rows']} 筆）、失敗 {st['err']}、還剩 {left} 天"
         f"（{time.time() - t0:.0f}s）")
    return st


def status(until: str | None = None) -> str:
    """一行狀態：DONE／LEFT n（給 workflow 判斷要不要再派一輪）。"""
    until = until or default_until()
    meta = load_meta()
    syms = wanted(meta["spans"]) if meta["spans"] else []
    px_left = sum(1 for s in syms if s not in meta["px_done"]) if syms else -1
    left = len(earn_pending(until))
    have = sum(1 for s in syms if meta["px_done"].get(s))
    if left == 0 and px_left == 0:
        return f"DONE 財報都查過、股價 {have}／{len(syms)} 檔有資料"
    return f"LEFT 財報 {left} 天、股價 {px_left} 檔"
