"""訊號成績單（事件研究）——只信有成績的訊號。

口徑（寫在頁面「說明」分頁，改這裡要同步改說明）：
  · 訊號日 t＝揭露／收盤資料可得的那個交易日；**進場＝t+1 開盤價**（揭露在收盤後，
    不可能用 t 的價格成交——用 t 收盤會偷看未來）。
  · 出場＝t+h 收盤（h＝5、20 個交易日）。
  · 報酬扣來回成本 0.585%（手續費 0.1425%×2 未折扣＋證交稅 0.3%）。
  · 超額＝個股報酬 − 加權指數**同一時窗**報酬（t+1 開盤 → t+h 收盤；指數開盤取 Yahoo ^TWII）。
    ⚠ 2026-10-14 踩坑：原本基準從 t 收盤起算，大盤開低的日子（如 2026-03-09 開盤 −3.7%）會把
    指數的跳空算成「贏大盤」——「開低才進」的超額因此被灌水。指數開盤缺值時才退回 t 收盤。
  · 「隔夜跳空」＝t+1 開盤 / t 收盤 − 1：抄作業的人多時，好處可能全在跳空裡、進場後已無肉。
  · 同一檔同一訊號 5 個交易日內重複觸發只算第一次（避免同一波段灌水樣本）。
  · 樣本 <30 標灰、不排名。
"""
from __future__ import annotations

import statistics

COST = 0.00585
HORIZONS = (5, 20)
DEDUP = 5
MIN_N = 30


def _ret(S, idx, t, h, idx_open=None):
    T = len(S["c"])
    if t + h >= T:
        return None
    o1 = S["o"][t + 1] or S["c"][t + 1]
    ch = S["c"][t + h]
    c0 = S["c"][t]
    i0 = (idx_open[t + 1] if idx_open and idx_open[t + 1] else None) or idx[t]
    ih = idx[t + h]
    if not (o1 and ch and c0 and i0 and ih):
        return None
    r = ch / o1 - 1 - COST
    return {"r": r, "x": r - (ih / i0 - 1), "g": o1 / c0 - 1}


def _agg(rs: list[dict]) -> dict:
    if not rs:
        return {"n": 0}
    xs = [r["x"] for r in rs]
    return {"n": len(rs),
            "r": round(statistics.mean(r["r"] for r in rs) * 100, 2),
            "x": round(statistics.mean(xs) * 100, 2),
            "xm": round(statistics.median(xs) * 100, 2),
            "w": round(sum(1 for x in xs if x > 0) / len(xs) * 100, 0),
            "g": round(statistics.mean(r["g"] for r in rs) * 100, 2)}


def signal_stats(D, sig_hist: dict, idx: list) -> dict:
    out = {}
    io = D.taiex_open()
    series_cache = {}
    keys = sorted({k for h in sig_hist.values() for day in h for k in day})
    for k in keys:
        per_h = {h: [] for h in HORIZONS}
        for code, hist in sig_hist.items():
            last_fire = -999
            fired = [i for i, day in enumerate(hist) if k in day]
            if not fired:
                continue
            S = series_cache.get(code) or D.series(code)
            series_cache[code] = S
            for t in fired:
                if t - last_fire <= DEDUP:
                    last_fire = t
                    continue
                last_fire = t
                for h in HORIZONS:
                    r = _ret(S, idx, t, h, io)
                    if r:
                        per_h[h].append(r)
        out[k] = {str(h): _agg(v) for h, v in per_h.items()}
        out[k]["ok"] = out[k]["5"].get("n", 0) >= MIN_N
    return out


def issuer_stats(D, L, meta: dict, idx: list) -> dict:
    """各投信主動 ETF「新建倉」後的表現＋誰最常先買（領先）。"""
    from . import ledger as LG
    news: dict[str, list] = {}
    first_by_code: dict[str, list] = {}
    for ev in L.events:
        m = meta.get(ev.etf) or {}
        if ev.kind != LG.NEW or m.get("k") != "a" or ev.date not in D.ix or not LG.is_tw(ev.code):
            continue
        t = D.ix[ev.date]
        news.setdefault(m["is"], []).append((ev.code, t))
        first_by_code.setdefault(ev.code, []).append((t, m["is"]))
    cache = {}
    out = {}
    io = D.taiex_open()
    for iss, lst in news.items():
        res = {h: [] for h in HORIZONS}
        for code, t in lst:
            S = cache.get(code) or D.series(code)
            cache[code] = S
            for h in HORIZONS:
                r = _ret(S, idx, t, h, io)
                if r:
                    res[h].append(r)
        out[iss] = {str(h): _agg(v) for h, v in res.items()}
        out[iss]["new"] = len(lst)
    # 領先：同一檔 20 個交易日內被 ≥2 家投信新建倉，最早那家記 lead、其餘記 follow
    lead: dict[str, int] = {}
    follow: dict[str, int] = {}
    for code, lst in first_by_code.items():
        lst.sort()
        i = 0
        while i < len(lst):
            grp = [lst[i]]
            j = i + 1
            while j < len(lst) and lst[j][0] - lst[i][0] <= 20:
                grp.append(lst[j])
                j += 1
            iss_seq = []
            for _, s in grp:
                if s not in iss_seq:
                    iss_seq.append(s)
            if len(iss_seq) >= 2:
                lead[iss_seq[0]] = lead.get(iss_seq[0], 0) + 1
                for s in iss_seq[1:]:
                    follow[s] = follow.get(s, 0) + 1
            i = j
    for iss in set(lead) | set(follow) | set(out):
        out.setdefault(iss, {"new": 0})
        out[iss]["lead"] = lead.get(iss, 0)
        out[iss]["follow"] = follow.get(iss, 0)
    return out
