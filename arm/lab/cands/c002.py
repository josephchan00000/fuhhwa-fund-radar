"""c002 選擇權到期週（Stivers & Sun 2013）。

每個月第三個星期五那一週（星期一到星期五）拿指數，其他時間空手：前一個星期五收盤買、第三個星期五收盤賣。
日曆排定的事（同總經策略的月底月初、Halloween），照排定那天收盤進出；只用日期推算，不看資料裡之後的交易日。
pos[k]＝第 k 天收盤之後要不要拿＝「第 k 天之後的下一個平日」落在窗口裡。
窗口＝第三個星期五往前 4＋pre 個平日、往後 post 個平日（pre、post＝0 是星期一到星期五；1＝多一天、−1＝少一天）。
"""
from datetime import date, timedelta

import numpy as np

_D0 = date(1970, 1, 5)                                  # 星期一


def _wd(d: date) -> int:
    """_D0 起的第幾個平日（只用在平日上）。"""
    n = (d - _D0).days
    return n // 7 * 5 + min(n % 7, 5)


def _third_friday(y: int, m: int) -> date:
    d = date(y, m, 15)                                  # 第三個星期五落在 15～21 日
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def pos(C, p, lag, now=False):
    pre, post = int(p["pre"]), int(p["post"])
    out = np.zeros(C.T)
    for k, s in enumerate(C.cal):
        nd = _next_weekday(date.fromisoformat(s))
        w = _wd(nd)
        for dm in (-1, 0, 1):
            y, m = nd.year, nd.month + dm
            if m == 0:
                y, m = y - 1, 12
            elif m == 13:
                y, m = y + 1, 1
            f = _wd(_third_friday(y, m))
            if f - 4 - pre <= w <= f + post:
                out[k] = 1.0
                break
    return out
