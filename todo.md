# TODO — 復華台股基金追蹤版本

> 目標：在現有「復華基金追蹤版本」(fuhhwa-fund-radar) 之上，新增一個 **台股版本**，涵蓋
> 復華 **國內股票型 + 國內平衡型 + 台灣智能**。沿用同一套引擎（`fhfund` 連接器、`fund_intro`、
> `fund_dashboard`、`usnews`），以**多市場參數化**方式擴充，不改動既有海外版行為。
>
> 好消息：連接器已驗證可直接抓台股基金（下方清單皆實測成功，NAV 為每日、持股月度）。

---

## 一、追蹤清單（14 檔，皆已用連接器實測 ✓）

### 國內股票型（9）
| id | 基金 | 備註 |
|----|------|------|
| 08 | 復華中小精選基金 | |
| 117 | 復華台灣好收益基金 | |
| 122 | 復華台灣科技高股息基金A類型 | 與 B 為同基金不同類別 |
| 123 | 復華台灣科技高股息基金B類型 | |
| 15 | 復華全方位基金A類型 | 與 TISA 為同基金不同類別 |
| 125 | 復華全方位基金TISA類型 | |
| 03 | 復華高成長基金 | |
| 01 | 復華復華基金 | |
| 06 | 復華數位經濟基金 | 實測 ✓ 台積電8.72%/台達電8.28%/旺矽7.52% |

### 國內平衡型（4）
| id | 基金 | 備註 |
|----|------|------|
| 11 | 復華人生目標基金 | 實測 ✓ 台光電/欣興/台積電 |
| 13 | 復華神盾基金 | |
| 04 | 復華傳家基金 | |
| 07 | 復華傳家二號基金 | |

### 台灣智能（1）
| id | 基金 | 備註 |
|----|------|------|
| 79 | 復華台灣智能基金 | **組合型（fund-of-funds）**；⚠ 詳情頁「十大持有標的」表為空（0 檔），持股揭露結構不同，需特別處理（見風險①） |

---

## 二、需先拍板的設計決策

- [x] **D1 · 台股版昨夜新聞要哪一種？** → **拍板 (b)**：新版型「台股盤後重點 + 盤前美股影響」（`arm/twnews.py` + `scripts/gen_twnews.py`，沿用 usnews 禁用詞合規掃描）。
  - (a) 沿用「昨夜美股」digest（台股半導體高度連動美股，仍高度相關）＝零額外工。
  - (b) 改做「台股盤後重點 + 盤前美股影響」新版型（需新 spec + 產生器分支）。← 採用
  - (c) 兩者都放（美股 + 台股各一區塊）。
- [x] **D2 · UI 形態？** → **拍板 (b)**：同一頁上層「海外／台股」切換（`fund_dashboard.render_combined` → `dashboard/index.html`；另保留 `--market tw` 產台股獨立頁 `tw.html`）。
  - (a) 獨立頁 `dashboard/tw.html`（最省、最低風險，海外版完全不動）。
  - (b) 同一頁加「台股／海外」上層切換（整合體驗、需較多改動）。← 採用
- [x] **D3 · 同基金多類別（A/B、A/TISA）是否合併？** → **拍板 (b)**：只留主類別（捨 123 高股息B、125 全方位TISA）→ 追蹤 **12 檔**。
  - (a) 全列（與海外版一致，用 id 當唯一鍵）。
  - (b) 只留主類別，避免重複。← 採用
- [x] **D4 · 台灣智能(79) 若持股抓不到，如何呈現？** → **拍板：另解析其 ETF 持股**（`fhfund` 退路嘗試 `_FOF_HEADINGS` 下的基金/ETF 標的表，`holdings_kind="fund"`；仍抓不到則顯示組合型說明＋月報連結）。⚠ 標題候選需以 79 實際頁面驗證（見風險①）。

---

## 三、建置步驟（checklist）

### A. 多市場參數化（核心，低風險）
- [x] `config/funds_tw.json`：依 D3(b) 為 12 檔，每筆 `{id, name, group}`；group ∈ `domestic_equity | domestic_balanced | fof`。
- [x] `arm/markets.py`（新）：市場註冊表（global/tw：funds/data/out/title/subtitle/news/news_label/tab_label）。
- [x] `arm/config.py`：`funds()` 加 `market="global"` 參數（讀對應 json）；保持既有無參呼叫相容。
- [x] `arm/fund_intro.py`：`load/all_funds` 參數化資料夾與設定來源（依 market）；新增 `funds_dir(market)`；`GROUP_LABEL` 補台股三組。
- [x] `arm/fund_dashboard.py`：`render(market="global")` ＋ `render_combined()`（D2b 整合頁），標題/資料源/新聞區塊依 market。

### B. 抓資料
- [x] `scripts/fetch_holdings.py`：加 `--market tw` → 寫 `data/funds_tw/{id}.json`。
- [ ] ⚠ 跑一次全 12 檔，確認 NAV/十大/國家/產業/基準日皆有；記錄 79 的狀況。（**本開發環境 egress 封鎖 fhtrust.com.tw，需在可連外環境跑**，如 GitHub Actions daily.yml）
- [x] `.gitignore`：比照 `data/funds/*.json`，放行 `data/funds_tw/*.json`。

### C. 重點標的簡介（台股個股）
- [ ] ⚠ 收集 12 檔的持股聯集（需先完成 B 的實抓）。
- [x] 預補台股常見大型持股簡介（中性事實、非投資建議）至 `config/holding_profiles.json`（台積電/台達電/欣興/台光電/旺矽原有；新增鴻海/廣達/聯發科/金控股等 29 檔）。
- [ ] ⚠ 驗證：所有台股持股經 `fund_intro.load` 合併後皆有 intro（全覆蓋檢查；待 B 實抓後執行）。

### D. 儀表板 + 產生器
- [x] `scripts/gen_fund_dashboard.py`：預設產整合頁 `index.html`（D2b）；`--market tw` → 台股獨立頁 `dashboard/tw.html`。
- [x] 採 D1(b)：新增 `arm/twnews.py` ＋ `scripts/gen_twnews.py`（台股盤後重點＋盤前美股影響）。
- [ ] ⚠ 目視檢查台股面板：12 分頁、持股介紹、配置圖、新聞區塊、合規揭露（待 B 實抓有資料後）。

### E. Routine / CI / 文件
- [x] `scripts/daily_fund.sh`：加跑台股（`fetch_holdings --market tw` + `gen_twnews` + 整合頁/獨立頁）。
- [x] `.github/workflows/daily.yml`：artifact/commit 納入 `data/funds_tw/*.json` + `reports/twnews/*_v*.md` + `dashboard/tw.html`。
- [x] `README.md`：加台股版本段落與追蹤清單（含 D1–D4 決策記錄）。

### F. 測試
- [x] `tests/test_markets.py`：台股 config 載入、`funds_tw.json` 完整性、市場參數化 `fund_intro`/`fund_dashboard` 冒煙、twnews、整合頁切換、fof 解析。
- [x] `python3 -m pytest -q` 全綠（151 passed）。

---

## 四、驗收（DoD）

- [ ] ⚠ 整合頁台股面板呈現 12 檔台股基金的完整持股介紹（NAV/報酬/配置/十大＋簡介），資料 100% 來自復華官網、可追溯。（待可連外環境實抓；本開發環境 fhtrust.com.tw 被 egress 封鎖）
- [ ] ⚠ 台股持股簡介全覆蓋（無 `no_intro`）。（待實抓後跑全覆蓋檢查）
- [x] 新聞區塊（D1b 台股版型＋海外美股版型）機制正常、合規掃描（禁用詞＋否定詞豁免）可運作。
- [x] 全測綠（151 passed）；`daily_fund.sh` 一鍵可重建海外版 + 台股版（整合頁＋獨立頁）。
- [x] 合規揭露齊備（受益憑證、過去績效不代表未來、非投資建議、禁用詞掃描；台股版揭露段不含境外匯率語、補平衡型債券風險）。

---

## 五、已知風險 / 待解

1. **台灣智能(79) 持股為 0**：組合型基金詳情頁沒有標準「十大持有標的」表 → 需檢視其 SSR HTML 結構（可能列的是 ETF 持股、或只在月報 PDF）。方案：(a) 只顯示 meta+月報連結；(b) 針對 fof 另寫解析分支。上線可先用 (a)。
2. **國內平衡型的「國家配置」多為單一（台灣）**：長條圖會較單調；平衡型另有債券部位，確認 `country_alloc/sector_alloc` 是否涵蓋債券（海外版 00986D 類似情況已處理）。
3. **同基金多類別**（122/123、15/125）NAV/持股幾乎相同 → 若嫌重複，套 D3(b)。
4. **台股新聞版型**（若走 D1(b)）需另寫 spec 與產生器分支，並注意台股個股同樣受禁用詞規範。

---

## 六、預估工作量

- 參數化 + config + 抓資料 + 儀表板：約半天（引擎已就緒，多為設定與參數化）。
- 台股個股簡介：視聯集數量，約 30–60 檔，可用子代理批量產出後人工抽查。
- 台灣智能(79) 特殊處理：另計，建議獨立一張子任務。

_本檔為建置計畫；實作時逐項打勾。引擎與海外版共用，改動以「新增」為主、不動既有海外版行為。_
