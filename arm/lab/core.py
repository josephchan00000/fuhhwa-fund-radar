"""交易計畫：核心＋機動（corespec VER 4：台股核心 20%、美股 0%；docs/lab_core70_plan.md 第 9～12、16～19 節）。

研究與每天建頁共用同一支 families()：
  research()        回測（scripts/run_core.py → data/lab/core_research.json；資料或規格改了才重跑）
  now_from_B(B)     景氣頁建頁時：三種過熱現在的讀數、該拿多少、下一個交易日的觸發價位（heatpage.view 放進 V["core"]）
  stk_from_adv(A)   個股頁建頁時：衛星裡的 ★ 策略、手上的股票、接下來要做的事（STK，訊號總覽沿用）
  record()／forward()  前瞻紀錄（只有 CI 寫回 data/lab/core_live.json）
"""
from __future__ import annotations

import json
import math
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from . import corespec as S

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "lab" / "core_research.json"
LIVE = ROOT / "data" / "lab" / "core_live.json"
STK: dict = {}                       # 個股頁建頁時放進來（stk_from_adv 的結果）
FLAT_NAME = "總經策略全部空手"          # VER 2 美股的第四個警訊（換現金表、前瞻紀錄用這個名字）


# ── 規則 ─────────────────────────────────────────────────────────────────────

def families(px, inf, lev, flat=None, mk: str | None = None) -> dict:
    """每天收盤：三種過熱亮不亮（沒有資料＝不亮）、亮幾種；flat＝總經策略全部空手（VER 2，FLAT 的市場）。
    ok＝那天收盤「沒有該賣的理由」（亮的少於 NEED 種、而且不是全部空手）；clear＝ok 連續了幾天；
    on＝收盤後決定的衛星拿不拿著：不 ok 那天就換現金，現金時要 ok 連續 REENTRY 天才買回（VER 2，台股 10 天）。"""
    from .xstrat import sma
    px = np.asarray(px, dtype=float)
    ma = sma(px, S.MA)
    lit = {"inf": np.nan_to_num(np.asarray(inf, dtype=float), nan=-1.0) >= S.HOT,
           "lev": np.nan_to_num(np.asarray(lev, dtype=float), nan=-1.0) >= S.HOT,
           "trend": np.isfinite(ma) & (px < np.nan_to_num(ma, nan=-1.0))}
    n = lit["inf"].astype(int) + lit["lev"].astype(int) + lit["trend"].astype(int)
    ok = n < S.NEED
    if flat is not None:
        lit["flat"] = np.asarray(flat, dtype=bool)
        ok = ok & ~lit["flat"]
    need = S.REENTRY.get(mk, 1) if mk else 1
    on, clear = decide(ok, need)
    return {"ma": ma, "lit": lit, "n": n, "ok": ok, "clear": clear, "on": on, "need": need}


def decide(ok: np.ndarray, need: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """不 ok 的那天收盤決定換現金；現金時要 ok 連續 need 天（含那天）才決定買回。→ (on, clear＝ok 連續了幾天)。"""
    ok = np.asarray(ok, dtype=bool)
    on = np.ones(len(ok), dtype=bool)
    clear = np.zeros(len(ok), dtype=int)
    st, c = True, 0
    for k in range(len(ok)):
        c = c + 1 if ok[k] else 0
        if not ok[k]:
            st = False
        elif not st and c >= need:
            st = True
        on[k], clear[k] = st, c
    return on, clear


def macro_flat(mk: str, cal: list[str]) -> np.ndarray | None:
    """總經策略全部空手（VER 2）：這個市場有資料的全部總經策略（不看判定）在那天收盤之後都沒有部位。
    對到 cal 的日期（cal 某天沒有總經策略的資料＝用那天以前最近一天的）；不是 FLAT 的市場回 None。"""
    if mk not in S.FLAT:
        return None
    from . import practsim as PS
    from . import xstrat as XT
    D = XT.data(mk)
    C = XT.Ctx(D)
    held_any = np.zeros(len(D["cal"]), dtype=bool)
    for s in PS.xs_specs(mk, D):
        held_any |= np.asarray(XT.held_pos(C, s), dtype=float) > 0.5
    xc = np.array(D["cal"])
    j = np.searchsorted(xc, np.array(cal), side="right") - 1
    return np.where(j >= 0, ~held_any[np.clip(j, 0, None)], False)


def macro_holding(mk: str) -> dict:
    """現在（總經策略資料的最後一天）哪幾條總經策略有部位：{"d", "held": [(鍵, 名稱)], "n": 全部幾條}。"""
    from . import practsim as PS
    from . import xstrat as XT
    D = XT.data(mk)
    C = XT.Ctx(D)
    specs = PS.xs_specs(mk, D)
    held = [(s["k"], s["name"]) for s in specs if float(XT.held_pos(C, s)[-1]) > 0.5]
    return {"d": D["cal"][-1], "held": held, "n": len(specs)}


def held(on: np.ndarray) -> np.ndarray:
    """sat[k]＝第 k 天收盤之後衛星拿著（1）或是現金（0）：第 k−LAG 天收盤的決定、第 k 天收盤照做。"""
    on = np.asarray(on, dtype=bool)
    sat = np.ones(len(on), dtype=float)
    if len(on) > S.LAG:
        sat[S.LAG:] = on[:len(on) - S.LAG].astype(float)
    return sat


def trigger_price(px) -> float | None:
    """下一個交易日收盤低於這個價位＝那天收盤在 200 日均線之下（前 199 天收盤平均；均線含當天收盤）。"""
    px = np.asarray(px, dtype=float)
    k = S.MA - 1
    if len(px) < k or np.isnan(px[-k:]).any():
        return None
    return float(px[-k:].sum() / k)


# ── 資料 ─────────────────────────────────────────────────────────────────────

def tw_lev(B: dict) -> tuple[list[str], np.ndarray]:
    """台股槓桿：融資 ÷ 上市市值（每天）的 0～100（crash.tw_inputs 的 W2；做法同 sigcat.frame_from_B）。"""
    from . import bubble as BU
    from . import crash as CR
    from . import heatdata as HD
    D = dict(B["D"])
    for n in ("twcap", "twmgn", "taiex90"):
        if n not in D:
            D[n] = HD.load(n)
    D["_tsmc"] = CR._tsmc_month(None)
    I = CR.tw_inputs(D=D, B=B, BX={"tw": BU.market_for("tw", B["D"])})
    return list(I["cal"]), np.asarray(I["x"]["W2"], dtype=float)


def inputs_from_B(mk: str, B: dict) -> dict:
    """景氣頁的 B → 對到 B 的日曆的 {"cal", "px", "inf", "lev", "items": (通膨項目, 槓桿項目)}。"""
    from . import crash as CR
    cal = list(B["cal"])
    px = np.array([np.nan if v is None else float(v) for v in B["px"]], dtype=float)
    fam = {f[0]: f for f in S.FAMS[mk]}
    inf = CR.align(cal, cal, B["hc"][fam["inf"][4]])
    if fam["lev"][3] == "crash":
        lc, lv = tw_lev(B)
        lev = CR.align(cal, lc, list(lv))
    else:
        lev = CR.align(cal, cal, B["hc"][fam["lev"][4]])
    return {"cal": cal, "px": px, "inf": inf, "lev": lev}


# ── 回測 ─────────────────────────────────────────────────────────────────────

def simulate(tot, rf, sat, a: int, b: int, c_idx: float, sl=None, inpos=None, swc=None, c_stk: float | None = None,
             core: float = S.CORE):
    """第 a 天收盤＝1 元、算到第 b−1 天收盤。每天：核心 core × 大盤＋機動（1 − core）×（拿著＝機動資產、現金＝利息）。
    sl＝機動資產每天的報酬（None＝大盤）；inpos[k]＝第 k 天收盤後機動裡的策略有持股（換現金、買回付個股的成本）；
    swc[k]＝機動拿著時那一天策略換倉要付的大盤成本（期初開盤賣大盤、期末收盤買大盤）。→ 淨值陣列（長度 b−a）。
    core 預設＝VER 1～3 的 70%（ussxspec 的舊研究照這個重現）；交易計畫用 scenario 傳 corespec.core_of(市場)。"""
    tot = np.asarray(tot, dtype=float)
    rf = np.asarray(rf, dtype=float)
    sl = tot if sl is None else np.asarray(sl, dtype=float)
    w = 1.0 - core
    nav = np.ones(b - a)
    v = 1.0
    for k in range(a + 1, b):
        on = sat[k - 1] > 0.5
        g = core * tot[k] + w * (sl[k] if on else rf[k])
        cost = 0.0
        if on and swc is not None and swc[k]:
            cost += w * swc[k]
        if sat[k] != sat[k - 1]:
            cost += w * (c_stk if (inpos is not None and c_stk is not None and inpos[k]) else c_idx)
        v *= (1 + g) * (1 - cost)
        nav[k - a] = v
    return nav


def simulate_fixed(tot, rf, share: float, a: int, b: int, sl=None, swc=None, core: float = S.CORE):
    """每天固定拿一樣多：機動一直有 share 比例拿著機動資產、其餘現金（平均部位相同，沒有換現金的成本）。"""
    tot = np.asarray(tot, dtype=float)
    rf = np.asarray(rf, dtype=float)
    sl = tot if sl is None else np.asarray(sl, dtype=float)
    w = 1.0 - core
    nav = np.ones(b - a)
    v = 1.0
    for k in range(a + 1, b):
        g = core * tot[k] + w * (share * sl[k] + (1 - share) * rf[k])
        cost = w * share * swc[k] if swc is not None and swc[k] else 0.0
        v *= (1 + g) * (1 - cost)
        nav[k - a] = v
    return nav


def _years(cal: list[str], a: int, b: int, nav) -> list[list]:
    """[[年, 報酬, 交易日數]]：每一年最後一個交易日對前一年最後一個交易日（第一年對起點）。"""
    out, last_y, base = [], None, 1.0
    end = {}
    cnt: dict[str, int] = {}
    for k in range(a, b):
        y = cal[k][:4]
        end[y] = k
        cnt[y] = cnt.get(y, 0) + (k > a)
    for y in sorted(end):
        v = nav[end[y] - a]
        out.append([y, v / base - 1, cnt[y]])
        base, last_y = v, y
    return out


def stats(cal: list[str], nav, a: int, b: int) -> dict:
    nav = np.asarray(nav, dtype=float)
    yrs = (date.fromisoformat(cal[b - 1]) - date.fromisoformat(cal[a])).days / 365.25
    m = float(nav[-1])
    pk = np.maximum.accumulate(nav)
    mdd = float((1 - nav / pk).max())
    ys = _years(cal, a, b, nav)
    full = [y for y in ys if y[2] >= S.YEAR_MIN]
    r = np.array([nav[i + S.ROLL] / nav[i] - 1 for i in range(len(nav) - S.ROLL)]) if len(nav) > S.ROLL else np.array([])
    out = {"m": m, "cagr": m ** (1 / yrs) - 1 if yrs > 0 and m > 0 else None, "mdd": mdd,
           "worst": min((y[1] for y in full), default=None), "years": ys}
    if len(r):
        q = np.quantile(r, S.Q)
        out.update({"q": [float(x) for x in q], "loss": float((r < 0).mean()), "n12": int(len(r))})
    if full:
        best = max(full, key=lambda y: y[1])
        rest = [y for y in full if y is not best]
        if rest:
            lg = sum(math.log1p(y[1]) for y in rest)
            nd = sum(y[2] for y in rest)
            out["ex_best"] = math.expm1(lg * 252 / nd) if nd else None
            out["best_y"] = best[0]
    return out


def cash_runs(sat: np.ndarray, a: int, b: int) -> list[tuple[int, int]]:
    """衛星是現金的每一段：(第一天收盤賣出那天, 最後一天)。之後那一天收盤買回。"""
    out, k = [], a + 1
    while k < b:
        if sat[k] < 0.5 and sat[k - 1] > 0.5:
            j = k
            while j + 1 < b and sat[j + 1] < 0.5:
                j += 1
            out.append((k, j))
            k = j + 1
        else:
            k += 1
    return out


def scenario(key: str, mk: str, cal, px, tot, rf, F: dict, a: int, b: int, c_idx: float, *, sl=None, inpos=None, swc=None,
             c_stk=None, sleeve: str = "index", core: float | None = None) -> dict:
    """一段回測：照計畫、一直抱著、每天固定拿一樣多；前後兩半、近 RECENT_Y 年；每一次換現金；逐年；每週的淨值。
    core＝核心比例（None＝這個市場 corespec 現在的 core_of；舊研究的重現明寫 core＝S.CORE）。"""
    core = S.core_of(mk) if core is None else core
    w = 1.0 - core
    sat = held(F["on"])
    plan = simulate(tot, rf, sat, a, b, c_idx, sl, inpos, swc, c_stk, core)
    hold = np.cumprod(np.concatenate([[1.0], 1 + np.asarray(tot, dtype=float)[a + 1:b]]))
    share = float(np.mean(sat[a:b - 1])) if b - 1 > a else 1.0
    fixed = simulate_fixed(tot, rf, share, a, b, sl, swc, core)
    mid = a + (b - a) // 2
    i10 = next((k for k in range(a, b) if cal[k] >= _minus_years(cal[b - 1], S.RECENT_Y)), a)

    def part(x0, x1):
        p = simulate(tot, rf, sat, x0, x1, c_idx, sl, inpos, swc, c_stk, core)
        h = np.cumprod(np.concatenate([[1.0], 1 + np.asarray(tot, dtype=float)[x0 + 1:x1]]))
        return {"a": cal[x0], "b": cal[x1 - 1], "plan": _brief(stats(cal, p, x0, x1)), "hold": _brief(stats(cal, h, x0, x1))}
    eps = []
    for k0, k1 in cash_runs(sat, a, b):
        d0 = k0 - S.LAG
        lit = [f[1] for f in S.FAMS[mk] if F["lit"][f[0]][d0]] + ([FLAT_NAME] if "flat" in F["lit"] and F["lit"]["flat"][d0] else [])
        x1 = min(k1 + 1, b - 1)
        asset = sl if sl is not None else tot
        ia = float(np.prod(1 + np.asarray(asset, dtype=float)[k0 + 1:x1 + 1]) - 1)
        ic = float(np.prod(1 + np.asarray(rf, dtype=float)[k0 + 1:x1 + 1]) - 1)
        ix = float(np.prod(1 + np.asarray(tot, dtype=float)[k0 + 1:x1 + 1]) - 1)
        eps.append({"d": cal[d0], "sell": cal[k0], "buy": cal[x1] if k1 + 1 < b else None, "lit": lit,
                    "days": k1 - k0 + 1, "ix": ix, "diff": w * (ic - ia)})
    sw = int(np.count_nonzero(np.abs(np.diff(sat[a:b])) > 0.5))
    yrs = (date.fromisoformat(cal[b - 1]) - date.fromisoformat(cal[a])).days / 365.25
    return {"key": key, "mk": mk, "sleeve": sleeve, "a": cal[a], "b": cal[b - 1], "core": core,
            "plan": stats(cal, plan, a, b), "hold": stats(cal, hold, a, b), "fixed": _brief(stats(cal, fixed, a, b)),
            "avg": core + w * share, "sw": sw / yrs if yrs > 0 else None,
            "halves": [part(a, mid + 1), part(mid, b)], "recent": part(i10, b),
            "eps": eps, "chart": _chart(cal, plan, hold, sat, a, b)}


def _brief(st: dict) -> dict:
    return {k: st.get(k) for k in ("m", "cagr", "mdd", "worst")}


def _minus_years(d: str, n: int) -> str:
    x = date.fromisoformat(d)
    try:
        return x.replace(year=x.year - n).isoformat()
    except ValueError:
        return (x - timedelta(days=365 * n)).isoformat()


def _chart(cal, plan, hold, sat, a: int, b: int) -> dict:
    """每週最後一個交易日的淨值（照計畫、一直抱著）＋衛星是現金的期間。"""
    pts = []
    for k in range(a, b):
        last = k == b - 1
        if last or date.fromisoformat(cal[k + 1]).isocalendar()[1] != date.fromisoformat(cal[k]).isocalendar()[1]:
            pts.append([cal[k], round(float(plan[k - a]), 4), round(float(hold[k - a]), 4)])
    cash = [[cal[k0], cal[k1]] for k0, k1 in cash_runs(sat, a, b)]
    return {"pts": pts, "cash": cash}


# ── 台股衛星：財報驚喜（大型股）資金帳戶的每天報酬 ────────────────────────────────

def stk_sleeve(cal: list[str], tot, P=None, rf=None) -> dict:
    """BACKTEST_SLEEVE（財報驚喜（大型股），bt3l.top5 的 p3 L）在 cal 上的每天報酬：有持股的日子＝資金帳戶（修正後的 bt3.account），
    沒有持股＝大盤（VER 1～3；rf 給了＝現金利息、不付大盤的成本：VER 4）。
    → {"sl", "inpos", "swc", "act": 那一天有沒有持有任何一期, "a": 第一期決定日, "b": 最後一期出場日}。"""
    from . import bt3, bt3d, bt3s
    P = P or bt3d.Panel()
    E = bt3.Elig(P)
    eps = bt3d.load_eps()
    rows = bt3s.p3_rows(P, E, "L", P.codes, eps, 60)
    done = [r for r in rows if r[1] is not None]
    pk = bt3s.pick(done, 0.0, 5, False, 20)
    acc = bt3.account(P, pk, "L")
    active = set()
    for t, x, _ in pk:
        active.update(range(t + 1, x + 1))
    r_s = {}
    pts = acc["curve"]
    for (i0, v0), (i1, v1) in zip(pts, pts[1:]):
        if i1 in active and v0 > 0:
            r_s[P.cal[i1]] = v1 / v0 - 1
    pos = {d: i for i, d in enumerate(P.cal)}
    tot = np.asarray(tot, dtype=float)
    T = len(cal)
    cash = rf is not None
    sl = np.asarray(rf, dtype=float).copy() if cash else tot.copy()
    inpos = np.zeros(T, dtype=bool)
    act = np.zeros(T, dtype=bool)
    swc = np.zeros(T)
    for k, d in enumerate(cal):
        i = pos.get(d)
        if i is None or i not in active:
            continue
        sl[k] = r_s.get(d, 0.0)
        act[k] = True
        inpos[k] = (i + 1) in active
        if cash:
            continue                                   # 空檔放現金：期初期末不買賣大盤
        if (i - 1) not in active:
            swc[k] += S.COST["tw"]                     # 期初：開盤賣大盤
        if (i + 1) not in active:
            swc[k] += S.COST["tw"]                     # 期末：收盤買大盤
    return {"sl": sl, "inpos": inpos, "swc": swc, "act": act, "a": P.cal[pk[0][0]], "b": P.cal[pk[-1][1]], "n": len(pk)}


def boom_sleeve(cal: list[str], rf) -> dict | None:
    """新飆股（corespec BOOM_BOOK）那本帳在 cal 上的每天報酬（VER 4）：引擎淨值的報酬（引擎的現金不算利息）
    ＋前一天收盤沒有投入的比例 × 現金利息。回測淨值＝data/lab/SX_CURVE_FILE（scripts/run_sx_curve.py）。
    → {"r", "a": 第一天, "b": 最後一天, "x": 平均持股比例}；檔案沒有 → None。"""
    try:
        doc = json.loads((ROOT / "data" / "lab" / S.SX_CURVE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    nav = dict(zip(doc["d"], doc["nav"]))
    xp = dict(zip(doc["d"], doc["x"]))
    rf = np.asarray(rf, dtype=float)
    T = len(cal)
    r = np.zeros(T)
    last, lastx = None, 0.0
    for k in range(T):
        v = nav.get(cal[k])
        if v is not None and last:
            r[k] = v / last - 1 + (1 - lastx) * rf[k]
        elif last:
            r[k] = rf[k]
        if v is not None:
            last = v
            lastx = xp.get(cal[k], lastx)
    return {"r": r, "a": doc["d"][0], "b": doc["d"][-1], "x": float(np.mean(doc["x"])) if doc["x"] else None}


# ── 研究 ─────────────────────────────────────────────────────────────────────

def market_inputs(mk: str, B: dict | None = None) -> dict:
    """回測用：xstrat 的日曆與收盤、含息報酬與利率（tilt.carry_inputs）、三種過熱（景氣頁同一個序列，依日期對過來）。"""
    from . import crash as CR
    from . import tilt as TL
    from . import xstrat as XT
    D = XT.data(mk)
    cal = list(D["cal"])
    px = np.asarray(D["px"], dtype=float)
    Cy = TL.carry_inputs(mk, cal, px)
    rf = np.asarray(Cy["rate"], dtype=float) * np.asarray(Cy["days"], dtype=float) / 365.0
    if B is None:
        if mk == "tw":
            from . import heatcalc as HC
            B = HC.build()
        else:
            from . import heatcalc_us as HU
            B = HU.build(mk)
    X = inputs_from_B(mk, B)
    inf = CR.align(cal, X["cal"], list(X["inf"]))
    lev = CR.align(cal, X["cal"], list(X["lev"]))
    return {"cal": cal, "px": px, "tot": np.asarray(Cy["tot"], dtype=float), "rf": rf, "inf": inf, "lev": lev}


def research() -> dict:
    out = {"ver": S.VER, "spec": S.SPEC_DATE, "made": date.today().isoformat(), "mk": {}}
    for mk in S.MARKETS:
        M = market_inputs(mk)
        cal, px, tot, rf = M["cal"], M["px"], M["tot"], M["rf"]
        F = families(px, M["inf"], M["lev"], macro_flat(mk, cal), mk)
        T = len(cal)
        c = S.COST["tw" if mk == "tw" else "us"]
        a = next(k for k, d in enumerate(cal) if d >= S.RULE_START[mk])
        sc = {"rule": scenario("rule", mk, cal, px, tot, rf, F, a, T, c)}
        if mk == "tw":
            st = stk_sleeve(cal, tot, rf=rf)                      # VER 4：財報驚喜沒有部位的日子＝現金
            star = S.STAR_ACTIVE * st["sl"] + (1 - S.STAR_ACTIVE) * rf
            pb = next(k for k, d in enumerate(cal) if d >= st["b"]) + 1
            zero = np.zeros(T)
            la = next(k for k, d in enumerate(cal) if d >= max(S.PLAN_START, st["a"]))
            sc["long"] = scenario("long", mk, cal, px, tot, rf, F, la, pb, c, sl=star, inpos=st["act"], swc=zero,
                                  c_stk=S.COST["tw_stk"], sleeve="star")
            bm = boom_sleeve(cal, rf)
            if bm:
                g = S.BOOM_SHARE[mk]
                pa = next(k for k, d in enumerate(cal) if d >= max(S.PLAN4_START, bm["a"]))
                sc["plan"] = scenario("plan", mk, cal, px, tot, rf, F, pa, pb, c, sl=g * bm["r"] + (1 - g) * star,
                                      inpos=np.ones(T, dtype=bool), swc=zero, c_stk=S.COST["tw_stk"], sleeve=f"{S.BOOM_BOOK}+star")
                sc["plan"]["boom_x"] = bm["x"]
        if mk in S.EARLY:
            ok = [k for k in range(T) if np.isfinite(M["inf"][k]) and np.isfinite(M["lev"][k]) and np.isfinite(F["ma"][k])]
            e0 = ok[0] if ok else None
            e1 = next((k for k, d in enumerate(cal) if d > S.EARLY[mk]), T)
            if e0 is not None and e1 - e0 > S.ROLL * 2:
                sc["early"] = scenario("early", mk, cal, px, tot, rf, F, e0, e1, c)
        last = T - 1
        out["mk"][mk] = {"sc": sc, "d": cal[last]}
    return out


def save(R: dict) -> bool:
    txt = json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if RES.exists() and RES.read_text(encoding="utf-8") == txt:
        return False
    RES.write_text(txt, encoding="utf-8")
    return True


def load() -> dict | None:
    try:
        R = json.loads(RES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None


# ── 現在 ─────────────────────────────────────────────────────────────────────

def now_from_B(B: dict) -> dict | None:
    """景氣頁的 B → 這個市場現在：三種過熱的讀數與亮不亮、亮幾種、該拿多少、要不要動、下一個交易日的觸發價位。
    不是交易計畫的市場回 None。"""
    mk = B.get("idx") or "tw"
    if mk not in S.MARKETS or not B.get("cal"):
        return None
    from . import heatspec as HS
    if mk == "tw":
        return _now(mk, B)
    from . import heatspec_us as U
    with HS.use(U.spec_for(mk)):
        return _now(mk, B)


def _now(mk: str, B: dict) -> dict:
    from . import heatpage as HP
    X = inputs_from_B(mk, B)
    cal, px = X["cal"], X["px"]
    F = families(px, X["inf"], X["lev"], macro_flat(mk, cal), mk)
    t = len(cal) - 1
    while t > 0 and np.isnan(px[t]):
        t -= 1
    fams = []
    for k, name, desc, src, item in S.FAMS[mk]:
        f = {"k": k, "name": name, "desc": desc, "lit": bool(F["lit"][k][t])}
        if src == "ma":
            ma = F["ma"][t]
            f.update({"px": float(px[t]), "ma": None if np.isnan(ma) else float(ma),
                      "pct": None if np.isnan(ma) else float(px[t] / ma - 1) * 100,
                      "trig": trigger_price(px[:t + 1])})
        else:
            x = X[k]
            i = t
            while i > 0 and np.isnan(x[i]):
                i -= 1
            f.update({"v": None if np.isnan(x[i]) else round(float(x[i]), 1), "vd": cal[i],
                      "item": item, "stale": (B.get("stale") or {}).get(item) if src == "heat" else None})
            if src == "heat":
                try:
                    f["src"] = HP._src_date(B, item, t)
                except Exception:                           # noqa: BLE001 —— 資料日只是顯示用
                    f["src"] = None
        fams.append(f)
    if "flat" in F["lit"]:
        try:
            H = macro_holding(mk)
        except Exception as e:                               # noqa: BLE001 —— 名單只是顯示用
            print(f"[交易計畫] {mk} 總經策略名單算不出來：{type(e).__name__}: {e}")
            H = {"d": None, "held": [], "n": None}
        fams.append({"k": "flat", "name": FLAT_NAME, "desc": "全部總經策略都沒有部位", "lit": bool(F["lit"]["flat"][t]),
                     "held": [nm for _, nm in H["held"]], "n_all": H["n"], "vd": H["d"]})
    sat = held(F["on"][:t + 1])
    core, w = S.core_of(mk), S.sat_of(mk)
    return {"mk": mk, "d": cal[t], "fams": fams, "n": int(F["n"][t]), "on": bool(F["on"][t]),
            "ok": bool(F["ok"][t]), "clear": int(F["clear"][t]), "need": int(F["need"]), "core": core,
            "now": float(core + w * sat[t]), "next": float(core + w * (1.0 if F["on"][t] else 0.0)),
            "due": bool((sat[t] > 0.5) != bool(F["on"][t]))}


# ── 台股衛星（個股頁建頁時） ─────────────────────────────────────────────────────

def star_share(n: int, mk: str = "tw") -> float | None:
    """★ 策略每一條占全部資金多少：機動 ×（1 − 新飆股的比例）÷ 條數（VER 4）。"""
    return S.sat_of(mk) * (1 - S.BOOM_SHARE.get(mk, 0.0)) / n if n else None


def boom_share(mk: str = "tw") -> float:
    """新飆股那本帳占全部資金多少：機動 × BOOM_SHARE（VER 4）。"""
    return S.sat_of(mk) * S.BOOM_SHARE.get(mk, 0.0)


def stk_from_adv(A: dict, asof: str | None = None, boom: dict | None = None) -> dict:
    """個股頁的 advice 結果 → 台股機動：★ 策略（照頁面順序）、每條手上的股票、接下來 45 天要做的事；
    boom＝新飆股那本帳現在的狀態（sxlive.plan_state，VER 4）。"""
    asof = asof or date.today().isoformat()
    book = [b for b in A.get("book") or [] if b.get("tier") == S.SLEEVE_TIER]
    ks = [b["k"] for b in book]
    hold: dict[str, list] = {k: [] for k in ks}
    for p in A.get("picks") or []:
        if p.get("k") in hold and p.get("act") == "持有中":
            hold[p["k"]].append({"c": p.get("c"), "n": p.get("n"), "ent": p.get("ent"), "out": p.get("out"),
                                 "r": p.get("now_r")})
    end = (date.fromisoformat(asof) + timedelta(days=45)).isoformat()
    ev = []
    for e in A.get("cal") or []:
        if e.get("k") not in hold or not e.get("d") or e["d"] < asof or e["d"] > end:
            continue
        ev.append({"d": e["d"], "at": e.get("at"), "act": e.get("act"), "k": e["k"], "sname": e.get("sname"),
                   "note": e.get("note"), "held": bool(e.get("held")), "ent": e.get("ent"), "plan": bool(e.get("plan")),
                   "pending": bool(e.get("pending")), "fix": e.get("fix"), "how": e.get("ent_how"),
                   "items": [{"c": x.get("c"), "n": x.get("n")} for x in (e.get("items") or [])][:8],
                   "n_items": len(e.get("items") or [])})
    ev.sort(key=lambda e: (e["d"], 0 if e.get("at") == "開盤" else 1, e["k"]))
    kinds = {k: (v or {}).get("kind") for k, v in (A.get("trades") or {}).items() if isinstance(v, dict)}
    return {"d": asof, "st": [{"k": b["k"], "name": b.get("name"), "kind": b.get("kind") or kinds.get(b["k"])} for b in book],
            "hold": hold, "ev": ev, "w": star_share(len(ks)), "boom": boom, "bw": boom_share()}


# ── 前瞻 ─────────────────────────────────────────────────────────────────────

def load_live() -> dict:
    """前瞻紀錄；版本不同（規則改過）＝從頭記。"""
    try:
        L = json.loads(LIVE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ver": S.VER, "days": {}}
    return L if L.get("ver") == S.VER else {"ver": S.VER, "days": {}}


def record(nows: dict, stk: dict | None, qm: dict | None = None) -> bool:
    """今天的紀錄（只有 CI，GITHUB_ACTIONS＝true 才寫回）：{資料日: {市場: {E, n, lit, v, sat}}}，同一個資料日覆蓋。
    qm＝{市場: 美股機動是不是放 QM}（corespec VER 3～4）；是的話 sat＝["qm"]（持股與淨值在 ussx_qm_live.json）。
    台股 sat＝★ 策略＋新飆股（VER 4；新飆股的持股與淨值在 sxlive.json）。"""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return False
    L = load_live()
    days = L.setdefault("days", {})
    for mk, n in (nows or {}).items():
        if not n or mk not in S.MARKETS or n["d"] < S.LIVE_START:
            continue
        rec = {"E": n["next"], "n": n["n"], "lit": [f["k"] for f in n["fams"] if f["lit"]],
               "v": {f["k"]: (round(f["pct"], 2) if f.get("pct") is not None else None) if f["k"] == "trend" else f.get("v")
                     for f in n["fams"] if f["k"] != "flat"}, "clear": n.get("clear")}
        fl = next((f for f in n["fams"] if f["k"] == "flat"), None)
        if fl is not None:
            rec["held"] = len(fl.get("held") or [])
        if mk == "tw" and stk:
            rec["sat"] = [s["k"] for s in stk.get("st") or []] + ([S.BOOM_BOOK] if stk.get("boom") else [])   # VER 4：新飆股那本帳
        elif (qm or {}).get(mk):
            rec["sat"] = ["qm"]
        days.setdefault(n["d"], {})[mk] = rec
    L["ver"] = S.VER
    txt = json.dumps(L, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if LIVE.exists() and LIVE.read_text(encoding="utf-8") == txt:
        return False
    LIVE.write_text(txt, encoding="utf-8")
    return True


def forward(mk: str, L: dict | None = None) -> dict:
    """前瞻：紀錄從 LIVE_START 起有幾個交易日、還要幾天才比。美股（衛星＝指數或美股強勢品質股）照紀錄算照做與一直抱著；台股衛星之後用逐筆交易重算。"""
    L = L if L is not None else load_live()
    ds = sorted(d for d, v in (L.get("days") or {}).items() if mk in v)
    n = len(ds)
    nxt = next((c for c in S.CHECKS if c > n), None)
    return {"n": n, "first": ds[0] if ds else None, "next": nxt, "start": S.LIVE_START}
