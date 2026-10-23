"""W7：修正飆股——目標改成到期實際報酬、逐年只用過去的資料找規則（reports/W7_plan.md，跑之前寫定；
規格 ../arm/lab/superfixspec.py VER 1）。

    python3 scripts/run_w7.py          → reports/W7_results.json（W7_results.md 另外依結果寫）
    python3 scripts/run_w7.py --smoke  → 只取 150 檔試跑（不寫檔、不記試驗）
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from superstock import combos as CB  # noqa: E402
from superstock import engine as EN  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402

LP.arm()
sys.path.insert(0, str(LP.REPO / "scripts"))
import run_super  # noqa: E402
from arm.lab import superfixspec as X  # noqa: E402
from arm.lab import superx as SX  # noqa: E402

REPORTS = ROOT / "reports"
LOG = print
RULE0, SUBS0, LABELS0 = dict(SX.RULE), tuple(SX.SUBS), dict(SX.LABELS)
G: dict = {}                                       # 給子行程用（fork 共用記憶體）


# ---------------------------------------------------------------------------------------------- 標籤
def lab_names() -> list[str]:
    out = [X.PRIMARY]
    out += [k for k in X.LABELS if k != X.PRIMARY]
    for k, gs in X.NEIGHBORS.items():
        out += [f"{k}_{round(g * 100)}" for g in gs]
    return out + [X.CURRENT]


def lab_def(lab: str) -> tuple[int, float] | None:
    """R 標籤 → (天數, 門檻)；A 照 superx（None）。"""
    if lab == X.CURRENT:
        return None
    base, _, g = lab.partition("_")
    n, g0 = X.LABELS[base]
    return n, (int(g) / 100 if g else g0)


def samples(n_codes: int | None = None) -> list[dict]:
    """run_super.samples()（樣本與特徵不變）；60／120 天的 fr 一次算出，再換成 R 標籤（第 N 天收盤 ≥ ×(1+g)）。"""
    SX.LABELS = {X.CURRENT: LABELS0[X.CURRENT], "_N60": (60, 0.0), "_N120": (120, 0.0)}
    try:
        rows = run_super.samples(n_codes, log=LOG)
    finally:
        SX.LABELS = LABELS0
    names = lab_names()
    for r in rows:
        y = r["y"]
        nb = {60: y.pop("_N60"), 120: y.pop("_N120")}
        for L in names:
            d = lab_def(L)
            if d is None:
                continue
            n, g = d
            b = nb[n]
            y[L] = None if b is None or b.get("fr") is None else {**b, "y": b["fr"] >= g}
    return rows


# ---------------------------------------------------------------------------------------------- 逐年找規則
def mine(task: tuple[str, int]) -> dict:
    lab, y = task
    rows, ix, cal = G["rows"], G["ix"], G["cal"]
    f = X.fold_periods(y)
    n = X.hold_of(lab)
    end = f"{y - 1}-12-31"
    i_last = max(i for i, d in enumerate(cal) if d <= end)
    is_rows = [r for r in rows if SX.in_rng(r["d"], f["is"])]
    val_rows = [r for r in rows if SX.in_rng(r["d"], f["val"]) and ix[r["d"]] + n <= i_last]
    SX._BITS.clear()
    out = {"lab": lab, "y": y, "thr": None, "rules": [], "n_is": len(is_rows), "n_val": len(val_rows),
           "base_is": SX._r(SX.base_rate(is_rows, lab)), "base_val": SX._r(SX.base_rate(val_rows, lab)), "try": []}
    for nm, thr in (("main", {}), ("fallback", X.FALLBACK)):
        SX.RULE = {**RULE0, **thr}
        SX.SUBS = f["subs"]
        try:
            ft = SX.feature_table(is_rows, lab)
            conds = SX.candidate_conds(ft)
            rules, tried = SX.mine_rules(is_rows, lab, conds)
            fin = SX.select_final(rules, val_rows, lab)
        finally:
            SX.RULE, SX.SUBS = RULE0, SUBS0
        out["try"].append({"thr": nm, "conds": len(conds), "tried": tried, "is_pass": len(rules), "final": len(fin)})
        if fin:
            out["thr"] = nm
            out["rules"] = [{"conds": [list(c) for c in r["conds"]], "txt": "、".join(SX.cond_text(c) for c in r["conds"]),
                             "is": r["is"], "val": {k: r["val"].get(k) for k in ("n", "pos", "p", "base", "lift")}}
                            for r in fin]
            break
    SX._BITS.clear()
    return out


# ---------------------------------------------------------------------------------------------- 報酬
def cagr(eq: pd.Series, a: str, b: str) -> float | None:
    """[a, b] 的年化：以 a 之前最後一天當起點（沒有就用期間第一天），兩段接起來＝整段。"""
    eq = eq.dropna()
    pre = eq[eq.index < pd.Timestamp(a)]
    win = eq[(eq.index >= pd.Timestamp(a)) & (eq.index <= pd.Timestamp(b))]
    if len(win) < 2:
        return None
    d0, v0 = (pre.index[-1], pre.iloc[-1]) if len(pre) else (win.index[0], win.iloc[0])
    yrs = (win.index[-1] - d0).days / 365.25
    return float((win.iloc[-1] / v0) ** (1 / yrs) - 1) if yrs > 0 and v0 > 0 else None


def mdd(eq: pd.Series, a: str, b: str) -> float | None:
    eq = eq.dropna()
    pre = eq[eq.index < pd.Timestamp(a)]
    win = eq[(eq.index >= pd.Timestamp(a)) & (eq.index <= pd.Timestamp(b))]
    if not len(win):
        return None
    s = pd.concat([pre.iloc[-1:], win]) if len(pre) else win
    return float((1 - s / s.cummax()).max())


def yearly(eq: pd.Series) -> dict:
    out, prev = {}, None
    eq = eq.dropna()
    for y in sorted(set(eq.index.year)):
        e = eq[eq.index.year == y]
        base = prev if prev is not None else e.iloc[0]
        out[int(y)] = float(e.iloc[-1] / base - 1)
        prev = e.iloc[-1]
    return out


def periods() -> dict:
    return {"all": (X.OOS_START, "2100-12-31"), "h1": X.HALVES[0], "h2": X.HALVES[1]}


def curve_stats(eq: pd.Series) -> dict:
    P = periods()
    return {"cagr": {k: cagr(eq, *v) for k, v in P.items()}, "mdd": {k: mdd(eq, *v) for k, v in P.items()},
            "yearly": yearly(eq[eq.index >= pd.Timestamp(X.OOS_START)])}


def trade_stats(res: EN.Result) -> dict:
    t = res.trades
    if t is None or not len(t):
        return {"n": 0}
    pnl = t["pnl"].sort_values(ascending=False)
    k = max(1, len(pnl) // 10)
    tot = float(pnl.sum())
    best = [{"c": str(r["stock_id"]), "a": str(pd.Timestamp(r["entry_date"]).date()), "b": str(pd.Timestamp(r["exit_date"]).date()),
             "ret": float(r["ret"])} for _, r in t.sort_values("ret", ascending=False).head(10).iterrows()]
    yrs = {}
    for y, g in t.groupby(pd.to_datetime(t["entry_date"]).dt.year):
        yrs[int(y)] = {"n": int(len(g)), "win": float((g["ret"] > 0).mean()), "avg": float(g["ret"].mean()), "med": float(g["ret"].median())}
    return {"n": int(len(t)), "win": float((t["ret"] > 0).mean()), "avg": float(t["ret"].mean()), "med": float(t["ret"].median()),
            "top10": float(pnl.head(k).sum() / tot) if tot else None, "hold": float(t["hold_days"].mean()),
            "exposure": float(res.exposure.mean()), "best": best, "years": yrs}


def signal_stats(m: EN.Market, el: np.ndarray, mask: np.ndarray, H: int) -> dict:
    """每一個訊號隔天開盤到第 H 個交易日收盤（不受 8 檔限制），和同一天合格股票的平均比。"""
    c, o = m.c_ff, m.o
    i0 = int(m.dates.searchsorted(pd.Timestamp(X.OOS_START)))
    base: dict[int, float] = {}
    recs = []
    for i, j in zip(*np.nonzero(mask)):
        if i < i0 or i + H >= m.n or not (o[i + 1, j] == o[i + 1, j]) or o[i + 1, j] <= 0:
            continue
        if i not in base:
            w = el[i]
            with np.errstate(invalid="ignore", divide="ignore"):
                base[i] = float(np.nanmean(c[i + H, w] / c[i, w] - 1))
        recs.append((m.dates[i], float(c[i + H, j] / o[i + 1, j] - 1), base[i]))
    df = pd.DataFrame(recs, columns=["d", "r", "b"])
    out = {}
    for k, (a, b) in periods().items():
        s = df[(df["d"] >= pd.Timestamp(a)) & (df["d"] <= pd.Timestamp(b))]
        out[k] = {"n": int(len(s)), "avg": float(s["r"].mean()) if len(s) else None,
                  "med": float(s["r"].median()) if len(s) else None, "win": float((s["r"] > 0).mean()) if len(s) else None,
                  "base": float(s["b"].mean()) if len(s) else None}
    out["years"] = {int(y): {"n": int(len(g)), "avg": float(g["r"].mean()), "base": float(g["b"].mean())}
                    for y, g in df.groupby(df["d"].dt.year)} if len(df) else {}
    ii = np.nonzero(mask[i0:])[0]
    wk = pd.Series(1, index=m.dates[i0 + ii]).groupby(m.dates[i0 + ii].to_period("W")).size()
    out["weekly"] = {"med": float(wk.median()) if len(wk) else 0.0, "avg": float(wk.mean()) if len(wk) else 0.0,
                     "max": int(wk.max()) if len(wk) else 0, "codes": int(len(set(np.nonzero(mask[i0:])[1])))}
    return out


# ---------------------------------------------------------------------------------------------- 主流程
def main(smoke: bool = False) -> None:
    t0 = time.time()
    n_codes = 150 if smoke else None
    rows = samples(n_codes)
    codes = sorted({r["c"] for r in rows}) if smoke else None
    m, extra = LP.load(codes=codes)
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    fund = LP.fundamentals(extra["cal"], m.stocks)
    el = F["elig"]
    LOG(f"[w7] 面板與特徵 {time.time() - t0:.0f} 秒")
    cal = list(extra["cal"])
    ix = {d: i for i, d in enumerate(cal)}
    assert all(r["d"] in ix for r in rows)
    G.update(rows=rows, ix=ix, cal=cal)
    LOG(f"[w7] 樣本 {len(rows):,} 列，{time.time() - t0:.0f} 秒")

    names = lab_names()
    tasks = [(L, y) for L in names for y in X.FOLDS]
    with mp.get_context("fork").Pool(4) as pool:
        folds = pool.map(mine, tasks, chunksize=1)
    FO = {(f["lab"], f["y"]): f for f in folds}
    for f in folds:
        LOG(f"[w7] {f['lab']:<7} {f['y']}：{f['thr'] or '沒有規則'}，{len(f['rules'])} 條（IS {f['n_is']:,}／VAL {f['n_val']:,}；"
            + "；".join(f"{t['thr']} 條件 {t['conds']} 試 {t['tried']} 樣本內過 {t['is_pass']} 定案 {t['final']}" for t in f["try"]) + "）")
    LOG(f"[w7] 找規則完成 {time.time() - t0:.0f} 秒")

    # 訊號：Y 年的列套 Y 年的規則
    mix = {pd.Timestamp(d): i for i, d in enumerate(m.dates)}
    mi = {d: mix.get(pd.Timestamp(d)) for d in {r["d"] for r in rows}}
    by_year: dict[int, list] = {}
    for r in rows:
        by_year.setdefault(int(r["d"][:4]), []).append(r)
    masks = {}
    for L in names:
        mk = np.zeros(m.c.shape, dtype=bool)
        for y in X.FOLDS:
            preds = [SX.rule_pred([tuple(c) for c in r["conds"]]) for r in FO[(L, y)]["rules"]]
            if not preds:
                continue
            for r in by_year.get(y, []):
                if any(p(r["f"]) for p in preds):
                    i, j = mi[r["d"]], m.col.get(r["c"])
                    if i is not None and j is not None:
                        mk[i, j] = True
        masks[L] = mk & el
    cur = [SX.rule_pred([tuple(c) for c in conds]) for _, conds in SX.live_rules(SX.load_res())]
    a_rows = [(r["c"], r["d"]) for r in rows if any(p(r["f"]) for p in cur)]
    ctx = CB.Ctx(m, F, fund, a_rows, CB.rev_days(cal))
    masks["R1"] = ctx.asig & el
    mf = EN.market_filter(m)

    runs, curves, ents = {}, {}, {}
    for L in names + ["R1"]:
        hold = X.hold_of(L) if L != "R1" else 60
        sig = CB.signals_from(ctx, masks[L], 0.08, f"W7_{L}")
        res = CB.run(ctx, sig, market=False, mf=mf, ma_exit=None, max_hold=hold, start=X.OOS_START, end=None,
                     weight=X.TRADE["weight"], breakeven_r=None)
        if not smoke:
            EN.evaluate(f"W7_{L}_wf" if L != "R1" else "W7_R1_page", "trade", res,
                        {"w7": L, "weight": X.TRADE["weight"], "max_hold": hold, "start": X.OOS_START, "data": "lab-A8",
                         "spec": f"superfixspec VER {X.VER}"}, m, reports_dir=REPORTS, allow_holdout=True)
        curves[L] = res.equity
        ents[L] = {(pd.Timestamp(d), str(c)) for d, c in res.entries}
        runs[L] = {**curve_stats(res.equity), "trades": trade_stats(res), "signals": signal_stats(m, el, masks[L], hold)}
        LOG(f"[w7] 回測 {L}：整段 {runs[L]['cagr']['all'] * 100:.1f}%（{runs[L]['cagr']['h1'] * 100:.1f}／"
            f"{runs[L]['cagr']['h2'] * 100:.1f}）回落 {runs[L]['mdd']['all'] * 100:.0f}%，{runs[L]['trades'].get('n')} 筆")

    # 只描述：新目標買到的股票有幾成也是現行目標／現行頁面規則買到的（同一天同一檔），逐年
    ov = {}
    for k in (X.CURRENT, "R1"):
        yy = {}
        for y in sorted({d.year for d, _ in ents[X.PRIMARY]}):
            e = {x for x in ents[X.PRIMARY] if x[0].year == y}
            yy[y] = [len(e), len(e & ents[k])]
        ov[k] = yy
    if os.environ.get("W7_DUMP"):
        import pickle
        pickle.dump({"curves": curves, "ents": ents}, open(os.environ["W7_DUMP"], "wb"))

    # 對照：合格股票等權（每天再平衡、不含成本）、加權報酬指數
    c_ff = m.c_ff
    r1 = np.zeros(m.c.shape)
    r1[1:] = c_ff[1:] / c_ff[:-1] - 1
    with np.errstate(invalid="ignore"):
        ew_r = np.nanmean(np.where(el[:-1], np.nan_to_num(r1[1:]), np.nan), axis=1)
    ew = pd.Series(np.concatenate([[1.0], np.cumprod(1 + np.nan_to_num(ew_r))]), index=m.dates)
    o0 = pd.Timestamp(X.OOS_START)                     # 和策略一樣以 OOS_START 收盤為起點
    ew, tr = ew[ew.index >= o0], m.index_tr.dropna()
    tr = tr[tr.index >= o0]
    bench = {"EW": curve_stats(ew), "TR": curve_stats(tr)}

    # 判定（只看 PRIMARY）
    P, C, E = runs[X.PRIMARY], runs[X.CURRENT], bench["EW"]
    c1 = all(P["cagr"][h] > C["cagr"][h] for h in ("h1", "h2"))
    c2 = (P["cagr"]["all"] - E["cagr"]["all"] >= X.PASS["ew_pts"] / 100) and all(P["cagr"][h] > E["cagr"][h] for h in ("h1", "h2"))
    c3 = P["mdd"]["all"] <= C["mdd"]["all"] + X.PASS["mdd_extra"] / 100
    verdict = "修好了" if (c1 and c2 and c3) else ("換目標有改善，但沒有穩定比一般股票好" if c1 else "換目標沒有用")
    sign = lambda x: (x > 0) - (x < 0)
    nb = {}
    for k, gs in X.NEIGHBORS.items():
        for g in gs:
            L = f"{k}_{round(g * 100)}"
            R = runs[L]
            same = sign(R["cagr"]["all"] - C["cagr"]["all"]) == sign(P["cagr"]["all"] - C["cagr"]["all"]) and \
                sign(R["cagr"]["all"] - E["cagr"]["all"]) == sign(P["cagr"]["all"] - E["cagr"]["all"])
            nb[L] = same
    out = {"ver": X.VER, "spec": X.SPEC_DATE, "made": time.strftime("%Y-%m-%d"), "last": str(m.dates[-1].date()),
           "folds": folds, "runs": runs, "bench": bench, "overlap": ov,
           "verdict": {"c1": c1, "c2": c2, "c3": c3, "text": verdict, "neighbors": nb}}
    if smoke:
        LOG(json.dumps({k: {"cagr": v["cagr"], "mdd": v["mdd"], "tr": v["trades"], "sg": v["signals"]["all"]}
                        for k, v in runs.items()}, ensure_ascii=False, default=str)[:3000])
        return
    out["sat"] = satellite(curves)
    (REPORTS / "W7_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    report()
    LOG(f"[w7] 判定：{verdict}（①{c1} ②{c2} ③{c3}）；鄰近方向一致 {nb}；{time.time() - t0:.0f} 秒")


def satellite(curves: dict) -> dict:
    """台股 corespec VER 2 的時點，OOS_START 起到財報驚喜回測最後一期：三成放不同的東西（core.scenario 同一套算法）。"""
    from arm.lab import core as CO
    from arm.lab import corespec as S
    M = CO.market_inputs("tw")
    cal, px, tot, rf = M["cal"], M["px"], M["tot"], M["rf"]
    F = CO.families(px, M["inf"], M["lev"], CO.macro_flat("tw", cal), "tw")
    st = CO.stk_sleeve(cal, tot)
    T = len(cal)
    a = next(k for k, d in enumerate(cal) if d >= X.OOS_START)
    b = next(k for k, d in enumerate(cal) if d >= st["b"]) + 1

    def daily(eq: pd.Series) -> np.ndarray:
        """引擎淨值 → cal 上每天的報酬（OOS_START 以前放大盤，用不到）；兩邊日曆對不上的日子，報酬算在淨值再出現的那天。"""
        nav = {str(d.date()): float(v) for d, v in eq.dropna().items()}
        r = np.asarray(tot, dtype=float).copy()
        last = None
        for k in range(T):
            v = nav.get(cal[k])
            if cal[k] >= X.OOS_START:
                r[k] = v / last - 1 if v is not None and last else 0.0
            if v is not None:
                last = v
        return r
    ones = np.ones(T, dtype=bool)
    fx = daily(curves[X.PRIMARY])
    sleeves = {
        "大盤": {},
        "財報驚喜（大型股）": {"sl": st["sl"], "inpos": st["inpos"], "swc": st["swc"], "c_stk": S.COST["tw_stk"]},
        "新飆股（R60 逐年）": {"sl": fx, "inpos": ones, "c_stk": S.COST["tw_stk"]},
        "財報驚喜＋新飆股各半": {"sl": X.SAT_MIX * np.asarray(st["sl"]) + (1 - X.SAT_MIX) * fx, "inpos": ones,
                         "swc": X.SAT_MIX * np.asarray(st["swc"]), "c_stk": S.COST["tw_stk"]},
        "現行飆股（R1）": {"sl": daily(curves["R1"]), "inpos": ones, "c_stk": S.COST["tw_stk"]},
        "現行目標逐年（A）": {"sl": daily(curves[X.CURRENT]), "inpos": ones, "c_stk": S.COST["tw_stk"]},
    }
    out = {"a": cal[a], "b": cal[b - 1], "rows": {}}
    for nm, kw in sleeves.items():
        sc = CO.scenario("w7", "tw", cal, px, tot, rf, F, a, b, S.COST["tw"], **kw)
        out["rows"][nm] = {"plan": {k: sc["plan"].get(k) for k in ("m", "cagr", "mdd", "worst")},
                           "halves": [{"a": h["a"], "b": h["b"], "m": h["plan"]["m"], "hold": h["hold"]["m"]} for h in sc["halves"]],
                           "years": sc["plan"]["years"]}
        out["hold"] = {k: sc["hold"].get(k) for k in ("m", "cagr", "mdd", "worst")}
        out["hold_years"] = sc["hold"]["years"]
    return out


# ---------------------------------------------------------------------------------------------- 報告
NAME = {"R60": "新目標：60 天後還在 +20%（主要）", "R120": "新目標：120 天後還在 +35%（抱 120 天）",
        "R60_15": "鄰近：60 天後 +15%", "R60_25": "鄰近：60 天後 +25%",
        "A": "現行目標（60 天內碰到 +50%），同一套逐年流程", "R1": "參考：現行頁面規則（固定；2019–2022 是它挑規則用過的期間）",
        "EW": "合格股票等權（每天再平衡、不含成本）", "TR": "加權報酬指數（含息）"}
ORDER = ("R60", "R120", "R60_15", "R60_25", "A", "R1")


def _p(x, d=1, sign=False):
    if x is None:
        return "—"
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def report() -> None:
    R = json.loads((REPORTS / "W7_results.json").read_text("utf-8"))
    V, runs, bench = R["verdict"], R["runs"], R["bench"]
    P, C, E = runs[X.PRIMARY], runs[X.CURRENT], bench["EW"]
    ck = lambda b: "✓" if b else "✗"
    L = ["# W7 結果：修正飆股（目標改成到期實際報酬、逐年只用過去資料找規則）", "",
         f"規格 `../arm/lab/superfixspec.py` VER {R['ver']}（計畫 `W7_plan.md`，跑之前 commit）。資料到 {R['last']}；"
         f"表格由 `scripts/run_w7.py` 產生（{R['made']}）。", "",
         "## 判定（只看 60 天 +20%）", "",
         f"**{V['text']}**", "",
         f"- ① 前後兩半都比現行目標（同一套逐年流程）高：{ck(V['c1'])}　"
         f"2019–2022 {_p(P['cagr']['h1'])} 對 {_p(C['cagr']['h1'])}；2023 起 {_p(P['cagr']['h2'])} 對 {_p(C['cagr']['h2'])}",
         f"- ② 整段比合格股票等權多 3 個百分點以上，而且兩半都比等權高：{ck(V['c2'])}　"
         f"整段 {_p(P['cagr']['all'])} 對 {_p(E['cagr']['all'])}；兩半等權 {_p(E['cagr']['h1'])}、{_p(E['cagr']['h2'])}",
         f"- ③ 最大回落沒有比現行目標深超過 5 個百分點：{ck(V['c3'])}　{_p(P['mdd']['all'], 0)} 對 {_p(C['mdd']['all'], 0)}",
         "- 鄰近門檻和主要結果方向一致嗎：" + "、".join(f"{NAME[k].split('：')[1]} {'一致' if v else '不一致（結論對門檻敏感）'}"
                                         for k, v in V["neighbors"].items()), "",
         f"## 1. 成績（{X.OOS_START} 起一次連續跑；8 檔各 12.5%、抱滿就賣、不停損；年化：兩半接起來＝整段）", "",
         "| | 整段年化 | 2019–2022 | 2023 起 | 最大回落 | 筆數 | 賺錢的比例 | 每筆中位數 | 最賺一成占總獲利 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k in ORDER:
        x, t = runs[k], runs[k]["trades"]
        L.append(f"| {NAME[k]} | {_p(x['cagr']['all'])} | {_p(x['cagr']['h1'])} | {_p(x['cagr']['h2'])} | {_p(x['mdd']['all'], 0)} | "
                 f"{t.get('n', 0)} | {_p(t.get('win'), 0)} | {_p(t.get('med'), 1, True)} | {_p(t.get('top10'), 0)} |")
    for k in ("EW", "TR"):
        x = bench[k]
        L.append(f"| {NAME[k]} | {_p(x['cagr']['all'])} | {_p(x['cagr']['h1'])} | {_p(x['cagr']['h2'])} | {_p(x['mdd']['all'], 0)} | | | | |")
    L += ["", "## 2. 訊號本身（不受 8 檔限制：每一個訊號隔天開盤買、抱滿 60 天〔120 天那一列抱 120 天〕）", "",
          "| | 訊號數 | 平均 | 中位數 | 賺錢的比例 | 同一天合格股票平均 | 2019–2022 平均（同一天） | 2023 起 平均（同一天） | 每週幾個（中位／最多） |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k in ORDER:
        s = runs[k]["signals"]
        a, h1, h2, w = s["all"], s["h1"], s["h2"], s["weekly"]
        L.append(f"| {NAME[k]} | {a['n']:,} | {_p(a['avg'], 1, True)} | {_p(a['med'], 1, True)} | {_p(a['win'], 0)} | {_p(a['base'], 1, True)} | "
                 f"{_p(h1['avg'], 1, True)}（{_p(h1['base'], 1, True)}） | {_p(h2['avg'], 1, True)}（{_p(h2['base'], 1, True)}） | "
                 f"{w['med']:.0f}／{w['max']} |")
    L += ["", "### 訊號本身逐年：每一個訊號抱滿之後的平均，減去同一天一般股票的平均（百分點）", "",
          "| 年 | " + " | ".join(NAME[k].split("（")[0] for k in ("R60", "A", "R1")) + " |", "| --- | --- | --- | --- |"]
    for y in sorted({int(y) for k in ("R60", "A", "R1") for y in runs[k]["signals"]["years"]}):
        cells = []
        for k in ("R60", "A", "R1"):
            v = runs[k]["signals"]["years"].get(str(y))
            cells.append(f"{(v['avg'] - v['base']) * 100:+.1f}（{v['n']:,} 個）" if v else "—")
        L.append(f"| {y} | " + " | ".join(cells) + " |")
    ov = R.get("overlap") or {}
    if ov:
        L += ["", "### 新目標買到的股票，有幾筆也是另外兩種做法同一天買到的", "", "| 年 | 新目標買進筆數 | 也被現行目標買到 | 也被現行頁面規則買到 |",
              "| --- | --- | --- | --- |"]
        for y in sorted(ov[X.CURRENT], key=int):
            n, a_ = ov[X.CURRENT][y]
            L.append(f"| {y} | {n} | {a_} | {ov['R1'][y][1]} |")
    L += ["", "### 新目標最賺的 10 筆", "", "| 股票 | 買進 | 賣出 | 報酬 |", "| --- | --- | --- | --- |"]
    for b in runs[X.PRIMARY]["trades"].get("best", []):
        L.append(f"| {b['c']} | {b['a']} | {b['b']} | {_p(b['ret'], 0, True)} |")
    ys = sorted({int(y) for k in ORDER for y in runs[k]["yearly"]})
    L += ["", "## 3. 逐年報酬", "", "| 年 | 60 天 +20% | 120 天 +35% | 現行目標逐年 | 現行頁面規則 | 等權 | 大盤 |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for y in ys:
        g = lambda d: _p(d.get(str(y), d.get(y)), 1, True)
        L.append(f"| {y} | {g(runs['R60']['yearly'])} | {g(runs['R120']['yearly'])} | {g(runs['A']['yearly'])} | "
                 f"{g(runs['R1']['yearly'])} | {g(bench['EW']['yearly'])} | {g(bench['TR']['yearly'])} |")
    L += ["", "## 4. 每一年用的規則", "", "### 60 天 +20%（主要）", "",
          "| 交易年 | 門檻 | 規則（找規則期間的命中率、提升倍數；挑規則期間的命中率、提升倍數） |", "| --- | --- | --- |"]
    FO = {(f["lab"], f["y"]): f for f in R["folds"]}
    for y in X.FOLDS:
        f = FO[(X.PRIMARY, y)]
        rs = "<br>".join(f"{r['txt']}（{_p(r['is']['p'], 0)}、{r['is']['lift']:.1f} 倍；{_p(r['val']['p'], 0)}、{r['val']['lift']:.1f} 倍）"
                         for r in f["rules"]) or "沒有"
        thr = {"main": "主門檻", "fallback": "備用門檻", None: "—"}[f["thr"]]
        L.append(f"| {y} | {thr} | {rs} |")
    L += ["", "### 每一年找到幾條（括號＝用了備用門檻）", "", "| 交易年 | " + " | ".join(NAME[k].split("（")[0] for k in ORDER[:-1]) + " |",
          "| --- | " + " | ".join("---" for _ in ORDER[:-1]) + " |"]
    for y in X.FOLDS:
        cells = []
        for k in ORDER[:-1]:
            f = FO[(k, y)]
            cells.append(f"{len(f['rules'])}{'（備用）' if f['thr'] == 'fallback' else ''}")
        L.append(f"| {y} | " + " | ".join(cells) + " |")
    S = R.get("sat")
    if S:
        L += ["", f"## 5. 放進交易計畫的三成（台股，corespec VER 2 的時點，{S['a']}～{S['b']}；只描述）", "",
              "| 三成放 | 100 萬變 | 年化 | 最慘時跌 | 最差一年 | 前半（一直抱著） | 後半（一直抱著） |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for nm, x in S["rows"].items():
            p, hv = x["plan"], x["halves"]
            L.append(f"| {nm} | {p['m'] * 100:,.0f} 萬 | {_p(p['cagr'])} | {_p(p['mdd'], 0)} | {_p(p['worst'], 1, True)} | "
                     f"{hv[0]['m'] * 100:,.0f} 萬（{hv[0]['hold'] * 100:,.0f} 萬） | {hv[1]['m'] * 100:,.0f} 萬（{hv[1]['hold'] * 100:,.0f} 萬） |")
        h = S["hold"]
        L.append(f"| 一直抱著大盤（全部） | {h['m'] * 100:,.0f} 萬 | {_p(h['cagr'])} | {_p(h['mdd'], 0)} | {_p(h['worst'], 1, True)} | | |")
    (REPORTS / "W7_results.md").write_text("\n".join(L) + "\n", "utf-8")
    LOG("[w7] 寫入 reports/W7_results.md")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        main(smoke="--smoke" in sys.argv)
