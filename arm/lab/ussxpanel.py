"""美股飆股研究的面板（ussxspec VER 1；docs/lab_us_sleeve_plan.md 第 9 節）：資料分支的股價 → 交易日 × 代號的陣列。研究用，不上頁面。

  load()          全部代號（財報行事曆＋ETF）：含息開高低收、實際成交價、成交值、成交量、第一天／最後一天
  dv20(P)         20 日平均成交值（最近 20 個交易日相加 ÷ 20，沒成交的日子算 0）
  report_index()  每一檔每一天「拿得到的最新一次財報」在第幾個交易日公布（公布日的下一個交易日起才算）
  eligible(P)     ussxspec 的選股範圍（每一天）
資料根目錄＝ussxdata.data_dir()（環境變數 USSX_DIR 指到資料分支的 worktree）。
"""
from __future__ import annotations

import bisect
from datetime import date

import numpy as np

from . import ussxdata as UD
from . import ussxspec as X


def calendar(start: str = X.PX_START) -> list[str]:
    """交易日＝SPY 有收盤的日子。"""
    return [d for d in UD.load_px("SPY")["d"] if d >= start]


def split_mult(ds: list[str], spl: list) -> np.ndarray:
    """每一天的「實際成交價 ÷ 分割還原價」＝那天之後（不含當天以前生效的）每一次分割的倍數相乘。
    分割在生效日 d 開盤生效：d 當天與之後的價格不用換算，d 以前的乘倍數。"""
    m = np.ones(len(ds))
    for d, r in sorted(spl or []):
        if not (r and r > 0):
            continue
        j = bisect.bisect_left(ds, d)
        m[:j] *= float(r)
    return m


def tr_factor(p: dict) -> np.ndarray:
    """含息價 ÷ 分割還原價（ussxdata.total_return_close 同一套）。"""
    c = np.asarray(p["c"], dtype=float)
    if not len(c):
        return np.ones(0)
    tr = np.asarray(UD.total_return_close(p), dtype=float)
    return tr / c


def load(syms: list[str] | None = None, start: str = X.PX_START, etfs: tuple = UD.ETFS) -> dict:
    """{"cal", "sym", "col", "etf"（是不是 ETF）, "O","H","L","C"（含息）, "RAW"（實際成交價）, "CS"（分割還原收盤，不含息）,
    "DV"（成交值）, "V"（分割還原量）,
    "first","last"（第一天、最後一天有收盤的索引；沒有＝−1）}。沒有收盤的格子是 nan（成交值、量是 0）。"""
    cal = calendar(start)
    ix = {d: i for i, d in enumerate(cal)}
    if syms is None:
        meta = UD.load_meta()
        syms = sorted(s for s, n in meta["px_done"].items() if n)
    syms = sorted(set(syms))
    T, N = len(cal), len(syms)
    O, H, L, C = (np.full((T, N), np.nan) for _ in range(4))
    RAW = np.full((T, N), np.nan, dtype=np.float32)
    CS = np.full((T, N), np.nan, dtype=np.float32)
    DV = np.zeros((T, N))
    V = np.zeros((T, N), dtype=np.float32)
    first = np.full(N, -1, dtype=np.int64)
    last = np.full(N, -1, dtype=np.int64)
    for j, s in enumerate(syms):
        p = UD.load_px(s)
        if not p["d"]:
            continue
        f = tr_factor(p)
        mu = split_mult(p["d"], p["spl"])
        rows = [(k, ix[d]) for k, d in enumerate(p["d"]) if d in ix]
        if not rows:
            continue
        ks = np.array([k for k, _ in rows])
        ii = np.array([i for _, i in rows])
        c = np.asarray(p["c"])[ks]
        O[ii, j] = np.asarray(p["o"])[ks] * f[ks]
        H[ii, j] = np.asarray(p["h"])[ks] * f[ks]
        L[ii, j] = np.asarray(p["l"])[ks] * f[ks]
        C[ii, j] = c * f[ks]
        RAW[ii, j] = c * mu[ks]
        CS[ii, j] = c
        v = np.asarray(p["v"])[ks]
        DV[ii, j] = c * v
        V[ii, j] = v
        first[j], last[j] = ii[0], ii[-1]
    etf = np.array([s in set(etfs) for s in syms])
    return {"cal": cal, "sym": syms, "col": {s: j for j, s in enumerate(syms)}, "etf": etf,
            "O": O, "H": H, "L": L, "C": C, "RAW": RAW, "CS": CS, "DV": DV, "V": V, "first": first, "last": last}


def dv20(P: dict, n: int = 20) -> np.ndarray:
    """最近 n 個交易日（含當天）的成交值相加 ÷ n；前 n−1 天是 nan。"""
    DV = P["DV"]
    cs = np.cumsum(DV, axis=0)
    out = np.full(DV.shape, np.nan)
    out[n - 1] = cs[n - 1] / n
    out[n:] = (cs[n:] - cs[:-n]) / n
    return out


def age(P: dict) -> np.ndarray:
    """第 i 天距離第一天有收盤幾個交易日（沒有收盤的代號＝−1）。"""
    T = len(P["cal"])
    a = np.arange(T)[:, None] - P["first"][None, :]
    a[:, P["first"] < 0] = -1
    return a


def report_days(cal: list[str], syms: list[str], earn: dict[str, list] | None = None) -> dict[str, list[int]]:
    """每一檔每一次財報「拿得到」的交易日索引（公布日的下一個交易日；同一天公布兩次算一次），由小到大。
    earn＝{代號: [[公布日, 實際, 預估, 家數, 季度], ...]}（沒給就讀 usstk 的 earn/）。"""
    earn = earn if earn is not None else earnings()
    out = {}
    for s in syms:
        rs = earn.get(s) or []
        ks = sorted({bisect.bisect_right(cal, r[0]) for r in rs})
        out[s] = [k for k in ks if k < len(cal)]
    return out


def earnings(years: range | None = None) -> dict[str, list]:
    """usstk 的財報行事曆 → {Yahoo 代號: [[公布日, 實際 EPS, 預估 EPS, 預估家數, 季度], ...]}（依公布日排序）。"""
    from . import usstk as U
    UD.point_usstk()
    years = years or range(int(U.EARN_START[:4]), date.today().year + 1)
    out: dict[str, list] = {}
    for y in years:
        for d, rows in (U.load_earn(y).get("rows") or {}).items():
            for r in rows:
                if not r or not r[0]:
                    continue
                out.setdefault(UD.ysym(str(r[0])), []).append([d] + list(r[1:]))
    for v in out.values():
        v.sort(key=lambda r: r[0])
    return out


def last_report(T: int, days: list[int]) -> np.ndarray:
    """每一天拿得到的最新一次財報的索引（沒有＝−1）。"""
    out = np.full(T, -1, dtype=np.int64)
    for k in days:
        out[k:] = k
    return out


def eligible(P: dict, liq: float = X.LIQ_MIN, rep: dict[str, list[int]] | None = None, D20: np.ndarray | None = None,
             A: np.ndarray | None = None) -> np.ndarray:
    """ussxspec 的選股範圍：不是 ETF、那天有收盤、20 日平均成交值 ≥ liq、實際成交價 ≥ PX_MIN、有股價滿 AGE_MIN 天、
    最近一次拿得到的財報在 EPS_RECENT 個交易日以內。"""
    T, N = P["C"].shape
    D20 = dv20(P) if D20 is None else D20
    A = age(P) if A is None else A
    rep = rep if rep is not None else report_days(P["cal"], P["sym"])
    with np.errstate(invalid="ignore"):
        el = (~P["etf"][None, :]) & np.isfinite(P["C"]) & (np.nan_to_num(D20, nan=0.0) >= liq) & \
             (np.nan_to_num(P["RAW"], nan=0.0) >= X.PX_MIN) & (A >= X.AGE_MIN)
    ok = np.zeros((T, N), dtype=bool)
    t = np.arange(T)
    for j, s in enumerate(P["sym"]):
        if not el[:, j].any():
            continue
        lr = last_report(T, rep.get(s) or [])
        ok[:, j] = (lr >= 0) & (t - lr <= X.EPS_RECENT)
    return el & ok
