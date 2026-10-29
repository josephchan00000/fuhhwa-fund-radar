# 列印版／存 PDF

> 獨立列印樹、五組重點、分頁規則、驗證方法、踩過的坑。
>
> 這一頁目前是從 CLAUDE.md 逐字搬來的（知識庫第一段），還沒整理；有出入時以 CLAUDE.md 為準。
> 改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產這一頁。

<!-- CLAUDE.md 第 835–893 行 -->
## 列印版／存 PDF（2026-09-07 使用者需求：「每天早上可以列印出來的版本」）

**歷史**：2026-07-20 第一版「晨會列印版」（把螢幕區塊套 `@media print` 硬印）使用者看過後指示
「格式醜、整個功能刪掉」，`tests/test_guards.py` 曾鎖「整組不得回來」；2026-09-07 使用者重新提出明確
需求（可列印／存 PDF、排版乾淨不可切頁、字小無妨、只要五組重點、基金 ETF 報酬率單獨一頁），改以
**獨立列印樹**重做，守門測試改鎖「舊作法不回歸、新版必須是獨立樹」。使用者若再嫌版面，先調 `printview.CSS`
的 `.pr-*` 規則，不要退回「硬印螢幕區塊」那條路。

頂欄「🖨 列印／PDF」＝ `window.print()`，瀏覽器對話框選「儲存為 PDF」即輸出（桌機／Android Chrome／
iOS Safari 皆同一條路，零外掛；CJK 字型交給瀏覽器）；「預覽」把同一份版面以 A4 寬顯示在螢幕
（`body.pv`，`#print` hash 也能直開；Esc／「返回網頁版」關閉）。模組＝ `arm/printview.py`
（`fund_dashboard.render()` 函式內匯入——printview 依賴本模組小工具，頂層互相 import 會成環）。

- **為什麼是獨立的 `#print` 樹、不是把螢幕版套 `@media print`**：螢幕版是四分頁 radio
  切換（display:none）＋新聞卡 `<details>` 收合＋橫捲表格，直接列印只會印出「當下那一段」（實測
  原頁面 print 只有 2 頁、多半空白）。列印樹只放使用者要的**五組重點**，資料全沿用 render() 已載入
  的物件、零新增抓取；螢幕上 `#print{display:none}`，`@media print` 用 `body>*:not(#print){display:none}`
  一刀藏掉其餘（含動態插入的 `.stale-banner`），所以 **`#print` 必須是 body 直屬子節點**。
- **版面（A4 直式、邊界 8–10mm、字 7–8.5pt；使用者：「字很小只要清楚就好」）**：第 1 頁 ①本週行事曆
  ＋②市場數據追蹤（＝市場溫度計三表；法人分項子列一併印出）；第 2 頁起 ③盤勢總覽（總經／台股／全球
  三欄並排）＋④重要度 8 分以上新聞（三份報告合併、依分數排、同分依總經→台股→美股、【深度】殿後；
  **每報至少 1 則**——該報當天沒有 8 分卡時補其最高分事件卡並標灰章「本報最高 N 分」，使用者同日
  指示：「放寬到 8 分以上…記得總經台股全球的都要涵蓋進去」；門檻 `MIN_SEV`／保底數 `LANE_MIN`
  兩個常數，`LANE_MIN=0` 即關閉保底）；最後一頁 ⑤基金・ETF 報酬率 **獨立一頁**
  （`break-before:page`），基金（左）／ETF（右）並排，字級依單側列數 `fit_pt()` 自動收斂
  （≤48 列 7.5pt、下限 5.5pt）——使用者：「這個單獨全部擠在一頁」。ETF 表主動式檔去「主動」前綴、
  「復華」金色、上櫃標「櫃」；當日漲跌沿用 `_chg_cell` 的序列落後防呆（印 —⚠ 不冒充）。
- **「同一資訊不可切到兩頁」的實作**＝ `break-inside:avoid`（每個 `.pr-sec` 區塊、每張 `.pr-card`）
  ＋只在 ⑤ 前強制分頁；④ 整段是 `.pr-flow`（卡與卡之間可換頁、標題 `break-after:avoid` 跟第一張卡走）。
  區塊塞不進本頁餘白就整塊順延，不靠固定高度。**3～4 頁是常態**（8 分卡 5～8 張時 ④ 約佔一頁）。
- **不放的東西**：只用網頁現有資訊（使用者原話）——費半／台積電 ADR 序列雖在 `macro_chips.json`
  但溫度計表沒列，列印版也不列；新聞卡只印 8 分以上（6–7 分見網頁版，每報保底補入者除外）；
  持股、社群、ETF 詳情不印。
- **驗證＝真的印**：`TZ=Asia/Taipei python3 scripts/check_print_layout.py dashboard/index.html --png DIR`
  （需 `pip install playwright pymupdf`；本容器瀏覽器 `/opt/pw-browsers/chromium-*/chrome-linux/chrome`）
  ——headless Chromium 印 A4 PDF、印前在每區塊／卡片首尾塞 2pt 白字標記 `@@BEG/END:id@@`，PyMuPDF 讀回
  比對「首尾同頁」「⑤ 獨占一頁」「① 從第 1 頁起」，`--png` 逐頁出圖可用 Read 看版面。
  `daily.yml` 煙測之後掛同一支（**只告警不擋**，infra 故障 exit 2 也不擋）。pytest `tests/test_print_layout.py`
  守結構：五 id 齊、報酬率頁涵蓋全部基金與 ETF、8 分門檻與每報保底、CSS 分頁規則、不與螢幕版 class 撞名。
- **踩過的坑**：①**零高度標記會被排到前一頁**——首版 BEG 標記是 `height:0` 的 block，⑤ 明明從新頁開始、
  標記卻落在前頁餘白（誤判切頁）；標記要塞進可見標題列內的 inline 字。②**全域無前綴 class 會漏進列印樹**：
  `.sub{font-size:12.5px}` 把法人子列字放大、`.nwatch{font-size:14.5px}` 把「後續觀察」放大、`.tag`／`.klabel`
  同型——列印樹一律 `pr-` 前綴，並在 `.pr` 下逐一壓回（test 有守禁用 class 集合）。③**手機藏文字別寫
  `.tb-print span`**——圖標外層也是 `<span class="ic">`，會連圖標一起藏、按鈕剩一顆空底色；文字獨立
  class `.tb-pl`。④新聞卡標籤欄用 `grid-template-columns:auto 1fr`——固定 5.6em 會讓「對市場情緒與股價影響」
  9 字標籤壓到內文。
  ⑤**③ 全球欄空了三週（2026-10-13 使用者：「印出來的昨夜美股總覽那欄都是空的」）**——
  版型只寫「🔹段名」沒寫 `##`，美股子代理 09-19 起寫成 `🔹**…總覽**` 粗體行，`_extract_overview`
  只認 `##` 標題 → **螢幕版「昨夜美股總覽」卡、列印版 ③ 全球欄、`check_reports` 速覽文風閘門三處同時
  靜默落空**（台股 8 月也有 22 天 `### 🔹盤前速覽`／`🔹**盤前速覽**` 同型讓速覽卡消失）。修法三層：
  ①**單一解析器 `usnews.find_section()`／`section_label()`**（## ／### 標題、整行粗體、🔹 起頭短行皆認，
  止於標題／`---`／`────`／下一個 🔹 段名；儀表板、列印版、check_reports 共用，段名 key 也集中在
  `usnews.OVERVIEW_KEY／PREMKT_KEY`）——歷史美股報 25 份空白全數復原、原本抽得到的 255 份（美股／總經／台股）輸出零變動；
  ②**版型源頭**：三支產生器段名行改成明寫 `## 🔹段名`＋`LABEL_RULE` 補一句；台股盤後版段名由
  「指數速覽」改「盤後速覽」（儀表板刻意不把指數速覽當速覽卡，照版型寫反而落空）；
  ③**閘門 `check_reports._check_head_sections`**：抽不到或內文空 → 🔴。另：③ 全球欄頭加印
  實際對應的美股交易日（`printview.us_trade_note`，週一那份是上週五）。**生效條件**：解析器＋閘門＝
  merge 進 main（CI 用 main 的程式建表）；版型＝merge 後再「排程搬家」。

