"""W3 研究（reports/W3_plan.md v1，跑之前寫定）：每週 × 合併名單 S9 上的股票 → 28 個條件、7 族分數、標籤；評估。

條件、7 族分數的定義在 fuhhwa arm/lab/layer.py（頁面同一套）。條件只用當週收盤以前的資料；
標籤（之後 N 日最高價 ≥ 收盤 × (1+g)）只拿來評估。
"""

from __future__ import annotations

import bisect
import json
import math

import numpy as np

from . import features as FT
from . import labpanel as LP
from . import sepa as SE
from . import watch as WT

PER = {"IS": ("2014-01-02", "2019-12-31"), "VAL": ("2020-01-02", "2022-12-30"), "HO": ("2023-01-02", "2100-12-31")}
SUBS = {"IS1": ("2014-01-02", "2016-12-31"), "IS2": ("2017-01-02", "2019-12-31")}
YEARS_VAL = ("2020", "2021", "2022")
LABS = {"A": (60, 0.5), "B": (250, 1.0), "C": (250, 2.0)}
MAIN = "B"                                   # 使用者 2026-10-16：一年內翻倍
TIER = {"lift": 1.5, "per_week": 1.0}        # 第一層門檻（3.1）
GREEDY = {"max_k": 3, "sub_lift": 1.2, "pos": 50, "per_week": 1.0}
JUDGE = {"lift": 1.3}                        # 2020–2022 判定（第 4 節）
NEW_GAP = 13                                 # 新進名單口徑：同一檔 13 週內只算第一次
PAIR_TOP, PAIR_NMIN = 10, 100
EARLY = {"B": WT.EARLY["B"], "C": WT.EARLY["C"], "E": WT.EARLY["E"]}


def shared():
    bt3d, _ = LP.arm()
    from arm.lab import layer as LY  # noqa: WPS433
    from arm.lab import packtest as PT  # noqa: WPS433

    return LY, PT, bt3d


# ---------------------------------------------------------------------------------------------- 橫斷面分數
def _latest_le(items: list[tuple[int, object]], i: int):
    """items＝[(可得日索引, 值)] 依日排序 → i 日（含）以前最新可得的值。"""
    k = bisect.bisect_right([t for t, _ in items], i) - 1
    return items[k][1] if k >= 0 else None


def cross_sections(m, F, W: np.ndarray, eps: dict, rev: dict, ind: dict, log=print) -> dict[str, list[set]]:
    """每週合格股票裡：營收驚喜前 20%、財報驚喜前 20%、相對強勢前 10%、價值＋動能前 20% → {鍵: [每週的代號集合]}。
    營收驚喜排除金融保險業（同月營收驚喜策略）；價值＋動能同 bt3s.p4_rows（E/P ≤ 0.25）。"""
    LY, PT, _ = shared()
    cal = [d.strftime("%Y-%m-%d") for d in m.dates]
    el = F["elig"]
    rf = PT.rev_forms(cal)                                         # [(可得日, 營收月份)]
    quarters = sorted({q for e in eps.values() for q in e})
    qf = sorted((t, q) for q in quarters if (t := PT.form_after_deadline(cal, PT.deadline(q))) is not None)
    dl = sorted((PT.deadline(q), q) for q in quarters)
    c_ff = m.c_ff
    raw = m.c / m.f
    fin = {c for c in m.stocks if "金融" in (ind.get(c) or "")}
    s_cache: dict = {}
    e_cache: dict = {}
    t_cache: dict = {}
    out: dict[str, list[set]] = {k: [] for k in ("sur20", "sue20", "mom10", "vm20")}
    for i in W:
        i = int(i)
        U = np.flatnonzero(el[i])
        ym, q = _latest_le(rf, i), _latest_le(qf, i)
        kq = bisect.bisect_right([d for d, _ in dl], cal[i]) - 1
        qstar = dl[kq][1] if kq >= 0 else None
        sur, sue, mom, ep = {}, {}, {}, {}
        for j in U:
            c = m.stocks[j]
            if ym is not None and c not in fin:
                key = (c, ym)
                if key not in s_cache:
                    s_cache[key] = PT.sur(rev.get(c) or {}, ym)
                sur[c] = s_cache[key]
            if q is not None and c in eps:
                key = (c, q)
                if key not in e_cache:
                    e_cache[key] = PT.sue(eps[c], q)
                sue[c] = e_cache[key]
            if i >= 126:
                a, b = c_ff[i - 126, j], c_ff[i - 21, j]
                if a == a and b == b and a > 0:
                    mom[c] = float(b / a - 1)
            if qstar is not None and c in eps and c in mom:
                key = (c, qstar)
                if key not in t_cache:
                    t_cache[key] = PT.ttm_eps(eps[c], cal[i])
                e, px = t_cache[key], raw[i, j]
                if e is not None and px == px and px > 0 and e / px <= 0.25:
                    ep[c] = float(e / px)
        out["sur20"].append(LY.top_set(sur, LY.TOP["sur20"]))
        out["sue20"].append(LY.top_set(sue, LY.TOP["sue20"]))
        out["mom10"].append(LY.top_set(mom, LY.TOP["mom10"]))

        def pr(d):
            return {c: (n + 1) / len(d) for n, c in enumerate(sorted(d, key=lambda c: (d[c], c)))}

        ra, rb = pr(ep), pr({c: mom[c] for c in ep})
        out["vm20"].append(LY.top_set({c: (ra[c] + rb[c]) / 2 for c in ra}, LY.TOP["vm20"]))
    log(f"[w3] 橫斷面：營收驚喜 {len(s_cache):,}、財報驚喜 {len(e_cache):,}、近四季 EPS {len(t_cache):,} 筆")
    return out


# ---------------------------------------------------------------------------------------------- 每週資料表
def build(m, F, extra, fund, W: np.ndarray, S9w: np.ndarray, a_set: set, b_set: set, eps: dict, rev: dict,
          ind: dict, log=print) -> dict:
    """→ 資料表（S9 上的每個股票週一列）＋ 涵蓋率要用的東西（每週收盤、段落）＋ 全部股票的每週標籤加總。"""
    LY, _, _ = shared()
    SP = SE.shared()
    T, N = m.c.shape
    cal = [d.strftime("%Y-%m-%d") for d in m.dates]
    el = F["elig"]
    K, X = LY.TIGHT
    tok, _, _ = SE.tight(m, F["hi52"], K, X, SP.NEAR_HIGH)
    rsl_new, _ = SE.rs_line(m)
    ma200, ma200p, maup = SE.ma200_up(m)
    ud = SE.ud_ratio(m)
    bno = SE.base_no(m, ma200, ma200p, np.flatnonzero(S9w.any(axis=0)))
    ppok, _, _ = SE.power_play(m, el, F["vol50"], F["dry"])
    log("[w3] 技術指標完成")
    Y = {L: FT.label(m, n, g, el) for L, (n, g) in LABS.items()}
    xs = cross_sections(m, F, W, eps, rev, ind, log)
    rows = []
    for k, i in enumerate(W):
        i = int(i)
        d = cal[i]
        js = np.flatnonzero(S9w[k])
        cnt: dict = {}
        for j in js:
            g = ind.get(m.stocks[j])
            if g:
                cnt[g] = cnt.get(g, 0) + 1
        for j in js:
            c = m.stocks[j]
            f = fund(c, i)
            rs, hi, cl, dy, u = F["rs"][i, j], F["hi52"][i, j], m.c[i, j], F["dry"][i, j], ud[i, j]
            cond = {
                "arule": (c, d) in a_set, "brule": (c, d) in b_set,
                "rnha": f.get("rnha") is True, "sur20": c in xs["sur20"][k],
                "ry25": f.get("ry3") is not None and f["ry3"] >= 0.25,
                "racc": f.get("racc") is not None and f["racc"] > 0,
                "sue20": c in xs["sue20"][k],
                "ey25": f.get("ey") is not None and f["ey"] >= 0.25,
                "eacc": f.get("eacc") is not None and f["eacc"] > 0,
                "c33": f.get("c33") is True,
                "gmd": f.get("gmd") is not None and f["gmd"] > 0,
                "roe15": f.get("roe") is not None and f["roe"] >= 0.15,
                "rs90": rs == rs and rs >= SP.RS_HI, "rsl": bool(rsl_new[i, j]), "mom10": c in xs["mom10"][k],
                "vcp": bool(F["vcp_ok"][i, j]), "tight": bool(tok[i, j]), "pp": bool(ppok[i, j]),
                "base12": int(bno[i, j]) in (1, 2), "ma200up": int(maup[i, j]) >= SP.MA200_UP,
                "ud12": u == u and u >= SP.UD_MIN,
                "h10": cl == cl and hi == hi and hi > 0 and cl / hi - 1 >= -0.10,
                "dry": dy == dy and dy <= SP.DRY,
                "ind2": cnt.get(ind.get(c), 0) >= 2,
                **LY.cap_bucket(None if extra["cap"][i, j] != extra["cap"][i, j] else float(extra["cap"][i, j])),
                "vm20": c in xs["vm20"][k],
            }
            y = {L: (None if Y[L][i, j] != Y[L][i, j] else int(Y[L][i, j])) for L in LABS}
            rows.append({"k": k, "j": int(j), "c": c, "d": d, "x": [bool(cond[key]) for key in LY.CKEYS],
                         "fam": LY.families(cond), "y": y})
    log(f"[w3] 資料表 {len(rows):,} 列")
    base = {L: {"pos": np.nansum(np.where(el[W], Y[L][W], np.nan), axis=1).tolist(),
                "n": (~np.isnan(np.where(el[W], Y[L][W], np.nan))).sum(axis=1).tolist()} for L in LABS}
    eps_w = {}
    for L in ("B", "C"):
        eps_w[L] = [(int(j), int(t0), int(pk), float(gain), float(m.h[pk, j]))
                    for j, t0, pk, gain in WT.episodes(m, Y[L], n=LABS[L][0])]
    YE = FT.label(m, 1250, 9.0, el)
    best: dict = {}
    for j, t0, pk, gain in WT.episodes(m, YE, n=1250):
        if cal[t0] >= PER["IS"][0] and (j not in best or gain > best[j][3]):
            best[j] = (int(j), int(t0), int(pk), float(gain), float(m.h[pk, j]))
    eps_w["E"] = sorted(best.values())
    return {"rows": rows, "W": [int(i) for i in W], "dates": [cal[int(i)] for i in W], "cal": cal, "stocks": m.stocks,
            "Cw": np.asarray(m.c[W], dtype=np.float32), "eps": eps_w, "base": base,
            "S9w": S9w.astype(bool)}


# ---------------------------------------------------------------------------------------------- 評估
class Tab:
    """資料表 → numpy 欄位，方便切期間、算命中率。"""

    def __init__(self, tb: dict):
        LY, _, _ = shared()
        r = tb["rows"]
        self.tb = tb
        self.keys = LY.CKEYS
        self.X = np.array([x["x"] for x in r], dtype=bool) if r else np.zeros((0, len(LY.CKEYS)), dtype=bool)
        self.fam = np.array([x["fam"] for x in r], dtype=bool) if r else np.zeros((0, len(LY.FAMILY)), dtype=bool)
        self.score = self.fam.sum(axis=1)
        self.k = np.array([x["k"] for x in r], dtype=int)
        self.j = np.array([x["j"] for x in r], dtype=int)
        self.d = np.array([x["d"] for x in r])
        self.y = {L: np.array([np.nan if x["y"][L] is None else x["y"][L] for x in r], dtype=float) for L in LABS}
        self.wd = np.array(tb["dates"])

    def col(self, key: str) -> np.ndarray:
        return self.X[:, self.keys.index(key)]

    def per(self, a: str, b: str) -> np.ndarray:
        return (self.d >= a) & (self.d <= b)

    def weeks(self, a: str, b: str) -> int:
        return int(((self.wd >= a) & (self.wd <= b)).sum())

    def new_entry(self, mask: np.ndarray, gap: int = NEW_GAP) -> np.ndarray:
        """同一檔 gap 週內只算第一次（只在 mask 內看）。"""
        out = np.zeros(len(mask), dtype=bool)
        last: dict = {}
        for n in np.flatnonzero(mask)[np.argsort(self.k[mask], kind="stable")]:
            j, k = self.j[n], self.k[n]
            if k - last.get(j, -10 ** 9) >= gap:
                out[n] = True
                last[j] = k
        return out

    def stat(self, mask: np.ndarray, a: str, b: str, lab: str = MAIN) -> dict:
        p = mask & self.per(a, b)
        y = self.y[lab][p]
        y = y[~np.isnan(y)]
        w = self.weeks(a, b)
        return {"n": int(p.sum()), "per_week": p.sum() / w if w else None, "pos": int(y.sum()),
                "p": float(y.mean()) if len(y) else None}


def lift(a: dict, b: dict):
    return a["p"] / b["p"] if a.get("p") is not None and b.get("p") else None


def base_rate(tb: dict, lab: str, a: str, b: str) -> float | None:
    wd = np.array(tb["dates"])
    sel = (wd >= a) & (wd <= b)
    pos = np.array(tb["base"][lab]["pos"])[sel].sum()
    n = np.array(tb["base"][lab]["n"])[sel].sum()
    return float(pos / n) if n else None


def single_table(T: Tab, a: str, b: str, subs: dict | None = None) -> list[dict]:
    """每個條件：S9 ∧ 條件的命中率、提升倍數（÷ 同期間 S9）、每週檔數、子期間提升倍數、新進名單口徑。"""
    allm = np.ones(len(T.d), dtype=bool)
    s9 = T.stat(allm, a, b)
    s9n = T.stat(T.new_entry(allm), a, b)
    out = []
    for n, key in enumerate(T.keys):
        m = T.X[:, n]
        st = T.stat(m, a, b)
        r = {"key": key, **st, "lift": lift(st, s9), "A": T.stat(m, a, b, "A")["p"], "C": T.stat(m, a, b, "C")["p"]}
        ne = T.stat(T.new_entry(m), a, b)
        r["new_p"], r["new_lift"] = ne["p"], lift(ne, s9n)
        for s, (x, y) in (subs or {}).items():
            r[s] = lift(T.stat(m, x, y), T.stat(allm, x, y))
        out.append(r)
    return out


def score_curve(T: Tab, a: str, b: str) -> list[dict]:
    allm = np.ones(len(T.d), dtype=bool)
    s9 = T.stat(allm, a, b)
    out = []
    for s in range(len(T.fam[0]) + 1 if len(T.fam) else 1):
        eq, ge = T.score == s, T.score >= s
        g = T.stat(ge, a, b)
        out.append({"s": s, "eq": T.stat(eq, a, b), "ge": g, "ge_lift": lift(g, s9),
                    "ge_A": T.stat(ge, a, b, "A")["p"], "ge_C": T.stat(ge, a, b, "C")["p"]})
    return out


def pick_tier(curve: list[dict], s9_p: float) -> int:
    """3.1：分數 ≥ s 的最小 s，使命中率 ≥ S9 × 1.5 且平均每週 ≥ 1 檔；沒有 → 平均每週 ≥ 1 檔裡命中率最高的 s。"""
    ok = [c for c in curve if (c["ge"]["per_week"] or 0) >= TIER["per_week"] and c["ge"]["p"] is not None]
    hit = [c for c in ok if c["ge"]["p"] >= TIER["lift"] * s9_p]
    if hit:
        return min(c["s"] for c in hit)
    return max(ok, key=lambda c: (c["ge"]["p"], -c["s"]))["s"] if ok else 0


def greedy(T: Tab, a: str, b: str, subs: dict, exclude=()) -> list[dict]:
    """3.2：一次加一個讓命中率提高最多的條件，最多 3 個；每步兩個子期間提升倍數都 ≥ 1.2、命中 ≥ 50、每週 ≥ 1 檔。"""
    allm = np.ones(len(T.d), dtype=bool)
    sub9 = {s: T.stat(allm, x, y) for s, (x, y) in subs.items()}
    cur, used, steps = allm, [], []
    cur_p = T.stat(cur, a, b)["p"]
    for _ in range(GREEDY["max_k"]):
        best = None
        for n, key in enumerate(T.keys):
            if key in used or key in exclude:
                continue
            m = cur & T.X[:, n]
            st = T.stat(m, a, b)
            if st["p"] is None or st["pos"] < GREEDY["pos"] or (st["per_week"] or 0) < GREEDY["per_week"]:
                continue
            sl = {s: lift(T.stat(m, x, y), sub9[s]) for s, (x, y) in subs.items()}
            if any(v is None or v < GREEDY["sub_lift"] for v in sl.values()):
                continue
            if best is None or st["p"] > best[1]["p"]:
                best = (key, st, sl, m)
        if best is None or best[1]["p"] <= cur_p:
            break
        key, st, sl, m = best
        used.append(key)
        cur, cur_p = m, st["p"]
        steps.append({"add": key, **st, "subs": sl})
    return steps


def pair_search(T: Tab, a: str, b: str, subs: dict, exclude=()) -> dict:
    """3.4（v2）：可選條件兩兩組合；S9 ∧ 兩個都成立，兩個子期間提升倍數都 ≥ 1.2、命中 ≥ 50、每週 ≥ 1 檔
    → 選命中率最高的一組；回傳試了幾組、符合幾組、前 10 名。"""
    allm = np.ones(len(T.d), dtype=bool)
    sub9 = {s: T.stat(allm, x, y) for s, (x, y) in subs.items()}
    s9 = T.stat(allm, a, b)
    keys = [k for k in T.keys if k not in exclude]
    tried, ok = 0, []
    for n, x in enumerate(keys):
        for y in keys[n + 1:]:
            tried += 1
            m = T.col(x) & T.col(y)
            st = T.stat(m, a, b)
            if st["p"] is None or st["pos"] < GREEDY["pos"] or (st["per_week"] or 0) < GREEDY["per_week"]:
                continue
            sl = {s: lift(T.stat(m, u, v), sub9[s]) for s, (u, v) in subs.items()}
            if any(v is None or v < GREEDY["sub_lift"] for v in sl.values()):
                continue
            ok.append({"pair": [x, y], **st, "lift": lift(st, s9), "subs": sl,
                       "new_p": T.stat(T.new_entry(m), a, b)["p"]})
    ok.sort(key=lambda r: (-r["p"], r["pair"]))
    return {"tried": tried, "passed": len(ok), "best": ok[0] if ok else None, "top": ok[:10]}


def pairs(T: Tab, single: list[dict], a: str, b: str) -> dict:
    top = [r["key"] for r in sorted((r for r in single if r["n"] >= PAIR_NMIN and r["lift"]), key=lambda r: -r["lift"])
           [:PAIR_TOP]]
    allm = np.ones(len(T.d), dtype=bool)
    s9 = T.stat(allm, a, b)
    cells = {}
    for x in top:
        for y in top:
            if x < y:
                st = T.stat(T.col(x) & T.col(y), a, b)
                cells[f"{x}|{y}"] = {**st, "lift": lift(st, s9)}
    return {"keys": top, "cells": cells}


def capture_w(eps: list, Lw: np.ndarray, W: np.ndarray, Cw: np.ndarray, early: float) -> dict:
    """W1 的「抓得早」（週名單版）：[T0 − 60 日, 高點) 之間列出過、而且列出時離高點還剩 ≥ early 的段落比例。"""
    n = hit = er = 0
    for j, t0, pk, gain, hpk in eps:
        n += 1
        a, b = np.searchsorted(W, t0 - WT.PRE), np.searchsorted(W, pk)
        ks = a + np.flatnonzero(Lw[a:b, j])
        if not len(ks):
            continue
        hit += 1
        cw = Cw[ks, j].astype(float)
        cw = cw[~np.isnan(cw)]
        if len(cw) and bool((hpk / cw - 1 >= early).any()):
            er += 1
    return {"n": n, "hit": hit, "early": er, "p_early": er / n if n else None}


def mask_weeks(T: Tab, mask: np.ndarray, shape: tuple) -> np.ndarray:
    Lw = np.zeros(shape, dtype=bool)
    Lw[T.k[mask], T.j[mask]] = True
    return Lw


def to_json(x):
    return json.loads(json.dumps(x, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def per_year(T: Tab, mask: np.ndarray, years=YEARS_VAL, lab: str = MAIN) -> dict:
    return {y: T.stat(mask, f"{y}-01-01", f"{y}-12-31", lab) for y in years}


def frac(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def isfinite(x) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))
