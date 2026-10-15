"""回測 v3：各策略套進新引擎（docs/backtest_v3_plan.md 第 5、7 節）。

第一步用現有資料：五年日線（大型股）、兩年日線（短期反轉）；不含股利（上櫃除權息回補後改含息）。
中型股要等下市公司價格與歷史發行股數回補（第 7 節步驟 3），之後同一套函式直接換範圍 "M"。
"""
from __future__ import annotations

import math
import statistics

from . import bt3
from . import packtest as PT

EDGES = ["2021-10-01", "2024-01-01"]          # 分期（資料拉長到 2014 後改成三段）


# ── 共用：形成日 × 分數 → 名單 → 帳戶 ──────────────────────────────────

def rows_at(P, E, b: str, codes, forms: list[int], score) -> list[tuple]:
    """→ [(t, x|None, {代號: 分數})]；x＝下一個形成日（最後一期 None＝本期名單）。"""
    cs = set(codes)
    out = []
    for k, t in enumerate(forms):
        x = forms[k + 1] if k + 1 < len(forms) else None
        sc = {}
        for c in E(t, b):
            if c in cs:
                v = score(c, t)
                if v is not None:
                    sc[c] = v
        out.append((t, x, sc))
    return out


def pick(rows, top: float, nmin: int, asc: bool = False, umin: int | None = None) -> list[tuple]:
    out = []
    for t, x, sc in rows:
        if len(sc) < (umin or nmin):
            continue
        n = max(nmin, math.ceil(top * len(sc)))
        out.append((t, x, sorted(sc, key=lambda c: (sc[c] if asc else -sc[c], c))[:n]))
    return out


def _ew(P, b, rows, pk):
    ok = {t for t, _, _ in pk}
    return bt3.account(P, [(t, x, sorted(sc)) for t, x, sc in rows if t in ok], b, mult=0, limit=False)


def xe_mean(P, b, rows, top, nmin, asc=False, umin=None) -> float | None:
    """參數鄰近用：只算選股平均（扣成本後對同一批股票等權，%）。"""
    done = [r for r in rows if r[1] is not None]
    pk = pick(done, top, nmin, asc, umin)
    U = bt3.vs_ew(bt3.account(P, pk, b), _ew(P, b, done, pk))
    xs = [u["xe"] for u in U if u.get("xe") is not None]
    return statistics.mean(xs) if xs else None


def evaluate(P, b: str, rows, *, top: float, nmin: int, asc: bool = False, umin: int | None = None,
             event: bool = False, nb: dict | None = None, edges=EDGES) -> dict:
    done = [r for r in rows if r[1] is not None]
    pk = pick(done, top, nmin, asc, umin)
    acc = bt3.account(P, pk, b)
    ew = _ew(P, b, done, pk)
    U = bt3.vs_ew(acc, ew)
    U2 = bt3.vs_ew(bt3.account(P, pk, b, mult=2), ew)
    x2s = [u["xe"] for u in U2 if u.get("xe") is not None]
    sel = bt3.sel_stats(U)
    pay = bt3.payoff(U)
    fac = bt3.quint(P, done, asc=asc)
    x2 = statistics.mean(x2s) if x2s else None
    now = None
    if rows and rows[-1][1] is None:
        cur = pick([rows[-1]], top, nmin, asc, umin)
        if cur:
            now = {"d": P.cal[rows[-1][0]], "picks": cur[0][2], "n_uni": len(rows[-1][2])}
    au = acc["units"]
    return {"b": b, "sel": sel, "pay": pay, "x2": x2, "nb": nb,
            "grade": bt3.grade3(sel, pay, x2, nb, event=event),
            "fac": {k: v for k, v in fac.items() if k != "per"},
            "fac_sub": bt3.subperiods(fac.get("per") or [], edges) if fac.get("n") else [],
            "sel_sub": bt3.subperiods(U, edges, "xe"),
            "acc": bt3.curve_stats(acc["curve"], P.cal), "ew": bt3.curve_stats(ew["curve"], P.cal),
            "lim": sum(u["lim"] for u in au), "lock": sum(u["lock"] for u in au),
            "to": statistics.mean(u["to"] for u in au if u.get("to") is not None) if au else None,
            "cost": statistics.mean(u["cost"] for u in au if u.get("cost") is not None) if au else None,
            "units": U, "now": now}


# ── 各策略的形成日與分數（主規格同 packtest.P1–P7，回測前寫定） ─────────────────

def p1_rows(P, E, b, codes, look=126, skip=21):
    forms = [t for t in PT._month_ends(P.cal) if t >= look]
    return rows_at(P, E, b, codes, forms, PT._mom(P, look, skip))


def p4_rows(P, E, b, codes, eps, look=126, skip=21, ep_max=0.25):
    forms = [t for t in PT._month_ends(P.cal) if t >= look]
    mom = PT._mom(P, look, skip)
    cs = set(codes) & set(eps)
    out = []
    for k, t in enumerate(forms):
        x = forms[k + 1] if k + 1 < len(forms) else None
        ep, mm = {}, {}
        for c in E(t, b):
            if c not in cs:
                continue
            px = P.s[c]["c"][t]
            e = PT._ttm_cached(P, eps, c, P.cal[t])
            m = mom(c, t)
            if px and e is not None and m is not None and e / px <= ep_max:
                ep[c], mm[c] = e / px, m
        pr = lambda d: {c: (i + 1) / len(d) for i, c in enumerate(sorted(d, key=lambda c: (d[c], c)))}
        ra, rb = pr(ep), pr(mm)
        out.append((t, x, {c: (ra[c] + rb[c]) / 2 for c in ra}))
    return out


def p5_rows(P, E, b, codes, start, look=5):
    forms = [t for t in PT._week_ends(P.cal) if P.cal[t] >= start and t >= look]

    def f(c, t):
        cs = P.s[c]["c"]
        a, z = cs[t - look], cs[t]
        return z / a - 1 if a and z else None
    return rows_at(P, E, b, codes, forms, f)


def p3_rows(P, E, b, codes, eps, hold=60):
    """每個法定期限一次：期限次一交易日開盤買、持有 hold 個交易日（期與期之間持有現金）。"""
    cs = set(codes) & set(eps)
    out = []
    for q in sorted({q for e in eps.values() for q in e}):
        dl = PT.deadline(q)
        j = next((i for i, d in enumerate(P.cal) if d > dl), None)
        if j is None:
            continue
        t = j - 1
        x = j + hold - 1
        sc = {}
        for c in E(t, b):
            if c in cs:
                v = PT._sue_cached(P, eps, c, q)
                if v is not None:
                    sc[c] = v
        out.append((t, x if x < P.T else None, sc))
    return out


def p7_rows(P, E, b, codes, rev, win=12, mn=6):
    fm = PT.rev_forms(P.cal)
    ym = dict(fm)
    cache: dict = {}

    def f(c, t):
        k = (c, ym[t])
        if k not in cache:
            cache[k] = PT.sur(rev.get(c) or {}, ym[t], win, mn)
        return cache[k]
    return rows_at(P, E, b, PT.non_fin(codes), [t for t, _ in fm], f)


# ── 逐筆交易型（趨勢突破 P2、既有策略） ────────────────────────────────

def trades_eval(P, units: list[dict], U2: list[dict], EWb: dict, b: str, *, nb: dict | None = None,
                event: bool = False, edges=EDGES, slots: int | None = 8) -> dict:
    """逐筆（或事件型每次一籃）→ 選股、報酬型態、評級；slots＝資金帳戶格數（事件型一籃一單位時不做帳戶）。"""
    sel = bt3.sel_stats(units, trades=True)
    x2s = [u["xe"] for u in U2 if u.get("xe") is not None]
    x2 = statistics.mean(x2s) if x2s else None
    pay = bt3.payoff(units)
    out = {"b": b, "sel": sel, "pay": pay, "x2": x2, "nb": nb, "grade": bt3.grade3(sel, pay, x2, nb, event=event),
           "sel_sub": bt3.subperiods(units, edges, "xe"), "units": units}
    if slots:
        sl = bt3.slots(P, units, n=slots)
        I = EWb[b][0]
        out.update({"acc": bt3.curve_stats(sl["curve"], P.cal),
                    "ew": bt3.curve_stats([(i, I[i]) for i, _ in sl["curve"] if I[i]], P.cal),
                    "taken": sl["taken"], "skipped": sl["skipped"]})
    return out


def p2_eval(P, longc, EWb, idx, io, with_grid=True) -> dict:
    TP = PT._Tpl(P, longc)
    EW_old = PT.ew_index(P, longc, PT.CAP_L)

    def units(spec, mult=1.0):
        sg = PT.p2_signals(TP, spec)
        return bt3.trade_units(PT.p2_trades(TP, sg, idx, io, EW_old, spec), P, EWb, b_fix="L", mult=mult)
    U = units(PT.P2)
    U2 = units(PT.P2, 2.0)
    nb = None
    if with_grid:
        def g(stop, vol):
            xs = [u["xe"] for u in units({**PT.P2, "stop": stop, "vol": vol}) if u.get("xe") is not None]
            return statistics.mean(xs) if xs else None
        nb = PT.grid(g, (0.06, 0.08, 0.10), (1.25, 1.5, 2.0), ("停損", "突破量倍數"))
    return trades_eval(P, U, U2, EWb, "L", nb=nb)


# ── 總表 ─────────────────────────────────────────────────────────────

def run(DL, *, with_grid: bool = True, existing: dict | None = None) -> dict:
    """第一步：P1–P5、P7（有資料時）、P2 用新引擎（大型股）；existing＝analyze.run() 的結果時，另算既有策略
    （共識加碼、臺灣50 提前卡位、長線）在新成本與「對同一批股票」下的成績。"""
    from .collect import yh_codes, yhl_codes
    iss = DL.issued()
    stock = lambda c: len(c) == 4 and c.isdigit() and not c.startswith("00")
    longc = [c for c in yhl_codes() if stock(c)]
    allc = [c for c in yh_codes() if stock(c)]
    P = PT.Px(DL, allc, iss)
    longc = [c for c in longc if c in P.s]
    E = bt3.Elig(P)
    EWb = {b: bt3.ew_index(P, E, b) for b in bt3.BUCKET}
    idx, io = DL.taiex(), DL.taiex_open()
    eps = PT.load_eps()
    out: dict = {"meta": {"d0": DL.cal[0], "d1": DL.cal[-1], "n_long": len(longc), "n_all": len(P.codes)}}
    G = PT.grid
    b = "L"

    r1 = p1_rows(P, E, b, longc)
    nb1 = G(lambda look, top: xe_mean(P, b, p1_rows(P, E, b, longc, look), top, 10), (105, 126, 147),
            (0.05, 0.10, 0.20), ("排序期間（交易日）", "買進比例")) if with_grid else None
    out["p1"] = evaluate(P, b, r1, top=0.10, nmin=10, nb=nb1)

    r4 = p4_rows(P, E, b, longc, eps)
    nb4 = G(lambda look, top: xe_mean(P, b, p4_rows(P, E, b, longc, eps, look), top, 10), (105, 126, 147),
            (0.05, 0.10, 0.20), ("動能期間（交易日）", "買進比例")) if with_grid else None
    out["p4"] = evaluate(P, b, r4, top=0.10, nmin=10, nb=nb4)

    r3 = p3_rows(P, E, b, longc, eps)
    nb3 = G(lambda top, hold: xe_mean(P, b, p3_rows(P, E, b, longc, eps, hold), top, 10, umin=20), (0.10, 0.20, 0.30),
            (40, 60, 80), ("買進比例", "持有天數")) if with_grid else None
    out["p3"] = evaluate(P, b, r3, top=0.20, nmin=10, umin=20, event=True, nb=nb3)

    start = min((min(DL.yh[c]) for c in allc if c in DL.yh and c not in set(longc)), default=DL.cal[0])
    start = DL.cal[min(DL.ix.get(start, 0) + 10, DL.T - 1)] if start in DL.ix else start
    r5 = p5_rows(P, E, b, allc, start)
    nb5 = G(lambda look, top: xe_mean(P, b, p5_rows(P, E, b, allc, start, look), top, 10, asc=True), (3, 5, 10),
            (0.05, 0.10, 0.20), ("排序天數", "買進比例")) if with_grid else None
    out["p5"] = evaluate(P, b, r5, top=0.10, nmin=10, asc=True, nb=nb5)

    rv = PT.load_rev()
    months = sorted({ym for r in rv.values() for ym in r})
    out["meta"]["rev_m"] = len(months)
    if len(months) >= 30:
        r7 = p7_rows(P, E, b, longc, rv)
        nb7 = G(lambda win, top: xe_mean(P, b, p7_rows(P, E, b, longc, rv, win), top, 10), (9, 12, 18),
                (0.05, 0.10, 0.20), ("標準差期間（月）", "買進比例")) if with_grid else None
        out["p7"] = evaluate(P, b, r7, top=0.10, nmin=10, nb=nb7)

    out["p2"] = p2_eval(P, longc, EWb, idx, io, with_grid)

    if existing:
        out.update(existing_eval(P, EWb, existing))
    return out


def existing_eval(P, EWb, d: dict) -> dict:
    """既有策略的樣本內交易 → 新成本、對同一批股票（依訊號日市值分大型／中型）。參數鄰近沿用舊口徑另列。"""
    out = {}
    st = {s.get("key"): s for s in (d.get("strat") or {}).get("list") or []}
    s1 = st.get("s1")
    if s1:
        U = bt3.trade_units(s1.get("ins") or [], P, EWb)
        U2 = bt3.trade_units(s1.get("ins") or [], P, EWb, mult=2)
        out["s1"] = {**_mixed(P, U, U2, EWb), "nb_old": (s1.get("score") or {}).get("nb")}
    s3 = st.get("s3")
    if s3:
        ver = next((v for v in s3.get("vers") or [] if (v.get("name") or "").startswith("提前卡位")), None)
        if ver:
            U = tw50_units(ver.get("ins") or [], P, EWb)
            U2 = tw50_units(ver.get("ins") or [], P, EWb, mult=2)
            ev = _by_review(U)
            ev2 = _by_review(U2)
            out["s3e"] = {**trades_eval(P, ev, ev2, EWb, "L", event=True, slots=None), "trades": len(U),
                          "nb_old": (ver.get("score") or {}).get("nb")}
    s5 = ((d.get("grow") or {}).get("s5") or {})
    if s5.get("ins"):
        U, U2 = s5_units(s5["ins"], P), s5_units(s5["ins"], P, mult=2)
        out["s5"] = {**_mixed(P, U, U2, EWb), "nb_old": (s5.get("score") or {}).get("nb")}
    return out


def _mixed(P, U, U2, EWb):
    """大型、中型混合的逐筆交易：整體評一次，另列各範圍筆數。"""
    r = trades_eval(P, U, U2, EWb, "L")
    r["by_b"] = {b: sum(1 for u in U if u["b"] == b) for b in bt3.BUCKET}
    return r


def tw50_units(trs: list[dict], P, EWb: dict, mult: float = 1.0) -> list[dict]:
    """臺灣50 版本交易有 ent（進場日開盤）與 out（出場日）；「開盤出」的以開盤價計。"""
    ix = {d: i for i, d in enumerate(P.cal)}
    I, IO = EWb["L"]
    out = []
    for tr in trs:
        if tr.get("st") != "closed" or tr.get("r") is None or tr.get("ent") not in ix or tr.get("out") not in ix:
            continue
        j, x = ix[tr["ent"]], ix[tr["out"]]
        at_open = "開盤出" in (tr.get("why") or "")
        r = tr["r"] + 0.585 - bt3.rt_cost("L", mult) * 100
        e = ((IO[x] if at_open else I[x]) / IO[j] - 1) * 100 if (IO[x] if at_open else I[x]) and IO[j] else None
        out.append({"d": tr.get("review") or tr["d"], "c": tr["c"], "b": "L", "t": j - 1, "x": x, "hd": max(x - j + 1, 1),
                    "r": r, "xe": None if e is None else r - e})
    return out


def _by_review(U: list[dict]) -> list[dict]:
    """同一次審核的幾檔等額平均＝一個單位（事件型）。"""
    g: dict[str, list] = {}
    for u in U:
        g.setdefault(u["d"], []).append(u)
    out = []
    for d in sorted(g):
        us = g[d]
        xs = [u["xe"] for u in us if u.get("xe") is not None]
        out.append({"d": d, "c": ",".join(u["c"] for u in us), "b": "L", "t": min(u["t"] for u in us),
                    "x": max(u["x"] for u in us), "hd": statistics.mean(u["hd"] for u in us),
                    "r": statistics.mean(u["r"] for u in us), "xe": statistics.mean(xs) if xs else None})
    return out


def s5_units(trs: list[dict], P, mult: float = 1.0) -> list[dict]:
    """長線交易的 xe 已是對長線宇宙等權（同一段時間）→ 只換成本。"""
    ix = {d: i for i, d in enumerate(P.cal)}
    out = []
    for tr in trs:
        if tr.get("st") != "closed" or tr.get("r") is None or tr["d"] not in ix:
            continue
        t = ix[tr["d"]]
        b = bt3.bucket_of(P.cap[tr["c"]][t]) if tr["c"] in P.cap else None
        b = b or "M"
        dc = 0.585 - bt3.rt_cost(b, mult) * 100
        out.append({"d": tr["d"], "c": tr["c"], "b": b, "t": t, "x": t + (tr.get("held") or 0), "hd": tr.get("held") or 1,
                    "r": tr["r"] + dc, "xe": None if tr.get("xe") is None else tr["xe"] + dc})
    return out
