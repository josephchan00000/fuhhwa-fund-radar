"""美股三成的規則 QM（ussxspec VER 3～6；docs/lab_us_sleeve_plan.md 第 13 節、docs/lab_core70_plan.md 第 19、20 節）：
每週名單、資金帳戶、研究、上線狀態。VER 4：空的位子放現金（不付指數的成本）、放進交易計畫照 corespec 的核心比例（美股 0%）。
VER 5：判定 ② 跟現在在用的計畫比（VER 3 的設定）。VER 6：③ 複委託只描述（使用者用海外券商）。

  research(C)  → data/lab/ussx_qm.json（scripts/run_ussx.py --qm；資料分支的資料）：重現第 12 節、判定 ①～④、只描述的項目、
                 交易計畫卡要的 scenario（spx、ndx 各一份）。
  snapshot(C)  → 最新一天收盤後的狀態：持股、明天開盤要賣的、這一週的名單與要買的（上線紀錄與頁面共用）。
C＝context()：面板、每週特徵（不算 VCP、標籤）、含息收盤、50 日線、股利、20 日成交值、計畫的指數報酬。
資金帳戶＝ussxbook.run（同 VER 2），只換 QM 的檔數與出場。"""
from __future__ import annotations

import json
import math
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import corespec as CS
from . import ussxbook as BK
from . import ussxfeat as UF
from . import ussxpanel as UP
from . import ussxrun as UR
from . import ussxspec as X
from . import ussxswap as SW

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "lab" / CS.US_SLEEVE_FILE
SURV = ROOT / "data" / "lab" / "ussx_surv.json"
KEYS = ("rs", "d52h", "om", "roe", "cap")


# ── 資料 ─────────────────────────────────────────────────────────────────────

def context(P: dict | None = None, earn: dict | None = None, workers: int = 4, log=print, plans: bool = True,
            extra: tuple = ()) -> dict:
    """extra＝另外要填的財報欄位（ussxfeat.build；只給研究用）。"""
    t0 = time.time()
    P = P if P is not None else UP.load()
    earn = earn if earn is not None else UP.earnings()
    cols = UF.build(P, X.LIQ_MIN, earn=earn, workers=workers, log=log, vcp=False, labels_on=False, extra=extra)
    el, D20 = cols.pop("el"), cols.pop("D20")
    Cf = UF.ffill(P["C"])
    S = UF.ffill(P["CS"].astype(float))
    with np.errstate(invalid="ignore", divide="ignore"):
        D = (Cf[1:] / Cf[:-1]) / (S[1:] / S[:-1]) - 1
    DIV = np.vstack([np.zeros((1, Cf.shape[1])), np.where(np.isfinite(D), D, 0.0)])
    del S, D
    C = {"P": P, "cal": P["cal"], "T": len(P["cal"]), "cols": cols, "el": el, "D20": D20, "Cf": Cf, "DIV": DIV,
         "MA": UF.roll_mean(Cf, X.QM_EXIT["ma"]), "yr": np.array([int(d[:4]) for d in cols["d"]])}
    if plans:
        C["PQ"] = UR.plan_inputs(P)
    log(f"[ussxqm] 資料 {time.time() - t0:.0f}s：{len(cols['d']):,} 列、到 {C['cal'][-1]}")
    return C


def a_of(cal: list[str], year: int) -> int:
    """year 年第一個交易日的前一天（收盤＝帳戶起點）。"""
    return next(k for k, d in enumerate(cal) if d >= f"{year}-01-01") - 1


# ── 規則 ─────────────────────────────────────────────────────────────────────

def qm_mask(f: dict, th: dict | None = None) -> np.ndarray:
    """五個條件同時成立（每一個都是「≥」；沒有值＝不成立）。"""
    th = th or X.QM
    with np.errstate(invalid="ignore"):
        m = np.ones(len(f["rs"]), dtype=bool)
        for k in KEYS:
            m &= np.asarray(f[k], dtype=float) >= th[k]
    return m


def signals(C: dict, mask: np.ndarray, y0: int | None = None, drop: frozenset = frozenset()) -> dict[int, list]:
    """{週訊號日: [(代號欄, RS)]}：依 RS 高到低、同分依代號（y0＝None：QM_Y0 起）。drop＝當作不存在的代號欄（只描述用）。"""
    y0 = X.QM_Y0 if y0 is None else y0
    cols = C["cols"]
    rs = cols["f"]["rs"]
    out: dict[int, list] = {}
    for k in np.nonzero(mask & (C["yr"] >= y0))[0]:
        j = int(cols["j"][k])
        if j in drop:
            continue
        out.setdefault(int(cols["di"][k]), []).append((j, float(rs[k]), cols["c"][k]))
    return {i: [(j, s) for j, s, _ in sorted(v, key=lambda x: (-x[1], x[2]))] for i, v in out.items()}


def lag_week(C: dict, sig: dict[int, list], n: int = 1) -> dict[int, list]:
    """晚 n 週才買（只描述）：每一週的名單挪到 n 週以後的週訊號日。"""
    wk = sorted(C["cols"]["wk"])
    pos = {d: k for k, d in enumerate(wk)}
    return {wk[pos[i] + n]: v for i, v in sig.items() if pos[i] + n < len(wk)}


def idle_of(C: dict, mk: str, mode: str | None = None) -> tuple[np.ndarray, float]:
    """閒置的錢每天的報酬與進出的成本：cash＝現金利息、不付成本（ussxspec VER 4）；index＝那個計畫的指數（VER 3）。"""
    Q = C["PQ"][mk]
    if (mode or X.QM_IDLE) == "cash":
        return Q["cash"], 0.0
    return Q["idle"], X.COST["idx"]


def run(C: dict, sig: dict[int, list], mk: str = "spx", c_stk: float = X.COST["stk"], b: int | None = None,
        idle: str | None = None) -> dict:
    """QM 的資金帳戶：QM_Y0 起；閒置的錢照 idle（None＝QM_IDLE：VER 4 放現金）。"""
    P = C["P"]
    a = a_of(C["cal"], X.QM_Y0)
    w = 1.0 / X.QM_SLOTS
    ir, ci = idle_of(C, mk, idle)
    r = BK.run(P["O"], C["Cf"], P["C"], P["last"], sig, a, b or C["T"], ir, ex=X.QM_EXIT, style=X.QM_STYLE,
               MA=C["MA"], D20=C["D20"], DIV=C["DIV"], weight=w, max_pos=X.QM_SLOTS,
               max_weight=max(w, X.TRADE["max_weight"]), c_stk=c_stk, c_idx=ci)
    r["a"] = a
    return r


def rets(C: dict, r: dict) -> np.ndarray:
    """帳戶每天的報酬（整個日曆；起點以前是 0）。"""
    return np.concatenate([np.zeros(r["a"]), BK.daily_ret(r["eq"])])


def stk_share(C: dict, r: dict) -> np.ndarray:
    return np.concatenate([np.zeros(r["a"]), r["stk"]])


# ── 放進交易計畫 ───────────────────────────────────────────────────────────────

def plan_scenarios(C: dict, mk: str, rr: np.ndarray, st: np.ndarray, a: int, b: int, c_stk: float,
                   core: float | None = None) -> tuple[dict, dict]:
    """機動換成 QM vs 機動放指數：同一段期間的 core.scenario（完整，頁面用）。同 ussxrun.plan_level。
    core＝核心比例（None＝corespec 現在的 core_of：VER 4 美股 0%；重現第 12 節用 0.70）。"""
    from . import core as CO
    P, Q = C["P"], C["PQ"][mk]
    cal = Q["cal"]
    pa, pb = Q["ix"][P["cal"][a]], Q["ix"][P["cal"][b - 1]] + 1
    sl = np.asarray(Q["tot"], dtype=float).copy()
    inpos = np.zeros(len(cal), dtype=bool)
    for k in range(a + 1, b):
        q = Q["ix"].get(P["cal"][k])
        if q is not None:
            sl[q] = rr[k]
            inpos[q] = st[k] > 0
    c = CS.COST["us"]
    cur = CO.scenario("cur", mk, cal, Q["px"], Q["tot"], Q["rf"], Q["F"], pa, pb, c, core=core)
    new = CO.scenario("plan", mk, cal, Q["px"], Q["tot"], Q["rf"], Q["F"], pa, pb, c, sl=sl, inpos=inpos, c_stk=c_stk, sleeve="qm",
                      core=core)
    return new, cur


# ── 研究 ─────────────────────────────────────────────────────────────────────

def _sym(C: dict, j: int) -> str:
    return C["P"]["sym"][j]


def _pnl_top(C: dict, r: dict, k: int = 8) -> list[list]:
    p: dict[int, float] = {}
    for t in r["trades"]:
        p[t[0]] = p.get(t[0], 0.0) + t[4] * t[6]
    tot = sum(p.values())
    return [[_sym(C, j), v / tot if tot else None] for j, v in sorted(p.items(), key=lambda x: -x[1])[:k]]


def _brief_stats(st: dict) -> dict:
    return {"cagr": st["cagr"], "mdd": st["mdd"], "m": st["m"], "halves": [h["cagr"] for h in st["halves"]]}


def roll_wins(C: dict, rr: np.ndarray, base: np.ndarray, a: int, years: int = 3) -> list[int]:
    """每個月第一個交易日起算的 years 年，策略贏 base 的次數／總次數（只描述）。"""
    cal, T = C["cal"], C["T"]
    starts = [k for k in range(a + 1, T) if cal[k][:7] != cal[k - 1][:7]]
    ok = n = 0
    e = 0
    for k in starts:
        end_d = f"{int(cal[k][:4]) + years}{cal[k][4:]}"
        e = max(e, k)
        while e < T and cal[e] < end_d:
            e += 1
        if e >= T:
            break
        s = float(np.prod(1 + rr[k + 1:e + 1]))
        bb = float(np.prod(1 + np.nan_to_num(base[k + 1:e + 1])))
        n += 1
        ok += s > bb
    return [ok, n]


def review_dist(C: dict, rr: np.ndarray, base: np.ndarray, a: int) -> dict:
    """檢討用：回測裡同長度窗口（每週起算、a 起）三成本身對 S&P 500 含息的超額（ln）分布 → 0～100 百分位的值。"""
    wk = [i for i in sorted(C["cols"]["wk"]) if i >= a]
    lr = np.log1p(rr)
    lb = np.log1p(np.nan_to_num(base))
    cs, cb = np.concatenate([[0.0], np.cumsum(lr)]), np.concatenate([[0.0], np.cumsum(lb)])
    out = {}
    for L in X.QM_REVIEW:
        xs = [float((cs[i + L + 1] - cs[i + 1]) - (cb[i + L + 1] - cb[i + 1])) for i in wk if i + L < C["T"]]
        out[str(L)] = {"n": len(xs), "q": [round(float(v), 5) for v in np.quantile(xs, np.linspace(0, 1, 101))] if xs else []}
    return out


def research(C: dict, log=print) -> dict:
    t0 = time.time()
    cal, T = C["cal"], C["T"]
    a, a14 = a_of(cal, X.QM_Y0), a_of(cal, X.QM_EVAL)
    m = qm_mask(C["cols"]["f"])
    sig = signals(C, m)
    spx_idle = C["PQ"]["spx"]["idle"]
    out = {"ver": X.VER, "spec": X.SPEC_DATE, "made": date.today().isoformat(), "last": cal[-1], "a": cal[a], "eval": cal[a14],
           "rule": {"qm": X.QM, "slots": X.QM_SLOTS, "exit": X.QM_EXIT}, "weeks": int(sum(1 for i in sig if i > a)),
           "signals": int(sum(len(v) for i, v in sig.items() if i > a))}
    R = {(mk, ck): run(C, sig, mk, c) for mk in X.QM_PLANS for ck, c in (("main", X.COST["stk"]), ("alt", X.COST["stk_alt"]))}
    log(f"[ussxqm] 帳戶 {time.time() - t0:.0f}s")
    spx_tr = BK.curve_stats(cal, spx_idle, a14, T)
    ew = BK.curve_stats(cal, C["ew"] if "ew" in C else UR.ew_returns(C["P"], C["el"], C["Cf"]), a14, T)
    j_q = C["P"]["col"].get("QQQ")
    qqq = np.zeros(T)
    if j_q is not None:
        q = C["Cf"][:, j_q]
        with np.errstate(invalid="ignore", divide="ignore"):
            qqq[1:] = np.nan_to_num(q[1:] / q[:-1] - 1)
    out["bench"] = {"spx_tr": spx_tr, "ew": ew, "qqq": BK.curve_stats(cal, qqq, a14, T),
                    "ndx": BK.curve_stats(cal, C["PQ"]["ndx"]["idle"], a14, T)}
    sleeve = {ck: BK.curve_stats(cal, rets(C, R[("spx", ck)]), a14, T) for ck in ("main", "alt")}
    out["sleeve"] = sleeve
    rs = R[("spx", "main")]
    out["trades"] = BK.trade_stats(rs["trades"], cal)
    for t in out["trades"].get("best", []):
        t["c"] = _sym(C, t.pop("j"))
    out["exposure"] = float(np.mean(rs["stk"][a14 - a:]))
    out["top"] = _pnl_top(C, rs)
    # 放進交易計畫
    plans, sc = {}, {}
    JB = X.QM_JUDGE_BASE
    for mk in X.QM_PLANS:
        for ck, c in (("main", X.COST["stk"]), ("alt", X.COST["stk_alt"])):
            r = R[(mk, ck)]
            new, cur = plan_scenarios(C, mk, rets(C, r), stk_share(C, r), a14, T, c)
            # VER 5：判定 ② 跟現在在用的計畫比（VER 3 的設定：核心 70%、機動放 QM、空位放指數；同一個成本）；cur＝機動放指數（只描述）
            rb = run(C, sig, mk, c, idle=JB["idle"])
            base = plan_scenarios(C, mk, rets(C, rb), stk_share(C, rb), a14, T, c, core=JB["core"])[0]
            plans[f"{mk}_{ck}"] = {"new": SW._brief(new), "cur": SW._brief(cur), "base": SW._brief(base), "judge": SW.judge(new, base)}
            if ck == "main":
                sc[mk] = new
    out["plans"], out["sc"] = plans, sc
    log(f"[ussxqm] 計畫 {time.time() - t0:.0f}s")
    # 判定 ①～④（同 ussxrun.books）
    def beats(st):
        ok_sp = st["cagr"] > spx_tr["cagr"] and all(h["cagr"] > hs["cagr"] for h, hs in zip(st["halves"], spx_tr["halves"]))
        ok_ew = st["cagr"] > ew["cagr"] and all(h["cagr"] > he["cagr"] for h, he in zip(st["halves"], ew["halves"]))
        return {"spx": bool(ok_sp), "ew": bool(ok_ew)}
    try:
        G = json.loads(SURV.read_text(encoding="utf-8")).get("G")
    except (OSError, ValueError):
        G = None
    v = {"c1": beats(sleeve["main"]), "c1_alt": beats(sleeve["alt"]), "surv_G": G}
    v["c2"] = {mk: plans[f"{mk}_main"]["judge"]["pass"] for mk in X.QM_PLANS}
    v["c3"] = {mk: bool(v["c1_alt"]["spx"] and v["c1_alt"]["ew"] and plans[f"{mk}_alt"]["judge"]["pass"]) for mk in X.QM_PLANS}
    v["c4"] = bool(G is not None and G * 100 < X.PASS["surv_max"])
    c1 = v["c1"]["spx"] and v["c1"]["ew"]
    v["need_alt"] = X.QM_NEED_ALT                                         # VER 6：③（複委託）照算、只描述
    v["pass"] = {mk: bool(c1 and v["c2"][mk] and (v["c3"][mk] or not X.QM_NEED_ALT) and v["c4"]) for mk in X.QM_PLANS}
    out["verdict"] = v
    # 重現第 12 節：照 VER 3 的設定（空位放指數、核心 70%）另外跑一次（ussxspec VER 4 ③）
    RS = X.QM_REPRO_SET
    r3 = run(C, sig, "spx", X.COST["stk"], idle=RS["idle"])
    rc = BK.curve_stats(cal, rets(C, r3), a14, T)["cagr"]
    rm = plan_scenarios(C, "spx", rets(C, r3), stk_share(C, r3), a14, T, X.COST["stk"], core=RS["core"])[0]["plan"]["m"]
    out["repro"] = {"cagr": rc, "plan_m": rm, "ref": X.QM_REF, "tol": X.QM_REPRO, "set": RS,
                    "ok": bool(abs(rc - X.QM_REF["cagr"]) <= X.QM_REPRO["cagr"] and abs(rm - X.QM_REF["plan_m"]) <= X.QM_REPRO["plan_m"])}
    out["switch"] = {mk: bool(out["repro"]["ok"] and v["pass"][mk]) for mk in X.QM_PLANS}
    # 只描述
    rr = rets(C, rs)
    desc: dict = {"roll3": roll_wins(C, rr, spx_idle, a14), "years": {y: [sleeve["main"]["years"].get(y), spx_tr["years"].get(y),
                                                                         ew["years"].get(y)] for y in sleeve["main"]["years"]}}
    top = [s for s, _ in out["top"]]
    drop = {}
    for k in X.QM_DROP:
        js = frozenset(C["P"]["col"][s] for s in top[:k])
        drop[str(k)] = {"syms": top[:k], **_brief_stats(BK.curve_stats(cal, rets(C, run(C, signals(C, m, drop=js))), a14, T))}
    desc["drop"] = drop
    desc["lag1"] = _brief_stats(BK.curve_stats(cal, rets(C, run(C, lag_week(C, sig))), a14, T))
    nb = {}
    for key, vals in X.QM_NB.items():
        for val in vals:
            mm = qm_mask(C["cols"]["f"], {**X.QM, key: val})
            nb[f"{key}={val:g}"] = _brief_stats(BK.curve_stats(cal, rets(C, run(C, signals(C, mm))), a14, T))
    desc["nb"] = nb
    out["desc"] = desc
    out["review"] = review_dist(C, rr, spx_idle, a14)
    out["now"] = snapshot(C, rs, sig)
    out["idle"] = X.QM_IDLE
    out["core"] = {mk: CS.core_of(mk) for mk in X.QM_PLANS}
    log(f"[ussxqm] 完成 {time.time() - t0:.0f}s：重現（VER 3 設定）三成本身 {rc * 100:.2f}%、計畫 {rm * 100:,.1f} 萬 → {out['repro']['ok']}；"
        f"VER {X.VER} 三成本身 {sleeve['main']['cagr'] * 100:.2f}%、計畫 {sc['spx']['plan']['m'] * 100:,.1f} 萬；判定 {v['pass']}")
    return out


# ── 最新一天收盤後 ─────────────────────────────────────────────────────────────

def _raw(C: dict, A: np.ndarray, i: int, j: int) -> float | None:
    """含息價 → 那天的實際成交價（同一天開高低收的倍數相同）。"""
    P = C["P"]
    c, raw, x = P["C"][i, j], P["RAW"][i, j], A[i, j]
    if not (np.isfinite(c) and np.isfinite(raw) and np.isfinite(x) and c > 0):
        return None
    return float(x * raw / c)


def _met(C: dict, i: int, js) -> dict[int, list]:
    """第 i 天（週訊號日）那一週 QM 的五個條件，順序同 KEYS（強度、離 52 週高點、營益率、近四季 ROE、市值）：
    {代號欄: [五個數]}。那一週不在範圍內（沒有樣本列）的代號不列。"""
    def rd(key, x):                                          # 強度一位小數、市值到百萬美元、比例四位小數；沒有值＝存成 null
        if not math.isfinite(x):
            return x
        return round(x, 1) if key == "rs" else round(x / 1e6) * 1e6 if key == "cap" else round(x, 4)

    cols = C["cols"]
    want = {int(j) for j in js}
    out = {}
    for k in np.nonzero(cols["di"] == i)[0]:
        j = int(cols["j"][k])
        if j in want:
            out[j] = [rd(key, float(cols["f"][key][k])) for key in KEYS]
    return out


def snapshot(C: dict, r: dict, sig: dict[int, list]) -> dict:
    """最新一天收盤後：持股（買進日、買進價、收盤、50 日線、占三成多少、曾經站上均線沒有）、明天開盤要賣的、
    最新一週的名單（前 QM_LIST 名）與明天開盤要買的（有空位才買，依名單順序）。價格都是實際成交價。
    met＝這一週（wk）手上、要買、名單前 QM_LIST 名的五個條件；met0＝手上的股票買進那一週的五個條件（為什麼選它；
    docs/lab_cfg_v2_plan.md 第 4 節）。"""
    P, cal, T = C["P"], C["cal"], C["T"]
    t = T - 1
    S = r["state"]
    eq = float(r["eq"][-1])
    hold = []
    for j, q in sorted(S["pos"].items(), key=lambda x: (x[1]["ei"], _sym(C, x[0]))):
        ei = q["ei"]
        cl, ma = C["Cf"][t, j], C["MA"][t, j]
        hold.append({"c": _sym(C, j), "ent": cal[ei], "epx": _raw(C, P["O"], ei, j), "px": _raw(C, C["Cf"], t, j),
                     "ma": _raw(C, C["MA"], t, j) if np.isfinite(ma) else None,
                     "r": float(cl / q["epx"] - 1) if q["epx"] > 0 else None, "w": float(q["k"] * cl / eq) if eq > 0 else None,
                     "above": bool(q["above"]), "sell": j in S["pend"]})
    wks = [i for i in sorted(sig) if i <= t]
    wd = wks[-1] if wks else None
    lst = [{"c": _sym(C, j), "rs": round(sc, 1)} for j, sc in (sig.get(wd) or [])[:X.QM_LIST]] if wd is not None else []
    done = wd is not None and week_done(cal[wd])
    buy, bj = [], []
    if wd == t and done:                                     # 最新一天就是（已經結束的一週的）週訊號日：明天開盤照名單補空位
        free = X.QM_SLOTS - (len(S["pos"]) - len(S["pend"]))
        for j, sc in sig[t]:
            if len(buy) >= free:
                break
            if j not in S["pos"]:
                buy.append(_sym(C, j))
                bj.append(j)
    met, met0 = {}, {}
    if wd is not None:
        js = list(S["pos"]) + bj + [j for j, _ in (sig.get(wd) or [])[:X.QM_LIST]]
        met = {_sym(C, j): v for j, v in _met(C, wd, js).items()}
    for j, q in S["pos"].items():
        si = q.get("si")
        v = _met(C, si, [j]).get(j) if si is not None else None
        if v is not None:
            met0[_sym(C, j)] = {"wk": cal[si], "v": v}
    return {"d": cal[t], "wk": cal[wd] if wd is not None else None, "wk_done": bool(done), "hold": hold,
            "sell": [h["c"] for h in hold if h["sell"]], "buy": buy, "list": lst,
            "n_list": len(sig.get(wd) or []) if wd is not None else 0, "idle": float(S["idle"] / eq) if eq > 0 else None,
            "next": next_day(cal[t]), "met": met, "met0": met0}


def next_day(d: str) -> str:
    """d 之後的第一個美股交易日（NYSE 休市表；xstrat 同一套）。"""
    from . import xstrat as XT
    return XT.future_days("spx", d, 1)[0]


def week_done(d: str) -> bool:
    """d 是不是那一週（ISO 週）的最後一個交易日：下一個交易日在之後的週。資料停在週中＝這一週還沒結束（名單還不算數）。"""
    a, b = date.fromisoformat(d).isocalendar()[:2], date.fromisoformat(next_day(d)).isocalendar()[:2]
    return a != b


# ── 存讀 ─────────────────────────────────────────────────────────────────────

def _clean(x):
    if isinstance(x, float):
        return None if not math.isfinite(x) else round(x, 6)
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating,)):
        return _clean(float(x))
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def save(R: dict, path: Path | None = None) -> bool:
    p = path or RES
    txt = json.dumps(_clean(R), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.write_text(txt, encoding="utf-8")
    return True


def load(path: Path | None = None) -> dict | None:
    """研究檔；版本不同＝沒有（頁面照舊放指數）。"""
    try:
        R = json.loads((path or RES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == X.VER else None


# ── 上線：每週紀錄（只增不改）──────────────────────────────────────────────────

LIVE = ROOT / "data" / "lab" / "ussx_qm_live.json"
WATCH = ROOT / "data" / "lab" / "ussx_qm_watch.json"


def _empty_live() -> dict:
    return {"ver": X.VER, "start": None, "weeks": {}, "diff": [], "curve": None, "now": None}


def load_live(path: Path | None = None) -> dict:
    """前瞻紀錄；版本不同＝從頭記。"""
    try:
        L = json.loads((path or LIVE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty_live()
    return L if L.get("ver") == X.VER else _empty_live()


def _held_at(C: dict, r: dict, i: int) -> list[dict]:
    """第 i 天收盤時拿著的股票（由逐筆交易重建）：買進日、買進價、收盤、占三成多少、那天收盤有沒有標記要賣。"""
    P, cal = C["P"], C["cal"]
    a = r["a"]
    e = float(r["eq"][i - a])
    out = []
    for j, si, ei, xi, ret, why, cin in r["trades"]:
        if not (ei <= i and (xi > i or why == "open")):
            continue
        epx = P["O"][ei, j]
        k = cin / (1 + X.COST["stk"]) / epx if epx > 0 else 0.0
        cl = C["Cf"][i, j]
        out.append({"c": _sym(C, j), "ent": cal[ei], "epx": _raw(C, P["O"], ei, j), "px": _raw(C, C["Cf"], i, j),
                    "ma": _raw(C, C["MA"], i, j) if np.isfinite(C["MA"][i, j]) else None,
                    "r": float(cl / epx - 1) if epx > 0 else None, "w": float(k * cl / e) if e > 0 else None,
                    "sell": bool(why != "open" and xi == i + 1)})
    return sorted(out, key=lambda h: (h["ent"], h["c"]))


def _trades_between(C: dict, r: dict, i0: int, i1: int) -> list[dict]:
    """第 i0 天收盤之後、到第 i1 天為止的買賣（開盤成交；實際成交價）。"""
    P, cal = C["P"], C["cal"]
    out = []
    for j, si, ei, xi, ret, why, cin in r["trades"]:
        if i0 < ei <= i1:
            out.append({"c": _sym(C, j), "act": "buy", "d": cal[ei], "px": _raw(C, P["O"], ei, j)})
        if why != "open" and i0 < xi <= i1:
            px = _raw(C, C["Cf"], int(P["last"][j]), j) if why == "delisted" else _raw(C, P["O"], xi, j)
            out.append({"c": _sym(C, j), "act": "sell", "d": cal[xi], "px": px, "why": why, "ret": float(ret)})
    return sorted(out, key=lambda x: (x["d"], x["act"] != "sell", x["c"]))


def live_update(C: dict, r: dict, sig: dict[int, list], L: dict | None = None, made: str | None = None) -> dict:
    """用到最新一天的資料重跑之後：每一個新的、已經結束的週訊號日（QM_LIVE 起）各記一筆；已經記下的週不改，
    重跑結果不同時另記一筆差異。另外更新從起點以來每天的淨值（curve）與最新一天的狀態（now）。r＝run(C, sig, "spx")。"""
    cal, T = C["cal"], C["T"]
    L = L if L is not None else load_live()
    a = r["a"]
    wk = [i for i in sorted(C["cols"]["wk"]) if cal[i] >= X.QM_LIVE and i < T and week_done(cal[i])]
    if not wk:
        L["now"] = snapshot(C, r, sig)
        return L
    s = wk[0]
    if L.get("start") and L["start"] != cal[s]:
        L.setdefault("diff", []).append({"d": cal[T - 1], "what": f"起點不同：紀錄 {L['start']}、重跑 {cal[s]}"})
    L["start"] = L.get("start") or cal[s]
    eq = r["eq"]
    idle = C["PQ"]["spx"]["idle"]
    nav = lambda i: float(eq[i - a] / eq[s - a])
    spx = lambda i: float(np.prod(1 + np.nan_to_num(idle[s + 1:i + 1])))
    weeks = L.setdefault("weeks", {})
    prev = None
    for i in wk:
        d = cal[i]
        rec = {"list": [{"c": _sym(C, j), "rs": round(sc, 1)} for j, sc in (sig.get(i) or [])[:X.QM_LIST]],
               "n_list": len(sig.get(i) or []), "hold": _held_at(C, r, i),
               "trades": _trades_between(C, r, prev if prev is not None else i, i), "nav": nav(i), "spx": spx(i),
               "buy_next": [x["c"] for x in _trades_between(C, r, i, i + 1) if x["act"] == "buy"] if i + 1 < T else None}
        rec["sell_next"] = [h["c"] for h in rec["hold"] if h["sell"]]
        if d not in weeks:
            weeks[d] = {**rec, "made": made or date.today().isoformat()}
        else:
            old = weeks[d]
            if [h["c"] for h in old.get("hold") or []] != [h["c"] for h in rec["hold"]] or \
                    [(x["c"], x["act"], x["d"]) for x in old.get("trades") or []] != [(x["c"], x["act"], x["d"]) for x in rec["trades"]]:
                note = f"{d} 那一週重跑的持股或買賣和紀錄不同"
                if not any(x.get("what") == note for x in L.get("diff") or []):
                    L.setdefault("diff", []).append({"d": cal[T - 1], "what": note})
            if old.get("buy_next") is None and rec["buy_next"] is not None:     # 記的時候還不知道隔天的開盤，之後補上
                old["buy_next"] = rec["buy_next"]
        prev = i
    L["curve"] = {"d": [cal[i] for i in range(s, T)], "nav": [round(nav(i), 6) for i in range(s, T)],
                  "spx": [round(spx(i), 6) for i in range(s, T)]}
    L["now"] = snapshot(C, r, sig)
    L["ver"] = X.VER
    return L


def save_live(L: dict, path: Path | None = None) -> bool:
    return save(L, path or LIVE)


def review_now(L: dict, R: dict | None) -> list[dict]:
    """滿 QM_REVIEW 個交易日的檢討：三成本身對 S&P 500 含息的超額（ln）在回測同長度窗口分布裡的百分位，低於 QM_P_LOW＝比回測差。"""
    cv = (L or {}).get("curve") or {}
    out = []
    n = len(cv.get("d") or []) - 1
    for k in X.QM_REVIEW:
        if n < k:
            out.append({"k": k, "due": None})
            continue
        ex = math.log(cv["nav"][k]) - math.log(cv["spx"][k])
        q = (((R or {}).get("review") or {}).get(str(k)) or {}).get("q") or []
        pct = None
        if q:
            pct = float(np.interp(ex, q, np.linspace(0, 1, len(q)))) if q[0] < q[-1] else None
        out.append({"k": k, "d": cv["d"][k], "ex": ex, "pct": pct, "low": bool(pct is not None and pct < X.QM_P_LOW)})
    return out


# ── 上線：每天檢查持股有沒有跌破 50 日線（main 的盤後刷新）────────────────────────

def watch_one(h: dict, base: str, s: dict | None) -> dict:
    """一檔持股：s＝Yahoo 日線（ussxdata.parse_chart；分割還原、配息另列）。從紀錄那天（base）的下一個交易日起逐日看：
    收盤 ≥ 50 日線＝站上；站上過以後收盤 < 50 日線＝下一個交易日開盤賣（同 ussxbook.run 的 trend＋ma）。"""
    from . import ussxdata as UD
    n = X.QM_EXIT["ma"]
    out = {"c": h["c"], "trig": None}
    if not s or len(s.get("d") or []) < n:
        out["err"] = "抓不到日線"
        return out
    tr = UD.total_return_close(s)
    ds, cs = s["d"], s["c"]
    above = bool(h.get("above"))
    for k in range(n - 1, len(ds)):
        if ds[k] <= base:
            continue
        ma = sum(tr[k - n + 1:k + 1]) / n
        if tr[k] >= ma:
            above = True
        elif above:
            out["trig"] = ds[k]
            out["on"] = next_day(ds[k])
            break
    k = len(ds) - 1
    ma = sum(tr[k - n + 1:k + 1]) / n
    out.update({"d": ds[k], "px": cs[k], "ma": ma * cs[k] / tr[k] if tr[k] > 0 else None,
                "pct": tr[k] / ma - 1 if ma > 0 else None, "above": above})
    return out


def watch(L: dict | None = None, fetch=None, made: str | None = None) -> dict:
    """最新一週紀錄的持股，逐檔抓 Yahoo 日線（ussxdata.fetch_since，從買進前約 150 天起）檢查。只是頁面提醒，帳以每週重跑為準。"""
    from datetime import timedelta
    from . import ussxdata as UD
    L = L if L is not None else load_live()
    now = L.get("now") or {}
    fetch = fetch or (lambda c, st: UD.fetch_since(c, st, timeout=20))    # 每天的檢查最多 8 檔：一檔最多等 20 秒（整支 180 秒內跑完）
    out = {"ver": X.VER, "made": made or date.today().isoformat(), "base": now.get("d"), "hold": [], "sell": [], "err": []}
    for h in now.get("hold") or []:
        start = (date.fromisoformat(h["ent"]) - timedelta(days=150)).isoformat()
        try:
            _, s, msg = fetch(h["c"], start)
        except Exception as e:                               # noqa: BLE001 —— 抓不到只少那一檔的提醒
            s, msg = None, f"{type(e).__name__}: {e}"
        w = watch_one(h, now.get("d") or "", s)
        if w.get("err"):
            out["err"].append({"c": h["c"], "msg": msg if msg != "ok" else w["err"]})
        out["hold"].append(w)
        if w.get("trig"):
            out["sell"].append({"c": h["c"], "trig": w["trig"], "on": w["on"]})
    ds = [w["d"] for w in out["hold"] if w.get("d")]
    out["d"] = max(ds) if ds else None
    return out


def save_watch(W: dict, path: Path | None = None) -> bool:
    return save(W, path or WATCH)


def load_watch(path: Path | None = None) -> dict | None:
    try:
        W = json.loads((path or WATCH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return W if W.get("ver") == X.VER else None
