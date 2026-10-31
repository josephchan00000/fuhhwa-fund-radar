"""景氣溫度頁第五版的描述層（docs/lab_heat_plan.md 第 14.14 節第 1、2、6 點；規格 heatspec VER 5）。

每天建頁用，只描述現在的位置，不碰預測關係：
  · 歷史位置：近 3 年、近 10 年、有資料以來的百分位（和分數同一條序列）；創幾年新高（新低）；近 10 年範圍與離極值多遠；
  · 頁首熱度色帶：五個面向近 52 週（每週最後一個交易日）的分數與五區、連續幾週、全期間位置、上次這麼熱（冷）、一句話；
  · 邊際變化（核心 13 項）：一階、二階、四種狀態、連續幾期、二階在近 10 年的百分位（研究檔另外驗證）。
全部只用當天拿得到的資料（月資料依公布時間差、美國資料晚一天），和分數同一套對齊規則。
"""
from __future__ import annotations

import bisect
from datetime import date

from . import heat as H
from . import heatcalc as C
from . import heatspec as S

def unit_of(k: str) -> str:
    """項目的單位（依當下規格：台股或美股）。"""
    return next((u for kk, _, _, u, *_ in S.IND if kk == k), "")


def __getattr__(name: str):
    if name == "UNIT":                                       # 舊名稱（外部讀 heatpos.UNIT 也拿得到當下規格的值）
        return {k: u for k, _, _, u, *_ in S.IND}
    raise AttributeError(name)


# ── 小工具 ───────────────────────────────────────────────────────────

def week_ends(cal: list[str]) -> list[int]:
    """每週（週一到週日）最後一個交易日的索引；最後一筆一定在（最新的交易日）。"""
    out = []
    for i, d in enumerate(cal):
        if i == len(cal) - 1 or date.fromisoformat(cal[i + 1]).isocalendar()[:2] != date.fromisoformat(d).isocalendar()[:2]:
            out.append(i)
    return out


def done_week_ends(cal: list[str]) -> list[int]:
    """已經過完的週末（訊號用；docs/lab_signal_quality_plan.md 第 9 節）：同 week_ends，但最新一天不是星期五（或星期六）就不算
    ——那一週還沒過完，當成週末會讓「過熱結束」這類週訊號週中先出現、週五又不見（回測只看真正的週末）。
    週五休市的那一週要到下一週第一個交易日才確定（晚一天，保守）。"""
    we = week_ends(cal)
    if we and we[-1] == len(cal) - 1 and date.fromisoformat(cal[-1]).weekday() < 4:
        we = we[:-1]
    return we


def _pct(past: list, x: float) -> float | None:
    """x 在 past（有值的）裡的百分位，同值算一半。"""
    if not past:
        return None
    s = sorted(past)
    lo, hi = bisect.bisect_left(s, x), bisect.bisect_right(s, x)
    return 100.0 * (lo + 0.5 * (hi - lo)) / len(s)


def _months_between(a: str, b: str) -> int:
    """a、b＝YYYY-MM（或 YYYY-MM-DD 取前 7 碼）→ b − a 的月數。"""
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def _years_back(d: str, n: int) -> str:
    """d 往前 n 個曆年的同一天（2/29 遇到平年用 2/28）。"""
    x = date.fromisoformat(d)
    try:
        return x.replace(year=x.year - n).isoformat()
    except ValueError:
        return x.replace(year=x.year - n, day=28).isoformat()


# ── 1. 歷史位置 ───────────────────────────────────────────────────────

def native(B: dict, k: str, t: int) -> tuple[list[str], list[float]] | None:
    """項目自己的序列（日資料＝來源日期上的值；月資料＝月序列），到第 t 個交易日拿得到的最後一筆為止。
    最後一筆＝頁面顯示的現值（和 raw[k][t] 同一個值）；沒有現值回 None。"""
    if B["raw"][k][t] is None:
        return None
    if S.FREQ_OF[k] == "m":
        cur = B["ym"][k][t]
        M = B["mraw"][k]
        ks = sorted(m for m in M if m <= cur)
        return ks, [M[m] for m in ks]
    N = B["nat"][k]
    day = B["cal"][t]
    ks = sorted(d for d in N if (d < day if k in S.US else d <= day))
    shift = S.AVAIL_DAYS.get(k)
    if shift:                                       # 週資料：存的是「拿得到的日期」，顯示時換回週末日期
        from datetime import timedelta
        ks2 = [(date.fromisoformat(d) - timedelta(days=shift)).isoformat() for d in ks]
        return ks2, [N[d] for d in ks]
    return ks, [N[d] for d in ks]


def position(B: dict, k: str, t: int | None = None) -> dict | None:
    """第 t 個交易日（預設最新）這一項的歷史位置；沒有現值回 None。
    → {"x", "p3", "p10", "pall", "from", "rec": {...} 或 None, "rng": {...} 或 None}"""
    t = len(B["cal"]) - 1 if t is None else t
    nat = native(B, k, t)
    if nat is None:
        return None
    freq = S.FREQ_OF[k]
    w3, w10 = S.POS_WIN[freq]
    if freq == "m":
        ks, vs = nat
        x = vs[-1]
        past_all = vs[:-1]
        win = lambda w: vs[max(0, len(vs) - 1 - w):len(vs) - 1]          # noqa: E731
    else:
        xs = B["raw"][k]
        x = xs[t]
        past_all = [v for v in xs[:t] if v is not None]
        win = lambda w: [v for v in xs[max(0, t - w):t] if v is not None]  # noqa: E731
    out = {"x": x, "p3": None, "p10": None, "pall": None, "from": nat[0][0], "rec": None, "rng": None}
    for key, w in (("p3", w3), ("p10", w10)):
        past = win(w)
        if len(past) >= S.POS_COVER * w:
            out[key] = _pct(past, x)
    if len(past_all) >= S.POS_ALL_MIN[freq]:
        out["pall"] = _pct(past_all, x)
    side_p = out["p10"] if out["p10"] is not None else out["pall"]
    ks, vs = nat
    if side_p is not None:
        out["rec"] = record(ks, vs, side_p >= 50, freq)
    out["rng"] = value_range(ks, vs, k, side_p is None or side_p >= 50)
    return out


def record(ks: list[str], vs: list[float], hi: bool, freq: str) -> dict:
    """上一次「嚴格」比現在高（hi）或低的日期 → 新高新低的說法。
    kind：ath＝有資料以來最高（最低）、since_y＝N 年新高、since＝YYYY 年 M 月以來、None＝相隔太近不寫。"""
    x, cur = vs[-1], ks[-1]
    j = next((i for i in range(len(vs) - 2, -1, -1) if (vs[i] > x if hi else vs[i] < x)), None)
    side = "hi" if hi else "lo"
    if j is None:
        return {"side": side, "kind": "ath", "d": ks[0], "tie": any(v == x for v in vs[:-1]), "n": None}
    if freq == "m":
        gap = _months_between(ks[j], cur)
        lo, yr = S.REC_MONTHS
        n = gap // 12
    else:
        gap = (date.fromisoformat(cur) - date.fromisoformat(ks[j])).days
        lo, yr = S.REC_DAYS
        n = int(gap / 365.25)
    if gap < lo:
        kind = None
    elif gap < yr:
        kind = "since"
    else:
        kind = "since_y"
    return {"side": side, "kind": kind, "d": ks[j], "tie": False, "n": n if kind == "since_y" else None}


def value_range(ks: list[str], vs: list[float], k: str, hi: bool) -> dict | None:
    """近 10 年（曆年，含今天）的最高、最低與日期（同值取最近一次），以及離那一邊的極值多遠。"""
    cur = ks[-1]
    a = _years_back(cur if len(cur) == 10 else cur + "-01", S.RANGE_YEARS)
    if len(cur) == 7:                                 # 月資料：近 120 個月
        a = C.ym_add(cur, -(12 * S.RANGE_YEARS - 1))
    pts = [(d, v) for d, v in zip(ks, vs) if d >= a[:len(d)] and (len(cur) == 7 or d > a)]
    if not pts:
        return None
    hv = max(v for _, v in pts)
    lv = min(v for _, v in pts)
    hd = max(d for d, v in pts if v == hv)
    ld = max(d for d, v in pts if v == lv)
    x = vs[-1]
    ext = hv if hi else lv
    unit = unit_of(k)
    if unit in S.PP_UNITS:
        dist, how = x - ext, "pp"
    elif all(v > 0 for _, v in pts):
        dist, how = 100.0 * (x / ext - 1.0), "pct"
    else:
        dist, how = x - ext, "abs"
    return {"hi": hv, "hi_d": hd, "lo": lv, "lo_d": ld, "side": "hi" if hi else "lo", "dist": dist, "how": how,
            "a": pts[0][0]}


# ── 2. 頁首熱度色帶 ───────────────────────────────────────────────────

def strip(B: dict, dim: str, t: int | None = None, we: list[int] | None = None) -> dict:
    """一個面向的近 52 週色帶與說明。we＝week_ends(cal)（算過就傳進來）。"""
    cal, comp = B["cal"], B["comp"][dim]
    t = len(cal) - 1 if t is None else t
    we = [i for i in (we if we is not None else week_ends(cal)) if i <= t]
    if not we or we[-1] != t:
        we = we + [t]
    cells = [(cal[i], comp[i], S.band(comp[i])) for i in we[-S.STRIP_WEEKS:]]
    x = comp[t]
    out = {"cells": cells, "score": x, "band": S.band(x), "weeks": 0, "first": None, "pos": None, "last": None}
    if x is None:
        return out
    bd = out["band"]
    n = 0
    for i in reversed(we):
        if S.band(comp[i]) != bd:
            break
        n += 1
    out["weeks"] = n
    first = next(i for i, v in enumerate(comp) if v is not None)
    out["first"] = cal[first]
    past = [v for v in comp[first:t] if v is not None]
    j = t                                               # 目前這一段（連續在同一區的交易日）的第一天
    while j > first and comp[j - 1] is not None and S.band(comp[j - 1]) == bd:
        j -= 1
    lo_mid, hi_mid = S.STRIP_MID
    if x >= hi_mid:
        out["pos"] = ("hot", 100.0 * sum(1 for v in past if v < x) / len(past)) if past else None
        k = next((i for i in range(j - 1, first - 1, -1) if comp[i] is not None and comp[i] >= x), None)
        out["last"] = ("hot", cal[k] if k is not None else None)
    elif x < lo_mid:
        out["pos"] = ("cold", 100.0 * sum(1 for v in past if v > x) / len(past)) if past else None
        k = next((i for i in range(j - 1, first - 1, -1) if comp[i] is not None and comp[i] <= x), None)
        out["last"] = ("cold", cal[k] if k is not None else None)
    else:
        out["pos"] = ("mid", _pct(past, x)) if past else None
    return out


def summary(strips: dict) -> str:
    """一句話：依區由熱到冷列面向名稱；過熱或過冷而且連續 ≥ 4 週的加「（N 週）」。"""
    parts = []
    for _, _, bd in reversed(S.BANDS):
        names = []
        for dim, st in strips.items():
            if st["band"] != bd:
                continue
            nm = S.DSHORT[dim]
            if bd in ("過熱", "過冷") and st["weeks"] >= S.STRIP_RUN_NOTE:
                nm += f"（{st['weeks']} 週）"
            names.append(nm)
        if names:
            parts.append("、".join(names) + bd)
    return "；".join(parts)


# ── 6. 邊際變化（核心 13 項） ────────────────────────────────────────

def _sign(v) -> int:
    return 0 if v is None or v == 0 else (1 if v > 0 else -1)


def state_of(d1, d2) -> int | None:
    """1＝一階 > 0、二階 > 0；2＝一階 > 0、二階 < 0；3＝一階 < 0、二階 < 0；4＝一階 < 0、二階 > 0；0＝持平；沒值 None。"""
    if d1 is None or d2 is None:
        return None
    a, b = _sign(d1), _sign(d2)
    if a == 0 or b == 0:
        return 0
    return {(1, 1): 1, (1, -1): 2, (-1, -1): 3, (-1, 1): 4}[(a, b)]


def word(k: str, st: int | None) -> str | None:
    if st is None:
        return None
    if st == 0:
        return S.DERIV_FLAT
    return S.DERIV_WORDS[S.DERIV[k]["kind"]][st - 1]


def _monthly_d(M: dict, spec: dict) -> tuple[dict, dict]:
    """月序列 {YYYY-MM: 值} → 一階、二階（月份相減，缺月就沒有）。"""
    d1 = {}
    for ym, v in M.items():
        if spec["d1"] == "self":
            d1[ym] = v
        elif spec["d1"] == "minus50":
            d1[ym] = v - 50.0
        elif spec["d1"] == "chg":
            b = M.get(C.ym_add(ym, -spec["L1"]))
            if b is not None:
                d1[ym] = v - b
        else:                                       # pct（月資料目前沒有用到）
            b = M.get(C.ym_add(ym, -spec["L1"]))
            if b:
                d1[ym] = 100.0 * (v / b - 1.0)
    d2 = {}
    for ym, v in d1.items():
        b = d1.get(C.ym_add(ym, -spec["L2"]))
        if b is not None:
            d2[ym] = v - b
    return d1, d2


def _daily_d(N: dict, spec: dict) -> tuple[dict, dict]:
    """來源日期上的序列 {日期: 值} → 一階、二階（依筆數相減；先取 smooth 筆平均）。"""
    ks = sorted(d for d, v in N.items() if v is not None)
    vs = [N[d] for d in ks]
    if spec.get("smooth"):
        vs = H.roll_mean(vs, spec["smooth"])
    d1: list = [None] * len(vs)
    for i, v in enumerate(vs):
        if v is None:
            continue
        if spec["d1"] == "self":
            d1[i] = v
        elif spec["d1"] == "minus50":
            d1[i] = v - 50.0
        else:
            j = i - spec["L1"]
            b = vs[j] if j >= 0 else None
            if b is None:
                continue
            if spec["d1"] == "chg":
                d1[i] = v - b
            elif b:
                d1[i] = 100.0 * (v / b - 1.0)
    L2 = spec["L2"]
    d2 = [None if i < L2 or d1[i] is None or d1[i - L2] is None else d1[i] - d1[i - L2] for i in range(len(d1))]
    return ({d: v for d, v in zip(ks, d1) if v is not None}, {d: v for d, v in zip(ks, d2) if v is not None})


def deriv(B: dict, k: str) -> dict:
    """核心訊號 k 的邊際變化：
    native＝(一階 dict, 二階 dict)（來源日期或月份上）；
    d1、d2、acc（二階熱度：二階在近 10 年的百分位依熱的方向轉換）、state：對齊交易日的逐日序列（只用當天拿得到的）。"""
    spec = S.DERIV[k]
    cal = B["cal"]
    if S.FREQ_OF[k] == "m":
        d1, d2 = _monthly_d(B["mraw"][k], spec)
        rel = S.RELEASE[k]
        a1, a2 = H.asof_monthly(cal, d1, rel), H.asof_monthly(cal, d2, rel)
        ks = sorted(d2)
        p = H.pct_series([d2[m] for m in ks], S.DERIV_PCT_WIN["m"], S.DERIV_PCT_MIN["m"])
        acc = H.asof_monthly(cal, {m: H.to_heat(x, S.HOT[k]) for m, x in zip(ks, p) if x is not None}, rel)
    else:
        d1, d2 = _daily_d(B["nat"][k], spec)
        stale = S.STALE.get(k, 7)
        a1 = H.asof_daily(cal, d1, after=k in S.US, stale=stale)
        a2 = H.asof_daily(cal, d2, after=k in S.US, stale=stale)
        acc = [H.to_heat(x, S.HOT[k]) for x in H.pct_series(a2, S.DERIV_PCT_WIN["d"], S.DERIV_PCT_MIN["d"])]
    state = [state_of(x, y) for x, y in zip(a1, a2)]
    return {"native": (d1, d2), "d1": a1, "d2": a2, "acc": acc, "state": state}


def deriv_now(B: dict, k: str, D: dict | None = None, t: int | None = None) -> dict | None:
    """第 t 個交易日（預設最新）的邊際變化：一階、二階、狀態、用詞、連續幾期、資料日、二階熱度、二階在近 10 年的百分位。"""
    D = D if D is not None else deriv(B, k)
    cal = B["cal"]
    t = len(cal) - 1 if t is None else t
    v1, v2 = D["d1"][t], D["d2"][t]
    if v1 is None or v2 is None:
        return None
    d1n, d2n = D["native"]
    if S.FREQ_OF[k] == "m":
        cur = B["ym"][k][t]
        ks = sorted(m for m in d2n if m <= cur)
    else:
        day = cal[t]
        ks = sorted(d for d in d2n if (d < day if k in S.US else d <= day))
    st = state_of(v1, v2)
    sg = _sign(v2)
    n = 0
    for d in reversed(ks):
        if _sign(d2n[d]) != sg or sg == 0:
            break
        n += 1
    acc = D["acc"][t]
    raw_p = None if acc is None else (acc if S.HOT[k] > 0 else 100.0 - acc)
    return {"d1": v1, "d2": v2, "state": st, "word": word(k, st), "streak": n, "asof": ks[-1] if ks else None,
            "acc": acc, "p10": raw_p, "note": S.DERIV_NOTE.get(k)}
