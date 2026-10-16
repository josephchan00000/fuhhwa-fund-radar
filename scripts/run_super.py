"""飆股研究（docs/lab_company_plan.md 第 4 節）：每週樣本 → 樣本內特徵表與規則 → 驗證期選規則 → 保留期只算一次。

規格事前寫定在 arm/lab/superx.py（VER）；資料或規格改了才重跑：
    TZ=Asia/Taipei python3 scripts/run_super.py            → data/lab/super_research.json
    TZ=Asia/Taipei python3 scripts/run_super.py --codes 300 → 只取前 300 檔試跑（不寫檔）
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm import clock  # noqa: E402
from arm.lab import bt3d, company, store, v3data  # noqa: E402
from arm.lab import packtest as PT  # noqa: E402
from arm.lab import superx as SX  # noqa: E402

OUT = "super_research.json"


def samples(n_codes: int | None = None, log=print) -> list[dict]:
    """每週最後一個交易日 × 合格股票 → {"c", "d", "f": 特徵, "y": 標籤}（2014 起）。"""
    t0 = time.time()
    P = bt3d.Panel()
    cal = P.cal
    codes = sorted(P.s)[:n_codes] if n_codes else sorted(P.s)
    fs = v3data.load_fs()
    eps = bt3d.mops_quarterly()
    rev = PT.load_rev()
    pxs = {c: SX.Px(P.s[c], cal) for c in codes}
    funds = {c: SX.Fund(company.quarters(fs.get(c), eps.get(c)), rev.get(c) or {}) for c in codes}
    qs, rf = SX.avail_index(cal)
    qitems = sorted((t, q) for q, t in qs.items())
    log(f"[super] 面板 {len(codes)} 檔、{len(cal)} 個交易日（{cal[0]}～{cal[-1]}），財報 {len(fs)} 檔，"
        f"{time.time() - t0:.0f} 秒")
    rows = []
    for i in SX.week_ends(cal):
        if cal[i] < SX.IS[0]:
            continue
        F = SX.feats_on(i, P, pxs, funds, qitems, rf, codes=codes)
        for c, f in F.items():
            y = {L: pxs[c].label(i, n, g) for L, (n, g) in SX.LABELS.items()}
            rows.append({"c": c, "d": cal[i], "f": {k: f.get(k) for k in SX.FK}, "y": y})
    log(f"[super] 樣本 {len(rows):,} 列（股票×週），{time.time() - t0:.0f} 秒")
    return rows


def _examples(rows: list, lab: str, conds, k: int = 8) -> list:
    """符合規則、之後真的變飆股的例子（同一檔只取第一次，依日期新到舊）。"""
    pr = SX.rule_pred([tuple(c) for c in conds])
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["d"]):
        y = r["y"].get(lab)
        if y and y["y"] and r["c"] not in seen and pr(r["f"]):
            seen.add(r["c"])
            out.append([r["c"], r["d"], SX._r(y["mx"], 3)])
    return out[-k:][::-1]


def run(rows: list, log=print) -> dict:
    per = {"is": [r for r in rows if SX.in_rng(r["d"], SX.IS)],
           "val": [r for r in rows if SX.in_rng(r["d"], SX.VAL)],
           "ho": [r for r in rows if SX.in_rng(r["d"], SX.HO)]}
    out = {"ver": SX.VER, "asof": clock.today_tw().isoformat(), "last": max(r["d"] for r in rows),
           "spec": {"labels": SX.LABELS, "liq_min": SX.LIQ_MIN, "cap_min": SX.CAP_MIN, "age_min": SX.AGE_MIN,
                    "is": SX.IS, "val": SX.VAL, "ho": SX.HO, "rule": SX.RULE, "qs": SX.QS},
           "n": {k: len(v) for k, v in per.items()},
           "codes": {k: len({r["c"] for r in v}) for k, v in per.items()}, "labels": {}}
    for L in SX.LABELS:
        t0 = time.time()
        ft = SX.feature_table(per["is"], L)
        conds = SX.candidate_conds(ft)
        rules, tried = SX.mine_rules(per["is"], L, conds)
        fin = SX.select_final(rules, per["val"], L)
        val_pass = sum(1 for r in rules if (r["val"]["lift"] or 0) >= SX.RULE["val_lift"] and r["val"]["n"] >= 50)
        for r in fin:
            r["is"].update(SX.eval_rule(per["is"], L, r["conds"]))
            r["ho"] = SX.eval_rule(per["ho"], L, r["conds"])          # 保留期：只在這裡算這一次
            r["txt"] = "、".join(SX.cond_text(c) for c in r["conds"])
            r["ex"] = _examples(per["ho"], L, r["conds"])
        union, base_d = {}, {}
        for k in ("is", "val", "ho"):
            B = SX.bits(per[k], L)
            m = 0
            for r in fin:
                m |= B.rule(r["conds"])
            n, pos = B.count(m)
            br = SX.base_rate(per[k], L)
            union[k] = {"n": n, "pos": pos, "p": SX._r(pos / n) if n else None,
                        "lift": SX._r(pos / n / br) if n and br else None,
                        **SX.dist([per[k][j] for j in SX.ones(m & B.valid)], L)}
            base_d[k] = SX.dist([per[k][j] for j in SX.ones(B.valid)], L)     # 全體（同一段期間所有合格股票週）
        yearly = []                                                            # 逐年：任一條規則 vs 全體（看穩不穩）
        B = SX.bits(rows, L)
        m = 0
        for r in fin:
            m |= B.rule(r["conds"])
        for y in sorted({r["d"][:4] for r in rows}):
            ym = B.year(y)
            n, pos = B.count(m & ym)
            n0, p0 = B.count(ym)
            if n0:
                yearly.append([y, n, pos, SX._r(pos / n) if n else None, SX._r(p0 / n0)])
        out["labels"][L] = {"base": {k: SX._r(SX.base_rate(v, L)) for k, v in per.items()}, "base_dist": base_d,
                            "ftab": ft, "conds": conds, "tried": tried, "is_pass": len(rules), "val_pass": val_pass,
                            "rules": fin, "union": union, "yearly": yearly}
        log(f"[super] 標籤 {L}：候選條件 {len(conds)}、試了 {tried} 個組合、樣本內通過 {len(rules)}、"
            f"驗證期通過 {val_pass}、定案 {len(fin)}，{time.time() - t0:.0f} 秒")
    out["checks"] = {k: SX.check_stats(v) for k, v in (("all", rows), *per.items())}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", type=int, default=None, help="只取前 N 檔試跑（不寫檔）")
    a = ap.parse_args()
    t0 = time.time()
    rows = samples(a.codes)
    res = run(rows)
    if a.codes:
        print(f"[super] 試跑完成（{time.time() - t0:.0f} 秒），不寫檔")
        return 0
    store.write_json(OUT, res)
    print(f"[super] 寫入 data/lab/{OUT}（{time.time() - t0:.0f} 秒）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
