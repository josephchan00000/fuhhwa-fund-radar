"""美股飆股研究 C 的主流程（ussxspec VER 1；docs/lab_us_sleeve_plan.md 第 4、9 節）。研究用，不上頁面；scripts/run_ussx.py --books。

books(P)  建樣本（ussxfeat）→ 五本帳逐年找規則（ussxmine）→ 訊號 → 資金帳戶（ussxbook）→ 三成本身、放進交易計畫（core.scenario）
          → 判定 ①～④；另外只描述：小一點的股票、出場比較、位子、M10 抓不抓得到大飆股、一天漲跌超過 2.5 倍的交易、股利預扣。
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import core as CO
from . import corespec as CS
from . import ussxbook as BK
from . import ussxfeat as UF
from . import ussxmine as UM
from . import ussxpanel as UP
from . import ussxspec as X
from . import ussxswap as SW

ROOT = Path(__file__).resolve().parents[2]
G: dict = {}


def _mine(task):
    lab, y = task
    return UM.mine_fold(G["cols"], lab, y, cal=G["cal"])


def mine_all(cols: dict, cal: list[str], books=None, workers: int = 4, log=print) -> dict:
    books = books or list(X.BOOKS)
    tasks = [(b, y) for b in books for y in X.folds(b)]
    G.update(cols=cols, cal=cal)
    t0 = time.time()
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            res = pool.map(_mine, tasks, chunksize=1)
    else:
        res = [_mine(t) for t in tasks]
    G.clear()
    out = {(r["lab"], r["y"]): r for r in res}
    for r in res:
        log(f"[ussx] {r['lab']:<4} {r['y']}：{r['thr'] or '沒有規則'} {len(r['rules'])} 條（IS {r['n_is']:,}／VAL {r['n_val']:,}）")
    log(f"[ussx] 找規則 {len(tasks)} 個（{time.time() - t0:.0f}s）")
    return out


def signals(cols: dict, folds: dict, book: str) -> dict[int, list]:
    """{訊號日: [(代號欄, RS)]}：Y 年的列套 Y 年的規則；RS 高到低、同分依代號。"""
    out: dict[int, list] = {}
    yr = np.array([int(d[:4]) for d in cols["d"]])
    for y in X.folds(book):
        rules = (folds.get((book, y)) or {}).get("rules") or []
        if not rules:
            continue
        idx = np.nonzero(yr == y)[0]
        m = UM.rule_mask(cols, rules, idx)
        for k in idx[m]:
            out.setdefault(int(cols["di"][k]), []).append((int(cols["j"][k]), float(cols["f"]["rs"][k]), cols["c"][k]))
    return {i: [(j, rs) for j, rs, _ in sorted(v, key=lambda x: (-x[1], x[2]))] for i, v in out.items()}


def plan_inputs(P: dict) -> dict:
    """spx、ndx 計畫的輸入（core）＋對到面板日曆的指數每天報酬。"""
    out = {}
    for mk in X.PLANS:
        Q = SW.plan_ctx(mk)
        ix = {d: k for k, d in enumerate(Q["cal"])}
        Q["ix"] = ix
        Q["idle"] = np.array([Q["tot"][ix[d]] if d in ix else 0.0 for d in P["cal"]])
        out[mk] = Q
    return out


def ew_returns(P: dict, el: np.ndarray, Cf: np.ndarray) -> np.ndarray:
    """同一批股票等權：前一天合格的股票、每天再平衡、含息、不算成本（沒有成交的日子報酬 0）。"""
    T = len(P["cal"])
    r = np.zeros(T)
    with np.errstate(invalid="ignore", divide="ignore"):
        d = Cf[1:] / Cf[:-1] - 1
    d = np.where(np.isfinite(d), d, 0.0)
    for t in range(1, T):
        m = el[t - 1]
        r[t] = float(d[t - 1][m].mean()) if m.any() else 0.0
    return r


def plan_level(P: dict, Q: dict, mk: str, eq: np.ndarray, stk: np.ndarray, a: int, b: int, c_stk: float) -> dict:
    """三成換成這本帳（閒置放那個計畫的指數）vs 現在的計畫：同一段期間的 core.scenario。"""
    cal = Q["cal"]
    pa, pb = Q["ix"][P["cal"][a]], Q["ix"][P["cal"][b - 1]] + 1
    sl = np.asarray(Q["tot"], dtype=float).copy()
    inpos = np.zeros(len(cal), dtype=bool)
    r = BK.daily_ret(eq)
    for k in range(a + 1, b):
        q = Q["ix"].get(P["cal"][k])
        if q is not None:
            sl[q] = r[k - a]
            inpos[q] = stk[k - a] > 0
    c = CS.COST["us"]
    cur = CO.scenario("cur", mk, cal, Q["px"], Q["tot"], Q["rf"], Q["F"], pa, pb, c)
    new = CO.scenario("ussx", mk, cal, Q["px"], Q["tot"], Q["rf"], Q["F"], pa, pb, c, sl=sl, inpos=inpos, c_stk=c_stk)
    j = SW.judge(new, cur)
    return {"cur": SW._brief(cur), "new": SW._brief(new), "judge": j}


def big_move_trades(trades: list, Cf: np.ndarray) -> list[bool]:
    out = []
    for j, si, ei, xi, *_ in trades:
        seg = Cf[ei:xi + 1, j]
        with np.errstate(invalid="ignore", divide="ignore"):
            rr = seg[1:] / seg[:-1]
        out.append(bool(np.any((rr >= X.BIG_MOVE) | (rr <= 1 / X.BIG_MOVE))))
    return out


def capture_m10(P: dict, cols: dict, sig: dict, Cf: np.ndarray, a: int, seed: int = X.SEED) -> dict:
    """M10 抓不抓得到大飆股（只描述）：a 以後的週、之後 1,250 個交易日內（到資料最後一天為止）最高收盤 ≥ 10 倍的股票，
    名單在「離之後的最高收盤還有 ≥ CAPTURE_LEFT 倍」的時候有沒有列出；和每週同樣檔數的隨機名單比。"""
    T = len(P["cal"])
    rng = np.random.default_rng(seed)
    di, jj = cols["di"], cols["j"]
    sel = np.nonzero(di >= a)[0]
    big: dict[int, tuple] = {}
    for k in sel:
        i, j = int(di[k]), int(jj[k])
        if j in big:
            continue
        e = min(i + 1250, T - 1, int(P["last"][j]))
        if e <= i:
            continue
        seg = Cf[i + 1:e + 1, j]
        pk = int(np.nanargmax(seg))
        if seg[pk] >= 10 * Cf[i, j]:
            big[j] = (i, i + 1 + pk, float(seg[pk]))
    wk_rows: dict[int, list] = {}
    for k in sel:
        wk_rows.setdefault(int(di[k]), []).append(int(jj[k]))

    def caught(lists: dict[int, list]) -> int:
        hit = 0
        for j, (s, pk_i, pk_v) in big.items():
            for i, js in lists.items():
                if i < pk_i and j in js and pk_v / Cf[i, j] >= X.CAPTURE_LEFT:
                    hit += 1
                    break
        return hit
    mine = {i: [j for j, _ in v] for i, v in sig.items() if i >= a}
    rnd = {}
    for i, v in mine.items():
        pool = wk_rows.get(i) or []
        n = min(len(v), len(pool))
        rnd[i] = list(rng.choice(pool, n, replace=False)) if n else []
    return {"big": len(big), "caught": caught(mine), "random": caught(rnd),
            "names": sorted(P["sym"][j] for j in big)[:200]}


def books(P: dict | None = None, workers: int = 4, log=print, small: bool = True, earn: dict | None = None,
          screen: dict | None = None) -> dict:
    t0 = time.time()
    P = P or UP.load()
    cal = P["cal"]
    T = len(cal)
    earn = earn if earn is not None else UP.earnings()
    cols = UF.build(P, X.LIQ_MIN, earn=earn, screen=screen, workers=workers, log=log)
    el = cols.pop("el")
    D20 = cols.pop("D20")
    Cf = UF.ffill(P["C"])
    log(f"[ussx] 樣本 {len(cols['d']):,} 列（{time.time() - t0:.0f}s）")
    folds = mine_all(cols, cal, workers=workers, log=log)
    PQ = plan_inputs(P)
    ew = ew_returns(P, el, Cf)
    MA = {n: UF.roll_mean(Cf, n) for n in (20, 50, 200)}
    S = UF.ffill(P["CS"].astype(float)) if "CS" in P else None
    DIV = None
    if S is not None:
        with np.errstate(invalid="ignore", divide="ignore"):
            DIV = (Cf[1:] / Cf[:-1]) / (S[1:] / S[:-1]) - 1
        DIV = np.vstack([np.zeros((1, Cf.shape[1])), np.where(np.isfinite(DIV), DIV, 0.0)])
    surv = json.loads((ROOT / "data" / "lab" / "ussx_surv.json").read_text(encoding="utf-8"))
    G_surv = surv.get("G")
    out = {"ver": X.VER, "spec": X.SPEC_DATE, "made": date.today().isoformat(), "last": cal[-1], "rows": int(len(cols["d"])),
           "folds": [folds[k] for k in sorted(folds)], "books": {}, "surv_G": G_surv}

    def engine(book, sig, a, idle, *, c_stk=X.COST["stk"], ex=None, style=None, weight=None, max_pos=None):
        ex = ex or X.exit_of(book)
        style = style or ("fixed" if book in X.FIXED else "trend")
        ma = MA.get(ex.get("ma")) if ex.get("ma") else None
        kw = {}
        if weight:
            kw["weight"], kw["max_weight"] = weight, max(weight, X.TRADE["max_weight"])
        if max_pos:
            kw["max_pos"] = max_pos
        return BK.run(P["O"], Cf, P["C"], P["last"], sig, a, T, idle, ex=ex, style=style, MA=ma, D20=D20, DIV=DIV,
                      c_stk=c_stk, **kw)

    for book in X.BOOKS:
        sig = signals(cols, folds, book)
        a = next(k for k, d in enumerate(cal) if d >= f"{X.first_year(book)}-01-01")
        a = a - 1                                             # 第一個交易年第一天之前的收盤＝起點（第一個訊號隔天才買）
        row: dict = {"a": cal[a], "b": cal[-1], "signals": int(sum(len(v) for v in sig.values())),
                     "weeks": int(sum(1 for i in sig if i >= a))}
        R = {}
        for mk in X.PLANS:
            for ck, c in (("main", X.COST["stk"]), ("alt", X.COST["stk_alt"])):
                R[(mk, ck)] = engine(book, sig, a, PQ[mk]["idle"], c_stk=c)
        spx_idle = PQ["spx"]["idle"]
        for ck in ("main", "alt"):
            r = R[("spx", ck)]
            st = BK.curve_stats(cal, np.concatenate([np.zeros(a), BK.daily_ret(r["eq"])]), a, T)
            row[f"sleeve_{ck}"] = st
        row["spx_tr"] = BK.curve_stats(cal, spx_idle, a, T)
        row["ew"] = BK.curve_stats(cal, ew, a, T)
        row["trades"] = BK.trade_stats(R[("spx", "main")]["trades"], cal)
        row["exposure"] = float(np.mean(R[("spx", "main")]["stk"]))
        bm = big_move_trades(R[("spx", "main")]["trades"], Cf)
        row["big_move"] = {"n": int(sum(bm)), "stats_ex": BK.trade_stats([t for t, f in zip(R[("spx", "main")]["trades"], bm)
                                                                           if not f], cal)}
        for t in row["trades"].get("best", []):
            t["c"] = P["sym"][t.pop("j")]
        dv = R[("spx", "main")]["div"]
        yrs = (date.fromisoformat(cal[-1]) - date.fromisoformat(cal[a])).days / 365.25
        eq0 = R[("spx", "main")]["eq"]
        row["div_drag"] = float(X.WHT * np.sum(dv[1:] / eq0[:-1]) / yrs) if yrs > 0 else None
        Qs = PQ["spx"]
        qa, qb = Qs["ix"][cal[a]], Qs["ix"][cal[-1]] + 1
        pr = np.zeros(len(Qs["px"]))
        pr[1:] = np.asarray(Qs["px"][1:], dtype=float) / np.asarray(Qs["px"][:-1], dtype=float) - 1
        row["div_drag_spx"] = float(X.WHT * np.sum(np.asarray(Qs["tot"])[qa + 1:qb] - pr[qa + 1:qb]) / yrs) if yrs > 0 else None
        row["plan"] = {}
        for mk in X.PLANS:
            for ck, c in (("main", X.COST["stk"]), ("alt", X.COST["stk_alt"])):
                r = R[(mk, ck)]
                row["plan"][f"{mk}_{ck}"] = plan_level(P, PQ[mk], mk, r["eq"], r["stk"], a, T, c)
        # 判定
        def beats(st):
            sp, e = row["spx_tr"], row["ew"]
            ok_sp = st["cagr"] > sp["cagr"] and all(h["cagr"] > hs["cagr"] for h, hs in zip(st["halves"], sp["halves"]))
            ok_ew = st["cagr"] > e["cagr"] and all(h["cagr"] > he["cagr"] for h, he in zip(st["halves"], e["halves"]))
            return {"spx": bool(ok_sp), "ew": bool(ok_ew)}
        v = {"c1": beats(row["sleeve_main"]), "c1_alt": beats(row["sleeve_alt"])}
        v["c2"] = {mk: row["plan"][f"{mk}_main"]["judge"]["pass"] for mk in X.PLANS}
        v["c3"] = {mk: bool(v["c1_alt"]["spx"] and v["c1_alt"]["ew"] and row["plan"][f"{mk}_alt"]["judge"]["pass"])
                   for mk in X.PLANS}
        v["c4"] = bool(G_surv is not None and G_surv * 100 < X.PASS["surv_max"])
        c1 = v["c1"]["spx"] and v["c1"]["ew"]
        v["pass"] = {mk: bool(c1 and v["c2"][mk] and v["c3"][mk] and v["c4"]) for mk in X.PLANS}
        row["verdict"] = v
        # 只描述：出場比較、位子
        alt = {}
        kind = "fixed" if book in X.FIXED else "trend"
        for k, spec in X.ALT_EXITS[kind].items():
            if kind == "fixed":
                r = engine(book, sig, a, spx_idle, ex=spec, style="w8")
            else:
                ex = {**{kk: vv for kk, vv in spec.items() if kk != "max"}, "hold": X.BOOKS[book]["n"]}
                r = engine(book, sig, a, spx_idle, ex=ex, style="trend")
            st = BK.curve_stats(cal, np.concatenate([np.zeros(a), BK.daily_ret(r["eq"])]), a, T)
            alt[k] = {"cagr": st["cagr"], "mdd": st["mdd"], "halves": [h["cagr"] for h in st["halves"]],
                      "n": BK.trade_stats(r["trades"], cal).get("n")}
        row["alt_exits"] = alt
        if book in X.TREND:
            sl = {}
            for n in X.ALT_SLOTS:
                r = engine(book, sig, a, spx_idle, weight=1.0 / n, max_pos=n)
                st = BK.curve_stats(cal, np.concatenate([np.zeros(a), BK.daily_ret(r["eq"])]), a, T)
                sl[str(n)] = {"cagr": st["cagr"], "mdd": st["mdd"], "halves": [h["cagr"] for h in st["halves"]]}
            row["alt_slots"] = sl
        if book == "M10":
            row["capture"] = capture_m10(P, cols, sig, Cf, a)
        out["books"][book] = row
        log(f"[ussx] {book}：三成本身 {row['sleeve_main']['cagr'] * 100:.1f}%（S&P 500 {row['spx_tr']['cagr'] * 100:.1f}%、"
            f"同一批 {row['ew']['cagr'] * 100:.1f}%）；判定 {v['pass']}（{time.time() - t0:.0f}s）")
    if small:
        out["small"] = small_universe(P, PQ, workers, log, t0, earn=earn, screen=screen)
    return out


def small_universe(P, PQ, workers, log, t0, earn=None, screen=None) -> dict:
    """只描述：範圍 SMALL（20 日平均成交值 ≥ SMALL_LIQ）的五本帳（主規格、海外券商成本、閒置放 S&P 500）。"""
    cal = P["cal"]
    T = len(cal)
    cols = UF.build(P, X.SMALL_LIQ, earn=earn, screen=screen, workers=workers, log=log)
    el = cols.pop("el")
    D20 = cols.pop("D20")
    Cf = UF.ffill(P["C"])
    folds = mine_all(cols, cal, workers=workers, log=log)
    ew = ew_returns(P, el, Cf)
    MA200 = UF.roll_mean(Cf, 200)
    out = {"rows": int(len(cols["d"])), "folds": [folds[k] for k in sorted(folds)], "books": {}}
    for book in X.BOOKS:
        sig = signals(cols, folds, book)
        a = next(k for k, d in enumerate(cal) if d >= f"{X.first_year(book)}-01-01") - 1
        ex = X.exit_of(book)
        r = BK.run(P["O"], Cf, P["C"], P["last"], sig, a, T, PQ["spx"]["idle"], ex=ex,
                   style="fixed" if book in X.FIXED else "trend", MA=MA200 if ex.get("ma") else None, D20=D20)
        st = BK.curve_stats(cal, np.concatenate([np.zeros(a), BK.daily_ret(r["eq"])]), a, T)
        out["books"][book] = {"sleeve": st, "ew": BK.curve_stats(cal, ew, a, T), "trades": BK.trade_stats(r["trades"], cal)}
        for t in out["books"][book]["trades"].get("best", []):
            t["c"] = P["sym"][t.pop("j")]
        log(f"[ussx] 小一點的股票 {book}：{st['cagr'] * 100:.1f}%（{time.time() - t0:.0f}s）")
    return out
