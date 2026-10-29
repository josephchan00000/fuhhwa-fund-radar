# 排程會話 MCP 審批（-32003）

> 排程會話呼叫 send_later／create_trigger 回 -32003 是逐會話授權的問題：`.claude/settings.json` 預先核准（排程搬家後才生效）、排不了就用背景 until 迴圈自驗、或請使用者按一次「一律允許」。
> 原始資料：CLAUDE.md「已知環境限制與防呆」段的 -32003 條（Routine prompt ②③④ 原文寫的「機制見 CLAUDE.md「已知環境限制與防呆」-32003 條」就是指這一條）；程式：`.claude/settings.json`。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

**徵狀**：排程會話的 send_later／create_trigger 回 `MCP error -32003: MCP tool call requires approval`，無人值守沒人能按核准，自驗鏈整條排不了。

**原因**：不是平台級強制審批，而是「逐會話授權」——排程綁定會話少了 claude-code-remote 工具的預先核准就會中
（另開互動會話呼叫 send_later 一次成功，無審批即回 trigger_id）。

修法三道：

1. **`.claude/settings.json`（2026-08-10 入庫）`permissions.allow` 預先核准**：官方文件確認 `mcp__<伺服器>__<工具>` 允許規則可免互動核准
   （伺服器名的連字號／空白會正規化成底線、比對不分大小寫）。清單＝claude-code-remote 六個 trigger 工具＋github actions 四工具
   （後者目前沒被擋，一併免疫）。
   **生效條件＝排程會話 checkout 的分支上要有這支檔**：先 merge 進 main，再做一次「排程搬家」（新會話自最新 main 分岔）才會被讀到——
   與步驟 9⑦ YOUTUBE_API_KEY workflow 檔同型的傳播機制（見 [排程與「排程搬家」](../ops/routines.md)、[全部更新](../ops/daily-update.md)）。
2. **無 MCP 自驗備援**（Routine prompt ②③④ 原文已補同一句）：send_later 回 -32003 → 改用 `Bash run_in_background` 背景 until 迴圈
   （每 5 分鐘 `git fetch origin main` 驗一次目標欄位，到自驗時點仍缺就輸出 MISSING 結束）；背景任務結束會喚醒會話，
   續走「補 dispatch → 再等 → 仍缺才推播」。
3. **立即緩解（不必等 merge）**：使用者在排程綁定的主會話請 Claude 呼叫一次 send_later 並按「一律允許」——該會話建立核准後，
   後續無人值守回合即可通過（此核准能否跨容器重佈建存活，官方未載明；根治仍靠第 1 道）。

## 不能改的規則

- **send_later 仍是首選，背景迴圈只是備援**：背景迴圈只在「容器活著」時有效（閒置回收無官方保證），跨容器持久性只有 send_later／Routine 有。
  全鏈失敗的最後防線本來就在（CI 看門狗 afterhours_alert＋run ❌ failure 信＋cron 兜底，見 [每日時點地圖與 cron](../ops/schedule.md)）。
- CronCreate／Monitor 同為會話行程內存機制，**不可**當持久排程替代。

## 踩過的坑

- **2026-08-10 盤後 Routine 自驗鏈排不了**：15:33 盤後 Routine 步驟①觸發 workflow 成功（**同回合 github MCP 的 actions_run_trigger
  完全沒被擋**、當日資料 15:36 照樣入庫），但步驟② send_later 與備援 create_trigger 連續 -32003。同日診斷出是逐會話授權，修法＝上面三道。

## 歷史

- 2026-08-10：踩坑、同日診斷、`.claude/settings.json` 入庫。
