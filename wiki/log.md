# 知識庫日誌

> 只往後加，新的寫在最下面。格式：`## [YYYY-MM-DD] 動作 | 標題`；動作＝搬家／收錄／整理／查詢。

## [2026-10-29] 搬家 | 第一段：CLAUDE.md 逐字切成 62 頁

- 來源：CLAUDE.md（main `75d3601e0` 那一版，3,976 行、29.5 萬字）。每一行只落在一頁，`python3 scripts/wiki_split.py --check` 驗證接回去一字不差（檔案標題那一行只留在 CLAUDE.md）。
- 使用者的決定（2026-10-29）：先逐字搬、再整理；CLAUDE.md 先照舊，確定知識庫沒問題再處理；做完事順手改頁面，使用者說「整理知識庫」時才做完整整理。
- 這段期間 CLAUDE.md 是正本：改了 CLAUDE.md 就重跑 `python3 scripts/wiki_split.py`，`tests/test_wiki.py` 會擋兩邊不一致。
- 規劃：`docs/llm_wiki_plan.md`。
