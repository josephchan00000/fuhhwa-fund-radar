# 容器的限制

> 時區、被擋的站與空轉、check_numbers 洗檔、git add 寫明路徑。
>
> 這一頁目前是從 CLAUDE.md 逐字搬來的（知識庫第一段），還沒整理；有出入時以 CLAUDE.md 為準。
> 改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產這一頁。

<!-- CLAUDE.md 第 589–601 行 -->
- **時區**：本機/CI/雲端容器多為 UTC，台北清晨執行時 `date.today()` 會差一天。
  程式內一律用 `arm/clock.py` 的 `today_tw()/now_tw()/stamp_tw()`；跑腳本時帶 `TZ=Asia/Taipei` 雙保險。
- **雲端 Claude 容器的網路政策會擋部分站點**（曾實測被擋：`fhtrust.com.tw`、Google News RSS、PTT；
  proxy 回 CONNECT 403）。被擋時：
  - `fetch_holdings.py` 已內建防呆：抓失敗跳過該檔、保留既有 `data/funds/*.json` 與 `_index.json`，勿手動清檔。
  - `fetch_fund_news.py`／`arm/fundnews.save()` 已內建防呆：本次擷取「全空」且既有落檔非空 → 不覆寫。
    **絕不可把非空的 `data/fund_news.json` 覆寫成全空**；若已誤覆寫，`git checkout -- data/fund_news.json` 還原。
  - NAV／持股快照抓不到就沿用既有快照，GitHub Actions（台北週一~六 06:50）會自動補抓。
  - 新聞查證用 WebSearch（伺服器端、不受 proxy 擋）；WebFetch 個別站點被擋就改用搜尋結果摘要。
  - **`fetch_etf_watch.py` 在此容器會「空轉逾時」而非快速失敗**（2026-07 踩坑）：etfinfo.tw 403 之外，
    報酬還逐檔對 stooq／yahoo／finmind／twse 各發請求，每請求 `timeout=25s`×retries、21 檔×4 源被擋時
    會累積卡 **20+ 分鐘**純空轉。**對策：依上方「效率原則」根本不要在此容器跑這三支抓取腳本**——一律交給
    正式區 `daily.yml`。若因故非跑不可，務必包 `timeout` 硬性上限（例 `timeout 60 python3 …`）避免空轉。
<!-- CLAUDE.md 第 693–697 行 -->
- **`check_numbers.py` 在容器內跑會把 `data/factcheck.json` 洗成「全 ⚪」**（2026-07-29 踩坑：
  容器 proxy 擋 twse/taifex → 一項都核不到，CI 的 10 🟢 被覆寫成 0 🟢/11 ⚪ 並隨 commit 上板）。
  已加落檔防呆：**本次 0 🟢 0 🔴、而既有落檔曾核到過 → 不覆寫**。跑完仍請 `git status data/` 確認。
  同型提醒：commit 前用 `git add <明確路徑>`，少用 `git add -A`——本次就是 `-A` 把 smoke-run 的
  degraded 檔一起帶進 commit。
