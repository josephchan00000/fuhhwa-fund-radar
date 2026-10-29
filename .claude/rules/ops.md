---
paths:
  - ".github/workflows/**"
  - "vercel.json"
  - "dashboard/vercel.json"
  - "scripts/check_live_deploy.py"
  - "scripts/daily_fund.sh"
  - ".claude/settings.json"
---
改 workflow、部署、排程相關設定之前，先讀 `wiki/ops/deploy.md`、`wiki/ops/schedule.md`、`wiki/ops/ci-budget.md`、`wiki/ops/routines.md`。
- push 觸發的 workflow 用「被推分支」上的 workflow 檔；改了要確認 main 上真的有。
- 兩支 vercel.json 要一致；`claude/**` 預覽部署關掉，main 不得關。
- 煙測只擋結構壞頁，數字對錯不擋發佈；新增排程或步驟前先想分鐘帳。
- 「內容在 main」不等於線上已部署；不可宣稱線上已生效。
