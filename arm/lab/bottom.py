"""大跌後的買點與落底訊號（docs/lab_crash_plan.md 第 4、13、16、17 節；規格 bottomspec VER 3）。

  events_e5()／e10_segments()   兩種事件（只用到當天以前的收盤）
  peak_of()                     事件前高點（第 t−59～t 天最高收盤那天）
  buy_out()                     一個買進日的結果（R20／R60／R120、再創新低、之後最大不利跌幅）
  recovery()                    事件後幾個交易日回到事件前高點
  wave()／position()            （VER 3）這一波的最低收盤、買進價在這一波的位置、買在相對低點（下三分之一）
  first_signal()                八個落底訊號：事件之後第 1～60 個交易日內第一次出現的那天
  groups_at()                   事件當天的分組（底子、籌碼、泡沫）
  cboot_counts()                環狀移動區塊重抽：每次每個事件被抽到幾次
  paired()／two_group()         同一事件兩種買法的差、第一組 vs 第二組
  market()                      一個市場：事件、分組、規則比較、描述、BH、判定
                                （VER 3：看買在相對低點的比例；訊號和固定等 10 天比、固定等 10 天和事件隔天買比；
                                 VER 1、VER 2 的判定（再跌破低點）留作 v1、v2）
  primary()                     HB1、HB2（台股＋S&P 500 合併，Holm）
  research()                    → data/lab/bottom_research.json
  now()                         每天建頁：進行中的事件、分組、訊號

研究檔只在資料或規格改了才重跑：TZ=Asia/Taipei python3 scripts/run_bottom.py（numpy）。
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import bottomspec as S

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "lab" / "bottom_research.json"


def _arr(xs) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in xs], dtype=float)


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# ── 事件 ─────────────────────────────────────────────────────────────────

def events_e5(px: np.ndarray, th: float) -> list[int]:
    """5 日急跌：收盤 ÷ 5 個交易日前 − 1 ≤ −th；事件之後 E5_GAP 個交易日內不再算。"""
    out, last = [], None
    k = S.E5_DAYS
    for i in range(k, len(px)):
        a, b = px[i], px[i - k]
        if not (_ok(a) and _ok(b)) or b <= 0:
            continue
        if a / b - 1.0 <= -th and (last is None or i - last > S.E5_GAP):
            out.append(i)
            last = i
    return out


def hi60(px: np.ndarray, i: int) -> float | None:
    """第 i−59～i 天（共 60 天）的最高收盤；不滿 60 天或有缺＝None。"""
    if i < S.E10_WIN - 1:
        return None
    w = px[i - S.E10_WIN + 1:i + 1]
    if np.isnan(w).any():
        return None
    return float(w.max())


def e10_segments(px: np.ndarray) -> list[tuple[int, int | None]]:
    """從 60 日高點跌 10% 的每一段：（開始那天, 結束那天或 None＝到最後一天還沒結束）。
    結束＝之後第一天收盤比當天的 60 日高點低不到 5%（那天不算在這一段裡）。"""
    out: list = []
    start = None
    for i in range(len(px)):
        h = hi60(px, i)
        if h is None or not _ok(px[i]):
            continue
        dd = 1.0 - px[i] / h
        if start is None:
            if dd >= S.E10_IN:
                start = i
        elif dd < S.E10_OUT:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, None))
    return out


def events_e10(px: np.ndarray) -> list[int]:
    return [a for a, _ in e10_segments(px)]


def peak_of(px: np.ndarray, t: int) -> int:
    """事件前高點：第 t−59～t 天最高收盤那天（同價取最後一天）。"""
    a = max(0, t - S.PEAK_WIN + 1)
    w = px[a:t + 1]
    m = np.nanmax(w)
    return a + int(np.nonzero(w == m)[0][-1])


# ── 結果 ─────────────────────────────────────────────────────────────────

def buy_out(px: np.ndarray, p: int, b: int) -> dict:
    """第 b 天收盤買：R20／R60／R120、NL20（之後 20 天內跌破「事件前高點到買進那天」的最低收盤）、MAE60。超出資料＝None。"""
    T = len(px)
    out: dict = {"b": b}
    if b >= T or not _ok(px[b]):
        return out
    out["reb"] = float(px[b] / np.nanmin(px[p:b + 1]) - 1.0)   # 買進時比事件前高點到那天的最低收盤高多少（只描述）
    for h in S.HS:
        out[f"r{h}"] = float(px[b + h] / px[b] - 1.0) if b + h < T and _ok(px[b + h]) else None
    if b + S.NL_H < T:
        ref = float(np.nanmin(px[p:b + 1]))
        out["nl"] = int(float(np.nanmin(px[b + 1:b + S.NL_H + 1])) < ref)
    if b + S.MAE_H < T:
        out["mae"] = max(0.0, float(1.0 - np.nanmin(px[b + 1:b + S.MAE_H + 1]) / px[b]))
    return out


def recovery(px: np.ndarray, t: int, p: int) -> tuple[int | None, int]:
    """→（事件後幾個交易日第一次收盤 ≥ 事件前高點，沒回到＝None；之後還有幾天資料）。"""
    tgt = px[p]
    T = len(px)
    for u in range(t + 1, T):
        if _ok(px[u]) and px[u] >= tgt:
            return u - t, T - 1 - t
    return None, T - 1 - t


def wave(px: np.ndarray, t: int, p: int) -> tuple[float, int] | None:
    """（VER 3）這一波：事件前高點 p 到 end＝min(第 t＋WAVE_H 天, 第一個收盤回到事件前高點的日子)
    →（這一波的最低收盤 L, end）。資料還沒到第 t＋WAVE_H 天、而且還沒回到前高＝這一波還沒結束 → None。"""
    T = len(px)
    end = None
    for u in range(t + 1, min(T, t + S.WAVE_H + 1)):
        if _ok(px[u]) and px[u] >= px[p]:
            end = u
            break
    if end is None:
        if t + S.WAVE_H > T - 1:
            return None
        end = t + S.WAVE_H
    return float(np.nanmin(px[p:end + 1])), end


def position(px: np.ndarray, p: int, b: int, w: tuple | None) -> tuple[float | None, int | None]:
    """（VER 3）第 b 天收盤在這一波的位置（0＝這一波最低收盤、1＝事件前高點）與 LP 買在相對低點
    （位置 ≤ LP_CUT 而且買進日不在這一波結束之後）。這一波還沒結束或沒有第 b 天收盤＝(None, None)。"""
    if w is None or b >= len(px) or not _ok(px[b]):
        return None, None
    lo, end = w
    pos = float((px[b] - lo) / (px[p] - lo))
    return pos, int(b <= end and pos <= S.LP_CUT)


# ── 落底訊號 ──────────────────────────────────────────────────────────────

def first_signal(k: str, sig: dict, px: np.ndarray, t: int, end: int) -> int | None | str:
    """訊號 k 在第 t＋1～end 天第一次出現的那天；沒有出現＝None；事件那天沒有資料＝"na"。
    sig＝這個市場對齊好的訊號序列（見 inputs_tw／inputs_us）。"""
    T = len(px)
    end = min(end, T - 1)
    if k == "C1":
        v = sig.get("vix")
        if v is None or not _ok(v[t]):
            return "na"
        m = v[t]
        for s in range(t + 1, end + 1):
            if not _ok(v[s]):
                continue
            m = max(m, v[s])
            if v[s] <= (1.0 - S.C1_DROP) * m:
                return s
        return None
    if k == "C2":
        v = sig.get("mchg")
        if v is None or not _ok(v[t]):
            return "na"
        for s in range(t + 1, end + 1):
            if _ok(v[s]) and v[s] <= -S.C2_DROP:
                return s
        return None
    if k == "C3":
        v = sig.get("t5")
        if v is None or not _ok(v[t]):
            return "na"
        for s in range(t + 1, end + 1):
            if not _ok(v[s]) or v[s] < S.C3_HI:
                continue
            w = v[max(0, s - S.C3_WIN):s]
            if np.any(w[~np.isnan(w)] <= S.C3_LO):
                return s
        return None
    if k == "C4":
        v = sig.get("nl")
        if v is None or not _ok(v[t]):
            return "na"
        m = v[t]
        for s in range(t + 1, end + 1):
            if not _ok(v[s]):
                continue
            m = max(m, v[s])
            if m >= S.C4_FLOOR and v[s] <= S.C4_HALF * m:
                return s
        return None
    if k == "C5":
        v, fl = sig.get("net"), sig.get("c5floor")
        if v is None or fl is None or not _ok(v[t]):
            return "na"
        m = max(0.0, -v[t])
        for s in range(t + 1, end + 1):
            if not _ok(v[s]):
                continue
            m = max(m, -v[s])
            if m >= fl and -v[s] <= (1.0 - S.C5_CUT) * m:
                return s
        return None
    if k == "C6":
        v, ma = sig.get("pc"), sig.get("pcma")
        if v is None or ma is None or not (_ok(v[t]) and _ok(ma[t])):
            return "na"
        above = v[t] > ma[t]
        for s in range(t + 1, end + 1):
            if not (_ok(v[s]) and _ok(ma[s])):
                continue
            if above and v[s] < ma[s]:
                return s
            if v[s] > ma[s]:
                above = True
        return None
    if k == "C7":
        vol = sig.get("vol")
        if vol is None or not _ok(vol[t]):
            return "na"
        m = t
        for s in range(t + 1, end + 1):
            if not _ok(px[s]):
                continue
            if px[s] <= px[m]:
                m = s
                continue
            if (s - m >= S.C7_GAP and _ok(px[s - 1]) and px[s] / px[s - 1] - 1.0 >= S.C7_UP
                    and _ok(vol[s]) and _ok(vol[s - 1]) and vol[s] > vol[s - 1]):
                return s
        return None
    if k == "C8":
        v = sig.get("adv")
        if v is None or not _ok(v[t]):
            return "na"
        for s in range(t + 1, end + 1):
            if _ok(v[s]) and v[s] >= S.C8_UP:
                return s
        return None
    if k == "C9":                                               # VER 4：融資維持率從 140% 以下回到 150% 以上
        v = sig.get("mr")
        if v is None or not _ok(v[t]):
            return "na"
        low = v[t] < S.C9_LO
        for s in range(t + 1, end + 1):
            if not _ok(v[s]):
                continue
            if low and v[s] >= S.C9_HI:
                return s
            if v[s] < S.C9_LO:
                low = True
        return None
    raise KeyError(k)


def rule_buy(k: str, sig: dict, px: np.ndarray, t: int, end: int | None = None) -> tuple:
    """規則 k → （訊號那天或 None 或 "na", 買進那天或 None）。W10＝固定第 t＋WAIT 天收盤買。"""
    if k == "W10":
        return t + S.WAIT - S.LAG, t + S.WAIT
    end = t + S.SIG_WIN if end is None else end
    s = first_signal(k, sig, px, t, end)
    if s is None or s == "na":
        return s, None
    return s, s + S.LAG


# ── 分組 ─────────────────────────────────────────────────────────────────

def groups_at(I: dict, t: int) -> tuple[dict, dict]:
    """事件當天：→（{fund, chip, bub: 1／0／None}, 當天的值）。"""
    g, v = {}, {}
    F = I["fund"]
    f0 = F[t - S.FUND_LOOK] if t >= S.FUND_LOOK else np.nan
    v["fund"], v["fund0"] = (float(F[t]) if _ok(F[t]) else None), (float(f0) if _ok(f0) else None)
    g["fund"] = None if v["fund"] is None or v["fund0"] is None else int(v["fund"] >= S.FUND_MIN and v["fund"] >= v["fund0"])
    X = I["chip"]
    w = X[max(0, t - S.CHIP_LOOK):t]
    w = w[~np.isnan(w)]
    v["chip"] = float(w.max()) if len(w) else None
    g["chip"] = None if not len(w) else int(w.max() >= S.CHIP_HOT)
    lv = I.get("bublv")
    if lv is not None:                                          # 泡沫頁每月判定的等級（月底判定、下個交易日起用）
        v["bub"] = int(lv[t]) if _ok(lv[t]) else None
        g["bub"] = None if v["bub"] is None else int(v["bub"] >= S.BUB_MIN)
    else:                                                       # 沒有等級序列時用 crash 的 BL2（等級 2 以上＝100）
        bb = I["bub"][t]
        v["bub"] = None
        g["bub"] = None if not _ok(bb) else int(bb >= 100.0)
    return g, v


# ── 重抽 ─────────────────────────────────────────────────────────────────

def cboot_counts(pos: np.ndarray, lo: int, hi: int, L: int = S.BLOCK, n_boot: int = S.BOOT_N,
                 seed: int = S.BOOT_SEED) -> np.ndarray | None:
    """環狀移動區塊重抽：日曆 lo～hi（含）共 n 天，每次抽 ⌈n／L⌉ 塊（超過最後一天接回第一天）；
    → (n_boot × 事件數) 每次每個事件被抽到幾次。天數不到 2L＝None。"""
    n = hi - lo + 1
    if n < 2 * L or not len(pos):
        return None
    k = math.ceil(n / L)
    rng = np.random.default_rng(seed)
    st = rng.integers(0, n, size=(n_boot, k))
    r = (np.asarray(pos) - lo).astype(np.int64)
    out = np.zeros((n_boot, len(r)), dtype=np.int64)
    for j in range(k):                                         # 一塊一塊加，避免一次開 n_boot × k × 事件數的陣列
        out += ((r[None, :] - st[:, j:j + 1]) % n < L)
    return out


def ci_p(reps: np.ndarray | None) -> tuple:
    """→ (下緣, 上緣, 雙尾 p, 單尾 p（差 ≤ 0 的比例）)；有效次數不到一半＝全部 None。"""
    if reps is None:
        return None, None, None, None
    r = reps[~np.isnan(reps)]
    if len(r) < len(reps) / 2 or not len(r):
        return None, None, None, None
    a = (1.0 - S.CI) / 2.0
    lo, hi = np.quantile(r, [a, 1.0 - a])
    le, ge = float(np.mean(r <= 0)), float(np.mean(r >= 0))
    pmin = 1.0 / S.BOOT_N
    return float(lo), float(hi), min(1.0, max(pmin, 2.0 * min(le, ge))), max(pmin, le)


def episodes(pos) -> int:
    p = sorted(int(x) for x in pos)
    if not p:
        return 0
    return 1 + sum(1 for a, b in zip(p, p[1:]) if b - a > S.EP_GAP)


def _wmean(C: np.ndarray, y: np.ndarray) -> np.ndarray:
    den = C.sum(axis=1)
    num = C @ y
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def _halves(pos: np.ndarray, fn) -> tuple:
    o = np.argsort(pos, kind="stable")
    m = len(o) // 2
    return fn(o[:m]), fn(o[m:])


def paired(pos: np.ndarray, d: np.ndarray) -> dict:
    """同一事件兩種買法的差（d＝規則 − 對照）：平均、區間、p、前後兩半。"""
    out = {"d": float(d.mean()) if len(d) else None}
    if len(d) == 0:
        return out
    C = cboot_counts(pos, int(pos.min()), int(pos.max()))
    out["lo"], out["hi"], out["p"], out["p1"] = ci_p(None if C is None else _wmean(C, d))
    out["h1"], out["h2"] = _halves(pos, lambda ix: float(d[ix].mean()) if len(ix) else None)
    return out


def two_group(pos: np.ndarray, g: np.ndarray, y: np.ndarray) -> dict:
    """第一組（g＝1）平均 − 第二組（g＝0）平均：差、區間、p、前後兩半（全部事件照時間切一半）。"""
    a, b = g == 1, g == 0
    out = {"d": float(y[a].mean() - y[b].mean()) if a.any() and b.any() else None}
    if out["d"] is None:
        return out
    C = cboot_counts(pos, int(pos.min()), int(pos.max()))
    if C is not None:
        reps = _wmean(C[:, a], y[a]) - _wmean(C[:, b], y[b])
        out["lo"], out["hi"], out["p"], out["p1"] = ci_p(reps)
    else:
        out["lo"] = out["hi"] = out["p"] = out["p1"] = None

    def half(ix):
        ga, gb = ix[g[ix] == 1], ix[g[ix] == 0]
        return float(y[ga].mean() - y[gb].mean()) if len(ga) and len(gb) else None
    out["h1"], out["h2"] = _halves(pos, half)
    return out


def bh(ps: list) -> list:
    from .heatrel import bh as _bh
    return _bh(ps)


def holm(ps: dict, alpha: float = S.HOLM_ALPHA) -> tuple[dict, dict]:
    from .heatreg import holm as _h
    return _h(ps, alpha)


def sdir(r: dict, pre: str) -> str:
    """一個差的方向：down＝區間上緣 < 0、兩半 < 0、q ≤ BH_Q；up＝反過來；其他 none。pre＝欄位前綴（nl／r）。"""
    lo, hi, h1, h2, q = (r.get(f"{pre}_{k}") for k in ("lo", "hi", "h1", "h2", "q"))
    if None in (lo, hi, h1, h2, q) or q > S.BH_Q:
        return "none"
    if hi < 0 and h1 < 0 and h2 < 0:
        return "down"
    if lo > 0 and h1 > 0 and h2 > 0:
        return "up"
    return "none"


def rule_verdict(r: dict) -> str:
    if r.get("few"):
        return "few"
    nl, rr = sdir(r, "nl"), sdir(r, "r")
    if nl == "down":
        d, h1, h2 = r.get("r_d"), r.get("r_h1"), r.get("r_h2")
        if None not in (d, h1, h2) and d >= 0 and h1 >= 0 and h2 >= 0:
            return "better"
        if rr == "down":
            return "trade"
        return "none"
    if nl == "up" or rr == "down":
        return "worse"
    return "none"


def rule_verdict3(r: dict) -> str:
    """（VER 3，規格 6.1c）有用＝買在相對低點的比例比較高、60 日報酬沒有比較少；比較高但報酬比較少＝有取捨。"""
    if r.get("few"):
        return "few"
    lp, rr = sdir(r, "lp"), sdir(r, "r")
    if lp == "up":
        return "trade" if rr == "down" else "better"
    if lp == "down" or rr == "down":
        return "worse"
    return "none"


def group_verdict(r: dict) -> str:
    if r.get("few"):
        return "few"
    lo, hi, h1, h2, q = (r.get(k) for k in ("lo", "hi", "h1", "h2", "q"))
    if None in (lo, hi, h1, h2, q) or q > S.BH_Q:
        return "none"
    if lo > 0 and h1 > 0 and h2 > 0:
        return "up"
    if hi < 0 and h1 < 0 and h2 < 0:
        return "down"
    return "none"


# ── 描述 ─────────────────────────────────────────────────────────────────

def _q(a, q) -> float | None:
    return float(np.quantile(a, q)) if len(a) else None


def desc(recs: list[dict], key: str = "b1") -> dict:
    """一組事件（買法 key）：R20／R60／R120 的平均、中位數、第 25／75 百分位、上漲比例；NL20 比例；MAE60 中位數與第 75 百分位；
    回到事件前高點（60／120／250 個交易日內回到的比例、中位數）。"""
    out: dict = {"n": len(recs)}
    for h in S.HS:
        a = np.array([r[key][f"r{h}"] for r in recs if r.get(key) and r[key].get(f"r{h}") is not None])
        out[f"r{h}"] = {"n": int(len(a)), "mean": float(a.mean()) if len(a) else None, "med": _q(a, 0.5),
                        "p25": _q(a, 0.25), "p75": _q(a, 0.75), "up": float(np.mean(a > 0)) if len(a) else None}
    nl = [r[key]["nl"] for r in recs if r.get(key) and r[key].get("nl") is not None]
    out["nl"] = {"n": len(nl), "rate": float(np.mean(nl)) if nl else None}
    lp = [r[key]["lp"] for r in recs if r.get(key) and r[key].get("lp") is not None]
    out["lp"] = {"n": len(lp), "rate": float(np.mean(lp)) if lp else None}
    ps = np.array([r[key]["pos"] for r in recs if r.get(key) and r[key].get("pos") is not None])
    out["pos"] = {"n": int(len(ps)), "med": _q(ps, 0.5)}
    rb = np.array([r[key]["reb"] for r in recs if r.get(key) and r[key].get("reb") is not None])
    out["reb"] = {"n": int(len(rb)), "med": _q(rb, 0.5)}
    mae = np.array([r[key]["mae"] for r in recs if r.get(key) and r[key].get("mae") is not None])
    out["mae"] = {"n": int(len(mae)), "med": _q(mae, 0.5), "p75": _q(mae, 0.75), "max": float(mae.max()) if len(mae) else None}
    rec = {}
    for h in S.REC_H:
        el = [r for r in recs if (r.get("rec") is not None and r["rec"] <= h) or r.get("fu", 0) >= h]
        rec[str(h)] = {"n": len(el), "share": float(np.mean([r.get("rec") is not None and r["rec"] <= h for r in el])) if el else None}
    hx = S.REC_H[-1]
    el = [r for r in recs if (r.get("rec") is not None and r["rec"] <= hx) or r.get("fu", 0) >= hx]
    vals = sorted((r["rec"] if r.get("rec") is not None and r["rec"] <= hx else math.inf) for r in el)
    rec["med"], rec["gt"] = _median_inf(vals)
    out["rec"] = rec
    return out


def _median_inf(vals: list) -> tuple:
    """排好的數字（沒回到＝無限大）→（中位數或 None, 中位數是不是「超過觀察期」）。"""
    if not vals:
        return None, None
    n = len(vals)
    m = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
    return (None, True) if math.isinf(m) else (float(m), False)


# ── 輸入 ─────────────────────────────────────────────────────────────────

def _exact(cal: list[str], ser: dict) -> np.ndarray:
    return np.array([float(ser[d]) if d in ser and ser[d] is not None else np.nan for d in cal])


def _native_chg(ser: dict, k: int) -> dict:
    ks = sorted(d for d, v in ser.items() if v)
    return {ks[i]: ser[ks[i]] / ser[ks[i - k]] - 1.0 for i in range(k, len(ks)) if ser[ks[i - k]]}


def _native_ma(ser: dict, k: int) -> dict:
    ks = sorted(d for d, v in ser.items() if v is not None)
    out = {}
    for i in range(k - 1, len(ks)):
        out[ks[i]] = sum(ser[ks[j]] for j in range(i - k + 1, i + 1)) / k
    return out


def breadth_series(br: dict) -> dict[str, dict]:
    """廣度（heatfetch.breadth_update：[上漲, 下跌, 站上60日, 60日家數, 新高, 新低, 250日家數]）→
    t5（10 日上漲家數占比，同景氣頁 T5）、adv（當天上漲占比）、nl（當天創 250 日新低占比）；家數不到 BREADTH_MIN 不算。"""
    from .heatdata import breadth_ind
    bk = sorted(br)
    cols = {f: [br[d][j] for d in bk] for j, f in enumerate(("adv", "dec", "above", "n60", "hi", "lo", "n250"))}
    t5 = {d: v / 100.0 for d, v in breadth_ind({"cal": bk, **cols})["T5"].items()}
    adv, nl = {}, {}
    for d in bk:
        a, b, lo, n250 = br[d][0], br[d][1], br[d][5], br[d][6]
        if a + b >= S.BREADTH_MIN:
            adv[d] = a / (a + b)
        if n250 >= S.BREADTH_MIN:
            nl[d] = lo / n250
    return {"t5": t5, "adv": adv, "nl": nl}


def us_breadth_series(br: dict) -> dict[str, dict]:
    """（VER 4）美股漲跌家數（usbreadth：[上漲, 下跌, 平盤, 上漲成交金額, 下跌成交金額, 上漲點數, 下跌點數, 有資料檔數, 成分股數]）→
    t5（最近 10 筆的上漲家數占比，和台股 breadth_series 同一個 breadth_ind 算法）、adv（當天上漲占比；上漲＋下跌不到 BREADTH_MIN 不算）。"""
    from .heatdata import breadth_ind
    bk = sorted(d for d, v in br.items() if v and v[0] is not None and v[1] is not None)
    z = [0] * len(bk)
    t5 = breadth_ind({"cal": bk, "adv": [br[d][0] for d in bk], "dec": [br[d][1] for d in bk],
                      "above": z, "n60": z, "hi": z, "lo": z, "n250": z})["T5"]
    adv = {}
    for d in bk:
        a, b = br[d][0], br[d][1]
        if a + b >= S.BREADTH_MIN:
            adv[d] = a / (a + b)
    return {"t5": {d: v / 100.0 for d, v in t5.items()}, "adv": adv}


def _bub_levels(cal: list[str], rows: list, done: set) -> np.ndarray:
    from .crash import rows_to_daily
    return rows_to_daily(cal, rows, lambda r: r.get("L"), done)


def inputs_tw(B: dict | None = None, IT: dict | None = None, BX: dict | None = None) -> dict:
    """台股：日曆與收盤（crash.tw_inputs，1990 起）、分組用的三個序列、八個訊號的序列（都對齊這個日曆）。"""
    from . import crash as CR
    from . import heat as H
    from . import heatcalc as HC
    if B is None:
        B = HC.build()
    if IT is None:
        IT = CR.tw_inputs(B=B, BX=BX)
    cal, px = list(IT["cal"]), np.asarray(IT["px"], dtype=float)
    D = B["D"]
    I = {"mk": "tw", "cal": cal, "px": px, "fund": CR.align(cal, B["cal"], B["comp"]["fund"]),
         "chip": np.asarray(IT["x"][S.CHIP_VAR["tw"]], dtype=float), "bub": np.asarray(IT["x"]["BL2"], dtype=float)}
    rows = (((BX or {}).get("tw") or {}).get("_C") or {}).get("rows") if BX else None
    if rows:
        I["bublv"] = _bub_levels(cal, rows, CR.complete_months(cal))
    sig: dict = {"vix": _arr(H.asof_daily(cal, D.get("vix") or {}, after=True, stale=7))}
    mg = {d: v[0] for d, v in (D.get("margin") or {}).items() if v and v[0]}
    sig["mchg"] = _exact(cal, _native_chg(mg, S.C2_DAYS))
    bs = breadth_series(D.get("breadth") or {})
    for k in ("t5", "adv", "nl"):
        sig[k] = _exact(cal, bs[k])
    sig["net"] = _exact(cal, HC.f1_foreign_fut(D.get("futi") or {}))
    sig["c5floor"] = S.C5_FLOOR["tw"]
    pc = {d: v[2] for d, v in (D.get("pcr") or {}).items() if v and len(v) > 2 and v[2] is not None}
    sig["pc"] = _exact(cal, pc)
    sig["pcma"] = _exact(cal, _native_ma(pc, S.C6_MA))
    sig["vol"] = _exact(cal, {d: v[0] for d, v in (D.get("turnover") or {}).items() if v and v[0]})
    if "C9" in S.SIG_MK["tw"]:                                   # VER 4：大盤融資維持率（%）
        from . import heatdata as HD
        mr = D.get("mratio") or HD.load("mratio")
        sig["mr"] = _exact(cal, {d: v[0] for d, v in mr.items() if v and v[0] is not None})
    I["sig"] = sig
    return I


def inputs_us(idx: str, Bu: dict, I0: dict, vol: dict | None = None, BX: dict | None = None) -> dict:
    """美股一個指數：Bu＝heatcalc_us.build(idx)、I0＝crash.us_inputs(idx)；vol＝Yahoo 成交量（費半沒有）。"""
    from . import crash as CR
    from . import heat as H
    cal, px = list(I0["cal"]), np.asarray(I0["px"], dtype=float)
    c0 = Bu["cal"].index(cal[0]) if cal else 0
    I = {"mk": idx, "cal": cal, "px": px, "fund": _arr(Bu["comp"]["fund"][c0:]),
         "chip": np.asarray(I0["x"][S.CHIP_VAR["us"]], dtype=float), "bub": np.asarray(I0["x"]["BL2"], dtype=float)}
    rows = (((BX or {}).get(idx) or {}).get("_C") or {}).get("rows") if BX else None
    if rows:
        I["bublv"] = _bub_levels(cal, rows, CR.complete_months(cal))
    sig: dict = {"vix": _arr(H.asof_daily(cal, (Bu.get("D") or {}).get("vix") or {}, stale=7)),
                 "net": _arr((Bu["raw"].get("S2") or [None] * len(Bu["cal"]))[c0:]), "c5floor": S.C5_FLOOR["us"]}
    if "C7" in S.SIG_MK[idx] and vol:
        sig["vol"] = _exact(cal, vol)
    if {"C3", "C8"} & set(S.SIG_MK[idx]):                        # VER 4：S&P 500 成分股的漲跌家數（四個指數同一份）
        from . import heatdata as HD
        bs = us_breadth_series(HD.load("us_breadth"))
        sig["t5"], sig["adv"] = _exact(cal, bs["t5"]), _exact(cal, bs["adv"])
    I["sig"] = sig
    return I


# ── 一個市場 ──────────────────────────────────────────────────────────────

def event_recs(I: dict, ev: str) -> list[dict]:
    """一種事件的每一次：事件日、事件前高點、深度、分組、事件隔天買／固定等 10 天／各訊號的結果、回到事件前高點。"""
    mk, cal, px = I["mk"], I["cal"], I["px"]
    T = len(cal)
    idxs = events_e5(px, S.E5_TH[mk]) if ev == "E5" else events_e10(px)
    out = []
    for t in idxs:
        p = peak_of(px, t)
        g, gv = groups_at(I, t)
        rec, fu = recovery(px, t, p)
        w = wave(px, t, p)
        depth = float(px[t] / px[t - S.E5_DAYS] - 1.0) if ev == "E5" else float(px[t] / px[p] - 1.0)
        b1 = buy_out(px, p, t + S.LAG)
        b1["pos"], b1["lp"] = position(px, p, t + S.LAG, w)
        r = {"t": t, "d": cal[t], "p": p, "pd": cal[p], "depth": depth, "dd": float(px[t] / px[p] - 1.0),
             "g": g, "gv": gv, "rec": rec, "fu": fu, "b1": b1, "rules": {},
             "wl": None if w is None else float(w[0] / px[p] - 1.0)}
        full = t + S.SIG_WIN <= T - 1                           # 60 天的窗口已經走完（才知道訊號有沒有出現）
        for k in ("W10",) + tuple(S.SIG_MK[mk]):
            s, b = rule_buy(k, I["sig"], px, t)
            rr = {"s": s if s != "na" else None, "na": s == "na", "full": full or (s not in (None, "na"))}
            if b is not None:
                rr["o"] = buy_out(px, p, b)
                rr["o"]["pos"], rr["o"]["lp"] = position(px, p, b, w)
            r["rules"][k] = rr
        out.append(r)
    return out


def _pair_rows(recs: list[dict], k: str, base: str = "b1") -> list[tuple]:
    """規則 k 和對照（事件隔天買 b1，或固定等 10 天 W10）都有 NL20 與 R60 的事件 → [(t, 規則結果, 對照結果)]。"""
    rows = []
    for r in recs:
        rr = r["rules"].get(k) or {}
        o = rr.get("o") or {}
        if base == "b1":
            ob = r["b1"]
        else:
            ob = ((r["rules"].get(base) or {}).get("o")) or {}
        if o.get("nl") is not None and o.get("r60") is not None and ob.get("nl") is not None and ob.get("r60") is not None:
            rows.append((r["t"], o, ob))
    return rows


def _cmp(rows: list[tuple], tag: str) -> dict:
    """同一事件兩種買法（rows＝[(t, 規則結果, 對照結果)]，tag＝對照的名字 b1／w10）→ 次數、段數、兩邊的 NL20 比例與 R60、
    差（規則 − 對照）的平均、區間、p、前後兩半、樣本不足。"""
    n = len(rows)
    pos = np.array([t for t, _, _ in rows], dtype=np.int64)
    out: dict = {"n": n, "ep": episodes(pos)}
    if n:
        nl_r = np.array([o["nl"] for _, o, _ in rows], dtype=float)
        nl_b = np.array([ob["nl"] for _, _, ob in rows], dtype=float)
        r_r = np.array([o["r60"] for _, o, _ in rows])
        r_b = np.array([ob["r60"] for _, _, ob in rows])
        mae_r = np.array([o["mae"] for _, o, _ in rows if o.get("mae") is not None])
        mae_b = np.array([ob["mae"] for _, _, ob in rows if ob.get("mae") is not None])
        out.update({"nl_rule": float(nl_r.mean()), f"nl_{tag}": float(nl_b.mean()), "r_rule": float(r_r.mean()),
                    f"r_{tag}": float(r_b.mean()), "r_rule_med": _q(r_r, 0.5), f"r_{tag}_med": _q(r_b, 0.5),
                    "mae_rule": _q(mae_r, 0.5), f"mae_{tag}": _q(mae_b, 0.5)})
        for pre, d in (("nl", nl_r - nl_b), ("r", r_r - r_b)):
            for a, b in paired(pos, d).items():
                out[f"{pre}_{a}"] = b
    out["few"] = bool(n < S.MIN_N or out["ep"] < S.MIN_EP or out.get("nl_lo") is None or out.get("r_lo") is None)
    return out


def _lp_rows(recs: list[dict], k: str, base: str) -> list[tuple]:
    """（VER 3）規則 k 和對照（b1 或 W10）的 LP 與 R60 都有值的事件 → [(t, 規則結果, 對照結果, 事件隔天買結果)]。"""
    rows = []
    for r in recs:
        o = ((r["rules"].get(k) or {}).get("o")) or {}
        ob = r["b1"] if base == "b1" else ((((r["rules"].get(base) or {}).get("o")) or {}))
        if None not in (o.get("lp"), o.get("r60"), ob.get("lp"), ob.get("r60")):
            rows.append((r["t"], o, ob, r["b1"]))
    return rows


def _cmp3(rows: list[tuple], base: str) -> dict:
    """（VER 3）規則 − 對照：LP（買在相對低點的比例差）與 R60 的平均、區間、p、前後兩半、樣本不足；
    另列兩邊與事件隔天買的 LP 比例、位置中位數、之後 60 日最多再跌的中位數（不判定）。"""
    n = len(rows)
    pos = np.array([t for t, *_ in rows], dtype=np.int64)
    out: dict = {"base": base, "n": n, "ep": episodes(pos)}
    if n:
        lp_r = np.array([o["lp"] for _, o, _, _ in rows], dtype=float)
        lp_b = np.array([ob["lp"] for _, _, ob, _ in rows], dtype=float)
        r_r = np.array([o["r60"] for _, o, _, _ in rows])
        r_b = np.array([ob["r60"] for _, _, ob, _ in rows])
        b1 = [x["lp"] for *_, x in rows if x.get("lp") is not None]
        out.update({"lp_rule": float(lp_r.mean()), "lp_base": float(lp_b.mean()),
                    "lp_b1": float(np.mean(b1)) if b1 else None,
                    "r_rule": float(r_r.mean()), "r_base": float(r_b.mean()),
                    "pos_rule": _q(np.array([o["pos"] for _, o, _, _ in rows]), 0.5),
                    "pos_base": _q(np.array([ob["pos"] for _, _, ob, _ in rows]), 0.5),
                    "mae_rule": _q(np.array([o["mae"] for _, o, _, _ in rows if o.get("mae") is not None]), 0.5),
                    "mae_base": _q(np.array([ob["mae"] for _, _, ob, _ in rows if ob.get("mae") is not None]), 0.5),
                    "reb_rule": _q(np.array([o["reb"] for _, o, _, _ in rows]), 0.5),
                    "reb_base": _q(np.array([ob["reb"] for _, _, ob, _ in rows]), 0.5)})
        for pre, d in (("lp", lp_r - lp_b), ("r", r_r - r_b)):
            for a, b in paired(pos, d).items():
                out[f"{pre}_{a}"] = b
    out["few"] = bool(n < S.MIN_N or out["ep"] < S.MIN_EP or out.get("lp_lo") is None or out.get("r_lo") is None)
    return out


def rule_stats(recs: list[dict], k: str) -> dict:
    """規則 k：出現比例、事件到訊號幾天、和事件隔天買比（NL20 與 R60 的差、區間、兩半、p；VER 1 的比較，平鋪在最上層）；
    訊號另和固定等 10 天比（VER 2 的判定依據，放在 w10）。"""
    out: dict = {}
    el = [r for r in recs if not (r["rules"].get(k) or {}).get("na")]
    seen = [r for r in el if (r["rules"].get(k) or {}).get("full")]
    fired = [r for r in seen if (r["rules"][k].get("s") is not None) or k == "W10"]
    out["elig"], out["seen"], out["fired"] = len(el), len(seen), len(fired)
    out["cov"] = len(fired) / len(seen) if seen else None
    if k != "W10":
        dl = [r["rules"][k]["s"] - r["t"] for r in fired if r["rules"][k].get("s") is not None]
        out["delay"] = float(np.median(dl)) if dl else None
        out["delay_q"] = [_q(np.array(dl), 0.25), _q(np.array(dl), 0.75)] if dl else None
    out.update(_cmp(_pair_rows(recs, k), "b1"))
    if k != S.SIG_BASE:
        out["w10"] = _cmp(_pair_rows(recs, k, base=S.SIG_BASE), "w10")
    base = "b1" if k == S.SIG_BASE else S.SIG_BASE
    out["lp"] = _cmp3(_lp_rows(recs, k, base), base)                # VER 3 的判定依據
    return out


def group_stats(recs: list[dict], g: str) -> dict:
    """分組 g：事件隔天買的 R60，第一組 − 第二組（區間、兩半、p）＋兩組各自的描述。"""
    rows = [r for r in recs if r["g"].get(g) is not None and r["b1"].get("r60") is not None]
    out: dict = {"n1": sum(1 for r in rows if r["g"][g] == 1), "n0": sum(1 for r in rows if r["g"][g] == 0)}
    out["g1"] = desc([r for r in recs if r["g"].get(g) == 1])
    out["g0"] = desc([r for r in recs if r["g"].get(g) == 0])
    pos = np.array([r["t"] for r in rows], dtype=np.int64)
    out["ep"] = episodes(pos)
    if out["n1"] and out["n0"]:
        gg = np.array([r["g"][g] for r in rows])
        y = np.array([r["b1"]["r60"] for r in rows])
        out.update(two_group(pos, gg, y))
    out["few"] = bool(out["n1"] < S.MIN_N or out["n0"] < S.MIN_N or out["ep"] < S.MIN_EP or out.get("lo") is None)
    return out


def market(I: dict) -> dict:
    """一個市場：兩種事件 × （描述、分組比較、規則比較）＋BH 與判定。"""
    mk, cal, px = I["mk"], I["cal"], I["px"]
    out: dict = {"start": cal[0] if cal else None, "end": cal[-1] if cal else None, "th": S.E5_TH[mk],
                 "sigma": float(np.nanstd(px[1:] / px[:-1] - 1.0, ddof=1)) if len(px) > 2 else None, "ev": {}}
    first = {}
    for k, key in (("C1", "vix"), ("C2", "mchg"), ("C3", "t5"), ("C4", "nl"), ("C5", "net"), ("C6", "pcma"),
                   ("C7", "vol"), ("C8", "adv"), ("C9", "mr")):
        v = I["sig"].get(key)
        if v is not None and k in S.SIG_MK[mk]:
            ix = np.nonzero(~np.isnan(v))[0]
            first[k] = cal[int(ix[0])] if len(ix) else None
    out["sigfirst"] = first
    for ev in S.EVENTS:
        recs = event_recs(I, ev)
        for r in recs:                                          # 訊號買進價比事件隔天的收盤高或低
            b1 = r["b1"].get("b")
            for k, rr in r["rules"].items():
                o = rr.get("o")
                if o and b1 is not None and o.get("b") is not None and o["b"] < len(px):
                    o["px_vs_b1"] = float(px[o["b"]] / px[b1] - 1.0)
        E: dict = {"n": len(recs), "all": desc(recs), "groups": {g: group_stats(recs, g) for g in S.GROUPS},
                   "rules": {k: rule_stats(recs, k) for k in ("W10",) + tuple(S.SIG_MK[mk])}}
        for k, st in E["rules"].items():
            vals = [r["rules"][k]["o"].get("px_vs_b1") for r in recs
                    if (r["rules"].get(k) or {}).get("o") and r["rules"][k]["o"].get("px_vs_b1") is not None]
            st["px_med"] = float(np.median(vals)) if vals else None
        # BH：規則和事件隔天買比（VER 1：固定等 10 天＋全部訊號）、訊號和固定等 10 天比（VER 2：只有訊號），
        # NL20、R60 各一個家族；分組（R60）。VER 4（6.4）：新加的訊號（SIG_ADD4）在每一種比較都自成一個家族，原本的家族照舊。
        add = set(S.SIG_ADD4.get(mk) or ())
        old = [k for k in E["rules"] if k not in add]
        new = [k for k in E["rules"] if k in add]
        for pre in ("nl", "r"):
            for fam in (old, new):
                ks = [k for k in fam if not E["rules"][k]["few"] and E["rules"][k].get(f"{pre}_p") is not None]
                for k, q in zip(ks, bh([E["rules"][k][f"{pre}_p"] for k in ks])):
                    E["rules"][k][f"{pre}_q"] = q
                ks = [k for k in fam if k != S.SIG_BASE and not E["rules"][k]["w10"]["few"]
                      and E["rules"][k]["w10"].get(f"{pre}_p") is not None]
                for k, q in zip(ks, bh([E["rules"][k]["w10"][f"{pre}_p"] for k in ks])):
                    E["rules"][k]["w10"][f"{pre}_q"] = q
        # VER 3（6.1c）：落底訊號 vs 固定等 10 天一個家族；固定等 10 天 vs 事件隔天買自成一個（LP、R60 各一個）；VER 4 新訊號另一個
        sig = [k for k in old if k != S.SIG_BASE]
        for pre in ("lp", "r"):
            for fam in (sig, [S.SIG_BASE], new):
                ks = [k for k in fam if not E["rules"][k]["lp"]["few"] and E["rules"][k]["lp"].get(f"{pre}_p") is not None]
                for k, q in zip(ks, bh([E["rules"][k]["lp"][f"{pre}_p"] for k in ks])):
                    E["rules"][k]["lp"][f"{pre}_q"] = q
        for k, st in E["rules"].items():
            st["nl_dir"], st["r_dir"] = sdir(st, "nl"), sdir(st, "r")
            st["v1"] = rule_verdict(st)                        # VER 1：和事件隔天買比再跌破低點
            if k == S.SIG_BASE:
                st["v2"] = st["v1"]
            else:
                w = st["w10"]                                  # VER 2：訊號和固定等 10 天比再跌破低點
                w["nl_dir"], w["r_dir"] = sdir(w, "nl"), sdir(w, "r")
                w["v"] = rule_verdict(w)
                st["v2"] = w["v"]
            c = st["lp"]                                       # VER 3：買在相對低點（現行判定）
            c["lp_dir"], c["r_dir"] = sdir(c, "lp"), sdir(c, "r")
            c["v"] = rule_verdict3(c)
            st["v"] = c["v"]
        gs = [g for g, st in E["groups"].items() if not st["few"] and st.get("p") is not None]
        for g, q in zip(gs, bh([E["groups"][g]["p"] for g in gs])):
            E["groups"][g]["q"] = q
        for g, st in E["groups"].items():
            st["v"] = group_verdict(st)
        E["list"] = [_list_row(r, mk) for r in recs]
        out["ev"][ev] = E
    return out


def _list_row(r: dict, mk: str) -> dict:
    """研究檔裡每一次事件（頁面清單用）。"""
    b1 = r["b1"]
    sig = {}
    for k, rr in r["rules"].items():
        if k == "W10":
            continue
        sig[k] = "na" if rr.get("na") else (None if rr.get("s") is None else int(rr["s"] - r["t"]))
        if rr.get("s") is None and not rr.get("na") and not rr.get("full"):
            sig[k] = "open"
    return {"d": r["d"], "pd": r["pd"], "depth": r["depth"], "dd": r["dd"], "g": r["g"], "gv": r["gv"],
            "r20": b1.get("r20"), "r60": b1.get("r60"), "r120": b1.get("r120"), "nl": b1.get("nl"), "mae": b1.get("mae"),
            "pos": b1.get("pos"), "lp": b1.get("lp"), "wl": r.get("wl"),
            "rec": r["rec"], "fu": r["fu"], "sig": sig}


# ── 主要假說 ──────────────────────────────────────────────────────────────

def pooled(parts: list[tuple[str, list[dict], float, list[str]]], g: str) -> dict:
    """HB1、HB2：parts＝[(市場, E5 的事件, 日報酬標準差, 日曆)]。R60 ÷（標準差 × √60），各市場第一組 − 第二組依第一組次數加權
    （兩組都至少 POOL_MIN 次的市場才算）；兩個市場日期的聯集日曆上環狀區塊重抽（同一段日子一起抽）；
    前後兩半＝合起來的事件依日期切在中間那一筆。"""
    obs, use, nn = [], [], {}
    for m, (mk, recs, sig, _) in enumerate(parts):
        rows = [r for r in recs if r["g"].get(g) is not None and r["b1"].get("r60") is not None]
        n1, n0 = sum(1 for r in rows if r["g"][g] == 1), sum(1 for r in rows if r["g"][g] == 0)
        if n1 < S.POOL_MIN or n0 < S.POOL_MIN:
            continue
        use.append(mk)
        nn[mk] = [n1, n0]
        z = sig * math.sqrt(S.MAIN_H)
        for r in rows:
            obs.append((r["d"], m, r["g"][g], r["b1"]["r60"] / z))
    out: dict = {"mk": use, "n": nn, "few": not obs}
    if not obs:
        return out
    obs.sort(key=lambda o: (o[0], o[1]))
    lo_d, hi_d = obs[0][0], obs[-1][0]
    U = sorted({d for mk, _, _, cal in parts if mk in use for d in cal if lo_d <= d <= hi_d})
    upos = {d: i for i, d in enumerate(U)}
    pos = np.array([upos[o[0]] for o in obs], dtype=np.int64)
    mm = np.array([o[1] for o in obs])
    gg = np.array([o[2] for o in obs])
    yy = np.array([o[3] for o in obs])
    out["d"] = float(pool_stat(np.ones((1, len(obs)), dtype=np.int64), mm, gg, yy)[0])
    C = cboot_counts(pos, 0, len(U) - 1)
    out["lo"], out["hi"], out["p"], out["p1"] = ci_p(None if C is None else pool_stat(C, mm, gg, yy))
    half = len(obs) // 2
    w = np.zeros((2, len(obs)), dtype=np.int64)
    w[0, :half] = 1
    w[1, half:] = 1
    h = pool_stat(w, mm, gg, yy)
    out["h1"], out["h2"] = (None if math.isnan(h[0]) else float(h[0])), (None if math.isnan(h[1]) else float(h[1]))
    out["days"] = len(U)
    return out


def pool_stat(C: np.ndarray, mm: np.ndarray, gg: np.ndarray, yy: np.ndarray) -> np.ndarray:
    """C＝(次數 × 事件) 每個事件被算幾次 → 各市場「第一組平均 − 第二組平均」依第一組次數加權平均（某市場某組是 0 次就不算那個市場）。"""
    num = np.zeros(C.shape[0])
    den = np.zeros(C.shape[0])
    for m in sorted(set(mm.tolist())):
        a, b = (mm == m) & (gg == 1), (mm == m) & (gg == 0)
        ca, cb = C[:, a].sum(axis=1), C[:, b].sum(axis=1)
        ok = (ca > 0) & (cb > 0)
        ma = (C[:, a] @ yy[a]) / np.where(ca > 0, ca, 1)
        mb = (C[:, b] @ yy[b]) / np.where(cb > 0, cb, 1)
        num += np.where(ok, ca * (ma - mb), 0.0)
        den += np.where(ok, ca, 0.0)
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def primary(parts: dict) -> dict:
    """主要假說（單尾、Holm）。parts＝{市場: (E5 的事件, 日報酬標準差, 日曆)}。"""
    out: dict = {}
    for h, sp in S.PRIMARY.items():
        r = pooled([(mk, *parts[mk]) for mk in S.POOL if mk in parts], sp["group"])
        r["few"] = bool(r.get("few") or r.get("p1") is None)
        out[h] = r
    adj, rej = holm({h: (None if v["few"] else v["p1"]) for h, v in out.items()})
    for h, v in out.items():
        v["padj"] = adj.get(h)
        v["ok"] = bool(rej.get(h) and (v.get("h1") or 0) > 0 and (v.get("h2") or 0) > 0)
    return out


# ── 研究檔 ────────────────────────────────────────────────────────────────

def _r(x):
    """浮點數留 4 位有效數字。"""
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(x) or math.isinf(x) else float(f"{float(x):.4g}")
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, dict):
        return {a: _r(b) for a, b in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(b) for b in x]
    return x


def inputs_all() -> dict:
    """五個市場的輸入（研究用）。"""
    from . import bubble as BU
    from . import crash as CR
    from . import heatcalc as HC
    from . import heatcalc_us as HU
    from . import heatdata as HD
    from . import heatspec as HS
    from . import heatspec_us as U
    BX = BU.compute()
    B = HC.build()
    I = {"tw": inputs_tw(B, CR.tw_inputs(B=B, BX=BX), BX)}
    BA = HU.build_all()
    for idx in U.INDEX_ORDER:
        with HS.use(U.spec_for(idx)):
            I0 = CR.us_inputs(idx, Bu=BA[idx], BX=BX)
            vol = HD.load(f"us_vol_{idx}") if "C7" in S.SIG_MK[idx] else None
            I[idx] = inputs_us(idx, BA[idx], I0, vol, BX)
    return I


def research(I: dict | None = None) -> dict:
    I = I if I is not None else inputs_all()
    M = {mk: market(I[mk]) for mk in S.MARKETS if mk in I}
    P = primary({mk: (event_recs(I[mk], "E5"), M[mk]["sigma"], I[mk]["cal"]) for mk in S.POOL if mk in I})
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "markets": _r(M), "primary": _r(P)}


def save_research(R: dict) -> None:
    RESEARCH.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load_research() -> dict | None:
    try:
        R = json.loads(RESEARCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None


# ── 每天建頁：現在的狀態 ──────────────────────────────────────────────────

def now(I: dict) -> dict:
    """今天（日曆最後一天）：進行中的事件（最近 60 個交易日內的 5 日急跌、還沒結束的「從 60 日高點跌 10%」）與它們的分組、訊號；
    今天離 60 日高點多少；最近一次兩種事件。"""
    mk, cal, px = I["mk"], I["cal"], I["px"]
    T = len(cal)
    out: dict = {"d": cal[-1] if T else None, "active": [], "last": {}}
    if not T:
        return out
    t = T - 1
    h = hi60(px, t)
    out["dd60"] = None if h is None else float(px[t] / h - 1.0)
    e5 = events_e5(px, S.E5_TH[mk])
    segs = e10_segments(px)
    out["last"] = {"E5": cal[e5[-1]] if e5 else None, "E10": cal[segs[-1][0]] if segs else None}
    act = []
    if e5 and t - e5[-1] <= S.SIG_WIN:
        act.append(("E5", e5[-1]))
    if segs and segs[-1][1] is None:
        act.append(("E10", segs[-1][0]))
    for ev, te in act:
        p = peak_of(px, te)
        g, gv = groups_at(I, te)
        lp = p + int(np.nanargmin(px[p:t + 1]))               # 事件前高點到今天的最低收盤
        row = {"ev": ev, "t": cal[te], "p": cal[p], "ppx": float(px[p]), "days": t - te,
               "depth": float(px[te] / px[te - S.E5_DAYS] - 1.0) if ev == "E5" else float(px[te] / px[p] - 1.0),
               "low": cal[lp], "lowdd": float(px[lp] / px[p] - 1.0), "nowdd": float(px[t] / px[p] - 1.0),
               "pos_now": float((px[t] - px[lp]) / (px[p] - px[lp])) if px[p] > px[lp] else None,
               "g": g, "gv": gv, "sig": {}}
        for k in S.SIG_MK[mk]:
            s = first_signal(k, I["sig"], px, te, te + S.SIG_WIN)
            if s == "na":
                row["sig"][k] = {"st": "na"}
            elif s is None:
                left = te + S.SIG_WIN - t
                row["sig"][k] = {"st": "wait", "left": left} if left > 0 else {"st": "none"}
            else:
                row["sig"][k] = {"st": "on", "d": cal[s], "after": s - te}
        row["w10"] = {"st": "on", "d": cal[te + S.WAIT]} if te + S.WAIT <= t else {"st": "wait", "left": te + S.WAIT - t}
        mr = I["sig"].get("mr")                                     # VER 4：融資維持率今天與事件以來最低（只描述）
        if mr is not None and "C9" in S.SIG_MK[mk]:
            seg = np.asarray(mr[te:t + 1], dtype=float)
            ok = np.nonzero(~np.isnan(seg))[0]
            if len(ok):
                j = int(ok[np.argmin(seg[ok])])
                row["mr"] = {"now": float(seg[ok[-1]]), "now_d": cal[te + int(ok[-1])],
                             "min": float(seg[j]), "min_d": cal[te + j]}
        out["active"].append(row)
    if len(out["active"]) == 2 and out["active"][0]["t"] == out["active"][1]["t"]:
        out["active"][0]["also"] = "E10"                       # 同一天同時是兩種事件：只列一次
        out["active"] = out["active"][:1]
    return out
