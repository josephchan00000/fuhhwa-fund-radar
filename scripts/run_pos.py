"""部位參考的回測（docs/lab_crash_plan.md 第 18 節；規格 arm/lab/posspec.py）→ data/lab/pos_research.json。

TZ=Asia/Taipei python3 scripts/run_pos.py（資料或規格改了才重跑；★ 清單讀訊號總覽研究檔，先跑 scripts/run_sig.py）。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.lab import pos, sigcat  # noqa: E402


def main() -> None:
    t0 = time.time()
    F = sigcat.frames()
    for mk, f in F.items():
        I = f.get("IB")
        if I is not None and list(I["cal"]) != list(f["cal"]):
            raise SystemExit(f"{mk}：大跌後檢查的日曆和訊號總覽不同")
    print(f"[pos] 資料 {time.time() - t0:.0f}s")
    R = pos.research(F)
    pos.save(R)
    print(f"[pos] 寫入 {pos.RES}，共 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
