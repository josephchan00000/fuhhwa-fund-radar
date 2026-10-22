"""報酬的穩健數字（sigspec 第 4.11 節 VER 17、xstratspec 第 9 節 VER 6；docs/lab_practical_plan.md）。

  trim_mean(v)  排除極端：由小到大排，去掉最好和最差各 k 個之後的平均；k＝⌊TRIM_Q × 次數⌋（至少 1），次數 < TRIM_N 時 k＝1；
                次數 < 3 回 None
  lbo_mean(v)   去掉最好一次：去掉最大的那一個之後的平均；次數 < 2 回 None
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
