#!/usr/bin/env python3
"""景氣溫度・美股版研究檔與 LPPLS 歷史（docs/lab_heat_us_plan.md 第 15 節；規格 heatspec_us VER 1）。

  TZ=Asia/Taipei python3 scripts/run_heat_us.py --lppls
      LPPLS 每週泡沫信心的整段歷史（四個美股指數＋加權指數，numpy、4 個行程平行，約 6～8 分鐘）
      → data/lab/heat/us_lppls_{指數}、tw_lppls；之後每天由 fetch_heat_us.py 只補新的週。
  TZ=Asia/Taipei python3 scripts/run_heat_us.py
      四個指數的驗證（同台股頁：每一項與面向分數、五區、技術事件、單項分析、二階回歸；另加泡沫事件）
      → data/lab/heat_us_research.json。資料或規格改了才重跑；每天建頁只讀它。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import heatbubble as BB  # noqa: E402
from arm.lab import heatcalc_us as CU  # noqa: E402
from arm.lab import heatdata as HD  # noqa: E402
from arm.lab import heatspec_us as U  # noqa: E402

OUT = ROOT / "data" / "lab" / "heat_us_research.json"
CHUNK = 200                                   # 每個工作單位幾週
_G = None


def _init() -> None:
    global _G
    _G = BB.LPPLSGrid()


def _work(job: tuple) -> list:
    name, lnp, idxs, dates = job
    return [(name, d, BB.lppls_at(_G, lnp, i)) for i, d in zip(idxs, dates)]


def lppls_all(names: list[str]) -> None:
    """全部重算（和 heatbubble.lppls_series 同一套：每週最後一個交易日、同樣的擬合與取位）。"""
    src = {f"us_lppls_{k}": HD.load(f"us_px_{k}") for k in U.INDEX_ORDER}
    src["tw_lppls"] = BB.taiex_daily()
    jobs = []
    need = BB.LPPLSGrid.n_needed()
    for name in names:
        ds, lnp, want = BB.lppls_points(src[name])
        pos = {d: i for i, d in enumerate(ds)}
        todo = [d for d in want if pos[d] + 1 >= need]
        print(f"[lppls] {name}: {len(ds)} 個交易日 {ds[0] if ds else '—'}～{ds[-1] if ds else '—'}，要算 {len(todo)} 週", flush=True)
        for a in range(0, len(todo), CHUNK):
            part = todo[a:a + CHUNK]
            jobs.append((name, lnp, [pos[d] for d in part], part))
    t0 = time.time()
    out: dict[str, dict] = {n: {} for n in names}
    with Pool(4, initializer=_init) as pool:
        for k, res in enumerate(pool.imap_unordered(_work, jobs), 1):
            for name, d, v in res:
                if v is not None:
                    out[name][d] = v
            if k % 10 == 0 or k == len(jobs):
                print(f"[lppls] {k}/{len(jobs)} 份（{time.time() - t0:.0f}s）", flush=True)
    for name in names:
        HD.save(name, "lppls_grid", out[name])
        ks = sorted(out[name])
        print(f"[lppls] {name}: 存 {len(ks)} 週 {ks[0] if ks else '—'}～{ks[-1] if ks else '—'}", flush=True)


def research() -> None:
    t0 = time.time()
    R = CU.research_all()
    OUT.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(f"[heat-us] 研究檔 {OUT.relative_to(ROOT)}：{OUT.stat().st_size // 1024} KB，{time.time() - t0:.0f} 秒", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lppls", nargs="*", help="只算 LPPLS 歷史（不給名稱＝四個美股指數＋加權指數）")
    a = ap.parse_args()
    if a.lppls is not None:
        lppls_all(a.lppls or [f"us_lppls_{k}" for k in U.INDEX_ORDER] + ["tw_lppls"])
    else:
        research()


if __name__ == "__main__":
    main()
