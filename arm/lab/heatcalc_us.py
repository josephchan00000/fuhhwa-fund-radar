"""美股景氣溫度（heatspec_us VER 1；docs/lab_heat_us_plan.md 第 15 節）：S&P 500、那斯達克、那斯達克 100、費半各算一份。

  load()            → D：美股各來源（data/lab/heat/us_*）＋台股頁也在用的 VIX、HYG、IEF、有效聯邦基金利率、貨幣基金＋台積電月營收
  build(idx, D)     → 和台股 heatcalc.build 同格式的 B（在 heatspec.use(heatspec_us.spec_for(idx)) 裡算，離開時換回台股規格）
  research(idx, B)  → 研究檔的一個指數（和台股同一套驗證；S&P 500 從 1950-01-01 起）＋泡沫事件
規則（項目、熱的方向、視窗、公布時間差）全在 heatspec_us；這裡只組資料。共用的部分（基本面、情緒籌碼、資金、估值、參考讀數）
四個指數算一次（shared），依指數的部分（技術、價格類泡沫）各算各的。

資料怎麼接（規格第 15.3、15.5 節；寫程式時補上的細節都在看任何結果之前）：
  · S&P 500 月平均股價：1928 起用每日收盤平均（當月至少 10 天），之前用 Shiller 的月平均；CPI：1947 起勞工統計局 CPI-U（未季調），
    之前用 Shiller 的 CPI；10 年公債月平均：1962 起 H.15 每日平均，之前用 Shiller 的 GS10；盈餘、股利只有 Shiller。
  · 各州初領救濟金 1987 年以前有些州沒有資料，1987-01-01 起的週才算（年增率 1988 起）。
  · 週資料（CFTC、H.4.1）的日期換成「拿得到的那天」（資料日＋heatspec_us.AVAIL_DAYS），頁面顯示時再換回資料日。
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

from . import heat as H
from . import heatbubble as BB
from . import heatcalc as C
from . import heatcalc_bub as CB
from . import heatdata as HD
from . import heatspec as S
from . import heatspec_us as U
from . import heattech as TT

PX = {k: f"us_px_{k}" for k in U.INDEX_ORDER}
LPPLS = {k: f"us_lppls_{k}" for k in U.INDEX_ORDER}
FILES = list(PX.values()) + [
    "us_vxn", "us_vix3m", "us_dxy", "us_rsp", "us_spy", "us_h15", "us_h41", "us_m2", "us_z1", "us_gdp",
    "us_cftc_am", "us_cftc_vix", "us_cftc_big", "us_cftc_mini", "us_philly", "us_ads", "us_cli", "us_claims",
    "us_bls", "us_umich", "us_ebp", "us_shiller", "us_wsts", "vix", "hyg", "ief", "effr", "mmf",
] + list(LPPLS.values())
CLAIMS_FROM = "1987-01-01"        # 各州初領救濟金：1987 年以前有些州沒有資料
UMICH_FROM = "1978-01"            # 密大消費者信心：1978 年以前是季資料
CMT3_FROM = "1981-09-01"          # 3 個月固定期限殖利率 1981-09 起；之前用 3 個月國庫券
YAHOO_FROM = "1928-01"            # S&P 500 每日收盤 1927-12-30 起（1927-12 只有 1 天，不算完整月份）
BLS_CPI_FROM = "1947-01"
H15_10Y_FROM = "1962-01"
Z1_REL = (3, 15)                  # Z.1 季底後約 10 週（同 S5）
GDP_REL = (2, 1)                  # GDP：季底後第二個月才算拿得到
EMINI = 5                         # E-mini S&P 500 一口＝大型契約 1/5


def load() -> dict:
    D = {n: HD.load(n) for n in FILES}
    D["tsmc"] = tsmc_rev()
    return D


def tsmc_rev() -> dict:
    """台積電月營收 {YYYY-MM: [營收, 去年同期]}（千元；去年同期＝營收 ÷（1＋公布的年增率），2012 年口徑改變不會算錯）。"""
    from . import store
    out = {}
    for ym, doc in store.load("rev"):
        v = ((doc or {}).get("s") or {}).get("2330")
        if v and len(v) >= 2 and v[0] and v[1] is not None and v[1] > -100:
            out[ym[:7]] = [v[0], v[0] / (1.0 + v[1] / 100.0)]
    return out


# ── 小工具 ───────────────────────────────────────────────────────────

def shift_days(ser: dict, n: int | None) -> dict:
    """{資料日: 值} → {拿得到的那天: 值}。"""
    if not n:
        return dict(ser)
    return {(date.fromisoformat(d) + timedelta(days=n)).isoformat(): v for d, v in ser.items()}


def col(ser: dict, j: int) -> dict:
    return {d: v[j] for d, v in ser.items() if v and len(v) > j and v[j] is not None}


def month_end(daily: dict) -> dict:
    return CB.month_end_px(daily)


def sat_count(ym: str) -> int:
    y, m = int(ym[:4]), int(ym[5:7])
    d = date(y, m, 1)
    n = 0
    while d.month == m:
        n += d.weekday() == 5
        d += timedelta(days=1)
    return n


def quarter_asof(q: dict, ym: str, rel: tuple) -> str | None:
    """季資料 {季底月: 值}：月份 ym 的值在 ym 的下一個月 1 日用，那時拿得到的最新一季（季底月）。"""
    day = f"{C.ym_add(ym, 1)}-01"
    ks = [k for k in q if q[k] is not None and H.avail_date(k, rel) <= day]
    return max(ks) if ks else None


def expanding_pct(ser: dict, min_n: int) -> dict:
    """{月: 值} → {月: 在有資料以來（不含當月）的百分位}。"""
    ks = sorted(ser)
    p = H.pct_series([ser[k] for k in ks], len(ks) + 1, min_n)
    return {k: x for k, x in zip(ks, p) if x is not None}


# ── 共用的長歷史月序列（S&P 500 價格、CPI、盈餘、股利、10 年公債） ────────────────────

def long_monthly(D: dict) -> dict:
    """→ {"p": S&P 500 月平均, "cpi", "e", "d", "y10", "spx_me": S&P 500 月底收盤}（各 {YYYY-MM: 值}）。"""
    sh = D.get("us_shiller") or {}
    spx = D.get("us_px_spx") or {}
    last = max(spx) if spx else "0000-00-00"
    pm = {ym: v for ym, v in CB.month_avg_px(spx, last).items() if ym >= YAHOO_FROM}
    p = {ym: v[0] for ym, v in sh.items() if v and v[0] and ym < YAHOO_FROM}
    p.update(pm)
    bls = D.get("us_bls") or {}
    cpi = {ym: v[3] for ym, v in sh.items() if v and len(v) > 3 and v[3] and ym < BLS_CPI_FROM}
    cpi.update({ym: v[1] for ym, v in bls.items() if v and v[1] and ym >= BLS_CPI_FROM})
    acc: dict[str, list] = {}
    for d, v in (D.get("us_h15") or {}).items():
        if v and len(v) > 3 and v[3] is not None:
            acc.setdefault(d[:7], []).append(v[3])
    y10 = {ym: v[4] for ym, v in sh.items() if v and len(v) > 4 and v[4] is not None and ym < H15_10Y_FROM}
    y10.update({ym: sum(v) / len(v) for ym, v in acc.items() if ym >= H15_10Y_FROM and len(v) >= C.MONTH_AVG_MIN
                and ym < last[:7]})
    return {"p": p, "cpi": cpi, "y10": y10, "spx_me": month_end(spx),
            "e": {ym: v[2] for ym, v in sh.items() if v and len(v) > 2 and v[2]},
            "d": {ym: v[1] for ym, v in sh.items() if v and len(v) > 1 and v[1]}}


def cape(L: dict) -> dict:
    """{月: CAPE}：月平均股價 ÷ 前一個月 CPI，除以「延後 6 個月的過去 10 年平均實質盈餘」（120 個月都要有）。"""
    lag = S.PSY["div_lag"]
    cpi, e, p = L["cpi"], L["e"], L["p"]
    re = {ym: e[ym] / cpi[ym] for ym in e if cpi.get(ym)}
    out = {}
    for ym, px in p.items():
        c = cpi.get(C.ym_add(ym, -S.PSY["cpi_lag"]))
        if not c:
            continue
        w = [re.get(C.ym_add(ym, -lag - j)) for j in range(120)]
        if all(x is not None for x in w):
            m = sum(w) / 120
            if m > 0:
                out[ym] = (px / c) / m
    return out


def ecy(L: dict, cp: dict) -> dict:
    """{月: 超額 CAPE 殖利率（%）}＝100 ÷ CAPE −（10 年公債 − 過去 10 年平均通膨）；通膨用到前一個月的 CPI。"""
    cpi, y10 = L["cpi"], L["y10"]
    lg = S.PSY["cpi_lag"]
    out = {}
    for ym, c in cp.items():
        a, b, y = cpi.get(C.ym_add(ym, -lg)), cpi.get(C.ym_add(ym, -lg - 120)), y10.get(ym)
        if a and b and y is not None:
            infl = 100.0 * ((a / b) ** 0.1 - 1.0)
            out[ym] = 100.0 / c - (y - infl)
    return out


def z1_ratios(D: dict, L: dict) -> tuple[dict, dict]:
    """→（巴菲特指標、Tobin's Q）{月: 比率}：最近一季拿得到的 Z.1 股票市值用之後的 S&P 500 月底漲跌推到月底；
    巴菲特指標的分母＝最近一季拿得到的名目 GDP（年化），Tobin's Q 的分母＝同一季 Z.1 淨值。"""
    z1 = D.get("us_z1") or {}
    eq, nw = col(z1, 0), col(z1, 1)
    gdp = {k: v for k, v in (D.get("us_gdp") or {}).items() if v}
    me = L["spx_me"]
    bf, tq = {}, {}
    for ym in sorted(me):
        q = quarter_asof(eq, ym, Z1_REL)
        if not q or not me.get(q):
            continue
        cap = eq[q] * me[ym] / me[q]
        g = quarter_asof(gdp, ym, GDP_REL)
        if g:
            bf[ym] = cap / gdp[g]
        if nw.get(q):
            tq[ym] = cap / nw[q]
    return bf, tq


# ── 共用（四個指數一樣）的項目 ───────────────────────────────────────────

def shared(D: dict) -> dict:
    """→ {"N": 日資料, "M": 月資料, "PRE": 直接換算的月資料, "REF": 參考讀數, "L": 長歷史月序列}。"""
    N: dict[str, dict] = {}
    M: dict[str, dict] = {}
    PRE: dict[str, dict] = {}
    ad = U.AVAIL_DAYS
    # 情緒籌碼
    am = D.get("us_cftc_am") or {}
    N["S1"] = shift_days({d: 100.0 * (v[0] - v[1]) / v[2] for d, v in am.items() if v and v[2]}, ad.get("S1"))
    big, mini = D.get("us_cftc_big") or {}, D.get("us_cftc_mini") or {}
    s2 = {}
    for d in set(big) | set(mini):
        net = oi = 0.0
        for v, f in ((big.get(d), 1.0), (mini.get(d), 1.0 / EMINI)):
            if v and v[2]:
                net += f * (v[0] - v[1])
                oi += f * v[2]
        if oi:
            s2[d] = 100.0 * net / oi
    N["S2"] = shift_days(s2, ad.get("S2"))
    vx = D.get("us_cftc_vix") or {}
    N["S3"] = shift_days({d: 100.0 * (v[0] - v[1]) / v[2] for d, v in vx.items() if v and v[2]}, ad.get("S3"))
    vix, v3m = D.get("vix") or {}, D.get("us_vix3m") or {}
    N["S4"] = {d: vix[d] / v3m[d] for d in vix if vix[d] and v3m.get(d)}
    # 資金
    N["R1"] = C.native(D.get("effr") or {}, lambda v: H.chg(H.roll_mean(v, 5), 126, pct=False))
    h15 = D.get("us_h15") or {}
    N["R2"] = C.native(col(h15, 2), lambda v: H.chg(v, 60, pct=False))
    N["R3"] = C.native(col(h15, 3), lambda v: H.chg(v, 60, pct=False))
    r4 = {}
    for d, v in h15.items():
        short = (v[1] if d >= CMT3_FROM else v[0]) if v else None
        if v and v[3] is not None and short is not None:
            r4[d] = v[3] - short
    N["R4"] = r4
    hy, ie = D.get("hyg") or {}, D.get("ief") or {}
    N["R5"] = C.native({d: hy[d] / ie[d] for d in hy if hy[d] and ie.get(d)}, lambda v: H.chg(v, 60))
    h41 = D.get("us_h41") or {}
    nl = {d: v[0] - v[1] - v[2] for d, v in h41.items() if v and None not in v[:3]}
    N["R8"] = shift_days(C.native(nl, lambda v: H.chg(v, 13)), ad.get("R8"))
    N["R9"] = C.native(D.get("us_dxy") or {}, lambda v: H.chg(v, 60))
    # 基本面（月）
    M["F1"] = {ym: v for ym, v in (D.get("us_philly") or {}).items() if v is not None}
    M["F2"] = C.month_avg(D.get("us_ads") or {})
    M["F3"] = {ym: v for ym, v in (D.get("us_cli") or {}).items() if v is not None}
    wk: dict[str, list] = {}
    for d, v in (D.get("us_claims") or {}).items():
        if v and d >= CLAIMS_FROM:
            wk.setdefault(d[:7], []).append(v)
    cm = {ym: sum(v) / len(v) for ym, v in wk.items() if len(v) == sat_count(ym)}
    M["F4"] = {ym: C.yoy(cm, ym) for ym in cm if C.yoy(cm, ym) is not None}
    bls = D.get("us_bls") or {}
    ur = col(bls, 0)
    u3 = {ym: sum(ur[C.ym_add(ym, -j)] for j in range(3)) / 3 for ym in ur
          if all(C.ym_add(ym, -j) in ur for j in range(3))}
    M["F5"] = {ym: v - min(u3[C.ym_add(ym, -j)] for j in range(1, 13)) for ym, v in u3.items()
               if all(C.ym_add(ym, -j) in u3 for j in range(1, 13))}
    for k, j in (("F6", 1), ("F7", 2)):
        ix = col(bls, j)
        M[k] = {ym: C.yoy(ix, ym) for ym in ix if C.yoy(ix, ym) is not None}
    L = long_monthly(D)
    e = L["e"]
    M["F8"] = {ym: 100.0 * (v / e[C.ym_add(ym, -12)] - 1.0) for ym, v in e.items()
               if (e.get(C.ym_add(ym, -12)) or 0) > 0}
    M["F9"] = {ym: v for ym, v in (D.get("us_umich") or {}).items() if v is not None and ym >= UMICH_FROM}
    M["F10"] = C.yoy3({ym: v for ym, v in (D.get("us_wsts") or {}).items() if v})
    tr = D.get("tsmc") or {}
    f11 = {}
    for ym in tr:
        ms = [tr.get(C.ym_add(ym, -j)) for j in range(3)]
        if all(ms) and sum(m[1] for m in ms):
            f11[ym] = 100.0 * (sum(m[0] for m in ms) / sum(m[1] for m in ms) - 1.0)
    M["F11"] = f11
    sc = col(D.get("us_z1") or {}, 2)
    M["S5"] = {ym: C.yoy(sc, ym) for ym in sc if C.yoy(sc, ym) is not None}
    M["R6"] = col(D.get("us_ebp") or {}, 1)
    m2 = {ym: v for ym, v in (D.get("us_m2") or {}).items() if v}
    M["R7"] = {ym: C.yoy(m2, ym) for ym in m2 if C.yoy(m2, ym) is not None}
    me = L["spx_me"]
    M["R10"] = {ym: (v / 1e12) / (me[ym] / 1000.0) for ym, v in (D.get("mmf") or {}).items() if v and me.get(ym)}
    # 泡沫：估值（美股整體）
    cp = cape(L)
    M["X6"] = cp
    M["X7"] = ecy(L, cp)
    bf, tq = z1_ratios(D, L)
    M["X8"] = BB.detrended_pct(bf, S.TREND["min"])
    M["X9"] = BB.detrended_pct(tq, S.TREND["min"])
    pd = {}
    for ym, px in L["p"].items():
        dv = L["d"].get(C.ym_add(ym, -S.PSY["div_lag"]))
        if px and dv:
            pd[ym] = math.log(px / dv)
    M["X10"], PRE["X10"] = BB.psy_monthly(pd, BB.load_cv())
    return {"N": N, "M": M, "PRE": PRE, "REF": references(D, L, M, cp), "L": L}


def real_price(L: dict, pm: dict) -> dict:
    """月平均價格 ÷ 前一個月 CPI，取對數（PSY、趨勢偏離用）。"""
    return CB.real_log(pm, L["cpi"], S.PSY["cpi_lag"])


def references(D: dict, L: dict, M: dict, cp: dict) -> dict:
    """參考讀數（不進分數）：Q1 Hussman 條件數（每天）、Q2 RSP ÷ SPY 一年變化（每天）、Q3 高盛熊市風險指標近似（每月）。"""
    REF: dict[str, dict] = {}
    spx = D.get("us_px_spx") or {}
    ds = sorted(d for d, v in spx.items() if v)
    px = [spx[d] for d in ds]
    ma = H.roll_mean(px, 250)
    h15 = D.get("us_h15") or {}
    y10 = H.asof_daily(ds, col(h15, 3), stale=7)
    y126 = H.roll_mean(y10, 126, 120)
    cpp = expanding_pct(cp, S.PCT_MIN["m"])
    cap = H.asof_monthly(ds, cpp, U.RELEASE["X6"])
    q1 = {}
    for i, d in enumerate(ds):
        if ma[i] is None or y10[i] is None or y126[i] is None or cap[i] is None:
            continue
        q1[d] = (cap[i] >= 80.0) + (px[i] > 1.07 * ma[i]) + (y10[i] > y126[i])
    REF["Q1"] = q1
    rsp, spy = D.get("us_rsp") or {}, D.get("us_spy") or {}
    REF["Q2"] = C.native({d: rsp[d] / spy[d] for d in rsp if rsp[d] and spy.get(d)}, lambda v: H.chg(v, 250))
    acc: dict[str, list] = {}
    for d, v in h15.items():
        if v and len(v) > 3 and v[2] is not None and v[3] is not None:
            acc.setdefault(d[:7], []).append(v[3] - v[2])
    spr = {ym: sum(v) / len(v) for ym, v in acc.items() if len(v) >= C.MONTH_AVG_MIN}
    mn = S.PCT_MIN["m"]
    parts = [(expanding_pct(col(D.get("us_bls") or {}, 0), mn), -1), (expanding_pct(M["F7"], mn), +1),
             (expanding_pct(spr, mn), -1), (cpp, +1), (expanding_pct(M["F1"], mn), +1)]
    q3 = {}
    for ym in sorted(set.intersection(*[set(p) for p, _ in parts])):
        q3[ym] = sum(p[ym] if s > 0 else 100.0 - p[ym] for p, s in parts) / len(parts)
    REF["Q3"] = q3
    return REF


# ── 依指數 ───────────────────────────────────────────────────────────

def calendar(D: dict, idx: str) -> tuple[list[str], list, dict]:
    ser = D.get(PX[idx]) or {}
    cal = sorted(d for d, v in ser.items() if v)
    px = [ser[d] for d in cal]
    return cal, px, {"days": len(cal), "first": cal[0] if cal else None, "last": cal[-1] if cal else None}


def index_items(D: dict, idx: str, cal: list[str], px: list, SH: dict) -> tuple[dict, dict, dict]:
    """依指數的項目 → (N 日資料, M 月資料, PRE 直接換算)：技術面、兩年漲幅、加速度、LPPLS、扣掉 S&P 500、PSY、趨勢偏離。"""
    on_cal = lambda xs: {d: v for d, v in zip(cal, xs) if v is not None}   # noqa: E731
    N: dict[str, dict] = {}
    N["T1"] = on_cal(C.rel_ma(px, 20))
    N["T2"] = on_cal(C.rel_ma(px, 60))
    N["T3"] = on_cal(C.rel_ma(px, 240))
    N["T4"] = on_cal(H.rsi(px, 14))
    N["T8"] = on_cal(H.roll_std_ret(px, 20))
    N["T9"] = dict(D.get("us_vxn" if U.IVOL[idx] == "vxn" else "vix") or {})
    MA = TT.mas(px)
    conds = [(px, MA[5]), (MA[5], MA[10]), (MA[10], MA[20]), (MA[20], MA[60]), (MA[60], MA[120]), (MA[120], MA[240])]
    N["T11"] = on_cal([None if MA[240][i] is None else sum(1 for a, b in conds if a[i] > b[i]) for i in range(len(cal))])
    N["T12"] = on_cal(H.chg(MA[60], 20))
    hi = C.roll_max(px, 120)
    N["T13"] = on_cal([None if p is None or h is None else 100.0 * (p / h - 1.0) for p, h in zip(px, hi)])
    CB.daily_runups(cal, px, N, "X2", "X3")
    PRE: dict[str, dict] = {}
    CB.lppls_item(D.get(LPPLS[idx]) or {}, N, PRE, "X5")
    if idx != "spx":
        ref = H.asof_daily(cal, D.get(PX["spx"]) or {}, stale=7)
        rel = [None if a is None or b is None or not b else a / b for a, b in zip(px, ref)]
        N["T14"] = on_cal(H.chg(rel, 60))
        N["X11"] = on_cal(BB.net_runup(px, ref, S.RUNUP_DAYS))
    M: dict[str, dict] = {}
    L = SH["L"]
    pm = L["p"] if idx == "spx" else CB.month_avg_px(dict(zip(cal, px)), cal[-1])
    CB.psy_trend(real_price(L, pm), M, PRE, "X1", "X4")
    return N, M, PRE


def build(idx: str, D: dict | None = None, SH: dict | None = None) -> dict:
    """→ 和台股 heatcalc.build 同格式的 B（多 "idx"）。SH＝shared(D) 的結果（四個指數一起算時只算一次）。"""
    D = D if D is not None else load()
    SH = SH if SH is not None else shared(D)
    with S.use(U.spec_for(idx)):
        cal, px, info = calendar(D, idx)
        N, M, PRE = index_items(D, idx, cal, px, SH)
        keys = set(S.KEYS)
        N = {**{k: v for k, v in SH["N"].items() if k in keys}, **N}
        M = {**{k: v for k, v in SH["M"].items() if k in keys}, **M}
        PRE = {**{k: v for k, v in SH["PRE"].items() if k in keys}, **PRE}
        B = C.score(D, cal, px, info, N, M, PRE, dict(SH["REF"]))
    B["idx"] = idx
    return B


def build_all(D: dict | None = None) -> dict:
    D = D if D is not None else load()
    SH = shared(D)
    return {idx: build(idx, D, SH) for idx in U.INDEX_ORDER}


# ── 驗證 ─────────────────────────────────────────────────────────────

def trim(B: dict, start: str | None) -> dict:
    """驗證樣本從 start 起（S&P 500：1950-01-01）：把逐日的序列切掉前面；分數本身用完整歷史算（只是暖身）。"""
    if not start:
        return B
    cal = B["cal"]
    i0 = next((i for i, d in enumerate(cal) if d >= start), len(cal))
    if i0 == 0:
        return B
    cut = lambda xs: xs[i0:]   # noqa: E731
    out = dict(B)
    out["cal"], out["px"] = cut(cal), cut(B["px"])
    for k in ("raw", "heat", "hc", "proxy", "ym"):
        out[k] = {n: cut(v) for n, v in B[k].items()}
    out["comp"] = {d: cut(v) for d, v in B["comp"].items()}
    out["cal_info"] = {**B["cal_info"], "val_first": out["cal"][0] if out["cal"] else None}
    return out


def research(idx: str, B: dict) -> dict:
    """一個指數的研究檔（同台股：每一項與面向分數的等級相關、五區、技術事件、第五版單項分析、第六版多層回歸；另加泡沫事件）。"""
    from . import heatrel, heatreg
    with S.use(U.spec_for(idx)):
        V = trim(B, S.VAL_START.get(idx))
        cal, px, comp = V["cal"], V["px"], V["comp"]
        dims = {}
        for dim in S.DIMS:
            keys = S.ITEMS[dim]
            items = {k: C.evaluate(V["hc"][k], px, cal, dim) for k in keys}
            first = {k: next((cal[i] for i, v in enumerate(V["hc"][k]) if v is not None), None) for k in keys}
            cf = next((cal[i] for i, v in enumerate(comp[dim]) if v is not None), None)
            dims[dim] = {"items": items, "first": first, "comp": C.evaluate(comp[dim], px, cal, dim), "comp_first": cf}
        ev = TT.all_events(px)
        fw = {h: TT.fwd_all(px, h) for h in S.EV_FWD}
        events = {k: {str(h): C._round_ev(TT.event_study(px, cal, ev[k], h, f=fw[h])) for h in S.EV_FWD} for k in S.EVENTS}
        D = B["D"]
        data = {}
        for n in FILES + ["tsmc"]:
            ks = sorted(D.get(n) or {})
            data[n] = [len(ks), ks[0] if ks else None, ks[-1] if ks else None]
        rel = heatrel.run(V)
        return {"ver": S.VER, "spec_date": S.SPEC_DATE, "idx": idx, "cal": V["cal_info"], "data": data, "dims": dims,
                "events": events, "wk": rel["wk"], "rel": rel["rel"], "deriv": heatrel.deriv_all(V),
                "m6": heatreg.run(V), "bub": BB.bubble_research(V)}


def _research_one(idx: str) -> tuple[str, dict]:
    D = load()
    return idx, research(idx, build(idx, D, shared(D)))


def research_all(procs: int = 4) -> dict:
    """四個指數各跑一次研究（procs＞1 時每個指數一個行程；結果和依序跑相同）。"""
    out = {"ver": U.VER, "spec_date": U.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"), "idx": {}}
    if procs > 1:
        from multiprocessing import Pool
        with Pool(min(procs, len(U.INDEX_ORDER))) as pool:
            res = dict(pool.map(_research_one, U.INDEX_ORDER))
    else:
        res = dict(_research_one(idx) for idx in U.INDEX_ORDER)
    out["idx"] = {idx: res[idx] for idx in U.INDEX_ORDER}
    return out
