"""W1：超級飆股觀察名單的評估（reports/W1_plan.md，跑之前寫定）。只評估名單，不評估買賣規則。

名單在每週最後一個交易日收盤產生（只用當天以前的資料）；飆股標籤與段落是唯一用到未來的東西。
"""

from __future__ import annotations

import numpy as np

from . import features as FT

SCREENS = {"S1": "現行飆股候選", "S2": "趨勢樣板", "S3": "樣板＋強勢前 10%", "S4": "VCP 成形", "S5": "VCP＋樣板",
           "S6": "營收創新高＋樣板", "S7": "營收強＋樣板", "S8": "一年翻倍規則", "S9": "合併名單（S1＋S5＋S6）"}
LABELS = {"A": (60, 0.5), "B": (250, 1.0), "C": (250, 2.0)}       # 飆股、翻倍股、超級飆股
SIZE_MAX = 30                                                      # 每週平均檔數上限（人看得過來）
PRE, GAP, EARLY, N_RAND = 60, 20, 0.5, 20
LIFT_MIN = 1.5


# ---------------------------------------------------------------------------------------------- 名單
def week_lists(ctx, F: dict, b_rows: list[tuple[str, str]], rev_yoy: float = 0.20) -> dict[str, np.ndarray]:
    """{名單: (週數 × 股票) bool}，列＝ctx.week_ends。"""
    m = ctx.m
    W = np.array(ctx.week_ends)
    el = F["elig"][W]
    tt = F["tt_pass"][W] & el
    rs = np.nan_to_num(F["rs"][W], nan=0.0)
    vcp = F["vcp_ok"][W] & el
    bsig = np.zeros(m.c.shape, dtype=bool)
    ix = {d: i for i, d in enumerate(m.dates.strftime("%Y-%m-%d"))}
    for c, d in b_rows:
        j, i = m.col.get(c), ix.get(d)
        if j is not None and i is not None:
            bsig[i, j] = True
    rnha = np.zeros(tt.shape, dtype=bool)
    rstr = np.zeros(tt.shape, dtype=bool)
    for k, j in zip(*np.nonzero(tt)):
        f = ctx.fund(m.stocks[j], int(W[k]))
        rnha[k, j] = f.get("rnha") is True
        rstr[k, j] = f.get("rnh12") is True or (f.get("ry3") is not None and f["ry3"] >= rev_yoy)
    L = {"S1": ctx.asig[W] & el, "S2": tt, "S3": tt & (rs >= 90), "S4": vcp, "S5": vcp & tt, "S6": tt & rnha,
         "S7": tt & rstr, "S8": bsig[W] & el}
    L["S9"] = L["S1"] | L["S5"] | L["S6"]
    return L


# ---------------------------------------------------------------------------------------------- 標籤與段落
def labels(m, elig: np.ndarray) -> dict[str, np.ndarray]:
    return {k: FT.label(m, n, g, elig) for k, (n, g) in LABELS.items()}


def episodes(m, y: np.ndarray, n: int = 250, gap: int = GAP) -> list[tuple[int, int, int, float]]:
    """[(股票欄, 起漲點 T0, 高點日, 漲幅)]：連續標成正的日子（間隔 < gap 併段）→ 段內收盤最低為 T0、之後 n 日最高為高點。"""
    out = []
    c, h = m.c, m.h
    for j in range(y.shape[1]):
        pos = np.flatnonzero(y[:, j] == 1)
        if not len(pos):
            continue
        cut = np.flatnonzero(np.diff(pos) >= gap) + 1
        for g in np.split(pos, cut):
            cg = c[g, j]
            t0 = int(g[np.nanargmin(cg)])
            seg = h[t0 + 1:t0 + n + 1, j]
            if not np.isfinite(seg).any():
                continue
            pk = t0 + 1 + int(np.nanargmax(seg))
            out.append((j, t0, pk, float(h[pk, j] / c[t0, j] - 1)))
    return out


def capture(ep: list[tuple], L: np.ndarray, W: np.ndarray, c: np.ndarray, h: np.ndarray) -> list[dict]:
    """每一段：名單在 [T0 − PRE, 高點) 有沒有出現過、出現時還剩多少漲幅、有沒有「抓得早」（還剩 ≥ EARLY）。"""
    out = []
    for j, t0, pk, gain in ep:
        a, b = np.searchsorted(W, t0 - PRE), np.searchsorted(W, pk)
        ks = a + np.flatnonzero(L[a:b, j])
        if not len(ks):
            out.append({"hit": False, "early": False, "rem": None, "gain": gain})
            continue
        cw = c[W[ks], j]
        rem = h[pk, j] / cw[~np.isnan(cw)] - 1
        out.append({"hit": True, "early": bool((rem >= EARLY).any()), "rem": float(rem[0]) if len(rem) else None,
                    "gain": gain})
    return out


def random_lists(L: np.ndarray, el: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """每週抽同樣檔數的隨機合格股票。"""
    R = np.zeros(L.shape, dtype=bool)
    for k in range(L.shape[0]):
        n = int(L[k].sum())
        pool = np.flatnonzero(el[k])
        if n and len(pool):
            R[k, rng.choice(pool, size=min(n, len(pool)), replace=False)] = True
    return R


# ---------------------------------------------------------------------------------------------- 指標
def _rate(xs) -> float | None:
    xs = list(xs)
    return float(np.mean(xs)) if xs else None


def screen_stats(L: np.ndarray, Y: dict[str, np.ndarray], W: np.ndarray, el: np.ndarray, rows: np.ndarray,
                 eps: dict[str, list], m, rng: np.random.Generator, n_rand: int = N_RAND) -> dict:
    """rows＝這段期間的週（bool，長度＝週數）；eps＝{標籤: 這段期間的段落}。"""
    Lr = L[rows]
    out: dict = {"size": float(Lr.sum(axis=1).mean()) if rows.any() else None}
    for k, y in Y.items():
        yw = y[W][rows]
        ok = ~np.isnan(yw)
        sel = Lr & ok
        base = float(np.nansum(yw * (el[rows] & ok)) / max(1, (el[rows] & ok).sum()))
        p = float(np.nansum(yw[sel]) / sel.sum()) if sel.sum() else None
        out[f"prec_{k}"], out[f"base_{k}"] = p, base
        out[f"lift_{k}"] = p / base if p is not None and base > 0 else None
        if k in ("B", "C"):
            full = ok.any(axis=1)                                      # 標籤走完的週
            out[f"week_{k}"] = _rate(bool((yw[i] == 1)[Lr[i]].any()) for i in np.flatnonzero(full))
    for k in ("B", "C"):
        cp = capture(eps[k], L, W, m.c, m.h)
        out[f"n_ep_{k}"] = len(cp)
        out[f"hit_{k}"] = _rate(x["hit"] for x in cp)
        out[f"early_{k}"] = _rate(x["early"] for x in cp)
        rems = sorted(x["rem"] for x in cp if x["rem"] is not None)
        out[f"rem_{k}"] = rems[len(rems) // 2] if rems else None
    rnd = {f"early_{k}": [] for k in ("B", "C")} | {f"week_{k}": [] for k in ("B", "C")}
    for _ in range(n_rand):
        R = random_lists(L, el, rng)
        Rr = R[rows]
        for k in ("B", "C"):
            cp = capture(eps[k], R, W, m.c, m.h)
            rnd[f"early_{k}"].append(_rate(x["early"] for x in cp) or 0.0)
            yw = Y[k][W][rows]
            full = (~np.isnan(yw)).any(axis=1)
            rnd[f"week_{k}"].append(_rate(bool((yw[i] == 1)[Rr[i]].any()) for i in np.flatnonzero(full)) or 0.0)
    for key, xs in rnd.items():
        out[f"rand_{key}"] = float(np.mean(xs))
        v = out.get(key)
        out[f"rlift_{key}"] = v / out[f"rand_{key}"] if v is not None and out[f"rand_{key}"] > 0 else None
    return out


def choose(stats: dict[str, dict], periods=("IS", "VAL")) -> str | None:
    """第 5 節：每週 ≤ SIZE_MAX 檔、超級飆股抓得早 ≥ 隨機 × 1.5、翻倍股提升倍數 ≥ 1.5（IS、VAL 都要）→ 抓得早比例最高。"""
    ok = []
    for s, st in stats.items():
        if all((st[p]["size"] or 1e9) <= SIZE_MAX and (st[p].get("rlift_early_C") or 0) >= LIFT_MIN
               and (st[p].get("lift_B") or 0) >= LIFT_MIN for p in periods):
            ok.append(s)
    if not ok:
        return None
    key = lambda s: (np.mean([stats[s][p]["early_C"] or 0 for p in periods]),
                     np.mean([stats[s][p]["early_B"] or 0 for p in periods]))
    return max(ok, key=key)
