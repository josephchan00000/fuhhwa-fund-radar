"""交易計畫（planspec VER 1；docs/lab_practical_plan.md 第 13 節）：上網頁條件過了的兩條寫成照著做的說明，加上事先定好的前瞻檢查。

  year_range(bh, nav)              研究期間照做一年（52 週）的報酬分布（照做、一直抱著）
  windows(bh, nav, w)              研究週序列每一週起算、w 週的窗口：一直抱著 x、照做 y（ln）
  same_market(x, y, bh, nav, n)    前瞻 n 個交易日的 (x, y) 和過去同樣行情比 → 位置 p 與狀態
  fut_episodes(cal, r, dr, a, s0, b) 每一段加碼的期貨部位累積盈虧（最低點、結束）、最差的一天
  live_def／live_atk               前瞻淨值（照做、一直抱著）
  market(mk, ...)／build()          頁面資料（策略頁「總經策略」這一期最上面）

全部從研究檔（practsim_research.json、tilt_research.json）、前瞻紀錄（practsim_live.json）與 xstrat 的價格算，不另存研究檔。
規則、成本、時點都是原本的（practspec、tiltspec、xstratspec），這裡只整理與檢查。只描述照規則做的結果，不寫買賣建議。
"""
from __future__ import annotations

import bisect
import math

import numpy as np

from . import planspec as S
from . import practlive as PL
from . import practsim as P
from . import tilt as TL
from . import tiltspec as TS
from . import xstrat as XT
from . import xstratspec as XS


def _r(v, k: int = 6):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), k)


def weeks(n: int) -> int:
    """前瞻 n 個交易日 ↔ 研究週序列幾週（四捨五入，至少 1）。"""
    return max(1, int(math.floor(n / S.WEEK_DAYS + 0.5)))


# ── 研究週序列 ────────────────────────────────────────────────────────────────

def weekly(plan: str, mk: str, PR: dict | None, TR: dict | None) -> tuple[list, np.ndarray, np.ndarray] | None:
    """研究週序列：(日期, 一直抱著, 照做)；淨值都從研究起點＝1。"""
    if plan == "def":
        x = (((PR or {}).get("mk") or {}).get(mk) or {}).get("x_series") or {}
        s = (x.get("r") or {}).get(S.PLANS["def"]["rule"]) or {}
    else:
        x = (((TR or {}).get("mk") or {}).get(mk) or {}).get("series") or {}
        s = (x.get("r") or {}).get(S.PLANS["atk"]["rule"]) or {}
    if not x.get("d") or not s.get("nav") or len(x["bh"]) != len(s["nav"]):
        return None
    return list(x["d"]), np.asarray(x["bh"], dtype=float), np.asarray(s["nav"], dtype=float)


def windows(bh: np.ndarray, nav: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    """每一週起算、w 週的窗口：x＝一直抱著 ln 漲跌、y＝照做 ln 漲跌。"""
    if len(bh) <= w:
        return np.array([]), np.array([])
    return np.log(bh[w:] / bh[:-w]), np.log(nav[w:] / nav[:-w])


def year_range(bh: np.ndarray, nav: np.ndarray) -> dict | None:
    """照做一年（RANGE_W 週）的報酬：RANGE_Q 的位置與賠錢的比例（照做 q／loss、一直抱著 bq／bloss）。"""
    x, y = windows(bh, nav, S.RANGE_W)
    if not len(y):
        return None
    ry, rx = np.expm1(y), np.expm1(x)
    return {"n": int(len(y)), "q": [_r(v, 4) for v in np.quantile(ry, S.RANGE_Q)], "loss": _r(np.mean(ry < 0), 4),
            "bq": [_r(v, 4) for v in np.quantile(rx, S.RANGE_Q)], "bloss": _r(np.mean(rx < 0), 4)}


def same_market(x: float, y: float, bh: np.ndarray, nav: np.ndarray, n: int) -> dict:
    """planspec ①：研究期間同樣長度的窗口裡，一直抱著漲跌最接近 x 的 NB_Q（至少 NB_MIN 個），照做的 y 在它們裡面的位置。
    → {"w": 週數, "N": 窗口數, "k": 比的窗口數, "p", "st": ok／bad／good（窗口不夠＝None）, "nq": 那些窗口照做的 25/50/75%, "nx": 一直抱著的範圍}"""
    w = weeks(n)
    X, Y = windows(bh, nav, w)
    N = len(X)
    out = {"w": w, "N": int(N), "n": n, "x": _r(math.expm1(x), 4), "y": _r(math.expm1(y), 4)}
    if N < S.NB_MIN:
        out["st"] = None
        return out
    k = max(S.NB_MIN, int(math.ceil(S.NB_Q * N)))
    idx = np.lexsort((np.arange(N), np.abs(X - x)))[:k]
    yy, xx = Y[idx], X[idx]
    p = (np.count_nonzero(yy < y) + 0.5 * np.count_nonzero(yy == y)) / k
    st = "bad" if p < S.P_LOW else "good" if p > S.P_HIGH else "ok"
    out.update({"k": k, "p": _r(p, 4), "st": st, "nq": [_r(v, 4) for v in np.expm1(np.quantile(yy, (0.25, 0.5, 0.75)))],
                "nx": [_r(math.expm1(float(xx.min())), 4), _r(math.expm1(float(xx.max())), 4)]})
    return out


# ── 期貨部位（進攻） ────────────────────────────────────────────────────────────

def fut_episodes(cal: list[str], r: np.ndarray, dr: np.ndarray, a: np.ndarray, s0: int, b: int) -> dict:
    """planspec ③：第 s0 天收盤（淨值 1）到第 b−1 天收盤；dr＝第 s0＋1～b−1 天的報酬。
    一段加碼＝第 s～e−1 天收盤之後都有加碼（a ＞ 0），第 e 天收盤平掉（e＝b 表示到最後還開著）。
    期貨部位第 j 天的盈虧＝前一天收盤的淨值 ×（dr_j − r_j）（含加碼、平倉、轉倉的成本）；累積到第 k 天，除以那一段開始前一天收盤的淨值
    （第 s0 天以前就開著的一段＝第 s0 天收盤）。→ {"list": [[開始, 結束或 None, 最低點, 最低點那天, 結束時]], "worst", "day", "dday"}"""
    nv = np.concatenate([[1.0], np.cumprod(1.0 + dr)])

    def at(j: int) -> float:
        return float(nv[j - s0])
    eps, worst_day, wd = [], 0.0, None
    i = s0
    while i < b:
        if not (np.isfinite(a[i]) and a[i] > 0):
            i += 1
            continue
        s = i
        while i < b and np.isfinite(a[i]) and a[i] > 0:
            i += 1
        e = i
        base = s - 1 if s > s0 else s0
        cum, lo, lo_d = 0.0, 0.0, None
        for j in range(max(s, s0 + 1), min(e, b - 1) + 1):
            g = dr[j - s0 - 1] - r[j]
            cum += at(j - 1) * g / at(base)
            if cum < lo:
                lo, lo_d = cum, cal[j]
            if a[j - 1] > 0 and g < worst_day:
                worst_day, wd = g, cal[j]
        eps.append([cal[s], cal[e] if e < b else None, _r(lo, 6), lo_d, _r(cum, 6)])
    lows = [x[2] for x in eps if x[2] is not None]
    wi = int(np.argmin(lows)) if lows else None
    return {"list": eps, "n": len(eps), "worst": lows[wi] if wi is not None else None,
            "wa": eps[wi][0] if wi is not None else None, "wz": eps[wi][1] if wi is not None else None,
            "wt": eps[wi][3] if wi is not None else None, "day": _r(worst_day, 6), "dday": wd}


def atk_path(mk: str, D: dict, carry: dict | None, s0: int, b: int) -> dict:
    """進攻（K4）第 s0 天收盤＝1 到第 b−1 天收盤的每天報酬、指數報酬與加碼（同 tilt.evaluate）。"""
    cal = list(D["cal"])
    px = np.asarray(D["px"], dtype=float)
    Cy = TL.carry_inputs(mk, cal, px, carry)
    roll = TL.roll_flags(mk, cal)
    r = P.daily_ret(px)
    a = np.nan_to_num(TL.ma_overlay(px), nan=0.0)
    dr = TL.day_ret(r, Cy, a, TL.costs(a, roll, s0), s0, b)
    return {"cal": cal, "px": px, "r": r, "a": a, "dr": dr}


# ── 前瞻 ──────────────────────────────────────────────────────────────────────

def live_def(mk: str, D: dict, L: dict | None) -> dict | None:
    """防守前瞻：實測區前瞻紀錄第一筆總經策略照做的那天起（practlive.positions，成本同 practlive.forward）。"""
    log_mk = ((L or {}).get("mk") or {}).get(mk) or {}
    cal = list(D["cal"])
    px = np.asarray(D["px"], dtype=float)
    p, a, gap = PL.positions(cal, log_mk, S.PLANS["def"]["rule"])
    if p is None:
        return None
    T = len(cal)
    pp = np.nan_to_num(p, nan=0.0)
    r = P.daily_ret(px)
    dr = P.day_ret(r, pp, P.turn_cost(pp, XS.COST[mk]), a, T)
    return {"a": a, "cal": cal, "nav": np.concatenate([[1.0], np.cumprod(1.0 + dr)]), "bh": px[a:] / px[a], "gap": gap}


def live_atk(mk: str, D: dict, carry: dict | None) -> dict | None:
    """進攻前瞻：LIVE_FROM 起（第一個不早於它的交易日收盤＝1，同 tilt.live）。"""
    cal = list(D["cal"])
    T = len(cal)
    a0 = bisect.bisect_left(cal, S.LIVE_FROM["atk"])
    if a0 >= T:
        return None
    x = atk_path(mk, D, carry, a0, T)
    px = x["px"]
    out = {"a": a0, "cal": cal, "nav": np.concatenate([[1.0], np.cumprod(1.0 + x["dr"])]), "bh": px[a0:] / px[a0], "gap": 0}
    out["fut"] = fut_episodes(cal, x["r"], x["dr"], x["a"], a0, T)
    return out


def checkpoint_day(mk: str, cal: list[str], a: int, c: int) -> str | None:
    """前瞻第 c 個交易日那天（資料還沒到＝照休市表往後推）。"""
    if a + c < len(cal):
        return cal[a + c]
    fd = XT.future_days(mk, cal[-1], a + c - (len(cal) - 1))
    return fd[-1] if fd else None


def pending(mk: str, cal: list[str], since: str) -> dict:
    """前瞻起點還沒有資料（例：進攻 10/23 起，資料只到 10/22）：起點＝第一個不早於 since 的交易日、第一次檢查的日子。"""
    fd = XT.future_days(mk, cal[-1], 10)
    a = next((d for d in fd if d >= since), None)
    out = {"a": a, "n": 0, "chk": [], "flags": [], "st": "wait"}
    if a:
        i = fd.index(a) + 1
        nd = XT.future_days(mk, cal[-1], i + S.CHECKS[0])
        out["next"] = {"n": S.CHECKS[0], "d": nd[-1] if nd else None}
    return out


def forward(mk: str, plan: str, lv: dict | None, wk: tuple | None, mdd_hist: float | None, fut_hist: float | None) -> dict | None:
    """前瞻的成績與三種檢查：{a, z, n, ret, bh, mdd, chk: [檢查點], next: {n, d}, flags: [dd／fut], st}。"""
    if not lv:
        return None
    cal, a, nav, bh = lv["cal"], lv["a"], lv["nav"], lv["bh"]
    n = len(nav) - 1
    out = {"a": cal[a], "z": cal[-1], "n": n, "gap": lv.get("gap", 0), "ret": _r(nav[-1] - 1.0, 6), "bh": _r(bh[-1] - 1.0, 6),
           "mdd": _r(float((1.0 - nav / np.maximum.accumulate(nav)).max()), 6), "chk": [], "flags": []}
    for c in S.CHECKS:
        if c > n:
            nx = c
            out["next"] = {"n": nx, "d": checkpoint_day(mk, cal, a, nx)}
            break
        if wk:
            res = same_market(math.log(float(bh[c])), math.log(float(nav[c])), wk[1], wk[2], c)
            res["d"] = cal[a + c]
            out["chk"].append(res)
    if mdd_hist is not None and out["mdd"] is not None and out["mdd"] > mdd_hist + 1e-12:
        out["flags"].append("dd")
    if plan == "atk" and fut_hist is not None:
        lw = (lv.get("fut") or {}).get("worst")
        out["fw"] = lw
        if lw is not None and lw < fut_hist - 1e-12:
            out["flags"].append("fut")
    last = next((x["st"] for x in reversed(out["chk"]) if x.get("st")), None)
    out["st"] = out["flags"][0] if out["flags"] else (last or "wait")
    return out


# ── 現在 ──────────────────────────────────────────────────────────────────────

def now_def(mk: str, D: dict, PR: dict | None, XR: dict | None) -> dict:
    """防守現在：今年選到的策略（同實測區的前瞻紀錄）、今天收盤後合計拿幾成；下一個交易日照規則要動的那幾條與動完之後的合計。"""
    from . import xsadvice as XA
    tg, sel, held = PL.strat_targets(mk, D, PR)
    rule = S.PLANS["def"]["rule"]
    ks = list(sel.get(rule) or [])
    M = (XR or {}).get(mk) or {}
    nx = next((M[k]["now"].get("nx") for k in M if (M[k].get("now") or {}).get("nx")), None)
    acts, nxt = [], {}
    for k in ks:
        h = float(held.get(k, 0.0))
        q = XA.due(M[k]) if k in M else None
        if q and nx and q[0] == nx:
            acts.append({"k": k, "name": XS.BY_KEY[k]["name"], "act": q[1]})
            h = 1.0 if q[1] == "買進" else 0.0 if q[1] == "賣出" else h
        nxt[k] = h
    n = len(ks)
    return {"d": D["cal"][-1], "nx": nx, "w": _r(tg.get(rule), 4), "n": n, "sel": ks,
            "held": [k for k in ks if held.get(k, 0.0) > 0], "acts": acts,
            "wn": _r(sum(nxt.values()) / n, 4) if n else None, "maybe": [x["k"] for x in acts if x["act"] == "可能買進"]}


def now_atk(mk: str, D: dict) -> dict:
    """進攻現在：收盤 vs 200 日均線、從哪天起；今天收盤後有沒有加碼、下一個交易日照規則要做什麼；
    下一個交易日收盤在哪個價位以上＝那天在 200 日均線上（＝前 199 天收盤平均）；換算成期貨口數（以今天收盤計）。"""
    cal = list(D["cal"])
    px = np.asarray(D["px"], dtype=float)
    st = TL.ma_state(px, cal)
    a = np.nan_to_num(TL.ma_overlay(px), nan=0.0)
    on = float(a[-1]) > 0
    act = None
    if st.get("up") and not on:
        act = "加碼"
    elif st and not st.get("up") and on:
        act = "平掉"
    flip = float(np.mean(px[-(TS.MA_N - 1):])) if len(px) >= TS.MA_N - 1 else None
    nx = XT.future_days(mk, cal[-1], 1)
    lots = []
    cap = S.CAPITAL.get(mk)
    for name, mult in S.CONTRACTS.get(mk, ()):
        per = float(px[-1]) * mult
        x = cap * TS.ADD / per if cap else None
        k = int(math.floor(x + 0.5)) if x is not None else None
        lots.append([name, mult, _r(per, 0), _r(x, 3), k, _r(k * per / cap, 4) if cap and k is not None else None])
    return {"d": cal[-1], "nx": nx[0] if nx else None, "up": st.get("up"), "since": st.get("since"), "ma": _r(st.get("ma"), 2),
            "px": _r(st.get("px"), 2), "on": on, "act": act, "flip": _r(flip, 2), "lots": lots, "cap": cap, "cur": S.CUR.get(mk), "add": TS.ADD}


# ── 一個市場 ──────────────────────────────────────────────────────────────────

def past_def(mk: str, PR: dict | None, wk: tuple | None) -> dict | None:
    R = (((PR or {}).get("mk") or {}).get(mk) or {}).get("rules", {}).get(S.PLANS["def"]["rule"])
    if not R:
        return None
    f = R["full"]
    out = {"a": f["rule"]["a"], "z": f["rule"]["z"], "cagr": f["rule"]["cagr"], "mdd": f["rule"]["mdd"], "worst": f["rule"]["worst"],
           "w": f["rule"].get("w"), "adj": f["rule"].get("adj"), "v": R.get("v"),
           "bh": {k: f["bh"][k] for k in ("cagr", "mdd", "worst")}, "yrs": f["rule"]["yrs"]}
    out["man"] = _r((1.0 + out["cagr"]) ** out["yrs"], 4)
    out["bman"] = _r((1.0 + out["bh"]["cagr"]) ** out["yrs"], 4)
    if wk:
        out["yr"] = year_range(wk[1], wk[2])
    return out


def past_atk(mk: str, TR: dict | None, wk: tuple | None, fut: dict | None) -> dict | None:
    R = (((TR or {}).get("mk") or {}).get(mk) or {}).get("rules", {}).get(S.PLANS["atk"]["rule"])
    if not R:
        return None
    f = R["full"]
    ep = [x for x in ((R.get("ep") or {}).get("list") or [])]
    pnl = [x[2] for x in ep if x[2] is not None]
    out = {"a": f["rule"]["a"], "z": f["rule"]["z"], "cagr": f["rule"]["cagr"], "mdd": f["rule"]["mdd"], "worst": f["rule"]["worst"],
           "share": f["rule"].get("share"), "starts": f["rule"].get("starts"), "adj": f["rule"].get("adj"), "v": R.get("v"),
           "man": _r(R["man"] / 1e6, 4), "bman": _r(R["man_bh"] / 1e6, 4), "fman": _r(R["man_fix"] / 1e6, 4),
           "bh": {k: f["bh"][k] for k in ("cagr", "mdd", "worst")}, "abar": f.get("abar"),
           "ep": {"n": len(pnl), "win": _r(np.mean([v > 0 for v in pnl]), 4) if pnl else None,
                  "med": _r(float(np.median(pnl)), 6) if pnl else None}}
    if fut:
        out["fut"] = {k: fut[k] for k in ("n", "worst", "wa", "wz", "wt", "day", "dday")}
    if wk:
        out["yr"] = year_range(wk[1], wk[2])
    return out


def research_fut(mk: str, D: dict, TR: dict | None, carry: dict | None) -> dict | None:
    """研究期間（tilt 研究檔的起點到終點）每一段加碼的期貨部位（planspec ③ 的基準）。"""
    M = ((TR or {}).get("mk") or {}).get(mk) or {}
    if not M.get("a") or not M.get("z"):
        return None
    cal = list(D["cal"])
    s0 = bisect.bisect_left(cal, M["a"])
    b = bisect.bisect_right(cal, M["z"])
    if s0 >= b - 1:
        return None
    x = atk_path(mk, D, carry, s0, b)
    out = fut_episodes(cal, x["r"], x["dr"], x["a"], s0, b)
    out["man"] = _r(float(np.prod(1.0 + x["dr"])), 6)
    return out


def market(mk: str, PR: dict | None, TR: dict | None, L: dict | None, XR: dict | None, carry: dict | None,
           D: dict | None = None) -> dict:
    D = D if D is not None else XT.data(mk)
    out: dict = {"mk": mk, "d": D["cal"][-1]}
    if mk in S.AVAIL["def"]:
        wk = weekly("def", mk, PR, TR)
        past = past_def(mk, PR, wk)
        if past:
            out["def"] = {"now": now_def(mk, D, PR, XR), "past": past,
                          "live": forward(mk, "def", live_def(mk, D, L), wk, past["mdd"], None)}
    if mk in S.AVAIL["atk"]:
        wk = weekly("atk", mk, PR, TR)
        fut = research_fut(mk, D, TR, carry)
        past = past_atk(mk, TR, wk, fut)
        if past:
            lv = live_atk(mk, D, carry)
            out["atk"] = {"now": now_atk(mk, D), "past": past,
                          "live": (forward(mk, "atk", lv, wk, past["mdd"], (fut or {}).get("worst")) if lv
                                   else pending(mk, list(D["cal"]), S.LIVE_FROM["atk"]))}
    if "def" not in out and "atk" not in out:
        T = ((TR or {}).get("mk") or {}).get(mk) or {}
        f = ((T.get("rules") or {}).get(S.PLANS["atk"]["rule"]) or {}).get("full") or {}
        b = f.get("bh") or {}
        out["bh"] = {k: b.get(k) for k in ("a", "cagr", "mdd", "worst")}
    return out


def build(PR: dict | None = None, TR: dict | None = None, L: dict | None = None, XR: dict | None = None) -> dict:
    """五個市場的交易計畫（策略頁「總經策略」這一期最上面）；某個市場算不出來只印日誌、不擋其他。"""
    PR = P.load() if PR is None else PR
    TR = TL.load() if TR is None else TR
    L = PL.load() if L is None else L
    if XR is None:
        XR = XT.run_all()
    carry = TL.load_carry()
    out: dict = {"ver": S.VER, "plans": {k: v["name"] for k, v in S.PLANS.items()},
                 "short": {k: v["short"] for k, v in S.PLANS.items()}, "avail": {k: list(v) for k, v in S.AVAIL.items()},
                 "checks": list(S.CHECKS), "mk": {}}
    for mk in S.MARKETS:
        try:
            out["mk"][mk] = market(mk, PR, TR, L, XR, carry)
        except Exception as e:                            # noqa: BLE001
            print(f"[交易計畫] {mk} 算不出來：{type(e).__name__}: {e}", flush=True)
    return out
