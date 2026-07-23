#!/usr/bin/env python3
"""抓「總經・籌碼數據」（市場溫度計）→ data/macro_chips.json。

來源：Yahoo（VIX／美10年債／DXY／台幣／油金）＋ TWSE（三大法人、融資融券）＋
TAIFEX（外資台指期淨部位、選擇權 P/C 比）。每指標獨立降級：抓不到沿用既有落檔
（含 WebSearch 種子值），絕不洗空。

⚠ 本 Claude 容器 proxy 擋這些站——此腳本只在正式區 CI（daily_fund.sh）跑。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import macrochips  # noqa: E402


def main() -> int:
    print("抓取總經・籌碼數據（市場溫度計）…")
    doc = macrochips.fetch()
    macrochips.save(doc)
    n = sum(1 for k in macrochips.ALL_KEYS
            if (doc.get("series") or {}).get(k))
    print(f"✅ 完成：{n}/{len(macrochips.ALL_KEYS)} 指標有序列 → {macrochips.DATA_FP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
