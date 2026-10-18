"""泡沫面向的模型（docs/lab_heat_us_plan.md 第 15.5 節；規格 heatspec 的 PSY、TREND、LPPLS、RUNUP_DAYS、ACC_DAYS）。

台股頁（VER 7）與美股頁（VER 1）共用；每個值都只用當天（當月）以前的資料。
  · PSY 爆炸性檢定（Phillips、Shi、Yu 2015）：BSADF＝所有起點、視窗至少 w0 期的 ADF（只放截距、落後 0 期）最大值；
    臨界值用「沒有泡沫」的隨機漫步模擬（psy_cv，numpy，研究時算一次存 data/lab/heat/psy_cv）；
  · 長期趨勢偏離：對數實質價格對時間的擴張視窗線性回歸，z＝偏離 ÷ 殘差標準差；
  · LPPLS 泡沫信心：125 個視窗在 (m, ω, tc) 網格上找殘差最小的一組（numpy）；正規方程式的左邊和日期無關，
    整個網格的反矩陣先算好，每個日期只算右邊（所以一個日期幾十毫秒）；
  · 兩年漲幅、加速度、扣掉 S&P 500 的兩年漲幅。
純 Python 的部分（PSY 統計量、趨勢偏離、漲幅）每天建頁用；numpy 的部分（PSY 模擬、LPPLS）只在研究與每日抓取時用。
"""
from __future__ import annotations

import math
from datetime import date

from . import heatdata as HD
from . import heatspec as S


# ── PSY：BSADF ──────────────────────────────────────────────────────────

def _prefix(y: list[float]) -> tuple[list, list, list, list, list]:
    """回歸 Δy_s ＝ α ＋ β y_{s−1}（s＝1…n−1）的前綴和：x＝y_{s−1}、z＝Δy_s；P[k]＝s＝1…k 的和。"""
    px, pz, pxx, pzz, pxz = [0.0], [0.0], [0.0], [0.0], [0.0]
    for s in range(1, len(y)):
        x, z = y[s - 1], y[s] - y[s - 1]
        px.append(px[-1] + x)
        pz.append(pz[-1] + z)
        pxx.append(pxx[-1] + x * x)
        pzz.append(pzz[-1] + z * z)
        pxz.append(pxz[-1] + x * z)
    return px, pz, pxx, pzz, pxz


def adf_window(P: tuple, r1: int, t: int) -> float | None:
    """視窗 [r1, t]（含兩端的點）的 ADF t 值：回歸用 s＝r1＋1…t。"""
    px, pz, pxx, pzz, pxz = P
    n = t - r1
    if n < 3:
        return None
    sx, sz = px[t] - px[r1], pz[t] - pz[r1]
    sxx, szz, sxz = pxx[t] - pxx[r1], pzz[t] - pzz[r1], pxz[t] - pxz[r1]
    dxx = sxx - sx * sx / n
    if dxx <= 1e-15:
        return None
    b = (sxz - sx * sz / n) / dxx
    a = (sz - b * sx) / n
    ssr = szz - a * sz - b * sxz
    s2 = ssr / (n - 2)
    if s2 <= 0:
        return None
    return b / math.sqrt(s2 / dxx)


def bsadf(y: list[float], w0: int, start: int = 0) -> list[float | None]:
    """y＝一條沒有缺值的序列；回 BSADF(t)（t＝0…n−1；t < w0 − 1 為 None）。start＞0 只算 t ≥ start（之前 None）。
    BSADF(t)＝max over r1 ∈ [0, t − w0 ＋ 1] 的 ADF(r1, t)。"""
    P = _prefix(y)
    out: list = [None] * len(y)
    for t in range(max(w0 - 1, start), len(y)):
        best = None
        for r1 in range(0, t - w0 + 2):
            v = adf_window(P, r1, t)
            if v is not None and (best is None or v > best):
                best = v
        out[t] = best
    return out


def psy_cv(w0: int, reps: int, nmax: int, seed: int, qs: tuple = (0.5, 0.95), chunk: int = 250) -> dict:
    """「沒有泡沫」（隨機漫步、常態增量）的 BSADF 分位數：第 n 個點（n＝t＋1）的 qs 分位數。numpy，研究時算一次。"""
    import numpy as np
    rng = np.random.default_rng(seed)
    out = {f"q{int(round(q * 100))}": [None] * nmax for q in qs}
    stats = np.full((reps, nmax), np.nan)
    for a in range(0, reps, chunk):
        b = min(reps, a + chunk)
        y = np.cumsum(rng.standard_normal((b - a, nmax)), axis=1)
        x, z = y[:, :-1], np.diff(y, axis=1)
        zero = np.zeros((b - a, 1))
        px = np.hstack([zero, np.cumsum(x, axis=1)])
        pz = np.hstack([zero, np.cumsum(z, axis=1)])
        pxx = np.hstack([zero, np.cumsum(x * x, axis=1)])
        pzz = np.hstack([zero, np.cumsum(z * z, axis=1)])
        pxz = np.hstack([zero, np.cumsum(x * z, axis=1)])
        for t in range(w0 - 1, nmax):
            r1 = np.arange(0, t - w0 + 2)
            n = (t - r1).astype(float)
            sx = px[:, t:t + 1] - px[:, r1]
            sz = pz[:, t:t + 1] - pz[:, r1]
            sxx = pxx[:, t:t + 1] - pxx[:, r1]
            szz = pzz[:, t:t + 1] - pzz[:, r1]
            sxz = pxz[:, t:t + 1] - pxz[:, r1]
            with np.errstate(invalid="ignore", divide="ignore"):
                dxx = sxx - sx * sx / n
                bb = (sxz - sx * sz / n) / dxx
                aa = (sz - bb * sx) / n
                s2 = (szz - aa * sz - bb * sxz) / (n - 2)
                tv = bb / np.sqrt(s2 / dxx)
            stats[a:b, t] = np.nanmax(np.where(n >= 3, tv, np.nan), axis=1)
    for q in qs:
        key = f"q{int(round(q * 100))}"
        col = np.nanquantile(stats[:, w0 - 1:], q, axis=0)
        out[key][w0 - 1:] = [round(float(v), 6) for v in col]
    return {"w0": w0, "reps": reps, "nmax": nmax, "seed": seed, **out}


def psy_heat(stat: float | None, q50: float | None, q95: float | None) -> float | None:
    """BSADF → 0～100：中位數＝lo、95% 臨界值＝hi（heatspec.PSY["map"]），線性換算、截在 0～100。"""
    if stat is None or q50 is None or q95 is None or q95 <= q50:
        return None
    lo, hi = S.PSY["map"]
    return max(0.0, min(100.0, lo + (hi - lo) * (stat - q50) / (q95 - q50)))


def load_cv() -> dict | None:
    cv = HD.load("psy_cv")
    p = S.PSY
    if not cv or cv.get("w0") != p["w0"] or cv.get("reps") != p["reps"] or cv.get("seed") != p["seed"]:
        return None
    return cv


def psy_monthly(M: dict, cv: dict | None) -> tuple[dict, dict]:
    """月序列 {YYYY-MM: 對數實質價格}（連續月份；中間缺月就從缺口之後重新起算）→（{月: BSADF}, {月: 0～100}）。"""
    ks = sorted(M)
    raw, heat = {}, {}
    seg: list[str] = []
    segs = []
    for k in ks:                                             # 依連續月份切段
        if seg and _months(seg[-1], k) != 1:
            segs.append(seg)
            seg = []
        seg.append(k)
    if seg:
        segs.append(seg)
    w0 = S.PSY["w0"]
    for sg in segs:
        st = bsadf([M[k] for k in sg], w0)
        for i, (k, v) in enumerate(zip(sg, st)):
            if v is None:
                continue
            raw[k] = v
            if cv and i < len(cv["q50"]):
                h = psy_heat(v, cv["q50"][i], cv["q95"][i])
                if h is not None:
                    heat[k] = h
    return raw, heat


def _months(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


# ── 長期趨勢偏離 ─────────────────────────────────────────────────────────

def trend_z(M: dict, min_n: int) -> tuple[dict, dict]:
    """{YYYY-MM: 對數實質價格} → （{月: z}, {月: 0～100}）；擴張視窗：用到當月為止的全部月份做 OLS（x＝月序號），
    至少 min_n 個月；z＝（當月 − 趨勢）÷ 殘差標準差（自由度 n − 2）。殘差平方和用中心化的累加，避免大數相減。"""
    ks = sorted(M)
    if not ks:
        return {}, {}
    base = ks[0]
    lo, k15 = S.TREND["map"]
    zs, hs = {}, {}
    xs: list[float] = []
    ys: list[float] = []
    for k in ks:
        xs.append(float(_months(base, k)))
        ys.append(M[k])
        n = len(xs)
        if n < min_n:
            continue
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        b = sxy / sxx
        a = my - b * mx
        ssr = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
        s = math.sqrt(ssr / (n - 2)) if ssr > 0 else 0.0
        if s <= 0:
            continue
        z = (ys[-1] - a - b * xs[-1]) / s
        zs[k] = z
        hs[k] = max(0.0, min(100.0, lo + k15 * z))
    return zs, hs


def detrended_pct(M: dict, min_n: int) -> dict:
    """{YYYY-MM: 比率} → {月: 比長期趨勢高幾 %}（取對數、擴張視窗 OLS、至少 min_n 個月；100 ×（比率 ÷ 趨勢 − 1））。"""
    L = {k: math.log(v) for k, v in M.items() if v and v > 0}
    ks = sorted(L)
    out = {}
    if not ks:
        return out
    base = ks[0]
    xs: list[float] = []
    ys: list[float] = []
    for k in ks:
        xs.append(float(_months(base, k)))
        ys.append(L[k])
        n = len(xs)
        if n < min_n:
            continue
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        a = my - b * mx
        out[k] = 100.0 * (math.exp(ys[-1] - a - b * xs[-1]) - 1.0)
    return out


# ── 兩年漲幅、加速度 ─────────────────────────────────────────────────────

def runup(px: list, h: int) -> list:
    """收盤 ÷ h 個交易日前 − 1（%）。"""
    return [None if i < h or not px[i] or not px[i - h] else 100.0 * (px[i] / px[i - h] - 1.0) for i in range(len(px))]


def accel(px: list, h_long: int, h_short: int) -> list:
    """h_short 日對數漲幅 − h_long 日對數漲幅 × h_short / h_long（百分點）。"""
    out: list = [None] * len(px)
    for i in range(h_long, len(px)):
        a, b, c = px[i], px[i - h_short], px[i - h_long]
        if a and b and c:
            out[i] = 100.0 * (math.log(a / b) - math.log(a / c) * h_short / h_long)
    return out


def net_runup(px: list, ref: list, h: int) -> list:
    """兩年對數漲幅 − 參考指數同期兩年對數漲幅（百分點）；px、ref 同一條交易日曆。"""
    out: list = [None] * len(px)
    for i in range(h, len(px)):
        a, b, c, d = px[i], px[i - h], ref[i], ref[i - h]
        if a and b and c and d:
            out[i] = 100.0 * (math.log(a / b) - math.log(c / d))
    return out


# ── LPPLS（numpy） ──────────────────────────────────────────────────────

class LPPLSGrid:
    """網格與正規方程式左邊的反矩陣（和日期無關）。τ＝t2 − t（0＝最後一天）。"""
    COND_MAX = 1e8

    def __init__(self, spec: dict | None = None):
        import numpy as np
        L = spec or S.LPPLS
        self.spec = L
        a, b, step = L["dt"]
        self.dts = np.arange(b, a - 1, -step)                    # 650、645、…、30
        self.N = int(self.dts.max()) + 1
        m = np.array(L["m"], float)
        w = np.array(L["w"], float)
        d = np.array(L["tc"], float)
        tau = np.arange(self.N, dtype=float)
        lg = np.log(d[:, None] + tau[None, :])                   # (δ, τ)
        F = np.exp(m[:, None, None] * lg[None])                  # (m, δ, τ)
        C = np.cos(w[:, None, None] * lg[None])                  # (ω, δ, τ)
        Sn = np.sin(w[:, None, None] * lg[None])
        G = F[:, None] * C[None]                                 # (m, ω, δ, τ)
        Hh = F[:, None] * Sn[None]
        self.m, self.w, self.d, self.F, self.G, self.H = m, w, d, F, G, Hh
        idx = self.dts
        cs = lambda x: np.cumsum(x, axis=-1)[..., idx]           # noqa: E731 —— τ＝0…dt 的和
        n = (idx + 1).astype(float)
        sf = cs(F)[:, None]                                      # (m, 1, δ, W)
        sg, sh = cs(G), cs(Hh)
        sff = cs(F * F)[:, None]
        sgg, shh = cs(G * G), cs(Hh * Hh)
        sfg, sfh, sgh = cs(F[:, None] * G), cs(F[:, None] * Hh), cs(G * Hh)
        shape = sg.shape
        A = np.empty(shape + (4, 4))
        one = np.broadcast_to(n, shape)
        sfb, sffb = np.broadcast_to(sf, shape), np.broadcast_to(sff, shape)
        rows = [[one, sfb, sg, sh], [sfb, sffb, sfg, sfh], [sg, sfg, sgg, sgh], [sh, sfh, sgh, shh]]
        for i in range(4):
            for j in range(4):
                A[..., i, j] = rows[i][j]
        tr = np.trace(A, axis1=-2, axis2=-1)[..., None, None]
        A = A + 1e-12 * tr * np.eye(4)                           # 近乎共線時穩住
        self.Ainv = np.linalg.inv(A)
        # 數值上近乎共線的組合（各欄標準化後條件數 ≥ COND_MAX，例如 m 很小、tc 很遠時 f 幾乎是常數）解不準、
        # 殘差平方和用正規方程式算會被捨入誤差弄成負的 → 這些組合不用（和日期無關，先算好）
        dg = np.sqrt(np.diagonal(A, axis1=-2, axis2=-1))
        An = A / (dg[..., :, None] * dg[..., None, :])
        self.ok = np.linalg.cond(An) < self.COND_MAX

    def fit(self, lnp):
        """lnp＝最近 N 個對數收盤（最後一個＝t2）。→（正泡沫比例, 負泡沫比例）；筆數不夠回 None。"""
        import numpy as np
        L = self.spec
        if len(lnp) < self.N:
            return None
        y = np.asarray(lnp[-self.N:], float)[::-1]               # y[τ]
        idx = self.dts
        cs = lambda x: np.cumsum(x, axis=-1)[..., idx]           # noqa: E731
        sy, syy = np.cumsum(y)[idx], np.cumsum(y * y)[idx]
        syf = cs(self.F * y)[:, None]
        syg, syh = cs(self.G * y), cs(self.H * y)
        shape = syg.shape
        rhs = np.stack([np.broadcast_to(sy, shape), np.broadcast_to(syf, shape), syg, syh], axis=-1)
        beta = np.einsum("...ij,...j->...i", self.Ainv, rhs)
        sse = np.broadcast_to(syy, shape) - np.einsum("...i,...i->...", beta, rhs)
        sse = np.where(self.ok & (sse >= 0), sse, np.inf)
        nm, nw, nd, nW = shape
        flat = sse.reshape(-1, nW)
        best = np.argmin(flat, axis=0)                            # 每個視窗誤差最小的一組
        pos = neg = 0
        for k in range(nW):
            im, iw, idl = np.unravel_index(best[k], (nm, nw, nd))
            A_, B_, C1, C2 = beta[im, iw, idl, k]
            m, w, dl, dt = self.m[im], self.w[iw], self.d[idl], int(idx[k])
            Cabs = math.hypot(C1, C2)
            if not (L["m_ok"][0] <= m <= L["m_ok"][1] and L["w_ok"][0] <= w <= L["w_ok"][1]):
                continue
            if dl > L["tc_ok"] * dt or Cabs <= 0:
                continue
            if (w / 2.0) * math.log((dl + dt) / dl) < L["osc"] or m * abs(B_) / (w * Cabs) < L["damp"]:
                continue
            fit = A_ + B_ * self.F[im, idl, :dt + 1] + C1 * self.G[im, iw, idl, :dt + 1] + C2 * self.H[im, iw, idl, :dt + 1]
            err = np.max(np.abs(np.exp(fit - y[:dt + 1]) - 1.0))
            if err > L["err"]:
                continue
            if B_ < 0:
                pos += 1
            elif B_ > 0:
                neg += 1
        return pos / nW, neg / nW


def week_last_days(ds: list[str]) -> list[str]:
    """每週（ISO 週）最後一個交易日。"""
    out = []
    for i, d in enumerate(ds):
        if i == len(ds) - 1 or date.fromisoformat(ds[i + 1]).isocalendar()[:2] != date.fromisoformat(d).isocalendar()[:2]:
            out.append(d)
    return out


def lppls_series(px: dict, have: dict | None = None, grid: LPPLSGrid | None = None, last_only: bool = False) -> dict:
    """{日期: 收盤} → {週末交易日: [正泡沫 %, 負泡沫 %]}（已有的週不重算；最後一週若還沒結束也先算，下次再覆蓋）。"""
    ds = sorted(d for d, v in px.items() if v and v > 0)
    lnp = [math.log(px[d]) for d in ds]
    pos = {d: i for i, d in enumerate(ds)}
    want = week_last_days(ds)
    have = have or {}
    if last_only:
        want = want[-1:]
    grid = grid or LPPLSGrid()
    out = {}
    for d in want:
        if d in have and d != ds[-1]:
            continue
        i = pos[d]
        r = grid.fit(lnp[:i + 1])
        if r is not None:
            out[d] = [round(100.0 * r[0], 2), round(100.0 * r[1], 2)]
    return out


def lppls_update(name: str, px: dict) -> int:
    """每天：只補新的週（整段歷史在研究時算好）。檔裡最後一筆可能是還沒結束的那一週（週中算的），
    一律拿掉、從那一週起重算，所以每天補出來的檔和整段一次算的一樣（每週只留最後一個交易日）。"""
    have = HD.load(name)
    if not have:
        raise RuntimeError(f"{name} 還沒有歷史（先跑 scripts/run_heat_us.py --lppls）")
    last = max(have)
    if last >= max(px or {last: 0}) and last in px:
        return 0
    keep = {d: v for d, v in have.items() if d < last}
    new = {d: v for d, v in lppls_series(px, keep).items() if d >= last}
    out = {**keep, **new}
    n = sum(1 for d, v in out.items() if have.get(d) != v) + sum(1 for d in have if d not in out)
    if n:
        HD.save(name, "lppls_grid", out)
    return n


def lppls_heat(pos: float | None, neg: float | None) -> float | None:
    if pos is None or neg is None:
        return None
    lo, k = S.LPPLS["map"]
    return max(0.0, min(100.0, lo + k * (pos - neg) / 100.0))


# ── 台股：1990 起的每日加權指數 ─────────────────────────────────────────────

def taiex_daily(D: dict | None = None) -> dict:
    """1990～1998 用證交所 FMTQIK（taiex90），1999 起用台股頁的交易日曆與收盤（官方為主、Yahoo 補）。"""
    from . import heatcalc as C
    D = D if D is not None else {n: HD.load(n) for n in ("turnover", "taiex")}
    cal, px, _ = C.calendar(D)
    out = {d: v for d, v in zip(cal, px) if v}
    t90 = D.get("taiex90") if "taiex90" in D else HD.load("taiex90")
    for d, v in (t90 or {}).items():                        # 1998 年以前一律用證交所官方（Yahoo 只補 1997～1998 官方沒有的天）
        if v and d < "1999-01-01":
            out[d] = v
    return out
