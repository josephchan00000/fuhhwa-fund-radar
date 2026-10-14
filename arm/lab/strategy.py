"""籌碼雷達：交易策略＋前瞻紙上交易（2026-10-14 使用者：「幫我擬定交易策略」→「好」）。

驗證原則（改這裡之前先讀 CLAUDE.md 籌碼雷達「策略」段）：
  · **規則寫死、帶版本與起算日**。紙上交易只記「規則建立之後」的訊號——之前的資料只能當
    「樣本內參考」，因為規則本身就是看那段資料挑出來的。要改規則＝新版本、新起算日、成績歸零。
  · **每次建表由分片資料重算**，不存交易狀態：同樣的資料永遠算出同樣的帳，不會有狀態檔壞掉的問題。
  · 進出場一律用「當時已知」的價格：訊號日 t 收盤後才知道 → 最早 t+1 開盤。
  · 成本：來回 0.585%；超額：對加權指數同一時窗（進場日開盤 → 出場日收盤；指數開盤取 Yahoo ^TWII），與成績單同口徑。
  · 驗證期滿（30 筆或 30 個交易日，先到者）：平均超額＞0 且勝率＞50% → 達標；否則不達標。
"""
from __future__ import annotations

import statistics

from . import ledger as LG
from . import ta

COST = 0.00585
PASS_N = 30
PASS_DAYS = 30

STRATEGIES = [
    # 持有期是看過 1～10 日全掃描後選的（開低組 10 個持有期中 8 個為正、5 日恰好為負）——
    # 方向不隨持有期改變，選 3 日只是取短；這段話同步寫在頁面上，不假裝是事前決定。
    {"key": "s1", "ver": 1, "since": "2026-10-14", "name": "共識加碼・開低才進",
     "rule": ["訊號：收盤後「共識加碼」亮燈（5 日內 ≥3 家投信主動 ETF 真加碼、主動合計淨買；同檔 5 日內只算第一次）",
              "進場：隔日開盤價「低於」訊號日收盤才以開盤價買進（8:59 看試撮）；平盤或開高則放棄",
              "出場：第 3 個交易日收盤；期間收盤跌破「進場價 − 2×ATR(14)」當日收盤停損",
              "依據（7/27～10/13）：開低組持有 1～10 日中 8 個持有期平均超額為正（+0.9%～+1.8%）、3 日 +1.8%／勝率 59%（34 筆）；不加條件跟進則 10 個持有期全為負"],
     "hold": 3, "stop_atr": 2.0, "gap_max": 0.0, "gap_strict": True},
    {"key": "s4", "ver": 1, "since": "2026-10-14", "name": "群益新建倉（觀察）",
     "rule": ["訊號：群益任一主動 ETF 新建倉（觀測期內首次持有）",
              "進場：隔日開盤價買進（不設跳空條件）",
              "出場：第 10 個交易日收盤；收盤跌破「進場價 − 3×ATR(14)」停損",
              "依據：持有 1～20 日各期平均超額皆為正（+0.5%～+3.3%，約 40 筆）；10 日 +3.3%／勝率 63%"],
     "hold": 10, "stop_atr": 3.0, "gap_max": None},
]


def _signals(key: str, D, sig_hist: dict, L, meta: dict) -> list[tuple[str, int]]:
    """(代號, 訊號日索引) 清單，只含台股。"""
    out = []
    if key == "s1":
        for code, hist in sig_hist.items():
            if not LG.is_tw(code):
                continue
            last = -999
            for t, day in enumerate(hist):
                if "cons" in day:
                    if t - last > 5:
                        out.append((code, t))
                    last = t
    elif key == "s4":
        seen = set()
        for ev in L.events:
            m = meta.get(ev.etf) or {}
            if ev.kind == LG.NEW and m.get("is") == "群益" and m.get("k") == "a" \
                    and LG.is_tw(ev.code) and ev.date in D.ix:
                k = (ev.code, D.ix[ev.date])
                if k not in seen:
                    seen.add(k)
                    out.append(k)
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def _trade(st: dict, code: str, t: int, S: dict, atr: list, idx: list, T: int,
           idx_open: list | None = None) -> dict | None:
    """模擬一筆。回傳 None＝資料還沒到訊號隔日（候選中）。"""
    o, c = S["o"], S["c"]
    if t + 1 >= T or c[t] is None:
        return None
    if o[t + 1] is None:
        return {"st": "skip", "why": "隔日無開盤價"}
    gap = o[t + 1] / c[t] - 1
    if st["gap_max"] is not None and (gap >= st["gap_max"] if st.get("gap_strict") else gap > st["gap_max"]):
        return {"st": "skip", "why": f"開高 {gap * 100:+.1f}%", "gap": round(gap * 100, 2)}
    entry = o[t + 1]
    a = ta.last_at(atr, t)
    stop = entry - st["stop_atr"] * a if a else None
    exit_i, why = None, None
    for i in range(t + 1, min(t + st["hold"], T - 1) + 1):
        if c[i] is None:
            continue
        if stop and c[i] < stop:
            exit_i, why = i, "停損"
            break
        if i == t + st["hold"]:
            exit_i, why = i, "到期"
    rec = {"gap": round(gap * 100, 2), "entry": entry, "stop": None if stop is None else round(stop, 2)}
    if exit_i is None:
        last_i = max((i for i in range(t + 1, T) if c[i] is not None), default=t + 1)
        r = c[last_i] / entry - 1 if c[last_i] else None
        rec.update({"st": "open", "held": last_i - t, "now": c[last_i],
                    "r": None if r is None else round(r * 100, 2)})
        return rec
    r = c[exit_i] / entry - 1 - COST
    i0 = (idx_open[t + 1] if idx_open and idx_open[t + 1] else None) or idx[t]
    b = idx[exit_i] / i0 - 1 if idx[exit_i] and i0 else None
    rec.update({"st": "closed", "exit": c[exit_i], "why": why, "held": exit_i - t,
                "r": round(r * 100, 2), "x": None if b is None else round((r - b) * 100, 2)})
    return rec


def _agg(trs: list[dict]) -> dict:
    xs = [t["x"] for t in trs if t.get("st") == "closed" and t.get("x") is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "x": round(statistics.mean(xs), 2), "xm": round(statistics.median(xs), 2),
            "w": round(sum(1 for x in xs if x > 0) / len(xs) * 100), "sum": round(sum(xs), 2)}


def run(D, sig_hist: dict, L, meta: dict, idx: list, names: dict) -> dict:
    T = D.T
    io = D.taiex_open()
    cache: dict[str, tuple] = {}

    def series(code):
        if code not in cache:
            S = D.series(code)
            cache[code] = (S, ta.atr(S["h"], S["l"], S["c"]))
        return cache[code]

    out = []
    for st in STRATEGIES:
        sigs = _signals(st["key"], D, sig_hist, L, meta)
        fwd, ins, cands = [], [], []
        for code, t in sigs:
            S, atr = series(code)
            rec = _trade(st, code, t, S, atr, idx, T, io)
            base = {"c": code, "n": names.get(code, code), "d": D.cal[t]}
            if rec is None:
                a = ta.last_at(atr, t)
                cands.append({**base, "px": S["c"][t],
                              "stop": round(S["c"][t] - st["stop_atr"] * a, 2) if a and S["c"][t] else None,
                              "gap_max": st["gap_max"]})
                continue
            (fwd if D.cal[t] >= st["since"] else ins).append({**base, **rec})
        days = sum(1 for d in D.cal if d >= st["since"])
        g = _agg(fwd)
        if g["n"] >= PASS_N or days >= PASS_DAYS:
            status = "達標" if g["n"] and g["x"] > 0 and g["w"] > 50 else "不達標"
        else:
            status = "驗證中"
        out.append({"key": st["key"], "ver": st["ver"], "since": st["since"], "name": st["name"],
                    "rule": st["rule"], "status": status, "days": days,
                    "fwd": fwd[-60:], "fwd_stats": g, "ins_stats": _agg(ins),
                    "ins_n": len(ins), "cands": cands})
    return {"list": out, "alerts": gap_alerts(D, sig_hist, names), "pass": [PASS_N, PASS_DAYS]}


def gap_alerts(D, sig_hist: dict, names: dict) -> list[dict]:
    """策略 2：最新交易日開盤跳空 ≥3% 的共識加碼股（前一交易日亮燈）——已持有者的減碼提醒。"""
    T = D.T
    out = []
    for code, hist in sig_hist.items():
        if not LG.is_tw(code) or T < 2:
            continue
        S = D.series(code)
        t = max((i for i in range(T) if S["o"][i] is not None), default=None)
        if not t or "cons" not in (hist[t - 1] or []) or not S["c"][t - 1]:
            continue
        gap = S["o"][t] / S["c"][t - 1] - 1
        if gap >= 0.03:
            out.append({"c": code, "n": names.get(code, code), "d": D.cal[t], "gap": round(gap * 100, 2)})
    return sorted(out, key=lambda x: -x["gap"])
