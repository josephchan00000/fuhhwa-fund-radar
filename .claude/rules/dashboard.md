---
paths:
  - "arm/fund_dashboard.py"
  - "arm/printview.py"
  - "arm/treemap.py"
  - "scripts/gen_fund_dashboard.py"
  - "scripts/smoke_dashboard.py"
  - "scripts/check_print_layout.py"
---
改主儀表板（復華雷達）之前，先讀對應的頁：新聞卡 `wiki/main/news-cards.md`、資料更新時間 `wiki/main/freshness.md`、
市場溫度計 `wiki/main/macro-thermometer.md`、ETF 表 `wiki/main/etf-watch.md`、當日漲跌 `wiki/main/etf-daily-change.md`、
ETF 詳情 `wiki/main/etf-detail.md`、列印版 `wiki/main/print.md`、基金報酬 `wiki/main/fund-returns.md`。
- 當日漲跌寧缺勿錯：`chg_trust`／`_chg_cell` 判準雙向 `chg_asof != as_of`。
- 新增資料來源要兩處都加：`_freshness_view()` 逾期清單＋區塊標題 `_fresh_chip()`。
- 版面驗證看真的看得到（`offsetParent`／截圖），不看 class；新增 class 先 grep 撞名。
- 本地重建的 `dashboard/index.html` 絕不 commit。
