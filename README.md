# 復華基金追蹤版本 · Fuh Hwa Fund Radar

追蹤 **復華投信共同基金**（全球股票型／全球平衡型）的每日情報工具。每天做兩件事：

1. 🧾 **持股介紹** — 每檔基金的基本資料 / NAV / 多期報酬 / 國家・產業配置 / **十大持有標的＋重點標的簡介**（月度官方揭露快照）。
2. 🗞️ **昨夜美股重大新聞** — 聚焦 Nasdaq／費城半導體／S&P500 的**公司與產業面**事件（AI／晶片／雲端／併購／財報／供應鏈…），兩種版型（Top 3 速寫包＋精簡版），附來源、台北時間戳與合規燈。

> 本版本刻意**不做「每天持股變化」**：共同基金僅月底揭露前十大持股、無逐日持股張數，故改以「持股介紹」呈現。（此為由主動式 ETF 行銷雷達改建的追蹤版本，ETF 專用的逐日換股/籌碼/文案引擎已非本版本主軸。）

---

## 追蹤清單（11 檔，見 `config/funds.json`）

**全球股票型**：復華美國新星(47)、全球大趨勢(23)、全球物聯網科技(77)、華人世紀(24)、亞太成長(18)、亞太神龍科技(82)、中國新經濟A股(57)、大中華中小策略(29)
**全球平衡型**：全球平衡(12)、中國新經濟平衡(53)、亞太平衡(16)

（括號內為 `fhtrust.com.tw/funds/funds_detail/{id}` 的 id；要增減基金只需改 `config/funds.json`。）

---

## 台股版本（12 檔，見 `config/funds_tw.json`）

同一套引擎以**多市場參數化**擴充出的**台股版本**，涵蓋復華國內股票型＋國內平衡型＋台灣智能。
**整合成同一頁**（`dashboard/index.html`）上層以「**海外／台股**」切換（亦保留 `dashboard/tw.html` 台股獨立頁）。

**國內股票型（7）**：中小精選(08)、台灣好收益(117)、台灣科技高股息A(122)、全方位A(15)、高成長(03)、復華(01)、數位經濟(06)
**國內平衡型（4）**：人生目標(11)、神盾(13)、傳家(04)、傳家二號(07)
**台灣智能（1）**：台灣智能(79) — **組合型（fund-of-funds）**，官網詳情頁無標準「十大持有標的」表；連接器退而解析其基金／ETF 投資標的（`holdings_kind="fund"`），抓不到時顯示組合型說明並導向月報。

**設計決策（todo D1–D4）**：
- **D1(b)** 台股專用新聞版型「**台股盤後重點 ＋ 盤前美股影響**」（`arm/twnews.py` / `scripts/gen_twnews.py`），與海外版「昨夜美股」平行、共用禁用詞合規掃描。
- **D2(b)** 單頁上層「海外／台股」切換（`fund_dashboard.render_combined`），各市場自帶新聞區塊與基金分頁，JS 作用域限縮於各面板。
- **D3(b)** 同基金多類別只留主類別（台灣科技高股息留 A 類型122、捨 B 類型123；全方位留 A 類型15、捨 TISA 類型125），避免重複 → 12 檔。
- **D4** 台灣智能(79) 解析基金／ETF 投資標的；市場註冊表見 `arm/markets.py`。

```bash
# 抓台股 12 檔持股介紹 → data/funds_tw/{id}.json
python3 scripts/fetch_holdings.py --market tw
python3 scripts/fetch_holdings.py --market tw 06        # 只抓指定 fundID

# 產台股新聞提示包（台股盤後重點＋盤前美股影響）→ 由 Claude 上網查證產 v1/v2
python3 scripts/gen_twnews.py
python3 scripts/gen_twnews.py --check                   # 禁用詞合規掃描

# 產整合頁（海外＋台股切換）→ dashboard/index.html；或台股獨立頁 → dashboard/tw.html
python3 scripts/gen_fund_dashboard.py --open            # 整合頁
python3 scripts/gen_fund_dashboard.py --market tw       # 台股獨立頁

# daily_fund.sh 已一併重建海外版 + 台股版（整合頁＋獨立頁）
```

---

## 快速開始（零安裝，純標準庫 + certifi TLS）

```bash
# 1) 抓 11 檔基金的持股介紹 → data/funds/{id}.json
python3 scripts/fetch_holdings.py
python3 scripts/fetch_holdings.py 47 12        # 只抓指定 fundID

# 2) 產昨夜美股新聞「提示包」（兩版型規格已內建、自動帶今日/昨夜美股交易日）
python3 scripts/gen_usnews.py
#    → 產 reports/usnews/prompts/{date}.md
#    新聞內容需「會上網查證的 LLM」產出（純 Python 不杜撰新聞），兩條路擇一：
#      A) Claude Code：說「依此提示包上網查證，產 v1/v2 兩檔」→ 產 reports/usnews/{date}_v1.md、_v2.md
#      B) 貼進聯網的 Claude，回存兩檔
python3 scripts/gen_usnews.py --check          # 對最新產出跑禁用詞合規掃描

# 3) 產儀表板（整合頁：海外／台股切換 + 持股介紹 + 昨夜美股/台股新聞 + 合規燈）→ dashboard/index.html
python3 scripts/gen_fund_dashboard.py --open

# 或一次跑完（新聞內容步驟仍由 LLM 補）：
bash scripts/daily_fund.sh
```

儀表板為**單一 `dashboard/index.html`**（**零 JS**——分頁切換以純 CSS radio+label 實現，任何禁 script 的預覽環境也能操作；零外部請求、雙擊即開，無 npm/node）：上層「海外／台股」切換，各市場頂部為新聞區塊（⚡本日重點速覽＋重點置頂新聞卡＋兩版型切換＋🟢/🔴 合規燈），下方每檔基金分頁的持股介紹。

---

## 資料來源與正確性

| 資料 | 來源 | 端點 | 頻率 |
|---|---|---|---|
| 基本資料 / NAV / 多期報酬 / 經理人 / 月報 / 投資策略 | 復華投信官網 | `GET /api/fund?fundID={id}`（JSON） | 每日 NAV |
| 十大持有標的（含產業）/ 國家配置 / 產業配置 / 資料日期 | 復華投信官網 | `/funds/funds_detail/{id}`（SSR HTML／SVG 解析） | 月底 |
| 重點標的簡介 | 人工／查證後落檔 | `config/holding_profiles.json` | 靜態，可增修 |
| 昨夜美股新聞 | Reuters/Bloomberg/WSJ/FT 等公開來源 | LLM 上網查證 → `reports/usnews/{date}_v*.md` | 每日 |

持股為**月度**官方揭露（如 2026/05/31），NAV 為每日；儀表板皆標「持股基準日」與「NAV 日」以免混淆。連接器純標準庫正則解析（`arm/connectors/fhfund.py`），缺任一端點即該欄留空、不整批崩。

---

## 程式骨架（追蹤版本新增／核心）

```
config/funds.json              海外版追蹤清單（id / name / group）— 單一事實來源
config/funds_tw.json           台股版追蹤清單（12 檔；domestic_equity / domestic_balanced / fof）
config/holding_profiles.json   重點標的簡介（中性事實敘述、非投資建議；跨市場共用，key 為持股原字串）
arm/markets.py                 市場註冊表（global / tw：設定來源 / 資料夾 / 輸出檔名 / 標題 / 新聞源 / 切換鈕名）
arm/connectors/fhfund.py       復華共同基金連接器（meta+NAV+報酬 / 十大持股 / 國家・產業配置；fof 退路解析基金標的）
arm/fund_intro.py              持股介紹組裝（掛簡介、摘要句、集中度；依 market 決定資料夾）
arm/usnews.py                  昨夜美股：兩版型規格常數 + 產出讀取 + 禁用詞合規掃描
arm/twnews.py                  台股新聞：台股盤後重點＋盤前美股影響（沿用 usnews 合規掃描）
arm/fund_dashboard.py          零安裝儀表板（render(market) 單市場 / render_combined 整合頁上層切換）
scripts/fetch_holdings.py      抓持股介紹 → data/funds/{id}.json（--market tw → data/funds_tw/）
scripts/gen_usnews.py          產昨夜美股提示包 / --check 合規掃描
scripts/gen_twnews.py          產台股新聞提示包 / --check 合規掃描
scripts/gen_fund_dashboard.py  產整合頁 dashboard/index.html（--market tw → 台股獨立頁 dashboard/tw.html）
scripts/daily_fund.sh          每日 routine 單一進入點（重建海外版 + 台股版整合頁）
tests/test_fund_tracker.py     新模組單測（fhfund 解析 / usnews / fund_intro）
tests/test_markets.py          多市場參數化單測（markets / funds_tw / twnews / 整合頁 / fof）
```

`arm/http.py`（certifi TLS）、`arm/config.py`（設定載入）沿用。ETF 版遺留的行銷/籌碼/文案模組仍在庫中但非本版本主軸。

---

## 合規（重要）

- 本工具為**市場資訊彙編／教育用途，非投資建議或招攬**；對外發布前建議經法遵核可。
- 禁用詞（`arm/usnews.BANNED`，內建掃描）：保證／穩賺／唯一／建議買賣／目標價 等；機構觀點以「該機構表示／認為／估測（日期）」呈現；不預測報酬、不以過去績效推未來。
- 揭露：投資人申購本基金係持有基金受益憑證，非本文提及之投資資產或標的；過去績效不代表未來表現，淨值可能因市場變動而上下；境外基金涉及匯率與國際市場風險；申購前應詳閱公開說明書／投資人須知。
- 新聞若查無足量或無法查證，一律誠實加「資料侷限說明」，切勿杜撰標題、數字或引言。

---

## 測試

```bash
python3 -m pytest -q          # 全綠
```
