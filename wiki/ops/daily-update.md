# 「全部更新」每日 SOP

> 使用者打「全部更新」就照這頁跑：容器只產新聞報告，抓資料、建表、部署交給 CI；步驟 1～9（含 9⑤～9⑨）怎麼做、怎麼驗。
> 原始資料：CLAUDE.md「指令：「全部更新」／「資料更新」」段的效率原則與步驟 1、3～7、9（步驟 2 在 [新聞報告規則](news-rules.md)，步驟 9 的部署與「線上沒更新」在 [部署](deploy.md)）；程式：`scripts/gen_usnews.py`、`scripts/gen_twnews.py`、`scripts/gen_macronews.py`、`scripts/check_reports.py`、`scripts/check_holdings_intro.py`、`scripts/check_numbers.py`、`scripts/gen_fund_dashboard.py`、`.github/workflows/daily.yml`。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

### 指令：「全部更新」／「資料更新」

使用者只要打**「全部更新」**（或「資料更新」），第一時間直接執行，不要再詢問。排程每天也火進綁定的對話跑這一份（見 [排程](routines.md)）。

**效率原則（2026-07 檢討；這是本流程最重要的一條）**：本 Claude 容器的 proxy 擋掉所有資料來源站（`fhtrust.com.tw` 403、`etfinfo.tw` 403、Google News、PTT），
在這裡跑 `fetch_holdings.py`／`fetch_fund_news.py`／`fetch_etf_watch.py` 注定失敗或卡到逾時（實測 `fetch_etf_watch.py` 空轉逾 20 分鐘、`fetch_holdings.py` 25 檔全 403）。
那是環境限制、不是程式 bug，「正式區」（`daily.yml` GitHub Actions，擁有者身分、完整網路）本來就會自己跑這三支。
所以在這裡「絕不」跑資料抓取腳本，只做「只有 Claude 能做」的事（WebSearch 產新聞內容），把資料抓取＋權威版儀表板整包丟給正式區，
最後讀 CI 入庫的 `dashboard/index.html` 驗證線上內容。每次省下約 25 分鐘的空轉。被擋的站與各腳本的反應見 [容器的限制](../env/container.md)。

| 步驟 | 在哪裡 | 做什麼 | 過關條件 |
|---|---|---|---|
| 1 | 容器 | 產提示包 | 秒級跑完 |
| 2 | 容器（平行子代理） | WebSearch 查證、寫當日新聞報告 | 照提示包版型，見 [新聞報告規則](news-rules.md) |
| 3 | 容器 | 合規掃描、內容 QA、簡介覆蓋率、數字核對 | 全 🟢（數字核對在容器內全 ⚪ 屬正常） |
| 4 | 容器 | 重建儀表板驗證，驗完丟掉 | 新聞欄位到今日 |
| 5 | 容器 | pytest | 全綠 |
| 6 | 容器 | commit＋push，只帶新聞報告 | — |
| 7 | CI | push 自動觸發：抓資料、建表、一次 commit 進 main、部署 | — |
| 9 | 容器 | 讀 main 上 CI 的 commit 驗證（9①～9⑨） | 見步驟 9 |

（原文沒有步驟 8，編號照留。）

### 步驟 1：產提示包

本地、秒級，是 WebSearch 的輸入，**要跑**：

`TZ=Asia/Taipei python3 scripts/gen_usnews.py && TZ=Asia/Taipei python3 scripts/gen_twnews.py && TZ=Asia/Taipei python3 scripts/gen_macronews.py`

### 步驟 2：上網查證產新聞內容

見 [新聞報告規則](news-rules.md)（守備範圍、選題、深度與漲跌分析、速覽文風、粗體標籤、籌碼讀落檔、子代理回傳格式）。

### 步驟 3：合規掃描＋內容 QA＋數字核對

依序跑，全部 🟢 才往下：

1. 合規掃描：`gen_usnews.py --check`、`gen_twnews.py --check`、`gen_macronews.py --check`。
2. 內容 QA：`TZ=Asia/Taipei python3 scripts/check_reports.py`。擋下的項目：
   - 檔案齊全／每報≥4卡／每卡有連結與重要度／行事曆為今日；
   - **每卡摘要或影響分析非空**——「摘要／影響分析皆空」這項是 2026-07-31 新增的防呆。🔴 訊息會直接指出是標籤沒加 `**粗體**`：
     把該報告的 `N. 標籤：` 改成 `N. **標籤**：` 即可，勿改渲染端（根因見 [新聞卡](../main/news-cards.md)）；
   - 2026-08-20 起：每卡漲跌分析欄＋影響分析≥2條＋分析合計≥120字（【深度】卡豁免）；
   - 2026-08-20 起：大變動提及（官方序列旗標的資產，對應報告全文須提及；序列過期或落檔讀不到＝跳過）；
   - 2026-10-13 起：頭段總覽／速覽抽得到（美股 v1／總經「…總覽」、台股「盤前／盤後速覽」；見 [列印版](../main/print.md) 踩坑⑤）；
   - 2026-10-13 起：行事曆台灣區與精簡上限（台／台股列或「本週無」註記、總列數 ≤30、引言 ≤220 字；見 [行事曆](../main/calendar.md)）。
3. 前十大簡介覆蓋率：`TZ=Asia/Taipei python3 scripts/check_holdings_intro.py`（🔴＝有持股缺簡介）。
   見 🔴 立即 WebSearch 查證，把缺的標的補進 `config/holding_profiles.json`（格式 `{name: {intro, ticker, country, verified}}`、純事實非投資建議、避開禁用詞），
   補到 🟢 為止。這是固定防呆步驟、不可略（2026-07-23 使用者：前十大簡介一再漏掉）。補完隨步驟 6 push 即自動落地：該檔走 daily.yml 併檔自動通道，不需 PR（見 9⑤）。
4. 數字核對：`TZ=Asia/Taipei python3 scripts/check_numbers.py`（高風險數字對官方 API）。本容器 proxy 擋 twse/taifex，會全 ⚪，屬正常，真正核對在 CI。

**發佈策略**（2026-07-20 使用者兩指示並行：數字要對＋防線不可硬到什麼都沒更新）：CI 端 🔴 **不擋發佈**——結果落 `data/factcheck.json` 隨每日 commit 入板，
儀表板「網頁更新時間」區顯示紅色警示章；主會話在步驟 9 讀該檔，見 🔴 **立即修正該數字並重推**（分鐘級收斂）。

### 步驟 4：重建儀表板驗證

本地、秒級，只為確認新聞入板＋渲染管線沒被新內容弄壞；**不需先抓資料**：
`TZ=Asia/Taipei python3 scripts/gen_fund_dashboard.py`，確認「🕒 資料更新時間」區塊的**新聞欄位**已更新至今日。
驗完務必 `git checkout -- dashboard/index.html` 丟棄本地重建結果（規則 2；為什麼見「踩過的坑」）。

### 步驟 5：測試

`python3 -m pytest -q` 全綠（此容器預設無 pytest，先 `pip install -q pytest`）。

### 步驟 6：commit＋push

推到本次會話指定分支，只帶「新聞報告」（`reports/*.md`＋提示包）；不帶 `dashboard/index.html`；`data/*` 被擋未更新、不會有 diff。
訊息用 `chore: 每日新聞更新 {日期}`。不必開 PR、不必 merge 進 main——步驟 7 由 CI 一次 commit。

### 步驟 7：正式區「單一 commit」抓真實資料＋建表＋部署

2026-07-18 起 push 即自動觸發：步驟 6 的 push 動到 `reports/**` 時，`daily.yml` 會自動觸發（`on: push branches claude/** paths reports/**`），
以被推分支為 `news_ref`——不需、也不必再手動呼叫 GitHub API/MCP（排程 Routine 的新會話沒有 MCP 工具，靠這條就夠）。CI 會：

①checkout main、把該分支今日 `reports/*.md` 併入 → ②抓**真實** NAV／持股／ETF／基金新聞 → ③重建儀表板 →
④以擁有者身分**一次 commit 進 main（新聞＋真實資料＋建表同一筆）** → ⑤打 Deploy Hook 部署（見 [部署](deploy.md)）。

main 每天只有**一筆權威 commit**。push 觸發的這一輪用的是**被推分支上的** workflow 檔，所以分支太舊時新通道與新金鑰不會生效（見 [排程](routines.md) 的「生效條件」）。

備援：互動會話若 push 沒觸發（如只改程式碼未動 reports），用 `mcp__github__actions_run_trigger` 帶 `inputs={"news_ref":"<分支>"}`；
留空 `news_ref`＝排程 cron 行為：只用 main 現有新聞重刷資料。

### 步驟 9：驗證線上內容

「全部更新」的完成定義＝網頁真的更新。等 `daily.yml` 跑完（約數分鐘）後驗證。Vercel 線上網址：`https://fuhhwa-fund-radar.vercel.app/#overview`。
容器看不到線上頁（截圖做不到，見「踩過的坑」），能做的是「內容已產出」驗證：直接讀 **main 上 CI 剛 commit 的那支檔**——
`git fetch origin main && git show origin/main:dashboard/index.html` 後檢查下面 ①～④（9⑤ 起接著編號），並用 `mcp__github__actions_*` 確認該次 `daily.yml` run `success`：

- ① 美股／台股新聞、總經・政策皆今日日期；
- ② 「🕒 產表」時戳為 CI 那次（會比本地時戳晚，證明 CI 已重產覆蓋）；
- ③ ETF 表有值；
- ④ 基金 `data/funds/*.json` 的 `nav_date` 已推進（NAV 常見 T+1，今日只到昨日 NAV 屬正常）。

另外讀 `data/factcheck.json`，有 🔴 就照步驟 3 的發佈策略修正重推。持股基準為月度值（顯示上月底）——不是資料沒更新。
「內容在 main」不等於「線上已部署」，宣稱線上生效之前的診斷見 [部署](deploy.md)。

#### 9⑤ 前十大簡介缺口

讀 `git show origin/main:data/holdings_intro_gap.json`。

- **晨間本步驟只讀不補**（使用者 2026-08-12：不佔早上、跟最簡單的那班）：count>0 → 成功推播裡帶一句「缺 N 檔簡介，15:33 班會補」即可。
  「主責＝15:33 盤後班」：補齊由 15:33 盤後籌碼 Routine 步驟②負責（該班最輕、又在晨間持股抓取之後，缺口當天下午清）。
- **連兩天 count>0**（昨天下午沒清＝排程搬家前過渡期或該班失效）才在晨間親自跑下面的極簡迴路並查原因。
- 缺口檔每筆的 `items[].src`：`fund` 基金前十大；`etf` ETF 完整持股（2026-10-21 起；ETF 那幾筆另帶 `ticker`＝補進 profiles 的代號、`etfs`＝哪幾檔持有；
  `etf_holdings.yml` 抓完持股也跑一次檢查）；`usqm` 美股三成（2026-10-24 起；配置頁美股列的股票＝手上的、要買的、名單前 5 名裡手上沒有的，`fund_intro.uncovered_us_qm`；
  `name`＝每週紀錄的英文公司名、`ticker`＝代號。配置頁 2026-10-28 起拿掉，見 [選股頁](../lab/pick-page.md)）。
  美股那一類的由來是使用者 2026-10-24：「美股那些公司誰知道你是什麼公司…台股不都有列嗎？比照著做」。名單每週六換，新進前 5 名的公司週一下午這班補。
- 美股簡介照「美國 公司名（中文名若有），本業；細節」寫：配置頁取「；」前那一段，「，」前＝公司名（去掉「美國」與結尾括號）、後＝本業一行（`corepage.us_label`）。

**極簡迴路**（15:33 班與晨間 backstop 共用；全程 ~5 分鐘、不跑任何抓取腳本）：

1. gap 檔 `items[].name` 就是快照原字串（已還原 `&amp;` 等實體）——**每檔 1 次 WebSearch** 查證（公司本業／代號／國別）。
2. 補進 `config/holding_profiles.json`（`{原字串: {intro, ticker, country, verified, url?}}`）：intro 純事實、避開禁用詞；country＝公司母國，如英飛凌→德國；
   `url` 選填＝基金型持有（組合型的子基金，無掛牌代號）的鉅亨基金頁 `https://fund.cnyes.com/detail/{名稱}/{cnyesId}`——渲染端優先用它，
   沒 url 又沒 ticker 的基金名去搜 Yahoo 必落空（2026-08-12 使用者：「點進去沒東西」）；股票/ETF 不用填，ticker＋country 會自動產 Yahoo 行情連結。
3. `TZ=Asia/Taipei python3 scripts/check_holdings_intro.py` 須 🟢——它同時把本地 gap 檔歸零，**一起 commit**（下一輪重建紅章即滅，不等 CI 自查）。
4. `python3 -m pytest -q tests/test_holdings_intro.py` 秒級確認 → commit＋push 本會話分支。

**push 即收工**：`config/holding_profiles.json` 已入 daily.yml 自動併檔通道（同 `data/etf_upcoming.json` 模式，防呆＝JSON 驗證＋有簡介筆數不得減少），
不需開 PR、不需 merge、不需 dispatch、不需監看，push 觸發的那輪 CI 自動併入 main＋重建＋部署。
生效條件＝本會話分支 fork 自「通道已上線（2026-08-12 PR #201）」的 main（push 觸發的 daily.yml 用被推分支的 workflow 檔，機制見 [排程](routines.md)）。
分支太舊時的徵狀＝push 後 main 的 profiles 沒動：補救＝`mcp__github__actions_run_trigger` dispatch daily.yml（ref=main、news_ref=本分支——dispatch 用 main 的 workflow 檔，併檔段必有通道）；根治＝排程搬家。
簡介庫本身的防呆見 [持股簡介補齊](../main/holdings-intro.md)。

#### 9⑥ 盤後完整性警示

讀 `git show origin/main:data/afterhours_alert.json`：`date`＝昨日且 `missing` 非空＝昨天盤後有缺口且到深夜都沒自癒（夜檢 Routine 應已推播過）。
早上這班會把缺口補齊，但要在推播裡帶一句、並查 afterhours run 日誌找根因（看門狗見 [每日時點地圖與 cron](schedule.md)）。

#### 9⑦ 社群 YouTube 驗證

使用者 2026-08-07：「每次更新都順便查一下 YouTube」。讀 `git show origin/main:data/fund_news.json`，`social` 內 `platform=="youtube"` 支數須 ≥1
（三層清單正常日不會是 0；為 0 時儀表板「網頁更新時間」列會掛「社群 YouTube 🔴 0 支」章）。

為 0＝金鑰沒帶到或抓取失敗：查該輪 CI 日誌 grep `[fundnews]`／`未設 YOUTUBE_API_KEY`。
補救＝`mcp__github__actions_run_trigger` dispatch daily.yml（ref=main、news_ref 留空）——dispatch 用 main 的 workflow 檔、金鑰必在；
根治＝排程搬家到新視窗（新分支自最新 main 分岔）。已知根因見「踩過的坑」；YouTube 清單見 [復華新聞與社群](../main/fund-news.md)。

#### 9⑧ 漏網新 ETF

讀 `git show origin/main:data/etf_upcoming_gap.json`。**`items` 非空就當天處理完，不要押到週一**——使用者 2026-08-10：「如果知道有漏為什麼要等下週再更新，直接跑即時更新吧？」
一週一次講的是「主動出去掃描」的頻率，不是「已知缺口的處理時機」；發現層每天都在跑，壓著已列名的缺口等一週沒有道理，而且處理「已列名的 N 檔」比盲掃便宜得多
（每週掃描的分工見 [ETF 募集週掃](etf-weekly-scan.md)）。

- `kind=listed`（已掛牌卻沒登錄）＝真漏網，儀表板 🔴 紅章——最優先，立即查證補登。
- offering（已核准／募集中待登錄）＝儀表板 ⚠ 琥珀章——同一輪一併 WebSearch 查證：有代號／募集期間就填正式欄位，只查得到「已核准」就用 `raise_hint`＋`asof` 登錄；
  **查無來源的欄位一律留空，不要猜代號或日期**。補完推分支（動到 `data/etf_upcoming.json` 會自動觸發 daily.yml 併入 main）。
- `pipeline` 欄（申請中、審查未過、或申報生效日尚未到）＝不警示也**不登錄**，生效後下輪自動升進 `items` 再處理。
  2026-08-28 起會上版（使用者：「有送件的 ETF 就可以更新上去即將登場」）：「即將登場」區第四組「已送件・審查中」精簡列自動展示 pipeline 內容
  （`fund_dashboard._applied_row`，同名去重、本家復華排最前、fail-open）——純展示，登錄／逼補時機不變（仍等申報生效）。

機制與坑見 [即將登場與新 ETF 自動發現](../main/etf-upcoming.md) 的「新 ETF『自動發現』層」。

#### 9⑨ 籌碼雷達兩行

使用者 2026-10-15 同意：「06:35 推播多帶兩行」。成功推播在 3 條市場重點之後，附上 `git show origin/main:data/lab/val_log.json`
最新資料日（`days` 最後一個鍵）的 `push` 欄，**原文照貼**。可能的行：

- 第一行＝下一個交易日開盤／收盤要做的買賣（例「10/16（五）沒有排定的買賣。」）；
- 台股新飆股有要賣要買時多一行（例「新飆股：11/2（一）開盤賣 奇鋐、買 金像電。」，2026-10-24 起）；
- 美股強勢品質股有要賣要買時多一行（例「美股強勢品質股：10/26（一）開盤賣 INSW、買 PAYC。」；2026-10-28 前叫「美股三成」）；
- 少見但勝率高的策略接下來 2 個交易日要買或賣時多一行（例「少見機會：11/3（二）收盤 S&P 500 買進（期中選舉後抱一年，抱到 2027/11/2）。」，2026-10-27 起）；
- 最後一行＝策略驗證事件（有事件才有）。

檔案讀不到或沒有 `push` 就省略這幾行、**不擋推播**。這些行由 CI 重建籌碼雷達時產生（`arm/lab/valog.py`，見 [籌碼雷達介面改版歷史](../lab/chip-ui.md) 的「版面 v4」），
不必自己算、也不要改寫內容。

## 不能改的規則

1. 容器裡「絕不」跑資料抓取腳本（效率原則）；抓資料與權威版儀表板一律交給正式區。
2. 本地重建的 `dashboard/index.html` **絕不 commit**，驗完就丟；分支只帶「純新聞報告」，push 一樣觸發 CI、一樣有權威建表。
3. 不必開 PR、不必 merge：main 每天一筆「單一 commit」由 CI 寫。
4. `check_reports.py` 報「摘要／影響分析皆空」是報告的標籤沒加粗體：改報告，**不要改渲染端**、不要放寬解析。
5. 數字核對 🔴 不擋發佈，但步驟 9 看到就要立即修正重推。
6. 9⑤ 缺口晨間只讀不補，連兩天紅才親自補；9⑧ 缺口當天處理、查無來源的欄位留空不猜；9⑨ 照貼不改寫、讀不到不擋推播。
7. 完成定義只到「CI commit 在 main＋該 `daily.yml` run success＋該 commit `nav_date` 已推進」，不可宣稱線上已生效（見 [部署](deploy.md)）。

## 踩過的坑

- **從容器「截圖」線上頁做不到（2026-07 實測）**：agent proxy 對 `fuhhwa-fund-radar.vercel.app:443` 回 **CONNECT 403（政策拒絕）**，與擋 fhtrust／etfinfo 同一套網路政策；
  Playwright/WebFetch/curl 一律不通。除非使用者改用更寬鬆的環境網路政策，否則別再嘗試截圖、白費算力；改讀 main 上的檔（步驟 9）。
- **本地 `dashboard/index.html` 每天 commit 會和 CI 打架（2026-07-23 省 token 優化）**：本地重建帶的是舊 NAV／ETF 快照。
  ①CI 稍後會用真實資料權威重產覆蓋，本地版沒有保留價值；②每天 commit 它幾乎必與 CI 的儀表板 commit 打架，逼出一整輪 fetch+merge+重建+re-push
  （實測是每日流程最大 token 消耗源）。修法＝步驟 4 驗完就丟（規則 2）。
- **舊架構「一天兩筆 commit、Vercel 常部到舊版→新聞會動淨值不動」**：步驟 7 的單一 commit（2026-07-18）根治，main 每天只有一筆權威 commit。
- **外資淨空單誤引彙整站**：報告寫 83,605 口、官方實為 86,189——步驟 3 數字核對與發佈策略就是為這種錯而設。
- **YouTube 全空（2026-08-07）**：push 觸發的 daily.yml 用「被推分支」上的 workflow 檔，排程會話分支若分岔自「daily.yml 掛上 YOUTUBE_API_KEY env（08-06 早）」之前的 main，
  該輪 env 就沒金鑰 → YouTube 全空，當時整段 social 還被洗成 0。現由 `fundnews._carry_social` 來源級防呆擋住：單平台全空沿用既有項目，
  CI 日誌會印「社群 youtube 本次全空、沿用既有 N 則」。補救與根治見 9⑦。
- **ETF 持股簡介慢慢倒退沒人發現（2026-10-21）**：ETF 持股原本只有測試的 95% 門檻守，主動式天天換股、滑到 97%（72 檔）。修法＝缺口檔加 `etf` 那一類（9⑤）。

## 歷史

- 2026-07：效率原則檢討，容器不再跑抓取腳本。
- 2026-07-18：步驟 7 改成 push 即自動觸發、CI 單一 commit。
- 2026-07-20：數字核對的發佈策略（🔴 不擋發佈、立即修正重推）。
- 2026-07-23：步驟 3 加前十大簡介檢查；步驟 4 改成驗完丟棄本地 index.html。
- 2026-07-31：`check_reports.py` 加「摘要／影響分析皆空」。
- 2026-08-03：新增 9⑥。
- 2026-08-07：新增 9⑦。
- 2026-08-10：新增 9⑧；同日兩度調整——先分級警示，再改「見到就處理」。
- 2026-08-12：9⑤ 全自動落地（併檔通道 PR #201）；同日改「主責＝15:33 盤後班」。2026-08-12 前的舊流程要開 PR 人工 merge（首例 PR #200），通道上線後勿再走。
- 2026-08-20：`check_reports.py` 加漲跌分析欄與大變動提及。
- 2026-08-28：9⑧ 的 pipeline 上版。
- 2026-10-13：`check_reports.py` 加頭段總覽／速覽與行事曆台灣區。
- 2026-10-15：新增 9⑨。
- 2026-10-21：缺口檔加 ETF 持股。
- 2026-10-24：缺口檔加美股三成；推播多新飆股一行。
- 2026-10-27：推播多少見機會一行。
- 2026-10-28：推播的「美股三成」改叫「美股強勢品質股」。
