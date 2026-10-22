"""實測區的前瞻紀錄（docs/lab_practice_page_plan.md 第 2.3、8 節；規則 practspec VER 1）。

  targets(mk, now, R)   今天每種用法該拿幾成：溫度計規則＝溫度計卡下面「過去讀數這樣的時候」同一份票數與位置（thermocal.now）；
                        總經策略＝當年選到的策略（研究檔；跨年沒有的就當場用截到 1 月 1 日的資料重新判定）與各自今天收盤後的部位
  update(new)           只有 CI（GITHUB_ACTIONS=true）寫回 data/lab/practsim_live.json（同一個資料日覆蓋；內容沒變不動檔）
  forward(log_mk, D)    從開始記的那天起照做的成績（和固定持有、一直持有比）

溫度計規則照規格只在每週最後一個交易日決定、下一個交易日收盤調整（之間沿用）；總經策略每天照各策略的部位。
沒有紀錄的日子沿用前一筆（記在 "gap"）。成本：部位變動 × xstratspec.COST（總經策略各策略的成本不同，這裡一律用 ETF 成本，偏保守）。
"""
from __future__ import annotations

import bisect
import json
import os
from datetime import date
from pathlib import Path

import numpy as np

from . import heatpos as HP
from . import practsim as P
from . import practspec as S
from . import sigspec as SS
from . import xstrat as XT
from . import xstratspec as XS

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "data" / "lab" / "practsim_live.json"
VER = 1
MIN_DAYS = 63                    # 前瞻不到 3 個月（63 個交易日）只寫「累積中」，不下結論


# ── 今天的目標部位 ─────────────────────────────────────────────────────────────

def thermo_targets(C: dict | None) -> dict:
    """C＝thermocal.now(...)：{溫度計: {"up": {"n", "grp"…}, "warn": {…}}} → {規則: 目標部位}；讀數不夠的規則不列。"""
    out: dict = {}
    if not C:
        return out
    if any(k not in C or C[k].get("up", {}).get("grp") is None or C[k].get("warn", {}).get("grp") is None for k in SS.THERMO_H):
        return out
    g = {k: {"u": C[k]["up"]["grp"], "w": C[k]["warn"]["grp"]} for k in SS.THERMO_H}
    n = {k: {"u": C[k]["up"]["n"], "w": C[k]["warn"]["n"]} for k in SS.THERMO_H}
    return {name: P.decide(R, g, n) for name, R in S.THERMO_RULES.items()}


def strat_selection(mk: str, D: dict, R: dict | None, year: int) -> dict:
    """那一年每條總經策略規則選到的策略：研究檔有那一年就用它，沒有就用截到那年 1 月 1 日的資料重新判定（practspec 第 3 節）。"""
    sel = ((R or {}).get("mk", {}).get(mk, {}) or {}).get("x_sel") or {}
    if all(str(year) in (sel.get(k) or {}) for k in S.STRAT_RULES):
        return {k: list(sel[k][str(year)]) for k in S.STRAT_RULES}
    tiers = P.xs_tiers(mk, D, [year])[year]
    return {k: sorted(s for s, t in tiers.items() if t in Rr["tiers"]) for k, Rr in S.STRAT_RULES.items()}


def strat_targets(mk: str, D: dict, R: dict | None) -> tuple[dict, dict, dict]:
    """總經策略規則今天收盤後的部位：{規則: 部位}、{規則: [選到的策略]}、{策略: 今天收盤後拿不拿}。"""
    cal = D["cal"]
    year = int(cal[-1][:4])
    sel = strat_selection(mk, D, R, year)
    C = XT.Ctx(D)
    specs = {s["k"]: s for s in P.xs_specs(mk, D)}
    held = {k: float(XT.held_pos(C, s)[-1]) for k, s in specs.items()}
    tg = {k: (sum(held.get(s, 0.0) for s in ks) / len(ks) if ks else 0.0) for k, ks in sel.items()}
    return tg, sel, held


def week_info(mk: str, d: str) -> tuple[str, str]:
    """d 之後的下一個交易日、d 那一週的最後一個交易日（d 自己就是的話＝d）；休市表同 xstrat.future_days。"""
    wk = date.fromisoformat(d).isocalendar()[:2]
    fd = XT.future_days(mk, d, 6)
    last = d
    for x in fd:
        if date.fromisoformat(x).isocalendar()[:2] != wk:
            break
        last = x
    return fd[0], last


def targets(mk: str, now: dict | None, R: dict | None, D: dict | None = None) -> dict | None:
    """今天這個市場每種用法該拿幾成。now＝sigcat.NOW[市場]（景氣頁建頁時算的現在有效）；沒有就只算總經策略。
    → {"d": 溫度計的資料日, "nx": 下一個交易日, "wend": 這週最後一個交易日, "t": {規則: 目標}, "xd": 總經策略的資料日,
       "sel": {規則: [策略]}, "held": {策略: 部位}, "cal": 溫度計讀數}。"""
    from . import thermocal as TC
    out: dict = {"t": {}}
    if now:
        try:
            C = TC.now(mk, now["on"], now.get("xon"), now["d"])
        except Exception as e:                        # noqa: BLE001
            print(f"[實測] {mk} 溫度計讀數算不出來：{type(e).__name__}: {e}")
            C = None
        out["d"] = now["d"]
        out["nx"], out["wend"] = week_info(mk, now["d"])
        out["t"].update(thermo_targets(C))
        if C:
            out["cal"] = {k: {s: {"n": C[k][s]["n"], "pct": C[k][s].get("pct"), "grp": C[k][s].get("grp")} for s in ("up", "warn")}
                          for k in SS.THERMO_H if k in C}
    try:
        D = D if D is not None else XT.data(mk)
        tg, sel, held = strat_targets(mk, D, R)
        out.update({"xd": D["cal"][-1], "sel": sel, "held": held})
        out["t"].update(tg)
    except Exception as e:                            # noqa: BLE001
        print(f"[實測] {mk} 總經策略的部位算不出來：{type(e).__name__}: {e}")
    return out if out["t"] else None


# ── 紀錄 ──────────────────────────────────────────────────────────────────────

def load(path: Path | None = None) -> dict:
    path = LIVE if path is None else path
    try:
        L = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ver": VER, "mk": {}}
    return L if isinstance(L, dict) and isinstance(L.get("mk"), dict) else {"ver": VER, "mk": {}}


def merge(L: dict, new: dict) -> dict:
    """new＝{市場: targets(...)} → 併進紀錄：溫度計規則記在溫度計的資料日、總經策略記在總經策略的資料日（同一天覆蓋）。"""
    out = {"ver": VER, "mk": {mk: {d: dict(v) for d, v in (x or {}).items()} for mk, x in (L.get("mk") or {}).items()}}
    for mk, x in new.items():
        if not x:
            continue
        m = out["mk"].setdefault(mk, {})
        th = {k: v for k, v in x["t"].items() if k in S.THERMO_RULES}
        st = {k: v for k, v in x["t"].items() if k in S.STRAT_RULES}
        if th and x.get("d"):
            m.setdefault(x["d"], {}).update({k: round(float(v), 4) for k, v in th.items()})
        if st and x.get("xd"):
            m.setdefault(x["xd"], {}).update({k: round(float(v), 4) for k, v in st.items()})
    for mk in out["mk"]:
        out["mk"][mk] = dict(sorted(out["mk"][mk].items()))
    return out


def update(new: dict, path: Path | None = None, force: bool = False) -> dict:
    """只有 CI（或 force）寫回；回傳併好的紀錄（本機建頁也用它顯示，但不寫檔）。"""
    path = LIVE if path is None else path
    L = merge(load(path), new)
    if force or os.environ.get("GITHUB_ACTIONS") == "true":
        text = json.dumps(L, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            old = path.read_text(encoding="utf-8")
        except OSError:
            old = None
        if old != text:
            path.write_text(text, encoding="utf-8")
    return L


# ── 前瞻成績 ─────────────────────────────────────────────────────────────────

def positions(cal: list[str], log_mk: dict, rule: str) -> tuple[np.ndarray | None, int | None, int]:
    """從第一筆紀錄起的部位（第 k 天收盤之後）。
    溫度計規則：第一筆紀錄是那天收盤後才知道的讀數 → 下一個交易日收盤才照做；之後只有週末的紀錄在下一個交易日收盤生效。
    總經策略：紀錄的就是那天收盤後各策略照規則的部位（訊號前一天就知道）→ 從第一筆紀錄那天起每天照紀錄。
    沒有紀錄的日子（或週末）沿用前一筆。→ (部位, 起點, 沿用的次數)；起點之前是 nan。"""
    days = sorted(d for d, v in log_mk.items() if rule in v)
    if not days:
        return None, None, 0
    a = bisect.bisect_left(cal, days[0])
    if a >= len(cal) or cal[a] != days[0]:
        return None, None, 0
    T = len(cal)
    thermo = rule in S.THERMO_RULES
    s = a + 1 if thermo else a
    if s >= T:
        return None, None, 0
    p = np.full(T, np.nan)
    p[s] = log_mk[days[0]][rule]
    gap = 0
    we = set(HP.week_ends(cal)) if thermo else set()
    for k in range(s + 1, T):
        if thermo:
            prev = cal[k - 1]
            if (k - 1) in we:
                if prev in log_mk and rule in log_mk[prev]:
                    p[k] = log_mk[prev][rule]
                    continue
                gap += 1
            p[k] = p[k - 1]
        else:
            d = cal[k]
            if d in log_mk and rule in log_mk[d]:
                p[k] = log_mk[d][rule]
            else:
                p[k] = p[k - 1]
                gap += 1
    return p, s, gap


def forward(log_mk: dict, D: dict) -> dict:
    """每種用法從開始記的那天起：天數、照做／固定持有／一直持有的報酬與最大回撤、平均部位、沿用的天數、夠不夠下結論。"""
    cal = list(D["cal"])
    px = np.asarray(D["px"], dtype=float)
    r = P.daily_ret(px)
    mk = D["mk"]
    out = {}
    for rule in S.RULES:
        p, a, gap = positions(cal, log_mk, rule)
        if p is None:
            continue
        T = len(cal)
        n = T - 1 - a
        x = {"a": cal[a], "z": cal[-1], "n": n, "gap": gap, "now": float(p[-1]), "ok": n >= MIN_DAYS}
        if n >= 1:
            pp = np.nan_to_num(p, nan=0.0)
            cmp = P.compare(cal, r, pp, P.turn_cost(pp, XS.COST[mk]), a, T) if n >= 2 else None
            dr = P.day_ret(r, pp, P.turn_cost(pp, XS.COST[mk]), a, T)
            wbar = float(np.mean(pp[a:T - 1]))
            x.update({"ret": float(np.prod(1.0 + dr) - 1.0), "fix": float(np.prod(1.0 + wbar * r[a + 1:T]) - 1.0),
                      "bh": float(px[-1] / px[a] - 1.0), "w": wbar})
            if cmp:
                x.update({"mdd": cmp["rule"]["mdd"], "fmdd": cmp["fix"]["mdd"], "bmdd": cmp["bh"]["mdd"]})
        out[rule] = x
    return out
