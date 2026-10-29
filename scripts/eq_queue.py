"""個股報告每週名單（每週六排程用；docs/lab_equity_report_plan.md 第 12 節）。

    TZ=Asia/Taipei python3 scripts/eq_queue.py          # 印這週要做的（最多 4 家）與排不到、不用做的
    TZ=Asia/Taipei python3 scripts/eq_queue.py --json   # 給程式讀
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm import clock  # noqa: E402
from arm.lab import eqqueue as Q  # noqa: E402


def main() -> int:
    r = Q.queue(clock.today_tw().isoformat())
    if "--json" in sys.argv[1:]:
        print(json.dumps(r, ensure_ascii=False))
        return 0
    print(f"{r['d']}：這週做 {len(r['todo'])} 家（最多 {r['max']} 家）")
    for c in r["todo"]:
        print(f"  做  {c['mk']} {c['code']} {c.get('name') or ''}：{c['why']}（{c['state']}）")
    for c in r["skip"]:
        print(f"  不做 {c['mk']} {c['code']} {c.get('name') or ''}：{c['why']}——{c['skip']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
