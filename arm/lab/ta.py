"""技術指標純函式（輸入皆為與交易日曆對齊的 list，缺值為 None）。

慣例：回傳與輸入等長的 list；資料不足處為 None。只在「有收盤價」的日子計算，
停牌日（None）沿用前值不推進指標，避免停牌把均線拉歪。
"""
from __future__ import annotations


def _clean(xs):
    """去掉 None，回傳 (值序列, 對應原索引)。"""
    vals, idx = [], []
    for i, x in enumerate(xs):
        if x is not None:
            vals.append(float(x))
            idx.append(i)
    return vals, idx


def _spread(n: int, idx: list[int], vals: list) -> list:
    out = [None] * n
    for i, v in zip(idx, vals):
        out[i] = v
    return out


def sma(xs: list, n: int) -> list:
    vals, idx = _clean(xs)
    out, s = [], 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        out.append(s / n if i >= n - 1 else None)
    return _spread(len(xs), idx, out)


def ema_vals(vals: list[float], n: int) -> list:
    k = 2 / (n + 1)
    out, e = [], None
    for i, v in enumerate(vals):
        if i < n - 1:
            out.append(None)
            continue
        if e is None:
            e = sum(vals[i - n + 1:i + 1]) / n
        else:
            e = v * k + e * (1 - k)
        out.append(e)
    return out


def macd(close: list, fast: int = 12, slow: int = 26, sig: int = 9):
    vals, idx = _clean(close)
    ef, es = ema_vals(vals, fast), ema_vals(vals, slow)
    dif = [(a - b) if a is not None and b is not None else None for a, b in zip(ef, es)]
    dv = [x for x in dif if x is not None]
    dea_part = ema_vals(dv, sig)
    dea, j = [], 0
    for x in dif:
        if x is None:
            dea.append(None)
        else:
            dea.append(dea_part[j])
            j += 1
    hist = [(a - b) if a is not None and b is not None else None for a, b in zip(dif, dea)]
    n = len(close)
    return _spread(n, idx, dif), _spread(n, idx, dea), _spread(n, idx, hist)


def rsi(close: list, n: int = 14) -> list:
    vals, idx = _clean(close)
    out = [None] * len(vals)
    if len(vals) <= n:
        return _spread(len(close), idx, out)
    g = l = 0.0
    for i in range(1, n + 1):
        d = vals[i] - vals[i - 1]
        g += max(d, 0)
        l += max(-d, 0)
    ag, al = g / n, l / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return _spread(len(close), idx, out)


def kd(high: list, low: list, close: list, n: int = 9):
    """台灣慣用 KD(9,3,3)：RSV 以 1/3 平滑，起始 K=D=50。"""
    pts = [(h, l, c) for h, l, c in zip(high, low, close)]
    idx = [i for i, (h, l, c) in enumerate(pts) if c is not None]
    hs = [pts[i][0] if pts[i][0] is not None else pts[i][2] for i in idx]
    ls = [pts[i][1] if pts[i][1] is not None else pts[i][2] for i in idx]
    cs = [pts[i][2] for i in idx]
    K, D = [], []
    k = d = 50.0
    for i in range(len(cs)):
        if i < n - 1:
            K.append(None)
            D.append(None)
            continue
        hh, ll = max(hs[i - n + 1:i + 1]), min(ls[i - n + 1:i + 1])
        rsv = 50.0 if hh == ll else (cs[i] - ll) / (hh - ll) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
        K.append(k)
        D.append(d)
    return _spread(len(close), idx, K), _spread(len(close), idx, D)


def atr(high: list, low: list, close: list, n: int = 14) -> list:
    idx = [i for i, c in enumerate(close) if c is not None]
    trs, prev = [], None
    for i in idx:
        h = high[i] if high[i] is not None else close[i]
        l = low[i] if low[i] is not None else close[i]
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        trs.append(tr)
        prev = close[i]
    out, a = [], None
    for j, tr in enumerate(trs):
        if j < n - 1:
            out.append(None)
            continue
        a = sum(trs[j - n + 1:j + 1]) / n if a is None else (a * (n - 1) + tr) / n
        out.append(a)
    return _spread(len(close), idx, out)


def last(xs: list):
    for x in reversed(xs):
        if x is not None:
            return x
    return None


def last_at(xs: list, t: int):
    for i in range(t, -1, -1):
        if xs[i] is not None:
            return xs[i]
    return None


def window(xs: list, t: int, n: int) -> list:
    """t 之前（不含 t）最近 n 個非空值。"""
    out = []
    i = t - 1
    while i >= 0 and len(out) < n:
        if xs[i] is not None:
            out.append(xs[i])
        i -= 1
    return out
