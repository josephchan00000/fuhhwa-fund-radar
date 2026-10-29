# ETF 持股資料

> ETF 持股從哪抓、挑主來源與驗證、非持股列、落檔與合併、個股報價日與貢獻、期貨部位；放棄的路線與探針經過。
> 原始資料：CLAUDE.md「ETF 詳情」底部區塊段的持股資料各條；規劃 `docs/etf_chg_fix_plan.md`；程式：`arm/etfholdings.py`、`scripts/fetch_etf_holdings.py`、`arm/connectors/issuers/pcf.py`。
> 最後更新：2026-10-29
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

畫面在 [ETF 詳情卡畫面](etf-detail.md)。

## 現在怎麼運作

### 抓取＝彙整站雙源（2026-07-30 最終定案，使用者指示「不必抓官網第一手，彙整站＋雙重驗證」）

`scripts/fetch_etf_holdings.py`＋獨立 workflow `.github/workflows/etf_holdings.yml`（台北週一~五 17:40；純 HTTP、每輪數十秒）。
- **主來源 etfinfo.tw**（Tier B）：`GET /api/etf/{code}` 的 holdings 欄位＝**完整每日快照**（stock_id/weight/shares＋snapshotDate），既有連接器 `arm/connectors/etfinfo.py` 的 `holdings_fresh()` 早已封裝；
  CI 每天抓規模／殖利率就在打同一 API，可達性已被證實數週。
- **副來源 Yahoo 股市持股頁**（Tier B）：`tw.stock.yahoo.com/quote/{code}.TW/holding` SSR 內嵌 JSON（`parse_embedded_json`；代號帶 .TW/.TWO 字尾已在 `_row_from_mapping` 去尾）。
  **MoneyDJ 已試過並移除**（2026-07-29 實測：basic0007 頁 table×0、SSR 表格已不存在）。
- **本家三檔（00991A/00998A/00986D）走復華官網 assetsExcel（Tier A 第一手）**：`config/products.json` 對映 `fund_id`（ETF23/24/25），舊管線 `arm/pipeline.py` 本就以此抓三檔（含前後快照 diff、**排除期貨避險列**——沿用此慣例）。
  順序＝fhtrust → etfinfo（同為每日 PCF 基準，**且兩源快照日相同時**做真正的權重驗證「🟢 雙源相符」，否則只驗構成）→ Yahoo。外股 ticker（'C US'）與債券（面額）原生支援；
  海外持股「個股當日漲跌/貢獻」原本因無台股報價顯示 —（誠實降級；2026-10-21 起改用 Yahoo 已收盤價）。
- **已排進每日循環（2026-07-30 使用者指示）**：本 job 抓持股後**直接重建儀表板＋commit＋打 Deploy Hook**——當日貢獻當晚上線，不等隔日早上；早上 daily.yml 重建時亦自然帶入 main 上最新持股檔。
  **為何獨立 workflow**：不佔 `daily.yml`「07:03 前線上可看」的關鍵路徑；失敗不影響任何現有功能。儀表板「網頁更新時間」有「ETF 持股揭露」鮮度列（停更逾 3 天列入紅色逾期警示＝該 workflow 掛了）。
- **`etf_holdings.yml` 有 `probe` 輸入開關**：只跑探針、跳過重建／commit／部署，且**探針模式 checkout 被 dispatch 的分支**（正式抓取仍固定 main）——曾踩：workflow 檔取自分支、程式碼卻取自 main，探針跑的是舊腳本、日誌零輸出。

### 挑主來源與驗證

- **主來源＝快照日最新者，不再硬性「第一手優先」（2026-07-30 使用者：「不能用 etfinfo 頂著嗎」）**：復華 assetsExcel 可能連日回同一份舊檔，硬性優先會讓 00991A 天天顯示假的「無異動」。
  ①各來源用**自己的快照日**（etfinfo＝官方 `snapshotDate`；fhtrust＝檔案自報日）；②**fhtrust 的日期只有「檔案自報」時才拿來比大小**，沿用請求日的視為未知、排在 etfinfo 之後；
  ③同一天時仍讓第一手 fhtrust 勝（可與 etfinfo 做真正的權重驗證）；④Yahoo 無快照日、永遠墊底；⑤**換源必須換到更新的快照**（`fetch_etf_holdings._prefer_incumbent`）：贏家不是既有來源、
  既有來源這次也抓得到、且**快照日沒有比既有揭露日更新** → 維持既有來源，真有更新的快照時照換（00991A 靠 etfinfo 頂著的情境不受影響）。
  曾踩：`fresh[code]["date"]` 對 fhtrust 來源直接寫 `fallback_date`（最近交易日），完全沒用到檔案日期——這是 00991A 被標成當日的直接原因。
- **雙重驗證 `etfholdings.cross_check(weights=False)` ＝「構成驗證」**：Yahoo 持股是**月度基準前十大**、etfinfo 是每日 PCF 快照——**跨基準日比權重是方法錯誤**（實測 19/21 檔被誤判 mismatch，
  權重差 1.2–4.2pp 全是時點差）。只驗前十大構成重合 ≥60% → 🟢「構成相符」；重合過低 → **weak「副源過舊・未能驗證」灰章**（多為月內調倉，**不是**主來源錯誤的證據，如 00929 月內大調倉重合僅 3/10）；
  僅一源 → single。紅 ⚠ mismatch 保留給未來同基準日源的真衝突。**不比股數**——兩站口徑常不同，比了誤殺。驗證結果存 entry `verify` 隨 detail 入板。
- **假陽性防呆 `is_plausible()`（務必守住，新增 adapter 後務必確認仍過這關）**：①檔數 ≥10；②**過半列須帶權重或股數**（沒有數量就算不出貢獻）；③不可整份都是 0 開頭的 ETF 代碼（只排除「全部」，才不會誤殺真的持有其他 ETF 的組合）。
  **債券 ETF 例外（2026-10-21）**：①的 10 檔是為通用網頁解析設的；etfinfo 是結構化 API、債券 ETF 可以只有幾檔——`_from_etfinfo` 對追蹤清單分類含「債」的檔改 1 檔門檻（`_MIN_BOND_HOLDINGS`），②③照舊；
  日誌（擋下或少於 10 檔收下時）印樣本列，CI 一輪就看得到收進來的是什麼。

### 哪些列不算持股、怎麼存

- **列宇宙對齊 `etfholdings.drop_non_holdings()`**：現金／保證金／應付款／期貨等非持股列一律不進 diff（fhtrust 本來就不給、etfinfo 的 PCF 快照會給），抓取端三個來源共用。判準＝代號 `^(M|DA|PFUR|…)_[A-Z]{3}$`／
  期貨合約 `^20\d{4}[A-Z]{2,3}$`（年月＋商品碼；`etfholdings._NH_FUT2` 另認 `UB:2026-12:B` 與商品碼在前的 `US202612`）／名稱含 MARGIN·PAYABLE·AFTER DEDUCTING·現金·應付…。
  **別誤殺帶交易所碼的外股**（`TLTW US` 有空格、不符期貨式樣）。
- 落檔 `data/etf_holdings.json`（**必須入庫**，`.gitignore` 已加 `!` 例外）：`prev` 存前一揭露日股數／權重（一併存 `name`），**沒有它就沒有「今日 vs 昨日」可比、Δ 整片是 —**（同 etf_watch／fund_nav_history 的坑）。
- **合併鐵則 `etfholdings.merge_one()`**：本次抓不到＝原封保留；**同一揭露日重抓不可把 prev 洗成今天自己**（否則 Δ 全變 0、看起來像「都沒異動」）；揭露日推進時才把舊 holdings 降級為 prev，並記 `prev_src`；
  新舊 holdings 的**股數＋權重全等** →「同一份快照」，當同一次揭露重抓，**不推進日期、不動 prev**（寧可少報一天鮮度，也不假造零異動日）。
  `_drop_fake_prev()`：既有落檔的 prev 與今日 holdings 全等 → 就地清掉，誠實顯示「尚無可對比的前一揭露日」。
- **來源切換時不判定新增／出清**（`contributions` 的 `xsrc`）：`prev_src != src` 時只比共同持股的加減碼，detail 標 `xsrc=[舊源, 新源]`，儀表板異動表底下（`mvfoot`）寫明「僅比對共同持股」。
  **這是最後一道防線**——真出清與「對方沒揭露」本來就分不出來，寧可少報也不假造。
- **`etfholdings.view()` 有補算 fallback**：落檔 detail 缺 `all`（舊 schema／CI 當次沿用舊值）時就地以 `holdings`／`prev` 補算「完整持股＋異動」——這兩者是純比較、不需網路，只有收盤價與當日漲跌非連網不可；
  補算後把舊 detail 已有的報價／貢獻依代號嫁接回來（不憑空補價、也不讓詳情區空著）。

### 個股報價日與貢獻（2026-10-21）

- **貢獻在 CI 端算好存進落檔的 `detail`**（`etfholdings.annotate`，個股報價 ← `arm/dayquotes.latest`＋`yahooq.fetch_foreign_on`）——容器內 proxy 擋 twse/tpex，建表時取不到報價；儀表板端 `etfholdings.view()` 只讀 `detail` 純渲染。
- **使用者決定**：漲跌一律用**最新交易日 T**（搭配各 ETF 最新揭露的持股；快照日≠T 時網頁兩個日期都標＋「不同日」章）；**海外只用已收盤的價格**，當地還沒收盤標「待收盤」，下一班自動補上。
- `arm/dayquotes.latest()`：決定 T（官方休市表、交易日 14:00 後才試今天），**上市、上櫃都要取到 T**（openapi 日期剛好是 T 就用；不是就抓 MI_INDEX／櫃買 dailyQuotes 指定日期版，
  正負號在「漲跌(+/-)」欄的 HTML 裡、X＝不比價；櫃買回應日≠T 不收），自我檢查「收盤 − 漲跌 ＝ 前一交易日官方收盤（籌碼雷達分片）」≥80% 才採用，拿不到換前一交易日——**絕不各取各的**。
- `yahooq.close_on()`：日線依 `gmtoffset` 換當地日期、`currentTradingPeriod` 正在交易的那天不收、那根收盤是空值改用 `regularMarketPrice`（最後成交時戳要落在當地那一天；
  歐股 10/20 那根到台北隔天中午都還是空值、時段資訊已換到 10/21——CI 探針實測）、前收只認緊鄰前一根。
- `detail.pd`＝報價日、每列 `qd`／`pend`；這班缺的列只沿用上一班**同一報價日**的值（`annotate(prior_doc=…)`——`merge_one` 拿到新揭露時回的新 entry 不帶舊 detail，上一班報價只在合併前那版找得到）。
  `_eh_payload` 只放 qd＝pd 的數字，舊格式（沒有 pd）顯示「漲跌更新中」。籌碼雷達 pos 分片的「揭露當下收盤」（`collect.snaps_from_holdings`，估海外成本用）也只收 pd＝揭露日的明細——快照較舊時收盤是別天的。
- CI 日誌每班一行「台股報價日 T：上市 來源 N 檔・自檢 x/y｜上櫃 …」＋「海外報價（Yahoo，當地 T 已收盤）✓…｜待收盤…」。
- **驗證**：探針模式（`probe=true`）跑 `_probe_quotes()`——印 T 與自檢、**對前一交易日再抓一次指定日期版**（早上 openapi 已是 T、正式流程走不到 MI_INDEX，探針要保證那條路也驗得到）、
  幾檔海外的末三根日線與正規時段。上線後用籌碼雷達官方分片逐列核對新落檔（docs 第 1 節方法）。

### 期貨部位（2026-10-21 使用者問「為什麼不算？」後同意另列）

- 期貨照舊**不進**持股 diff、權重合計、方塊圖、貢獻度：①換月（代號一季一換，用代號比會變成假出清＋假新增）、②權重是名目曝險（只付保證金；00987D 兩檔公債 87.41%＋期貨 36.55%＝約 124%）、③口數和股數／面額不能比。
  但 00987D「主動統一美國公債量化增益」看多時用期貨把美債曝險拉到 120%～130%、看空時用期貨對沖——**期貨口數就是策略本體**，丟掉它持股詳情只剩兩檔一直抱著的公債。
- 落檔 entry 另帶 `fut`／`prev_fut`（`{id, name, qty(空單為負), weight(名目%), amt}`；揭露日推進時 fut 降級成 prev_fut，規則同 prev；`None`＝主來源沒揭露期貨（Yahoo），`[]`＝有揭露、沒期貨）。
  抓取端 `etfholdings.split_futures()`（etfinfo 列帶 `kind="future"`＝API 的 `assetType`，比代號可靠）、fhtrust 的期貨區段（`kind=="future"`，舊管線就有）另存，**持股列與上線前完全相同**（tests 守）。
- `etfholdings.fut_view()`：依商品代號合併（`fut_key`：`UB:2026-12:B`／`US202612`／`202609TY`／彭博式 `TYZ6` 都認），比前一揭露日加減口數；**月份換了＝轉倉**，不算平倉＋新建；空單權重一律記負；
  跨來源只比兩邊都有的商品（同 xsrc 規則）。名稱去掉「202612 」月份前綴（00986D 的寫法）。
- 網頁：詳情卡「持股異動」與「完整持股明細」之間的「期貨部位」表（合約｜口數｜名目曝險｜比上次），上方一行「持股 87.4% ＋ 期貨名目 36.55% ＝ 合計約淨值的 124%」（持股合計 <60% 的檔不寫合計）；
  卡片標題列「・期貨 +10 口／期貨轉倉」；持股沒動但期貨有動時，異動區的空白訊息會指過去。上線第一天沒有前一揭露日的期貨資料（舊落檔沒有 fut），區塊寫「下一個揭露日起可看加減口數」。
- 只有兩檔有期貨（2026-10-21 探針，38 檔全掃）：00987D `UB:2026-12:B` 87 口 36.55%、00986D `US202612` 65 口 11.18%（fhtrust 與 etfinfo 一致，金額 2.24 億元＝名目）。

### 放棄的路線（勿走回頭路）

- **投信官網第一手（逐家逆向 7 輪＋無頭瀏覽器 3 輪）**：官網幾乎全是 SPA、持股靠 XHR，群益還在 Incapsula 防護後面；瀏覽器雖過得了 WAF，但復華等站頁面只 render 前十大、拿不到完整清單。
  `fetch_etf_holdings_browser.py` 保留為備援、不排程（其「攔截 XHR＋DOM 解析＋列表頁自尋」機制若日後需要可直接復用）。
- **純 HTTP 路線（`arm/connectors/issuers/pcf.py`）保留為解析層與備援**：沒有跨投信統一官方端點（2026-07-29 查證：證交所／櫃買／政府開放平台皆無彙總 API，各投信自行在官網揭露）→「**候選 URL＋通用解析＋探針**」：
  每檔依序試候選來源，通用解析吃 JSON／HTML 表格／xlsx（重用 `fhtrust._parse_xlsx`），抓不到就印 HTTP 狀態／content-type／內容前段。**收斂方式：跑 `scripts/fetch_etf_holdings.py --probe` 於 CI，
  讀日誌逐家證實後改 `_cands()`**（同 cnyesfund.py 當初 6 輪 CI 收斂的做法）。已知可用型態：元大 `www.yuantaetfs.com/tradeInfo/pcf/{code}`。抓不到的檔安靜降級（該 ETF 就沒有展開明細），不影響其餘欄位與其他 ETF。
- **第三方交叉驗證＝純 HTTP 已證實不可行（2026-07-30 兩輪 CI 探針，使用者核可三站後實測、決定收在這裡）**：**玩股網** `www.wantgoo.com/stock/etf/{code}/constituent` 兩個 URL 皆 **403**
  （WAF 擋機房 IP；它的資料基準最理想：官方說明寫含「櫃買中心公開揭露之申購買回清單」、每交易日更新，也是唯一涵蓋上櫃的候選）；**CMoney** `www.cmoney.tw/etf/tw/{code}/fundholding` HTTP 200、259KB，
  但持股全在 XHR 後面（HTML 內「成分股」只出現在 meta 文案；bundle 改成 HEAD 問大小、由大到小深掃主檔後**仍找不到任何持股相關端點**）；**ETF觀測站** `fundclear.com.tw`（集保）是**基金**觀測站，
  bundle 撈出的 API 全是 `/api/performance/*`、`/api/offshore/*`，不做 ETF 持股。**要再撿起來只有瀏覽器路線**（玩股網若是擋 UA／無頭特徵則有機會，若是擋 IP 信譽則一樣不通）。
  探針保留（`pcf.third_party_cands()`／`probe_third_party()`，只在 `--probe` 模式跑）。**決策背景**：第三方源的價值在「假無異動」修好後已從「補涵蓋」降為「多一個驗證章」——00998A／00986D 本來就有真實 Δ。
  現行驗證維持「etfinfo 主＋Yahoo 驗構成」；本家三檔第一手 fhtrust。

## 踩過的坑

- **持股明細的漲跌拿錯天（2026-10-21 使用者：「ETF持股異動那邊，漲跌幅是錯的欸」；盤查與規劃 `docs/etf_chg_fix_plan.md`）**：漲跌數字本身沒算錯（報價日對上時 257 檔全與官方一致），錯在**拿錯天**。
  舊碼一律抓 openapi 全市場表「當下那份」、不看日期：①**證交所 openapi 要到隔天清晨才更新（凌晨 3:21 還是舊的、8:02 已更新），櫃買當晚就更新**——19:00、22:30、凌晨那幾班同一張表上市＝前一天、上櫃＝當天
  （10/20 晚上 00981A 欣興顯示 10/19 的 +2.75%，10/20 實際 −5.80%）；②持股快照較舊的 ETF 配到別天的漲跌、毫無標示（00987A 快照 10/15〔加權 −3.41%〕顯示 10/16 的漲跌，合計貢獻 +1.96pp vs 正確約 −6.5pp）；
  ③海外 Yahoo 取「最後兩個非空收盤」：22:30 以後收到美股盤中價，台北早上美股剛收盤那根收盤是**空值**被跳過 → 拿到前兩個交易日的漲跌。83 版落檔 39% 的台股列錯日——run 全綠、check 全過，
  又是「兩個來源並排卻沒問是不是同一天」的同型坑（見 [ETF 當日漲跌的坑](etf-daily-change.md)「當日漲跌與收盤價差一天並排」；主頁 ETF 表本身有 chg_trust 防呆、不受影響）。修＝上面報價日一節。
- **假的「本次無異動」（2026-07-30 使用者發現 00991A）**：`fhtrust.fetch_holdings` 原本把**我們請求的日期**當資料日回傳（`"date": iso_date`），但 assetsExcel 端點對不同 ymd 可能回同一份檔案 →
  揭露日往前跳、內容一模一樣，`merge_one` 把舊快照降級成 prev，Δ 全變 0，看板顯示「持股股數沒有變化」。**識別法：權重也全等**（權重是市值比重，兩個不同交易日不可能 49 檔全部到小數第三位都相同）。
  三道修法：① `fhtrust._meta_date()` 從 xlsx 單格 meta 掃**檔案自報的資料日**（西元／民國都收），以它為 `date`；掃不到才回退請求日，並在 CI 日誌標「⚠ 檔案未見日期、沿用請求日」；
  ②「同一份快照」防呆；③ `_drop_fake_prev()`。**etfinfo 來源不受影響**（snapshotDate 是官方欄位，實測 21 檔權重都有變動）。
- **跨來源 diff 的假「全部出清」（2026-08-05 使用者發現 00986D：「全部出清？加碼的也出清？」）**：`prev` 與 `holdings` **出自不同來源時「揭露範圍的差異」會被整批算成新增／出清**。
  實況：00986D 07-30 fhtrust 的 xlsx 掃不到檔案自報日期（排序鍵退成空字串）→ **同一個揭露日被 etfinfo 頂掉**，etfinfo 多給的 11 列（`202609US`／`202609TY` 公債期貨、`M_*` MARGIN、`DA_*` 扣除應付證券款、
  `PFUR_*` 應付買回款、`TLTW US`）全被判「新增」；隔天 fhtrust 回來、揭露日推進 → 同樣 11 列又全被判「出清」。其中 `PFUR_NTD`／`DA_USD`／`M_AUD` 的前日股數是**負數**（應付款），出清 Δ ＝ 0 −(負) ＝ **正值**，
  於是表上出現「+14,749 張」卻標出清——就是使用者說的「加碼的也出清」。**三道修法（缺一不可）**：列宇宙對齊、`xsrc`、`_prefer_incumbent`。
  **待查**（2026-10-29 看：00986D 現在來源是 fhtrust，持股與前一揭露日都沒有 `TLTW US`）：`TLTW US`（權重 3.5% 的 ETF 部位）只出現在 etfinfo，復華 xlsx 沒有——若它本該在，就是 `fhtrust._parse_xlsx` 漏了某個區段。
  抓取端已加「列宇宙差異」CI 日誌（僅 fhtrust／僅 etfinfo 各列前 6 個代號），下一輪 run 讀日誌即可判讀。
- **2026-07-29 教訓：曾誤標 00998A/00986D「結構性不支援」**——使用者指正後發現限制在自己的 schema（台股 4 碼驗證），不在資料；**下結論前先查 products.json／既有管線（pipeline.py）有沒有現成能力。**
- **債券 ETF 被檔數門檻擋掉（2026-10-21）**：00987D 美國公債只持有 3 檔，自 08-26 掛牌一直被擋、詳情區沒有它。分支上的 probe 看到 3 列＝兩檔 30 年期美國公債（59.7%、27.8%）＋`UB:2026-12:B 超長美債` 期貨（87 口、36.55%）
  ——期貨照慣例不算持股（同 00986D），`_NH_FUT2` 補認 `UB:2026-12:B` 與 `US202612`（00986D 的 etfinfo 列，原本也漏網）。
- **純 HTTP 投信官網探針，一輪一輪**：
  - **第 1 輪（2026-07-29，run 30420827829）**：野村 HTTP 500、統一 302 無限轉址、群益／安聯／證交所 ETFortune 全回 **SPA 外殼 HTML**（持股由 JS 動態載入）→ 真正的清單在 XHR 後面。
    探針加 `_api_hints()`：抓到 SPA 外殼時**從 HTML／內嵌 JS 撈出疑似資料端點印進日誌**，一輪就能收斂，不必一輪換一個猜測網址。同輪**假陽性**：通用解析從 ETFortune 頁面的**其他 ETF 推薦連結**刮到
    `0050 元大台灣50／0056 元大高股息／0052 富邦科技`，權重股數全 None，卻通過舊的「≥5 列」門檻 → 兩檔 ETF 上線了完全錯誤的展開明細 → 加 `is_plausible()`。
  - **第 2 輪**：①防呆生效（日誌現出 `[判為非持股清單：3 檔、帶量 0 檔]`）；②**元大 `tradeInfo/pcf/{code}` 回 1.07 MB HTML**（不是空殼）但表格解析 0 檔 → 資料是**內嵌在 script 的 JSON**，與 cnyesfund 當初完全同型 →
    新增 `parse_embedded_json()`（平衡物件掃描、原文＋反跳脫各試一次、只認帶權重或股數者）；③`_API_HINT` 舊版無詞界的 `api` 會匹配 c-**api**-tal（群益 capitalfund），整排 hint 都是導覽連結 → 加詞界；
    ④新增 `_key_hits()`：大頁面零結果時列出疑似鍵名命中次數，區分「真 SPA 外殼（該找 XHR API）」與「資料就在頁面裡、只是鍵名不同（該補鍵名）」。
  - **第 3 輪**：元大回 `鍵名命中={'shares':24,'weight':191,'股數':10,'權重':59,'比重':7,'成分股':63,'持股':9}` 但 **stockNo／stockId／stockCode 全 0 次** → 代號欄叫別的名字，平衡掃描的錨點一次都沒觸發；
    `weight` 那 191 次多半是 CSS `font-weight`；群益的 `證券代號` 只出現 3 次且是 HTML 文字非 JSON 鍵。修：錨點鍵名放寬到 `code/id/symbol/ticker/secId/secNo`（`_KEY_ID` 同步補 symbol/ticker，否則錨點觸發了
    `_row_from_mapping` 仍取不到值）；`_key_hits` 扣掉 `font-weight`；**`_key_hits` 改印「資料錨字末次出現的上下文原始片段」**——只印次數無法決斷是 HTML 表格／內嵌 JSON／純樣板，印片段才能一輪定位結構。
  - **第 4 輪定案：「從頁面 HTML 撈持股」是死路，別再往這條調解析器**：元大「成分股」末次上下文是**費率表／指數編製規則文案**（`…以下(含)：0.10%…Quarterly re-balance…`）、群益「證券代號」是**基金公告內文**
    （`【基金公告】…群益半導體收益（證券代號：00927）…`）；那 1 MB 的元大頁面是把全站文案與路由打包的 SPA bundle，**持股資料全靠 XHR**。→ 主力改 `_bundle_api_hints()`：**從 `<script src>` 抓 JS bundle、
    再 regex 找 API 路徑字面值**。節流鐵則：**每站台每次執行只掃一次、最多 3 支 bundle**（`_bundle_cache` 以 host 為鍵）——23 檔逐檔重掃會對投信站發出上百個不必要請求。
  - **第 5～6 輪：bundle 路線有效但踩到自家 bug**。第 5 輪元大 bundle 掃出 **`/api/bridge`**（通用 API 閘道，光有路徑打不出請求 → 加「呼叫脈絡」把端點前後 ~360 字元程式碼一併記錄，看得出 method 與 body 參數名）。
    第 6 輪才發現：群益「bundle」424450B、安聯 9437B **與各自的 HTML 頁面同大小**——**SPA catch-all 路由把 index.html 原封回給任何 .js 路徑**，白掃三輪。防呆：**回應以 `<` 開頭或位元組數等於頁面 → 判為
    catch-all 假 bundle**，日誌講明；並列出「頁面 script 共 N 支：檔名…」以便挑對主 bundle（元大只抓到 3.3KB 小 chunk）。
