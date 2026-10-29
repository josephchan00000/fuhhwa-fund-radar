---
paths:
  - "arm/lab/page.py"
  - "arm/lab/analyze.py"
  - "arm/lab/store.py"
  - "arm/lab/market.py"
  - "arm/lab/collect.py"
  - "arm/lab/ledger.py"
  - "arm/lab/backtest.py"
  - "arm/lab/bt3*.py"
  - "arm/lab/advice.py"
  - "arm/lab/trades.py"
  - "arm/lab/optim.py"
  - "arm/lab/health.py"
  - "arm/lab/packtest.py"
  - "arm/lab/growth.py"
  - "arm/lab/strategy.py"
  - "arm/lab/v3*.py"
  - "arm/lab/stockviz.py"
  - "scripts/fetch_lab.py"
  - "scripts/backfill_lab.py"
  - "scripts/run_bt3.py"
  - "scripts/run_opt.py"
---
改籌碼雷達的資料、回測或個股頁之前，先讀 `wiki/lab/overview.md`，再看對應的頁：資料 `chip-data.md`、訊號與第一代策略 `chip-strategy.md`、
介面 `chip-ui.md`、回測方法 `backtest-v3.md`、逐筆交易 `trades.md`、策略健檢 `selfopt.md`、資料包策略 `strategy-pack.md`、長線 `growth-s5.md`（都在 `wiki/lab/`）。
- 規則變動都在看結果前寫定並 commit；要改策略＝新版本＋新起算日。
- 改任何策略回測，要確認 `tests/test_selfopt.py` 的不變式仍綠（共用 `bt3.engine`）。
- 容器內絕不跑 fetch_lab／backfill_lab 的抓取；`.ping/lab` 第一行只能寫模式。
- 幾支 JS 串成同一個 `<script>`，不得有同名函式或頂層 const。
