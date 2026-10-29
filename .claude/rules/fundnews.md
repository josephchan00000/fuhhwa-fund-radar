---
paths:
  - "arm/fundnews.py"
  - "arm/connectors/gnews.py"
  - "scripts/fetch_fund_news.py"
---
改復華新聞・社群之前，先讀 `wiki/main/fund-news.md`。
- 絕不把非空的 `data/fund_news.json` 覆寫成全空；單一平台全空沿用既有（`_carry_social`）。
- 不收負面文章；舊文重收先想「標題有沒有自帶年代」；外語判準用該語言獨有的字，用 Unicode 區段前先確認記號有沒有被共用。
- YouTube 加查詢組前先算額度帳；強基金只抓 `/forum` 總覽頁，別再加網址或換標頭。
- 抓取一律 `retries=1／timeout=12`，失敗印訊息本體。
