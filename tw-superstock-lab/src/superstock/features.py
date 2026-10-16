"""特徵（SPEC §5.3 裡 S01 SEPA 用到的部分）與標籤（§5.1）。

決策只用 t 日收盤（含）以前的資料；標籤是唯一用到未來的東西，只拿來算命中率。
細節的解讀寫在 reports/P4_S01_plan.md（跑結果之前寫定）。
"""

from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from .engine import Market

NAN = float("nan")

# SPEC §5.3 VCP（使用者核定）：轉折門檻 3%、基底起點＝近 260 日最高點且至少 30 日前、2～6 段、
# 每段 < 前一段 × 1.1、第一段 ≤ 35%、最後一段 ≤ 10%、收盤 ≥ 樞紐 × 0.9、量縮（10 日 ÷ 50 日均量）≤ 0.7
VCP = {"thr": 0.03, "win": 260, "base_min": 30, "n_min": 2, "n_max": 6, "grow": 1.1, "d1_max": 0.35,
       "dn_max": 0.10, "near": 0.9, "dry": 0.7, "atr_k": None}
# v2（reports/P4_S01_plan.md 第 9 節，2026-10-16）：v1 的固定 3% 轉折對台股太細——樣板全過、基底 ≥30 日的日子裡
# 88% 被切成超過 6 段，VCP 幾乎不成立（9 年 26 筆交易）。只改轉折門檻＝max(3%, 1.5 × ATR14 ÷ 收盤)，
# 1.5 倍 ATR 取自 GitHub 最多人用的 VCP 篩選器（tradermonty/claude-trading-skills vcp-screener）；其餘條件不動。
VCP_V2 = {**VCP, "atr_k": 1.5}
# v3（reports/W5_plan.md 第 3 節，2026-10-16，跑結果之前寫定）：照書修正——每段嚴格比前一段小、低點逐段墊高、
# 最後一段低點在基底上半部、成形只算還沒突破；V3s 另把基底下限改 15 日（3 週）。
VCP_V3 = {**VCP_V2, "grow": 1.0, "rise": True, "upper": 0.5, "below": True}
VCP_V3S = {**VCP_V3, "base_min": 15}


# ---------------------------------------------------------------------------------------------- 合格
def eligible(m: Market, cap: np.ndarray | None = None, cap_min: float = 40e8, val_min: float = 1e7,
             age_min: int = 60, gap_max: int = 10) -> np.ndarray:
    """SPEC §5.1：當天有交易、20 日成交值中位數 ≥ 1,000 萬、上市滿 60 個交易日、前 60 日沒有超過 10 天的連續停牌；
    lab 面板另加最近月底市值 ≥ cap_min（見 labpanel）。"""
    has = ~np.isnan(m.c)
    med = pd.DataFrame(m.val).rolling(20, min_periods=10).median().to_numpy()
    age = np.cumsum(has, axis=0)
    run = np.zeros(has.shape, dtype=np.int32)
    for i in range(1, has.shape[0]):
        run[i] = np.where(has[i], 0, run[i - 1] + 1)
    gap60 = pd.DataFrame(run).rolling(60, min_periods=1).max().to_numpy()
    with np.errstate(invalid="ignore"):
        ok = has & (med >= val_min) & (age >= age_min) & (gap60 <= gap_max)
        if cap is not None:
            ok &= cap >= cap_min
    return ok


# ---------------------------------------------------------------------------------------------- 趨勢樣板、RS、量
def rs_pct(score: pd.DataFrame, elig: np.ndarray) -> np.ndarray:
    """當天合格股票互相排名 → 1～99（SPEC：0.4·r63＋0.2·r126＋0.2·r189＋0.2·r252 的橫斷面百分位）。"""
    sc = score.where(elig)
    rank = sc.rank(axis=1, method="average")
    n = sc.notna().sum(axis=1)
    rs = (100 * rank).div(n + 1, axis=0).round().clip(1, 99)
    return rs.to_numpy(dtype=float)


def trend(m: Market, elig: np.ndarray) -> dict[str, np.ndarray]:
    """趨勢樣板 8 條（SPEC §5.3）：收盤 > MA150 且 > MA200；MA150 > MA200；MA200 比 20 日前高；MA50 > MA150 且 > MA200；
    收盤 > MA50；收盤 ≥ 52 週低 × 1.3；收盤 ≥ 52 週高 × 0.75；RS ≥ 70。52 週高低用日最高／最低（252 日、含當天）。"""
    c = pd.DataFrame(m.c_ff)
    ma50, ma150, ma200 = (c.rolling(w, min_periods=w).mean() for w in (50, 150, 200))
    ma200p = ma200.shift(20)
    hi = pd.DataFrame(m.h).rolling(252, min_periods=200).max()
    lo = pd.DataFrame(m.l).rolling(252, min_periods=200).min()
    r = {n: c / c.shift(n) - 1 for n in (63, 126, 189, 252)}
    score = 0.4 * r[63] + 0.2 * r[126] + 0.2 * r[189] + 0.2 * r[252]
    rs = rs_pct(score, elig)
    conds = [(c > ma150) & (c > ma200), ma150 > ma200, ma200 > ma200p, (ma50 > ma150) & (ma50 > ma200),
             c > ma50, c >= 1.3 * lo, c >= 0.75 * hi]
    arr = [x.to_numpy(dtype=bool) for x in conds] + [np.nan_to_num(rs, nan=0.0) >= 70]
    cnt = np.sum(arr, axis=0)
    return {"tt_count": cnt, "tt_pass": (cnt == 8) & elig, "rs": rs, "ma50": ma50.to_numpy(),
            "hi52": hi.to_numpy(), "lo52": lo.to_numpy()}


def volume(m: Market) -> dict[str, np.ndarray]:
    v = pd.DataFrame(m.vol)
    v10 = v.rolling(10, min_periods=8).mean()
    v50 = v.rolling(50, min_periods=40).mean()
    return {"vol50": v50.to_numpy(), "dry": (v10 / v50).to_numpy()}


# ---------------------------------------------------------------------------------------------- VCP
class ZigZag:
    """3% 轉折（SPEC §5.3），從基底起點 s（近 260 日最高點）開始一天一天往後推，只用推到的那天（含）以前的資料。
    往上段：創新高就更新候選高點；最低跌破候選高點 × (1−門檻) → 確認高點、改找低點（反之亦然）。
    確認的那一天就是轉折被「看見」的那一天，所以任何一天的狀態都沒有用到未來。"""

    __slots__ = ("h", "l", "thr", "th", "s", "t", "sw", "up", "cv", "ci")

    def __init__(self, h: np.ndarray, l: np.ndarray, s: int, thr: float, th: np.ndarray | None = None):
        """th＝每天的轉折門檻（v2：max(3%, k × ATR14 ÷ 收盤)，用當天以前的資料算）；None＝固定 thr。"""
        self.h, self.l, self.thr, self.th, self.s, self.t = h, l, thr, th, s, s
        self.sw: list[tuple[str, int, float]] = []
        self.up = True
        self.cv, self.ci = float(h[s]), s

    def advance(self, t: int) -> None:
        h, l, th0, th = self.h, self.l, self.thr, self.th
        up, cv, ci, sw = self.up, self.cv, self.ci, self.sw
        for i in range(self.t + 1, t + 1):
            hi, lo = h[i], l[i]
            if hi != hi or lo != lo:
                continue
            thr = th0 if th is None else th[i]
            if up:
                if hi > cv:
                    cv, ci = hi, i
                elif lo <= cv * (1 - thr):
                    sw.append(("H", ci, cv))
                    up, cv, ci = False, lo, i
            else:
                if lo < cv:
                    cv, ci = lo, i
                elif hi >= cv * (1 + thr):
                    sw.append(("L", ci, cv))
                    up, cv, ci = True, hi, i
        self.up, self.cv, self.ci = up, cv, ci
        self.t = max(self.t, t)

    def contractions(self) -> tuple[list[tuple[float, float, int, int]], float]:
        """[(高點, 低點, 高點日, 低點日)]：每個已確認高點配它之後的低點（還在往下的最後一段用目前最低）；
        樞紐＝最後一個已確認高點。基底高點還沒被確認（之後沒跌到 3%）→ 沒有收縮。"""
        sw = self.sw
        pairs = []
        for k in range(0, len(sw), 2):
            _, hi_i, hi_v = sw[k]
            if k + 1 < len(sw):
                _, lo_i, lo_v = sw[k + 1]
            elif not self.up:
                lo_i, lo_v = self.ci, self.cv
            else:
                continue
            pairs.append((hi_v, lo_v, hi_i, lo_i))
        pivot = pairs[-1][0] if pairs else NAN
        return pairs, pivot


def vcp_check(pairs, pivot: float, close: float, dry: float, spec: dict = VCP) -> bool:
    """spec 選用鍵（W5_plan 第 3 節；沒有＝不檢查，V1／V2 結果不變）：rise＝低點逐段墊高；
    upper＝最後一段低點 ≥ 基底最低 ＋ upper ×（基底高點 − 基底最低）；below＝收盤 ≤ 樞紐（還沒突破）。"""
    n = len(pairs)
    if not (spec["n_min"] <= n <= spec["n_max"]) or not (pivot == pivot) or not (close == close):
        return False
    ds = [1 - lo / hi for hi, lo, _, _ in pairs]
    if ds[0] > spec["d1_max"] or ds[-1] > spec["dn_max"]:
        return False
    if any(ds[k] >= spec["grow"] * ds[k - 1] for k in range(1, n)):
        return False
    if spec.get("rise") and any(pairs[k][1] <= pairs[k - 1][1] for k in range(1, n)):
        return False
    if spec.get("upper") is not None:
        lo_min = min(p[1] for p in pairs)
        if pairs[-1][1] < lo_min + spec["upper"] * (pairs[0][0] - lo_min):
            return False
    if spec.get("below") and close > pivot:
        return False
    return close >= spec["near"] * pivot and dry == dry and dry <= spec["dry"]


def atr_thr(m: Market, k: float, floor: float) -> np.ndarray:
    """每天的轉折門檻＝max(floor, k × ATR14 ÷ 收盤)；ATR14＝真實波幅（還原價）14 日平均，只用當天以前的資料。"""
    prev = pd.DataFrame(m.c).ffill().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        tr = np.fmax(m.h, prev) - np.fmin(m.l, prev)
    atr = pd.DataFrame(tr).rolling(14, min_periods=10).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        th = k * atr / pd.DataFrame(m.c).ffill().to_numpy()
    return np.fmax(np.nan_to_num(th, nan=floor), floor)


def vcp(m: Market, need: np.ndarray, dry: np.ndarray, spec: dict = VCP) -> dict[str, np.ndarray]:
    """每檔股票、need 為真的日子：VCP 是否成立與它的樞紐、段數、第一段／最後一段深度、基底天數、最後一段低點。"""
    T, N = m.c.shape
    ok = np.zeros((T, N), dtype=bool)
    pivot, d1, dn, low = (np.full((T, N), np.nan) for _ in range(4))
    nseg = np.zeros((T, N), dtype=np.int8)
    base = np.zeros((T, N), dtype=np.int16)
    win, bmin, thr = spec["win"], spec["base_min"], spec["thr"]
    TH = atr_thr(m, spec["atr_k"], thr) if spec.get("atr_k") else None
    for j in range(N):
        if not need[:, j].any():
            continue
        h, l, c = m.h[:, j], m.l[:, j], m.c[:, j]
        th = None if TH is None else TH[:, j]
        dq: deque = deque()
        zz = None
        nd = need[:, j]
        for t in range(T):
            x = h[t]
            if x == x:
                while dq and h[dq[-1]] < x:
                    dq.pop()
                dq.append(t)
            while dq and dq[0] <= t - win:
                dq.popleft()
            if not dq:
                continue
            s = dq[0]
            if zz is None or zz.s != s:
                zz = ZigZag(h, l, s, thr, th)
            if not nd[t] or t - s < bmin:
                continue
            zz.advance(t)
            pairs, pv = zz.contractions()
            if not pairs:
                continue
            nseg[t, j] = len(pairs)
            pivot[t, j] = pv
            d1[t, j] = 1 - pairs[0][1] / pairs[0][0]
            dn[t, j] = 1 - pairs[-1][1] / pairs[-1][0]
            low[t, j] = pairs[-1][1]
            base[t, j] = t - s
            ok[t, j] = vcp_check(pairs, pv, c[t], dry[t, j], spec)
    return {"ok": ok, "pivot": pivot, "n": nseg, "d1": d1, "dn": dn, "low": low, "base": base}


# ---------------------------------------------------------------------------------------------- 標籤
def race(m: Market, up: float = 0.20, dn: float = 0.08, n: int = 120,
         elig: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """交易命中（W5_plan 第 4 節）：之後 n 個交易日內先碰到收盤 ×（1＋up）→ 1，先碰到 ×（1−dn）或同一天兩個都碰到 → 0；
    n 日都沒碰到 → 0（另回傳這些格子）；n 日還沒走完又沒碰到 → NaN。"""
    T, N = m.c.shape
    c = m.c
    tgt, stp = c * (1 + up), c * (1 - dn)
    res = np.full((T, N), np.nan)
    done = np.zeros((T, N), dtype=bool)
    with np.errstate(invalid="ignore"):
        for k in range(1, n + 1):
            hk = np.full((T, N), np.nan)
            lk = np.full((T, N), np.nan)
            hk[:T - k], lk[:T - k] = m.h[k:], m.l[k:]
            down, upx = (lk <= stp) & ~done, (hk >= tgt) & ~done
            res[down] = 0.0
            res[upx & ~down] = 1.0
            done |= down | upx
    tail = (np.arange(T)[:, None] + n) > T - 1
    und = ~done & ~tail
    res[und] = 0.0
    res[np.isnan(c)] = np.nan
    if elig is not None:
        res[~elig] = np.nan
    return res, und & ~np.isnan(res)


def fwd_max(m: Market, n: int) -> np.ndarray:
    """t+1..t+n 的最高價（還原）；面板尾端未來還沒發生 → NaN；已下市股用到下市為止。"""
    H = pd.DataFrame(m.h)
    out = H[::-1].rolling(n, min_periods=1).max()[::-1].shift(-1).to_numpy(copy=True)
    out[max(0, m.n - n):] = np.nan
    return out


def label(m: Market, n: int, g: float, elig: np.ndarray | None = None) -> np.ndarray:
    """SPEC §5.1：之後 n 個交易日內最高價 ÷ 今天收盤 − 1 ≥ g → 1，否則 0；不合格或未知 → NaN。"""
    fm = fwd_max(m, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        y = np.where(np.isnan(fm) | np.isnan(m.c), np.nan, (fm / m.c - 1 >= g).astype(float))
    if elig is not None:
        y = np.where(elig, y, np.nan)
    return y


def compute(m: Market, cap: np.ndarray | None = None, vcp_spec: dict = VCP) -> dict[str, np.ndarray]:
    """S01 需要的全部特徵（一次算好）。"""
    el = eligible(m, cap)
    tr = trend(m, el)
    vo = volume(m)
    vc = vcp(m, el, vo["dry"], vcp_spec)
    return {"elig": el, **tr, **vo, **{f"vcp_{k}": v for k, v in vc.items()}}
