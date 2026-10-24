#!/usr/bin/env python3
"""交易計畫 VER 4（corespec；docs/lab_core70_plan.md 第 19 節）：新飆股（R60）那本帳的回測淨值 → data/lab/sx_r60_curve.json。

W7（tw-superstock-lab reports/W7_results.json）已經找好的逐年規則、同一個引擎（combos.run 固定權重模式），不重新找規則；
存每天收盤的淨值與持股占那本帳的比例（引擎的現金不算利息，core.research 照前一天的持股比例補上現金利息）。
  TZ=Asia/Taipei python3 scripts/run_sx_curve.py      （約 2.5 分鐘；資料或規則改了才重跑）
年化要和 W7 的結果一樣（差超過 0.01 個百分點就不寫檔）。"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import run_w7 as W  # noqa: E402
from superstock import combos as CB  # noqa: E402
from superstock import engine as EN  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402

from arm.lab import corespec as S  # noqa: E402

X, SX = W.X, W.SX
OUT = ROOT / "data" / "lab" / S.SX_CURVE_FILE


def main() -> int:
    t0 = time.time()
    L = S.BOOM_BOOK
    R = json.loads((W.REPORTS / "W7_results.json").read_text(encoding="utf-8"))
    FO = {(f["lab"], f["y"]): f for f in R["folds"]}
    rows = W.samples(None)
    m, extra = LP.load(codes=None)
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    fund = LP.fundamentals(extra["cal"], m.stocks)
    el = F["elig"]
    cal = list(extra["cal"])
    print(f"資料 {time.time() - t0:.0f}s", flush=True)
    mix = {pd.Timestamp(d): i for i, d in enumerate(m.dates)}
    mi = {d: mix.get(pd.Timestamp(d)) for d in {r["d"] for r in rows}}
    by_year: dict[int, list] = {}
    for r in rows:
        by_year.setdefault(int(r["d"][:4]), []).append(r)
    mk = np.zeros(m.c.shape, dtype=bool)
    for y in X.FOLDS:
        preds = [SX.rule_pred([tuple(c) for c in r["conds"]]) for r in FO[(L, y)]["rules"]]
        for r in by_year.get(y, []) if preds else []:
            if any(p(r["f"]) for p in preds):
                i, j = mi[r["d"]], m.col.get(r["c"])
                if i is not None and j is not None:
                    mk[i, j] = True
    ctx = CB.Ctx(m, F, fund, [], CB.rev_days(cal))
    sig = CB.signals_from(ctx, mk & el, 0.08, f"W7_{L}")
    res = CB.run(ctx, sig, market=False, mf=EN.market_filter(m), ma_exit=None, max_hold=X.hold_of(L), start=X.OOS_START, end=None,
                 weight=X.TRADE["weight"], breakeven_r=None)
    st = W.curve_stats(res.equity)
    ref = R["runs"][L]["cagr"]["all"]
    got = st["cagr"]["all"]
    print(f"{L} 年化 {got * 100:.2f}%（W7 {ref * 100:.2f}%）、平均持股比例 {float(res.exposure.mean()):.3f}", flush=True)
    if abs(got - ref) > 1e-4:
        print("和 W7 對不上，不寫檔")
        return 1
    eq = res.equity.dropna()
    ex = res.exposure.reindex(eq.index).ffill().fillna(0.0)
    doc = {"ver": 1, "spec": f"corespec VER {S.VER}", "book": L, "src": "tw-superstock-lab reports/W7_results.json（folds）",
           "made": date.today().isoformat(), "cagr": round(float(got), 6),
           "d": [str(d.date()) for d in eq.index], "nav": [round(float(v) / float(eq.iloc[0]), 6) for v in eq.values],
           "x": [round(float(v), 4) for v in ex.values]}
    txt = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    if OUT.exists() and OUT.read_text(encoding="utf-8") == txt:
        print("沒有變更", OUT)
    else:
        OUT.write_text(txt, encoding="utf-8")
        print("已寫入", OUT, f"（{len(doc['d'])} 天、{doc['d'][0]}～{doc['d'][-1]}）")
    print(f"完成 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
