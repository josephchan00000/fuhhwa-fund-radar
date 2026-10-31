"""EMA 賣壓（emaspec VER 1；docs/lab_signal_quality_plan.md 第 13 節，C 段第一部分）：法人買賣超與成交金額各做指數平均，
和現在的合計位階、連續買賣超逐年比「列出來之後實際比平常好多少」→ data/lab/ema_research.json（scripts/run_ema.py）。

變數照 sigcat.inst_vars 的寫法（對齊交易日、和過去比成 0～100、賣超＝熱），訊號用 sigcat.inst_signals（同一套 6 種），
逐年紀錄用 sigoos.walk（同「預估之後」）。現在的兩個家族用這裡的程式算的紀錄要和 sigoos.market 一模一樣（check_base）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import emaspec as E
from . import sigspec as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / E.OUT


def ema_ratio(cal: list[str], a: dict, b: dict, w: float) -> dict:
    """{日期: 100 × EMA(a) ÷ EMA(b)}：兩邊都有值的日子才更新（α＝2 ÷ (w＋1)，第一天＝當天的值），更新滿 w 次以後才有值。"""
    al = E.alpha(w)
    ea = eb = None
    n = 0
    out: dict = {}
    for d in cal:
        x, y = a.get(d), b.get(d)
        if x is None or not y:
            continue
        if ea is None:
            ea, eb = float(x), float(y)
        else:
            ea = al * x + (1.0 - al) * ea
            eb = al * y + (1.0 - al) * eb
        n += 1
        if n >= w and eb:
            out[d] = 100.0 * ea / eb
    return out


def ema_vars(cal: list, B: dict, spans: tuple = E.SPANS) -> list[dict]:
    """11 個 EMA 賣壓變數在這個日曆上的 0～100（同 sigcat.inst_vars 的位階；spans＝實際用的天數，代號與看多久照 E.SPANS 對應的那一個）。"""
    from . import crash as CR
    from . import heat as H
    from . import heatcalc as HC
    from . import heatspec as HS
    D = B.get("D") or {}
    if not D.get("inst"):
        return []
    A = HC.inst_amounts(D["inst"])
    to = {d: v[0] for d, v in (D.get("turnover") or {}).items() if v and v[0]}
    out = []
    for who in S.INST_WHO:
        for w0, w in zip(E.SPANS, spans):
            if (who, w0) in E.SKIP:
                continue
            raw = H.asof_daily(B["cal"], ema_ratio(B["cal"], A[who], to, w), stale=7)
            hb = [H.to_heat(p, -1) for p in H.pct_series(raw, HS.PCT_WIN["d"], HS.PCT_MIN["d"])]
            out.append({"key": f"{who}{E.KEY}{w0}", "who": who, "w": w0, "span": w, "H": S.INST_H[w0],
                        "name": f"{S.INST_NAMES[who]} EMA {w0} 日賣壓", "x": CR.align(cal, B["cal"], hb), "amt": None})
    return out


def families(F: dict, B: dict, spans: tuple = E.SPANS) -> dict[str, list[dict]]:
    """台股的三個家族：E＝EMA 位階、S＝現在的合計位階、R＝現在的連續買賣超（sigcat.inst_signals）。"""
    from . import sigcat as G
    cur = G.inst_signals(F)
    ema = G.inst_signals({**F, "ivars": ema_vars(F["cal"], B, spans)})
    return {"E": ema,
            "S": [sd for sd in cur if sd["sig"] in S.INST_VARIANTS],
            "R": [sd for sd in cur if "_run" in sd["sig"]]}


def records(F: dict, sds: list[dict]) -> list[dict]:
    """逐年紀錄（同 sigoos.market 的迴圈：自己的看多久＋溫度計跨期間，偏多與警示）。"""
    from . import sigcat as G
    from . import sigoos as OOS
    mk, cal, px = F["mk"], F["cal"], F["px"]
    cuts = OOS.cuts_for(cal)
    Yc: dict = {}
    out = []
    for sd in sds:
        H = sd["H"]
        for Hx in [H] + (sorted(set(S.THERMO_H.values()) - {H}) if sd["cat"] in S.THERMO_X_CATS else []):
            if Hx not in Yc:
                Yc[Hx] = (G.outcomes(px, Hx, G.warn_th(mk, Hx)), OOS._ra1(px, Hx))
            (Yu, Yw, _), ra = Yc[Hx]
            if Hx == H:
                out += OOS.walk(mk, sd, cuts, Yu, Yw, ra, ("up", "warn"))
            else:
                out += OOS.walk(mk, {**sd, "H": Hx}, cuts, Yu, Yw, ra, ("up", "warn"), x=True)
    return out


def listed(recs: list[dict]) -> list[dict]:
    """那時候的成績過列出門檻的紀錄（次數 ≥ N_MIN 已經是 walk 的條件；命中率 − 平常 ≥ THERMO_EDGE）。"""
    return [r for r in recs if r["n"] >= S.N_MIN and r["e"] >= S.THERMO_EDGE]


def metrics(recs: list[dict]) -> dict:
    """列出來的紀錄：筆數、o 平均、o > 0 的比例；另分偏多／警示、自己的看多久／跨期間。"""
    def m(rs):
        o = np.asarray([r["o"] for r in rs], dtype=float)
        return {"n": int(len(o)), "mean": float(o.mean()) if len(o) else None,
                "pos": float((o > 0).mean()) if len(o) else None, "years": len({r["yr"] for r in rs})}
    L = listed(recs)
    return {"all": m(L), "up": m([r for r in L if r["d"] == "up"]), "warn": m([r for r in L if r["d"] == "warn"]),
            "own": m([r for r in L if not r.get("x")]), "x": m([r for r in L if r.get("x")]), "all_recs": len(recs)}


def diff_ci(a: list[dict], b: list[dict], draws: int = E.DRAWS, seed: int = E.SEED) -> dict:
    """列出來的紀錄 a、b 的 o 平均差（a − b）與以「年」為一塊重抽的 95% 區間（兩邊都有紀錄的年；同一批年）。"""
    A, Bl = listed(a), listed(b)
    ys = sorted({r["yr"] for r in A} & {r["yr"] for r in Bl})
    if len(ys) < 2:
        return {"d": None, "lo": None, "hi": None, "years": len(ys)}

    def by_year(rs):
        out = {y: [0.0, 0] for y in ys}
        for r in rs:
            if r["yr"] in out:
                out[r["yr"]][0] += r["o"]
                out[r["yr"]][1] += 1
        return np.asarray([out[y][0] for y in ys]), np.asarray([out[y][1] for y in ys], dtype=float)
    sa, na = by_year(A)
    sb, nb = by_year(Bl)
    d0 = sa.sum() / na.sum() - sb.sum() / nb.sum()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(ys), size=(draws, len(ys)))
    NA, NB = na[idx].sum(axis=1), nb[idx].sum(axis=1)
    ok = (NA > 0) & (NB > 0)
    d = sa[idx].sum(axis=1)[ok] / NA[ok] - sb[idx].sum(axis=1)[ok] / NB[ok]
    return {"d": float(d0), "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)), "years": len(ys)}


def decide(fam: dict, diffs: dict) -> dict:
    """第 4 點：E 對 S、E 對 R 換不換。"""
    out = {}
    for k in ("S", "R"):
        d = diffs[f"E-{k}"]
        out[k] = E.better(fam["E"]["all"]["mean"], fam[k]["all"]["mean"], d["lo"], fam["E"]["all"]["pos"], fam[k]["all"]["pos"])
    return out


def check_base(F: dict, fams: dict) -> list[str]:
    """S、R 用這裡算的逐年紀錄，要和 sigoos.market 算的同一批訊號一模一樣。→ 不一樣的訊號 id。"""
    from . import sigoos as OOS
    ids = {sd["id"] for k in ("S", "R") for sd in fams[k]}
    ref: dict = {}
    for r in OOS.market(F):
        if r["id"] in ids:
            ref.setdefault(r["id"], []).append(r)
    got: dict = {}
    for r in records(F, fams["S"] + fams["R"]):
        got.setdefault(r["id"], []).append(r)
    return sorted(i for i in ids if ref.get(i, []) != got.get(i, []))


def run(base: dict | None = None, log=print) -> dict:
    from . import sigrobust as RB
    base = base if base is not None else RB.base_data()
    F, B = base["F"]["tw"], base["BT"]
    fams = families(F, B)
    log(f"[ema] 訊號：EMA {len(fams['E'])}、合計 {len(fams['S'])}、連續 {len(fams['R'])}")
    bad = check_base(F, fams)
    if bad:
        raise RuntimeError(f"現在的家族逐年紀錄和 sigoos 不一樣：{bad[:10]}（共 {len(bad)} 個）")
    log("[ema] 現在的兩個家族和「預估之後」的紀錄一模一樣")
    recs = {k: records(F, sds) for k, sds in fams.items()}
    fam = {k: metrics(v) for k, v in recs.items()}
    diffs = {f"E-{k}": diff_ci(recs["E"], recs[k]) for k in ("S", "R")}
    sens = {}
    for f in E.SENS:
        sp = tuple(E.span_nb(w, f) for w in E.SPANS)
        rE = records(F, families(F, B, sp)["E"])
        sens[str(f)] = {"spans": list(sp), "m": metrics(rE), "E-S": diff_ci(rE, recs["S"]), "E-R": diff_ci(rE, recs["R"])}
    log("[ema] 天數 ×0.8、×1.2 ok")
    idwho = {sd["id"]: sd["grp"] for sds in fams.values() for sd in sds}
    who = {w: {k: metrics([r for r in v if idwho.get(r["id"]) == w])["all"] for k, v in recs.items()} for w in S.INST_WHO}
    return {"ver": E.VER, "spec_date": E.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": F["cal"][-1], "n": {k: len(v) for k, v in fams.items()}, "fam": fam, "diff": diffs,
            "better": decide(fam, diffs), "sens": sens, "who": who}


def save(R: dict, path: Path | None = None) -> None:
    (path or OUT).write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load(path: Path | None = None) -> dict | None:
    try:
        R = json.loads((path or OUT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if (R.get("ver") or 0) >= E.VER else None
