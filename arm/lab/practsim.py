"""實戰模擬（規格 arm/lab/practspec.py；docs/lab_practical_plan.md 第 11 節）。

照網頁的用法操作，每年 1 月 1 日只用當時拿得到的資料判定，看之後的成績，和一直持有、平均部位一樣的固定持有比：
  溫度計規則（A1～A4、B1、D1）  thermocal.weekly 的逐年週末票數 → 每週的目標部位
  總經策略（M1、M2）            每年 1 月 1 日把之後的資料拿掉、照 xstratspec 重新判定 → 那一年照 ★（＋●）的策略做
研究：TZ=Asia/Taipei python3 scripts/run_practsim.py → data/lab/practsim_research.json（資料或規格改了才重跑）。
tests/test_practsim.py 和逐筆直接算的版本比對。
"""
from __future__ import annotations

import bisect
import json
import math
import zlib
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from . import heatpos as HP
from . import practspec as S
from . import sigspec as SS
from . import thermocal as TC
from . import xstrat as XT
from . import xstratspec as XS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "practsim_research.json"


# ── 報酬與淨值 ───────────────────────────────────────────────────────────────

def daily_ret(px) -> np.ndarray:
    """r[k]＝第 k−1 天收盤到第 k 天收盤的漲跌（第 0 天、缺值＝0）。"""
    p = np.asarray(px, dtype=float)
    r = np.zeros(len(p))
    ok = np.isfinite(p[1:]) & np.isfinite(p[:-1]) & (p[:-1] > 0)
    r[1:][ok] = p[1:][ok] / p[:-1][ok] - 1.0
    return r


def day_ret(r: np.ndarray, p: np.ndarray, cost: np.ndarray, a: int, b: int) -> np.ndarray:
    """第 a＋1～b−1 天每天的報酬：（1 ＋ 前一天收盤後的部位 × 當天漲跌）×（1 − 當天收盤調整的成本）− 1。"""
    return (1.0 + p[a:b - 1] * r[a + 1:b]) * (1.0 - cost[a + 1:b]) - 1.0


def turn_cost(p: np.ndarray, c: float) -> np.ndarray:
    """溫度計規則：第 d 天收盤部位變動 |Δ| × 成本（每一邊）。"""
    out = np.zeros(len(p))
    out[1:] = np.abs(np.diff(p)) * c
    return out


def _yrs(cal: list[str], a: int, b: int) -> float:
    return max(1e-9, (date.fromisoformat(cal[b - 1]) - date.fromisoformat(cal[a])).days / 365.25)


def stats(cal: list[str], dr: np.ndarray, a: int, b: int, w: np.ndarray | None = None) -> dict:
    """第 a 天收盤（淨值 1）到第 b−1 天收盤：年化、最大回撤、夏普、年化 ÷ 最大回撤、平均部位、一年調整幾次、
    完整日曆年的報酬、最差一年。dr＝第 a＋1～b−1 天的報酬；w＝第 a～b−2 天收盤之後的部位（沒給＝不算部位）。"""
    nav = np.concatenate([[1.0], np.cumprod(1.0 + dr)])
    yrs = _yrs(cal, a, b)
    cagr = float(nav[-1] ** (1.0 / yrs) - 1.0)
    mdd = float((1.0 - nav / np.maximum.accumulate(nav)).max())
    sd = float(np.std(dr, ddof=1)) if len(dr) > 1 else 0.0
    out = {"cagr": cagr, "mdd": mdd, "sharpe": float(np.mean(dr) / sd * math.sqrt(252.0)) if sd > 0 else None,
           "mar": cagr / mdd if mdd > 0 else None, "yrs": yrs, "a": cal[a], "z": cal[b - 1]}
    if w is not None and len(w):
        out["w"] = float(np.mean(w))
        out["adj"] = float(np.count_nonzero(np.abs(np.diff(w)) > 1e-12) / yrs)
    ends: dict = {}
    for i in range(a, b):
        ends[cal[i][:4]] = i - a                       # 那一年最後一天收盤在 nav 裡的位置
    ys = sorted(ends)
    yearly = []
    last_y = cal[b - 1][:4]
    last_full = b < len(cal) and cal[b][:4] != last_y  # 期間最後一天剛好是那一年最後一個交易日
    for y0, y1 in zip(ys, ys[1:]):
        if y1 == last_y and not last_full:
            break                                      # 期間最後一年沒有完整（今年還沒過完，或半段切在年中）
        yearly.append([y1, float(nav[ends[y1]] / nav[ends[y0]] - 1.0)])
    out["yearly"] = yearly
    out["worst"] = min((v for _, v in yearly), default=None)
    return out


def compare(cal: list[str], r: np.ndarray, p: np.ndarray, cost: np.ndarray, a: int, b: int) -> dict:
    """同一段期間的規則、固定持有（每天拿規則的平均部位、不扣成本）、一直持有。"""
    dr = day_ret(r, p, cost, a, b)
    w = p[a:b - 1]
    wbar = float(np.mean(w)) if len(w) else 0.0
    return {"rule": stats(cal, dr, a, b, w), "fix": stats(cal, wbar * r[a + 1:b], a, b),
            "bh": stats(cal, r[a + 1:b], a, b), "wbar": wbar}


def verdict(full: dict, h1: dict, h2: dict) -> str:
    """practspec 第 5 節：better＝全期間夏普較高、最大回撤不比固定持有大、前後兩半夏普都較高；worse＝全期間與前後兩半夏普都較低。"""
    def gt(x: dict) -> bool | None:
        a, b = x["rule"]["sharpe"], x["fix"]["sharpe"]
        return None if a is None or b is None else a > b

    def lt(x: dict) -> bool | None:
        a, b = x["rule"]["sharpe"], x["fix"]["sharpe"]
        return None if a is None or b is None else a < b
    if gt(full) and gt(h1) and gt(h2) and full["rule"]["mdd"] <= full["fix"]["mdd"] + 1e-12:
        return "better"
    if lt(full) and lt(h1) and lt(h2):
        return "worse"
    return "same"


def _sh(x: np.ndarray) -> np.ndarray:
    sd = x.std(axis=-1, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(sd > 0, x.mean(axis=-1) / sd * math.sqrt(252.0), np.nan)


def boot_ci(a: np.ndarray, b: np.ndarray, key: str) -> list[float] | None:
    """規則減一直持有的夏普差：BOOT_BLOCK 天一塊的循環區塊重抽 BOOT_DRAWS 次的 95% 區間（只呈現）。
    種子＝(BOOT_SEED, CRC32(規則:市場))，和計算順序無關。"""
    n, L = len(a), S.BOOT_BLOCK
    if n < 2 * L:
        return None
    rng = np.random.default_rng([S.BOOT_SEED, zlib.crc32(key.encode("utf-8"))])
    vals = np.empty(S.BOOT_DRAWS)
    for j in range(S.BOOT_DRAWS):
        st = rng.integers(0, n, size=n // L + 1)
        idx = (st[:, None] + np.arange(L)[None, :]).ravel()[:n] % n
        vals[j] = _sh(a[idx]) - _sh(b[idx])
    vals = vals[np.isfinite(vals)]
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if len(vals) else None


def bears(cal: list[str], px: np.ndarray, r: np.ndarray, p: np.ndarray, cost: np.ndarray, a: int, wbar: float) -> list[dict]:
    """每一段大跌（指數收盤跌 BEAR 以上，hotdd.declines 的多空門檻法則；評估期間內）：高點到低點規則、固定持有、指數的變化。"""
    from . import hotdd as HDD
    out = []
    T = len(cal)
    for e in HDD.declines(cal[a:], px[a:], S.BEAR):
        pk, tr = a + e["pk"], a + e["tr"]
        if tr <= pk:
            continue
        rule = float(np.prod(1.0 + day_ret(r, p, cost, pk, tr + 1)) - 1.0)
        fix = float(np.prod(1.0 + wbar * r[pk + 1:tr + 1]) - 1.0)
        out.append({"pk": cal[pk], "tr": cal[tr], "bh": float(px[tr] / px[pk] - 1.0), "rule": rule, "fix": fix,
                    "open": bool(e["open"]) or tr == T - 1})
    return out


def evaluate(key: str, cal: list[str], px: np.ndarray, p: np.ndarray, cost: np.ndarray, s0: int) -> dict:
    """一條規則在一個市場：全期間、前後兩半、近 10 年、判定、夏普差的區間、每一段大跌、現在的部位。"""
    T = len(cal)
    r = daily_ret(px)
    m = s0 + (T - s0) // 2
    full = compare(cal, r, p, cost, s0, T)
    h1, h2 = compare(cal, r, p, cost, s0, m), compare(cal, r, p, cost, m, T)
    d = date.fromisoformat(cal[-1])
    try:
        r10 = d.replace(year=d.year - S.RECENT_YEARS).isoformat()
    except ValueError:
        r10 = d.replace(year=d.year - S.RECENT_YEARS, day=28).isoformat()
    a10 = max(s0, bisect.bisect_left(cal, r10))
    rec = compare(cal, r, p, cost, a10, T)
    ci = boot_ci(day_ret(r, p, cost, s0, T), r[s0 + 1:T], key)
    return {"full": full, "h1": h1, "h2": h2, "rec": rec, "v": verdict(full, h1, h2), "ci": ci,
            "bears": bears(cal, px, r, p, cost, s0, full["wbar"]), "now": float(p[T - 1])}


def series(px: np.ndarray, p: np.ndarray, cost: np.ndarray, a: int, wbar: float, idx: list[int]) -> dict:
    """畫圖用（只呈現）：idx 那幾天收盤的淨值（規則、固定持有；第 a 天＝1）與部位。"""
    r = daily_ret(px)
    T = len(px)
    nav = np.concatenate([[1.0], np.cumprod(1.0 + day_ret(r, p, cost, a, T))])
    fix = np.concatenate([[1.0], np.cumprod(1.0 + wbar * r[a + 1:T])])
    j = np.asarray(idx, dtype=np.int64) - a
    return {"nav": [round(float(x), 4) for x in nav[j]], "fix": [round(float(x), 4) for x in fix[j]],
            "pos": [round(float(p[i]), 3) for i in idx]}


def group_series(cal: list[str], px: np.ndarray, a: int, idx: list[int]) -> dict:
    """同一個起點的規則共用：取樣的日子與一直持有的淨值。"""
    return {"d": [cal[i] for i in idx], "bh": [round(float(px[i] / px[a]), 4) for i in idx]}


# ── 溫度計規則 ───────────────────────────────────────────────────────────────

def decide(R: dict, g: dict, n: dict) -> float:
    """一條溫度計規則這一週的目標部位：g＝各溫度計兩邊的分組（lo／mid／hi）、n＝票數。"""
    if R.get("any"):
        on = n[R["hz"][0]][R["side"]] >= 1
    else:
        on = sum(g[k][R["side"]] == "hi" for k in R["hz"]) >= R["need"]
    return R["on"] if on else R["off"]


def thermo_positions(T: int, W: dict) -> tuple[dict, int | None, list[dict]]:
    """thermocal.weekly 的週末票數 → 每條溫度計規則的部位（第 k 天收盤之後）、評估起點、每週的讀數。
    週末 t 收盤決定，第 t＋LAG 天收盤調整、維持到下一次調整；排不出位置的週不決定（評估從第一個排得出位置的週末的下一個交易日開始）。"""
    H = W["hist"]
    t = np.asarray(H["short"]["t"], dtype=np.int64)
    rk = {(k, c): TC.rank(H[k][c]) for k in SS.THERMO_H for c in ("u", "w")}
    first = next((j for j in range(len(t)) if all(rk[(k, c)][j] is not None for k in SS.THERMO_H for c in ("u", "w"))), None)
    pos = {k: np.full(T, np.nan) for k in S.THERMO_RULES}
    weeks = []
    if first is None:
        return pos, None, weeks
    for j in range(first, len(t)):
        tj = int(t[j])
        a = tj + S.LAG
        z = int(t[j + 1]) + S.LAG if j + 1 < len(t) else T
        g = {k: {c: TC.group(rk[(k, c)][j][1]) for c in ("u", "w")} for k in SS.THERMO_H}
        weeks.append({"t": tj, "n": {k: {c: int(H[k][c][j]) for c in ("u", "w")} for k in SS.THERMO_H},
                      "pct": {k: {c: round(rk[(k, c)][j][0], 4) for c in ("u", "w")} for k in SS.THERMO_H}, "g": g})
        for name, R in S.THERMO_RULES.items():
            if a < T:
                pos[name][a:min(z, T)] = decide(R, g, weeks[-1]["n"])
    s0 = int(t[first]) + S.LAG
    for k in pos:
        if s0 < T:
            pos[k][:s0] = np.nan
    return pos, (s0 if s0 < T else None), weeks


def thermo_market(F: dict, W: dict | None = None) -> dict:
    """一個市場的溫度計規則（A1～A4、B1、D1）。"""
    mk, cal = F["mk"], list(F["cal"])
    px = np.asarray(F["px"], dtype=float)
    T = len(cal)
    W = W if W is not None else TC.weekly(F)
    pos, s0, weeks = thermo_positions(T, W)
    out = {"a": cal[s0] if s0 is not None else None, "rules": {}}
    if s0 is None or T - s0 < 2 * S.BOOT_BLOCK:
        return out
    c = XS.COST[mk]
    wk = [w for w in weeks if w["t"] >= s0]                # 評估從 s0 收盤開始（第一個決定的週末＝s0 − LAG，不畫）
    idx = [w["t"] for w in wk]
    ser = {**group_series(cal, px, s0, idx), "r": {},
           "rd": {k: {cc: [w["pct"][k][cc] for w in wk] for cc in ("u", "w")} for k in SS.THERMO_H}}
    for k, p in pos.items():
        pp = np.nan_to_num(p, nan=1.0)
        out["rules"][k] = evaluate(f"{k}:{mk}", cal, px, pp, turn_cost(pp, c), s0)
        ser["r"][k] = series(px, pp, turn_cost(pp, c), s0, out["rules"][k]["full"]["wbar"], idx)
    out["series"] = ser
    last = weeks[-1]
    out["last"] = {"d": cal[last["t"]], "n": last["n"], "pct": last["pct"], "g": last["g"],
                   "pending": last["t"] + S.LAG >= T,
                   "target": {k: decide(R, last["g"], last["n"]) for k, R in S.THERMO_RULES.items()}}
    out["share_hi"] = {k: {c: float(np.mean([w["g"][k][c] == "hi" for w in weeks])) for c in ("u", "w")} for k in SS.THERMO_H}
    return out


# ── 總經策略 ─────────────────────────────────────────────────────────────────

def truncate(D: dict, cut: int) -> dict:
    """把第 cut 天以後的資料全部拿掉（所有跟日曆一樣長的序列一起截）。"""
    T = len(D["cal"])
    out = {}
    for k, v in D.items():
        if k == "cal":
            out[k] = list(v)[:cut]
        elif isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == T:
            out[k] = v[:cut]
        else:
            out[k] = v
    return out


def xs_first_year(mk: str) -> int:
    """EVAL_START 滿 XS_WARM_Y 年的下一個 1 月 1 日（剛好是 1 月 1 日就是那一年）。"""
    d = XS.EVAL_START[mk]
    y = int(d[:4]) + S.XS_WARM_Y
    return y if d[5:] == "01-01" else y + 1


def xs_specs(mk: str, D: dict) -> list[dict]:
    return [s for s in XS.STRATS if mk in s["mk"] and XT.has_data(D, s["k"])]


def xs_tiers(mk: str, D: dict, years: list[int]) -> dict:
    """每一個判定年：把那年 1 月 1 日以後的資料拿掉、照 xstratspec 重新判定 → {年: {策略: tier}}（資料那時還沒有的不列）。"""
    cal = D["cal"]
    out = {}
    for y in years:
        cut = bisect.bisect_left(cal, f"{y}-01-01")
        Dt = truncate(D, cut)
        C = XT.Ctx(Dt)
        out[y] = {s["k"]: XT.judge(C, s) for s in xs_specs(mk, Dt)}
    return out


def xs_positions(D: dict, sel: dict, a: int) -> tuple[np.ndarray, np.ndarray, dict]:
    """sel＝{年: [策略…]} → 整個組合的部位（第 k 天收盤之後）與每天收盤調整的成本（各策略各算、不抵銷）。
    每一份＝1 ÷ 那一年的條數；第 k 天屬於哪一年看第 k 天的日期（1 月第一個交易日收盤換年）。"""
    mk, cal = D["mk"], D["cal"]
    T = len(cal)
    C = XT.Ctx(D)
    specs = {s["k"]: s for s in xs_specs(mk, D)}
    hp = {k: XT.held_pos(C, s) for k, s in specs.items()}
    cs = {k: XS.cost(mk, k) for k in specs}
    yr = np.array([int(d[:4]) for d in cal])
    wt = {k: np.zeros(T) for k in specs}
    for y, ks in sel.items():
        m = yr == y
        for k in ks:
            if k in wt:
                wt[k][m] = 1.0 / len(ks)
    eff = {k: wt[k] * hp[k] for k in specs}
    expo = np.zeros(T)
    cost = np.zeros(T)
    for k in specs:
        expo += eff[k]
        cost[1:] += np.abs(np.diff(eff[k])) * cs[k]
    cost[:a + 1] = 0.0
    return expo, cost, {k: float(hp[k][a:].mean()) for k in specs}


def xs_market(mk: str, D: dict | None = None) -> dict:
    """一個市場的總經策略規則（M1、M2）。"""
    D = D if D is not None else XT.data(mk)
    cal = D["cal"]
    px = np.asarray(D["px"], dtype=float)
    T = len(cal)
    y0, y1 = xs_first_year(mk), int(cal[-1][:4])
    years = list(range(y0, y1 + 1))
    a = bisect.bisect_left(cal, f"{y0}-01-01")
    tiers = xs_tiers(mk, D, years)
    out = {"a": cal[a] if a < T else None, "tiers": {str(y): t for y, t in tiers.items()}, "rules": {}, "sel": {}}
    if a >= T - 2 * S.BOOT_BLOCK:
        return out
    idx = [i for i in HP.week_ends(cal) if i >= a]
    ser = {**group_series(cal, px, a, idx), "r": {}}
    for name, R in S.STRAT_RULES.items():
        sel = {y: sorted(k for k, t in tiers[y].items() if t in R["tiers"]) for y in years}
        expo, cost, _ = xs_positions(D, sel, a)
        res = evaluate(f"{name}:{mk}", cal, px, expo, cost, a)
        res["empty"] = [y for y in years if not sel[y]]
        out["rules"][name] = res
        out["sel"][name] = {str(y): v for y, v in sel.items()}
        ser["r"][name] = series(px, expo, cost, a, res["full"]["wbar"], idx)
    out["series"] = ser
    C = XT.Ctx(D)
    out["held"] = {"d": cal[-1], "p": {s["k"]: float(XT.held_pos(C, s)[-1]) for s in xs_specs(mk, D)}}
    return out


# ── 研究 ─────────────────────────────────────────────────────────────────────

def page_check(res: dict) -> dict:
    """practspec 第 9 節：PAGE_RULES 每一條在它有算的市場裡 better、worse 的個數與能不能放上網頁。"""
    out = {}
    for k in S.PAGE_RULES:
        vs = [m.get("rules", {}).get(k, {}).get("v") for m in res.values()]
        vs = [v for v in vs if v]
        nb, nw = sum(v == "better" for v in vs), sum(v == "worse" for v in vs)
        out[k] = {"n": len(vs), "better": nb, "worse": nw, "ok": nb >= S.PAGE_MIN_BETTER and nw <= S.PAGE_MAX_WORSE}
    return out


def research(F: dict | None = None, mks: tuple = S.MARKETS, W: dict | None = None) -> dict:
    """五個市場（scripts/run_practsim.py）。F＝sigcat.frames()（溫度計規則）；總經策略用 xstrat.data。"""
    from . import sigcat as G
    F = F if F is not None else G.frames()
    W = W or {}
    mk_out = {}
    for mk in mks:
        res = {}
        if mk in F:
            res.update({f"t_{k}": v for k, v in thermo_market(F[mk], W.get(mk)).items()})
        x = xs_market(mk)
        res.update({f"x_{k}": v for k, v in x.items()})
        res["rules"] = {**res.pop("t_rules", {}), **res.pop("x_rules", {})}
        mk_out[mk] = res
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mk": mk_out, "page": page_check(mk_out)}


def _r(v):
    if isinstance(v, float):
        return None if not math.isfinite(v) else round(v, 6)
    if isinstance(v, dict):
        return {str(k): _r(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_r(x) for x in v]
    return v


def save(R: dict, path: Path | None = None) -> None:
    path = OUT if path is None else path
    path.write_text(json.dumps(_r(R), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load(path: Path | None = None) -> dict | None:
    path = OUT if path is None else path
    try:
        R = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if (R.get("ver") or 0) >= S.VER else None
