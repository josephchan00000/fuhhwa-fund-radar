"""美股做法的母體＋每年只用以前挑（docs/lab_us_sleeve_plan.md 第 12.3、12.4 節；ytdspec VER 1）。
10/23 的探索程式（工作階段暫存區）搬進來：條件、賣出、檔數、大盤濾網的組合一樣；資料改 ussxspec VER 8（財報只用當時已申報的數字）、
空位改放現金（ytdspec US_IDLE，同現在的計畫）。

  ctx(C)            ussxqm.context() 再補 200 日線、大盤濾網、波動、離財報幾天、平順與 MAX（探索時的 Ctx 同一套）
  selections(cx)    21 種條件 → 每一列是否符合
  run_one(cx, name) 一種做法的資金帳戶（不換股：ussxbook.run；每週換股：run_rot）
  walk(yr, pools, L, k) 每年 1 月 1 日照過去 L 年最好的 k 種（ytdspec 二②）"""
from __future__ import annotations

import math

import numpy as np

from . import ussxbook as BK
from . import ussxfeat as UF
from . import ussxpanel as UP
from . import ussxqm as QM
from . import ussxspec as X
from . import ytdspec as S

EXITS_HOLD = {
    "50日線（最多一年）": ({"ma": 50, "hold": 250}, "trend"),
    "50日線（不設上限）": ({"ma": 50}, "trend"),
    "回落25%": ({"trail": 0.25}, "trend"),
    "回落30%或年線": ({"trail": 0.30, "ma": 200, "hold": 250}, "trend"),
    "抱60天": ({"hold": 60}, "fixed"),
    "抱120天": ({"hold": 120}, "fixed"),
}
EXITS_ROT = {"只換股": ({}, "trend"), "換股＋50日線": ({"ma": 50}, "trend"), "換股＋回落25%": ({"trail": 0.25}, "trend")}
KEEPS = {"前N名": 1, "前2N名": 2}


# ── 資料 ─────────────────────────────────────────────────────────────────────

def ctx(C: dict) -> dict:
    """QM 的 context 再補探索時用到的欄位（不改 C 本身）。"""
    P = C["P"]
    Cf = C["Cf"]
    cx = dict(C)
    cx["MAS"] = {50: UF.roll_mean(Cf, 50), 200: UF.roll_mean(Cf, 200)}
    j = P["col"]["SPY"]
    cx["regime"] = Cf[:, j] >= cx["MAS"][200][:, j]          # S&P 500（SPY）收盤在年線上
    cx["rep"] = UP.report_days(P["cal"], P["sym"], C["earn"])
    return cx


def vol(cx: dict) -> np.ndarray:
    """每一列：之前 252 個交易日的日報酬標準差（年化；滿 200 天才算）。"""
    Cf, cols = cx["Cf"], cx["cols"]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.log(Cf[1:] / Cf[:-1])
    r = np.vstack([np.full((1, Cf.shape[1]), np.nan), r])
    ok = np.isfinite(r)
    x = np.where(ok, r, 0.0)
    c1 = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(x, axis=0)])
    c2 = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(x * x, axis=0)])
    cn = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(ok, axis=0)])
    di, jj = cols["di"], cols["j"]
    lo = np.maximum(di - 251, 0)
    n = cn[di + 1, jj] - cn[lo, jj]
    s1 = c1[di + 1, jj] - c1[lo, jj]
    s2 = c2[di + 1, jj] - c2[lo, jj]
    with np.errstate(invalid="ignore", divide="ignore"):
        v = np.sqrt(np.maximum(s2 / n - (s1 / n) ** 2, 0)) * math.sqrt(252)
    return np.where(n >= 200, v, np.nan)


def dsr(cx: dict) -> np.ndarray:
    """每一列：離最近一次財報公布幾個交易日（沒有＝nan）。"""
    cols, P = cx["cols"], cx["P"]
    di, jj = cols["di"], cols["j"]
    out = np.full(len(di), np.nan)
    by: dict[int, list] = {}
    for k, j in enumerate(jj.tolist()):
        by.setdefault(j, []).append(k)
    for j, ks in by.items():
        days = np.asarray(cx["rep"].get(P["sym"][j]) or [], dtype=np.int64)
        if not len(days):
            continue
        ks = np.asarray(ks)
        q = np.searchsorted(days, di[ks], side="right") - 1
        ok = q >= 0
        out[ks[ok]] = di[ks[ok]] - days[q[ok]]
    return out


def path_feats(cx: dict) -> dict:
    """ID＝sgn(過去 12～1 個月報酬) ×（下跌天數比例 − 上漲天數比例）（越低越平順）；MAX＝近 21 個交易日最大單日報酬。"""
    Cf, cols = cx["Cf"], cx["cols"]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = Cf[1:] / Cf[:-1] - 1
    r = np.vstack([np.full((1, Cf.shape[1]), np.nan), r])
    pos = np.concatenate([np.zeros((1, r.shape[1])), np.cumsum(r > 0, axis=0)])
    neg = np.concatenate([np.zeros((1, r.shape[1])), np.cumsum(r < 0, axis=0)])
    di, jj = cols["di"], cols["j"]
    lo, hi = np.maximum(di - 251, 0), np.maximum(di - 20, 0)
    n = (hi - lo).astype(float)
    p = pos[hi + 1, jj] - pos[lo, jj]
    q = neg[hi + 1, jj] - neg[lo, jj]
    with np.errstate(invalid="ignore", divide="ignore"):
        pret = Cf[hi, jj] / Cf[lo, jj] - 1
        ID = np.sign(pret) * (q - p) / n
    mx = np.full(len(di), np.nan)
    for k0 in range(0, len(di), 100000):
        a, b = di[k0:k0 + 100000], jj[k0:k0 + 100000]
        seg = np.stack([r[np.maximum(a - t, 0), b] for t in range(21)], axis=1)
        with np.errstate(invalid="ignore"):
            mx[k0:k0 + 100000] = np.nanmax(np.where(np.isfinite(seg), seg, -np.inf), axis=1)
    mx[~np.isfinite(mx)] = np.nan
    return {"ID": ID, "MAX": mx}


def weekly_q(cx: dict, val: np.ndarray, base_mask: np.ndarray, q: float) -> np.ndarray:
    """每週在 base_mask 的列之間，val ≤ 那週第 q 分位的列。"""
    w = cx["cols"]["w"]
    out = np.zeros(len(val), dtype=bool)
    idx = np.nonzero(base_mask & np.isfinite(val))[0]
    if not len(idx):
        return out
    order = idx[np.argsort(w[idx], kind="stable")]
    ww = w[order]
    cut = np.flatnonzero(np.diff(ww)) + 1
    for g in np.split(order, cut):
        th = np.quantile(val[g], q)
        out[g[val[g] <= th]] = True
    return out


def selections(cx: dict) -> dict[str, np.ndarray]:
    """21 種條件（第 12.3 節；名稱與順序＝ytdspec.US_SELS）。"""
    f = cx["cols"]["f"]
    v = vol(cx)
    ds = dsr(cx)
    with np.errstate(invalid="ignore"):
        M = (f["rs"] >= 80) & (f["d52h"] >= -0.25)
        Q = (f["om"] >= 0.10) & (f["roe"] >= 0.15)
        G = (f["ey"] >= 0.25) & (f["sy"] >= 0.20)
        P = f["om"] > 0
        T = f["tt_all"] == 1
        L = f["cap"] >= 2e9
        Sx = (f["sur"] >= 0.10) & (ds <= 10)
        pf = path_feats(cx)
        mom = f["rs"] >= 80
        smooth = weekly_q(cx, pf["ID"], mom, 1 / 3)
        lowmax = weekly_q(cx, pf["MAX"], mom, 0.5)
        out = {
            "強勢": M,
            "強勢＋品質": M & Q,
            "強勢＋成長": M & G,
            "強勢＋成長＋賺錢": M & G & P,
            "強勢＋品質＋成長": M & Q & G,
            "趨勢樣板＋成長（CAN SLIM）": T & G,
            "趨勢樣板＋成長＋賺錢": T & G & P,
            "趨勢樣板＋品質": T & Q,
            "強勢＋品質＋中大型": M & Q & L,
            "強勢＋成長＋中大型": M & G & L,
            "強勢＋財報驚喜": M & Sx,
            "強勢＋財報驚喜＋賺錢": M & Sx & P,
            "趨勢樣板": T,
            "52週新高": (f["d52h"] >= -0.05) & (f["rs"] >= 80),
            "品質（不看強弱）": Q,
            "低波動強勢": (f["rs"] >= 80) & (v <= 0.40) & (f["d52h"] >= -0.15),
            "平順動能": smooth,
            "平順動能＋賺錢": smooth & P,
            "低MAX動能": lowmax,
            "大型強勢（市值≥100億＋趨勢樣板）": (f["cap"] >= 1e10) & T,
            "中大型強勢（市值≥20億＋趨勢樣板＋RS≥90）": L & T & (f["rs"] >= 90),
        }
    assert tuple(out) == S.US_SELS
    return out


# ── 做法 ─────────────────────────────────────────────────────────────────────

def names() -> dict[str, list[str]]:
    """{池: [做法名稱]}；名稱寫法同探索（不換股：條件｜賣出｜N檔｜濾網；每週換股：條件｜賣出（留前幾名）｜N檔｜濾網）。"""
    hold = [f"{s}｜{e}｜{n}檔｜{g}" for s in S.US_SELS for g in S.US_REG for e in S.US_EXITS_HOLD for n in S.US_NS]
    rot = [f"{s}｜{e}（{kn}）｜{n}檔｜{g}" for s in S.US_SELS for g in S.US_REG for e in S.US_EXITS_ROT for kn in S.US_KEEPS
           for n in S.US_NS]
    assert len(hold) + len(rot) == S.n_grid()
    return {"全部": hold + rot, "不換股": hold, "每週換股": rot}


def parse(name: str) -> dict:
    s, e, n, g = name.split("｜")
    out = {"sel": s, "n": int(n.replace("檔", "")), "reg": g}
    if e in S.US_EXITS_HOLD:                                # 不換股的賣出名稱本身也有括號（50日線（最多一年））
        out.update(rot=False, exit=e)
    else:
        en, kn = e[:-1].rsplit("（", 1)
        out.update(rot=True, exit=en, keep=KEEPS[kn])
    return out


def sig_from_mask(cx: dict, mask: np.ndarray, y0: int = S.US_Y0) -> dict[int, list]:
    """每週：符合的列依 RS 高到低（同分依代號）。"""
    return QM.signals(cx, mask, y0=y0)


def idle(cx: dict) -> tuple[np.ndarray, float]:
    return QM.idle_of(cx, "spx", S.US_IDLE)


def run_one(cx: dict, name: str, sig_cache: dict, b: int | None = None) -> dict:
    """一種做法的資金帳戶（US_Y0 年初起）：{"eq", "stk", "trades", "a"}。sig_cache＝{(條件, 濾網): 訊號}。"""
    P = cx["P"]
    T = b or cx["T"]
    p = parse(name)
    key = (p["sel"], p["reg"])
    sig = sig_cache[key]
    a = QM.a_of(cx["cal"], S.US_Y0)
    n = p["n"]
    w = 1.0 / n
    ir, ci = idle(cx)
    if p["rot"]:
        ex, style = EXITS_ROT[p["exit"]]
        ma = cx["MAS"].get(ex.get("ma")) if ex.get("ma") else None
        wk = [i for i in cx["cols"]["wk"] if i > a]
        r = run_rot(P["O"], cx["Cf"], P["C"], P["last"], sig, a, T, ir, ex=ex, style=style, MA=ma, D20=cx["D20"],
                    weight=w, max_pos=n, max_weight=max(w, X.TRADE["max_weight"]), keep=n * p["keep"], wk_days=wk,
                    c_stk=X.COST["stk"], c_idx=ci)
    else:
        ex, style = EXITS_HOLD[p["exit"]]
        ma = cx["MAS"].get(ex.get("ma")) if ex.get("ma") else None
        r = BK.run(P["O"], cx["Cf"], P["C"], P["last"], sig, a, T, ir, ex=ex, style=style, MA=ma, D20=cx["D20"],
                   DIV=cx["DIV"], weight=w, max_pos=n, max_weight=max(w, X.TRADE["max_weight"]), c_stk=X.COST["stk"], c_idx=ci)
    r["a"] = a
    return r


def signals_all(cx: dict, sels: dict[str, np.ndarray]) -> dict:
    """{(條件, 濾網): 訊號}。"""
    out = {}
    for s, m in sels.items():
        sg = sig_from_mask(cx, m)
        out[(s, S.US_REG[0])] = sg
        out[(s, S.US_REG[1])] = {i: v for i, v in sg.items() if cx["regime"][i]}
    return out


def run_rot(O, Cf, Cr, last, sig, a, b, idle_r, *, ex, style="trend", MA=None, D20=None, weight=0.125, max_pos=8,
            max_weight=0.20, max_adv=X.TRADE["max_adv"], capital=X.TRADE["capital"], c_stk=X.COST["stk"], c_idx=X.COST["idx"],
            keep=None, wk_days=None):
    """每週換股的資金帳戶：ussxbook.run 同一套買賣，另外每週最後一個交易日檢查——拿著的股票不在那週名單的前 keep 名就隔天開盤賣。
    keep＝None＝和 ussxbook.run 每天的資產、每一筆交易都相同（tests）。"""
    L = b - a
    eq = np.empty(L)
    stk = np.zeros(L)
    idl = float(capital)
    eq[0] = idl
    eq_prev = idl
    pos, pend, trades = {}, {}, []
    orders = list(sig.get(a, [])) if a + 1 < b else []
    orders_si = a
    hold = ex.get("hold")
    trail, ma_on, stop = ex.get("trail"), MA is not None and ex.get("ma"), ex.get("stop")
    wk = set(wk_days or [])

    def sell(i, j, px, why):
        nonlocal idl
        q = pos.pop(j)
        net = q["k"] * px * (1 - c_stk)
        idl += net * (1 - c_idx)
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
            x = min(x, idl * (1 - c_idx) / (1 + c_stk))
            if x <= 1e-9 * eq_prev:
                continue
            idl -= x * (1 + c_stk) / (1 - c_idx)
            pos[j] = {"k": x / o, "ei": i, "si": orders_si, "cin": x * (1 + c_stk), "epx": o, "hi": -math.inf, "above": False}
        orders = []
        idl *= 1 + (idle_r[i] if np.isfinite(idle_r[i]) else 0.0)
        pv = 0.0
        for j, q in pos.items():
            c = Cf[i, j]
            pv += q["k"] * c
            if j in pend or not np.isfinite(Cr[i, j]):
                continue
            q["hi"] = max(q["hi"], c)
            why = None
            if style == "trend" and ma_on:
                m = MA[i, j]
                if np.isfinite(m):
                    if c >= m:
                        q["above"] = True
                    elif q["above"]:
                        why = "ma"
            if why is None and trail and c <= q["hi"] * (1 - trail):
                why = "trail"
            if why is None and stop and c < q["epx"] * (1 - stop):
                why = "stop"
            if why is None and hold and i - q["ei"] >= hold:
                why = "time"
            if why:
                pend[j] = why
        if keep is not None and i in wk and i + 1 < b:
            top = {j for j, _ in (sig.get(i) or [])[:keep]}
            for j in pos:
                if j not in pend and j not in top:
                    pend[j] = "rot"
        e = idl + pv
        eq[i - a] = e
        stk[i - a] = pv / e if e > 0 else 0.0
        eq_prev = e
        if i in sig and i + 1 < b:
            orders = [(j, sc) for j, sc in sig[i] if j not in pos and j not in pend]
            orders_si = i
    for j, q in pos.items():
        trades.append([j, q["si"], q["ei"], b - 1, q["k"] * Cf[b - 1, j] * (1 - c_stk) / q["cin"] - 1, "open", q["cin"]])
    return {"eq": eq, "stk": stk, "trades": trades}


def daily(cx: dict, r: dict) -> np.ndarray:
    """每天的報酬（長度＝日曆；起點以前＝0）。"""
    return np.concatenate([np.zeros(r["a"]), BK.daily_ret(r["eq"])])


def yearly(cal: list[str], rr: np.ndarray, y0: int, y1: int) -> dict[int, float]:
    yrs = np.array([int(d[:4]) for d in cal])
    out = {}
    for y in range(y0, y1 + 1):
        m = yrs == y
        out[y] = float(np.prod(1 + rr[m]) - 1) if m.any() else 0.0
    return out


# ── 每年只用以前挑 ───────────────────────────────────────────────────────────

def picks(yr: dict[str, dict[int, float]], pool: list[str], L: int, k: int, Y: int) -> list[str]:
    """Y 年 1 月 1 日：pool 裡過去 L 個日曆年報酬連乘最高的 k 種（同分依名稱）。"""
    sc = []
    for nm in pool:
        v = 1.0
        for y in range(Y - L, Y):
            v *= 1 + yr[nm][y]
        sc.append((-v, nm))
    sc.sort()
    return [nm for _, nm in sc[:k]]


def walk(yr: dict[str, dict[int, float]], pool: list[str], L: int, k: int, y_last: int, spx_yr: dict[int, float]) -> dict:
    """每年 1 月 1 日照過去 L 年最好的 k 種（年初等分、年中不調；換掉的那一年扣 US_SWITCH × 換掉的比例）；
    還不能挑的年份（Y < US_Y0＋L）放 S&P 500 含息。→ {"yr": {年: 報酬}, "pick": {年: [做法]}, "cost": {年: 扣掉的換手成本}}"""
    out, pk, cost, prev = {}, {}, {}, None
    for Y in range(S.US_RANK_Y0, y_last + 1):
        if Y < S.US_Y0 + L:
            out[Y], pk[Y], cost[Y] = spx_yr[Y], [], 0.0
            continue
        ch = picks(yr, pool, L, k, Y)
        r = float(np.mean([yr[nm][Y] for nm in ch]))
        c = S.US_SWITCH * len(set(ch) - set(prev)) / k if prev is not None and set(prev) != set(ch) else 0.0
        out[Y], pk[Y], cost[Y] = r - c, ch, c
        prev = ch
    return {"yr": out, "pick": pk, "cost": cost}


def cagr(yr: dict[int, float], y0: int, y1: int) -> float:
    v = 1.0
    for y in range(y0, y1 + 1):
        v *= 1 + yr[y]
    return v ** (1 / (y1 - y0 + 1)) - 1


def choose(wf: dict[str, dict]) -> tuple[str, list[list]]:
    """24 種挑法依 US_RANK_Y0～US_RANK_Y1 的年化由高到低排（同分依名稱），取第 US_RANK 名。→ (名稱, 排名表)"""
    rk = sorted(((-cagr(w["yr"], S.US_RANK_Y0, S.US_RANK_Y1), nm) for nm, w in wf.items()))
    table = [[nm, round(-c, 6)] for c, nm in rk]
    return rk[S.US_RANK - 1][1], table
