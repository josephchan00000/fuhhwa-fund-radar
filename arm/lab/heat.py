"""景氣溫度頁的計算核心（docs/lab_heat_plan.md 第 4、12 節；規格在 heatspec.py）。

純函式、不碰網路：
  · 百分位：今天的值在「今天以前」的視窗裡的位置（同值算一半），只用過去的資料。
  · 熱度：依熱的方向轉成 0～100。
  · 面向總分與細項影響：該面向的項目等權平均；每項影響＝（熱度 − 50）÷ 有值的項數，加起來＋50＝總分。
  · 驗證：之後漲跌（t＋1 收盤起算）、期間最大跌幅、五段統計、等級相關＋移動區塊重抽信賴區間、前後兩半、判定。
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


_MDD: dict = {}


def _mdd_all(px: list, h: int, lag: int) -> list:
    out: list = [None] * len(px)
    n = len(px)
    for i in range(n):
        a = i + lag
        b = a + h
        if b >= n or px[a] is None or px[b] is None:
            continue
        pk, dd = None, 0.0
        for p in px[a:b + 1]:
            if p is None:
                continue
            if pk is None or p > pk:
                pk = p
            elif 1.0 - p / pk > dd:
                dd = 1.0 - p / pk
        out[i] = dd
    return out


def fwd_mdd(px: list, i: int, h: int, lag: int = S.DAILY_LAG) -> float | None:
    """t 日訊號 → 第 t＋lag～t＋lag＋h 天收盤的最大回撤（期間最高收盤到之後最低收盤，0～1；sigspec VER 24 的「最大跌幅」，
    和訊號總覽的大跌同一個算法）。資料不夠回 None。同一條價格整條算一次存起來（研究要對很多項目、很多個樣本日查）。"""
    key = (id(px), len(px), h, lag)
    c = _MDD.get(key)
    if c is None or c[0] is not px:
        c = _MDD[key] = (px, _mdd_all(px, h, lag))
    return c[1][i] if 0 <= i < len(c[1]) else None


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


def bands(scores: list, rets: list, dds: list, mdds: list | None = None, dates: list | None = None) -> list[dict]:
    """五段：天數、之後平均漲跌、中位數、上漲機率、期間最大跌幅中位數（%，從進場價算；頁面 VER 24 起不列）；最後一列＝所有日子。
    mdds＝每個樣本的最大回撤（fwd_mdd，0～1）→ 另記 ddw＝最差一次（%，負數）、ddwd＝那一次的日期（dates；sigspec VER 24 的「最大跌幅」）。"""
    out = []
    groups = [(lo, hi, nm) for lo, hi, nm in S.BANDS] + [(None, None, "全部")]
    for lo, hi, nm in groups:
        idx = [k for k, s in enumerate(scores) if s is not None and rets[k] is not None
               and (lo is None or lo <= s < hi)]
        r = [rets[k] for k in idx]
        d = [dds[k] for k in idx if dds[k] is not None]
        b = {"band": nm, "n": len(r),
             "avg": round(100 * statistics.mean(r), 2) if r else None,
             "med": round(100 * statistics.median(r), 2) if r else None,
             "up": round(100 * sum(1 for v in r if v > 0) / len(r), 1) if r else None,
             "dd": round(100 * statistics.median(d), 2) if d else None}
        if mdds is not None:
            w = [k for k in idx if mdds[k] is not None]
            if w:
                j = max(w, key=lambda k: (mdds[k], -k))             # 一樣大取最早的那一個
                b["ddw"] = round(-100 * mdds[j], 2)
                b["ddwd"] = dates[j] if dates is not None else None
        out.append(b)
    return out


def spearman(x: list, y: list) -> float | None:
    """等級相關（不算信賴區間；前後兩半用）。"""
    if len(x) < 3:
        return None
    return _pearson(_rank(x), _rank(y))


def verdict(rho: float | None, lo: float | None, hi: float | None, r1: float | None, r2: float | None,
            n: int, min_n: int) -> str:
    """判定（規劃文件第 12.7 節）：few＝樣本不足；weak＝全期間信賴區間上緣 < 0 而且前後兩半的相關都 < 0；
    strong＝下緣 > 0 而且兩半都 > 0；其他 none＝看不出穩定關係。"""
    if n < min_n or None in (rho, lo, hi, r1, r2):
        return "few"
    if hi < 0 and r1 < 0 and r2 < 0:
        return "weak"
    if lo > 0 and r1 > 0 and r2 > 0:
        return "strong"
    return "none"


# ── 日期對齊（第 4 節第 7 點） ─────────────────────────────────────────

def asof_daily(cal: list[str], ser: dict, *, after: bool = False, stale: int = 7) -> list:
    """日資料 → 對齊交易日曆：每個交易日取「當天（after=True 時：當天以前）」最近一筆，超過 stale 個日曆天沒更新就算缺。
    after＝True 用在美國資料：美國 d 日收盤在台灣 d＋1 日早上才看得到，所以台灣 d 日只能用 d 日以前的。"""
    from datetime import date as _d
    ks = sorted(k for k, v in ser.items() if v is not None)
    out: list = [None] * len(cal)
    j = -1
    for i, t in enumerate(cal):
        while j + 1 < len(ks) and (ks[j + 1] < t if after else ks[j + 1] <= t):
            j += 1
        if j >= 0 and (_d.fromisoformat(t) - _d.fromisoformat(ks[j])).days <= stale:
            out[i] = ser[ks[j]]
    return out


def avail_date(ym: str, rel: tuple[int, int]) -> str:
    """月資料 ym（YYYY-MM）在第 ym＋rel[0] 個月的第 rel[1] 天起才算拿得到。"""
    y, m = int(ym[:4]), int(ym[5:7]) + rel[0]
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}-{rel[1]:02d}"


def asof_monthly(dates: list[str], ser: dict, rel: tuple[int, int], late: dict | None = None) -> list:
    """月資料 {YYYY-MM: 值} → 每個日期當下拿得到的最新一個月的值（依公布時間差）。
    late＝{月: 那一期實際拿得到的日子}（heatspec VER 11：補出來的月份、已知延後公布；和公布時間差取晚的）。"""
    late = late or {}
    av = sorted((max(avail_date(ym, rel), late.get(ym, "")), ym) for ym, v in ser.items() if v is not None)
    out: list = [None] * len(dates)
    j = -1
    for i, t in enumerate(dates):
        while j + 1 < len(av) and av[j + 1][0] <= t:
            j += 1
        if j >= 0:
            out[i] = ser[av[j][1]]
    return out


def _ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def _ym_diff(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def fill_gaps(ser: dict, maxgap: int, geo: bool = False) -> dict:
    """月資料 {YYYY-MM: 值} 連續缺 ≤ maxgap 個月時，用前後兩個月內插（heatspec VER 10、heatspec_us VER 2）：
    geo＝幾何內插（CPI 這類指數；只缺一個月＝前後兩個月的幾何平均），否則算術內插（只缺一個月＝前後兩個月平均）。
    只補前後都有值的缺口；值是 None 的當成缺。"""
    ks = sorted(k for k, v in ser.items() if v is not None)
    out = {k: ser[k] for k in ks}
    for a, b in zip(ks, ks[1:]):
        gap = _ym_diff(a, b) - 1
        if not 1 <= gap <= maxgap:
            continue
        va, vb = ser[a], ser[b]
        for j in range(1, gap + 1):
            w = j / (gap + 1)
            if geo and va > 0 and vb > 0:
                out[_ym_add(a, j)] = va * (vb / va) ** w
            else:
                out[_ym_add(a, j)] = va + (vb - va) * w
    return dict(sorted(out.items()))


def gap_dates(raw: dict, rel: tuple[int, int], known: dict, maxgap: int) -> dict:
    """heatspec VER 11：fill_gaps 補出來的月份（前後都有值、連續缺 ≤ maxgap）→ {月: 拿得到的日子}＝缺口後第一個有值的月份
    拿得到的日子（補值用到它；known＝它的實際公布日，和公布時間差取晚的）。raw＝補之前的月資料。"""
    out = {}
    ks = sorted(k for k, v in raw.items() if v is not None)
    for a, b in zip(ks, ks[1:]):
        gap = _ym_diff(a, b) - 1
        if 1 <= gap <= maxgap:
            d = max(avail_date(b, rel), known.get(b, ""))
            for j in range(1, gap + 1):
                out[_ym_add(a, j)] = d
    return out


def late_dates(raw: dict, rel: tuple[int, int], known: dict, maxgap: int) -> dict:
    """heatspec VER 11：和公布時間差不同的「實際拿得到的日子」→ {月: YYYY-MM-DD}：已知延後公布（known）＋補出來的月份（gap_dates）。"""
    return {**known, **gap_dates(raw, rel, known, maxgap)}


def stale_info(months: list[str], rel: tuple[int, int], today: str) -> tuple[str | None, list[str]]:
    """月資料過期（heatspec VER 10）：有值的月份 → (最後一期, 照這一項過去的間隔應該已經拿得到、卻還沒有的期)。
    間隔＝最近 12 期相鄰兩期相差月數的中位數（月資料 1、季資料 3）；第 last＋間隔、last＋2×間隔…裡公布日 ≤ today 的都算缺。"""
    ks = sorted(months)
    if not ks:
        return None, []
    tail = ks[-13:]
    gaps = sorted(_ym_diff(a, b) for a, b in zip(tail, tail[1:]))
    step = max(1, gaps[len(gaps) // 2]) if gaps else 1
    due, m = [], _ym_add(ks[-1], step)
    while avail_date(m, rel) <= today and len(due) < 120:
        due.append(m)
        m = _ym_add(m, step)
    return ks[-1], due


def chg(xs: list, k: int, pct: bool = True) -> list:
    """和 k 期前比：變化率（%）或差。"""
    out: list = [None] * len(xs)
    for i in range(k, len(xs)):
        a, b = xs[i], xs[i - k]
        if a is None or b is None:
            continue
        if pct:
            out[i] = 100.0 * (a / b - 1.0) if b else None
        else:
            out[i] = a - b
    return out


def roll_sum(xs: list, k: int, min_n: int | None = None) -> list:
    out: list = [None] * len(xs)
    min_n = k if min_n is None else min_n
    for i in range(k - 1, len(xs)):
        w = [v for v in xs[i - k + 1:i + 1] if v is not None]
        if len(w) >= min_n:
            out[i] = sum(w)
    return out


def roll_mean(xs: list, k: int, min_n: int | None = None) -> list:
    out: list = [None] * len(xs)
    min_n = k if min_n is None else min_n
    for i in range(k - 1, len(xs)):
        w = [v for v in xs[i - k + 1:i + 1] if v is not None]
        if len(w) >= min_n:
            out[i] = sum(w) / len(w)
    return out


def rsi(px: list, k: int = 14) -> list:
    """Wilder RSI：第一個值用前 k 天漲跌的簡單平均，之後「前值 ×（k − 1）＋今天」÷ k；平均跌＝0 時 100。
    某天或前一天沒有價格 → 那天 None、平均不更新。"""
    out: list = [None] * len(px)
    ag = al = None
    first: list = []
    for i in range(1, len(px)):
        if px[i] is None or px[i - 1] is None:
            continue
        d = px[i] - px[i - 1]
        g, l_ = max(d, 0.0), max(-d, 0.0)
        if ag is None:
            first.append((g, l_))
            if len(first) < k:
                continue
            ag = sum(a for a, _ in first) / k
            al = sum(b for _, b in first) / k
        else:
            ag = (ag * (k - 1) + g) / k
            al = (al * (k - 1) + l_) / k
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def roll_std_ret(px: list, k: int) -> list:
    """日報酬 k 日標準差（年化，%）。"""
    r: list = [None] * len(px)
    for i in range(1, len(px)):
        if px[i] and px[i - 1]:
            r[i] = px[i] / px[i - 1] - 1.0
    out: list = [None] * len(px)
    for i in range(k, len(px)):
        w = [v for v in r[i - k + 1:i + 1] if v is not None]
        if len(w) >= k - 2:
            out[i] = 100.0 * statistics.pstdev(w) * math.sqrt(250)
    return out
