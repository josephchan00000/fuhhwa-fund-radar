"""反向檢查研究檔：籌碼連續過熱、技術面轉空之後 3 個月的最大回撤（docs/lab_hotdd_plan.md 第 7 節）。

TZ=Asia/Taipei python3 scripts/run_hotch.py → data/lab/hotch_research.json（資料或規格改了才重跑）。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import hotch as X  # noqa: E402


def main() -> None:
    t0 = time.time()
    R = X.research()
    X.save_research(R)
    print(f"[hotch] 研究檔 {X.RESEARCH}（{time.time() - t0:.0f} 秒）")
    for h, v in R["primary"].items():
        print(f"  {h}: n={v.get('n')} ep={v.get('ep')} d={v.get('d')} p1={v.get('p1')} padj={v.get('padj')} ok={v.get('ok')}")


if __name__ == "__main__":
    main()
