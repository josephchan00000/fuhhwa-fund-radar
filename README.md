# 台指選擇權資料分支（claude/txo-data）

只放資料、不放程式；**絕不合併進 main**（同 `claude/ussx-data`）。程式在 main：`arm/lab/txodata.py`、`scripts/fetch_txo.py`，
由 `.github/workflows/txo_data.yml` checkout 到 `txodata/` 後寫入、commit 回這個分支。規劃：main 的 `docs/lab_txo_plan.md`。

- `bars/{年}/{日期}.json.gz`：期交所選擇權每筆成交（期交所只留 30 個交易日）整理成 TXO 日盤每分鐘一根
- `day/{年-月}.json.gz`：期交所選擇權每日交易行情（日盤）
- `idx/{年}/{日期}.json.gz`：證交所每 5 秒加權指數
- `state.json`：每種資料存到哪一天、缺哪些天
