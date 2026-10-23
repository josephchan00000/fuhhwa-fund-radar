"""美股飆股研究 C：一本帳的資金帳戶（ussxspec VER 1 的 TRADE；docs/lab_us_sleeve_plan.md 第 4.6、9 節）。研究用，不上頁面。

run(...)  第 a 天收盤＝capital 美元、全部放閒置（指數）；每一天：
  開盤：資料提早結束（下市）的部位用最後一天收盤賣 → 昨天收盤標記要賣的部位開盤賣（沒有開盤價就延到有的那天）
        → 昨天收盤的訊號依 RS 高到低開盤買（沒有開盤價就不買；只有那一天有效）
  收盤：閒置照指數的報酬漲跌（買賣股票時進出閒置的指數都當作在前一天收盤，開盤前的跳空不算）→ 部位照收盤（含息）計價
        → 檢查出場條件（那天有收盤才檢查）→ 這一天是訊號日就下明天的單。
  每檔目標＝前一天收盤總資產 × weight，不超過 max_weight，也不超過前一天 20 日平均成交值 × max_adv；最多 max_pos 檔；
  買股票的錢從閒置賣指數（指數那一邊付 c_idx），股票付 c_stk；賣股票反過來。資料最後一天還拿著的照收盤算。
出場 ex：{"hold": n}＝買進後第 n 個交易日收盤到期；趨勢（style "trend"）＝收盤 ≤ 買進以後最高收盤 × (1 − trail)、
  或收盤跌破 ma 日均線（買進以後收盤曾經在均線之上才算）、或到 hold 天；台股 W8 的比較（style "w8"）＝照 W8 原樣：
  收盤 < 均線、收盤 < 買進價 × (1 − stop)、收盤 < 買進以後最高收盤 × (1 − trail)，沒有時間上限。
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from . import ussxspec as X


def run(O: np.ndarray, Cf: np.ndarray, Cr: np.ndarray, last: np.ndarray, sig: dict[int, list], a: int, b: int,
        idle_r: np.ndarray, *, ex: dict, style: str = "fixed", MA: np.ndarray | None = None, D20: np.ndarray | None = None,
        DIV: np.ndarray | None = None, weight: float = X.TRADE["weight"], max_pos: int = X.TRADE["max_pos"],
        max_weight: float = X.TRADE["max_weight"], max_adv: float = X.TRADE["max_adv"], capital: float = X.TRADE["capital"],
        c_stk: float = X.COST["stk"], c_idx: float = X.COST["idx"]) -> dict:
    """O、Cf＝含息開盤、含息收盤（往前補齊）；Cr＝含息收盤（沒有成交＝nan，用來判斷那天有沒有收盤）；
    sig＝{訊號日: [(代號欄, RS)]}（已經依 RS 高到低、同分依代號排好）；idle_r＝閒置那份每天的報酬。
    → {"eq": 每天收盤總資產（a～b−1）, "stk": 股票占總資產, "n": 檔數, "div": 股票部分當天收到的股利（美元）, "trades": [...]}"""
    L = b - a
    eq = np.empty(L)
    stk = np.zeros(L)
    npos = np.zeros(L, dtype=np.int64)
    divs = np.zeros(L)
    idle = float(capital)
    eq[0] = idle
    eq_prev = idle
    pos: dict[int, dict] = {}
    pend: dict[int, str] = {}
    trades: list[list] = []
    orders = list(sig.get(a, [])) if a + 1 < b else []
    orders_si = a
    hold = ex.get("hold")
    trail, ma_on, stop = ex.get("trail"), MA is not None and ex.get("ma"), ex.get("stop")

    def sell(i: int, j: int, px: float, why: str) -> None:
        nonlocal idle
        q = pos.pop(j)
        gross = q["k"] * px
        net = gross * (1 - c_stk)
        idle += net * (1 - c_idx)
        trades.append([j, q["si"], q["ei"], i, net / q["cin"] - 1, why, q["cin"]])
        pend.pop(j, None)

    for i in range(a + 1, b):
        for j in [j for j in pos if last[j] < i]:
            sell(i, j, Cf[last[j], j], "delisted")
        for j in [j for j in pend if j in pos]:
            if np.isfinite(O[i, j]) and O[i, j] > 0:
                sell(i, j, O[i, j], pend[j])
        for j, sc in orders:
            if j in pos or len(pos) >= max_pos:
                continue
            o = O[i, j]
            if not (np.isfinite(o) and o > 0):
                continue
            x = min(weight, max_weight) * eq_prev
            if D20 is not None and np.isfinite(D20[i - 1, j]):
                x = min(x, max_adv * D20[i - 1, j])
            x = min(x, idle * (1 - c_idx) / (1 + c_stk))
            if x <= 1e-9 * eq_prev:
                continue
            idle -= x * (1 + c_stk) / (1 - c_idx)
            pos[j] = {"k": x / o, "ei": i, "si": orders_si, "cin": x * (1 + c_stk), "epx": o, "hi": -math.inf, "above": False}
        orders = []
        idle *= 1 + (idle_r[i] if np.isfinite(idle_r[i]) else 0.0)
        pv = 0.0
        dv = 0.0
        for j, q in pos.items():
            c = Cf[i, j]
            pv += q["k"] * c
            if DIV is not None and np.isfinite(DIV[i, j]):
                dv += q["k"] * Cf[i - 1, j] * DIV[i, j]
            if j in pend or not np.isfinite(Cr[i, j]):
                continue
            q["hi"] = max(q["hi"], c)
            why = None
            if style == "w8":
                m = MA[i, j] if ma_on else np.nan
                if ma_on and np.isfinite(m) and c < m:
                    why = "ma"
                elif stop and c < q["epx"] * (1 - stop):
                    why = "stop"
                elif trail and c < q["hi"] * (1 - trail):
                    why = "trail"
            else:
                if style == "trend" and ma_on:
                    m = MA[i, j]
                    if np.isfinite(m):
                        if c >= m:
                            q["above"] = True
                        elif q["above"]:
                            why = "ma"
                if why is None and trail and c <= q["hi"] * (1 - trail):
                    why = "trail"
                if why is None and hold and i - q["ei"] >= hold:
                    why = "time"
            if why:
                pend[j] = why
        e = idle + pv
        eq[i - a] = e
        stk[i - a] = pv / e if e > 0 else 0.0
        npos[i - a] = len(pos)
        divs[i - a] = dv
        eq_prev = e
        if i in sig and i + 1 < b:
            orders = [(j, sc) for j, sc in sig[i] if j not in pos]
            orders_si = i
    state = {"pos": {j: dict(q) for j, q in pos.items()}, "pend": dict(pend), "orders": list(orders), "orders_si": orders_si,
             "idle": idle}                                   # 最後一天收盤後的狀態（美股三成上線用：持股、明天開盤要賣的、要買的）
    for j, q in pos.items():                                 # 資料最後一天還拿著的：照收盤算（只記錄、不賣）
        trades.append([j, q["si"], q["ei"], b - 1, q["k"] * Cf[b - 1, j] * (1 - c_stk) / q["cin"] - 1, "open", q["cin"]])
    return {"eq": eq, "stk": stk, "n": npos, "div": divs, "trades": trades, "state": state}


def daily_ret(eq: np.ndarray) -> np.ndarray:
    r = np.zeros(len(eq))
    r[1:] = eq[1:] / eq[:-1] - 1
    return r


def cagr(cal: list[str], eq: np.ndarray, a: int, b: int) -> float | None:
    """cal[a]～cal[b−1] 的年化（eq 以 a 為第 0 個）。"""
    yrs = (date.fromisoformat(cal[b - 1]) - date.fromisoformat(cal[a])).days / 365.25
    v = eq[b - 1 - a] / eq[0]
    return v ** (1 / yrs) - 1 if yrs > 0 and v > 0 else None


def mdd(eq: np.ndarray) -> float:
    pk = np.maximum.accumulate(eq)
    return float((1 - eq / pk).max())


def halves(a: int, b: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """依交易日切一半（core.scenario 同一套：前半 a～mid、後半 mid～b−1）。"""
    mid = a + (b - a) // 2
    return (a, mid + 1), (mid, b)


def curve_stats(cal: list[str], r: np.ndarray, a: int, b: int) -> dict:
    """每天報酬 r（cal 上；只用 a+1～b−1）→ 整段、前後兩半的年化與最大回落、逐年。"""
    def nav(x0, x1):
        return np.cumprod(np.concatenate([[1.0], 1 + np.nan_to_num(r[x0 + 1:x1])]))
    out = {"a": cal[a], "b": cal[b - 1]}
    e = nav(a, b)
    out["cagr"], out["mdd"], out["m"] = cagr(cal, e, a, b), mdd(e), float(e[-1])
    hs = []
    for x0, x1 in halves(a, b):
        eh = nav(x0, x1)
        hs.append({"a": cal[x0], "b": cal[x1 - 1], "cagr": cagr(cal, eh, x0, x1), "mdd": mdd(eh), "m": float(eh[-1])})
    out["halves"] = hs
    yrs, base, prev_y = {}, 1.0, None
    for k in range(a, b):
        y = cal[k][:4]
        yrs[y] = float(e[k - a] / base - 1)
        if k + 1 < b and cal[k + 1][:4] != y:
            base = e[k - a]
    out["years"] = yrs
    return out


def trade_stats(trades: list[list], cal: list[str]) -> dict:
    t = [x for x in trades if x[5] != "open"]
    rs = sorted(x[4] for x in t)
    if not rs:
        return {"n": 0, "open": len(trades) - len(t)}
    pnl = sorted(((x[4]) * x[6] for x in t), reverse=True)
    tot = sum(pnl)
    k = max(1, len(pnl) // 10)
    hold = [x[3] - x[2] for x in t]
    best = sorted(t, key=lambda x: -x[4])[:10]
    return {"n": len(t), "open": len(trades) - len(t), "win": sum(1 for x in rs if x > 0) / len(rs), "avg": sum(rs) / len(rs),
            "med": rs[len(rs) // 2], "top10": sum(pnl[:k]) / tot if tot else None, "hold": sum(hold) / len(hold),
            "why": {w: sum(1 for x in t if x[5] == w) for w in sorted({x[5] for x in t})},
            "best": [{"j": int(x[0]), "a": cal[x[2]], "b": cal[x[3]], "ret": float(x[4])} for x in best]}
