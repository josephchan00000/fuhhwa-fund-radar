---
paths:
  - "arm/lab/heat*.py"
  - "arm/lab/heattech.py"
  - "scripts/run_heat*.py"
  - "scripts/fetch_heat*.py"
---
改景氣頁（市場頁）的計算或畫面之前，先讀 `wiki/lab/heat-tw.md`、`wiki/lab/heat-us.md`、`wiki/lab/heat-viz.md`（版面見 `wiki/lab/market-page.md`）。
- 規格事前寫定，要改＝VER＋1；不因結果不好看放寬門檻或改規格。
- 和台股頁共用的統計常數一律從 heatspec 匯入；Granger 多重比較分家族。
- 不把 `var()` 寫進 SVG 屬性；美股頁不得出現台股文字；sigpage 改 #sgd 格式要一起改 `split_sgd` 與 `sgAdd`。
- SEC 聯絡 email 只從 secret `SEC_CONTACT_EMAIL` 讀，程式與存檔不出現。
