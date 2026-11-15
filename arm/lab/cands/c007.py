"""c007 同月份季節性（Heston & Sadka 2008，大型股）。

每個月最後一個交易日收盤，合格股票依「過去 n 年同一個月（＝下個月的月份）的月報酬平均」排序，平均最高的先買
（規格 pick 的 top，不加 asc），抱到下一個月底。
月報酬＝那個月最後一個交易日收盤 ÷ 前一個月最後一個交易日收盤 − 1（還原權息後的收盤 P.s[代號]["c"]；
月底＝packtest._month_ends，下一個交易日已經換月才算）。n 年裡任何一年缺月報酬（月底沒有收盤）的股票不排。
過去幾年的同一個月最晚是去年的這個月份，都在第 t 天以前，只用到第 t 天以前的收盤。
"""
from .. import bt3s
from .. import packtest as PT


def _ym_add(ym: str, k: int) -> str:
    """YYYY-MM 往後 k 個月（k 可為負）。"""
    m = int(ym[:4]) * 12 + int(ym[5:7]) - 1 + k
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


def rows(P, E, b, codes, p, F):
    n = int(p["n"])
    forms = PT._month_ends(P.cal)
    me = {P.cal[t][:7]: t for t in forms}

    def score(c, t):
        cl = P.s[c]["c"]
        nxt = _ym_add(P.cal[t][:7], 1)
        rs = []
        for k in range(1, n + 1):
            ym = _ym_add(nxt, -12 * k)
            i, i0 = me.get(ym), me.get(_ym_add(ym, -1))
            if i is None or i0 is None or i > t:
                return None
            if not cl[i] or not cl[i0]:
                return None
            rs.append(cl[i] / cl[i0] - 1)
        return sum(rs) / n

    return bt3s.rows_at(P, E, b, codes, forms, score)
