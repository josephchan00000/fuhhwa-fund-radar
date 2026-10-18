"""泡沫頁的計算（規格 bubspec VER 2；docs/lab_risk_plan.md 第 8、9 節）。

每個市場每月一個樣本（月底最後一個交易日），算六個條件（P1 價格爆發、P2 兩年翻倍在高點、P3 偏離長期趨勢、
E 價格漲得比基本面快、V 估值、F 槓桿）與 0～4 級（VER 2；VER 1 的等級另存 L1 當對照）；
每個條件都只用該日以前「拿得到」的資料（公布時間差照景氣頁的規則）。
  · E：每個市場的「價格 ÷ 基本面」比值（fund_ratios）取對數，做和 P1 同一套 PSY，連續 E_RUN 個月超過臨界值；
  · P1 的臨界值表（不同長期漲勢各模擬一次）用 numpy 算一次存 data/lab/heat/psy_cv_drift（cv_table），
    同一個種子給每一檔漂移（共同亂數，內插比較平順）；
  · 驗證（重抽）只在研究時跑（scripts/run_bub.py → data/lab/bub_research.json），每天建頁只算現在的狀態與歷史等級。
"""
from __future__ import annotations

import math

from . import bubspec as BS
from . import heatdata as HD

CV_NAME = "psy_cv_drift"


SHORT = {"P1": "價格爆發", "P2": "兩年翻倍", "P3": "偏離趨勢", "E": "漲得比基本面快", "V": "估值", "F": "槓桿"}   # 頁面用的短名稱
CONDS = ("P1", "P2", "P3", "E", "V", "F")
FUND_STALE = 12                                      # 基本面最新一期比當月舊超過 12 個月就不算比值（來源停更時不硬接）


# ── P1：有長期漲勢的 PSY 臨界值 ──────────────────────────────────────────────

def cv_table(progress=None) -> dict:
    """DRIFT_GRID 每一檔各模擬 CV_REPS 次 → {"grid", "w0", "reps", "seed", "nmax", "q50": [每一檔的序列], "q95": [...]}。"""
    from . import heatbubble as HB
    w0 = BS.PSY["w0"]
    q50, q95 = [], []
    for g in BS.DRIFT_GRID:
        cv = HB.psy_cv(w0, BS.CV_REPS, BS.CV_NMAX, BS.CV_SEED, qs=(0.5, 0.95), drift=g)
        q50.append(cv["q50"])
        q95.append(cv["q95"])
        if progress:
            progress(g, cv)
    return {"grid": list(BS.DRIFT_GRID), "w0": w0, "reps": BS.CV_REPS, "seed": BS.CV_SEED, "nmax": BS.CV_NMAX,
            "q50": q50, "q95": q95}


def load_cv_table() -> dict | None:
    t = HD.load(CV_NAME)
    if not t or t.get("grid") != list(BS.DRIFT_GRID) or t.get("w0") != BS.PSY["w0"] or t.get("reps") != BS.CV_REPS \
            or t.get("seed") != BS.CV_SEED or t.get("nmax") != BS.CV_NMAX:
        return None
    return t


def cv_at(T: dict, n: int, g: float) -> tuple[float | None, float | None]:
    """第 n 個樣本位置（0 起算）、漂移 g → （中位數, 95% 臨界值），相鄰兩檔線性內插；g 截在表的範圍內。"""
    grid = T["grid"]
    g = min(max(g, grid[0]), grid[-1])
    j = 0
    while j < len(grid) - 2 and g > grid[j + 1]:
        j += 1
    w = 0.0 if grid[j + 1] == grid[j] else (g - grid[j]) / (grid[j + 1] - grid[j])
    out = []
    for key in ("q50", "q95"):
        a, b = T[key][j], T[key][j + 1]
        if n >= len(a) or a[n] is None or b[n] is None:
            return None, None
        out.append(a[n] * (1.0 - w) + b[n] * w)
    return out[0], out[1]


# ── 小工具 ───────────────────────────────────────────────────────────────

def _ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def _mdiff(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def fill_cpi(cpi: dict) -> dict:
    """{YYYY-MM: CPI} → 連續 ≤ CPI_GAP_MAX 個月的缺口用前後兩個月幾何內插補上（只缺一個月＝前後兩個月的幾何平均）。"""
    ks = sorted(k for k, v in cpi.items() if v)
    out = {k: cpi[k] for k in ks}
    for a, b in zip(ks, ks[1:]):
        gap = _mdiff(a, b) - 1
        if 1 <= gap <= BS.CPI_GAP_MAX:
            for j in range(1, gap + 1):
                out[_ym_add(a, j)] = cpi[a] * (cpi[b] / cpi[a]) ** (j / (gap + 1))
    return out


def expanding_pct_span(ser: dict, min_months: int) -> dict:
    """{YYYY-MM: 值} → {月: 在有資料以來（不含當月）的百分位}；從第一筆到當月要 ≥ min_months 個月（季資料也用月數算）。
    百分位＝（比它小的筆數＋相等筆數的一半）÷ 過去筆數（同 heat.pct_series）。"""
    import bisect
    ks = sorted(k for k, v in ser.items() if v is not None)
    out: dict = {}
    past: list = []
    for k in ks:
        x = ser[k]
        if past and _mdiff(ks[0], k) >= min_months:
            lo, hi = bisect.bisect_left(past, x), bisect.bisect_right(past, x)
            out[k] = 100.0 * (lo + 0.5 * (hi - lo)) / len(past)
        bisect.insort(past, x)
    return out


def _segments(M: dict) -> list[list[str]]:
    segs, seg = [], []
    for k in sorted(M):
        if seg and _mdiff(seg[-1], k) != 1:
            segs.append(seg)
            seg = []
        seg.append(k)
    if seg:
        segs.append(seg)
    return segs


def psy_drift(M: dict, T: dict) -> dict:
    """{YYYY-MM: 對數實質價格} → {月: {"s": BSADF, "q50", "q95", "g": 漂移 ÷ 標準差, "x": 0～100, "hit": BSADF ＞ q95}}。
    缺月就從缺口之後重新起算（同景氣頁）；漂移用到當月為止的月變化（Welford），至少 DRIFT_MIN_N 個變化。"""
    from . import heatbubble as HB
    out: dict = {}
    for sg in _segments(M):
        ys = [M[k] for k in sg]
        st = HB.bsadf(ys, BS.PSY["w0"])
        n, mean, m2 = 0, 0.0, 0.0
        for i, k in enumerate(sg):
            if i:
                d = ys[i] - ys[i - 1]
                n += 1
                delta = d - mean
                mean += delta / n
                m2 += delta * (d - mean)
            if st[i] is None or n < BS.DRIFT_MIN_N or m2 <= 0:
                continue
            g = mean / math.sqrt(m2 / (n - 1))
            q50, q95 = cv_at(T, i, g)
            if q95 is None:
                continue
            out[k] = {"s": st[i], "q50": q50, "q95": q95, "g": g, "x": HB.psy_heat(st[i], q50, q95), "hit": st[i] > q95}
    return out


def p1_flags(R: dict) -> dict:
    """{月: 當月與前 PSY_RUN − 1 個月都超過 95% 臨界值}（有 PSY 讀數的月份才有值）。"""
    return {k: all((R.get(_ym_add(k, -j)) or {}).get("hit") for j in range(BS.PSY_RUN)) for k in R}


def p2_daily(px: list) -> tuple[list, list, list]:
    """→（兩年漲幅 %, 離歷史最高收盤 %, 成立與否）；兩年漲幅算不出來的日子三個都是 None。"""
    from . import heatbubble as HB
    ru = HB.runup(px, BS.RUNUP_DAYS)
    ath, dist, flag = None, [None] * len(px), [None] * len(px)
    for i, p in enumerate(px):
        if p:
            ath = p if ath is None else max(ath, p)
        if ru[i] is None or not p or not ath:
            continue
        dist[i] = 100.0 * (p / ath - 1.0)
        flag[i] = ru[i] >= BS.RUN2_PCT and p >= ath * (1.0 - BS.RUN2_ATH)
    return ru, dist, flag


def month_end_idx(cal: list[str]) -> list[int]:
    """每個月最後一個交易日在 cal 的位置。"""
    out = []
    for i, d in enumerate(cal):
        if i + 1 == len(cal) or cal[i + 1][:7] != d[:7]:
            out.append(i)
    return out


# ── 各市場的月資料 ─────────────────────────────────────────────────────────

TW_FILES = ("taiex", "turnover", "taiex90", "taiexm", "twcpi", "margin", "tw_lppls", "exports")
US_FILES = ("us_px_spx", "us_px_ixic", "us_px_ndx", "us_px_sox", "us_shiller", "us_bls", "us_h15", "us_z1", "us_gdp",
            "us_rsp", "us_spy", "us_lppls_spx", "us_lppls_ixic", "us_lppls_ndx", "us_lppls_sox", "us_wsts", "us_cp")
REL = (1, 1)                                         # 月資料：下個月 1 日起才算拿得到（同景氣頁 X1、X4、X6～X9）


def load_tw() -> dict:
    from .heatcalc_bub import load_tw_val
    D = {n: HD.load(n) for n in TW_FILES}
    D["twval"] = load_tw_val()
    return D


def load_us() -> dict:
    return {n: HD.load(n) for n in US_FILES}


# ── VER 2：基本面比值 ─────────────────────────────────────────────────────────

def roll_sum(F: dict, n: int) -> dict:
    """月資料 {YYYY-MM: 值} → {月: 近 n 個月合計}（n 個月都要有）。"""
    out = {}
    for k in F:
        ks = [_ym_add(k, -j) for j in range(n)]
        if all(F.get(x) is not None for x in ks):
            out[k] = sum(F[x] for x in ks)
    return out


def roll_q_avg(F: dict, n: int) -> dict:
    """季資料 {季底 YYYY-MM: 年率} → {季底: 近 n 季平均}（n 季都要有）。"""
    out = {}
    for k in F:
        ks = [_ym_add(k, -3 * j) for j in range(n)]
        if all(F.get(x) is not None for x in ks):
            out[k] = sum(F[x] for x in ks) / n
    return out


def fund_asof(F: dict, months, rel: tuple) -> dict:
    """基本面 {期別 YYYY-MM: 值} → {月: (期別, 值)}：那個月月底拿得到的最新一期（比當月舊超過 FUND_STALE 個月就不算）。"""
    from . import heat as H
    av = sorted((H.avail_date(ym, rel), ym) for ym, v in F.items() if v is not None)
    out: dict = {}
    j = -1
    for m in sorted(months):
        end = f"{m}-31"
        while j + 1 < len(av) and av[j + 1][0] <= end:
            j += 1
        if j >= 0 and _mdiff(av[j][1], m) <= FUND_STALE:
            out[m] = (av[j][1], F[av[j][1]])
    return out


def ratio_log(pm: dict, fa: dict) -> dict:
    """{月: 月平均價格} ÷ {月: (期別, 基本面)} → {月: log 比值}。"""
    return {m: math.log(pm[m] / fa[m][1]) for m in pm if m in fa and pm[m] and fa[m][1] and fa[m][1] > 0}


def fund_ratios(mk: str, I: dict, D: dict) -> dict:
    """市場 mk 的基本面比值（bubspec.FUND）→ {名稱: {"lr": {月: log 比值}, "f": {月: (期別, 基本面)}, "p": {月: 價格}}}。
    台股本益比的價格是「有四季淨利公司的月底市值」、基本面是它們的四季淨利（已按財報期限）；出口比值用實質加權指數（P1 的 lr）。"""
    out: dict = {}
    for k in BS.FUND[mk]:
        if k == "pe":
            L = I["L"]
            fa = fund_asof(L["e"], L["p"].keys(), BS.FUND_REL["pe"])
            out[k] = {"lr": ratio_log(L["p"], fa), "f": fa, "p": L["p"], "raw": L["e"]}
        elif k == "pe_tw":
            val = D.get("twval") or {}
            pc = {ym: v[0] for ym, v in val.items() if v[0] and v[1] and v[1] > 0}
            fa = {ym: (ym, val[ym][1]) for ym in pc}
            out[k] = {"lr": ratio_log(pc, fa), "f": fa, "p": pc}
        elif k == "ex":
            ex = roll_sum({ym: v for ym, v in (D.get("exports") or {}).items() if v}, BS.FUND_SUM["ex"])
            lr = I["lr"]
            fa = fund_asof(ex, lr.keys(), BS.FUND_REL["ex"])
            out[k] = {"lr": {m: lr[m] - math.log(fa[m][1]) for m in lr if m in fa and fa[m][1] > 0}, "f": fa,
                      "p": {m: math.exp(v) for m, v in lr.items()}, "raw": ex}
        elif k == "wsts":
            ws = roll_sum({ym: v for ym, v in (D.get("us_wsts") or {}).items() if v}, BS.FUND_SUM["wsts"])
            fa = fund_asof(ws, I["pm"].keys(), BS.FUND_REL["wsts"])
            out[k] = {"lr": ratio_log(I["pm"], fa), "f": fa, "p": I["pm"], "raw": ws}
        elif k == "cp":
            cp = D.get("us_cp") or HD.load("us_cp")
            c4 = roll_q_avg({ym: v for ym, v in cp.items() if v}, BS.FUND_SUM["cp"])
            fa = fund_asof(c4, I["pm"].keys(), BS.FUND_REL["cp"])
            out[k] = {"lr": ratio_log(I["pm"], fa), "f": fa, "p": I["pm"], "raw": c4}
    return out


def e_flags(FR: dict, T: dict) -> dict:
    """每條比值做 PSY → {名稱: {"R": psy_drift 結果, "f": {月: 連續 E_RUN 個月超過}}}。"""
    out = {}
    for k, v in FR.items():
        R = psy_drift(v["lr"], T)
        out[k] = {"R": R, "f": {m: all((R.get(_ym_add(m, -j)) or {}).get("hit") for j in range(BS.E_RUN)) for m in R}}
    return out


def tw_inputs(D: dict) -> dict:
    """台股：日線（1990 起）、實質月平均取對數（國發會 1982 起）、槓桿（融資 ÷ 市值）、參考讀數。"""
    from . import heatbubble as HB
    from . import heatcalc_bub as CB
    E = HB.taiex_daily(D)
    cal = sorted(d for d, v in E.items() if v)
    px = [E[d] for d in cal]
    pm = CB.tw_month_avg(D, E)
    cpi = fill_cpi({k: v[0] for k, v in (D.get("twcpi") or {}).items() if v and v[0]})
    lr = CB.real_log(pm, cpi, BS.PSY["cpi_lag"])
    me: dict = {}
    for d in sorted(D.get("margin") or {}):
        v = D["margin"][d]
        if v and v[0]:
            me[d[:7]] = v[0]
    val = D.get("twval") or {}
    fuel = {ym: 100.0 * me[ym] / val[ym][2] for ym in val if ym in me and val[ym][2]}
    pe = {ym: v[0] / v[1] for ym, v in val.items() if v[1] and v[1] > 0}
    tsmc = {ym: 100.0 * v[3] / v[2] for ym, v in val.items() if v[2]}
    lp = D.get("tw_lppls") or {}
    I = {"cal": cal, "px": px, "pm": pm, "lr": lr, "fuel_raw": fuel, "fuel": expanding_pct_span(fuel, BS.FUEL_MIN_MONTHS["tw"]),
         "fuel_rel": REL, "val": None, "val_raw": None,
         "ref": {"pe": pe, "tsmc": tsmc, "lppls": {d: v[0] - v[1] for d, v in lp.items() if v and len(v) >= 2}}}
    I["fund"] = fund_ratios("tw", I, D)
    return I


def us_inputs(D: dict) -> dict:
    """美股四個指數共用的長歷史（CPI 補缺月）、估值（只給 S&P 500）、槓桿（家計證券融資年增率）。"""
    from . import heatcalc as C
    from . import heatcalc_us as HU
    from . import heatbubble as HB
    from . import heatspec_us as U
    L = dict(HU.long_monthly(D))
    L["cpi"] = fill_cpi(L["cpi"])
    cp = HU.cape(L)
    bf, tq = HU.z1_ratios(D, L)
    raw = {"X6": cp, "X8": HB.detrended_pct(bf, BS.TREND["min"]), "X9": HB.detrended_pct(tq, BS.TREND["min"])}
    sc = HU.col(D.get("us_z1") or {}, 2)
    s5 = {ym: C.yoy(sc, ym) for ym in sc if C.yoy(sc, ym) is not None}
    rsp, spy = D.get("us_rsp") or {}, D.get("us_spy") or {}
    rs = {d: rsp[d] / spy[d] for d in rsp if rsp[d] and spy.get(d)}
    return {"L": L, "val_raw": raw, "val": {k: expanding_pct_span(v, BS.VAL_MIN_MONTHS) for k, v in raw.items()},
            "fuel_raw": s5, "fuel": expanding_pct_span(s5, BS.FUEL_MIN_MONTHS["us"]), "fuel_rel": U.RELEASE["S5"],
            "ecy": HU.ecy(L, cp), "rsp_spy": rs}


def us_index_inputs(D: dict, S: dict, idx: str) -> dict:
    from . import heatcalc_bub as CB
    ser = D.get(f"us_px_{idx}") or {}
    cal = sorted(d for d, v in ser.items() if v)
    px = [ser[d] for d in cal]
    L = S["L"]
    pm = L["p"] if idx == "spx" else CB.month_avg_px(dict(zip(cal, px)), cal[-1])
    lp = D.get(f"us_lppls_{idx}") or {}
    on = idx in BS.VAL_MARKETS
    ref = {"lppls": {d: v[0] - v[1] for d, v in lp.items() if v and len(v) >= 2}}
    if idx == "spx":
        ref.update({"ecy": S["ecy"], "rsp_spy": S["rsp_spy"]})
    I = {"cal": cal, "px": px, "pm": pm, "lr": CB.real_log(pm, L["cpi"], BS.PSY["cpi_lag"]), "L": L,
         "fuel_raw": S["fuel_raw"], "fuel": S["fuel"], "fuel_rel": S["fuel_rel"],
         "val": S["val"] if on else None, "val_raw": S["val_raw"] if on else None, "ref": ref}
    I["fund"] = fund_ratios(idx, I, D)
    return I


# ── 每月的條件與等級 ───────────────────────────────────────────────────────

def conditions(I: dict, T: dict) -> dict:
    """I＝tw_inputs／us_index_inputs 的結果 → 每個月底（最後一個交易日）的條件與等級，以及算條件用的月資料。
    每個條件是 True／False／None（None＝資料還不夠，分級時當作不成立）。"""
    from . import heat as H
    from . import heatbubble as HB
    cal, px = I["cal"], I["px"]
    me = month_end_idx(cal)
    dates = [cal[i] for i in me]
    R = psy_drift(I["lr"], T)
    p1m = p1_flags(R)
    z, _ = HB.trend_z(I["lr"], BS.TREND["min"])
    ru, dist, f2 = p2_daily(px)
    p1 = H.asof_monthly(dates, p1m, REL)
    p3z = H.asof_monthly(dates, z, REL)
    fu = H.asof_monthly(dates, I["fuel"], I["fuel_rel"]) if I["fuel"] else [None] * len(dates)
    va = {k: H.asof_monthly(dates, v, REL) for k, v in (I["val"] or {}).items()}
    EF = e_flags(I.get("fund") or {}, T)
    ea = [H.asof_monthly(dates, v["f"], REL) for v in EF.values()]
    rows = []
    for j, i in enumerate(me):
        P1 = p1[j]
        P2 = f2[i]
        P3 = None if p3z[j] is None else p3z[j] >= BS.TREND_Z
        V = None
        if va:
            have = [va[k][j] for k in BS.VAL_ITEMS if k in va and va[k][j] is not None]
            if have:
                need = BS.VAL_NEED if len(have) >= 2 else 1
                V = sum(1 for x in have if x >= BS.VAL_PCT) >= need
        F = None if fu[j] is None else fu[j] >= BS.FUEL_PCT
        es = [e[j] for e in ea if e[j] is not None]
        E = (any(es)) if es else None
        p = sum(1 for x in (P1, P2, P3) if x)
        rows.append({"d": dates[j], "P1": P1, "P2": P2, "P3": P3, "E": E, "V": V, "F": F,
                     "L": BS.level2(p > 0, bool(E), bool(V), bool(F)), "L1": BS.level(p, bool(V), bool(F))})
    return {"rows": rows, "me": me, "R": R, "z": z, "ru": ru, "dist": dist, "f2": f2, "EF": EF}


# ── 現在的狀態、歷史、泡沫段 ─────────────────────────────────────────────────

def _latest(ser: dict, day: str, rel: tuple) -> tuple[str | None, object]:
    """月資料 {YYYY-MM: 值} 在 day 當下拿得到的最新一個月與值。"""
    from . import heat as H
    best = None
    for ym, v in ser.items():
        if v is None or H.avail_date(ym, rel) > day:
            continue
        if best is None or ym > best:
            best = ym
    return (best, ser[best]) if best else (None, None)


def status(I: dict, C: dict) -> dict:
    """最後一個交易日的五個條件（含讀數）與等級。"""
    cal = I["cal"]
    day = cal[-1]
    ym1, r1 = _latest(C["R"], day, REL)
    run = 0
    if ym1:
        while (C["R"].get(_ym_add(ym1, -run)) or {}).get("hit"):
            run += 1
    P1 = None if not ym1 else run >= BS.PSY_RUN
    ym3, z = _latest(C["z"], day, REL)
    P3 = None if z is None else z >= BS.TREND_Z
    P2 = C["f2"][-1]
    out = {"d": day, "P1": P1, "P2": P2, "P3": P3,
           "p1": None if not ym1 else {"ym": ym1, "s": r1["s"], "q95": r1["q95"], "x": r1["x"], "g": r1["g"], "run": run},
           "p2": {"ru": C["ru"][-1], "dist": C["dist"][-1]}, "p3": {"ym": ym3, "z": z}}
    V = None
    if I["val"]:
        items = {}
        for k in BS.VAL_ITEMS:
            ym, p = _latest(I["val"].get(k) or {}, day, REL)
            if p is not None:
                items[k] = {"ym": ym, "pct": p, "raw": (I["val_raw"].get(k) or {}).get(ym)}
        if items:
            need = BS.VAL_NEED if len(items) >= 2 else 1
            V = sum(1 for v in items.values() if v["pct"] >= BS.VAL_PCT) >= need
        out["v"] = items
    F = None
    if I["fuel"]:
        ym, p = _latest(I["fuel"], day, I["fuel_rel"])
        if p is not None:
            F = p >= BS.FUEL_PCT
            out["f"] = {"ym": ym, "pct": p, "raw": I["fuel_raw"].get(ym)}
    if I.get("fuel_raw"):
        ymr, raw = _latest(I["fuel_raw"], day, I["fuel_rel"])
        out.setdefault("f", {"ym": ymr, "pct": None, "raw": raw})
    out["V"], out["F"] = V, F
    E, ei = None, {}
    for k, ef in (C.get("EF") or {}).items():
        ym, r = _latest(ef["R"], day, REL)
        if not ym:
            continue
        run = 0
        while (ef["R"].get(_ym_add(ym, -run)) or {}).get("hit"):
            run += 1
        fr = I["fund"][k]
        ei[k] = {"ym": ym, "s": r["s"], "q95": r["q95"], "g": r["g"], "run": run, "r": math.exp(fr["lr"][ym]),
                 "dec": decomp(fr, ym), "cyc": cyc_z(I, k, ym)}
        E = (E or False) or run >= BS.E_RUN
    out["e"], out["E"] = ei, E
    p = sum(1 for x in (P1, P2, P3) if x)
    out["L"] = BS.level2(p > 0, bool(E), bool(V), bool(F))
    out["L1"] = BS.level(p, bool(V), bool(F))
    return out


def decomp(fr: dict, ym: str) -> dict | None:
    """兩年拆解（只描述）：ym 與 SPLIT_MONTHS 個月前的價格、基本面、比值變化 %。"""
    a = _ym_add(ym, -BS.SPLIT_MONTHS)
    p, f = fr["p"], fr["f"]
    if not (p.get(ym) and p.get(a) and ym in f and a in f and f[a][1]):
        return None
    pc, fc = p[ym] / p[a] - 1.0, f[ym][1] / f[a][1] - 1.0
    return {"a": a, "p": 100.0 * pc, "f": 100.0 * fc, "r": 100.0 * ((1.0 + pc) / (1.0 + fc) - 1.0), "fa": f[a][0], "fz": f[ym][0]}


def cyc_z(I: dict, k: str, ym: str) -> dict | None:
    """景氣高峰參考（只描述）：基本面（平滑後、取對數）從有資料起到 ym 那個月用的那一期，比長期趨勢高幾個標準差
    （擴張視窗 OLS、至少 TREND["min"] 個月；企業獲利是季資料，至少 80 季）。台股本益比的淨利只有 2013 起，不算。"""
    from . import heatbubble as HB
    fr = I["fund"][k]
    raw = fr.get("raw")
    last = (fr["f"].get(ym) or (None, None))[0]
    if not raw or not last:
        return None
    M = {per: math.log(v) for per, v in raw.items() if per <= last and v and v > 0}
    z, _ = HB.trend_z(M, BS.TREND["min"] if k != "cp" else BS.TREND["min"] // 3)
    return {"per": last, "z": z[last]} if last in z else None


def _mno(d: str) -> int:
    return int(d[:4]) * 12 + int(d[5:7])


def episodes(rows: list, cal: list[str], px: list, me: list[int], min_level: int = 3) -> list[dict]:
    """等級 ≥ min_level 的段（中間隔 ≥ BUB_EPI_GAP 個月才算新的一段）：起訖月、月數、最高等級、出現過的條件、
    段內最高收盤與日期、之後 504 個交易日內的最低收盤與跌幅（資料不夠 504 天的標 open）。"""
    from . import heatbubble as HB
    flags = [r["L"] >= min_level for r in rows]
    out = []
    for a, b in HB.episodes([_mno(r["d"]) for r in rows], flags):
        lo_i = me[a - 1] + 1 if a > 0 else 0
        hi_i = me[b]
        k = max(range(lo_i, hi_i + 1), key=lambda i: px[i] or 0)
        end = min(len(px) - 1, k + BS.BUB_DD[1][0])
        m = min(range(k, end + 1), key=lambda i: px[i] or float("inf"))
        seg = [r for r in rows[a:b + 1] if r["L"] >= min_level]
        out.append({"a": rows[a]["d"][:7], "z": rows[b]["d"][:7], "n": len(seg), "max": max(r["L"] for r in seg),
                    "cond": [c for c in CONDS if any(r.get(c) for r in seg)],
                    "peak": {"d": cal[k], "px": px[k]}, "low": {"d": cal[m], "px": px[m]},
                    "dd": 100.0 * (px[m] / px[k] - 1.0), "open": k + BS.BUB_DD[1][0] >= len(px)})
    return out


def history(rows: list, px: list, me: list[int]) -> dict:
    """頁面用：從第一個算得出 P1 的月份起，每月的等級、條件（緊湊字串）與月底收盤。"""
    j0 = next((j for j, r in enumerate(rows) if r["P1"] is not None), None)
    if j0 is None:
        return {"d": [], "L": [], "c": [], "p": []}
    J = range(j0, len(rows))
    code = lambda r: "".join(c for c, k in (("1", "P1"), ("2", "P2"), ("3", "P3"), ("e", "E"), ("v", "V"), ("f", "F"))  # noqa: E731
                             if r.get(k))
    return {"d": [rows[j]["d"][:7] for j in J], "L": [rows[j]["L"] for j in J], "c": [code(rows[j]) for j in J],
            "p": [round(px[me[j]], 2) for j in J]}


def refs_now(I: dict) -> dict:
    """參考讀數（不進分級）的最新值：LPPLS（正 − 負泡沫信心 %）、上漲加速度、台股本益比與台積電占比、美股超額 CAPE 殖利率與 RSP ÷ SPY 一年變化。"""
    from . import heatbubble as HB
    cal, px = I["cal"], I["px"]
    day = cal[-1]
    out: dict = {}
    lp = I["ref"].get("lppls") or {}
    if lp:
        d = max(lp)
        out["lppls"] = {"d": d, "v": lp[d]}
    ac = HB.accel(px, BS.RUNUP_DAYS, 126)
    if ac and ac[-1] is not None:
        out["acc"] = {"d": day, "v": ac[-1]}
    for k in ("pe", "tsmc", "ecy"):
        ser = I["ref"].get(k) or {}
        ym, v = _latest(ser, day, REL)
        if v is not None:
            out[k] = {"d": ym, "v": v}
    rs = I["ref"].get("rsp_spy") or {}
    ds = sorted(rs)
    if len(ds) > 250:
        out["rsp"] = {"d": ds[-1], "v": 100.0 * (rs[ds[-1]] / rs[ds[-251]] - 1.0)}
    return out


def market(mk: str, I: dict, T: dict) -> dict:
    C = conditions(I, T)
    return {"name": BS.NAMES[mk], "index": BS.INDEX_NAMES[mk], "now": status(I, C), "hist": history(C["rows"], I["px"], C["me"]),
            "ref": refs_now(I),
            "epi": episodes(C["rows"], I["cal"], I["px"], C["me"]),
            "_C": C}


def compute(T: dict | None = None, Dtw: dict | None = None, Dus: dict | None = None) -> dict:
    """五個市場的現在狀態、歷史等級、泡沫段（每天建頁用；不跑驗證）。"""
    T = T or load_cv_table()
    if not T:
        return {}
    Dtw = Dtw if Dtw is not None else load_tw()
    Dus = Dus if Dus is not None else load_us()
    out = {"ver": BS.VER, "tw": market("tw", tw_inputs(Dtw), T)}
    S = us_inputs(Dus)
    for idx in ("spx", "ixic", "ndx", "sox"):
        out[idx] = market(idx, us_index_inputs(Dus, S, idx), T)
    return out


# ── 驗證（研究時跑；scripts/run_bub.py） ────────────────────────────────────

RESEARCH = "data/lab/bub_research.json"


def _flag_x(rows: list, J: range, t: str) -> list:
    if t in ("L2", "L3"):
        lv = int(t[1])
        return [100.0 if rows[j]["L"] >= lv else 0.0 for j in J]
    if t == "L4":
        return [100.0 if rows[j]["L"] == 4 else 0.0 for j in J]
    if t == "L3v1":
        return [100.0 if rows[j]["L1"] >= 3 else 0.0 for j in J]
    if t in ("PF", "PN"):                               # 價格過熱而且（PF）／但沒有（PN）漲得比基本面快
        out = []
        for j in J:
            r = rows[j]
            price = bool(r["P1"] or r["P2"] or r["P3"])
            fund = bool(r.get("E") or r.get("V"))
            out.append(100.0 if price and (fund if t == "PF" else not fund) else 0.0)
        return out
    return [None if rows[j].get(t) is None else (100.0 if rows[j][t] else 0.0) for j in J]


def _mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def validate(rows: list, dates: list[str], dd: dict, fwd: dict, tests: tuple = BS.TESTS2) -> dict:
    """rows／dates／dd／fwd 是同一批月樣本；每個條件與等級跑 heatbubble.crash_test，另加平均報酬（只描述）。"""
    from . import heatbubble as HB
    J = range(len(rows))
    out: dict = {"a": dates[0][:7], "z": dates[-1][:7], "n": len(dates)}
    for t in tests:
        x = _flag_x(rows, J, t)
        if all(v is None for v in x) or not any(v for v in x if v is not None):
            out[t] = {"n_hot": 0}
            continue
        r = HB.crash_test(dates, x, dd)
        for h, _ in BS.BUB_DD:
            r[str(h)]["ret_hot"] = _mean([f for f, v in zip(fwd[h], x) if v is not None and v >= 80])
            r[str(h)]["ret_all"] = _mean([f for f, v in zip(fwd[h], x) if v is not None])
        r["share"] = 100.0 * sum(1 for v in x if v) / sum(1 for v in x if v is not None)
        out[t] = r
    out["dist"] = {str(lv): 100.0 * sum(1 for r in rows if r["L"] == lv) / len(rows) for lv in BS.LEVELS}
    if all("L1" in r for r in rows):
        out["dist1"] = {str(lv): 100.0 * sum(1 for r in rows if r["L1"] == lv) / len(rows) for lv in BS.LEVELS}
    return out


def validate_daily(C: dict, px: list, start: str | None = None) -> dict:
    """主樣本：月底一個樣本，從 P1、P2 都算得出來的第一個月起（start＝另外再要求的起日）；回落、報酬用日收盤、t＋1 起算。"""
    from . import heatbubble as HB
    rows, me = C["rows"], C["me"]
    J = [j for j, r in enumerate(rows) if r["P1"] is not None and r["P2"] is not None and (not start or r["d"] >= start)]
    if not J:
        return {}
    J = list(range(J[0], len(rows)))
    lag = BS.DAILY_LAG
    dd = {h: [HB.max_drawdown(px, me[j] + lag, me[j] + lag + h) for j in J] for h, _ in BS.BUB_DD}
    fwd = {}
    for h, _ in BS.BUB_DD:
        fwd[h] = []
        for j in J:
            a, b = me[j] + lag, me[j] + lag + h
            fwd[h].append(100.0 * (px[b] / px[a] - 1.0) if b < len(px) and px[a] and px[b] else None)
    return validate([rows[j] for j in J], [rows[j]["d"] for j in J], dd, fwd)


def tw_ext(I: dict, T: dict) -> dict:
    """台股延伸樣本（只當穩健度）：國發會月平均 1982 起，訊號用當月讀數，回落用之後第 1 個月起 12、24 個月的月平均。"""
    from . import heatbubble as HB
    from .heatspec import M6_EXT_SHIFT
    pm = I["pm"]
    ks = sorted(k for k, v in pm.items() if v)
    if not ks:
        return {}
    months = [ks[0]]
    while months[-1] < ks[-1]:
        months.append(_ym_add(months[-1], 1))
    pa = [pm.get(m) for m in months]
    R = psy_drift(I["lr"], T)
    p1m = p1_flags(R)
    z, _ = HB.trend_z(I["lr"], BS.TREND["min"])
    ex = (I.get("fund") or {}).get("ex")
    em = e_flags({"ex": ex}, T)["ex"]["f"] if ex else {}
    rows, ath = [], None
    for i, m in enumerate(months):
        v = pa[i]
        if v:
            ath = v if ath is None else max(ath, v)
        P2 = None
        if i >= BS.EXT_RUN_MONTHS and v and pa[i - BS.EXT_RUN_MONTHS]:
            P2 = v / pa[i - BS.EXT_RUN_MONTHS] - 1.0 >= BS.RUN2_PCT / 100.0 and v >= ath * (1.0 - BS.RUN2_ATH)
        P1 = p1m.get(m)
        P3 = None if m not in z else z[m] >= BS.TREND_Z
        E = em.get(m)
        p = sum(1 for x in (P1, P2, P3) if x)
        rows.append({"d": f"{m}-28", "P1": P1, "P2": P2, "P3": P3, "E": E, "V": None, "F": None,
                     "L": BS.level2(p > 0, bool(E), False, False), "L1": BS.level(p, False, False)})
    J = [j for j, r in enumerate(rows) if r["P1"] is not None and r["P2"] is not None]
    if not J:
        return {}
    J = list(range(J[0], len(rows)))
    hm = {252: 12, 504: 24}
    sh = M6_EXT_SHIFT
    dd = {h: [HB.max_drawdown(pa, j + sh, j + sh + hm[h]) for j in J] for h, _ in BS.BUB_DD}
    fwd = {h: [100.0 * (pa[j + sh + hm[h]] / pa[j + sh] - 1.0) if j + sh + hm[h] < len(pa) and pa[j + sh]
               and pa[j + sh + hm[h]] else None for j in J] for h, _ in BS.BUB_DD}
    sub = [rows[j] for j in J]
    out = validate(sub, [r["d"] for r in sub], dd, fwd, tests=("P1", "P2", "P3", "E", "PF", "PN", "L2", "L3", "L3v1"))
    # 泡沫段（月平均）
    epi = []
    for a, b in HB.episodes([_mno(r["d"]) for r in sub], [r["L"] >= 3 for r in sub]):
        k = max(range(J[a], J[b] + 1), key=lambda i: pa[i] or 0)
        end = min(len(pa) - 1, k + hm[504])
        m = min(range(k, end + 1), key=lambda i: pa[i] or float("inf"))
        seg = [r for r in sub[a:b + 1] if r["L"] >= 3]
        epi.append({"a": sub[a]["d"][:7], "z": sub[b]["d"][:7], "n": len(seg), "max": max(r["L"] for r in seg),
                    "cond": [c for c in ("P1", "P2", "P3", "E") if any(r.get(c) for r in seg)],
                    "peak": {"d": months[k], "px": pa[k]}, "low": {"d": months[m], "px": pa[m]},
                    "dd": 100.0 * (pa[m] / pa[k] - 1.0), "open": k + hm[504] >= len(pa)})
    out["epi"] = epi
    code = lambda r: "".join(c for c, k in (("1", "P1"), ("2", "P2"), ("3", "P3"), ("e", "E")) if r.get(k))  # noqa: E731
    out["hist"] = {"d": [r["d"][:7] for r in sub], "L": [r["L"] for r in sub], "c": [code(r) for r in sub],
                   "p": [None if not pa[j] else round(pa[j], 2) for j in J]}      # 月平均（頁面畫虛線）
    return out


def research(T: dict | None = None, Dtw: dict | None = None, Dus: dict | None = None) -> dict:
    """五個市場的驗證（主樣本＋S&P 500 1950 起＋台股延伸樣本）。"""
    from . import heatbubble as HB
    T = T or load_cv_table()
    if not T:
        raise SystemExit("沒有 PSY 漂移臨界值表：先跑 scripts/run_bub.py --cv")
    Dtw = Dtw if Dtw is not None else load_tw()
    Dus = Dus if Dus is not None else load_us()
    out: dict = {"ver": BS.VER, "spec_date": BS.SPEC_DATE, "cp_src": cp_source()}
    It = tw_inputs(Dtw)
    Ct = conditions(It, T)
    out["tw"] = {"main": validate_daily(Ct, It["px"]), "ext": tw_ext(It, T)}
    S = us_inputs(Dus)
    for idx in ("spx", "ixic", "ndx", "sox"):
        I = us_index_inputs(Dus, S, idx)
        C = conditions(I, T)
        out[idx] = {"main": validate_daily(C, I["px"])}
        if idx == "spx":
            out[idx]["robust"] = validate_daily(C, I["px"], start=BS.SPX_ROBUST_START)
    return HB._rnd(out)


def cp_source() -> str | None:
    """美國企業獲利用的是哪一條（抓取時寫在檔案的來源標籤）。"""
    from . import store
    return (store.read(HD.KIND, "us_cp") or {}).get("src")


def save_research(R: dict) -> bool:
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / RESEARCH
    txt = json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.write_text(txt, encoding="utf-8")
    return True


def load_research() -> dict | None:
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / RESEARCH
    try:
        R = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == BS.VER else None


# ── 每天建頁：景氣頁先算、泡沫頁沿用（同一個程序） ──────────────────────────────

_CACHE: dict = {}


def _cached(key, D, fn):
    hit = _CACHE.get(key)
    if hit is not None and hit[0] is D:
        return hit[1]
    v = fn()
    _CACHE[key] = (D, v)
    _CACHE[("last",) + key[1:]] = v
    return v


def market_for(mk: str, D: dict) -> dict | None:
    """mk＝tw／spx／ixic／ndx／sox；D＝景氣頁已經載入的原始資料（heatcalc.load／heatcalc_us.load）。"""
    T = _cached(("T",), None, load_cv_table)
    if not T:
        return None
    if mk == "tw":
        return _cached(("m", mk), D, lambda: market(mk, tw_inputs(D), T))
    S = _cached(("us",), D, lambda: us_inputs(D))
    return _cached(("m", mk), D, lambda: market(mk, us_index_inputs(D, S, mk), T))


def now_for(mk: str, D: dict) -> dict | None:
    r = market_for(mk, D)
    if not r:
        return None
    n = r["now"]
    return {"mk": mk, "L": n["L"], "cond": [c for c in CONDS if n.get(c)], "d": n["d"]}


def last(mk: str) -> dict | None:
    """這個程序裡最近一次算好的市場結果（泡沫頁建頁時沿用景氣頁算過的）。"""
    return _CACHE.get(("last", mk))


def clear_cache() -> None:
    _CACHE.clear()
