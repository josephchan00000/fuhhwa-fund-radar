# 指令「整理知識庫」

> 使用者打「整理知識庫」才全面檢查：體檢、事實比對、找矛盾與過時、修好、日誌一行、回報；平常做完事只改相關的那一頁。
> 原始資料：CLAUDE.md「指令：整理知識庫」段；規劃 `docs/llm_wiki_plan.md` 第 5、14 節；程式 `scripts/wiki_lint.py`、`scripts/wiki_facts.py`、`scripts/wiki_split.py`、`tests/test_wiki.py`。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那一段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

知識庫＝`wiki/`（目錄 `wiki/index.md`、日誌 `wiki/log.md`）；第 5 段瘦身之前 CLAUDE.md 仍是正本。

使用者 2026-10-29 的決定：**做完事順手改**（只改相關的那一頁、`wiki/log.md` 加一行 `## [日期] 操作 | 標題`）**＋你說才整理**——
全面檢查只在使用者打「整理知識庫」時做，不排程、不在別的指令裡順便做。

全程不跑資料抓取腳本、不動 `reports/**`，也不碰 push 會觸發 workflow 的檔（`data/etf_upcoming.json`、`config/holding_profiles.json`、
`config/index_reviews.json`、`config/strategy_candidates.json`、`config/strategy_board.json`、`arm/lab/cands/**`）：

1. `python3 scripts/wiki_lint.py`（只讀）：
   - 錯＝連結斷、頁沒列進目錄、頁太長（1.5 萬字）、頁首格式、CLAUDE.md 的事實記號頁上不見了、路徑規則 `.claude/rules/*.md` 的 paths 對不到檔或指到不存在的頁；
   - 提醒＝「現在怎麼運作」「不能改的規則」兩節提到的檔案或 `模組.函式` 找不到、沒有任何頁連到的頁、CLAUDE.md 太長。
2. 錯一定修。提醒逐條看：改名或拿掉了 → 改那一頁（舊說法移到「歷史」）；本來就該這樣的留著。
3. `git log --since=<日誌上次「整理」的日期>` 看之後動過的程式，對照相關頁：互相矛盾、被新規則蓋掉的舊規則 → 舊的移到「歷史」或刪掉；
   刪事實記號要在日誌寫 `- 刪：`記號`——原因`（`scripts/wiki_facts.py` 才不會報不見）。有矛盾不確定哪個對 → 先問使用者，不要猜。
4. `python3 scripts/wiki_facts.py` 與 `python3 -m pytest -q tests/test_wiki.py` 全綠 → 日誌加一行 `## [日期] 整理 | 摘要`
   → commit「chore: 整理知識庫 {日期}」push 本會話指定分支 → 開 PR、merge 進 main。
5. 回報：改了哪幾頁、刪了什麼、有沒有要使用者決定的矛盾。

### 路徑規則（`.claude/rules/*.md`）

讀到某些檔時自動載入的提醒：開頭 `paths:` 列檔案樣式，內容＝該先讀哪一頁＋幾條不能改的規則（每份不超過 1,500 字）。
頁改名或拆頁時要一起改規則（體檢會擋）。

## 不能改的規則

- **大原則（使用者 2026-10-29 原話）**：「切記你的架構要清晰不要變成會浪費更多的token 然後絕對不要影響到本來的產出品質跟架構邏輯
  不要因為這個把本來的根本弄掉了」「一些沒用或是明顯被覆蓋的規則可以清除，但我上面提到的大原則絕不要忘記」。
- 跨主題的教訓寫進 [跨主題的教訓](../lessons.md)，使用者的偏好與原話寫進 [使用者偏好](../user.md)。
- 頁的格式：`# 標題`、`> 一句話摘要`、`## 現在怎麼運作` 在最前面，再來不能改的規則、踩過的坑、歷史；改的是過時的句子，不是往後加。

## 歷史

- 2026-10-29：LLM Wiki 第 4 段建立這個指令、`scripts/wiki_lint.py` 與路徑規則。
