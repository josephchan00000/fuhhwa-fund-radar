"""打亂日子測試（sigspec 第 3.5 節，VER 9；docs/lab_noise_plan.md 第 10 節）。

「隨便亂排做得到一樣準嗎」：把訊號出現的日子整段循環平移 LUCK_DRAWS 次（保留訊號自己出現的節奏與長度，只打斷和之後漲跌的對應），
看平移後命中率 ≥ 實際命中率的比例。和 sigcat.ev_stat／st_stat 同一套計次與命中率（tests/test_sigluck.py 逐一比對）。

  Shift          一個市場層級訊號的平移計算（事件型、狀態型）
  market_p(...)  一個市場層級訊號 → 偏多、警示的 p（＋運氣會產生的 ★、◆ 期望個數；VER 17 起 p 也只呈現）
  sign_p(b, c)   兩兩成對（大跌後買點、個股偏多）：單尾精確符號檢定
  shift_p(...)   通用：給「第 j 次平移的命中率」函式 → p
"""
from __future__ import annotations

import math
import zlib

import numpy as np

from . import sigspec as S


def rng_for(key: str) -> np.random.Generator:
    """每個訊號自己的亂數（種子＝(LUCK_SEED, 代號的 CRC32)），和計算順序無關。"""
    return np.random.default_rng([S.LUCK_SEED, zlib.crc32(key.encode("utf-8"))])


def offsets(rng: np.random.Generator, L: int, D: int = S.LUCK_DRAWS) -> np.ndarray:
    """平移量：[⌊LUCK_SHIFT[0] × L⌋, ⌊LUCK_SHIFT[1] × L⌋) 均勻隨機。"""
    lo = int(S.LUCK_SHIFT[0] * L)
    hi = max(lo + 1, int(S.LUCK_SHIFT[1] * L))
    return rng.integers(lo, hi, size=D)


def p_of(hits: np.ndarray, actual: float | None) -> float | None:
    """p＝（1 ＋ 平移後命中率 ≥ 實際的次數）÷（1 ＋ 平移次數）；平移後沒有任何一次（nan）的不算 ≥。"""
    if actual is None:
        return None
    v = hits[~np.isnan(hits)]
    return float((1 + int(np.sum(v >= actual - 1e-12))) / (1 + len(hits)))


def loo_p(hits: np.ndarray) -> np.ndarray:
    """每一次平移相對其他平移的 p：（1 ＋ 其他平移 ≥ 這一次的次數）÷ 平移次數（＝含自己 ≥ 的次數 ÷ 平移次數）。nan → 1。"""
    D = len(hits)
    v = np.where(np.isnan(hits), -np.inf, hits)
    srt = np.sort(v)
    ge = D - np.searchsorted(srt, v - 1e-12, side="left")
    return np.where(np.isnan(hits), 1.0, ge / D)


def sign_p(b: int, c: int) -> float:
    """兩兩成對：只有訊號中了 b 次、只有對照中了 c 次 → P(X ≥ b)，X ~ 二項(b＋c, 1/2)；b＋c＝0 → 1。"""
    n = b + c
    if n == 0:
        return 1.0
    return float(sum(math.comb(n, k) for k in range(b, n + 1)) / 2 ** n)


class Shift:
    """一個市場層級訊號（sigcat.signals 的 sd）。occ(o)＝平移 o 個樣本後的（每一次的第一天、偏多結果、警示結果、天數）：
    事件型每一次一天；狀態型每一段＝段內平均與窗口完整的天數（VER 22：命中率＝每一天一樣重＝依天數加權）。"""

    def __init__(self, sd: dict, Yu: np.ndarray, Yw: np.ndarray):
        self.kind, self.H = sd["kind"], sd["H"]
        self.samp = np.asarray(sd["samp"], dtype=np.int64)
        self.L = len(self.samp)
        self.yu, self.yw = Yu[self.samp], Yw[self.samp]
        self.valid = ~np.isnan(self.yu) & ~np.isnan(self.yw)
        if self.kind == "event":
            pos = {int(t): i for i, t in enumerate(self.samp)}
            self.P = np.array(sorted(pos[int(t)] for t in sd["days"] if int(t) in pos), dtype=np.int64)
        else:
            self.st = np.asarray(sd["state"], dtype=bool)
            self.gap = 1 if sd.get("monthly") else S.EP_GAP
            b = sd.get("brk")                              # VER 20：相反的極端跟著狀態一起平移
            self.brk = None if b is None else np.asarray(b, dtype=bool)

    def occ(self, o: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        empty = (np.zeros(0, dtype=np.int64), np.zeros(0), np.zeros(0), np.zeros(0))
        if self.L == 0:
            return empty
        if self.kind == "event":
            if not len(self.P):
                return empty
            Q = np.sort((self.P + o) % self.L)
            days = self.samp[Q]
            kept, last = [], None
            for q, t in zip(Q.tolist(), days.tolist()):     # 同 sigcat.dedupe：H 個交易日內再出現不算新的一次
                if last is not None and t - last <= self.H:
                    continue
                kept.append(q)
                last = t
            kp = np.array(kept, dtype=np.int64)
            kp = kp[self.valid[kp]]
            return self.samp[kp], self.yu[kp], self.yw[kp], np.ones(len(kp))
        st = np.roll(self.st, o) if o else self.st
        pos = np.nonzero(st)[0]
        if not len(pos):
            return empty
        cut = np.diff(pos) - 1 >= self.gap
        if self.brk is not None:                           # 中斷的樣本裡有相反的極端＝新的一段（同 sigcat.episodes）
            br = np.roll(self.brk, o) if o else self.brk
            cb = np.concatenate([[0], np.cumsum(br.astype(np.int64))])
            cut = cut | (cb[pos[1:]] - cb[pos[:-1] + 1] > 0)
        starts = np.concatenate([[0], np.nonzero(cut)[0] + 1]).astype(np.int64)
        v = self.valid[pos]
        cnt = np.add.reduceat(v.astype(np.int64), starts)
        su = np.add.reduceat(np.where(v, self.yu[pos], 0.0), starts)
        sw = np.add.reduceat(np.where(v, self.yw[pos], 0.0), starts)
        ok = cnt > 0
        return self.samp[pos[starts[ok]]], su[ok] / cnt[ok], sw[ok] / cnt[ok], cnt[ok].astype(float)


def _summ(first, u, w, cnt, r0) -> dict:
    """→ {方向: (次數, 命中率, 近 10 年次數, 近 10 年命中率)}；命中率依天數加權（VER 22：每一天一樣重；事件型天數都是 1）。"""
    m10 = first >= r0
    out = {}
    for d, y in (("up", u), ("warn", w)):
        out[d] = (len(y), float((y * cnt).sum() / cnt.sum()) if len(y) else None, int(m10.sum()),
                  float((y[m10] * cnt[m10]).sum() / cnt[m10].sum()) if m10.any() else None)
    return out


def passes(n, hit, base, n10, hit10, base10, d: str, recent: bool = True) -> bool:
    """過門檻（sigspec 第 3 節）。"""
    if not n or n < S.N_MIN or hit is None or base is None:
        return False
    if hit < S.HIT_MIN[d] or hit - base < S.EDGE_GOOD:
        return False
    if recent and (n10 or 0) >= S.RECENT_N:
        return hit10 is not None and base10 is not None and hit10 >= S.HIT_MIN[d] and hit10 - base10 >= S.EDGE_GOOD
    return True


def passes_win(n, hit, base, n10, hit10, base10, d: str) -> bool:
    """VER 17（sigspec 第 3.5 節）：運氣個數用的判定＝第 3 節新判定的命中率部分（報酬兩條沒有算）。"""
    if not n or n < S.N_MIN or hit is None or base is None:
        return False
    hm = S.HIT_MIN[d]
    if hit < hm or hit < base:
        return False
    if (n10 or 0) >= S.RECENT_N:
        return hit10 is not None and base10 is not None and hit10 >= hm and hit10 >= base10
    return True


def market_p(sd: dict, Yu: np.ndarray, Yw: np.ndarray, r0: int, R: dict, draws: int = S.LUCK_DRAWS) -> dict:
    """一個市場層級訊號 → {方向: {"p": p, "luck": 運氣會產生 ★ 的機率, "luck_rare": 運氣會產生 ◆ 的機率}}
    （把每一次平移當成真的、用 VER 17 判定的命中率部分：平移後次數 ≥ STAR_N 算 ★、N_MIN～STAR_N − 1 算 ◆）。
    R＝sigcat.ev_stat／st_stat 的實際結果（用它的命中率與平常，確保和判定同一組數字）。p 只呈現（VER 17）。"""
    sh = Shift(sd, Yu, Yw)
    out = {d: {"p": None, "luck": 0.0, "luck_rare": 0.0} for d in ("up", "warn")}
    if sh.L == 0:
        return out
    rows = [_summ(*sh.occ(int(o)), r0) for o in offsets(rng_for(sd["id"]), sh.L, draws)]
    for d in ("up", "warn"):
        st = R[d]
        hits = np.array([np.nan if x[d][1] is None else x[d][1] for x in rows])
        out[d]["p"] = p_of(hits, st.get("hit"))
        b, b10 = st.get("base"), st.get("base10")
        c = cr = 0
        for x in rows:
            n, h, n10, h10 = x[d]
            if passes_win(n, h, b, n10, h10, b10, d):
                if n >= S.STAR_N:
                    c += 1
                else:
                    cr += 1
        out[d]["luck"] = c / draws
        out[d]["luck_rare"] = cr / draws
    return out


def shift_p(actual: float | None, hit_of, L: int, key: str, draws: int = S.LUCK_DRAWS) -> float | None:
    """通用：hit_of(o)＝平移 o 之後的命中率（沒有任何一次＝None）→ p。L＝平移範圍的長度。"""
    if actual is None or L <= 1:
        return None
    hits = np.array([np.nan if (h := hit_of(int(o))) is None else h for o in offsets(rng_for(key), L, draws)])
    return p_of(hits, actual)


def _ep_hits(flag: np.ndarray, y: np.ndarray, gap: int = 1) -> list[float]:
    """一個序列：flag 為真、y 有值的每一個月（VER 22：每一個月一樣重；VER 9～21 是每一段的平均）。"""
    v = y[np.nonzero(flag)[0]]
    return v[~np.isnan(v)].tolist()


def ind_p(key: str, seqs: list[tuple[np.ndarray, np.ndarray, np.ndarray]], actual: dict,
          draws: int = S.LUCK_DRAWS) -> dict:
    """產業泡沫（sigspec 第 3.5 節）：seqs＝每個產業（狀態, 偏多結果, 警示結果）的月份序列（結果沒有值＝nan）；
    每次平移各產業 ⌊u × 月數⌋（u 共用）→ 合併各段的命中率。actual＝{方向: 實際命中率}（None＝不算）→ {方向: p}。"""
    out = {d: None for d in ("up", "warn")}
    if not any(actual.get(d) is not None for d in out):
        return out
    us = rng_for(key).uniform(S.LUCK_SHIFT[0], S.LUCK_SHIFT[1], size=draws)
    hits = {d: [] for d in out}
    for u in us:
        eu, ew = [], []
        for fl, yu, yw in seqs:
            f = np.roll(fl, int(u * len(fl)))
            eu += _ep_hits(f, yu)
            ew += _ep_hits(f, yw)
        hits["up"].append(float(np.mean(eu)) if eu else np.nan)
        hits["warn"].append(float(np.mean(ew)) if ew else np.nan)
    for d in out:
        if actual.get(d) is not None:
            out[d] = p_of(np.array(hits[d]), actual[d])
    return out


def stock_hit(fired: dict, hit: dict, t0: int, L: int, dedup: int, o: int = 0) -> float | None:
    """個股警示：fired＝{代號: 訊號日（遞增）}、hit＝{代號: 第 t0 天起每一天中了沒有（1／0／nan＝窗口不完整）}；
    每一檔的訊號日在 [t0, t0＋L) 裡一起平移 o（超過尾端從頭接），同 sigcat.stock_signal_rows 去重（一檔 dedup 日內再出現不算，
    「上一次」含被略過的那一天），再取窗口完整的平均。"""
    ys = []
    for code, ds in fired.items():
        h = hit[code]
        sh = sorted(t0 + (t - t0 + o) % L for t in ds if t0 <= t < t0 + L)
        last = -10 ** 9
        for t in sh:
            if t - last <= dedup:
                last = t
                continue
            last = t
            v = h[t - t0]
            if not np.isnan(v):
                ys.append(v)
    return float(np.mean(ys)) if ys else None
