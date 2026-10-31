"""第二套算法（docs/lab_signal_quality_plan.md 第 5、8 節，A 段）：照規格從輸入重算市場層級訊號與成績，和網頁用的 sigcat 在同一份資料上逐一比對。

不呼叫 sigcat 的偵測與統計（signals、ev_stat、st_stat、dedupe、episodes、outcomes）；只用 sigcat.frames 組好的輸入（0～100、收盤、法人金額…）。
0～100 這一層另由 truncheck（截斷重建）核對。

  detect(F)        每個訊號：事件型的出現日、狀態型的樣本日與在不在狀態中（定義照 sigspec 第 4 節、heatspec.EVT、hotdd、hotch、heattech）
  outcomes(...)    偏多、警示、最大回撤（逐筆迴圈）
  ev_stats／st_stats  次數、命中率、平常（第 3.4 節：事件去重；狀態分段、每一天一樣重）
  check_market(F)  和 sigcat 比對 → {"n", "checked", "bad": [...], "skip": [...]}
"""
from __future__ import annotations

import math

import numpy as np

from . import sigspec as S

TOL = 1e-9                       # 同一份資料、兩套算法：命中率、平常要一樣到浮點誤差
TECH_SKIP = ("dtop", "dbot", "hstop", "hsbot")   # 型態類還沒有第二套算法（只靠截斷重建與測試）


def _fin(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# ── 偵測 ──────────────────────────────────────────────────────────────────────

def _zone_events(x: np.ndarray, kind: str) -> list[int]:
    """進入過熱：今天 ≥ HOT、前 20 個交易日都有值而且 < HOT；進入過冷反過來（heatspec.EVT）。"""
    thr, prior = (S.HOT, 20) if kind == "hot" else (S.COLD, 20)
    out = []
    for t in range(prior, len(x)):
        if not _fin(x[t]):
            continue
        w = x[t - prior:t]
        if not all(_fin(u) for u in w):
            continue
        if kind == "hot" and x[t] >= thr and all(u < thr for u in w):
            out.append(t)
        elif kind == "cold" and x[t] < thr and all(u >= thr for u in w):
            out.append(t)
    return out


def _exits(x: np.ndarray, we: list[int], hot: bool) -> list[int]:
    """過熱（過冷）結束：週末連續 ≥ EXIT_MIN 週在區內之後，第一個有值而且離開的週末；沒有值的週末只讓週數歸零。"""
    out, run = [], 0
    for i in we:
        v = x[i]
        inside = _fin(v) and ((v >= S.HOT) if hot else (v < S.COLD))
        if inside:
            run += 1
            continue
        if _fin(v) and run >= S.EXIT_MIN:
            out.append(i)
        run = 0
    return out


def _streak13(x: np.ndarray, we: list[int]) -> np.ndarray:
    """每天：今天 ≥ HOT → 1＋今天以前最後一個週末為止連續過熱的週末數，否則 0；沒有值＝NaN（hotch 的 w(t)）。"""
    T = len(x)
    out = np.full(T, np.nan)
    wes = sorted(we)
    run = 0
    j = 0
    last = 0
    for t in range(T):
        while j < len(wes) and wes[j] < t:
            run = run + 1 if (_fin(x[wes[j]]) and x[wes[j]] >= S.HOT) else 0
            last = run
            j += 1
        if _fin(x[t]):
            out[t] = 1 + last if x[t] >= S.HOT else 0
    return out


def _var_sigs(mk: str, cat: str, v: dict, we: list[int], inst: bool = False) -> list[dict]:
    x = np.asarray(v["x"], dtype=float)
    samp = np.flatnonzero(~np.isnan(x))
    xs = x[samp]
    out = [{"id": f"{mk}:{cat}:{v['key']}:hot", "kind": "state", "H": v["H"], "samp": samp, "state": xs >= S.HOT,
            "brk": xs < S.COLD},
           {"id": f"{mk}:{cat}:{v['key']}:cold", "kind": "state", "H": v["H"], "samp": samp, "state": xs < S.COLD,
            "brk": xs >= S.HOT},
           {"id": f"{mk}:{cat}:{v['key']}:hot_in", "kind": "event", "H": v["H"], "samp": samp, "days": _zone_events(x, "hot")},
           {"id": f"{mk}:{cat}:{v['key']}:cold_in", "kind": "event", "H": v["H"], "samp": samp, "days": _zone_events(x, "cold")},
           {"id": f"{mk}:{cat}:{v['key']}:hot_out", "kind": "event", "H": v["H"], "samp": samp, "days": _exits(x, we, True)}]
    if inst:
        out.append({"id": f"{mk}:{cat}:{v['key']}:cold_out", "kind": "event", "H": v["H"], "samp": samp,
                    "days": _exits(x, we, False)})
    else:
        w = _streak13(x, we)[samp]
        out.append({"id": f"{mk}:{cat}:{v['key']}:hot13", "kind": "state", "H": v["H"], "samp": samp,
                    "state": np.nan_to_num(w, nan=0.0) >= S.HOT_WEEKS, "brk": xs < S.COLD})
    if cat not in S.EP_BREAK_CATS:
        for sd in out:
            sd.pop("brk", None)
    return out


def _runs(amt: np.ndarray, sign: int, n: int) -> list[int]:
    out, c = [], 0
    for t in range(len(amt)):
        c = c + 1 if (_fin(amt[t]) and amt[t] * sign > 0) else 0
        if c == n:
            out.append(t)
    return out


def _sma(px: np.ndarray, n: int) -> np.ndarray:
    """簡單平均：窗口裡 n 天都有收盤才算。"""
    T = len(px)
    out = np.full(T, np.nan)
    ok = ~np.isnan(px)
    v = np.where(ok, px, 0.0)
    cs, cn = np.concatenate([[0.0], np.cumsum(v)]), np.concatenate([[0], np.cumsum(ok)])
    for t in range(n - 1, T):
        if cn[t + 1] - cn[t + 1 - n] == n:
            out[t] = (cs[t + 1] - cs[t + 1 - n]) / n
    return out


def _side(a: np.ndarray, b: np.ndarray) -> list:
    """+1／−1／0（差距小到浮點誤差＝相等：累加順序不同會差 1e-12，例：收盤剛好等於月線的那幾天）。"""
    out = []
    for p, q in zip(a, b):
        if np.isnan(p) or np.isnan(q):
            out.append(None)
        elif abs(p - q) <= 1e-9 * max(abs(p), abs(q)):
            out.append(0)
        else:
            out.append(1 if p > q else -1)
    return out


def _flip(sd: list, prior: int = 10, conf: int = 3) -> tuple[list[int], list[int]]:
    """換邊：最近 conf 天都是新的一邊、再往前 prior 天都是另一邊（0 或沒有值都不算）。"""
    dn, up = [], []
    for t in range(prior + conf - 1, len(sd)):
        new, old = sd[t - conf + 1:t + 1], sd[t - conf - prior + 1:t - conf + 1]
        if all(s == -1 for s in new) and all(s == 1 for s in old):
            dn.append(t)
        elif all(s == 1 for s in new) and all(s == -1 for s in old):
            up.append(t)
    return dn, up


def _pivot_breaks(px: np.ndarray, thr: float = 0.05) -> tuple[list[int], list[int]]:
    """前波高低點（收盤回落／反彈 thr 才確認）→ 跌破前波低點、突破前波高點（每個轉折點只算一次）。"""
    piv = []
    mode, hi, lo = 0, None, None
    for i, p in enumerate(px):
        if np.isnan(p):
            continue
        if hi is None:
            hi = lo = i
            continue
        if mode >= 0 and p > px[hi]:
            hi = i
        if mode <= 0 and p < px[lo]:
            lo = i
        if mode >= 0 and p <= px[hi] * (1 - thr):
            piv.append(("H", hi, px[hi], i))
            mode, lo = -1, i
        elif mode <= 0 and p >= px[lo] * (1 + thr):
            piv.append(("L", lo, px[lo], i))
            mode, hi = 1, i
    dn, up, used = [], [], set()
    last = {"H": None, "L": None}
    j = 0
    for t in range(1, len(px)):
        while j < len(piv) and piv[j][3] < t:
            last[piv[j][0]] = j
            j += 1
        if np.isnan(px[t]) or np.isnan(px[t - 1]):
            continue
        if last["L"] is not None and last["L"] not in used and px[t] < piv[last["L"]][2] <= px[t - 1]:
            dn.append(t)
            used.add(last["L"])
        if last["H"] is not None and last["H"] not in used and px[t] > piv[last["H"]][2] >= px[t - 1]:
            up.append(t)
            used.add(last["H"])
    return dn, up


def _tech(mk: str, px: np.ndarray) -> list[dict]:
    T = len(px)
    M = {n: _sma(px, n) for n in (20, 60, 240)}
    ev: dict = {}
    for n, a, b in ((20, "ma20_dn", "ma20_up"), (60, "ma60_dn", "ma60_up"), (240, "ma240_dn", "ma240_up")):
        ev[a], ev[b] = _flip(_side(px, M[n]))
    ev["x_dead"], ev["x_gold"] = _flip(_side(M[20], M[60]))
    ev["s60_dn"], ev["s60_up"] = _flip([None] + _side(M[60][1:], M[60][:-1]))
    ev["pv_dn"], ev["pv_up"] = _pivot_breaks(px)
    samp = np.arange(S.EV_START, T)
    return [{"id": f"{mk}:tech:{k}", "kind": "event", "H": S.H_TECH, "samp": samp, "days": [t for t in d if t >= S.EV_START]}
            for k, d in ev.items()]


def detect(F: dict) -> tuple[list[dict], list[str]]:
    """一個市場的訊號（第二套）；回傳 (訊號, 沒有第二套算法的訊號 id 前綴)。"""
    mk, cal, px, we = F["mk"], F["cal"], np.asarray(F["px"], dtype=float), list(F["we"])
    T = len(cal)
    out: list[dict] = []
    for cat, key in (("heat", "vars"), ("crash", "cvars"), ("bd", "bvars")):
        for v in F.get(key) or []:
            out += _var_sigs(mk, cat, v, we)
    # 同時兩個以上面向過熱
    hot, have = np.zeros(T, dtype=int), np.zeros(T, dtype=int)
    for d in F["dims"]:
        c = np.asarray(F["comp"][d], dtype=float)
        hot += (~np.isnan(c) & (np.nan_to_num(c, nan=-1) >= S.HOT)).astype(int)
        have += (~np.isnan(c)).astype(int)
    samp = np.flatnonzero(have >= S.MULTI_MIN_DIMS)
    out.append({"id": f"{mk}:multi:M2:hot", "kind": "state", "H": S.H_MULTI, "samp": samp, "state": hot[samp] >= S.MULTI_K})
    mev = [t for t in range(20, T) if have[t] >= S.MULTI_MIN_DIMS and hot[t] >= S.MULTI_K
           and all(have[j] >= S.MULTI_MIN_DIMS and hot[j] < S.MULTI_K for j in range(t - 20, t))]
    out.append({"id": f"{mk}:multi:M2:hot_in", "kind": "event", "H": S.H_MULTI, "samp": samp, "days": mev})
    # 情境
    src = S.SCEN_SRC["tw" if mk == "tw" else "us"]
    X = {}
    for g in S.SCEN_DIMS:
        arrs = [np.asarray(F["comp"][d], dtype=float) for d in src[g] if d in F["comp"]]
        X[g] = np.mean(np.vstack(arrs), axis=0) if len(arrs) == len(src[g]) else np.full(T, np.nan)
    for key, _name, cond, _why in S.SCENARIOS:
        if cond in ("many_hi", "many_lo"):
            Mx = np.vstack([X[g] for g in S.SCEN_DIMS])
            ok = (~np.isnan(Mx)).sum(axis=0) >= S.SCEN_MIN_DIMS
            on = ((Mx >= S.SCEN_HI) if cond == "many_hi" else (Mx < S.SCEN_LO)) & ~np.isnan(Mx)
            flag = ok & (on.sum(axis=0) >= S.SCEN_MANY)
        else:
            ok = np.ones(T, dtype=bool)
            flag = np.ones(T, dtype=bool)
            for g, o in cond:
                ok &= ~np.isnan(X[g])
                flag &= (X[g] >= S.SCEN_HI) if o == "hi" else (X[g] < S.SCEN_LO)
            flag &= ok
        sp = np.flatnonzero(ok)
        out.append({"id": f"{mk}:scen:{key}", "kind": "state", "H": S.H_SCEN, "samp": sp, "state": flag[sp]})
    # 法人
    for v in F.get("ivars") or []:
        x = np.asarray(v["x"], dtype=float)
        if v["w"] in S.INST_POS_WIN:
            out += _var_sigs(mk, "inst", v, we, inst=True)
            continue
        sp = np.flatnonzero(~np.isnan(x))
        hi, lo = S.INST_DAY
        out.append({"id": f"{mk}:inst:{v['key']}:day_sell", "kind": "event", "H": v["H"], "samp": sp,
                    "days": [int(t) for t in sp if x[t] >= hi]})
        out.append({"id": f"{mk}:inst:{v['key']}:day_buy", "kind": "event", "H": v["H"], "samp": sp,
                    "days": [int(t) for t in sp if x[t] <= lo]})
        amt = np.asarray(v["amt"], dtype=float)
        sa = np.flatnonzero(~np.isnan(amt))
        for sign, tag in ((-1, "sell"), (1, "buy")):
            for n in S.INST_RUN:
                out.append({"id": f"{mk}:inst:{v['key']}:{tag}_run{n}", "kind": "event", "H": S.INST_H["run"], "samp": sa,
                            "days": _runs(amt, sign, n)})
    # 技術事件
    out += _tech(mk, px)
    # 邊際變化
    for v in F["deriv"]:
        sp = np.flatnonzero(np.asarray(v["have"], dtype=bool))
        x = np.asarray(v["x"], dtype=float)
        for s in S.DERIV_STATES:
            out.append({"id": f"{mk}:deriv:{v['key']}:{s}", "kind": "state", "H": S.H_DERIV, "samp": sp,
                        "state": x[sp] == s})
    # 泡沫（月底一個樣本，已經過完的月份）
    me: dict = {}
    for i, d in enumerate(cal):
        me[d[:7]] = i
    done = {d[:7] for d in cal if d[:7] < cal[-1][:7]}
    rows = [r for r in F["bub"] if str(r.get("d"))[:7] in done and str(r.get("d"))[:7] in me]
    for k in S.BUB_SIGNALS:
        val = []
        for r in rows:
            f = (None if r.get("L") is None else r["L"] >= int(k[1])) if k in ("L2", "L3") else \
                (None if r.get(k) is None else bool(r[k]))
            if f is not None:
                val.append((me[str(r["d"])[:7]], f))
        if val:
            out.append({"id": f"{mk}:bub:{k}", "kind": "state", "H": S.H_BUB, "samp": np.array([i for i, _ in val]),
                        "state": np.array([f for _, f in val], dtype=bool), "monthly": True})
    return out, [f"{mk}:tech:{k}" for k in TECH_SKIP]


# ── 成績 ──────────────────────────────────────────────────────────────────────

def outcomes(px: np.ndarray, H: int, th: float) -> tuple[np.ndarray, np.ndarray]:
    """第 t 天的訊號：e＝t＋LAG、z＝e＋H。偏多＝收盤 z > e；警示＝e～z 收盤的最大回撤 ≥ th。e、z 沒有收盤＝不算（NaN）。"""
    T = len(px)
    up, wn = np.full(T, np.nan), np.full(T, np.nan)
    for t in range(T):
        e, z = t + S.LAG, t + S.LAG + H
        if z >= T or np.isnan(px[e]) or np.isnan(px[z]):
            continue
        w = px[e:z + 1]
        w = w[~np.isnan(w)]
        pk = np.maximum.accumulate(w)
        up[t] = float(px[z] > px[e])
        wn[t] = float(np.max(1.0 - w / pk) >= th)
    return up, wn


def _dedupe(days, H: int) -> list[int]:
    out, last = [], None
    for t in sorted(days):
        if last is None or t - last > H:
            out.append(int(t))
            last = t
    return out


def _base(Y: np.ndarray, samp) -> float | None:
    v = Y[np.asarray(samp, dtype=np.int64)]
    v = v[~np.isnan(v)]
    return float(v.mean()) if len(v) else None


def ev_stats(sd: dict, Yu: np.ndarray, Yw: np.ndarray, H: int) -> dict:
    ok = set(int(i) for i in sd["samp"])
    kept = [t for t in _dedupe([t for t in sd["days"] if t in ok], H) if not (np.isnan(Yu[t]) or np.isnan(Yw[t]))]
    return {"occ": kept, "up": {"n": len(kept), "hit": float(np.mean([Yu[t] for t in kept])) if kept else None,
                                "base": _base(Yu, sd["samp"])},
            "warn": {"n": len(kept), "hit": float(np.mean([Yw[t] for t in kept])) if kept else None, "base": _base(Yw, sd["samp"])}}


def st_stats(sd: dict, Yu: np.ndarray, Yw: np.ndarray) -> dict:
    samp = np.asarray(sd["samp"], dtype=np.int64)
    st = np.asarray(sd["state"], dtype=bool)
    gap = 1 if sd.get("monthly") else S.EP_GAP
    brk = sd.get("brk")
    eps: list[list[int]] = []
    for p in np.flatnonzero(st).tolist():
        if eps:
            q = eps[-1][-1]
            between = range(q + 1, p)
            if p - q - 1 < gap and not (brk is not None and any(bool(brk[i]) for i in between)):
                eps[-1].append(p)
                continue
        eps.append([p])
    occ, days = [], []
    for ep in eps:
        ts = [int(samp[i]) for i in ep if not (np.isnan(Yu[samp[i]]) or np.isnan(Yw[samp[i]]))]
        if ts:
            occ.append((int(samp[ep[0]]), int(samp[ep[-1]]), len(ep)))
            days += ts
    return {"occ": occ, "up": {"n": len(occ), "hit": float(np.mean([Yu[t] for t in days])) if days else None, "base": _base(Yu, samp)},
            "warn": {"n": len(occ), "hit": float(np.mean([Yw[t] for t in days])) if days else None, "base": _base(Yw, samp)}}


def _close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= TOL


# ── 比對 ──────────────────────────────────────────────────────────────────────

def check_market(F: dict) -> dict:
    """同一份 F：sigcat（網頁用的那一套）與第二套的訊號、出現日、每一個看多久的次數與命中率逐一比對。"""
    from . import sigcat as G
    mk = F["mk"]
    px = np.asarray(F["px"], dtype=float)
    A = {sd["id"]: sd for sd in G.signals(F)}
    B, skip_ids = detect(F)
    Bm = {sd["id"]: sd for sd in B}
    bad: list = []
    skip = sorted(i for i in A if i in skip_ids)
    for sid in sorted(set(A) ^ set(Bm)):
        if sid not in skip:
            bad.append([sid, "只有一邊有這個訊號", "sigcat" if sid in A else "第二套"])
    Ya: dict = {}
    Yb: dict = {}
    checked = 0
    for sid in sorted(set(A) & set(Bm)):
        a, b = A[sid], Bm[sid]
        if a["kind"] == "event":
            da = sorted(int(t) for t in a["days"])
            if da != sorted(b["days"]):
                bad.append([sid, "出現日不同", len(da), len(b["days"])])
                continue
        else:
            sa, sb = np.asarray(a["samp"], dtype=np.int64), np.asarray(b["samp"], dtype=np.int64)
            if not np.array_equal(sa, sb) or not np.array_equal(np.asarray(a["state"], bool), np.asarray(b["state"], bool)):
                bad.append([sid, "狀態不同", int(np.asarray(a["state"], bool).sum()), int(np.asarray(b["state"], bool).sum())])
                continue
            if (a.get("brk") is None) != (b.get("brk") is None) or \
                    (a.get("brk") is not None and not np.array_equal(np.asarray(a["brk"], bool), np.asarray(b["brk"], bool))):
                bad.append([sid, "相反極端的分段不同"])
                continue
        hs = [a["H"]] + ([H for H in S.THERMO_H.values() if H != a["H"]] if sid.split(":")[1] in S.THERMO_X_CATS else [])
        for H in hs:
            if H not in Ya:
                th = G.warn_th(mk, H)
                Yu, Yw, _ = G.outcomes(px, H, th)
                Ya[H] = (Yu, Yw)
                Yb[H] = outcomes(px, H, th)
                if not (np.array_equal(np.isnan(Yu), np.isnan(Yb[H][0])) and np.allclose(np.nan_to_num(Yu), np.nan_to_num(Yb[H][0]))
                        and np.allclose(np.nan_to_num(Yw), np.nan_to_num(Yb[H][1]))):
                    bad.append([f"{mk}:outcomes", "偏多／警示的逐日結果不同", H])
            Yu, Yw = Ya[H]
            samp = np.asarray(a["samp"], dtype=np.int64)
            if a["kind"] == "event":
                ra = G.ev_stat(a["days"], Yu, Yw, samp, H, 0)
                rb = ev_stats(b, *Yb[H], H)
                if [int(o[0]) for o in ra["occ"]] != rb["occ"]:
                    bad.append([sid, "去重後的次數不同", H, len(ra["occ"]), len(rb["occ"])])
                    continue
            else:
                gap = 1 if a.get("monthly") else S.EP_GAP
                ra = G.st_stat(np.asarray(a["state"], dtype=bool), samp, Yu, Yw, gap, 0, brk=a.get("brk"))
                rb = st_stats(b, *Yb[H])
                if [(int(o[0]), int(o[1]), int(o[2])) for o in ra["occ"]] != rb["occ"]:
                    bad.append([sid, "分段不同", H, len(ra["occ"]), len(rb["occ"])])
                    continue
            for d in ("up", "warn"):
                if ra[d]["n"] != rb[d]["n"] or not _close(ra[d]["hit"], rb[d]["hit"]) or not _close(ra[d]["base"], rb[d]["base"]):
                    bad.append([sid, "成績不同", H, d, ra[d]["n"], rb[d]["n"], ra[d]["hit"], rb[d]["hit"]])
        checked += 1
    return {"mk": mk, "n": len(A), "checked": checked, "skip": skip, "bad": bad}
