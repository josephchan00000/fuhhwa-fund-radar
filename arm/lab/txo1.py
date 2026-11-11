"""台指選擇權結算日的兩條：O1 結算日順勢（txospec VER 1 的規則＋VER 2 兩個對照）、O4 結算均價（VER 2）。

規格在 arm/lab/txospec.py；看任何成績之前寫定的實作細節在 docs/lab_txo_plan.md 第 19.7 節，這裡照做、不改：
  · 結算日＝每個到期別在日行情裡最後出現的那一天（2016-01-04 起、有 5 秒指數的日子），只買當天到期那一批。
  · 5 秒指數：第 0 個＝前一天收盤、第 1 個（09:00:05）＝開盤；日振幅＝(09:00:05～13:30:00 最高 − 最低) ÷ 前一天收盤。
  · 噪音區間 σ(t)＝前 NOISE_DAYS 個有 5 秒指數的交易日、同一個位置 |指數 ÷ 那天開盤 − 1| 的平均；今天平均價＝09:00:05 起的累計平均。
  · 模型價＝Black-Scholes（r＝0），時間＝離 13:30 還剩的分鐘 ÷ (SESSION_MIN × 252)；波動率＝前一個交易日同一個契約的結算價
    用那天收盤（＝今天第 0 個 5 秒指數）、時間 1/252 反推，一整天固定；反推不出來那一筆不做。
  · 成本＝txospec.side_cost（手續費＋期交稅＋1 檔滑價，每口每邊）；結算那一邊＝手續費＋期交稅×結算值（沒有滑價）；判定用兩倍成本。
本模組只讀資料、只算，不抓任何東西。
"""
from __future__ import annotations

import gzip
import json
import math
import random
from pathlib import Path

import numpy as np

from . import txodata as T
from . import txospec as S

VER = 1
N_IDX = 3241                      # 09:00:00～13:30:00 每 5 秒
TRADING_YEAR = 252
DAY_FROM = 2015                   # 日行情只讀這一年 12 月以後（2016 年 1 月的第一個結算日要前一天的結算價）


def kof(hhmm: str) -> int:
    """「HH:MM」→ 5 秒指數陣列的位置（09:00:00＝0）。"""
    h, m = map(int, hhmm.split(":"))
    return ((h - 9) * 3600 + m * 60) // 5


def sec_of(k: int) -> int:
    """5 秒指數位置 → 當天第幾秒。"""
    return 9 * 3600 + 5 * k


K_ENTRY = list(range(kof(S.ENTRY_FROM), kof(S.ENTRY_TO) + 1, S.CHECK_MIN * 12))
K_EXIT = kof(S.EXIT_BY)
K_CLOSE = N_IDX - 1


# ── 數學 ──────────────────────────────────────────────────────────────────────

def _erf(x: np.ndarray) -> np.ndarray:
    """Abramowitz-Stegun 7.1.26（誤差 < 1.5e-7）。"""
    s = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * a)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-a * a)
    return s * y


def ncdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + _erf(np.asarray(x, dtype=float) / math.sqrt(2.0)))


def t_left(k: np.ndarray | int) -> np.ndarray:
    """離 13:30 還剩的時間（年）：分鐘 ÷ (SESSION_MIN × 252)。"""
    return np.maximum(K_CLOSE - np.asarray(k, dtype=float), 0.0) * 5 / 60 / (S.SESSION_MIN * TRADING_YEAR)


def bs_vec(cp: str, s: np.ndarray, k: float, t: np.ndarray, vol: float) -> np.ndarray:
    s = np.asarray(s, dtype=float)
    t = np.asarray(t, dtype=float)
    intr = np.maximum(s - k, 0.0) if cp == "C" else np.maximum(k - s, 0.0)
    sd = vol * np.sqrt(np.maximum(t, 1e-12))
    d1 = (np.log(s / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    px = s * ncdf(d1) - k * ncdf(d2) if cp == "C" else k * ncdf(-d2) - s * ncdf(-d1)
    return np.where(t > 0, np.maximum(px, intr), intr)


def iv_prev(cp: str, settle: float | None, prev_close: float, k: float) -> float | None:
    """前一天結算價 → 波動率（時間 1/252）；反推不出來 None。"""
    from . import txocalc as C
    if not settle or settle <= 0:
        return None
    return C.iv(cp, float(settle), prev_close, k, 1.0 / TRADING_YEAR)


def intrinsic(cp: str, f: float, k: float) -> float:
    return max(f - k, 0.0) if cp == "C" else max(k - f, 0.0)


# ── 資料 ──────────────────────────────────────────────────────────────────────

def load_idx(root: Path, start: str = "2015-12-01") -> dict[str, np.ndarray]:
    out = {}
    for f in sorted((Path(root) / "idx").glob("*/*.json.gz")):
        d = f.name[:10]
        if d < start:
            continue
        doc = json.loads(gzip.decompress(f.read_bytes()))
        v = np.cumsum(np.asarray(doc["v"], dtype=np.int64)) / 100.0
        if len(v) == N_IDX:
            out[d] = v
    return out


def load_book(root: Path, year_from: int = DAY_FROM) -> tuple[list[str], dict, dict]:
    """日行情 → (交易日清單, {(日, 到期別): {履約價: [C收, C結, P收, P結]}}, {到期別: 最後出現的日子})。"""
    book: dict[tuple[str, str], dict] = {}
    last: dict[str, str] = {}
    days = set()
    for f in sorted((Path(root) / "day").glob("*.json.gz")):
        if int(f.name[:4]) < year_from:
            continue
        doc = json.loads(gzip.decompress(f.read_bytes()))
        ci = {c: i for i, c in enumerate(doc["cols"])}
        for r in doc["rows"]:
            d, exp = r[ci["d"]], r[ci["exp"]]
            days.add(d)
            if d > last.get(exp, ""):
                last[exp] = d
            q = book.setdefault((d, exp), {}).setdefault(r[ci["k"]], [None, None, None, None])
            j = 0 if r[ci["cp"]] == "C" else 2
            q[j], q[j + 1] = r[ci["c"]], r[ci["s"]]
    return sorted(days), book, last


def settle_days(days: list[str], last: dict[str, str], idx: dict, start: str = "2016-01-04") -> dict[str, str]:
    """{結算日: 到期別}：到期別最後出現的那一天（資料最後一天還在交易的不算）；同一天兩個到期別取月選。"""
    end = days[-1] if days else ""
    out: dict[str, str] = {}
    for exp, d in last.items():
        if d < start or d >= end and d != T.exp_date(exp).isoformat() or d not in idx:
            continue
        if d not in out or (len(exp) == 6 and len(out[d]) != 6):
            out[d] = exp
    return dict(sorted(out.items()))


def load_bars(root: Path, d: str) -> dict | None:
    f = Path(root) / "bars" / d[:4] / f"{d}.json.gz"
    if not f.exists():
        return None
    doc = json.loads(gzip.decompress(f.read_bytes()))
    return {key: T.from_bars(rows, doc.get("step", 1)) for key, rows in doc["c"].items()}


class Mkt:
    """5 秒指數、日行情、結算日的查詢，以及每天的噪音區間。"""

    def __init__(self, idx: dict[str, np.ndarray], days: list[str], book: dict, sett: dict[str, str]):
        self.idx = idx
        self.iday = sorted(idx)
        self.ipos = {d: i for i, d in enumerate(self.iday)}
        self.days = days
        self.dpos = {d: i for i, d in enumerate(days)}
        self.book = book
        self.sett = sett
        self._amp = {d: (v[1:].max() - v[1:].min()) / v[0] for d, v in idx.items()}

    def prev_day(self, d: str) -> str | None:
        i = self.dpos.get(d)
        return self.days[i - 1] if i else None

    def vol_avg(self, d: str) -> float | None:
        i = self.ipos[d]
        if i < S.VOL_DAYS:
            return None
        return float(np.mean([self._amp[x] for x in self.iday[i - S.VOL_DAYS:i]]))

    def sigma(self, d: str) -> np.ndarray | None:
        i = self.ipos[d]
        if i < S.NOISE_DAYS:
            return None
        rows = [np.abs(self.idx[x] / self.idx[x][1] - 1.0) for x in self.iday[i - S.NOISE_DAYS:i]]
        return np.mean(rows, axis=0)

    def prev_settle(self, d: str, exp: str, k: float, cp: str) -> float | None:
        p = self.prev_day(d)
        q = (self.book.get((p, exp)) or {}).get(k) if p else None
        if not q:
            return None
        v = q[1] if cp == "C" else q[3]
        return float(v) if v else None

    def strikes(self, d: str, exp: str) -> set:
        p = self.prev_day(d)
        return set((self.book.get((p, exp)) or {}).keys()) if p else set()


class Day:
    """一個結算日算好的東西：指數、今天平均價、噪音區間、結算價。"""

    def __init__(self, m: Mkt, d: str, sig: np.ndarray, kk: float):
        v = m.idx[d]
        self.d, self.v, self.exp = d, v, m.sett[d]
        self.pc, self.op = float(v[0]), float(v[1])
        cs = np.cumsum(v[1:])
        self.avg = np.concatenate([[v[0]], cs / np.arange(1, N_IDX)])
        self.up = max(self.op, self.pc) * (1 + kk * sig)
        self.lo = min(self.op, self.pc) * (1 - kk * sig)
        self.F = S.settle_price(list(v))


# ── O1：一天的交易（單位：一口、點數；口數在 sim 裡算）──────────────────────

def _strike(s: float, cp: str, otm: int) -> float:
    atm = math.floor(s / S.STRIKE_STEP + 0.5) * S.STRIKE_STEP
    return float(atm + otm * S.STRIKE_STEP if cp == "C" else atm - otm * S.STRIKE_STEP)


def exit_path(dy: Day, cp: str, k_in: int, kx: float, iv: float, stop1: np.ndarray, end: int = K_EXIT) -> dict:
    """進場之後每 5 秒檢查出場（txospec O1）：① stop1 ② 價 ≤ 進場 × STOP_PREM ③ end 全部出；
    價 ≥ 進場 × TP_MULT 先賣一半，剩下的另外看指數回吐 TRAIL_IDX、權利金從最高跌 TRAIL_PREM。"""
    ks = np.arange(k_in, end + 1)
    idx = dy.v[k_in:end + 1]
    px = bs_vec(cp, idx, kx, t_left(ks), iv)
    p0 = float(px[0])
    st = stop1[1:] | (px[1:] <= p0 * S.STOP_PREM)
    tp = px[1:] >= p0 * S.TP_MULT
    j_st = int(np.argmax(st)) if st.any() else None
    j_tp = int(np.argmax(tp)) if tp.any() else None
    if j_tp is None or (j_st is not None and j_st < j_tp):
        j = j_st if j_st is not None else len(st) - 1
        why = "stop" if j_st is not None else "time"
        return {"p0": p0, "parts": [["all", float(px[j + 1]), int(ks[j + 1]), why]]}
    s0 = float(idx[0])
    ext = np.maximum.accumulate(idx) if cp == "C" else np.minimum.accumulate(idx)
    run = np.abs(ext - s0)
    back = np.abs(ext - idx)
    tr_i = (run > 0) & (back > run * S.TRAIL_IDX)
    tr_p = px <= np.maximum.accumulate(px) * (1 - S.TRAIL_PREM)
    rest = (st | tr_i[1:] | tr_p[1:])
    rest[:j_tp] = False
    j2 = int(np.argmax(rest)) if rest.any() else None
    why = "stop" if j2 is not None and st[j2] else ("trail" if j2 is not None else "time")
    j2 = j2 if j2 is not None else len(st) - 1
    return {"p0": p0, "parts": [["half", float(px[j_tp + 1]), int(ks[j_tp + 1]), "tp"],
                                ["rest", float(px[j2 + 1]), int(ks[j2 + 1]), why]]}


def stop1_of(dy: Day, cp: str, k_in: int, end: int = K_EXIT) -> np.ndarray:
    sl = slice(k_in, end + 1)
    if cp == "C":
        return (dy.v[sl] <= dy.up[sl]) | (dy.v[sl] < dy.avg[sl])
    return (dy.v[sl] >= dy.lo[sl]) | (dy.v[sl] > dy.avg[sl])


def stop1_mirror(dy: Day, cp: str, k_in: int, d0: float, end: int = K_EXIT) -> np.ndarray:
    """打亂測試換方向的那一筆：指數往不利的方向走 d0 點就出（d0＝原方向進場時離①的距離）。"""
    s0 = dy.v[k_in]
    sl = dy.v[k_in:end + 1]
    return sl <= s0 - d0 if cp == "C" else sl >= s0 + d0


def o1_day(m: Mkt, dy: Day, otm: int, mode: str = "main") -> tuple[list[dict], list[dict]]:
    """一天的 O1 交易（mode：main／two）。回傳 (交易, 沒做的訊號與原因)。"""
    out, skipped = [], []
    k_free, n_tr = 0, 0
    for k in K_ENTRY:
        if n_tr >= S.MAX_TRADES or k <= k_free:
            continue
        s = float(dy.v[k])
        if s > dy.up[k] and s > dy.avg[k]:
            cp = "C"
        elif s < dy.lo[k] and s < dy.avg[k]:
            cp = "P"
        else:
            continue
        legs = [otm] if mode == "main" else [0, S.TWO_GAP]
        made = []
        for o in legs:
            kx = _strike(s, cp, o)
            iv = iv_prev(cp, m.prev_settle(dy.d, dy.exp, kx, cp), dy.pc, kx)
            if iv is None:
                skipped.append({"d": dy.d, "k": k, "cp": cp, "kx": kx, "why": "no_iv"})
                made = []
                break
            st1 = stop1_of(dy, cp, k)
            r = exit_path(dy, cp, k, kx, iv, st1)
            if r["p0"] < S.MIN_PREM:
                skipped.append({"d": dy.d, "k": k, "cp": cp, "kx": kx, "why": "min_prem"})
                made = []
                break
            d0 = float(s - max(dy.up[k], dy.avg[k])) if cp == "C" else float(min(dy.lo[k], dy.avg[k]) - s)
            made.append({"d": dy.d, "exp": dy.exp, "k": k, "cp": cp, "kx": kx, "iv": iv, "s0": s, "d0": d0,
                         "p0": r["p0"], "parts": r["parts"], "F": dy.F, "w": 1.0 / len(legs)})
        if not made:
            continue
        out.extend(made)
        n_tr += 1
        k_free = max(p[2] for t in made for p in t["parts"])
    return out, skipped


def hold_variant(t: dict) -> dict:
    """對照 hold：13:00 還沒出的（理由 time）不賣、抱到結算。"""
    parts = [list(p) for p in t["parts"]]
    last = parts[-1]
    if last[3] == "time":
        last[1], last[2], last[3] = intrinsic(t["cp"], t["F"], t["kx"]), K_CLOSE, "settle"
    return {**t, "parts": parts}


def flip_trade(m: Mkt, dy: Day, t: dict, otm: int) -> dict | None:
    """打亂測試：同一天、同一時刻、反方向、同樣價外檔數；①改成往不利方向走 d0 點。"""
    cp = "P" if t["cp"] == "C" else "C"
    kx = _strike(t["s0"], cp, otm)
    iv = iv_prev(cp, m.prev_settle(dy.d, dy.exp, kx, cp), dy.pc, kx)
    if iv is None:
        return None
    r = exit_path(dy, cp, t["k"], kx, iv, stop1_mirror(dy, cp, t["k"], t["d0"]))
    if r["p0"] < S.MIN_PREM:
        return None
    return {**t, "cp": cp, "kx": kx, "iv": iv, "p0": r["p0"], "parts": r["parts"]}


# ── 帳戶 ──────────────────────────────────────────────────────────────────────

def _exit_cost(price: float, why: str, fee: float, cm: float) -> float:
    if why == "settle":
        return cm * (fee + S.TAX * price * S.MULT)
    return S.side_cost(price, fee, cm)


def sim(trades: list[dict], cap: float, fee: float = S.FEE, cm: float = 2.0, extra: float = 0.0, stops: bool = True) -> dict:
    """trades：{d, k, p0, parts [[half/rest/all, 價, 出場位置, 理由]], w（這一檔占 cap 的比例）}。
    口數＝floor(帳戶 × cap × w ÷ (進場價 × 50 ＋ 一邊成本))；half 賣 floor(口數 ÷ 2)；extra＝每邊另加的點數（模型誤差）。
    一天、一個月已實現虧損達 DAY_STOP／MONTH_STOP（用當天、當月開始時的帳戶）就不再進場。"""
    acct = float(S.ACCOUNT)
    pend: list[tuple[tuple, float]] = []
    rows, curve = [], [(None, acct)]
    day_open, day_real, mon_open, mon_real = {}, {}, {}, {}

    def realize(upto: tuple):
        nonlocal acct
        for key, pnl in sorted(p for p in pend if p[0] <= upto):
            d = key[0]
            day_open.setdefault(d, acct)
            mon_open.setdefault(d[:7], acct)
            acct += pnl
            day_real[d] = day_real.get(d, 0.0) + pnl
            mon_real[d[:7]] = mon_real.get(d[:7], 0.0) + pnl
            curve.append((d, acct))
        pend[:] = [p for p in pend if p[0] > upto]

    for t in sorted(trades, key=lambda t: (t["d"], t["k"], t["kx"])):
        realize((t["d"], t["k"]))
        d = t["d"]
        day_open.setdefault(d, acct)
        mon_open.setdefault(d[:7], acct)
        if stops and day_real.get(d, 0.0) <= -S.DAY_STOP * day_open[d]:
            rows.append({**t, "skip": "day_stop"})
            continue
        if stops and mon_real.get(d[:7], 0.0) <= -S.MONTH_STOP * mon_open[d[:7]]:
            rows.append({**t, "skip": "month_stop"})
            continue
        p0 = t["p0"]
        per = p0 * S.MULT + S.side_cost(p0, fee)
        lots = int(acct * cap * t.get("w", 1.0) // per) if per > 0 else 0
        if lots < 1:
            rows.append({**t, "skip": "lots0"})
            continue
        pnl = -lots * (S.side_cost(p0, fee, cm) + extra * S.MULT)
        left = lots
        for kind, px, kx_, why in t["parts"]:
            q = lots // 2 if kind == "half" else left
            left -= q
            pnl += q * ((px - p0) * S.MULT - _exit_cost(px, why, fee, cm) - (0 if why == "settle" else extra * S.MULT))
        last_k = max(p[2] for p in t["parts"])
        pend.append(((d, last_k), pnl))
        rows.append({**t, "x": d, "lots": lots, "pnl": round(pnl, 1), "ret": round(pnl / (lots * per), 4), "acct0": round(acct, 1)})
    realize(("9999-12-31", 10 ** 9))
    return {"rows": rows, "curve": curve, "final": acct}


def metrics(res: dict) -> dict:
    from . import txobt as B
    return B.metrics(res)


# ── O1 研究 ──────────────────────────────────────────────────────────────────

def o1_all(m: Mkt, grid: list[dict], log=print) -> dict:
    """每一組參數、每一個結算日的交易（主規則與 two）。"""
    sig_cache: dict[str, np.ndarray | None] = {}
    days_cache: dict[tuple, Day] = {}
    res = {i: {"main": [], "two": [], "skip": []} for i in range(len(grid))}
    info = {"days": 0, "no_hist": 0, "vol_skip": {i: 0 for i in range(len(grid))}}
    for d in m.sett:
        sig = sig_cache.setdefault(d, m.sigma(d))
        va = m.vol_avg(d)
        if sig is None or va is None or m.prev_day(d) is None:
            info["no_hist"] += 1
            continue
        info["days"] += 1
        for i, g in enumerate(grid):
            if va < g["vol_min"]:
                info["vol_skip"][i] += 1
                continue
            key = (d, g["k"])
            if key not in days_cache:
                days_cache[key] = Day(m, d, sig, g["k"])
            dy = days_cache[key]
            tr, sk = o1_day(m, dy, g["otm"], "main")
            res[i]["main"].extend(tr)
            res[i]["skip"].extend(sk)
            tw, _ = o1_day(m, dy, g["otm"], "two")
            res[i]["two"].extend(tw)
        if len(days_cache) > 64:
            days_cache.clear()
    log(f"[txo1] O1：結算日 {len(m.sett)}、可算 {info['days']}、歷史不足 {info['no_hist']}")
    return {"res": res, "info": info}


def walk_forward(grid: list[dict], per_combo: dict[int, dict], first_year: int = S.WF_FIRST_YEAR) -> dict[int, int | None]:
    """每年 1 月 1 日只用以前的年份：平均每筆淨損益（兩倍成本）最高、筆數 ≥ WF_MIN_TRADES 的一組（同分取前面的）。"""
    years = sorted({int(r["d"][:4]) for c in per_combo.values() for r in c["rows"] if "pnl" in r})
    pick: dict[int, int | None] = {}
    for y in range(first_year, (max(years) if years else first_year) + 1):
        best, best_v = None, None
        for i in range(len(grid)):
            pn = [r["pnl"] for r in per_combo[i]["rows"] if "pnl" in r and int(r["d"][:4]) < y]
            if len(pn) < S.WF_MIN_TRADES:
                continue
            v = sum(pn) / len(pn)
            if best_v is None or v > best_v:
                best, best_v = i, v
        pick[y] = best
    return pick


def oos_trades(trades_by_combo: dict[int, list[dict]], pick: dict[int, int | None]) -> list[dict]:
    out = []
    for y, i in pick.items():
        if i is None:
            continue
        out.extend(t for t in trades_by_combo[i] if int(t["d"][:4]) == y)
    return out


def placebo(actual: list[dict], flipped: list[dict | None], n: int, seed: int, cap: float) -> dict:
    """每一筆一半機率換成反方向（換不到的那一次不算），PLACEBO_N 次；比例＝隨機平均每筆 ≥ 實際的次數 ÷ n。"""
    base = metrics(sim(actual, cap))
    if not base.get("n"):
        return {"p": None}
    rnd = random.Random(seed)
    ge, means = 0, []
    for _ in range(n):
        tr = []
        for a, f in zip(actual, flipped):
            if rnd.random() < 0.5:
                tr.append(a)
            elif f is not None:
                tr.append(f)
        mt = metrics(sim(tr, cap))
        mu = mt.get("mean", 0.0) if mt.get("n") else 0.0
        means.append(mu)
        ge += mu >= base["mean"]
    return {"p": round(ge / n, 4), "rand_mean": round(sum(means) / n, 1), "actual": base["mean"], "n": n}


def real_check(root: Path, trades: list[dict]) -> dict:
    """有分 K 的日子：同一筆交易用真實成交重算。進場＝訊號那一分鐘之後第一根 1 分 K 收盤；出場同理；前後 2 分鐘沒成交記「沒成交」。
    每邊差距（點，正的＝對買方不利）：進場 真實 − 模型、出場 模型 − 真實。"""
    cache: dict[str, dict | None] = {}
    sides, rows = [], []
    for t in trades:
        b = cache.setdefault(t["d"], load_bars(root, t["d"])) if t["d"] >= S.O4_FROM else None
        if b is None:
            continue
        key = f"{t['exp']}|{t['cp']}|{int(t['kx'])}"
        bars = b.get(key)
        if not bars:
            rows.append({"d": t["d"], "key": key, "miss": "no_bars"})
            continue

        def fill(k: int):
            m0 = sec_of(k) // 60 + 1
            for mm in (m0, m0 + 1):
                for s0, o, h, lo, c, v in bars:
                    if s0 == mm * 60 and v > 0:
                        return c
            return None
        pin = fill(t["k"])
        outs = [fill(p[2]) if p[3] != "settle" else p[1] for p in t["parts"]]
        if pin is None or any(x is None for x in outs):
            rows.append({"d": t["d"], "key": key, "miss": "no_fill"})
            continue
        sides.append(pin - t["p0"])
        for p, x in zip(t["parts"], outs):
            if p[3] != "settle":
                sides.append(p[1] - x)
        rows.append({"d": t["d"], "key": key, "k": t["k"], "model": [round(t["p0"], 2)] + [round(p[1], 2) for p in t["parts"]],
                     "real": [pin] + outs})
    srt = sorted(sides)
    med = (srt[len(srt) // 2] if len(srt) % 2 else (srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2) if srt else None
    prem = [t["p0"] for t in trades if t["d"] >= S.O4_FROM]
    avgp = sum(prem) / len(prem) if prem else None
    ok = med is not None and avgp is not None and med <= S.MODEL_ERR_MAX * avgp
    return {"n_sides": len(sides), "med_err": None if med is None else round(med, 3), "avg_prem": None if avgp is None else round(avgp, 2),
            "credible": bool(ok), "rows": rows}


def run_o1(root: Path, m: Mkt, placebo_n: int = S.PLACEBO_N, log=print) -> dict:
    grid = S.grid_o1()
    allr = o1_all(m, grid, log)
    res = allr["res"]
    cap = S.CAP["O1"]
    per_combo = {i: sim(res[i]["main"], cap) for i in range(len(grid))}
    table = []
    for i, g in enumerate(grid):
        mt = metrics(per_combo[i])
        table.append({**g, **{k: mt.get(k) for k in ("n", "mean", "mean_ret", "win", "x2", "maxdd", "years_ok", "total")},
                      "skips": len(res[i]["skip"])})
    pick = walk_forward(grid, per_combo)
    oos = oos_trades({i: res[i]["main"] for i in res}, pick)
    res_oos = sim(oos, cap)
    mt = metrics(res_oos)
    # 打亂：同一筆換方向
    by_day = {}
    flipped = []
    for t in oos:
        key = (t["d"], grid[pick[int(t["d"][:4])]]["k"])
        if key not in by_day:
            by_day[key] = Day(m, t["d"], m.sigma(t["d"]), key[1])
        flipped.append(flip_trade(m, by_day[key], t, grid[pick[int(t["d"][:4])]]["otm"]))
    pl = placebo(oos, flipped, placebo_n, S.SEED, cap)
    # 真實價核對：9/17 起所有參數組的交易（去重）
    seen, rc_tr = set(), []
    for i in res:
        for t in res[i]["main"]:
            key = (t["d"], t["k"], t["cp"], t["kx"], tuple(tuple(p) for p in t["parts"]))
            if t["d"] >= S.O4_FROM and key not in seen:
                seen.add(key)
                rc_tr.append(t)
    rc = real_check(root, rc_tr)
    extra = max(rc["med_err"] or 0.0, 0.0)
    mt_err = metrics(sim(oos, cap, extra=extra)) if rc["credible"] else None
    from . import txobt as B
    jd = B.judge(mt, pl["p"], "O1")
    jd["ok"]["6_model"] = bool(rc["credible"] and mt_err and mt_err.get("n") and mt_err["mean"] > 0)
    if jd["verdict"] != "只列、不判定（筆數不夠）":
        jd["verdict"] = "過關" if all(jd["ok"].values()) else "沒過"
    # 只列
    two = oos_trades({i: res[i]["two"] for i in res}, pick)
    hold = [hold_variant(t) for t in oos]
    cmp_ = {
        "fee50": metrics(sim(oos, cap, fee=S.FEE_ALT)),
        "cost1": metrics(sim(oos, cap, cm=1.0)),
        "two": metrics(sim(two, cap)),
        "hold": metrics(sim(hold, cap)),
        "seller": seller(m, oos, by_day, grid, pick),
    }
    reasons: dict[str, int] = {}
    for t in oos:
        for p in t["parts"]:
            reasons[p[3]] = reasons.get(p[3], 0) + 1
    return {
        "grid": table, "pick": {str(y): (None if i is None else grid[i]) for y, i in pick.items()},
        "info": {**allr["info"], "vol_skip": {str(k): v for k, v in allr["info"]["vol_skip"].items()}},
        "oos": mt, "judge": jd, "placebo": pl, "model_check": {k: v for k, v in rc.items() if k != "rows"},
        "model_rows": rc["rows"][:60], "oos_with_err": mt_err, "compare": cmp_, "exit_reasons": reasons,
        "trades": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k not in ("parts",)}
                   | {"parts": [[p[0], round(p[1], 2), p[2], p[3]] for p in r.get("parts", [])]}
                   for r in res_oos["rows"]],
    }


def seller(m: Mkt, oos: list[dict], by_day: dict, grid: list[dict], pick: dict) -> dict:
    """VER 1 只列的賣方對照：O1 買的同一個契約，09:30 賣出、13:00 買回（模型價，一口，兩倍成本）。"""
    k930 = kof("09:30")
    pn = []
    for t in oos:
        dy = by_day[(t["d"], grid[pick[int(t["d"][:4])]]["k"])]
        a = float(bs_vec(t["cp"], dy.v[k930:k930 + 1], t["kx"], t_left(np.array([k930])), t["iv"])[0])
        b = float(bs_vec(t["cp"], dy.v[K_EXIT:K_EXIT + 1], t["kx"], t_left(np.array([K_EXIT])), t["iv"])[0])
        pn.append((a - b) * S.MULT - S.side_cost(a, mult=2.0) - S.side_cost(b, mult=2.0))
    if not pn:
        return {"n": 0}
    return {"n": len(pn), "mean": round(sum(pn) / len(pn), 1), "win": round(sum(1 for x in pn if x > 0) / len(pn), 4)}


# ── O4 結算均價（只用真實成交）────────────────────────────────────────────────

O4_K = [kof(x) for x in S.O4_CHECKS]


def band(m: Mkt, d: str, k: int) -> float | None:
    """過去 O4_BAND_DAYS 個交易日：k 之後到 13:25:00 的每一個 5 秒指數與收盤，離那天 k 的指數最遠多少點，取最大。"""
    i = m.ipos[d]
    if i < S.O4_BAND_DAYS:
        return None
    best = 0.0
    for x in m.iday[i - S.O4_BAND_DAYS:i]:
        v = m.idx[x]
        rest = np.concatenate([v[k + 1:S.SETTLE_K[1] + 1], [v[S.CLOSE_K]]])
        best = max(best, float(np.max(np.abs(rest - v[k]))))
    return best


def bounds(v: np.ndarray, k: int, b: float) -> tuple[float, float]:
    """已知 13:00:05～k，剩下的 (m＋1) 個用 S ± B：結算價最低、最高。"""
    done = float(np.sum(v[S.SETTLE_K[0]:k + 1]))
    rest = S.SETTLE_K[1] - k + 1
    s = float(v[k])
    return (done + rest * (s - b)) / S.SETTLE_N, (done + rest * (s + b)) / S.SETTLE_N


def o4_day(m: Mkt, root: Path, d: str, edge: float = S.O4_EDGE, ks: list[int] | None = None) -> tuple[list[dict], list[dict]]:
    """一個結算日的 O4 候選與交易（單位一口）。候選＝當天到期、最少值 > 0、那一刻有成交（打亂測試用）。"""
    exp = m.sett[d]
    bars = load_bars(root, d)
    if bars is None:
        return [], []
    v = m.idx[d]
    F = S.settle_price(list(v))
    picks, cands, done = [], [], set()
    for k in ks or O4_K:
        b = band(m, d, k)
        if b is None:
            continue
        lo, hi = bounds(v, k, b)
        m0 = sec_of(k) // 60
        here = []
        for key, rows in bars.items():
            e, cp, kx = key.split("|")
            if e != exp:
                continue
            kx = float(kx)
            fl = max(lo - kx, 0.0) if cp == "C" else max(kx - hi, 0.0)
            if fl <= 0:
                continue
            px = None
            for mm in (m0, m0 + 1):
                for s0, o, h, l_, c, vol in rows:
                    if s0 == mm * 60 and vol > 0:
                        px = c
                        break
                if px is not None:
                    break
            if px is None:
                continue
            gap = fl - px - S.side_cost(px) / S.MULT - (S.FEE + S.TAX * fl * S.MULT) / S.MULT
            t = {"d": d, "exp": exp, "k": k, "cp": cp, "kx": kx, "floor": round(fl, 2), "p0": px, "gap": round(gap, 2),
                 "parts": [["all", intrinsic(cp, F, kx), S.CLOSE_K, "settle"]], "F": F, "w": 1.0, "band": round(b, 2)}
            cands.append(t)
            if gap >= edge and key not in done:
                here.append(t)
        for t in sorted(here, key=lambda t: -(t["floor"] - t["p0"])):
            if len(picks) >= S.O4_MAX_DAY:
                break
            done.add(f"{t['exp']}|{t['cp']}|{int(t['kx'])}")
            picks.append(t)
    return picks, cands


def o4_judge(mt: dict, rows: list[dict], p: float | None) -> dict:
    tr = [r for r in rows if "pnl" in r]
    days = {r["d"] for r in tr}
    tot = sum(r["pnl"] for r in tr)
    byd: dict[str, float] = {}
    for r in tr:
        byd[r["d"]] = byd.get(r["d"], 0.0) + r["pnl"]
    top = max(byd.values()) / tot if tr and tot > 0 else None
    ok = {"1_mean": bool(mt.get("n")) and mt["mean"] > 0,
          "2_n": len(tr) >= S.O4_MIN_N and len(days) >= S.O4_MIN_DAYS,
          "3_top_day": top is not None and top <= S.O4_TOP_DAY,
          "4_placebo": p is not None and p <= S.PLACEBO_P}
    if not ok["2_n"]:
        return {"ok": ok, "verdict": "只列、不判定（筆數不夠）", "days": len(days), "top_day": top}
    return {"ok": ok, "verdict": "過關" if all(ok.values()) else "沒過", "days": len(days), "top_day": top}


def run_o4(root: Path, m: Mkt, placebo_n: int = S.PLACEBO_N, log=print) -> dict:
    cap = S.O4_CAP_EACH
    days = [d for d in m.sett if d >= S.O4_FROM]
    picks, cands, per_day = [], [], []
    alt = {e: [] for e in S.O4_EDGE_ALT}
    late = []
    for d in days:
        p, c = o4_day(m, root, d)
        if not c and load_bars(root, d) is None:
            continue
        picks.extend(p)
        cands.extend(c)
        per_day.append({"d": d, "F": S.settle_price(list(m.idx[d])), "cands": len(c), "picks": len(p)})
        for e in S.O4_EDGE_ALT:
            alt[e].extend(o4_day(m, root, d, edge=e)[0])
        late.extend(o4_day(m, root, d, ks=[x for x in O4_K if x >= kof("13:15")])[0])
    res = sim(picks, cap)
    mt = metrics(res)
    # 打亂：同一天、同一時刻、從候選隨機挑同樣筆數
    rnd = random.Random(S.SEED)
    by_slot: dict[tuple, list[dict]] = {}
    for c in cands:
        by_slot.setdefault((c["d"], c["k"]), []).append(c)
    p = None
    if mt.get("n"):
        ge = 0
        for _ in range(placebo_n):
            tr = [rnd.choice(by_slot[(t["d"], t["k"])]) for t in picks]
            m2 = metrics(sim(tr, cap))
            ge += (m2.get("mean", 0.0) if m2.get("n") else 0.0) >= mt["mean"]
        p = round(ge / placebo_n, 4)
    log(f"[txo1] O4：有分 K 的結算日 {len(per_day)}、交易 {mt.get('n', 0)}")
    return {"days": per_day, "metrics": mt, "judge": o4_judge(mt, res["rows"], p), "placebo_p": p,
            "compare": {"cost1": metrics(sim(picks, cap, cm=1.0)), "fee50": metrics(sim(picks, cap, fee=S.FEE_ALT)),
                        **{f"edge{e:g}": metrics(sim(alt[e], cap)) for e in S.O4_EDGE_ALT},
                        "late": metrics(sim(late, cap))},
            "trades": [{k: v for k, v in r.items()} for r in res["rows"]],
            "check": settle_check(root, m, days)}


def settle_check(root: Path, m: Mkt, days: list[str]) -> dict:
    """資料核對：當天到期、深度價內買權（結算價 − 履約價 ≥ 200）13:25 以後最後一筆成交，和「結算價 − 履約價」差多少。"""
    diffs = []
    for d in days:
        bars = load_bars(root, d)
        if not bars:
            continue
        F = S.settle_price(list(m.idx[d]))
        for key, rows in bars.items():
            e, cp, kx = key.split("|")
            if e != m.sett[d] or cp != "C" or F - float(kx) < 200:
                continue
            late = [r for r in rows if r[0] >= 13 * 3600 + 25 * 60 and r[5] > 0]
            if late:
                diffs.append(late[-1][4] - (F - float(kx)))
    srt = sorted(abs(x) for x in diffs)
    return {"n": len(diffs), "med_abs": round(srt[len(srt) // 2], 2) if srt else None,
            "mean": round(sum(diffs) / len(diffs), 2) if diffs else None}


def run(root: Path, placebo_n: int = S.PLACEBO_N, log=print) -> dict:
    root = Path(root)
    idx = load_idx(root)
    days, book, last = load_book(root)
    sett = settle_days(days, last, idx)
    m = Mkt(idx, days, book, sett)
    log(f"[txo1] 5 秒指數 {len(idx)} 天、日行情 {len(days)} 天、結算日 {len(sett)}")
    return {"ver": VER, "spec": S.VER, "spec_fp": S.fingerprint(), "asof": max(idx), "settle_days": len(sett),
            "o1": run_o1(root, m, placebo_n, log), "o4": run_o4(root, m, placebo_n, log)}
