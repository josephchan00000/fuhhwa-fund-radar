"""大跌中的強落底訊號（sigspec 第 5.5 節，VER 30；docs/lab_thermo_fair_plan.md 第 4～7 節）。

逐年檢查：每年 1 月 1 日只用那時以前走完的窗口挑強的落底型訊號，那一年每個週末「大跌中而且強的亮著」（原本要上頁面的框）
有沒有出現，之後 3 個月怎麼走（research；scripts/run_bottombox.py → data/lab/bottombox_research.json）。
只描述＋規格寫定的判定。VER 31 起框不上頁面（使用者選「併進清單」），VER 32 起清單也不分強弱；結果只在研究紀錄（sigpage.fair_html）。
"""
from __future__ import annotations

import bisect
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import bottom as BO
from . import bottomspec as BS
from . import sigcat as G
from . import sigspec as S
from . import thermocal as TC

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "bottombox_research.json"


# ── 哪些算、多強 ──────────────────────────────────────────────────────────────

def side_of(r: dict) -> str | None:
    """落底型 → 方向（"buy"＝大跌後買點、"up"＝偏多）；不是 → None。r＝研究列或訊號定義（cat、sig、var、H）。"""
    cat = r.get("cat")
    if cat == "buy":
        return "buy"
    if cat in S.BOTTOM_COLD_CATS and r.get("sig") in S.BOTTOM_COLD_SIGS and (r.get("H") or 0) <= S.BOTTOM_H_MAX:
        return "up"
    if cat == "inst" and r.get("sig") in S.BOTTOM_INST_SIGS:
        return "up"
    if cat == "scen" and r.get("var") in S.BOTTOM_SCEN:
        return "up"
    return None


def strong(st: dict | None) -> bool:
    """次數 ≥ N_MIN 而且之後上漲的機率 − 任一天 ≥ BOTTOM_EDGE。"""
    if not st or (st.get("n") or 0) < S.N_MIN or st.get("hit") is None or st.get("base") is None:
        return False
    return round(st["hit"] - st["base"], 9) >= S.BOTTOM_EDGE


# ── 大跌中 ────────────────────────────────────────────────────────────────────

def drop_days(px, mk: str) -> np.ndarray:
    """每一天是不是在大跌中（同 bottom.now）：最近一次 5 日急跌在 SIG_WIN 個交易日內，或「從 60 日高點跌 10%」那一段還沒結束。"""
    px = np.asarray(px, dtype=float)
    T = len(px)
    g = np.zeros(T, dtype=bool)
    for a, b in BO.e10_segments(px):
        g[a:(T if b is None else b)] = True
    for te in BO.events_e5(px, BS.E5_TH[mk]):
        g[te:min(T, te + BS.SIG_WIN + 1)] = True
    return g


def drop_now(px, mk: str) -> dict | None:
    """資料最後一天：不在大跌中 → None；在 → {"dd60": 離 60 日高點多少（負數）, "e5": 5 日急跌那天的位置或 None, "e10": 那一段開始的位置或 None}。"""
    px = np.asarray(px, dtype=float)
    T = len(px)
    if not T:
        return None
    t = T - 1
    e5 = BO.events_e5(px, BS.E5_TH[mk])
    segs = BO.e10_segments(px)
    a5 = e5[-1] if e5 and t - e5[-1] <= BS.SIG_WIN else None
    a10 = segs[-1][0] if segs and segs[-1][1] is None else None
    if a5 is None and a10 is None:
        return None
    h = BO.hi60(px, t)
    return {"dd60": None if h is None else float(px[t] / h - 1.0), "e5": a5, "e10": a10}


def _drop_end(px, mk: str, ev: str, te: int) -> int:
    """事件 te 那一段大跌「還在進行」到哪一天（不含）：5 日急跌＝te＋SIG_WIN＋1 或下一次 5 日急跌；從高點跌 10%＝那一段結束那天。"""
    T = len(px)
    if ev == "E5":
        e5 = BO.events_e5(px, BS.E5_TH[mk])
        nxt = [x for x in e5 if x > te]
        return min(T, te + BS.SIG_WIN + 1, nxt[0] if nxt else T)
    for a, b in BO.e10_segments(px):
        if a == te:
            return T if b is None else b
    return te + 1


def buy_active(sd0: dict, px, mk: str, T: int) -> np.ndarray:
    """大跌後買點一條規則每一天是不是現在有效（同 sigcat.now_market）：出現後不到 H_BUY 個交易日，而且那一段大跌還在進行。"""
    a = np.zeros(T, dtype=bool)
    ends: dict = {}
    for te, b, _, _ in sd0["buys"]:
        s = int(b) - S.LAG
        if te not in ends:
            ends[te] = _drop_end(px, mk, sd0["ev"], int(te))
        e = min(T, s + S.H_BUY, ends[te])
        if e > s >= 0:
            a[s:e] = True
    return a


# ── 研究檔 ────────────────────────────────────────────────────────────────────

_RES: dict = {}


def load() -> dict | None:
    if "R" not in _RES:
        try:
            R = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            R = None
        _RES["R"] = R if R and (R.get("ver") or 0) >= S.BOTTOM_VER else None
    return _RES["R"]


# ── 逐年檢查 ──────────────────────────────────────────────────────────────────

def _grp(mask: np.ndarray, t: np.ndarray, Yu: np.ndarray, Yw: np.ndarray, Yu2: np.ndarray) -> dict:
    """一組週：窗口完整的週數、之後 3 個月上漲比例、大回撤比例；之後 1 個月上漲比例（窗口完整的另算）。"""
    tt = t[mask]
    u, w, u2 = Yu[tt], Yw[tt], Yu2[tt]
    ok, ok2 = ~np.isnan(u) & ~np.isnan(w), ~np.isnan(u2)
    return {"n": int(ok.sum()), "up": float(u[ok].mean()) if ok.any() else None,
            "dd": float(w[ok].mean()) if ok.any() else None,
            "n1": int(ok2.sum()), "up1": float(u2[ok2].mean()) if ok2.any() else None}


def verdict(box: dict, drop: dict, ep: int) -> str:
    """few＝段數 < BOTTOM_MIN_EP；ok＝上漲比例比大跌中全部週高 BOTTOM_GAIN 以上、大回撤比例不比它高；no＝其餘。"""
    if ep < S.BOTTOM_MIN_EP or box["up"] is None or drop["up"] is None:
        return "few"
    if round(box["up"] - drop["up"], 9) >= S.BOTTOM_GAIN and box["dd"] <= drop["dd"]:
        return "ok"
    return "no"


def market(F: dict) -> dict:
    """一個市場的逐年檢查（第 5.5 節）。"""
    mk, cal = F["mk"], F["cal"]
    px = np.asarray(F["px"], dtype=float)
    T = len(cal)
    we = np.asarray(F["we"], dtype=np.int64)
    sds = [sd for sd in G.signals(F) if side_of(sd) == "up"]
    _, bsd = G.buy_signals(F)
    for sd0 in bsd:
        sd0["cat"] = "buy"
    allsd = sds + list(bsd)
    acts = [TC.active(sd, T, int(sd["H"])) for sd in sds] + [buy_active(sd0, px, mk, T) for sd0 in bsd]
    Ys: dict = {}
    for sd in allsd:
        H = int(sd["H"])
        if H not in Ys:
            Ys[H] = G.outcomes(px, H, G.warn_th(mk, H))
    gate = drop_days(px, mk)
    Yu, Yw, _ = G.outcomes(px, S.BOTTOM_CHK_H, G.warn_th(mk, S.BOTTOM_CHK_H))
    Yu2 = G.outcomes(px, S.BOTTOM_CHK_H2, G.warn_th(mk, S.BOTTOM_CHK_H2))[0]
    y0, y1 = TC.first_year(cal), int(cal[-1][:4])
    tw, bw, years, now_strong = [], [], [], []
    for yr in range(y0, y1 + 1):
        cut = bisect.bisect_left(cal, f"{yr}-01-01")
        wk = we[(we >= cut) & (we < bisect.bisect_left(cal, f"{yr + 1}-01-01"))]
        picked = []
        for i, sd in enumerate(allsd):
            Rb = TC.stats_before(sd, cut, Ys[int(sd["H"])], int(sd["H"]))
            if Rb is not None and strong(Rb.get("up")):
                picked.append(i)
        if yr == y1:
            now_strong = [allsd[i]["id"] for i in picked]
        if not len(wk):
            continue
        on = np.zeros(len(wk), dtype=bool)
        for i in picked:
            on |= acts[i][wk]
        box = on & gate[wk]
        tw += [int(t) for t in wk]
        bw += [bool(x) for x in box]
        years.append([yr, len(picked), int(box.sum())])
    t = np.asarray(tw, dtype=np.int64)
    b = np.asarray(bw, dtype=bool)
    g = gate[t] if len(t) else np.zeros(0, dtype=bool)
    ep = int(sum(1 for j in range(len(b)) if b[j] and (j == 0 or not b[j - 1])))
    res = {"box": _grp(b, t, Yu, Yw, Yu2), "drop": _grp(g, t, Yu, Yw, Yu2), "drop_nobox": _grp(g & ~b, t, Yu, Yw, Yu2),
           "all": _grp(np.ones(len(t), dtype=bool), t, Yu, Yw, Yu2)}
    first = next((tw[j] for j in range(len(b)) if b[j]), None)
    return {"y0": y0, "weeks": [cal[int(x)] for x in (t[0], t[-1])] if len(t) else None, "th": G.warn_th(mk, S.BOTTOM_CHK_H),
            **res, "ep": ep, "v": verdict(res["box"], res["drop"], ep), "first": None if first is None else cal[first],
            "years": years, "strong_now": now_strong,
            "box_weeks": [cal[int(x)] for x, y in zip(t, b) if y]}


def research(F: dict | None = None) -> dict:
    F = F if F is not None else G.frames()
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": {mk: F[mk]["cal"][-1] for mk in F}, "mk": {mk: G._r(market(F[mk])) for mk in S.MARKETS if mk in F}}


def save(R: dict, path: Path | None = None) -> None:
    path = OUT if path is None else path
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(path)
    _RES.pop("R", None)
