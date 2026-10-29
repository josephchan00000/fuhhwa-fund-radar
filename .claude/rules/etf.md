---
paths:
  - "arm/etfwatch.py"
  - "arm/etfholdings.py"
  - "arm/etfdiscover.py"
  - "arm/dayquotes.py"
  - "arm/connectors/issuers/**"
  - "scripts/fetch_etf_*.py"
  - "scripts/check_new_etfs.py"
  - "data/etf_upcoming.json"
---
改 ETF 抓取、合併、當日漲跌或即將登場之前，先讀 `wiki/main/etf-watch.md`、`wiki/main/etf-daily-change.md`、`wiki/main/etf-holdings.md`、`wiki/main/etf-upcoming.md`。
- 兩個欄位來自不同來源並排呈現時，先問是不是同一天的；漲跌判準雙向 `chg_asof != as_of`。
- 官方當日表呼叫一律帶 `retries=1, timeout=12`；測試一律 mock，不打外網。
- `merge_one`：同一揭露日重抓不可把 prev 洗成今天；來源切換時不判定新增／出清（`xsrc`）。
- 本家復華新檔不得列 `not_tracked`；pytest 見 seed／fallback 兩支紅＝當天就轉正。
- 容器內絕不跑 `fetch_etf_*.py`（會空轉 20+ 分鐘）。
