"""期貨加碼（規格 arm/lab/tiltspec.py；docs/lab_tilt_plan.md）。

平常 100% 抱著指數，買點出現時另外用期貨多拿 ADD，和「一直抱著」「固定加碼同樣多」比：
  K1～K3  總經策略每年 1 月 1 日重新判定（同實戰模擬 M2），當年 ★／● 的策略任何一條持有中＝加碼
  K4      收盤在 200 日均線上＝加碼
  K5      溫度計短線偏多多（實戰模擬 B1 同一串決定）＝加碼
加碼那一份照期貨的持有成本算（含息報酬 − 利率），每一邊十萬分之五＋換月。
研究：TZ=Asia/Taipei python3 scripts/run_tilt.py → data/lab/tilt_research.json（資料或規格改了才重跑）。
tests/test_tilt.py 和逐筆直接算的版本比對。
"""
from __future__ import annotations

import bisect
import json
import math
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import heatpos as HP
from . import practsim as PS
from . import practspec as PSS
from . import tiltspec as S
from . import xstrat as XT
from . import xstratspec as XS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "tilt_research.json"


# ── 報酬、利率、天數 ─────────────────────────────────────────────────────────

def day_gaps(cal: list[str]) -> np.ndarray:
    """第 k−1 天到第 k 天的日曆天數（第 0 天＝0）。"""
    out = np.zeros(len(cal))
    for k in range(1, len(cal)):
        out[k] = (date.fromisoformat(cal[k]) - date.fromisoformat(cal[k - 1])).days
    return out


def tr_series(cal: list[str], q: dict) -> np.ndarray:
    """加權報酬指數對到日曆（沒有＝nan）。"""
    return np.array([float(q[d]) if q.get(d) else np.nan for d in cal])


def div_tw(px: np.ndarray, tr: np.ndarray) -> np.ndarray:
    """台股每天的股息報酬（tiltspec 第 2 節）：有報酬指數的第 k 天＝TR_k ÷ TR_{k'} − P_k ÷ P_{k'}（k'＝前一個有報酬指數的日子，
    兩天之間的股息都算在第 k 天）；沒有報酬指數的日子＝0。"""
    out = np.zeros(len(px))
    prev = None
    for k in range(len(px)):
        if not np.isfinite(tr[k]) or not (px[k] > 0):
            continue
        if prev is not None:
            out[k] = tr[k] / tr[prev] - px[k] / px[prev]
        prev = k
    return out


def asof_monthly(cal: list[str], mv: dict[str, float]) -> np.ndarray:
    """每天用「前一天那個月或之前最近一個月」的月資料（第 k 天的值＝第 k−1 天所在月份；第 0 天＝nan）。"""
    ms = sorted(m for m, v in mv.items() if v is not None)
    out = np.full(len(cal), np.nan)
    for k in range(1, len(cal)):
        i = bisect.bisect_right(ms, cal[k - 1][:7]) - 1
        if i >= 0:
            out[k] = float(mv[ms[i]])
    return out


def asof_daily(cal: list[str], dv: dict[str, float]) -> np.ndarray:
    """每天用第 k−1 天或之前最近的日資料（第 0 天＝nan）。"""
    ds = sorted(d for d, v in dv.items() if v is not None)
    out = np.full(len(cal), np.nan)
    for k in range(1, len(cal)):
        i = bisect.bisect_right(ds, cal[k - 1]) - 1
        if i >= 0:
            out[k] = float(dv[ds[i]])
    return out


def div_spx(cal: list[str], shiller: dict) -> np.ndarray:
    """S&P 500 每天的股息報酬：第 k−1 天那個月（沒有值就往前找）的 D ÷ P × 天數 ÷ 365（Shiller：[P, D, E, CPI, 10 年債]）。"""
    dp = {m: v[1] / v[0] for m, v in shiller.items() if v and v[0] and v[1]}
    return np.nan_to_num(asof_monthly(cal, dp), nan=0.0) * day_gaps(cal) / S.DAY_COUNT


def carry_inputs(mk: str, cal: list[str], px: np.ndarray, D: dict | None = None) -> dict:
    """加碼那一份每天的含息報酬與利率（tiltspec 第 2 節）。D＝{"tr": {日期: 報酬指數}, "effr": {日期: %}, "cbc": {月: %},
    "shiller": {月: [...]}}（沒給就讀資料檔）。→ {"tot": 含息漲跌, "rate": 年利率（小數）, "days": 天數, "tr0": 台股第一個有報酬指數的日子}"""
    D = D if D is not None else load_carry()
    r = PS.daily_ret(px)
    days = day_gaps(cal)
    out = {"days": days, "tr0": None}
    if mk == "tw":
        tr = tr_series(cal, D.get("tr") or {})
        out["tot"] = r + div_tw(px, tr)
        ok = np.nonzero(np.isfinite(tr))[0]
        out["tr0"] = cal[int(ok[0])] if len(ok) else None
        rate = asof_monthly(cal, D.get("cbc") or {})
    else:
        out["tot"] = r + (div_spx(cal, D.get("shiller") or {}) if mk == "spx" else 0.0)
        rate = asof_daily(cal, D.get("effr") or {})
    out["rate"] = np.nan_to_num(rate, nan=0.0) / 100.0
    return out


def load_carry() -> dict:
    from . import heatdata as HD
    from . import store
    tr = (store.read_json("v3_tr.json", {}) or {}).get("q") or {}
    cb = (HD.load("cbcbank") or {})
    return {"tr": tr, "effr": HD.load("effr") or {}, "shiller": HD.load("us_shiller") or {},
            "cbc": {m: v[3] for m, v in cb.items() if v and len(v) > 3 and v[3] is not None}}


# ── 換月 ────────────────────────────────────────────────────────────────────

def nth_weekday(y: int, m: int, wd: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(days=7 * (n - 1))


def roll_flags(mk: str, cal: list[str]) -> np.ndarray:
    """轉倉日（tiltspec 第 3 節）：台指期＝每個月第三個星期三，美股＝3、6、9、12 月第三個星期五；當天或之後第一個交易日。"""
    T = len(cal)
    out = np.zeros(T, dtype=bool)
    if not T:
        return out
    freq, wd = S.ROLL_TW if mk == "tw" else S.ROLL_US
    y, m = int(cal[0][:4]), int(cal[0][5:7])
    y1 = int(cal[-1][:4])
    while y <= y1:
        if freq == "monthly" or m in (3, 6, 9, 12):
            st = nth_weekday(y, m, wd, S.ROLL_NTH).isoformat()
            i = bisect.bisect_left(cal, st)
            if st >= cal[0] and i < T:
                out[i] = True
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# ── 加碼部位 ─────────────────────────────────────────────────────────────────

def any_on(cal: list[str], hp: dict[str, np.ndarray], sel: dict[int, list[str]]) -> np.ndarray:
    """第 k 天收盤之後的加碼：那一年（看第 k 天的日期）選到的策略任何一條持有中＝ADD，否則 0。"""
    T = len(cal)
    yr = np.array([int(d[:4]) for d in cal])
    on = np.zeros(T, dtype=bool)
    for y, ks in sel.items():
        m = yr == y
        for k in ks:
            if k in hp:
                on |= m & (np.asarray(hp[k]) > 0.5)
    return np.where(on, S.ADD, 0.0)


def xs_overlays(mk: str, D: dict, tiers: dict[int, dict[str, str]]) -> dict[str, np.ndarray]:
    """K1～K3：每年 tiers（practsim.xs_tiers）裡判定 ★／● 而且分組符合的策略。"""
    C = XT.Ctx(D)
    specs = {s["k"]: s for s in PS.xs_specs(mk, D)}
    hp = {k: XT.held_pos(C, s) for k, s in specs.items()}
    out = {}
    for name, R in S.RULES.items():
        if R["src"] != "xs":
            continue
        sel = {y: sorted(k for k, t in tt.items() if t in S.XS_TIERS and k in specs and specs[k]["grp"] in R["grps"])
               for y, tt in tiers.items()}
        out[name] = any_on(D["cal"], hp, sel)
        out[name + ":sel"] = sel
    out["_hp"] = hp
    return out


def ma_overlay(px: np.ndarray) -> np.ndarray:
    """K4：收盤在 200 日均線上＝ADD（第 t＋LAG 天收盤照做；均線沒有值＝nan）。"""
    p = XT.pos_daily_ma(px, S.MA_N, S.LAG)
    return np.where(np.isnan(p), np.nan, p * S.ADD)


def thermo_overlay(cal: list[str], Fcal: list[str], W: dict) -> tuple[np.ndarray, str | None]:
    """K5：practspec B1 的決定（偏多多＝FULL）→ ADD，否則 0；對到 cal（溫度計的日曆沒有的日子、起點之前＝nan）。→ (加碼, 起點日期)"""
    pos, s0, _ = PS.thermo_positions(len(Fcal), W)
    b1 = pos["B1"]
    on = PSS.THERMO_RULES["B1"]["on"]
    ix = {d: i for i, d in enumerate(Fcal)}
    out = np.full(len(cal), np.nan)
    for k, d in enumerate(cal):
        i = ix.get(d)
        if i is not None and np.isfinite(b1[i]):
            out[k] = S.ADD if abs(b1[i] - on) < 1e-12 else 0.0
    return out, (Fcal[s0] if s0 is not None else None)


# ── 淨值 ────────────────────────────────────────────────────────────────────

def costs(a: np.ndarray, roll: np.ndarray, a0: int) -> np.ndarray:
    """第 k 天收盤的成本：|a_k − a_{k−1}| × COST_FUT ＋ 轉倉日 min(a_{k−1}, a_k) × 2 × COST_FUT；第 a0 天以前（含）＝0。"""
    T = len(a)
    c = np.zeros(T)
    c[1:] = np.abs(np.diff(a)) * S.COST_FUT + roll[1:] * np.minimum(a[:-1], a[1:]) * 2.0 * S.COST_FUT
    c[:a0 + 1] = 0.0
    return c


def day_ret(r: np.ndarray, Cy: dict, a: np.ndarray, cost: np.ndarray, a0: int, b: int) -> np.ndarray:
    """第 a0＋1～b−1 天每天的報酬：（1 ＋ 本金 ＋ a_{k−1} ×（含息漲跌 − 利率 × 天數 ÷ 365））×（1 − 成本_k）− 1。"""
    tot, rate, days = Cy["tot"], Cy["rate"], Cy["days"]
    k = np.arange(a0 + 1, b)
    g = r[k] + a[k - 1] * (tot[k] - rate[k] * days[k] / S.DAY_COUNT)
    return (1.0 + g) * (1.0 - cost[k]) - 1.0


def fixed(T: int, abar: float) -> np.ndarray:
    return np.full(T, abar)


def compare(cal: list[str], r: np.ndarray, Cy: dict, roll: np.ndarray, a: np.ndarray, a0: int, b: int) -> dict:
    """同一段期間的規則、固定加碼同樣多（每天加碼規則在這段期間的平均，只收轉倉成本）、一直抱著。"""
    dr = day_ret(r, Cy, a, costs(a, roll, a0), a0, b)
    abar = float(np.mean(a[a0:b - 1])) if b - 1 > a0 else 0.0
    f = fixed(len(a), abar)
    df = day_ret(r, Cy, f, costs(f, roll, a0), a0, b)
    st = PS.stats(cal, dr, a0, b, a[a0:b - 1])
    st["starts"] = float(np.count_nonzero((a[a0 + 1:b] > 0) & (a[a0:b - 1] <= 0)) / st["yrs"])
    st["share"] = float(np.mean(a[a0:b - 1] > 0)) if b - 1 > a0 else 0.0
    return {"rule": st, "fix": PS.stats(cal, df, a0, b), "bh": PS.stats(cal, r[a0 + 1:b], a0, b), "abar": abar}


def verdict(full: dict, h1: dict, h2: dict) -> str:
    """tiltspec 第 7 節：better＝全期間與前後兩半年化都比固定加碼高、全期間最大回撤不比較大；worse＝三段年化都比較低。"""
    gt = [x["rule"]["cagr"] > x["fix"]["cagr"] for x in (full, h1, h2)]
    lt = [x["rule"]["cagr"] < x["fix"]["cagr"] for x in (full, h1, h2)]
    if all(gt) and full["rule"]["mdd"] <= full["fix"]["mdd"] + 1e-12:
        return "better"
    if all(lt):
        return "worse"
    return "same"


def nav(dr: np.ndarray) -> np.ndarray:
    return np.concatenate([[1.0], np.cumprod(1.0 + dr)])


def episodes(cal: list[str], px: np.ndarray, a: np.ndarray, nv: np.ndarray, a0: int, b: int) -> dict:
    """每一段加碼（第 s 天收盤開始有加碼、第 e 天收盤平掉；期間內 a ＞ 0）：淨值漲跌 − 指數漲跌（＝這次加碼多賺或少賺了帳戶的幾 %）。
    nv＝規則的淨值（第 a0 天＝1，nv[i] 是第 a0＋i 天）。最後還在加碼中的一段算到最後一天、標 open。"""
    out = []
    s = None
    for k in range(a0, b):
        on = a[k] > 0
        if on and s is None:
            s = k
        elif not on and s is not None:
            out.append((s, k, False))
            s = None
    if s is not None:
        out.append((s, b - 1, True))
    rows = []
    for s, e, op in out:
        if e <= s:
            continue
        x = float(nv[e - a0] / nv[s - a0] - px[e] / px[s])
        rows.append([cal[s], cal[e], round(x, 6), int(e - s), op])
    xs = [r[2] for r in rows if not r[4]]
    return {"n": len(xs), "win": (sum(1 for v in xs if v > 0) / len(xs)) if xs else None,
            "med": float(np.median(xs)) if xs else None, "worst": min(xs) if xs else None,
            "best": max(xs) if xs else None, "sum": float(sum(xs)) if xs else None, "list": rows}


def bears(cal: list[str], px: np.ndarray, nv: np.ndarray, nf: np.ndarray, a0: int) -> list[dict]:
    """每一段大跌（指數收盤跌 BEAR 以上，hotdd.declines；評估期間內）：高點到低點規則、固定加碼、指數的變化。"""
    from . import hotdd as HDD
    out = []
    T = len(cal)
    for e in HDD.declines(cal[a0:], px[a0:], S.BEAR):
        pk, tr = a0 + e["pk"], a0 + e["tr"]
        if tr <= pk:
            continue
        out.append({"pk": cal[pk], "tr": cal[tr], "bh": float(px[tr] / px[pk] - 1.0),
                    "rule": float(nv[tr - a0] / nv[pk - a0] - 1.0), "fix": float(nf[tr - a0] / nf[pk - a0] - 1.0),
                    "open": bool(e["open"]) or tr == T - 1})
    return out


def boot_ci(dr: np.ndarray, df: np.ndarray, key: str) -> list[float] | None:
    """規則減固定加碼的年化對數報酬差：BOOT_BLOCK 天一塊的循環區塊重抽 BOOT_DRAWS 次的 95% 區間（只呈現）。"""
    n, L = len(dr), S.BOOT_BLOCK
    if n < 2 * L:
        return None
    x = np.log1p(dr) - np.log1p(df)
    rng = np.random.default_rng([S.BOOT_SEED, zlib.crc32(key.encode("utf-8"))])
    vals = np.empty(S.BOOT_DRAWS)
    for j in range(S.BOOT_DRAWS):
        st = rng.integers(0, n, size=n // L + 1)
        idx = (st[:, None] + np.arange(L)[None, :]).ravel()[:n] % n
        vals[j] = float(np.mean(x[idx])) * 252.0
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def evaluate(key: str, cal: list[str], px: np.ndarray, Cy: dict, roll: np.ndarray, a: np.ndarray, s0: int) -> dict:
    """一條規則在一個市場：全期間、前後兩半、近 10 年、判定、區間、每一段加碼、每一段大跌、現在的加碼。"""
    T = len(cal)
    r = PS.daily_ret(px)
    m = s0 + (T - s0) // 2
    full = compare(cal, r, Cy, roll, a, s0, T)
    h1, h2 = compare(cal, r, Cy, roll, a, s0, m), compare(cal, r, Cy, roll, a, m, T)
    d = date.fromisoformat(cal[-1])
    try:
        r10 = d.replace(year=d.year - S.RECENT_YEARS).isoformat()
    except ValueError:
        r10 = d.replace(year=d.year - S.RECENT_YEARS, day=28).isoformat()
    a10 = max(s0, bisect.bisect_left(cal, r10))
    rec = compare(cal, r, Cy, roll, a, a10, T)
    dr = day_ret(r, Cy, a, costs(a, roll, s0), s0, T)
    f = fixed(T, full["abar"])
    df = day_ret(r, Cy, f, costs(f, roll, s0), s0, T)
    nv, nf = nav(dr), nav(df)
    return {"full": full, "h1": h1, "h2": h2, "rec": rec, "v": verdict(full, h1, h2), "ci": boot_ci(dr, df, key),
            "ep": episodes(cal, px, a, nv, s0, T), "bears": bears(cal, px, nv, nf, s0), "now": float(a[T - 1]),
            "man": round(1_000_000 * float(nv[-1])), "man_fix": round(1_000_000 * float(nf[-1])),
            "man_bh": round(1_000_000 * float(px[T - 1] / px[s0]))}


def series(cal: list[str], px: np.ndarray, Cy: dict, roll: np.ndarray, a: np.ndarray, abar: float, s0: int,
           idx: list[int]) -> dict:
    """畫圖用（只呈現）：idx 那幾天收盤的淨值（規則、固定加碼；第 s0 天＝1）與加碼。"""
    r = PS.daily_ret(px)
    T = len(cal)
    nv = nav(day_ret(r, Cy, a, costs(a, roll, s0), s0, T))
    f = fixed(T, abar)
    nf = nav(day_ret(r, Cy, f, costs(f, roll, s0), s0, T))
    j = np.asarray(idx, dtype=np.int64) - s0
    return {"nav": [round(float(x), 4) for x in nv[j]], "fix": [round(float(x), 4) for x in nf[j]],
            "add": [round(float(a[i]), 3) for i in idx]}


# ── 一個市場 ─────────────────────────────────────────────────────────────────

def start_index(cal: list[str], dates: list[str | None]) -> int | None:
    """評估起點＝幾個起點日期最晚的那一天（在 cal 上第一個 ≥ 它的交易日）；任何一個沒有＝None。"""
    if any(d is None for d in dates):
        return None
    i = bisect.bisect_left(cal, max(dates))
    return i if i < len(cal) else None


def market(mk: str, D: dict | None = None, F: dict | None = None, W: dict | None = None,
           tiers: dict | None = None, carry: dict | None = None) -> dict:
    """一個市場的五條規則。D＝xstrat.data(mk)、F＝sigcat 的 frame（溫度計）、W＝thermocal.weekly(F)、tiers＝practsim.xs_tiers。"""
    from . import thermocal as TC
    D = D if D is not None else XT.data(mk)
    cal = list(D["cal"])
    px = np.asarray(D["px"], dtype=float)
    T = len(cal)
    y0 = PS.xs_first_year(mk)
    years = list(range(y0, int(cal[-1][:4]) + 1))
    tiers = tiers if tiers is not None else PS.xs_tiers(mk, D, years)
    X = xs_overlays(mk, D, tiers)
    ov = {k: X[k] for k in S.RULES if S.RULES[k]["src"] == "xs"}
    ov["K4"] = ma_overlay(px)
    th_start = None
    if F is not None:
        W = W if W is not None else TC.weekly(F)
        ov["K5"], th_start = thermo_overlay(cal, list(F["cal"]), W)
    Cy = carry_inputs(mk, cal, px, carry)
    ma_ok = np.nonzero(np.isfinite(ov["K4"]))[0]
    starts = {"xs": f"{y0}-01-01", "thermo": th_start, "ma": cal[int(ma_ok[0])] if len(ma_ok) else None}
    if mk == "tw":
        starts["tr"] = Cy["tr0"]
    s0 = start_index(cal, list(starts.values()))
    out = {"starts": starts, "a": cal[s0] if s0 is not None else None, "z": cal[-1], "tiers": {str(y): t for y, t in tiers.items()},
           "sel": {k: {str(y): v for y, v in X[k + ":sel"].items()} for k in ("K1", "K2", "K3")}, "rules": {}}
    if s0 is None or T - s0 < 2 * S.BOOT_BLOCK or "K5" not in ov:
        return out
    roll = roll_flags(mk, cal)
    idx = [i for i in HP.week_ends(cal) if i >= s0]
    ser = {"d": [cal[i] for i in idx], "bh": [round(float(px[i] / px[s0]), 4) for i in idx], "r": {}}
    for k in S.RULES:
        a = np.nan_to_num(ov[k], nan=0.0)
        res = evaluate(f"{k}:{mk}", cal, px, Cy, roll, a, s0)
        out["rules"][k] = res
        ser["r"][k] = series(cal, px, Cy, roll, a, res["full"]["abar"], s0, idx)
    out["series"] = ser
    hp = X["_hp"]
    yl = int(cal[-1][:4])
    out["now"] = {"d": cal[-1], "on": {k: [s for s in X[k + ":sel"].get(yl, []) if hp[s][-1] > 0.5]
                                       for k in ("K1", "K2", "K3")},
                  "ma": bool(np.nan_to_num(ov["K4"][-1]) > 0), "thermo": bool(np.nan_to_num(ov["K5"][-1]) > 0)}
    out["carry"] = {"rate_avg": float(np.mean(Cy["rate"][s0 + 1:])),
                    "div_avg": float(np.sum(Cy["tot"][s0 + 1:] - PS.daily_ret(px)[s0 + 1:]) / PS._yrs(cal, s0, T))}
    return out


def page_check(res: dict) -> dict:
    """tiltspec 第 8 節：PAGE_RULES 每一條在 JUDGED 市場裡 better、worse 的個數與能不能放上網頁。"""
    out = {}
    for k in S.RULES:
        vs = [res.get(m, {}).get("rules", {}).get(k, {}).get("v") for m in S.JUDGED]
        vs = [v for v in vs if v]
        nb, nw = sum(v == "better" for v in vs), sum(v == "worse" for v in vs)
        out[k] = {"n": len(vs), "better": nb, "worse": nw,
                  "ok": k in S.PAGE_RULES and nb >= S.PAGE_MIN_BETTER and nw <= S.PAGE_MAX_WORSE}
    return out


def research(F: dict | None = None, mks: tuple = S.MARKETS, W: dict | None = None) -> dict:
    """五個市場（scripts/run_tilt.py）。F＝sigcat.frames()（溫度計）。"""
    from . import sigcat as G
    F = F if F is not None else G.frames()
    W = W or {}
    carry = load_carry()
    mk_out = {mk: market(mk, F=F.get(mk), W=W.get(mk), carry=carry) for mk in mks}
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mk": mk_out, "page": page_check(mk_out)}


def save(R: dict, path: Path | None = None) -> None:
    PS.save(R, OUT if path is None else path)


def load(path: Path | None = None) -> dict | None:
    path = OUT if path is None else path
    try:
        R = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if (R.get("ver") or 0) >= S.VER else None
