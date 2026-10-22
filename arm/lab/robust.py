"""報酬的穩健數字（sigspec 第 4.11 節 VER 17、xstratspec 第 9 節 VER 6；docs/lab_practical_plan.md）。

  trim_mean(v)  排除極端：由小到大排，去掉最好和最差各 k 個之後的平均；k＝⌊TRIM_Q × 次數⌋（至少 1），次數 < TRIM_N 時 k＝1；
                次數 < 3 回 None
  lbo_mean(v)   去掉最好一次：去掉最大的那一個之後的平均；次數 < 2 回 None
  trim_mean_w(v, w)、lbo_mean_w(v, w)  VER 22（sigspec 第 4.11 節）：每一個單位（狀態型＝一段）帶權重（段內天數）——
                排序與去掉幾個照單位算，其餘照權重平均；權重全部是 1 時和上面兩個一樣。
"""
from __future__ import annotations

import math

import numpy as np

from . import sigspec as S


def _clean(v) -> np.ndarray:
    a = np.asarray([x for x in (v if v is not None else []) if x is not None], dtype=float)
    return np.sort(a[np.isfinite(a)])


def trim_k(n: int, q: float = S.TRIM_Q, n_small: int = S.TRIM_N) -> int:
    """去掉幾個（每一邊）。"""
    return 1 if n < n_small else max(1, int(math.floor(q * n + 1e-9)))


def trim_mean(v, q: float = S.TRIM_Q, n_small: int = S.TRIM_N) -> float | None:
    a = _clean(v)
    n = len(a)
    if n < 3:
        return None
    k = trim_k(n, q, n_small)
    return float(a[k:n - k].mean())


def lbo_mean(v) -> float | None:
    a = _clean(v)
    if len(a) < 2:
        return None
    return float(a[:-1].mean())


def _clean_w(v, w) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray([np.nan if x is None else x for x in (v if v is not None else [])], dtype=float)
    b = np.asarray(w if w is not None else np.ones(len(a)), dtype=float)
    m = np.isfinite(a) & np.isfinite(b) & (b > 0)
    o = np.argsort(a[m], kind="stable")
    return a[m][o], b[m][o]


def trim_mean_w(v, w, q: float = S.TRIM_Q, n_small: int = S.TRIM_N) -> float | None:
    """排除極端（權重版）：依值由小到大排，去掉最好和最差各 k 個單位（k 照單位數），其餘照權重平均。"""
    a, b = _clean_w(v, w)
    n = len(a)
    if n < 3:
        return None
    k = trim_k(n, q, n_small)
    return float((a[k:n - k] * b[k:n - k]).sum() / b[k:n - k].sum())


def lbo_mean_w(v, w) -> float | None:
    """去掉最好一次（權重版）：去掉值最大的那一個單位，其餘照權重平均。"""
    a, b = _clean_w(v, w)
    if len(a) < 2:
        return None
    return float((a[:-1] * b[:-1]).sum() / b[:-1].sum())
