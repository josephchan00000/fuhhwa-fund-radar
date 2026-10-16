#!/usr/bin/env python3
"""策略健檢與自我改良（docs/lab_selfopt_plan.md）：每週一重跑 → data/lab/opt_research.json（入庫）。

第一部分：v3 長歷史面板的回測參考（財報、月營收的每期報酬、持有路徑分位數表、逐筆進場特徵），每日健檢查表用。
第二部分：optim v1 的 48 個改良候選全部重跑（配對比較、六項檢查、分級）；門檻與清單見 arm/lab/optim.py。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm import clock  # noqa: E402
from arm.lab import analyze, bt3d, health, optim, store  # noqa: E402


def main() -> None:
    t0 = time.time()
    P = bt3d.Panel()
    doc = health.build_ref_file(P)
    print(f"[opt] 回測參考 {sorted(doc['ref'])}（資料到 {doc['asof']}）、{time.time() - t0:.0f} 秒")
    keep: dict = {}
    analyze.run(keep=keep)
    doc["opt"] = optim.run_all(P, keep)
    today = clock.today_tw().isoformat()
    doc["opt"]["run"] = today
    doc["opt"]["asof_d"] = keep["D"].cal[-1] if keep.get("D") else None
    # 影子版本：先算登記中各版本的前瞻（同每日建頁的算法），再依本次分級決定誰進出（第 6 節）
    reg = optim.load_reg()
    sh = optim.shadow_daily(keep, reg=reg, res_doc=doc, today=today)
    fw_st = {(x["k"], x["c"]): x["st"] for x in sh["items"] if x.get("st")}
    doc["opt"]["reg_ch"] = optim.update_reg(reg, doc["opt"]["res"], today, fw_st)
    optim.save_reg(reg)
    store.write_json(health.REF_FILE, doc)
    n = {k: sum(1 for c in r.get("cands") or [] if c.get("tier") == optim.STRONG) for k, r in doc["opt"]["res"].items()}
    print(f"[opt] 改良候選完成、證據強 {n}、影子版本異動 {doc['opt']['reg_ch']}、共 {time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
