"""少見但勝率高的策略（規格 arm/lab/rarespec.py VER 1；docs/lab_rare_plan.md）。

每一條規則 → 一組交易 (t 訊號那天, b 買進那天, q 賣出那天)（都是收盤、交易日位置）→ 成績、判定、參數鄰近、另外看的期間、打亂測試、現在。
研究檔 data/lab/rare_research.json＝scripts/run_rare.py（資料或規格改了才重跑）。
"""
from __future__ import annotations

import bisect
import math
import zlib
from datetime import date, timedelta

import numpy as np

from . import rarespec as S
from . import robust as RB
from . import xstrat as XT

OUT = "rare_research.json"


# ── 資料 ───────────────────────────────────────────────────────────────────

def data(mk: str) -> dict:
    """總經策略同一份（xstrat.data）＋ v3a：收盤時已經知道的 VIX3M（美股＝當天；台股＝前一個美股交易日，同 vixa）。"""
    from . import heatdata as HD
    D = XT.data(mk)
    v3 = HD.load("us_vix3m") or {}
    cal = D["cal"]
    if mk == "tw":
        from . import heat as H
        D["v3a"] = np.array([np.nan if v is None else float(v) for v in H.asof_daily(cal, v3, after=True, stale=7)])
    else:
        D["v3a"] = np.array([float(v3[d]) if v3.get(d) else np.nan for d in cal])
    return D


def idx_ge(cal: list[str], d: str) -> int:
    return bisect.bisect_left(cal, d)


def days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def idx_le(cal: list[str], d: str) -> int:
    """d 當天或之前最後一個交易日的位置（沒有＝−1）。"""
    return bisect.bisect_right(cal, d) - 1


# ── 規則（第 4 節）：回傳 [(t, b, q)]（q 可以超過資料＝還沒賣） ───────────────────────

def election_days(y0: int = 1928, y1: int = 2040) -> list[str]:
    """美國期中選舉日：11 月第一個星期一之後的星期二（年份除以 4 餘 2）。"""
    out = []
    for y in range(y0, y1 + 1):
        if y % 4 != 2:
            continue
        d = date(y, 11, 1)
        while d.weekday() != 0:
            d += timedelta(days=1)
        out.append((d + timedelta(days=1)).isoformat())
    return out


def tr_mid(cal: list[str], p: dict) -> list[tuple]:
    out = []
    for E in election_days():
        b = idx_le(cal, E)
        if b < 0 or E > cal[-1]:
            continue
        out.append((b, b, b + p["H"]))
    return out


def _months(cal: list[str]) -> dict:
    """{"YYYY-MM": [位置]}。"""
    m: dict = {}
    for i, d in enumerate(cal):
        m.setdefault(d[:7], []).append(i)
    return m


def tr_santa(cal: list[str], p: dict) -> list[tuple]:
    M = _months(cal)
    out = []
    for ym, Dy in M.items():
        if ym[5:] != "12":
            continue
        y = int(ym[:4])
        Jy = M.get(f"{y + 1:04d}-01", [])
        if len(Dy) < p["before"] + 1 or len(Jy) < p["after"]:
            continue
        b = Dy[-(p["before"] + 1)]
        out.append((b, b, Jy[p["after"] - 1]))
    return out


def tr_jan(cal: list[str], px: np.ndarray, p: dict) -> list[tuple]:
    """一月漲 > th → 1 月最後一個交易日收盤是訊號、隔天收盤買、同年 12 月最後一個交易日收盤賣（12 月沒走完＝q 用 len(cal)＋之後的位置）。"""
    M = _months(cal)
    T = len(cal)
    out = []
    for ym, Jy in M.items():
        if ym[5:] != "01":
            continue
        y = int(ym[:4])
        P = M.get(f"{y - 1:04d}-12")
        if not P:
            continue
        J = Jy[-1]
        if f"{y:04d}-02" not in M and J == T - 1:
            continue                                    # 1 月還沒走完（資料最後一天在 1 月）
        if not (px[J] / px[P[-1]] - 1.0 > p["th"]):
            continue
        Dy = M.get(f"{y:04d}-12")
        nxt = M.get(f"{y + 1:04d}-01")
        if Dy and nxt:
            q = Dy[-1]
        else:
            q = T + 10 ** 6                              # 12 月還沒走完：持有中（現在另外算賣出日）
        out.append((J, J + S.LAG, q))
    return out


def ath_days(px: np.ndarray, gap: int) -> list[int]:
    """收盤創新高（比之前所有日子都高），而且上一次創新高是 gap 天以前或更早。"""
    out, mx, last = [], px[0], 0
    for t in range(1, len(px)):
        if px[t] > mx:
            if t - last >= gap:
                out.append(t)
            mx, last = px[t], t
    return out


def bull_scan(px: np.ndarray, th: float) -> tuple[list[int], dict]:
    """熊市後漲 th：→ (訊號日, 資料最後一天的狀態 {"bear", "M", "L"})。"""
    out = []
    mx, bear, lo = px[0], False, None
    for t in range(1, len(px)):
        if not bear:
            mx = max(mx, px[t])
            if px[t] <= (1.0 - th) * mx:
                bear, lo = True, px[t]
        else:
            lo = min(lo, px[t])
            if px[t] >= (1.0 + th) * lo:
                out.append(t)
                bear, mx = False, px[t]
    return out, {"bear": bear, "M": float(mx), "L": None if lo is None else float(lo)}


def vixinv_days(r: np.ndarray, th: float, reset: int) -> list[int]:
    out = []
    for t in range(reset, len(r)):
        if not (np.isfinite(r[t]) and r[t] >= th):
            continue
        w = r[t - reset:t]
        if np.isfinite(w).all() and (w < th).all():
            out.append(t)
    return out


LNY_MIN_GAP = 5           # 農曆年休市至少 5 個日曆天（1990～2026 實際 8～12 天）；資料剛好停在封關日時那一年看不到休市、先不算


def lny_close(days: list[str]) -> dict:
    """{年: 封關日的位置}：1/10～2/28 之間、和下一個交易日相隔最多日曆天的那一天（days 可以接上未來的交易日）。"""
    out: dict = {}
    best: dict = {}
    lo, hi = S.LNY_WINDOW
    for i in range(len(days) - 1):
        d = days[i]
        y = d[:4]
        if not (f"{y}-{lo}" <= d <= f"{y}-{hi}"):
            continue
        g = days_between(d, days[i + 1])
        if int(y) not in best or g > best[int(y)]:
            best[int(y)] = g
            out[int(y)] = i
    return {y: i for y, i in out.items() if best[y] >= LNY_MIN_GAP}


def tr_lny(cal: list[str], k: str, p: dict) -> list[tuple]:
    out = []
    for y, C in lny_close(cal).items():
        if k == "lnypre":
            if C - p["k"] >= 0:
                out.append((C - p["k"], C - p["k"], C))
        else:
            out.append((C, C, C + p["H"]))
    return out


def nsf_days(cal: list[str]) -> list[int]:
    out = []
    for d, _ in S.NSF:
        i = idx_le(cal, d)
        if i >= 0 and d <= cal[-1]:
            out.append(i)
    return out


def raw_trades(D: dict, k: str, p: dict) -> list[tuple]:
    """一條規則、一組參數 → 全部的 (t, b, q)（還沒依評估期間篩選、事件型還沒去重）。"""
    cal, px = D["cal"], D["px"]
    if k == "mid":
        return tr_mid(cal, p)
    if k == "santa":
        return tr_santa(cal, p)
    if k == "jan":
        return tr_jan(cal, px, p)
    if k in ("lnypre", "lnypost"):
        return tr_lny(cal, k, p)
    if k == "ath":
        ts = ath_days(px, p["gap"])
    elif k == "bull":
        ts = bull_scan(px, p["th"])[0]
    elif k == "vixinv":
        ts = vixinv_days(D["vixa"] / D["v3a"], p["th"], p["reset"])
    elif k == "nsf":
        ts = nsf_days(cal)
    else:
        raise KeyError(k)
    return [(t, t + S.LAG, t + S.LAG + p["H"]) for t in ts]


def select(trades: list[tuple], lo: int, hi: int | None, H: int | None, T: int) -> tuple[list[tuple], list[tuple]]:
    """買進日在 lo～hi（含；hi＝None＝不限）→ (賣出日在資料裡的, 還沒賣的)。H 不是 None＝事件型，照 t 去重（同 xstrat.dedupe）。"""
    tr = sorted(x for x in trades if x[1] >= lo and (hi is None or x[1] <= hi))
    if H is not None:
        keep = set(XT.dedupe([t for t, _, _ in tr], H))
        tr = [x for x in tr if x[0] in keep]
    done = [x for x in tr if x[2] < T]
    open_ = [x for x in tr if x[1] < T <= x[2]]
    return done, open_


def hold_of(R: dict, p: dict) -> int | None:
    """事件型去重用的天數（排定的規則不去重）。"""
    return p["H"] if R["when"] == "sig" and R["k"] != "jan" else None


# ── 成績與判定（第 6 節） ─────────────────────────────────────────────────────

def base_rate(px: np.ndarray, lo: int, hi: int | None, holds: list[int], c: float) -> float | None:
    """隨便挑一天：買進日 lo～hi（hi＝None＝到最後一個能抱滿的日子），抱 h 天賺錢的比例；每一次用它自己的 h，再平均。"""
    T = len(px)
    ws, cache = [], {}
    for h in holds:
        if h not in cache:
            top = T - h - 1 if hi is None else min(hi, T - h - 1)
            if top < lo:
                cache[h] = None
            else:
                r = px[lo + h:top + h + 1] / px[lo:top + 1] * (1.0 - c) / (1.0 + c) - 1.0
                cache[h] = float((r > 0).mean())
        if cache[h] is not None:
            ws.append(cache[h])
    return float(np.mean(ws)) if ws else None


def mae(px: np.ndarray, b: int, q: int) -> float:
    """抱的期間中途最多跌：買進價到持有期間（b 之後到 q）最低收盤。"""
    if q <= b:
        return 0.0
    return float(max(0.0, 1.0 - px[b + 1:q + 1].min() / px[b]))


def stats(px: np.ndarray, trades: list[tuple], lo: int, hi: int | None, c: float) -> dict:
    """一組已經篩好的交易 → 次數、賺錢比例、中位數、平均、排除極端、去掉最好一次、最差、最好、獲利因子、隨便挑一天、中途最多跌。"""
    if not trades:
        return {"n": 0}
    r = np.array([XT.net(px[b], px[q], c) for _, b, q in trades])
    holds = [q - b for _, b, q in trades]
    gain, loss = float(r[r > 0].sum()), float(-r[r < 0].sum())
    m = [mae(px, b, q) for _, b, q in trades]
    out = {"n": len(r), "win": float((r > 0).mean()), "med": float(np.median(r)), "avg": float(r.mean()),
           "trim": RB.trim_mean(r, S.TRIM_Q, S.TRIM_N), "lbo": RB.lbo_mean(r),
           "worst": float(r.min()), "best": float(r.max()), "pf": (gain / loss) if loss > 0 else None,
           "hold": float(np.mean(holds)), "base": base_rate(px, lo, hi, holds, c),
           "mae": float(np.median(m)), "mae_max": float(max(m))}
    out["ok"] = ok(out)
    return out


def ok(s: dict) -> bool:
    """過關（不看次數）：賺錢比例 ≥ WIN、不低於隨便挑一天、中位數 ＞ 0、排除極端的平均 ＞ 0。"""
    w, b, m, t = s.get("win"), s.get("base"), s.get("med"), s.get("trim")
    return bool(w is not None and b is not None and m is not None and t is not None
                and w >= S.WIN and w >= b and m > 0 and t > 0)


def tier(full: dict, rec_ok: bool | None, share: float) -> str:
    if full.get("n", 0) < S.N_MIN:
        return "few"
    if not full["ok"]:
        return "none"
    if (rec_ok is None or rec_ok) and share >= S.GRID_OK - 1e-12:
        return "good"
    return "ref"


def binom_p(n: int, k: int, p0: float | None) -> float | None:
    """如果每一次賺錢的機率＝p0，至少 k 次賺錢的機率（單尾）。"""
    if not n or p0 is None:
        return None
    return float(sum(math.comb(n, i) * p0 ** i * (1.0 - p0) ** (n - i) for i in range(k, n + 1)))


def luck(px: np.ndarray, trades: list[tuple], lo: int, c: float, key: str) -> float | None:
    """打亂測試：買進日整段循環挪動 LUCK_DRAWS 次（每一次抱的天數不變），賺錢比例 ≥ 實際的比例（同 xstrat.luck_trade，種子 LUCK_SEED）。"""
    if not trades:
        return None
    T = len(px)
    L = T - lo
    e = np.array([b for _, b, _ in trades]) - lo
    h = np.array([q - b for _, b, q in trades])
    win = float(np.mean([XT.net(px[b], px[q], c) > 0 for _, b, q in trades]))
    rng = np.random.default_rng([S.LUCK_SEED, zlib.crc32(key.encode("utf-8"))])
    a, z = int(S.LUCK_SHIFT[0] * L), max(int(S.LUCK_SHIFT[0] * L) + 1, int(S.LUCK_SHIFT[1] * L))
    ge = 0
    for o in rng.integers(a, z, size=S.LUCK_DRAWS).tolist():
        e2 = lo + (e + o) % L
        q2 = e2 + h
        okk = q2 < T
        if not okk.any():
            continue
        rr = px[q2[okk]] / px[e2[okk]] * (1.0 - c) / (1.0 + c) - 1.0
        if float((rr > 0).mean()) >= win - 1e-12:
            ge += 1
    return (1 + ge) / (1 + S.LUCK_DRAWS)


def halves(px: np.ndarray, cal: list[str], trades: list[tuple], c: float) -> list[dict]:
    """依買進日先後分成前一半、後一半（奇數時中間那一次算前一半）。"""
    n = len(trades)
    if n < 2:
        return []
    k = (n + 1) // 2
    out = []
    for part in (trades[:k], trades[k:]):
        r = np.array([XT.net(px[b], px[q], c) for _, b, q in part])
        out.append({"n": len(r), "win": float((r > 0).mean()), "med": float(np.median(r)),
                    "a": cal[part[0][1]], "z": cal[part[-1][1]]})
    return out


def _r(v, k: int = 4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), k)


def _rs(s: dict) -> dict:
    return {kk: (_r(v) if isinstance(v, float) else v) for kk, v in s.items()}


# ── 一條規則、一個市場 ───────────────────────────────────────────────────────

class Mkt:
    def __init__(self, mk: str, D: dict | None = None):
        self.mk = mk
        self.D = D or data(mk)
        self.cal, self.px = self.D["cal"], np.asarray(self.D["px"], dtype=float)
        self.T = len(self.cal)
        self.c = S.COST[mk]
        self.s0 = idx_ge(self.cal, S.START[mk])
        self.r0 = idx_ge(self.cal, XT._recent_from(self.cal))

    def trades(self, R: dict, p: dict, lo: int | None = None, hi: int | None = None) -> tuple[list[tuple], list[tuple]]:
        return select(raw_trades(self.D, R["k"], p), self.s0 if lo is None else lo, hi, hold_of(R, p), self.T)


def evaluate(M: Mkt, R: dict) -> dict:
    k, p = R["k"], R["p"]
    px, cal, c = M.px, M.cal, M.c
    done, open_ = M.trades(R, p)
    full = stats(px, done, M.s0, None, c)
    rec_tr = [x for x in done if x[1] >= M.r0]
    rec = stats(px, rec_tr, M.r0, None, c)
    rec_ok = ok(rec) if rec.get("n", 0) >= S.N10 else None
    grid = []
    for q in XT._combos(R["grid"]):
        pp = {**p, **q}
        g = full if pp == p else stats(px, M.trades(R, pp)[0], M.s0, None, c)
        grid.append({"p": q, "ok": bool(g.get("ok")) and g.get("n", 0) >= S.N_MIN, "n": g.get("n", 0),
                     "win": _r(g.get("win")), "base": _r(g.get("base")), "med": _r(g.get("med"))})
    share = sum(g["ok"] for g in grid) / len(grid)
    tr = tier(full, rec_ok, share)
    key = f"rare:{M.mk}:{k}"
    out = {"k": k, "mk": M.mk, "a": cal[M.s0], "z": cal[-1], "r0": cal[M.r0], "cost": c, "lag": S.LAG if R["when"] == "sig" else 0,
           "full": _rs(full), "rec": _rs(rec), "rec_ok": rec_ok, "grid": grid, "grid_ok": _r(share), "tier": tr,
           "few": full.get("n", 0) < S.FEW_TAG,
           "luck": _r(luck(px, done, M.s0, c, key)),
           "binom": _r(binom_p(full.get("n", 0), int(round(full.get("win", 0) * full.get("n", 0))) if full.get("n") else 0,
                               full.get("base")), 6),
           "halves": [_rs(h) for h in halves(px, cal, done, c)]}
    # 另外看的期間（第 7 節）：來源之後、S&P 500 1950 年以前
    outs = {}
    if R.get("pub"):
        lo = idx_ge(cal, f"{R['pub']:04d}-01-01")
        sub = [x for x in done if x[1] >= lo]
        outs["pub"] = {"from": f"{R['pub']:04d}", **_rs(stats(px, sub, lo, None, c))}
    if M.mk == S.EARLY[0]:
        lo, hi = idx_ge(cal, S.EARLY[1]), idx_le(cal, S.EARLY[2])
        sub, _ = M.trades(R, p, lo=lo, hi=hi)
        outs["early"] = {"from": S.EARLY[1][:4], "to": S.EARLY[2][:4], **_rs(stats(px, sub, lo, hi, c))}
    out["outs"] = outs
    # 全部資金照做（其他時間空手）、同一段一直抱著
    tr4 = [(t, b, q, q) for t, b, q in done]
    eq = XT.trade_equity(px, tr4, M.s0, c)
    cs = XT.curve_stats(eq, cal, M.s0)
    out["curve"] = {"cagr": _r(cs["cagr"]), "mdd": _r(cs["mdd"]),
                    "expo": _r(float(XT.trade_held(M.T, tr4)[M.s0 + 1:].mean())) if M.T > M.s0 + 1 else None}
    bh = XT.bh_stats(px, cal, M.s0)
    out["bh"] = {"cagr": _r(bh["cagr"]), "mdd": _r(bh["mdd"])}
    out["tr"] = [[cal[t], cal[b], _r(px[b], 2), cal[q], _r(px[q], 2), q - b, _r(XT.net(px[b], px[q], c), 5),
                  _r(mae(px, b, q), 5)] for t, b, q in done]
    out["now"] = now(M, R, done, open_)
    out["rec_v"] = recommend(R, out) if M.mk == R["home"] else None
    return out


def recommend(R: dict, res: dict) -> str:
    """第 7 節：主要市場 ★ 而且另外看的期間（OUT_N 次以上的）都不低於隨便挑一天＝rec；● 或 ★ 但另外那段沒過＝watch；其他＝no。"""
    t = res["tier"]
    if t not in ("good", "ref"):
        return "no"
    if t == "ref":
        return "watch"
    for o in res["outs"].values():
        if o.get("n", 0) >= S.OUT_N and (o.get("base") is None or o["win"] < o["base"]):
            return "watch"
    return "rec"


# ── 現在 ───────────────────────────────────────────────────────────────────

def now(M: Mkt, R: dict, done: list[tuple], open_: list[tuple]) -> dict:
    """資料最後一天：持有中（哪天買、哪天賣）、下一次排定的日子（排定的規則）、事件型離觸發還差多少。
    之後的交易日＝xstrat.future_days（證交所／NYSE 休市表）；台股表沒有涵蓋的年份標 approx（證交所可能另加休市日）。"""
    from .. import twholidays
    k, p = R["k"], R["p"]
    cal, px, T = M.cal, M.px, M.T
    fut = XT.future_days(M.mk, cal[-1], 400)
    days = cal + fut
    out: dict = {"last": cal[-1]}

    def approx(d: str | None) -> bool:
        return bool(d and M.mk == "tw" and not twholidays.covers(date.fromisoformat(d)))

    if R["when"] == "sched":
        tr = tr_mid(days, p) if k == "mid" else tr_santa(days, p) if k == "santa" else tr_lny(days, k, p)
        for t, b, q in sorted(tr, key=lambda x: x[1]):
            if q < T:
                continue
            qd = days[q] if q < len(days) else None
            out.update({"st": "hold" if b < T else "wait", "bd": days[b], "qd": qd, "approx": approx(qd)})
            if b < T:
                out.update({"bp": _r(px[b], 2), "chg": _r(px[-1] / px[b] - 1.0)})
            if k in ("lnypre", "lnypost"):
                C = q if k == "lnypre" else b
                out.update({"close": days[C], "reopen": days[C + 1] if C + 1 < len(days) else None})
            break
        return out
    if open_:
        t, b, q = open_[-1]
        qd = days[q] if q < len(days) else None
        if k == "jan" and q >= T:
            y = int(cal[b][:4])
            dec = [d for d in days[T:] if d[:7] == f"{y:04d}-12"]
            qd = dec[-1] if dec else None
        out.update({"st": "hold", "sd": cal[t], "bd": cal[b], "bp": _r(px[b], 2), "qd": qd, "approx": approx(qd),
                    "chg": _r(px[-1] / px[b] - 1.0)})
        return out
    out["st"] = "wait"
    if k == "jan":
        y = int(cal[-1][:4]) + (1 if cal[-1][5:7] != "01" else 0)
        jan = [d for d in days if d[:7] == f"{y:04d}-01"]
        out["check"] = jan[-1] if jan else None
    elif k == "ath":
        mx = float(px.max())
        last = int(np.flatnonzero(px >= mx)[0])
        out.update({"ath": cal[last], "ath_px": _r(mx, 2), "since": T - 1 - last, "need": p["gap"], "off": _r(px[-1] / mx - 1.0)})
    elif k == "bull":
        st = bull_scan(px, p["th"])[1]
        if st["bear"]:
            out.update({"bear": True, "low": _r(st["L"], 2), "confirm": _r((1 + p["th"]) * st["L"], 2)})
        else:
            out.update({"bear": False, "high": _r(st["M"], 2), "bear_at": _r((1 - p["th"]) * st["M"], 2)})
        out["px"] = _r(px[-1], 2)
    elif k == "vixinv":
        r = M.D["vixa"] / M.D["v3a"]
        fin = np.flatnonzero(np.isfinite(r))
        if len(fin):
            j = int(fin[-1])
            out.update({"ratio": _r(r[j]), "rd": cal[j]})
    return out


def run(markets: tuple = S.MARKETS) -> dict:
    res: dict = {"spec_ver": S.VER, "asof": None, "rules": {}}
    Ms = {mk: Mkt(mk) for mk in markets}
    res["asof"] = {mk: M.cal[-1] for mk, M in Ms.items()}
    for R in S.RULES:
        res["rules"][R["k"]] = {mk: evaluate(Ms[mk], R) for mk in R["mk"] if mk in Ms}
    return res


def write(res: dict) -> bool:
    import json
    from . import store
    p = store.LAB / OUT
    txt = json.dumps(res, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.write_text(txt, encoding="utf-8")
    return True


def load() -> dict | None:
    import json
    from . import store
    p = store.LAB / OUT
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if d.get("spec_ver") == S.VER else None
