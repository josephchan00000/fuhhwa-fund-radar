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
    eps = {k: WT.episodes(m, Y[k], n=WT.LABELS[k][0]) for k in WT.SHORT + WT.LONG}
    LOG(f"[w1] 名單與段落 {time.time() - t0:.0f} 秒；段落數 " + "、".join(f"{WT.LNAME[k]} {len(v):,}" for k, v in eps.items()))
    el_w = F["elig"][W]
    wd = m.dates[W]
    rng = np.random.default_rng(20261016)
    stats: dict = {s: {} for s in L}
    for p, (a, b) in {**PER, "ALL": ("2014-01-02", "2100-12-31")}.items():
        rows_p = np.asarray((wd >= pd.Timestamp(a)) & (wd <= pd.Timestamp(b)))
        labs, prec = (WT.LONG, WT.LONG) if p == "ALL" else (WT.SHORT, ("A",) + WT.SHORT)
        ep_p = {k: [e for e in eps[k] if pd.Timestamp(a) <= m.dates[e[1]] <= pd.Timestamp(b)] for k in labs}
        for s in L:
            stats[s][p] = WT.screen_stats(L[s], Y, W, el_w, rows_p, ep_p, m, rng, labs=labs, prec=prec)
        LOG(f"[w1] {p} 完成 {time.time() - t0:.0f} 秒")
    e10 = [e for e in eps["E"] if m.dates[e[1]] >= pd.Timestamp("2014-01-02")]
    case = WT.cases(e10, L, W, m, WT.EARLY["E"])
    chosen, miss = WT.choose(stats)
    try:
        from arm.lab import company  # noqa: WPS433
        names = company.names()
    except Exception:  # noqa: BLE001
        names = {}
    for r in case:
        r["name"] = names.get(r["c"], r["c"])
    out = {"plan": "reports/W1_plan.md v2", "chosen": chosen, "missing": miss, "stats": stats, "cases_10x": case,
           "n_ep": {k: len(v) for k, v in eps.items()}, "asof": time.strftime("%Y-%m-%d")}
    (REPORTS / "W1_watch.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    (REPORTS / "W1_watch.md").write_text(md(out), "utf-8")
    LOG(f"[w1] 選中 {chosen}（{WT.SCREENS.get(chosen)}）{'；未達：' + '、'.join(miss) if miss else ''}；{time.time() - t0:.0f} 秒")


def _p(x, d=0):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def _f(x, d=1):
    return "—" if x is None else f"{x:.{d}f}"


def md(out: dict) -> str:
    st = out["stats"]
    ch = out["chosen"]
    L = ["# W1　超級飆股觀察名單：評估結果", "",
         "方法：`reports/W1_plan.md` v2（跑之前 commit）。資料：lab 面板（PROGRESS A8）。表格由 `scripts/run_watch.py` 產生。",
         "保留期（2023 起）之前已用過，只拿來核對、不拿來挑。", "",
         f"**選中：{ch}　{WT.SCREENS.get(ch, '（沒有名單）')}**" + (f"（沒有名單完全符合資格；它未達：{'、'.join(out['missing'])}）"
                                                              if out.get("missing") else ""), ""]
    L += ["## 多年大飆股（全期：起漲點 2014 年起、期限走完）", "",
          "| 名單 | 每週檔數 | 3 年 5 倍：抓得早（隨機） | 5 年 10 倍：抓得早（隨機） | 5 年 20 倍：抓得早（隨機） | 10 倍段出現時還剩（中位數） | 5 倍股比例（全體） | 10 倍股比例（全體） |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s, name in WT.SCREENS.items():
        x = st[s]["ALL"]
        L.append(f"| {s} {name} | {_f(x['size'])} | {_p(x.get('early_D'))}（{_p(x.get('rand_early_D'))}） | "
                 f"{_p(x.get('early_E'))}（{_p(x.get('rand_early_E'))}） | {_p(x.get('early_F'))}（{_p(x.get('rand_early_F'))}） | "
                 f"{_f((x.get('rem_E') or -1) + 1) + ' 倍' if x.get('rem_E') is not None else '—'} | "
                 f"{_p(x.get('prec_D'), 1)}（{_p(x.get('base_D'), 1)}） | {_p(x.get('prec_E'), 2)}（{_p(x.get('base_E'), 2)}） |")
    x = st["S1"]["ALL"]
    L += ["", f"段落數：3 年 5 倍 {x['n_ep_D']}、5 年 10 倍 {x['n_ep_E']}、5 年 20 倍 {x['n_ep_F']}。"
              f"抓得早＝名單列出時離高點還剩 ≥ √k 倍（5 倍段 2.24 倍、10 倍段 3.16 倍、20 倍段 4.47 倍）。", ""]
    for p in PER:
        L += [f"## 一年內翻倍、3 倍（{p}）", "",
              "| 名單 | 每週檔數 | 每週含翻倍股（隨機） | 翻倍抓得早（隨機） | 3 倍抓得早（隨機） | 出現時還剩（翻倍段，中位數） | 翻倍股比例（全體） | 3 倍股比例（全體） | 3 個月 +50%（全體） |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for s, name in WT.SCREENS.items():
            x = st[s][p]
            L.append(f"| {s} {name} | {_f(x['size'])} | {_p(x.get('week_B'))}（{_p(x.get('rand_week_B'))}） | "
                     f"{_p(x.get('early_B'))}（{_p(x.get('rand_early_B'))}） | {_p(x.get('early_C'))}（{_p(x.get('rand_early_C'))}） | "
                     f"{_p(x.get('rem_B'))} | {_p(x.get('prec_B'), 1)}（{_p(x.get('base_B'), 1)}） | "
                     f"{_p(x.get('prec_C'), 1)}（{_p(x.get('base_C'), 1)}） | {_p(x.get('prec_A'), 1)}（{_p(x.get('base_A'), 1)}） |")
        x = st["S1"][p]
        L += ["", f"翻倍段落 {x['n_ep_B']} 段、3 倍段落 {x['n_ep_C']} 段（起漲點在這段期間、起漲時是合格股票）。", ""]
    L += ["## 5 年 10 倍以上的股票：各名單什麼時候抓到", "",
          "格子＝第一次列出的日期／當時已漲幾倍（從起漲點算）→ 離高點還剩幾倍；★＝抓得早。空白＝這份名單在 T0 前 60 日到高點之間沒有列出過。", "",
          "| 股票 | 起漲 | 高點 | 倍數 | " + " | ".join(WT.SCREENS) + " |", "| --- | --- | --- | --- | " + " | ".join("---" for _ in WT.SCREENS) + " |"]
    for r in out["cases_10x"]:
        cells = []
        for s in WT.SCREENS:
            b = r["by"].get(s)
            cells.append("" if not b else f"{b['d']}／{_f(b['up'], 1)}→{_f(b['rem'], 1)}{'★' if b['early'] else ''}")
        L.append(f"| {r['c']} {r['name']} | {r['t0']} | {r['pk']} | {r['x']:g} | " + " | ".join(cells) + " |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
