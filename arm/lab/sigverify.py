"""第二套算法（docs/lab_signal_quality_plan.md 第 5、8 節，A 段）：照規格從輸入重算市場層級訊號與成績，和網頁用的 sigcat 在同一份資料上逐一比對。

不呼叫 sigcat 的偵測與統計（signals、ev_stat、st_stat、dedupe、episodes、outcomes）；只用 sigcat.frames 組好的輸入（0～100、收盤、法人金額…）。
0～100 這一層另由 truncheck（截斷重建）核對。

  detect(F)        每個訊號：事件型的出現日、狀態型的樣本日與在不在狀態中（定義照 sigspec 第 4 節、heatspec.EVT、hotdd、hotch、heattech）
  outcomes(...)    偏多、警示、最大回撤（逐筆迴圈）
  ev_stats／st_stats  次數、命中率、平常（第 3.4 節：事件去重；狀態分段、每一天一樣重）
  check_market(F)  和 sigcat 比對 → {"n", "checked", "bad": [...], "skip": [...]}
"""
from __future__ import annotations

import bisect
import math

import numpy as np

from . import sigspec as S

TOL = 1e-9                       # 同一份資料、兩套算法：命中率、平常要一樣到浮點誤差
TECH_SKIP: tuple = ()             # A-1b 起型態類（M 頭、W 底、頭肩）也有第二套算法


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


def _pivots(px: np.ndarray, thr: float = 0.05) -> list[tuple]:
    """轉折點（收盤從高點回落 thr 才確認高點、從低點反彈 thr 才確認低點，高低交替）→ [(種類, 那天, 收盤, 確認那天)]。"""
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
    return piv


def _pivot_breaks(px: np.ndarray, piv: list[tuple]) -> tuple[list[int], list[int]]:
    """跌破前波低點、突破前波高點（確認日在今天以前的最近一個；每個轉折點只算一次）。"""
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


def _first_cross(px: np.ndarray, piv: list[tuple], j: int, line, below: bool) -> int | None:
    """第 j 個轉折點確認那天起、下一個轉折點確認前一天為止，收盤第一次跌破（below）／突破 line(t) 的那天。"""
    end = piv[j + 1][3] if j + 1 < len(piv) else len(px)
    for t in range(piv[j][3], end):
        if not np.isnan(px[t]) and (px[t] < line(t) if below else px[t] > line(t)):
            return t
    return None


def _patterns(px: np.ndarray, piv: list[tuple]) -> dict:
    """M 頭／W 底（連續三個轉折點，兩端相差 ≤ DT_TOL × 平均、相隔 ≥ DT_GAP 天，跌破／突破中間那一點）、
    頭肩頂／頭肩底（連續五個轉折點：頭最高（低）、兩肩不低於（不高於）對側肩與它腋下的中點、左右時間比 ≤ HS_RATIO，
    跌破／突破兩個腋下的連線）。heatspec 第 EVENTS 節。"""
    from . import heatspec as HS
    ev = {"dtop": [], "dbot": [], "hstop": [], "hsbot": []}
    for j in range(2, len(piv)):
        a, m, b = piv[j - 2], piv[j - 1], piv[j]
        if abs(a[2] - b[2]) <= HS.DT_TOL * (a[2] + b[2]) / 2 and b[1] - a[1] >= HS.DT_GAP:
            top = b[0] == "H"
            t = _first_cross(px, piv, j, lambda _t, v=m[2]: v, top)
            if t is not None:
                ev["dtop" if top else "dbot"].append(t)
    for j in range(4, len(piv)):
        ls, a1, h, a2, rs = piv[j - 4:j + 1]
        top = rs[0] == "H"
        sg = 1 if top else -1
        if not (sg * h[2] > sg * ls[2] and sg * h[2] > sg * rs[2]):
            continue
        if sg * ls[2] < sg * (rs[2] + a2[2]) / 2 or sg * rs[2] < sg * (ls[2] + a1[2]) / 2:
            continue
        lt, rt = h[1] - ls[1], rs[1] - h[1]
        if rt > HS.HS_RATIO * lt or lt > HS.HS_RATIO * rt:
            continue
        k = (a2[2] - a1[2]) / (a2[1] - a1[1])
        t = _first_cross(px, piv, j, lambda _t, a1=a1, k=k: a1[2] + (_t - a1[1]) * k, top)
        if t is not None:
            ev["hstop" if top else "hsbot"].append(t)
    return ev


def _tech(mk: str, px: np.ndarray) -> list[dict]:
    T = len(px)
    M = {n: _sma(px, n) for n in (20, 60, 240)}
    ev: dict = {}
    for n, a, b in ((20, "ma20_dn", "ma20_up"), (60, "ma60_dn", "ma60_up"), (240, "ma240_dn", "ma240_up")):
        ev[a], ev[b] = _flip(_side(px, M[n]))
    ev["x_dead"], ev["x_gold"] = _flip(_side(M[20], M[60]))
    ev["s60_dn"], ev["s60_up"] = _flip([None] + _side(M[60][1:], M[60][:-1]))
    from . import heatspec as HS
    piv = _pivots(px, HS.PIVOT_THR)
    ev["pv_dn"], ev["pv_up"] = _pivot_breaks(px, piv)
    ev.update(_patterns(px, piv))
    samp = np.arange(S.EV_START, T)
    return [{"id": f"{mk}:tech:{k}", "kind": "event", "H": S.H_TECH, "samp": samp, "days": [t for t in d if t >= S.EV_START]}
            for k, d in ev.items()]


def _done_weeks(cal: list) -> list[int]:
    """訊號用的週末：每個 ISO 週最後一個交易日；最新一天要是星期五或星期六才算（那一週還沒過完就不算）。"""
    from datetime import date
    out = []
    for i, d in enumerate(cal):
        if i + 1 < len(cal):
            if date.fromisoformat(cal[i + 1]).isocalendar()[:2] != date.fromisoformat(d).isocalendar()[:2]:
                out.append(i)
        elif date.fromisoformat(d).weekday() >= 4:
            out.append(i)
    return out


def detect(F: dict) -> tuple[list[dict], list[str]]:
    """一個市場的訊號（第二套）；回傳 (訊號, 沒有第二套算法的訊號 id 前綴)。"""
    mk, cal, px = F["mk"], F["cal"], np.asarray(F["px"], dtype=float)
    we = _done_weeks(cal)
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


def _episodes(sd: dict) -> list[list[int]]:
    """狀態型：在狀態中的樣本分段（和上一個在狀態中的樣本相隔 < gap 個樣本、中間沒到過相反的極端＝同一段）→ 每段的日子。"""
    samp = np.asarray(sd["samp"], dtype=np.int64)
    st = np.asarray(sd["state"], dtype=bool)
    gap = 1 if sd.get("monthly") else S.EP_GAP
    brk = sd.get("brk")
    eps: list[list[int]] = []
    for p in np.flatnonzero(st).tolist():
        if eps and p - eps[-1][-1] - 1 < gap and not (brk is not None and any(bool(brk[i]) for i in range(eps[-1][-1] + 1, p))):
            eps[-1].append(p)
        else:
            eps.append([p])
    return [[int(samp[i]) for i in ep] for ep in eps]


def st_stats(sd: dict, Yu: np.ndarray, Yw: np.ndarray) -> dict:
    samp = np.asarray(sd["samp"], dtype=np.int64)
    occ, days = [], []
    for ep in _episodes(sd):
        ts = [t for t in ep if not (np.isnan(Yu[t]) or np.isnan(Yw[t]))]
        if ts:
            occ.append((ep[0], ep[-1], len(ep)))
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



# ── A-1b：之後怎麼走的報酬表、近 10 年、最大跌幅、判定（第二套） ───────────────────

def fwd(px: np.ndarray, H: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """第 t 天的訊號（e＝t＋LAG、z＝e＋H）→ (之後漲跌, 中途最多跌, 最大跌幅)，逐筆迴圈：
    漲跌＝z 收盤 ÷ e 收盤 − 1；中途最多跌＝min(0, e＋1～z 最低收盤 ÷ e 收盤 − 1)；最大跌幅＝e～z 收盤的最大回撤（e、z 都要有收盤）。"""
    p = [None if np.isnan(v) else float(v) for v in px]
    T = len(p)
    r, a, d = np.full(T, np.nan), np.full(T, np.nan), np.full(T, np.nan)
    for t in range(T - S.LAG - H):
        e, z = t + S.LAG, t + S.LAG + H
        pe, pz = p[e], p[z]
        if pe is None:
            continue
        mid = [v for v in p[e + 1:z + 1] if v is not None]
        if mid:
            a[t] = min(0.0, min(mid) / pe - 1.0)
        if pz is None:
            continue
        r[t] = pz / pe - 1.0
        pk, dd = pe, 0.0
        for v in mid:
            if v > pk:
                pk = v
            else:
                dd = max(dd, 1.0 - v / pk)
        d[t] = dd
    return r, a, d


def _q(vals: list, q: float) -> float:
    """每一個一樣重的百分位：由小到大第 ceil(q × n) 個（不內插）。"""
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s) - 1e-9) - 1))]


def _trim_lbo(vals: list, ws: list) -> list:
    """排除極端（兩邊各去掉 k 個單位：次數 < TRIM_N 去 1 個，其餘 TRIM_Q）、去掉最好一次；其餘照權重平均。"""
    pr = sorted(zip(vals, ws), key=lambda x: x[0])
    n = len(pr)
    k = 1 if n < S.TRIM_N else max(1, int(math.floor(S.TRIM_Q * n + 1e-9)))
    wm = lambda xs: sum(v * w for v, w in xs) / sum(w for _, w in xs)
    return [wm(pr[k:n - k]) if n >= 3 else None, wm(pr[:-1]) if n >= 2 else None]


def _worst(vals: list, days: list, cal: list) -> list:
    """最大跌幅最差一次與日期（一樣大取最早的）；沒有值＝[]。"""
    fin = [(v, t) for v, t in zip(vals, days) if not np.isnan(v)]
    if not fin:
        return []
    best = max(v for v, _ in fin)
    return [best, cal[next(t for v, t in fin if v == best)]]


def returns(groups: list, RA2: dict, cal: list, states: bool) -> dict:
    """groups＝每一次的日子（事件：一天一組；狀態：一段一組）→ {"s": RET_H 每一期 13 欄（同 sigcat.ret_cell）,
    "p": PATH_D 每一天 [25%, 中位數, 75%]}；每一天一樣重，排除極端與去掉最好一次的單位＝每一次（狀態：每一段的平均、權重＝天數）。"""
    s = []
    for h in S.RET_H:
        R, A, D = RA2[h]
        rs, as_, ds, ix, mv, mw = [], [], [], [], [], []
        for g in groups:
            k = [t for t in g if not (np.isnan(R[t]) or np.isnan(A[t]))]
            if k:
                rs += [R[t] for t in k]
                as_ += [A[t] for t in k]
                ds += [D[t] for t in k]
                ix += k
                mv.append(sum(R[t] for t in k) / len(k))
                mw.append(float(len(k)))
        if not rs:
            s.append(None)
            continue
        m = len(rs)
        o = (mv, mw) if states else (rs, [1.0] * m)
        s.append([len(mv), sum(rs) / m, *(_q(rs, q) for q in S.RET_Q), sum(1 for x in rs if x > 0) / m,
                  _q(as_, 0.5), _q(as_, S.MAE_Q), min(as_), *_trim_lbo(*o), *_worst(ds, ix, cal)])
    pth = []
    for dd in S.PATH_D:
        R = RA2[dd][0]
        v = [R[t] for g in groups for t in g if not np.isnan(R[t])]
        pth.append([_q(v, q) for q in S.RET_Q] if v else None)
    return {"s": s, "p": pth}


def recent_start(cal: list) -> int:
    """近 10 年的起點：資料最後一天往前 RECENT_YEARS 年的同月同日（2/29 改 2/28），日曆上第一個不早於它的日子。"""
    y, m, d = (int(x) for x in cal[-1].split("-"))
    start = f"{y - S.RECENT_YEARS:04d}-{m:02d}-{28 if (m, d) == (2, 29) else d:02d}"
    return next((i for i, c in enumerate(cal) if c >= start), len(cal))


def judge(st: dict, d: str, cell: list | None, cost: float) -> str:
    """判定（sigspec 第 3 節 VER 17）：— few（次數 < N_MIN）；○ none（沒過門檻）；★ good（≥ STAR_N 次）；◆ rare。
    門檻＝命中率 ≥ HIT_MIN 而且 ≥ 平常；近 10 年有 RECENT_N 次以上也要同樣過；偏多另要報酬中位數與排除極端的平均都 > 來回成本。"""
    n, hit, base = st["n"] or 0, st["hit"], st["base"]
    if n < S.N_MIN or hit is None or base is None:
        return "few"
    ok = hit >= S.HIT_MIN[d] and hit >= base
    if ok and (st["n10"] or 0) >= S.RECENT_N:
        ok = st["hit10"] is not None and st["base10"] is not None and st["hit10"] >= S.HIT_MIN[d] and st["hit10"] >= st["base10"]
    if ok and d != "warn":                              # 偏多與大跌後買點
        ok = bool(cell and len(cell) >= 11 and cell[3] is not None and cell[9] is not None
                  and cell[3] > 2 * cost and cell[9] > 2 * cost)
    if not ok:
        return "none"
    return "good" if n >= S.STAR_N else "rare"


def row2(F: dict, sd: dict, cache: dict) -> dict:
    """一個訊號自己那一期的研究列（第二套）：次數、命中率、平常、近 10 年、最大跌幅、報酬表、判定（不含打亂日子測試）。"""
    from . import sigcat as G
    mk, cal = F["mk"], F["cal"]
    px = np.asarray(F["px"], dtype=float)
    H = sd["H"]
    if "RA" not in cache:
        cache["RA"], cache["r0"] = {}, recent_start(cal)
    for h in set(S.RET_H) | set(S.PATH_D) | {H}:
        if h not in cache["RA"]:
            cache["RA"][h] = fwd(px, h)
    RA2, r0 = cache["RA"], cache["r0"]
    if ("Y", H) not in cache:
        cache[("Y", H)] = outcomes(px, H, G.warn_th(mk, H))       # 警示門檻是規格常數（sigspec），不是計算
    Yu, Yw = cache[("Y", H)]
    Yd = RA2[H][2]
    samp = [int(i) for i in sd["samp"]]
    s10 = [t for t in samp if t >= r0]
    full = lambda t: not (np.isnan(Yu[t]) or np.isnan(Yw[t]))
    if sd["kind"] == "event":
        ok = set(samp)
        groups = [[t] for t in _dedupe([t for t in sd["days"] if t in ok], H)]
        segs = [g for g in groups if full(g[0])]
    else:
        groups = _episodes(sd)
        segs = [[t for t in g if full(t)] for g in groups]
        segs = [s2 if s2 else None for s2 in segs]
        firsts = [g[0] for g, s2 in zip(groups, segs) if s2]
        segs = [s2 for s2 in segs if s2]
    alld = [t for g in segs for t in g]
    in10 = [g for g, f in zip(segs, ([g[0] for g in segs] if sd["kind"] == "event" else firsts)) if f >= r0]
    all10 = [t for g in in10 for t in g]
    mean = lambda v: (sum(v) / len(v)) if v else None
    out = {}
    for dk, Y in (("up", Yu), ("warn", Yw)):
        out[dk] = {"n": len(segs), "hit": mean([Y[t] for t in alld]), "base": _base(Y, samp), "n10": len(in10),
                   "hit10": mean([Y[t] for t in all10]), "base10": _base(Y, s10) if s10 else None}
    dv = [Yd[t] for t in alld if not np.isnan(Yd[t])]
    bv = [Yd[t] for t in samp if not np.isnan(Yd[t])]
    out["warn"]["mdd"] = float(np.median(dv)) if dv else None
    out["warn"]["mdd_base"] = float(np.median(bv)) if bv else None
    w = _worst([Yd[t] for t in alld], alld, cal)
    if w:
        out["warn"]["mddw"], out["warn"]["mddw_d"] = w
    ret = returns(groups, RA2, cal, sd["kind"] != "event")
    cell = ret["s"][S.RET_H.index(H)] if H in S.RET_H else None
    for dk in ("up", "warn"):
        out[dk]["tier"] = judge(out[dk], dk, cell, S.ABS_COST[mk])
    order = {t: i for i, t in enumerate(S.TIERS)}
    edge = lambda st: (st["hit"] - st["base"]) if st["hit"] is not None and st["base"] is not None else -9.0
    ds = sorted(("up", "warn"), key=lambda d: (order[out[d]["tier"]], -edge(out[d])))
    top = out[ds[0]]["tier"]
    out["tier"], out["dir"] = top, ([d for d in ds if out[d]["tier"] == "good"] if top == "good" else [ds[0]])
    out["ret"] = ret
    return out


def _same(a, b) -> bool:
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        return isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    fa, fb = _fin(a), _fin(b)
    return fa == fb and (not fa or abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(a))))


ROW_KEYS = ("n", "hit", "base", "n10", "hit10", "base10", "tier")
WARN_KEYS = ("mdd", "mdd_base", "mddw", "mddw_d")


def row_diff(ra: dict, rb: dict) -> list:
    """網頁的研究列 ra（sigcat.evaluate）和第二套 rb：不一樣的欄位。"""
    out = []
    for d in ("up", "warn"):
        for k in ROW_KEYS + (WARN_KEYS if d == "warn" else ()):
            if not _same(ra[d].get(k), rb[d].get(k)):
                out.append(f"{d}.{k}")
    if ra["tier"] != rb["tier"] or list(ra["dir"]) != list(rb["dir"]):
        out.append("判定")
    for part in ("s", "p"):
        for i, (x, y) in enumerate(zip(ra["ret"][part], rb["ret"][part])):
            if not _same(x, y):
                out.append(f"ret.{part}[{i}]")
    return out


def check_rows(F: dict) -> dict:
    """研究列：網頁用的 sigcat.evaluate（打亂日子測試換成不算——VER 17 起它只呈現、不影響判定，而且是亂數）
    和第二套 row2 比：自己那一期的次數、命中率、平常、近 10 年、最大跌幅、之後怎麼走的報酬表、判定。"""
    from . import sigcat as G
    from . import sigluck as LK
    A = {sd["id"]: sd for sd in G.signals(F)}
    B = {sd["id"]: sd for sd in detect(F)[0]}
    real = LK.market_p
    LK.market_p = lambda *a, **k: {d: {"p": None, "luck": 0.0, "luck_rare": 0.0} for d in ("up", "warn")}
    bad, n, ca, cb = [], 0, {}, {}
    try:
        for sid in sorted(set(A) & set(B)):
            diff = row_diff(G.evaluate(F, A[sid], ca), row2(F, B[sid], cb))
            n += 1
            if diff:
                bad.append([sid, *diff[:6]])
    finally:
        LK.market_p = real
    return {"mk": F["mk"], "n": n, "bad": bad}



def check_buy(F: dict) -> dict:
    """大跌後買點：買進日由 bottom 偵測（它的逐筆直接算對照在 tests/test_bottom.py），這裡用第二套重算每條規則的
    次數、上漲比例、平常、近 10 年、報酬表（買進日收盤進場、窗口完整的那幾次）與判定，和 sigcat.buy_rows 比。"""
    from . import sigcat as G
    from . import sigluck as LK
    I, sds = G.buy_signals(F)
    if I is None:
        return {"mk": F["mk"], "n": 0, "bad": []}
    real = LK.market_p
    LK.market_p = lambda *a, **k: {d: {"p": None, "luck": 0.0, "luck_rare": 0.0} for d in ("up", "warn")}
    try:
        rows = {r["id"]: r for r in G.buy_rows(F)}
    finally:
        LK.market_p = real
    cal, px = list(I["cal"]), np.asarray(I["px"], dtype=float)
    H = S.H_BUY
    up, wn = outcomes(px, H, G.warn_th(F["mk"], H))
    RA2 = {h: fwd(px, h) for h in set(S.RET_H) | set(S.PATH_D)}
    r0 = recent_start(cal)
    samp = [int(i) for i in I["samp"]]
    s10 = [t for t in samp if t >= r0]
    calx = cal[S.LAG:] + [None] * S.LAG                  # 最大跌幅最差一次寫買進日
    mean = lambda v: (sum(v) / len(v)) if v else None
    bad = []
    for sd0 in sds:
        ok = set(samp)
        occ = [t for t in _dedupe([t for t in sd0["days"] if t in ok], H) if not (np.isnan(up[t]) or np.isnan(wn[t]))]
        st = {"n": len(occ), "hit": mean([up[t] for t in occ]), "base": _base(up, samp),
              "n10": sum(1 for t in occ if t >= r0), "hit10": mean([up[t] for t in occ if t >= r0]),
              "base10": _base(up, s10) if s10 else None}
        ret = returns([[t] for t in occ], RA2, calx, False)
        st["tier"] = judge(st, "buy", ret["s"][S.RET_H.index(H)], S.ABS_COST[F["mk"]])
        ra = rows.get(sd0["id"])
        if ra is None:
            bad.append([sd0["id"], "網頁沒有這一列"])
            continue
        diff = [k for k in ROW_KEYS if not _same(ra["buy"].get(k), st[k])]
        diff += [f"ret.{part}[{i}]" for part in ("s", "p") for i, (x, y) in enumerate(zip(ra["ret"][part], ret[part])) if not _same(x, y)]
        if diff:
            bad.append([sd0["id"], *diff[:6]])
    return {"mk": F["mk"], "n": len(sds), "bad": bad}



# ── A-1b：逐年檢查（sigoos）、溫度計票數（thermocal）、產業泡沫（第二套） ──────────────

def _cat(sd: dict) -> str:
    return sd["id"].split(":")[1]


def _nanmean(v: np.ndarray) -> float | None:
    v = v[~np.isnan(v)]
    return float(v.mean()) if len(v) else None


def _prep(sd: dict, H: int) -> dict:
    """一個訊號在看 H 天時的全部資料：事件＝去重後的出現日；狀態＝在狀態中的每一天（依段）與段號、每段第一天。"""
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if sd["kind"] == "event":
        ok = set(samp.tolist())
        return {"samp": samp, "kept": np.asarray(_dedupe([t for t in sd["days"] if t in ok], H), dtype=np.int64)}
    eps = _episodes(sd)
    return {"samp": samp, "D": np.asarray([t for e in eps for t in e], dtype=np.int64),
            "E": np.asarray([j for j, e in enumerate(eps) for _ in e], dtype=np.int64),
            "F0": np.asarray([e[0] for e in eps], dtype=np.int64)}


def _pstats(P: dict, H: int, cut: int, r0: int, Yu: np.ndarray, Yw: np.ndarray, min_samp: int) -> dict | None:
    """只用窗口在 cut 之前走完的樣本（t＋LAG＋H < cut）的次數、命中率、平常、近 10 年（r0 起）；樣本少於 min_samp → None。
    去重與分段是全部資料的前段（去重從前往後、分段只看之前的樣本，截掉後面不會改變前面）。"""
    lim = cut - S.LAG - H
    samp = P["samp"]
    K = int(np.searchsorted(samp, lim, side="left"))
    if K < min_samp:
        return None
    ts = samp[:K]
    if "kept" in P:
        k = P["kept"][P["kept"] < lim]
        days = k[~(np.isnan(Yu[k]) | np.isnan(Yw[k]))]
        eid, first = np.arange(len(days)), days
        groups = [[int(t)] for t in days]
    else:
        m = P["D"] < lim
        d, e = P["D"][m], P["E"][m]
        groups = [g.tolist() for g in np.split(d, np.flatnonzero(np.diff(e)) + 1)] if len(d) else []
        f = ~(np.isnan(Yu[d]) | np.isnan(Yw[d]))
        days, eid = d[f], e[f]
        first = P["F0"][eid]
    in10 = first >= r0
    out = {"groups": groups, "ts": ts}
    for dk, Y in (("up", Yu), ("warn", Yw)):
        out[dk] = {"n": int(len(np.unique(eid))), "hit": float(Y[days].mean()) if len(days) else None,
                   "base": _nanmean(Y[ts]), "n10": int(len(np.unique(eid[in10]))),
                   "hit10": float(Y[days[in10]].mean()) if in10.any() else None, "base10": _nanmean(Y[ts[ts >= r0]])}
    return out


def _cell_rows(samples: list) -> list | None:
    """每一次一組 [(報酬, 中途最多跌, 最大跌幅, 日期)…] → 報酬格（同 sigcat.ret_cell：每一個樣本一樣重；
    排除極端與去掉最好一次的單位＝一組、權重＝組內樣本數；最大跌幅沒有就沒有最後兩欄）。"""
    rs = [x[0] for g in samples for x in g]
    if not rs:
        return None
    as_ = [x[1] for g in samples for x in g]
    m = len(rs)
    mv = [sum(x[0] for x in g) / len(g) for g in samples if g]
    mw = [float(len(g)) for g in samples if g]
    out = [len(mv), sum(rs) / m, *(_q(rs, q) for q in S.RET_Q), sum(1 for x in rs if x > 0) / m,
           _q(as_, 0.5), _q(as_, S.MAE_Q), min(as_), *_trim_lbo(mv, mw)]
    fin = [(x[2], x[3]) for g in samples for x in g if x[2] is not None and not np.isnan(x[2])]
    if fin:
        best = max(v for v, _ in fin)
        out += [best, next(d for v, d in fin if v == best)]
    return out


def _cell_h(groups: list, R: np.ndarray, A: np.ndarray) -> list | None:
    """日資料：每組日子 → 那一期的報酬格（沒有最大跌幅欄；sigoos 的 train 用）。"""
    return _cell_rows([[(R[t], A[t], None, None) for t in g if not (np.isnan(R[t]) or np.isnan(A[t]))] for g in groups])


def _cuts(cal: list) -> list[tuple]:
    """逐年：資料開始滿 CAL_WARM_Y 年的下一個 1 月 1 日（第一天剛好 1/1 就那一年）起到最後一年 →
    (年, cut, 下一個 cut, 近 10 年起點)。"""
    y = int(cal[0][:4]) + S.CAL_WARM_Y
    y0 = y if cal[0][5:] == "01-01" else y + 1
    at = lambda s: bisect.bisect_left(cal, s)
    return [(yr, at(f"{yr}-01-01"), at(f"{yr + 1}-01-01"), at(f"{yr - S.RECENT_YEARS}-01-01"))
            for yr in range(y0, int(cal[-1][:4]) + 1)]


def _test(P: dict, c: int, c2: int, Y: np.ndarray, R: np.ndarray) -> tuple | None:
    """那一年 [c, c2) 實際的結果（全部資料的去重與分段）→ (命中率, 報酬平均, 次數, 平常, 平常的報酬平均)。"""
    if "kept" in P:
        k = P["kept"]
        d = k[(k >= c) & (k < c2)]
        d = d[~np.isnan(Y[d])]
        cnt = len(d)
    else:
        m = (P["D"] >= c) & (P["D"] < c2)
        d, e = P["D"][m], P["E"][m]
        f = ~np.isnan(Y[d])
        d, cnt = d[f], len(np.unique(e[f]))
    if not len(d):
        return None
    samp = P["samp"]
    bs = samp[(samp >= c) & (samp < c2)]
    bs = bs[~np.isnan(Y[bs])]
    if not len(bs):
        return None
    return float(Y[d].mean()), _nanmean(R[d]), int(cnt), float(Y[bs].mean()), _nanmean(R[bs])


def _walk(mk: str, sd: dict, cuts: list, Yu, Yw, R, A, dirs: tuple, x: bool) -> list[dict]:
    """一個訊號的逐年紀錄（sigspec 第 4.14 節 ①）：每年 1 月 1 日只用之前走完的窗口算成績與判定，對那一年實際的結果。"""
    H = sd["H"]
    P = _prep(sd, H)
    out = []
    for yr, c, c2, r0 in cuts:
        tn = None
        for d in dirs:
            te = _test(P, c, c2, Yw if d == "warn" else Yu, R)
            if te is None:
                continue
            if tn is None:
                tn = _pstats(P, H, c, r0, Yu, Yw, S.CAL_MIN_SAMP) or False
                if tn:
                    tn["cell"] = _cell_h(tn["groups"], R, A)
                    tn["bmean"] = _nanmean(R[tn["ts"]])
            if tn is False:
                break
            st = tn["warn" if d == "warn" else "up"]
            if st["n"] < S.N_MIN or st["hit"] is None or st["base"] is None:
                continue
            rec = {"id": sd["id"], "d": d, "H": int(H), "yr": int(yr), "n": st["n"], "e": st["hit"] - st["base"],
                   "o": te[0] - te[3], "tn": te[2], "tier": judge(st, d, tn["cell"], S.ABS_COST[mk])}
            if x:
                rec["x"] = 1
            cell = tn["cell"]
            if d != "warn" and cell and tn["bmean"] is not None and te[1] is not None and te[4] is not None:
                rec["er"], rec["or"] = cell[1] - tn["bmean"], te[1] - te[4]
            out.append(rec)
    return out


def oos2(F: dict) -> list[dict]:
    """逐年檢查（第二套，同 sigoos.market 的紀錄）：每個訊號在自己的看多久＋另外兩支溫度計的看多久（"x"）＋大跌後買點。"""
    from . import sigcat as G
    from . import sigoos as OO
    mk = F["mk"]
    px = np.asarray(F["px"], dtype=float)
    cuts = _cuts(F["cal"])
    cache: dict = {}
    out = []
    for sd in detect(F)[0]:
        cat = _cat(sd)
        if cat not in OO.MARKET_CATS:                 # 範圍是規格（第 4.14 節），不是計算
            continue
        H = sd["H"]
        for Hx in [H] + (sorted(set(S.THERMO_H.values()) - {H}) if cat in S.THERMO_X_CATS else []):
            if Hx not in cache:
                cache[Hx] = (*outcomes(px, Hx, G.warn_th(mk, Hx)), *fwd(px, Hx)[:2])
            out += _walk(mk, {**sd, "H": Hx}, cuts, *cache[Hx], ("up", "warn"), Hx != H)
    I, bsd = G.buy_signals(F)                           # 買進日由 bottom 偵測（tests/test_bottom.py 有逐筆直接算的對照）
    if I is not None:
        bp = np.asarray(I["px"], dtype=float)
        Hb = S.H_BUY
        Yb = (*outcomes(bp, Hb, G.warn_th(mk, Hb)), *fwd(bp, Hb)[:2])
        bc = _cuts(list(I["cal"]))
        for sd in bsd:
            out += _walk(mk, sd, bc, *Yb, ("buy",), False)
    return out


def _rec_key(r: dict) -> tuple:
    return r["id"], r["d"], r["H"], r["yr"], r.get("x", 0)


def check_oos(F: dict) -> dict:
    """逐年檢查：網頁用的 sigoos.market(F) 和第二套 oos2(F) 的每一筆（訊號 × 方向 × 看多久 × 年）比。"""
    from . import sigoos as OO
    A = {_rec_key(r): r for r in OO.market(F)}
    B = {_rec_key(r): r for r in oos2(F)}
    bad = [[*k, "只有一邊有這一筆", "網頁" if k in A else "第二套"] for k in sorted(set(A) ^ set(B), key=str)]
    for k in sorted(set(A) & set(B), key=str):
        diff = [f for f in ("n", "e", "o", "tn", "tier", "er", "or") if not _same(A[k].get(f), B[k].get(f))]
        if diff:
            bad.append([*k, *diff])
    return {"mk": F["mk"], "n": len(A), "bad": bad[:50], "nbad": len(bad)}


def _expire(F: dict, sds: list[dict]) -> None:
    """事件型「之後出現就不再算現在有效」的日子（sigspec VER 20），寫進 sd["exp"]：0～100 的變數照 EXPIRE_ON
    （過冷、過熱的日子或同一個變數另一個事件的日子）；技術事件照 TECH_PAIRS 成對；法人單日與連續照 INST_SIDE 分買、賣兩邊。"""
    mk = F["mk"]
    by = {sd["id"]: sd for sd in sds}
    xs = [("heat", v) for v in F.get("vars") or []] + [("crash", v) for v in F.get("cvars") or []] + \
         [("bd", v) for v in F.get("bvars") or []] + [("inst", v) for v in F.get("ivars") or [] if v["w"] in S.INST_POS_WIN]
    for cat, v in xs:
        x = np.asarray(v["x"], dtype=float)
        f = ~np.isnan(x)
        cond = {"lt_cold": np.flatnonzero(f & (np.nan_to_num(x) < S.COLD)), "ge_hot": np.flatnonzero(f & (np.nan_to_num(x) >= S.HOT))}
        for sig, parts in S.EXPIRE_ON.items():
            sd = by.get(f"{mk}:{cat}:{v['key']}:{sig}")
            if sd is not None:
                got = [cond[c] if c in cond else np.asarray((by.get(f"{mk}:{cat}:{v['key']}:{c}") or {}).get("days", []), dtype=np.int64)
                       for c in parts]
                sd["exp"] = np.unique(np.concatenate(got)).astype(np.int64)
    for a, b in S.TECH_PAIRS:
        sa, sb = by.get(f"{mk}:tech:{a}"), by.get(f"{mk}:tech:{b}")
        if sa is not None and sb is not None:
            sa["exp"], sb["exp"] = np.unique(sb["days"]).astype(np.int64), np.unique(sa["days"]).astype(np.int64)
    for v in F.get("ivars") or []:
        if v["w"] in S.INST_POS_WIN:
            continue
        side = {sig: by.get(f"{mk}:inst:{v['key']}:{sig}") for sig in S.INST_SIDE}
        for sig, sd in side.items():
            if sd is not None:
                other = [np.asarray(o["days"], dtype=np.int64) for g, o in side.items() if o is not None and S.INST_SIDE[g] != S.INST_SIDE[sig]]
                sd["exp"] = np.unique(np.concatenate(other)).astype(np.int64) if other else np.zeros(0, dtype=np.int64)


def _active(sd: dict, T: int, H: int) -> np.ndarray:
    """每一天這個訊號在看 H 天的溫度計是不是現在有效：狀態型＝那天在狀態中（月資料到下一個月底前都算）；
    事件型＝最近一次出現（樣本開始以後）在 H 天內，而且之後還沒出現相反的讀數。"""
    a = np.zeros(T, dtype=bool)
    samp = [int(t) for t in sd["samp"]]
    if not samp:
        return a
    if sd["kind"] == "state":
        st = list(np.asarray(sd["state"], dtype=bool))
        for i, on in enumerate(st):
            if on:
                if sd.get("monthly"):
                    a[samp[i]:samp[i + 1] if i + 1 < len(samp) else T] = True
                else:
                    a[samp[i]] = True
        return a
    ex = sorted(int(t) for t in sd.get("exp", []))
    for t in sd["days"]:
        if t < samp[0]:
            continue
        j = bisect.bisect_right(ex, t)
        a[t:min(t + H, ex[j]) if j < len(ex) else t + H] = True
    return a


def _vote(st: dict | None) -> str:
    """會投哪一邊：偏多（警示）方向次數 ≥ N_MIN 而且命中率 − 平常 ≥ THERMO_EDGE（sigspec 第 5 節 ④b，VER 23）。"""
    if st is None:
        return ""
    return "".join(c for c, d in (("u", "up"), ("w", "warn"))
                   if st[d]["n"] >= S.N_MIN and st[d]["hit"] is not None and st[d]["base"] is not None
                   and st[d]["hit"] - st[d]["base"] >= S.THERMO_EDGE)


def thermo2(F: dict, items: dict) -> dict:
    """溫度計（第二套，同 thermocal.weekly＋market）：每年 1 月 1 日只用之前走完的窗口決定每個訊號投哪一邊，
    那一年每個週末兩邊各有幾個項目有效；位置（和之前最近 CAL_RANK_W 週比）、分組、之後的比例、區塊重抽。items＝{訊號: 項目}。"""
    from . import sigcat as G
    mk, cal = F["mk"], F["cal"]
    T = len(cal)
    px = np.asarray(F["px"], dtype=float)
    we = np.asarray(F["we"], dtype=np.int64)
    sds = [sd for sd in detect(F)[0] if _cat(sd) in S.THERMO_X_CATS]
    _expire(F, sds)
    Y = {k: outcomes(px, H, G.warn_th(mk, H)) for k, H in S.THERMO_H.items()}
    acts = {k: [_active(sd, T, H) for sd in sds] for k, H in S.THERMO_H.items()}
    preps = {k: [_prep(sd, H) for sd in sds] for k, H in S.THERMO_H.items()}
    cuts = _cuts(cal)
    y1 = int(cal[-1][:4])
    hist = {k: {"t": [], "u": [], "w": []} for k in S.THERMO_H}
    votes: dict = {}
    for yr, cut, nxt, _ in cuts:
        wk = we[(we >= cut) & (we < nxt)]
        if not len(wk) and yr != y1:
            continue
        for k, H in S.THERMO_H.items():
            on = {"u": {}, "w": {}}
            for i, sd in enumerate(sds):
                v = _vote(_pstats(preps[k][i], H, cut, 0, *Y[k], S.CAL_MIN_SAMP))
                if yr == y1 and v:
                    votes.setdefault(sd["id"], {"i": items[sd["id"]], "v": {}})["v"][k] = v
                for c in v:
                    it = items[sd["id"]]
                    on[c][it] = on[c].get(it, np.zeros(len(wk), dtype=bool)) | acts[k][i][wk]
            hist[k]["t"] += [int(t) for t in wk]
            for c in ("u", "w"):
                hist[k][c] += [int(sum(int(arr[j]) for arr in on[c].values())) for j in range(len(wk))]
    hz = {}
    for k, H in S.THERMO_H.items():
        h = hist[k]
        res = {}
        for side, c, Yx in (("up", "u", Y[k][0]), ("warn", "w", Y[k][1])):
            gs, ys = [], []
            for j, t in enumerate(h["t"]):
                prior = h[c][max(0, j - S.CAL_RANK_W):j]
                if len(prior) < S.CAL_RANK_MIN or np.isnan(Yx[t]):
                    continue
                mid = (sum(1 for p in prior if p < h[c][j]) + 0.5 * sum(1 for p in prior if p == h[c][j])) / len(prior)
                gs.append(0 if mid <= S.CAL_TERC[0] else 2 if mid >= S.CAL_TERC[1] else 1)
                ys.append(float(Yx[t]))
            res[side] = _verdict(gs, ys)
        keep = S.CAL_RANK_W + 1
        res["wk"], res["u"], res["w"] = [cal[t] for t in h["t"][-keep:]], h["u"][-keep:], h["w"][-keep:]
        hz[k] = res
    return {"hist": hist, "votes": votes, "hz": hz}


def _verdict(gs: list[int], ys: list[float]) -> dict:
    """「多」（2）減「少」（0）兩組之後的比例，CAL_BLOCK 週一塊的循環區塊重抽 CAL_DRAWS 次（種子 CAL_SEED）的 95% 區間。"""
    names = ("lo", "mid", "hi")
    grp = {names[i]: [sum(y for g, y in zip(gs, ys) if g == i) / gs.count(i) if gs.count(i) else None, gs.count(i)] for i in range(3)}
    diff = lambda G_, Y_: (float(Y_[G_ == 2].mean() - Y_[G_ == 0].mean()) if (G_ == 2).any() and (G_ == 0).any() else None)
    g, y = np.asarray(gs, dtype=int), np.asarray(ys, dtype=float)
    out = {"g": grp, "all": [float(y.mean()) if len(y) else None, len(y)], "d": diff(g, y), "ci": None}
    if min(grp["lo"][1], grp["hi"][1]) < S.CAL_MIN_WEEKS:
        out["v"] = "few"
        return out
    rng = np.random.default_rng(S.CAL_SEED)            # 重抽的亂數順序要和網頁同一個（規格寫定的種子）
    n, L = len(y), S.CAL_BLOCK
    vals = []
    for _ in range(S.CAL_DRAWS):
        starts = rng.integers(0, n, size=n // L + 1)
        idx = np.asarray([(s + j) % n for s in starts for j in range(L)][:n])
        v = diff(g[idx], y[idx])
        if v is not None:
            vals.append(v)
    lo, hi = (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (None, None)
    out["ci"] = [lo, hi]
    out["v"] = "few" if lo is None else "rel" if lo > 0 else "rev" if hi < 0 else "none"
    return out


def check_thermo(F: dict) -> dict:
    """溫度計：網頁用的 thermocal（weekly 的每週票數、今年的票、market 的分組比例與重抽判定）和第二套 thermo2 比。
    項目鍵（同一個項目算一票）是命名規則，照 sigcat.item_key。"""
    from . import sigcat as G
    from . import thermocal as TC
    items = {sd["id"]: TC.item_of(sd) for sd in G.signals(F)}
    W, M, B = TC.weekly(F), TC.market(F), thermo2(F, items)
    bad = []
    for k in S.THERMO_H:
        for c in ("t", "u", "w"):
            a, b = W["hist"][k][c], B["hist"][k][c]
            if a != b:
                j = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                bad.append([k, f"每週票數 {c}", len(a), len(b), j])
        for side in ("up", "warn"):
            va, vb = M["hz"][k][side], B["hz"][k][side]
            diff = [f for f in ("all", "d", "ci", "v") if not _same(va.get(f), vb.get(f))]
            diff += [f"g.{g}" for g in ("lo", "mid", "hi") if not _same(va["g"][g], vb["g"][g])]
            if diff:
                bad.append([k, side, *diff])
    va = {sid: x["v"] for sid, x in (M.get("votes") or {}).items()}
    vb = {sid: x["v"] for sid, x in B["votes"].items()}
    if va != vb:
        bad.append(["今年的票", len(va), len(vb), sorted(set(va) ^ set(vb))[:5]])
    return {"mk": F["mk"], "n": sum(len(W["hist"][k]["t"]) for k in S.THERMO_H), "bad": bad}


def _madd(m: str, k: int) -> str:
    y, mm = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mm // 12:04d}-{mm % 12 + 1:02d}"


def _mdd(xs: list) -> float | None:
    """最大回撤（最高點到之後最低點的跌幅，0～1）；沒有值的跳過。"""
    pk, dd = None, 0.0
    for x in xs:
        if x is None or not x > 0:
            continue
        if pk is None or x > pk:
            pk = x
        else:
            dd = max(dd, 1.0 - x / pk)
    return None if pk is None else dd


def ind2(group: str, I: dict, T, last: str | None = None) -> list[dict]:
    """產業泡沫（第二套，同 sigcat.ind_rows）：每個產業每個月底在不在等級 L2／L3，連續在＝一段；之後 H_IND_M 個月的上漲、
    大回撤（≥ WARN_LONG）每一個月一樣重；次數＝段數；近 10 年＝段的第一個月在 last 往前 10 年以後；報酬表＝RET_H_M 個月；判定同第 3 節。
    等級本身（bubind.conditions）是輸入。"""
    from . import bubind as BI
    pan = []
    for code, Sx in I["S"].items():
        rows = BI.conditions(Sx, T)["rows"]
        j0 = next((j for j, r in enumerate(rows) if r["P1"] is not None and r["P2"] is not None), None)
        if j0 is not None:
            pan.append((code, Sx["me"], rows[j0:]))
    months = sorted({r["d"] for _, _, rows in pan for r in rows})
    if not months:
        return []
    r0m = _madd(last or months[-1], -12 * S.RECENT_YEARS)
    cost = S.ABS_COST["us" if group in ("ff", "us") else "tw"]
    mean = lambda v: (sum(v) / len(v)) if v else None
    out = []
    for k in S.IND_SIGNALS:
        lv = int(k[1])
        bu, bw, bd, b10u, b10w = [], [], [], [], []
        eps, worst, rgroups = [], [], []
        for code, me, rows in pan:
            seq = []
            for r in rows:
                m = r["d"]
                if r.get("L") is None or m not in me:
                    continue
                v0 = me[m]
                fut = [me.get(_madd(m, j)) for j in range(1, S.H_IND_M + 1)]
                if not v0 or any(v is None for v in fut):
                    u = w = dd = None
                else:
                    dd = _mdd([v0] + fut)
                    u, w = float(fut[-1] > v0), float(dd >= S.WARN_LONG)
                    bu.append(u), bw.append(w), bd.append(dd)
                    if m >= r0m:
                        b10u.append(u), b10w.append(w)
                seq.append((m, r["L"] >= lv, u, w, dd))
            i = 0
            while i < len(seq):
                if not seq[i][1]:
                    i += 1
                    continue
                j = i
                while j + 1 < len(seq) and seq[j + 1][1]:
                    j += 1
                ep = seq[i:j + 1]
                if any(x[2] is not None for x in ep):
                    eps.append((ep[0][0], [x[2] for x in ep if x[2] is not None], [x[3] for x in ep if x[3] is not None],
                                [x[4] for x in ep if x[4] is not None]))
                    worst += [(x[4], f"{x[0]} {code}") for x in ep if x[4] is not None]
                grp = []
                for x in ep:
                    v0, fut = me.get(x[0]), []
                    if not v0:
                        continue
                    smp = {}
                    for h in range(1, max(S.RET_H_M) + 1):
                        v = me.get(_madd(x[0], h))
                        if v is None:
                            break
                        fut.append(v)
                        if h in S.RET_H_M:
                            smp[h] = (fut[-1] / v0 - 1.0, min(0.0, min(fut) / v0 - 1.0), _mdd([v0] + fut), f"{x[0]} {code}")
                    grp.append(smp)
                rgroups.append(grp)
                i = j + 1
        dirs = {}
        for d, base, b10, idx in (("up", bu, b10u, 1), ("warn", bw, b10w, 2)):
            e10 = [e for e in eps if e[0] >= r0m]
            dirs[d] = {"n": len(eps), "hit": mean([y for e in eps for y in e[idx]]), "base": mean(base),
                       "n10": len(e10), "hit10": mean([y for e in e10 for y in e[idx]]), "base10": mean(b10)}
        cells = [_cell_rows([[smp[h] for smp in g if h in smp] for g in rgroups]) for h in S.RET_H_M]
        paths = []
        for h in S.RET_H_M:
            v = [smp[h][0] for g in rgroups for smp in g if h in smp]
            paths.append([_q(v, q) for q in S.RET_Q] if v else None)
        ret = {"s": cells, "p": paths}
        cell = cells[S.RET_H_M.index(S.H_IND_M)]
        for d in dirs:
            dirs[d]["tier"] = judge(dirs[d], d, cell, cost)
        dv = [v for e in eps for v in e[3]]
        dirs["warn"]["mdd"] = float(np.median(dv)) if dv else None
        dirs["warn"]["mdd_base"] = float(np.median(bd)) if bd else None
        if worst:
            b = max(v for v, _ in worst)
            dirs["warn"]["mddw"], dirs["warn"]["mddw_d"] = b, next(dd for v, dd in worst if v == b)
        order = {t: i for i, t in enumerate(S.TIERS)}
        edge = lambda st: (st["hit"] - st["base"]) if st["hit"] is not None and st["base"] is not None else -9.0
        ds = sorted(("up", "warn"), key=lambda d: (order[dirs[d]["tier"]], -edge(dirs[d])))
        top = dirs[ds[0]]["tier"]
        out.append({"id": f"ind:{group}:{k}", "up": dirs["up"], "warn": dirs["warn"], "tier": top,
                    "dir": [d for d in ds if dirs[d]["tier"] == "good"] if top == "good" else [ds[0]], "ret": ret})
    return out


def check_ind(groups: dict | None = None, T=None) -> dict:
    """產業泡沫：網頁用的 sigcat.ind_rows（打亂日子測試換成不算）和第二套 ind2 比。groups＝{組: bubind 的輸入}（沒給就讀資料，同 ind_all）。"""
    from . import bubind as BI
    from . import sigcat as G
    from . import sigluck as LK
    if groups is None:
        from . import bubble as BU
        T = BU.load_cv_table()
        L = BU.us_inputs(BU.load_us())["L"]
        groups = {"ff": BI.ff_inputs(L), "us": BI.us_inputs(L), "tw": BI.tw_inputs()}
    memo: dict = {}
    real_c, real_p = BI.conditions, LK.ind_p
    BI.conditions = lambda Sx, T_: memo.setdefault(id(Sx), real_c(Sx, T_))   # 等級是輸入：兩邊共用同一份
    LK.ind_p = lambda *a, **k: {}
    try:
        bad, n = [], 0
        for g, I in groups.items():
            if not I:
                continue
            A = {r["id"]: r for r in G.ind_rows(g, I, T)}
            for rb in ind2(g, I, T):
                n += 1
                ra = A.get(rb["id"])
                diff = ["網頁沒有這一列"] if ra is None else row_diff(ra, rb)
                if diff:
                    bad.append([rb["id"], *diff[:6]])
    finally:
        BI.conditions, LK.ind_p = real_c, real_p
    return {"n": n, "bad": bad}
