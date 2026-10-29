---
paths:
  - "arm/usnews.py"
  - "arm/twnews.py"
  - "arm/macronews.py"
  - "scripts/gen_*news.py"
  - "scripts/check_reports.py"
---
改新聞提示包、閘門或新聞卡解析之前，先讀 `wiki/ops/news-rules.md`（新聞卡渲染見 `wiki/main/news-cards.md`，行事曆見 `wiki/main/calendar.md`）。
- 卡內欄位標籤一律 `N. **標籤**：`；解析缺欄位時改報告，**不要放寬 `extract_cards()` 的 regex**。
- 錨定與閘門是「下限保證」，不是選題範圍；閘門只能多一道檢查，不能排除任何新聞。
- 禁用詞與「目標價」例外見 `wiki/ops/content-rules.md`。
- 排程會話用自己分支上的 gen_*.py；它每天 06:36 先合併 main，merge 後下一班生效（`wiki/ops/routines.md`）。
