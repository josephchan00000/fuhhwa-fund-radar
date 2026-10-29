---
paths:
  - "arm/lab/sxlive*.py"
  - "arm/lab/superx.py"
  - "arm/lab/super*spec.py"
  - "arm/lab/sx*spec.py"
  - "arm/lab/sepa*.py"
  - "arm/lab/vcp.py"
  - "arm/lab/layer.py"
  - "arm/lab/watchlist.py"
  - "scripts/run_sxlive*.py"
  - "scripts/run_super.py"
  - "scripts/run_sx_curve.py"
---
改新飆股或飆股研究之前，先讀 `wiki/lab/boom-live.md`、`wiki/lab/superstock.md`。
- 前瞻紀錄只增不改；每版規格寫在算出結果之前；`nav` 新的帳加在最後。
- page.py 只准 `from . import sxlive`、只讀 `LAST`；其他頁面模組不准出現 sxlive。
- 飆股研究沿用 W7 的逐年流程；書的方法別再用同一批資料換參數重跑。
