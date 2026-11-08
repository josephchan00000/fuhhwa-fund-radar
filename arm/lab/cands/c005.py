"""c005 接近一年高點（George & Hwang 2004，大型股）。

每個月最後一個交易日收盤，合格股票依「當天收盤 ÷ 過去 n 個交易日（含當天）最高收盤」排序，比值最高（最接近高點）的先買
（規格 pick 的 top，不加 asc），抱到下一個月底。價格用還原權息後的收盤（P.s[代號]["c"]）；窗口內有收盤的日子少於八成就不排。
只用到第 t 天以前的收盤。
"""
from .. import bt3s
from .. import packtest as PT


def rows(P, E, b, codes, p, F):
    n = int(p["n"])
    need = int(n * 0.8)

    def score(c, t):
        if t < n:
            return None
        cl = P.s[c]["c"]
        win = [cl[i] for i in range(t - n + 1, t + 1) if cl[i]]
        if len(win) < need or not cl[t]:
            return None
        hi = max(win)
        return cl[t] / hi if hi > 0 else None

    return bt3s.rows_at(P, E, b, codes, PT._month_ends(P.cal), score)
