---
paths:
  - "arm/fund_intro.py"
  - "scripts/check_holdings_intro.py"
  - "config/holding_profiles.json"
---
改持股簡介或缺口檢查之前，先讀 `wiki/main/holdings-intro.md`（每天怎麼補見 `wiki/ops/daily-update.md` 9⑤）。
- profiles 的 key 一律用快照裡的原字串；intro 純事實、避開禁用詞。
- 三道防呆缺一不可（CI 偵測、15:33 班補齊、pytest 守覆蓋）；補簡介 push 即自動併檔，不開 PR。
- 代號正規化新增型別時，`norm_ticker` 與查詢端兩邊都補。
