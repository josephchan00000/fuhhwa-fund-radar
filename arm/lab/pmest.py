"""盤前第 5 段：用台指期 08:45 開盤重估 09:01（規格 arm/lab/pmestspec.py VER 1；docs/lab_premarket_plan.md 第 16 節）。
只讀資料分支（5 秒指數、期貨日行情與夜盤、選擇權日行情算波動率）與 main 存的台指期逐筆，不抓任何東西。
  run(root) → data/lab/pmest_research.json（scripts/run_pmest.py 寫）
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from . import pmestspec as S


def _stats(e: np.ndarray, em: np.ndarray) -> dict:
    a = np.abs(e)
    return {"n": int(len(e)), "med": round(float(np.median(a)), 1), "p80": round(float(np.percentile(a, 80)), 1),
            "med_em": round(float(np.median(a / em)), 3), "p80_em": round(float(np.percentile(a / em, 80)), 3),
            "bias": round(float(np.mean(e)), 1)}


def rows(root: Path, log=print) -> list[dict]:
    from . import heatbubble as BB
    from . import pmval as V
    idx = {d: v for d, v in V.load_idx(root).items() if d >= "2016-01-04"}
    closes = {k: float(v) for k, v in BB.taiex_daily().items() if v}
    iv = V.ivs(root)
    fday, fnight = V.load_futday(root)
    days = sorted(d for d in idx if d in closes)
    out = []
    for prev, d in zip(days[:-1], days[1:]):
        if d < S.FIRST or d not in fnight or prev not in fday or d not in fday or not iv.get(prev):
            continue
        k = V.night_k(fnight, d)
        if k not in fday[prev] or k not in fday[d] or not fday[d][k][0]:
            continue
        v = idx[d]
        if len(v) <= S.OPEN_T:
            continue
        c = closes[prev]
        pc = fday[prev][k][3]
        out.append({"d": d, "o": float(v[S.OPEN_T]), "c": c, "em": c * iv[prev] * math.sqrt(1 / S.TRADING_YEAR),
                    "e1": c + fnight[d][k][3] - pc, "e2": c + fday[d][k][0] - pc})
    log(f"可用的日子 {len(out)} 天（{out[0]['d']}～{out[-1]['d']}）" if out else "沒有可用的日子")
    return out


def e3_rows(rs: list[dict]) -> list[dict]:
    """有存逐筆的日子：E3＝C＋（08:50:00 那一刻台指期價 − 前一天 13:30 價）（同 premkt 的近月契約）。"""
    from . import futdata as F
    from .premkt import _tx1330
    by = {r["d"]: r for r in rs}
    files = sorted(p.name[:10] for p in (Path(__file__).resolve().parents[2] / "data/lab/fut/tx").glob("*.json.gz"))
    out = []
    for prev, d in zip(files[:-1], files[1:]):
        if d not in by:
            continue
        t0 = _tx1330(F, prev)
        ticks = F.load_day(d) or {}
        k = F.near(d, ticks) if ticks else None
        px = next((p for s, p, _, _ in reversed(ticks.get(k) or []) if s <= S.E3_T), None)
        if t0 is None or px is None:
            continue
        r = dict(by[d])
        r["e3"] = r["c"] + float(px) - float(t0)
        out.append(r)
    return out


def run(root: Path, log=print) -> dict:
    rs = rows(Path(root), log)
    o = np.array([r["o"] for r in rs])
    em = np.array([r["em"] for r in rs])
    est = {k: np.array([r[k] if k != "n" else r["c"] for r in rs]) for k in ("e1", "e2", "n")}
    out = {"ver": S.VER, "spec_fp": S.fingerprint(), "first": rs[0]["d"], "last": rs[-1]["d"], "n": len(rs),
           "full": {k: _stats(o - v, em) for k, v in est.items()}}
    ds = [r["d"] for r in rs]
    half = sorted(ds)[len(ds) // 2]
    out["halves"] = {}
    for nm, sel in (("h1", np.array([d < half for d in ds])), ("h2", np.array([d >= half for d in ds]))):
        out["halves"][nm] = {k: round(float(np.median(np.abs(o[sel] - v[sel]))), 1) for k, v in est.items()} | {"n": int(sel.sum())}
    m1, m2 = out["full"]["e1"]["med"], out["full"]["e2"]["med"]
    gain = 1 - m2 / m1 if m1 else 0.0
    ok = {"gain": gain >= S.MIN_GAIN, "h1": out["halves"]["h1"]["e2"] < out["halves"]["h1"]["e1"],
          "h2": out["halves"]["h2"]["e2"] < out["halves"]["h2"]["e1"]}
    out["judge"] = {"gain": round(gain, 4), "ok": ok, "verdict": "過關" if all(ok.values()) else "沒過"}
    # 只列：E1 大錯的日子
    e1a, e2a = np.abs(o - est["e1"]), np.abs(o - est["e2"])
    big = e1a > np.percentile(e1a, 80)
    out["big"] = {"n": int(big.sum()), "e1_med": round(float(np.median(e1a[big])), 1), "e2_med": round(float(np.median(e2a[big])), 1),
                  "halved": round(float((e2a[big] <= e1a[big] / 2).mean()), 4)}
    recent = rs[-10:]
    out["recent"] = [[r["d"], round(r["e1"]), round(r["e2"]), round(r["o"])] for r in recent]
    e3 = e3_rows(rs)
    if e3:
        o3 = np.array([r["o"] for r in e3])
        em3 = np.array([r["em"] for r in e3])
        out["e3"] = {"first": e3[0]["d"], "last": e3[-1]["d"],
                     **{k: _stats(o3 - np.array([r[k] for r in e3]), em3) for k in ("e1", "e2", "e3")}}
    log(f"E1 中位數 {m1}、E2 {m2}（少 {gain:.0%}）→ {out['judge']['verdict']}")
    return out
