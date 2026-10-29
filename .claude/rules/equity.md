---
paths:
  - "arm/lab/eq*.py"
  - "scripts/eq_*.py"
  - "scripts/check_eq.py"
  - ".claude/skills/equity-report/**"
---
改個股報告或產業報告之前，先讀 `wiki/lab/equity-report.md`；寫報告照技能 `.claude/skills/equity-report/SKILL.md`。
- 報告裡的數字只能來自資料包（`scripts/eq_facts.py`），或同一段附來源連結；`scripts/check_eq.py` 全 🟢 才能推。
- 評等與目標價照 `arm/lab/eqspec.py`（事前寫定、要改＝VER＋1 並先問使用者）；「目標價」只准出現在個股報告。
- 舊版報告不覆蓋（新檔＝新報告日）；容器內不跑資料抓取。
