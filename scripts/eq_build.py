"""個股報告建頁（docs/lab_equity_report_plan.md 第 11 節）。

    python3 scripts/eq_build.py                              # reports/eq → dashboard/rp/*.html（建頁流程會自動跑）
    python3 scripts/eq_build.py --one 報告.md --out 某處.html  # 只預覽一份（資料包＝同名 .facts.json）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import eqpage as P  # noqa: E402
from arm.lab import eqsite  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.one:
        md = Path(a.one)
        pack = json.loads(md.with_suffix(".facts.json").read_text(encoding="utf-8"))
        text = md.read_text(encoding="utf-8")
        html = P.ind_render(text, pack) if pack.get("kind") == "ind" else P.render(text, pack, {})
        out = Path(a.out or md.with_suffix(".html"))
        out.write_text(html, encoding="utf-8")
        print(f"寫入 {out}")
        return 0
    r = eqsite.build()
    print(f"個股報告 {len(r['companies'])} 份、產業報告 {len(r['industries'])} 份，改寫 {r['wrote']} 頁")
    return 0


if __name__ == "__main__":
    sys.exit(main())
