"""預估之後（sigspec 第 4.14 節，VER 18；docs/lab_practical_plan.md 第 10 節）。

  market(F)       一個市場的逐年紀錄（訊號 × 方向 × 年：那時看得到的成績、那一年實際的結果）
  table(recs)     衰退表：各格的筆數、市場 × 年數、平均、留下來的比例 k、k_r（截在 0～1），另列區間、前後兩段、★◆ 與其他
  research(F)     → data/lab/sigoos_research.json（scripts/run_sigoos.py）
  est(r, d)       每天建頁：研究檔的一列 → 預估之後的命中率與多賺（研究檔沒有、不在範圍＝None）
  est_x(r, d, k)  VER 21：跨期間的票（研究列 xh[k]）→ 預估之後的命中率（第 4.14 節 ⑧，只用 x 的格子）
  yearly(recs)    VER 21：每一格逐年的加總（第 4.14 節 ⑨）；ktab(yk, 年)＝只用那時已經走完的紀錄算的 k（溫度計校正用）

只呈現，不參與 ★／◆／○／— 判定；VER 21 起第 5 節 ④ 用預估之後決定今天的清單與溫度計列不列。
"""
from __future__ import annotations

import bisect
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import sigcat as G
from . import sigspec as S
from . import thermocal as TC

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "sigoos_research.json"
MARKET_CATS = ("heat", "multi", "scen", "inst", "tech", "deriv", "crash", "bub")   # 第 4.14 節的範圍（＋大跌後買點）
NB_NAMES = ("5～14 次", "15～39 次", "40 次以上")
EB_NAMES = ("比平常低", "高 0～5 點", "高 5～10 點", "高 10～20 點", "高 20 點以上")
SIGN_NAMES = {"n": "比平常低", "p": "不比平常低"}
LEVEL_NAMES = ("L1", "L2", "L3", "L1・偏多", "L2・偏多", "L3・偏多")


# ── 分格 ──────────────────────────────────────────────────────────────────────

def nb(n: int) -> int:
    """訓練次數分組（FWD_NB）：0＝5～14、1＝15～39、2＝40 以上。"""
    return bisect.bisect_right(S.FWD_NB, n)


def eb(e: float) -> int:
    """過去的優勢分組（FWD_EB）：0＝< 0、1＝0～5、2＝5～10、3＝10～20、4＝20 個百分點以上。"""
    return bisect.bisect_right(S.FWD_EB, e)


def key(d: str, H: int, b, g, x: bool = False) -> str:
    """格子的鍵：[x:]方向|看多久|次數（* ＝合併）|優勢（0～4，或 n／p＝正負）；x＝跨期間（第 4.14 節 ⑧，VER 21）。"""
    return f"{S.FWD_XP if x else ''}{d}|{H}|{'*' if b is None else b}|{g}"


def split_key(k: str) -> tuple[bool, str, int, str, str]:
    """格子的鍵 → (跨期間？, 方向, 看多久, 次數, 優勢)。"""
    x = k.startswith(S.FWD_XP)
    d, H, b, g = (k[len(S.FWD_XP):] if x else k).split("|")
    return x, d, int(H), b, g


def chain(d: str, H: int, n: int, e: float, x: bool = False) -> list[str]:
    """第 4.14 節 ③ 往上找的順序：L1 → L2 → L3（大跌後買點最後接偏多 × H_BUY 那一串）；跨期間（⑧）只找 x 的格子。"""
    b, g, sg = nb(n), eb(e), ("n" if e < 0 else "p")
    out = [key(d, H, b, g, x), key(d, H, None, g, x), key(d, H, None, sg, x)]
    if d == "buy" and not x:
        out += [key("up", S.H_BUY, b, g), key("up", S.H_BUY, None, g), key("up", S.H_BUY, None, sg)]
    return out


def _neg(k: str) -> bool:
    g = k.rsplit("|", 1)[1]
    return g in ("0", "n")


def _clip(x: float | None) -> float | None:
    return None if x is None else float(min(1.0, max(0.0, x)))


# ── ① 逐年紀錄 ────────────────────────────────────────────────────────────────

def _wmed(v: np.ndarray, w: np.ndarray | None = None) -> float | None:
    """加權中位數（第 4.11 節：由小到大排，累計權重第一次 ≥ 一半的那一個值，不內插；等權＝第 ⌈n/2⌉ 個）。"""
    v = np.asarray(v, dtype=float)
    if w is None:
        w = np.ones(len(v))
    m = np.isfinite(v)
    if not m.any():
        return None
    return G.wquant(v[m], np.asarray(w, dtype=float)[m], 0.5)


def _ra1(px, H: int) -> dict:
    return {"R": {H: G.fwd_ret(px, H)}, "A": {H: G.fwd_mae(px, H)}, "hs": (H,), "ps": ()}


def prep(sd: dict) -> dict:
    """全部資料的去重（事件型）與分段（狀態型）：之後那一年照全部資料的算法（第 4.14 節 ①）。"""
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if sd["kind"] == "event":
        ok = set(int(i) for i in samp)
        return {"kept": np.asarray(G.dedupe([t for t in sd["days"] if t in ok], sd["H"]), dtype=np.int64)}
    gap = 1 if sd.get("monthly") else S.EP_GAP
    st = np.asarray(sd["state"], dtype=bool)
    epid = np.full(len(samp), -1, dtype=np.int64)
    for j, ep in enumerate(G.episodes(np.nonzero(st)[0].tolist(), gap, sd.get("brk"))):
        epid[ep] = j
    return {"st": st, "epid": epid}


def train(sd: dict, c: int, r0: int, Yu: np.ndarray, Yw: np.ndarray, ra: dict) -> dict | None:
    """那時候看得到的成績：只用窗口在 cut 之前走完的樣本日（t＋LAG＋H < c；同 thermocal.stats_before）。
    → {"R": ev_stat／st_stat, "cell": 報酬格（ret_cell；第 2 格＝平均、第 4 格＝中位數）, "bmed": 平常的報酬中位數, "bmean": 平常的報酬平均}；
    樣本日少於 CAL_MIN_SAMP 回 None。"""
    H = sd["H"]
    samp = np.asarray(sd["samp"], dtype=np.int64)
    m = samp + S.LAG + H < c
    if int(m.sum()) < S.CAL_MIN_SAMP:
        return None
    ts = samp[m]
    if sd["kind"] == "event":
        R = G.ev_stat([t for t in sd["days"] if t + S.LAG + H < c], Yu, Yw, ts, H, r0)
        groups = [[o[0]] for o in R["occ"]]
    else:
        gap = 1 if sd.get("monthly") else S.EP_GAP
        st = np.asarray(sd["state"], dtype=bool)[m]
        brk = None if sd.get("brk") is None else np.asarray(sd["brk"], dtype=bool)[m]
        R = G.st_stat(st, ts, Yu, Yw, gap, r0, brk=brk)
        groups = [ts[ep] for ep in G.episodes(np.nonzero(st)[0].tolist(), gap, brk)]
    cell = G.ret_stats(groups, ra)["s"][0] if groups else None
    rb = ra["R"][H][ts]
    rb = rb[np.isfinite(rb)]
    return {"R": R, "cell": cell, "bmed": _wmed(rb), "bmean": float(rb.mean()) if len(rb) else None}


def test(sd: dict, P: dict, c: int, c2: int, Y: np.ndarray, Yr: np.ndarray) -> tuple | None:
    """那一年實際的結果：訊號日在 [c, c2) 的每一次（窗口走完的）。→ (命中率, 報酬平均, 次數, 平常, 平常的報酬平均)；
    這一年沒有任何一次窗口走完回 None。狀態型每一段（這一年裡的部分）一樣重。報酬用平均（VER 19；VER 18 用中位數，次數少時偏低）。"""
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if sd["kind"] == "event":
        k = P["kept"]
        tt = k[(k >= c) & (k < c2)]
        tt = tt[np.isfinite(Y[tt])]
        if not len(tt):
            return None
        r = Yr[tt]
        r = r[np.isfinite(r)]
        hit, rm, cnt = float(Y[tt].mean()), (float(r.mean()) if len(r) else None), int(len(tt))
    else:
        idx = np.nonzero((samp >= c) & (samp < c2) & P["st"])[0]
        idx = idx[np.isfinite(Y[samp[idx]])]
        if not len(idx):
            return None
        groups: dict = {}
        for i in idx:
            groups.setdefault(int(P["epid"][i]), []).append(int(samp[i]))
        gs = [np.asarray(g, dtype=np.int64) for g in groups.values()]
        hit = float(np.mean([Y[g].mean() for g in gs]))
        rs = [Yr[g][np.isfinite(Yr[g])] for g in gs]
        rs = [r for r in rs if len(r)]
        rm = float(np.mean([r.mean() for r in rs])) if rs else None            # 每一段一樣重
        cnt = len(gs)
    bs = samp[(samp >= c) & (samp < c2)]
    bs = bs[np.isfinite(Y[bs])]
    if not len(bs):
        return None
    rb = Yr[bs]
    rb = rb[np.isfinite(rb)]
    return hit, rm, cnt, float(Y[bs].mean()), (float(rb.mean()) if len(rb) else None)


def walk(mk: str, sd: dict, cuts: list, Yu: np.ndarray, Yw: np.ndarray, ra: dict, dirs: tuple, x: bool = False) -> list[dict]:
    """一個訊號的逐年紀錄（第 4.14 節 ①）：一筆＝方向 × 年（訓練次數 ≥ N_MIN、那一年至少一次窗口走完）。
    x＝跨期間（⑧）：sd 的 H 已換成那支溫度計的看多久，紀錄標 "x"。"""
    P = prep(sd)
    Yr = ra["R"][sd["H"]]
    cost = S.ABS_COST[mk]
    out = []
    for yr, c, c2, r0 in cuts:
        Tn = None
        for d in dirs:
            te = test(sd, P, c, c2, Yw if d == "warn" else Yu, Yr)
            if te is None:
                continue
            if Tn is None:
                Tn = train(sd, c, r0, Yu, Yw, ra) or False
            if Tn is False:
                break
            st = Tn["R"]["warn" if d == "warn" else "up"]
            n, hit, base = st["n"], st["hit"], st["base"]
            if n < S.N_MIN or hit is None or base is None:
                continue
            rec = {"mk": mk, "id": sd["id"], "d": d, "H": int(sd["H"]), "yr": int(yr), "n": int(n),
                   "e": float(hit - base), "o": float(te[0] - te[3]), "tn": te[2],
                   "tier": G.tier_abs(st, d, Tn["cell"], cost)}
            if x:
                rec["x"] = 1
            cell = Tn["cell"]
            if d != "warn" and cell and cell[1] is not None and Tn["bmean"] is not None and te[1] is not None and te[4] is not None:
                rec["er"] = float(cell[1] - Tn["bmean"])             # VER 19：過去多賺、之後多賺都用平均
                rec["or"] = float(te[1] - te[4])
            out.append(rec)
    return out


def cuts_for(cal: list[str]) -> list[tuple]:
    """每年 1 月 1 日（thermocal.first_year 起到資料最後一年）：(年, cut, 下一個 cut, 近 10 年起點)。"""
    y0, y1 = TC.first_year(cal), int(cal[-1][:4])
    return [(yr, bisect.bisect_left(cal, f"{yr}-01-01"), bisect.bisect_left(cal, f"{yr + 1}-01-01"),
             bisect.bisect_left(cal, f"{yr - S.RECENT_YEARS}-01-01")) for yr in range(y0, y1 + 1)]


def market(F: dict) -> list[dict]:
    """一個市場：signals(F) 的每一個訊號（偏多、警示）＋大跌後買點（買點）的逐年紀錄。"""
    mk, cal, px = F["mk"], F["cal"], F["px"]
    cuts = cuts_for(cal)
    Yc: dict = {}
    out = []
    for sd in G.signals(F):
        if sd["cat"] not in MARKET_CATS:
            continue
        H = sd["H"]
        for Hx in [H] + (sorted(set(S.THERMO_H.values()) - {H}) if sd["cat"] in S.THERMO_X_CATS else []):
            if Hx not in Yc:
                Yc[Hx] = (G.outcomes(px, Hx, G.warn_th(mk, Hx)), _ra1(px, Hx))
            (Yu, Yw, _), ra = Yc[Hx]
            if Hx == H:
                out += walk(mk, sd, cuts, Yu, Yw, ra, ("up", "warn"))
            else:                                      # VER 21 ⑧：跨期間（同 sigcat.cross_stats，H 換成那支溫度計的看多久）
                out += walk(mk, {**sd, "H": Hx}, cuts, Yu, Yw, ra, ("up", "warn"), x=True)
    I, bsd = G.buy_signals(F)
    if I is not None:
        H = S.H_BUY
        Yu, Yw, _ = G.outcomes(I["px"], H, G.warn_th(mk, H))
        ra = _ra1(I["px"], H)
        bc = cuts_for(I["cal"])
        for sd in bsd:
            out += walk(mk, sd, bc, Yu, Yw, ra, ("buy",))
    return out


# ── ② ③ 衰退表 ────────────────────────────────────────────────────────────────

def _ratio(o: np.ndarray, e: np.ndarray) -> float | None:
    s = float(e.sum())
    return None if not len(e) or s == 0 else float(o.sum()) / s


def _boot(rs: list[dict], fo: str, fe: str, rng: np.random.Generator) -> list | None:
    """以市場 × 年為一塊重抽 FWD_DRAWS 次的 Σo ÷ Σe（沒有截）的 95% 區間（第 4.14 節 ⑥，只描述）。"""
    by: dict = defaultdict(lambda: [0.0, 0.0])
    for r in rs:
        x = by[(r["mk"], r["yr"])]
        x[0] += r[fo]
        x[1] += r[fe]
    if len(by) < 2:
        return None
    A = np.asarray(list(by.values()), dtype=float)
    idx = rng.integers(0, len(A), size=(S.FWD_DRAWS, len(A)))
    so, se = A[idx, 0].sum(axis=1), A[idx, 1].sum(axis=1)
    ok = se != 0
    if not ok.any():
        return None
    v = so[ok] / se[ok]
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def cell(rs: list[dict], k: str, rng: np.random.Generator) -> dict:
    """一格（第 4.14 節 ②③⑥）：筆數、市場 × 年數、平均、k、k_r（算不出＝None；截在 0～1）與另列的描述。"""
    neg = _neg(k)
    e = np.asarray([r["e"] for r in rs], dtype=float)
    o = np.asarray([r["o"] for r in rs], dtype=float)
    rr = [r for r in rs if "er" in r]
    er = np.asarray([r["er"] for r in rr], dtype=float)
    orr = np.asarray([r["or"] for r in rr], dtype=float)
    ncl = len({(r["mk"], r["yr"]) for r in rs})
    nclr = len({(r["mk"], r["yr"]) for r in rr})

    def ok(n, nc, m, eps):
        return n >= S.FWD_MIN_N and nc >= S.FWD_MIN_CL and m is not None and ((m <= -eps) if neg else (m >= eps))

    me = float(e.mean()) if len(e) else None
    mer = float(er.mean()) if len(er) else None
    kraw, krraw = _ratio(o, e), _ratio(orr, er)
    out = {"n": len(rs), "ncl": ncl, "e": me, "o": float(o.mean()) if len(o) else None,
           "kraw": kraw, "k": _clip(kraw) if ok(len(rs), ncl, me, S.FWD_EPS) else None,
           "nr": len(rr), "nclr": nclr, "er": mer, "or": float(orr.mean()) if len(orr) else None,
           "krraw": krraw, "kr": _clip(krraw) if ok(len(rr), nclr, mer, S.FWD_EPS_R) else None,
           "ci": _boot(rs, "o", "e", rng), "cir": _boot(rr, "or", "er", rng) if rr else None}
    star = [r for r in rs if r["tier"] in ("good", "rare")]
    rest = [r for r in rs if r["tier"] not in ("good", "rare")]
    out["gs"] = {g: [len(x), float(np.mean([r["o"] for r in x])) if x else None,
                     float(np.mean([r["e"] for r in x])) if x else None] for g, x in (("star", star), ("other", rest))}
    sp = {}
    for nm, x in (("a", [r for r in rs if r["yr"] < S.FWD_SPLIT]), ("b", [r for r in rs if r["yr"] >= S.FWD_SPLIT])):
        sp[nm] = [len(x), _ratio(np.asarray([r["o"] for r in x], float), np.asarray([r["e"] for r in x], float)) if x else None]
    out["split"] = sp
    return out


def table(recs: list[dict]) -> dict:
    """衰退表：每一筆紀錄放進它自己那一串的 L1、L2、L3（大跌後買點的偏多那一串不放：偏多的格子只用偏多的紀錄）。
    格子依鍵排序、一個亂數產生器（FWD_SEED）依序重抽。"""
    agg: dict = defaultdict(list)
    for r in recs:
        for k in chain(r["d"], r["H"], r["n"], r["e"], bool(r.get("x")))[:3]:
            agg[k].append(r)
    rng = np.random.default_rng(S.FWD_SEED)
    return {k: cell(agg[k], k, rng) for k in sorted(agg)}


def by_market(recs: list[dict]) -> dict:
    """各市場的 L3（方向 × 看多久 × 優勢 ≥ 0）k（第 4.14 節 ⑥，只描述）→ {市場: {鍵: [筆數, k（沒有截）]}}。"""
    agg: dict = defaultdict(list)
    for r in recs:
        if r["e"] >= 0 and not r.get("x"):                     # VER 21：跨期間的紀錄不算（第 4.14 節 ⑧）
            agg[(r["mk"], key(r["d"], r["H"], None, "p"))].append(r)
    out: dict = {}
    for (mk, k), rs in sorted(agg.items()):
        out.setdefault(mk, {})[k] = [len(rs), _ratio(np.asarray([r["o"] for r in rs], float), np.asarray([r["e"] for r in rs], float))]
    return out


def own(recs: list[dict]) -> dict:
    """每個訊號自己的逐年樣本外（第 4.14 節 ⑤）→ {訊號: {方向: [年數, e, o, e_r, o_r 的平均]}}。"""
    agg: dict = defaultdict(list)
    for r in recs:
        if not r.get("x"):                                     # VER 21：跨期間的紀錄不算（第 4.14 節 ⑧）
            agg[(r["id"], r["d"])].append(r)
    out: dict = {}
    for (sid, d), rs in sorted(agg.items()):
        rr = [r for r in rs if "er" in r]
        out.setdefault(sid, {})[d] = [len(rs), float(np.mean([r["e"] for r in rs])), float(np.mean([r["o"] for r in rs])),
                                     float(np.mean([r["er"] for r in rr])) if rr else None,
                                     float(np.mean([r["or"] for r in rr])) if rr else None]
    return out


def yearly(recs: list[dict]) -> dict:
    """第 4.14 節 ⑨（VER 21）：每一格（含 x）、每一年（之後那一年）→ [筆數, 那一年有紀錄的市場數, Σe, Σo]（溫度計校正用）。"""
    agg: dict = defaultdict(dict)
    for r in recs:
        for k in chain(r["d"], r["H"], r["n"], r["e"], bool(r.get("x")))[:3]:
            a = agg[k].setdefault(r["yr"], [0, set(), 0.0, 0.0])
            a[0] += 1
            a[1].add(r["mk"])
            a[2] += r["e"]
            a[3] += r["o"]
    return {k: {str(y): [a[0], len(a[1]), round(a[2], 6), round(a[3], 6)] for y, a in sorted(v.items())}
            for k, v in sorted(agg.items())}


def ktab(yk: dict, year: int) -> dict:
    """第 5 節 ③d（VER 21）：只用之後那一年 ≤ year − CAL_K_LAG[看多久] 的紀錄算的留下來的比例（條件同第 4.14 節 ③，只算命中率）
    → {鍵: {"k": k 或 None}}；給 lookup 用（kr 找不到＝用 k）。"""
    out = {}
    for k, ys in yk.items():
        H = split_key(k)[2]
        upto = year - S.CAL_K_LAG[H]
        n = ncl = 0
        se = so = 0.0
        for y, a in ys.items():
            if int(y) <= upto:
                n += a[0]
                ncl += a[1]
                se += a[2]
                so += a[3]
        me = se / n if n else None
        ok = (n >= S.FWD_MIN_N and ncl >= S.FWD_MIN_CL and me is not None
              and ((me <= -S.FWD_EPS) if _neg(k) else (me >= S.FWD_EPS)) and se != 0)
        out[k] = {"k": _clip(so / se) if ok else None}
    return out


# ── 研究檔 ────────────────────────────────────────────────────────────────────

def research(F: dict | None = None, recs: list[dict] | None = None) -> dict:
    if recs is None:
        F = F if F is not None else G.frames()
        recs = []
        for mk in S.MARKETS:
            if mk in F:
                recs += market(F[mk])
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": {mk: F[mk]["cal"][-1] for mk in F} if F else {}, "nrec": len(recs),
            "nrec_x": sum(1 for r in recs if r.get("x")),
            "cells": G._r(table(recs)), "mk": G._r(by_market(recs)), "own": G._r(own(recs)), "yk": yearly(recs)}


def save(R: dict, path: Path | None = None) -> None:
    path = OUT if path is None else path
    path.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


_CACHE: dict = {}


def load(path: Path | None = None) -> dict | None:
    path = OUT if path is None else path
    if path not in _CACHE:
        try:
            R = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            R = None
        _CACHE[path] = R if R and (R.get("ver") or 0) >= S.FWD_VER else None
    return _CACHE[path]


# ── ④ 每個訊號的預估之後 ──────────────────────────────────────────────────────

def lookup(cells: dict, d: str, H: int, n: int, e: float, x: bool = False) -> dict:
    """第 4.14 節 ③：k、k_r 各自照順序往上找第一個算得出的格子。→ {"k", "lv", "key", "kr", "lvr", "keyr"}（lv＝LEVEL_NAMES 的位置；
    k 都找不到＝0、lv None；k_r 都找不到＝用 k、lvr None）。x＝跨期間（⑧：只找 x 的格子）。"""
    ch = chain(d, H, n, e, x)
    out = {"k": 0.0, "lv": None, "key": None, "kr": None, "lvr": None, "keyr": None}
    for i, k in enumerate(ch):
        c = cells.get(k)
        if c and c.get("k") is not None:
            out.update(k=c["k"], lv=i, key=k)
            break
    for i, k in enumerate(ch):
        c = cells.get(k)
        if c and c.get("kr") is not None:
            out.update(kr=c["kr"], lvr=i, keyr=k)
            break
    if out["kr"] is None:
        out["kr"] = out["k"]
    return out


def _bmed(r: dict) -> float | None:
    """這個訊號自己看多久那一期，平常的報酬中位數（研究檔 bases）。"""
    q = r.get("ret") or {}
    b = G.research_bases().get(q.get("bk") or "")
    if not b or r.get("H") not in S.RET_H:
        return None
    s = (b.get("s") or [])
    i = S.RET_H.index(r["H"])
    c = s[i] if i < len(s) else None
    return None if not c or len(c) < 4 else c[3]


def est(r: dict, d: str, T: dict | None = None) -> dict | None:
    """第 4.14 節 ④：研究檔的一列、一個方向 → {"hit": 過去, "base": 平常, "fh": 預估之後的命中率, "k", "lv", "key",
    （偏多與買點）"med", "bmed", "ex": 過去多賺, "fx": 預估之後多賺, "fm": 預估之後的報酬中位數, "kr", "lvr",
    "own": [年數, e, o, e_r, o_r]}；研究檔沒有、不在範圍、次數 < N_MIN 回 None。"""
    T = load() if T is None else T
    if not T or r.get("cat") not in MARKET_CATS + ("buy",) or r.get("mk") not in S.MARKETS:
        return None
    st = r.get(d) or {}
    n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
    if n < S.N_MIN or hit is None or base is None:
        return None
    L = lookup(T.get("cells") or {}, d, int(r["H"]), int(n), float(hit - base))
    out = {"hit": hit, "base": base, "fh": base + L["k"] * (hit - base), "k": L["k"], "lv": L["lv"], "key": L["key"],
           "own": ((T.get("own") or {}).get(r["id"]) or {}).get(d)}
    if d != "warn":
        c = G.ret_at(r.get("ret"), int(r["H"]))
        med, bm = (c[3] if c and len(c) > 3 else None), _bmed(r)
        if med is not None and bm is not None:
            fx = L["kr"] * (med - bm)
            out.update(med=med, bmed=bm, ex=med - bm, fx=fx, fm=bm + fx, kr=L["kr"], lvr=L["lvr"], keyr=L["keyr"])
    return out


def est_x(r: dict, d: str, k: str, T: dict | None = None) -> dict | None:
    """第 4.14 節 ⑧（VER 21）：跨期間的票——研究列 xh[k]（溫度計 k 的看多久）的次數、命中率、平常 → x 的格子找 k →
    {"hit", "base", "fh": 預估之後的命中率, "k", "lv", "key", "H"}；研究檔沒有、不在範圍、次數 < N_MIN 回 None。只估命中率。"""
    T = load() if T is None else T
    X = (r.get("xh") or {}).get(k)
    if not T or not X or r.get("cat") not in S.THERMO_X_CATS or r.get("mk") not in S.MARKETS:
        return None
    st = X.get(d) or {}
    n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
    if n < S.N_MIN or hit is None or base is None:
        return None
    L = lookup(T.get("cells") or {}, d, int(X["H"]), int(n), float(hit - base), x=True)
    return {"hit": hit, "base": base, "fh": base + L["k"] * (hit - base), "k": L["k"], "lv": L["lv"], "key": L["key"],
            "H": int(X["H"])}
