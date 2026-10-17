"""景氣溫度頁的計算核心（docs/lab_heat_plan.md 第 4、5 節；規格在 heatspec.py）。

純函式、不碰網路：
  · 百分位：今天的值在「今天以前」的視窗裡的位置（同值算一半），只用過去的資料。
  · 熱度：依熱的方向轉成 0～100。
  · 總分與細項影響：算進總分的指標等權平均；每項影響＝（熱度 − 50）÷ 有值的項數，加起來＋50＝總分。
  · 驗證：之後漲跌（t＋1 收盤起算）、期間最大跌幅、五段統計、等級相關＋移動區塊重抽信賴區間、判定、納入規則。
"""
from __future__ import annotations

import bisect
import math
import random
import statistics

from . import heatspec as S


# ── 百分位與熱度 ─────────────────────────────────────────────────────

def pct_rank(xs: list, i: int, win: int, min_n: int) -> float | None:
    """xs[i] 在 xs[i−win : i]（不含今天）有值者中的百分位（0～100；同值算一半）。歷史不足 min_n 回 None。"""
    x = xs[i]
    if x is None:
        return None
    past = [v for v in xs[max(0, i - win):i] if v is not None]
    if len(past) < min_n:
        return None
    lo = sum(1 for v in past if v < x)
    eq = sum(1 for v in past if v == x)
    return 100.0 * (lo + 0.5 * eq) / len(past)


def pct_series(xs: list, win: int, min_n: int) -> list:
    """整條序列的百分位（排序視窗，O(n log win)），結果和逐點 pct_rank 相同。"""
    out: list = [None] * len(xs)
    window: list = []            # 排序好的過去值
    hist: list = []              # 依時間的過去值（含 None 佔位不放進來）
    for i, x in enumerate(xs):
        if x is not None and len(window) >= min_n:
            lo = bisect.bisect_left(window, x)
            hi = bisect.bisect_right(window, x)
            out[i] = 100.0 * (lo + 0.5 * (hi - lo)) / len(window)
        # 今天的值加進視窗；超出 win 天的舊值移出（以「天」計，含沒有值的日子）
        hist.append(x)
        if x is not None:
            bisect.insort(window, x)
        if len(hist) > win:
            old = hist[-win - 1]
            if old is not None:
                del window[bisect.bisect_left(window, old)]
    return out


def to_heat(p: float | None, hot: int) -> float | None:
    if p is None:
        return None
    return p if hot > 0 else 100.0 - p


# ── 總分與細項影響 ────────────────────────────────────────────────────

def need(n_inc: int) -> int:
    return max(1, math.ceil(S.MIN_AVAIL * n_inc - 1e-9))


def composite(heats: dict, inc: list[str]) -> float | None:
    """算進總分的指標等權平均；有值的項數 ≥ 2/3 才給分數。"""
    v = [heats[k] for k in inc if heats.get(k) is not None]
    if not inc or len(v) < need(len(inc)):
        return None
    return sum(v) / len(v)


def contrib(heats: dict, inc: list[str]) -> dict:
    """每項把總分往熱或冷拉了幾分、佔比（%）。所有影響加起來＋50＝總分。"""
    have = [k for k in inc if heats.get(k) is not None]
    if not inc or len(have) < need(len(inc)):
        return {}
    n = len(have)
    c = {k: (heats[k] - 50.0) / n for k in have}
    tot = sum(abs(x) for x in c.values())
    return {k: {"pull": c[k], "share": (100.0 * abs(c[k]) / tot) if tot else 0.0} for k in have}


# ── 之後漲跌 ─────────────────────────────────────────────────────────

def fwd(px: list, i: int, h: int, lag: int = S.DAILY_LAG) -> tuple[float | None, float | None]:
    """t 日訊號 → (t＋lag 收盤到 t＋lag＋h 收盤的漲跌, 期間最大跌幅)。資料不夠回 (None, None)。"""
    a = i + lag
    b = a + h
    if b >= len(px) or px[a] is None or px[b] is None:
        return None, None
    p0 = px[a]
    lows = [p for p in px[a + 1:b + 1] if p is not None]
    return px[b] / p0 - 1.0, (min(lows) / p0 - 1.0 if lows else None)


# ── 統計 ─────────────────────────────────────────────────────────────

def _rank(xs: list) -> list[float]:
    o = sorted(range(len(xs)), key=lambda k: xs[k])
    r = [0.0] * len(xs)
    j = 0
    while j < len(o):
        k = j
        while k + 1 < len(o) and xs[o[k + 1]] == xs[o[j]]:
            k += 1
        for m in range(j, k + 1):
            r[o[m]] = (j + k) / 2
        j = k + 1
    return r


def _pearson(a: list, b: list) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if not sa or not sb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def spearman_ci(x: list, y: list, block: int, n_boot: int = S.BOOT_N, seed: int = S.BOOT_SEED,
                ci: float = S.CI) -> tuple[float | None, float | None, float | None]:
    """等級相關（樣本內排名後的 Pearson）＋移動區塊重抽信賴區間（區塊長＝持有天數；固定種子）。"""
    n = len(x)
    if n < max(30, 2 * block):
        return None, None, None
    rx, ry = _rank(x), _rank(y)
    rho = _pearson(rx, ry)
    rnd = random.Random(seed)
    L = max(1, block)
    starts = n - L + 1
    reps = []
    for _ in range(n_boot):
        bx: list = []
        by: list = []
        while len(bx) < n:
            s = rnd.randrange(starts)
            bx.extend(rx[s:s + L])
            by.extend(ry[s:s + L])
        r = _pearson(bx[:n], by[:n])
        if r is not None:
            reps.append(r)
    if len(reps) < n_boot // 2:
        return rho, None, None
    reps.sort()
    a = (1 - ci) / 2
    return rho, reps[int(a * len(reps))], reps[min(len(reps) - 1, int((1 - a) * len(reps)))]


def bands(scores: list, rets: list, dds: list) -> list[dict]:
    """五段：天數、之後平均漲跌、中位數、上漲機率、期間最大跌幅中位數（%）；最後一列＝所有日子。"""
    out = []
    groups = [(lo, hi, nm) for lo, hi, nm in S.BANDS] + [(None, None, "全部")]
    for lo, hi, nm in groups:
        idx = [k for k, s in enumerate(scores) if s is not None and rets[k] is not None
               and (lo is None or lo <= s < hi)]
        r = [rets[k] for k in idx]
        d = [dds[k] for k in idx if dds[k] is not None]
        out.append({"band": nm, "n": len(r),
                    "avg": round(100 * statistics.mean(r), 2) if r else None,
                    "med": round(100 * statistics.median(r), 2) if r else None,
                    "up": round(100 * sum(1 for v in r if v > 0) / len(r), 1) if r else None,
                    "dd": round(100 * statistics.median(d), 2) if d else None})
    return out


def verdict(is_rho: float | None, is_lo: float | None, is_hi: float | None, oos_rho: float | None,
            n_is: int, n_oos: int, min_is: int, min_oos: int) -> str:
    """判定（第 5 節）：weak＝熱了之後較弱、strong＝較強、flip＝方向不穩、none＝看不出關係、few＝樣本不足。"""
    if n_is < min_is or n_oos < min_oos or is_rho is None or is_lo is None or is_hi is None:
        return "few"
    if is_hi < 0:
        return "weak" if (oos_rho is not None and oos_rho < 0) else "flip"
    if is_lo > 0:
        return "strong" if (oos_rho is not None and oos_rho > 0) else "flip"
    return "none"


def is_dir(is_lo: float | None, is_hi: float | None) -> int:
    """樣本內有沒有關係、方向（−1＝熱了之後較弱、＋1＝較強、0＝看不出或樣本不足）。"""
    if is_lo is None or is_hi is None:
        return 0
    if is_hi < 0:
        return -1
    if is_lo > 0:
        return 1
    return 0


def select(dirs: dict[str, int]) -> tuple[int, list[str]]:
    """納入總分（第 4 節第 3 點，只看樣本內）：有關係的指標以多數方向為準（一樣多取「熱了之後較弱」），同方向的才算。
    → (該線方向, 算進去的指標)。一個都沒有 → (0, [])。"""
    pos = sorted(k for k, d in dirs.items() if d > 0)
    neg = sorted(k for k, d in dirs.items() if d < 0)
    if not pos and not neg:
        return 0, []
    if len(pos) > len(neg):
        return 1, pos
    if len(neg) > len(pos):
        return -1, neg
    return S.TIE_DIR, (neg if S.TIE_DIR < 0 else pos)
