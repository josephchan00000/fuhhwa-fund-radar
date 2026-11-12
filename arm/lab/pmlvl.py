"""盤前價位第 4 段：依正常波動畫價位、停損也跟著波動（規格 arm/lab/pmlvlspec.py VER 1；docs/lab_premarket_plan.md 第 15 節）。

只讀資料分支（5 秒指數、期貨日行情與夜盤、選擇權日行情算波動率），不抓任何東西。
  run(root) → data/lab/pmlvl_research.json（scripts/run_pmlvl.py 寫）
每一天：錨點 A（夜盤估的開盤）± k·em 兩個價位 → rev（回頭）或 brk（突破）進場 → s·em 停損、t·em 目標、13:25 出場。
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from . import pmlvlspec as S


# ── 資料 ─────────────────────────────────────────────────────────────────────

def prepare(root: Path, log=print) -> list[tuple]:
    """→ [(日, 錨點 A, 正常波動 em, 前一天收盤 C, 5 秒指數陣列)]（FIRST 起、A 與 em 都有的日子）。"""
    from . import heatbubble as BB
    from . import pmval as V
    idx = {d: v for d, v in V.load_idx(root).items() if d >= "2016-01-04"}
    closes = {k: float(v) for k, v in BB.taiex_daily().items() if v}
    idx = {d: v for d, v in idx.items() if d in closes and len(v) > S.EXIT_T}
    iv = V.ivs(root)
    fday, fnight = V.load_futday(root)
    days = sorted(idx)
    out = []
    for prev, d in zip(days[:-1], days[1:]):
        if d < S.FIRST or d not in fnight or prev not in fday or not iv.get(prev) or prev not in closes:
            continue
        k = V.night_k(fnight, d)
        if k not in fday[prev]:
            continue
        c = closes[prev]
        a = c + fnight[d][k][3] - fday[prev][k][3]
        em = c * iv[prev] * math.sqrt(1 / S.TRADING_YEAR)
        out.append((d, float(a), float(em), c, idx[d]))
    log(f"可用的日子 {len(out)} 天（{out[0][0]}～{out[-1][0]}）" if out else "沒有可用的日子")
    return out


# ── 一天 ─────────────────────────────────────────────────────────────────────

def _exit(p: np.ndarray, e: int, px: float, dirn: int, s: float, t: float, em: float) -> tuple[int, float, str]:
    """進場在第 e 個點、價格 px、方向 dirn（+1 買、−1 賣）→ (出場第幾個, 出場價, 原因)。"""
    seg = p[e + 1:S.EXIT_T + 1]
    stop, tgt = px - dirn * s * em, px + dirn * t * em
    if dirn > 0:
        hit = (seg <= stop) | (seg >= tgt)
    else:
        hit = (seg >= stop) | (seg <= tgt)
    j = int(np.argmax(hit)) if hit.any() else -1
    if j < 0:
        return S.EXIT_T, float(p[S.EXIT_T]), "time"
    x = float(seg[j])
    why = "stop" if (dirn > 0 and x <= stop) or (dirn < 0 and x >= stop) else "target"
    return e + 1 + j, x, why


def _first_cross(p: np.ndarray, lvl: float, up: bool, after: int) -> int | None:
    """第 after 個點之後（不含）第一次越過價位（前一點還沒越過、這一點越過），ENTRY_LAST 以前；沒有＝None。"""
    lo = max(after + 1, S.ENTRY_FROM)
    if lo > S.ENTRY_LAST:
        return None
    cur = p[lo:S.ENTRY_LAST + 1] >= lvl if up else p[lo:S.ENTRY_LAST + 1] <= lvl
    prv = p[lo - 1:S.ENTRY_LAST] >= lvl if up else p[lo - 1:S.ENTRY_LAST] <= lvl
    m = cur & ~prv
    return lo + int(np.argmax(m)) if m.any() else None


def day_trades(p: np.ndarray, anchor: float, em: float, fam: str, k: float, s: float, t: float) -> list[tuple]:
    """→ [(進場第幾個, 進場價, 方向, 出場第幾個, 出場價, 原因, 哪一邊 'u'/'d')]。"""
    o = float(p[S.OPEN_T])
    up_lvl, dn_lvl = anchor + k * em, anchor - k * em
    sides = {}
    if o < up_lvl:
        sides["u"] = (up_lvl, True, -1 if fam == "rev" else +1)
    if o > dn_lvl:
        sides["d"] = (dn_lvl, False, +1 if fam == "rev" else -1)
    out, after = [], S.OPEN_T
    while sides:
        cand = []
        for nm, (lvl, up, dirn) in sides.items():
            i = _first_cross(p, lvl, up, after)
            if i is not None:
                cand.append((i, nm, dirn))
        if not cand:
            break
        i, nm, dirn = min(cand)
        px = float(p[i])
        x_i, x_px, why = _exit(p, i, px, dirn, s, t, em)
        out.append((i, px, dirn, x_i, x_px, why, nm))
        del sides[nm]
        after = x_i
    return out


def pnl(entry: float, exit_: float, dirn: int, mult: float = S.COST_MULT) -> float:
    return dirn * (exit_ - entry) * S.MTX - mult * (S.side_cost(entry) + S.side_cost(exit_))


# ── 全部組合 ──────────────────────────────────────────────────────────────────

def all_trades(days: list[tuple], anchor_open: bool = False) -> dict:
    """→ {(族, k, s, t): [交易 dict]}。"""
    out = {}
    for fam in S.FAMILIES:
        for k, s, t in S.grid():
            rows = []
            for d, a, em, c, p in days:
                anc = float(p[S.OPEN_T]) if anchor_open else a
                for i, px, dirn, x_i, x_px, why, nm in day_trades(p, anc, em, fam, k, s, t):
                    fpx = _exit(p, i, px, -dirn, s, t, em)[1]             # 打亂測試用：同一刻反方向的結果
                    rows.append({"d": d, "i": i, "px": px, "dir": dirn, "xi": x_i, "xpx": x_px, "why": why, "side": nm,
                                 "em": em, "c": c, "pnl": pnl(px, x_px, dirn), "pnl1": pnl(px, x_px, dirn, 1),
                                 "flip": pnl(px, fpx, -dirn), "pts": dirn * (x_px - px)})
            out[(fam, k, s, t)] = rows
    return out


def metrics(rows: list[dict], key: str = "pnl") -> dict:
    if not rows:
        return {"n": 0}
    v = np.array([r[key] for r in rows], dtype=float)
    years: dict[str, float] = {}
    for r in rows:
        years[r["d"][:4]] = years.get(r["d"][:4], 0.0) + r[key]
    cum = np.cumsum(v)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    ds = sorted(r["d"] for r in rows)
    half = ds[len(ds) // 2]
    h1 = [r[key] for r in rows if r["d"] < half]
    h2 = [r[key] for r in rows if r["d"] >= half]
    top = sorted(v)[:-S.TOP_DROP] if len(v) > S.TOP_DROP else []
    return {"n": int(len(v)), "mean": round(float(v.mean()), 1), "med": round(float(np.median(v)), 1),
            "win": round(float((v > 0).mean()), 4), "total": round(float(v.sum()), 1),
            "pts": round(float(np.mean([r["pts"] for r in rows])), 2),
            "maxdd": round(float((peak - cum).max()), 1),
            "years": {y: round(x, 1) for y, x in sorted(years.items())},
            "years_ok": round(sum(1 for x in years.values() if x > 0) / len(years), 4),
            "h1": round(float(np.mean(h1)), 1) if h1 else None, "h2": round(float(np.mean(h2)), 1) if h2 else None,
            "ex_top": round(float(np.mean(top)), 1) if len(top) else None,
            "why": {w: sum(1 for r in rows if r["why"] == w) for w in ("stop", "target", "time")}}


def walk_forward(tr: dict, fam: str) -> tuple[dict, list[dict]]:
    """每年用之前年份挑平均最好的一組 → ({年: (k, s, t)}, 樣本外交易)。"""
    years = sorted({r["d"][:4] for rows in tr.values() for r in rows})
    picks, oos = {}, []
    for y in years:
        if int(y) < S.OOS_FIRST:
            continue
        best, best_m = None, None
        for k, s, t in S.grid():
            past = [r["pnl"] for r in tr[(fam, k, s, t)] if r["d"][:4] < y]
            if len(past) < S.MIN_PICK_N:
                continue
            m = float(np.mean(past))
            if best_m is None or m > best_m:
                best, best_m = (k, s, t), m
        if best is None:
            continue
        picks[y] = best
        oos += [r for r in tr[(fam, *best)] if r["d"][:4] == y]
    oos.sort(key=lambda r: (r["d"], r["i"]))
    return picks, oos


def placebo(rows: list[dict], seed: int = S.SEED, n: int = S.PLACEBO_N) -> dict:
    if not rows:
        return {"p": None}
    a = np.array([r["pnl"] for r in rows])
    f = np.array([r["flip"] for r in rows])
    g = np.random.default_rng(seed)
    act = float(a.mean())
    means = np.array([np.where(g.random(len(a)) < 0.5, f, a).mean() for _ in range(n)])
    return {"p": round(float((means >= act).mean()), 4), "rand_mean": round(float(means.mean()), 1), "actual": round(act, 1)}


def judge(m: dict, pl: dict) -> dict:
    ok = {
        "1_mean": m.get("n", 0) > 0 and m["mean"] > 0,
        "2_placebo": pl.get("p") is not None and pl["p"] <= S.P_MAX,
        "3_years": m.get("n", 0) > 0 and m["years_ok"] >= S.YEARS_OK - 1e-9,
        "4_halves": m.get("n", 0) > 0 and (m["h1"] or 0) > 0 and (m["h2"] or 0) > 0,
        "5_n": m.get("n", 0) >= S.MIN_N,
        "6_ex_top": m.get("n", 0) > 0 and (m["ex_top"] or 0) > 0,
    }
    return {"ok": ok, "verdict": "過關" if all(ok.values()) else "沒過"}


def _terc(days: list[tuple]) -> dict[str, int]:
    """每天的波動（em ÷ C）在過去 250 天（不含當天）的三分位：0 低、1 中、2 高；不到 60 天不分。"""
    out, hist = {}, []
    for d, a, em, c, p in days:
        x = em / c
        if len(hist) >= 60:
            h = hist[-250:]
            lo, hi = np.percentile(h, [100 / 3, 200 / 3])
            out[d] = 0 if x <= lo else 2 if x >= hi else 1
        hist.append(x)
    return out


def run(root: Path, log=print) -> dict:
    days = prepare(Path(root), log)
    tr = all_trades(days)
    log(f"錨點＝夜盤估的開盤：72 組算完")
    tro = all_trades(days, anchor_open=True)
    log(f"錨點＝09:01 實際開盤（只列）：72 組算完")
    terc = _terc(days)
    out = {"ver": S.VER, "spec_fp": S.fingerprint(), "asof": days[-1][0] if days else None, "first": days[0][0] if days else None,
           "days": len(days), "fam": {}, "grid": [], "list": {"open": {}, "cost1": {}, "em_terc": {}}}
    for fam in S.FAMILIES:
        picks, oos = walk_forward(tr, fam)
        m = metrics(oos)
        pl = placebo(oos)
        out["fam"][fam] = {"pick": {y: list(v) for y, v in picks.items()}, "oos": m, "placebo": pl, "judge": judge(m, pl),
                           "trades": [[r["d"], r["i"], round(r["px"], 2), r["dir"], r["xi"], round(r["xpx"], 2), r["why"], round(r["pnl"])]
                                      for r in oos]}
        po, oo = walk_forward(tro, fam)
        out["list"]["open"][fam] = {"pick": {y: list(v) for y, v in po.items()}, "oos": metrics(oo)}
        out["list"]["cost1"][fam] = metrics(oos, "pnl1")
        out["list"]["em_terc"][fam] = {str(g): metrics([r for r in oos if terc.get(r["d"]) == g]) for g in (0, 1, 2)}
        log(f"{fam}：樣本外 {m.get('n')} 筆、平均 {m.get('mean')} 元、打亂 p={pl.get('p')} → {out['fam'][fam]['judge']['verdict']}")
    for (fam, k, s, t), rows in tr.items():
        m = metrics(rows)
        out["grid"].append({"fam": fam, "k": k, "s": s, "t": t, "n": m.get("n", 0), "mean": m.get("mean"), "win": m.get("win"),
                            "years_ok": m.get("years_ok")})
    return out
