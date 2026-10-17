"""景氣溫度頁：把 data/lab/heat 的原始資料組成各指標、熱度、總分與驗證（docs/lab_heat_plan.md 第 3～5、10 節；規格 heatspec）。

研究（scripts/run_heat.py → data/lab/heat_research.json）和每天建頁共用這一支，同一套算法：
  · 交易日曆與加權指數：證交所 FMTQIK（官方收盤）為主，官方沒有的月份用 Yahoo ^TWII；
  · 日資料指標先在「來源自己的日期」上算（例如 60 個交易日前），再對齊台灣交易日（美國資料晚一天才用）；
  · 月資料指標在月序列上算百分位（和過去 120 個月比），到公布日才算拿得到；
  · 驗證：日資料每天一個樣本；長線每月最後一個交易日一個樣本（區塊長度＝持有期間換算成月數）。
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from . import heat as H
from . import heatdata as HD
from . import heatspec as S

FILES = ["margin", "inst", "futi", "opti", "mtxoi", "pcr", "vixtw", "taiex", "vix", "hyg", "ief", "turnover",
         "usdtwd", "money", "ndc", "pmi", "orders", "twcpi", "effr", "uscpi", "ust", "breadth"]
DAILY = [k for k in S.KEYS if S.LINES[S.LINE_OF[k]]["freq"] == "d"]
MONTHLY = [k for k in S.KEYS if S.LINES[S.LINE_OF[k]]["freq"] == "m"]
MONTH_AVG_MIN = 10          # 日資料取當月平均：當月至少 10 天有值


def load() -> dict:
    return {n: HD.load(n) for n in FILES}


# ── 交易日曆與加權指數 ───────────────────────────────────────────────

def calendar(D: dict) -> tuple[list[str], list[float], dict]:
    off = {d: v[1] for d, v in (D.get("turnover") or {}).items() if v and len(v) > 1 and v[1]}
    yh = {d: v for d, v in (D.get("taiex") or {}).items() if v}
    have = {d[:7] for d in off}
    cal = sorted(set(off) | {d for d in yh if d[:7] not in have})
    px = [off.get(d) or yh.get(d) for d in cal]
    both = [abs(off[d] / yh[d] - 1) for d in off if d in yh]
    info = {"days": len(cal), "official": sum(1 for d in cal if d in off), "first": cal[0] if cal else None,
            "last": cal[-1] if cal else None,
            "yahoo_vs_official_max_pct": round(100 * max(both), 3) if both else None,
            "yahoo_vs_official_med_pct": round(100 * sorted(both)[len(both) // 2], 4) if both else None}
    return cal, px, info


# ── 小工具 ───────────────────────────────────────────────────────────

def native(ser: dict, fn) -> dict:
    """在來源自己的日期序列上算（例如「60 個交易日前」），回 {日期: 值}。"""
    ks = sorted(k for k, v in ser.items() if v is not None)
    out = fn([ser[k] for k in ks])
    return {k: v for k, v in zip(ks, out) if v is not None}


def rel_ma(xs: list, k: int) -> list:
    m = H.roll_mean(xs, k)
    return [100.0 * (x / a - 1.0) if x is not None and a else None for x, a in zip(xs, m)]


def ratio_sum(cal: list[str], a: dict, b: dict, k: int) -> list:
    """a 的 k 日合計 ÷ b 的 k 日合計（%），只用兩邊都有值的日子；k 天裡至少 max(k−2, ⌈0.9k⌉) 天有值。"""
    pa = [a.get(d) for d in cal]
    pb = [b.get(d) for d in cal]
    need = max(k - 2, math.ceil(0.9 * k))
    out: list = [None] * len(cal)
    for i in range(k - 1, len(cal)):
        sa = sb = 0.0
        n = 0
        for j in range(i - k + 1, i + 1):
            if pa[j] is not None and pb[j]:
                sa += pa[j]
                sb += pb[j]
                n += 1
        if n >= need and sb:
            out[i] = 100.0 * sa / sb
    return out


def ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def month_avg(ser: dict, min_n: int = MONTH_AVG_MIN) -> dict:
    acc: dict[str, list] = {}
    for d, v in ser.items():
        if v is not None:
            acc.setdefault(d[:7], []).append(v)
    return {ym: sum(v) / len(v) for ym, v in acc.items() if len(v) >= min_n}


def yoy(ser: dict, ym: str) -> float | None:
    a, b = ser.get(ym), ser.get(ym_add(ym, -12))
    return 100.0 * (a / b - 1.0) if a is not None and b else None


# ── 期貨選擇權（FinMind 法人未平倉） ────────────────────────────────────

FOREIGN = "外資"


def f1_foreign_fut(futi: dict) -> dict:
    """外資大台＋小台 ÷ 4＋微台 ÷ 20 的未平倉淨額（大台口數）；大台、小台都要有，微台上市前算 0。"""
    out = {}
    for d, v in futi.items():
        tx, mtx, tmf = ((v.get(c) or {}).get(FOREIGN) for c in ("TX", "MTX", "TMF"))
        if tx and mtx:
            out[d] = (tx[0] - tx[1]) + (mtx[0] - mtx[1]) / 4 + ((tmf[0] - tmf[1]) / 20 if tmf else 0)
    return out


def f2_retail_mtx(futi: dict, mtxoi: dict) -> dict:
    """（法人小台空單 − 法人小台多單）÷ 小台全市場未平倉（%）；三類法人都要有。"""
    out = {}
    for d, v in futi.items():
        m, oi = v.get("MTX") or {}, mtxoi.get(d)
        if len(m) >= 3 and oi:
            out[d] = 100.0 * (sum(x[1] for x in m.values()) - sum(x[0] for x in m.values())) / oi
    return out


def f3_foreign_opt(opti: dict) -> dict:
    """外資買權未平倉淨金額 − 賣權未平倉淨金額（千元 → 億元）。"""
    out = {}
    for d, v in opti.items():
        c, p = (v.get("買權") or {}).get(FOREIGN), (v.get("賣權") or {}).get(FOREIGN)
        if c and p:
            out[d] = ((c[0] - c[1]) - (p[0] - p[1])) / 1e5
    return out


# ── 各指標原始值 ─────────────────────────────────────────────────────

US = {"S5", "M7", "M8"}                     # 美國資料：台灣 t 日只能用美國 t 日以前的收盤


def native_daily(D: dict, cal: list[str], px: list) -> dict[str, dict]:
    """各日資料指標在「來源自己的日期」上的值 {指標: {日期: 值}}（買賣超比、加權指數類直接在台灣交易日上算）。"""
    N: dict[str, dict] = {}
    on_cal = lambda xs: {d: v for d, v in zip(cal, xs) if v is not None}   # noqa: E731
    mg = {d: v[0] for d, v in (D.get("margin") or {}).items() if v and v[0]}
    N["S1"] = native(mg, lambda v: H.chg(v, 5))
    N["M4"] = native(mg, lambda v: H.chg(v, 60))
    inst = D.get("inst") or {}
    tot = {d: v["total"] for d, v in inst.items() if v.get("total") is not None}
    fx = {d: sum(x for n, x in v.items() if n.startswith("Foreign")) for d, v in inst.items()
          if any(n.startswith("Foreign") for n in v)}
    to = {d: v[0] for d, v in (D.get("turnover") or {}).items() if v and v[0]}
    N["S3"] = on_cal(ratio_sum(cal, tot, to, 5))
    N["M5"] = on_cal(ratio_sum(cal, fx, to, 60))
    br = D.get("breadth") or {}
    bk = sorted(br)
    bi = HD.breadth_ind({"cal": bk, **{f: [br[d][j] for d in bk]
                                       for j, f in enumerate(("adv", "dec", "above", "n60", "hi", "lo", "n250"))}})
    for k in ("S2", "M2", "M3"):
        N[k] = bi[k]
    N["S4"] = on_cal(H.roll_std_ret(px, 20))
    N["S6"] = on_cal(rel_ma(px, 20))
    N["M1"] = on_cal(rel_ma(px, 120))
    vix = D.get("vix") or {}
    N["S5"] = native(vix, lambda v: rel_ma(v, 50))
    N["M8"] = dict(vix)
    pc = {d: v[2] for d, v in (D.get("pcr") or {}).items() if v and v[2] is not None}
    N["S7"] = native(pc, lambda v: H.roll_mean(v, 5))
    N["F1"] = f1_foreign_fut(D.get("futi") or {})
    N["F2"] = f2_retail_mtx(D.get("futi") or {}, D.get("mtxoi") or {})
    N["F3"] = f3_foreign_opt(D.get("opti") or {})
    N["F4"] = dict(D.get("vixtw") or {})
    N["M6"] = native(D.get("usdtwd") or {}, lambda v: H.chg(v, 60))
    hy, ie = D.get("hyg") or {}, D.get("ief") or {}
    rat = {d: hy[d] / ie[d] for d in hy if ie.get(d)}
    N["M7"] = native(rat, lambda v: H.chg(v, 60))
    return N


def raw_daily(D: dict, cal: list[str], px: list, N: dict | None = None) -> dict[str, list]:
    """對齊台灣交易日：沿用最近一筆（超過 7 個日曆天算缺；廣度 4 天）；美國資料晚一天才用。"""
    N = N if N is not None else native_daily(D, cal, px)
    return {k: H.asof_daily(cal, N[k], after=k in US, stale=4 if k in ("S2", "M2", "M3") else 7) for k in N}


def raw_monthly(D: dict) -> dict[str, dict]:
    M: dict[str, dict] = {}
    ndc = D.get("ndc") or {}
    M["L1"] = {ym: v[6] for ym, v in ndc.items() if v[6] is not None}
    M["L2"] = {ym: v[1] - ndc[ym_add(ym, -6)][1] for ym, v in ndc.items()
               if v[1] is not None and (ndc.get(ym_add(ym, -6)) or [None, None])[1] is not None}
    M["L3"] = dict(D.get("pmi") or {})
    od = D.get("orders") or {}

    def s3(ym):
        xs = [od.get(ym_add(ym, -j)) for j in range(3)]
        return sum(xs) if all(x is not None for x in xs) else None
    M["L4"] = {ym: 100.0 * (s3(ym) / s3(ym_add(ym, -12)) - 1.0) for ym in od if s3(ym) and s3(ym_add(ym, -12))}
    mo = D.get("money") or {}

    def myoy(ym, j):                       # 央行公布的年增率；沒有（最早 12 個月）就自己算
        v = mo.get(ym)
        if v and v[j + 1] is not None:
            return v[j + 1]
        return yoy({k: x[j] for k, x in mo.items() if x[j]}, ym)
    M["L5"] = {ym: myoy(ym, 0) - myoy(ym, 2) for ym in mo if myoy(ym, 0) is not None and myoy(ym, 2) is not None}
    tc = D.get("twcpi") or {}
    idx = {k: v[0] for k, v in tc.items() if v[0]}
    M["L6"] = {ym: (v[1] if v[1] is not None else yoy(idx, ym)) for ym, v in tc.items()
               if v[1] is not None or yoy(idx, ym) is not None}
    ff = month_avg(D.get("effr") or {})
    M["L7"] = {ym: v - ff[ym_add(ym, -12)] for ym, v in ff.items() if ym_add(ym, -12) in ff}
    cpi = D.get("uscpi") or {}
    M["L8"] = {ym: yoy(cpi, ym) for ym in cpi if yoy(cpi, ym) is not None}
    sp = {d: v[2] - v[1] for d, v in (D.get("ust") or {}).items() if v and v[1] is not None and v[2] is not None}
    M["L9"] = month_avg(sp)
    return M


# ── 熱度 ─────────────────────────────────────────────────────────────

def build(D: dict | None = None) -> dict:
    """→ {"cal", "px", "cal_info", "raw": {k: 逐日值}, "heat": {k: 逐日 0～100}, "ym": {k: 逐日用到的月份},
    "mraw": {k: 月序列}, "nat": {k: 來源日期上的值}}"""
    D = D if D is not None else load()
    cal, px, info = calendar(D)
    N = native_daily(D, cal, px)
    raw = raw_daily(D, cal, px, N)
    heat = {k: [H.to_heat(p, S.HOT[k]) for p in H.pct_series(raw[k], S.PCT_WIN["d"], S.PCT_MIN["d"])] for k in DAILY}
    M = raw_monthly(D)
    ymu: dict[str, list] = {}
    for k in MONTHLY:
        ks = sorted(M[k])
        p = H.pct_series([M[k][x] for x in ks], S.PCT_WIN["m"], S.PCT_MIN["m"])
        hm = {ym: H.to_heat(x, S.HOT[k]) for ym, x in zip(ks, p) if x is not None}
        heat[k] = H.asof_monthly(cal, hm, S.RELEASE[k])
        raw[k] = H.asof_monthly(cal, M[k], S.RELEASE[k])
        ymu[k] = H.asof_monthly(cal, {ym: ym for ym in M[k]}, S.RELEASE[k])
    return {"cal": cal, "px": px, "cal_info": info, "raw": raw, "heat": heat, "ym": ymu, "mraw": M, "nat": N, "D": D}


def composite_series(heat: dict, inc: list[str], n: int) -> list:
    return [H.composite({k: heat[k][i] for k in inc}, inc) for i in range(n)]


# ── 驗證（第 5 節） ───────────────────────────────────────────────────

def sample_idx(cal: list[str], line: str) -> list[int]:
    """日資料：每個交易日；長線（月）：每月最後一個交易日。"""
    if S.LINES[line]["freq"] != "m":
        return list(range(len(cal)))
    return [i for i in range(len(cal)) if i == len(cal) - 1 or cal[i + 1][:7] != cal[i][:7]]


def split_key(line: str) -> str:
    return "fo" if line == "fo" else S.LINES[line]["freq"]


def _in(d: str, rng: tuple) -> bool:
    a, z = rng
    return (a is None or d >= a) and (z is None or d <= z)


def _r(x, k=3):
    return None if x is None else round(x, k)


def evaluate(x: list, px: list, cal: list[str], line: str) -> dict:
    """x＝逐日熱度（某指標或總分）→ {持有天數: {"is", "oos": {n, rho, lo, hi, a, z, bands}, "verdict", "dir"}}。
    判定與方向用沒有四捨五入的數字；輸出才取位數。"""
    L = S.LINES[line]
    sp = S.SPLIT[split_key(line)]
    min_is, min_oos = S.MIN_SAMPLE[split_key(line)]
    idx = sample_idx(cal, line)
    out = {}
    for h in L["fwd"]:
        block = h if L["freq"] == "d" else max(1, round(h / 21))
        rows: dict[str, list] = {"is": [], "oos": []}
        for i in idx:
            if x[i] is None:
                continue
            r, dd = H.fwd(px, i, h)
            if r is None:
                continue
            for part in ("is", "oos"):
                if _in(cal[i], sp[part]):
                    rows[part].append((x[i], r, dd, cal[i]))
        res: dict = {}
        raw: dict = {}
        for part, rr in rows.items():
            xs, ys, ds = [a for a, *_ in rr], [b for _, b, *_ in rr], [c for _, _, c, _ in rr]
            rho, lo, hi = H.spearman_ci(xs, ys, block)
            raw[part] = (rho, lo, hi, len(rr))
            res[part] = {"n": len(rr), "rho": _r(rho), "lo": _r(lo), "hi": _r(hi),
                         "a": rr[0][3] if rr else None, "z": rr[-1][3] if rr else None,
                         "bands": H.bands(xs, ys, ds)}
        (ir, il, ih, inn), (orh, _, _, onn) = raw["is"], raw["oos"]
        res["verdict"] = H.verdict(ir, il, ih, orh, inn, onn, min_is, min_oos)
        res["dir"] = H.is_dir(il, ih) if inn >= min_is else 0
        res["block"] = block
        out[h] = res
    return out


def research(B: dict | None = None) -> dict:
    """全部指標與各線總分的驗證＋納入規則（第 4 節第 3 點，只看樣本內、主要持有期間）。"""
    B = B if B is not None else build()
    cal, px, heat = B["cal"], B["px"], B["heat"]
    D = B["D"]
    lines = {}
    for ln, L in S.LINES.items():
        keys = [k for k in S.KEYS if S.LINE_OF[k] == ln]
        items = {k: evaluate(heat[k], px, cal, ln) for k in keys}
        first = {k: next((cal[i] for i, v in enumerate(heat[k]) if v is not None), None) for k in keys}
        dirs = {k: items[k][L["main"]]["dir"] for k in keys}
        d, inc = H.select(dirs)
        comp = evaluate(composite_series(heat, inc, len(cal)), px, cal, ln) if inc else None
        lines[ln] = {"dir": d, "inc": inc, "items": items, "first": first, "comp": comp}
    data = {}
    for n in FILES:
        ks = sorted(D.get(n) or {})
        data[n] = [len(ks), ks[0] if ks else None, ks[-1] if ks else None]
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cal": B["cal_info"], "data": data, "lines": lines}
