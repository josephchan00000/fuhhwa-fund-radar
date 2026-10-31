"""今天的訊號「第幾天進場」的格子（sigspec VER 26 第 5.1 節；docs/lab_signal_listing_plan.md）。

  cond(F, sd)          事件型的觸發條件逐日（AGE_COND；沒有條件＝None）
  days(sd, T, H, cx)   這個訊號在看 H 天的溫度計現在有效的每一天：第幾天、哪一格、算哪一次、是不是樣本日
  buy_days(I, sd, mk)  大跌後買點的同一件事（那一段大跌還在進行、出現後 H_BUY 天內才算）
  table(...)           全部資料的每一格：次數、天數、命中率、漲跌中位數、最大跌幅最差一次
  Prefix               逐年：cut 之前走完的每一格（③d 的票、之後也成立的訓練）與那一年的結果
  research(F)          → data/lab/sigage_research.json（scripts/run_sigage.py）
  load()、cell()、est()  每天建頁：今天那一格、之後也成立

格子只用來決定今天列不列（第 5 節 ④c），每個訊號自己的成績與判定不變（sig_research.json）。
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import sigcat as G
from . import sigoos as O
from . import sigspec as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "sigage_research.json"
NC = len(S.AGE_B) * 3                      # 格的編號＝分段 × 3 ＋ 條件（0 成立、1 已斷、2 不分）
CK = "ox-"                                 # 格的鍵：分段的位置＋這一個字（例 "2x"＝5～9 天、條件已斷）


def bucket(k):
    """第幾天 → 分段的位置（AGE_B）。"""
    return np.searchsorted(S.AGE_B, k, side="right") - 1


def ckey(cid: int) -> str:
    return f"{cid // 3}{CK[cid % 3]}"


def cid_of(ck: str) -> int:
    return int(ck[:-1]) * 3 + CK.index(ck[-1])


def ck_now(k: int, st: str) -> str:
    """今天：第幾天、條件（"on"／"off"／"-"）→ 格的鍵。"""
    return ckey(int(bucket(int(k))) * 3 + S.AGE_ST.index(st))


# ── 觸發條件（事件型） ──────────────────────────────────────────────────────────

def cond_kind(sd: dict) -> str | None:
    key = f"tech:{sd.get('var')}" if sd.get("cat") == "tech" else f"{sd.get('cat')}:{sd.get('sig')}"
    return S.AGE_COND.get(key)


def _ffill(c: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """沒有讀數的日子照最近一個有讀數的那天（第一個讀數之前＝False）。"""
    i = np.maximum.accumulate(np.where(ok, np.arange(len(c)), -1))
    return np.where(i >= 0, c[np.maximum(i, 0)], False)


def _sides(px: np.ndarray) -> dict:
    """heattech.all_events 用的逐日狀態（+1／−1／0；算不出＝NaN）：收盤對月線、季線、年線，月線對季線，季線對前一天。"""
    from . import heattech as TT
    M = {n: np.array([np.nan if v is None else v for v in TT.mas([None if np.isnan(p) else float(p) for p in px])[n]],
                     dtype=float) for n in (20, 60, 240)}
    s60 = np.concatenate([[np.nan], M[60][1:] - M[60][:-1]])
    return {"ma20": np.sign(px - M[20]), "ma60": np.sign(px - M[60]), "ma240": np.sign(px - M[240]),
            "x": np.sign(M[20] - M[60]), "s60": np.sign(s60)}


def cond(F: dict, sd: dict, cache: dict | None = None) -> np.ndarray | None:
    """第 5.1 節 AGE_COND：每一天觸發條件還成立＝True（沒有讀數的日子照最近一個有讀數的那天）；不在 AGE_COND＝None。"""
    kind = cond_kind(sd)
    if kind is None:
        return None
    cache = {} if cache is None else cache
    T = len(F["cal"])
    if kind in ("ge_hot", "lt_cold"):
        src = {"heat": F.get("vars"), "crash": F.get("cvars"), "bd": F.get("bvars"), "inst": F.get("ivars")}[sd["cat"]] or []
        xs = [v["x"] for v in src if v.get("key") == sd.get("var")]
        if not xs:                                        # 找不到變數（例：測試的假訊號）＝不分條件
            return None
        x = np.asarray(xs[0], dtype=float)
        ok = ~np.isnan(x)
        xx = np.nan_to_num(x, nan=50.0)
        return _ffill(xx >= S.HOT if kind == "ge_hot" else xx < S.COLD, ok)
    if kind == "multi":
        if not F.get("dims"):
            return None
        hot = np.zeros(T, dtype=int)
        have = np.zeros(T, dtype=int)
        for d in F["dims"]:
            c = np.asarray(F["comp"][d], dtype=float)
            hot += (~np.isnan(c) & (np.nan_to_num(c, nan=-1) >= S.HOT)).astype(int)
            have += (~np.isnan(c)).astype(int)
        return _ffill(hot >= S.MULTI_K, have >= S.MULTI_MIN_DIMS)
    if kind == "run":
        xs = [v["amt"] for v in F.get("ivars") or [] if v.get("key") == sd.get("var")]
        if not xs:
            return None
        amt = np.asarray(xs[0], dtype=float)
        sign = -1 if sd["sig"].startswith("sell") else 1
        n = int(sd["sig"].rsplit("run", 1)[1])
        ok = ~np.isnan(amt)
        good = ok & (np.nan_to_num(amt) * sign > 0)
        run = np.zeros(T, dtype=int)
        c = 0
        for t in range(T):
            c = c + 1 if good[t] else 0
            run[t] = c
        return _ffill(run >= n, ok)
    if F.get("px") is None:
        return None
    if "sides" not in cache:
        cache["sides"] = _sides(np.asarray(F["px"], dtype=float))
    v = sd["var"]
    s = cache["sides"]["x" if v.startswith("x_") else v.rsplit("_", 1)[0]]
    want = -1 if (v.endswith("_dn") or v == "x_dead") else 1
    return _ffill(s == want, ~np.isnan(s))


# ── 現在有效的每一天 ──────────────────────────────────────────────────────────

def _empty() -> dict:
    z = np.zeros(0, dtype=np.int64)
    return {"t": z, "k": z, "cid": z, "cl": z, "s": np.zeros(0, dtype=bool)}


def days(sd: dict, T: int, H: int, cx: np.ndarray | None = None) -> dict:
    """這個訊號在看 H 天的溫度計（第 5 節；VER 20 相反的讀數就失效；同 thermocal.active）現在有效的每一天 →
    {"t": 日子（遞增）, "k": 第幾天, "cid": 格, "cl": 算哪一次（事件＝去重後的一次、狀態＝一段；−1 不算）, "s": 是不是樣本日}。
    事件型：第幾天＝那天 − 最近一次出現；狀態型：那天 − 這一段第一天（月資料＝月底那一天，到下一個月底前都算同一格）。"""
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if not len(samp):
        return _empty()
    smask = np.zeros(T, dtype=bool)
    smask[samp] = True
    if sd["kind"] == "state":
        st = np.asarray(sd["state"], dtype=bool)
        mon = bool(sd.get("monthly"))
        gap = 1 if mon else S.EP_GAP
        nxt = np.concatenate([samp[1:], [T]])
        ts, ks, cls = [], [], []
        for j, ep in enumerate(G.episodes(np.nonzero(st)[0].tolist(), gap, sd.get("brk"))):
            ep = np.asarray(ep, dtype=np.int64)
            k0 = samp[ep] - samp[ep[0]]
            if mon:
                for p, kk in zip(ep.tolist(), k0.tolist()):
                    r = np.arange(samp[p], nxt[p], dtype=np.int64)
                    ts.append(r)
                    ks.append(np.full(len(r), kk, dtype=np.int64))
                    cls.append(np.full(len(r), j, dtype=np.int64))
            else:
                ts.append(samp[ep])
                ks.append(k0)
                cls.append(np.full(len(ep), j, dtype=np.int64))
        if not ts:
            return _empty()
        t, k, cl = np.concatenate(ts), np.concatenate(ks), np.concatenate(cls)
        return {"t": t, "k": k, "cid": bucket(k) * 3 + 2, "cl": cl, "s": smask[t]}
    D = np.asarray(sorted(int(x) for x in sd["days"] if x >= samp[0]), dtype=np.int64)
    if not len(D):
        return _empty()
    end = G.exp_end(sd, D, H)
    tt = np.arange(D[0], T, dtype=np.int64)
    j = np.searchsorted(D, tt, side="right") - 1
    act = tt < end[j]
    t, j = tt[act], j[act]
    k = t - D[j]
    kept = np.asarray(G.dedupe([int(x) for x in D if smask[x]], H), dtype=np.int64)
    cl = np.searchsorted(kept, D[j], side="right") - 1
    if cx is None:
        stc = np.full(len(t), 2, dtype=np.int64)
    else:
        stc = np.where(cx[t], 0, 1).astype(np.int64)
        stc[k == 0] = 0                                   # 第 0 天一定成立
    return {"t": t, "k": k, "cid": bucket(k) * 3 + stc, "cl": cl, "s": smask[t]}


def buy_days(I: dict, sd: dict, mk: str) -> dict:
    """大跌後買點（sigcat.buy_signals 的一條規則）：訊號日（買進日 − LAG）起 H_BUY 個交易日內、而且那一段大跌還在進行
    （bottom.now：5 日急跌＝那一次還是最近一次、在 SIG_WIN 個交易日內；從 60 日高點跌 10%＝那一段還沒結束）的每一天。"""
    from . import bottom as BO
    from . import bottomspec as BS
    px = np.asarray(I["px"], dtype=float)
    T = len(px)
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if not sd["buys"] or not len(samp):
        return _empty()
    if sd["ev"] == "E5":
        e5 = BO.events_e5(px, BS.E5_TH[mk])
        nxt = {a: (e5[i + 1] if i + 1 < len(e5) else T) for i, a in enumerate(e5)}
        alive = {a: min(a + BS.SIG_WIN + 1, nxt[a]) for a in e5}
    else:
        alive = {a: (T if z is None else z) for a, z in BO.e10_segments(px)}
    pairs = sorted((b - S.LAG, alive.get(te, te)) for te, b, _, _ in sd["buys"])
    D = np.asarray([p[0] for p in pairs], dtype=np.int64)
    end = np.minimum(D + S.H_BUY, np.asarray([p[1] for p in pairs], dtype=np.int64))
    smask = np.zeros(T, dtype=bool)
    smask[samp] = True
    tt = np.arange(D[0], T, dtype=np.int64)
    j = np.searchsorted(D, tt, side="right") - 1
    act = tt < end[j]
    t, j = tt[act], j[act]
    k = t - D[j]
    kept = np.asarray(G.dedupe([int(x) for x in D if smask[x]], S.H_BUY), dtype=np.int64)
    cl = np.searchsorted(kept, D[j], side="right") - 1
    return {"t": t, "k": k, "cid": bucket(k) * 3 + 2, "cl": cl, "s": smask[t]}


# ── 每一格的成績 ──────────────────────────────────────────────────────────────

def _base(Y: np.ndarray, samp: np.ndarray) -> float | None:
    v = Y[samp]
    v = v[np.isfinite(v)]
    return float(v.mean()) if len(v) else None


def table(Dd: dict, Yu: np.ndarray, Yw: np.ndarray, Yr: np.ndarray, Yd: np.ndarray, samp: np.ndarray, cal: list) -> dict:
    """全部資料（第 5.1 節）：{"b": [平常偏多, 平常警示, 平常漲跌中位數], "c": {格: [次數, 天數, 偏多, 警示, 漲跌中位數,
    最大跌幅最差一次, 那一天]}}；樣本日、窗口完整、算得到哪一次的日子才算，每一天一樣重。"""
    t = Dd["t"]
    sel = Dd["s"] & np.isfinite(Yu[t]) & np.isfinite(Yw[t]) & (Dd["cl"] >= 0)
    t, cid, cl = t[sel], Dd["cid"][sel], Dd["cl"][sel]
    rb = Yr[samp]
    rb = rb[np.isfinite(rb)]
    out = {"b": [_base(Yu, samp), _base(Yw, samp), float(np.median(rb)) if len(rb) else None], "c": {}}
    for c in np.unique(cid).tolist():
        m = cid == c
        tc = t[m]
        r = Yr[tc]
        r = r[np.isfinite(r)]
        w = G.worst_dd(Yd[tc], tc, cal)
        out["c"][ckey(int(c))] = [int(len(np.unique(cl[m]))), int(m.sum()), float(Yu[tc].mean()), float(Yw[tc].mean()),
                                  float(np.median(r)) if len(r) else None, w[0] if w else None, w[1] if w else None]
    return out


class Prefix:
    """逐年（第 5.1 節 ③d、之後也成立）：樣本日、窗口完整的日子依日期排好，at(cut)＝窗口在 cut 之前走完的
    （t＋LAG＋H < cut）每一格與平常；year(c, c2)＝訊號日在 [c, c2) 的每一格與那一年的平常。"""

    def __init__(self, Dd: dict, Yu: np.ndarray, Yw: np.ndarray, samp: np.ndarray, H: int):
        t = Dd["t"]
        sel = Dd["s"] & np.isfinite(Yu[t]) & np.isfinite(Yw[t]) & (Dd["cl"] >= 0)
        self.t, self.cid, cl = t[sel], Dd["cid"][sel], Dd["cl"][sel]
        self.yu, self.yw = Yu[self.t], Yw[self.t]
        pair = self.cid * (int(cl.max()) + 1 if len(cl) else 1) + cl
        _, first = np.unique(pair, return_index=True)
        self.pf, self.pc = first, self.cid[first]                 # 每一次（格 × 哪一次）第一天的位置
        self.samp = np.asarray(samp, dtype=np.int64)
        ok = np.isfinite(Yu[self.samp]) & np.isfinite(Yw[self.samp])
        self.bt = self.samp[ok]
        self.cu = np.concatenate([[0.0], np.cumsum(Yu[self.bt])])
        self.cw = np.concatenate([[0.0], np.cumsum(Yw[self.bt])])
        self.H = int(H)

    def _cells(self, a: int, b: int) -> tuple:
        cid = self.cid[a:b]
        m = np.bincount(cid, minlength=NC).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            hu = np.bincount(cid, self.yu[a:b], minlength=NC) / m
            hw = np.bincount(cid, self.yw[a:b], minlength=NC) / m
        return m, hu, hw

    def at(self, cut: int) -> dict | None:
        lim = cut - S.LAG - self.H
        if int(np.searchsorted(self.samp, lim, side="left")) < S.CAL_MIN_SAMP:
            return None
        q = int(np.searchsorted(self.bt, lim, side="left"))
        if not q:
            return None
        p = int(np.searchsorted(self.t, lim, side="left"))
        m, hu, hw = self._cells(0, p)
        n = np.bincount(self.pc[self.pf < p], minlength=NC)
        return {"n": n, "m": m, "up": hu, "warn": hw, "bu": self.cu[q] / q, "bw": self.cw[q] / q}

    def year(self, c: int, c2: int) -> dict | None:
        a, b = int(np.searchsorted(self.t, c, side="left")), int(np.searchsorted(self.t, c2, side="left"))
        qa, qb = int(np.searchsorted(self.bt, c, side="left")), int(np.searchsorted(self.bt, c2, side="left"))
        if a == b or qa == qb:
            return None
        m, hu, hw = self._cells(a, b)
        q = qb - qa
        return {"m": m, "up": hu, "warn": hw, "bu": (self.cu[qb] - self.cu[qa]) / q, "bw": (self.cw[qb] - self.cw[qa]) / q}


def passes(P: dict | None, d: str) -> np.ndarray:
    """at(cut) 的每一格這一邊會不會列（次數 ≥ N_MIN、命中率 − 平常 ≥ THERMO_EDGE）；None＝都不會。"""
    if P is None:
        return np.zeros(NC, dtype=bool)
    h = P["warn" if d == "warn" else "up"]
    b = P["bw" if d == "warn" else "bu"]
    with np.errstate(invalid="ignore"):
        return (P["n"] >= S.N_MIN) & np.isfinite(h) & (h - b >= S.THERMO_EDGE)


# ── 之後也成立的格子（第 5.1 節：第 4.14 節 ①～③ 的作法，鍵前面加 AGE_XP） ───────────────────

def chain(p: str, d: str, H: int, n: int, e: float) -> list[str]:
    b, g, sg = O.nb(n), O.eb(e), ("n" if e < 0 else "p")
    out = [f"{p}{d}|{H}|{b}|{g}", f"{p}{d}|{H}|*|{g}", f"{p}{d}|{H}|*|{sg}"]
    if d == "buy":
        out += [f"{p}up|{S.H_BUY}|{b}|{g}", f"{p}up|{S.H_BUY}|*|{g}", f"{p}up|{S.H_BUY}|*|{sg}"]
    return out


def walk(agg: dict, mk: str, Pf: Prefix, cuts: list, dirs: tuple, p: str) -> int:
    """一個訊號、一支溫度計的逐年紀錄（一筆＝格 × 方向 × 年：訓練次數 ≥ N_MIN、那一年這一格至少一天）→ 加進 agg
    （{鍵: {(市場, 年): [筆數, Σe, Σo]}}，只放自己那一串的前三個鍵，同 sigoos.table）。回傳筆數。"""
    nrec = 0
    for yr, c, c2, _ in cuts:
        tr = Pf.at(c)
        if tr is None:
            continue
        te = Pf.year(c, c2)
        if te is None:
            continue
        ok = (tr["n"] >= S.N_MIN) & (te["m"] > 0)
        for cid in np.nonzero(ok)[0].tolist():
            for d in dirs:
                w = "warn" if d == "warn" else "up"
                e = float(tr[w][cid] - tr["bw" if w == "warn" else "bu"])
                o = float(te[w][cid] - te["bw" if w == "warn" else "bu"])
                for k in chain(p, d, Pf.H, int(tr["n"][cid]), e)[:3]:
                    a = agg[k].setdefault((mk, int(yr)), [0, 0.0, 0.0])
                    a[0] += 1
                    a[1] += e
                    a[2] += o
                nrec += 1
    return nrec


def grid(agg: dict) -> dict:
    """每一格（同第 4.14 節 ②③⑥）：筆數、市場 × 年數、平均、k（算得出才有；截在 0～1）、市場 × 年為一塊重抽的 95% 區間（只描述）。"""
    rng = np.random.default_rng(S.FWD_SEED)
    out = {}
    for key in sorted(agg):
        A = np.asarray(list(agg[key].values()), dtype=float)
        n, se, so = int(A[:, 0].sum()), float(A[:, 1].sum()), float(A[:, 2].sum())
        me = se / n if n else None
        neg = key.rsplit("|", 1)[1] in ("0", "n")
        ok = n >= S.FWD_MIN_N and len(A) >= S.FWD_MIN_CL and me is not None and ((me <= -S.FWD_EPS) if neg else (me >= S.FWD_EPS))
        kraw = so / se if se else None
        ci = None
        if len(A) >= 2:
            idx = rng.integers(0, len(A), size=(S.FWD_DRAWS, len(A)))
            ss, oo = A[idx, 1].sum(axis=1), A[idx, 2].sum(axis=1)
            v = oo[ss != 0] / ss[ss != 0]
            ci = [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if len(v) else None
        out[key] = {"n": n, "ncl": len(A), "e": me, "o": so / n if n else None, "kraw": kraw,
                    "k": float(min(1.0, max(0.0, kraw))) if ok and kraw is not None else None, "ci": ci}
    return out


# ── 研究 ──────────────────────────────────────────────────────────────────────

def market(F: dict, agg: dict) -> tuple[dict, int, int]:
    """一個市場：每個市場層級訊號 × 三支溫度計、每條大跌後買點的全部資料格子；逐年紀錄加進 agg。→ (列, 筆數, 跨期間筆數)。"""
    mk, cal, px = F["mk"], F["cal"], F["px"]
    T = len(cal)
    cuts = O.cuts_for(cal)
    Y: dict = {}
    cache: dict = {}
    rows: dict = {}
    nrec = nx = 0
    for sd in G.signals(F):
        if sd["cat"] not in O.MARKET_CATS:
            continue
        cx = cond(F, sd, cache)
        samp = np.asarray(sd["samp"], dtype=np.int64)
        for hz, H in S.THERMO_H.items():
            x = H != sd["H"]
            if x and sd["cat"] not in S.THERMO_X_CATS:
                continue
            if H not in Y:
                Y[H] = (*G.outcomes(px, H, G.warn_th(mk, H)), G.fwd_ret(px, H))
            Yu, Yw, Yd, Yr = Y[H]
            Dd = days(sd, T, H, cx)
            rows.setdefault(sd["id"], {})[hz] = {"H": H, **table(Dd, Yu, Yw, Yr, Yd, samp, cal)}
            c = walk(agg, mk, Prefix(Dd, Yu, Yw, samp, H), cuts, ("up", "warn"), S.AGE_XP[1 if x else 0])
            nrec += c
            nx += c if x else 0
    I, bsd = G.buy_signals(F)
    if I is not None:
        H = S.H_BUY
        bpx = np.asarray(I["px"], dtype=float)
        Yu, Yw, Yd = G.outcomes(bpx, H, G.warn_th(mk, H))
        Yr = G.fwd_ret(bpx, H)
        bc = O.cuts_for(I["cal"])
        for sd in bsd:
            Dd = buy_days(I, sd, mk)
            samp = np.asarray(sd["samp"], dtype=np.int64)
            rows.setdefault(sd["id"], {})["mid"] = {"H": H, **table(Dd, Yu, Yw, Yr, Yd, samp, list(I["cal"]))}
            nrec += walk(agg, mk, Prefix(Dd, Yu, Yw, samp, H), bc, ("buy",), S.AGE_XP[0])
    return rows, nrec, nx


def research(F: dict | None = None) -> dict:
    F = F if F is not None else G.frames()
    agg: dict = defaultdict(dict)
    rows: dict = {}
    nrec = nx = 0
    for mk in S.MARKETS:
        if mk in F:
            r, a, b = market(F[mk], agg)
            rows.update(r)
            nrec += a
            nx += b
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": {mk: F[mk]["cal"][-1] for mk in F}, "nrec": nrec, "nrec_x": nx,
            "rows": G._r(rows), "cells": G._r(grid(agg))}


def save(R: dict, path: Path | None = None) -> None:
    path = OUT if path is None else path
    path.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


_CACHE: dict = {}


def load(path: Path | None = None) -> dict | None:
    """研究檔；沒有或版本 < AGE_VER 回 None（第 5 節 ④c：照 ④b 列、頁面標第幾天的成績還沒算）。"""
    path = OUT if path is None else path
    if path not in _CACHE:
        try:
            R = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            R = None
        _CACHE[path] = R if R and (R.get("ver") or 0) >= S.AGE_VER else None
    return _CACHE[path]


# ── 每天建頁 ──────────────────────────────────────────────────────────────────

def cell(A: dict | None, sid: str, hz: str, ck: str | None) -> dict | None:
    """今天那一格（研究檔 rows[訊號][溫度計]）→ {"n", "m", "up": {n, hit, base}, "warn": {…}, "rmed", "bmed", "ddw", "ddw_d", "ck"}；
    沒有這一格（過去沒有一天落在這裡）→ 次數 0 的空格；研究檔沒有這個訊號 → None。"""
    R = ((A or {}).get("rows") or {}).get(sid, {}).get(hz)
    if not R or ck is None:
        return None
    b = R.get("b") or [None, None, None]
    c = (R.get("c") or {}).get(ck) or [0, 0, None, None, None, None, None]
    n, m, hu, hw, rm, dw, dd = (c + [None] * 7)[:7]
    return {"ck": ck, "n": n, "m": m, "up": {"n": n, "hit": hu, "base": b[0]}, "warn": {"n": n, "hit": hw, "base": b[1]},
            "rmed": rm, "bmed": b[2], "ddw": dw, "ddw_d": dd}


def ok_cell(c: dict | None, d: str) -> tuple[bool, str | None, float | None]:
    """④c：今天那一格這一邊過不過 → (過, 沒過的原因 AGE_WHY, 那一格的 e)。"""
    st = (c or {}).get("warn" if d == "warn" else "up") or {}
    n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
    if n < S.N_MIN or hit is None or base is None:
        return False, "few", None if hit is None or base is None else hit - base
    e = hit - base
    return (e >= S.THERMO_EDGE), (None if e >= S.THERMO_EDGE else "weak"), e


def est(A: dict | None, d: str, H: int, n: int, e: float, x: bool) -> dict:
    """那一格的之後也成立（第 5.1 節）：照順序往上找第一個算得出 k 的格子（找不到＝0）→ {"k", "lv", "key", "g": k × e}。"""
    cells = (A or {}).get("cells") or {}
    for i, key in enumerate(chain(S.AGE_XP[1 if x else 0], d, int(H), int(n), float(e))):
        c = cells.get(key)
        if c and c.get("k") is not None:
            return {"k": c["k"], "lv": i, "key": key, "g": c["k"] * e}
    return {"k": 0.0, "lv": None, "key": None, "g": 0.0}
