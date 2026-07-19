#!/usr/bin/env python3
"""高風險數字事實核對 CLI（SOP／CI 用）。

用法：TZ=Asia/Taipei python3 scripts/check_numbers.py [YYYY-MM-DD] [--strict]
掃描當日 5 份報告，抽「句內含日期」的高風險數字與官方 API 比對，並把結果寫入
data/factcheck.json（儀表板「資料更新時間」區顯示核對狀態）。

**發佈策略（2026-07-20 使用者指示：不可因防線過硬導致什麼都沒更新）**：
  預設一律 exit 0——🔴 不擋發佈，改走「照常發佈＋儀表板紅色警示＋主會話驗證時立即修正重推」。
  `--strict` 才會在 🔴 時 exit 1（僅供手動把關，CI 不用）。
  🟢 相符　🔴 不符（落檔＋警示）　⚪ 官方不可得（本 Claude 容器 proxy 擋 twse/taifex 屬正常）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm import clock, factcheck  # noqa: E402

OUT = ROOT / "data" / "factcheck.json"


def run(day: str | None = None, strict: bool = False) -> int:
    d = day or f"{clock.today_tw():%Y-%m-%d}"
    files = [ROOT / "reports" / "usnews" / f"{d}_v1.md",
             ROOT / "reports" / "usnews" / f"{d}_v2.md",
             ROOT / "reports" / "twnews" / f"{d}.md",
             ROOT / "reports" / "macronews" / f"{d}.md",
             ROOT / "reports" / "macrocal" / f"{d}.md"]
    year = int(d[:4])
    items = []
    for fp in files:
        if not fp.exists():
            continue
        claims = factcheck.extract_claims(fp.read_text(encoding="utf-8"), year)
        for r in factcheck.check_claims(claims):
            c = r.claim
            items.append({"status": r.status, "file": fp.name, "kind": c.kind,
                          "claimed": c.value, "official": r.official,
                          "day": f"{c.day:%m/%d}", "sentence": c.sentence[:160]})
    green = sum(1 for i in items if i["status"] == "🟢")
    red = sum(1 for i in items if i["status"] == "🔴")
    skipped = sum(1 for i in items if i["status"] == "⚪")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"date": d, "as_of": clock.stamp_tw(), "green": green,
                               "red": red, "skipped": skipped, "items": items},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    for i in items:
        if i["status"] == "🔴":
            print(f"🔴 {i['file']}｜{i['kind']}｜報告值 {i['claimed']:,.2f} vs 官方 "
                  f"{i['official']:,.2f}（{i['day']}）\n   ↳ {i['sentence'][:120]}")
    if red:
        print(f"[數字核對] 🔴 {red} 項與官方不符（另 {green} 🟢、{skipped} ⚪）——"
              "照常發佈但儀表板已標警示，請立即修正該數字後重推")
        return 1 if strict else 0
    print(f"[數字核對] 🟢 {green} 項與官方相符；⚪ {skipped} 項官方不可得（略過）")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--strict"]
    sys.exit(run(args[0] if args else None, strict="--strict" in sys.argv))
