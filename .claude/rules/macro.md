---
paths:
  - "arm/macrochips.py"
  - "arm/factcheck.py"
  - "scripts/fetch_macro_chips.py"
  - "scripts/check_numbers.py"
---
改市場溫度計或官方數字核對之前，先讀 `wiki/main/macro-thermometer.md`。
- 絕不把非空序列洗成空；None 與 0（無資料哨兵）不寫入；最新一天每輪重抓（官方會盤後修正）。
- 外資辨識用「陸資」，勿用「自營 not in」；期交所外資淨部位只有一份解析（`_taifex_tx_foreign`），口徑鎖 TX 大台＋外資。
- 不手動填補缺漏日；過期由 ⚠ 過期章揭露。
- 容器內跑 `check_numbers.py` 後 `git status data/` 確認沒洗掉 `data/factcheck.json`。
