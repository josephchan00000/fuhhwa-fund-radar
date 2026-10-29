# 知識庫日誌

> 只往後加，新的寫在最下面。格式：`## [YYYY-MM-DD] 動作 | 標題`；動作＝搬家／收錄／整理／查詢。

## [2026-10-29] 搬家 | 第一段：CLAUDE.md 逐字切成 62 頁

- 來源：CLAUDE.md（main `75d3601e0` 那一版，3,976 行、29.5 萬字）。每一行只落在一頁，`python3 scripts/wiki_split.py --check` 驗證接回去一字不差（檔案標題那一行只留在 CLAUDE.md）。
- 使用者的決定（2026-10-29）：先逐字搬、再整理；CLAUDE.md 先照舊，確定知識庫沒問題再處理；做完事順手改頁面，使用者說「整理知識庫」時才做完整整理。
- 這段期間 CLAUDE.md 是正本：改了 CLAUDE.md 就重跑 `python3 scripts/wiki_split.py`，`tests/test_wiki.py` 會擋兩邊不一致。
- 規劃：`docs/llm_wiki_plan.md`。

## [2026-10-29] 收錄 | 交易計畫與今年逐月表改看 N8

- CLAUDE.md 三處新增（交易計畫 VER 5、飆股前瞻記錄 VER 5＋頁面帳本還原兩次的坑、今年逐月表 ytdspec VER 2），重跑 `scripts/wiki_split.py`：內容進 `lab/core-plan.md`、`lab/boom-live.md`、`lab/cfg-research.md`，其他頁只有行號標記移動。

## [2026-10-29] 整理 | 第二段：ops、env、main 三個資料夾

- 25 頁照第 3.3 節的格式重寫（現在怎麼運作 → 不能改的規則 → 踩過的坑 → 歷史），拿掉逐字切片的行號標記；拆出 7 頁：
  `ops/news-rules-scope`、`ops/news-rules-depth`、`ops/news-rules-style`、`ops/news-rules-numbers`、`ops/routines-prompts`、`main/fund-news-social`、`main/etf-holdings-routes`。
- 新寫兩頁：`user.md`（使用者偏好，每條附原話與日期）、`lessons.md`（跨主題的教訓）。
- 事實比對（`python3 scripts/wiki_facts.py`）：CLAUDE.md 那幾段的 2,296 個事實記號（程式碼片段、日期、帶單位的數字、引號裡的字、run 編號、VER）全部還在，不見 0 個；沒有刪任何記號。
- 六段排程 prompt 原文逐行和 CLAUDE.md 比對一字不差。
- 原文前後說法不一致的地方沒有改，列在 `docs/llm_wiki_plan.md` 第 12 節，等確認。
- 目錄改成：整理過的頁，標題與摘要讀頁面自己的第 1、3 行；逐字的 37 頁（lab）照舊由 `scripts/wiki_split.py` 重產。

## [2026-10-29] 整理 | 第三段：lab 資料夾＋第二段縮回原本長度＋CLAUDE.md 11 處過時用字

- lab 37 頁照第 3.3 節重寫；`lab/signals-versions.md` 原本 2 萬字，拆出 `lab/signals-versions-early.md`（VER 1～16）。
- 第二段變長的頁縮回去：拆頁併回原頁（`ops/news-rules` 四個細則頁、`ops/routines-prompts`、`main/fund-news-social`、`main/etf-holdings-routes`），
  整個知識庫的內文比逐字版多 5.6%（多的是每頁開頭四行），第二段結束時是多 35%。
- CLAUDE.md 第二段列的 11 處前後不一致，逐條對程式查證後改用字（規則、門檻、步驟編號、排程 prompt 都沒動），對應的頁同步改。
- 使用者 2026-10-29：「一些沒用或是明顯被覆蓋的規則可以清除，但我上面提到的大原則絕不要忘記」。只刪原文寫明已被取代的，每條帶走的記號如下：
- 刪：`xstratpage.today_line`——舊訊號總覽 x9o.html 卡片底下的總經策略那一行；x9o.html 2026-10-23 起轉址，市場頁段寫「`xstratpage.board／chip／summary／summary_line／today_line` 一併刪掉」。
- 刪：`heatviz._tz_orig`、`1個月・原本看3個月`——VER 15「溫度計另外算進去的」區的標示；原文寫 VER 21 起該區拿掉。
- 刪：`thermocal.vote(R,cells,H,x)`、`ktab(yk,那一年)`——VER 21「過去讀數這樣的時候」改用 sigoos 格子投票；VER 23 原文寫「`thermocal.vote(R)` 只吃統計、不再用 sigoos 的格子」。
- 刪：`.tzst`、`sigpage.today_html`、`今天有效的訊號`——VER 21 今天的重點裡的總經策略小區、舊訊號總覽的「今天有效的訊號」；市場頁段寫這兩個都已刪掉。
