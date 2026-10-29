# 「全部更新」每日 SOP

> 效率原則、產提示包、合規掃描與 QA、重建驗證、commit、CI 單一 commit、步驟 9 驗證線上內容（含 9⑤～9⑨）。
>
> 這一頁目前是從 CLAUDE.md 逐字搬來的（知識庫第一段），還沒整理；有出入時以 CLAUDE.md 為準。
> 改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產這一頁。

<!-- CLAUDE.md 第 3–17 行 -->
## 指令：「全部更新」／「資料更新」

使用者只要打**「全部更新」**（或「資料更新」），第一時間直接執行，不要再詢問。

> **效率原則（2026-07 檢討，務必遵守——這是本流程最重要的一條）**：本 Claude 容器 proxy 會擋掉**所有**
> 資料來源站（`fhtrust.com.tw` 403、`etfinfo.tw` 403、Google News、PTT），所以在這裡跑
> `fetch_holdings.py`／`fetch_fund_news.py`／`fetch_etf_watch.py` **注定失敗或卡到逾時**
> （實測 `fetch_etf_watch.py` 在此**空轉逾 20 分鐘**、`fetch_holdings.py` 25 檔全 403）——那不是程式 bug，
> 是環境限制，正式區完全不會發生。這三支抓取「正式區」（`daily.yml` GitHub Actions，擁有者身分、完整網路）
> **本來就會自己跑**。**因此在這裡「絕不」跑資料抓取腳本**——只做「只有 Claude 能做」的事（WebSearch 產新聞
> 內容），把資料抓取＋權威版儀表板整包丟給正式區，最後**讀 CI 入庫的 `dashboard/index.html` 驗證線上內容**
> （截圖 Vercel 線上頁被同一套 proxy 政策擋、做不到，詳見步驟 9）。這樣可省下每次約 25 分鐘的空轉。

1. **產提示包**（本地、秒級，是 WebSearch 的輸入，**要跑**）：
   `TZ=Asia/Taipei python3 scripts/gen_usnews.py && TZ=Asia/Taipei python3 scripts/gen_twnews.py && TZ=Asia/Taipei python3 scripts/gen_macronews.py`
<!-- CLAUDE.md 第 218–261 行 -->
3. **合規掃描＋內容 QA＋數字核對**：`gen_usnews.py --check`、`gen_twnews.py --check`、`gen_macronews.py --check` 全須 🟢；
   另跑 `TZ=Asia/Taipei python3 scripts/check_reports.py` 須 🟢（檔案齊全／每報≥4卡／每卡有連結與重要度／
   **每卡摘要或影響分析非空**／**2026-08-20 起：每卡漲跌分析欄＋影響分析≥2條＋分析合計≥120字**（【深度】卡豁免）／
   **2026-08-20 起：大變動提及**（官方序列旗標的資產，對應報告全文須提及；序列過期或落檔讀不到＝跳過）／
   **2026-10-13 起：頭段總覽／速覽抽得到**（美股 v1／總經「…總覽」、台股「盤前／盤後速覽」；見列印版專節踩坑⑤）／
   **2026-10-13 起：行事曆台灣區與精簡上限**（台／台股列或「本週無」註記、總列數 ≤30、引言 ≤220 字）／
   行事曆為今日）——「摘要／影響分析皆空」該項是 2026-07-31 新增的防呆，
   🔴 訊息會直接指出是標籤沒加 `**粗體**`（見步驟 2 與下方專節），照著把該報告的 `N. 標籤：` 改成
   `N. **標籤**：` 即可，勿改渲染端；
   **再跑 `TZ=Asia/Taipei python3 scripts/check_holdings_intro.py`（前十大簡介覆蓋率，🔴＝有持股缺簡介）——
   見 🔴 立即 WebSearch 查證後把缺的標的補進 `config/holding_profiles.json`（格式 `{name: {intro, ticker, country, verified}}`、
   純事實非投資建議、避開禁用詞），補到 🟢 為止**（2026-07-23 使用者：前十大簡介一再漏掉，此為固定防呆步驟，不可略；
   補完隨步驟 6 push 即自動落地——該檔走 daily.yml 併檔自動通道，不需 PR，見步驟 9⑤）；
   再跑 `TZ=Asia/Taipei python3 scripts/check_numbers.py`（高風險數字對官方 API——本容器 proxy 擋 twse/taifex
   會全 ⚪ 屬正常，真正核對在 CI）。**發佈策略（2026-07-20 使用者兩指示並行：數字要對＋防線不可硬到什麼都沒更新）**：
   CI 端 🔴 **不擋發佈**——結果落 `data/factcheck.json` 隨每日 commit 入板、儀表板「網頁更新時間」區顯示
   紅色警示章；主會話在步驟 9 驗證時讀該檔，見 🔴 **立即修正該數字並重推**（分鐘級收斂）。
   曾踩：外資淨空單誤引彙整站 83,605 口、官方實為 86,189。
4. **重建儀表板驗證**（本地、秒級，只為確認新聞入板＋渲染管線沒被新內容弄壞；**不需先抓資料**）：
   `TZ=Asia/Taipei python3 scripts/gen_fund_dashboard.py`，確認「🕒 資料更新時間」區塊**新聞欄位**已更新至今日。
   **驗完務必 `git checkout -- dashboard/index.html` 丟棄本地重建結果**（2026-07-23 省 token 優化）——
   本地重建的 index.html 帶的是舊 NAV／ETF 快照，**絕不 commit**：①CI 稍後會用真實資料權威重產覆蓋，
   本地版沒有保留價值；②每天 commit 它幾乎必與 CI 的儀表板 commit 打架，逼出一整輪 fetch+merge+重建+
   re-push（實測是每日流程最大 token 消耗源）。丟棄後分支只帶「純新聞報告」，push 一樣觸發 CI、一樣有權威建表。
5. **測試**：`python3 -m pytest -q` 全綠（此容器預設無 pytest，先 `pip install -q pytest`）。
6. **commit＋push** 到本次會話指定分支：**只帶「新聞報告」**（`reports/*.md`＋提示包；**不帶 `dashboard/index.html`**——見步驟 4，本地版不 commit，由 CI 產權威版；`data/*` 被擋未更新、不會有 diff）。訊息用 `chore: 每日新聞更新 {日期}`。**不必開 PR、不必 merge 進 main**——見步驟 7，改由 CI 一次 commit。
7. **正式區「單一 commit」抓真實資料＋建表＋部署（2026-07-18 起：push 即自動觸發）**：
   步驟 6 的 push 動到 `reports/**` 時，`daily.yml` 會**自動觸發**（`on: push branches claude/** paths reports/**`），
   以被推分支為 `news_ref`——**不需、也不必再手動呼叫 GitHub API/MCP**（排程 Routine 的新會話沒有 MCP 工具，靠這條就夠）。
   CI 會：①checkout main、把該分支今日 `reports/*.md` 併入 → ②抓**真實** NAV／持股／ETF／基金新聞 → ③重建儀表板 →
   ④以擁有者身分**一次 commit 進 main（新聞＋真實資料＋建表同一筆）** → ⑤打 Deploy Hook 部署。
   **這根治了舊架構「一天兩筆 commit、Vercel 常部到舊版→新聞會動淨值不動」的坑**：main 每天只有**一筆權威 commit**。
   （互動會話若 push 沒觸發（如只改程式碼未動 reports），備援：`mcp__github__actions_run_trigger` 帶 `inputs={"news_ref":"<分支>"}`；
   留空 `news_ref`＝排程 cron 行為：只用 main 現有新聞重刷資料。）
9. **驗證線上內容（「全部更新」的完成定義＝網頁真的更新）**：等 `daily.yml` 跑完（約數分鐘）後驗證。
   - **Vercel 線上網址**：`https://fuhhwa-fund-radar.vercel.app/#overview`。
   - ⚠ **從此容器「截圖」線上頁做不到**（2026-07 實測）：agent proxy 對 `fuhhwa-fund-radar.vercel.app:443`
     回 **CONNECT 403（政策拒絕）**，與擋 fhtrust／etfinfo 同一套網路政策；Playwright/WebFetch/curl 一律不通。
     除非使用者改用更寬鬆的環境網路政策，否則別再嘗試截圖、白費算力。
   - ✅ **可行的「內容已產出」驗證**：直接讀 **main 上 CI 剛 commit 的那支檔**——
     `git fetch origin main && git show origin/main:dashboard/index.html` 後檢查：①美股／台股新聞、總經・政策
     皆今日日期；②「🕒 產表」時戳為 CI 那次（會比本地時戳晚，證明 CI 已重產覆蓋）；③ETF 表有值；④基金
     `data/funds/*.json` 的 `nav_date` 已推進（NAV 常見 T+1，今日只到昨日 NAV 屬正常）。並用
     `mcp__github__actions_*` 確認該次 `daily.yml` run `success`。
<!-- CLAUDE.md 第 289–356 行 -->
   - **⑤ 前十大簡介缺口（2026-07-23 使用者：一再漏掉；2026-08-12 全自動落地；同日改「主責＝15:33 盤後班」）**：讀
     `git show origin/main:data/holdings_intro_gap.json`。**晨間本步驟只讀不補**（使用者 2026-08-12：
     不佔早上、跟最簡單的那班）——count>0 → 成功推播裡帶一句「缺 N 檔簡介，15:33 班會補」即可；
     **補齊主責＝15:33 盤後籌碼 Routine 步驟②**（該班最輕、又在晨間持股抓取之後，缺口當天下午清）。
     **連兩天 count>0**（昨天下午沒清＝排程搬家前過渡期或該班失效）才在晨間親自跑下列迴路並查原因。
     **2026-10-21 起缺口檔也含 ETF 持股**（`items[].src`＝`fund` 基金前十大／`etf` ETF 完整持股；
     ETF 那幾筆另帶 `ticker`＝補進 profiles 的代號、`etfs`＝哪幾檔持有）——ETF 持股原本只有測試的
     95% 門檻守，主動式天天換股、滑到 97%（72 檔）沒人發現；`etf_holdings.yml` 抓完持股也跑一次檢查。
     **2026-10-24 起也含美股三成**（`src`＝`usqm`：配置頁美股列的股票＝手上的、要買的、名單前 5 名裡手上沒有的，
     `fund_intro.uncovered_us_qm`；`name`＝每週紀錄的英文公司名、`ticker`＝代號）——使用者：「美股那些公司誰知道你是什麼公司…
     台股不都有列嗎？比照著做」。美股簡介**照「美國 公司名（中文名若有），本業；細節」寫**：配置頁取「；」前那一段，
     「，」前＝公司名（去掉「美國」與結尾括號）、後＝本業一行（`corepage.us_label`）。名單每週六換，新進前 5 名的公司週一下午這班補。
     **極簡迴路**（15:33 班與晨間 backstop 共用；全程 ~5 分鐘、不跑任何抓取腳本）：
     ① gap 檔 `items[].name` 就是快照原字串（已還原 `&amp;` 等實體）——**每檔 1 次 WebSearch** 查證（公司本業／代號／國別）；
     ② 補進 `config/holding_profiles.json`（`{原字串: {intro, ticker, country, verified, url?}}`，
        intro 純事實、避開禁用詞；country＝公司母國，如英飛凌→德國；**`url` 選填＝
        基金型持有（組合型的子基金，無掛牌代號）的鉅亨基金頁**
        `https://fund.cnyes.com/detail/{名稱}/{cnyesId}`——渲染端優先用它，沒 url 又沒
        ticker 的基金名去搜 Yahoo 必落空（2026-08-12 使用者：「點進去沒東西」）；
        股票/ETF 不用填，ticker＋country 會自動產 Yahoo 行情連結）；
     ③ `TZ=Asia/Taipei python3 scripts/check_holdings_intro.py` 須 🟢——它同時把本地 gap 檔歸零，
        **一起 commit**（下一輪重建紅章即滅，不等 CI 自查）；
     ④ `python3 -m pytest -q tests/test_holdings_intro.py` 秒級確認 → commit＋push 本會話分支。
     **push 即收工**：`config/holding_profiles.json` 已入 daily.yml 自動併檔通道（同
     `data/etf_upcoming.json` 模式，防呆＝JSON 驗證＋有簡介筆數不得減少）——**不需開 PR、
     不需 merge、不需 dispatch、不需監看**，push 觸發的那輪 CI 自動併入 main＋重建＋部署。
     （2026-08-12 前的舊流程要開 PR 人工 merge——首例 PR #200；通道上線後勿再走。）
     ⚠ **生效條件＝本會話分支 fork 自「通道已上線（2026-08-12 PR #201）」的 main**——push 觸發
     的 daily.yml 用**被推分支**的 workflow 檔（同 9⑦ YOUTUBE 金鑰傳播機制）。分支太舊時徵狀＝
     push 後 main 的 profiles 沒動：補救＝`mcp__github__actions_run_trigger` dispatch daily.yml
     （ref=main、news_ref=本分支——dispatch 用 main 的 workflow 檔，併檔段必有通道）；根治＝排程搬家。
   - **⑥ 盤後完整性警示（2026-08-03 新增）**：讀 `git show origin/main:data/afterhours_alert.json`——
     `date`＝昨日且 `missing` 非空＝昨天盤後有缺口且到深夜都沒自癒（夜檢 Routine 應已推播過）；
     早上這班會把缺口補齊，但請在推播裡帶一句、並查 afterhours run 日誌找根因。
   - **⑦ 社群 YouTube 驗證（2026-08-07 使用者：「每次更新都順便查一下 YouTube」）**：讀
     `git show origin/main:data/fund_news.json`，`social` 內 `platform=="youtube"` 支數須 ≥1
     （三層清單正常日不會是 0；為 0 時儀表板「網頁更新時間」列會掛「社群 YouTube 🔴 0 支」章）。
     為 0 ＝金鑰沒帶到或抓取失敗：查該輪 CI 日誌 grep `[fundnews]`／`未設 YOUTUBE_API_KEY`。
     **已知根因（2026-08-07 踩坑）：push 觸發的 daily.yml 用「被推分支」上的 workflow 檔**——
     排程會話分支若分岔自「daily.yml 掛上 YOUTUBE_API_KEY env（08-06 早）」之前的 main，
     該輪 env 就沒金鑰 → YouTube 全空（當時整段 social 還被洗成 0，現由 `fundnews._carry_social`
     來源級防呆擋住：單平台全空沿用既有項目、CI 日誌會印「社群 youtube 本次全空、沿用既有 N 則」）。
     補救＝`mcp__github__actions_run_trigger` dispatch daily.yml（ref=main、news_ref 留空）——
     dispatch 用 main 的 workflow 檔、金鑰必在；根治＝排程搬家到新視窗（新分支自最新 main 分岔）。
   - **⑧ 漏網新 ETF（2026-08-10 新增；同日兩度調整——先分級警示，再改「見到就處理」）**：讀
     `git show origin/main:data/etf_upcoming_gap.json`。**`items` 非空就當天處理完，不要押到週一**
     （使用者 2026-08-10：「如果知道有漏為什麼要等下週再更新，直接跑即時更新吧？」——
     **一週一次講的是「主動出去掃描」的頻率，不是「已知缺口的處理時機」**；發現層每天都在跑，
     壓著已列名的缺口等一週沒有道理，而且處理「已列名的 N 檔」比盲掃便宜得多）：
     · `kind=listed`（已掛牌卻沒登錄）＝真漏網，儀表板 🔴 紅章——最優先，立即查證補登；
     · offering（已核准／募集中待登錄）＝儀表板 ⚠ 琥珀章——**同一輪一併 WebSearch 查證**，
       有代號／募集期間就填正式欄位、只查得到「已核准」就用 `raise_hint`＋`asof` 登錄，
       **查無來源的欄位一律留空，不要猜代號或日期**；補完推分支（動到
       `data/etf_upcoming.json` 會自動觸發 daily.yml 併入 main）；
     · `pipeline` 欄（申請中、審查未過、或申報生效日尚未到）＝不警示也**不登錄**，
       生效後下輪自動升進 `items` 再處理。**2026-08-28 起會上版**（使用者：「有送件的
       ETF 就可以更新上去即將登場」）：「即將登場」區第四組「已送件・審查中」精簡列
       自動展示 pipeline 內容（`fund_dashboard._applied_row`，同名去重、本家復華排最前、
       fail-open）——純展示，登錄／逼補時機不變（仍等申報生效）。
     機制與坑見下方「新 ETF『自動發現』層」專節。
   - **⑨ 籌碼雷達兩行（2026-10-15 使用者同意：「06:35 推播多帶兩行」）**：成功推播在 3 條市場重點之後，附上
     `git show origin/main:data/lab/val_log.json` 最新資料日（`days` 最後一個鍵）的 `push` 欄**原文照貼**：
     第一行＝下一個交易日開盤／收盤要做的買賣（例「10/16（五）沒有排定的買賣。」），台股新飆股有要賣要買時多一行（例「新飆股：11/2（一）開盤賣 奇鋐、買 金像電。」，2026-10-24 起），美股強勢品質股有要賣要買時多一行（例「美股強勢品質股：10/26（一）開盤賣 INSW、買 PAYC。」；2026-10-28 前叫「美股三成」），少見但勝率高的策略接下來 2 個交易日要買或賣時多一行（例「少見機會：11/3（二）收盤 S&P 500 買進（期中選舉後抱一年，抱到 2027/11/2）。」，2026-10-27 起），
     最後一行＝策略驗證事件（有事件才有）。
     檔案讀不到或沒有 `push` 就省略這兩行、**不擋推播**。這兩行由 CI 重建籌碼雷達時產生（`arm/lab/valog.py`，見「版面 v4」專節），
     不必自己算、也不要改寫內容。
   - 註：持股基準為月度值（顯示上月底）——不是資料沒更新。

