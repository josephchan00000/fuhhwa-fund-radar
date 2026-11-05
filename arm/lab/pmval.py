"""盤前作戰圖第 3 段驗證（premktspec VER 1；docs/lab_premarket_plan.md 第 11、12 節）。只讀資料分支與 main 已存的資料、不連網。

Q1 預估開盤誤差、Q2 碰到的比例、Q3 價位擋不擋得住（含強度）、Q4 籌碼期貨指標有沒有用；規格在 premktspec，這裡照做。
  run(root) → dict（scripts/run_pmval.py 寫 data/lab/premkt_research.json）
"""
from __future__ import annotations

import gzip
import json
import math
import random
from pathlib import Path

import numpy as np

from . import premktspec as S

ROOT = Path(__file__).resolve().parents[2]


# ── 資料 ──────────────────────────────────────────────────────────────────────

def load_idx(root: Path) -> dict[str, np.ndarray]:
    """資料分支 idx/{年}/{日}.json.gz → {日: 5 秒指數陣列}（第 0 個＝前一天收盤、第 1 個＝09:00:05）。"""
    out = {}
    for f in sorted((Path(root) / "idx").glob("*/*.json.gz")):
        v = json.loads(gzip.decompress(f.read_bytes())).get("v") or []
        if len(v) > 60:
            out[f.name[:10]] = np.cumsum(np.array(v, dtype=np.int64)) / 100.0
    return out


def load_futday(root: Path) -> tuple[dict, dict]:
    """futday → ({日: {契約: [開, 高, 低, 收, 量]}} 日盤, {日: {契約: [...]}} 夜盤（日期＝它前面那段夜盤之後的交易日））。"""
    day, night = {}, {}
    for f in sorted((Path(root) / "futday").glob("*.json.gz")):
        doc = json.loads(gzip.decompress(f.read_bytes()))
        for d, exp, sess, o, h, l, c, v, s, oi in doc["rows"]:
            if c is None:
                continue
            (night if sess == "N" else day).setdefault(d, {})[exp] = [o, h, l, c, v or 0]
    return day, night


def load_oi(root: Path, days: set[str]) -> dict[str, dict]:
    """選擇權日行情 → {日: {"exp", "xd", "k": {履約價: [買權未平倉, 賣權未平倉, 買權價, 賣權價]}}}（到期日晚於那天的最近一批）。"""
    from . import txodata as T
    out: dict[str, dict] = {}
    for f in sorted((Path(root) / "day").glob("*.json.gz")):
        m = f.name[:7]
        if not any(d.startswith(m) for d in days):
            continue
        doc = json.loads(gzip.decompress(f.read_bytes()))
        ci = {c: i for i, c in enumerate(doc["cols"])}
        per: dict[str, dict[str, tuple]] = {}
        for r in doc["rows"]:
            d = r[ci["d"]]
            if d not in days:
                continue
            exp = r[ci["exp"]]
            xd = r[ci["xd"]] or T.exp_date(exp).isoformat()
            if xd <= d:
                continue
            e = per.setdefault(d, {}).setdefault(exp, (xd, {}))
            q = e[1].setdefault(r[ci["k"]], [0, 0, None, None])
            j = 0 if r[ci["cp"]] == "C" else 1
            q[j] = r[ci["oi"]] or 0
            q[2 + j] = r[ci["c"]] or r[ci["s"]]
        for d, exps in per.items():
            exp, (xd, ks) = min(exps.items(), key=lambda kv: kv[1][0])
            out[d] = {"exp": exp, "xd": xd, "k": ks}
    return out


def ivs(root: Path) -> dict[str, float]:
    """每個交易日的價平跨式隱含波動率（txobt.straddle_iv）。"""
    from . import txobt as B
    days, book = B.load_book(root)
    m = B.Mkt(days, book, B.load_close())
    out = {}
    for d in m.days:
        if d >= "2015-10-01":
            v = B.straddle_iv(m, d)
            if v:
                out[d] = v
    return out


def tx1330s() -> dict[str, tuple[str, float]]:
    """main 存的台指期逐筆（最近 30 天）→ {日: (近月契約, 13:30 價格)}（同 premkt._tx1330）。"""
    from . import futdata as F
    out = {}
    for f in sorted((ROOT / "data/lab/fut/tx").glob("*.json.gz")):
        d = f.name[:10]
        ticks = F.load_day(d) or {}
        k = F.near(d, ticks) if ticks else None
        px = next((p for s, p, _, _ in reversed(ticks.get(k) or []) if s <= 13 * 3600 + 30 * 60), None)
        if px is not None:
            out[d] = (k, float(px))
    return out


# ── 小工具 ────────────────────────────────────────────────────────────────────

def first_passage(p: np.ndarray, level: float, side: str, b: float) -> int | None:
    """碰到價位之後先回頭 b（擋住＝1）還是先再穿過 b（沒擋住＝0）；沒碰到或到收盤都沒有＝None（未碰到回 -1）。"""
    hit = np.nonzero(p >= level)[0] if side == "up" else np.nonzero(p <= level)[0]
    if not len(hit):
        return -1
    seg = p[hit[0]:]
    if side == "up":
        back, thru = np.nonzero(seg <= level - b)[0], np.nonzero(seg >= level + b)[0]
    else:
        back, thru = np.nonzero(seg >= level + b)[0], np.nonzero(seg <= level - b)[0]
    ib = back[0] if len(back) else None
    it = thru[0] if len(thru) else None
    if ib is None and it is None:
        return None
    if it is None or (ib is not None and ib < it):
        return 1
    return 0


def rsi(cs: list[float], n: int = 14) -> float | None:
    from .premkt import rsi as R
    return R(cs, n)


def _split(ds: list[str]) -> str:
    s = sorted(ds)
    return s[len(s) // 2] if s else ""


# ── Q1 預估開盤 ──────────────────────────────────────────────────────────────

def night_k(fnight: dict, d: str) -> str:
    """夜盤（交易日期＝d）成交量最大的契約。"""
    return max(fnight[d], key=lambda c: fnight[d][c][4])


def q1(idx: dict, closes: dict, em: dict, fday: dict, fnight: dict, tx1330: dict | None = None) -> dict:
    """tx1330＝{前一天: (近月契約, 台指期 13:30 價格)}（只有存了逐筆的日子）→ 另列 E0。"""
    days = sorted(idx)
    rows, rows0 = [], []
    for prev, d in zip(days[:-1], days[1:]):
        if d < S.NIGHT_FIRST or d not in fnight or prev not in fday or d not in em or prev not in closes:
            continue
        k = night_k(fnight, d)
        if k not in fday[prev]:
            continue
        v = idx[d]
        c0 = closes[prev]
        e1 = c0 + fnight[d][k][3] - fday[prev][k][3]
        rows.append((d, float(v[1]), float(v[60]), e1, c0, em[d]))
        t = (tx1330 or {}).get(prev)
        if t and t[0] in fnight[d]:
            rows0.append((d, float(v[1]), float(v[60]), c0 + fnight[d][t[0]][3] - t[1], c0, em[d], e1))
    if not rows:
        return {"n": 0}

    def stats(est_i, tgt_i, rs=None):
        rs = rows if rs is None else rs
        e = np.array([r[tgt_i] - r[est_i] for r in rs])
        x = np.abs(e) / np.array([r[5] for r in rs])
        return {"med_pts": round(float(np.median(np.abs(e))), 1), "p80_pts": round(float(np.percentile(np.abs(e), 80)), 1),
                "med_em": round(float(np.median(x)), 3), "p80_em": round(float(np.percentile(x, 80)), 3),
                "bias": round(float(np.mean(e)), 1)}
    half = _split([r[0] for r in rows])
    out = {"n": len(rows), "first": rows[0][0], "last": rows[-1][0],
           "E1_open": stats(3, 1), "N_open": stats(4, 1), "E1_o5": stats(3, 2), "N_o5": stats(4, 2)}
    halves = {}
    for nm, sel in (("h1", [r for r in rows if r[0] < half]), ("h2", [r for r in rows if r[0] >= half])):
        a = np.median([abs(r[1] - r[3]) for r in sel])
        b = np.median([abs(r[1] - r[4]) for r in sel])
        halves[nm] = {"E1": round(float(a), 1), "N": round(float(b), 1), "n": len(sel)}
    out["halves"] = halves
    out["use_night"] = (out["E1_open"]["med_pts"] < out["N_open"]["med_pts"]
                        and all(h["E1"] < h["N"] for h in halves.values()))
    if rows0:
        out["E0"] = {"n": len(rows0), "first": rows0[0][0], "last": rows0[-1][0],
                     "E0_open": stats(3, 1, rows0), "E1_open": stats(6, 1, rows0), "N_open": stats(4, 1, rows0)}
    return out


# ── Q2 碰到的比例 ─────────────────────────────────────────────────────────────

def q2(idx: dict, em: dict) -> dict:
    up = {x: [] for x in S.TOUCH_X}
    dn = {x: [] for x in S.TOUCH_X}
    for d, v in idx.items():
        if d not in em:
            continue
        o, p, e = float(v[1]), v[1:], em[d]
        hi, lo = float(p.max()), float(p.min())
        for x in S.TOUCH_X:
            up[x].append(hi >= o + x * e)
            dn[x].append(lo <= o - x * e)
    return {"n": len(up[S.TOUCH_X[0]]), "x": list(S.TOUCH_X),
            "up": [round(sum(up[x]) / len(up[x]), 4) for x in S.TOUCH_X],
            "dn": [round(sum(dn[x]) / len(dn[x]), 4) for x in S.TOUCH_X]}


# ── Q3 價位 ──────────────────────────────────────────────────────────────────

def day_levels(prev: str, d: str, idx: dict, closes: dict, em: dict, oi: dict, fday: dict, fnight: dict) -> list[tuple[str, float]]:
    """d 那天（用 prev 收盤時知道的）全部價位 [(種類, 價位)]。"""
    from . import txocalc as TC
    from .premkt import pivots
    vp = idx[prev]
    h, l = float(vp[1:].max()), float(vp[1:].min())
    c = closes[prev]
    out = [("prev_hi", h), ("prev_lo", l), ("prev_close", c)]
    pv = pivots(h, l, c)
    out += [("pivot_p", pv["P"]), ("pivot_r1", pv["R1"]), ("pivot_s1", pv["S1"]), ("pivot_r2", pv["R2"]), ("pivot_s2", pv["S2"])]
    ks = sorted(k for k in closes if k <= prev)
    cs = [closes[k] for k in ks[-60:]]
    for n, nm in ((5, "ma5"), (20, "ma20"), (60, "ma60")):
        if len(cs) >= n:
            out.append((nm, sum(cs[-n:]) / n))
    if len(cs) >= 20:
        w = cs[-20:]
        m = sum(w) / 20
        sd = (sum((x - m) ** 2 for x in w) / 20) ** 0.5
        out += [("boll_up", m + 2 * sd), ("boll_dn", m - 2 * sd), ("hi20", max(w)), ("lo20", min(w))]
    e = em.get(d)
    ob = oi.get(prev)
    if ob and e:
        band = {k: q for k, q in ob["k"].items() if abs(k - c) <= S.OPT_BAND * e}
        ca = max(((k, q[0]) for k, q in band.items() if k > c), key=lambda t: t[1], default=None)
        pu = max(((k, q[1]) for k, q in band.items() if k < c), key=lambda t: t[1], default=None)
        if ca and ca[1]:
            out.append(("opt_call", float(ca[0])))
        if pu and pu[1]:
            out.append(("opt_put", float(pu[0])))
        px = {k: {"C": (q[2] or 0, q[0]), "P": (q[3] or 0, q[1])} for k, q in ob["k"].items()}
        mp = TC.max_pain(px)
        if mp:
            out.append(("opt_pain", float(mp)))
    if e:
        o = float(idx[d][1])
        k0 = math.floor((o - S.MAX_X * e) / S.ROUND) * S.ROUND
        while k0 <= o + S.MAX_X * e:
            out.append(("round500", float(k0)))
            k0 += S.ROUND
    if d in fnight and prev in fday:
        k = night_k(fnight, d)
        if k in fday[prev]:
            basis = fday[prev][k][3] - c
            out += [("night_hi", fnight[d][k][1] - basis), ("night_lo", fnight[d][k][2] - basis)]
    return out


def _placebo_bins(idx: dict, em: dict) -> dict:
    """同一邊、同樣距離的任意價位在全部日子的結果：{(邊, 格): [1/0, ...]}。"""
    nb = int(round((S.MAX_X - S.MIN_X) / S.BIN)) + 1
    out: dict[tuple, list] = {}
    for d, v in idx.items():
        e = em.get(d)
        if not e:
            continue
        o, p = float(v[1]), v[1:]
        for j in range(nb):
            x = S.MIN_X + j * S.BIN
            for side, lv in (("up", o + x * e), ("dn", o - x * e)):
                r = first_passage(p, lv, side, S.BOUNCE * e)
                if r in (0, 1):
                    out.setdefault((side, j), []).append(r)
    return out


def _bin(x: float) -> int:
    return int(round((x - S.MIN_X) / S.BIN))


def judge_hold(events: list[tuple[str, str, int, int]], bins: dict, rng: random.Random) -> dict:
    """events＝[(日, 邊, 格, 結果 1/0)] → 擋住比例、基準、p、前後兩半。"""
    n = len(events)
    if not n:
        return {"n": 0}
    rate = sum(e[3] for e in events) / n
    base_each = [sum(bins[(s, b)]) / len(bins[(s, b)]) for _, s, b, _ in events]
    base = sum(base_each) / n
    pools = [bins[(s, b)] for _, s, b, _ in events]
    ge = 0
    for _ in range(S.PLACEBO_N):
        r = sum(rng.choice(pl) for pl in pools) / n
        ge += r >= rate
    p = ge / S.PLACEBO_N
    half = _split([e[0] for e in events])
    hh = {}
    for nm, sel in (("h1", [i for i, e in enumerate(events) if e[0] < half]), ("h2", [i for i, e in enumerate(events) if e[0] >= half])):
        if sel:
            hh[nm] = {"n": len(sel), "rate": round(sum(events[i][3] for i in sel) / len(sel), 4),
                      "base": round(sum(base_each[i] for i in sel) / len(sel), 4)}
    ok = (n >= S.MIN_EVENTS and rate - base >= S.EDGE and p <= S.P_MAX and len(hh) == 2
          and all(h["rate"] > h["base"] for h in hh.values()))
    return {"n": n, "rate": round(rate, 4), "base": round(base, 4), "edge": round(rate - base, 4), "p": round(p, 4),
            "halves": hh, "ok": ok}


CAT = {"prev_hi": "price", "prev_lo": "price", "prev_close": "price", "night_hi": "night", "night_lo": "night",
       "pivot_p": "pivot", "pivot_r1": "pivot", "pivot_s1": "pivot", "pivot_r2": "pivot", "pivot_s2": "pivot",
       "ma5": "ma", "ma20": "ma", "ma60": "ma", "boll_up": "ma", "boll_dn": "ma", "hi20": "ma", "lo20": "ma",
       "opt_call": "opt", "opt_put": "opt", "opt_pain": "opt", "round500": "round"}   # 對到 premkt.KINDS（頁面強度＝不同類別數）


def diff_test(a: list[int], b: list[int], g: np.random.Generator) -> float:
    """a 的擋住比例比 b 高，是不是運氣：兩組結果混在一起隨機分組 PLACEBO_N 次，差距 ≥ 實際的比例。"""
    x = np.array(a + b, dtype=float)
    na, real = len(a), np.mean(a) - np.mean(b)
    ge = 0
    for _ in range(S.PLACEBO_N):
        y = g.permutation(x)
        ge += (y[:na].mean() - y[na:].mean()) >= real
    return ge / S.PLACEBO_N


def q3(idx: dict, closes: dict, em: dict, oi: dict, fday: dict, fnight: dict, rng: random.Random) -> dict:
    from .premkt import cluster
    bins = _placebo_bins(idx, em)
    days = sorted(idx)
    ev: dict[str, list] = {k: [] for k in S.LEVEL_KINDS}
    und: dict[str, int] = {k: 0 for k in S.LEVEL_KINDS}
    strength: dict[str, list] = {"1": [], "2": [], "3+": []}
    for prev, d in zip(days[:-1], days[1:]):
        e = em.get(d)
        if not e:
            continue
        v = idx[d]
        o, p = float(v[1]), v[1:]
        lv = day_levels(prev, d, idx, closes, em, oi, fday, fnight)

        def test(price):
            x = abs(price - o) / e
            if not (S.MIN_X <= x <= S.MAX_X):
                return None
            side = "up" if price > o else "dn"
            r = first_passage(p, price, side, S.BOUNCE * e)
            return side, _bin(x), r
        for kind, price in lv:
            t = test(price)
            if not t:
                continue
            side, b, r = t
            if r is None:
                und[kind] += 1
            elif r in (0, 1) and (side, b) in bins:
                ev[kind].append((d, side, b, r))
        for band in cluster([{"px": px, "kind": CAT[k], "name": k} for k, px in lv], o, S.CLUSTER):
            t = test(band["mid"])
            if not t or t[2] not in (0, 1) or (t[0], t[1]) not in bins:
                continue
            n = band["n"]
            strength["1" if n == 1 else "2" if n == 2 else "3+"].append((d, t[0], t[1], t[2]))
    out = {"kinds": {k: {**judge_hold(ev[k], bins, rng), "undecided": und[k]} for k in S.LEVEL_KINDS},
           "strength": {k: judge_hold(v, bins, rng) for k, v in strength.items()}}
    s1, s3 = out["strength"].get("1", {}), out["strength"].get("3+", {})
    if s1.get("n") and s3.get("n"):
        out["strength_p"] = diff_test([e[3] for e in strength["3+"]], [e[3] for e in strength["1"]], np.random.default_rng(S.SEED))
        out["strength_ok"] = bool(s3["rate"] - s1["rate"] >= S.EDGE and out["strength_p"] <= S.P_MAX)
    else:
        out["strength_ok"] = False
    return out


# ── Q4 因素 ──────────────────────────────────────────────────────────────────

def _tercile(hist: list[float], x: float) -> int:
    if len(hist) < S.RANK_N:
        return 0
    w = sorted(hist[-S.RANK_N:])
    lo, hi = w[len(w) // 3], w[2 * len(w) // 3]
    return 1 if x > hi else -1 if x < lo else 0


def factor_states(days: list[str], idx: dict, closes: dict, fday: dict, fnight: dict) -> dict[str, dict[str, int]]:
    """{因素: {目標日: 狀態 ±1}}；狀態用目標日前一天收盤（美股＝目標日清晨）以前的資料。"""
    from . import heatdata as HD
    from .premkt import kd, macd
    futi, opti, pcr, inst, margin, mtxoi = (HD.load(n) or {} for n in ("futi", "opti", "pcr", "inst", "margin", "mtxoi"))
    sox = HD.load("us_px_sox") or {}
    out: dict[str, dict[str, int]] = {k: {} for k in S.FACTORS}
    hist: dict[str, list[float]] = {k: [] for k in ("fx_fut_lvl", "retail", "pcr", "margin")}
    prev_fx = prev_opt = prev_mg = None
    ck = sorted(closes)
    hl: list[tuple[float, float, float]] = []
    for prev, d in zip(days[:-1], days[1:]):
        vp = idx[prev]
        hl.append((float(vp[1:].max()), float(vp[1:].min()), closes[prev]))
        f = futi.get(prev)
        if f and f.get("TX", {}).get("外資"):
            net = f["TX"]["外資"][0] - f["TX"]["外資"][1]
            if prev_fx is not None:
                out["fx_fut_chg"][d] = 1 if net > prev_fx else -1 if net < prev_fx else 0
            out["fx_fut_lvl"][d] = _tercile(hist["fx_fut_lvl"], net)
            hist["fx_fut_lvl"].append(net)
            prev_fx = net
        if f and f.get("MTX") and mtxoi.get(prev):
            r = -sum(a - b for a, b in f["MTX"].values()) / mtxoi[prev]
            out["retail"][d] = _tercile(hist["retail"], r)
            hist["retail"].append(r)
        o = opti.get(prev)
        if o:
            try:
                v = (o["買權"]["外資"][0] - o["買權"]["外資"][1]) - (o["賣權"]["外資"][0] - o["賣權"]["外資"][1])
                if prev_opt is not None:
                    out["fx_opt_chg"][d] = 1 if v > prev_opt else -1 if v < prev_opt else 0
                prev_opt = v
            except (KeyError, IndexError, TypeError):
                pass
        if pcr.get(prev) and pcr[prev][5] is not None:
            out["pcr"][d] = _tercile(hist["pcr"], pcr[prev][5])
            hist["pcr"].append(pcr[prev][5])
        if inst.get(prev) and inst[prev].get("total") is not None:
            t = inst[prev]["total"]
            out["inst"][d] = 1 if t > 0 else -1 if t < 0 else 0
        if margin.get(prev):
            mv = margin[prev][0]
            if prev_mg is not None:
                out["margin"][d] = _tercile(hist["margin"], mv - prev_mg)
                hist["margin"].append(mv - prev_mg)
            prev_mg = mv
        if prev in fday and fday[prev]:
            k = max(fday[prev], key=lambda c: fday[prev][c][4])
            bs = fday[prev][k][3] - closes[prev]
            out["basis"][d] = 1 if bs > 0 else -1 if bs < 0 else 0
        if d >= S.NIGHT_FIRST and d in fnight and prev in fday:
            k = night_k(fnight, d)
            if k in fday[prev]:
                ch = fnight[d][k][3] - fday[prev][k][3]
                out["night"][d] = 1 if ch > 0 else -1 if ch < 0 else 0
        sk = [k for k in sox if k < d]
        if len(sk) >= 2:
            a, b = sox[sk[-1]], sox[sk[-2]]
            if a and b:
                out["sox"][d] = 1 if a > b else -1 if a < b else 0
        cs = [closes[k] for k in ck if k <= prev][-200:]
        r = rsi(cs)
        if r is not None:
            out["rsi"][d] = 1 if r < 30 else -1 if r > 70 else 0
        if len(cs) >= 20:
            out["ma20"][d] = 1 if cs[-1] > sum(cs[-20:]) / 20 else -1
        k_ = kd(hl[-40:])
        if k_:
            out["kd"][d] = 1 if k_[0] > k_[1] else -1
        m = macd(cs)
        if m:
            out["macd"][d] = 1 if m[0] > 0 else -1
    return out


def q4(days: list[str], idx: dict, closes: dict, fday: dict, fnight: dict) -> dict:
    states = factor_states(days, idx, closes, fday, fnight)
    g = np.random.default_rng(S.SEED)
    ret = {}
    for prev, d in zip(days[:-1], days[1:]):
        v = idx[d]
        c1 = float(v[-1])                                   # 收盤＝13:30 的 5 秒指數（規格「共同」）
        ret[d] = {"oc": c1 / float(v[1]) - 1, "cc": c1 / closes[prev] - 1}
    out = {}
    for f, (direction, desc, targets) in S.FACTORS.items():
        st = {d: s for d, s in states[f].items() if s and d in ret}
        res = {"desc": desc, "dir": direction, "n": len(st)}
        for t in targets:
            ds = sorted(st)
            if not ds:
                res[t] = {"n": 0, "ok": False}
                continue
            sig = np.array([direction * st[d] for d in ds], dtype=float)
            r = np.array([ret[d][t] for d in ds])
            score = float(np.mean(sig * r))
            ge = 0
            for _ in range(S.PLACEBO_N):
                ge += float(np.mean(g.permutation(sig) * r)) >= score
            p = ge / S.PLACEBO_N
            half = _split(ds)
            h1 = [i for i, d in enumerate(ds) if d < half]
            h2 = [i for i, d in enumerate(ds) if d >= half]
            hs = [float(np.mean(sig[h] * r[h])) if h else 0.0 for h in (h1, h2)]
            bull = sig > 0
            res[t] = {"n": len(ds), "score_bp": round(score * 1e4, 2), "p": round(p, 4),
                      "h1_bp": round(hs[0] * 1e4, 2), "h2_bp": round(hs[1] * 1e4, 2),
                      "hit": round(float(np.mean(sig * r > 0)), 4),
                      "bull_n": int(bull.sum()), "bull_mean_bp": round(float(r[bull].mean() * 1e4), 2) if bull.any() else None,
                      "bull_up": round(float((r[bull] > 0).mean()), 4) if bull.any() else None,
                      "bear_n": int((~bull).sum()), "bear_mean_bp": round(float(r[~bull].mean() * 1e4), 2) if (~bull).any() else None,
                      "bear_up": round(float((r[~bull] > 0).mean()), 4) if (~bull).any() else None,
                      "ok": len(ds) >= S.MIN_SIGNAL and p <= S.P_MAX and hs[0] > 0 and hs[1] > 0}
        out[f] = res
    return out


# ── 全部 ─────────────────────────────────────────────────────────────────────

def run(root: Path, log=print) -> dict:
    from . import heatbubble as BB
    rng = random.Random(S.SEED)
    idx = {d: v for d, v in load_idx(root).items() if d >= S.IDX_FIRST}
    closes = {k: float(v) for k, v in BB.taiex_daily().items() if v}
    idx = {d: v for d, v in idx.items() if d in closes}
    iv = ivs(root)
    days = sorted(idx)
    em = {}
    for prev, d in zip(days[:-1], days[1:]):
        if iv.get(prev):
            em[d] = closes[prev] * iv[prev] * math.sqrt(1 / S.TRADING_YEAR)
    fday, fnight = load_futday(root)
    oi = load_oi(root, set(days))
    log(f"5 秒指數 {len(days)} 天（{days[0]}～{days[-1]}），有正常波動 {len(em)} 天，期貨日行情 {len(fday)} 天、夜盤 {len(fnight)} 天，"
        f"選擇權未平倉 {len(oi)} 天")
    out = {"ver": S.VER, "spec_fp": S.fingerprint(), "asof": days[-1], "days": len(days), "em_days": len(em)}
    out["q1"] = q1(idx, closes, em, fday, fnight, tx1330s())
    log(f"Q1 完成：{out['q1'].get('n')} 天")
    out["q2"] = q2(idx, em)
    log("Q2 完成")
    out["q3"] = q3(idx, closes, em, oi, fday, fnight, rng)
    log("Q3 完成")
    out["q4"] = q4(days, idx, closes, fday, fnight)
    log("Q4 完成")
    return out
