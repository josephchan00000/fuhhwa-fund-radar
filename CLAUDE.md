# CLAUDE.md — 復華基金雷達 · 給 Claude 的操作規則

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
2. **上網查證產新聞內容**（**Claude 專屬、不可省、~10 分**；純 Python 不杜撰新聞，此步用 WebSearch 補；可派平行子代理，各自嚴守提示包版型）：
   - `reports/usnews/{今日}_v1.md`、`_v2.md`（昨夜美股；先查證美股當日是否休市）
   - `reports/twnews/{今日}.md`（台股；週末/休市日改寫最近交易日並註明）
   - `reports/macronews/{今日}.md`、`reports/macrocal/{今日}.md`（總經政策＋本週行事曆；
     行事曆涵蓋**美國＋歐盟＋中國＋日本**重點數據與**重要企業財報／法說**，項目加「美：／歐：／中：／日：／財報：」前綴；
     引言須含**「市況」段**（2026-07-22 使用者需求）：`市況：台股 …｜美股 …｜日股 …｜韓股 …｜陸股 …｜港股 …`
     六市場依序、全形「｜」分隔，各填「正常交易」或「M/D 因〇〇休市」——儀表板今日重點據此
     產雙視圖 chip（台股頁＝台股本身、全球頁＝美＋日韓陸港），格式勿改）
   - **週末合併時窗**（提示包會自動帶入 `usnews.weekend_note()`）：週六涵蓋週五晚間起、週日再含週六、
     **週一須把週五晚間＋週六＋週日整個週末最重要的新聞一次綜合整理**，不可只看最近一天。
   - **提示包已自動預算（2026-07 效率優化，不必再自己查）**：①`usnews.calendar_anchor()` 已算好
     「今日星期幾／對應昨夜美股實際交易日／鄰近美股休市日」——**直接採信、勿再花搜尋自行推算星期與假日**；
     ②`usnews.prior_block()` 已把前一日日報的卡標題列成「已報導清單」——**清單內的舊聞若無新進展就直接略過、不要重查**。
   - 不重複收錄前一日已報導的舊聞；有新進展標【延伸】。每卡至少 1 條真實可點 [標題](URL)。
   - **來源以主流媒體為主（2026-07-20 使用者指示，規則已寫進提示包 `usnews.SRC_RULE_GLOBAL/_TW`）**：
     台股首選經濟日報／工商時報／中央社／聯合／鉅亨；全球首選 WSJ／FT／CNN／Reuters／Bloomberg／
     CNBC／富途牛牛。**每卡至少 1 條主流媒體原文連結**；聚合站（ts2.tech、KuCoin 等）只能當補充、
     不得為唯一出處。
   - **卡數下限＝每報 ≥4 卡**（2026-07 由 6 調降以省時；門檻仍為重要度 6/10 以上、上不封頂，深度文照樣保底 1 篇）。
   - **深度報告精選保底 1 篇**（台股與美股報告各自保底；標題括注用【深度】）：台股從經濟日報／
     工商時報／中央社專題／財訊・今周刊挑；美股從富途牛牛深度文、Reuters Analysis／Bloomberg
     深度專題挑。只挑真深度（產業鏈拆解/商業模式/政策影響），當日不足放寬到近 3 天並註明刊出日。
   - **子代理回傳格式＝精簡三行（2026-07-23 省 token；派工 prompt 末段務必明確要求）**：只回
     ①卡數 ②各卡標題一行清單 ③check 結果（🟢/🔴）。**不要**逐項複述查證過程、口徑核對細節、
     排除的假線索、資料侷限全文——那些寫進報告檔即可，主會話需要時直接 grep 該檔。整段回傳控制在
     ~15 行內。（真實內容都在 `reports/*.md`；主會話只需知道「幾卡、標題、有沒有過 check」就能收尾。）
3. **合規掃描＋內容 QA＋數字核對**：`gen_usnews.py --check`、`gen_twnews.py --check`、`gen_macronews.py --check` 全須 🟢；
   另跑 `TZ=Asia/Taipei python3 scripts/check_reports.py` 須 🟢（檔案齊全／每報≥4卡／每卡有連結與重要度／行事曆為今日）；
   **再跑 `TZ=Asia/Taipei python3 scripts/check_holdings_intro.py`（前十大簡介覆蓋率，🔴＝有持股缺簡介）——
   見 🔴 立即 WebSearch 查證後把缺的標的補進 `config/holding_profiles.json`（格式 `{name: {intro, ticker, country, verified}}`、
   純事實非投資建議、避開禁用詞），補到 🟢 為止**（2026-07-23 使用者：前十大簡介一再漏掉，此為固定防呆步驟，不可略）；
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
   - ⚠️ **「內容在 main」≠「線上已部署」——2026-07-17 踩過的大坑，務必分清**：
     - **單一 commit 架構（步驟 7）已根治「兩筆 commit」問題**：main 每天只有一筆權威 CI commit（新聞＋真實資料＋建表同一筆），不會再有「合併版舊資料」被誤部署。舊坑徵狀是「**新聞會動、淨值不動**」——若再出現，先查 main 最新 commit 的 `data/funds/*.json` `nav_date` 是否真的新（否則是 `news_ref` 沒帶到／CI 沒抓到資料），再查 Vercel 部署對到哪個 commit。
     - **我（容器內 Claude）看不到 Vercel 線上頁**（proxy CONNECT 403），所以**不可只憑「main 檔已更新」就宣稱「線上已生效」**——那是我 07-17 誤報的錯。我的完成定義只到「**CI commit 在 main＋該 `daily.yml` run success＋該 commit `nav_date` 已推進**」；「**線上真的更新**」需使用者端或 Deploy Hook 確認。
     - **主動部署**：`daily.yml` 末步已加「打 **Vercel Deploy Hook**」（`secrets.VERCEL_DEPLOY_HOOK`）——CI commit 完直接觸發 production 部署 main 最新，**不靠 Vercel 自動偵測**（自動偵測曾卡 Initializing／部到舊版）。**使用者需先建 hook**：Vercel 專案 Settings→Git→Deploy Hooks 建 `main` 分支 hook → URL 存成 repo secret `VERCEL_DEPLOY_HOOK`。未設時該步自動跳過、不影響 commit。
     - Vercel `vercel.json` 已設 `Cache-Control: no-store`（全站不快取）→ **線上看到舊的一律是「沒部署」而非快取**，別叫使用者清快取白忙。
   - **⑤ 前十大簡介缺口（2026-07-23 使用者：一再漏掉，務必查）**：讀 `git show origin/main:data/holdings_intro_gap.json`，
     `count` 須為 0。若 >0＝CI 端抓到新持股缺簡介（見下方專節根因）——**立即 WebSearch 補進
     `config/holding_profiles.json` 並重推**（同數字核對 🔴 的分鐘級收斂）；儀表板「網頁更新時間」列也會顯示 🔴 警示章。
   - 註：持股基準為月度值（顯示上月底）——不是資料沒更新。

## 指令：「排程搬家」（2026-07-24 建立；使用者約 3–5 天執行一次）

使用者在**任何**對話窗打**「排程搬家」**（或「搬排程」）＝把每日 06:35 自動更新 Routine 改綁到**當前**
對話窗。**不要詢問、不要查證其他東西、不改任何檔案、不 commit**——固定三個 MCP 呼叫收工（最省 token）：

1. `list_triggers`（先用預設 limit；找不到再用 cursor 翻頁）→ 找**名稱以「復華基金雷達 每日全部更新」
   開頭且 `enabled:true`** 的 Routine。若它的 `persistent_session_id` 已是本會話 → 回一句「排程已綁本視窗」結束。
2. `create_trigger`（預設自綁本會話，**不帶** `persistent_session_id`／`create_new_session_on_fire`）：
   - name：`復華基金雷達 每日全部更新(台北 06:35・07:03 前完成)`
   - cron_expression：`35 22 * * *`（＝台北 06:35）
   - prompt：**下方原文照抄、一字不改**。
3. `delete_trigger` 刪掉步驟 1 找到的舊 Routine（機制備忘：`update_trigger` 改不了綁定會話、跨會話
   update 也被組織政策擋，但**跨會話 delete 可行**——2026-07-24 實證；所以搬家＝建新＋刪舊，不是改舊）。
4. 一句話回報：新 trigger id＋下次觸發時間。create_trigger 若警告「no MCP connectors」**可忽略**
   （SOP 第 7 步走 push 自動觸發、驗證用 git，不依賴 MCP）。
5. **回報時務必提醒使用者「模型要重設」**（2026-07-27 使用者踩到：以為設過 sonnet，實際每日跑都是
   新視窗的預設模型）。機制：trigger 的 `job_config` **沒有 model 欄位**，只有 `persistent_session_id`
   ——每日火進哪個視窗，就用**那個視窗當下的模型**。舊視窗設過的 `/model` **不會**跟著搬家過來，
   新視窗一律回到預設。所以每次搬家後，使用者要在**新視窗**自己打一次 `/model sonnet`
   （容器內 Claude 無法代勞，`update_trigger` 的 model 參數對綁定會話的 routine 也無效）。

Routine prompt 原文（步驟 2 照抄用）：

> （排程自動觸發）全部更新。依 repo CLAUDE.md「指令：全部更新」SOP 完整執行：產提示包 → 平行子代理 WebSearch 產當日新聞（美股 v1/v2、台股、總經、行事曆；嚴守版型／禁用詞／每卡連結）→ gen_*.py --check 與 check_reports.py 全 🟢 → 重建儀表板 → pytest 全綠 → commit+push 到本會話指定分支（push 動到 reports/** 會自動觸發 daily.yml）→ 等 main 前進後驗證（新聞今日、產表時戳為 CI、nav_date 推進）。完成或失敗都用 PushNotification 推播一句話結果給使用者（成功：當日 3 條市場重點摘要；失敗：卡在哪一步＋影響）。不可宣稱「線上已生效」（本環境看不到 Vercel）。若工作樹有未完成的其他工作，先 stash 或用獨立分支，勿混入每日更新 commit。

## 每日固定時間自動更新（2026-07-18 建立；同日改「火進主會話」模式）

- **排程 Routine**（claude.ai Routines）：每天 **台北 06:35**（UTC 22:35）**火進主會話**跑「全部更新」SOP。
  目標：**07:03 前線上可看當日內容**（2026-07-20 使用者指示；實測全程 15–28 分，06:35 起跑最壞壓線、
  一般 06:55 完成）。**trigger id 與綁定會話會隨「排程搬家」（見下方專節）改變**——一律以
  `list_triggers` 實查為準，本檔不再記死 id（2026-07-24 起；使用者約每 3–5 天在新視窗搬一次）。
- **為何不用「開新會話」模式（2026-07-18 實測兩次全滅，勿走回頭路）**：fresh-session 點火綁的環境
  （env_01FK…「化學」）沒掛本 repo source，會話起來連最小 heartbeat push 都做不到（第二次點火帶
  「3 分鐘心跳測試」指令仍 18 分鐘零輸出）。改火進主會話後有 repo、有 GitHub MCP、有完整脈絡；
  「火進既有會話」模式在本帳號有 07-13 send_later 成功先例。完成/失敗以 PushNotification 推播使用者。
- **想省 token 改用 sonnet 跑排程（2026-07-23 使用者需求）＝目前工具做不到，機制備忘**：
  ① 本排程 Routine 綁在**持久主會話**，其模型「跟著該會話走」——不是跟著 trigger；
  ② `update_trigger` 改模型全組織停用（回 `model_update_disabled`）；改綁在其他會話的 trigger 也被擋；
  ③ 新開會話仍預設落在無 repo 的「化學」env（同上兩次全滅主因）。
  **唯一可行槓桿＝在「排程當前綁定的主會話」內執行 `/model sonnet`**（會固定生效、
  之後每日火進該會話即用 sonnet）；此動作只能由使用者在該會話操作，容器內 Claude 無法代勞。
  若日後組織開放 routine 模型設定、或把本 repo 掛上某個可排程 env，才談得上「fresh sonnet 會話」路徑。
- 排程點火的回合若 MCP 不可用，SOP 第 7 步照樣走「push 自動觸發」；驗證用 git（fetch origin main
  看是否前進＋檢查檔案內容）即可。
- **備援**：repo cron 移至**台北週一~六 07:15**（2026-07-20 起，原 06:50）——改為「事後兜底」：Routine 失敗時
  新聞沿用前日（或撿分支已推的今日新聞），但 NAV／持股／ETF 照樣更新；頁面瀏覽器端有「逾 2 天未重建」
  紅色警示橫幅當最後防線。
- **部署**：CI commit 後打 `secrets.VERCEL_DEPLOY_HOOK` 主動部署；**該 secret 未設前**，部署仍靠 Vercel 自動偵測
  （曾卡 Initializing）——如使用者回報線上沒更新，先問 Vercel Deployments 對到哪個 commit。

## 已知環境限制與防呆（曾踩過的坑，不要再犯）

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
- **前十大持股「簡介一再漏掉」的根因與防呆（2026-07-23 使用者多次反映，務必守住）**：
  - **根因**：持股在**正式區 CI 抓**（本容器 proxy 擋 fhtrust，抓不到）——每月換持股時，新標的名
    **只會出現在 CI 產出的 `data/funds/*.json`**，容器端（主會話）看到的是舊快照，本地檢查／pytest
    自然抓不到新標的缺簡介 → 漏的簡介直接隨 CI commit 上線。這不是誰忘了，是「抓取在 CI、補簡介在容器」
    的時間差結構性造成。
  - **防呆（三道，缺一不可）**：
    ① **CI 端即時偵測**：`daily_fund.sh` 在建表前跑 `scripts/check_holdings_intro.py`，把缺口寫
       `data/holdings_intro_gap.json`（入庫），儀表板「網頁更新時間」列顯示 🔴「N 檔缺簡介」警示章。
    ② **每日 SOP 固定步驟**（步驟 3 與步驟 9⑤）：主會話每輪讀該 gap 檔，見 🔴 立即 WebSearch 補
       `config/holding_profiles.json` 並重推——分鐘級收斂，比照數字核對 🔴。
    ③ **pytest 守覆蓋**：`tests/test_holdings_intro.py` 斷言「已入庫的基金快照前十大 100% 有簡介」，
       容器端一旦看到含新標的的快照就會紅、逼在發佈前補齊。
  - **補簡介格式**：`config/holding_profiles.json` 的 `profiles` 下 `{持股原字串: {intro, ticker, country, verified}}`；
    key 必須是 `data/funds/*.json` 內 `top_holdings[].name` 的**原字串**（含 `*` 等後綴，精確對應）；
    intro 純事實描述、非投資建議、避開禁用詞。冷門標的先 WebSearch 查證再寫。
- **`check_numbers.py` 在容器內跑會把 `data/factcheck.json` 洗成「全 ⚪」**（2026-07-29 踩坑：
  容器 proxy 擋 twse/taifex → 一項都核不到，CI 的 10 🟢 被覆寫成 0 🟢/11 ⚪ 並隨 commit 上板）。
  已加落檔防呆：**本次 0 🟢 0 🔴、而既有落檔曾核到過 → 不覆寫**。跑完仍請 `git status data/` 確認。
  同型提醒：commit 前用 `git add <明確路徑>`，少用 `git add -A`——本次就是 `-A` 把 smoke-run 的
  degraded 檔一起帶進 commit。
- **新聞來源黑名單**：排除「富聯網」（moneylink）。
- **禁用詞**（正文不得出現，機構觀點也要改寫避開）：保證、穩賺、必賺、包賺、必漲、必跌、一定會、唯一、
  建議買賣、建議買、建議賣、目標價、零風險、無風險、穩賺不賠。

## 儀表板「🕒 資料更新時間」區塊

`arm/fund_dashboard.py` 的 `_freshness_view()`，顯示各資料來源鮮度（皆台北時間）：
NAV 日／持股基準（月度）／持股快照抓取／美股新聞／台股新聞／總經・政策／經濟行事曆／基金新聞・社群／
ETF 數據追蹤／總經・籌碼數據／儀表板產表。新增資料來源時請同步加進此區塊。

## 「市場溫度計」（總經分頁，2026-07-23 使用者需求）

總經分頁**行事曆／政策新聞之後**的 `#macro-data` 區塊，兩張官方數據表（`arm/macrochips.py`
資料層、`arm/fund_dashboard._macro_data_view()` 渲染），每列＝最新值＋日變化＋近5日＋
近30日 inline SVG sparkline＋資料日：
- **全球市場溫度計**（Yahoo Finance 官方序列）：VIX（附平靜/正常/偏高/恐慌狀態燈）、
  美國 10 年期公債殖利率（`^TNX`÷10、日變化以 bp）、美元指數 DXY、美元兌新台幣、布蘭特原油、黃金。
- **台股籌碼**（TWSE／期交所官方）：三大法人買賣超（**合計主列可點 ▸ 展開外資／投信／自營商分項**，
  `inst_total/inst_foreign/inst_trust/inst_dealer` 四序列，`_twse_inst_all` 解析 BFI82U——
  外資列名為「外資及陸資(不含外資自營商)」含「自營」字樣，故以獨有「陸資」二字辨識，勿用「自營 not in」誤殺）、
  外資台指期未平倉淨部位（`淨空/淨多 X 口`）、融資餘額、融券餘額、台指選擇權 P/C 比。
- **呈現慣例（2026-07-23 使用者需求）**：①每列都帶單位（指數＝點、殖利率＝%、匯率＝元、油＝美元/桶、
  金＝美元/盎司、法人/融資＝億、融券＝張、期貨＝口）；②**指標名稱本身即官方揭露頁可點連結**
  （`_MD_SRC`，非表底 footer）；③**流量（買賣超）走勢用零基準長條圖**（`_spark_bars`，綠買超/紅賣超，
  單日爆量不會把折線拉歪），水準值（指數/價/餘額）才用折線 `_spark`（縮放至區間高低、看相對形狀）。

**踩過的坑：序列「靜默凍結」（2026-07-29 使用者回報「外資淨空單數字是錯的」）**——
`tx_foreign_net` 自 7/23 起停更、儀表板連續 6 天以現值姿態顯示 75,198。根因與三道修法：
- **根因① 抓取單點失效**：`futContractsDateDown` 單一參數組合失效後回 0 列（同時段 `pcRatioDown`
  正常＝非網路問題），舊碼沉默回 `{}`。→ 現改：**queryEndDate 夾到已結算交易日**
  （`_last_settled`，期交所 15:00 後才有當日資料）＋**多組 POST 參數變體依序試**＋**逐日兜底**＋
  **把 HTTP 狀態／例外寫進 CI 日誌**（本容器 proxy 擋期交所，日誌是唯一除錯管道）。
- **根因② 口徑沒鎖**：舊解析只認「列中有外資」，未驗商品 → 期交所若忽略 `commodityId` 就會安靜
  讀到小台／電子期。→ `_tx_rows_to_series` **強制商品＝臺股期貨(TX 大台)＋身份別＝外資（排除外資自營商）**；
  商品名在 CSV 是 rowspan 展平（只出現在該商品首列），故以「最後見到的非空商品名」延續，
  否則外資列會因商品名空白被整批丟棄。儀表板欄名改「外資台指期淨部位（**大台**）」、表註寫明
  **不含小台／微台**，與彙整站常見的「大＋小＋微台合計」口徑本就不會一致。
- **根因③ 過期看不見**：「抓不到就保留舊序列」保護了資料，卻讓凍結靜默。→ `_md_stale_badge()`：
  資料日落後逾 2 個交易日的指標，名稱下方顯示紅色 **⚠ 過期** 章（附落後天數 tooltip）。
- `factcheck.taifex_tx_foreign_net` 已改為呼叫同一支 `macrochips._taifex_tx_foreign`——
  **單一實作**，不要再各留一份解析（兩份會同時失效、又只顯示 ⚪「官方不可得」看不出原因）。
- **不要手動填補缺漏日的值**：實測各彙整站給出互相矛盾的數字（45,869／80,042／82,255），
  正是「誤引彙整站」同型坑。修抓取讓 CI 取官方值，過渡期由 ⚠ 過期章負責誠實揭露。

架構同 etf_watch 慣例：
- **資料層 `data/macro_chips.json` 必須入庫**（`.gitignore` 已加 `!` 例外）——跨日累積序列＋
  來源被擋時的 fallback。合併鐵則 `arm/macrochips._merge()`：本次官方新值覆蓋同日舊值，
  整段抓不到＝保留舊序列，值為 None 一律不寫入，**絕不把非空序列洗成空**；每指標留最近 45 筆。
- **官方抓取重用 `arm/factcheck.py`**（TWSE BFI82U 三大法人、TAIFEX TX 淨額、Yahoo 指數序列同端點）；
  新寫 TWSE MI_MARGN（融資融券）、TAIFEX pcRatioDown（P/C 比）解析。
- **本容器 proxy 擋 twse/taifex/yahoo**——抓取只在正式區 CI（`daily_fund.sh` 平行加跑
  `scripts/fetch_macro_chips.py`、`daily.yml` commit 步驟加 `data/macro_chips.json`）；
  容器內只讀落檔建儀表板。查不到可靠值的指標（如某日 P/C 比）整列不顯示、不留空值。
- **踩過的坑**：①TAIFEX 逐日端點在「今日盤中未結算」時外資淨部位／選擇權會回 `0`——`_taifex_tx_foreign`／
  `_taifex_pc_ratio` 一律**濾掉 0**（0＝無資料哨兵，否則最新值變「淨多 0 口」、走勢尾端插歸零）。
  ②手機排版：`mdtbl` 第一欄（指標）`position:sticky` 凍結、資料日收進名稱下方小字、日變化與近5日併一欄上下疊，
  只留 4 欄（指標／最新值／日變化·近5日／走勢）才塞得下走勢圖；名稱去掉（上市）（未平倉）後綴（移到表註）。
- 種子值以 WebSearch 多來源交叉查證後寫進落檔（例：外資台指期以 7/17 官方 86,189 口為錨逐日自洽）。
- 新增指標：在 `macrochips.GLOBAL_SPECS`／`TW_KEYS` 與 `fund_dashboard._MD_GLOBAL_ROWS`／`_MD_TW_ROWS` 同步加列。
- **資料來源可點連結**（2026-07-23 使用者需求）：每組表底 `fund_dashboard._md_src_footer()` 依 `_MD_SRC`
  列官方揭露頁連結（全球＝Yahoo Finance 各報價頁；台股＝證交所 BFI82U／MI_MARGN、期交所 futContractsDate／pcRatio），
  同機構同頁去重、只列「有資料」的指標。新增指標時記得在 `_MD_SRC` 補對應官方頁 URL。

## 「ETF 數據追蹤」分頁（左上第四分頁）

追蹤台股被動 ETF（0056/00878/00919/00929/0050/006208）＋**主動式股票 ETF** 15 檔（含本家 00991A、
2026-07 新增熱門／新募集 00988A/00990A/00403A/00407A）＋**「其他」組**（2026-07-20 新增：本家上櫃
00998A 主動復華金融股息／00986D 主動復華金融債息，`kind="other"`、Yahoo 代碼字尾 .TWO；
本家各檔不整列高亮，改在產品名內把「復華」標品牌金色 `.fh`）的
規模／成立日期／過去一週・一月報酬／配息殖利率／收益分配頻率；儀表板 ETF 表只把
「代碼／名稱」識別欄 CSS sticky 凍結（`.etftbl`，`nth-child(2)` left:0；代碼自成一行 `.etcode`、
名稱整段換行 `.etname`＋`min-width:92px` 避免名稱首字被擠上代碼列），手機橫向捲動時
恆可見（性質欄隨捲動移出、不佔凍結空間——兩張表已按性質分組，捲動時不需重複顯示）；
**雙資料來源**（各自獨立降級）：規模／年化配息率／配息頻率 ← etfinfo.tw（Tier B）；
**過去一週／一月報酬 ← 多來源自算**（`_fetch_returns`：stooq → Yahoo → FinMind →
`arm/connectors/twse.fetch_month`，依序取第一個歷史夠密者；以最新交易日收盤對回推 7／30 日曆日
前最後交易日計算，並有「基準日須接近目標日」防呆避免稀疏序列算出錯值）；`ret_src` 記每檔實際
用了哪個源供追查。**報酬為總報酬口徑（2026-07-22 修正）**：Yahoo 抓取帶 `events=div`，區間內
除息加回再算（曾踩：7/16 除息 4.75 的 006208 一週報酬比同指數 0050 多跌整整一個股息），儀表板
報酬格標「＋息X」；債券型（`_BOND_CODES`，收盤天然重複）放寬 `_is_degenerate` 髒序列門檻至 15%，
否則 00986D 全源被誤判髒、報酬整片空。上櫃兩檔 etfinfo 未收錄 → 收盤價由報酬序列末值回填、
規模／首配用 WebSearch 查證種子（`SEED_PERF` 含 `last_div`），年化配息率以配息×次數÷序列收盤自算。
**當月預估配息**（etfinfo 只揭露已實際除息者、抓不到投信預告）：依序 MOPS
（`arm/connectors/mops.etf_distributions`，端點多變、常抓不到）→ **`arm/etfwatch.ANNOUNCED_EST`
人工維護清單**（投信官方已公告之首配／當期預估，除息日未到）。取本月未到期者 → 配息欄「預估 X*」，
過月自動失效。**投信新公告配息時，把 `{code: {amount, ex_date}}` 補進 `ANNOUNCED_EST`**
（來源：各投信官網／經濟日報等；除息後 etfinfo 會接手實際值）。例：00991A 首配 0.77（除息 7/21）、0056 Q3 擬配 1.35。
欄位另含**最新收盤價**（etfinfo 市價）與**最近一次配息**（最近一次「實際」除息金額）；
若投信於配息月已公告該月**預計配息金額**（etfinfo 配息表中除息日在本月且未到期／標記預估者），
於配息欄加註「預估 X*」橘標，*＝投信公告非正式配息金額，實際以除息公告為準。
**配息殖利率一律用年化配息率**＝最近一次「實際」配息金額 ÷ 最新市價 × 配息頻率次數
（月配×12／季配×4／半年配×2／年配×1），不是 trailingYield 近12月回溯值；
追蹤清單改 `arm/etfwatch.py` 的 `WATCHLIST` 即可（含**成立日期靜態值**——不需抓、永不空白）。
資料層 `data/etf_watch.json`：`scripts/fetch_etf_watch.py` 逐檔「欄位級合併」，fallback 鏈為
**本次 etfinfo 新值 → 既有落檔值 → 內建 `SEED_PERF` 週報底稿**（成立日一律取 WATCHLIST 靜態值）。
報酬數據標 `perf_asof` 基準日、規模／殖利率標 `as_of` 抓取日，儀表板分別備註（沿用最近可得值時使用者已同意）。
來源 etfinfo.tw 屬 Tier B，正式對外前以各投信官網核對。

**欄序與當日漲跌（2026-07-29 使用者需求）**：欄序＝最新收盤價／**當日漲跌**／過去一週／過去一月／
最近一次配息／換算年化配息率／收益分配頻率／**規模／成立日期（靜態資料移到最右）**。
當日漲跌由 `_returns_from_series` 以同一份收盤序列的末兩點自算（`chg_pct/chg_amt/prev_close/prev_date`），
**除息日以「除息參考價＝前收 − 每單位配息」為基準**並標【除息】——否則整段配息會被算成跌幅
（同 2026-07-22 區間報酬修過的總報酬坑）。抓不到就沿用既有值，絕不洗成空白。

## ETF「持股變化與當日貢獻」展開明細（2026-07-29 使用者需求）

ETF 表每列下方一個原生 `<details>` 展開鈕，內含：持股／權重／**加減碼(股)**／Δ權重／
個股當日漲跌／**貢獻(pp)**＝權重% × 個股當日漲跌% ÷ 100。依 |貢獻| 排序、只列前 12 檔，
其餘併「其餘 N 檔合計」；前一揭露日有、今日沒有的標「已出清」，前一日沒有的標「新進」。
**合計不硬湊等於 ETF 市價漲跌**——現金／期貨部位、費用、揭露時點差都在殘差，表註誠實寫明。

- 資料層 `data/etf_holdings.json`（**必須入庫**，`.gitignore` 已加 `!` 例外）：`prev` 存前一揭露日
  股數／權重，**沒有它就沒有「今日 vs 昨日」可比、Δ 整片是 —**（同 etf_watch／fund_nav_history 的坑）。
  合併鐵則 `etfholdings.merge_one()`：本次抓不到＝原封保留；**同一揭露日重抓不可把 prev 洗成今天自己**
  （否則 Δ 全變 0、看起來像「都沒異動」）；揭露日推進時才把舊 holdings 降級為 prev。
- **貢獻在 CI 端算好存進落檔的 `detail`**（`etfholdings.annotate`，個股報價 ← `twse/tpex.fetch_today_all`）——
  容器內 proxy 擋 twse/tpex，建表時取不到報價；儀表板端 `etfholdings.view()` 只讀 `detail` 純渲染。
- **抓取：沒有跨投信統一官方端點**（2026-07-29 查證：證交所／櫃買／政府開放平台皆無彙總 API，
  各投信自行在官網揭露）→ `arm/connectors/issuers/pcf.py` 做成「**候選 URL＋通用解析＋探針**」：
  每檔依序試候選來源，通用解析吃 JSON／HTML 表格／xlsx（重用 `fhtrust._parse_xlsx`），
  抓不到就印 HTTP 狀態／content-type／內容前段。**收斂方式：跑 `scripts/fetch_etf_holdings.py --probe`
  於 CI，讀日誌逐家證實後改 `_cands()`**（同 cnyesfund.py 當初 6 輪 CI 收斂的做法）。
  已知可用型態：元大 `www.yuantaetfs.com/tradeInfo/pcf/{code}`。抓不到的檔安靜降級（該 ETF 就沒有
  展開明細），不影響其餘欄位與其他 ETF。
- **排序配對**：ETF 表點欄排序的 JS 必須把 `.hdrow`（展開列）當「附屬於前一列」一起搬——
  獨立排序會與所屬 ETF 脫鉤，且 `.hdrow` 只有一個 colspan 欄，`cells[i]` 為 undefined 會讓整個排序爆掉。

**踩過的坑（勿再犯）**：
- `data/etf_watch.json` 曾被 `.gitignore` 的 `data/*` 擋掉沒入庫 → CI 從零抓、etfinfo 缺欄 → 成立日期／
  週月報酬整片變 null。已在 `.gitignore` 加 `!data/etf_watch.json` 例外，此檔**必須入庫**當 fallback。
- 欄位級 fallback 用「值是否為 None」判斷，**不可用 `dict.get(key, default)`**——CI 曾把欄位寫成顯式 `null`，
  `get(key, default)` 會回傳那個 null 而非 default，反而把資料洗空。用 `arm/etfwatch._pick()`。

## 基金多期報酬「每日基準」覆蓋層（2026-07-15 新增，鉅亨 Tier B）

**官網 `/api/fund` 的多期報酬（roiY2D/roi3m/roi1y…）是「月底基準」**——git 史實測 NAV 天天動、
YTD/1y 十四天不變（皆上月底值），使用者已明確要求每日基準。解法：`arm/connectors/cnyesfund.py`
（2026-07-15 歷經 6 輪 CI 收斂的**最終架構**，勿走回頭路）：
- **取數路徑＝「釘選 cnyesId → 直取詳情頁」**：`data/cnyes_fund_map.json`（**入庫**）存全部
  25 檔的 cnyesId（WebSearch 逐檔查回並核對 share class）；詳情頁 `fund.cnyes.com/detail/x/{cnyesId}/`
  的 HTML 以 `_objects_from_html()` 平衡物件掃描抽資料（頁面無 __NEXT_DATA__、狀態以他形內嵌）。
  **新增基金時：WebSearch 查其鉅亨詳情頁 URL、把 cnyesId 補進 map 檔即可。**
- **死路備忘（CI 實測，勿再試）**：`fund.api.cnyes.com` 全路徑 404；`gfe-fund.cnyes.com` 任何
  路徑都回同一張 XHTML 舊頁；搜尋頁 `fund.cnyes.com/search/` SSR 不吃 query（任何 keyword 都
  回同 20 筆熱門清單，名稱比對必零命中）。
- 詳情頁實際鍵：`return1Month/3Month/6Month/1Year/returnYTD`＋`nav/priceDate/change(Percent)`；
  **無 1週／2年／3年獨立鍵**（1週回退自建 NAV 序列自算、3年回退官網月底值——混合基準已在
  總覽副標註明）；複合鍵 `returns` 內部結構每日於 CI 日誌印出（debug 首檔），未來可再收斂。
- `fetch_holdings.py` 抓完官網後 `cnyesfund.apply_overlay()`：寫 `returns_daily`＋`returns_daily_asof`
  進 `data/funds/*.json`；鉅亨 NAV 日**較新**時一併覆蓋 nav（標 `nav_src="cnyes"`）。
- 儀表板 `overview_rows()` 逐欄 fallback：**鉅亨每日值 → 官網月底值**；1週/1月再多一層 → 自建
  NAV 序列自算。總覽區有「多期報酬」鮮度 chip。
- **此容器 proxy 擋 cnyes（CONNECT 403）**——**用 CI 日誌（`mcp__github__get_job_logs`）驗證與
  迭代**，勿在本容器嘗試打 cnyes。整層失敗只是回退官網值，不會壞版面。

## 基金總覽「1週／1月」報酬（2026-07-15 新增）

官網 `/api/fund` 多期報酬**沒有 1週/1月**，由 `arm/fundnav.py` 以自建 NAV 序列自算：
資料層 `data/fund_nav_history.json`（**必須入庫**，`.gitignore` 已加例外——跨日累積的持久層，
CI 從零開始會整片變 —，同 etf_watch 的坑）；`fetch_holdings.py` 抓完自動 `fundnav.record()` 累積，
斷史時 `scripts/backfill_fund_nav.py` 走 git 歷史（`data/funds/_index.json` 每日快照）重建。
計算有「基準日須接近目標日」防呆（1週 tol=5 天、1月 tol=10 天），史料不足回 None → 儀表板顯示 —
（序列自 2026/07/01 起，「1月」欄約 2026/08 初起自然補齊，非資料壞掉）。
舊 `arm/navhist.py` 是 ETF 管線的 sqlite 模組，與此無關、勿混用。
