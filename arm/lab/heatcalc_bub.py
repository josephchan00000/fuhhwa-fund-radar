"""台股泡沫面向（heatspec VER 7，docs/lab_heat_us_plan.md 第 15 節）的資料組裝；模型在 heatbubble。

  X1 PSY、X4 趨勢偏離：加權指數月平均（國發會 1982 起；國發會還沒有的完整月份用每日收盤平均）÷ 前一個月 CPI，取對數；
  X2 兩年漲幅、X3 加速度：1990 起的每日收盤（1998 年以前證交所 FMTQIK，之後台股頁的交易日曆）；
  X5 LPPLS：data/lab/heat/tw_lppls（每週算一次）；
  X6 上市櫃本益比：月底總市值 ÷ 近四季歸屬母公司淨利（同一批公司；財報過了法定公告期限才算進去）；
  X7 市值 ÷ GDP：月底總市值 ÷ 近四季名目 GDP（季底後第二個月 1 日起才算拿得到）；
  Q1 台積電市值占比（參考讀數）。
月份是不是「完整」：交易日曆最後一天以前的月份才算（當月還沒過完的不算）。
"""
from __future__ import annotations

import math

from . import heat as H
from . import heatbubble as BB
from . import heatspec as S


def month_avg_px(daily: dict, last_day: str, min_n: int = 10) -> dict:
    """{日期: 收盤} → {YYYY-MM: 月平均}；只算 last_day 那個月以前的完整月份，當月至少 min_n 天。"""
    acc: dict[str, list] = {}
    for d, v in daily.items():
        if v and d[:7] < last_day[:7]:
            acc.setdefault(d[:7], []).append(v)
    return {ym: sum(v) / len(v) for ym, v in acc.items() if len(v) >= min_n}


def month_end_px(daily: dict) -> dict:
    """{日期: 收盤} → {YYYY-MM: 月底（當月最後一個交易日）收盤}。"""
    out: dict = {}
    for d in sorted(daily):
        if daily[d]:
            out[d[:7]] = daily[d]
    return out


def real_log(pm: dict, cpi: dict, lag: int) -> dict:
    """月平均價格 ÷ 前 lag 個月 CPI，取對數。"""
    from .heatcalc import ym_add
    out = {}
    for ym, p in pm.items():
        c = cpi.get(ym_add(ym, -lag))
        if p and c:
            out[ym] = math.log(p / c)
    return out


def psy_trend(lr: dict, M: dict, PRE: dict, k_psy: str, k_trend: str | None) -> None:
    raw, heat = BB.psy_monthly(lr, BB.load_cv())
    M[k_psy], PRE[k_psy] = raw, heat
    if k_trend:
        z, hz = BB.trend_z(lr, S.TREND["min"])
        M[k_trend], PRE[k_trend] = z, hz


def daily_runups(dates: list[str], px: list, N: dict, k_run: str, k_acc: str) -> None:
    ru, ac = BB.runup(px, S.RUNUP_DAYS), BB.accel(px, S.RUNUP_DAYS, S.ACC_DAYS)
    N[k_run] = {d: v for d, v in zip(dates, ru) if v is not None}
    N[k_acc] = {d: v for d, v in zip(dates, ac) if v is not None}


def lppls_item(lp: dict, N: dict, PRE: dict, k: str) -> None:
    """{週末交易日: [正泡沫 %, 負泡沫 %]} → 原始值（正 − 負，%）與 0～100。"""
    N[k] = {d: v[0] - v[1] for d, v in lp.items() if v and len(v) >= 2}
    PRE[k] = {d: BB.lppls_heat(v[0], v[1]) for d, v in lp.items() if v and len(v) >= 2}


def load_tw_val() -> dict:
    """上市櫃月底市值與近四季歸屬母公司淨利 → {YYYY-MM: [有四季淨利那批公司的市值, 它們的四季淨利(元), 全部市值, 台積電市值]}。"""
    from . import store
    from .packtest import deadline
    from .v3data import load_fs
    fs = load_fs()
    q_all = sorted({q for e in fs.values() for q in e})
    out = {}
    for kind in ("v3me_tw", "v3me_tp"):
        for _, doc in store.load(kind):
            d, s = (doc or {}).get("d"), (doc or {}).get("s") or {}
            if not d:
                continue
            ym = d[:7]
            qs = [q for q in q_all if deadline(q) <= d][-4:]
            row = out.setdefault(ym, [0.0, 0.0, 0.0, 0.0])
            for c, v in s.items():
                if not v or len(v) < 2 or not v[0] or not v[1]:
                    continue
                cap = float(v[0]) * float(v[1])
                row[2] += cap
                if c == "2330":
                    row[3] += cap
                if len(qs) == 4:
                    e = fs.get(c) or {}
                    ni = [(e.get(q) or {}).get("nip") for q in qs]
                    if all(x is not None for x in ni):
                        row[0] += cap
                        row[1] += 1000.0 * sum(ni)
    return out


def tw_bubble(D: dict, N: dict, M: dict, PRE: dict, REF: dict) -> None:
    """把台股泡沫七項（與參考讀數）放進 N、M、PRE、REF。資料缺的項目留空（測試資料沒有泡沫資料時整段跳過）。"""
    from .heatcalc import calendar, ym_add
    if not (D.get("turnover") or D.get("taiex")):
        return
    E = BB.taiex_daily(D)
    ds = sorted(E)
    if not ds:
        return
    daily_runups(ds, [E[d] for d in ds], N, "X2", "X3")
    lppls_item(D.get("tw_lppls") or {}, N, PRE, "X5")
    cal, _, _ = calendar(D)
    pm = month_avg_px(E, cal[-1]) if cal else {}
    pm.update({ym: v for ym, v in (D.get("taiexm") or {}).items() if v and (not cal or ym < cal[-1][:7])})
    cpi = {k: v[0] for k, v in (D.get("twcpi") or {}).items() if v and v[0]}
    psy_trend(real_log(pm, cpi, S.PSY["cpi_lag"]), M, PRE, "X1", "X4")
    val = D.get("twval") or {}
    gdp = D.get("twgdp") or {}
    x6, x7, q1 = {}, {}, {}
    for ym, (cap4, ni4, cap, tsmc) in sorted(val.items()):
        if ni4 > 0:
            x6[ym] = cap4 / ni4
        day = f"{ym_add(ym, 1)}-01"
        qs = sorted(q for q in gdp if H.avail_date(q, (2, 1)) <= day)[-4:]
        if len(qs) == 4 and all(gdp[q] for q in qs) and cap:
            x7[ym] = 100.0 * cap / (1e6 * sum(gdp[q] for q in qs))
        if cap:
            q1[ym] = 100.0 * tsmc / cap
    M["X6"], M["X7"] = x6, x7
    REF["Q1"] = q1
