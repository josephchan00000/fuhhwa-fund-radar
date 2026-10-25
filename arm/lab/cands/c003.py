"""c003 低波動（Blitz & van Vliet 2007，大型股）。

每個月最後一個交易日收盤，合格股票依「過去 n 個交易日（含當天）的日報酬標準差」排序，波動最低的先買（規格 pick 的 asc），
抱到下一個月底。報酬用還原權息後的收盤（P.s[代號]["c"]）；窗口內有收盤的日子少於八成就不排。只用到第 t 天以前的收盤。
"""
import math

from .. import bt3s
from .. import packtest as PT


def rows(P, E, b, codes, p, F):
    n = int(p["n"])
    need = int(n * 0.8)

    def score(c, t):
        if t < n:
            return None
        cl = P.s[c]["c"]
        r = []
        for i in range(t - n + 1, t + 1):
            a, z = cl[i - 1], cl[i]
            if a and z:
                r.append(math.log(z / a))
        if len(r) < need:
            return None
        m = sum(r) / len(r)
        return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))

    return bt3s.rows_at(P, E, b, codes, PT._month_ends(P.cal), score)
