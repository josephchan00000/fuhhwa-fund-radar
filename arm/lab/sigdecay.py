"""天數衰減（decayspec VER 1；docs/lab_signal_quality_plan.md 第 13.3 節，C 段第二部分）：訊號自己的成績 × 0.5^(第幾天 ÷ 半衰期)，
半衰期同一類訊號一起估；和 sigspec VER 26 的格子逐年比列出來之後準不準 → data/lab/decay_research.json（scripts/run_decay.py）。

迴圈照 thermocal._weekly（同一批訊號、同一個現在有效、同一套 stats_before／vote、同一個第幾天與條件 sigage.days／cond），
VER 25 的每週票數要和 thermocal 一模一樣（check）；VER 26 的每週票數直接用 thermocal._weekly 的。
"""
from __future__ import annotations

import bisect
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import decayspec as D
from . import sigspec as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / D.OUT


def fit_h(num: np.ndarray, den: np.ndarray) -> int | None:
    """R(k)＝num ÷ den → H_GRID 裡使 Σ den ×（R − 0.5^(k ÷ h)）² 最小的 h（同分取大的）；den 全是 0 回 None。"""
    m = den > 0
    if not m.any():
        return None
    k = np.nonzero(m)[0].astype(float)
    R, w = num[m] / den[m], den[m]
    best, bh = None, None
    for h in D.H_GRID:
        err = float((w * (R - D.decay(k, h)) ** 2).sum())
        if best is None or err <= best + 1e-12 * max(1.0, abs(best)):
            best, bh = err, h
    return bh


def _train(Dd: dict, Yu: np.ndarray, Yw: np.ndarray) -> dict:
    """訓練用的日子（同 sigage.Prefix：樣本日、窗口完整、算得到哪一次），依日期排好：日子、第幾天（截在 K_CAP）、條件、結果。"""
    t = Dd["t"]
    sel = Dd["s"] & np.isfinite(Yu[t]) & np.isfinite(Yw[t]) & (Dd["cl"] >= 0)
    t = t[sel]
    return {"t": t, "k": np.minimum(Dd["k"][sel], D.K_CAP), "c": Dd["cid"][sel] % 3, "u": Yu[t], "w": Yw[t]}


def _sum(hh: dict, wk: np.ndarray, oo: dict) -> None:
    hh["t"] += [int(t) for t in wk]
    for c in ("u", "w"):
        tot = np.zeros(len(wk), dtype=int)
        for arr in oo[c].values():
            tot += arr
        hh[c] += [int(x) for x in tot]


def weekly(F: dict) -> dict:
    """一個市場：逐年滾動的週末票數——VER 25（核對用）與衰減版；每一年每支溫度計估出來的半衰期。"""
    from . import sigage as A
    from . import sigcat as G
    from . import thermocal as TC
    mk, cal, px = F["mk"], F["cal"], F["px"]
    T = len(cal)
    we = np.asarray(F["we"], dtype=np.int64)
    sds = [sd for sd in G.signals(F) if sd["cat"] in S.THERMO_X_CATS]
    items = [TC.item_of(sd) for sd in sds]
    Y = {k: G.outcomes(px, H, G.warn_th(mk, H)) for k, H in S.THERMO_H.items()}
    acts = {k: [TC.active(sd, T, H) for sd in sds] for k, H in S.THERMO_H.items()}
    cache: dict = {}
    cxs = [A.cond(F, sd, cache) for sd in sds]
    kday: dict = {}
    cday: dict = {}
    tr: dict = {}
    for k, H in S.THERMO_H.items():
        kday[k], cday[k], tr[k] = [], [], []
        for sd, cx in zip(sds, cxs):
            Dd = A.days(sd, T, H, cx)
            kk = np.full(T, -1, dtype=np.int64)
            kk[Dd["t"]] = np.minimum(Dd["k"], D.K_CAP)
            cc = np.full(T, -1, dtype=np.int64)
            cc[Dd["t"]] = Dd["cid"] % 3
            kday[k].append(kk)
            cday[k].append(cc)
            tr[k].append(_train(Dd, Y[k][0], Y[k][1]))
    y0, y1 = TC.first_year(cal), int(cal[-1][:4])
    hist = {k: {"t": [], "u": [], "w": []} for k in S.THERMO_H}
    histD = {k: {"t": [], "u": [], "w": []} for k in S.THERMO_H}
    fits: list = []
    nogate = {k: [0, 0] for k in S.THERMO_H}                  # [這一邊沒有半衰期、照 VER 25 列的項目週數, 全部項目週數]
    zero = lambda: np.zeros(D.K_CAP + 1)                      # noqa: E731
    for yr in range(y0, y1 + 1):
        cut = bisect.bisect_left(cal, f"{yr}-01-01")
        wk = we[(we >= cut) & (we < bisect.bisect_left(cal, f"{yr + 1}-01-01"))]
        if not len(wk) and yr != y1:
            continue
        for k, H in S.THERMO_H.items():
            lim = cut - S.LAG - H
            V = []
            for sd in sds:
                R = TC.stats_before(sd, cut, Y[k], H)
                v = TC.vote(R)
                V.append((v, {c: R["up" if c == "u" else "warn"] for c in v} if v else {}))
            num: dict = defaultdict(zero)
            den: dict = defaultdict(zero)
            sig: dict = defaultdict(set)
            for i, sd in enumerate(sds):
                v, st = V[i]
                if not v:
                    continue
                Z = tr[k][i]
                p = int(np.searchsorted(Z["t"], lim, side="left"))
                if not p:
                    continue
                kk, cc = Z["k"][:p], Z["c"][:p]
                for c in v:
                    e, b = st[c]["hit"] - st[c]["base"], st[c]["base"]
                    y = (Z["u"] if c == "u" else Z["w"])[:p]
                    for cond in range(3):
                        m = cc == cond
                        if not m.any():
                            continue
                        nn = np.bincount(kk[m], weights=y[m] - b, minlength=D.K_CAP + 1)
                        dd = np.bincount(kk[m], minlength=D.K_CAP + 1) * e
                        for g in ((sd["cat"], cond, c), (D.ALL, cond, c)):
                            num[g] += nn
                            den[g] += dd
                            sig[g].add(i)
            hmap = {g: fit_h(num[g], den[g]) for g in num
                    if len(sig[g]) >= D.FIT_MIN_SIG and float(den[g].sum()) >= D.FIT_MIN_W}
            fits += [[yr, k, g[0], D.CONDS[g[1]], g[2], h, len(sig[g])] for g, h in sorted(hmap.items(), key=str)]
            on = {"u": {}, "w": {}}
            onD = {"u": {}, "w": {}}
            for i, sd in enumerate(sds):
                v, st = V[i]
                if not v:
                    continue
                a = acts[k][i][wk]
                kk, cc = kday[k][i][wk], cday[k][i][wk]
                for c in v:
                    on[c][items[i]] = on[c].get(items[i], np.zeros(len(wk), dtype=bool)) | a
                    e = st[c]["hit"] - st[c]["base"]
                    hs = np.asarray([hmap.get((sd["cat"], int(x), c)) or hmap.get((D.ALL, int(x), c)) or 0 if x >= 0 else 0
                                     for x in cc], dtype=float)
                    gate = hs > 0
                    pred = np.where(gate, e * 0.5 ** (np.maximum(kk, 0) / np.where(gate, hs, 1.0)), e)   # 同 decayspec.decay，逐週的半衰期
                    keep = a & (kk >= 0) & (pred >= S.THERMO_EDGE)
                    nogate[k][0] += int((a & ~gate).sum())
                    nogate[k][1] += int(a.sum())
                    onD[c][items[i]] = onD[c].get(items[i], np.zeros(len(wk), dtype=bool)) | keep
            _sum(hist[k], wk, on)
            _sum(histD[k], wk, onD)
    return {"y0": y0, "y1": y1, "Y": Y, "hist": hist, "histD": histD, "fits": fits, "nogate": nogate}


def year_sums(cal: list, Y: dict, h: dict) -> dict:
    """每支溫度計、每一邊：每年的 Σ 項目數 × 結果、Σ 項目數（週末之後窗口完整的）→ {溫度計: {邊: {年: [Σ, 項目週數]}}}。"""
    out: dict = {}
    for k in S.THERMO_H:
        Yu, Yw, _ = Y[k]
        t = np.asarray(h[k]["t"], dtype=np.int64)
        res = {}
        for side, c, Yx in (("up", "u", Yu), ("warn", "w", Yw)):
            y = Yx[t] if len(t) else np.zeros(0)
            n = np.asarray(h[k][c], dtype=float)
            yrs: dict = {}
            for tt, yy, nn in zip(t.tolist(), y.tolist(), n.tolist()):
                if not np.isfinite(yy):
                    continue
                s = yrs.setdefault(int(cal[tt][:4]), [0.0, 0.0])
                s[0] += nn * yy
                s[1] += nn
            res[side] = yrs
        out[k] = res
    return out


def rate(ys: dict) -> list:
    s, n = sum(v[0] for v in ys.values()), sum(v[1] for v in ys.values())
    return [s / n if n else None, int(n)]


def market(F: dict) -> dict:
    """一個市場：三套規則的比較（同 thermocal.compare 的比例）、每年的加總（重抽用）、半衰期。VER 25 和 thermocal 不一樣就停。"""
    from . import thermocal as TC
    W26 = TC._weekly(F, age=True)
    W = weekly(F)
    for k in S.THERMO_H:
        if W["hist"][k] != W26["hist"][k]:
            raise RuntimeError(f"{F['mk']} {k}：VER 25 的每週票數和 thermocal 不一樣")
    cal = F["cal"]
    ys = {"v25": year_sums(cal, W["Y"], W["hist"]), "v26": year_sums(cal, W["Y"], W26["hist26"]),
          "decay": year_sums(cal, W["Y"], W["histD"])}
    cmp = {k: {side: {r: rate(ys[r][k][side]) for r in ys} for side in ("up", "warn")} for k in S.THERMO_H}
    ref = TC.compare(W26["Y"], W26["hist"], W26["hist26"])
    for k in S.THERMO_H:
        for side in ("up", "warn"):
            for r in ("v25", "v26"):
                a, b = cmp[k][side][r], ref[k][side][r]
                if a[1] != b[1] or (a[0] is None) != (b[0] is None) or (a[0] is not None and abs(a[0] - b[0]) > 1e-12):
                    raise RuntimeError(f"{F['mk']} {k} {side} {r}：比例和 thermocal.compare 不一樣 {a} vs {b}")
    return {"cmp": cmp, "ys": ys, "fits": W["fits"], "nogate": W["nogate"]}


def summary(M: dict, draws: int = D.DRAWS, seed: int = D.SEED) -> dict:
    """30 組（市場 × 溫度計 × 邊）的「衰減 − VER 26」平均與以年為一塊重抽的 95% 區間；列出來的項目週數總和；換不換。"""
    groups = [(mk, k, side) for mk in sorted(M) for k in S.THERMO_H for side in ("up", "warn")]
    d0 = []
    for mk, k, side in groups:
        a, b = M[mk]["cmp"][k][side]["decay"][0], M[mk]["cmp"][k][side]["v26"][0]
        if a is not None and b is not None:
            d0.append(a - b)
    years = sorted({y for mk in M for r in ("v26", "decay") for k in S.THERMO_H for side in ("up", "warn")
                    for y in M[mk]["ys"][r][k][side]})
    rng = np.random.default_rng(seed)
    yi = {y: i for i, y in enumerate(years)}
    arr = {}
    for g in groups:
        mk, k, side = g
        z = np.zeros((2, 2, len(years)))
        for j, r in enumerate(("decay", "v26")):
            for y, (s, n) in M[mk]["ys"][r][k][side].items():
                z[j, 0, yi[y]], z[j, 1, yi[y]] = s, n
        arr[g] = z
    boots = []
    for _ in range(draws):
        idx = rng.integers(0, len(years), size=len(years))
        ds = []
        for g in groups:
            z = arr[g][:, :, idx].sum(axis=2)
            if z[0, 1] > 0 and z[1, 1] > 0:
                ds.append(z[0, 0] / z[0, 1] - z[1, 0] / z[1, 1])
        if ds:
            boots.append(float(np.mean(ds)))
    cover = {r: int(sum(M[mk]["cmp"][k][side][r][1] for mk, k, side in groups)) for r in ("v25", "v26", "decay")}
    dm = float(np.mean(d0)) if d0 else None
    lo = float(np.percentile(boots, 2.5)) if boots else None
    hi = float(np.percentile(boots, 97.5)) if boots else None
    win = sum(1 for x in d0 if x > 0)
    return {"d": dm, "lo": lo, "hi": hi, "groups": len(d0), "win": win, "cover": cover,
            "better": D.better(dm, lo, cover["decay"], cover["v26"])}


def run(F: dict | None = None, log=print) -> dict:
    from . import sigcat as G
    F = F if F is not None else G.frames()
    M = {}
    for mk in S.MARKETS:
        if mk in F:
            M[mk] = market(F[mk])
            log(f"[decay] {mk} ok")
    out = {"ver": D.VER, "spec_date": D.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "last": {mk: F[mk]["cal"][-1] for mk in M}, "sum": summary(M),
           "mk": {mk: {"cmp": m["cmp"], "fits": m["fits"], "nogate": m["nogate"]} for mk, m in M.items()}}
    return out


def save(R: dict, path: Path | None = None) -> None:
    (path or OUT).write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load(path: Path | None = None) -> dict | None:
    try:
        R = json.loads((path or OUT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if (R.get("ver") or 0) >= D.VER else None
