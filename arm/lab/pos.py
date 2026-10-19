"""部位參考（docs/lab_crash_plan.md 第 18 節；規格 arm/lab/posspec.py）。

研究：TZ=Asia/Taipei python3 scripts/run_pos.py → data/lab/pos_research.json（資料或規格改了才重跑）。
頁面 2026-10-19 拿掉（docs/lab_crash_plan.md 第 20 節）；研究程式留著供之後重做，now() 目前沒有頁面在用。
"""
from __future__ import annotations

import bisect
import json
import math
from datetime import date
from pathlib import Path

import numpy as np

from . import posspec as S

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "lab" / "pos_research.json"


# ── 報酬與波動 ───────────────────────────────────────────────────────────────

def daily_returns(px) -> np.ndarray:
    """收盤 → 日報酬（第 0 天＝0；缺值當天＝0）。"""
    p = np.asarray(px, dtype=float)
    r = np.zeros(len(p))
    ok = np.isfinite(p[1:]) & np.isfinite(p[:-1]) & (p[:-1] > 0)
    r[1:][ok] = p[1:][ok] / p[:-1][ok] - 1.0
    return r


def spx_div(cal: list[str], shiller: dict) -> np.ndarray:
    """S&P 500 每天另加的股利報酬＝當月股利 ÷ 當月價格 ÷ 252（Shiller 月資料；最新月份沒有股利時沿用最後一個比例）。"""
    yl = {m: v[1] / v[0] for m, v in (shiller or {}).items() if v and v[0] and v[1] is not None and len(v) > 1}
    ms = sorted(yl)
    out = np.zeros(len(cal))
    for i, d in enumerate(cal):
        j = bisect.bisect_right(ms, d[:7]) - 1
        if j >= 0:
            out[i] = yl[ms[j]] / 252.0
    return out


def vol20(r: np.ndarray) -> np.ndarray:
    """近 VOL_N 日年化波動（對數報酬標準差 × √252，含當天）；不足 VOL_N 天＝nan。"""
    lr = np.log1p(r)
    T = len(r)
    out = np.full(T, np.nan)
    n = S.VOL_N
    if T < n + 1:
        return out
    c1 = np.concatenate([[0.0], np.cumsum(lr)])
    c2 = np.concatenate([[0.0], np.cumsum(lr * lr)])
    for t in range(n, T):                              # 第 t 天：用第 t−n＋1～t 天的報酬（第 0 天沒有報酬）
        s1 = c1[t + 1] - c1[t + 1 - n]
        s2 = c2[t + 1] - c2[t + 1 - n]
        var = (s2 - s1 * s1 / n) / (n - 1)
        out[t] = math.sqrt(max(var, 0.0) * 252.0)
    return out


def target_vol(v: np.ndarray) -> np.ndarray:
    """目標＝到前一天為止所有有值的近 20 日波動的平均（逐日擴張）；暖身期（第 VOL_WARM 天以前）＝nan。"""
    T = len(v)
    out = np.full(T, np.nan)
    s = n = 0.0
    for t in range(T):
        if t >= S.VOL_WARM and n:
            out[t] = s / n
        if not math.isnan(v[t]):
            s += v[t]
            n += 1
    return out


def r1_pos(v: np.ndarray, tg: np.ndarray) -> np.ndarray:
    out = np.full(len(v), np.nan)
    ok = np.isfinite(v) & np.isfinite(tg) & (v > 0)
    out[ok] = np.minimum(1.0, tg[ok] / v[ok])
    return out


# ── 訊號有效期間 ─────────────────────────────────────────────────────────────

def active_state(T: int, samp, state, monthly: bool = False) -> np.ndarray:
    """狀態型：當天在狀態中；月資料：那個月底起維持到下一個月底前一天（最後一個到最後一天）。"""
    a = np.zeros(T, dtype=bool)
    samp = [int(i) for i in samp]
    for j, i in enumerate(samp):
        if not state[j]:
            continue
        if monthly:
            z = samp[j + 1] if j + 1 < len(samp) else T
            a[i:z] = True
        else:
            a[i] = True
    return a


def active_event(T: int, days, H: int, start: int = 0) -> np.ndarray:
    """事件型：出現那天起 H 個交易日內（第 d～d＋H−1 天）。"""
    a = np.zeros(T, dtype=bool)
    for d in days:
        if d >= start:
            a[d:min(T, d + H)] = True
    return a


def star_ids(rows: list[dict], mk: str) -> dict:
    """訊號總覽研究檔裡這個市場判定為 ★ 的訊號 → {"warn": [...], "buy": [...], "up": [...]}。"""
    out = {"warn": [], "buy": [], "up": []}
    for r in rows:
        if r.get("mk") != mk or r.get("tier") != "good":
            continue
        for d in r.get("dir") or []:
            if d in out:
                out[d].append(r["id"])
    return out


def activity(F: dict, ids: dict) -> dict:
    """{方向: 逐日 bool（任一個 ★ 有效）}＋{方向: {id: 有效天數}}。"""
    from . import sigcat as G
    T = len(F["cal"])
    sd = {s["id"]: s for s in G.signals(F)}
    out = {d: np.zeros(T, dtype=bool) for d in ("warn", "up", "buy")}
    days = {d: {} for d in out}
    for d in ("warn", "up"):
        for k in ids.get(d) or []:
            s = sd.get(k)
            if not s:
                continue
            if s["kind"] == "state":
                a = active_state(T, s["samp"], s["state"], bool(s.get("monthly")))
            else:
                a = active_event(T, s["days"], s["H"], int(s["samp"][0]) if len(s["samp"]) else 0)
            out[d] |= a
            days[d][k] = int(a.sum())
    bd = buy_days(F, ids.get("buy") or [])
    for k, ds in bd.items():
        a = active_event(T, ds, S.BUY_DAYS)
        out["buy"] |= a
        days["buy"][k] = int(a.sum())
    return {"a": out, "days": days}


def buy_days(F: dict, ids: list[str]) -> dict:
    """買點 ★（id＝市場:buy:事件:規則）→ {id: [訊號出現那天…]}（bottom.event_recs 的規則結果 s）。"""
    from . import bottom as BO
    I = F.get("IB")
    out: dict = {}
    if not I or not ids:
        return out
    recs = {}
    for k in ids:
        _, _, ev, rule = k.split(":")
        if ev not in recs:
            recs[ev] = BO.event_recs(I, ev)
        out[k] = sorted({int(r["rules"][rule]["s"]) for r in recs[ev]
                         if (r["rules"].get(rule) or {}).get("s") is not None})
    return out


# ── 目標部位與模擬 ───────────────────────────────────────────────────────────

def targets(p1: np.ndarray, act: dict) -> dict:
    """各版本每天收盤後的目標部位（nan＝暖身期）。"""
    w, b, u = act["warn"], act["buy"], act["up"]
    vw = np.where(w, np.minimum(p1, S.WARN_CAP), p1)
    vwb = np.where(b & np.isfinite(p1), 1.0, vw)
    vwbu = np.where((b | u) & np.isfinite(p1), 1.0, vw)
    full = np.where(np.isfinite(p1), 1.0, np.nan)
    return {"full": full, "v": p1, "vw": vw, "vwb": vwb, "vwbu": vwbu}


def simulate(r: np.ndarray, tgt: np.ndarray, cost: float, s0: int, s1: int | None = None) -> dict:
    """第 s0～s1−1 天：每天先用持有的部位賺當天報酬，再在收盤執行前一天收盤算出的目標（相差 ≥ BAND 才調整，扣成本）。
    起點部位＝100%。→ {"nav": 淨值（第 s0 天收盤後）, "w": 當天收盤後的部位, "pr": 每天報酬, "n_tr": 調整次數}"""
    s1 = len(r) if s1 is None else s1
    w = 1.0
    nav = 1.0
    pend = None
    navs, ws, prs = [], [], []
    ntr = 0
    for t in range(s0, s1):
        v0 = nav
        nav *= 1.0 + w * r[t]
        if pend is not None and not math.isnan(pend) and abs(pend - w) >= S.BAND - 1e-12:
            nav *= 1.0 - abs(pend - w) * cost
            w = float(pend)
            ntr += 1
        pend = tgt[t]
        navs.append(nav)
        ws.append(w)
        prs.append(nav / v0 - 1.0)
    return {"nav": np.array(navs), "w": np.array(ws), "pr": np.array(prs), "n_tr": ntr}


# ── 指標 ─────────────────────────────────────────────────────────────────────

def metrics(nav: np.ndarray, pr: np.ndarray, w: np.ndarray, n_tr: int) -> dict:
    """年化報酬、年化波動、夏普（年化平均日報酬 ÷ 年化波動，不扣無風險利率）、最大回落、最長回落期間（交易日）、平均部位、一年調整幾次。"""
    N = len(nav)
    if N < 2:
        return {}
    yrs = N / 252.0
    cagr = float(nav[-1] ** (1.0 / yrs) - 1.0)
    vol = float(np.std(pr, ddof=1) * math.sqrt(252.0))
    sharpe = float(np.mean(pr) * 252.0 / vol) if vol > 0 else None
    pk = np.maximum.accumulate(np.concatenate([[1.0], nav]))[1:]
    dd = nav / pk - 1.0
    mdd = float(-dd.min())
    longest = run = 0
    for x in dd:
        run = run + 1 if x < -1e-12 else 0
        longest = max(longest, run)
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "mdd": mdd, "dd_days": int(longest), "avg_w": float(np.mean(w)),
            "tr_y": float(n_tr / yrs), "n": N}


def verdict(m: dict, base: dict) -> str:
    if not m or not base:
        return "none"
    if base["mdd"] - m["mdd"] >= S.MDD_GAIN - 1e-12:
        return "better" if base["cagr"] - m["cagr"] < S.CAGR_TOL else "trade"
    return "none"


def bear_rows(cal: list[str], px, s0: int, sims: dict) -> list[dict]:
    """每一段大跌（指數收盤跌 BEAR 以上，多空門檻法則）：起訖、指數跌幅、各版本同一段的淨值變化。"""
    from . import hotdd as HDD
    seg = HDD.declines(cal[s0:], np.asarray(px, dtype=float)[s0:], S.BEAR)
    out = []
    for e in seg:
        row = {"pk": cal[s0 + e["pk"]], "tr": cal[s0 + e["tr"]], "dd": e["dd"], "open": e["open"]}
        for v, sm in sims.items():
            nav = sm["nav"]
            row[v] = float(nav[e["tr"]] / nav[e["pk"]] - 1.0)
        out.append(row)
    return out


def _recent_start(cal: list[str], s0: int) -> int:
    z = date.fromisoformat(cal[-1])
    try:
        a = z.replace(year=z.year - S.RECENT_YEARS).isoformat()
    except ValueError:                                # 2/29
        a = z.replace(year=z.year - S.RECENT_YEARS, day=28).isoformat()
    return max(s0, bisect.bisect_left(cal, a))


def run_market(mk: str, cal: list[str], px, act: dict, extra_r: np.ndarray | None = None, tr_px: dict | None = None) -> dict:
    """一個市場的回測：各版本全期間與近 10 年的指標、判定、每一段大跌、月底淨值（畫圖）、2013 起含息重算（台股）。"""
    r = daily_returns(px)
    if extra_r is not None:
        r = r + extra_r
    v = vol20(daily_returns(px))
    tg = target_vol(v)
    p1 = r1_pos(v, tg)
    T = targets(p1, act)
    ok = np.nonzero(np.isfinite(p1))[0]
    if not len(ok):
        return {}
    s0 = int(ok[0])
    cost = S.COST[mk]
    sims = {k: simulate(r, T[k], cost, s0) for k in S.VERSIONS}
    M = {k: metrics(sm["nav"], sm["pr"], sm["w"], sm["n_tr"]) for k, sm in sims.items()}
    rs = _recent_start(cal, s0)
    simr = {k: simulate(r, T[k], cost, rs) for k in S.VERSIONS}
    MR = {k: metrics(sm["nav"], sm["pr"], sm["w"], sm["n_tr"]) for k, sm in simr.items()}
    out = {"mk": mk, "d0": cal[s0], "d1": cal[-1], "r0": cal[rs], "m": M, "mr": MR,
           "verdict": {k: verdict(M[k], M["full"]) for k in S.VERSIONS if k != "full"},
           "verdict_r": {k: verdict(MR[k], MR["full"]) for k in S.VERSIONS if k != "full"},
           "bears": bear_rows(cal, px, s0, sims),
           "share": {d: float(act[d][s0:].mean()) for d in ("warn", "buy", "up")},
           "curve": _curve(cal, s0, sims)}
    if tr_px:
        a = bisect.bisect_left(cal, S.TR_FROM[mk])
        q = [tr_px.get(d) for d in cal]
        rt = daily_returns([np.nan if x is None else x for x in q])
        st = max(a + 1, s0)
        simt = {k: simulate(rt, T[k], cost, st) for k in S.VERSIONS}
        out["tr"] = {"d0": cal[st], "m": {k: metrics(sm["nav"], sm["pr"], sm["w"], sm["n_tr"]) for k, sm in simt.items()}}
        out["tr"]["verdict"] = {k: verdict(out["tr"]["m"][k], out["tr"]["m"]["full"]) for k in S.VERSIONS if k != "full"}
    return out


def _curve(cal: list[str], s0: int, sims: dict) -> dict:
    """月底淨值（畫圖用）：{"d": [YYYY-MM…], 版本: [淨值…]}。"""
    idx = [i for i in range(s0, len(cal)) if i == len(cal) - 1 or cal[i + 1][:7] != cal[i][:7]]
    out = {"d": [cal[i][:7] for i in idx]}
    for k, sm in sims.items():
        out[k] = [round(float(sm["nav"][i - s0]), 4) for i in idx]
    return out


# ── 研究 ─────────────────────────────────────────────────────────────────────

def research(F: dict | None = None, rows: list[dict] | None = None) -> dict:
    from . import heatdata as HD
    from . import sigcat as G
    F = F if F is not None else G.frames()
    rows = rows if rows is not None else G.research_rows()
    out = {"ver": S.VER, "spec": S.SPEC_DATE, "mk": {}}
    shiller = (HD.load("us_shiller") or {}).get("d") or {}
    trq = {}
    try:
        trq = json.loads((ROOT / "data" / "lab" / "v3_tr.json").read_text(encoding="utf-8")).get("q") or {}
    except (OSError, ValueError):
        pass
    for mk in S.MARKETS:
        f = F.get(mk)
        if not f:
            continue
        ids = star_ids(rows, mk)
        A = activity(f, ids)
        ex = spx_div(f["cal"], shiller) if (mk == "spx" and S.SPX_DIV) else None
        R = run_market(mk, f["cal"], f["px"], A["a"], ex, trq if mk == "tw" else None)
        R["ids"] = ids
        R["days"] = A["days"]
        out["mk"][mk] = R
    return out


def save(R: dict) -> None:
    RES.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load() -> dict | None:
    try:
        R = json.loads(RES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == S.VER else None


# ── 每天：今天的部位參考 ─────────────────────────────────────────────────────

def now(mk: str, cal: list[str], px, on: dict, ids: dict) -> dict | None:
    """今天收盤後的目標部位（下一個交易日收盤調整）：各版本、近 20 日波動與目標、現在有效的 ★ 警示／買點／偏多。
    on＝訊號總覽的「現在有效」（sigcat.now_market）；買點只算出現後 BUY_DAYS 個交易日內。"""
    if not cal:
        return None
    v = vol20(daily_returns(px))
    tg = target_vol(v)
    p1 = r1_pos(v, tg)
    if not np.isfinite(p1[-1]):
        return None
    T = len(cal)
    act = {}
    for d in ("warn", "up"):
        act[d] = sorted(k for k in ids.get(d) or [] if k in on)
    buy = []
    for k in ids.get("buy") or []:
        x = on.get(k)
        if x and x.get("since"):
            i = bisect.bisect_left(cal, x["since"])
            if T - 1 - i < S.BUY_DAYS:
                buy.append(k)
    a = {"warn": np.array([bool(act["warn"])]), "buy": np.array([bool(buy)]), "up": np.array([bool(act["up"])])}
    tgt = {k: float(x[0]) for k, x in targets(np.array([p1[-1]]), a).items()}
    return {"mk": mk, "d": cal[-1], "vol": float(v[-1]), "tgt_vol": float(tg[-1]), "pos": tgt,
            "warn": act["warn"], "buy": buy, "up": act["up"]}
