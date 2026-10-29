"""大跌風險研究（docs/lab_crash_plan.md 第 10 節；規格 crashspec VER 1）。

  outcomes()        五個結果變數（只用 t＋1 以後的收盤）
  tw_inputs()       台股：日曆、收盤、17 個預測變數的逐日 0～100
  us_inputs(idx)    美股：同上（每個指數）
  analyze()         一個市場 × 預測變數 × 結果：分區表、扣掉波動的差、重抽區間、前後兩半、樣本不足、穩健度、樣本外
  research()        五個市場全部算完＋BH＋主要假說（Holm）→ data/lab/crash_research.json
  now()             每天建頁：今天每個預測變數的 0～100、今天落在哪一組波動（研究檔的分組界線）
  vol_state()       每天建頁：今天的 20 日波動在全部日子裡的位置，同一組波動的日子之後的比例（描述）

研究檔只在資料或規格改了才重跑：TZ=Asia/Taipei python3 scripts/run_crash.py（numpy）。
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import crashspec as S

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "lab" / "crash_research.json"


# ── 結果變數與控制變數 ─────────────────────────────────────────────────────

def _sw(a: np.ndarray, w: int) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view
    return sliding_window_view(a, w)


def sigma(px: np.ndarray) -> float:
    """整個樣本的日報酬標準差（A5 的分母）。"""
    sr = px[1:] / px[:-1] - 1.0
    return float(np.std(sr, ddof=1))


def outcomes(px: np.ndarray, th: tuple, sig: float | None = None) -> dict[str, np.ndarray]:
    """→ {A1..A5: 逐日值（NaN＝之後的期間不完整）}。A1～A4 是 0／1。"""
    n = len(px)
    out = {k: np.full(n, np.nan) for k in S.OUTCOMES}
    if n < 2:
        return out
    q1, q2, q3 = th
    sr = px[1:] / px[:-1] - 1.0                    # sr[i]＝第 i＋1 天的日報酬
    lr = np.log(px[1:] / px[:-1])
    sig = sig if sig is not None else sigma(px)
    h = S.H["A1"]
    if n - 1 >= h:
        m = _sw(sr, h).min(axis=1)                 # 第 t＋1～t＋h 天的最差日報酬
        out["A1"][: n - h] = (m <= -q1).astype(float)
        mp = _sw(px[1:], h).min(axis=1)            # 第 t＋1～t＋h 天的最低收盤
        out["A2"][: n - h] = (mp / px[: n - h] - 1.0 <= -q2).astype(float)
    h3 = S.H["A3"]
    if n - 1 >= h3:
        mp3 = _sw(px[1:], h3).min(axis=1)
        out["A3"][: n - h3] = (mp3 / px[: n - h3] - 1.0 <= -q3).astype(float)
    h4, b4 = S.H["A4"], S.VOL_BEFORE
    if n - 1 >= h4 + b4:
        sa = _sw(lr, h4).std(axis=1, ddof=1)       # sa[t]＝第 t＋1～t＋h4 天
        sb = _sw(lr, b4).std(axis=1, ddof=1)       # sb[t−b4]＝第 t−b4＋1～t 天
        t = np.arange(b4, n - h4)
        out["A4"][t] = (sa[t] >= S.VOL_RATIO * sb[t - b4]).astype(float)
    h5 = S.H["A5"]
    if n - 1 >= h5:
        w = np.partition(_sw(sr, h5), S.WORST_K - 1, axis=1)[:, : S.WORST_K]
        out["A5"][: n - h5] = -w.mean(axis=1) / sig
    return out


def vol20(px: np.ndarray) -> np.ndarray:
    """近 20 個交易日（第 t−19～t 天）日對數報酬的標準差。"""
    n, k = len(px), S.VOL_WIN
    out = np.full(n, np.nan)
    if n > k:
        lr = np.log(px[1:] / px[:-1])
        out[k:] = _sw(lr, k).std(axis=1, ddof=1)
    return out


def dev60(px: np.ndarray) -> np.ndarray:
    n, k = len(px), S.MA_DEV
    out = np.full(n, np.nan)
    if n >= k:
        out[k - 1:] = px[k - 1:] / _sw(px, k).mean(axis=1) - 1.0
    return out


# ── 預測變數 ──────────────────────────────────────────────────────────────

def _f(x) -> float:
    return np.nan if x is None else float(x)


def _pct(xs: list, win: int, mn: int) -> list:
    from .heat import pct_series
    return pct_series(xs, win, mn)


def align(cal: list[str], src_cal: list[str], vals: list) -> np.ndarray:
    """依日期把另一個日曆上的值對過來（沒有的日子 NaN）。"""
    pos = {d: i for i, d in enumerate(src_cal)}
    return np.array([_f(vals[pos[d]]) if d in pos else np.nan for d in cal])


def month_ends(cal: list[str]) -> dict[str, int]:
    """{YYYY-MM: 那個月最後一個交易日的位置}；最後一個月沒過完（日曆最後一天之後還有同月的日子）也算進來，由呼叫端決定要不要用。"""
    out: dict[str, int] = {}
    for i, d in enumerate(cal):
        out[d[:7]] = i
    return out


def complete_months(cal: list[str], today: str | None = None) -> set[str]:
    """已經過完的月份：日曆最後一天所在的月份不算（除非 today 已經是下個月）。"""
    ms = {d[:7] for d in cal}
    last = (today or cal[-1])[:7] if cal else ""
    return {m for m in ms if m < last}


def _ym_next(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + 1
    return f"{y + (m > 12):04d}-{(m - 1) % 12 + 1:02d}"


def monthly_to_daily(cal: list[str], vals: dict) -> np.ndarray:
    """第 m 個月的值用在 m＋1 月的每個交易日。"""
    nxt = {_ym_next(m): v for m, v in vals.items() if v is not None}
    return np.array([_f(nxt.get(d[:7])) for d in cal])


def rows_to_daily(cal: list[str], rows: list[dict], key, done: set[str]) -> np.ndarray:
    """泡沫頁的每月判定（月底那一列）→ 下一個交易日起用到下一個月底；只用已經過完的月份。"""
    vals = {}
    for r in rows:
        ym = str(r.get("d"))[:7]
        if ym in done:
            v = key(r)
            vals[ym] = None if v is None else float(v)
    return monthly_to_daily(cal, vals)


def _cap_month(twcap: dict, me_px: dict) -> dict:
    """上市月底市值（元）：央行有的月份用央行；之後的月份用最近一個央行月份 × 加權指數月底漲跌。"""
    out, last = {}, None
    for ym in sorted(set(twcap) | set(me_px)):
        c = (twcap.get(ym) or [None] * 3)[2]
        if c:
            out[ym], last = c * 1e6, ym
        elif last and ym in me_px and last in me_px and me_px[last]:
            out[ym] = twcap[last][2] * 1e6 * me_px[ym] / me_px[last]
    return out


def _cap_daily(cal: list[str], px: np.ndarray, twcap: dict, me_px: dict) -> np.ndarray:
    """估計的每日上市市值：前一個月底（央行有的最近一個月份）的市值 × 加權指數從那天起的漲跌。"""
    cm = sorted(m for m, v in twcap.items() if v and v[2] and m in me_px)
    out = np.full(len(cal), np.nan)
    j = -1
    for i, d in enumerate(cal):
        ym = d[:7]
        while j + 1 < len(cm) and cm[j + 1] < ym:
            j += 1
        if j >= 0:
            m = cm[j]
            out[i] = twcap[m][2] * 1e6 * px[i] / me_px[m]
    return out


def tw_inputs(D: dict | None = None, B: dict | None = None, BX: dict | None = None) -> dict:
    """台股：→ {"cal", "px", "x": {代號: 逐日 0～100（NaN＝沒有）}, "raw": {W1～W4: 原始值}}。
    D＝heatdata 的檔（測試用）；B＝heatcalc.build()；BX＝bubble.compute()。"""
    from . import heatbubble as BB
    from . import heatdata as HD
    load = (lambda n: (D or {}).get(n) or {}) if D is not None else HD.load
    E = BB.taiex_daily({n: load(n) for n in ("turnover", "taiex", "taiex90")}) if D is not None else BB.taiex_daily()
    cal = sorted(d for d, v in E.items() if v and d >= S.START["tw"])
    px = np.array([float(E[d]) for d in cal])
    me = month_ends(cal)
    me_px = {m: px[i] for m, i in me.items()}
    done = complete_months(cal)
    twcap, twmgn, fm = load("twcap"), load("twmgn"), load("margin")
    capm = _cap_month(twcap, me_px)
    # 分子：2001 起上市融資（FinMind 月底）；之前央行（上市＋上櫃）
    fm_me: dict = {}
    for d in sorted(fm):
        v = fm[d]
        if v and v[0]:
            fm_me[d[:7]] = float(v[0])
    num = {}
    for ym in sorted(set(twmgn) | set(fm_me)):
        if ym >= "2001-01":
            if ym in fm_me:
                num[ym] = fm_me[ym]
        elif (twmgn.get(ym) or [None])[0]:
            num[ym] = twmgn[ym][0] * 1e6
    months = sorted(m for m in set(num) & set(capm) if m in done or m < cal[0][:7])
    w1 = {m: num[m] / capm[m] for m in months if capm[m]}
    w1p = _monthly_pct(w1)
    # W3：扣掉台積電（自算 v3me_tw 月底市值，2013 起）
    tsmc = _tsmc_month(D)
    w3 = {m: num[m] / (capm[m] - tsmc[m]) for m in months if m in tsmc and capm[m] > tsmc[m]}
    w3p = _monthly_pct(w3)
    capd = _cap_daily(cal, px, twcap, me_px)
    from .heat import asof_daily
    mg = np.array([_f(None if v is None else v) for v in asof_daily(cal, {d: (v[0] if v else None) for d, v in fm.items()},
                                                                       stale=4)])
    w2 = mg / capd
    to = load("turnover")
    tv = np.array([_f((to.get(d) or [None])[0]) for d in cal])
    k = 20
    w4 = np.full(len(cal), np.nan)
    if len(cal) >= k:
        m20 = _sw(tv, k).mean(axis=1)                       # 有一天 NaN 整個窗就是 NaN
        w4[k - 1:] = m20 / capd[k - 1:]
    x = {"W1": monthly_to_daily(cal, w1p), "W3": monthly_to_daily(cal, w3p),
         "W2": np.array([_f(v) for v in _pct([None if math.isnan(v) else float(v) for v in w2], *S.PCT_DAILY)]),
         "W4": np.array([_f(v) for v in _pct([None if math.isnan(v) else float(v) for v in w4], *S.PCT_DAILY)])}
    if B is None:
        from . import heatcalc as HC
        B = HC.build()
    for kk in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "L5", "T9"):
        x[kk] = align(cal, B["cal"], B["hc"].get(kk) or [None] * len(B["cal"]))
    x["Dchip"] = align(cal, B["cal"], B["comp"]["chip"])
    x["Dfund"] = align(cal, B["cal"], B["comp"]["fund"])
    _bubble_into(x, "tw", cal, done, BX)
    raw = {"W1": w1, "W3": w3, "W2": w2, "W4": w4, "cap": capd}
    return {"cal": cal, "px": px, "x": x, "raw": raw}


def _monthly_pct(ser: dict) -> dict:
    ks = sorted(ser)
    p = _pct([ser[k] for k in ks], *S.PCT_MONTHLY)
    return {k: v for k, v in zip(ks, p) if v is not None}


def _tsmc_month(D: dict | None) -> dict:
    if D is not None:
        return dict(D.get("_tsmc") or {})
    from . import store
    out = {}
    for _, doc in store.load("v3me_tw"):
        d, s = (doc or {}).get("d"), (doc or {}).get("s") or {}
        v = s.get("2330")
        if d and v and len(v) >= 2 and v[0] and v[1]:
            out[d[:7]] = float(v[0]) * float(v[1])
    return out


def _bubble_into(x: dict, mk: str, cal: list[str], done: set[str], BX: dict | None) -> None:
    if BX is None:
        from . import bubble as BU
        BX = BU.compute()
    rows = (((BX or {}).get(mk) or {}).get("_C") or {}).get("rows") or []
    x["BL2"] = rows_to_daily(cal, rows, lambda r: None if r.get("L") is None else (100.0 if r["L"] >= 2 else 0.0), done)
    x["BP1"] = rows_to_daily(cal, rows, lambda r: None if r.get("P1") is None else (100.0 if r["P1"] else 0.0), done)


def us_inputs(idx: str, D: dict | None = None, Bu: dict | None = None, BX: dict | None = None) -> dict:
    """美股一個指數：→ {"cal", "px", "x"}。Bu＝heatcalc_us.build(idx)。"""
    from . import heatdata as HD
    if Bu is None:
        from . import heatcalc_us as HU
        Bu = HU.build(idx)
    c0 = next((i for i, d in enumerate(Bu["cal"]) if d >= S.START[idx]), len(Bu["cal"]))
    cal = Bu["cal"][c0:]
    px = np.array([_f(v) for v in Bu["px"][c0:]])
    done = complete_months(cal)
    x = {}
    for kk in tuple(p for p in S.PRED[idx] if p.startswith("S")) + ("T9",):
        x[kk] = np.array([_f(v) for v in (Bu["hc"].get(kk) or [None] * len(Bu["cal"]))[c0:]])
    x["Dsent"] = np.array([_f(v) for v in Bu["comp"]["sent"][c0:]])
    if "VOL" in S.PRED[idx]:
        vol = (D or {}).get(f"us_vol_{idx}") if D is not None else HD.load(f"us_vol_{idx}")
        x["VOL"] = volume_heat(Bu["cal"], vol or {})[c0:]
    _bubble_into(x, idx, cal, done, BX)
    return {"cal": cal, "px": px, "x": x}


def volume_heat(cal: list[str], vol: dict) -> np.ndarray:
    """成交量能＝20 日平均 ÷ 250 日平均 − 1，和過去 750 個交易日比的百分位（窗內有一天沒有成交量就沒有值）。"""
    a, b = S.VOL_MA
    v = np.array([_f(vol.get(d)) for d in cal])
    r = np.full(len(cal), np.nan)
    if len(cal) >= b:
        ma = _sw(v, a).mean(axis=1)                          # ma[i]＝第 i～i＋a−1 天
        mb = _sw(v, b).mean(axis=1)
        t = np.arange(b - 1, len(cal))
        r[t] = ma[t - a + 1] / mb[t - b + 1] - 1.0
    p = _pct([None if math.isnan(z) else float(z) for z in r], *S.PCT_DAILY)
    return np.array([_f(z) for z in p])


def pred_info(mk: str, p: str) -> dict:
    """→ {"name": 名稱, "hot": 熱代表什麼}（頁面與文件用）。景氣頁的項目用景氣頁的名稱與方向。"""
    if p in ("W1", "W2", "W3", "W4", "VOL"):
        return {"name": S.PRED_NAMES[p], "hot": "比過去 3 年 80% 的時候高"}
    if p in ("Dchip", "Dfund", "Dsent"):
        return {"name": S.PRED_NAMES[p], "hot": "面向分數 80 以上"}
    if p in S.FLAGS:
        return {"name": S.PRED_NAMES[p], "hot": "成立"}
    from . import heatspec as HS
    if mk == "tw":
        meta = _heat_item(HS, p)
    else:
        from . import heatspec_us as HU
        with HS.use(HU.spec_for(mk)):
            meta = _heat_item(HS, p)
        if p == "T9":
            meta = dict(meta, name="VXN（那斯達克 100 波動率指數）" if HU.IVOL[mk] == "vxn" else "VIX")
    hi = meta["dir"] > 0
    return {"name": meta["name"], "hot": f'比過去 {meta["yrs"]} 年 80% 的時候' + ("高" if hi else "低")}


def _heat_item(HS, p: str) -> dict:
    """景氣頁的項目：名稱、熱的方向、和過去幾年比（日資料 3 年；月、季資料與另外指定視窗的項目 10 年）。"""
    row = next(x for x in HS.IND if x[0] == p)
    return {"name": row[2], "dir": row[4], "yrs": 10 if row[5] == "m" or p in HS.PCT_WIN_ITEM else 3}


# ── 統計 ─────────────────────────────────────────────────────────────────

def terciles(v: np.ndarray) -> tuple[float, float]:
    q = np.quantile(v, [1.0 / 3.0, 2.0 / 3.0])
    return float(q[0]), float(q[1])


def groups(v: np.ndarray, cuts: tuple) -> np.ndarray:
    return (v >= cuts[0]).astype(int) + (v >= cuts[1]).astype(int)


def _cols(y: np.ndarray, hot: np.ndarray, g: np.ndarray, ng: int) -> np.ndarray:
    """每天的貢獻：每組 [熱的天數, 熱的 y 合計, 不熱的天數, 不熱的 y 合計]。"""
    c = np.zeros((len(y), 4 * ng))
    for s in range(ng):
        mh, mn = hot & (g == s), (~hot) & (g == s)
        c[:, 4 * s], c[:, 4 * s + 1] = mh, np.where(mh, y, 0.0)
        c[:, 4 * s + 2], c[:, 4 * s + 3] = mn, np.where(mn, y, 0.0)
    return c


def d_from_totals(T: np.ndarray) -> np.ndarray:
    """T（…, 4×組數）→ 組內「熱 − 不熱」依熱的天數加權（熱、不熱都 ≥ MIN_STRAT 天的組才算）。"""
    ch, sh, cn, sn = T[..., 0::4], T[..., 1::4], T[..., 2::4], T[..., 3::4]
    ok = (ch >= S.MIN_STRAT) & (cn >= S.MIN_STRAT)
    diff = np.where(ok, sh / np.where(ch > 0, ch, 1.0) - sn / np.where(cn > 0, cn, 1.0), 0.0)
    w = np.where(ok, ch, 0.0)
    W = w.sum(axis=-1)
    return np.where(W > 0, (w * diff).sum(axis=-1) / np.where(W > 0, W, 1.0), np.nan)


def strat_diff(y: np.ndarray, hot: np.ndarray, g: np.ndarray, ng: int = S.VOL_GROUPS) -> float | None:
    d = float(d_from_totals(_cols(y, hot, g, ng).sum(axis=0)))
    return None if math.isnan(d) else d


def boot(c: np.ndarray, n_boot: int = S.BOOT_N, L: int = S.BLOCK, seed: int = S.BOOT_SEED) -> np.ndarray | None:
    """移動區塊重抽：c＝每天的貢獻（照時間），一次抽 ⌈n／L⌉ 塊 → 每次的差（n_boot 個）。天數不到 2L 回 None。"""
    n = len(c)
    if n < 2 * L:
        return None
    P = np.vstack([np.zeros(c.shape[1]), np.cumsum(c, axis=0)])
    BS = P[L:] - P[:-L]
    k = math.ceil(n / L)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    step = 250
    for a in range(0, n_boot, step):
        m = min(step, n_boot - a)
        st = rng.integers(0, n - L + 1, size=(m, k))
        out[a:a + m] = d_from_totals(BS[st].sum(axis=1))
    return out


def ci_p(reps: np.ndarray | None) -> tuple:
    """→ (下緣, 上緣, 雙尾 p, 單尾 p（差 ≤ 0 的比例）)。"""
    if reps is None:
        return None, None, None, None
    r = reps[~np.isnan(reps)]
    if len(r) < len(reps) // 2:
        return None, None, None, None
    a = (1.0 - S.CI) / 2.0
    lo, hi = np.quantile(r, [a, 1.0 - a])
    le, ge = float(np.mean(r <= 0)), float(np.mean(r >= 0))
    pmin = 1.0 / S.BOOT_N
    return float(lo), float(hi), min(1.0, max(pmin, 2.0 * min(le, ge))), max(pmin, le)


def episodes(pos: np.ndarray, gap: int = S.EP_GAP) -> int:
    if len(pos) == 0:
        return 0
    p = np.sort(pos)
    return int(1 + np.sum(np.diff(p) > gap))


def bh(ps: list) -> list:
    from .heatrel import bh as _bh
    return _bh(ps)


def holm(ps: dict, alpha: float = S.HOLM_ALPHA) -> tuple[dict, dict]:
    from .heatreg import holm as _h
    return _h(ps, alpha)


def _nw_meat(u: np.ndarray, L: int) -> np.ndarray:
    Sm = u.T @ u
    for l in range(1, min(L, len(u) - 1) + 1):
        G = u[l:].T @ u[:-l]
        Sm += (1.0 - l / (L + 1.0)) * (G + G.T)
    return Sm


def logit_fit(y: np.ndarray, X: np.ndarray, b0: np.ndarray | None = None, it: int = 50) -> np.ndarray | None:
    b = np.zeros(X.shape[1]) if b0 is None else b0.copy()
    for _ in range(it):
        eta = np.clip(X @ b, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        W = p * (1.0 - p)
        Hm = X.T @ (X * W[:, None])
        try:
            step = np.linalg.solve(Hm, X.T @ (y - p))
        except np.linalg.LinAlgError:
            return None
        b = b + step
        if np.max(np.abs(step)) < 1e-8:
            return b
    return None


def logit_hac(y: np.ndarray, X: np.ndarray, L: int) -> tuple | None:
    b = logit_fit(y, X)
    if b is None:
        return None
    p = 1.0 / (1.0 + np.exp(-np.clip(X @ b, -30, 30)))
    Hm = X.T @ (X * (p * (1.0 - p))[:, None])
    try:
        Hi = np.linalg.inv(Hm)
    except np.linalg.LinAlgError:
        return None
    V = Hi @ _nw_meat(X * (y - p)[:, None], L) @ Hi
    return b, np.sqrt(np.maximum(np.diag(V), 0.0))


def ols_hac(y: np.ndarray, X: np.ndarray, L: int) -> tuple | None:
    try:
        XtXi = np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return None
    b = XtXi @ (X.T @ y)
    V = XtXi @ _nw_meat(X * (y - X @ b)[:, None], L) @ XtXi
    return b, np.sqrt(np.maximum(np.diag(V), 0.0))


def nw_t(d: np.ndarray, L: int) -> float | None:
    n = len(d)
    if n < 3:
        return None
    m = d.mean()
    e = d - m
    v = float(e @ e) / n
    for l in range(1, min(L, n - 1) + 1):
        v += 2.0 * (1.0 - l / (L + 1.0)) * float(e[l:] @ e[:-l]) / n
    return None if v <= 0 else float(m / math.sqrt(v / n))


def oos(pos: np.ndarray, y: np.ndarray, hot: np.ndarray, lv: np.ndarray, dv: np.ndarray, cal: list[str], h: int) -> dict:
    """樣本外（第 10.4 節第 9 點）：每月第一個交易日重估；訓練只用 t＋h < 那個月第一天的日子。"""
    ok = ~np.isnan(dv)
    pos, y, hot, lv, dv = pos[ok], y[ok], hot[ok], lv[ok], dv[ok]
    starts = [i for i, d in enumerate(cal) if d >= S.OOS_START and (i == 0 or cal[i - 1][:7] != d[:7])]
    XV = np.column_stack([np.ones(len(y)), lv, dv])
    XX = np.column_stack([np.ones(len(y)), hot.astype(float), lv, dv])
    pV, pX, yy = [], [], []
    bV = bX = None
    for j, M in enumerate(starts):
        nxt = starts[j + 1] if j + 1 < len(starts) else len(cal)
        te = (pos >= M) & (pos < nxt)
        if not te.any():
            continue
        tr = pos + h < M
        nt = int(tr.sum())
        if nt < S.OOS_MIN_TRAIN or y[tr].sum() < S.OOS_MIN_EVENTS or hot[tr].sum() < S.MIN_STRAT \
                or (~hot[tr]).sum() < S.MIN_STRAT:
            continue
        bV = logit_fit(y[tr], XV[tr], bV)
        bX = logit_fit(y[tr], XX[tr], bX)
        if bV is None or bX is None:
            bV = bX = None
            continue
        pV.append(1.0 / (1.0 + np.exp(-np.clip(XV[te] @ bV, -30, 30))))
        pX.append(1.0 / (1.0 + np.exp(-np.clip(XX[te] @ bX, -30, 30))))
        yy.append(y[te])
    if not yy:
        return {"n": 0}
    pV, pX, yy = np.concatenate(pV), np.concatenate(pX), np.concatenate(yy)
    lV, lX = (yy - pV) ** 2, (yy - pX) ** 2
    d = lV - lX
    t = nw_t(d, h)
    v = "same"
    if t is not None and d.mean() > 0 and t >= S.NW_Z:
        v = "better"
    elif t is not None and d.mean() < 0 and t <= -S.NW_Z:
        v = "worse"
    return {"n": int(len(yy)), "bV": float(lV.mean()), "bX": float(lX.mean()),
            "skill": float(d.mean() / lV.mean()) if lV.mean() > 0 else None, "t": t, "v": v}


def zone_of(v: np.ndarray) -> np.ndarray:
    """0～100 → 第幾區（0＝≥ 80 … 4＝< 20）。"""
    out = np.full(len(v), len(S.ZONES) - 1)
    for k in range(len(S.ZONES) - 2, -1, -1):
        out = np.where(v >= S.ZONES[k][0], k, out)
    return out


def analyze(cal: list[str], x: np.ndarray, y: np.ndarray, vol: np.ndarray, dv: np.ndarray, h: int,
            binary: bool, with_oos: bool = True) -> dict:
    """一個預測變數 × 一個結果。"""
    ok = ~np.isnan(x) & ~np.isnan(y) & ~np.isnan(vol)
    pos = np.nonzero(ok)[0]
    out: dict = {"n": int(len(pos))}
    if len(pos) == 0:
        out["v"] = "few"
        return out
    xs, ys, vs = x[pos], y[pos], vol[pos]
    hot = xs >= S.HOT
    cuts = terciles(vs)
    g = groups(vs, cuts)
    out.update({"a": cal[pos[0]], "z": cal[pos[-1]], "cuts": [cuts[0], cuts[1]],
                "nh": int(hot.sum()), "nn": int((~hot).sum()), "ep": episodes(pos[hot]),
                "base": float(ys.mean()), "hot": float(ys[hot].mean()) if hot.any() else None,
                "not": float(ys[~hot].mean()) if (~hot).any() else None})
    zs = zone_of(xs)
    out["zones"] = [[int((zs == k).sum()), float(ys[zs == k].mean()) if (zs == k).any() else None]
                    for k in range(len(S.ZONES))]
    out["strata"] = [[int((hot & (g == s)).sum()), float(ys[hot & (g == s)].mean()) if (hot & (g == s)).any() else None,
                      int((~hot & (g == s)).sum()), float(ys[~hot & (g == s)].mean()) if (~hot & (g == s)).any() else None]
                     for s in range(S.VOL_GROUPS)]
    if out["nh"] < S.MIN_HOT_DAYS or out["nn"] < S.MIN_HOT_DAYS or out["ep"] < S.MIN_EPISODES:
        out["v"] = "few"
        return out
    c = _cols(ys, hot, g, S.VOL_GROUPS)
    out["d"] = strat_diff(ys, hot, g)
    half = len(pos) // 2
    out["h1"] = strat_diff(ys[:half], hot[:half], g[:half])
    out["h2"] = strat_diff(ys[half:], hot[half:], g[half:])
    out["lo"], out["hi"], out["p"], out["p1"] = ci_p(boot(c))
    # 穩健度：回歸（熱＋log 波動＋乖離），Newey–West
    rk = ~np.isnan(dv[pos])
    if rk.sum() > 100:
        X = np.column_stack([np.ones(int(rk.sum())), hot[rk].astype(float), np.log(vs[rk]), dv[pos][rk]])
        f = (logit_hac if binary else ols_hac)(ys[rk], X, h)
        if f is not None:
            b, se = f
            z = float(b[1] / se[1]) if se[1] > 0 else None
            out["rob"] = {"b": float(b[1]), "z": z}
    if binary and with_oos:
        out["oos"] = oos(pos, ys, hot, np.log(vs), dv[pos], cal, h)
    return out


def verdict(r: dict, q: float | None) -> str:
    if r.get("v") == "few":
        return "few"
    lo, hi, h1, h2 = r.get("lo"), r.get("hi"), r.get("h1"), r.get("h2")
    if None in (lo, hi, h1, h2) or q is None or q > S.BH_Q:
        return "none"
    if lo > 0 and h1 > 0 and h2 > 0:
        return "up"
    if hi < 0 and h1 < 0 and h2 < 0:
        return "down"
    return "none"


def robust_ok(r: dict) -> bool | None:
    rb, d = r.get("rob"), r.get("d")
    if not rb or rb.get("z") is None or d is None or d == 0:
        return None
    return bool(np.sign(rb["b"]) == np.sign(d) and abs(rb["z"]) >= S.NW_Z)


# ── 市場層級：全部預測變數 × 結果 ───────────────────────────────────────────────

def market(mk: str, I: dict, with_oos: bool = True) -> dict:
    cal, px = I["cal"], I["px"]
    sig = sigma(px)
    A = outcomes(px, S.TH[mk], sig)
    vol, dv = vol20(px), dev60(px)
    preds: dict = {}
    for p in S.PRED[mk]:
        x = I["x"].get(p)
        if x is None:
            preds[p] = {"out": {}}
            continue
        has = np.nonzero(~np.isnan(x))[0]
        preds[p] = {"a": cal[has[0]] if len(has) else None, "out": {}}
        for o in S.OUTCOMES:
            preds[p]["out"][o] = analyze(cal, x, A[o], vol, dv, S.H[o], o in S.BINARY, with_oos)
    for o in S.OUTCOMES:                                    # BH：同一市場、同一結果
        ks = [p for p in preds if preds[p]["out"].get(o, {}).get("v") != "few" and preds[p]["out"].get(o)]
        qs = bh([preds[p]["out"][o].get("p") for p in ks])
        for p, q in zip(ks, qs):
            r = preds[p]["out"][o]
            r["q"] = q
        for p in preds:
            r = preds[p]["out"].get(o)
            if r is not None:
                r["v"] = verdict(r, r.get("q"))
                r["ok"] = robust_ok(r)
    base = {o: float(np.nanmean(A[o])) for o in S.OUTCOMES}
    return {"start": cal[0], "end": cal[-1], "sigma": sig, "base": base, "preds": preds}


def pooled(parts: list[tuple[str, list[str], np.ndarray, np.ndarray, np.ndarray]], o: str = "A5") -> dict:
    """HA4：parts＝[(市場, 日曆, x, y, vol)]。分組＝市場 × 波動三組；重抽在聯集日曆上抽區塊。"""
    obs = []
    for m, (mk, cal, x, y, vol) in enumerate(parts):
        ok = ~np.isnan(x) & ~np.isnan(y) & ~np.isnan(vol)
        pos = np.nonzero(ok)[0]
        if len(pos) == 0:
            continue
        g = groups(vol[pos], terciles(vol[pos])) + S.VOL_GROUPS * m
        for i, gg in zip(pos, g):
            obs.append((cal[i], int(gg), bool(x[i] >= S.HOT), float(y[i])))
    if not obs:
        return {"n": 0}
    dates = sorted({d for d, _, _, _ in obs})
    upos = {d: i for i, d in enumerate(dates)}
    ng = S.VOL_GROUPS * len(parts)
    U = len(dates)
    c = np.zeros((U, 4 * ng))
    for d, gg, hot, yv in obs:
        k = 4 * gg + (0 if hot else 2)
        c[upos[d], k] += 1.0
        c[upos[d], k + 1] += yv
    dval = float(d_from_totals(c.sum(axis=0)))
    half = U // 2
    lo, hi, p, p1 = ci_p(boot(c))
    return {"n": len(obs), "days": U, "nh": int(c[:, 0::4].sum()), "d": dval,
            "h1": float(d_from_totals(c[:half].sum(axis=0))), "h2": float(d_from_totals(c[half:].sum(axis=0))),
            "lo": lo, "hi": hi, "p": p, "p1": p1}


def primary(M: dict, I: dict) -> dict:
    """主要假說（Holm、單尾）。M＝各市場的結果、I＝各市場的輸入（HA4 要原始序列）。"""
    out: dict = {}
    for h, spec in S.PRIMARY.items():
        if len(spec["mk"]) == 1:
            mk = spec["mk"][0]
            r = M[mk]["preds"][spec["pred"][mk]]["out"][spec["out"]]
            out[h] = {k: r.get(k) for k in ("d", "lo", "hi", "p1", "h1", "h2", "nh", "ep", "n")}
            out[h]["few"] = r.get("v") == "few"
        else:
            parts = []
            for mk in spec["mk"]:
                cal, px = I[mk]["cal"], I[mk]["px"]
                A = outcomes(px, S.TH[mk])
                parts.append((mk, cal, I[mk]["x"][spec["pred"][mk]], A[spec["out"]], vol20(px)))
            out[h] = pooled(parts, spec["out"])
            out[h]["few"] = out[h].get("n", 0) == 0
    adj, rej = holm({h: (None if v.get("few") else v.get("p1")) for h, v in out.items()})
    for h, v in out.items():
        v["padj"] = adj.get(h)
        v["ok"] = bool(rej.get(h) and (v.get("h1") or 0) > 0 and (v.get("h2") or 0) > 0)
    return out


# ── 研究檔 ────────────────────────────────────────────────────────────────

def _r(x):
    """浮點數留 5 位有效數字（比例、差、波動的分組界線都夠用）。"""
    if x is None:
        return None
    if isinstance(x, float):
        return None if math.isnan(x) else float(f"{x:.5g}")
    if isinstance(x, dict):
        return {a: _r(b) for a, b in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(b) for b in x]
    return x


def inputs_all() -> dict:
    from . import bubble as BU
    from . import heatcalc_us as HU
    BX = BU.compute()
    I = {"tw": tw_inputs(BX=BX)}
    BA = HU.build_all()
    for idx in ("spx", "ixic", "ndx", "sox"):
        I[idx] = us_inputs(idx, Bu=BA[idx], BX=BX)
    return I


def research(I: dict | None = None, with_oos: bool = True) -> dict:
    I = I if I is not None else inputs_all()
    M = {mk: market(mk, I[mk], with_oos) for mk in S.MARKETS}
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "markets": _r(M), "primary": _r(primary(M, I))}


def save_research(R: dict) -> None:
    RESEARCH.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load_research() -> dict | None:
    try:
        R = json.loads(RESEARCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None


# ── 每天建頁：今天的狀態 ──────────────────────────────────────────────────

def vol_state(mk: str, I: dict) -> dict:
    """今天的 20 日波動（描述，不是檢定）：在全部日子裡的百分位、落在哪一組（全部日子的三分位），
    以及同一組波動的日子之後五種大跌的比例（A5 是平均）和全部日子比。"""
    px = I["px"]
    vol = vol20(px)
    t = len(px) - 1
    vt = None if t < 0 or math.isnan(vol[t]) else float(vol[t])
    out: dict = {"vol": vt, "pct": None, "g": None, "rows": {}}
    ok = ~np.isnan(vol)
    if vt is None or ok.sum() < S.VOL_GROUPS:
        return out
    cuts = terciles(vol[ok])
    g = np.where(ok, groups(vol, cuts), -1)
    out.update({"pct": float((vol[ok] < vt).mean()), "g": int((vt >= cuts[0]) + (vt >= cuts[1])),
                "cuts": [cuts[0], cuts[1]], "a": I["cal"][int(np.argmax(ok))]})
    A = outcomes(px, S.TH[mk])
    for o in S.OUTCOMES:
        m = ok & ~np.isnan(A[o])
        mg = m & (g == out["g"])
        if m.any() and mg.any():
            out["rows"][o] = {"g": float(A[o][mg].mean()), "ng": int(mg.sum()), "all": float(A[o][m].mean()), "n": int(m.sum())}
    return out


def now(mk: str, I: dict, R: dict | None) -> dict:
    """今天（日曆最後一天）每個預測變數的 0～100、熱不熱、今天的波動落在研究檔哪一組。"""
    cal, px = I["cal"], I["px"]
    vol = vol20(px)
    t = len(cal) - 1
    rm = ((R or {}).get("markets") or {}).get(mk) or {}
    out = {"d": cal[t], "vol": None if math.isnan(vol[t]) else float(vol[t]), "preds": {}}
    for p in S.PRED[mk]:
        x = I["x"].get(p)
        v = None if x is None or math.isnan(x[t]) else float(x[t])
        rp = (rm.get("preds") or {}).get(p) or {}
        gs = {}
        for o, r in (rp.get("out") or {}).items():
            cuts = r.get("cuts")
            if cuts and out["vol"] is not None:
                gs[o] = int((out["vol"] >= cuts[0]) + (out["vol"] >= cuts[1]))
        out["preds"][p] = {"v": v, "hot": None if v is None else v >= S.HOT, "g": gs}
    return out
