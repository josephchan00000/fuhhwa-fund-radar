"""P5 檢驗（SPEC §7）：DSR（Bailey & López de Prado 2014）、參數鄰近（plateau）、隨機選股百分位。"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import NormalDist, median, pvariance

EULER = 0.5772156649015329
ND = NormalDist()


def sr_per_obs(sharpe_ann: float, n_obs: int, years: float) -> float:
    """年化 Sharpe → 每期（日）Sharpe（引擎用每年觀測數 ppy＝n_obs ÷ 年數 年化）。"""
    ppy = n_obs / years if years > 0 else 252.0
    return sharpe_ann / math.sqrt(ppy)


def dsr(sr: float, T: int, skew: float, kurt: float, trials: list[float]) -> dict:
    """sr＝待檢驗的每期 Sharpe；trials＝全部試驗的每期 Sharpe（含它自己）；kurt 為一般峰態（常態＝3）。
    SR0＝在 N 個試驗、試驗間 Sharpe 變異 V 之下，純運氣最好的那一個的期望值；DSR＝P(真實 Sharpe > SR0)。"""
    N = len(trials)
    if N < 2 or T < 3:
        return {"dsr": None, "sr0": None, "n": N, "var": None}
    v = pvariance(trials)
    sr0 = math.sqrt(v) * ((1 - EULER) * ND.inv_cdf(1 - 1 / N) + EULER * ND.inv_cdf(1 - 1 / (N * math.e)))
    den = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if den <= 0:
        return {"dsr": None, "sr0": sr0, "n": N, "var": v}
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(den)
    return {"dsr": ND.cdf(z), "sr0": sr0, "n": N, "var": v, "z": z}


def trial_srs(path: str | Path, suffix: str = "_VAL") -> list[float]:
    """trials.csv 裡名稱以 suffix 結尾、有 Sharpe 的試驗 → 每期 Sharpe。"""
    out = []
    p = Path(path)
    if not p.exists():
        return out
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r["name"].endswith(suffix) or not r.get("sharpe") or not r.get("n_obs"):
                continue
            from datetime import date
            yrs = (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days / 365.25
            out.append(sr_per_obs(float(r["sharpe"]), int(r["n_obs"]), yrs))
    return out


def plateau(center: float | None, neighbors: list[float | None], ratio_max: float = 1.3) -> dict:
    """SPEC：中心（選中的參數）Sharpe 不可高於周圍格中位數 × 1.3；周圍中位數 ≤ 0 而中心 > 0 也算不過（孤峰）。"""
    xs = [x for x in neighbors if x is not None and x == x]
    if center is None or not xs:
        return {"ok": False, "median": None, "ratio": None}
    md = median(xs)
    if md <= 0:
        return {"ok": center <= 0, "median": md, "ratio": None}
    return {"ok": center <= ratio_max * md, "median": md, "ratio": center / md}


def pct_rank(x: float, dist: list[float]) -> float | None:
    xs = [v for v in dist if v is not None and v == v]
    if not xs or x is None:
        return None
    return sum(1 for v in xs if v < x) / len(xs)
