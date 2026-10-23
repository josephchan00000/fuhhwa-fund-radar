"""美股飆股研究的資料（docs/lab_us_sleeve_plan.md 第 4.2、8 節；抓取只在 CI 跑，本容器擋 nasdaq／yahoo）。

範圍：那斯達克財報行事曆（usstk 的 earn/）出現過的全部代號＋指數 ETF（存活偏誤的量法與換指數那條用）。
股價：Yahoo 日線開高低收、成交量——Yahoo 回什麼就存什麼（分割已經還原、現金股利沒還原），另存配息、分割紀錄，
     2006 年起。已下市的公司 Yahoo 沒有（存活偏誤，docs 第 2 節）。
     存的是「抓的那天為準」的分割還原價（asof）：之後才發生的分割，讀的時候再用分割紀錄換算，舊檔不必重寫。

存檔：資料根目錄＝環境變數 USSX_DIR（研究時指到資料分支 claude/ussx-data 的 worktree），預設 data/lab/ussx/。
  px/{代號}.json.gz：{"asof": 抓的日期, "d0": 第一天, "dd": [和前一筆相隔幾個日曆天],
                       "c": [round(10000 ln 收盤) 和前一筆的差]（第一個是本身）,
                       "o"/"h"/"l": [round(10000 ln(價 ÷ 收盤))]（沒有＝0）,
                       "v": [round(100 ln(1＋成交量)) 和前一筆的差],
                       "div": [[日期, 每股現金股利]], "spl": [[日期, 新股數 ÷ 舊股數]]}
  meta.json.gz：{"px_done": {代號: 抓到幾天（0＝Yahoo 沒有）}, "fail": {代號: 失敗幾次}, "screen": 篩選器抓的日期}
  screen.json.gz：{代號: [交易所, 產業大類, 產業, 國家, IPO 年, 抓的那天的市值]}（那斯達克篩選器，是現在的分類）
"""
from __future__ import annotations

import gzip
import io
import json
import math
import os
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PX_START = "2006-01-01"
# 存活偏誤的量法（大型 RSP、中型 IJH／MDY、小型 IJR／IWM）＋換指數那條（QQQ、SOXX、IVW）＋成長股對照（IWF、IWO）
ETFS = ("SPY", "RSP", "IJH", "MDY", "IJR", "IWM", "QQQ", "SOXX", "IVW", "IWF", "IWO")
EXCHANGES = ("nasdaq", "nyse", "amex")
SCREEN_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&exchange={ex}&download=true"
CHART_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
             "?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit")
FAIL_MAX = 3                 # 同一檔失敗幾次就不再試（算做完，status 另外列出）
SAVE_EVERY = 200             # 每抓幾檔存一次 meta（中途被 timeout 砍掉也不白做）


def data_dir() -> Path:
    p = os.environ.get("USSX_DIR")
    return Path(p) if p else ROOT / "data" / "lab" / "ussx"


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
    with gzip.open(p, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def px_path(sym: str) -> Path:
    return data_dir() / "px" / f"{sym}.json.gz"


def load_meta() -> dict:
    m = _read(data_dir() / "meta.json.gz") or {}
    return {"px_done": m.get("px_done") or {}, "fail": m.get("fail") or {}, "screen": m.get("screen")}


def save_meta(doc: dict) -> bool:
    return _write(data_dir() / "meta.json.gz", doc)


def load_screen() -> dict:
    return _read(data_dir() / "screen.json.gz") or {}


# ── 範圍 ───────────────────────────────────────────────────────────────────────

def ysym(s: str) -> str:
    """財報行事曆與 SEC 的代號 → Yahoo 的寫法（BRK.B → BRK-B）。"""
    return s.strip().upper().replace(".", "-").replace("/", "-")


def calendar_symbols() -> list[str]:
    """那斯達克財報行事曆出現過的全部代號（usstk 的 earn/，是今天的代號）。"""
    from . import usstk
    out = set()
    for y in range(int(usstk.EARN_START[:4]), date.today().year + 1):
        for rows in (usstk.load_earn(y).get("rows") or {}).values():
            for r in rows:
                if r and r[0]:
                    out.add(ysym(str(r[0])))
    return sorted(out)


def universe() -> list[str]:
    return sorted(set(calendar_symbols()) | set(ETFS))


# ── Yahoo 日線 ─────────────────────────────────────────────────────────────────

def _local_date(ts, off: int) -> date:
    return datetime.fromtimestamp(int(ts) + off, timezone.utc).date()


def parse_chart(doc: dict, now: float | None = None) -> dict | None:
    """Yahoo chart（日線、events=div,split）→ {"d","o","h","l","c","v","div","spl"}；週末、還在交易中的那一天不收；
    收盤沒有的那天不收（開高低沒有的那天用收盤代替）。回應裡沒有 result＝None（查不到）。"""
    res = (((doc or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return None
    meta = res.get("meta") or {}
    off = int(meta.get("gmtoffset") or -18000)
    ts = res.get("timestamp") or []
    q = (((res.get("indicators") or {}).get("quote")) or [{}])[0] or {}
    reg = ((meta.get("currentTradingPeriod") or {}).get("regular")) or {}
    now = time.time() if now is None else now
    live = None
    try:
        if int(reg.get("start") or 0) <= now < int(reg.get("end") or 0):
            live = _local_date(reg["start"], off).isoformat()
    except (TypeError, ValueError):
        live = None

    def col(k):
        v = q.get(k) or []
        return lambda i: v[i] if i < len(v) else None

    O, H, L, C, V = col("open"), col("high"), col("low"), col("close"), col("volume")
    out = {"d": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    seen = set()
    for i, t in enumerate(ts):
        c = C(i)
        if c is None or not isinstance(c, (int, float)) or not (c > 0) or not math.isfinite(c):
            continue
        dd = _local_date(t, off)
        if dd.weekday() >= 5:
            continue
        d = dd.isoformat()
        if d == live or d in seen:
            continue
        seen.add(d)

        def ok(x):
            return float(x) if isinstance(x, (int, float)) and x > 0 and math.isfinite(x) else float(c)

        v = V(i)
        out["d"].append(d)
        out["c"].append(float(c))
        out["o"].append(ok(O(i)))
        out["h"].append(max(ok(H(i)), float(c)))
        out["l"].append(min(ok(L(i)), float(c)))
        out["v"].append(float(v) if isinstance(v, (int, float)) and v >= 0 and math.isfinite(v) else 0.0)
    ev = res.get("events") or {}
    div, spl = [], []
    for x in (ev.get("dividends") or {}).values():
        try:
            a = float(x.get("amount"))
            if a > 0 and math.isfinite(a):
                div.append([_local_date(x["date"], off).isoformat(), a])
        except (TypeError, ValueError, KeyError):
            continue
    for x in (ev.get("splits") or {}).values():
        try:
            n, m = float(x.get("numerator")), float(x.get("denominator"))
            if n > 0 and m > 0:
                spl.append([_local_date(x["date"], off).isoformat(), n / m])
        except (TypeError, ValueError, KeyError):
            continue
    out["div"] = sorted(div)
    out["spl"] = sorted(spl)
    return out


def enc_px(s: dict, asof: str) -> dict:
    """parse_chart 的結果 → 存檔格式（見檔頭）。"""
    ds = s.get("d") or []
    rec = {"asof": asof, "d0": ds[0] if ds else None, "dd": [], "c": [], "o": [], "h": [], "l": [], "v": [],
           "div": s.get("div") or [], "spl": s.get("spl") or []}
    if not ds:
        return rec
    prev_d, prev_c, prev_v = date.fromisoformat(ds[0]), None, None
    for k, d in enumerate(ds):
        x = date.fromisoformat(d)
        rec["dd"].append((x - prev_d).days)
        prev_d = x
        lc = round(10000.0 * math.log(s["c"][k]))
        rec["c"].append(lc if prev_c is None else lc - prev_c)
        prev_c = lc
        for key in ("o", "h", "l"):
            rec[key].append(round(10000.0 * math.log(s[key][k] / s["c"][k])))
        lv = round(100.0 * math.log1p(max(0.0, s["v"][k])))
        rec["v"].append(lv if prev_v is None else lv - prev_v)
        prev_v = lv
    return rec


def dec_px(rec: dict) -> dict:
    """存檔格式 → {"asof","d","o","h","l","c","v","div","spl"}（價格精度 1bp、量精度約 1%）。"""
    out = {"asof": (rec or {}).get("asof"), "d": [], "o": [], "h": [], "l": [], "c": [], "v": [],
           "div": (rec or {}).get("div") or [], "spl": (rec or {}).get("spl") or []}
    if not rec or not rec.get("d0"):
        return out
    d = date.fromisoformat(rec["d0"])
    acc_c = acc_v = 0
    for k, g in enumerate(rec["dd"]):
        if k:
            d = d + timedelta(days=g)
        acc_c = rec["c"][k] if k == 0 else acc_c + rec["c"][k]
        acc_v = rec["v"][k] if k == 0 else acc_v + rec["v"][k]
        c = math.exp(acc_c / 10000.0)
        out["d"].append(d.isoformat())
        out["c"].append(c)
        out["o"].append(c * math.exp(rec["o"][k] / 10000.0))
        out["h"].append(c * math.exp(rec["h"][k] / 10000.0))
        out["l"].append(c * math.exp(rec["l"][k] / 10000.0))
        out["v"].append(math.expm1(acc_v / 100.0))
    return out


def load_px(sym: str) -> dict:
    return dec_px(_read(px_path(sym)) or {})


def total_return_close(p: dict) -> list[float]:
    """含息還原收盤（以最後一天為準；除息日前的價格乘 (1 − 股利 ÷ 前一天收盤)，同 Yahoo 的算法）。
    存的價格已經是分割還原，股利也是同一個基準。"""
    import bisect
    c = p.get("c") or []
    if not c:
        return []
    ds = p["d"]
    f = [1.0] * len(c)                      # f[i]＝第 i 天除息的倍數，乘在第 i 天以前的每一天
    for d, a in p.get("div") or []:
        i = bisect.bisect_left(ds, d)       # 除息日剛好沒有交易（或資料缺那天）→ 算在之後的第一個交易日
        if i >= len(c) or i == 0:
            continue
        r = 1.0 - a / c[i - 1]
        if 0 < r < 1:
            f[i] *= r
    out = [0.0] * len(c)
    acc = 1.0
    for i in range(len(c) - 1, -1, -1):
        out[i] = c[i] * acc
        acc *= f[i]
    return out


# ── 抓取（只在 CI）─────────────────────────────────────────────────────────────

def _log(*a) -> None:
    print("[ussx]", *a, flush=True)


def _get(url: str, *, timeout: int = 60, headers: dict | None = None) -> bytes:
    from ..http import get_bytes
    return get_bytes(url, retries=2, timeout=timeout, use_cache=False, headers=headers)


def fetch_chart(sym: str, now: float | None = None) -> tuple[str, dict | None, str]:
    p1 = int(datetime.fromisoformat(PX_START).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time() if now is None else now)
    url = CHART_URL.format(sym=urllib.parse.quote(sym), p1=p1, p2=p2)
    for k in range(3):
        try:
            s = parse_chart(json.loads(_get(url, timeout=60).decode("utf-8")))
            return sym, (s if s is not None else {"d": []}), "ok"
        except Exception as e:                                # noqa: BLE001
            msg = str(e)
            if "404" in msg or "Not Found" in msg:
                return sym, {"d": []}, "404"
            if "429" in msg:
                time.sleep(5 * (k + 1))
                continue
            return sym, None, f"{type(e).__name__}: {msg[:160]}"
    return sym, None, "429"


def todo_px(meta: dict, syms: list[str]) -> list[str]:
    return [s for s in syms if s not in meta["px_done"] and meta["fail"].get(s, 0) < FAIL_MAX]


def backfill_px(*, budget_s: float = 2700, workers: int = 4) -> dict:
    """沒抓過的代號逐檔抓（失敗 FAIL_MAX 次就不再試）；時間到就存檔結束。"""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    meta = load_meta()
    syms = universe()
    todo = todo_px(meta, syms)
    st = {"universe": len(syms), "todo": len(todo), "ok": 0, "none": 0, "err": 0}
    asof = datetime.now(timezone.utc).date().isoformat()
    done_n = 0
    for a in range(0, len(todo), SAVE_EVERY):
        if time.time() - t0 > budget_s:
            break
        chunk = todo[a:a + SAVE_EVERY]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for sym, s, why in ex.map(fetch_chart, chunk):
                if s is None:
                    st["err"] += 1
                    meta["fail"][sym] = meta["fail"].get(sym, 0) + 1
                    if st["err"] <= 8:
                        _log(f"股價 {sym} ✗ {why}")
                    continue
                n = len(s.get("d") or [])
                if n:
                    _write(px_path(sym), enc_px(s, asof))
                    st["ok"] += 1
                else:
                    st["none"] += 1
                meta["px_done"][sym] = n
                done_n += 1
        save_meta(meta)
    left = len(todo_px(meta, syms))
    st["left"] = left
    _log(f"股價：範圍 {len(syms)} 檔、這次要抓 {len(todo)} 檔（有 {st['ok']}、Yahoo 沒有 {st['none']}、失敗 {st['err']}）；"
         f"還剩 {left} 檔（{time.time() - t0:.0f}s）")
    return st


def parse_screen(doc: dict, ex: str) -> dict:
    """那斯達克篩選器一個交易所 → {代號: [交易所, 產業大類, 產業, 國家, IPO 年, 市值]}。"""
    rows = (((doc or {}).get("data") or {}).get("rows")) or []
    out = {}
    for r in rows:
        sym = ysym(str(r.get("symbol") or ""))
        if not sym:
            continue
        try:
            cap = float(str(r.get("marketCap") or "").replace(",", "") or "nan")
        except ValueError:
            cap = float("nan")
        ipo = str(r.get("ipoyear") or "").strip()
        out[sym] = [ex, str(r.get("sector") or "").strip(), str(r.get("industry") or "").strip(),
                    str(r.get("country") or "").strip(), int(ipo) if ipo.isdigit() else None,
                    cap if math.isfinite(cap) else None]
    return out


def fetch_screen() -> dict:
    from .fwdfetch import NASDAQ_HDR
    out = {}
    for ex in EXCHANGES:
        try:
            doc = json.loads(_get(SCREEN_URL.format(ex=ex), timeout=90, headers=NASDAQ_HDR).decode("utf-8"))
            got = parse_screen(doc, ex)
            _log(f"篩選器 {ex}：{len(got)} 檔")
            for k, v in got.items():
                out.setdefault(k, v)
        except Exception as e:                                # noqa: BLE001
            _log(f"篩選器 {ex} ✗ {type(e).__name__}: {str(e)[:160]}")
    return out


def update_screen() -> int:
    """篩選器一天抓一次（三個交易所都要有才寫）。"""
    meta = load_meta()
    today = date.today().isoformat()
    if meta.get("screen") == today:
        return 0
    got = fetch_screen()
    exs = {v[0] for v in got.values()}
    if len(exs) < len(EXCHANGES):
        _log(f"篩選器只拿到 {sorted(exs)}，不寫")
        return 0
    _write(data_dir() / "screen.json.gz", got)
    meta["screen"] = today
    save_meta(meta)
    return len(got)


def status() -> str:
    """一行狀態：DONE／LEFT（給 workflow 判斷要不要再派一輪）；SEC 的狀態另外由 secfin.status() 接在後面。"""
    meta = load_meta()
    syms = universe()
    left = len(todo_px(meta, syms))
    have = sum(1 for s in syms if meta["px_done"].get(s))
    gave_up = sum(1 for s in syms if s not in meta["px_done"] and meta["fail"].get(s, 0) >= FAIL_MAX)
    head = "DONE" if left == 0 and meta.get("screen") else "LEFT"
    return (f"{head} 股價 {have}／{len(syms)} 檔有資料、還剩 {left} 檔、放棄 {gave_up} 檔；"
            f"篩選器 {meta.get('screen') or '還沒抓'}")
