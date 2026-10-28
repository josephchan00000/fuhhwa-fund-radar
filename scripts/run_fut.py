"""台指期早盤策略的研究（arm/lab/futres.py；docs/lab_fut_plan.md）：重算 data/lab/fut_research.json、印摘要。

每天 CI 抓完台指期逐筆（scripts/fetch_fut.py）之後跑；只讀已存的資料、不發任何請求，幾秒就好。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import futres as R  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true", help="只印、不寫檔")
    a = ap.parse_args()
    doc = R.run()
    la = doc["lookahead"]
    m = la["main"]
    print(f"台指期早盤（偷看版，規格 VER {doc['spec_ver']}）：算得出落差的交易日 {la['n_days']} 天、到 {doc['asof']}")
    if m.get("n"):
        print(f"  照規則做 {m['n']} 筆：平均每筆 {m['mean']:+.2f} 點、中位數 {m['median']:+.2f}、賺錢 {m['win']:.0%}、"
              f"方向亂選平均不比它差的比例 {la['placebo_p']}")
    else:
        print("  照規則做 0 筆（門檻要先累積 10 天）")
    for k, v in la["compare"].items():
        if v.get("n"):
            print(f"  {k}：{v['n']} 筆、平均 {v['mean']:+.2f}、賺錢 {v['win']:.0%}")
    for c in la["catchup"]["all"]:
        print(f"  到 {c['at']}：{c['n']} 天、和 E 同方向 {c['agree']}、順著 E 平均 {c['mean']} 點")
    print(f"  判定：{la['verdict']}（滿 {R.P.JUDGE['days']} 天才判定）")
    skips = [r for r in la["days"] if "skip" in r]
    for r in skips:
        print(f"  {r['d']} 沒算：{r['skip']}")
    rt = doc["realtime"]
    rm, er = rt["main"], rt["compare"].get("est_err") or {}
    print(f"台指期早盤（即時版，從 {rt.get('start')} 起取樣）：算得出落差的交易日 {rt['n_days']} 天、判定：{rt['verdict']}")
    if rm.get("n"):
        print(f"  照規則做 {rm['n']} 筆：平均每筆 {rm['mean']:+.2f} 點、中位數 {rm['median']:+.2f}、賺錢 {rm['win']:.0%}、"
              f"方向亂選平均不比它差的比例 {rt['placebo_p']}")
    if er.get("n"):
        print(f"  試撮估算 − 偷看版開盤水準：{er['n']} 天、平均 {er['mean']:+.2f} 點、平均差 {er['mae']:.2f} 點")
    for r in rt["days"]:
        if "skip" in r:
            print(f"  {r['d']} 沒算：{r['skip']}")
        else:
            print(f"  {r['d']}：比重 {r['cov']:.0%}（{r['n']} 檔，太舊 {r['stale']}、沒試撮價 {r['nopx']}）")
    if not a.no_write:
        print("  寫檔" if R.write(doc) else "  內容沒變、不改寫")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
