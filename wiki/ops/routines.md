# 排程與「排程搬家」

> 六個排程都火進同一個綁定的對話；那個對話用自己分支上的檔案，所以改了提示包、workflow 檔、settings.json 要「merge 進 main 後排程搬家」才生效；搬家步驟與模型重設。
> 原始資料：CLAUDE.md「指令：「排程搬家」」「每日固定時間自動更新」兩段，以及各段寫的「生效條件」；prompt 原文在 [排程 prompt 原文](routines-prompts.md)；規劃 `docs/llm_wiki_plan.md` 第 6 節。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

### 六個排程

都是 claude.ai Routines，**火進同一個主會話**（綁定會話）。trigger id 與綁定會話會隨「排程搬家」改變——一律以 `list_triggers` 實查為準，
本檔不記死 id（2026-07-24 起；使用者約每 3–5 天在新視窗搬一次）。

| 排程名稱（`create_trigger` 的 name） | cron（UTC） | 做什麼 | prompt |
|---|---|---|---|
| `復華基金雷達 每日全部更新(台北 06:35・07:03 前完成)` | `35 22 * * *` | [全部更新](daily-update.md) | ① |
| `復華基金雷達 盤後籌碼即時更新(台北 15:33)` | `33 7 * * 1-5` | 觸發盤後刷新、補持股簡介缺口、自驗 | ② |
| `復華基金雷達 晚間NAV·PCF即時更新(台北 18:58)` | `58 10 * * 1-5` | 觸發基金 NAV 與主動式 ETF 當日 PCF 刷新、自驗、23:20 夜檢 | ③ |
| `復華基金雷達 美股收盤序列更新(台北 05:08)` | `8 21 * * 1-5` | 費半與台積電 ADR 昨夜收盤入檔，供晨報引用 | ④ |
| `復華基金雷達 ETF募集週掃(台北週一 08:05)` | `5 0 * * 1` | [ETF 募集週掃](etf-weekly-scan.md) | ⑤ |
| `復華基金雷達 策略探勘週報(台北週日 19:47)` | `47 11 * * 0` | [策略探勘週報](strategy-scouting.md) | ⑥ |

- 06:35（UTC 22:35）那班跑「全部更新」SOP，目標＝**07:03 前線上可看當日內容**（2026-07-20 使用者指示；實測全程 15–28 分，06:35 起跑最壞壓線、一般 06:55 完成）。
- 15:33、18:58、05:08 三班負責「準時」：GitHub cron 會遲到，改由 Routine 秒級打 workflow_dispatch，自驗「失敗才推播、成功安靜」。時點地圖與 cron 兜底見 [每日時點地圖與 cron](schedule.md)。
- 自驗靠 `send_later`；被 MCP 審批擋下（-32003）時改用背景迴圈，見 [排程會話 MCP 審批](../env/mcp-approval.md)。
- 排程點火的回合若 MCP 不可用，SOP 第 7 步照樣走「push 自動觸發」；驗證用 git（fetch origin main 看是否前進＋檢查檔案內容）即可。

### 為什麼火進主會話、不開新會話

2026-07-18 實測「開新會話」模式兩次全滅：fresh-session 點火綁的環境（env_01FK…「化學」）沒掛本 repo source，會話起來連最小 heartbeat push 都做不到
（第二次點火帶「3 分鐘心跳測試」指令仍 18 分鐘零輸出）。改「火進主會話」後有 repo、有 GitHub MCP、有完整脈絡；
「火進既有會話」模式在本帳號有 07-13 send_later 成功先例。完成／失敗以 PushNotification 推播使用者。

### 生效條件＝merge 進 main 後做一次「排程搬家」

**是什麼**：排程火進的綁定會話，用的是**它自己 checkout 的分支**上的檔案，不是 main。下面四類東西改了，merge 進 main 還不夠，
要綁定會話的分支上也有新檔，排程才會用到。根治做法＝「排程搬家」：在新視窗開新會話（新分支自最新 main 分岔），把排程改綁過去。
只 merge、分支又沒拿到新檔＝排程照舊用舊版。各頁寫「生效條件＝merge 進 main 後排程搬家」都是指這一節。

| 類別 | 為什麼排程會用到舊版 | 例子（細節在哪一頁） |
|---|---|---|
| 新聞提示包規則 | 排程會話用自己 checkout 分支上的 gen_*.py 產提示包 | `usnews.weekend_note()` 的週末最重大事件保底、`usnews.depth_note`／`move_note`／`LABEL_RULE`、`pick_note`、`SEV_RUBRIC`、`market_anchor`、`BRIEF_STYLE`（[新聞報告規則](news-rules.md)）；版型的段名（[列印版](../main/print.md)）；行事曆台灣區、昨日版底稿（[行事曆](../main/calendar.md)） |
| push 觸發的 workflow 檔 | push 觸發的 `daily.yml` 用**被推分支**上的 workflow 檔 | `YOUTUBE_API_KEY` 金鑰（[全部更新](daily-update.md) 9⑦）、`config/holding_profiles.json` 併檔通道（9⑤）、`git add` 清單裡的 `dashboard/x9s.json`（[籌碼雷達介面改版歷史](../lab/chip-ui.md)）、併檔段沿用 `not_tracked`（[即將登場](../main/etf-upcoming.md)） |
| `.claude/settings.json` | 排程會話讀自己分支上的這支檔 | MCP 工具預先核准（[-32003](../env/mcp-approval.md)） |
| 容器端閘門 `check_reports.py` | 它在排程會話裡、照自己分支上的版本跑 | 原文寫法不一致：[行事曆](../main/calendar.md) 台灣區寫提示包與閘門都要 merge 後排程搬家；同頁 Phase 2 寫閘門 merge 即生效（容器端 check_reports）；[列印版](../main/print.md) 寫解析器＋閘門 merge 進 main 即可（CI 用 main 的程式建表） |

**merge 進 main 就生效、不用搬家的**：CI 建表、渲染、解析（`daily.yml` 一律 checkout main，再把分支的今日新聞併進來）；
dispatch 觸發的 workflow（用 main 的 workflow 檔）；策略候選的合併通道（檢查程式一律用 main 的，見 [策略探勘週報](strategy-scouting.md)）。

**分支太舊時的補救（不必等搬家）**：

- workflow 檔太舊：`mcp__github__actions_run_trigger` dispatch daily.yml（ref=main；news_ref 留空＝只用 main 現有新聞重刷資料，填本會話分支＝把那個分支的新聞與通道檔併進來）。9⑤、9⑦ 就是這樣補。
- `x9s.json` 這類 `git add` 清單：下一班 cron／dispatch 自然補上。
- settings.json：使用者在綁定會話請 Claude 呼叫一次 send_later 並按「一律允許」（[-32003](../env/mcp-approval.md) 第③道）。

**現在的情況（2026-10-23 查）**：五個復華排程都綁在 10/16 開的視窗（分支 `claude/exciting-cerf-isj9q7`），它從 10/17 起**每天 06:36 先把 origin/main 合併進分支**才寫新聞
（`git log --first-parent` 每天一筆 merge main）——所以 merge 進 main，下一班就拿得到，IA v5 第 4 段那次不必搬家（[導覽與入口](../lab/nav.md)）。
`docs/llm_wiki_plan.md` 第 6 節同理：合併之後下一次叫醒就用新的 CLAUDE.md。策略探勘週報的 prompt ⑥ 第一步本來就會先合併 origin/main。
**哪天它的分支停止合併 main**（first-parent 歷史上沒有 merge main），新加進 workflow 的檔就不會被那一班 commit，那時再做「排程搬家」（並重設 `/model`）。
要知道現在是哪一種，就看綁定會話分支的 `git log --first-parent`。

**也要搬家的情況**：2026-10-16 改寫 git 歷史之後，本地還是舊歷史的視窗（排程會話、舊對話）不可再推送舊分支或把 origin/main 合併進去（unrelated histories），
改寫後要「排程搬家」到新視窗（[改寫 git 歷史](../env/git-history.md)）。

### 指令：「排程搬家」

使用者在**任何**對話窗打**「排程搬家」**（或「搬排程」）＝把**全部六個** Routine（每日：06:35 全部更新、15:33 盤後籌碼、18:58 晚間 NAV·PCF、05:08 美股收盤序列；
每週：週一 08:05 ETF 募集週掃、週日 19:47 策略探勘週報）改綁到**當前**對話窗。**不要詢問、不要查證其他東西、不改任何檔案、不 commit**——
固定「list → 建六個 → 刪舊的」收工（最省 token）：

1. `list_triggers`（先用預設 limit；找不到再用 cursor 翻頁）→ 找**名稱以「復華基金雷達」開頭且 `enabled:true`** 的 Routine
   （正常應有 6 個；歷史上只有 1／3／4／5 個＝尚未擴編，照樣往下走）。全部的 `persistent_session_id` 都已是本會話 → 回一句「排程已綁本視窗」結束。
   回應常超過工具上限、被存成檔案：**別開子代理讀全文**，直接 `python3 -c` 讀那支檔 `json.loads` 後只印 `id｜name｜cron_expression｜enabled｜persistent_session_id`
   一行一個，秒級收斂。要看某支的 prompt 原文就印 `job_config.ccr.events[*].data.message.content`（**頂層沒有 `prompt` 欄位**，只有這裡有）。
2. `create_trigger` ×6（預設自綁本會話，**不帶** `persistent_session_id`／`create_new_session_on_fire`）：name 與 cron 照上面的表，
   prompt 照 [排程 prompt 原文](routines-prompts.md) 一字不改照抄。
3. `delete_trigger` 逐一刪掉步驟 1 找到的舊 Routine。
4. 一句話回報：六個新 trigger id＋各自下次觸發時間。`create_trigger` 若警告「no MCP connectors」**可忽略**（SOP 第 7 步走 push 自動觸發、驗證用 git，不依賴 MCP）。
   步驟 1 若查到「本檔沒記載」的復華 Routine：照樣搬，prompt 從舊 trigger 的 `job_config` 原文照抄，並在回報時提一句「本檔要補記」。
5. **回報時務必提醒使用者「模型要重設」**（下一節）。

### 搬家後模型要重設

trigger 的 `job_config` **沒有 model 欄位**，只有 `persistent_session_id`——每日火進哪個視窗，就用**那個視窗當下的模型**（模型「跟著該會話走」，不是跟著 trigger）。
舊視窗設過的 `/model` **不會**跟著搬家過來，新視窗一律回到預設。所以每次搬家後，使用者要在**新視窗**自己打一次 `/model sonnet`。

容器內 Claude 無法代勞：`update_trigger` 改模型全組織停用（回 `model_update_disabled`），model 參數對綁定會話的 routine 也無效；改綁在其他會話的 trigger 也被擋。
**唯一可行槓桿＝在「排程當前綁定的主會話」內執行 `/model sonnet`**（會固定生效、之後每日火進該會話即用 sonnet），只能由使用者在該會話操作。
新開會話仍預設落在無 repo 的「化學」env，所以要等組織開放 routine 模型設定、或把本 repo 掛上某個可排程 env，才談得上「fresh sonnet 會話」路徑。

## 不能改的規則

1. 搬家不詢問、不查證、不改檔、不 commit，固定「list → 建六個 → 刪舊的」；prompt 一字不改照抄。
2. 搬家＝建新＋刪舊，不是改舊：`update_trigger` 改不了綁定會話、跨會話 update 也被組織政策擋，但**跨會話 delete 可行**（2026-07-24 實證）。
3. 排程一律「火進主會話」，不回頭用「開新會話」模式。
4. 不記死 trigger id；以 `list_triggers` 實查為準。
5. 改了「生效條件」那四類東西，要確認綁定會話的分支拿得到（它每天合併 main，或排程搬家），不能只看 main。
6. 搬家後一定提醒使用者「模型要重設」。

## 踩過的坑

- **`list_triggers` 輸出超過工具上限（2026-08-07 實測 70KB／一行）**：帳號裡累積數十個 `send_later` 一次性 trigger，回應被截斷並存成檔案。修法＝步驟 1 的讀法。
- **「開新會話」模式兩次全滅（2026-07-18）**：見上面「為什麼火進主會話」。
- **以為設過 sonnet（2026-07-27 使用者踩到）**：實際每日跑都是新視窗的預設模型。修法＝搬家步驟 5 提醒「模型要重設」。
- **本檔沒記載的排程（2026-08-07）**：05:08 美股收盤序列那支是搬家時在 `list_triggers` 裡才發現的，所以有搬家步驟 4 的「本檔要補記」。
- **分支太舊、排程用到舊版**：YouTube 金鑰（[全部更新](daily-update.md) 9⑦）、簡介併檔通道（9⑤）、`not_tracked` 被併檔段洗掉（[即將登場](../main/etf-upcoming.md)）、
  `x9s.json` 沒被 add（[籌碼雷達介面改版歷史](../lab/chip-ui.md)）。機制見「生效條件」。

## 歷史

- 2026-07-18：建每日 06:35 Routine；同日改「火進主會話」模式。
- 2026-07-20：使用者指示 07:03 前線上可看當日內容。
- 2026-07-23：使用者想改用 sonnet 跑排程省 token，查明目前工具做不到（見「搬家後模型要重設」）。
- 2026-07-24：建「排程搬家」指令；本檔不再記死 trigger id。
- 2026-07-27：搬家步驟加「模型要重設」提醒。
- 2026-08-03：擴為三個（加 15:33 盤後籌碼、18:58 晚間 NAV·PCF）。
- 2026-08-05：建 05:08 美股收盤序列；2026-08-07 搬家時發現本檔沒記載，補記，四個。
- 2026-08-10：加週一 08:05 ETF 募集週掃，五個；同日踩到 -32003。
- 2026-08-12：15:33 班加「前十大簡介缺口順手補」。
- 2026-10-17：排程會話開始每天 06:36 合併 main（2026-10-23 查到）。
- 2026-10-24：加週日 19:47 策略探勘週報，六個一起搬。
