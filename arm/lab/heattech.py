"""景氣溫度頁：技術面的關鍵價位與事件（docs/lab_heat_plan.md 第 13.3、13.8 節；規格 heatspec VER 4）。

純函式、只用加權指數收盤、不偷看未來：
  · 轉折點：收盤從最高點回落 PIVOT_THR（5%）才確認那個高點（低點反之），記下確認日；確認前不知道它是轉折點。
  · 狀態改變（跌破／站回均線、月線季線交叉、季線轉向）：之前至少 EV_PRIOR 個交易日都是原來的狀態，
    連 EV_CONF 個交易日變成新的狀態才算，事件日是最後那一天。
  · 跌破前波低點／突破前波高點：最近一個已確認的低（高）點，收盤第一次穿過那天；每個轉折點只算一次。
  · 型態：M 頭／W 底、頭肩頂／頭肩底用已確認的轉折點認，最後一個轉折點確認後、下一個轉折點確認前，
    收盤第一次跌破（突破）頸線那天才成立。
  · 事件研究：之後 10／60 個交易日的漲跌（t＋1 收盤起算，同 heat.fwd），和同期所有交易日比；移動區塊重抽信賴區間、前後兩半。
"""
from __future__ import annotations

import random
import statistics

from . import heat as H
from . import heatspec as S


# ── 均線 ─────────────────────────────────────────────────────────────

def mas(px: list, ns=S.MA_NS) -> dict[int, list]:
    return {n: H.roll_mean(px, n) for n in ns}


def _side(a, b):
    if a is None or b is None:
        return None
    return 1 if a > b else (-1 if a < b else 0)


# ── 轉折點 ────────────────────────────────────────────────────────────

def pivots(px: list, thr: float = S.PIVOT_THR) -> list[dict]:
    """收盤轉折點（directional change）：{k: "H"/"L", i: 高低點那天, p: 收盤, c: 確認那天}，高低交替。
    一開始兩邊都找，先碰到門檻的那邊決定第一個轉折點。"""
    out: list[dict] = []
    mode = 0                       # 0＝未定、+1＝往上找高點、−1＝往下找低點
    hi = lo = None
    for i, p in enumerate(px):
        if p is None:
            continue
        if hi is None:
            hi = lo = i
            continue
        if mode >= 0 and p > px[hi]:
            hi = i
        if mode <= 0 and p < px[lo]:
            lo = i
        if mode >= 0 and p <= px[hi] * (1 - thr):
            out.append({"k": "H", "i": hi, "p": px[hi], "c": i})
            mode, lo = -1, i
        elif mode <= 0 and p >= px[lo] * (1 + thr):
            out.append({"k": "L", "i": lo, "p": px[lo], "c": i})
            mode, hi = 1, i
    return out


def confirmed(pv: list[dict], t: int) -> list[dict]:
    """t 日收盤時已確認的轉折點。"""
    return [x for x in pv if x["c"] <= t]


# ── 事件 ─────────────────────────────────────────────────────────────

def state_events(sd: list, prior: int = S.EV_PRIOR, conf: int = S.EV_CONF) -> tuple[list[int], list[int]]:
    """sd＝逐日狀態（+1／−1；0 或 None 算不成立）→（變成 −1 的事件日, 變成 +1 的事件日）。
    事件日 t：t−conf+1…t 都是新狀態，再往前 prior 天（t−conf−prior+1…t−conf）都是另一個狀態。"""
    dn, up = [], []
    for t in range(prior + conf - 1, len(sd)):
        new = sd[t - conf + 1:t + 1]
        old = sd[t - conf - prior + 1:t - conf + 1]
        if all(x == -1 for x in new) and all(x == 1 for x in old):
            dn.append(t)
        elif all(x == 1 for x in new) and all(x == -1 for x in old):
            up.append(t)
    return dn, up


def break_events(px: list, pv: list[dict]) -> tuple[list[int], list[int]]:
    """跌破前波低點（dn）／突破前波高點（up）：最近一個已確認（確認日 < t）的低（高）點，
    t 日收盤 < 它而前一日收盤 ≥ 它（突破反之）；每個轉折點只算一次。"""
    dn, up = [], []
    last = {"H": None, "L": None}
    done: set[int] = set()
    j = 0
    for t in range(1, len(px)):
        while j < len(pv) and pv[j]["c"] < t:
            last[pv[j]["k"]] = j
            j += 1
        if px[t] is None or px[t - 1] is None:
            continue
        lo, hi = last["L"], last["H"]
        if lo is not None and lo not in done and px[t] < pv[lo]["p"] <= px[t - 1]:
            dn.append(t)
            done.add(lo)
        if hi is not None and hi not in done and px[t] > pv[hi]["p"] >= px[t - 1]:
            up.append(t)
            done.add(hi)
    return dn, up


def _window(pv: list[dict], j: int, n: int) -> range:
    """第 j 個轉折點確認那天起、下一個轉折點確認前（不含那天）。"""
    end = pv[j + 1]["c"] if j + 1 < len(pv) else n
    return range(pv[j]["c"], end)


def double_events(px: list, pv: list[dict], tol: float = S.DT_TOL, gap: int = S.DT_GAP) -> tuple[list[int], list[int]]:
    """M 頭（dn）／W 底（up），Lo、Mamaysky、Wang（2000）：連續三個轉折點＝高、低、高（W 底反之），
    兩個高點相差 ≤ tol ×（兩者平均）、相隔 ≥ gap 個交易日；頸線＝中間的低點。第三個轉折點確認後、
    下一個轉折點確認前，收盤第一次 < 頸線（W 底：> 頸線）那天成立。"""
    dn, up = [], []
    for j in range(2, len(pv)):
        a, m, b = pv[j - 2], pv[j - 1], pv[j]
        if abs(a["p"] - b["p"]) > tol * (a["p"] + b["p"]) / 2 or b["i"] - a["i"] < gap:
            continue
        top = b["k"] == "H"
        for t in _window(pv, j, len(px)):
            if px[t] is not None and (px[t] < m["p"] if top else px[t] > m["p"]):
                (dn if top else up).append(t)
                break
    return dn, up


def hs_events(px: list, pv: list[dict], ratio: float = S.HS_RATIO) -> tuple[list[int], list[int]]:
    """頭肩頂（dn）／頭肩底（up），neurotrader888 的規則：連續五個轉折點＝左肩、腋下、頭、腋下、右肩；
    頭最高（最低）；兩肩都不低於（不高於）「對側肩和它的腋下」的中點；左右兩段時間比 ≤ ratio；
    頸線＝兩個腋下的連線。右肩確認後、下一個轉折點確認前，收盤第一次跌破（突破）頸線那天成立。"""
    dn, up = [], []
    for j in range(4, len(pv)):
        ls, a1, h, a2, rs = pv[j - 4:j + 1]
        top = rs["k"] == "H"
        if top:
            if not (h["p"] > ls["p"] and h["p"] > rs["p"]):
                continue
            if ls["p"] < (rs["p"] + a2["p"]) / 2 or rs["p"] < (ls["p"] + a1["p"]) / 2:
                continue
        else:
            if not (h["p"] < ls["p"] and h["p"] < rs["p"]):
                continue
            if ls["p"] > (rs["p"] + a2["p"]) / 2 or rs["p"] > (ls["p"] + a1["p"]) / 2:
                continue
        lt, rt = h["i"] - ls["i"], rs["i"] - h["i"]
        if rt > ratio * lt or lt > ratio * rt:
            continue
        slope = (a2["p"] - a1["p"]) / (a2["i"] - a1["i"])
        for t in _window(pv, j, len(px)):
            neck = a1["p"] + (t - a1["i"]) * slope
            if px[t] is not None and (px[t] < neck if top else px[t] > neck):
                (dn if top else up).append(t)
                break
    return dn, up


def all_events(px: list) -> dict[str, list[int]]:
    """16 種事件（heatspec.EVENTS）→ {事件: 事件日索引}。"""
    M = mas(px)
    pv = pivots(px)
    ev: dict[str, list[int]] = {}
    for n, a, b in ((20, "ma20_dn", "ma20_up"), (60, "ma60_dn", "ma60_up"), (240, "ma240_dn", "ma240_up")):
        ev[a], ev[b] = state_events([_side(p, m) for p, m in zip(px, M[n])])
    ev["x_dead"], ev["x_gold"] = state_events([_side(a, b) for a, b in zip(M[20], M[60])])
    m60 = M[60]
    ev["s60_dn"], ev["s60_up"] = state_events([None] + [_side(m60[i], m60[i - 1]) for i in range(1, len(m60))])
    ev["pv_dn"], ev["pv_up"] = break_events(px, pv)
    ev["dtop"], ev["dbot"] = double_events(px, pv)
    ev["hstop"], ev["hsbot"] = hs_events(px, pv)
    return {k: ev[k] for k in S.EVENTS}


# ── 事件研究 ─────────────────────────────────────────────────────────

def _mean(xs):
    return statistics.mean(xs) if xs else None


def fwd_all(px: list, h: int) -> list:
    return [H.fwd(px, i, h)[0] for i in range(len(px))]


def event_study(px: list, cal: list[str], idx: list[int], h: int, start: int = S.EV_START, f: list | None = None) -> dict:
    """事件之後 h 個交易日的漲跌 vs 同期所有交易日（索引 ≥ start、之後漲跌算得出來的日子）。
    差＝事件平均 − 所有日子平均；信賴區間＝移動區塊重抽（區塊長 h、固定種子）；前後兩半依事件數切在中間那一筆。
    f＝fwd_all(px, h)（同一個 h 算過就傳進來，省時間）。"""
    f = f if f is not None else fwd_all(px, h)
    base = [i for i in range(start, len(px)) if f[i] is not None]
    evs = [i for i in idx if i >= start and f[i] is not None]
    allr = [f[i] for i in base]
    er = [f[i] for i in evs]
    out = {"n": len(evs), "avg": _mean(er), "up": (sum(1 for v in er if v > 0) / len(er)) if er else None,
           "all_avg": _mean(allr), "all_up": (sum(1 for v in allr if v > 0) / len(allr)) if allr else None,
           "a": cal[evs[0]] if evs else None, "z": cal[evs[-1]] if evs else None, "yrs": sorted({cal[i][:4] for i in evs})}
    out["diff"] = None if out["avg"] is None or out["all_avg"] is None else out["avg"] - out["all_avg"]
    ise = set(evs)
    lo, hi = boot_diff(allr, [i in ise for i in base], h)
    out["lo"], out["hi"] = lo, hi
    halves = []
    if len(evs) >= 2:
        m = len(evs) // 2
        cut = evs[m]                                  # 後一半從第 m 筆事件那天起
        for part, rng in ((evs[:m], (start, cut)), (evs[m:], (cut, len(px)))):
            ar = [f[i] for i in base if rng[0] <= i < rng[1]]
            pr = [f[i] for i in part]
            d = None if not ar or not pr else _mean(pr) - _mean(ar)
            halves.append({"n": len(pr), "diff": d})
    out["h1"], out["h2"] = (halves + [None, None])[:2]
    out["verdict"] = ev_verdict(out)
    return out


def boot_diff(r: list, flag: list, L: int, n_boot: int = S.BOOT_N, seed: int = S.BOOT_SEED) -> tuple:
    """移動區塊重抽：每次抽區塊（長 L）湊滿 len(r) 天，算「事件日平均 − 所有日子平均」，取 95% 區間。
    用前綴和，一個區塊 O(1)。事件少於 2 天或天數不到 2L 回 (None, None)。"""
    n = len(r)
    if sum(flag) < 2 or n < 2 * L:
        return None, None
    P, PE, PF = [0.0], [0.0], [0]
    for x, f in zip(r, flag):
        P.append(P[-1] + x)
        PE.append(PE[-1] + (x if f else 0.0))
        PF.append(PF[-1] + (1 if f else 0))
    rnd = random.Random(seed)
    L = max(1, L)
    starts = n - L + 1
    reps = []
    for _ in range(n_boot):
        sa = se = 0.0
        na = ne = 0
        while na < n:
            st = rnd.randrange(starts)
            sa += P[st + L] - P[st]
            se += PE[st + L] - PE[st]
            ne += PF[st + L] - PF[st]
            na += L
        if ne:
            reps.append(se / ne - sa / na)
    if len(reps) < n_boot // 2:
        return None, None
    reps.sort()
    q = (1 - S.CI) / 2
    return reps[int(q * len(reps))], reps[min(len(reps) - 1, int((1 - q) * len(reps)))]


def ev_verdict(r: dict) -> str:
    """few＝事件 < EV_MIN；weak＝差的信賴區間上緣 < 0 而且前後兩半都 < 0；strong 反之；其他 none。"""
    if r["n"] < S.EV_MIN or r["lo"] is None or not r.get("h1") or not r.get("h2") \
            or r["h1"]["diff"] is None or r["h2"]["diff"] is None:
        return "few"
    if r["hi"] < 0 and r["h1"]["diff"] < 0 and r["h2"]["diff"] < 0:
        return "weak"
    if r["lo"] > 0 and r["h1"]["diff"] > 0 and r["h2"]["diff"] > 0:
        return "strong"
    return "none"


# ── 現在的價位 ───────────────────────────────────────────────────────

def streak(sd: list) -> dict:
    """最後一天的狀態、已連續幾天、之前那一段（另一個狀態）連續幾天。
    pending＝已經換到新狀態但還不滿 EV_CONF 天、之前又滿 EV_PRIOR 天（再撐 EV_CONF − n 天就成立）。"""
    if not sd or sd[-1] not in (1, -1):
        return {"side": None, "n": 0, "prev": 0, "pending": False}
    s = sd[-1]
    n = 0
    while n < len(sd) and sd[-1 - n] == s:
        n += 1
    m = 0
    while n + m < len(sd) and sd[-1 - n - m] == -s:
        m += 1
    return {"side": s, "n": n, "prev": m, "pending": n < S.EV_CONF and m >= S.EV_PRIOR}


def levels(px: list, cal: list[str], t: int | None = None) -> dict:
    """t 日（預設最後一天）收盤時：各均線數值、距離、方向；季線扣抵值（之後 5 個交易日）；
    最近的已確認高低點與還沒確認的高低點；下方最近的支撐、上方最近的壓力（均線＋最近 6 個已確認轉折點）。"""
    t = len(px) - 1 if t is None else t
    M = mas(px)
    p = px[t]
    ma = {}
    for n in S.MA_NS:
        v, v0 = M[n][t], M[n][t - 1] if t >= 1 else None
        ma[n] = {"v": v, "dist": None if v is None else 100.0 * (p / v - 1.0),
                 "dir": None if v is None or v0 is None else _side(v, v0)}
    ded = [{"k": k, "v": px[t - 60 + k]} for k in range(1, S.DEDUCT_N + 1) if t - 60 + k >= 0]
    pv = confirmed(pivots(px[:t + 1]), t)
    lastH = next((x for x in reversed(pv) if x["k"] == "H"), None)
    lastL = next((x for x in reversed(pv) if x["k"] == "L"), None)
    cands = [(M[n][t], S.MA_NAME[n], None) for n in S.MA_LEVELS if M[n][t] is not None]
    cands += [(x["p"], "前波高點" if x["k"] == "H" else "前波低點", cal[x["i"]]) for x in pv[-S.LEVEL_PIVOTS:]]
    below = [c for c in cands if c[0] < p]
    above = [c for c in cands if c[0] > p]
    sup = max(below, key=lambda c: c[0]) if below else None
    res = min(above, key=lambda c: c[0]) if above else None
    m60 = M[60]
    states = {f"ma{n}": [_side(a, b) for a, b in zip(px[:t + 1], M[n][:t + 1])] for n in (20, 60, 240)}
    states["x"] = [_side(a, b) for a, b in zip(M[20][:t + 1], M[60][:t + 1])]
    states["s60"] = [None] + [_side(m60[i], m60[i - 1]) for i in range(1, t + 1)]
    return {"t": cal[t], "close": p, "ma": ma, "deduct": ded, "st": {k: streak(v) for k, v in states.items()},
            "hi": None if lastH is None else {"d": cal[lastH["i"]], "p": lastH["p"]},
            "lo": None if lastL is None else {"d": cal[lastL["i"]], "p": lastL["p"]},
            "sup": None if sup is None else {"v": sup[0], "what": sup[1], "d": sup[2], "dist": 100.0 * (sup[0] / p - 1.0)},
            "res": None if res is None else {"v": res[0], "what": res[1], "d": res[2], "dist": 100.0 * (res[0] / p - 1.0)}}
