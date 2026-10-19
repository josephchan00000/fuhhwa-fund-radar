"""訊號總覽（docs/lab_signal_plan.md、arm/lab/sigspec.py）：把所有市場訊號依規格展開，算命中率、平常、判定與現在有沒有效。

研究：scripts/run_sig.py → data/lab/sig_research.json（資料或規格改了才重跑）。
每天建頁：frames() 由各頁已經算好的資料組成，now_market() 只算「現在有沒有效」。
"""
from __future__ import annotations

import bisect
import json
import math
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from . import sigspec as S

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "lab" / "sig_research.json"

CAT_NAMES = {"heat": "景氣項目", "multi": "景氣面向", "tech": "技術事件", "deriv": "邊際變化", "crash": "大跌風險",
             "bub": "泡沫", "ind": "產業泡沫", "buy": "大跌後買點", "stock": "個股訊號", "strat": "個股策略"}
TIER_ORDER = {t: i for i, t in enumerate(S.TIERS)}


def _arr(xs) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in xs], dtype=float)


def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _lst(a) -> list:
    """NaN → None（heatrel／hotdd 的事件函式用 None 表示沒有值）。"""
    return [None if _nan(float(v)) else float(v) for v in a]


# ── 結果 ─────────────────────────────────────────────────────────────────────

def warn_th(mk: str, H: int) -> float:
    from . import crashspec as CS
    return CS.TH[mk][S.WARN_TH_IDX[H]] if H in S.WARN_TH_IDX else S.WARN_LONG


def outcomes(px, H: int, th: float) -> tuple[np.ndarray, np.ndarray]:
    """第 t 天的訊號 → (偏多, 警示)：1／0，窗口不完整或沒有收盤＝NaN。
    e＝t＋LAG；偏多＝第 e＋H 天收盤 > 第 e 天；警示＝第 e＋1～e＋H 天任一天收盤 ≤ 第 e 天 ×（1 − th）。"""
    px = np.asarray(px, dtype=float)
    T = len(px)
    up = np.full(T, np.nan)
    wn = np.full(T, np.nan)
    n = T - S.LAG - H
    if n <= 0:
        return up, wn
    pe = px[S.LAG:S.LAG + n]
    pz = px[S.LAG + H:S.LAG + H + n]
    win = np.lib.stride_tricks.sliding_window_view(px[S.LAG + 1:], H)[:n]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mn = np.nanmin(win, axis=1)
    ok = ~np.isnan(pe) & ~np.isnan(pz) & ~np.isnan(mn)
    up[:n] = np.where(ok, (pz > pe).astype(float), np.nan)
    wn[:n] = np.where(ok, (mn <= pe * (1.0 - th)).astype(float), np.nan)
    return up, wn


# ── 次數、命中率、判定 ─────────────────────────────────────────────────────────

def recent_from(cal: list[str]) -> str:
    """資料最後一天往前 RECENT_YEARS 年（同月同日；2/29 改 2/28）。"""
    d = date.fromisoformat(cal[-1])
    try:
        return d.replace(year=d.year - S.RECENT_YEARS).isoformat()
    except ValueError:
        return d.replace(year=d.year - S.RECENT_YEARS, day=28).isoformat()


def dedupe(days, H: int) -> list[int]:
    """一次訊號之後 H 個交易日內再出現不算新的一次。"""
    out, last = [], None
    for t in sorted(days):
        if last is not None and t - last <= H:
            continue
        out.append(int(t))
        last = t
    return out


def _mean(xs) -> float | None:
    xs = [x for x in xs if not _nan(x)]
    return float(np.mean(xs)) if xs else None


def _base(Y: np.ndarray, samp: np.ndarray) -> float | None:
    v = Y[samp]
    v = v[~np.isnan(v)]
    return float(v.mean()) if len(v) else None


def ev_stat(days, Yu: np.ndarray, Yw: np.ndarray, samp: np.ndarray, H: int, r0: int) -> dict:
    """事件型：samp＝可以算平常的日子（輸入有值）索引；r0＝近 10 年起點的索引。
    → {"up": 統計, "warn": 統計, "occ": [[t, 偏多, 警示], …]}（只含窗口完整的次）。"""
    ok = set(int(i) for i in samp)
    kept = dedupe([t for t in days if t in ok], H)
    occ = [[t, Yu[t], Yw[t]] for t in kept if not (np.isnan(Yu[t]) or np.isnan(Yw[t]))]
    samp10 = samp[samp >= r0]
    out = {"occ": occ}
    for j, (dk, Y) in enumerate((("up", Yu), ("warn", Yw))):
        ys = [o[1 + j] for o in occ]
        ys10 = [o[1 + j] for o in occ if o[0] >= r0]
        out[dk] = {"n": len(ys), "hit": _mean(ys), "base": _base(Y, samp),
                   "n10": len(ys10), "hit10": _mean(ys10), "base10": _base(Y, samp10)}
    return out


def episodes(pos: list[int], gap: int) -> list[list[int]]:
    """pos＝狀態中的樣本在樣本序列裡的位置（遞增）→ 每一段的位置；中斷的樣本數 < gap 算同一段。"""
    out: list[list[int]] = []
    for p in pos:
        if out and p - out[-1][-1] - 1 < gap:
            out[-1].append(p)
        else:
            out.append([p])
    return out


def st_stat(state: np.ndarray, samp: np.ndarray, Yu: np.ndarray, Yw: np.ndarray, gap: int, r0: int) -> dict:
    """狀態型：samp＝樣本日（輸入有值；月資料＝每月最後一個交易日）索引，state＝這些樣本日是否在狀態中（同長度）。
    一段的命中率＝段內窗口完整的日子的比例；整體＝各段平均。→ {"up", "warn", "occ": [[第一天, 最後一天, 天數, 偏多, 警示], …]}。"""
    pos = [i for i in range(len(samp)) if state[i]]
    occ = []
    for ep in episodes(pos, gap):
        ts = samp[ep]
        u, w = Yu[ts], Yw[ts]
        m = ~np.isnan(u) & ~np.isnan(w)
        if not m.any():
            continue
        occ.append([int(ts[0]), int(ts[-1]), int(len(ts)), float(u[m].mean()), float(w[m].mean())])
    samp10 = samp[samp >= r0]
    out = {"occ": occ}
    for j, (dk, Y) in enumerate((("up", Yu), ("warn", Yw))):
        ys = [o[3 + j] for o in occ]
        ys10 = [o[3 + j] for o in occ if o[0] >= r0]
        out[dk] = {"n": len(ys), "hit": _mean(ys), "base": _base(Y, samp),
                   "n10": len(ys10), "hit10": _mean(ys10), "base10": _base(Y, samp10)}
    return out


def tier(st: dict, d: str, recent: bool = True) -> str:
    """規劃第 3.2 節（sigspec 第 3 節）。用沒有四捨五入的數字。"""
    n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
    if n < S.N_MIN or hit is None or base is None:
        return "few"
    edge = hit - base
    good = hit >= S.HIT_MIN[d] and edge >= S.EDGE_GOOD
    if good and recent and (st.get("n10") or 0) >= S.RECENT_N:
        h10, b10 = st.get("hit10"), st.get("base10")
        good = h10 is not None and b10 is not None and h10 >= S.HIT_MIN[d] and h10 - b10 >= S.EDGE_GOOD
    if good:
        return "good"
    return "ref" if edge >= S.EDGE_REF else "none"


def best(dirs: dict) -> tuple[str, list[str]]:
    """這一列的判定＝各方向裡較好的（同級取差大的）；兩個方向都是 ★ 就兩個都列。"""
    def key(d):
        st = dirs[d]
        e = (st["hit"] - st["base"]) if st.get("hit") is not None and st.get("base") is not None else -9
        return (TIER_ORDER[st["tier"]], -e)
    ds = sorted(dirs, key=key)
    top = dirs[ds[0]]["tier"]
    return top, ([d for d in ds if dirs[d]["tier"] == "good"] if top == "good" else [ds[0]])


# ── 市場資料 ─────────────────────────────────────────────────────────────────

def _names(HS) -> dict:
    return {k: nm for k, _, nm, *_ in HS.IND}


def frame(mk: str, B: dict, I: dict, IB: dict | None = None, BX: dict | None = None) -> dict:
    """一個市場的訊號資料（美股要在 heatspec.use(該指數) 裡呼叫）：
    B＝景氣頁的 build、I＝crash 的輸入（日曆、收盤、W1～W4／VOL）、IB＝bottom 的輸入、BX＝bubble.compute()。"""
    from . import crash as CR
    from . import heatpage as HP
    from . import heatpos as P
    from . import heatspec as HS
    cal = list(I["cal"])
    px = np.asarray(I["px"], dtype=float)
    nm = _names(HS)
    dims = list(HP.shown_dims())
    V = []
    for d in dims:
        V.append({"key": "D" + d, "name": HS.DIMS[d]["name"], "grp": d, "H": S.H_DIM[d],
                  "x": CR.align(cal, B["cal"], B["comp"][d])})
        for k in HS.ITEMS[d]:
            V.append({"key": k, "name": nm[k], "grp": d, "H": S.H_DIM[d],
                      "x": CR.align(cal, B["cal"], B["hc"].get(k) or [None] * len(B["cal"]))})
    CV = []
    from . import crashspec as CS
    for k in S.CRASH_VARS[mk]:
        if k in I["x"]:
            CV.append({"key": k, "name": CS.PRED_NAMES[k], "grp": "crash", "H": S.H_CRASH, "x": np.asarray(I["x"][k], float)})
    comp = {d: CR.align(cal, B["cal"], B["comp"][d]) for d in dims}
    DV = []
    for k in HS.DERIV:
        st = P.deriv(B, k)["state"]
        x = CR.align(cal, B["cal"], [None if s in (None, 0) else float(s) for s in st])
        flat = CR.align(cal, B["cal"], [None if s is None else float(s) for s in st])
        DV.append({"key": k, "name": nm[k], "kind": HS.DERIV[k]["kind"], "x": x, "have": ~np.isnan(flat)})
    rows = ((BX or {}).get(mk) or {}).get("_C", {}).get("rows") or []
    return {"mk": mk, "cal": cal, "px": px, "we": P.week_ends(cal), "vars": V, "cvars": CV, "comp": comp, "dims": dims,
            "deriv": DV, "deriv_words": dict(HS.DERIV_WORDS), "bub": rows, "IB": IB, "r0": recent_from(cal)}


def frames(BT: dict | None = None, BA: dict | None = None, BX: dict | None = None) -> dict:
    """五個市場（研究用；每天建頁由各頁自己組 frame）。"""
    from . import bottom as BO
    from . import bubble as BU
    from . import crash as CR
    from . import heatcalc as HC
    from . import heatcalc_us as HU
    from . import heatdata as HD
    from . import heatspec as HS
    from . import heatspec_us as U
    BX = BX if BX is not None else BU.compute()
    BT = BT if BT is not None else HC.build()
    IT = CR.tw_inputs(B=BT, BX=BX)
    F = {"tw": frame("tw", BT, IT, BO.inputs_tw(BT, IT, BX), BX)}
    BA = BA if BA is not None else HU.build_all()
    for idx in U.INDEX_ORDER:
        with HS.use(U.spec_for(idx)):
            I0 = CR.us_inputs(idx, Bu=BA[idx], BX=BX)
            from . import bottomspec as BS
            vol = HD.load(f"us_vol_{idx}") if "C7" in BS.SIG_MK[idx] else None
            F[idx] = frame(idx, BA[idx], I0, BO.inputs_us(idx, BA[idx], I0, vol, BX), BX)
    return F


# ── 訊號展開 ─────────────────────────────────────────────────────────────────

def _var_signals(F: dict, v: dict, cat: str) -> list[dict]:
    """景氣項目／面向／大跌風險項目的 6 種。"""
    from . import hotch as HCH
    from . import hotdd as HDD
    from .heatrel import heat_events
    x = v["x"]
    T = len(x)
    have = ~np.isnan(x)
    samp = np.nonzero(have)[0]
    xl = _lst(x)
    out = []
    for sg in S.VARIANTS:
        kind = S.VARIANT_KIND[sg]
        sd = {"id": f"{F['mk']}:{cat}:{v['key']}:{sg}", "cat": cat, "grp": v["grp"], "var": v["key"], "vn": v["name"],
              "sig": sg, "name": f"{v['name']}・{S.VARIANT_NAMES[sg]}", "kind": kind, "H": v["H"], "samp": samp}
        if sg == "hot":
            sd["state"] = x[samp] >= S.HOT
        elif sg == "cold":
            sd["state"] = x[samp] < S.COLD
        elif sg == "hot13":
            w = HCH.streak_days(xl, F["we"])
            sd["state"] = np.array([(w[i] or 0) >= S.HOT_WEEKS for i in samp], dtype=bool)
        elif sg == "hot_in":
            sd["days"] = heat_events(xl, "hot")
        elif sg == "cold_in":
            sd["days"] = heat_events(xl, "cold")
        elif sg == "hot_out":
            sd["days"] = HDD.exits(xl, F["we"], S.EXIT_MIN)
        out.append(sd)
    return out


def signals(F: dict) -> list[dict]:
    """一個市場的全部市場層級訊號定義（不含結果）。"""
    from . import heatspec as HS
    from . import heattech as TT
    from . import hotdd as HDD
    mk, cal, px = F["mk"], F["cal"], F["px"]
    T = len(cal)
    out: list[dict] = []
    for v in F["vars"]:
        out += _var_signals(F, v, "heat")
    for v in F["cvars"]:
        out += _var_signals(F, v, "crash")
    # 同時兩個以上面向過熱
    dims = F["dims"]
    hot = np.zeros(T, dtype=int)
    have = np.zeros(T, dtype=int)
    for d in dims:
        c = F["comp"][d]
        hot += (~np.isnan(c) & (np.nan_to_num(c, nan=-1) >= S.HOT)).astype(int)
        have += (~np.isnan(c)).astype(int)
    samp = np.nonzero(have >= S.MULTI_MIN_DIMS)[0]
    base = {"cat": "multi", "grp": "multi", "var": "M2", "vn": "同時兩個以上面向過熱", "H": S.H_MULTI, "samp": samp}
    out.append({**base, "id": f"{mk}:multi:M2:hot", "sig": "hot", "name": "同時兩個以上面向過熱中", "kind": "state",
                "state": hot[samp] >= S.MULTI_K})
    comp = {d: _lst(F["comp"][d]) for d in dims}
    out.append({**base, "id": f"{mk}:multi:M2:hot_in", "sig": "hot_in", "name": "進入同時兩個以上面向過熱", "kind": "event",
                "days": HDD.multi(comp, dims, S.MULTI_K)})
    # 技術事件
    ev = TT.all_events([None if _nan(p) else float(p) for p in px])
    samp = np.arange(S.EV_START, T)
    for k, nm in HS.EVENTS.items():
        out.append({"id": f"{mk}:tech:{k}", "cat": "tech", "grp": "tech", "var": k, "vn": nm, "sig": "ev", "name": nm,
                    "kind": "event", "H": S.H_TECH, "samp": samp, "days": [t for t in ev[k] if t >= S.EV_START]})
    # 邊際變化
    for v in F["deriv"]:
        samp = np.nonzero(v["have"])[0]
        words = F["deriv_words"][v["kind"]]
        for s in S.DERIV_STATES:
            out.append({"id": f"{mk}:deriv:{v['key']}:{s}", "cat": "deriv", "grp": "deriv", "var": v["key"], "vn": v["name"],
                        "sig": str(s), "name": f"{v['name']}・{words[s - 1]}", "kind": "state", "H": S.H_DERIV,
                        "samp": samp, "state": v["x"][samp] == s})
    # 泡沫（每月最後一個交易日一個樣本；只用已經過完的月份）
    from . import crash as CR
    me = CR.month_ends(cal)
    done = CR.complete_months(cal)
    rows = [r for r in F["bub"] if str(r.get("d"))[:7] in done and str(r.get("d"))[:7] in me]
    for k in S.BUB_SIGNALS:
        val = []
        for r in rows:
            if k in ("L2", "L3"):
                L = r.get("L")
                val.append((me[str(r["d"])[:7]], None if L is None else L >= int(k[1])))
            else:
                f = r.get(k)
                val.append((me[str(r["d"])[:7]], None if f is None else bool(f)))
        val = [(i, f) for i, f in val if f is not None]
        if not val:
            continue
        samp = np.array([i for i, _ in val], dtype=np.int64)
        out.append({"id": f"{mk}:bub:{k}", "cat": "bub", "grp": "bub", "var": k, "vn": S.BUB_NAMES[k], "sig": k,
                    "name": S.BUB_NAMES[k], "kind": "state", "H": S.H_BUB, "samp": samp, "monthly": True,
                    "state": np.array([f for _, f in val], dtype=bool)})
    return out


def evaluate(F: dict, sd: dict, Ycache: dict) -> dict:
    """一個訊號 → 一列（含每一次）。"""
    mk, cal = F["mk"], F["cal"]
    H = sd["H"]
    if H not in Ycache:
        Ycache[H] = outcomes(F["px"], H, warn_th(mk, H))
    Yu, Yw = Ycache[H]
    r0 = bisect.bisect_left(cal, F["r0"])
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if sd["kind"] == "event":
        R = ev_stat(sd["days"], Yu, Yw, samp, H, r0)
        occ = [[cal[t], int(u), int(w)] for t, u, w in R["occ"]]
    else:
        gap = 1 if sd.get("monthly") else S.EP_GAP
        R = st_stat(np.asarray(sd["state"], dtype=bool), samp, Yu, Yw, gap, r0)
        occ = [[cal[a], cal[z], n, u, w] for a, z, n, u, w in R["occ"]]
    dirs = {}
    for d in ("up", "warn"):
        st = R[d]
        st["tier"] = tier(st, d)
        dirs[d] = st
    tr, ds = best(dirs)
    row = {k: sd[k] for k in ("id", "cat", "grp", "var", "vn", "sig", "name", "kind", "H")}
    row.update({"mk": mk, "th": warn_th(mk, H), "a": cal[int(samp[0])] if len(samp) else None,
                "z": cal[int(samp[-1])] if len(samp) else None, "up": dirs["up"], "warn": dirs["warn"],
                "tier": tr, "dir": ds, "occ": occ})
    if sd.get("monthly"):
        row["monthly"] = True
    return row


# ── 大跌後買點（bottomspec VER 3） ─────────────────────────────────────────────

def buy_rows(F: dict) -> list[dict]:
    """兩種大跌 × 規則：命中＝買在這一波的相對低點；平常＝同一批事件固定等 10 天（固定等 10 天＝事件隔天買）。"""
    from . import bottom as BO
    from . import bottomspec as BS
    I = F["IB"]
    if not I:
        return []
    mk, cal = F["mk"], F["cal"]
    out = []
    for ev in BS.EVENTS:
        recs = BO.event_recs(I, ev)
        for k in ("W10",) + tuple(BS.SIG_MK[mk]):
            base = "b1" if k == "W10" else BS.SIG_BASE
            rows = BO._lp_rows(recs, k, base)
            occ = [[cal[t], int(o["lp"]), int(ob["lp"])] for t, o, ob, _ in rows]
            r10 = [o for o in occ if o[0] >= F["r0"]]
            st = {"n": len(occ), "hit": _mean([o[1] for o in occ]), "base": _mean([o[2] for o in occ]),
                  "n10": len(r10), "hit10": _mean([o[1] for o in r10]), "base10": _mean([o[2] for o in r10])}
            st["tier"] = tier(st, "buy")
            r60 = [o.get("r60") for t, o, _, _ in rows]
            out.append({"id": f"{mk}:buy:{ev}:{k}", "mk": mk, "cat": "buy", "grp": ev, "var": k,
                        "vn": BS.RULE_NAMES[k], "sig": ev, "kind": "event", "H": None,
                        "name": f"{BS.EVENT_NAMES[ev]}・{BS.RULE_NAMES[k]}",
                        "base_name": "事件隔天就買" if k == "W10" else "固定等 10 天",
                        "a": occ[0][0] if occ else None, "z": occ[-1][0] if occ else None,
                        "buy": st, "tier": st["tier"], "dir": ["buy"], "occ": occ,
                        "up60": _mean([1.0 if (r or 0) > 0 else 0.0 for r in r60 if r is not None])})
    return out


# ── 產業泡沫 ─────────────────────────────────────────────────────────────────

def _months_add(m: str, k: int) -> str:
    y, mm = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mm // 12:04d}-{mm % 12 + 1:02d}"


def ind_rows(group: str, I: dict, T: dict, last: str | None = None) -> list[dict]:
    """一組產業（bubind 的輸入）：每個產業各自分段、全部合併。"""
    from . import bubind as BI
    from . import bubindspec as BIS
    pan = []
    for code, Sx in I["S"].items():
        C = BI.conditions(Sx, T)
        rows = C["rows"]
        j0 = next((j for j, r in enumerate(rows) if r["P1"] is not None and r["P2"] is not None), None)
        if j0 is None:
            continue
        pan.append((code, Sx["me"], rows[j0:]))
    months_all = sorted({r["d"] for _, _, rows in pan for r in rows})
    if not months_all:
        return []
    zl = last or months_all[-1]
    r0m = _months_add(zl, -12 * S.RECENT_YEARS)
    out = []
    for k in S.IND_SIGNALS:
        lv = int(k[1])
        occ, base_u, base_w, b10u, b10w = [], [], [], [], []
        for code, me, rows in pan:
            seq = []
            for r in rows:
                m = r["d"]
                if r.get("L") is None or m not in me:
                    continue
                v0 = me[m]
                fut = [me.get(_months_add(m, j)) for j in range(1, S.H_IND_M + 1)]
                if not v0 or any(v is None for v in fut):
                    u = w = None
                else:
                    u = 1.0 if fut[-1] > v0 else 0.0
                    w = 1.0 if min(fut) <= v0 * (1.0 - S.WARN_LONG) else 0.0
                seq.append((m, r["L"] >= lv, u, w))
                if u is not None:
                    base_u.append(u)
                    base_w.append(w)
                    if m >= r0m:
                        b10u.append(u)
                        b10w.append(w)
            pos = [i for i, s in enumerate(seq) if s[1]]
            for ep in episodes(pos, 1):
                us = [seq[i][2] for i in ep if seq[i][2] is not None]
                ws = [seq[i][3] for i in ep if seq[i][3] is not None]
                if us:
                    occ.append([seq[ep[0]][0], seq[ep[-1]][0], len(ep), float(np.mean(us)), float(np.mean(ws)), code])
        occ.sort(key=lambda o: (o[0], o[5]))
        dirs = {}
        for j, (d, bs, b10) in enumerate((("up", base_u, b10u), ("warn", base_w, b10w))):
            ys = [o[3 + j] for o in occ]
            ys10 = [o[3 + j] for o in occ if o[0] >= r0m]
            st = {"n": len(ys), "hit": _mean(ys), "base": _mean(bs), "n10": len(ys10), "hit10": _mean(ys10),
                  "base10": _mean(b10)}
            st["tier"] = tier(st, d)
            dirs[d] = st
        tr, ds = best(dirs)
        gname = BIS.GROUP_NAMES[group] if hasattr(BIS, "GROUP_NAMES") else group
        out.append({"id": f"ind:{group}:{k}", "mk": "us" if group in ("ff", "us") else "tw", "cat": "ind", "grp": group,
                    "var": k, "vn": gname, "sig": k, "name": f"{gname}・{S.BUB_NAMES[k]}", "kind": "state",
                    "H": S.H_IND_M, "monthly": True, "th": S.WARN_LONG, "a": occ[0][0] if occ else None, "z": zl,
                    "up": dirs["up"], "warn": dirs["warn"], "tier": tr, "dir": ds, "occ": occ})
    return out


def ind_all() -> list[dict]:
    from . import bubble as BU
    from . import bubind as BI
    T = BU.load_cv_table()
    if not T:
        return []
    L = BU.us_inputs(BU.load_us())["L"]
    out = []
    for g, fn in (("ff", lambda: BI.ff_inputs(L)), ("us", lambda: BI.us_inputs(L)), ("tw", BI.tw_inputs)):
        I = fn()
        if I:
            out += ind_rows(g, I, T)
    return out


# ── 研究 ─────────────────────────────────────────────────────────────────────

def market(F: dict) -> list[dict]:
    Yc: dict = {}
    rows = [evaluate(F, sd, Yc) for sd in signals(F)]
    return rows + buy_rows(F)


def _r(x):
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(x) or math.isinf(x) else float(f"{float(x):.4g}")
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, dict):
        return {a: _r(b) for a, b in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(b) for b in x]
    return x


def research(F: dict | None = None, with_ind: bool = True) -> dict:
    F = F if F is not None else frames()
    rows = []
    for mk in S.MARKETS:
        if mk in F:
            rows += market(F[mk])
    if with_ind:
        rows += ind_all()
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": {mk: F[mk]["cal"][-1] for mk in F}, "rows": _r(rows)}


def save_research(R: dict) -> None:
    RESEARCH.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load_research() -> dict | None:
    try:
        R = json.loads(RESEARCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None


_RCACHE: dict = {}


def research_rows() -> list[dict]:
    """研究檔的列（同一個程序裡只讀一次：五個景氣頁與訊號總覽共用）。"""
    if "rows" not in _RCACHE:
        _RCACHE["rows"] = (load_research() or {}).get("rows") or []
    return _RCACHE["rows"]


def today_for(now: dict | None) -> dict | None:
    """景氣頁「今天的重點」：now＝now_for_B 的結果；研究檔沒有就回 None。"""
    rows = research_rows()
    if not now or not rows:
        return None
    return {"mk": now["mk"], "d": now["d"], **today(rows, now["on"], now["mk"])}


# ── 現在有沒有效（每天建頁） ───────────────────────────────────────────────────

def now_market(F: dict) -> dict:
    """一個市場 → {訊號 id: {"since": 開始日, "n": 已經幾天（月資料＝幾個月）, "left": 事件型剩幾天}}，只列現在有效的。
    狀態型＝資料最後一天在狀態中（月資料＝最後一個過完的月份）；事件型＝最近一次出現在最後 H 個交易日內；
    買點＝目前一段大跌（bottom.now 進行中）之後已經出現。"""
    cal = F["cal"]
    T = len(cal)
    out: dict = {}
    for sd in signals(F):
        samp = np.asarray(sd["samp"], dtype=np.int64)
        if sd["kind"] == "state":
            st = np.asarray(sd["state"], dtype=bool)
            if not len(samp) or not st[-1]:
                continue
            if not sd.get("monthly") and samp[-1] != T - 1:
                continue
            gap = 1 if sd.get("monthly") else S.EP_GAP
            ep = episodes([i for i in range(len(samp)) if st[i]], gap)[-1]
            out[sd["id"]] = {"since": cal[int(samp[ep[0]])], "n": len(ep)}
        else:
            ds = [t for t in sd["days"] if t >= (samp[0] if len(samp) else 0)]
            if ds and T - 1 - ds[-1] < sd["H"]:
                out[sd["id"]] = {"since": cal[ds[-1]], "n": T - 1 - ds[-1], "left": sd["H"] - (T - 1 - ds[-1])}
    I = F.get("IB")
    if I:
        from . import bottom as BO
        Nw = BO.now(I)
        for a in Nw.get("active") or []:
            evs = (a["ev"],) + ((a["also"],) if a.get("also") else ())
            sigs = {"W10": a.get("w10") or {}, **(a.get("sig") or {})}
            for k, v in sigs.items():
                if v.get("st") == "on":
                    for ev in evs:
                        out[f"{F['mk']}:buy:{ev}:{k}"] = {"since": v["d"], "event": a["t"]}
    return out


def edge(st: dict | None) -> float | None:
    if not st or st.get("hit") is None or st.get("base") is None:
        return None
    return st["hit"] - st["base"]


def today(rows: list[dict], on: dict, mk: str) -> dict:
    """景氣頁「今天的重點」（sigspec 第 5 節）：這個市場現在有效的 ★，同一個變數只留差最大的一種，依差排序、最多 TODAY_MAX 列；
    沒有 ★ 時列 ● 前 TODAY_REF 列。→ {"good": [...], "ref": [...]}（每列＝研究列＋現在的狀態＋方向＋差）。"""
    def pick(tr: str) -> list[dict]:
        best_by: dict = {}
        for r in rows:
            if r.get("mk") != mk or r["tier"] != tr or r["id"] not in on:
                continue
            for d in r["dir"]:
                e = edge(r.get(d))
                if e is None:
                    continue
                key = (r["cat"], r["var"])
                if key not in best_by or e > best_by[key]["edge"]:
                    best_by[key] = {**r, "d": d, "edge": e, "now": on[r["id"]]}
        return sorted(best_by.values(), key=lambda x: (-x["edge"], x["id"]))
    g = pick("good")[:S.TODAY_MAX]
    return {"good": g, "ref": [] if g else pick("ref")[:S.TODAY_REF]}


# ── 每天建頁：景氣頁的 B → 這個市場現在有沒有效（存在程序裡給訊號總覽沿用） ──────────

NOW: dict = {}                                       # {市場: {"d": 資料最後一天, "on": now_market(...)}}


def frame_from_B(B: dict) -> dict | None:
    """景氣頁的 B（heatcalc.build／heatcalc_us.build；美股要在 heatspec.use(該指數) 裡呼叫）→ frame。
    做法同 bottompage.state：泡沫用 bubble.market_for、台股融資 ÷ 市值用 crash.tw_inputs 現算。"""
    from . import bottom as BO
    from . import bottomspec as BS
    from . import bubble as BU
    from . import crash as CR
    from . import heatdata as HD
    mk = B.get("idx") or "tw"
    if mk not in S.MARKETS or not B.get("cal") or B.get("D") is None:
        return None
    BX = {mk: BU.market_for(mk, B["D"])}
    if mk == "tw":
        D = dict(B["D"])
        for n in ("twcap", "twmgn", "taiex90"):
            if n not in D:
                D[n] = HD.load(n)
        D["_tsmc"] = CR._tsmc_month(None)
        I = CR.tw_inputs(D=D, B=B, BX=BX)
        IB = BO.inputs_tw(B=B, IT=I, BX=BX)
    else:
        I = CR.us_inputs(mk, Bu=B, BX=BX)
        vol = HD.load(f"us_vol_{mk}") if "C7" in BS.SIG_MK[mk] else None
        IB = BO.inputs_us(mk, B, I, vol, BX)
    if not len(I["cal"]):
        return None
    return frame(mk, B, I, IB, BX)


def now_for_B(B: dict) -> dict | None:
    """景氣頁建頁時呼叫：算這個市場現在有效的訊號，存進 NOW（訊號總覽沿用）。失敗回 None、不擋景氣頁。"""
    try:
        F = frame_from_B(B)
        if F is None:
            return None
        NOW[F["mk"]] = {"mk": F["mk"], "d": F["cal"][-1], "on": now_market(F)}
        return NOW[F["mk"]]
    except Exception as e:                            # noqa: BLE001
        print(f"[訊號總覽] 現在的狀態算不出來：{type(e).__name__}: {e}")
        return None


# ── 個股訊號與策略（籌碼雷達建頁時算，寫 data/lab/sig_stock.json 給訊號總覽） ─────────────

STOCK = ROOT / "data" / "lab" / "sig_stock.json"


def stock_signal_rows(D, sig_hist: dict, idx: list, io: list) -> list[dict]:
    """籌碼雷達 8 種訊號（sigspec 第 4.8 節）：同一檔 DEDUP 日內重複只算一次（同 backtest.signal_stats）；
    t＋1 開盤買、第 t＋H_STOCK 天收盤賣。"""
    from . import analyze as AN
    from . import backtest as BT
    H = S.H_STOCK
    cal = list(D.cal)
    T = len(cal)
    cache: dict = {}
    out = []
    for k, (nm, desc) in AN.SIG_DEF.items():
        d = "warn" if k in S.STOCK_WARN else "up"
        occ = []
        live = []
        for code, hist in sig_hist.items():
            fired = [i for i, day in enumerate(hist) if k in day]
            if not fired:
                continue
            Sx = cache.get(code) or D.series(code)
            cache[code] = Sx
            last = -999
            for t in fired:
                if t - last <= BT.DEDUP:
                    last = t
                    continue
                last = t
                if t == T - 1:
                    live.append(code)
                r = BT._ret(Sx, idx, t, H, io)
                if not r:
                    continue
                gross = r["r"] + BT.COST
                mkr = r["r"] - r["x"]
                hit = (r["r"] > 0) if d == "up" else (gross < 0)
                bh = (mkr > 0) if d == "up" else (mkr < 0)
                occ.append([cal[t], code, int(hit), int(bh), round(100 * r["r"], 2)])
        occ.sort()
        st = {"n": len(occ), "hit": _mean([o[2] for o in occ]), "base": _mean([o[3] for o in occ]),
              "n10": None, "hit10": None, "base10": None}
        st["tier"] = tier(st, d, recent=False)
        out.append({"id": f"stk:sig:{k}", "mk": "stk", "cat": "stock", "grp": "stock", "var": k, "vn": nm, "sig": k,
                    "name": nm, "desc": desc, "kind": "event", "H": H, d: st, "tier": st["tier"], "dir": [d],
                    "a": occ[0][0] if occ else None, "z": cal[-1], "occ": occ, "live": sorted(set(live)),
                    "avg": _mean([o[4] for o in occ])})
    return out


def _strat_tier(pay: dict, n: int) -> str:
    if n < S.STRAT_N_MIN:
        return "few"
    if pay.get("ok"):
        return "good"
    return "ref" if (pay.get("avg") or 0) > 0 else "none"


def strat_rows(adv: dict, bt3r: dict | None = None) -> list[dict]:
    """個股策略（sigspec 第 4.9 節）：有逐筆紀錄的（機會頁那幾條）用全部已出場交易算報酬型態；
    回測方法 v3 其他版本（整組）沒有逐筆紀錄，用研究檔的樣本內、樣本外報酬型態（兩段都過才 ★）。"""
    from . import bt3
    from . import trades as TR
    out = []
    names = {g["k"]: g for g in (adv.get("grades3") or [])}
    I = {c: i for i, c in enumerate(TR.TR_COLS)}
    for k, v in (adv.get("trades") or {}).items():
        tr = ((v.get("res") or {}).get("tr")) or []
        rows = [r for r in tr if len(r) > I["hd"] and r[I["st"]] == "c" and r[I["r"]] is not None and r[I["hd"]]]
        units = [{"r": r[I["r"]], "hd": r[I["hd"]]} for r in rows]
        pay = bt3.payoff(units)
        mk = [r[I["mk"]] for r in rows if r[I["mk"]] is not None]
        g = names.get(k) or {}
        st = {"n": pay.get("n", 0), "hit": None if not pay.get("n") else pay["win"] / 100.0,
              "base": _mean([1.0 if m > 0 else 0.0 for m in mk]), "n10": None, "hit10": None, "base10": None}
        tr_ = _strat_tier(pay, st["n"])
        st["tier"] = tr_
        out.append({"id": f"stk:strat:{k}", "mk": "stk", "cat": "strat", "grp": "strat", "var": k,
                    "vn": g.get("name") or k, "sig": k, "name": g.get("name") or k, "desc": g.get("kind"),
                    "kind": "trade", "H": None, "up": st, "tier": tr_, "dir": ["up"], "pay": pay, "old": g.get("grade"),
                    "unit": v.get("unit"), "a": None, "z": None, "occ": []})
    for row in ((bt3r or {}).get("rows") or []):
        k = row.get("k")
        if not k or k in names:
            continue
        ins, oos = row.get("ins") or {}, row.get("oos") or {}
        n = (ins.get("n") or 0) + (oos.get("n") or 0)
        ok = bool(ins.get("pay_ok")) and (not oos.get("n") or bool(oos.get("pay_ok")))
        avg = _mean([x for x in ((ins.get("m"), oos.get("m")) if oos.get("n") else (ins.get("m"),)) if x is not None])
        tr_ = "few" if n < S.STRAT_N_MIN else ("good" if ok else ("ref" if (avg or 0) > 0 else "none"))
        bname = {"L": "大型股", "M": "中型股"}.get(row.get("b"), "")
        nm = f"{row.get('name')}（{bname}・整組）"
        win = _mean([x for x in (ins.get("win"), oos.get("win")) if x is not None])
        st = {"n": n, "hit": None if win is None else win / 100.0, "base": None, "n10": None, "hit10": None,
              "base10": None, "tier": tr_}
        out.append({"id": f"stk:strat:{k}", "mk": "stk", "cat": "strat", "grp": "strat", "var": k, "vn": nm, "sig": k,
                    "name": nm, "desc": "回測方法 v3 研究版本（同一批股票全部買）", "kind": "trade", "H": None, "up": st,
                    "tier": tr_, "dir": ["up"], "old": row.get("grade"), "unit": row.get("unit"),
                    "pay": {"ins": {x: ins.get(x) for x in ("n", "win", "ratio", "m", "pay_ok")},
                            "oos": {x: oos.get(x) for x in ("n", "win", "ratio", "m", "pay_ok")}},
                    "a": ins.get("d0"), "z": oos.get("d1") or ins.get("d1"), "occ": []})
    return out


def write_stock(data: dict, ctx: dict, path: Path | None = None) -> bool:
    """籌碼雷達建頁後呼叫（page.build）：個股訊號＋策略 → data/lab/sig_stock.json（內容沒變不改寫）。
    個股訊號或機會頁的策略任一個算不出來就不寫（不拿殘缺的資料蓋掉前一版）。"""
    path = path or STOCK
    if ctx.get("D") is None or not ((data.get("adv") or {}).get("trades")):
        return False
    rows = []
    try:
        rows += stock_signal_rows(ctx["D"], ctx["sig_hist"], ctx["taiex"], ctx["D"].taiex_open())
    except Exception as e:                            # noqa: BLE001
        print(f"[訊號總覽] 個股訊號算不出來：{type(e).__name__}: {e}")
        return False
    try:
        bt3r = json.loads((ROOT / "data" / "lab" / "bt3_research.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bt3r = None
    try:
        rows += strat_rows(data.get("adv") or {}, bt3r)
    except Exception as e:                            # noqa: BLE001
        print(f"[訊號總覽] 個股策略算不出來：{type(e).__name__}: {e}")
        return False
    txt = json.dumps({"ver": S.VER, "d": list(ctx["D"].cal)[-1] if ctx.get("D") is not None else None,
                      "rows": _r(rows)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == txt:
        return False
    path.write_text(txt, encoding="utf-8")
    return True


def load_stock() -> dict | None:
    try:
        R = json.loads(STOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None
