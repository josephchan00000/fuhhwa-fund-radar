"""台指期早盤策略：每天盤前取樣（docs/lab_fut_plan.md 第 4.4、10 節；即時版用，估算方法寫在 futspec VER 2）。

開盤前的試撮價只有即時的，沒有歷史檔，所以每個交易日自己存：
  08:58:00～09:00:15 每 5 秒一輪（TICKS），每輪：
    證交所 MIS 兩個請求，各 BATCH 檔（前一個交易日市值比重前 TOP_N 檔上市股票，分三批輪流；第一個請求另帶加權指數 t00、櫃買指數 o00）；
    期交所 MIS 一個請求（台指期每個契約，含「臺指現貨」那一列）。
  證交所 MIS 一次 50 檔約 1.8 秒、150 檔要 10 秒、200 檔回不來（2026-10-27 探針），所以一批 50 檔、一輪兩批：
  每 5 秒對證交所最多兩個請求（比一般說的每 5 秒 3 個少），每檔約每 7.5 秒更新一次。
存 data/lab/fut/pre/{日期}.json.gz（一天一檔、只增不改）：
  {"d", "dp" 比重用的前一個交易日, "syms" 依比重排的代號, "w" 比重, "y" 前一天收盤（MIS 的 y）,
   "tw_f" / "tf_f" 欄位名稱, "s": [每個請求一筆]}
  每筆＝{"k": "tw"／"tf", "t0"／"t1" 請求開始／收到的時間（台北，當天第幾秒，到 0.01 秒）, "b" 第幾批, "r": {代號: 變了的欄位}}
  「變了的欄位」＝跟同一檔上一次比，第一次是完整的陣列，之後是 {欄位位置: 新值}（沒變就不記）；decode() 還原。
"""
from __future__ import annotations

import json
import time
import urllib.request

from . import futsig as G
from . import store

KIND = "fut/pre"
TOP_N = 150
BATCH = 50
PER_TICK = 2
START_S = 8 * 3600 + 58 * 60          # 08:58:00
END_S = 9 * 3600 + 15                 # 09:00:15（含）
STEP = 5
IDX = ("t00", "o00")
TW_F = ("pz", "ps", "z", "tv", "a1", "b1", "f1", "g1", "o", "h", "l", "v", "ip", "ts", "t", "tlong", "%")
TF_F = ("CLastPrice", "CTime", "CTestPrice", "CTestTime", "CTestVolume", "CBidPrice1", "CAskPrice1",
        "CTotalVolume", "COpenPrice", "CHighPrice", "CLowPrice", "CRefPrice", "Status")
MIS_TW = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex}&json=1&delay=0&_={ms}"
MIS_TF = "https://mis.taifex.com.tw/futures/api/getQuoteList"
TF_BODY = {"MarketType": "0", "SymbolType": "F", "KindID": "1", "CID": "TXF", "ExpireMonth": "",
           "RowSize": "全部", "PageNo": "", "SortColumn": "", "AscDesc": "A"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def log(*a) -> None:
    print("[futpre]", *a, flush=True)


def ticks(start: int = START_S, end: int = END_S, step: int = STEP) -> list[int]:
    return list(range(start, end + 1, step))


def batches(syms: list[str], size: int = BATCH) -> list[list[str]]:
    return [syms[i:i + size] for i in range(0, len(syms), size)]


def plan(n_batches: int, n_ticks: int, per_tick: int = PER_TICK) -> list[list[int]]:
    """每一輪要抓哪幾批：依序輪流（第 0 輪 0、1，第 1 輪 2、0，…）。"""
    out, k = [], 0
    for _ in range(n_ticks):
        out.append([(k + j) % n_batches for j in range(min(per_tick, n_batches))])
        k += per_tick
    return out


def top_symbols(dprev: str, n: int = TOP_N) -> tuple[list[str], dict[str, float]]:
    """前一個交易日市值比重前 n 檔上市普通股（futsig.weights 同一套比重）。"""
    w = G.weights(dprev)
    syms = [c for c, _ in sorted(w.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]
    return syms, {c: round(w[c], 7) for c in syms}


def tw_row(m: dict) -> list[str]:
    """證交所 MIS 一檔 → TW_F 順序的字串陣列（委買委賣只留第一檔）。"""
    first = lambda k: str(m.get(k, "")).split("_")[0]                     # noqa: E731
    pick = {"a1": first("a"), "b1": first("b"), "f1": first("f"), "g1": first("g")}
    return [pick[k] if k in pick else str(m.get(k, "")) for k in TW_F]


def tf_row(m: dict) -> list[str]:
    return [str(m.get(k, "")) for k in TF_F]


def _get_tw(codes: list[str], timeout: int = 6) -> tuple[list[dict] | None, str]:
    ex = "|".join((f"tse_{c}.tw" if c != "o00" else "otc_o00.tw") for c in codes)
    url = MIS_TW.format(ex=ex, ms=int(time.time() * 1000))
    try:
        from ..http import _CTX
        req = urllib.request.Request(url, headers={**UA, "Referer": "https://mis.twse.com.tw/stock/index.jsp"})
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return json.loads(r.read().decode("utf-8")).get("msgArray") or [], f"HTTP {r.status}"
    except Exception as e:                                                # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def _get_tf(timeout: int = 4) -> tuple[list[dict] | None, str]:
    try:
        from ..http import _CTX
        req = urllib.request.Request(MIS_TF, data=json.dumps(TF_BODY).encode(), headers={
            **UA, "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://mis.taifex.com.tw", "Referer": "https://mis.taifex.com.tw/futures/"})
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return (json.loads(r.read().decode("utf-8")).get("RtData") or {}).get("QuoteList") or [], f"HTTP {r.status}"
    except Exception as e:                                                # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:120]}"


class Delta:
    """同一個鍵（"tw:2330"、"tf:TXFK6-F"）跟上一次比，只記變了的欄位。"""

    def __init__(self):
        self.last: dict[str, list[str]] = {}

    def add(self, key: str, vals: list[str]):
        old = self.last.get(key)
        self.last[key] = list(vals)
        if old is None:
            return list(vals)
        ch = {str(i): v for i, (a, v) in enumerate(zip(old, vals)) if a != v}
        return ch or None


def decode(doc: dict) -> list[dict]:
    """存檔 → 每個請求一筆、每檔都是完整欄位的 dict：[{"k", "t0", "t1", "b", "r": {代號: {欄位: 值}}}]。"""
    names = {"tw": doc["tw_f"], "tf": doc["tf_f"]}
    last: dict[str, list[str]] = {}
    out = []
    for s in doc.get("s") or []:
        k = s["k"]
        rows = {}
        for code, v in (s.get("r") or {}).items():
            key = f"{k}:{code}"
            if isinstance(v, list):
                cur = list(v)
            else:
                cur = list(last[key])
                for i, x in v.items():
                    cur[int(i)] = x
            last[key] = cur
            rows[code] = dict(zip(names[k], cur))
        out.append({"k": k, "t0": s["t0"], "t1": s["t1"], "b": s.get("b"), "r": rows})
    return out


def sample(d: str, dprev: str, *, now_s, sleep, get_tw=_get_tw, get_tf=_get_tf,
           start: int = START_S, end: int = END_S) -> dict | None:
    """照 TICKS 抓一天。now_s()＝台北當天第幾秒；過了的輪次不補抓（不讓請求擠在一起）。"""
    syms, w = top_symbols(dprev)
    if not syms:
        log(f"{dprev} 沒有比重資料，不取樣")
        return None
    bs = batches(syms)
    tk = ticks(start, end)
    pl = plan(len(bs), len(tk))
    dl = Delta()
    doc = {"d": d, "dp": dprev, "syms": syms, "w": w, "y": {}, "tw_f": list(TW_F), "tf_f": list(TF_F),
           "top_n": TOP_N, "batch": BATCH, "s": []}
    n_ok = n_err = n_skip = 0
    for i, t in enumerate(tk):
        now = now_s()
        if now >= t + STEP:
            n_skip += 1
            continue
        if now < t:
            sleep(t - now)
        for j, b in enumerate(pl[i]):
            codes = (list(IDX) if j == 0 else []) + bs[b]
            t0 = now_s()
            arr, st = get_tw(codes)
            t1 = now_s()
            if arr is None:
                n_err += 1
                log(f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d} 證交所第 {b} 批 ✗ {st}")
                continue
            n_ok += 1
            rec = {}
            for m in arr:
                c = str(m.get("c") or "")
                if not c:
                    continue
                if c not in doc["y"] and m.get("y") not in (None, "", "-"):
                    doc["y"][c] = str(m.get("y"))
                ch = dl.add(f"tw:{c}", tw_row(m))
                if ch is not None:
                    rec[c] = ch
            doc["s"].append({"k": "tw", "t0": round(t0, 2), "t1": round(t1, 2), "b": b, "r": rec})
        t0 = now_s()
        arr, st = get_tf()
        t1 = now_s()
        if arr is None:
            n_err += 1
            log(f"期交所 ✗ {st}")
            continue
        rec = {}
        for m in arr:
            sid = str(m.get("SymbolID") or "")
            if sid:
                ch = dl.add(f"tf:{sid}", tf_row(m))
                if ch is not None:
                    rec[sid] = ch
        doc["s"].append({"k": "tf", "t0": round(t0, 2), "t1": round(t1, 2), "b": None, "r": rec})
    doc["n"] = {"ok": n_ok, "err": n_err, "skip_ticks": n_skip}
    log(f"{d}：{len(tk)} 輪、跳過 {n_skip} 輪，證交所成功 {n_ok} 次、失敗 {n_err} 次")
    return doc if n_ok else None


def save(doc: dict) -> bool:
    if store.read(KIND, doc["d"]):
        return False                     # 只增不改
    return store.write(KIND, doc["d"], doc)


def load(d: str) -> list[dict] | None:
    doc = store.read(KIND, d)
    return decode(doc) if doc else None
