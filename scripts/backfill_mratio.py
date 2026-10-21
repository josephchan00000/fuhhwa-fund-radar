#!/usr/bin/env python3
"""台股融資維持率回補（arm/lab/mratio.py；docs/lab_expert_plan.md 第 10 節）。只在 CI 跑：本容器擋 FinMind。

  python3 scripts/backfill_mratio.py --budget-min 50     做到時間或額度用完就存檔（可以重跑續做）
  python3 scripts/backfill_mratio.py --status            印進度：第一行 DONE／STUCK／LEFT n
  python3 scripts/backfill_mratio.py --series            只重算維持率序列（data/lab/heat/mratio）

第一輪把要做的代號清單（證交所上市的股票、ETF、存託憑證，含已終止上市）存進 data/lab/mratio/uni，之後各輪沿用；
回補截止日 END＝第一輪開始時最新的融資合計日（之後的日子由官方分片算）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import heatdata as HD  # noqa: E402
from arm.lab import mratio as M  # noqa: E402
from arm.lab import store  # noqa: E402


def log(msg: str) -> None:
    print(msg, flush=True)


def build_universe() -> dict:
    """要做的代號：[(代號, 證交所上市起日或 None, 終止上市日或 None)]，依現在的融資張數由大到小（已終止上市的排最後）。"""
    pacer = M.Pacer()
    today = date.today().isoformat()
    info = M.fm_list("TaiwanStockInfo", pacer)
    dl = M.fm_list("TaiwanStockDelisting", pacer)
    twse_off = M.twse_delisted()
    m_tw = next((doc.get("m_tw") for _, doc in reversed(store.load("mkt", last=7)) if doc.get("m_tw")), None) or {}
    uni = M.universe(info, dl, twse_off, listed=_listed(), m_tw=m_tw, today=today)
    log(f"[mratio] 代號清單：{uni['n']}（上市中 {uni['n_live']}、已終止上市 {uni['n_off']}；"
        f"FinMind 總覽 {len(info)} 列、下市櫃表 {len(dl)} 列、證交所終止上市 {len(twse_off)} 列）")
    return uni


def _listed() -> dict[str, str]:
    try:
        return json.loads((ROOT / "data" / "stock_industry.json").read_text("utf-8")).get("listed") or {}
    except Exception:                                         # noqa: BLE001
        return {}


def status() -> str:
    uni = store.read(M.KIND, "uni")
    done = M.load_done()
    agg = M.load_agg()
    if not uni:
        return "LEFT ?（還沒有代號清單）"
    todo = [u for u in uni["codes"] if u[0] not in done["codes"] and u[0] not in done["skip"]]
    runs = done.get("runs") or []
    head = "DONE" if not todo else ("STUCK" if len(runs) >= 2 and all(r.get("done", 0) == 0 and not r.get("quota")
                                                                      for r in runs[-2:]) else f"LEFT {len(todo)}")
    s = M.build_series(agg, HD.load("margin"), {})
    cov = [v[1] for v in s.values()]
    lines = [head,
             f"代號 {len(uni['codes'])}：做完 {len(done['codes'])}、跳過 {len(done['skip'])}、還沒做 {len(todo)}、失敗中 {len(done['fail'])}",
             f"截止日 {agg.get('end')}；合計有 {len(agg.get('d') or {})} 天"]
    if cov:
        ks = sorted(s)
        lines.append(f"維持率 {len(s)} 天（{ks[0]}～{ks[-1]}），涵蓋率中位 {sorted(cov)[len(cov) // 2]:.3f}、最低 {min(cov):.3f}")
    if runs:
        lines.append(f"最近一輪：{runs[-1]}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=float, default=50)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--series", action="store_true")
    a = ap.parse_args()
    if a.status:
        print(status())
        return
    if a.series:
        log(f"[mratio] 維持率序列：{M.update_series()} 筆改動")
        return
    t0 = time.time()
    uni = store.read(M.KIND, "uni")
    if not uni:
        uni = build_universe()
        store.write(M.KIND, "uni", uni)
    agg = M.load_agg()
    end = agg.get("end") or max(HD.load("margin"))
    left = a.budget_min * 60 - (time.time() - t0)
    st = M.backfill([tuple(u) for u in uni["codes"]], end=end, budget_s=max(60.0, left))
    done = M.load_done()
    done.setdefault("runs", []).append({"t": time.strftime("%Y-%m-%d %H:%M"), **st})
    done["runs"] = done["runs"][-8:]
    store.write(M.KIND, "done", done)
    log(f"[mratio] 這一輪：{st}")
    log(f"[mratio] 維持率序列：{M.update_series()} 筆改動")


if __name__ == "__main__":
    main()
