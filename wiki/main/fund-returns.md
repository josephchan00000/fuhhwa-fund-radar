# 基金多期報酬

> 鉅亨每日基準覆蓋層、自建 NAV 序列算 1 週／1 月。
> 原始資料：CLAUDE.md「基金多期報酬『每日基準』覆蓋層」「基金總覽『1週／1月』報酬」兩段；
> 程式：`arm/connectors/cnyesfund.py`、`arm/fundnav.py`、`fetch_holdings.py`、`scripts/backfill_fund_nav.py`
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

基金總覽的多期報酬由儀表板 `overview_rows()` 逐欄 fallback：**鉅亨每日值 → 官網月底值**；1週/1月再多一層 → 自建 NAV 序列自算。
鉅亨沒有 1週／2年／3年獨立鍵：1週回退自建 NAV 序列自算、3年回退官網月底值——混合基準已在總覽副標註明。總覽區有「多期報酬」鮮度 chip。

### 鉅亨每日基準覆蓋層（`arm/connectors/cnyesfund.py`，Tier B）

- **為什麼要**：官網 `/api/fund` 的多期報酬（roiY2D/roi3m/roi1y…）是「月底基準」——git 史實測 NAV 天天動、YTD/1y 十四天不變（皆上月底值），
  使用者已明確要求「每日基準」。
- **取數路徑＝「釘選 cnyesId → 直取詳情頁」**：`data/cnyes_fund_map.json`（**入庫**）存全部 25 檔的 cnyesId（WebSearch 逐檔查回並核對 share class）；
  詳情頁 `fund.cnyes.com/detail/x/{cnyesId}/` 的 HTML 以 `_objects_from_html()` 平衡物件掃描抽資料（頁面無 __NEXT_DATA__、狀態以他形內嵌）。
- **詳情頁實際鍵**：`return1Month/3Month/6Month/1Year/returnYTD`＋`nav/priceDate/change(Percent)`；無 1週／2年／3年獨立鍵；
  複合鍵 `returns` 內部結構每日於 CI 日誌印出（debug 首檔），未來可再收斂。
- **寫入**：`fetch_holdings.py` 抓完官網後 `cnyesfund.apply_overlay()`：寫 `returns_daily`＋`returns_daily_asof` 進 `data/funds/*.json`；
  鉅亨 NAV 日**較新**時一併覆蓋 nav（標 `nav_src="cnyes"`）。
- 整層失敗只是回退官網值，不會壞版面。
- **新增基金時**：WebSearch 查其鉅亨詳情頁 URL、把 cnyesId 補進 map 檔即可。

### 「1週／1月」：自建 NAV 序列（`arm/fundnav.py`）

官網 `/api/fund` 多期報酬**沒有 1週/1月**，所以用自建 NAV 序列自算：
- 資料層 `data/fund_nav_history.json`（**必須入庫**，`.gitignore` 已加例外——跨日累積的持久層）；`fetch_holdings.py` 抓完自動 `fundnav.record()` 累積；
  斷史時 `scripts/backfill_fund_nav.py` 走 git 歷史（`data/funds/_index.json` 每日快照）重建。
- 計算有「基準日須接近目標日」防呆（1週 tol=5 天、1月 tol=10 天），史料不足回 None → 儀表板顯示 —。
- 序列自 2026/07/01 起，「1月」欄約 2026/08 初起自然補齊，非資料壞掉。

## 不能改的規則

- cnyesfund 的「釘選 cnyesId → 直取詳情頁」是 2026-07-15 歷經 6 輪 CI 收斂的**最終架構**，勿走回頭路（死路見下）。
- **此容器 proxy 擋 cnyes（CONNECT 403）**——用 CI 日誌（`mcp__github__get_job_logs`）驗證與迭代，勿在本容器嘗試打 cnyes。
- `data/cnyes_fund_map.json`、`data/fund_nav_history.json` 都要入庫；NAV 序列沒入庫的話 CI 從零開始，1週／1月會整片變 —（同 etf_watch 的坑，見 [ETF 數據追蹤表](etf-watch.md)）。
- 舊 `arm/navhist.py` 是 ETF 管線的 sqlite 模組，與此無關、勿混用。

## 踩過的坑

- **鉅亨的死路（CI 實測，勿再試）**：`fund.api.cnyes.com` 全路徑 404；`gfe-fund.cnyes.com` 任何路徑都回同一張 XHTML 舊頁；
  搜尋頁 `fund.cnyes.com/search/` SSR 不吃 query（任何 keyword 都回同 20 筆熱門清單，名稱比對必零命中）。

## 歷史

- 2026-07-15：同日新增兩件——鉅亨每日基準覆蓋層（歷經 6 輪 CI 收斂）；基金總覽 1週／1月 改由自建 NAV 序列自算。
