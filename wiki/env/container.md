# 容器的限制

> 時區、被擋的站與空轉、check_numbers 洗檔、git add 寫明路徑。
> 原始資料：CLAUDE.md「已知環境限制與防呆」段的時區、網路政策、`check_numbers.py` 三條；程式：`arm/clock.py`、`fetch_holdings.py`、`fetch_fund_news.py`、`arm/fundnews.save()`。
> 最後更新：2026-10-29
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

## 現在怎麼運作

- **時區**：本機/CI/雲端容器多為 UTC，台北清晨執行時 `date.today()` 會差一天。程式內一律用 `arm/clock.py` 的 `today_tw()/now_tw()/stamp_tw()`；
  跑腳本時帶 `TZ=Asia/Taipei` 雙保險。
- **雲端 Claude 容器的網路政策會擋部分站點**（曾實測被擋：`fhtrust.com.tw`、Google News RSS、PTT；proxy 回 CONNECT 403）。
  資料抓取一律交給正式區 `daily.yml`（見 [全部更新](../ops/daily-update.md) 的效率原則）。被擋時各支腳本的反應：
  - `fetch_holdings.py`：抓失敗跳過該檔、保留既有 `data/funds/*.json` 與 `_index.json`，勿手動清檔。
  - `fetch_fund_news.py`／`arm/fundnews.save()`：本次擷取「全空」且既有落檔非空 → 不覆寫。
  - NAV／持股快照抓不到就沿用既有快照，GitHub Actions（台北週一~六 07:15 cron；2026-07-20 前是 06:50）會自動補抓（[每日時點地圖](../ops/schedule.md)）。
  - 新聞查證用 WebSearch（伺服器端、不受 proxy 擋）；WebFetch 個別站點被擋就改用搜尋結果摘要。

## 不能改的規則

- **絕不可把非空的 `data/fund_news.json` 覆寫成全空**；若已誤覆寫，`git checkout -- data/fund_news.json` 還原。
- **根本不要在此容器跑三支抓取腳本**（`fetch_holdings.py`、`fetch_fund_news.py`、`fetch_etf_watch.py`）。若因故非跑不可，務必包 `timeout` 硬性上限
  （例 `timeout 60 python3 …`）避免空轉。
- commit 前用 `git add <明確路徑>`，少用 `git add -A`。跑過 `check_numbers.py` 之後請 `git status data/` 確認。

## 踩過的坑

- **`fetch_etf_watch.py` 在此容器會「空轉逾時」而非快速失敗（2026-07）**：etfinfo.tw 403 之外，報酬還逐檔對 stooq／yahoo／finmind／twse 各發請求，
  每請求 `timeout=25s`×retries、21 檔×4 源被擋時會累積卡 **20+ 分鐘**純空轉。修法：不在容器跑（上面的規則）。
- **`check_numbers.py` 在容器內跑會把 `data/factcheck.json` 洗成「全 ⚪」（2026-07-29）**：容器 proxy 擋 twse/taifex → 一項都核不到，
  CI 的 10 🟢 被覆寫成 0 🟢/11 ⚪ 並隨 commit 上板。修法：落檔防呆——**本次 0 🟢 0 🔴、而既有落檔曾核到過 → 不覆寫**。
  同一次也發現：是 `git add -A` 把 smoke-run 的 degraded 檔一起帶進 commit（所以有上面「寫明路徑」那條）。
