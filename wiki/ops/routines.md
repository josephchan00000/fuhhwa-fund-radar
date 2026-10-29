# 排程與「排程搬家」

> 六個排程都火進同一個綁定的對話（它每天先合併 main，merge 進 main 後下一班就生效）；搬家步驟、模型重設、prompt 原文。
> 原始資料：CLAUDE.md「指令：「排程搬家」」「每日固定時間自動更新」；`docs/llm_wiki_plan.md` 第 3.1、6 節。
> 最後更新：2026-10-29
> CLAUDE.md 仍留著對應的指令段落（排程照它執行）：那一段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）；其他內容以這一頁為準。

## 現在怎麼運作

claude.ai Routines，六個都**火進同一個主會話**（綁定會話）；name、cron 見搬家步驟 2。trigger id 與綁定會話隨搬家改變，一律以 `list_triggers` 實查為準、本檔不記死 id（2026-07-24 起；使用者約每 3–5 天在新視窗搬一次）。
① [全部更新](daily-update.md) 目標＝**07:03 前線上可看當日內容**（2026-07-20 使用者指示；實測全程 15–28 分，06:35 起跑最壞壓線、一般 06:55 完成）；
②③④ 負責準時（[時點地圖](schedule.md)；-32003 見 [MCP 審批](../env/mcp-approval.md)）；⑤ [ETF 募集週掃](etf-weekly-scan.md)；⑥ [策略探勘週報](strategy-scouting.md)。
排程點火的回合若 MCP 不可用，SOP 第 7 步照樣走「push 自動觸發」；驗證用 git（fetch origin main 看是否前進＋檢查檔案內容）即可。

**為什麼火進主會話**：2026-07-18 實測「開新會話」兩次全滅——點火綁的環境（env_01FK…「化學」）沒掛本 repo，連 heartbeat push 都做不到
（帶「3 分鐘心跳測試」指令仍 18 分鐘零輸出）；主會話有 repo、GitHub MCP、完整脈絡，「火進既有會話」有 07-13 send_later 成功先例。完成／失敗以 PushNotification 推播。

### 「生效條件＝排程搬家」怎麼讀（2026-10-29 查證）

- 各頁寫的「merge 進 main 後做一次排程搬家才生效」＝排程會話 checkout 的分支上要有那份改動：提示包 gen_*.py、push 觸發的 workflow 檔
  （`daily.yml` 用**被推分支**的檔；踩過 9⑤、9⑦、`x9s.json`、[`not_tracked`](../main/etf-upcoming.md)）、`.claude/settings.json`、`check_reports.py`（只在排程會話裡跑，CI 沒跑）。
- 2026-10-17 起排程會話每天 06:36 先把 origin/main 合併進自己的分支（`git log --first-parent` 每天一筆「merge main」，10/22～10/28 天天都有），
  所以**現在 merge 進 main 之後下一班就生效，不必為了生效搬家**；分支停止合併 main 時才要搬（並重設 `/model`）。
- 查法：`list_triggers` 看綁定會話 → `get_session` 看分支 → `git log --first-parent origin/{分支}` 找最近幾天的「merge main」。
  2026-10-29 查：六個排程都綁在 2026-10-16 開的視窗（分支 `claude/exciting-cerf-isj9q7`）。
- 與分支無關：CI 建表（`daily.yml` checkout main）、dispatch 的 workflow、策略候選合併通道。
- 補救：workflow 檔太舊＝dispatch daily.yml（ref=main；news_ref 留空＝只用 main 新聞重刷、填本會話分支＝併進它的新聞與通道檔）；
  settings.json＝在綁定會話呼叫一次 send_later 按「一律允許」。2026-10-16 [改寫 git 歷史](../env/git-history.md)後舊歷史的視窗要搬家。

### 指令：「排程搬家」

在**任何**對話窗打**「排程搬家」**（或「搬排程」）＝把**全部六個** Routine 改綁到**當前**對話窗。
**不要詢問、不要查證其他東西、不改任何檔案、不 commit**——固定「list → 建六個 → 刪舊的」收工（最省 token）：

1. `list_triggers`（先用預設 limit；找不到再用 cursor 翻頁）→ 找**名稱以「復華基金雷達」開頭且 `enabled:true`** 的 Routine
   （正常 6 個；歷史上只有 1／3／4／5 個＝尚未擴編，照樣往下走）。全部的 `persistent_session_id` 都已是本會話 → 回一句「排程已綁本視窗」結束。
   回應常被截斷存成檔案（坑 1）：**別開子代理讀全文**，`python3 -c` 讀那支檔 `json.loads` 後只印 `id｜name｜cron_expression｜enabled｜persistent_session_id`
   一行一個；prompt 原文在 `job_config.ccr.events[*].data.message.content`（**頂層沒有 `prompt` 欄位**）。
2. `create_trigger` ×6（預設自綁本會話，**不帶** `persistent_session_id`／`create_new_session_on_fire`），name｜cron（UTC）：
   - ① `復華基金雷達 每日全部更新(台北 06:35・07:03 前完成)`｜`35 22 * * *`
   - ② `復華基金雷達 盤後籌碼即時更新(台北 15:33)`｜`33 7 * * 1-5`
   - ③ `復華基金雷達 晚間NAV·PCF即時更新(台北 18:58)`｜`58 10 * * 1-5`
   - ④ `復華基金雷達 美股收盤序列更新(台北 05:08)`｜`8 21 * * 1-5`
   - ⑤ `復華基金雷達 ETF募集週掃(台北週一 08:05)`｜`5 0 * * 1`
   - ⑥ `復華基金雷達 策略探勘週報(台北週日 19:47)`｜`47 11 * * 0`
3. `delete_trigger` 逐一刪舊的。搬家＝建新＋刪舊：`update_trigger` 改不了綁定會話、跨會話 update 也被組織政策擋，但**跨會話 delete 可行**（2026-07-24 實證）。
4. 一句話回報：六個新 trigger id＋各自下次觸發時間。`create_trigger` 警告「no MCP connectors」**可忽略**（SOP 第 7 步走 push 自動觸發、驗證用 git）。
   查到「本檔沒記載」的復華 Routine：照樣搬，prompt 從舊 trigger 的 `job_config` 原文照抄，回報提一句「本檔要補記」。
5. **回報時務必提醒使用者「模型要重設」**：trigger 的 `job_config` **沒有 model 欄位**，只有 `persistent_session_id`——火進哪個視窗就用**那個視窗當下的模型**
   （「跟著該會話走」）。舊視窗的 `/model` **不會**搬過來，使用者要在**新視窗**自己打一次 `/model sonnet`：容器內 Claude 無法代勞（`update_trigger` 改模型全組織停用、
   回 `model_update_disabled`，改綁在其他會話的 trigger 也被擋），**唯一可行槓桿＝在「排程當前綁定的主會話」內執行 `/model sonnet`**；
   新開會話預設落在無 repo 的「化學」env，等組織開放 routine 模型設定或本 repo 掛上可排程 env，才談得上「fresh sonnet 會話」。

## 不能改的規則

- prompt **一字不改**（引號、全形標點、空格、`**` 照原樣；建 trigger 時的文字才會送出，改了要再搬一次）。
- prompt 引用 CLAUDE.md 的「指令：全部更新」「指令：ETF 募集週掃」「指令：策略探勘週報」、步驟 9⑤、週掃步驟 2.5、「已知環境限制與防呆」的 -32003 條，瘦身時這些標題與編號要留。

## 踩過的坑

- `list_triggers` 超過工具上限（2026-08-07 實測 70KB／一行，帳號累積數十個 `send_later` 一次性 trigger）→ 步驟 1 的讀法。
- 以為設過 sonnet（2026-07-27 使用者踩到），實際每日跑都是新視窗的預設模型 → 步驟 5。
- 05:08 那支是搬家時在 `list_triggers` 裡才發現的（2026-08-07）→ 步驟 4「本檔要補記」。

## 歷史

- 個數：07-18 一個、2026-08-03 三個、08-07 四個、2026-08-10 五個（同日踩 -32003）、10-24 六個。
- 2026-07-23 想改 sonnet 省 token，查明做不到；08-12 15:33 班加補簡介缺口。

## Routine prompt 原文

### Routine prompt 原文①——每日全部更新（06:35）

> （排程自動觸發）全部更新。依 repo CLAUDE.md「指令：全部更新」SOP 完整執行：產提示包 → 平行子代理 WebSearch 產當日新聞（美股 v1/v2、台股、總經、行事曆；嚴守提示包版型——含分析深度六條與每卡 **漲跌分析** 欄（粗體標籤）／禁用詞／每卡連結）→ gen_*.py --check 與 check_reports.py 全 🟢 → 重建儀表板 → pytest 全綠 → commit+push 到本會話指定分支（push 動到 reports/** 會自動觸發 daily.yml）→ 等 main 前進後驗證（新聞今日、產表時戳為 CI、nav_date 推進）。完成或失敗都用 PushNotification 推播一句話結果給使用者（成功：當日 3 條市場重點摘要＋籌碼雷達兩行——git show origin/main:data/lab/val_log.json 取 days 最後一天的 push 欄原文照貼（今天開盤／收盤要做的買賣；有驗證事件才有第二行），讀不到就省略、不擋推播；失敗：卡在哪一步＋影響）。不可宣稱「線上已生效」（本環境看不到 Vercel）。若工作樹有未完成的其他工作，先 stash 或用獨立分支，勿混入每日更新 commit。

### Routine prompt 原文②——盤後籌碼即時更新（15:33）

> （排程自動觸發）盤後籌碼即時更新——GitHub cron 實測遲 1~3 小時，本 Routine 負責準時；全程只做三件事、不跑任何資料抓取腳本、不動 reports/**：① 用 mcp__github__actions_run_trigger（method=run_workflow、workflow_id=afterhours_refresh.yml、ref=main）觸發盤後刷新，成功觸發即收工、不等它跑完；MCP 不可用時備援＝在本會話指定分支寫 .ping/afterhours（內容任意）後 git add -f、commit、push——該路徑 push 會自動觸發同一 workflow。② 前十大簡介缺口順手補（使用者 2026-08-12：不佔早上、掛在本班——本班最輕且在晨間持股抓取之後）：git fetch origin main 讀 data/holdings_intro_gap.json，count=0 → 跳過；count>0 → 依 CLAUDE.md 步驟 9⑤ 極簡迴路：每檔 1 次 WebSearch 查證（公司本業／代號／國別）→ 補 config/holding_profiles.json（{原字串:{intro,ticker,country,verified}}，intro 純事實、避開禁用詞）→ python3 -m pytest -q tests/test_holdings_intro.py → commit「chore: 補持股簡介 N 檔」push 本會話指定分支——push 自動觸發 daily.yml 併檔＋重建上線，不需 PR、不需監看。③ send_later 排 60 分鐘後自驗：git fetch origin main 讀 data/macro_chips.json，若為交易日（以證交所官方休市表為準：python3 -c "from arm import twholidays,clock; print(twholidays.is_closed(clock.today_tw()))" 印 False 才是交易日）而 inst_total 仍缺今日 → 補 dispatch 一次、再 send_later 25 分鐘後檢查，仍缺才 PushNotification 一句話（缺什麼＋afterhours run 日誌看到的原因）；資料已到或休市 → 安靜結束、不推播、不留言（使用者 2026-08-03 指定「失敗才推播」）；若②有補簡介，同回合加驗 origin/main 的 data/holdings_intro_gap.json 已歸 0，仍 >0（分支 workflow 檔太舊、併檔通道沒生效）→ mcp__github__actions_run_trigger dispatch daily.yml（ref=main、news_ref=本會話指定分支）一次即可修復。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

### Routine prompt 原文③——晚間 NAV·PCF 即時更新（18:58）

> （排程自動觸發）晚間數據即時更新（基金 NAV＋主動式 ETF 當日 PCF）——不跑任何資料抓取腳本、不動 reports/**：① mcp__github__actions_run_trigger 連發兩個 dispatch（皆 ref=main）：afterhours_refresh.yml（18 時後場次會加抓基金 NAV）與 etf_holdings.yml；MCP 不可用時備援＝push .ping/afterhours 哨兵（只能觸發前者，後者靠其 17:40 cron 遲到自癒即可）。② send_later 排 45 分鐘後自驗：git fetch origin main，a) data/funds/_index.json 最新 nav_date ≥ 上一交易日、b) data/etf_holdings.json 本家主動式（00991A）揭露日已推進（休市日無新 PCF 屬正常、勿誤報）；異常 → 補 dispatch 一次、25 分鐘後仍異常才 PushNotification 一句話。③ 自驗回合結束前再 send_later 一個台北 23:20 的夜檢：讀 origin/main 的 data/macro_chips.json 與 data/afterhours_alert.json，交易日而 margin_bal 缺今日或 alert missing 非空 → PushNotification 一句話（22:05 cron 整班消失時這是唯一的主動警報）；正常 → 安靜結束。皆「失敗才推播、成功安靜」。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

### Routine prompt 原文④——美股收盤序列更新（05:08，2026-08-05 建立、2026-08-07 補記本檔）

> （排程自動觸發）美股收盤序列更新（費半 ^SOX／台積電 ADR 昨夜收盤入檔，供 06:35 晨報引用；台北 05:08＝美東收盤後，夏令 17:08／冬令 16:08）——全程不跑任何資料抓取腳本、不動 reports/**：① 用 mcp__github__actions_run_trigger（method=run_workflow、workflow_id=afterhours_refresh.yml、ref=main）觸發刷新，成功觸發即收工、不等它跑完；MCP 不可用時備援＝在本會話指定分支寫 .ping/afterhours（內容任意）後 git add -f、commit、push——該路徑 push 會自動觸發同一 workflow。② send_later 排 35 分鐘後自驗：git fetch origin main 讀 data/macro_chips.json，series.sox 與 series.tsm_adr 須含最近一個美股交易日（以前一美東平日為準；美股休市日無新 bar 屬正常、勿誤報——休市日以 arm/usnews._US_MKT_HOLIDAYS（NYSE 公告表）為準）；缺 → 補 dispatch 一次、再 send_later 20 分鐘後檢查，仍缺才 PushNotification 一句話（缺什麼＋afterhours run 日誌看到的原因）；已到或休市 → 安靜結束、不推播（失敗才推播）。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

### Routine prompt 原文⑤——ETF 募集週掃（週一 08:05，2026-08-10 建立）

> （排程自動觸發）ETF 募集週掃——找到新 ETF 募集資訊、主動更新「即將登場」（使用者 2026-08-10 指示：主動更新、一週一次）。依 repo CLAUDE.md「指令：ETF 募集週掃」SOP 執行：全程不跑資料抓取腳本、不動 reports/**、只改 data/etf_upcoming.json。① git fetch origin main 讀 origin/main 的 data/etf_upcoming_gap.json（CI 自動發現的漏網檔）與 data/etf_upcoming.json 現況，pytest tests/test_etfwatch.py 看 stale guard 有無紅；② WebSearch 盤點（鉅亨 IPO 頁 fund.cnyes.com/IPO/index.htm＋MoneyDJ 新基金頁＋工商時報／經濟日報「投信新基金」稿，容器擋原頁就用搜尋摘要），逐檔兩來源核對：新核准檔補登（時程未定 raise_hint＋asof、未派碼 code:null）、hint 檔補正式日期、募集期間／掛牌日／配息頻率異動修正、掛牌逾期條目清理；海外被動指數檔 track:false；本家復華新檔最優先、絕不可漏；③ 更新頂層 as_of＝今日 → pytest 全綠 → commit「chore: ETF 募集週掃 {日期}」push 本會話指定分支（push 動到該檔自動觸發 daily.yml 併入 main 重建上線，不需人工 merge）；③-b 依 CLAUDE.md 週掃步驟 2.5 維護 config/index_reviews.json（被動指數審核時程與官方結果：只改查得到官方公告的日期與名單、不猜，as_of＝今日，pytest tests/test_lab.py 須綠，與 etf_upcoming 同一個 commit push）；④ 有異動 → PushNotification 一句話列出異動檔；無異動 → 安靜結束不推播；失敗 → 推播卡在哪一步。

### Routine prompt 原文⑥——策略探勘週報（週日 19:47，2026-10-24 建立）

> （排程自動觸發）策略探勘週報——依 repo CLAUDE.md「指令：策略探勘週報」SOP 執行；全程不跑資料抓取腳本、不動 reports/**。① git fetch origin main 後把 origin/main 合併進本會話指定分支（候選的程式與檢查要是最新的）；讀 config/strategy_candidates.json 與 config/strategy_board.json 的 cand：還沒決定的已有 10 條 → 不找，PushNotification 一句「策略候選已有 N 條還沒決定，請回試用／納入／不納入」後結束。② WebSearch 找新策略：來源限學術（SSRN、arXiv q-fin、期刊）、AQR／Alpha Architect／Quantpedia／Research Affiliates 等量化研究、台灣投信券商研究報告；挑最多 2 條「規則寫得清楚、有公開成績、現有資料做得出來」、和已有的候選與頁面上的策略不重複的；找不到就安靜結束、不推播。③ 每條寫規格一筆（config/strategy_candidates.json 的 items；欄位照 arm/lab/candspec.py：id 接續編號、found＝今天、name、mk、engine、kind、how 一句白話規則、src 至少一條 https 原文連結、why、p、grid、各型態要的 H／b／pick／ex、sha）＋程式一支 arm/lab/cands/{編號}.py（照 arm/lab/cands/__init__.py 的範本；參數從 p 讀、只用那一天收盤以前的資料、台股財報與月營收一律經過 cands.Fin）；sha 用 python3 -c "from arm.lab import candrun as R; print(R.sha_file(R.PROG/'c00X.py'))" 填；資料不夠的只寫規格、need＝「需要資料：…」、不寫程式。④ TZ=Asia/Taipei python3 scripts/run_cands.py --check 與 python3 -m pytest -q tests/test_cands.py tests/test_candspec.py 全綠 → git add config/strategy_candidates.json arm/lab/cands → commit「chore: 策略候選 {編號} {名稱}」→ push 本會話指定分支（push 自動觸發 strategy_cands.yml：用 main 的檢查、回測、乾淨算完才併進 main、重建頁面）。⑤ 等結果：Bash run_in_background 的 until 迴圈（每 2 分鐘 git fetch origin main，最多 45 分鐘）等 origin/main 的 data/lab/cands_research.json 出現這幾個編號：出現＝安靜結束（星期一 06:35 推播會帶「策略候選」一行）；45 分鐘沒出現＝讀 strategy_cands.yml 那一輪的日誌（mcp__github__actions_list／get_job_logs）：程式出錯或用到未來的資料就修程式（還沒進 main 的候選可以改；修的是程式錯誤，不是看了成績調參數）、重填 sha、再推一次；第二次還是不行 → PushNotification 一句卡在哪裡。
