"""W8：飆股「抱到出場條件才賣」——W7 同一批訊號、同一個引擎，只換出場（reports/W8_plan.md，跑之前寫定；
規格 ../arm/lab/sxexitspec.py VER 1）。

    python3 scripts/run_w8.py          → reports/W8_results.json、W8_results.md
    python3 scripts/run_w8.py --smoke  → 只取 150 檔試跑（不寫檔、不記試驗）
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_w7 as W  # noqa: E402  —— W7 的樣本、面板、統計（同一套）

from arm.lab import sxexitspec as XS  # noqa: E402

CB, EN, FT, LP, SX, X = W.CB, W.EN, W.FT, W.LP, W.SX, W.X
REPORTS = W.REPORTS
LOG = print


class PosFlags:
    """收盤出場條件（引擎在收盤時對每一個持有中的部位查 exit_flags[i, s]）：跌破均線、比買進價低、比買進以後最高收盤低。"""

    def __init__(self, ctx, spec: dict):
        self.m, self.spec = ctx.m, spec
        self.ma = ctx.ma(spec["ma"]) if spec.get("ma") else None
        self.sim = None

    def __getitem__(self, key) -> bool:
        i, s = key
        p = self.sim.pos.get(s)
        c = self.m.c[i, s]
        if p is None or not (c == c):
            return False
        if self.ma is not None and self.ma[i, s] == self.ma[i, s] and c < self.ma[i, s]:
            return True
        if self.spec.get("stop") and c < p.entry_px * (1 - self.spec["stop"]):
            return True
        if self.spec.get("trail"):
            hi = np.nanmax(self.m.c[p.entry_i:i + 1, s])
            if c < hi * (1 - self.spec["trail"]):
                return True
        return False


def run_exit(ctx, sig: pd.DataFrame, spec: dict) -> EN.Result:
    """CB.run（固定權重、沒有大盤濾網、沒有移動停損）照抄，只多收盤出場條件。"""
    m = ctx.m
    cfg = replace(EN.EngineConfig(costs=EN.Costs()), breakeven_r=None, market_filter=False, block_disposition=False,
                  max_hold_days=spec.get("hold"))
    by_day: dict[int, list] = {}
    ix = {d: i for i, d in enumerate(m.dates)}
    for d, c, sc in zip(sig["date"], sig["stock_id"], sig["score"]):
        i, s = ix.get(pd.Timestamp(d)), m.col.get(str(c))
        if i is None or s is None:
            continue
        by_day.setdefault(i, []).append(EN.Order(s, "open", weight=X.TRADE["weight"], score=float(sc)))
    flags = PosFlags(ctx, spec) if any(k in spec for k in ("ma", "stop", "trail")) else None
    sim = EN.Simulator(m, cfg, exit_flags=flags, mf=np.ones(m.n, dtype=bool))
    if flags is not None:
        flags.sim = sim
    return sim.run(lambda i, _s: [EN.Order(o.s, o.kind, stop_pct=o.stop_pct, weight=o.weight, score=o.score)
                                  for o in by_day.get(i, [])], X.OOS_START, None)


def main(smoke: bool = False) -> None:
    t0 = time.time()
    n_codes = 150 if smoke else None
    rows = W.samples(n_codes)
    codes = sorted({r["c"] for r in rows}) if smoke else None
    m, extra = LP.load(codes=codes)
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    fund = LP.fundamentals(extra["cal"], m.stocks)
    el = F["elig"]
    cal = list(extra["cal"])
    LOG(f"[w8] 面板、特徵、樣本 {time.time() - t0:.0f} 秒")
    w7 = json.loads((REPORTS / "W7_results.json").read_text("utf-8"))
    FO = {(f["lab"], f["y"]): f for f in w7["folds"]}
    mix = {pd.Timestamp(d): i for i, d in enumerate(m.dates)}
    mi = {d: mix.get(pd.Timestamp(d)) for d in {r["d"] for r in rows}}
    by_year: dict[int, list] = {}
    for r in rows:
        by_year.setdefault(int(r["d"][:4]), []).append(r)
    ctx = CB.Ctx(m, F, fund, [], CB.rev_days(cal))
    mf = EN.market_filter(m)
    runs: dict = {}
    for L in XS.LABELS:                                # 訊號：W7 的規則原封不動（不重找）
        mk = np.zeros(m.c.shape, dtype=bool)
        for y in X.FOLDS:
            preds = [SX.rule_pred([tuple(c) for c in r["conds"]]) for r in FO[(L, y)]["rules"]]
            for r in by_year.get(y, []) if preds else []:
                if any(p(r["f"]) for p in preds):
                    i, j = mi[r["d"]], m.col.get(r["c"])
                    if i is not None and j is not None:
                        mk[i, j] = True
        sig = CB.signals_from(ctx, mk & el, 0.08, f"W7_{L}")
        runs[L] = {}
        for k, spec in XS.EXITS.items():
            res = run_exit(ctx, sig, spec)
            if k == XS.BASE:                           # 檢查：和 W7 的 CB.run 完全相同
                ref = CB.run(ctx, sig, market=False, mf=mf, ma_exit=None, max_hold=X.hold_of(L), start=X.OOS_START,
                             end=None, weight=X.TRADE["weight"], breakeven_r=None)
                assert np.allclose(res.equity.to_numpy(), ref.equity.to_numpy(), rtol=1e-12), "X0 和 W7 不同"
            if not smoke:
                EN.evaluate(f"W8_{L}_{k}", "trade", res, {"w8": k, "exit": spec, "label": L, "weight": X.TRADE["weight"],
                                                           "start": X.OOS_START, "data": "lab-A8", "spec": f"sxexitspec VER {XS.VER}"},
                            m, reports_dir=REPORTS, allow_holdout=True)
            st = {**W.curve_stats(res.equity), "trades": W.trade_stats(res)}
            runs[L][k] = st
            LOG(f"[w8] {L} {k} {spec}：整段 {st['cagr']['all'] * 100:.1f}%（{st['cagr']['h1'] * 100:.1f}／{st['cagr']['h2'] * 100:.1f}）"
                f"回落 {st['mdd']['all'] * 100:.0f}%，{st['trades'].get('n')} 筆、平均抱 {st['trades'].get('hold', 0):.0f} 天")
    if not smoke:                                      # 檢查：X0 的整段年化＝W7
        for L in XS.LABELS:
            assert abs(runs[L][XS.BASE]["cagr"]["all"] - w7["runs"][L]["cagr"]["all"]) < 1e-12, f"{L} X0 ≠ W7"
    B = runs[XS.PRIMARY][XS.BASE]
    verdict = {}
    for k in XS.EXITS:
        if k == XS.BASE:
            continue
        R = runs[XS.PRIMARY][k]
        c1 = all(R["cagr"][h] > B["cagr"][h] for h in ("h1", "h2"))
        c2 = R["mdd"]["all"] <= B["mdd"]["all"] + XS.PASS["mdd_extra"] / 100
        verdict[k] = {"c1": c1, "c2": c2, "pass": c1 and c2}
    sign = lambda x: (x > 0) - (x < 0)  # noqa: E731
    sens = {f"{a}/{b}": sign(runs[XS.PRIMARY][a]["cagr"]["all"] - B["cagr"]["all"]) !=
            sign(runs[XS.PRIMARY][b]["cagr"]["all"] - B["cagr"]["all"]) for a, b in XS.NEIGHBORS}
    out = {"ver": XS.VER, "spec": XS.SPEC_DATE, "made": time.strftime("%Y-%m-%d"), "last": str(m.dates[-1].date()),
           "runs": runs, "bench": w7["bench"], "verdict": verdict, "sensitive": sens}
    if smoke:
        LOG(json.dumps({L: {k: v["cagr"] for k, v in d.items()} for L, d in runs.items()}, ensure_ascii=False))
        return
    (REPORTS / "W8_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    report()
    LOG(f"[w8] 判定 {verdict}；鄰近方向不同 {sens}；{time.time() - t0:.0f} 秒")


NAMES = {"X0": "固定抱 60 天", "X1": "跌破 50 日線", "X2": "跌破 20 日線", "X3": "比買進後最高收盤低 20%",
         "X4": "比買進後最高收盤低 30%", "X5": "虧 8% 或跌破 50 日線", "X6": "虧 20% 或從最高收盤回落 30%"}


def report() -> None:
    R = json.loads((REPORTS / "W8_results.json").read_text("utf-8"))
    p = lambda x: "—" if x is None else f"{x * 100:.1f}%"  # noqa: E731
    lines = ["# W8 結果：飆股「抱到出場條件才賣」", "",
             f"計畫 `W8_plan.md`；規格 `../arm/lab/sxexitspec.py` VER {R['ver']}；資料到 {R['last']}；樣本外 2019-01-02 起。", ""]
    for L in XS.LABELS:
        lines += [f"## {'新目標（R60）' if L == 'R60' else '現行目標（A，只描述）'}", "",
                  "| 出場 | 整段年化 | 2019–2022 | 2023 起 | 最大回落 | 筆數 | 平均抱幾天 | 賺錢比例 | 最賺一成占獲利 | 判定 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for k in XS.EXITS:
            s = R["runs"][L][k]
            t = s["trades"]
            v = R["verdict"].get(k) if L == XS.PRIMARY else None
            vt = "（對照）" if k == XS.BASE else ("—" if v is None else ("比較好" if v["pass"] else
                                                                       "沒有比較好" if not v["c1"] else "回落太深"))
            lines.append(f"| {k} {NAMES[k]} | {p(s['cagr']['all'])} | {p(s['cagr']['h1'])} | {p(s['cagr']['h2'])} | "
                         f"{p(s['mdd']['all'])} | {t.get('n')} | {t.get('hold', 0):.0f} | {p(t.get('win'))} | {p(t.get('top10'))} | {vt} |")
        lines.append("")
    b = R["bench"]
    lines += [f"對照：一般股票等權 {p(b['EW']['cagr']['all'])}（最大回落 {p(b['EW']['mdd']['all'])}）、"
              f"加權報酬指數 {p(b['TR']['cagr']['all'])}（{p(b['TR']['mdd']['all'])}）。", "",
              "鄰近參數方向不一樣（＝對參數敏感）：" + "、".join(f"{k} {'是' if v else '否'}" for k, v in R["sensitive"].items()), ""]
    (REPORTS / "W8_results.md").write_text("\n".join(lines), "utf-8")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        main(smoke="--smoke" in sys.argv)
