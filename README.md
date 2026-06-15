# FH-ARM — 復華主動式 ETF 每日行銷情報雷達

把 [etfinfo.tw](https://www.etfinfo.tw/) 的 ETF 資訊站「訊號化」能力學起來，重建成**以復華主動式 ETF 為主角**的每日行銷情報引擎：每天收盤後自動算出「**今天該主打哪檔、用什麼數字證明、怎麼寫成文案、給誰講**」。

## 它每天幫你做什麼
- 🎯 **每日賣點榜**：23 個賣點偵測器掃過所有復華主動 ETF，評分排序出今日最強賣點。
- 🆚 **持股差異化**：復華選股 vs 同業差在哪、獨門卡位了什麼、主動度多高、賭對了沒。
- 📈 **多週期績效**：1日/3日/週/雙週/月/季/YTD/成立來，自動挑「對我們最有利的週期」並列出被比下去的競品。
- 🔥 **量能突出**：爆量、同類量能排名、誰被比下去。
- 🕵️ **分點推敲**：哪個分點在大買、推估可能買家（標「推估」）。
- 📡 **社群/KOL 情報**：地毯式撈網紅與社群講的賣點、聲量、疑似業配 → 直接當素材庫。
- 🧩 **同業話術複製庫**：對手的訴求/招數/口碑行銷收進來，附「套用到復華怎麼改」。
- ✍️ **自動文案**：Claude 火力全開寫多版本文案，合規**事後標注**風險（不擋發想）。

## 技術棧
Python 資料管線 + PostgreSQL + FastAPI（後端 / 公開資料）｜Next.js 儀表板（前端）

## 文件（單一來源）
- 📄 **[docs/SPEC.md](docs/SPEC.md)** — 規格 + 路線圖整合版（v0.6）
  - **Part I 系統規格**：§4 資料源、§5 Schema、§8 偵測器、§18 進階情報引擎、§19 競品情報、§20 資料正確性、§21 想法引擎
  - **Part II 建置路線圖**：里程碑勾選清單（M0✅～M9）、依賴、驗收(DoD)、建議執行順序 ← 想知道「下一步做什麼」看這
  - （原 todo.md 已併入 Part II）

## 現況（M0 + M1 + M2 + M3 + M5 完成；M4 創意情報層介面完成；競品/籌碼已接 etfinfo + Histock live）
- 規格 v0.10（含進階情報引擎 + 合規事後標注 + §20 資料正確性保證 + etfinfo 第三方彙整源）。
- **三檔主角全上線**（00991A 台股、00998A 全球金融股、00986D 全球金融債），皆用權威資料端到端跑通並過 100% 正確性閘門。
- 績效改 **NAV 含息總報酬**（全球股/債無 TWSE 市價，NAV 是唯一權威績效源）；受益人數接 **集保 TDCC**；資金流偵測（規模週增/破關卡）；多檔輪播今日主角。
- **M2 跨家持股差異化（✅ 完成）**：主動度 Active Share（vs 0050）**即時真實**（00991A 76%）；獨門股/權重偏離/Jaccard 重疊/領先卡位由 `arm/diff_engine.py` 計算。**競品逐日持股已接 etfinfo.tw**（6 競品落地）→ 00991A 重押國巨 8.9%（同業均 2.5%、偏離 +6.4pt 居同業之冠）、與統一重疊 Jaccard 40%、與元大僅 15%，全部真實可追溯。
- **M5 題材/時事引擎上線**：題材熱度由 `STOCK_DAY_ALL` 全市場個股漲幅**每日動態算出**（非固定清單），`arm/themes.py`＋`THEME_TAILWIND` 偵測器＋想法引擎「重倉產業＝當日強勢題材」。題材表改 **stock_id 為鍵**（跨 TWSE/復華零歧義）。實測 2026-06-12：重倉【AI半導體龍頭】台積電+聯發科 19.3% 全紅順風。
- **M3 籌碼推敲（✅ 完成，多源 live）**：券商分點 **Histock**（免費前 N 大，每日落快照累積成多日窗→真實「連續買超天數」）＋ **FinMind**（付費 `FINMIND_TOKEN`：全分點+多日+量，優先序最高）；**外資分點合計** `FOREIGN_BRANCH_BUY`（實測南亞科 6 家外資 +21,081 張）；法人籌碼 **etfinfo** `INSTITUTIONAL_BUY`＋「聰明錢共識」。身份經 `broker_map` 推估、**一律標「推估・非確認」**。
- **M4 創意情報（live + Claude 深析）**：`arm/connectors/social/{news,ptt,dcard,facebook,youtube}.py`（免費 news/ptt/dcard 永遠註冊、YouTube/FB 需金鑰）；`analyze(m, llm=)` 接 **Claude（claude-opus-4-8）逐則深析**（`ANTHROPIC_API_KEY`，缺則 baseline）。**每日雲端 routine**：`scripts/daily_routine.sh` + `.github/workflows/daily.yml`（cron 週一~五 17:40）。
- **🆕 第三方資料源（皆 Tier B、缺金鑰即誠實降級不崩）**：etfinfo（競品持股/配息/法人籌碼）、Histock + FinMind（券商分點）、RSS/PTT/Dcard/YouTube/FB（社群）。`pytest` **83 綠**。

### 跑跑看（零安裝，純標準庫 + SQLite；TLS 走 certifi）
```bash
python3 scripts/fetch_etfinfo.py        # （建議先跑）從 etfinfo 補實競品持股 + 法人籌碼（Tier B）
python3 scripts/run_daily.py            # 跑全部主角（含今日輪播主角）
python3 scripts/run_daily.py 00998A     # 只跑單一檔
python3 scripts/backfill_nav.py         # （首次）回補各日 NAV 歷史
```

實測輸出（資料日 2026-06-12）：
```
[資料品質閘門] 全部 ✅（NAV×單位數≈AUM 差 0.0028%、權重合計 98.07%、50 檔股數全正）
[多週期報酬 vs 0050]  成立以來 +97.20% / 基準 +64.70% / Alpha +32.50%
                      年初以來 +82.82% / 基準 +52.28% / Alpha +30.54%
[持股張數異動]        新建倉 臻鼎-KY +2,000張；加碼 國巨 +1,050張…
[今日賣點榜]
  1. ★87.0 ALPHA_BEAT      成立以來超額報酬 +32.50%，跑贏 0050
  2. ★87.0 BEAT_PEERS_MULTI 7 個週期都贏過 0050
  3. ★65.2 MANAGER_ADD      經理人新建倉 臻鼎-KY +2,000 張
  4. ★55.1 HIT_HOT_STOCK    重倉南亞科技漲停 +10%，拉抬淨值
```

### 已驗證的權威資料源（Tier A，必須 100% 正確）
- 績效（NAV 含息）：復華 `/api/assetsExcel/{fund_id}/{YYYYMMDD}` 逐日 NAV → `nav_history`（fund_id：00991A=ETF23、00998A=ETF24、00986D=ETF25）。
- 台股市價交叉驗證：TWSE `STOCK_DAY_ALL`（當日）+ `STOCK_DAY`（歷史）官方收盤。
- 張數/面額/NAV/AUM/在外單位數：同上復華持股 xlsx（支援股票/期貨/債券多區段）。
- 受益人數：集保 TDCC 開放資料（id=1-5 股權分散合計列）→ `holders_history`（週更）。

### Tier B 第三方彙整源（標來源/as-of，待人工核實）
- **etfinfo.tw**（`arm/connectors/etfinfo.py`）：競品每日持股（`/api/etf/{code}`，`source` 多為 issuer-official）、配息/近12月殖利率、**主動ETF/投信估算新進**（`/api/active/tracking`）。經 `scripts/fetch_etfinfo.py` 落成 drop-in。
- **Histock**（`arm/connectors/brokers/histock.py`）：**券商分點買賣超**（個股/ETF 分公司進出靜態 HTML 表）。`brokers.load_flows` 預設 live、`config/broker_flows/{code}.json` 可覆蓋。買家身份經 `broker_map` 推估、**標「推估・非確認」**（分點僅到分公司）。
- **共同鐵則**：非 Tier A，數字先給可能值、上線前以投信官網/證交所核實。

### 程式骨架
```
arm/connectors/{twse,fhtrust,tdcc}.py  權威資料連接器（市價/持股NAV/受益人）
arm/connectors/etfinfo.py          Tier B 第三方彙整（競品持股/配息/法人籌碼；etfinfo.tw JSON API）
arm/connectors/issuers/            跨家持股統一介面（Holding + 競品註冊表 + drop-in 承接）
arm/connectors/brokers/            分點進出統一介面（BrokerFlow + histock live adapter + drop-in 覆蓋）
arm/connectors/social/             社群/KOL 情報統一介面（SocialMention + analyze + adapter slot + drop-in）
arm/calendar.py                    TWSE 交易日曆（由 0050 序列判定）
arm/navhist.py                     NAV 含息總報酬骨幹（回補 + 配息再投入）
arm/quality.py                     100% 正確性閘門（fail-loud；股/債分流）
arm/metrics.py                     多週期報酬/Alpha/持股部位diff
arm/peers.py                       全市場台股主動ETF同類排名
arm/diff_engine.py                 跨家差異化：獨門/偏離z/Jaccard重疊/Active Share/領先
arm/chips.py                       籌碼推敲：券商分點(推估)+主動ETF/投信法人籌碼(聰明錢共識)
arm/themes.py                      題材熱度（STOCK_DAY_ALL 全市場漲幅動態算）
arm/signals.py                     賣點偵測器 + 評分
arm/ideas.py                       多元想法組合引擎 + 合規事後標注
arm/pipeline.py                    端到端流程（多檔輪播）
```

### 同類排名（v0.4，全市場 21 檔台股主動ETF，官方價 100% 正確）
```
年初以來  第 2/11 名   近3月 第 3/13 名   近1週 第 4/18 名
年初以來比下去: 野村00980A、群益00992A、統一00981A …
```
公平性：YTD 只計「年初即存在」的基金（年中掛牌者排除，不虛報）。

### 每日多元想法組合（v0.5，核心）
不給「一個冠軍」，每天跨面向給 ~10 個不同角度（績效／籌碼／題材／同類排名／配息倒數／逆向誠實／持股差異化／同業招數／社群KOL…），合規事後標注 🟢🟡🔴。
```bash
python3 scripts/run_daily.py 00991A      # 即時跑一次
cat reports/2026-06-12_00991A.md         # 看當日想法報告
```
多樣性：類別加權（籌碼/題材/內容創意加重）＋主題日輪換＋防重複＋wildcard。

### 每日自動排程（已設定）
launchd `com.fhtrust.fharm.daily` 週一～五 17:40 自動跑 → `reports/{date}.md`、log 在 `data/daily.log`。
- 關閉：`launchctl unload ~/Library/LaunchAgents/com.fhtrust.fharm.daily.plist`
- 兩層：資料想法層=本機自動；創意情報層（KOL地毯搜尋/競品新招/文案）需 Claude 補實。

### M2 ★ 跨家持股差異化（✅ 完成，競品持股已接 etfinfo）
- **主動度 Active Share vs 0050 即時真實**（00991A 76%）；偵測器 `ACTIVE_SHARE`/`UNIQUE_HOLDING`/`DIVERGENT_BET`/`LEAD_POSITION`、`arm/diff_engine.py`、`tests/test_diff_engine.py` 9 綠。
- **競品逐日持股已接 etfinfo.tw**：`scripts/fetch_etfinfo.py holdings` 把 6 競品（統一 00981A/00403A、群益 00992A、野村 00980A/00985A、元大 00990A）持股落成 `config/competitor_holdings/{code}.json`（Tier B、標 as-of/source）。實測 00991A：重押國巨 8.9%（同業均 2.5%、偏離 +6.4pt 居同業之冠）、獨門南亞科/台灣晶技、與統一重疊 Jaccard 40%。0050 基準在 `config/benchmark_0050.json`。
- 也可手動覆蓋：自行把競品持股放成同格式檔即生效（drop-in 不改碼）；各投信官網 SPA 的逐家 adapter slot 仍保留供日後直連（見 docs/SPEC.md §18.1）。

### M3 ★ 籌碼推敲（✅ 完成，券商分點 + 法人籌碼雙源 live）
- **券商分點已接 Histock live**（`arm/connectors/brokers/histock.py`）：每日抓本檔 ETF + 前 5 大重倉股的分公司進出（靜態 HTML 表，無需 API/登入），算關鍵分點 / 連續買超天數 / 買超佔成交比；身份經 `config/broker_map.json` 名稱關鍵字推估（外資/投信/中實戶），**一律標「推估・非確認」**（分點僅到分公司）。`SMART_MONEY` 偵測器。實測 00991A：本檔港商野村 +7,899 張、重倉南亞科 台灣摩根 +5,775、國巨 +3,550、台積電 美林 +1,911（皆推估外資）。`config/broker_flows/{code}.json` 可人工覆蓋。
- **法人籌碼已接 etfinfo**：`scripts/fetch_etfinfo.py active` 取主動ETF/投信「估算新進/加碼」→ `config/active_flow/{date}.json`；`arm/chips.institutional_flow`（本檔持股 ∩ 法人買盤）＋ `INSTITUTIONAL_BUY` 偵測器＋想法「聰明錢共識」。實測：重倉國巨被 4 ETF/3 投信新進約 29 億（與復華重押互證）。**法人(集合)層級、非個別買家，標 Tier B 待核對。**
- 測試：`tests/test_chips.py`、`tests/test_histock.py`（分點解析+空白欄對齊回歸）、`tests/test_etfinfo.py`。

> 註：分點買賣超無單一權威 live 源（證交所 `bsr` 逐檔 + 驗證碼、第三方為 SPA/付費，性質同 M2 競品持股）→ 已備統一 `BrokerFlow` 介面 + drop-in 承接層，待第三方 adapter 補實（見 docs/SPEC.md §18.4）。**買家身份只到分公司層級，一律標「推估・非確認」。**

### 下一步（M4 後半 / M6）
M2/M3/M5 引擎、**M4 社群介面＋本機 git** 皆完成。M4 剩**對外動作待授權**：(1) 推私有 repo、(2) 接 live adapter（YouTube/PTT/Dcard/RSS，逐家填 `social.LIVE_ADAPTERS`）、(3) 每日雲端 routine、(4) Claude 逐則 LLM 深析（`analyze(m, llm=...)` 接口已備）。其餘：Claude 文案層（M6）、Next.js 儀表板（M7）、逐期配息金額做完整含息再投入。

---

## 待辦規格：配息產品比較引擎（00998A／00986D 入息優勢雷達）

> **背景**：00998A（全球金融股票入息）與 00986D（全球金融債券入息）**兩檔都主打配息**。光比報酬不夠，要在**全市場所有配息型 ETF**裡找出這兩檔的「**配息比較優勢**」（配息率／頻率／穩定／填息／含息報酬），當成每日行銷彈藥。
>
> **與 M2 不衝突（刻意分開，避免打架）**：M2 比的是「持股內容差異化（獨門股/重疊/主動度）」走 `arm/diff_engine.py`＋`connectors/issuers/`；本引擎比的是「配息維度排名」，**全新獨立模組 `arm/income_peers.py`＋`arm/income_metrics.py`＋ `INCOME_*` 偵測器**，不改 M2 的任何檔案。可排為 M2 之後或平行。

### 它要回答什麼
- 「在 N 檔**海外/全球股票入息** ETF 中，00998A 年化配息率排第 X、含息總報酬排第 Y，把 ○○、○○ 比下去。」
- 「在 N 檔**債券月配** ETF 中，00986D 月月領＋目標息率 6~7%，配息穩定度／填息優於 ○○。」

### 比較對象（peer universe）— 分組才公平
- 發掘規則：名稱含「入息／月配／季配／高股息／收息／債」或有配息頻率者。
- **兩組對標**：
  - 00998A → 海外/全球股票入息 ETF（高股息＋月/季配類）。
  - 00986D → 債券月配 ETF（金融債／非投等債／綜合債）。
- 先放重點競品名單到 `config/income_peers.json`（如高股息 00939/00940/00946…、月配債 00772B/00937B/00933B…，**上線前以官方代碼核實**），再自動擴充。

### 比較維度（Tier A：配息數字一律官方，嚴禁臆測）
1. **年化配息率／近 12 月殖利率**＝近 12 月每單位配息合計 ÷ NAV（最關鍵）。
2. **配息頻率**（月配 > 季配 的行銷力；月月領訴求）。
3. **配息穩定度**（每期金額變異係數、連續配息次數）。
4. **填息表現**（除息後多久填息、填息率）。
5. **配息來源透明度**（收益平準金／本金占比 → 誠實揭露，反向當信任牌）。
6. **NAV 含息總報酬**（公平比較，直接接 M1-4 的 NAV 骨幹／`nav_history`）。
7. 規模／受益人（人氣，已有 TDCC）。
8. 費用率。

### 落地 checklist（之後可直接照做）
- [ ] `config/income_peers.json`：兩組配息型對標名單＋重點競品（官方代碼核實）。
- [ ] `config/distributions.json`：擴充自家＋競品**官方配息紀錄**（沿用既有 schema：`{etf:{ex_date:amount}}`）；先補 00998A/00986D 自家逐期。
- [ ] `arm/income_metrics.py`：殖利率／年化配息率／連配／填息／穩定度（純函式、可測）。
- [ ] `arm/income_peers.py`：配息型同類發掘＋各維度 `rank_of`/`beaten`（**仿 `arm/peers.py` 寫法**，勿動 peers.py）。
- [ ] `arm/signals.py`：新增 `INCOME_YIELD_RANK`、`PAYOUT_FREQ_EDGE`、`DIVIDEND_STREAK`、`FILL_DIVIDEND`、`INCOME_TR_RANK`（**與 M2 detectors 並存、勿改既有**）。
- [ ] `arm/ideas.py`：新增 `g_income_edge` 產生器＋「配息優勢」類別（CAT_WEIGHT 可加重，因兩檔主打配息）。
- [ ] 配息資料源工程：TWSE/TPEx 除權息公告、各投信官網、或第三方彙整（CMoney/MoneyDJ）；競品無 assetsExcel → 用市價做除權息調整的含息報酬。
- [ ] `tests/`：income_metrics（殖利率/連配/填息）、income_peers（分組公平性與排名）。
- [ ] **DoD**：00998A/00986D 每日想法含「在 N 檔配息 ETF 中，配息率／頻率／含息報酬的相對優勢＋被比下去清單」，且**配息數字 100% 官方可追溯**。

## 定位
內部行銷發想輔助工具，非投顧、非投資建議。對外發布前建議經法遵核可。
