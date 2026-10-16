"""W1：超級飆股觀察名單的評估（reports/W1_plan.md v2，跑之前寫定）。只評估名單，不評估買賣規則。

名單在每週最後一個交易日收盤產生（只用當天以前的資料）；飆股標籤與段落是唯一用到未來的東西。
"""

from __future__ import annotations

import math

import numpy as np

from . import features as FT

SCREENS = {"S1": "現行飆股候選", "S2": "趨勢樣板", "S3": "樣板＋強勢前 10%", "S4": "VCP 成形", "S5": "VCP＋樣板",
           "S6": "營收創新高＋樣板", "S7": "營收強＋樣板", "S8": "一年翻倍規則", "S9": "合併名單（S1＋S5＋S6）"}
# 標籤：(期限交易日, 最高漲幅門檻)。A 飆股、B 翻倍股、C 超級飆股（一年 3 倍）；v2 加 D 5 倍（3 年）、E 10 倍、F 20 倍（5 年）
LABELS = {"A": (60, 0.5), "B": (250, 1.0), "C": (250, 2.0), "D": (750, 4.0), "E": (1250, 9.0), "F": (1250, 19.0)}
LNAME = {"A": "3 個月 +50%", "B": "一年翻倍", "C": "一年 3 倍", "D": "3 年 5 倍", "E": "5 年 10 倍", "F": "5 年 20 倍"}
SHORT = ("B", "C")                                                 # 分 IS／VAL／保留期算
LONG = ("D", "E", "F")                                             # 段落少，合在全期算
# 抓得早：第一次之後任一次出現時，到高點還剩的漲幅門檻（v1：一年期 +50%；v2：多年期還剩 √k 倍）
EARLY = {"B": 0.5, "C": 0.5, "D": math.sqrt(5) - 1, "E": math.sqrt(10) - 1, "F": math.sqrt(20) - 1}
SIZE_MAX = 30                                                      # 每週平均檔數上限（人看得過來）
PRE, GAP, N_RAND = 60, 20, 20
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


def capture(ep: list[tuple], L: np.ndarray, W: np.ndarray, c: np.ndarray, h: np.ndarray,
            early: float = 0.5) -> list[dict]:
    """每一段：名單在 [T0 − PRE, 高點) 有沒有出現過；第一次出現時已漲幾倍、離高點還剩多少；
    抓得早＝其中任一次出現時離高點還剩 ≥ early。"""
    out = []
    for j, t0, pk, gain in ep:
        a, b = np.searchsorted(W, t0 - PRE), np.searchsorted(W, pk)
        ks = a + np.flatnonzero(L[a:b, j])
        if not len(ks):
            out.append({"hit": False, "early": False, "rem": None, "gain": gain, "first": None, "up": None})
            continue
        cw = c[W[ks], j]
        good = ~np.isnan(cw)
        rem = h[pk, j] / cw[good] - 1
        k0 = int(ks[good][0]) if good.any() else int(ks[0])
        out.append({"hit": True, "early": bool((rem >= early).any()), "rem": float(rem[0]) if len(rem) else None,
                    "gain": gain, "first": int(W[k0]), "up": float(c[W[k0], j] / c[t0, j] - 1) if good.any() else None})
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
                 eps: dict[str, list], m, rng: np.random.Generator, labs: tuple[str, ...] = SHORT,
                 prec: tuple[str, ...] = ("A", "B", "C"), n_rand: int = N_RAND) -> dict:
    """rows＝這段期間的週（bool，長度＝週數）；eps＝{標籤: 這段期間的段落}；labs＝要算「抓到幾成」的標籤。"""
    Lr = L[rows]
    out: dict = {"size": float(Lr.sum(axis=1).mean()) if rows.any() else None}
    for k in prec:
        yw = Y[k][W][rows]
        ok = ~np.isnan(yw)
        sel = Lr & ok
        base = float(np.nansum(yw * (el[rows] & ok)) / max(1, (el[rows] & ok).sum()))
        p = float(np.nansum(yw[sel]) / sel.sum()) if sel.sum() else None
        out[f"prec_{k}"], out[f"base_{k}"] = p, base
        out[f"lift_{k}"] = p / base if p is not None and base > 0 else None
        if k in labs:
            full = ok.any(axis=1)                                      # 標籤走完的週
            out[f"week_{k}"] = _rate(bool((yw[i] == 1)[Lr[i]].any()) for i in np.flatnonzero(full))
    for k in labs:
        cp = capture(eps[k], L, W, m.c, m.h, EARLY[k])
        out[f"n_ep_{k}"] = len(cp)
        out[f"hit_{k}"] = _rate(x["hit"] for x in cp)
        out[f"early_{k}"] = _rate(x["early"] for x in cp)
        rems = sorted(x["rem"] for x in cp if x["rem"] is not None)
        out[f"rem_{k}"] = rems[len(rems) // 2] if rems else None
    rnd = {f"{a}_{k}": [] for a in ("early", "week") for k in labs}
    for _ in range(n_rand):
        R = random_lists(L, el, rng)
        Rr = R[rows]
        for k in labs:
            cp = capture(eps[k], R, W, m.c, m.h, EARLY[k])
            rnd[f"early_{k}"].append(_rate(x["early"] for x in cp) or 0.0)
            yw = Y[k][W][rows]
            full = (~np.isnan(yw)).any(axis=1)
            rnd[f"week_{k}"].append(_rate(bool((yw[i] == 1)[Rr[i]].any()) for i in np.flatnonzero(full)) or 0.0)
    for key, xs in rnd.items():
        out[f"rand_{key}"] = float(np.mean(xs))
        v = out.get(key)
        out[f"rlift_{key}"] = v / out[f"rand_{key}"] if v is not None and out[f"rand_{key}"] > 0 else None
    return out


def cases(ep: list[tuple], Ls: dict[str, np.ndarray], W: np.ndarray, m, early: float) -> list[dict]:
    """逐檔表：每一段（例如 10 倍股）＋每份名單第一次列出它的日期、當時已漲幾倍、離高點還剩幾倍、算不算抓得早。"""
    out = []
    for e in sorted(ep, key=lambda e: -e[3]):
        j, t0, pk, gain = e
        row = {"c": m.stocks[j], "t0": str(m.dates[t0].date()), "pk": str(m.dates[pk].date()), "x": round(gain + 1, 1),
               "by": {}}
        for s, L in Ls.items():
            x = capture([e], L, W, m.c, m.h, early)[0]
            if x["hit"]:
                row["by"][s] = {"d": str(m.dates[x["first"]].date()), "up": None if x["up"] is None else round(x["up"] + 1, 2),
                                "rem": None if x["rem"] is None else round(x["rem"] + 1, 2), "early": x["early"]}
        out.append(row)
    return out


def choose(stats: dict[str, dict], periods=("IS", "VAL")) -> tuple[str | None, list[str]]:
    """v2 第 7 節：資格（IS、VAL 都要：每週 ≤ SIZE_MAX 檔、一年 3 倍抓得早 ≥ 隨機 × 1.5、翻倍股提升倍數 ≥ 1.5）
    → 依全期 5 倍與 10 倍股「抓得早」平均排序，同分比一年 3 倍抓得早；沒有名單有資格時改取每週 ≤ SIZE_MAX 檔裡排序最前的，
    並回傳它沒達到的條件。"""
    def small(s):
        return all((stats[s][p]["size"] or 1e9) <= SIZE_MAX for p in periods)

    def missing(s):
        out = []
        for p in periods:
            st = stats[s][p]
            if (st.get("rlift_early_C") or 0) < LIFT_MIN:
                out.append(f"{p} 一年 3 倍抓得早不到隨機的 {LIFT_MIN:g} 倍")
            if (st.get("lift_B") or 0) < LIFT_MIN:
                out.append(f"{p} 翻倍股提升倍數不到 {LIFT_MIN:g}")
        return out

    def key(s):
        a = stats[s].get("ALL") or {}
        return (np.mean([a.get("early_D") or 0, a.get("early_E") or 0]),
                np.mean([stats[s][p].get("early_C") or 0 for p in periods]))
    pool = [s for s in stats if small(s)]
    ok = [s for s in pool if not missing(s)]
    if ok:
        return max(ok, key=key), []
    if pool:
        best = max(pool, key=key)
        return best, missing(best)
    return None, []
