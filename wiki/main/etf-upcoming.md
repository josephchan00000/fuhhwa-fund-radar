# 即將登場與新 ETF 自動發現

> 掛牌自動加入追蹤、上櫃檔分組、五狀態三分組、發現層、not_tracked、募集表格解析、併檔通道。
> 原始資料：CLAUDE.md「ETF 數據追蹤」分頁段「『即將登場』→ 掛牌日自動加入追蹤」到「募集表格解析」幾條與「併檔通道把 `not_tracked` 洗掉」；程式：`arm/etfwatch.py`、`arm/etfdiscover.py`、`scripts/check_new_etfs.py`。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

新 ETF 的路徑：CI 發現層找出缺口 → 人工查證登錄（缺口當天補，[步驟 9⑧](../ops/daily-update.md)；每週一 [ETF 募集週掃](../ops/etf-weekly-scan.md) 全面盤點）
→「即將登場」分組展示 → 掛牌當天自動進 [ETF 數據追蹤表](etf-watch.md) → 人工轉正進 WATCHLIST。

### 條目存在 `data/etf_upcoming.json`（2026-08-10 起，勿再寫回程式碼）

- `etfwatch.UPCOMING` 由 `_load_upcoming()` 讀該檔 items（載入器 fail-open 回空、tests 會紅）。搬出程式碼的原因：週掃 Routine 只推**資料檔**就能經 daily.yml 併檔段自動入 main，不需人工 merge 程式碼分支。
- 併檔段防呆：JSON 驗證失敗（壞檔）→ 保留 main 現有版；分支 `as_of` 舊於 main → 不倒灌；分支版缺 `not_tracked` 時沿用 main 的（2026-09-23 起）。
- **改條目＝改 JSON（記得更新頂層 `as_of`＝今日）；改狀態機制／視窗常數才動 etfwatch.py。**

### 掛牌自動加入追蹤（半自動，2026-08-05）

- `etfwatch.watch_tuples()`＝WATCHLIST＋「`UPCOMING` 有 `list_date` 且已到、尚未轉正」的檔自動升級；kind/cat 用條目選填欄，不填＝active／主動式。
  消費端（rows／load stub／fetch_etf_holdings targets）都吃 `watch_tuples()`：掛牌當天 CI 就抓績效＋持股，stub 先上代碼／名稱／頻率。首例＝00410A（8/3 掛牌、8/5 轉正）。
- 債券檔**務必**填 cat 含「債」——`bond_codes()` 靠它放寬髒序列門檻。
- **上櫃檔（櫃買掛牌，如統一 00411A/00987D）kind 照型態填 active／passive、cat 加「・上櫃」**，勿再填 other（2026-08-28 使用者指示分組跟型態走）；etfinfo 未收錄等技術差異自動處理。
- 仍需人工：①UPCOMING 登錄（募集／掛牌公告無統一 API）；②掛牌後「轉正」進 WATCHLIST（查證成立日／頻率、補 SEED_PERF）。
  `tests/test_etfwatch.py::test_upcoming_graduation_guard`：**掛牌逾 14 天未轉正 → 紅**（同 [持股簡介](holdings-intro.md) 的逼補模式）。

### 「即將登場」五狀態三分組

- 狀態＝募集中(now)／即將募集(soon)／掛牌 MM/DD(list)／**募集結束・待掛牌(pend)**／已核准・時程未定(hint)。
- `upcoming()` 回三組：raising（卡片）／listing（卡片）／**approved（hint 第三組，`_upcoming_hint_row()` 精簡列**——常一掛一個多月、資訊只有「核准了」，不佔卡片）。
  hint＝`raise_hint`＋`asof` 查證日，**允許 `code: None`（顯示「代號未定」）**；日期公告後改填 raise_start/list_date 即移入上方分組。
  第四組「已送件・審查中」（2026-08-28 起）＝gap 檔 `pipeline` 自動展示。
- 視窗：已公告掛牌日 45 天（00409A 的 9/2 一公告就看得到）、募集起日、待掛牌、核准待定各 45 天。募集期間優先於掛牌呈現，募集卡帶「預定掛牌 MM/DD」副標。
- **`track: False`＝僅前瞻展示、掛牌後不進追蹤表**：海外被動指數檔 009829 大華銀KOSPI50／009827 玉山算力／009828 中信台日韓PCB——被動組是策展的 6 檔台股大表，勿自動塞入污染。
- 守門 `test_upcoming_stale_entries_guard`：募集結束逾 30 天無掛牌日／核准待定（asof）逾 45 天／掛牌逾 30 天未清理 → 紅（過期自動下架只是遮問題，守門逼收斂才是防呆本體）。
- 維護：每日台股新聞見「新 ETF 核准／開募／掛牌」（尤其本家）→ WebSearch 查證（代號／募集期間／掛牌日／頻率，兩來源一致）補進 `UPCOMING`；
  全面盤點用 **MoneyDJ 新基金頁 `moneydj.com/funddj/fundmarket.djhtm?a=broncho-1`**（2026-08-10 使用者提供；容器擋 moneydj，用 WebSearch 摘要或交給正式區）＋工商時報月度「投信新基金」；
  只有核准沒時程（如安聯加密科技、大華銀非投等債）→ hint 登錄。

### 新 ETF「自動發現」層（`arm/etfdiscover.py`＋`scripts/check_new_etfs.py`）

graduation／stale guard 只認「已登錄」條目，**一檔從沒登錄過的 ETF 對所有測試而言不存在**。CI 每日跑（`daily_fund.sh` 步驟 3.6，`|| true` 不擋發佈），兩層互補：

- **① 市場首見台帳（掛牌層，零版式風險）**：TWSE＋TPEx 官方每日收盤取全市場代碼，篩 ETF 型（`^00\d{2,4}[A-Z]?$`，個股／ETN 02／權證 03-08 開頭不會誤入），
  記入 **`data/etf_seen.json`（必須入庫，`.gitignore` 已加例外）** 的「首見日」；首見日在近 `DISCOVER_DAYS`=60 天內又不在 WATCHLIST+UPCOMING → 缺口。
  抓到時已掛牌——**下限保證：沒有任何一檔新 ETF 會完全從雷達上消失**。台帳空時一次認列既有（`first: None`）、不報警，且只在市場檔數 ≥`MIN_MARKET_FOR_BASELINE`=100 時才建。
- **② 募集頁前瞻層（皆 fail-open）**：`頁面內容 − 已掛牌 − 已登錄 = 真正的新募集候選`，既有 ETF 的參照連結自動濾掉、版式漂移也不誤報；解析失敗回空＋印 CI 日誌（grep `[新 ETF 發現]`），只損失前瞻性。
  - **鉅亨 IPO 頁 `fund.cnyes.com/IPO/index.htm`**（2026-08-10 使用者提供；cnyes 對 CI 可達已由 cnyesfund 連接器天天證實，最可靠）＝名稱層：列「基金名稱＋募集期間」無代碼，`_norm_name()` 正規化比對
    （去括注／主動式／ETF／基金等詞；<4 字泛稱不比），**未派碼的新檔也逮得住**；既有 ETF 廣告連結由「台帳名稱」濾掉。
  - **MoneyDJ 新基金頁**也走名稱層（代碼掃描 `00\d{2,4}[A-Z]?` 留作「日後頁面補上代碼」的加分項，抓 0 不算異常）。
  - 名稱比對用**子序列**、不用子字串；名稱 regex 允許數字/英文起頭，另要求 ≥3 個中文字擋 `iShares ETF` 泛稱。同一檔可能被兩層各報一筆（無代碼對不上名稱），週掃補登後一起消失，可接受。
- **募集表格解析（`parse_offering_table`／`stage_of`）**：鉅亨 IPO 頁是純 HTML 表格 `基金名稱｜基金類別｜經理人｜申請日｜核淮日期｜募集期間｜申請額度`
  （「核淮」是頁面錯字，兩種寫法都收；欄位以**表頭文字定位**）。缺口從「只有名字」變「可直接查證」：①`stage_of()`＝raising（募集期間已定）／approved（核淮日期已下）／
  **applied（申請中）**，判準＝核淮日期欄**含日期樣式且不含審查／申請中等狀態字**；②募集期間就是要的資料，週掃只需找第二來源；③基金類別是權威 ETF 判準。
  解析 0 列＝退回純名稱層、缺口照報並印探針片段。

### 缺口檔、警示章與 `not_tracked`

- 缺口寫 **`data/etf_upcoming_gap.json`（入庫）** → 「網頁更新時間」列警示章（`_new_etf_chip()`）→ 步驟 9⑧ 處置（同「前十大持股簡介」的逼補迴路）。
- 警示三級：🔴 紅＝`kind=listed` 已掛牌真漏網（附代碼，每日立即補）；⚠ 琥珀＝已核准／募集中待登錄（只給檔數，清單在 gap 檔）；
  申請中（stage=applied）在 `save_gap()` 就分流進 **`pipeline` 欄**——不進 count、不上章（第四組照樣展示），核准後下輪升入 items。
- **`load_gap()` 讀取端再濾一次已登錄代碼**：gap 檔是 CI 快照，否則補登後紅章掛到下一輪（補的人以為沒生效）；現在**下一次重建即滅章**，`count` 一併重算。未派碼條目（`code: None`）保留。
- 容器擋 twse/tpex/moneydj/cnyes → 本地跑一律 ⚪「未檢查」屬正常。
- **`not_tracked`＝「已掛牌、看到了、刻意不追蹤」**：`data/etf_upcoming.json` 頂層鍵（併檔通道只驗 `items`，新頂層鍵原封帶過）；欄位 `{code, name, issuer, list_date, why, asof}`，
  **`why` 必填**（「把判斷記下來」而不是「把警示關掉」，tests 有守）。`etfwatch.NOT_TRACKED`（`_load_not_tracked()`，壞檔 fail-open 回 `[]`＝重新被警示，寧可多警示）
  → `etfdiscover.known_codes()`／`known_names()` 都吃。只給「已確認掛牌、且我們決定不納入追蹤表」的檔（目前＝海外被動指數檔）。

## 不能改的規則

- **14 天寬限是「逾期才紅」，不是「可以拖 14 天」**：`test_seed_file_loads_and_covers_watchlist` 與 `test_fetch_falls_back_to_seed_...` **掛牌當天就紅**
  （`Extra items: '00409A'`——watch_tuples 自動升級進表、WATCHLIST/SEED_PERF 卻沒有它）。**pytest 見這兩支紅＝當天就要轉正**，本家檔尤然（「本家復華新檔最優先、絕不可漏」）；graduation guard 的 14 天是最後防線、不是排程。
- **本家復華新檔一律不得列 `not_tracked`**（要轉正進 WATCHLIST）。
- **申請中 ≠ 已核准**；**「核淮日期欄非空」≠ 已核准**。
- 發現層來源不可達時 gap 檔**「不覆寫」也「不新建」**。
- 警示章維持三級、琥珀只給檔數（使用者嫌紅章長名稱「很躁」，勿走回頭路）。
- 結構探針印上下文片段，不印次數或鍵名。

## 踩過的坑

- **募集結束沒掛牌日的檔直接消失（2026-08-10 前）**：統一雙檔 8/7 募完當天就從版上不見，研討會投影片抓包「不齊全」主因之一 → 加 pend，續留最長 45 天。
- **從沒登錄過的檔沒有測試會紅（2026-08-10）**：08-10 那 4 檔靠使用者的研討會投影片才發現（使用者：「你是怎麼確保之後都抓得到的呢？」）→ 自動發現層。
- **baseline 三坑**：①台帳空時不一次認列，第一輪噴出市場 200+ 檔；②首建那輪單邊交易所掛掉（2026-08-05 tpex openapi 曾整輪失敗），baseline 只含半個市場、隔天另一半被誤判新掛牌
  → `MIN_MARKET_FOR_BASELINE`；③**來源不可達時覆寫或新建 gap 檔**（08-10 實跑抓到）：覆寫把真缺口洗成 0、新建把「沒檢查」寫成「0 缺口 🟢」commit 進去——反覆踩的靜默失敗。
- **CI 首輪（2026-08-10 run 31351244025，三項修正已入庫，勿走回頭路）**：baseline 353 檔（twse 236＋tpex 117）、掛牌層 0 缺口符合預期；
  - **MoneyDJ 對 CI 其實可達**（54,564 bytes、非 WAF 空殼），但掃出 0 個代碼——新基金募集頁只列名稱與募集期間、新檔多半未派碼 → 改走名稱層；
  - **子字串比對誤報**：`富邦科技`(0052) vs `富邦台灣科技指數`、`永豐科技趨勢`(00410A) vs `永豐台灣科技趨勢` 判成兩檔；改子序列後 17→13 筆，
    四筆濾除全對（另兩筆＝009826 貝萊德世界股票、00991B 貝萊德A級公司債，早已在台帳）；
  - **名稱 regex 限 CJK 起頭**：`10年期AAA至A級…` 的「10」被切掉 → 對不上清單而誤報；
  - **探針借錯函式**：`cnyesfund._objects_from_html()` 錨定 `"cnyesId"`，IPO 頁沒這個鍵 → 一行都沒印；改印「首筆名稱周邊 ±220 字原文片段」
    （同 2026-07-29 元大那輪：印次數／鍵名無法決斷結構，印上下文片段才能一輪定位），一輪就收斂出表格解析。
- **把申請中當已核准（2026-08-10）**：中信台灣聚焦成長只有申請日、無核淮日期，沒有 applied 會被當「已核准待募」上板；同日 CI 第二輪：核淮日期欄會填狀態字——
  `115.9.14申報生效` 才是真核准、`審查中` 是還沒過，只看非空會把聯博兩檔與**本家復華台美策略**誤標成已核准。
- **紅章太躁（2026-08-10）**：紅章列 13 檔長名稱 → 三級、琥珀只給檔數、申請中進 `pipeline`。
- **14 天寬限被當成可以拖（2026-09-03）**：00409A 掛牌當天兩支 pytest 就紅；判斷「pytest 紅但不擋當日新聞推送」是對的，錯在只在推播附註一句就放著，
  隔天使用者問「ETF 淨值是不是沒更新到」——本家新檔已掛「底稿」標籤、配息頻率空白一整天。
- **stale guard 與發現層互相矛盾（2026-09-21，009829）**：stale guard 要求「掛牌逾 30 天的條目清出 UPCOMING」（對的），但離開 UPCOMING 後 `known_codes()` 不認得，
  每天判成 🔴「已掛牌未登錄」。009829 大華銀韓國KOSPI50（`track:false`）09-20 週掃依規清理後，隔天起天天誤報——紅章＋**4 個 pytest 連紅**
  （`known_codes`／seminar／upcoming_view／freshness_view）。兩邊都沒錯，缺第三種狀態 → `not_tracked`。
- **併檔通道把 `not_tracked` 洗掉（2026-09-23）**：09-21 週掃在排程會話的舊分支（分岔自 not_tracked 上線前）改 `data/etf_upcoming.json`，as_of 與 main 同為 09-21，
  併檔段只擋「較舊」→ 整份覆蓋，009829 又被判漏網、3 個 pytest 紅 → 分支版缺 `not_tracked` 時沿用 main 的；根治仍是排程搬家（[排程](../ops/routines.md)）。

## 歷史

- 2026-08-05 掛牌自動加入追蹤（使用者需求）。
- 2026-08-10 使用者兩輪指示（研討會投影片抓包資料不齊全＋「太長記得分類一下，尤其是只有核准還沒確定募集時間的」）→ 五狀態三分組、掛牌日視窗 14 天放寬到 45 天、
  條目搬到 JSON；同日建自動發現層、警示三級、募集表格解析。
- 2026-08-28 上櫃檔分組跟型態走、第四組「已送件・審查中」；2026-09-21 `not_tracked`、`load_gap()` 再濾；2026-09-23 併檔段沿用 main 的 `not_tracked`。
