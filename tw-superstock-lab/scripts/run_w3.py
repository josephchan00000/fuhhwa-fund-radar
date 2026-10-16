"""W3：第二層篩選——交叉比對各策略、提高一年內翻倍的命中率（reports/W3_plan.md v1，跑之前寫定）。

    .venv/bin/python -u scripts/run_w3.py --stage is    建資料表（快取 data/cache/w3_table.pkl）＋只算 2014–2019
                                                        → reports/W3_is.{md,json}（定第一層門檻、逐步加條件；先 commit）
    .venv/bin/python -u scripts/run_w3.py --stage val   讀快取與 W3_is.json 的定案 → 2020–2022 判定、2023 起參考
                                                        → reports/W3_results.{md,json}、../data/lab/layer_research.json
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from superstock import combos as CB  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402
from superstock import layer as LA  # noqa: E402
from superstock import watch as WT  # noqa: E402

REPORTS = ROOT / "reports"
CACHE = ROOT / "data" / "cache" / "w3_table.pkl"
OUT = LP.REPO / "data" / "lab" / "layer_research.json"
LOG = print
T0 = time.time()


def log(msg: str) -> None:
    LOG(f"{msg}（{time.time() - T0:.0f} 秒）")


def build_table() -> dict:
    m, extra = LP.load()
    log("[w3] 面板")
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    log("[w3] 樣板、RS、VCP")
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
    del rows
    log(f"[w3] A 規則 {len(a_rows):,}、B 規則 {len(b_rows):,}")
    ctx = CB.Ctx(m, F, fund, a_rows, [])
    W = np.array(ctx.week_ends)
    L = WT.week_lists(ctx, F, b_rows)
    log(f"[w3] 合併名單：平均每週 {L['S9'].sum(axis=1).mean():.1f} 檔")
    LY, PT, bt3d = LA.shared()
    eps, rev = bt3d.load_eps(), PT.load_rev()
    ind = json.loads((LP.REPO / "data" / "stock_industry.json").read_text("utf-8"))["industry"]
    tb = LA.build(m, F, extra, fund, W, L["S9"], set(a_rows), set(b_rows), eps, rev, ind, LOG)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("wb") as fh:
        pickle.dump(tb, fh, protocol=pickle.HIGHEST_PROTOCOL)
    log(f"[w3] 快取 {CACHE}")
    return tb


# ---------------------------------------------------------------------------------------------- 2014–2019
def stage_is() -> None:
    tb = build_table()
    LY, _, _ = LA.shared()
    T = LA.Tab(tb)
    a, b = LA.PER["IS"]
    allm = np.ones(len(T.d), dtype=bool)
    s9 = {L: T.stat(allm, a, b, L) for L in LA.LABS}
    s9_new = T.stat(T.new_entry(allm), a, b)
    base = {L: LA.base_rate(tb, L, a, b) for L in LA.LABS}
    single = LA.single_table(T, a, b, LA.SUBS)
    curve = LA.score_curve(T, a, b)
    s_star = LA.pick_tier(curve, s9["B"]["p"])
    t1 = T.score >= s_star
    t1n = T.stat(T.new_entry(t1), a, b)
    gr = LA.greedy(T, a, b, LA.SUBS, exclude=LY.LIST_ONLY)
    pr = LA.pairs(T, single, a, b)
    fam = []
    for n, name in enumerate(LY.FNAMES):
        st = T.stat(T.fam[:, n], a, b)
        fam.append({"name": name, **st, "lift": LA.lift(st, s9["B"])})
    out = {"plan": "reports/W3_plan.md v1", "asof": time.strftime("%Y-%m-%d"), "period": [a, b], "s_star": s_star,
           "greedy": gr, "s9": s9, "s9_new": s9_new, "base": base, "t1": {L: T.stat(t1, a, b, L) for L in LA.LABS},
           "t1_new": t1n, "single": single, "curve": curve, "pairs": pr, "fam": fam,
           "n_rows": len(T.d), "n_weeks": T.weeks(a, b)}
    out = LA.to_json(out)
    (REPORTS / "W3_is.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    (REPORTS / "W3_is.md").write_text(md_is(out), "utf-8")
    log(f"[w3] 2014–2019 完成：第一層＝分數 ≥ {s_star}；逐步加條件：{'、'.join(g['add'] for g in gr) or '無'}")


def _p(x, d=1):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def _x(x, d=2):
    return "—" if x is None else f"{x:.{d}f}"


def md_is(o: dict) -> str:
    LY, _, _ = LA.shared()
    s9 = o["s9"]
    L = ["# W3　第二層篩選：2014–2019 分析（定第一層門檻；2020–2022 還沒看）", "",
         "方法：`reports/W3_plan.md` v1（跑之前 commit）。表格由 `scripts/run_w3.py --stage is` 產生。", "",
         f"- 合併名單 S9：{o['n_rows']:,} 個股票週（全期）；2014–2019 平均每週 {_x(s9['B']['per_week'], 1)} 檔。",
         f"- 一年內翻倍命中率：S9 {_p(s9['B']['p'])}，全部合格股票 {_p(o['base']['B'])}；"
         f"3 個月 +50%：S9 {_p(s9['A']['p'])}（全部 {_p(o['base']['A'])}）；一年 3 倍：S9 {_p(s9['C']['p'])}（全部 {_p(o['base']['C'])}）。",
         f"- **第一層＝7 族分數 ≥ {o['s_star']}**：一年內翻倍 {_p(o['t1']['B']['p'])}（S9 的 {_x(LA.lift(o['t1']['B'], s9['B']))} 倍），"
         f"平均每週 {_x(o['t1']['B']['per_week'], 1)} 檔；新進名單口徑 {_p(o['t1_new']['p'])}（S9 {_p(o['s9_new']['p'])}）。", "",
         "## 分數曲線（分數 ≥ s）", "",
         "| s | 每週檔數 | 一年翻倍 | 提升倍數 | 3 個月 +50% | 一年 3 倍 | 剛好 = s 的命中率 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for c in o["curve"]:
        L.append(f"| {c['s']} | {_x(c['ge']['per_week'], 1)} | {_p(c['ge']['p'])} | {_x(c['ge_lift'])} | {_p(c['ge_A'])} | "
                 f"{_p(c['ge_C'])} | {_p(c['eq']['p'])}（{c['eq']['n']:,}） |")
    L += ["", "## 7 族各自（S9 ∧ 該族）", "", "| 族 | 每週檔數 | 一年翻倍 | 提升倍數 |", "| --- | --- | --- | --- |"]
    for f in o["fam"]:
        L.append(f"| {f['name']} | {_x(f['per_week'], 1)} | {_p(f['p'])} | {_x(f['lift'])} |")
    L += ["", "## 單一條件（S9 ∧ 條件）", "",
          "| 條件 | 每週檔數 | 一年翻倍 | 提升倍數 | 2014–16 | 2017–19 | 新進名單 | 3 個月 +50% | 一年 3 倍 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in sorted(o["single"], key=lambda r: -(r["lift"] or 0)):
        tag = "（只列）" if r["key"] in LY.LIST_ONLY else ""
        L.append(f"| {LY.CNAME[r['key']]}{tag} | {_x(r['per_week'], 1)} | {_p(r['p'])} | {_x(r['lift'])} | {_x(r.get('IS1'))} | "
                 f"{_x(r.get('IS2'))} | {_x(r['new_lift'])} | {_p(r['A'])} | {_p(r['C'])} |")
    L += ["", "## 逐步加條件（對照）", ""]
    if o["greedy"]:
        L += ["| 步驟 | 加上 | 每週檔數 | 一年翻倍 | 2014–16 | 2017–19 |", "| --- | --- | --- | --- | --- | --- |"]
        for n, g in enumerate(o["greedy"], 1):
            L.append(f"| {n} | {LY.CNAME[g['add']]} | {_x(g['per_week'], 1)} | {_p(g['p'])} | {_x(g['subs'].get('IS1'))} | "
                     f"{_x(g['subs'].get('IS2'))} |")
    else:
        L.append("沒有條件同時做到兩個子期間提升倍數 ≥ 1.2、命中 ≥ 50、每週 ≥ 1 檔。")
    keys = o["pairs"]["keys"]
    if keys:
        L += ["", "## 兩兩交叉（單一條件提升倍數前 10 名；格子＝兩個條件同時成立的一年翻倍命中率／每週檔數）", "",
              "| | " + " | ".join(LY.CNAME[k] for k in keys) + " |", "| --- | " + " | ".join("---" for _ in keys) + " |"]
        for x in keys:
            cells = []
            for y in keys:
                if x == y:
                    cells.append("—")
                    continue
                c = o["pairs"]["cells"].get(f"{min(x, y)}|{max(x, y)}")
                cells.append("—" if not c or c["p"] is None else f"{_p(c['p'])}／{_x(c['per_week'], 1)}")
            L.append(f"| {LY.CNAME[x]} | " + " | ".join(cells) + " |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------- 2020–2022、2023 起
def stage_val() -> None:
    with CACHE.open("rb") as fh:
        tb = pickle.load(fh)
    isr = json.loads((REPORTS / "W3_is.json").read_text("utf-8"))
    LY, _, _ = LA.shared()
    T = LA.Tab(tb)
    s_star = isr["s_star"]
    allm = np.ones(len(T.d), dtype=bool)
    t1 = T.score >= s_star
    gm = allm.copy()
    for g in isr["greedy"]:
        gm &= T.col(g["add"])
    W = np.array(tb["W"])
    shape = tb["S9w"].shape
    t1w = LA.mask_weeks(T, t1, shape)
    per = {}
    for p, (a, b) in LA.PER.items():
        per[p] = {"s9": {L: T.stat(allm, a, b, L) for L in LA.LABS}, "t1": {L: T.stat(t1, a, b, L) for L in LA.LABS},
                  "t2": {L: T.stat(~t1, a, b, L) for L in LA.LABS}, "greedy": {L: T.stat(gm, a, b, L) for L in LA.LABS},
                  "base": {L: LA.base_rate(tb, L, a, b) for L in LA.LABS},
                  "s9_new": T.stat(T.new_entry(allm), a, b), "t1_new": T.stat(T.new_entry(t1), a, b),
                  "cover": {}}
        for L in ("B", "C"):
            ep = [e for e in tb["eps"][L] if a <= tb["cal"][e[1]] <= b]
            per[p]["cover"][L] = {"s9": LA.capture_w(ep, tb["S9w"], W, tb["Cw"], LA.EARLY[L]),
                                  "t1": LA.capture_w(ep, t1w, W, tb["Cw"], LA.EARLY[L])}
    cover_e = {"s9": LA.capture_w(tb["eps"]["E"], tb["S9w"], W, tb["Cw"], LA.EARLY["E"]),
               "t1": LA.capture_w(tb["eps"]["E"], t1w, W, tb["Cw"], LA.EARLY["E"])}
    yrs = {"s9": LA.per_year(T, allm), "t1": LA.per_year(T, t1)}
    v = per["VAL"]
    lift_v = LA.lift(v["t1"]["B"], v["s9"]["B"])
    years_ok = all(yrs["t1"][y]["p"] is not None and yrs["s9"][y]["p"] is not None and yrs["t1"][y]["p"] >= yrs["s9"][y]["p"]
                   for y in LA.YEARS_VAL)
    new_ok = (v["t1_new"]["p"] or 0) > (v["s9_new"]["p"] or 0)
    judge = {"lift": lift_v, "lift_ok": lift_v is not None and lift_v >= LA.JUDGE["lift"], "years_ok": years_ok,
             "new_ok": new_ok}
    judge["pass"] = judge["lift_ok"] and years_ok and new_ok
    single_v = LA.single_table(T, *LA.PER["VAL"])
    single_h = LA.single_table(T, *LA.PER["HO"])
    single_i = {r["key"]: r for r in isr["single"]}
    rev = [r["key"] for r in single_v if (single_i[r["key"]]["lift"] or 0) > 1 and (r["lift"] or 0) < 1]
    out = LA.to_json({"plan": "reports/W3_plan.md v1", "asof": time.strftime("%Y-%m-%d"), "s_star": s_star,
                      "greedy": [g["add"] for g in isr["greedy"]], "per": per, "years": yrs, "cover_e": cover_e,
                      "judge": judge, "single_val": single_v, "single_ho": single_h, "reversed": rev})
    (REPORTS / "W3_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    (REPORTS / "W3_results.md").write_text(md_val(out, isr), "utf-8")
    export(out, isr)
    log(f"[w3] 判定：{'過關' if judge['pass'] else '不過關'}（2020–2022 提升 {_x(lift_v)} 倍、三年都不反向 {years_ok}、"
        f"新進名單同方向 {new_ok}）")


def md_val(o: dict, isr: dict) -> str:
    LY, _, _ = LA.shared()
    j = o["judge"]
    L = ["# W3　第二層篩選：結果", "",
         "方法：`reports/W3_plan.md` v1（跑之前 commit）。第一層門檻與逐步加條件只用 2014–2019 定（`reports/W3_is.md`，"
         "看 2020–2022 之前 commit）。表格由 `scripts/run_w3.py --stage val` 產生。2023 年起只列數字、不參與判定。", "",
         f"**第一層＝7 族分數 ≥ {o['s_star']}。判定：{'過關' if j['pass'] else '不過關'}**"
         f"（2020–2022 一年翻倍命中率是 S9 的 {_x(j['lift'])} 倍，門檻 {LA.JUDGE['lift']}；三年都不比 S9 差：{'是' if j['years_ok'] else '否'}；"
         f"新進名單口徑同方向：{'是' if j['new_ok'] else '否'}）", "",
         "## 命中率（一年內翻倍；括號＝每週檔數）", "",
         "| 期間 | 第一層 | 第二層（S9 其餘） | S9 | 全部合格股票 | 逐步加條件（對照） | 第一層新進名單 | S9 新進名單 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p in LA.PER:
        x = o["per"][p]
        L.append(f"| {p} | {_p(x['t1']['B']['p'])}（{_x(x['t1']['B']['per_week'], 1)}） | {_p(x['t2']['B']['p'])}（{_x(x['t2']['B']['per_week'], 1)}） | "
                 f"{_p(x['s9']['B']['p'])}（{_x(x['s9']['B']['per_week'], 1)}） | {_p(x['base']['B'])} | {_p(x['greedy']['B']['p'])}（{_x(x['greedy']['B']['per_week'], 1)}） | "
                 f"{_p(x['t1_new']['p'])} | {_p(x['s9_new']['p'])} |")
    L += ["", "## 2020–2022 逐年（一年內翻倍）", "", "| 年 | 第一層 | S9 |", "| --- | --- | --- |"]
    for y in LA.YEARS_VAL:
        L.append(f"| {y} | {_p(o['years']['t1'][y]['p'])}（{o['years']['t1'][y]['n']:,}） | {_p(o['years']['s9'][y]['p'])}（{o['years']['s9'][y]['n']:,}） |")
    L += ["", "## 其他目標（第一層／S9／全部）", "", "| 期間 | 3 個月 +50% | 一年 3 倍 |", "| --- | --- | --- |"]
    for p in LA.PER:
        x = o["per"][p]
        L.append(f"| {p} | {_p(x['t1']['A']['p'])}／{_p(x['s9']['A']['p'])}／{_p(x['base']['A'])} | "
                 f"{_p(x['t1']['C']['p'])}／{_p(x['s9']['C']['p'])}／{_p(x['base']['C'])} |")
    L += ["", "## 涵蓋率（抓得早的段落比例：第一層／S9）", "", "| 期間 | 翻倍段 | 3 倍段 |", "| --- | --- | --- |"]
    for p in LA.PER:
        c = o["per"][p]["cover"]
        L.append(f"| {p} | {c['B']['t1']['early']}／{c['B']['s9']['early']}（共 {c['B']['s9']['n']}） | "
                 f"{c['C']['t1']['early']}／{c['C']['s9']['early']}（共 {c['C']['s9']['n']}） |")
    e = o["cover_e"]
    L += ["", f"5 年 10 倍股（2014 起，每檔取漲最多的一段）：第一層抓得早 {e['t1']['early']}／{e['t1']['n']} 檔，S9 {e['s9']['early']}／{e['s9']['n']} 檔。", ""]
    if o["reversed"]:
        L += ["2014–2019 提升倍數 > 1、2020–2022 卻 < 1 的條件：" + "、".join(LY.CNAME[k] for k in o["reversed"]) + "。", ""]
    L += ["## 單一條件：2014–2019 與 2020–2022 的提升倍數", "", "| 條件 | 2014–2019 | 2020–2022 | 2023 起 |", "| --- | --- | --- | --- |"]
    vi = {r["key"]: r for r in o["single_val"]}
    hi = {r["key"]: r for r in o["single_ho"]}
    for r in sorted(isr["single"], key=lambda r: -(r["lift"] or 0)):
        k = r["key"]
        L.append(f"| {LY.CNAME[k]} | {_x(r['lift'])} | {_x(vi[k]['lift'])} | {_x(hi[k]['lift'])} |")
    return "\n".join(L) + "\n"


def export(o: dict, isr: dict) -> None:
    """頁面用的小檔：第一層門檻、各層過去命中率、涵蓋率、判定。"""
    LY, _, _ = LA.shared()
    keep = ("p", "per_week", "n")

    def sm(x):
        return {k: x.get(k) for k in keep}

    per = {}
    for p, x in o["per"].items():
        per[p] = {"t1": {L: sm(x["t1"][L]) for L in LA.LABS}, "t2": {L: sm(x["t2"][L]) for L in LA.LABS},
                  "s9": {L: sm(x["s9"][L]) for L in LA.LABS}, "base": x["base"],
                  "cover": {L: {"t1": x["cover"][L]["t1"], "s9": x["cover"][L]["s9"]} for L in ("B", "C")}}
    res = {"v": 1, "asof": o["asof"], "plan": o["plan"], "main": "B", "s": o["s_star"], "judge": o["judge"],
           "fam": [[n, d] for n, d, _ in LY.FAMILY], "per": per, "years": o["years"], "cover_e": o["cover_e"],
           "greedy": o["greedy"]}
    OUT.write_text(json.dumps(LA.to_json(res), ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    log(f"[w3] → {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("is", "val"), required=True)
    args = ap.parse_args()
    stage_is() if args.stage == "is" else stage_val()
