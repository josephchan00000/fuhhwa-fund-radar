# 排程會話 MCP 審批（-32003）

> send_later 被擋的原因、settings.json 預先核准、背景迴圈備援。
>
> 這一頁目前是從 CLAUDE.md 逐字搬來的（知識庫第一段），還沒整理；有出入時以 CLAUDE.md 為準。
> 改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產這一頁。

<!-- CLAUDE.md 第 602–620 行 -->
- **排程會話的 send_later／create_trigger 被 MCP 審批擋下：`MCP error -32003: MCP tool call requires approval`（2026-08-10 踩坑）**：
  15:33 盤後 Routine 步驟①觸發 workflow 成功（**同回合 github MCP 的 actions_run_trigger 完全沒被擋**、
  當日資料 15:36 照樣入庫），但步驟② send_later 與備援 create_trigger 連續 -32003——無人值守沒人能按核准，
  自驗鏈整條排不了。**同日診斷：非平台級強制審批**——另開互動會話呼叫 send_later 一次成功（無審批即回
  trigger_id），即審批要求是「逐會話授權」：排程綁定會話少了 claude-code-remote 工具的預先核准就會中。修法三道：
  ① **`.claude/settings.json`（2026-08-10 入庫）`permissions.allow` 預先核准**：官方文件確認
    `mcp__<伺服器>__<工具>` 允許規則可免互動核准（伺服器名的連字號／空白會正規化成底線、比對不分大小寫）。
    清單＝claude-code-remote 六個 trigger 工具＋github actions 四工具（後者目前沒被擋，一併免疫）。
    **生效條件＝排程會話 checkout 的分支上要有這支檔**：先 merge 進 main，再做一次「排程搬家」
    （新會話自最新 main 分岔）才會被讀到——與步驟 9⑦ YOUTUBE_API_KEY workflow 檔同型的傳播機制。
  ② **無 MCP 自驗備援（Routine prompt ②③④ 原文已補同一句）**：send_later 回 -32003 → 改用
    `Bash run_in_background` 背景 until 迴圈（每 5 分鐘 `git fetch origin main` 驗一次目標欄位，
    到自驗時點仍缺就輸出 MISSING 結束）；背景任務結束會喚醒會話，續走「補 dispatch → 再等 → 仍缺才推播」。
    注意它只在「容器活著」時有效（閒置回收無官方保證）——跨容器持久性只有 send_later／Routine 有，
    所以 send_later 仍是首選、這是備援；全鏈失敗的最後防線本來就在（CI 看門狗 afterhours_alert＋
    run ❌ failure 信＋cron 兜底）。CronCreate／Monitor 同為會話行程內存機制，**不可**當持久排程替代。
  ③ **立即緩解（不必等 merge）**：使用者在排程綁定的主會話請 Claude 呼叫一次 send_later 並按
    「一律允許」——該會話建立核准後，後續無人值守回合即可通過（此核准能否跨容器重佈建存活，
    官方未載明；根治仍靠 ①）。
