"""W4（reports/W4_plan.md v1，跑之前寫定）：每週大盤狀態 M1～M9，以及各狀態下名單的命中率。

狀態只用當週收盤以前的資料；加權指數＝價格指數（labpanel 的 index_level）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

VARS = {
    "M1": ("加權指數在 200 日線之上", ["否", "是"]),
    "M2": ("加權指數 50 日線 > 200 日線", ["否", "是"]),
    "M3": ("加權指數離 52 週高點", ["5% 以內", "5～15%", "15% 以上"]),
    "M4": ("合格股票站上 200 日線的比例", ["40% 以下", "40～60%", "60% 以上"]),
    "M5": ("通過趨勢樣板的比例比 4 週前", ["沒有增加", "增加"]),
    "M6": ("52 週新高家數 − 新低家數", ["≤ 0", "> 0"]),
    "M7": ("名單檔數比過去 52 週中位數", ["不較多", "較多"]),
    "M8": ("加權指數近 6 個月報酬", ["≤ 0", "> 0"]),
    "M9": ("加權指數 20 日波動比過去一年中位數", ["不較高", "較高"]),
}
WEEKS_MIN, HALF_MIN, RATIO = 26, 13, 1.3


def daily_states(m, F: dict) -> dict[str, np.ndarray]:
    """日資料的 M1～M4、M6、M8、M9（M5、M7 要用週資料，見 weekly_states）＋通過趨勢樣板的比例。NaN＝資料不夠。"""
    idx = m.index_level.to_numpy(dtype=float)
    s = pd.Series(idx)
    ma50, ma200 = s.rolling(50, min_periods=50).mean().to_numpy(), s.rolling(200, min_periods=200).mean().to_numpy()
    hi = s.rolling(252, min_periods=200).max().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        m1 = np.where(np.isnan(ma200), np.nan, (idx > ma200).astype(float))
        m2 = np.where(np.isnan(ma200) | np.isnan(ma50), np.nan, (ma50 > ma200).astype(float))
        dd = idx / hi - 1
        m3 = np.where(np.isnan(dd), np.nan, np.where(dd >= -0.05, 0, np.where(dd >= -0.15, 1, 2)).astype(float))
        r126 = idx / s.shift(126).to_numpy() - 1
        m8 = np.where(np.isnan(r126), np.nan, (r126 > 0).astype(float))
        lr = np.log(s / s.shift(1))
        vol = (lr.rolling(20, min_periods=20).std() * np.sqrt(252)).to_numpy()
        vmed = pd.Series(vol).rolling(252, min_periods=200).median().to_numpy()
        m9 = np.where(np.isnan(vol) | np.isnan(vmed), np.nan, (vol > vmed).astype(float))
    el = F["elig"]
    C = pd.DataFrame(m.c_ff)
    ma200s = C.rolling(200, min_periods=200).mean().to_numpy()
    cmax = C.rolling(252, min_periods=200).max().to_numpy()
    cmin = C.rolling(252, min_periods=200).min().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        has = el & ~np.isnan(ma200s)
        br = np.where(has.sum(axis=1) > 0, (has & (m.c_ff > ma200s)).sum(axis=1) / np.maximum(has.sum(axis=1), 1), np.nan)
        m4 = np.where(np.isnan(br), np.nan, np.where(br <= 0.40, 0, np.where(br <= 0.60, 1, 2)).astype(float))
        okh = el & ~np.isnan(cmax)
        nh = (okh & (m.c_ff >= cmax)).sum(axis=1)
        nl = (okh & (m.c_ff <= cmin)).sum(axis=1)
        m6 = np.where(okh.sum(axis=1) > 0, (nh - nl > 0).astype(float), np.nan)
        tts = np.where(el.sum(axis=1) > 0, (F["tt_pass"] & el).sum(axis=1) / np.maximum(el.sum(axis=1), 1), np.nan)
    return {"M1": m1, "M2": m2, "M3": m3, "M4": m4, "M6": m6, "M8": m8, "M9": m9, "tts": tts, "br": br, "idx": idx}


def weekly_states(D: dict, W: np.ndarray, s9_count: np.ndarray) -> dict[str, np.ndarray]:
    """週資料：M1～M9（週數 × 1）。M5＝通過樣板比例比 4 週前高；M7＝名單檔數比前 52 週中位數多。"""
    out = {k: D[k][W] for k in ("M1", "M2", "M3", "M4", "M6", "M8", "M9")}
    tts = D["tts"][W]
    m5 = np.full(len(W), np.nan)
    m5[4:] = np.where(np.isnan(tts[4:]) | np.isnan(tts[:-4]), np.nan, (tts[4:] > tts[:-4]).astype(float))
    out["M5"] = m5
    m7 = np.full(len(W), np.nan)
    for k in range(52, len(W)):
        m7[k] = float(s9_count[k] > np.median(s9_count[k - 52:k]))
    out["M7"] = m7
    return out


def runs(states: np.ndarray, sel: np.ndarray, v: float) -> int:
    """sel 期間內，狀態 v 連續出現了幾段。"""
    n, prev = 0, False
    for x, ok in zip(states, sel):
        cur = bool(ok and x == v)
        if cur and not prev:
            n += 1
        prev = cur
    return n


def by_state(T, wk_state: np.ndarray, wd: np.ndarray, a: str, b: str, mask: np.ndarray | None = None,
             lab: str = "B") -> dict:
    """各狀態：週數、出現段數、名單（或 mask）股票週的命中率。T＝layer.Tab。"""
    sel = (wd >= a) & (wd <= b)
    row_state = wk_state[T.k]
    m = np.ones(len(T.d), dtype=bool) if mask is None else mask
    out = {}
    for v in sorted({x for x in wk_state[sel] if x == x}):
        rs = m & (row_state == v) & T.per(a, b)
        y = T.y[lab][rs]
        y = y[~np.isnan(y)]
        out[int(v)] = {"weeks": int((sel & (wk_state == v)).sum()), "runs": runs(wk_state, sel, v),
                       "n": int(rs.sum()), "p": float(y.mean()) if len(y) else None}
    return out


def base_by_state(tb: dict, wk_state: np.ndarray, a: str, b: str, lab: str = "B") -> dict:
    """全部合格股票在各狀態下的命中率（週加總）。"""
    wd = np.array(tb["dates"])
    sel = (wd >= a) & (wd <= b)
    pos, n = np.array(tb["base"][lab]["pos"]), np.array(tb["base"][lab]["n"])
    out = {}
    for v in sorted({x for x in wk_state[sel] if x == x}):
        s = sel & (wk_state == v)
        out[int(v)] = float(pos[s].sum() / n[s].sum()) if n[s].sum() else None
    return out


def spread(st: dict, min_weeks: int) -> tuple[int, int, float] | None:
    """週數夠的狀態裡命中率最高 ÷ 最低 → (最高狀態, 最低狀態, 差距)。"""
    ok = {v: x for v, x in st.items() if x["weeks"] >= min_weeks and x["p"] is not None}
    if len(ok) < 2:
        return None
    hi = max(ok, key=lambda v: ok[v]["p"])
    lo = min(ok, key=lambda v: ok[v]["p"])
    return (hi, lo, ok[hi]["p"] / ok[lo]["p"]) if ok[lo]["p"] > 0 else (hi, lo, float("inf"))


def stable(full: dict, halves: list[dict]) -> tuple[bool, tuple | None]:
    """W4_plan 第 3 節：2014–2019 的最高、最低狀態，在兩個子期間都是最高、最低（各 ≥ 13 週），差距都 ≥ 1.3。"""
    sp = spread(full, WEEKS_MIN)
    if sp is None:
        return False, None
    hi, lo, _ = sp
    for h in halves:
        if any(h.get(v, {}).get("weeks", 0) < HALF_MIN or h[v]["p"] is None for v in (hi, lo)):
            return False, sp
        shp = spread(h, HALF_MIN)
        if shp is None or shp[0] != hi or shp[1] != lo or shp[2] < RATIO:
            return False, sp
    return True, sp
