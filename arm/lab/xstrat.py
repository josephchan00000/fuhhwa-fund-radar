"""大神策略（規格 arm/lab/xstratspec.py；docs/lab_expert_plan.md）：照原作者的規則交易，算成績、判定與現在的狀態。

只用指數收盤與 VIX 收盤，五個市場全部算一次只要幾秒，所以每天建頁時重算（不另存研究檔；規則與門檻寫死在規格裡）：
  data(mk)              日曆、收盤、VIX（美股）
  market(mk, D)         一個市場全部策略的結果（成績、判定、參數鄰近、打亂測試、淨值、每一筆、現在）
  run_all()             五個市場（程序內快取，景氣頁與訊號總覽共用）
tests/test_xstrat.py 和逐筆直接算的版本比對。
"""
from __future__ import annotations

import itertools
import math
import zlib
from datetime import date, timedelta

import numpy as np

from . import xstratspec as S

# ── 資料 ───────────────────────────────────────────────────────────────────

def data(mk: str) -> dict:
    """{"mk", "cal": [日期], "px": 收盤, "vix": VIX 收盤（美股，對到同一個日曆；沒有＝nan）}。"""
    from . import heatdata as HD
    if mk == "tw":
        from . import heatbubble as BB
        ser = BB.taiex_daily()
    else:
        ser = HD.load(f"us_px_{mk}")
    cal = sorted(d for d, v in ser.items() if v)
    out = {"mk": mk, "cal": cal, "px": np.array([float(ser[d]) for d in cal])}
    if mk != "tw":
        vx = HD.load("vix") or {}
        out["vix"] = np.array([float(vx[d]) if vx.get(d) else np.nan for d in cal])
    return out


# ── 指標 ───────────────────────────────────────────────────────────────────

def sma(x: np.ndarray, n: int) -> np.ndarray:
    """簡單移動平均（含當天；窗內有 nan 或不滿 n 天＝nan）。"""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    ok = ~np.isnan(x)
    cs = np.concatenate([[0.0], np.cumsum(np.where(ok, x, 0.0))])
    cn = np.concatenate([[0], np.cumsum(ok)])
    s, c = cs[n:] - cs[:-n], cn[n:] - cn[:-n]
    out[n - 1:] = np.where(c == n, s / n, np.nan)
    return out


def rsi(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder RSI：第一個平均用前 n 天漲跌的簡單平均，之後（前值 ×（n−1）＋今天）÷ n。跌幅為 0＝100。"""
    x = np.asarray(x, dtype=float)
    T = len(x)
    out = np.full(T, np.nan)
    if T <= n:
        return out
    d = np.diff(x)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = float(up[:n].mean()), float(dn[:n].mean())
    out[n] = 100.0 if ad == 0 else 100.0 - 100.0 / (1.0 + au / ad)
    for i in range(n + 1, T):
        au = (au * (n - 1) + up[i - 1]) / n
        ad = (ad * (n - 1) + dn[i - 1]) / n
        out[i] = 100.0 if ad == 0 else 100.0 - 100.0 / (1.0 + au / ad)
    return out


def wilder_avgs(x: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """每一天的 Wilder 平均漲幅、跌幅（和 rsi() 同一條公式；前 n 天＝nan）。"""
    x = np.asarray(x, dtype=float)
    T = len(x)
    AU, AD = np.full(T, np.nan), np.full(T, np.nan)
    if T <= n:
        return AU, AD
    d = np.diff(x)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = float(up[:n].mean()), float(dn[:n].mean())
    AU[n], AD[n] = au, ad
    for i in range(n + 1, T):
        au = (au * (n - 1) + up[i - 1]) / n
        ad = (ad * (n - 1) + dn[i - 1]) / n
        AU[i], AD[i] = au, ad
    return AU, AD


def rsi_below_price(close: float, au: float, ad: float, n: int, r: float) -> float | None:
    """下一個交易日收盤要低於多少，n 日 RSI 才會 ＜ r（規格第 8 節 VER 2 的 P*；嚴格小於）。au、ad＝今天的 Wilder 平均。"""
    if not (au == au and ad == ad) or r <= 0 or r >= 100:
        return None
    k = r / (100.0 - r)
    d = (n - 1) * (k * ad - au) if k * ad > au else (n - 1) * (ad - au / k)
    return close + d


def month_ends(cal: list[str], last_is_end: bool = False) -> list[int]:
    """每個月最後一個交易日的位置；資料最後一天只有 last_is_end（照休市表確定是月底）才算。"""
    out = [k for k in range(len(cal) - 1) if cal[k][:7] != cal[k + 1][:7]]
    if cal and last_is_end:
        out.append(len(cal) - 1)
    return out


# ── 交易日曆（「現在」用：明天、這個月底、下一次月底月初） ───────────────────────────

def _closed(mk: str, d: date) -> bool:
    if d.weekday() >= 5:
        return True
    if mk == "tw":
        from .. import twholidays
        return bool(twholidays.is_closed(d))
    from ..usnews import _US_MKT_HOLIDAYS
    return d in _US_MKT_HOLIDAYS


def future_days(mk: str, last: str, n: int) -> list[str]:
    """last 之後的 n 個交易日（週末＋證交所／NYSE 休市表；表沒有涵蓋的平日當成開市）。"""
    out, x = [], date.fromisoformat(last)
    while len(out) < n:
        x += timedelta(days=1)
        if not _closed(mk, x):
            out.append(x.isoformat())
    return out


# ── 交易型 ─────────────────────────────────────────────────────────────────

def _next_true(flag: np.ndarray) -> np.ndarray:
    """nxt[i]＝i 起（含）第一個 flag 為真的位置；沒有＝len。"""
    T = len(flag)
    idx = np.where(flag, np.arange(T), T)
    return np.minimum.accumulate(idx[::-1])[::-1]


def sig_trades(setup: np.ndarray, exit_ok: np.ndarray, s0: int, lag: int) -> tuple[list[tuple], dict]:
    """訊號型（rsi2、vixs）：空手時第 t 天收盤 setup → 第 e＝t＋lag 天收盤買；出場訊號＝第一個 x ≥ max(e, t＋1) 的 exit_ok；
    第 q＝x＋lag 天收盤賣，q 起再看新的訊號。→ ([(t, e, x, q)], 資料最後的狀態)。"""
    T = len(setup)
    nxt = _next_true(np.asarray(exit_ok, dtype=bool))
    st = np.asarray(setup, dtype=bool)
    out = []
    i = s0
    while i < T:
        if not st[i]:
            i += 1
            continue
        e = i + lag
        if e >= T:
            return out, {"st": "buy", "t": i}
        x = int(nxt[max(e, i + 1)]) if max(e, i + 1) < T else T
        if x >= T:
            return out, {"st": "hold", "t": i, "e": e}
        q = x + lag
        if q >= T:
            return out, {"st": "sell", "t": i, "e": e, "x": x}
        out.append((i, e, x, q))
        i = q
    return out, {"st": "wait"}


def tom_trades(cal: list[str], s0: int, before: int, after: int, mk: str | None = None) -> tuple[list[tuple], dict]:
    """月底月初：每個月最後一個交易日 L，第 L−before 天收盤買、第 L＋after 天收盤賣。→ ([(e, e, q, q)], 現在)。
    現在（mk 有給才算）：照休市表推這個月底與之後的交易日。"""
    T = len(cal)
    ends = month_ends(cal)
    out = []
    for L in ends:
        e, q = L - before, L + after
        if e >= s0 and q < T:
            out.append((e, e, q, q))
    if not mk or not T:
        return out, {}
    fut = future_days(mk, cal[-1], 70)
    days = cal + fut
    allends = [k for k in range(len(days) - 1) if days[k][:7] != days[k + 1][:7]]
    last = T - 1
    for L in allends:
        e, q = L - before, L + after
        if q < last:
            continue
        if e <= last < q:
            st = "sell" if q == last + 1 else "hold"
            return out, {"st": st, "e": e, "ed": days[e], "qd": days[q]}
        if e == last + 1:
            return out, {"st": "buy", "ed": days[e], "qd": days[q]}
        if e > last:
            return out, {"st": "wait", "ed": days[e], "qd": days[q]}
    return out, {"st": "wait"}


def net(a: float, b: float, c: float) -> float:
    """買在 a、賣在 b，每一邊成本 c 的淨報酬。"""
    return b / a * (1.0 - c) / (1.0 + c) - 1.0


def base_win(px: np.ndarray, lo: int, hold: np.ndarray, c: float) -> tuple[float | None, float | None]:
    """隨便挑同樣天數：每一筆持有 h 天 → 第 lo 天起每一天買、抱 h 天（扣成本）賺錢的比例；再對每一筆平均（勝率、平均報酬）。"""
    if not len(hold):
        return None, None
    T = len(px)
    cache: dict = {}
    ws, rs = [], []
    for h in hold.tolist():
        if h not in cache:
            if lo + h >= T:
                cache[h] = (None, None)
            else:
                r = px[lo + h:] / px[lo:T - h] * (1.0 - c) / (1.0 + c) - 1.0
                cache[h] = (float((r > 0).mean()), float(r.mean()))
        w, m = cache[h]
        if w is not None:
            ws.append(w)
            rs.append(m)
    return (float(np.mean(ws)), float(np.mean(rs))) if ws else (None, None)


def trade_stats(px: np.ndarray, trades: list[tuple], lo: int, c: float) -> dict:
    """一組交易（只算 e ≥ lo 的）→ 筆數、勝率、平均、中位數、獲利因子、平均持有、最差、最好、隨便挑同樣天數。"""
    tr = [t for t in trades if t[1] >= lo]
    if not tr:
        return {"n": 0}
    r = np.array([net(px[e], px[q], c) for _, e, _, q in tr])
    h = np.array([q - e for _, e, _, q in tr])
    gain, loss = float(r[r > 0].sum()), float(-r[r < 0].sum())
    bw, br = base_win(px, lo, h, c)
    return {"n": len(tr), "win": float((r > 0).mean()), "avg": float(r.mean()), "med": float(np.median(r)),
            "pf": (gain / loss) if loss > 0 else None, "hold": float(h.mean()), "worst": float(r.min()), "best": float(r.max()),
            "base": bw, "base_avg": br}


def trade_held(T: int, trades: list[tuple]) -> np.ndarray:
    """held[t]＝第 t 天的漲跌（收盤 t−1 → t）有沒有持有。"""
    held = np.zeros(T, dtype=bool)
    for _, e, _, q in trades:
        held[e + 1:q + 1] = True
    return held


def trade_equity(px: np.ndarray, trades: list[tuple], lo: int, c: float) -> np.ndarray:
    """照做的淨值（第 lo 天收盤＝1；買進那天收盤除以 1＋成本、賣出那天收盤乘 1−成本；空手 0%）。"""
    T = len(px)
    tr = [t for t in trades if t[1] >= lo]
    held = trade_held(T, tr)
    r = np.ones(T)
    r[1:] = np.where(held[1:], px[1:] / px[:-1], 1.0)
    for _, e, _, q in tr:
        r[e] /= (1.0 + c)
        r[q] *= (1.0 - c)
    return np.cumprod(r[lo:])                          # 起始資金 1（第 lo 天收盤之前）；第 lo 天收盤就買的成本含在第一個值


# ── 進出型 ─────────────────────────────────────────────────────────────────

def pos_daily_ma(px: np.ndarray, n: int, lag: int) -> np.ndarray:
    """每天：收盤 > n 日均線＝1，否則 0（均線沒有值＝nan）；第 t＋lag 天收盤照做 → pos[k]＝第 k 天收盤之後的部位。"""
    m = sma(px, n)
    dec = np.where(np.isnan(m), np.nan, (px > m).astype(float))
    pos = np.full(len(px), np.nan)
    pos[lag:] = dec[:len(px) - lag] if lag else dec
    return pos


def _pos_monthly(T: int, ends: list[int], dec: list[float], lag: int) -> np.ndarray:
    pos = np.full(T, np.nan)
    for m, k in enumerate(ends):
        a = k + lag
        if a >= T:
            break
        b = ends[m + 1] + lag if m + 1 < len(ends) else T
        pos[a:min(b, T)] = dec[m]
    return pos


def pos_faber(px: np.ndarray, ends: list[int], n: int, lag: int) -> np.ndarray:
    """每個月底：收盤 > 最近 n 個月底收盤的平均（含這個月）＝1；第 月底＋lag 天收盤照做。"""
    mc = px[ends]
    dec = [np.nan if m < n - 1 else float(mc[m] > mc[m - n + 1:m + 1].mean()) for m in range(len(ends))]
    return _pos_monthly(len(px), ends, dec, lag)


def pos_mom(px: np.ndarray, ends: list[int], n: int, lag: int) -> np.ndarray:
    """每個月底：收盤 > n 個月前那個月底的收盤＝1。"""
    mc = px[ends]
    dec = [np.nan if m < n else float(mc[m] > mc[m - n]) for m in range(len(ends))]
    return _pos_monthly(len(px), ends, dec, lag)


def hal_months(start: int, months: int) -> set[int]:
    return {(start - 1 + j) % 12 + 1 for j in range(months)}


def pos_hal(cal: list[str], start: int, months: int, nxt: str | None = None) -> np.ndarray:
    """Halloween：pos[k]＝下一個交易日的月份在持有月份裡（＝那幾個月每一天的漲跌都算到）。nxt＝資料最後一天的下一個交易日。"""
    H = hal_months(start, months)
    T = len(cal)
    pos = np.full(T, np.nan)
    for k in range(T - 1):
        pos[k] = 1.0 if int(cal[k + 1][5:7]) in H else 0.0
    if nxt:
        pos[T - 1] = 1.0 if int(nxt[5:7]) in H else 0.0
    return pos


def alloc_equity(px: np.ndarray, pos: np.ndarray, lo: int, c: float) -> tuple[np.ndarray, int]:
    """照做的淨值（第 lo 天收盤＝1，照當時的部位開始，不算第一次進場成本）；第 k 天收盤換邊扣一次成本。→ (淨值, 換邊次數)。"""
    p = np.nan_to_num(pos, nan=0.0)
    T = len(px)
    r = np.ones(T)
    r[1:] = np.where(p[:-1] > 0, px[1:] / px[:-1], 1.0)
    sw = np.zeros(T, dtype=bool)
    sw[lo + 1:] = p[lo + 1:] != p[lo:-1]
    r[sw] *= (1.0 - c)
    r[lo] = 1.0                                         # 第 lo 天收盤才開始（那天的漲跌不算）
    return np.cumprod(r[lo:]), int(sw.sum())


def _years(cal: list[str], lo: int) -> float:
    return max(1e-9, (date.fromisoformat(cal[-1]) - date.fromisoformat(cal[lo])).days / 365.25)


def curve_stats(eq: np.ndarray, cal: list[str], lo: int) -> dict:
    """淨值（第 lo 天起）→ 年化、最大回撤、年化 ÷ 最大回撤、最差一個完整日曆年。"""
    yrs = _years(cal, lo)
    cagr = float(eq[-1] ** (1.0 / yrs) - 1.0)
    mdd = float((1.0 - eq / np.maximum.accumulate(eq)).max())
    worst = None
    seg = cal[lo:]
    last_of: dict = {}
    for i, d in enumerate(seg):
        last_of[d[:4]] = i
    ys = sorted(last_of)
    for a, b in zip(ys, ys[1:]):
        if b == cal[-1][:4]:
            break                                       # 今年還沒過完
        y = float(eq[last_of[b]] / eq[last_of[a]] - 1.0)
        worst = y if worst is None or y < worst else worst
    return {"cagr": cagr, "mdd": mdd, "mar": (cagr / mdd) if mdd > 0 else None, "worst": worst, "yrs": yrs}


def bh_stats(px: np.ndarray, cal: list[str], lo: int) -> dict:
    return curve_stats(px[lo:] / px[lo], cal, lo)


# ── 判定（規格第 6 節） ──────────────────────────────────────────────────────

def trade_pass(s: dict) -> bool:
    return bool(s.get("n", 0) >= S.TR_N_MIN and s["win"] >= S.TR_WIN and s.get("base") is not None
                and s["win"] - s["base"] >= S.TR_EDGE and s["avg"] > 0)


def trade_pass_recent(s: dict) -> bool | None:
    """近 10 年：不到 TR_N10 筆＝不看（None）；其餘同一條（不看全期間的筆數下限）。"""
    if s.get("n", 0) < S.TR_N10:
        return None
    return bool(s["win"] >= S.TR_WIN and s.get("base") is not None and s["win"] - s["base"] >= S.TR_EDGE and s["avg"] > 0)


def alloc_pass(s: dict, b: dict) -> bool:
    if s["mdd"] <= 0 or b["mdd"] <= 0:
        return False
    return bool(s["mdd"] <= S.AL_MDD * b["mdd"] and s["cagr"] / s["mdd"] >= b["cagr"] / b["mdd"])


def tier(kind: str, full_ok: bool, rec_ok: bool | None, grid_share: float | None, few: bool) -> str:
    if few:
        return "few"
    if not full_ok:
        return "none"
    if (rec_ok is None or rec_ok) and grid_share is not None and grid_share >= S.GRID_OK - 1e-12:
        return "good"
    return "ref"


# ── 打亂測試（規格第 7 節，只標示） ───────────────────────────────────────────

def rng_for(key: str) -> np.random.Generator:
    return np.random.default_rng([S.LUCK_SEED, zlib.crc32(key.encode("utf-8"))])


def _offsets(key: str, L: int) -> np.ndarray:
    lo = int(S.LUCK_SHIFT[0] * L)
    hi = max(lo + 1, int(S.LUCK_SHIFT[1] * L))
    return rng_for(key).integers(lo, hi, size=S.LUCK_DRAWS)


def luck_trade(px: np.ndarray, trades: list[tuple], lo: int, c: float, key: str) -> float | None:
    tr = [t for t in trades if t[1] >= lo]
    if not tr:
        return None
    T = len(px)
    L = T - lo
    e = np.array([t[1] for t in tr]) - lo
    h = np.array([t[3] - t[1] for t in tr])
    win = float(np.mean([net(px[a], px[b], c) > 0 for _, a, _, b in tr]))
    ge = 0
    for o in _offsets(key, L).tolist():
        e2 = lo + (e + o) % L
        q2 = e2 + h
        ok = q2 < T
        if not ok.any():
            continue
        r = px[q2[ok]] / px[e2[ok]] * (1.0 - c) / (1.0 + c) - 1.0
        if float((r > 0).mean()) >= win - 1e-12:
            ge += 1
    return (1 + ge) / (1 + S.LUCK_DRAWS)


def luck_alloc(px: np.ndarray, pos: np.ndarray, lo: int, c: float, cal: list[str], key: str) -> float | None:
    eq, _ = alloc_equity(px, pos, lo, c)
    st = curve_stats(eq, cal, lo)
    if st["mar"] is None:
        return None
    p = np.nan_to_num(pos, nan=0.0)
    held = p[lo:-1] > 0                                  # 第 lo＋1…T−1 天的漲跌有沒有持有
    L = len(held)
    rr = px[lo + 1:] / px[lo:-1]
    yrs = _years(cal, lo)
    ge = 0
    for o in _offsets(key, L).tolist():
        hs = np.roll(held, o)
        f = np.where(hs, rr, 1.0)
        sw = np.zeros(L, dtype=bool)
        sw[1:] = hs[1:] != hs[:-1]                       # 換邊在前一天收盤
        f[np.nonzero(sw)[0] - 1] *= (1.0 - c)
        e2 = np.concatenate([[1.0], np.cumprod(f)])
        mdd = float((1.0 - e2 / np.maximum.accumulate(e2)).max())
        if mdd <= 0:
            continue
        mar = (e2[-1] ** (1.0 / yrs) - 1.0) / mdd
        if mar >= st["mar"] - 1e-12:
            ge += 1
    return (1 + ge) / (1 + S.LUCK_DRAWS)


# ── 一個市場 ───────────────────────────────────────────────────────────────

def _combos(grid: dict) -> list[dict]:
    ks = list(grid)
    return [dict(zip(ks, vs)) for vs in itertools.product(*(grid[k] for k in ks))]


def _idx_from(cal: list[str], d: str) -> int:
    return next((i for i, x in enumerate(cal) if x >= d), len(cal))


def _recent_from(cal: list[str]) -> str:
    d = date.fromisoformat(cal[-1])
    try:
        return d.replace(year=d.year - S.RECENT_YEARS).isoformat()
    except ValueError:
        return d.replace(year=d.year - S.RECENT_YEARS, day=28).isoformat()


class Ctx:
    """一個市場算策略要的東西（指標只算一次）。"""

    def __init__(self, D: dict):
        self.mk, self.cal, self.px = D["mk"], list(D["cal"]), np.asarray(D["px"], dtype=float)
        self.vix = D.get("vix")
        self.T = len(self.cal)
        self.c = S.COST[self.mk]                         # 進出型（ETF）；交易型用 S.cost(市場, 策略)
        self.s0 = _idx_from(self.cal, S.EVAL_START[self.mk])
        self.r0 = _idx_from(self.cal, _recent_from(self.cal))
        self.fut = future_days(self.mk, self.cal[-1], 45) if self.T else []
        last_end = bool(self.fut) and self.fut[0][:7] != self.cal[-1][:7]
        self.ends = month_ends(self.cal)                 # 資料裡確定的月底（判定用，不含今天）
        self.ends_now = month_ends(self.cal, last_end)   # 今天如果就是月底也算（現在用）
        self.last_end = last_end
        self._sma: dict = {}
        self.rsi2 = rsi(self.px, 2)

    def ma(self, n: int) -> np.ndarray:
        if n not in self._sma:
            self._sma[n] = sma(self.px, n)
        return self._sma[n]

    def wilder(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        if ("w", n) not in self._sma:
            self._sma[("w", n)] = wilder_avgs(self.px, n)
        return self._sma[("w", n)]

    # 交易型
    def trades(self, k: str, p: dict, lag: int, now: bool = False) -> tuple[list[tuple], dict]:
        px = self.px
        if k == "rsi2":
            r = self.rsi2 if p["rsi_n"] == 2 else rsi(px, p["rsi_n"])
            setup = (px > self.ma(p["ma"])) & (r < p["rsi_max"])
            return sig_trades(setup, px > self.ma(p["exit_ma"]), self.s0, lag)
        if k == "vixs":
            v = self.vix
            m = sma(v, p["vix_ma"])
            st = np.nan_to_num(v, nan=-1.0) >= (1.0 + p["stretch"]) * np.nan_to_num(m, nan=np.inf)
            run = st.copy()
            for j in range(1, p["days"]):
                run[j:] &= st[:-j]
                run[:j] = False
            setup = run & (px > self.ma(p["ma"]))
            return sig_trades(setup, self.rsi2 > p["exit_rsi"], self.s0, lag)
        if k == "tom":
            return tom_trades(self.cal, self.s0, p["before"], p["after"], self.mk if now else None)
        raise KeyError(k)

    # 進出型
    def pos(self, k: str, p: dict, lag: int, now: bool = False) -> np.ndarray:
        ends = self.ends_now if now else self.ends
        if k == "faber":
            return pos_faber(self.px, ends, p["n"], lag)
        if k == "mom12":
            return pos_mom(self.px, ends, p["n"], lag)
        if k == "ma200":
            return pos_daily_ma(self.px, p["n"], lag)
        if k == "hal":
            return pos_hal(self.cal, p["start"], p["months"], self.fut[0] if (now and self.fut) else None)
        raise KeyError(k)


def _trade_eval(C: Ctx, k: str, p: dict, lag: int) -> dict:
    c = S.cost(C.mk, k)
    tr, _ = C.trades(k, p, lag)
    full = trade_stats(C.px, tr, C.s0, c)
    full["ok"] = trade_pass(full)
    eq = trade_equity(C.px, tr, C.s0, c)
    full.update({kk: v for kk, v in curve_stats(eq, C.cal, C.s0).items() if kk in ("cagr", "mdd")})
    full["expo"] = float(trade_held(C.T, [t for t in tr if t[1] >= C.s0])[C.s0 + 1:].mean()) if C.T > C.s0 + 1 else None
    return {"tr": tr, "full": full, "eq": eq}


def _alloc_eval(C: Ctx, k: str, p: dict, lag: int, lo: int | None = None) -> dict:
    lo = C.s0 if lo is None else lo
    pos = C.pos(k, p, lag)
    eq, nsw = alloc_equity(C.px, pos, lo, C.c)
    st = curve_stats(eq, C.cal, lo)
    held = np.nan_to_num(pos[lo:-1], nan=0.0) > 0
    st.update({"sw": nsw / st["yrs"], "expo": float(held.mean()) if len(held) else None})
    return {"pos": pos, "eq": eq, "s": st}


def _r(v, k: int = 4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), k)


def strategy(C: Ctx, spec: dict) -> dict:
    """一個市場的一個策略 → 成績、判定、參數鄰近、打亂測試、淨值（月底取樣）、每一筆、現在。"""
    k, kind, p = spec["k"], spec["kind"], spec["p"]
    key = f"xs:{C.mk}:{k}"
    bh = bh_stats(C.px, C.cal, C.s0)
    bh_r = bh_stats(C.px, C.cal, C.r0)
    out = {"k": k, "mk": C.mk, "kind": kind, "grp": spec["grp"], "a": C.cal[C.s0], "z": C.cal[-1], "r0": C.cal[C.r0],
           "bh": bh, "bh_r": bh_r}
    if kind == "trade":
        c, lag = S.cost(C.mk, k), S.lag(C.mk, k)
        out.update({"cost": c, "lag": None if k == "tom" else lag})          # 月底月初照排定的日子，沒有落後
        M = _trade_eval(C, k, p, lag)
        rec = trade_stats(C.px, M["tr"], C.r0, c)
        rec_ok = trade_pass_recent(rec)
        eq_r = trade_equity(C.px, M["tr"], C.r0, c)
        rec.update({kk: v for kk, v in curve_stats(eq_r, C.cal, C.r0).items() if kk in ("cagr", "mdd")})
        if C.T > C.r0 + 1:
            rec["expo"] = float(trade_held(C.T, [t for t in M["tr"] if t[1] >= C.r0])[C.r0 + 1:].mean())
        grid = []
        for q in _combos(spec["grid"]):
            pp = {**p, **q}
            g = M if pp == p else _trade_eval(C, k, pp, lag)
            f = g["full"]
            grid.append({"p": q, "ok": f["ok"], "n": f["n"], "win": f.get("win"), "base": f.get("base"), "avg": f.get("avg"),
                         "pf": f.get("pf")})
        share = sum(g["ok"] for g in grid) / len(grid)
        few = M["full"]["n"] < S.TR_N_MIN
        out.update({"full": M["full"], "rec": rec, "rec_ok": rec_ok, "grid": grid, "grid_ok": share,
                    "tier": tier(kind, M["full"]["ok"], rec_ok, share, few),
                    "p": luck_trade(C.px, M["tr"], C.s0, c, key)})
        if k != "tom":
            R = _trade_eval(C, k, p, S.ref_lag(C.mk, k))
            out["ref"] = R["full"]
            out["ref_lag"] = S.ref_lag(C.mk, k)
        out["eq"] = _sample(C, M["eq"], C.s0)
        out["tr"] = [[C.cal[e], _r(C.px[e], 2), C.cal[q], _r(C.px[q], 2), q - e, _r(net(C.px[e], C.px[q], c), 5)]
                     for _, e, _, q in M["tr"] if e >= C.s0]
    else:
        out.update({"cost": C.c, "lag": S.LAG})
        M = _alloc_eval(C, k, p, S.LAG)
        full = M["s"]
        full["ok"] = alloc_pass(full, bh)
        R = _alloc_eval(C, k, p, S.LAG, lo=C.r0)
        rec = R["s"]
        rec_ok = alloc_pass(rec, bh_r)
        grid = []
        for q in _combos(spec["grid"]):
            pp = {**p, **q}
            g = M if pp == p else _alloc_eval(C, k, pp, S.LAG)
            ok = alloc_pass(g["s"], bh)
            grid.append({"p": q, "ok": ok, "cagr": g["s"]["cagr"], "mdd": g["s"]["mdd"], "mar": g["s"]["mar"], "sw": g["s"]["sw"]})
        share = sum(g["ok"] for g in grid) / len(grid)
        few = _years(C.cal, C.s0) < S.AL_YEARS_MIN
        out.update({"full": full, "rec": rec, "rec_ok": rec_ok, "grid": grid, "grid_ok": share,
                    "tier": tier(kind, full["ok"], rec_ok, share, few), "p": luck_alloc(C.px, M["pos"], C.s0, C.c, C.cal, key)})
        if k != "hal":
            out["ref"] = _alloc_eval(C, k, p, S.LAG_REF)["s"]
            out["ref_lag"] = S.LAG_REF
        out["eq"] = _sample(C, M["eq"], C.s0)
        out["tr"] = _spans(C, M["pos"])
    out["now"] = now_state(C, spec)
    if k == "hal":
        out["season"] = season(C, p)
    return out


def _sample(C: Ctx, eq: np.ndarray, lo: int) -> dict:
    """淨值月底取樣（＋最後一天）：{"d": [日期], "s": 策略, "b": 買進持有}（都從 1 起）。"""
    idx = [k for k in month_ends(C.cal) if k >= lo] + [C.T - 1]
    idx = sorted(set(idx))
    return {"d": [C.cal[k] for k in idx], "s": [_r(eq[k - lo], 4) for k in idx], "b": [_r(C.px[k] / C.px[lo], 4) for k in idx]}


def _spans(C: Ctx, pos: np.ndarray) -> list[list]:
    """進出型每一段持有：[買進日, 買價, 賣出日（還在持有＝None）, 賣價, 交易日數, 這一段的報酬（扣進出成本）]。"""
    p = np.nan_to_num(pos, nan=0.0)
    out = []
    a = C.s0 if p[C.s0] > 0 else None
    for k in range(C.s0 + 1, C.T):
        if p[k] > 0 and p[k - 1] <= 0:
            a = k
        elif p[k] <= 0 and p[k - 1] > 0 and a is not None:
            out.append([C.cal[a], _r(C.px[a], 2), C.cal[k], _r(C.px[k], 2), k - a, _r(net(C.px[a], C.px[k], C.c), 5)])
            a = None
    if a is not None:
        out.append([C.cal[a], _r(C.px[a], 2), None, _r(C.px[-1], 2), C.T - 1 - a, _r(C.px[-1] / C.px[a] - 1.0, 5)])
    return out


def season(C: Ctx, p: dict) -> dict:
    """Halloween（主參數 11～4 月）：評估期間裡每一年「前一年 10 月底 → 4 月底」與「4 月底 → 10 月底」的漲跌（月底收盤）。"""
    if (p["start"], p["months"]) != (11, 6):
        return {}
    mc = {C.cal[k][:7]: C.px[k] for k in month_ends(C.cal) if k >= C.s0}
    win, oth, ys = [], [], []
    for y in sorted({int(m[:4]) for m in mc}):
        a, b, c = mc.get(f"{y - 1}-10"), mc.get(f"{y}-04"), mc.get(f"{y}-10")
        if a and b and c:
            win.append(b / a - 1.0)
            oth.append(c / b - 1.0)
            ys.append(y)
    if not win:
        return {}
    w, o = np.array(win), np.array(oth)
    m10 = len(w) >= 10
    return {"n": len(w), "y0": ys[0], "y1": ys[-1], "w": float(w.mean()), "o": float(o.mean()), "wu": float((w > 0).mean()),
            "ou": float((o > 0).mean()), "better": float((w > o).mean()),
            "w10": float(w[-10:].mean()) if m10 else None, "o10": float(o[-10:].mean()) if m10 else None,
            "b10": float((w[-10:] > o[-10:]).mean()) if m10 else None}


# ── 現在（規格第 8 節） ───────────────────────────────────────────────────────

def same_day_levels(C: Ctx, p: dict, st: str) -> dict:
    """當天收盤進出的 RSI(2)（規格第 8 節 VER 2）：下一個交易日的價位。
    空手：收盤在 lo 以上（站在 200 日線上）、hi 以下（2 日 RSI ＜ rsi_max）＝買進訊號；hi 比今天收盤低不到 NEAR 而且 hi ＞ lo＝near。
    持有：收盤高於 ex（站上 exit_ma 日線）＝出場訊號。"""
    t, px = C.T - 1, C.px
    out: dict = {}
    if st == "hold":
        m = p["exit_ma"] - 1
        if t + 1 >= m and m > 0:
            out["ex_px"] = _r(float(px[t - m + 1:t + 1].mean()), 2)
        return out
    if st != "wait":
        return out
    m = p["ma"] - 1
    lo = float(px[t - m + 1:t + 1].mean()) if t + 1 >= m else None
    AU, AD = C.wilder(p["rsi_n"])
    hi = rsi_below_price(float(px[t]), float(AU[t]), float(AD[t]), p["rsi_n"], p["rsi_max"])
    out.update({"lo_px": _r(lo, 2), "hi_px": _r(hi, 2)})
    if hi is not None and lo is not None:
        out["hi_chg"] = _r(hi / px[t] - 1.0, 4)
        out["lo_chg"] = _r(lo / px[t] - 1.0, 4)
        out["can"] = bool(hi > lo)
        if hi > lo and hi / px[t] - 1.0 >= -S.NEAR:
            out["st"] = "near"
    return out


def now_state(C: Ctx, spec: dict) -> dict:
    k, p = spec["k"], spec["p"]
    t = C.T - 1
    px = C.px
    nx = C.fut[0] if C.fut else None                   # 下一個交易日（照休市表）
    if spec["kind"] == "trade":
        lag = S.lag(C.mk, k)
        _, st = C.trades(k, p, lag, now=True)
        out = {"st": st.get("st", "wait"), "d": C.cal[t], "nx": nx, "lag": None if k == "tom" else lag, "px": _r(px[t], 2)}
        if k == "tom":
            out.update({kk: st[kk] for kk in ("ed", "qd") if kk in st})
            if "e" in st and st["e"] <= t:
                out["ep"], out["ret"], out["held"] = _r(px[st["e"]], 2), _r(px[t] / px[st["e"]] - 1.0, 5), t - st["e"]
            return out
        if "e" in st and st["e"] <= t:
            out.update({"ed": C.cal[st["e"]], "ep": _r(px[st["e"]], 2), "ret": _r(px[t] / px[st["e"]] - 1.0, 5),
                        "held": t - st["e"]})
        if "t" in st:
            out["td"] = C.cal[st["t"]]
        m200 = C.ma(p["ma"])[t]
        out["ma"] = _r(px[t] / m200 - 1.0, 4) if m200 == m200 else None
        out["rsi2"] = _r(C.rsi2[t], 1)
        if k == "rsi2":
            m5 = C.ma(p["exit_ma"])[t]
            out["ex"] = _r(px[t] / m5 - 1.0, 4) if m5 == m5 else None
            if lag == 0:
                out.update(same_day_levels(C, p, out["st"]))
        else:
            v, m = C.vix, sma(C.vix, p["vix_ma"])
            out["vix"] = _r(v[t], 2)
            out["vs"] = _r(v[t] / m[t] - 1.0, 4) if m[t] == m[t] and m[t] else None
            run = 0
            j = t
            while j >= 0 and v[j] == v[j] and m[j] == m[j] and v[j] >= (1.0 + p["stretch"]) * m[j]:
                run += 1
                j -= 1
            out["run"] = run
        return out
    pos = C.pos(k, p, S.LAG, now=True)
    cur = pos[t]
    out = {"d": C.cal[t], "st": "in" if cur == 1 else "out", "nx": nx}
    nxt = None
    if k == "ma200":
        m = C.ma(p["n"])[t]
        nxt = float(px[t] > m) if m == m else None
        out["dist"] = _r(px[t] / m - 1.0, 4) if m == m else None
    elif k in ("faber", "mom12"):
        if C.last_end:
            ends = C.ends_now
            dec = pos_faber(px, ends, p["n"], 0)[t] if k == "faber" else pos_mom(px, ends, p["n"], 0)[t]
            nxt = None if dec != dec else float(dec)
        ends = C.ends
        mc = px[ends]
        if k == "faber":
            prev = mc[-(p["n"] - 1):] if p["n"] > 1 else mc[:0]
            avg = (float(prev.sum()) + px[t]) / p["n"]
            out["dist"] = _r(px[t] / avg - 1.0, 4)
        else:
            cm = C.cal[t][:7]
            y, mth = int(cm[:4]), int(cm[5:7]) - p["n"]
            while mth <= 0:
                y, mth = y - 1, mth + 12
            back = f"{y}-{mth:02d}"
            kk = next((e for e in ends if C.cal[e][:7] == back), None)
            out["dist"] = _r(px[t] / px[kk] - 1.0, 4) if kk is not None else None
        md = [d for d in [C.cal[t]] + C.fut if d[:7] == C.cal[t][:7]]
        out["chk"] = md[-1] if md else None
        out["prov"] = None if out.get("dist") is None else (1 if out["dist"] > 0 else 0)
    elif k == "hal":
        if len(C.fut) >= 2:
            H = hal_months(p["start"], p["months"])
            nxt = 1.0 if int(C.fut[1][5:7]) in H else 0.0
        H = hal_months(p["start"], p["months"])
        seq = [C.cal[t]] + C.fut
        j = next((j for j in range(1, len(seq)) if (int(seq[j][5:7]) in H) != (cur == 1)), None)
        out["sw"] = seq[j - 1] if j else None          # 換邊那天收盤（新的月份開始前一個交易日）
    if nxt is not None and cur == cur and nxt != cur:
        out["st"] = "turn_in" if nxt == 1 else "turn_out"
    sp = _spans(C, pos)
    if sp and sp[-1][2] is None and cur == 1:
        out.update({"ed": sp[-1][0], "ret": sp[-1][5]})
    return out


# ── 全部 ───────────────────────────────────────────────────────────────────

def market(mk: str, D: dict | None = None) -> dict:
    D = D if D is not None else data(mk)
    C = Ctx(D)
    return {s["k"]: strategy(C, s) for s in S.STRATS if mk in s["mk"]}


_CACHE: dict = {}


def run_all(force: bool = False) -> dict:
    """五個市場（程序內快取；景氣頁與訊號總覽共用）。某個市場算不出來只印日誌、不擋其他。"""
    if _CACHE and not force:
        return _CACHE
    out = {}
    for mk in S.MARKETS:
        try:
            out[mk] = market(mk)
        except Exception as e:                            # noqa: BLE001
            print(f"[大神策略] {mk} 算不出來：{type(e).__name__}: {e}")
    _CACHE.clear()
    _CACHE.update(out)
    return _CACHE
