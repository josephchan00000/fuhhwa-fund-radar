---
paths:
  - "arm/lab/sig*.py"
  - "arm/lab/thermocal.py"
  - "arm/lab/simdays.py"
  - "arm/lab/robust.py"
  - "scripts/run_sig*.py"
  - "scripts/run_thermo.py"
  - "scripts/run_sim.py"
---
改訊號判定、溫度計或訊號頁之前，先讀 `wiki/lab/signals.md`（版本紀錄 `wiki/lab/signals-versions.md`、`wiki/lab/signals-versions-early.md`）。
- 規格 `sigspec.py` 先改、先 commit，才重跑研究；升版看要不要動 `RES_VER`。
- 狀態型每一天一樣重（VER 22），不要改回每一段平均；跌幅一律列最差一次（VER 24）。
- 後一段研究改掉前一段決定的前提時，先回頭問使用者。
- 市場頁（景氣頁）要在 sigpage 之前、同一個程序裡建（sigpage 讀它存的研究卡與指標）。
