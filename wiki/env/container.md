# 容器的限制

> 時區、被擋的站與空轉、check_numbers 洗檔、git add 寫明路徑。
> 原始資料：CLAUDE.md「已知環境限制與防呆」段的時區、網路政策、`check_numbers.py` 三條；程式：`arm/clock.py`、`fetch_holdings.py`、`fetch_fund_news.py`、`arm/fundnews.save()`。
> 最後更新：2026-11-01
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

## 現在怎麼運作

- **時區**：本機/CI/雲端容器多為 UTC，台北清晨執行時 `date.today()` 會差一天。程式內一律用 `arm/clock.py` 的 `today_tw()/now_tw()/stamp_tw()`（2026-11-01 體檢第 9 條把 `arm/`、`scripts/` 裡直接取今天的 54 處（28 個檔）都換掉了；`smoke_dashboard.py` 不載 arm，自己用 UTC+8 算）；
  跑腳本時帶 `TZ=Asia/Taipei` 雙保險。
- **雲端 Claude 容器的網路政策會擋部分站點**（曾實測被擋：`fhtrust.com.tw`、Google News RSS、PTT；proxy 回 CONNECT 403）。
  資料抓取一律交給正式區 `daily.yml`（見 [全部更新](../ops/daily-update.md) 的效率原則）。被擋時各支腳本的反應：
  - `fetch_holdings.py`：抓失敗跳過該檔、保留既有 `data/funds/*.json` 與 `_index.json`，勿手動清檔；只有持股頁抓不到（出錯或解析 0 筆）時，
    前十大、四種配置、持股基準日沿用上一次、淨值照新的（持股基準日不前進就是過期標記，另記 `holdings_error`；2026-11-01 起，之前會寫成空的）。
  - `fetch_fund_news.py`／`arm/fundnews.save()`：本次擷取「全空」且既有落檔非空 → 不覆寫。
  - NAV／持股快照抓不到就沿用既有快照，GitHub Actions（台北週一~六 07:15 cron；2026-07-20 前是 06:50）會自動補抓（[每日時點地圖](../ops/schedule.md)）。
  - 新聞查證用 WebSearch（伺服器端、不受 proxy 擋）；WebFetch 個別站點被擋就改用搜尋結果摘要。
- **寫落檔**（2026-11-01 起）：跨天要沿用的檔（前瞻紀錄、累積序列、抓不到時沿用的快照）用 `arm/fileio.py` 的 `write_text`／`write_bytes`——先寫到同資料夾的暫存檔 `.{檔名}.{行程編號}.tmp` 再換名，CI 的 `timeout` 剛好在寫檔時砍掉程式，原本的檔還是完整的。
  七本前瞻紀錄（基金淨值歷史、交易計畫、每天的推播紀錄、今年逐月、美股強勢品質股每週紀錄、策略候選試用、飆股前瞻記錄）要寫回時用 strict 讀：檔案在但讀不起來就停下報錯（CI 印 `::error::`），不當成空的從頭記；頁面顯示照樣當成沒有。

## 不能改的規則

- **絕不可把非空的 `data/fund_news.json` 覆寫成全空**；若已誤覆寫，`git checkout -- data/fund_news.json` 還原。
- **根本不要在此容器跑三支抓取腳本**（`fetch_holdings.py`、`fetch_fund_news.py`、`fetch_etf_watch.py`）。若因故非跑不可，務必包 `timeout` 硬性上限
  （例 `timeout 60 python3 …`）避免空轉。
- commit 前用 `git add <明確路徑>`，少用 `git add -A`。跑過 `check_numbers.py` 之後請 `git status data/` 確認。
- 前瞻紀錄讀到壞檔停下報錯時：從 git 歷史還原那個檔（`git log -- <檔>` 找最後一個好的版本），不要刪掉讓它從頭記。暫存檔 `*.tmp` 由 `.gitignore` 擋；workflow 用 `git add -f data/lab` 整個資料夾加時仍會被加進去，看到可以刪。

## 踩過的坑

- **`fetch_etf_watch.py` 在此容器會「空轉逾時」而非快速失敗（2026-07）**：etfinfo.tw 403 之外，報酬還逐檔對 stooq／yahoo／finmind／twse 各發請求，
  每請求 `timeout=25s`×retries、21 檔×4 源被擋時會累積卡 **20+ 分鐘**純空轉。修法：不在容器跑（上面的規則）。
- **`check_numbers.py` 在容器內跑會把 `data/factcheck.json` 洗成「全 ⚪」（2026-07-29）**：容器 proxy 擋 twse/taifex → 一項都核不到，
  CI 的 10 🟢 被覆寫成 0 🟢/11 ⚪ 並隨 commit 上板。修法：落檔防呆——**本次 0 🟢 0 🔴、而既有落檔曾核到過 → 不覆寫**。
  同一次也發現：是 `git add -A` 把 smoke-run 的 degraded 檔一起帶進 commit（所以有上面「寫明路徑」那條）。
