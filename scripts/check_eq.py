"""檢查個股報告或產業報告（docs/lab_equity_report_plan.md 第 9 節）：全 🟢 才能推。

    TZ=Asia/Taipei python3 scripts/check_eq.py reports/eq/tw/4958/2026-10-30.md
    TZ=Asia/Taipei python3 scripts/check_eq.py reports/eq/ind/tw-L000/2026-10-30.md
    不給路徑＝檢查 reports/eq 底下每一份。報告旁邊要有同名的 .facts.json（scripts/eq_facts.py 產）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import eqreport as R  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def one(p: Path) -> list[str]:
    fp = p.with_suffix(".facts.json")
    if not fp.exists():
        return [f"沒有資料包 {fp.name}"]
    pack = json.loads(fp.read_text(encoding="utf-8"))
    text = p.read_text(encoding="utf-8")
    return R.check_ind(text, pack) if pack.get("kind") == "ind" else R.check(text, pack)


def main() -> int:
    paths = [Path(x) for x in sys.argv[1:]] or sorted((ROOT / "reports" / "eq").glob("**/*.md"))
    bad = 0
    for p in paths:
        errs = one(p)
        print(f"{'🟢' if not errs else '🔴'} {p}")
        for e in errs:
            print(f"   - {e}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
