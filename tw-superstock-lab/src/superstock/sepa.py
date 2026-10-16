"""W2 研究版（reports/W2_plan.md v1，跑之前寫定）：每天每檔的《超級績效》技術狀態、樞紐、停損、加分，以及評估。

狀態轉換（Track）、第幾個基底（base_counts）、爆發型（pp_at）、加分（score）直接用 fuhhwa arm/lab/sepa.py
（頁面同一套）；緊密整理、RS 線、200 日線上揚天數、量價足跡用 pandas 向量化，tests 逐日比對兩邊一致。
決策只用 t 日收盤（含）以前的資料；進場一律隔天開盤；結果（之後的漲跌）只拿來評估。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import features as FT
from . import labpanel as LP

GRID = [(10, 0.06), (10, 0.08), (10, 0.10), (15, 0.06), (15, 0.08), (15, 0.10)]
DEDUP = 20
KCODE = {"vcp": 1, "tight": 2, "pp": 3}


def shared():
    LP.arm()
    from arm.lab import sepa as SP  # noqa: WPS433

    return SP


def _l(a: np.ndarray) -> list:
    return [None if x != x else float(x) for x in a.tolist()]


# ---------------------------------------------------------------------------------------------- 指標
def tight(m, hi52: np.ndarray, K: int, X: float, near: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """緊密整理（同 SP.tight_at）：近 K 日最高 ÷ 最低 − 1 ≤ X，且收盤 ≥ 52 週高點 × near → (成立, 樞紐, 整理低點)。"""
    H = pd.DataFrame(m.h).rolling(K, min_periods=K - 2).max().to_numpy()
    L = pd.DataFrame(m.l).rolling(K, min_periods=K - 2).min().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        ok = (L > 0) & (H / L - 1 <= X) & (m.c >= near * hi52)
    return ok, H, L


def rs_line(m) -> tuple[np.ndarray, np.ndarray]:
    """RS 線＝含息收盤 ÷ 加權報酬指數。→ (創 252 日新高, 創新高而收盤還沒創 252 日新高＝領先)。"""
    tr = m.index_tr.to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        rsl = m.c_ff / tr[:, None]
    mx = pd.DataFrame(rsl).rolling(252, min_periods=200).max().to_numpy()
    pmx = pd.DataFrame(m.c_ff).rolling(252, min_periods=200).max().to_numpy()
    with np.errstate(invalid="ignore"):
        new = rsl >= mx
        lead = new & ~(m.c_ff >= pmx)
    return new, lead


def ma200_up(m) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """200 日線（前值補齊收盤）、20 日前的 200 日線、連續上揚天數（今天 > 昨天）。"""
    ma = pd.DataFrame(m.c_ff).rolling(200, min_periods=200).mean()
    up = (ma > ma.shift(1)).to_numpy()
    out = np.zeros(up.shape, dtype=np.int32)
    for t in range(1, len(out)):
        out[t] = np.where(up[t], out[t - 1] + 1, 0)
    return ma.to_numpy(), ma.shift(20).to_numpy(), out


def ud_ratio(m, n: int = 50) -> np.ndarray:
    """近 n 日上漲日量 ÷ 下跌日量（同 SP.ud_at）；有效天數 < n × 0.8 → NaN；沒有下跌日 → inf。"""
    prev = pd.DataFrame(m.c).ffill().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        ch = m.c - prev
    valid = ~np.isnan(ch) & ~np.isnan(m.vol)
    v = np.where(valid, m.vol, 0.0)
    with np.errstate(invalid="ignore"):
        up = np.where(valid & (ch > 0), v, 0.0)
        dn = np.where(valid & (ch < 0), v, 0.0)

    def roll(a):
        return pd.DataFrame(a).rolling(n, min_periods=1).sum().to_numpy()

    su, sd, cnt = roll(up), roll(dn), roll(valid.astype(float))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(sd > 0, su / np.where(sd > 0, sd, 1.0), np.where(su > 0, np.inf, np.nan))
    r[cnt < int(n * 0.8)] = np.nan
    r[: n - 1] = np.nan
    return r


def base_no(m, ma200: np.ndarray, ma200p: np.ndarray, cols: np.ndarray | None = None) -> np.ndarray:
    SP = shared()
    T, N = m.c.shape
    out = np.zeros((T, N), dtype=np.int16)
    for j in (range(N) if cols is None else cols):
        out[:, j] = SP.base_counts(_l(m.c_ff[:, j]), _l(ma200[:, j]), _l(ma200p[:, j]))
    return out


def power_play(m, el: np.ndarray, vol50: np.ndarray, dry: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """爆發型（同 SP.pp_at）。先用「近 71 日內有一天收盤 ÷ 之前 40 日最低收盤 ≥ 2」篩候選（pp_at 成立的必要條件）。"""
    SP = shared()
    T, N = m.c.shape
    C = pd.DataFrame(m.c_ff)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = C / C.rolling(41, min_periods=1).min()
    cand = (ratio.rolling(71, min_periods=1).max() >= SP.PP["mult"]).to_numpy() & el
    cand[:SP.PP["look"] + SP.PP["surge_days"]] = False
    ok = np.zeros((T, N), dtype=bool)
    piv, low = np.full((T, N), np.nan), np.full((T, N), np.nan)
    raw = m.c / m.f
    for j in np.flatnonzero(cand.any(axis=0)):
        h, l, c, v, v50 = _l(m.h[:, j]), _l(m.l[:, j]), _l(m.c_ff[:, j]), _l(m.vol[:, j]), _l(vol50[:, j])
        for t in np.flatnonzero(cand[:, j]):
            rc, dy = raw[t, j], dry[t, j]
            r = SP.pp_at(h, l, c, v, v50, None if rc != rc else float(rc), None if dy != dy else float(dy), int(t))
            if r:
                ok[t, j] = True
                piv[t, j], low[t, j] = r
    return ok, piv, low


def statuses(m, F: dict, S9: np.ndarray, PP: tuple, TG: tuple) -> dict[str, np.ndarray]:
    """每天每檔的狀態（SP.Track）：−1 不在名單、0 打底中、1 今天突破、2 突破後仍在買點、3 準備好、4 突破失敗、5 漲太遠。"""
    SP = shared()
    T, N = m.c.shape
    st = np.full((T, N), -1, dtype=np.int8)
    piv, low = np.full((T, N), np.nan), np.full((T, N), np.nan)
    kind = np.zeros((T, N), dtype=np.int8)
    ppok, pppiv, pplow = PP
    tok, tH, tL = TG
    el, vok, vpiv, vlow = F["elig"], F["vcp_ok"], F["vcp_pivot"], F["vcp_low"]
    v50, dry, ma50 = F["vol50"], F["dry"], F["ma50"]
    on_all = S9 | ppok
    for j in np.flatnonzero(on_all.any(axis=0)):
        t0 = int(np.argmax(on_all[:, j]))
        c, vol, v5, dy, m50 = (_l(a[:, j]) for a in (m.c, m.vol, v50, dry, ma50))
        s9, pj, e = S9[:, j], ppok[:, j], el[:, j]
        tr = SP.Track()
        for t in range(t0, T):
            on9, onp = bool(s9[t]), bool(pj[t])
            on = on9 or onp
            ready = None
            if on and c[t] is not None:
                vc = (float(vpiv[t, j]), float(vlow[t, j])) if vok[t, j] else None
                tg = (float(tH[t, j]), float(tL[t, j])) if tok[t, j] else None
                pp = (float(pppiv[t, j]), float(pplow[t, j])) if onp else None
                ready = SP.ready_at(on9, bool(e[t]), c[t], dy[t], vc, tg, pp)
            s, pv, lw, kd = tr.step(t, c[t], vol[t], v5[t - 1] if t else None, m50[t], on, ready)
            if s >= 0:
                st[t, j] = s
                if pv is not None:
                    piv[t, j], low[t, j], kind[t, j] = pv, (np.nan if lw is None else lw), KCODE[kd]
    return {"st": st, "piv": piv, "low": low, "kind": kind}


# ---------------------------------------------------------------------------------------------- 排序
def industry_counts(stocks: list[str], ind: dict, S9: np.ndarray) -> np.ndarray:
    """每天每檔：同產業有幾檔在名單上（含自己若在名單上）。"""
    names = sorted({ind[c] for c in stocks if c in ind})
    code = {n: i for i, n in enumerate(names)}
    g = np.array([code.get(ind.get(c), -1) for c in stocks])
    out = np.zeros(S9.shape, dtype=np.int16)
    has = g >= 0
    for t in range(S9.shape[0]):
        cnt = np.bincount(g[S9[t] & has], minlength=len(names))
        out[t, has] = cnt[g[has]]
    return out


def scores(ev: np.ndarray, F: dict, rsl_new, bno, maup, rnha, s1, ud, indn) -> np.ndarray:
    """ev（要排的格子）→ 加分總和（SP.score）；其餘格子 −1。"""
    SP = shared()
    out = np.full(ev.shape, -1, dtype=np.int8)
    rs = F["rs"]
    for t, j in zip(*np.nonzero(ev)):
        r = rs[t, j]
        u = ud[t, j]
        out[t, j] = sum(SP.score(None if r != r else float(r), bool(rsl_new[t, j]), int(bno[t, j]), int(maup[t, j]),
                                 bool(rnha[t, j]), bool(s1[t, j]), None if u != u else float(u), int(indn[t, j])))
    return out


def top_n(ev: np.ndarray, pts: np.ndarray, rs: np.ndarray, stocks: list[str], n: int) -> np.ndarray:
    """每天在 ev 的格子裡依（加分高、RS 高、代號）取前 n。"""
    out = np.zeros(ev.shape, dtype=bool)
    for t in np.flatnonzero(ev.any(axis=1)):
        js = np.flatnonzero(ev[t])
        order = sorted(js, key=lambda j: (-int(pts[t, j]), -(0 if rs[t, j] != rs[t, j] else rs[t, j]), stocks[j]))
        out[t, order[:n]] = True
    return out


# ---------------------------------------------------------------------------------------------- 評估
def entry(m, days: int = 3) -> np.ndarray:
    """隔天開盤；隔天沒成交往後找，3 天內都沒有 → NaN。"""
    out = np.full(m.c.shape, np.nan)
    for k in range(days, 0, -1):
        o = np.full(m.c.shape, np.nan)
        o[:-k] = m.o[k:]
        out = np.where(np.isnan(o), out, o)
    return out


def outcomes(m) -> dict[str, np.ndarray]:
    e = entry(m)
    fm60, fm250 = FT.fwd_max(m, 60), FT.fwd_max(m, 250)
    T = m.n

    def fwd_c(k):
        o = np.full(m.c.shape, np.nan)
        o[:T - k] = m.c_ff[k:]
        return o

    with np.errstate(invalid="ignore", divide="ignore"):
        A = np.where(np.isnan(fm60) | np.isnan(e), np.nan, (fm60 >= 1.5 * e).astype(float))
        B = np.where(np.isnan(fm250) | np.isnan(e), np.nan, (fm250 >= 2.0 * e).astype(float))
        r20, r60 = fwd_c(20) / e - 1, fwd_c(60) / e - 1
    return {"e": e, "A": A, "B": B, "r20": r20, "r60": r60}


def stop_first(m, cells: list[tuple[int, int]], e: np.ndarray, stop: np.ndarray, n: int = 60, up: float = 0.2) -> list:
    """每格：60 日內先跌破停損價（還沒漲到 +20%）→ 1；先漲到 +20% 或都沒碰到 → 0；資料不夠 → None。"""
    out = []
    T = m.n
    for t, j in cells:
        px, sp = e[t, j], stop[t, j]
        if px != px or sp != sp or t + n >= T:
            out.append(None)
            continue
        if px <= sp:
            out.append(1)
            continue
        res = 0
        for k in range(t + 1, t + n + 1):
            lo, hi = m.l[k, j], m.h[k, j]
            if lo == lo and lo <= sp:
                res = 1
                break
            if hi == hi and hi >= px * (1 + up):
                break
        out.append(res)
    return out


def dedup(mask: np.ndarray, gap: int = DEDUP) -> np.ndarray:
    """同一檔 gap 個交易日內只算第一天。"""
    out = np.zeros(mask.shape, dtype=bool)
    for j in np.flatnonzero(mask.any(axis=0)):
        last = -10 ** 9
        for t in np.flatnonzero(mask[:, j]):
            if t - last >= gap:
                out[t, j] = True
                last = t
    return out


def rate(x: np.ndarray, mask: np.ndarray) -> tuple[float | None, int]:
    v = x[mask]
    v = v[~np.isnan(v)]
    return (float(v.mean()) if len(v) else None), int(len(v))


def med(x: np.ndarray, mask: np.ndarray) -> float | None:
    v = x[mask]
    v = v[~np.isnan(v)]
    return float(np.median(v)) if len(v) else None
