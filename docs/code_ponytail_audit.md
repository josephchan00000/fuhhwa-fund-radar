# 程式體檢報告（ponytail 第二段，2026-11-01，只出報告、不改程式）

> `docs/code_ponytail_plan.md` 第 4 節第 2 段。依 ponytail 的順序看：正確 → 安全 → 撐得住預期負載 → 有測試 → 速度 → 精簡。
> 每一條都附具體情境（「這樣的情況會得到這個錯的結果」）與出處（檔案:行）；說某段沒人用之前都全專案搜尋過（程式、測試、workflow、文件、字串）。
> 地圖見 `docs/code_ponytail_map.md`。看的是 main（PR #424 之後）。使用者 2026-11-01 確認：舊的本機流程「沒在跑了」。

## 結論

- **必修 2 條**：基金前十大持股、美股強勢品質股的「明天開盤賣」提醒，來源當天抓不到時會被寫成空的。
- **該修 5 條**：寫檔中途被砍會留半個檔（而且幾本前瞻紀錄讀到壞檔會從頭記）、新聞與美國內部人資料的局部洗空、三個由別的檔算出來的結果在來源讀不到時寫空、舊的本機流程整套拿掉。
- **可以更好 3 條**：沒人用的小東西、日期寫法、合併前自動跑測試。
- **沒有問題的**：安全（公開的申請單只收嚴格格式的代號、只有擁有者能觸發動作；金鑰不印不存；workflow 的指令沒有把外人可控的文字直接塞進 shell）、
  撐得住（約 30 人看的網站＋每天十幾班 CI，頁面有 gzip 與重新驗證快取）、測試（正式流程 203 個模組只有 14 個沒有直接被測試引用，都很小）、
  速度（全部測試約 4 分鐘；每週核對 35 分鐘在週末跑）、時區（14 支 workflow 都設台北時間）、數字核對在容器跑會洗檔那條已經有保護。

## 必修

### 1. 基金持股頁抓不到時，前十大持股與配置被寫成空的
- **出處**：`scripts/fetch_holdings.py:61` 無條件寫 `data/funds/{id}.json`；`arm/connectors/fhfund.py:263-266` 持股頁出錯時回傳空清單、`:227` 頁面改版找不到持股也只印一行。
- **情境**：復華官網的持股頁某天出錯或改版 → 每檔基金的 `top_holdings`、資產／國家／產業配置都變 `[]`、持股基準日變空 → 首頁的前十大與配置整片空白；
  「前十大簡介缺口」還會誤報 0 檔。每天早上和盤後三班都會跑，任何一班碰到就洗掉。
- **修法**：持股或配置抓到 0 筆（或出錯）時，那幾欄沿用舊檔；只更新抓到的部分（淨值等）。加一個模擬「持股頁出錯」的小測試。約 10 行。
- **不修會怎樣**：違反鐵則「非空的落檔絕不覆寫成空」；空白會一直到下一班成功才恢復。

### 2. 美股強勢品質股「跌破 50 日線、明天開盤賣」的提醒，Yahoo 抓不到時會被洗掉
- **出處**：`arm/lab/ussxqm.py` 的 `watch()`（抓不到的那一檔只記「抓不到日線」）與 `save_watch()`（照寫）；`scripts/fetch_ussx_watch.py:38-39`；推播讀它（`arm/lab/valog.py`）。
- **情境**：前一天已經判定「X 收盤跌破 50 日線→明天開盤賣」，隔天那一班 Yahoo 被限流 → 新檔 `sell: []` 照寫 → 選股頁與 06:35 推播少了那一行賣出。
  程式正常結束，workflow 的「沿用既有落檔」提示也不會出現。
- **修法**：哪一檔抓不到，就沿用上一次那一檔的結果（含已經觸發的賣出）；全部抓不到就不寫。加一個小測試。約 10 行。
- **不修會怎樣**：最需要照做的那一天（要賣）反而可能看不到提醒。

## 該修

### 3. 寫檔中途被砍會留下半個檔，而且幾本前瞻紀錄讀到壞檔會從頭記
- **出處**：全專案沒有「先寫暫存檔再換名」的寫法（`write_text` 151 處、`os.replace` 0 處）；workflow 多數抓取步驟是 `timeout N … || echo 沿用既有落檔`，
  被砍之後下一步照樣 commit（例 `afterhours_refresh.yml:101-124`）。讀檔失敗就當成空的：`arm/fundnav.py:41`（基金淨值歷史）、`arm/lab/core.py:569`（交易計畫前瞻紀錄）、
  `arm/lab/valog.py:472`（每天的推播與驗證紀錄）、`arm/lab/ytd.py:185`（今年逐月上線紀錄）。
- **情境**：某一步剛好在寫 `data/lab/val_log.json` 時被 timeout 砍掉 → 檔案只剩一半 → 被 commit 進 main → 下一班讀不起來、當成空的，從今天重新記 → 前瞻紀錄的歷史不見（只能從 git 歷史手動救回）。
  機率低（寫檔只要幾毫秒），但一旦發生是安靜的，而且會一路錯下去。
- **修法**：一個小函式「寫到同資料夾的暫存檔，寫完再換名」，用在 CI 會寫的落檔與紀錄；四本紀錄讀檔失敗（檔案存在但讀不起來）時停下報錯，不要當空的重寫。約 30 行。

### 4. Google 新聞抓不到、但 PTT／YouTube 有抓到時，各基金新聞被寫成空的
- **出處**：`arm/fundnews.py:1396-1410`：保護只管「整份全空」，社群另有逐平台沿用（`_carry_social`），新聞沒有；`arm/connectors/gnews.py:42-43` 出錯一律回空。
- **情境**：Google 新聞被限流、PTT 正常 → 整份不是全空 → 品牌新聞只剩媒體 RSS、每檔基金的新聞都變 `[]` → 照寫、commit。
- **修法**：比照社群，Google 新聞這一路整個沒有回來時，沿用前一次的新聞項目。約 15 行。

### 5. 美國內部人買賣季資料：SEC 改了欄位名稱時，那三個月被換成空的、而且不會重抓
- **出處**：`arm/lab/insider.py:370-379`（季資料整月取代）、`:395-403`（只檢查下載成功，解析出 0 筆照寫，並記成這一季做完）。
- **情境**：SEC 改了表格的欄位名 → 解析出 0 筆 → 三個月的內部人資料被換成空的 → 這一季記成做完、以後不會再抓 → 美股景氣頁的內部人那一項少了三個月。
- **修法**：解析出 0 筆就跳過、不記成做完、印警告。約 3 行。

### 6. 三個由別的檔算出來的結果，來源讀不到時會寫成空的
- **出處**：`arm/lab/usfin.py:320-328`（美股財報摘要；資料分支讀不到時每檔都是空）、`arm/lab/mratio.py:153-166`（融資維持率序列；分片讀不到時寫空序列）、
  `arm/lab/fcst.py:427-443`（Yahoo 法人預估；上市名單分片讀不到時寫空）。
- **情境**：例如 CI 那一班資料分支沒拉到 → `data/lab/ussx_fin.json` 的 `s` 變 `{}` → 美股個股卡的季財報那一段全部消失。
- **修法**：來源讀不到（或算出來 0 筆而舊檔有東西）就不寫。每處 3～5 行。

### 7. 舊的本機流程整套拿掉（使用者確認沒在跑了）
- **範圍**（每個檔都全專案搜尋過：正式流程、排程、指令、技能、知識庫都沒有用到；只被彼此和自己的測試用到）：
  - 程式 52 個檔、約 6,300 行：腳本 10 支（`run_daily`、`gen_copy`、`gen_dashboard`、`fetch_fast`、`fetch_news`、`fetch_peers`、`fetch_etfinfo`、`backfill_nav`、`vercel_publish`、`cf_publish`）、
    shell 6 支（`daily_routine`、`daily_run`、`publish`、`publish_public`、`publish_vercel`、`install_schedule`）、模組 14 個＋`arm/copy/`（7 個），
    以及只被它們用到的 `arm/connectors/brokers/`（5）、`arm/connectors/social/`（9）、`arm/connectors/twse_mis.py`。
  - 測試 16 支、1,121 行（96 個測試），都只測這些程式，沒有要拆開的。
  - 它專用的舊資料 56 個檔、約 6.5 萬行：`config/active_flow/`（約 5.1 萬行）、`config/competitor_holdings/`（約 1.1 萬行）、券商分點與社群設定、
    `config/compliance.yaml`／`.json`、`intel_seed`、`distributions`、`benchmark_0050`、`products.yaml`（沒人讀的 `products.json` 對照版），以及 `reports/intel/`（6 月的 17 個檔）。
  - 合計 124 個檔、約 7.2 萬行。在複本上整批刪掉試過：全部測試 2,216 個通過、知識庫體檢 0 錯。
- **要一起改**：`.claude/rules/calendar.md` 列著 `arm/calendar.py`（不改知識庫測試會紅；正式的交易日曆是 `arm/twholidays.py`）；
  知識庫 `env/git-history.md` 那一行標「已刪」；`README.md` 一行。
- **具體風險（不刪的話）**：`scripts/gen_dashboard.py:20` 會寫 `dashboard/index.html`——正是 CI 建的正式首頁，誰手動跑一次就蓋掉；
  96 個測試每次都在測沒人跑的程式；看程式的人會以為還有一套每日流程。
- **要你決定**：臉書抓取（`arm/connectors/social/facebook.py` 與 `config/social_fb_pages.json`，連同共用的 `social/__init__.py`、`base.py`、`filters.py` 約 260 行）——
  `docs/social_api_plan.md` 的第二階段「FB 自家粉專」打算沿用它，那一階段還沒做。留著，或一起拿掉（之後要做再從 git 拿回來）。
- **第二步（拿掉之後剩下的零件）**：`arm/config.py` 的 `distributions()`、`connectors/issuers` 的 4 個函式、`connectors/etfinfo.py` 的 3 個函式、
  `connectors/tdcc.py` 寫資料庫那段——拿掉之後 `arm/db.py`（60 行）也可以拿掉。
- **附帶**：`cf_publish.py` 裡寫死的 Cloudflare 帳號 id 刪檔後仍留在 git 歷史（是帳號 id、不是金鑰）。
- **推送注意**：刪 `reports/intel/` 推到 `claude/**` 會觸發 daily.yml，那一輪會自己跳過（`daily.yml:169-174`）；改由 PR 合併。

## 可以更好

### 8. 沒人用的小東西（約 150 行）
- 12 個函式（約 104 行）：`connectors/issuers/pcf.py` `fetch_one`、`lab/bubble.py` 與 `lab/bubpage.py` 的 `clear_cache`、`bubpage._g_src`、`futsim` 的 `as_dict`、`heatpage._strips`、
  `heatviz.key_html`、`heatviz.items_table`、`pickcal.on_or_after`、`usbreadth.ratio_arrays`、`tw-superstock-lab` 的 `industry_counts`、`stop_first`。
- 約 25 個沒用到的常數（例 `thermocal.SIDES`、`page.SLUG`、`tilt.LIVE_MIN_DAYS`）、8 個沒用到的 import（`tilt.py` 2 個、`ussxmine`、`board`、`ussxrun`、`ussxfeat`、兩支 probe）、
  7 個算了沒用的區域變數、10 個沒有變數的 f 字串、3 個沒用到的參數與過時的說明（`ussxmine.mine_fold` 的 `ix_of`、`hotdd.now` 的 `R_mk`、`cnyesfund.search_all` 的 `max_pages`）。
  （另外 158 個 import 是刻意轉出的，有 `noqa` 標記，不動。）全部逐一確認過沒有算錯的地方。

### 9. 日期寫法：66 處直接取今天，沒有用台北時間的函式
- **出處**：例 `arm/lab/eqfacts.py:546`、`arm/lab/candrun.py:849`、`arm/lab/heatfetch.py:93`；鐵則要用 `arm/clock.py` 的 `today_tw()`。
- **情境**：CI 都有設台北時區，所以現在沒事；在沒設時區的地方跑（例如容器裡忘了加 `TZ=Asia/Taipei`），台北早上 8 點前會拿到前一天。
- **修法**：機械地換成 `clock.today_tw()`；輸出不變。66 處，淨行數 0。

### 10. 合併前沒有自動跑測試
- **現況**：沒有 workflow 在 PR 時跑測試；每次合併前靠手動跑全部測試（到目前都有做）。
- **修法**：加一支 PR 時跑 `pytest`（不含要瀏覽器的兩支）的小 workflow，約 25 行；公開 repo 不算分鐘。
- **不修會怎樣**：只要哪次忘了跑，壞掉的程式會進 main，隔天 07:15 那班才發現。

## 第三段怎麼修（你挑完之後）

- 一條一個小 PR；每一個都要：全部測試、`test_plain`、`test_old_urls` 通過；**全部頁面重建一次和修之前逐字比對**（產表時間這類戳記除外）——
  第 1～6 條在正常情況下輸出一模一樣（只差在出錯的那一天），另加模擬出錯的小測試；第 8、9 條必須一模一樣；第 7 條拿掉的程式沒有任何頁面用到。
- 合併後看 CI 那一輪成功、資料日推進。
