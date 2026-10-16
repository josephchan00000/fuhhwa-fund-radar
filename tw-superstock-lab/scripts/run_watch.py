"""W1：超級飆股觀察名單評估（reports/W1_plan.md，跑之前寫定）。

    .venv/bin/python scripts/run_watch.py   → reports/W1_watch.{md,json}
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from superstock import combos as CB  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402
from superstock import watch as WT  # noqa: E402

REPORTS = ROOT / "reports"
PER = {"IS": ("2014-01-02", "2019-12-31"), "VAL": ("2020-01-02", "2022-12-30"), "HO": ("2023-01-02", "2100-12-31")}
LOG = print


def main() -> None:
    t0 = time.time()
    m, extra = LP.load()
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    fund = LP.fundamentals(extra["cal"], m.stocks)
    sys.path.insert(0, str(LP.REPO / "scripts"))
    import run_super  # noqa: WPS433
    from arm.lab import superx as SX  # noqa: WPS433

    res = SX.load_res()
    pa = [SX.rule_pred([tuple(c) for c in conds]) for _, conds in SX.live_rules(res)]
    pb = [SX.rule_pred([tuple(c) for c in r["conds"]]) for r in ((res.get("labels") or {}).get("B") or {}).get("rules") or []]
    rows = run_super.samples(log=LOG)
    a_rows = [(r["c"], r["d"]) for r in rows if any(p(r["f"]) for p in pa)]
    b_rows = [(r["c"], r["d"]) for r in rows if any(p(r["f"]) for p in pb)]
    ctx = CB.Ctx(m, F, fund, a_rows, [])
    LOG(f"[w1] 準備 {time.time() - t0:.0f} 秒；A 規則 {len(a_rows):,}、B 規則（{len(pb)} 條）{len(b_rows):,}")
    W = np.array(ctx.week_ends)
    L = WT.week_lists(ctx, F, b_rows)
    Y = WT.labels(m, F["elig"])
    eps = {k: WT.episodes(m, Y[k]) for k in ("B", "C")}
    LOG(f"[w1] 名單與段落 {time.time() - t0:.0f} 秒；翻倍段落 {len(eps['B']):,}、超級飆股段落 {len(eps['C']):,}")
    el_w = F["elig"][W]
    wd = m.dates[W]
    rng = np.random.default_rng(20261016)
    stats: dict = {s: {} for s in L}
    for p, (a, b) in PER.items():
        rows_p = np.asarray((wd >= pd.Timestamp(a)) & (wd <= pd.Timestamp(b)))
        ep_p = {k: [e for e in eps[k] if pd.Timestamp(a) <= m.dates[e[1]] <= pd.Timestamp(b)] for k in eps}
        for s in L:
            stats[s][p] = WT.screen_stats(L[s], Y, W, el_w, rows_p, ep_p, m, rng)
        LOG(f"[w1] {p} 完成 {time.time() - t0:.0f} 秒")
    chosen = WT.choose(stats)
    out = {"plan": "reports/W1_plan.md v1", "chosen": chosen, "stats": stats,
           "n_ep": {k: len(v) for k, v in eps.items()}, "asof": time.strftime("%Y-%m-%d")}
    (REPORTS / "W1_watch.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    (REPORTS / "W1_watch.md").write_text(md(out), "utf-8")
    LOG(f"[w1] 選中 {chosen}（{WT.SCREENS.get(chosen)}）；{time.time() - t0:.0f} 秒")


def _p(x, d=0):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def _f(x, d=1):
    return "—" if x is None else f"{x:.{d}f}"


def md(out: dict) -> str:
    st = out["stats"]
    L = ["# W1　超級飆股觀察名單：評估結果", "",
         "方法：`reports/W1_plan.md` v1（跑之前 commit）。資料：lab 面板（PROGRESS A8）。表格由 `scripts/run_watch.py` 產生。",
         "保留期（2023 起）之前已用過，只拿來核對、不拿來挑。", "",
         f"**選中：{out['chosen']}　{WT.SCREENS.get(out['chosen'], '（沒有名單符合條件）')}**", ""]
    for p in PER:
        L += [f"## {p}", "",
              "| 名單 | 每週檔數 | 每週含翻倍股（隨機） | 翻倍股抓得早（隨機） | 超級飆股抓得早（隨機） | 出現時還剩（翻倍段，中位數） | 翻倍股比例（全體） | 超級飆股比例（全體） | 60 日 +50%（全體） |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for s, name in WT.SCREENS.items():
            x = st[s][p]
            L.append(f"| {s} {name} | {_f(x['size'])} | {_p(x.get('week_B'))}（{_p(x.get('rand_week_B'))}） | "
                     f"{_p(x.get('early_B'))}（{_p(x.get('rand_early_B'))}） | {_p(x.get('early_C'))}（{_p(x.get('rand_early_C'))}） | "
                     f"{_p(x.get('rem_B'))} | {_p(x.get('prec_B'), 1)}（{_p(x.get('base_B'), 1)}） | "
                     f"{_p(x.get('prec_C'), 1)}（{_p(x.get('base_C'), 1)}） | {_p(x.get('prec_A'), 1)}（{_p(x.get('base_A'), 1)}） |")
        x = st["S1"][p]
        L += ["", f"翻倍段落 {x['n_ep_B']} 段、超級飆股段落 {x['n_ep_C']} 段（T0 在這段期間、起漲時是合格股票）。", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
