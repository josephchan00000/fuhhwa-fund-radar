"""W9：用《超級績效》的選股邏輯挑台股（規格 ../arm/lab/sepaspec.py VER 1、../docs/lab_sepa_pick_plan.md，跑之前寫定）。

    python3 scripts/run_w9.py          → reports/W9_results.json＋W9_results.md
    python3 scripts/run_w9.py --smoke  → 只取 150 檔試跑（不寫檔、不記試驗）
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_w7 as W7  # noqa: E402  （LP.arm()、run_super、superx 都在這裡載好）
from superstock import combos as CB  # noqa: E402
from superstock import engine as EN  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402
from arm.lab import sepaspec as S  # noqa: E402
from arm.lab import superfixspec as X  # noqa: E402
from arm.lab import superx as SX  # noqa: E402

REPORTS = ROOT / "reports"
LOG = print


def samples(n_codes: int | None = None) -> list[dict]:
    """每週最後一個交易日 × 合格股票的特徵（run_super.samples，不算標籤）。"""
    lab0 = dict(SX.LABELS)
    SX.LABELS = {}
    try:
        return W7.run_super.samples(n_codes, log=LOG)
    finally:
        SX.LABELS = lab0


def rs_score(m: EN.Market) -> np.ndarray:
    c = pd.DataFrame(m.c_ff)
    out = sum(w * (c / c.shift(n) - 1) for n, w in S.RS_WEIGHTS)
    return out.to_numpy(dtype=float)


def market_ok(m: EN.Market) -> np.ndarray:
    lv = m.index_level.reindex(m.dates).ffill()
    with np.errstate(invalid="ignore"):
        return (lv > lv.rolling(S.MARKET["ma"], min_periods=S.MARKET["ma"]).mean()).to_numpy()


def signals(m: EN.Market, mask: np.ndarray, score: np.ndarray, tag: str) -> pd.DataFrame:
    ii, jj = np.nonzero(mask)
    return pd.DataFrame({"date": m.dates[ii], "stock_id": np.array(m.stocks)[jj], "entry": "open",
                         "score": np.nan_to_num(score[ii, jj], nan=-9.0), "tag": tag})


def run(ctx: CB.Ctx, sig: pd.DataFrame, *, mf: np.ndarray | None, exit_cfg: dict, start: str) -> EN.Result:
    """CB.run 的固定權重模式；多一個「固定權重＋停損」（書的 8% 停損）。"""
    m = ctx.m
    cfg = replace(EN.EngineConfig(costs=EN.Costs()), breakeven_r=None, market_filter=mf is not None,
                  block_disposition=False, max_hold_days=exit_cfg["max_hold"])
    mfu = mf if mf is not None else np.ones(m.n, dtype=bool)
    ix = {d: i for i, d in enumerate(m.dates)}
    by_day: dict[int, list] = {}
    for d, c, sc in zip(sig["date"], sig["stock_id"], sig["score"]):
        i, s = ix.get(pd.Timestamp(d)), m.col.get(str(c))
        if i is None or s is None:
            continue
        by_day.setdefault(i, []).append((s, float(sc)))
    stop = exit_cfg["stop"]

    def decide(i: int, sim: EN.Simulator) -> list:
        if not mfu[i]:
            return []
        return [EN.Order(s, "open", weight=S.TRADE["weight"], score=sc, **({"stop_pct": stop} if stop else {}))
                for s, sc in by_day.get(i, [])]

    sim = EN.Simulator(m, cfg, exit_flags=CB.exit_flags(ctx, exit_cfg["ma_exit"]), mf=mfu)
    return sim.run(decide, start, None)


def long_stats(eq: pd.Series) -> dict:
    P = {"all": (S.START_LONG, "2100-12-31"), "p0": (S.START_LONG, "2018-12-31"), "h1": S.HALVES[0], "h2": S.HALVES[1]}
    return {"cagr": {k: W7.cagr(eq, *v) for k, v in P.items()}, "mdd": {k: W7.mdd(eq, *v) for k, v in P.items()},
            "yearly": W7.yearly(eq)}


def vname(v: dict) -> str:
    return f"{v['screen']}|{v['exit']}|{'mkt' if v['market'] else 'nomkt'}"


def main(smoke: bool = False) -> None:
    t0 = time.time()
    n_codes = 150 if smoke else None
    rows = samples(n_codes)
    codes = sorted({r["c"] for r in rows}) if smoke else None
    m, extra = LP.load(codes=codes)
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    fund = LP.fundamentals(extra["cal"], m.stocks)
    el = F["elig"]
    mix = {pd.Timestamp(d): i for i, d in enumerate(m.dates)}
    mi = {d: mix.get(pd.Timestamp(d)) for d in {r["d"] for r in rows}}
    LOG(f"[w9] 面板、特徵、樣本 {len(rows):,} 列，{time.time() - t0:.0f} 秒")

    # 選股遮罩
    masks = {}
    for scr in S.SCREENS:
        mk = np.zeros(m.c.shape, dtype=bool)
        for r in rows:
            if S.passes(r["f"], scr):
                i, j = mi[r["d"]], m.col.get(r["c"])
                if i is not None and j is not None:
                    mk[i, j] = True
        masks[scr] = mk & el

    # 新飆股（W7 的 R60）：用存下來的逐年規則重建，同一套引擎重跑，年化要和 W7 一樣
    W7R = json.loads((REPORTS / "W7_results.json").read_text("utf-8"))
    FO = {(f["lab"], f["y"]): f for f in W7R["folds"]}
    by_year: dict[int, list] = {}
    for r in rows:
        by_year.setdefault(int(r["d"][:4]), []).append(r)
    mk = np.zeros(m.c.shape, dtype=bool)
    for y in X.FOLDS:
        preds = [SX.rule_pred([tuple(c) for c in rr["conds"]]) for rr in FO[(S.COMPARE, y)]["rules"]]
        for r in by_year.get(y, []):
            if preds and any(p(r["f"]) for p in preds):
                i, j = mi[r["d"]], m.col.get(r["c"])
                if i is not None and j is not None:
                    mk[i, j] = True
    ctx = CB.Ctx(m, F, fund, [], CB.rev_days(list(extra["cal"])))
    sig = CB.signals_from(ctx, mk & el, 0.08, "W9_R60")
    res = CB.run(ctx, sig, market=False, mf=np.ones(m.n, dtype=bool), ma_exit=None, max_hold=60, start=X.OOS_START,
                 end=None, weight=X.TRADE["weight"], breakeven_r=None)
    r60 = {**W7.curve_stats(res.equity), "trades": W7.trade_stats(res)}
    want = W7R["runs"][S.COMPARE]["cagr"]["all"]
    LOG(f"[w9] 新飆股重建：{r60['cagr']['all'] * 100:.4f}%（W7 存的 {want * 100:.4f}%）")
    if not smoke and abs(r60["cagr"]["all"] - want) > 1e-9:
        raise SystemExit("新飆股重建和 W7 不一樣，不出結果")
    ents_r60 = {(pd.Timestamp(d), str(c)) for d, c in res.entries}

    # 主規格與只描述的組合
    score = rs_score(m)
    mf = market_ok(m)
    runs, curves = {}, {}
    for v in S.VARIANTS:
        k = vname(v)
        sg = signals(m, masks[v["screen"]], score, f"W9_{k}")
        res = run(ctx, sg, mf=mf if v["market"] else None, exit_cfg=S.EXITS[v["exit"]], start=S.START)
        ents = {(pd.Timestamp(d), str(c)) for d, c in res.entries}
        runs[k] = {**W7.curve_stats(res.equity), "trades": W7.trade_stats(res),
                   "same_r60": len(ents & ents_r60) / len(ents) if ents else None}
        curves[k] = res.equity
        if not smoke:
            EN.evaluate(f"W9_{k}", "trade", res, {"w9": k, "spec": f"sepaspec VER {S.VER}", "start": S.START, "data": "lab-A8"},
                        m, reports_dir=REPORTS, allow_holdout=True)
        LOG(f"[w9] {k}：{runs[k]['cagr']['all'] * 100:.1f}%（{runs[k]['cagr']['h1'] * 100:.1f}／{runs[k]['cagr']['h2'] * 100:.1f}）"
            f"回落 {runs[k]['mdd']['all'] * 100:.0f}%，{runs[k]['trades'].get('n')} 筆")
    main_k = vname(S.MAIN_CFG)

    # 2014 年起（主規格，只描述）
    sg = signals(m, masks["main"], score, "W9_long")
    res_l = run(ctx, sg, mf=mf, exit_cfg=S.EXITS[S.EXIT], start=S.START_LONG)
    long_ = {**long_stats(res_l.equity), "trades": W7.trade_stats(res_l)}

    # 對照
    c_ff = m.c_ff
    r1 = np.zeros(m.c.shape)
    r1[1:] = c_ff[1:] / c_ff[:-1] - 1
    with np.errstate(invalid="ignore"):
        ew_r = np.nanmean(np.where(el[:-1], np.nan_to_num(r1[1:]), np.nan), axis=1)
    ew_all = pd.Series(np.concatenate([[1.0], np.cumprod(1 + np.nan_to_num(ew_r))]), index=m.dates)
    tr_all = m.index_tr.dropna()
    o0, o1 = pd.Timestamp(S.START), pd.Timestamp(S.START_LONG)
    bench = {"EW": W7.curve_stats(ew_all[ew_all.index >= o0]), "TR": W7.curve_stats(tr_all[tr_all.index >= o0])}
    bench_long = {"EW": long_stats(ew_all[ew_all.index >= o1]), "TR": long_stats(tr_all[tr_all.index >= o1])}

    # 每週通過幾檔、實際買了幾檔（主規格，2019 起）
    i0 = int(m.dates.searchsorted(o0))
    wk_pass = pd.Series(masks["main"][i0:].sum(axis=1), index=m.dates[i0:])
    wk_pass = wk_pass[wk_pass.index.isin([pd.Timestamp(r["d"]) for r in rows])]
    weekly = {"pass_med": float(wk_pass.median()), "pass_p10": float(wk_pass.quantile(.1)),
              "pass_p90": float(wk_pass.quantile(.9)), "weeks_zero": float((wk_pass == 0).mean())}
    verdict = S.verdict(runs[main_k], r60, bench["TR"])
    out = {"ver": S.VER, "spec": S.SPEC_DATE, "made": time.strftime("%Y-%m-%d"), "last": str(m.dates[-1].date()),
           "main": main_k, "runs": runs, "r60": r60, "bench": bench, "long": long_, "bench_long": bench_long,
           "weekly": weekly, "verdict": verdict}
    LOG(f"[w9] 判定：{verdict}；{time.time() - t0:.0f} 秒")
    if smoke:
        return
    (REPORTS / "W9_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    report()


def _p(x, d=1, sign=False):
    if x is None:
        return "—"
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def report() -> None:
    R = json.loads((REPORTS / "W9_results.json").read_text("utf-8"))
    mk, r60, tr, ew = R["main"], R["r60"], R["bench"]["TR"], R["bench"]["EW"]
    M = R["runs"][mk]
    L = [f"# W9　用《超級績效》的選股邏輯挑台股：結果", "",
         f"規格：`arm/lab/sepaspec.py` VER {R['ver']}（{R['spec']}，跑之前 commit）；規劃 `docs/lab_sepa_pick_plan.md`。"
         f"資料到 {R['last']}。數字由 `scripts/run_w9.py` 產生。", "",
         f"## 判定：{R['verdict']}", "",
         "| 2019 起 | 整段年化 | 2019–2022 | 2023 起 | 最大回落 | 筆數 | 賺錢比例 | 每筆中位數 | 最賺一成占獲利 | 平均抱幾天 | 平均持股 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]

    def row(name, s, tdt=None):
        t = tdt or {}
        return (f"| {name} | {_p(s['cagr']['all'])} | {_p(s['cagr']['h1'])} | {_p(s['cagr']['h2'])} | {_p(s['mdd']['all'], 0)} | "
                f"{t.get('n', '—')} | {_p(t.get('win'), 0)} | {_p(t.get('med'), 1, True)} | {_p(t.get('top10'), 0)} | "
                f"{round(t['hold']) if t.get('hold') else '—'} | {_p(t.get('exposure'), 0)} |")
    L += [row("**《超級績效》選股（主規格）**", M, M["trades"]), row("新飆股", r60, r60["trades"]),
          row("加權報酬指數", tr), row("合格股票等權", ew), ""]
    L += ["## 逐年", "", "| 年 | 主規格 | 新飆股 | 加權報酬指數 | 等權 |", "| --- | --- | --- | --- | --- |"]
    for y in sorted(M["yearly"]):
        L.append(f"| {y} | {_p(M['yearly'][y])} | {_p(r60['yearly'].get(y))} | {_p(tr['yearly'].get(y))} | {_p(ew['yearly'].get(y))} |")
    L += ["", "## 只描述：其他組合（不判定）", "",
          "| 組合 | 整段年化 | 2019–2022 | 2023 起 | 最大回落 | 筆數 | 賺錢比例 | 和新飆股同一天買同一檔 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    nm = {"main": "照書三關", "strict": "都要加速", "trend": "只看趨勢與強度", "ma50": "跌破 50 日線", "hold60": "抱 60 天",
          "book": "8% 停損＋50 日線", "mkt": "看大盤", "nomkt": "不看大盤"}
    for k, s in R["runs"].items():
        a, b, c = k.split("|")
        t = s["trades"]
        L.append(f"| {nm[a]}・{nm[b]}・{nm[c]}{'（主規格）' if k == mk else ''} | {_p(s['cagr']['all'])} | {_p(s['cagr']['h1'])} | "
                 f"{_p(s['cagr']['h2'])} | {_p(s['mdd']['all'], 0)} | {t.get('n')} | {_p(t.get('win'), 0)} | {_p(s.get('same_r60'), 0)} |")
    G, BL = R["long"], R["bench_long"]
    L += ["", "## 只描述：2014 年起（主規格）", "",
          "| | 整段年化 | 2014–2018 | 2019–2022 | 2023 起 | 最大回落 |", "| --- | --- | --- | --- | --- | --- |"]
    for name, s in (("主規格", G), ("加權報酬指數", BL["TR"]), ("合格股票等權", BL["EW"])):
        L.append(f"| {name} | {_p(s['cagr']['all'])} | {_p(s['cagr']['p0'])} | {_p(s['cagr']['h1'])} | {_p(s['cagr']['h2'])} | "
                 f"{_p(s['mdd']['all'], 0)} |")
    w = R["weekly"]
    L += ["", f"每週通過照書三關（2019 起）：中位數 {w['pass_med']:.0f} 檔（10% 的週 {w['pass_p10']:.0f} 檔以下、90% 的週 "
          f"{w['pass_p90']:.0f} 檔以下），{_p(w['weeks_zero'], 0)} 的週一檔都沒有。", ""]
    (REPORTS / "W9_results.md").write_text("\n".join(L), "utf-8")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        main(smoke="--smoke" in sys.argv)
