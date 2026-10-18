"""景氣溫度頁：把 data/lab/heat 的原始資料組成各項、0～100、面向總分與驗證
（docs/lab_heat_plan.md 第 12、13 節；規格 heatspec VER 4、實作細節第 12.7、13.9 節）。

研究（scripts/run_heat.py → data/lab/heat_research.json）和每天建頁共用這一支，同一套算法：
  · 交易日曆與加權指數：證交所 FMTQIK（官方收盤）為主，官方沒有的月份用 Yahoo ^TWII；
  · 日資料先在「來源自己的日期」上算（例如 60 個交易日前），再對齊台灣交易日（美國資料晚一天才用）；
  · 月資料在月序列上算百分位（和過去 120 個月比），到公布日才算拿得到；
  · 面向總分＝該面向全部項目等權平均（有值的項數 ≥ 2/3；台指 VIX 用美國 VIX 代替的日子不算進去）；
  · 驗證：全期間等級相關＋信賴區間、前後兩半、五段統計；基本面每月最後一個交易日一個樣本，其他每天一個；
  · 關鍵價位與事件（heattech）：事件研究也在 research() 裡算，現在的價位在頁面當天算。
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone

from . import heat as H
from . import heatdata as HD
from . import heatspec as S
from . import heattech as TT
from . import store

FILES = ["margin", "inst", "futi", "opti", "mtxoi", "pcr", "vixtw", "taiex", "vix", "hyg", "ief", "turnover",
         "usdtwd", "money", "ndc", "exports", "pmi", "orders", "twcpi", "effr", "uscpi", "ust", "breadth",
         "mmf", "spx", "qfii", "cbcbank", "sitca", "sfbflow"]
DAILY = [k for k in S.KEYS if S.FREQ_OF[k] == "d"]
MONTHLY = [k for k in S.KEYS if S.FREQ_OF[k] == "m"]
BREADTH = ("T5", "T6", "T7")
MONTH_AVG_MIN = 10          # 日資料取當月平均：當月至少 10 天有值
FIN = "金融保險"             # B6 不算的產業（月營收含投資損益）


def fin_codes() -> set[str]:
    try:
        ind = json.loads((store.ROOT / "data" / "stock_industry.json").read_text(encoding="utf-8")).get("industry") or {}
    except (OSError, ValueError):
        return set()
    return {c for c, v in ind.items() if v == FIN}


def rev_sums(shards, fin: set[str]) -> dict:
    """月營收分片 → {年-月: [營收合計, 去年同期合計, 家數]}（千元）。每家公司：營收 > 0、自己公布的年增率有值且 > −100%；
    去年同期＝營收 ÷（1＋年增率），所以 2012（個體）→ 2013（合併）的口徑改變不會算錯。金融保險不算。"""
    out = {}
    for ym, doc in shards:
        a = b = 0.0
        n = 0
        for c, v in ((doc or {}).get("s") or {}).items():
            if c in fin or not v or len(v) < 2:
                continue
            r, y = v[0], v[1]
            if r is None or y is None or r <= 0 or y <= -100:
                continue
            a += r
            b += r / (1.0 + y / 100.0)
            n += 1
        if n:
            out[ym[:7]] = [a, b, n]
    return out


def load() -> dict:
    D = {n: HD.load(n) for n in FILES}
    D["rev"] = rev_sums(store.load("rev"), fin_codes())
    return D


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


def ma_ratio(xs: list, a: int, b: int) -> list:
    """a 日平均 ÷ b 日平均 − 1（%），兩個平均都要滿天數。"""
    ma, mb = H.roll_mean(xs, a), H.roll_mean(xs, b)
    return [100.0 * (x / y - 1.0) if x is not None and y else None for x, y in zip(ma, mb)]


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


def roll_max(xs: list, k: int) -> list:
    """近 k 天（含今天）最高；k 天都要有值。"""
    out: list = [None] * len(xs)
    for i in range(k - 1, len(xs)):
        w = xs[i - k + 1:i + 1]
        if all(v is not None for v in w):
            out[i] = max(w)
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


def yoy3(ser: dict) -> dict:
    """近 3 個月合計 ÷ 去年同期 3 個月合計 − 1（%），6 個月都要有值。"""
    def s3(ym):
        xs = [ser.get(ym_add(ym, -j)) for j in range(3)]
        return sum(xs) if all(x is not None for x in xs) else None
    out = {}
    for ym in ser:
        a, b = s3(ym), s3(ym_add(ym, -12))
        if a is not None and b:
            out[ym] = 100.0 * (a / b - 1.0)
    return out


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


# ── 各項原始值 ───────────────────────────────────────────────────────

def native_daily(D: dict, cal: list[str], px: list) -> dict[str, dict]:
    """各日資料項目在「來源自己的日期」上的值 {項目: {日期: 值}}（買賣超比、加權指數類直接在台灣交易日上算）。"""
    N: dict[str, dict] = {}
    on_cal = lambda xs: {d: v for d, v in zip(cal, xs) if v is not None}   # noqa: E731
    mgr = D.get("margin") or {}
    mg = {d: v[0] for d, v in mgr.items() if v and v[0]}
    N["C1"] = {d: v / 1e8 for d, v in mg.items()}
    N["C2"] = native(mg, lambda v: H.chg(v, 20))
    N["C3"] = {d: 100.0 * v[2] / v[1] for d, v in mgr.items() if v and len(v) > 2 and v[1] and v[2] is not None}
    futi = D.get("futi") or {}
    N["C4"] = f2_retail_mtx(futi, D.get("mtxoi") or {})
    N["C5"] = f1_foreign_fut(futi)
    N["C6"] = f3_foreign_opt(D.get("opti") or {})
    pc = {d: v[2] for d, v in (D.get("pcr") or {}).items() if v and v[2] is not None}
    N["C7"] = native(pc, lambda v: H.roll_mean(v, 5))
    sw = {}
    for d, v in (D.get("sitca") or {}).items():           # 週資料：週末日期 + 7 天才算拿得到
        sw[(date.fromisoformat(d) + timedelta(days=S.AVAIL_DAYS["C8"])).isoformat()] = v
    N["C8"] = sw
    # 全球資金（美國資料，在來源自己的日期上算）
    ff = D.get("effr") or {}
    N["G1"] = native(ff, lambda v: H.chg(H.roll_mean(v, 5), 126, pct=False))
    ust = D.get("ust") or {}
    u2 = {d: v[1] for d, v in ust.items() if v and len(v) > 1 and v[1] is not None}
    u10 = {d: v[2] for d, v in ust.items() if v and len(v) > 2 and v[2] is not None}
    N["G2"] = native(u2, lambda v: H.chg(v, 60, pct=False))
    N["G3"] = native(u10, lambda v: H.chg(v, 60, pct=False))
    hy, ie = D.get("hyg") or {}, D.get("ief") or {}
    rat = {d: hy[d] / ie[d] for d in hy if ie.get(d)}
    N["G4"] = native(rat, lambda v: H.chg(v, 60))
    # 台灣資金
    inst = D.get("inst") or {}
    fx = {d: sum(x for n, x in v.items() if n.startswith("Foreign")) for d, v in inst.items()
          if any(n.startswith("Foreign") for n in v)}
    to = {d: v[0] for d, v in (D.get("turnover") or {}).items() if v and v[0]}
    N["L3"] = on_cal(ratio_sum(cal, fx, to, 60))
    N["L4"] = native(D.get("usdtwd") or {}, lambda v: H.chg(v, 60))
    N["L5"] = native(to, lambda v: ma_ratio(v, 20, 250))
    qf = {d: 100.0 * v[0] / v[1] for d, v in (D.get("qfii") or {}).items() if v and v[1]}
    N["L7"] = on_cal(H.chg(H.asof_daily(cal, qf, stale=S.STALE["L7"]), 60, pct=False))
    N["T1"] = on_cal(rel_ma(px, 20))
    N["T2"] = on_cal(rel_ma(px, 60))
    N["T3"] = on_cal(rel_ma(px, 240))
    N["T4"] = on_cal(H.rsi(px, 14))
    br = D.get("breadth") or {}
    bk = sorted(br)
    bi = HD.breadth_ind({"cal": bk, **{f: [br[d][j] for d in bk]
                                       for j, f in enumerate(("adv", "dec", "above", "n60", "hi", "lo", "n250"))}})
    for k in BREADTH:
        N[k] = bi[k]
    N["T8"] = on_cal(H.roll_std_ret(px, 20))
    N["T9"] = dict(D.get("vix") or {})
    N["T10"] = dict(D.get("vixtw") or {})
    M = TT.mas(px)
    conds = [(px, M[5]), (M[5], M[10]), (M[10], M[20]), (M[20], M[60]), (M[60], M[120]), (M[120], M[240])]
    N["T11"] = on_cal([None if M[240][i] is None else sum(1 for a, b in conds if a[i] > b[i]) for i in range(len(cal))])
    N["T12"] = on_cal(H.chg(M[60], 20))
    hi = roll_max(px, 120)
    N["T13"] = on_cal([None if p is None or h is None else 100.0 * (p / h - 1.0) for p, h in zip(px, hi)])
    return N


def raw_daily(D: dict, cal: list[str], px: list, N: dict | None = None) -> dict[str, list]:
    """對齊台灣交易日：沿用最近一筆（超過 7 個日曆天算缺；廣度 4 天；週資料見 heatspec.STALE）；美國資料晚一天才用。"""
    N = N if N is not None else native_daily(D, cal, px)
    return {k: H.asof_daily(cal, N[k], after=k in S.US, stale=4 if k in BREADTH else S.STALE.get(k, 7)) for k in N}


def raw_monthly(D: dict) -> dict[str, dict]:
    M: dict[str, dict] = {}
    ndc = D.get("ndc") or {}
    M["B1"] = {ym: v[6] for ym, v in ndc.items() if v[6] is not None}
    M["B2"] = {ym: v[1] - ndc[ym_add(ym, -6)][1] for ym, v in ndc.items()
               if v[1] is not None and (ndc.get(ym_add(ym, -6)) or [None, None])[1] is not None}
    M["B3"] = dict(D.get("pmi") or {})
    M["B4"] = yoy3(D.get("orders") or {})
    M["B5"] = yoy3(D.get("exports") or {})
    rv = D.get("rev") or {}
    b6 = {}
    for ym in rv:
        ms = [rv.get(ym_add(ym, -j)) for j in range(3)]
        if all(ms) and sum(m[1] for m in ms):
            b6[ym] = 100.0 * (sum(m[0] for m in ms) / sum(m[1] for m in ms) - 1.0)
    M["B6"] = b6
    tc = D.get("twcpi") or {}
    idx = {k: v[0] for k, v in tc.items() if v[0]}
    M["B7"] = {ym: (v[1] if v[1] is not None else yoy(idx, ym)) for ym, v in tc.items()
               if v[1] is not None or yoy(idx, ym) is not None}
    cpi = D.get("uscpi") or {}
    M["B8"] = {ym: yoy(cpi, ym) for ym in cpi if yoy(cpi, ym) is not None}
    mo = D.get("money") or {}

    def myoy(ym, j):                       # 央行公布的年增率；沒有（最早 12 個月）就自己算
        v = mo.get(ym)
        if v and v[j + 1] is not None:
            return v[j + 1]
        return yoy({k: x[j] for k, x in mo.items() if x[j]}, ym)
    M["L1"] = {ym: myoy(ym, 0) - myoy(ym, 2) for ym in mo if myoy(ym, 0) is not None and myoy(ym, 2) is not None}
    M["L2"] = {ym: myoy(ym, 0) for ym in mo if myoy(ym, 0) is not None}
    spx: dict[str, float] = {}
    for d, v in sorted((D.get("spx") or {}).items()):        # 月底收盤＝當月最後一筆
        if v:
            spx[d[:7]] = v
    M["G5"] = {ym: (v / 1e12) / (spx[ym] / 1000.0) for ym, v in (D.get("mmf") or {}).items() if v and spx.get(ym)}
    sf = D.get("sfbflow") or {}

    def flow(ym):                                         # 單月淨匯入；沒有就用前後兩個月底累計相減
        v = sf.get(ym) or [None, None]
        if v[0] is not None:
            return v[0]
        p = sf.get(ym_add(ym, -1)) or [None, None]
        return v[1] - p[1] if v[1] is not None and p[1] is not None else None
    M["L6"] = {ym: flow(ym) for ym in sf if flow(ym) is not None}
    cb = D.get("cbcbank") or {}
    M["L8"] = {ym: 100.0 * v[0] / mo[ym][2] for ym, v in cb.items()
               if v and v[0] is not None and (mo.get(ym) or [None] * 3)[2]}
    M["L9"] = {ym: v[3] - cb[ym_add(ym, -3)][3] for ym, v in cb.items()
               if v and v[3] is not None and (cb.get(ym_add(ym, -3)) or [None] * 4)[3] is not None}
    M["L10"] = {ym: v[1] - v[2] for ym, v in cb.items() if v and v[1] is not None and v[2] is not None}
    return M


# ── 0～100 與面向總分 ─────────────────────────────────────────────────

def build(D: dict | None = None) -> dict:
    """→ {"cal", "px", "cal_info", "raw": {k: 逐日值}, "heat": {k: 逐日 0～100（頁面顯示，含代替）},
    "hc": {k: 逐日 0～100（算進總分的）}, "proxy": {k: 逐日是否用代替}, "ym": {k: 逐日用到的月份},
    "mraw": {k: 月序列}, "nat": {k: 來源日期上的值}, "comp": {面向: 逐日總分}, "vixcorr": {...}}"""
    D = D if D is not None else load()
    cal, px, info = calendar(D)
    N = native_daily(D, cal, px)
    raw = raw_daily(D, cal, px, N)
    for k in DAILY:                                    # 規格有、但還沒有資料的項目＝整條沒有值
        raw.setdefault(k, [None] * len(cal))
        N.setdefault(k, {})
    heat = {k: ([None if v is None else 100.0 * v / S.DIRECT[k] for v in raw[k]] if k in S.DIRECT else
                [H.to_heat(p, S.HOT[k]) for p in H.pct_series(raw[k], S.PCT_WIN["d"], S.PCT_MIN["d"])]) for k in DAILY}
    M = raw_monthly(D)
    ymu: dict[str, list] = {}
    for k in MONTHLY:
        M.setdefault(k, {})
        ks = sorted(M[k])
        p = H.pct_series([M[k][x] for x in ks], S.PCT_WIN["m"], S.PCT_MIN["m"])
        hm = {ym: H.to_heat(x, S.HOT[k]) for ym, x in zip(ks, p) if x is not None}
        heat[k] = H.asof_monthly(cal, hm, S.RELEASE[k])
        raw[k] = H.asof_monthly(cal, M[k], S.RELEASE[k])
        ymu[k] = H.asof_monthly(cal, {ym: ym for ym in M[k]}, S.RELEASE[k])
    hc = dict(heat)
    proxy: dict[str, list] = {}
    for k, src in S.PROXY.items():
        own = heat[k]
        proxy[k] = [own[i] is None and raw[k][i] is not None and heat[src][i] is not None for i in range(len(cal))]
        heat[k] = [heat[src][i] if proxy[k][i] else own[i] for i in range(len(cal))]
        hc[k] = own
    comp = {d: [H.composite({k: hc[k][i] for k in S.ITEMS[d]}, S.ITEMS[d]) for i in range(len(cal))] for d in S.DIMS}
    pairs = [(raw["T10"][i], raw["T9"][i]) for i in range(len(cal))
             if raw["T10"][i] is not None and raw["T9"][i] is not None]
    vc = {"n": len(pairs), "r": H._pearson([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 3 else None,
          "a": next((cal[i] for i in range(len(cal)) if raw["T10"][i] is not None), None)}
    return {"cal": cal, "px": px, "cal_info": info, "raw": raw, "heat": heat, "hc": hc, "proxy": proxy, "ym": ymu,
            "mraw": M, "nat": N, "comp": comp, "vixcorr": vc, "D": D}


# ── 驗證（第 12.7 節） ─────────────────────────────────────────────────

def sample_idx(cal: list[str], freq: str) -> list[int]:
    """每天一個；m＝每月最後一個交易日一個。"""
    if freq != "m":
        return list(range(len(cal)))
    return [i for i in range(len(cal)) if i == len(cal) - 1 or cal[i + 1][:7] != cal[i][:7]]


def _in(d: str, rng: tuple) -> bool:
    a, z = rng
    return (a is None or d >= a) and (z is None or d <= z)


def _r(x, k=3):
    return None if x is None else round(x, k)


def evaluate(x: list, px: list, cal: list[str], dim: str) -> dict:
    """x＝逐日 0～100（某項或面向總分）→ {持有天數: {n, rho, lo, hi, a, z, h1, h2, verdict, bands, ref, block}}。
    判定用沒有四捨五入的數字；輸出才取位數。"""
    L = S.DIMS[dim]
    freq = L["freq"]
    idx = sample_idx(cal, freq)
    out = {}
    for h in L["fwd"]:
        block = h if freq == "d" else max(1, round(h / 21))
        rows = []
        for i in idx:
            if x[i] is None:
                continue
            r, dd = H.fwd(px, i, h)
            if r is not None:
                rows.append((cal[i], x[i], r, dd))
        xs, ys, ds = [b for _, b, _, _ in rows], [c for _, _, c, _ in rows], [d for *_, d in rows]
        rho, lo, hi = H.spearman_ci(xs, ys, block)
        m = len(rows) // 2
        r1 = H.spearman(xs[:m], ys[:m])
        r2 = H.spearman(xs[m:], ys[m:])
        bands = H.bands(xs, ys, ds)
        for b, (lo_, hi_, _) in zip(bands, S.BANDS):          # 這一區出現在哪幾年（只當資訊：樣本是不是集中在一段）
            b["yrs"] = sorted({d[:4] for d, v, _, _ in rows if lo_ <= v < hi_})
        ref = []
        for rng in S.SPLIT_REF[freq]:
            sub = [(b, c) for d, b, c, _ in rows if _in(d, rng)]
            ref.append({"n": len(sub), "rho": _r(H.spearman([a for a, _ in sub], [b for _, b in sub]))})
        out[h] = {"n": len(rows), "rho": _r(rho), "lo": _r(lo), "hi": _r(hi),
                  "a": rows[0][0] if rows else None, "z": rows[-1][0] if rows else None,
                  "h1": {"n": m, "rho": _r(r1), "z": rows[m - 1][0] if m else None},
                  "h2": {"n": len(rows) - m, "rho": _r(r2), "a": rows[m][0] if len(rows) > m else None},
                  "verdict": H.verdict(rho, lo, hi, r1, r2, len(rows), S.MIN_N[freq]),
                  "bands": bands, "ref": ref, "block": block}
    return out


def _round_ev(r: dict) -> dict:
    """事件研究輸出取位數（判定已經用沒有四捨五入的數字算好）。"""
    out = dict(r)
    for k in ("avg", "all_avg", "diff", "lo", "hi"):
        out[k] = _r(out.get(k), 6)
    for k in ("up", "all_up"):
        out[k] = _r(out.get(k), 4)
    for k in ("h1", "h2"):
        if out.get(k):
            out[k] = {"n": out[k]["n"], "diff": _r(out[k]["diff"], 6)}
    return out


def research(B: dict | None = None) -> dict:
    """每一項、每個面向總分的驗證（只當資訊，不拿來刪項目）。"""
    B = B if B is not None else build()
    cal, px, comp = B["cal"], B["px"], B["comp"]
    D = B["D"]
    dims = {}
    for dim in S.DIMS:
        keys = S.ITEMS[dim]
        # 台指 VIX 只驗它自己的 0～100（代替的日子就是美國 VIX，不重複驗）
        items = {k: evaluate(B["hc"][k], px, cal, dim) for k in keys}
        first = {k: next((cal[i] for i, v in enumerate(B["hc"][k]) if v is not None), None) for k in keys}
        cf = next((cal[i] for i, v in enumerate(comp[dim]) if v is not None), None)
        dims[dim] = {"items": items, "first": first, "comp": evaluate(comp[dim], px, cal, dim), "comp_first": cf}
    ev = TT.all_events(px)
    fw = {h: TT.fwd_all(px, h) for h in S.EV_FWD}
    events = {k: {str(h): _round_ev(TT.event_study(px, cal, ev[k], h, f=fw[h])) for h in S.EV_FWD} for k in S.EVENTS}
    data = {}
    for n in FILES + ["rev"]:
        ks = sorted(D.get(n) or {})
        data[n] = [len(ks), ks[0] if ks else None, ks[-1] if ks else None]
    from . import heatreg, heatrel            # 第五、六版（第 14.14、15.11 節）；放這裡避免循環匯入
    rel = heatrel.run(B)
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cal": B["cal_info"], "data": data, "dims": dims, "events": events,
            "wk": rel["wk"], "rel": rel["rel"], "deriv": heatrel.deriv_all(B),
            "m6": heatreg.run(B, HD.load("taiexm"))}
