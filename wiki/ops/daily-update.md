# 「全部更新」每日 SOP

> 使用者打「全部更新」就照這頁跑：容器只產新聞報告，抓資料、建表、部署交給 CI；步驟 1～9（含 9⑤～9⑨）怎麼做、怎麼驗。
> 原始資料：CLAUDE.md「指令：「全部更新」／「資料更新」」段（步驟 2 在 [新聞報告規則](news-rules.md)，部署在 [部署](deploy.md)）；程式：`scripts/check_reports.py`、`.github/workflows/daily.yml`。
> 最後更新：2026-10-29
> CLAUDE.md 仍留著對應的指令段落（排程照它執行）：那一段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）；其他內容以這一頁為準。

## 現在怎麼運作

### 指令：「全部更新」／「資料更新」

使用者只要打**「全部更新」**（或「資料更新」），第一時間直接執行，不要再詢問；排程每天也火進綁定的對話跑這一份（[排程](routines.md)）。

**效率原則（2026-07 檢討，本流程最重要的一條）**：容器 proxy 擋掉**所有**資料來源站（`fhtrust.com.tw` 403、`etfinfo.tw` 403、Google News、PTT），
在這裡跑 `fetch_holdings.py`／`fetch_fund_news.py`／`fetch_etf_watch.py` **注定失敗或卡到逾時**（實測 `fetch_etf_watch.py` 空轉逾 20 分鐘、`fetch_holdings.py` 25 檔全 403）。
那是環境限制、不是程式 bug，「正式區」（`daily.yml` GitHub Actions，擁有者身分、完整網路）本來就會自己跑。所以這裡「絕不」跑資料抓取腳本，
只做「只有 Claude 能做」的事（WebSearch 產新聞），抓資料＋權威版儀表板整包丟給正式區，最後讀 CI 入庫的 `dashboard/index.html` 驗證，每次省約 25 分鐘空轉
（被擋的站見 [容器的限制](../env/container.md)）。步驟編號照原文（沒有步驟 8）。

### 1. 產提示包（本地、秒級，是 WebSearch 的輸入，**要跑**）

`TZ=Asia/Taipei python3 scripts/gen_usnews.py && TZ=Asia/Taipei python3 scripts/gen_twnews.py && TZ=Asia/Taipei python3 scripts/gen_macronews.py`

### 2. 上網查證產新聞內容

見 [新聞報告規則](news-rules.md)。

### 3. 合規掃描＋內容 QA＋數字核對（全 🟢 才往下）

1. `gen_usnews.py --check`、`gen_twnews.py --check`、`gen_macronews.py --check`。
2. `TZ=Asia/Taipei python3 scripts/check_reports.py`：檔案齊全／每報≥4卡／每卡有連結與重要度／行事曆為今日；**每卡摘要或影響分析非空**
   （「摘要／影響分析皆空」2026-07-31 新增，🔴 會直接指出標籤沒加 `**粗體**`：把 `N. 標籤：` 改成 `N. **標籤**：`，勿改渲染端，根因見 [新聞卡](../main/news-cards.md)）；
   2026-08-20 起：每卡漲跌分析欄＋影響分析≥2條＋分析合計≥120字（【深度】卡豁免）、大變動提及（官方序列旗標的資產，對應報告全文須提及；序列過期或落檔讀不到＝跳過）；
   2026-10-13 起：頭段總覽／速覽抽得到（美股 v1／總經「…總覽」、台股「盤前／盤後速覽」，[列印版](../main/print.md) 踩坑⑤）、
   行事曆台灣區與精簡上限（台／台股列或「本週無」註記、總列數 ≤30、引言 ≤220 字，[行事曆](../main/calendar.md)）。
3. `TZ=Asia/Taipei python3 scripts/check_holdings_intro.py`（🔴＝有持股缺簡介）：立即 WebSearch 查證，補進 `config/holding_profiles.json`
   （`{name: {intro, ticker, country, verified}}`、純事實非投資建議、避開禁用詞）到 🟢 為止；固定防呆、不可略（2026-07-23 使用者：前十大簡介一再漏掉）。
   隨步驟 6 push 即自動落地（daily.yml 併檔自動通道，不需 PR，見 9⑤）。
4. `TZ=Asia/Taipei python3 scripts/check_numbers.py`（高風險數字對官方 API）：容器 proxy 擋 twse/taifex 會全 ⚪，屬正常，真正核對在 CI。

**發佈策略**（2026-07-20 使用者兩指示並行：數字要對＋防線不可硬到什麼都沒更新）：CI 端 🔴 **不擋發佈**——結果落 `data/factcheck.json` 隨每日 commit 入板、
「網頁更新時間」區顯示紅色警示章；步驟 9 讀該檔，見 🔴 **立即修正該數字並重推**（分鐘級收斂）。

### 4. 重建儀表板驗證（本地、秒級，**不需先抓資料**）

`TZ=Asia/Taipei python3 scripts/gen_fund_dashboard.py`，只為確認新聞入板＋渲染管線沒被新內容弄壞：「🕒 資料更新時間」區塊的**新聞欄位**已到今日。
驗完務必 `git checkout -- dashboard/index.html` 丟棄（見坑②）。

### 5～7. 測試、commit、CI 單一 commit

- 5：`python3 -m pytest -q` 全綠（容器預設無 pytest，先 `pip install -q pytest`）。
- 6：推到本次會話指定分支，**只帶「新聞報告」**（`reports/*.md`＋提示包；不帶 `dashboard/index.html`；`data/*` 被擋未更新、不會有 diff），訊息 `chore: 每日新聞更新 {日期}`；
  不必開 PR、不必 merge 進 main。
- 7：push 動到 `reports/**` 就自動觸發 `daily.yml`（`on: push branches claude/** paths reports/**`，2026-07-18 起），以被推分支為 `news_ref`——
  不必再手動呼叫 GitHub API/MCP（排程 Routine 的新會話沒有 MCP 工具，靠這條就夠）。CI：①checkout main、併入該分支今日 `reports/*.md` → ②抓**真實** NAV／持股／ETF／基金新聞
  → ③重建儀表板 → ④擁有者身分**一次 commit 進 main（新聞＋真實資料＋建表同一筆）** → ⑤打 Deploy Hook（[部署](deploy.md)）。main 每天只有**一筆權威 commit**。
  push 觸發用**被推分支**上的 workflow 檔，分支太舊時新通道與金鑰不生效（[排程](routines.md)「生效條件」）。
  備援：push 沒觸發（如只改程式碼未動 reports）→ `mcp__github__actions_run_trigger` 帶 `inputs={"news_ref":"<分支>"}`；留空 `news_ref`＝排程 cron 行為：只用 main 現有新聞重刷資料。

### 9. 驗證線上內容

「全部更新」的完成定義＝網頁真的更新。等 `daily.yml` 跑完（約數分鐘）；線上網址 `https://fuhhwa-fund-radar.vercel.app/#overview`，但容器截圖做不到（坑①），
改做「內容已產出」驗證：`git fetch origin main && git show origin/main:dashboard/index.html` 看 ①美股／台股新聞、總經・政策皆今日日期；
②「🕒 產表」時戳為 CI 那次（比本地晚＝CI 已重產覆蓋）；③ETF 表有值；④基金 `data/funds/*.json` 的 `nav_date` 已推進（NAV 常見 T+1，今日只到昨日屬正常）；
並用 `mcp__github__actions_*` 確認該次 `daily.yml` run `success`。讀 `data/factcheck.json`，🔴 照發佈策略修正重推。
持股基準為月度值（顯示上月底）——不是資料沒更新。「內容在 main」≠「線上已部署」，見 [部署](deploy.md)。

#### 9⑤ 前十大簡介缺口

讀 `git show origin/main:data/holdings_intro_gap.json`。**晨間只讀不補**（使用者 2026-08-12：不佔早上、跟最簡單的那班）：count>0 → 成功推播帶一句「缺 N 檔簡介，15:33 班會補」；
「主責＝15:33 盤後班」（盤後籌碼 Routine 步驟②：該班最輕、又在晨間持股抓取之後，缺口當天下午清）。**連兩天 count>0**（昨天下午沒清＝排程搬家前過渡期或該班失效）
才在晨間親自跑極簡迴路並查原因。

`items[].src`：
- `fund` 基金前十大；`etf` ETF 完整持股（2026-10-21 起，另帶 `ticker`＝補進 profiles 的代號、`etfs`＝哪幾檔持有；`etf_holdings.yml` 抓完持股也跑一次檢查）；
- `usqm` 美股三成（2026-10-24 起；配置頁美股列的股票＝手上的、要買的、名單前 5 名裡手上沒有的；2026-10-28 起是選股頁美股強勢品質股那張卡列的同一批，`fund_intro.uncovered_us_qm`；
  `name`＝每週紀錄的英文公司名、`ticker`＝代號；[選股頁](../lab/pick-page.md)）。由來是使用者 2026-10-24：「美股那些公司誰知道你是什麼公司…台股不都有列嗎？比照著做」；
  名單每週六換，新進前 5 名的公司週一下午這班補。美股簡介照「美國 公司名（中文名若有），本業；細節」寫：頁面上取「；」前那一段，「，」前＝公司名（去掉「美國」與結尾括號）、
  後＝本業一行（`corepage.us_label`）。

**極簡迴路**（15:33 班與晨間 backstop 共用；~5 分鐘、不跑抓取腳本）：

1. gap 檔 `items[].name` 就是快照原字串（已還原 `&amp;` 等實體），**每檔 1 次 WebSearch** 查證（公司本業／代號／國別）；
2. 補進 `config/holding_profiles.json`（`{原字串: {intro, ticker, country, verified, url?}}`）：intro 純事實、避開禁用詞；country＝公司母國，如英飛凌→德國；
   `url` 選填＝基金型持有（組合型的子基金，無掛牌代號）的鉅亨基金頁 `https://fund.cnyes.com/detail/{名稱}/{cnyesId}`，渲染端優先用它，沒 url 又沒 ticker 的基金名去搜 Yahoo 必落空
   （2026-08-12 使用者：「點進去沒東西」）；股票/ETF 不用填，ticker＋country 自動產 Yahoo 行情連結；
3. `TZ=Asia/Taipei python3 scripts/check_holdings_intro.py` 須 🟢（同時把本地 gap 檔歸零，**一起 commit**，下一輪重建紅章即滅）；
4. `python3 -m pytest -q tests/test_holdings_intro.py` → commit＋push 本會話分支。

**push 即收工**：`config/holding_profiles.json` 在 daily.yml 自動併檔通道（同 `data/etf_upcoming.json` 模式，防呆＝JSON 驗證＋有簡介筆數不得減少），
不需 PR、merge、dispatch、監看。生效條件＝本會話分支 fork 自「通道已上線（2026-08-12 PR #201）」的 main；分支太舊的徵狀＝push 後 main 的 profiles 沒動，
補救＝`mcp__github__actions_run_trigger` dispatch daily.yml（ref=main、news_ref=本分支——dispatch 用 main 的 workflow 檔，併檔段必有通道），根治＝排程搬家。
2026-08-12 前的舊流程開 PR 人工 merge（首例 PR #200），勿再走。簡介庫的防呆見 [持股簡介補齊](../main/holdings-intro.md)。

#### 9⑥ 盤後完整性警示

`git show origin/main:data/afterhours_alert.json`：`date`＝昨日且 `missing` 非空＝昨天盤後有缺口且到深夜都沒自癒（夜檢 Routine 應已推播過）。
早上這班會補齊，但在推播裡帶一句、查 afterhours run 日誌找根因（[時點地圖](schedule.md)）。

#### 9⑦ 社群 YouTube 驗證

使用者 2026-08-07：「每次更新都順便查一下 YouTube」。`git show origin/main:data/fund_news.json` 的 `social` 內 `platform=="youtube"` 須 ≥1
（三層清單正常日不會是 0；0 時「網頁更新時間」列掛「社群 YouTube 🔴 0 支」章）。為 0＝金鑰沒帶到或抓取失敗：查 CI 日誌 grep `[fundnews]`／`未設 YOUTUBE_API_KEY`；
補救＝dispatch daily.yml（ref=main、news_ref 留空，用 main 的 workflow 檔、金鑰必在），根治＝排程搬家（新分支自最新 main 分岔）。根因見坑⑤，清單見 [復華新聞](../main/fund-news.md)。

#### 9⑧ 漏網新 ETF

`git show origin/main:data/etf_upcoming_gap.json` 的 **`items` 非空就當天處理完，不要押到週一**（使用者 2026-08-10：「如果知道有漏為什麼要等下週再更新，直接跑即時更新吧？」）：
一週一次講的是「主動出去掃描」的頻率，不是「已知缺口的處理時機」；發現層每天在跑，處理「已列名的 N 檔」比盲掃便宜（分工見 [ETF 募集週掃](etf-weekly-scan.md)）。
- `kind=listed`（已掛牌卻沒登錄）＝真漏網、🔴 紅章，最優先立即查證補登。
- offering（已核准／募集中待登錄）＝⚠ 琥珀章，同一輪 WebSearch 查證：有代號／募集期間就填正式欄位，只查得到「已核准」用 `raise_hint`＋`asof`；
  **查無來源的欄位一律留空，不要猜代號或日期**。補完推分支（動到 `data/etf_upcoming.json` 自動觸發 daily.yml 併入 main）。
- `pipeline` 欄（申請中、審查未過、申報生效日未到）＝不警示也**不登錄**，生效後下輪升進 `items`。2026-08-28 起上版（使用者：「有送件的 ETF 就可以更新上去即將登場」）：
  「即將登場」第四組「已送件・審查中」精簡列（`fund_dashboard._applied_row`，同名去重、本家復華排最前、fail-open），純展示，登錄時機不變。

機制見 [即將登場](../main/etf-upcoming.md) 的「新 ETF『自動發現』層」。

#### 9⑨ 籌碼雷達推播行

使用者 2026-10-15 同意：「06:35 推播多帶兩行」（原本兩行、現在最多六行；Routine prompt ① 仍叫「兩行」，指的就是 `push` 欄全部）。成功推播的 3 條市場重點之後，
**原文照貼** `git show origin/main:data/lab/val_log.json` 最新資料日（`days` 最後一個鍵）的 `push` 欄：

- 第一行＝下一個交易日開盤／收盤要做的買賣（例「10/16（五）沒有排定的買賣。」）；
- 有要賣要買時多一行：台股新飆股（例「新飆股：11/2（一）開盤賣 奇鋐、買 金像電。」，2026-10-24 起）、美股強勢品質股（例「美股強勢品質股：10/26（一）開盤賣 INSW、買 PAYC。」；2026-10-28 前叫「美股三成」）；
- 少見但勝率高的策略接下來 2 個交易日要買或賣時多一行（例「少見機會：11/3（二）收盤 S&P 500 買進（期中選舉後抱一年，抱到 2027/11/2）。」，2026-10-27 起；[少見但勝率高的策略](../lab/rare.md)）；
- 策略候選第一次有結果時多一行（「策略候選：新增…」，[新策略候選](../lab/candidates.md)）；
- 最後一行＝策略驗證事件（有才有）。

讀不到或沒有 `push` 就省略、**不擋推播**。由 CI 重建籌碼雷達時產生（`arm/lab/valog.py`，順序與條件見 `valog.push_lines`；[籌碼雷達](../lab/chip-ui.md)「版面 v4」），不必自己算、不要改寫。

## 不能改的規則

1. 容器「絕不」跑資料抓取腳本。
2. 本地重建的 `dashboard/index.html` **絕不 commit**，分支只帶「純新聞報告」（push 一樣觸發 CI、一樣有權威建表）。
3. 不開 PR、不 merge：main 每天一筆「單一 commit」由 CI 寫。
4. 「摘要／影響分析皆空」＝改報告，**不改渲染端**、不放寬解析。
5. 數字核對 🔴 不擋發佈，但看到就立即修正重推。
6. 9⑤ 晨間只讀、連兩天紅才補；9⑧ 當天處理、查無來源留空；9⑨ 照貼、讀不到不擋推播。
7. 完成定義只到「CI commit 在 main＋該 `daily.yml` run success＋該 commit `nav_date` 已推進」，不可宣稱線上已生效。

## 踩過的坑

- ① **容器「截圖」線上頁做不到（2026-07 實測）**：agent proxy 對 `fuhhwa-fund-radar.vercel.app:443` 回 **CONNECT 403（政策拒絕）**，與擋 fhtrust／etfinfo 同一套政策，
  Playwright/WebFetch/curl 一律不通；除非使用者改用更寬鬆的網路政策，別再嘗試、白費算力。
- ② **本地 `dashboard/index.html` 每天 commit 會和 CI 打架（2026-07-23 省 token 優化）**：本地帶的是舊 NAV／ETF 快照，CI 稍後權威重產覆蓋、本地版沒有保留價值；
  每天 commit 幾乎必與 CI 的儀表板 commit 打架，逼出一整輪 fetch+merge+重建+re-push（實測是每日流程最大 token 消耗源）→ 驗完就丟。
- ③ **舊架構「一天兩筆 commit、Vercel 常部到舊版→新聞會動淨值不動」** → 步驟 7 單一 commit（2026-07-18）根治。
- ④ **外資淨空單誤引彙整站 83,605 口、官方實為 86,189** → 步驟 3 數字核對與發佈策略。
- ⑤ **YouTube 全空（2026-08-07）**：push 觸發的 daily.yml 用「被推分支」上的 workflow 檔，排程會話分支分岔自「daily.yml 掛上 YOUTUBE_API_KEY env（08-06 早）」之前的 main，
  該輪 env 沒金鑰，整段 social 還被洗成 0。現由 `fundnews._carry_social` 來源級防呆擋住（單平台全空沿用既有項目，CI 日誌印「社群 youtube 本次全空、沿用既有 N 則」）。
- ⑥ **ETF 持股簡介慢慢倒退（2026-10-21）**：原本只有測試的 95% 門檻守，主動式天天換股滑到 97%（72 檔）沒人發現 → 缺口檔加 `etf`（9⑤）。

## 歷史

- 2026-07 效率原則；07-18 單一 commit；07-20 發佈策略；07-23 簡介檢查、本地重建驗完丟棄。
- 2026-08-03 加 9⑥、08-07 加 9⑦、2026-08-10 加 9⑧（同日兩度調整：先分級警示，再改「見到就處理」）、08-12 9⑤ 全自動落地。
- 2026-10-15 加 9⑨。各閘門與推播行的起始日寫在步驟裡。
