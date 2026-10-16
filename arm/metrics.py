"""指標引擎：多週期報酬 / Alpha、折溢價、持股張數 diff。"""
from __future__ import annotations


def period_return(series: list[tuple[str, float, int]], n: int) -> float | None:
    """近 n 個交易日報酬：close[-1]/close[-1-n] - 1。"""
    if len(series) <= n:
        return None
    return series[-1][1] / series[-1 - n][1] - 1


def ytd_return(series: list[tuple[str, float, int]], year: int) -> float | None:
    """年初以來報酬：標準口徑以『前一年最後交易日(≤ {year-1}-12-31)收盤』為基準。

    若序列無前一年資料（如今年才掛牌），退回當年首個交易日為基準；年中(>1/15)才掛牌者
    無可比 YTD → 回 None（避免拿掛牌日當年初基準虛報）。
    """
    cur = [s for s in series if s[0][:4] == str(year)]
    if not cur:
        return None
    prior = [s for s in series if s[0] <= f"{year - 1}-12-31"]
    if prior:                                   # 以去年最後交易日收盤為基準（12/31 口徑）
        return cur[-1][1] / prior[-1][1] - 1
    if len(cur) < 2 or cur[0][0] > f"{year}-01-15":
        return None
    return cur[-1][1] / cur[0][1] - 1


def si_return(series: list[tuple[str, float, int]]) -> float | None:
    if len(series) < 2:
        return None
    return series[-1][1] / series[0][1] - 1


def multi_period(series: list[tuple[str, float, int]], periods: dict, year: int) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for name, n in periods.items():
        if name == "ytd":
            out[name] = ytd_return(series, year)
        elif name == "si":
            out[name] = si_return(series)
        else:
            out[name] = period_return(series, int(n))
    return out


def alpha_vs(etf: dict[str, float | None], bench: dict[str, float | None]) -> dict[str, float | None]:
    return {k: (etf[k] - bench[k]) if (etf.get(k) is not None and bench.get(k) is not None) else None
            for k in etf}


def premium_discount(close: float, nav: float) -> float:
    return (close - nav) / nav


def holdings_diff(prev: list[dict], curr: list[dict]) -> dict[str, list[dict]]:
    """以股數(張數)比較兩快照，分類 新進/加碼/減碼/撤出。"""
    pm = {h["stock_id"]: h for h in prev}
    cm = {h["stock_id"]: h for h in curr}
    new, add, cut, exit_ = [], [], [], []
    for sid, c in cm.items():
        p = pm.get(sid)
        if p is None:
            new.append({**c, "delta_shares": c["shares"]})
        else:
            d = c["shares"] - p["shares"]
            if d > 0:
                add.append({**c, "delta_shares": d, "prev_shares": p["shares"]})
            elif d < 0:
                cut.append({**c, "delta_shares": d, "prev_shares": p["shares"]})
    for sid, p in pm.items():
        if sid not in cm:
            exit_.append({**p, "delta_shares": -p["shares"]})
    keyabs = lambda x: abs(x["delta_shares"])
    return {
        "new": sorted(new, key=keyabs, reverse=True),
        "add": sorted(add, key=keyabs, reverse=True),
        "cut": sorted(cut, key=keyabs, reverse=True),
        "exit": sorted(exit_, key=keyabs, reverse=True),
    }
