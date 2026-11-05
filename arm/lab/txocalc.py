"""選擇權作戰表資料（docs/lab_txo_plan.md 第 17 節）：每天晚上用資料分支的日行情與 5 秒指數，準備「下一個交易日」用的數字，
給選擇權分頁的計算機自動帶入。只是當天收盤後的事實與公式，不是策略成績。

  build(day_rows, close, asof)  → 文件：收盤指數、下一個交易日、最近幾批到期（隱含指數水準 f、價平上下 N_STRIKES 檔的結算價與用 f 反推的波動率）、
                                   明天的正常波動範圍（價平波動率 × √(1/252)）、成本與每筆上限（照 txospec）
  bs(…)／iv(…)                  Black-Scholes（r＝0）與反推波動率；頁面的 JS 用同一套公式算情境
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from . import txodata as T
from . import txospec as S

VER = 4               # VER 2（2026-11-05）：波動率用選擇權隱含的指數水準反推，不用 13:30 的指數收盤
                      # VER 3（2026-11-05）：每批多存收盤 ±OI_BAND 內每個履約價的未平倉與最大痛點（盤前作戰圖用）
                      # VER 4（2026-11-05）：價平＝有掛牌、離收盤最近的履約價（大跌後新加的履約價 100 點一檔，四捨五入到 50 點會找不到）
N_STRIKES = 10          # 價平上下各幾檔（使用者 2026-11-05：各 10 檔）
N_EXP = 4               # 列最近幾批到期
TRADING_YEAR = 252
FWD_STRIKES = 2       # 隱含指數水準用價平上下幾檔
OI_BAND = 0.08          # 未平倉存收盤上下 8% 內的履約價（docs/lab_premarket_plan.md）


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(cp: str, s: float, k: float, t: float, vol: float) -> float:
    """歐式選擇權理論價（r＝0、不配息）；t 以年計，t ≤ 0 就是內含價值。"""
    intrinsic = max(0.0, s - k) if cp == "C" else max(0.0, k - s)
    if t <= 0 or vol <= 0:
        return intrinsic
    sd = vol * math.sqrt(t)
    d1 = (math.log(s / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    if cp == "C":
        return s * _ncdf(d1) - k * _ncdf(d2)
    return k * _ncdf(-d2) - s * _ncdf(-d1)


def iv(cp: str, price: float, s: float, k: float, t: float) -> float | None:
    """反推波動率（二分法，1%～300%）；價格低於內含價值或時間 ≤ 0 → None。"""
    if not price or price <= 0 or t <= 0:
        return None
    lo, hi = 0.01, 3.0
    if price < bs(cp, s, k, t, lo) - 1e-9 or price > bs(cp, s, k, t, hi):
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs(cp, s, k, t, mid) < price:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def is_trading(d: date) -> bool:
    from arm import twholidays as H
    return d.weekday() < 5 and not H.is_closed(d)


def next_trading(d: date) -> date:
    n = d + timedelta(days=1)
    while not is_trading(n):
        n += timedelta(days=1)
    return n


def trading_days(a: date, b: date) -> int:
    """(a, b] 之間的交易日數。"""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if is_trading(d):
            n += 1
    return n


def implied_forward(px: dict, atm: float, width: int = FWD_STRIKES) -> float | None:
    """選擇權自己隱含的指數水準（r＝0 的買賣權平價：F＝K＋C−P），取價平上下 width 檔的中位數。
    選擇權 13:45 收盤、加權指數 13:30 收盤，直接用指數收盤反推波動率會讓買權、賣權的波動率差好幾個百分點。"""
    xs = sorted(k + v["C"][0] - v["P"][0] for k, v in px.items()
                if abs(k - atm) <= width * S.STRIKE_STEP and v.get("C", (0,))[0] and v.get("P", (0,))[0])
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def max_pain(px: dict) -> float | None:
    """最大痛點：到期時買方（買權＋賣權）價值總和最小的履約價（用全部履約價的未平倉）。"""
    oc = {k: v.get("C", (0, 0))[1] or 0 for k, v in px.items()}
    op = {k: v.get("P", (0, 0))[1] or 0 for k, v in px.items()}
    if not any(oc.values()) and not any(op.values()):
        return None
    ks = sorted(px)
    return min(ks, key=lambda K: (sum(o * max(0, K - k) for k, o in oc.items()) + sum(o * max(0, k - K) for k, o in op.items()), K))


def build(rows: list[list], close: float, asof: date) -> dict:
    """rows＝txodata.parse_day 的列（同一天、日盤）；close＝asof 當天加權指數收盤。"""
    C = {c: i for i, c in enumerate(T.COLS)}
    day = asof.isoformat()
    by: dict[str, dict] = {}
    for r in rows:
        if r[C["d"]] != day:
            continue
        xd = date.fromisoformat(r[C["xd"]]) if r[C["xd"]] else T.exp_date(r[C["exp"]])
        if xd <= asof:
            continue
        e = by.setdefault(r[C["exp"]], {"code": r[C["exp"]], "date": xd.isoformat(), "px": {}})
        px = r[C["s"]] or r[C["c"]] or 0
        e["px"].setdefault(r[C["k"]], {})[r[C["cp"]]] = (px, r[C["oi"]] or 0)
    nxt = next_trading(asof)
    listed = sorted({k for e in by.values() for k, v in e["px"].items() if v.get("C", (0,))[0] and v.get("P", (0,))[0]})
    atm = min(listed, key=lambda k: (abs(k - close), k)) if listed else round(close / S.STRIKE_STEP) * S.STRIKE_STEP
    exps = []
    for e in sorted(by.values(), key=lambda e: e["date"])[:N_EXP]:
        xd = date.fromisoformat(e["date"])
        n = trading_days(asof, xd)
        t = n / TRADING_YEAR
        ks = sorted(k for k in e["px"] if abs(k - atm) <= N_STRIKES * S.STRIKE_STEP)
        f = implied_forward(e["px"], atm) or close
        out = []
        for k in ks:
            c, p = e["px"][k].get("C", (0, 0)), e["px"][k].get("P", (0, 0))
            out.append([k, c[0], iv("C", c[0], f, k, t), p[0], iv("P", p[0], f, k, t), c[1], p[1]])
        oi = [[k, e["px"][k].get("C", (0, 0))[1] or 0, e["px"][k].get("P", (0, 0))[1] or 0]
              for k in sorted(e["px"]) if abs(k - close) <= OI_BAND * close]
        exps.append({"code": e["code"], "date": e["date"], "n": n, "tomorrow": xd == nxt, "f": round(f, 1), "rows": out,
                     "oi": oi, "pain": max_pain(e["px"])})
    atm_iv = None
    for e in exps:
        if e["tomorrow"]:
            continue
        both = [x for x in e["rows"] if x[2] and x[4]]
        r = next((x for x in both if x[0] == atm), None) or min(both, key=lambda x: (abs(x[0] - close), x[0]), default=None)
        vs = [v for v in (r[2], r[4]) if v] if r else []
        if vs:
            atm_iv = round(sum(vs) / len(vs), 4)
            break
    em = round(close * atm_iv * math.sqrt(1 / TRADING_YEAR), 1) if atm_iv else None
    return {"ver": VER, "spec": S.VER, "asof": day, "next": nxt.isoformat(), "close": round(close, 2), "atm": atm,
            "atm_iv": atm_iv, "em": em, "mult": S.MULT, "fee": S.FEE, "tax": S.TAX, "slip": S.SLIP_TICKS,
            "caps": S.CAP, "day_stop": S.DAY_STOP, "month_stop": S.MONTH_STOP, "step": S.STRIKE_STEP, "exps": exps}
