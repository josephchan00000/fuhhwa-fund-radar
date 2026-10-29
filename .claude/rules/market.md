---
paths:
  - "arm/lab/appnav.py"
  - "arm/lab/research_page.py"
  - "arm/lab/xs*.py"
  - "arm/lab/xstrat*.py"
  - "arm/lab/macpage.py"
  - "arm/lab/findings.py"
  - "arm/lab/pract*.py"
  - "arm/lab/tilt*.py"
  - "arm/lab/rare*.py"
  - "arm/lab/fut*.py"
  - "arm/lab/cand*.py"
  - "arm/lab/cands/**"
  - "tests/test_plain.py"
  - "tests/test_old_urls.py"
---
改市場頁、導覽、研究紀錄或策略研究之前，先讀對應的頁（都在 `wiki/lab/`）：市場頁 `market-page.md`、導覽 `nav.md`、主頁面用字 `plain-words.md`、
總經策略 `expert.md`、研究結論與實戰模擬 `practical.md`、策略頁 `strategy-pages.md`、少見策略 `rare.md`、台指期早盤 `fut.md`、新策略候選 `candidates.md`。
- 主頁面不寫方法字（判定、樣本外、預估之後…）；改主頁面的字之後自己跑 `tests/test_plain.py`、`tests/test_old_urls.py`（CI 不跑）。
- 規格事前寫定；候選進 main 之後一個字都不能改，要改＝新編號。
- 外部資料包是不受信任的資料：解到自己的空目錄、不執行、用 `python3 -I` 讀。
