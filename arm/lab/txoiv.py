"""自算台指選擇權 30 天隱含波動率（docs/lab_dims_plan.md 第 4 節：補技術面 T10 台指 VIX 的歷史）。

期交所的台指 VIX 免費只給近幾個月（data/lab/heat/vixtw，2026-07 起才開始存），所以 T10 一直沒有 0～100、不算分。
這裡用資料分支 claude/txo-data 的「選擇權每日交易行情」（day/{年-月}.json.gz，2002-01 起）每天自己算一個數：

  1. 只用月選擇權（到期別 YYYYMM；週選 2012 年才有，用了會讓前後口徑不同）、離到期 ≥ MIN_TD 個交易日的那幾批。
  2. 每一批：價格＝結算價（沒有就用收盤）；先用加權指數收盤找價平，再用買賣權平價反推選擇權自己隱含的指數水準 f
     （txocalc.implied_forward，r＝0），以 f 重找價平；價平的買權、賣權各反推一個波動率（txocalc.iv），取平均。
  3. 用離到期的交易日數在 TARGET_TD（21 個交易日≈30 天）兩側最近的兩批，照總變異數線性內插（同 VIX 的做法）；
     只有一邊就用最近那一批。
  → {日期: [30 天隱含波動率 %, 最近一批的價平波動率 %, 最近一批離到期交易日數]}

不是期交所的台指 VIX（算法不同：VIX 用整條履約價的價格加權）；頁面要寫「自算」。只讀資料分支、不連外網。
"""
from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date

from . import txocalc as C
from . import txodata as T

TARGET_TD = 21          # 30 個日曆天約 21 個交易日
MIN_TD = 5              # 離到期不到 5 個交易日的那一批不用（快到期的價格雜訊大）
TRADING_YEAR = 252


def td_between(cal: list[str], a: str, b: date) -> int:
    """(a, b] 之間的交易日數：b 在已知交易日曆內就數日曆，超過的部分用 txocalc 的休市表數。"""
    bs = b.isoformat()
    if cal and bs <= cal[-1]:
        return bisect_right(cal, bs) - bisect_right(cal, a)
    last = cal[-1] if cal and cal[-1] > a else a
    n = bisect_right(cal, last) - bisect_right(cal, a) if cal else 0
    return n + C.trading_days(date.fromisoformat(last), b)


def expiry_iv(px: dict, close: float, t: float) -> float | None:
    """一批到期的價平波動率（年化，小數）。px＝{履約價: {"C": 價格, "P": 價格}}。"""
    both = {k: v for k, v in px.items() if v.get("C") and v.get("P")}
    if not both or t <= 0:
        return None
    atm0 = min(both, key=lambda k: (abs(k - close), k))
    f = C.implied_forward({k: {"C": (v["C"], 0), "P": (v["P"], 0)} for k, v in both.items()}, atm0) or close
    atm = min(both, key=lambda k: (abs(k - f), k))
    vs = [x for x in (C.iv("C", both[atm]["C"], f, atm, t), C.iv("P", both[atm]["P"], f, atm, t)) if x]
    return sum(vs) / len(vs) if vs else None


def day_iv(rows: list[list], day: str, close: float, cal: list[str]) -> list | None:
    """rows＝某個月日行情的列（txodata.COLS）；close＝那天加權指數收盤；cal＝交易日曆（加權指數有收盤的日子）。"""
    ci = {c: i for i, c in enumerate(T.COLS)}
    by: dict[str, dict] = {}
    xds: dict[str, date] = {}
    for r in rows:
        if r[ci["d"]] != day:
            continue
        code = str(r[ci["exp"]]).strip()
        if len(code) != 6 or not code.isdigit():
            continue                                          # 只用月選擇權
        p = r[ci["s"]] or r[ci["c"]]
        if not p or p <= 0:
            continue
        by.setdefault(code, {}).setdefault(r[ci["k"]], {})[r[ci["cp"]]] = float(p)
        if r[ci["xd"]]:
            xds[code] = date.fromisoformat(r[ci["xd"]])
    pts = []
    for code, px in by.items():
        xd = xds.get(code) or T.exp_date(code)
        n = td_between(cal, day, xd)
        if n < MIN_TD:
            continue
        v = expiry_iv(px, close, n / TRADING_YEAR)
        if v:
            pts.append((n, v))
    if not pts:
        return None
    pts.sort()
    lo = [p for p in pts if p[0] <= TARGET_TD]
    hi = [p for p in pts if p[0] >= TARGET_TD]
    if lo and hi and lo[-1][0] != hi[0][0]:
        (n1, v1), (n2, v2) = lo[-1], hi[0]
        w = (n2 - TARGET_TD) / (n2 - n1)
        iv = math.sqrt((w * v1 * v1 * n1 + (1 - w) * v2 * v2 * n2) / TARGET_TD)
    else:
        iv = (hi[0] if hi else lo[-1])[1]
    return [round(iv * 100, 2), round(pts[0][1] * 100, 2), pts[0][0]]


def month_series(doc: dict, taiex: dict, cal: list[str]) -> dict:
    """一個月的日行情檔 → {日期: [...]}（那天要有加權指數收盤）。"""
    rows = doc.get("rows") or []
    out = {}
    for d in sorted({r[0] for r in rows}):
        c = taiex.get(d)
        if not c:
            continue
        v = day_iv(rows, d, float(c), cal)
        if v:
            out[d] = v
    return out
