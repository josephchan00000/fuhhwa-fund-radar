"""P5（lab 面板先跑）：綜合策略找最優解（規則與挑選程序：reports/P5_plan.md，跑之前寫定）。

三步分開跑，每一步的結果先 commit 再跑下一步：
    .venv/bin/python scripts/run_p5.py --search    84 組 IS／VAL → 族代表 → VAL 關卡 → 入圍 → reports/P5_search.{md,json}、P5_finalists.json
    .venv/bin/python scripts/run_p5.py --robust    入圍者：參數鄰近、成本 ×2、資金規模、隨機選股 1,000 次、DSR → reports/P5_robust.{md,json}
    .venv/bin/python scripts/run_p5.py --holdout   入圍者跑保留期一次 → reports/P5_holdout.json、gate_P5_lab.md
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
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
from superstock import validate as VD  # noqa: E402

REPORTS = ROOT / "reports"
PER = {"IS": ("2014-01-02", "2019-12-31"), "VAL": ("2020-01-02", "2022-12-30")}
HO = ("2023-01-02", "2100-12-31")
KEYS = ("cagr", "excess_cagr", "bench_cagr", "maxdd", "bench_maxdd", "sharpe", "trades", "win_rate", "payoff",
        "expectancy", "avg_hold", "exposure", "y_A_precision", "y_A_base", "y_A_lift", "n_obs", "skew", "kurt", "years")
LOG = print
G: dict = {}                                     # 給隨機選股的子行程用（fork 共用記憶體）


# ---------------------------------------------------------------------------------------------- 共用
def setup() -> dict:
    t0 = time.time()
    m, extra = LP.load()
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    LOG(f"[p5] 面板與特徵 {time.time() - t0:.0f} 秒")
    yA = FT.label(m, 60, 0.5, F["elig"])
    ii, jj = np.nonzero(F["elig"])
    labels = pd.DataFrame({"date": m.dates[ii], "stock_id": np.array(m.stocks)[jj], "y_A": yA[ii, jj]})
    fund = LP.fundamentals(extra["cal"], m.stocks)
    sys.path.insert(0, str(LP.REPO / "scripts"))
    import run_super  # noqa: WPS433
    from arm.lab import superx as SX  # noqa: WPS433

    preds = [SX.rule_pred([tuple(c) for c in conds]) for _, conds in SX.live_rules(SX.load_res())]
    a_rows = [(r["c"], r["d"]) for r in run_super.samples(log=LOG) if any(p(r["f"]) for p in preds)]
    ctx = CB.Ctx(m, F, fund, a_rows, CB.rev_days(extra["cal"]))
    LOG(f"[p5] A 規則訊號 {len(a_rows):,} 個；準備完成 {time.time() - t0:.0f} 秒")
    return {"m": m, "F": F, "ctx": ctx, "labels": labels, "mf": EN.market_filter(m), "t0": t0}


def summarize(mt: dict) -> dict:
    out = {k: mt.get(k) for k in KEYS}
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in out.items()}


def run_one(S: dict, name: str, sig: pd.DataFrame, rng: tuple, *, market: bool, ma_exit, max_hold, stop_pct=0.08,
            base: EN.EngineConfig | None = None, log_trial: bool = True, allow_holdout: bool = False,
            params: dict | None = None, weight: float | None = None,
            breakeven_r: float | None = 2.0) -> tuple[dict, EN.Result]:
    s, e = rng
    res = CB.run(S["ctx"], sig, market=market, mf=S["mf"], ma_exit=ma_exit, max_hold=max_hold, stop_pct=stop_pct,
                 start=s, end=e, base=base, weight=weight, breakeven_r=breakeven_r)
    lab = S["labels"][(S["labels"]["date"] >= pd.Timestamp(s)) & (S["labels"]["date"] <= pd.Timestamp(e))]
    pr = {**(params or {}), "market": market, "ma_exit": ma_exit, "max_hold": max_hold,
          "stop_pct": None if weight else stop_pct, "weight": weight, "breakeven_r": breakeven_r, "data": "lab-A8"}
    if log_trial:
        mt = EN.evaluate(name, "trade", res, pr, S["m"], labels=lab, reports_dir=REPORTS, allow_holdout=allow_holdout)
    else:
        mt = res.metrics(bench=S["m"].index_tr, labels=lab)
    return summarize(mt), res


def spec_of(cfg: str) -> dict:
    f, e, x, k = cfg.split("_")
    return {"fam": f, "entry": e, "exit": x, "mk": k, "market": CB.MARKETS[k], **CB.EXITS[x]}


def yearly(eq: pd.Series) -> dict:
    out, prev = {}, None
    for y in sorted(set(eq.index.year)):
        e = eq[eq.index.year == y]
        base = prev if prev is not None else e.iloc[0]
        out[int(y)] = float(e.iloc[-1] / base - 1)
        prev = e.iloc[-1]
    return out


def _p(x, d=1):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def _f(x, d=2):
    return "—" if x is None else f"{x:.{d}f}"


def cfg_label(cfg: str) -> str:
    f, e, x, k = cfg.split("_")
    return f"{CB.FNAME[f]}｜{CB.ENTRIES[e]}｜{CB.XNAME[x]}｜大盤濾網{'開' if k == 'M1' else '關'}"


# ---------------------------------------------------------------------------------------------- 第 1 步：搜尋
def search(S: dict) -> None:
    rows: dict[str, dict] = {}
    sigs: dict[tuple, pd.DataFrame] = {}
    for f, e, x, k in CB.configs():
        if (f, e) not in sigs:
            sigs[(f, e)] = CB.build_signals(S["ctx"], f, e)
            LOG(f"[p5] 訊號 {f}_{e}：{len(sigs[(f, e)]):,} 個（{time.time() - S['t0']:.0f} 秒）")
        name = CB.cname(f, e, x, k)
        sp = spec_of(name)
        r = {}
        for p, rng in PER.items():
            r[p], _ = run_one(S, f"P5_{name}_{p}", sigs[(f, e)], rng, market=sp["market"], ma_exit=sp["ma_exit"],
                              max_hold=sp["max_hold"], params={"cfg": name, "period": p})
        rows[name] = r
    champ = {}
    for f in CB.FAMILIES:
        ok = [(n, r) for n, r in rows.items() if n.startswith(f + "_") and (r["IS"]["trades"] or 0) >= 100
              and r["IS"]["sharpe"] is not None]
        if ok:
            champ[f] = max(ok, key=lambda t: t[1]["IS"]["sharpe"])[0]

    def gate(n):
        v = rows[n]["VAL"]
        return ((v["trades"] or 0) >= 50 and (v["excess_cagr"] or -1) > 0 and v["maxdd"] is not None
                and v["bench_maxdd"] is not None and v["maxdd"] >= v["bench_maxdd"])
    passed = {f: n for f, n in champ.items() if gate(n)}
    non_a = sorted((n for f, n in passed.items() if f not in CB.A_FAMILIES), key=lambda n: -rows[n]["VAL"]["sharpe"])[:2]
    a_fam = sorted((n for f, n in passed.items() if f in CB.A_FAMILIES), key=lambda n: -rows[n]["VAL"]["sharpe"])[:1]
    fin = non_a + a_fam
    out = {"plan": "reports/P5_plan.md v1", "rows": rows, "champions": champ, "passed": passed, "finalists": fin,
           "signals": {f"{f}_{e}": len(s) for (f, e), s in sigs.items()}}
    (REPORTS / "P5_search.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    (REPORTS / "P5_finalists.json").write_text(json.dumps({"finalists": fin, "asof": time.strftime("%Y-%m-%d")},
                                                          ensure_ascii=False, indent=1), "utf-8")
    L = ["# P5 第 1 步：84 組搜尋（IS 調參、VAL 關卡、入圍）", "",
         "規則：`reports/P5_plan.md` v1（跑之前 commit）。資料：lab 面板（PROGRESS A8）。表格由 `scripts/run_p5.py --search` 產生。", "",
         "## 族代表（IS Sharpe 最高、IS ≥100 筆）與 VAL 關卡", "",
         "| 族 | 代表設定 | IS Sharpe | IS 年化／超額 | IS 筆數 | VAL Sharpe | VAL 年化／超額 | VAL 回落（大盤） | VAL 筆數 | 過關 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for f in CB.FAMILIES:
        n = champ.get(f)
        if not n:
            L.append(f"| {CB.FNAME[f]} | 沒有 IS ≥100 筆的組 | | | | | | | | |")
            continue
        a, v = rows[n]["IS"], rows[n]["VAL"]
        L.append(f"| {CB.FNAME[f]} | {cfg_label(n)} | {_f(a['sharpe'])} | {_p(a['cagr'])}／{_p(a['excess_cagr'])} | {a['trades']} | "
                 f"{_f(v['sharpe'])} | {_p(v['cagr'])}／{_p(v['excess_cagr'])} | {_p(v['maxdd'])}（{_p(v['bench_maxdd'])}） | "
                 f"{v['trades']} | {'✓' if n in passed.values() else '✗'} |")
    L += ["", "入圍：" + ("、".join(cfg_label(n) for n in fin) if fin else "（沒有）"), "",
          "## 全部 84 組", "", "| 設定 | IS Sharpe | IS 年化 | IS 超額 | IS 回落 | IS 筆數 | IS 勝率 | VAL Sharpe | VAL 年化 | VAL 超額 | VAL 回落 | VAL 筆數 | VAL 勝率 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for n, r in rows.items():
        a, v = r["IS"], r["VAL"]
        L.append(f"| {n} | {_f(a['sharpe'])} | {_p(a['cagr'])} | {_p(a['excess_cagr'])} | {_p(a['maxdd'])} | {a['trades']} | "
                 f"{_p(a['win_rate'], 0)} | {_f(v['sharpe'])} | {_p(v['cagr'])} | {_p(v['excess_cagr'])} | {_p(v['maxdd'])} | "
                 f"{v['trades']} | {_p(v['win_rate'], 0)} |")
    (REPORTS / "P5_search.md").write_text("\n".join(L) + "\n", "utf-8")
    LOG(f"[p5] 搜尋完成：族代表 {champ}；過關 {list(passed)}；入圍 {fin}（{time.time() - S['t0']:.0f} 秒）")


# ---------------------------------------------------------------------------------------------- 第 2 步：穩健度
def _rand_worker(seed: int) -> float | None:
    S = G["S"]
    rng = np.random.default_rng(seed)
    sig = CB.random_signals(S["ctx"], G["sig"], rng)
    mt, _ = run_one(S, "random", sig, PER["VAL"], market=G["sp"]["market"], ma_exit=G["sp"]["ma_exit"],
                    max_hold=G["sp"]["max_hold"], log_trial=False)
    return mt["cagr"]


def neighbors(sp: dict) -> list[tuple[float, dict]]:
    """停損 6／8／10% × 出場參數 ×0.67／×1／×1.33（第 3 節第 4 步）。"""
    out = []
    for stop in (0.06, 0.08, 0.10):
        for fac in (0.67, 1.0, 1.33):
            if sp["ma_exit"]:
                kw = {"ma_exit": int(round(sp["ma_exit"] * fac)), "max_hold": sp["max_hold"]}
            else:
                kw = {"ma_exit": None, "max_hold": int(round(sp["max_hold"] * fac))}
            out.append((stop, kw))
    return out


def robust(S: dict, n_rand: int = 1000) -> None:
    fin = json.loads((REPORTS / "P5_finalists.json").read_text("utf-8"))["finalists"]
    srch = json.loads((REPORTS / "P5_search.json").read_text("utf-8"))["rows"]
    out = {"finalists": fin, "res": {}}
    for n in fin:
        sp = spec_of(n)
        sig = CB.build_signals(S["ctx"], sp["fam"], sp["entry"])
        R = {"center": srch[n], "grid": [], "cost2": {}, "capital": {}}
        for stop, kw in neighbors(sp):
            cell = {"stop": stop, **kw}
            if stop == 0.08 and kw["ma_exit"] == sp["ma_exit"] and kw["max_hold"] == sp["max_hold"]:
                cell.update({p: srch[n][p] for p in PER})
            else:
                for p, rng in PER.items():
                    cell[p], _ = run_one(S, f"P5r_{n}_s{int(stop * 100)}_{kw['ma_exit']}_{kw['max_hold']}_{p}", sig, rng,
                                         market=sp["market"], stop_pct=stop, params={"cfg": n, "period": p, "robust": "grid"},
                                         **kw)
            R["grid"].append(cell)
        c2 = EN.EngineConfig(costs=EN.Costs(scale=2.0))
        for p, rng in PER.items():
            R["cost2"][p], _ = run_one(S, f"P5r_{n}_cost2_{p}", sig, rng, market=sp["market"], ma_exit=sp["ma_exit"],
                                       max_hold=sp["max_hold"], base=c2, params={"cfg": n, "period": p, "robust": "cost2"})
        for cap in (1e6, 1e8):
            R["capital"][f"{cap:.0e}"], _ = run_one(S, f"P5r_{n}_cap{cap:.0e}", sig, PER["VAL"], market=sp["market"],
                                                    ma_exit=sp["ma_exit"], max_hold=sp["max_hold"],
                                                    base=EN.EngineConfig(capital=cap, costs=EN.Costs()), log_trial=False)
        for p in PER:
            cen = srch[n][p]["sharpe"]
            nb = [c[p]["sharpe"] for c in R["grid"] if not (c["stop"] == 0.08 and c["ma_exit"] == sp["ma_exit"]
                                                            and c["max_hold"] == sp["max_hold"])]
            R[f"plateau_{p}"] = VD.plateau(cen, nb)
        G.update({"S": S, "sig": sig, "sp": sp})
        t1 = time.time()
        with mp.get_context("fork").Pool(4) as pool:
            dist = pool.map(_rand_worker, range(n_rand), chunksize=10)
        R["random"] = {"n": n_rand, "pct": VD.pct_rank(srch[n]["VAL"]["cagr"], dist),
                       "p50": float(np.nanmedian([x for x in dist if x is not None])),
                       "p95": float(np.nanpercentile([x for x in dist if x is not None], 95))}
        LOG(f"[p5] {n} 隨機 {n_rand} 次 {time.time() - t1:.0f} 秒：百分位 {R['random']['pct']}")
        out["res"][n] = R
    trials = VD.trial_srs(REPORTS / "trials.csv", "_VAL")
    for n in fin:
        v = srch[n]["VAL"]
        sr = VD.sr_per_obs(v["sharpe"], v["n_obs"], v["years"])
        out["res"][n]["dsr"] = VD.dsr(sr, v["n_obs"], v["skew"], v["kurt"], trials)
    (REPORTS / "P5_robust.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    L = ["# P5 第 2 步：入圍者的穩健度", "", "規則：`reports/P5_plan.md` v1 第 3 節第 4 步。表格由 `scripts/run_p5.py --robust` 產生。", "",
         "| 入圍 | 參數鄰近 IS／VAL | 成本 ×2 VAL 超額 | 隨機 1,000 次：百分位（中位數／95 百分位） | DSR（試驗數） | 本金 100 萬／1 億 VAL 年化 |",
         "| --- | --- | --- | --- | --- | --- |"]
    for n in fin:
        R = out["res"][n]
        pl = "／".join("✓" if R[f"plateau_{p}"]["ok"] else "✗" for p in PER)
        rd = R["random"]
        ds = R["dsr"]
        L.append(f"| {cfg_label(n)} | {pl} | {_p(R['cost2']['VAL']['excess_cagr'])} | {_p(rd['pct'], 0)}（{_p(rd['p50'])}／{_p(rd['p95'])}） | "
                 f"{_f(ds.get('dsr'))}（{ds.get('n')}） | {_p(R['capital']['1e+06']['cagr'])}／{_p(R['capital']['1e+08']['cagr'])} |")
    L += ["", "參數鄰近（Sharpe，IS／VAL）：", ""]
    for n in fin:
        L.append(f"**{cfg_label(n)}**")
        L.append("")
        L.append("| 停損 | 出場參數 | IS Sharpe | VAL Sharpe | VAL 超額 |")
        L.append("| --- | --- | --- | --- | --- |")
        for c in out["res"][n]["grid"]:
            L.append(f"| {int(c['stop'] * 100)}% | {('MA' + str(c['ma_exit'])) if c['ma_exit'] else ('持有 ' + str(c['max_hold']) + ' 日')} | "
                     f"{_f(c['IS']['sharpe'])} | {_f(c['VAL']['sharpe'])} | {_p(c['VAL']['excess_cagr'])} |")
        L.append("")
    (REPORTS / "P5_robust.md").write_text("\n".join(L) + "\n", "utf-8")
    LOG(f"[p5] 穩健度完成（{time.time() - S['t0']:.0f} 秒）")


# ---------------------------------------------------------------------------------------------- 第 3 步：保留期
def holdout(S: dict) -> None:
    fin = json.loads((REPORTS / "P5_finalists.json").read_text("utf-8"))["finalists"]
    rob = json.loads((REPORTS / "P5_robust.json").read_text("utf-8"))["res"]
    srch = json.loads((REPORTS / "P5_search.json").read_text("utf-8"))["rows"]
    out = {"finalists": fin, "res": {}}
    for n in fin:
        sp = spec_of(n)
        sig = CB.build_signals(S["ctx"], sp["fam"], sp["entry"])
        h, res = run_one(S, f"P5h_{n}_HO", sig, HO, market=sp["market"], ma_exit=sp["ma_exit"], max_hold=sp["max_hold"],
                         allow_holdout=True, params={"cfg": n, "period": "HO"})
        h2, _ = run_one(S, f"P5h_{n}_cost2_HO", sig, HO, market=sp["market"], ma_exit=sp["ma_exit"], max_hold=sp["max_hold"],
                        base=EN.EngineConfig(costs=EN.Costs(scale=2.0)), allow_holdout=True,
                        params={"cfg": n, "period": "HO", "robust": "cost2"})
        R = rob[n]
        gate = {"ho_excess": (h["excess_cagr"] or -1) > 0, "dsr": (R["dsr"].get("dsr") or 0) >= 0.95,
                "plateau": bool(R["plateau_IS"]["ok"] and R["plateau_VAL"]["ok"]),
                "random": (R["random"]["pct"] or 0) >= 0.95, "cost2": (h2["excess_cagr"] or -1) > 0}
        tr = res.trades
        best = []
        if tr is not None and len(tr):
            for _, r in tr.sort_values("ret", ascending=False).head(10).iterrows():
                best.append({"stock_id": r["stock_id"], "entry": str(r["entry_date"].date()), "exit": str(r["exit_date"].date()),
                             "ret": float(r["ret"]), "reason": r["reason"]})
        out["res"][n] = {"HO": h, "HO_cost2": h2, "gate": gate, "pass": all(gate.values()), "yearly": yearly(res.equity),
                         "best": best}
        LOG(f"[p5] 保留期 {n}：年化 {_p(h['cagr'])}、超額 {_p(h['excess_cagr'])}、回落 {_p(h['maxdd'])}、{h['trades']} 筆、"
            f"勝率 {_p(h['win_rate'], 0)}；GATE {'通過' if all(gate.values()) else '未通過'} {gate}")
    # 參考組（P5 計畫 v2，打開保留期之前寫定）：不參與挑選，只用來對照
    ref = {}
    a_sig = CB.signals_from(S["ctx"], S["ctx"].asig & S["F"]["elig"], 0.08, "R1")
    ref["R1"], _ = run_one(S, "P5ref_R1_page_HO", a_sig, HO, market=False, ma_exit=None, max_hold=60, weight=0.125,
                           breakeven_r=None, allow_holdout=True, params={"ref": "R1 現行飆股候選照頁面做", "period": "HO"})
    ref["R2"], _ = run_one(S, "P5ref_R2_s01v2_HO", CB.build_signals(S["ctx"], "F0", "E1"), HO, market=True, ma_exit=50,
                           max_hold=None, allow_holdout=True, params={"ref": "R2 照書做 S01 v2 主規格", "period": "HO"})
    for k, a in PER.items():
        ref[f"R1_{k}"], _ = run_one(S, f"P5ref_R1_page_{k}", a_sig, a, market=False, ma_exit=None, max_hold=60,
                                    weight=0.125, breakeven_r=None, params={"ref": "R1", "period": k})
    out["ref"] = ref
    (REPORTS / "P5_holdout.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    L = ["# GATE P5（lab 面板先跑）：綜合策略的保留期檢驗", "",
         "規則：`reports/P5_plan.md` v1。入圍者在保留期（2023-01-02 起）各跑一次，之後不再調參數。表格由 `scripts/run_p5.py --holdout` 產生。", "",
         "| 入圍 | IS 年化／超額 | VAL 年化／超額 | 保留期 年化／超額 | 保留期回落（大盤） | 保留期筆數 | 勝率 | 賺賠比 | 60 日 +50% 比例（全體） | GATE P5 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for n in fin:
        a, v, h = srch[n]["IS"], srch[n]["VAL"], out["res"][n]["HO"]
        L.append(f"| {cfg_label(n)} | {_p(a['cagr'])}／{_p(a['excess_cagr'])} | {_p(v['cagr'])}／{_p(v['excess_cagr'])} | "
                 f"{_p(h['cagr'])}／{_p(h['excess_cagr'])} | {_p(h['maxdd'])}（{_p(h['bench_maxdd'])}） | {h['trades']} | "
                 f"{_p(h['win_rate'], 0)} | {_f(h['payoff'])} | {_p(h['y_A_precision'])}（{_p(h['y_A_base'])}） | "
                 f"{'通過' if out['res'][n]['pass'] else '未通過'} |")
    rn = {"R1": "參考：現行飆股候選照頁面做（週末符合就買、持有 60 日、不停損）", "R2": "參考：照書做（S01 v2 主規格）"}
    for k in ("R1", "R2"):
        h = ref[k]
        a = ref.get(f"{k}_IS") or {}
        v = ref.get(f"{k}_VAL") or {}
        L.append(f"| {rn[k]} | {_p(a.get('cagr'))}／{_p(a.get('excess_cagr'))} | {_p(v.get('cagr'))}／{_p(v.get('excess_cagr'))} | "
                 f"{_p(h['cagr'])}／{_p(h['excess_cagr'])} | {_p(h['maxdd'])}（{_p(h['bench_maxdd'])}） | {h['trades']} | "
                 f"{_p(h['win_rate'], 0)} | {_f(h['payoff'])} | {_p(h['y_A_precision'])}（{_p(h['y_A_base'])}） | 不參與 |")
    L += ["", "各項關卡：保留期超額 > 0／DSR ≥ 0.95／參數鄰近／隨機 ≥ 95 百分位／成本 ×2 仍贏大盤", ""]
    for n in fin:
        g = out["res"][n]["gate"]
        L.append(f"- {cfg_label(n)}：" + "／".join("✓" if g[k] else "✗" for k in ("ho_excess", "dsr", "plateau", "random", "cost2")))
    L.append("")
    (REPORTS / "gate_P5_lab.md").write_text("\n".join(L) + "\n", "utf-8")
    LOG(f"[p5] 保留期完成（{time.time() - S['t0']:.0f} 秒）")


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--search", action="store_true")
    g.add_argument("--robust", action="store_true")
    g.add_argument("--holdout", action="store_true")
    ap.add_argument("--n-rand", type=int, default=1000)
    a = ap.parse_args()
    S = setup()
    if a.search:
        search(S)
    elif a.robust:
        robust(S, a.n_rand)
    else:
        holdout(S)


if __name__ == "__main__":
    main()
