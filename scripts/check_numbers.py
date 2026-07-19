#!/usr/bin/env python3
"""高風險數字事實核對 CLI（SOP／CI 用）。

用法：TZ=Asia/Taipei python3 scripts/check_numbers.py [YYYY-MM-DD]
掃描當日 5 份報告（usnews v1/v2、twnews、macronews、macrocal），抽「句內含日期」的
高風險數字與官方 API 比對：
  🟢 相符　🔴 不符（exit 1，CI 擋下）　⚪ 官方不可得（不擋——本 Claude 容器 proxy
  會擋 twse/taifex 屬正常，真正把關在 CI 端）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm import clock, factcheck  # noqa: E402


def run(day: str | None = None) -> int:
    d = day or f"{clock.today_tw():%Y-%m-%d}"
    files = [ROOT / "reports" / "usnews" / f"{d}_v1.md",
             ROOT / "reports" / "usnews" / f"{d}_v2.md",
             ROOT / "reports" / "twnews" / f"{d}.md",
             ROOT / "reports" / "macronews" / f"{d}.md",
             ROOT / "reports" / "macrocal" / f"{d}.md"]
    year = int(d[:4])
    bad = checked = skipped = 0
    for fp in files:
        if not fp.exists():
            continue
        claims = factcheck.extract_claims(fp.read_text(encoding="utf-8"), year)
        for r in factcheck.check_claims(claims):
            c = r.claim
            if r.status == "⚪":
                skipped += 1
                continue
            checked += 1
            if r.status == "🔴":
                bad += 1
                print(f"🔴 {fp.name}｜{c.kind}｜報告值 {c.value:,.2f} vs 官方 {r.official:,.2f}"
                      f"（{c.day:%m/%d}）\n   ↳ {c.sentence[:120]}")
    if bad:
        print(f"[數字核對] 🔴 {bad} 項與官方不符（另 {checked - bad} 🟢、{skipped} ⚪）——不得發佈，須修正")
        return 1
    print(f"[數字核對] 🟢 {checked} 項與官方相符；⚪ {skipped} 項官方不可得（略過）")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))
