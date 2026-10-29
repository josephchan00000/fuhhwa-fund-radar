# 出處與授權

這份技能的流程與報告架構改寫自 Anthropic 的 financial-services-plugins
（https://github.com/anthropics/financial-services-plugins ，Apache License 2.0，授權全文：https://www.apache.org/licenses/LICENSE-2.0 ）：

- `plugins/vertical-plugins/equity-research/skills/initiating-coverage`（首次報告五步驟、首頁格式、圖表編號、品質檢查清單）
- `plugins/vertical-plugins/equity-research/skills/sector-overview`（產業報告架構）
- `plugins/vertical-plugins/equity-research/skills/catalyst-calendar`、`thesis-tracker`（催化劑、論點追蹤）
- `plugins/vertical-plugins/financial-analysis/skills/comps-analysis`、`competitive-analysis`（同業比較、競爭定位）

改了什麼（2026-10-29）：全部改寫成繁體中文；報告從 30～50 頁 Word 改成 8～12 頁網頁；數字一律來自本專案的資料包（不使用原外掛的付費資料源）；
估值改用本益比／淨值比區間與固定的評等門檻（`arm/lab/eqspec.py`）；拿掉 DCF 與 Excel 模型；加上台股資料（月營收、三大法人、ETF 持股、產業鏈）。
原外掛的程式與檔案沒有複製進本專案。
