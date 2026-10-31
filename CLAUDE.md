# CLAUDE.md — 復華基金雷達 · 給 Claude 的操作規則

復華基金雷達＝復華投信基金與 ETF 的每日儀表板（主頁 `dashboard/index.html`，Vercel 部署）＋籌碼雷達研究站（`dashboard/x9*.html`：市場、選股、研究紀錄）。
主要資料夾：`arm/`（程式；籌碼雷達在 `arm/lab/`）、`scripts/`（抓取、建頁、研究、檢查）、`data/`（落檔與研究檔）、`dashboard/`（CI 建出來的頁面）、
`reports/`（每天的新聞報告）、`config/`、`docs/`（每個功能的規劃與結果）、`wiki/`（知識庫）、`tw-superstock-lab/`（飆股研究）。

## 知識庫怎麼用（2026-10-29 起；docs/llm_wiki_plan.md）

這份檔只留鐵則與五個指令；每個功能怎麼運作、不能改的規則、踩過的坑、歷史，都在 `wiki/`（下面一行會把目錄一起載入；沒載入就自己讀 `wiki/index.md`）。
- **動手前**：看目錄，讀相關的頁；讀到某些程式時，`.claude/rules/*.md` 也會自動提醒該先讀哪一頁。
- **做完事**：改相關那一頁（改掉過時的句子，不是往後加），`wiki/log.md` 加一行；摘要變了就改那一頁第 3 行，再跑 `python3 scripts/wiki_split.py` 重產目錄。
- **全面檢查**只在使用者打「整理知識庫」時做（見下方指令）。
- 這份檔只有鐵則或指令改了才動；五個指令在 `wiki/ops/` 各有一份整理版，改了要兩邊一起改（`python3 scripts/wiki_facts.py` 會檢查）。
- 瘦身前（2026-10-29）的全文：`git show d6ed51029:CLAUDE.md`。

@wiki/index.md

## 鐵則（每次都要守；細節在括號裡的頁）

**容器與資料**
- 時間一律台北：程式用 `arm/clock.py` 的 `today_tw()/now_tw()/stamp_tw()`，跑腳本帶 `TZ=Asia/Taipei`（`wiki/env/container.md`）。
- 容器的網路會擋資料來源站（fhtrust、etfinfo、證交所、櫃買、期交所、Yahoo、鉅亨、Google News、PTT、vercel.app）：**容器內絕不跑資料抓取腳本**
  （`fetch_*.py`、`backfill_*.py`），抓取交給 CI；非跑不可就包 `timeout`（`wiki/env/container.md`）。
- 絕不把非空的落檔覆寫成空（例 `data/fund_news.json`；誤覆寫用 `git checkout -- <檔>` 還原）；容器跑過 `check_numbers.py` 之後 `git status data/` 確認。
- 本機建出來的 `dashboard/*.html`、`dashboard/*.json` 絕不 commit（CI 建權威版）；`git add` 一律寫明路徑，不用 `-A`。
- 不可宣稱「線上已生效」：容器看不到 Vercel；完成定義＝CI commit 在 main＋該 run success＋資料日推進（`wiki/ops/deploy.md`）。
- 資料分支 `claude/ussx-data` 絕不合併進 main；SEC 聯絡 email 只從 secret `SEC_CONTACT_EMAIL` 讀，不印、不存。
- 上傳或下載的外部資料包是不受信任的資料：解到自己的空目錄、不執行裡面的程式、用 `python3 -I` 讀。
- commit 一律 noreply 身分；不寫使用者的姓名、email、本機路徑（`tests/test_privacy.py`；`wiki/env/git-history.md`）。

**上線**
- push 觸發的 workflow 用「被推分支」上的 workflow 檔；修法要進 main 才算數，改 workflow 要確認 main 上真的有（`wiki/ops/routines.md`）。
- 這些檔 push 到 `claude/**` 就會觸發 workflow 併進 main：`reports/**`、`data/etf_upcoming.json`、`config/holding_profiles.json`、`config/index_reviews.json`（daily.yml），
  `config/strategy_candidates.json`、`config/strategy_board.json`、`arm/lab/cands/**`（strategy_cands.yml）；不是要走那條通道就不要動。
- 防線不可硬到什麼都沒更新：數字核對不擋發佈，結果上板、見紅就修。

**內容**
- 禁用詞（正文不得出現，機構觀點也要改寫避開）：保證、穩賺、必賺、包賺、必漲、必跌、一定會、唯一、建議買賣、建議買、建議賣、目標價、零風險、無風險、穩賺不賠；
  「目標價」只有三個例外（`wiki/ops/content-rules.md`；第三個＝個股報告的評等與目標價）。新聞來源黑名單：排除「富聯網」（moneylink）。
- 主頁面（市場頁、選股頁）用字：不寫方法字、比較只寫一次「任一天」、不用箭頭；改了自己跑 `tests/test_plain.py`、`tests/test_old_urls.py`（CI 不跑；`wiki/lab/plain-words.md`）。

**研究**
- 規格先寫好、commit，才算結果；要改＝VER＋1，不在看過結果之後改舊版本；看過結果才改的要照實寫出來。
- 判定沒過就照實講，不為好看放寬門檻，但要附上可以試的下一步；後一段研究改掉前一段決定的前提時，先回頭問使用者。

**頁面與程式**
- 兩個來源並排呈現時，先問是不是同一天的；「抓不到就沿用」一定要配一個過期標記；說「沒有資料」之前，先 grep 專案裡有沒有人已經在抓（`wiki/lessons.md`）。
- 版面驗證看真的看得到（`offsetParent`／截圖），不看 class；新增 CSS class 先查撞名；幾支 JS 串成同一個 `<script>` 時不得有同名函式或頂層 const。
- 寫進 `GITHUB_OUTPUT` 的指令，stdout 只能有那個值。

**跟使用者**
- 回報一律繁體中文、白話、結論先講；方法術語只在研究紀錄（`wiki/user.md`）。
- 先深度規劃、問決定、再一段一段做；每一段做完讓使用者看過，使用者說「好」「繼續」才往下。
- 派子代理要它回報精簡（新聞子代理＝三行：卡數、各卡標題、check 結果），細節寫進檔案。
- 知識庫大原則（使用者 2026-10-29）：架構要清晰、不要變成浪費更多 token，絕不影響本來的產出品質與架構邏輯，不要把本來的根本弄掉。

## 指令：「全部更新」／「資料更新」

使用者只要打**「全部更新」**（或「資料更新」），第一時間直接執行，不要再詢問。

> **效率原則（2026-07 檢討，務必遵守——這是本流程最重要的一條）**：本 Claude 容器 proxy 會擋掉**所有**
> 資料來源站（`fhtrust.com.tw` 403、`etfinfo.tw` 403、Google News、PTT），所以在這裡跑
> `fetch_holdings.py`／`fetch_fund_news.py`／`fetch_etf_watch.py` **注定失敗或卡到逾時**
> （實測 `fetch_etf_watch.py` 在此**空轉逾 20 分鐘**、`fetch_holdings.py` 25 檔全 403）——那不是程式 bug，
> 是環境限制，正式區完全不會發生。這三支抓取「正式區」（`daily.yml` GitHub Actions，擁有者身分、完整網路）
> **本來就會自己跑**。**因此在這裡「絕不」跑資料抓取腳本**——只做「只有 Claude 能做」的事（WebSearch 產新聞
> 內容），把資料抓取＋權威版儀表板整包丟給正式區，最後**讀 CI 入庫的 `dashboard/index.html` 驗證線上內容**
> （截圖 Vercel 線上頁被同一套 proxy 政策擋、做不到，詳見步驟 9）。這樣可省下每次約 25 分鐘的空轉。

1. **產提示包**（本地、秒級，是 WebSearch 的輸入，**要跑**）：
   `TZ=Asia/Taipei python3 scripts/gen_usnews.py && TZ=Asia/Taipei python3 scripts/gen_twnews.py && TZ=Asia/Taipei python3 scripts/gen_macronews.py`
2. **上網查證產新聞內容**（**Claude 專屬、不可省、~10 分**；純 Python 不杜撰新聞，此步用 WebSearch 補；可派平行子代理，各自嚴守提示包版型）：
   - `reports/usnews/{今日}_v1.md`、`_v2.md`（昨夜美股；先查證美股當日是否休市）
   - `reports/twnews/{今日}.md`（台股；週末/休市日改寫最近交易日並註明）
   - `reports/macronews/{今日}.md`、`reports/macrocal/{今日}.md`（總經政策＋本週行事曆；
     行事曆涵蓋**美國＋歐盟＋中國＋日本**重點數據與**海外企業財報／法說**，項目加「美：／歐：／中：／日：／財報：」前綴；
     **台灣區另用「台：」（官方經濟數據）與「台股：」（公司法說・財報，代號必填）前綴**；
     **精簡上限：總列數 ≤30、同指標口徑併一列、只收排定事件、引言只寫更新／市況／本週焦點**
     （2026-10-13 起，見 wiki/main/calendar.md「行事曆台灣區與精簡規則」）；
     **週末版另帶上週結果**（上週五與上週仍未公布的列，填實際值、放表格最後，不算進 30 列；2026-10-30 起）；
     **已過公布時間、實際值還空白的列必補**（提示包逐列列出；查不到在「註」寫「待補：項目——原因」；2026-10-31 起）；
     引言須含**「市況」段**（2026-07-22 使用者需求）：`市況：台股 …｜美股 …｜日股 …｜韓股 …｜陸股 …｜港股 …`
     六市場依序、全形「｜」分隔，各填「正常交易」或「M/D 因〇〇休市」——儀表板今日重點據此
     產雙視圖 chip（台股頁＝台股本身、全球頁＝美＋日韓陸港），格式勿改）
   - **週末合併時窗＝累進**（提示包會自動帶入 `usnews.weekend_note()`，改規則改那支函式即可）：
     週六涵蓋週五晚間起、週日再含週六、**週一須把週五晚間＋週六＋週日整個週末最重要的新聞一次
     綜合整理**，不可只看最近一天。
     · **週末新聞稀疏時的取捨（2026-08-03 使用者回報「週一的台股新聞很爛、一點都不重要」）**：
       週末本來就少新聞，子代理容易改用**「投顧看後市」「法人估某數字」「本週有哪些事要公布」**
       這類看法與預告湊卡數——**這些不是事件，重要度一律視為 <6、不得單獨成卡**（機構觀點只能在
       某張事件卡段內輔助引用一句）。卡數不足時**寧可少 1～2 卡**，或把時窗往前延伸到週五盤中／盤前
       補真正發生過、尚未報導的事件，**絕不用預測性內容充數**。
     · **不要為了補卡數而跨界抄國際新聞（2026-08-03 使用者最終定調）**：
       同日曾試過「週一台股報告以國際事件領銜」，使用者看過後回覆「感覺新聞變成都一樣了，
       還是要切開來…不要混在一起」——那版讓台股報告變成總經報告的翻版。**正確作法是往前
       累進補台股自己的事件**（公司公告、法說、官方統計、籌碼、交易所措施），不是改抄國際新聞。
     · **週末最重大事件保底（2026-08-31 使用者回報 Kevin Warsh 案，勿再犯）**：週五最重要的
       沃許（Fed 主席）傑克森霍爾鷹派談話，六、日總經報都有卡，**週一那份卻整份無卡**——
       「已報導清單＋週末無新進展→略過」壓過了週一綜整要求，只剩總覽一句「詳前份日報」；
       但儀表板只顯示當日報告，指向前份日報＝事件對讀者直接消失（美股報因以「上週五交易日」
       為報導主體而天然重收、逃過一劫；總經／台股報沒有交易日錨、最易中招）。規則已入
       `usnews.weekend_note()` 的【週末最重大事件保底】段（`prior_block()`／`pick_note()` 同步掛
       例外註記）：時窗內最重大 1～2 件事即使無新進展，週末三日皆**必須成卡重收**——
       【延伸】＋新在哪＝「週末綜整」，寫成「事件全貌＋累積市場反應＋本週檢核點」的綜整版。
       生效條件＝merge 進 main 後做一次「排程搬家」（同提示包規則的固定傳播機制）。
   - **各報守備範圍／切開來寫（2026-08-03 使用者：「還是要切開來…不要混在一起」）**——
     規則在 `usnews.lane_note(kind)`，三支產生器都會帶入（`kind`＝tw／macro／us，改規則改那支即可）：
     · **台股報告＝台股本位**：大盤與個股、族群與供應鏈、公司公告與法說、官方統計、
       交易所措施、官方籌碼、除權息與新股。**國際事件（戰事／央行／關稅／油價／國際大廠）
       原則上留給總經與美股報告**；只有直接牽動台股時才收，且**只寫「對台股哪些族群／個股／
       供應鏈的影響」那一面**，不重述事件本身與全球資產分析。
     · **總經報告＝國際政策與總體本位**（白宮／關稅／央行／地緣／制裁，及其對全球經濟與
       美債美元油金股指的影響），不逐檔點台股個股。
     · **美股報告＝美股公司與產業本位**（財報財測／併購合作／產品資本支出／供應鏈人事／
       監管訴訟），不寫成政策評論。
     · **唯一例外（2026-08-03 使用者同意）**：台股報告可在**「盤前／盤後速覽」段落用 1～2 句
       帶到國際背景**，讓只看台股那份的讀者知道昨夜／週末有哪些大事在牽動今天開盤；
       格式＝『事件一句＋對台股哪個方向的意涵一句』，**不另開卡片、不展開全球資產分析**。
     · 讀者是把三份當三個不同視角在看的——**三份都在寫同一批事件就失去意義**。
     · 台股來源**以經濟日報（money.udn.com）為主**，其次工商時報／中央社／聯合／鉅亨
       （規則在 `usnews.SRC_RULE_TW`）。
   - **提示包已自動預算（2026-07 效率優化，不必再自己查）**：①`usnews.calendar_anchor()` 已算好
     「今日星期幾／對應昨夜美股實際交易日／鄰近美股休市日」——**直接採信、勿再花搜尋自行推算星期與假日**；
     ②`usnews.prior_block()` 已把前一日日報的卡標題列成「已報導清單」——**清單內的舊聞若無新進展就直接略過、不要重查**。
   - 不重複收錄前一日已報導的舊聞；有新進展標【延伸】。每卡至少 1 條真實可點 [標題](URL)。
   - **來源以主流媒體為主（2026-07-20 使用者指示，規則已寫進提示包 `usnews.SRC_RULE_GLOBAL/_TW`）**：
     台股首選經濟日報／工商時報／中央社／聯合／鉅亨；全球首選 WSJ／FT／CNN／Reuters／Bloomberg／
     CNBC／富途牛牛。**每卡至少 1 條主流媒體原文連結**；聚合站（ts2.tech、KuCoin 等）只能當補充、
     不得為唯一出處。
   - **台股報必收經濟日報當日頭條（2026-08-04 使用者：「經濟日報頭條一定要放」）**：台股子代理
     查證第一步先掃 money.udn.com 當日頭版頭條／要聞，屬台股守備範圍者**必收為一卡**、不得因選題
     取捨而漏掉（當日案例：頭條「台股關禁閉規定 鬆綁」處置股新制＝全市場交易制度變革，第一輪
     子代理竟整篇沒收）；屬國際／總經者交總經報收、台股報在速覽帶一句。規則已入 `usnews.SRC_RULE_TW`
     （提示包自動帶），派工 prompt 仍要點名。
   - **⚠ 正文禁「查證過程」字句（2026-08-04 使用者：「沒抓到數字就算了，還寫出來還加粗體是在
     幹嘛」）**：數字查不到（未達兩來源一致）→ 正文就自然地只寫方向與定性描述，像一般新聞一樣；
     「未取得兩個獨立來源一致值」「本文一律不列數字」「依內規」「見資料侷限說明」這類流程性字句
     **只能寫在文末「資料侷限說明」段**，總覽／速覽／卡片各欄嚴禁出現、更不得加粗（當日踩坑：
     盤前速覽把整句免責文加粗放在正文，使用者直接開罵）。規則已入 `usnews.HILITE_RULE` 數據口徑段。
     **2026-08-17 再犯同型（使用者：「請避免之後再發生」）——「資料來源機制說明」也是流程性字句**：
     昨夜美股總覽正文出現「費半與 ADR 數字取自本機官方落檔 `series.sox`／`series.tsm_adr`」——
     讀者不知道也不需要知道數字從哪支檔讀。**檔名／欄位名／「落檔」字樣一律不得入正文**；
     此型自 2026-08-17 起由 `check_reports.py` 的 `_check_process_language()` 結構性擋下
     （`_PROCESS_RE`＝落檔／series.*／*.json＋08-04 那批句式；「資料侷限」「合規」段豁免）——
     歷史報告掃描顯示「詳見資料侷限說明」在速覽正文其實反覆復發，此閘門一併根治。
   - **⚠ 籌碼數字一律讀本機官方落檔 `data/macro_chips.json`，不要引媒體、也不要因為抓不到就省略
     （2026-08-03 使用者：「有官方數據一切以官方為準」）**：三大法人合計／外資及陸資／投信／自營商
     買賣超、外資台指期淨部位（大台）、融資融券餘額、台指選擇權 P/C 比，**CI 每天已從證交所 BFI82U／
     MI_MARGN 與期交所抓好並入庫**，容器端 `git show origin/main:data/macro_chips.json`（或直接讀工作區檔）
     就拿得到，**完全不需連外網**。`series.{指標}` 是 `{日期: 值}`，取最後一個交易日即可；
     `as_of` 是抓取時戳（當日盤後數字要等 15:40 那班 `afterhours_refresh.yml`，早上跑時最新只到前一交易日，
     這是正常的、不是缺資料）。
     · **踩過的坑（2026-08-02）**：子代理引兩家媒體都寫的「三大法人買超 846.76 億」，官方實為 **873.1 億**；
       逐項比對後**差額 26.4 億全部出在投信（官方 360.2 vs 媒體 333.82）**，外資與自營商兩邊一致。
       **兩家媒體數字一致 ≠ 官方口徑**——同型於 2026-07-20 的外資淨空單誤引彙整站。
     · **也不要走另一個極端**：隔天子代理改成「查不到官方就整段不寫」，結果整份報告只剩 1 個數字可核。
       官方值就在落檔裡，該寫就寫、寫官方的。真的落檔也沒有的指標才只寫方向並列入資料侷限。
     · 措辭保持可解析形式（例「三大法人合計買超 873.1 億元」），別寫成括號夾注——
       `arm/factcheck.py` 抽不到 claim 就等於數字不再受檢（2026-08-02 實測過）。
   - **⚠ 落檔曾混入「美股盤中值」（2026-09-23 使用者：「費半又抓到盤中資料了」）**：盤後刷新班次
     （台北 22:30／01:00／02:00）落在美股盤中，Yahoo 日線的當日 bar＝盤中即時價，舊碼照收入檔；
     05:08 收盤班那天沒跑到 → 06:35 晨報照抄 02:00 的 12,617.21（+1.48%），實際收盤 12,689.82
     （+2.06%）、ADR 448.97 vs 452.00。修法＝`macrochips._CLOSE_ONLY`（sox／tsm_adr／vix）依 Yahoo
     `meta.currentTradingPeriod.regular` 判斷「仍在交易時段」→ 當日 bar 不收、且把先前誤收的同日值
     剔除（日誌印「剔除 … 盤中值」）；收盤後的班次才寫入。**所以美股收盤後、05:08 班之前，落檔最新
     一天可能是「前一交易日」——這是正確的，不是缺資料**；晨報仍須確認最新日＝昨夜美股交易日。
   - **費半／台積電 ADR 收盤同走官方落檔（2026-08-04 新增，根治「收盤稿互斥查無一致值」）**：
     `macrochips.GLOBAL_SPECS` 已加 `sox`（^SOX）／`tsm_adr`（TSM）兩序列，CI 每日自 Yahoo 官方
     序列抓進 `data/macro_chips.json`（僅資料層，溫度計表未加列）——報告引用費半／ADR 收盤值
     一律優先讀此落檔；落檔尚無序列時才用「媒體兩來源一致」。⚠ 媒體收盤稿的坑：搜尋引擎會把
     **他日**收盤稿混進當日結果（自由財經等網址無日期，08-04 險些把他日「費半重挫 5.71%」當
     週一收盤），引用前先核對文內有無**當日專屬事件標記**，對不上就棄用。
   - **卡數下限＝每報 ≥4 卡**（2026-07 由 6 調降以省時；門檻仍為重要度 6/10 以上、上不封頂，深度文照樣保底 1 篇）。
   - **分析深度硬性要求＋每卡必填「漲跌分析」欄（2026-08-19 使用者：「排程用 sonnet 內容不夠深入」＋
     「新聞分析加一欄漲跌分析、大跌/大漲的理由」）**：規則在 `usnews.depth_note(min_chars)`／
     `usnews.move_note(kind)`／`usnews.LABEL_RULE`，五份版型（美股 v1/v2、台股盤前/盤後、總經）自動帶入，
     改規則改那三個即可——
     · **深度六條**（寧可卡少而深，卡數下限仍 4）：①影響分析寫滿「事件→傳導機制→具體標的」三層因果鏈；
       ②每卡至少 1 個量化錨點（查證得到的數字）；③空泛結論句（「情緒轉趨保守」）後必接「為什麼／機制」；
       ④每卡至少補 1 項**原文之外**的查證背景（供應鏈位置／前次事件對照／歷史水準）——深度的主要來源；
       ⑤末影響欄以「後續觀察：…」收（具體檢核事件與時點，不寫空話）；⑥每卡正文 ≥150–200 字
       （版型各異；每卡字數上限已放寬 200–320／180–300，勿改回 120–180 的舊上限）。
     · **漲跌分析欄**＝該事件牽動標的/指數的**實際漲跌幅＋大漲大跌歸因**（主因＋次因，以來源佐證、
       「市場解讀為」中性表述；無明顯反應也要一句「反應有限＋為什麼」；【深度】精選卡免此欄）；
       寫成單行 `N. **漲跌分析**：…`（**標籤必加粗體**，解析同摘要欄）。儀表板渲染成金色塊，
       解析在 `extract_cards()` 的 `move`、渲染在 `_news_view()` 的 `.ngmv`。
     · 派工 prompt 仍要點名「每卡必含 **漲跌分析**（粗體標籤）＋深度六條逐條對照」；
       `check_reports.py` 自 **2026-08-20** 起擋「缺漲跌分析／影響分析 <2 條／每卡分析合計 <120 字」。
     · **生效條件＝本分支 merge 進 main 後做一次「排程搬家」**（排程會話用自己 checkout 分支上的
       gen_*.py 產提示包——與 9⑦ workflow 檔、settings.json 同型傳播機制；只 merge 不搬家＝排程仍用舊提示包）。
   - **選題邏輯＝由上而下（2026-08-19 使用者：「要真的篩選到熱門、市場真正重要的新聞」）**：
     舊選題是「關鍵字→搜到什麼收什麼」，會漏掉關鍵字外的當日頭條。四個機制（生效條件同上一條）：
     · **選題五步 `usnews.pick_note(kind)`**（五份版型自動帶入）：①掃描建候選 10–15 條（各主流媒體
       Top/頭版＋市場實際變動——漲跌/量異常的指數/板塊/個股＋行事曆已公布項；總經報必涵蓋昨日
       已公布重大數據的結果與市場反應）→②過濾（守備範圍/已報導/非事件——「預告與投顧觀點不入卡」
       自此平日與週末同標準）→③證據錨定評分→④≥6 全收且**「當日最大的事」必有著落**→⑤收尾補漏
       自查（最熱三件事各自成卡/總覽歸因/明確交他報）。「建議關鍵字」已降級為搜尋起點。
     · **評分校準（`usnews.SEV_RUBRIC` 增補；2026-08-31 使用者定調「從影響投資的重要性出發」後
       全面改「投資影響本位」）**：重要度只回答「牽動哪些資產／族群、多大、多確定」——事件嚴重度、
       軍事烈度、悲劇性、新聞聲量一律不加分。舊版漏洞＝「多家主流媒體同日獨立報導」可單獨撐起
       7–8 分：戰爭頭條天然聲量大，導致 2026-08-31 週一總經報 6 卡中 4 卡是地緣戰事、其中兩卡
       自己的漲跌分析寫著「反應有限」仍拿 7 分，把牽動所有資產的 Fed 主席談話擠出版面——已堵：
       ①7–8 分必須有「實際資產波動」或「已排定時點的具體傳導」，聲量只能當熱度佐證；
       ②**與漲跌分析欄互鎖**：卡內寫「反應有限／無可歸因變動」→ 至多 6 分；
       ③**地緣／戰事以「資產通道」計分**（油氣・航運・國防・供應鏈・避險資產的實際變動或新增
       暴險），例行戰況無資產反應又無新增暴險＝≤5 不成卡、總覽帶一句即可；
       ④央行／利率／財政／關稅走折現率通道牽動所有資產，同等證據下天然高於單一地緣事件
       （總經版補充段 `macronews.py`「政策面重要度參考」同步改寫）。
       分數不是湊卡工具、不得抬分/壓分——此條不變。生效條件＝merge 進 main 後「排程搬家」。
     · **市場變動錨定 `usnews.market_anchor(kind)`／`market_flags()`**：gen_*.py 產包時讀官方落檔
       `data/macro_chips.json`（先 fetch 讀 origin/main、退回工作區檔、全失敗整段略過）算最新一日
       變動，達門檻（費半/ADR/油金 ±2%、美元/台幣 ±1%、美債 ±10bp、VIX ±15%、法人 ±300 億）掛
       ⚑ 旗標＝「保底必答題」：歸因必須入卡或總覽（擇一、不硬湊卡）；序列未更新標「自行查證」不旗標。
     · **大變動提及閘門（`check_reports.py` 2026-08-20 起）**：旗標資產在對應報告（美股報＝費半/ADR、
       總經報＝美債/美元/台幣/油/金/VIX）全文隻字未提才 🔴。
     · **⚠ 錨定「看不到今晨」＝結構性盲點（2026-08-31 使用者抓包：川普炸伊朗、油價大漲卻沒收）**：
       美軍週日（8/30）空襲伊朗拉拉克島阻其向荷莫茲海峽布雷，布蘭特週一亞洲早盤跳漲逾 2%、
       重回 90 美元，**當日三份報告全沒收**。根因兩條，都不是「規則沒寫」而是機制本身看不到：
       ①**錨定序列本質落後**——06:35 產包時最新是 08-30 收盤 89.83（+0.58%），**低於 ±2% 門檻、
       不會旗標**；跳漲發生在報告產出後的亞洲盤，錨定結構上不可能反映「週日／今晨」的事。
       子代理若把「錨定沒旗標」當成「沒事發生」就必漏。②**同題舊稿蓋掉新事件**——該報其實有
       伊朗卡（封鎖／貿易萎縮，8/24–29 舊料），代理搜「伊朗」抓到舊角度就收工，沒查到週日的新攻擊。
       三處修法：`market_anchor()` 末段加「錨定＝收盤／落檔值、今晨與亞洲盤突發不在其中，
       不可因沒旗標就當沒事」警語（含本例）；`_SCAN["macro"]` 加⑤「持續性議題的最新一手進展
       ——戰事／封鎖／制裁／關稅每輪都要查最近 24 小時有無新實際事件，不可用同題舊稿代替」；
       `_SCAN["tw_pre"]` 加「今晨亞洲盤的國際突發（油價／匯率／他國股市）」；`weekend_note()`
       補反向風險段（週日與今晨才發生的事最容易整個漏）。生效條件＝merge 進 main 後「排程搬家」。
     · **⚠ 錨定與閘門＝「下限保證」、絕不是選題範圍（2026-08-19 使用者特別要求，勿走回頭路）**：
       市場當日主角可能是清單外的匯率/原物料/加密資產/他國股市/突發事件——這些由選題五步①的
       開放式判準（「波動異常」或「多家媒體領銜」）負責抓，錨定文案與 pick_note 都明寫此原則；
       閘門機制上只會「多一道檢查」（提及即過、不要求成卡、序列過期跳過、落檔讀不到 fail-open），
       永遠不可能排除任何新聞。發現常態盲點時優先想「掃描清單補一句」，不是無限擴錨定序列。
   - **速覽／總覽段＝「10 秒讀者」的文風規格 `usnews.BRIEF_STYLE`（2026-09-01 使用者看手機版
     盤前速覽後指示：「整段粗體的偏少…廢話不要太多，你是專業的語言分析師幫我保留精華用詞精準」）**：
     五份版型自動帶入，改規則改那支常數即可。六條——①整段 ≤220 字、≤3 小段、每句 ≤35 字；
     ②結論先行（第一句就是方向＋牽動誰，數字擺第二句以後）；③**版型與內規標籤不得入正文**
     （「國際背景一句帶過」「（細節留給總經與美股報告）」「盤前研判（中性陳述）」——要分段就
     直接換段，同「查證過程不入正文」原則）；④刪填充語（值得注意的是／整體而言／換言之／
     這也是…的背景）；⑤**粗體每小段 2–3 處、結論詞組也要標**（方向與受影響對象、關鍵事件名、
     檢核點），不是只標數字——原本整段只有數字有底色，讀者沒有落點；⑥形容詞能換成數字或
     具體事實就換（寫「跌破五日線」不寫「表現不佳」）。**卡片求深、速覽求快，與 depth_note
     的深度六條不衝突**。閘門在 `check_reports.py` 的 `_check_brief`（2026-09-01 起）：
     散文超 320 字／出現版型標籤與填充語／粗體 <2 處 → 🔴。
     ⚠ **字數只算散文段、條列另計**（首版把兩者合計，美股與總經那種「指數收盤條列＋一段解析」
     的索引式總覽必紅——條列本來就好掃、不是使用者抱怨的長篇敘述）；條列改以條數 ≤6、
     每條 ≤130 字設限，免得有人把長文塞進 bullet 繞過上限。
     生效條件＝merge 進 main 後做一次「排程搬家」（同其他提示包規則）。
   - **卡片可讀性 `usnews.READ_RULE`（2026-09-01 使用者：「不只是在速覽喔，整個新聞卡也要套用」）**：
     與深度六條**並行不衝突**——深度講「要寫到幾層因果」，這條講「同樣的內容要寫成讀得下去的樣子」，
     總字數不減。五條：①**每句 ≤40 字**（實測當日卡片均長 42–70 字、單句最長 146 字，一句塞三四個
     子句讀者中途就棄）；②**每欄 2–3 處粗體、結論詞組也要標**（`HILITE_RULE` 原本寫「每欄至多 2 處」
     ——那個上限正是台股卡只有 0–3 處、其中一張深度卡整張沒粗體的來源，已改為 2–3 處）；
     ③**多層傳導分句寫**（「第一層是資金：…。第二層是…。」每層各自成句），「後續觀察：…」獨立成句
     置於欄末；④刪填充語；⑤形容詞能換數字就換。
     · **渲染端配套 `fund_dashboard._lines()`**：欄內遇「第N層／其N／①」與句末「後續觀察：」
       自動斷行（後者另加虛線分隔、壓低對比）。**只認明確列舉標記、句號一律不亂斷**——
       亂斷會把「甲公司。乙公司」這種連續敘述切碎，比不斷更難讀。純呈現層、不改字，
       既有報告重建即生效（當日 19 張卡共斷出 28 行）。
     · 閘門 `check_reports._check_card_read`（**2026-09-02 起**，今日報告不回溯）：每卡粗體 <3 處／
       超過 60 字的句子 >2 句／出現填充語 → 🔴。當日實測若套用會抓出 30 項（台股 11、美股 9、總經 10），
       示範改寫台股卡 1 後：粗體 3→14、均長 59→38、≥60 字句 9→2。
   - **⚠ 卡內欄位標籤「必須加粗體」`N. **新聞摘要**：…`（2026-07-31 連三次踩坑，派工 prompt 務必寫明）**：
     儀表板 `arm/usnews.extract_cards()` 抽摘要／影響分析的 regex **要求標籤帶 `**`**（`^\s*\d*\.?\s*\*\*新聞摘要\*\*[：:]`），
     子代理寫成 `1. 新聞摘要：`（無粗體）→ 解析全落空、`summary`/`points` 皆空 → **儀表板該卡只剩參考連結、
     詳細分析整片消失**（合規掃描與舊版 check_reports 都照樣 🟢，因為連結與徽章都在，看起來一切正常）。
     現已由 `check_reports.py` 的「摘要／影響分析皆空」檢查擋下（見步驟 3），但**源頭仍是派工時要講清楚**。
   - **深度報告精選保底 1 篇**（台股與美股報告各自保底；標題括注用【深度】）：台股從經濟日報／
     工商時報／中央社專題／財訊・今周刊挑；美股從富途牛牛深度文、Reuters Analysis／Bloomberg
     深度專題挑。只挑真深度（產業鏈拆解/商業模式/政策影響），當日不足放寬到近 3 天並註明刊出日。
   - **子代理回傳格式＝精簡三行（2026-07-23 省 token；派工 prompt 末段務必明確要求）**：只回
     ①卡數 ②各卡標題一行清單 ③check 結果（🟢/🔴）。**不要**逐項複述查證過程、口徑核對細節、
     排除的假線索、資料侷限全文——那些寫進報告檔即可，主會話需要時直接 grep 該檔。整段回傳控制在
     ~15 行內。（真實內容都在 `reports/*.md`；主會話只需知道「幾卡、標題、有沒有過 check」就能收尾。）
3. **合規掃描＋內容 QA＋數字核對**：`gen_usnews.py --check`、`gen_twnews.py --check`、`gen_macronews.py --check` 全須 🟢；
   另跑 `TZ=Asia/Taipei python3 scripts/check_reports.py` 須 🟢（檔案齊全／每報≥4卡／每卡有連結與重要度／
   **每卡摘要或影響分析非空**／**2026-08-20 起：每卡漲跌分析欄＋影響分析≥2條＋分析合計≥120字**（【深度】卡豁免）／
   **2026-08-20 起：大變動提及**（官方序列旗標的資產，對應報告全文須提及；序列過期或落檔讀不到＝跳過）／
   **2026-10-13 起：頭段總覽／速覽抽得到**（美股 v1／總經「…總覽」、台股「盤前／盤後速覽」；見 wiki/main/print.md 踩坑⑤）／
   **2026-10-13 起：行事曆台灣區與精簡上限**（台／台股列或「本週無」註記、總列數 ≤30、引言 ≤220 字）／
   **2026-10-31 起：週末版帶齊上週結果列**（上週五與上週仍未公布的列）／
   **2026-10-31 起：已過公布時間的列要填實際值或在註寫「待補：項目——原因」**／
   行事曆為今日）——「摘要／影響分析皆空」該項是 2026-07-31 新增的防呆，
   🔴 訊息會直接指出是標籤沒加 `**粗體**`（見步驟 2 與 wiki/main/news-cards.md），照著把該報告的 `N. 標籤：` 改成
   `N. **標籤**：` 即可，勿改渲染端；
   **再跑 `TZ=Asia/Taipei python3 scripts/check_holdings_intro.py`（前十大簡介覆蓋率，🔴＝有持股缺簡介）——
   見 🔴 立即 WebSearch 查證後把缺的標的補進 `config/holding_profiles.json`（格式 `{name: {intro, ticker, country, verified}}`、
   純事實非投資建議、避開禁用詞），補到 🟢 為止**（2026-07-23 使用者：前十大簡介一再漏掉，此為固定防呆步驟，不可略；
   補完隨步驟 6 push 即自動落地——該檔走 daily.yml 併檔自動通道，不需 PR，見步驟 9⑤）；
   再跑 `TZ=Asia/Taipei python3 scripts/check_numbers.py`（高風險數字對官方 API——本容器 proxy 擋 twse/taifex
   會全 ⚪ 屬正常，真正核對在 CI）。**發佈策略（2026-07-20 使用者兩指示並行：數字要對＋防線不可硬到什麼都沒更新）**：
   CI 端 🔴 **不擋發佈**——結果落 `data/factcheck.json` 隨每日 commit 入板、儀表板「網頁更新時間」區顯示
   紅色警示章；主會話在步驟 9 驗證時讀該檔，見 🔴 **立即修正該數字並重推**（分鐘級收斂）。
   曾踩：外資淨空單誤引彙整站 83,605 口、官方實為 86,189。
4. **重建儀表板驗證**（本地、秒級，只為確認新聞入板＋渲染管線沒被新內容弄壞；**不需先抓資料**）：
   `TZ=Asia/Taipei python3 scripts/gen_fund_dashboard.py`，確認「🕒 資料更新時間」區塊**新聞欄位**已更新至今日。
   **驗完務必 `git checkout -- dashboard/index.html` 丟棄本地重建結果**（2026-07-23 省 token 優化）——
   本地重建的 index.html 帶的是舊 NAV／ETF 快照，**絕不 commit**：①CI 稍後會用真實資料權威重產覆蓋，
   本地版沒有保留價值；②每天 commit 它幾乎必與 CI 的儀表板 commit 打架，逼出一整輪 fetch+merge+重建+
   re-push（實測是每日流程最大 token 消耗源）。丟棄後分支只帶「純新聞報告」，push 一樣觸發 CI、一樣有權威建表。
5. **測試**：`python3 -m pytest -q` 全綠（此容器預設無 pytest，先 `pip install -q pytest`）。
6. **commit＋push** 到本次會話指定分支：**只帶「新聞報告」**（`reports/*.md`＋提示包；**不帶 `dashboard/index.html`**——見步驟 4，本地版不 commit，由 CI 產權威版；`data/*` 被擋未更新、不會有 diff）。訊息用 `chore: 每日新聞更新 {日期}`。**不必開 PR、不必 merge 進 main**——見步驟 7，改由 CI 一次 commit。
7. **正式區「單一 commit」抓真實資料＋建表＋部署（2026-07-18 起：push 即自動觸發）**：
   步驟 6 的 push 動到 `reports/**` 時，`daily.yml` 會**自動觸發**（`on: push branches claude/** paths reports/**`），
   以被推分支為 `news_ref`——**不需、也不必再手動呼叫 GitHub API/MCP**（排程 Routine 的新會話沒有 MCP 工具，靠這條就夠）。
   CI 會：①checkout main、把該分支今日 `reports/*.md` 併入 → ②抓**真實** NAV／持股／ETF／基金新聞 → ③重建儀表板 →
   ④以擁有者身分**一次 commit 進 main（新聞＋真實資料＋建表同一筆）** → ⑤打 Deploy Hook 部署。
   **這根治了舊架構「一天兩筆 commit、Vercel 常部到舊版→新聞會動淨值不動」的坑**：main 每天只有**一筆權威 commit**。
   （互動會話若 push 沒觸發（如只改程式碼未動 reports），備援：`mcp__github__actions_run_trigger` 帶 `inputs={"news_ref":"<分支>"}`；
   留空 `news_ref`＝排程 cron 行為：只用 main 現有新聞重刷資料。）
9. **驗證線上內容（「全部更新」的完成定義＝網頁真的更新）**：等 `daily.yml` 跑完（約數分鐘）後驗證。
   - **Vercel 線上網址**：`https://fuhhwa-fund-radar.vercel.app/#overview`。
   - ⚠ **從此容器「截圖」線上頁做不到**（2026-07 實測）：agent proxy 對 `fuhhwa-fund-radar.vercel.app:443`
     回 **CONNECT 403（政策拒絕）**，與擋 fhtrust／etfinfo 同一套網路政策；Playwright/WebFetch/curl 一律不通。
     除非使用者改用更寬鬆的環境網路政策，否則別再嘗試截圖、白費算力。
   - ✅ **可行的「內容已產出」驗證**：直接讀 **main 上 CI 剛 commit 的那支檔**——
     `git fetch origin main && git show origin/main:dashboard/index.html` 後檢查：①美股／台股新聞、總經・政策
     皆今日日期；②「🕒 產表」時戳為 CI 那次（會比本地時戳晚，證明 CI 已重產覆蓋）；③ETF 表有值；④基金
     `data/funds/*.json` 的 `nav_date` 已推進（NAV 常見 T+1，今日只到昨日 NAV 屬正常）。並用
     `mcp__github__actions_*` 確認該次 `daily.yml` run `success`。
   - ⚠️ **「內容在 main」≠「線上已部署」——2026-07-17 踩過的大坑，務必分清**：
     - **單一 commit 架構（步驟 7）已根治「兩筆 commit」問題**：main 每天只有一筆權威 CI commit（新聞＋真實資料＋建表同一筆），不會再有「合併版舊資料」被誤部署。舊坑徵狀是「**新聞會動、淨值不動**」——若再出現，先查 main 最新 commit 的 `data/funds/*.json` `nav_date` 是否真的新（否則是 `news_ref` 沒帶到／CI 沒抓到資料），再查 Vercel 部署對到哪個 commit。
     - **我（容器內 Claude）看不到 Vercel 線上頁**（proxy CONNECT 403），所以**不可只憑「main 檔已更新」就宣稱「線上已生效」**——那是我 07-17 誤報的錯。我的完成定義只到「**CI commit 在 main＋該 `daily.yml` run success＋該 commit `nav_date` 已推進**」；「**線上真的更新**」需使用者端或 Deploy Hook 確認。
     - **主動部署**：`daily.yml` 末步已加「打 **Vercel Deploy Hook**」（`secrets.VERCEL_DEPLOY_HOOK`）——CI commit 完直接觸發 production 部署 main 最新，**不靠 Vercel 自動偵測**（自動偵測曾卡 Initializing／部到舊版）。**使用者需先建 hook**：Vercel 專案 Settings→Git→Deploy Hooks 建 `main` 分支 hook → 複製 URL → GitHub repo Settings→Secrets and variables→**Actions**→New repository secret，Name 一字不差填 `VERCEL_DEPLOY_HOOK`、Secret 貼 URL（**注意別建成 Variables 或 Environment secret**，workflow 讀的是 repository secret）。`daily.yml`／`afterhours_refresh.yml`／`etf_holdings.yml` **三支都已寫好讀這把 secret，建一次三班全生效**，程式碼不必動。未設時該步自動跳過、不影響 commit。
     - **⚠ 踩過的坑：secret 一直沒建 →「資料準時進 main、線上停在舊版」（2026-08-13 使用者回報「今天 15:40 的還沒更新」）**：
       當天 15:33 Routine 準時開跑、`afterhours_refresh` run **success**、15:34 就 commit 進 main（`21b5bcb`；2026-10-16 改寫歷史後這個編號已不存在），
       三大法人／外資台指期／P/C 比／全球溫度計全是當日值、儀表板產表時戳 15:34 也對——**資料層與 CI 全鏈零異常**，
       線上卻是舊版。**決定性證據＝該 run「觸發 Vercel 部署」步驟的日誌印「（未設 VERCEL_DEPLOY_HOOK secret，
       跳過主動部署）」、env 區 `VERCEL_DEPLOY_HOOK:` 是空值**——這把 secret 自 07-17 規劃以來從沒建成，
       每天都在空跳，部署一直只靠 Vercel 自動偵測 git push；當天那筆偵測漏接，線上就停在舊版。
       · **診斷順序（下次照這條走，數分鐘可判；別再從抓取端查起——這類「線上舊」的坑，資料端全綠是常態）**：
         ①`git show origin/main:data/macro_chips.json` 看序列最後日期 → 是今日就不是抓取問題；
         ②儀表板產表時戳是否為該班時間 → 是就不是建表問題；
         ③**讀該 run 部署步驟的日誌**（`mcp__github__get_job_logs`）→ 印「未設…跳過」＝secret 沒生效、
         印 `HTTP 2xx` 才算真的打出去 → 若已打出去仍是舊版，才輪到請使用者查 Vercel Deployments。
       · **當下緩解**＝dispatch 一輪 `daily.yml`（ref=main、`news_ref` 留空＝只用 main 現有新聞重刷資料）
         產生新的 commit＋push 事件，給自動偵測第二次機會（2026-08-13 實測有效，17:24 那筆上線）；
         **根治只有把 secret 建起來**。
       · **✅ 已解決（2026-08-13 當晚使用者建立 secret，dispatch `daily.yml` run 31690853627 驗證通過）**：
         該輪部署步驟日誌印 `VERCEL_DEPLOY_HOOK: ***`（讀到了、遮罩顯示）＋
         `{"job":{"id":"…","state":"PENDING"…}}` ＋ **`HTTP 201`**——hook 真的打出去、Vercel 已排程部署。
         **步驟耗時也是判準**：未設時瞬間 echo 完就 exit（0 秒），真打出去約 3~4 秒。
       · **驗證要挑對 workflow（實測差異）**：**`daily.yml` 的部署步驟沒有任何 `if:` 守門、無條件執行**
         ——要驗 secret 就 dispatch 它（`news_ref` 留空），必定跑到那步、必定有日誌可讀；
         `afterhours_refresh.yml`／`etf_holdings.yml` 的同一步有 `if: steps.guard.outputs.changed == 'true'`，
         資料沒變動的空轉輪會**整步跳過**，拿那種 run 驗會什麼都看不到、誤以為沒生效。
     - Vercel `vercel.json` 已設 `Cache-Control: no-cache`（2026-08-14 多人化 Phase 1 由 no-store 改，**兩支 vercel.json 根目錄與 dashboard/ 都要一致**）：瀏覽器可存但**每次都必須向伺服器 revalidate**——內容沒變回 304（~1KB）、變了才全量下載，多人重複造訪省流（規劃時以 100–300 人上限估，實際約 30 人）；**「線上看到舊的一律是「沒部署」而非快取」的診斷鐵則不變**（每次都 revalidate，瀏覽器快取不可能是原因），別叫使用者清快取白忙。304 是否生效看對時哨兵日誌的「（記錄）帶 If-None-Match 重打」行。
   - **⑤ 前十大簡介缺口（2026-07-23 使用者：一再漏掉；2026-08-12 全自動落地；同日改「主責＝15:33 盤後班」）**：讀
     `git show origin/main:data/holdings_intro_gap.json`。**晨間本步驟只讀不補**（使用者 2026-08-12：
     不佔早上、跟最簡單的那班）——count>0 → 成功推播裡帶一句「缺 N 檔簡介，15:33 班會補」即可；
     **補齊主責＝15:33 盤後籌碼 Routine 步驟②**（該班最輕、又在晨間持股抓取之後，缺口當天下午清）。
     **連兩天 count>0**（昨天下午沒清＝排程搬家前過渡期或該班失效）才在晨間親自跑下列迴路並查原因。
     **2026-10-21 起缺口檔也含 ETF 持股**（`items[].src`＝`fund` 基金前十大／`etf` ETF 完整持股；
     ETF 那幾筆另帶 `ticker`＝補進 profiles 的代號、`etfs`＝哪幾檔持有）——ETF 持股原本只有測試的
     95% 門檻守，主動式天天換股、滑到 97%（72 檔）沒人發現；`etf_holdings.yml` 抓完持股也跑一次檢查。
     **2026-10-24 起也含美股三成**（`src`＝`usqm`：配置頁美股列的股票＝手上的、要買的、名單前 5 名裡手上沒有的；2026-10-28 起是選股頁美股強勢品質股那張卡列的同一批，
     `fund_intro.uncovered_us_qm`；`name`＝每週紀錄的英文公司名、`ticker`＝代號）——使用者：「美股那些公司誰知道你是什麼公司…
     台股不都有列嗎？比照著做」。美股簡介**照「美國 公司名（中文名若有），本業；細節」寫**：頁面上取「；」前那一段，
     「，」前＝公司名（去掉「美國」與結尾括號）、後＝本業一行（`corepage.us_label`）。名單每週六換，新進前 5 名的公司週一下午這班補。
     **極簡迴路**（15:33 班與晨間 backstop 共用；全程 ~5 分鐘、不跑任何抓取腳本）：
     ① gap 檔 `items[].name` 就是快照原字串（已還原 `&amp;` 等實體）——**每檔 1 次 WebSearch** 查證（公司本業／代號／國別）；
     ② 補進 `config/holding_profiles.json`（`{原字串: {intro, ticker, country, verified, url?}}`，
        intro 純事實、避開禁用詞；country＝公司母國，如英飛凌→德國；**`url` 選填＝
        基金型持有（組合型的子基金，無掛牌代號）的鉅亨基金頁**
        `https://fund.cnyes.com/detail/{名稱}/{cnyesId}`——渲染端優先用它，沒 url 又沒
        ticker 的基金名去搜 Yahoo 必落空（2026-08-12 使用者：「點進去沒東西」）；
        股票/ETF 不用填，ticker＋country 會自動產 Yahoo 行情連結）；
     ③ `TZ=Asia/Taipei python3 scripts/check_holdings_intro.py` 須 🟢——它同時把本地 gap 檔歸零，
        **一起 commit**（下一輪重建紅章即滅，不等 CI 自查）；
     ④ `python3 -m pytest -q tests/test_holdings_intro.py` 秒級確認 → commit＋push 本會話分支。
     **push 即收工**：`config/holding_profiles.json` 已入 daily.yml 自動併檔通道（同
     `data/etf_upcoming.json` 模式，防呆＝JSON 驗證＋有簡介筆數不得減少）——**不需開 PR、
     不需 merge、不需 dispatch、不需監看**，push 觸發的那輪 CI 自動併入 main＋重建＋部署。
     （2026-08-12 前的舊流程要開 PR 人工 merge——首例 PR #200；通道上線後勿再走。）
     ⚠ **生效條件＝本會話分支 fork 自「通道已上線（2026-08-12 PR #201）」的 main**——push 觸發
     的 daily.yml 用**被推分支**的 workflow 檔（同 9⑦ YOUTUBE 金鑰傳播機制）。分支太舊時徵狀＝
     push 後 main 的 profiles 沒動：補救＝`mcp__github__actions_run_trigger` dispatch daily.yml
     （ref=main、news_ref=本分支——dispatch 用 main 的 workflow 檔，併檔段必有通道）；根治＝排程搬家。
   - **⑥ 盤後完整性警示（2026-08-03 新增）**：讀 `git show origin/main:data/afterhours_alert.json`——
     `date`＝昨日且 `missing` 非空＝昨天盤後有缺口且到深夜都沒自癒（夜檢 Routine 應已推播過）；
     早上這班會把缺口補齊，但請在推播裡帶一句、並查 afterhours run 日誌找根因。
   - **⑦ 社群 YouTube 驗證（2026-08-07 使用者：「每次更新都順便查一下 YouTube」）**：讀
     `git show origin/main:data/fund_news.json`，`social` 內 `platform=="youtube"` 支數須 ≥1
     （三層清單正常日不會是 0；為 0 時儀表板「網頁更新時間」列會掛「社群 YouTube 🔴 0 支」章）。
     為 0 ＝金鑰沒帶到或抓取失敗：查該輪 CI 日誌 grep `[fundnews]`／`未設 YOUTUBE_API_KEY`。
     **已知根因（2026-08-07 踩坑）：push 觸發的 daily.yml 用「被推分支」上的 workflow 檔**——
     排程會話分支若分岔自「daily.yml 掛上 YOUTUBE_API_KEY env（08-06 早）」之前的 main，
     該輪 env 就沒金鑰 → YouTube 全空（當時整段 social 還被洗成 0，現由 `fundnews._carry_social`
     來源級防呆擋住：單平台全空沿用既有項目、CI 日誌會印「社群 youtube 本次全空、沿用既有 N 則」）。
     補救＝`mcp__github__actions_run_trigger` dispatch daily.yml（ref=main、news_ref 留空）——
     dispatch 用 main 的 workflow 檔、金鑰必在；根治＝排程搬家到新視窗（新分支自最新 main 分岔）。
   - **⑧ 漏網新 ETF（2026-08-10 新增；同日兩度調整——先分級警示，再改「見到就處理」）**：讀
     `git show origin/main:data/etf_upcoming_gap.json`。**`items` 非空就當天處理完，不要押到週一**
     （使用者 2026-08-10：「如果知道有漏為什麼要等下週再更新，直接跑即時更新吧？」——
     **一週一次講的是「主動出去掃描」的頻率，不是「已知缺口的處理時機」**；發現層每天都在跑，
     壓著已列名的缺口等一週沒有道理，而且處理「已列名的 N 檔」比盲掃便宜得多）：
     · `kind=listed`（已掛牌卻沒登錄）＝真漏網，儀表板 🔴 紅章——最優先，立即查證補登；
     · offering（已核准／募集中待登錄）＝儀表板 ⚠ 琥珀章——**同一輪一併 WebSearch 查證**，
       有代號／募集期間就填正式欄位、只查得到「已核准」就用 `raise_hint`＋`asof` 登錄，
       **查無來源的欄位一律留空，不要猜代號或日期**；補完推分支（動到
       `data/etf_upcoming.json` 會自動觸發 daily.yml 併入 main）；
     · `pipeline` 欄（申請中、審查未過、或申報生效日尚未到）＝不警示也**不登錄**，
       生效後下輪自動升進 `items` 再處理。**2026-08-28 起會上版**（使用者：「有送件的
       ETF 就可以更新上去即將登場」）：「即將登場」區第四組「已送件・審查中」精簡列
       自動展示 pipeline 內容（`fund_dashboard._applied_row`，同名去重、本家復華排最前、
       fail-open）——純展示，登錄／逼補時機不變（仍等申報生效）。
     機制與坑見 wiki/main/etf-upcoming.md「新 ETF『自動發現』層」。
   - **⑨ 籌碼雷達推播行（2026-10-15 使用者同意：「06:35 推播多帶兩行」；原本兩行，現在最多六行，Routine prompt ① 仍叫「兩行」，指的就是 `push` 欄全部）**：成功推播在 3 條市場重點之後，附上
     `git show origin/main:data/lab/val_log.json` 最新資料日（`days` 最後一個鍵）的 `push` 欄**原文照貼**：
     第一行＝下一個交易日開盤／收盤要做的買賣（例「10/16（五）沒有排定的買賣。」），台股新飆股有要賣要買時多一行（例「新飆股：11/2（一）開盤賣 奇鋐、買 金像電。」，2026-10-24 起），美股強勢品質股有要賣要買時多一行（例「美股強勢品質股：10/26（一）開盤賣 INSW、買 PAYC。」；2026-10-28 前叫「美股三成」），少見但勝率高的策略接下來 2 個交易日要買或賣時多一行（例「少見機會：11/3（二）收盤 S&P 500 買進（期中選舉後抱一年，抱到 2027/11/2）。」，2026-10-27 起），策略候選第一次有結果時多一行（「策略候選：新增…」，見 wiki/lab/candidates.md「新策略候選」），
     最後一行＝策略驗證事件（有事件才有）。
     檔案讀不到或沒有 `push` 就省略這幾行、**不擋推播**。這幾行由 CI 重建籌碼雷達時產生（`arm/lab/valog.py`，順序與條件見 `valog.push_lines`；見 wiki/lab/chip-ui.md「版面 v4」），
     不必自己算、也不要改寫內容。
   - 註：持股基準為月度值（顯示上月底）——不是資料沒更新。

## 指令：「ETF 募集週掃」（2026-08-10 建立——使用者：「找到募集的資訊然後主動更新，一週一次」）

**與每日 SOP 步驟 9⑧ 的分工（2026-08-10 使用者釐清後定調，勿混淆）**：
「一週一次」講的是**主動出去掃描**的頻率；**已被發現層列名的缺口不等週一、當天就補**
（見步驟 9⑧）。所以本週掃的價值在**每日流程做不到的那些事**：全面盤點（發現層兩個來源
都沒收錄的檔）、既有條目的日期／頻率異動核對、hint 檔補正式日期、過期條目清理、
`pipeline` 內申請中檔有無新生效。正常情況下每日已把新缺口補掉，週掃多半只是核對與清理。

每週 Routine（台北週一 08:05）火進綁定會話執行；使用者手動打「ETF 募集週掃」也照跑。
**全程不跑資料抓取腳本、不動 reports/**、只改 `data/etf_upcoming.json`（＋審核相關時 `config/index_reviews.json`）**：

1. `git fetch origin main` 後讀 **origin/main** 的 `data/etf_upcoming_gap.json`（CI 自動發現的
   漏網檔，見 wiki/main/etf-upcoming.md「新 ETF 自動發現層」；`items`＝待登錄的已核准／募集中／已掛牌檔＋
   **`pipeline`＝申請中檔（不警示、僅盤點，本週掃順手看有無新核准）**）與
   `data/etf_upcoming.json` 現況；跑
   `python3 -m pytest tests/test_etfwatch.py -q` 看 stale guard 有無紅（過期條目）。
2. **WebSearch 盤點**（容器擋 moneydj/cnyes/chinatimes 原頁，用搜尋摘要即可）：鉅亨 IPO 頁
   （`fund.cnyes.com/IPO/index.htm`，2026-08-10 使用者提供）＋MoneyDJ 新基金頁
   ＋工商時報／經濟日報「投信新基金」稿＋逐檔精查。**每筆資料兩來源一致才寫**：
   - gap 檔缺口與新核准檔 → 補登（時程未定用 `raise_hint`＋`asof`；未派碼 `code: null`）；
   - hint 檔等到日期公告 → 改填 `raise_start`/`raise_end`/`list_date` 正式欄位；
   - 已登錄檔核對募集期間／掛牌日／配息頻率有無異動；掛牌逾期條目清理；
   - 海外被動指數檔 `track: false`；**本家復華新檔最優先、絕不可漏**。
2.5 **指數審核維護（2026-10-14 起；籌碼雷達「指數調整」資料源 `config/index_reviews.json`）**：
   每週掃一次即可、只在「有事」時改檔——①`next` 標「推算／未公布」的日期，查官方公告
   （富時羅素／證交所＝臺灣50、臺灣高股息；MSCI 半年度表＝00878；臺灣指數公司 technical notice
   ＝00919／00929，通常前一個月初公布下月時程）→ 查到就改日期、`status:"官方"`；②公告日過後
   把官方納入／刪除寫進 `history`（`adds`/`dels` 用 4 碼代號，`src` 至少一條、兩來源一致才寫），
   並把 `next` 推到下一次；③規則若改版（成分檔數、緩衝名次）同步改 `rule`，數字不確定寫「未查證」。
   **不猜日期、不猜名單**——查不到就維持「推算」。更新頂層 `as_of`＝今日；
   `pytest tests/test_lab.py -q` 須綠（守 JSON 格式與代號）。
3. 更新頂層 `as_of`＝今日 → pytest 全綠 → commit `chore: ETF 募集週掃 {日期}` push 本會話
   指定分支——**push 動到該檔會自動觸發 daily.yml**（on.push.paths 含它與 `config/index_reviews.json`），
   併檔段驗證後帶進 main 重建上線，**不需人工 merge**。
4. 結果：**有異動 → PushNotification 一句話**（改了哪幾檔）；無異動 → 安靜結束不推播；
   失敗 → 推播卡在哪一步。

## 指令：「策略探勘週報」（2026-10-24 建立；IA v5 第 5 段，docs/lab_ia_v5_plan.md 第 6、24 節）

每週日台北 19:47 Routine 火進綁定會話執行；使用者手動打「策略探勘週報」也照跑。框架規格 `arm/lab/candspec.py`（VER 2），
程式 `arm/lab/candrun.py`、`scripts/run_cands.py`，合併通道 `.github/workflows/strategy_cands.yml`。**全程不跑資料抓取腳本、不動 reports/**：

1. 先把 origin/main 合併進本會話分支（候選的程式與檢查要最新的）。讀 `config/strategy_candidates.json` 與
   `config/strategy_board.json` 的 `cand`：還沒決定的已有 10 條 → 不找，推播提醒使用者回「試用／納入／不納入」。
2. **找**（WebSearch）：來源限學術（SSRN、arXiv q-fin、期刊）、大型資產管理公司與知名量化部落格（AQR、Alpha Architect、
   Quantpedia、Research Affiliates…）、台灣投信券商研究報告。每週**最多 2 條**，四個條件都要：規則寫得清楚（參數有數字、
   能直接寫成程式）、有公開成績、**現有資料做得到**（指數收盤、VIX、漲跌家數、融資維持率；台股長歷史價量、月營收、季財報、EPS；
   美股資料分支的價量與 SEC 財報）、和已有的候選與頁面上的策略不重複。找不到就不湊、安靜結束。
3. **先寫規格再算**：規格一筆（`config/strategy_candidates.json` 的 `items`；欄位照 candspec：id 接續編號、found＝今天、name、
   mk、engine、kind、how 一句白話規則、src 至少一條 https 原文連結、why、p、grid、各型態要的 H／b／pick／ex、sha）＋
   程式一支 `arm/lab/cands/{編號}.py`（照 `arm/lab/cands/__init__.py` 的範本；參數從 p 讀、只用那一天收盤以前的資料、
   台股財報與月營收一律經過 `cands.Fin`）。sha＝`python3 -c "from arm.lab import candrun as R; print(R.sha_file(R.PROG/'c00X.py'))"`。
   資料不夠的只寫規格、`need`＝「需要資料：…」、不寫程式（使用者說要才去補資料）。
4. `TZ=Asia/Taipei python3 scripts/run_cands.py --check` 與 `python3 -m pytest -q tests/test_cands.py tests/test_candspec.py` 全綠
   → `git add config/strategy_candidates.json arm/lab/cands` → commit「chore: 策略候選 {編號} {名稱}」→ push 本會話分支。
   **push 就觸發合併通道**：用 main 的檢查、回測（指數型＝xstrat、台股個股＝回測方法 v3、美股個股＝ussxbook；有美股的另外拿資料分支）、
   用到未來資料的兩道檢查、放進計畫試算；**新候選乾淨地算完才併進 main**（規格、程式、結果同一筆 commit），再派 daily.yml 重建頁面。
5. 等結果（Bash `run_in_background` until 迴圈，每 2 分鐘 `git fetch origin main`，最多 45 分鐘）：`origin/main` 的
   `data/lab/cands_research.json` 出現這幾個編號＝安靜結束（星期一 06:35 推播會帶「策略候選：新增…」一行）。
   沒出現＝讀那一輪 strategy_cands.yml 的日誌：程式出錯或「用到未來的資料」→ 修程式（**還沒進 main 的候選可以改**；修的是程式錯誤，
   不是看了成績調參數）、重填 sha、再推一次；第二次還是不行 → 推播一句卡在哪裡。
- **使用者的決定**（任何對話回「試用 X／納入 X／不納入 X」）：改 `config/strategy_board.json` 的 `cand`（`{編號: {dec: trial／adopt／reject,
  d: 日期, why: 原因}}`）→ push 任何 `claude/**` 分支 → 合併通道只拿 `cand` 那一段併進 main（其他欄位照 main）。
  試用＝每週日排程記紙上成績（`data/lab/cands_live.json`，只增不改），滿 63 個交易日列照做對一直抱著；
  納入＝全部策略表「觀察中・納入，等放上選股頁」，選股頁加上這條策略的卡片（pickpage，另外規劃、先問使用者）時用 override 改「使用中」；不納入＝淘汰一行。
  （2026-10-28 前是「等計畫改版」：交易計畫出新版本才改使用中；配置頁拿掉之後改成看選股頁。）
- **不做**：通用規則語言（每條候選都是一支小程式＋鎖定）、看過結果改參數（要改＝新的編號，`prev` 指到舊的）、網頁上的按鈕。

## 指令：「整理知識庫」（2026-10-29 建立；LLM Wiki 第 4 段，docs/llm_wiki_plan.md 第 5、14 節）

知識庫＝`wiki/`（目錄 `wiki/index.md`、日誌 `wiki/log.md`）；2026-10-29 瘦身後頁面就是正本，CLAUDE.md 只留鐵則與五個指令（指令在 wiki/ops/ 的整理版要和這裡一致）。使用者 2026-10-29 的決定：
**做完事順手改**（只改相關的那一頁、`wiki/log.md` 加一行 `## [日期] 操作 | 標題`）**＋你說才整理**——全面檢查只在使用者打「整理知識庫」時做，
不排程、不在別的指令裡順便做。**大原則（使用者 2026-10-29 原話）：「切記你的架構要清晰不要變成會浪費更多的token 然後絕對不要影響到本來的產出品質跟架構邏輯
不要因為這個把本來的根本弄掉了」「一些沒用或是明顯被覆蓋的規則可以清除，但我上面提到的大原則絕不要忘記」。**
全程不跑資料抓取腳本、不動 `reports/**`，也不碰 push 會觸發 workflow 的檔（`data/etf_upcoming.json`、`config/holding_profiles.json`、
`config/index_reviews.json`、`config/strategy_candidates.json`、`config/strategy_board.json`、`arm/lab/cands/**`）：

1. `python3 scripts/wiki_lint.py`（只讀）：錯＝連結斷、頁沒列進目錄、頁太長（1.5 萬字）、頁首格式、CLAUDE.md 的事實記號頁上不見了、
   路徑規則 `.claude/rules/*.md` 的 paths 對不到檔或指到不存在的頁；提醒＝「現在怎麼運作」「不能改的規則」兩節提到的檔案或 `模組.函式` 找不到、
   沒有任何頁連到的頁、CLAUDE.md 太長。
2. 錯一定修。提醒逐條看：改名或拿掉了 → 改那一頁（舊說法移到「歷史」）；本來就該這樣的留著。
3. `git log --since=<日誌上次「整理」的日期>` 看之後動過的程式，對照相關頁：互相矛盾、被新規則蓋掉的舊規則 → 舊的移到「歷史」或刪掉；
   刪事實記號要在日誌寫 `- 刪：`記號`——原因`（`scripts/wiki_facts.py` 才不會報不見）。有矛盾不確定哪個對 → 先問使用者，不要猜。
4. `python3 scripts/wiki_facts.py` 與 `python3 -m pytest -q tests/test_wiki.py` 全綠 → 日誌加一行 `## [日期] 整理 | 摘要`
   → commit「chore: 整理知識庫 {日期}」push 本會話指定分支 → 開 PR、merge 進 main。
5. 回報：改了哪幾頁、刪了什麼、有沒有要使用者決定的矛盾。

路徑規則 `.claude/rules/*.md`＝讀到某些檔時自動載入的提醒（開頭 `paths:` 列檔案樣式，內容＝該先讀哪一頁＋幾條不能改的規則）；
頁改名或拆頁時要一起改規則（體檢會擋）。

## 指令：「排程搬家」（2026-07-24 建立；2026-08-03 擴為三個；2026-08-07 四個；2026-08-10 五個；2026-10-24 六個；2026-10-30 起**七個 Routine 一起搬**）

使用者在**任何**對話窗打**「排程搬家」**（或「搬排程」）＝把**全部七個** Routine（每日：06:35 全部更新、
15:33 盤後籌碼、18:58 晚間 NAV·PCF、05:08 美股收盤序列、20:47 個股報告；每週：週一 08:05 ETF 募集週掃、週日 19:47 策略探勘週報）改綁到**當前**
對話窗。**不要詢問、不要查證其他東西、不改任何檔案、不 commit**——固定「list → 建七個 → 刪舊的」收工（最省 token）：

1. `list_triggers`（先用預設 limit；找不到再用 cursor 翻頁）→ 找**名稱以「復華基金雷達」開頭且
   `enabled:true`** 的 Routine（正常應有 7 個；歷史上只有 1／3／4／5／6 個＝尚未擴編，照樣往下走）。
   全部的 `persistent_session_id` 都已是本會話 → 回一句「排程已綁本視窗」結束。
   · **⚠ 輸出會超過工具上限**（2026-08-07 實測 70KB／一行）：帳號裡累積數十個 `send_later` 一次性
     trigger，`list_triggers` 回應會被截斷並存成檔案。**別開子代理讀全文**——直接
     `python3 -c` 讀那支檔 `json.loads` 後只印 `id｜name｜cron_expression｜enabled｜persistent_session_id`
     一行一個，秒級收斂。要看某支的 prompt 原文則印
     `job_config.ccr.events[*].data.message.content`（**頂層沒有 `prompt` 欄位**，只有這裡有）。
2. `create_trigger` ×7（預設自綁本會話，**不帶** `persistent_session_id`／`create_new_session_on_fire`；
   prompt 用下方各自的原文照抄、一字不改）：
   - `復華基金雷達 每日全部更新(台北 06:35・07:03 前完成)`｜cron `35 22 * * *`
   - `復華基金雷達 盤後籌碼即時更新(台北 15:33)`｜cron `33 7 * * 1-5`
   - `復華基金雷達 晚間NAV·PCF即時更新(台北 18:58)`｜cron `58 10 * * 1-5`
   - `復華基金雷達 美股收盤序列更新(台北 05:08)`｜cron `8 21 * * 1-5`
   - `復華基金雷達 ETF募集週掃(台北週一 08:05)`｜cron `5 0 * * 1`
   - `復華基金雷達 個股報告(台北每天 20:47)`｜cron `47 12 * * *`
   - `復華基金雷達 策略探勘週報(台北週日 19:47)`｜cron `47 11 * * 0`
3. `delete_trigger` 逐一刪掉步驟 1 找到的舊 Routine（機制備忘：`update_trigger` 改不了綁定會話、跨會話
   update 也被組織政策擋，但**跨會話 delete 可行**——2026-07-24 實證；所以搬家＝建新＋刪舊，不是改舊）。
4. 一句話回報：七個新 trigger id＋各自下次觸發時間。create_trigger 若警告「no MCP connectors」**可忽略**
   （SOP 第 7 步走 push 自動觸發、驗證用 git，不依賴 MCP）。
   · **步驟 1 若查到「本檔沒記載」的復華 Routine**（2026-08-07 就是這樣發現 05:08 那支）：照樣搬，
     prompt 從舊 trigger 的 `job_config` 原文照抄，並在回報時提一句「本檔要補記」。
5. **回報時務必提醒使用者「模型要重設」**（2026-07-27 使用者踩到：以為設過 sonnet，實際每日跑都是
   新視窗的預設模型）。機制：trigger 的 `job_config` **沒有 model 欄位**，只有 `persistent_session_id`
   ——每日火進哪個視窗，就用**那個視窗當下的模型**。舊視窗設過的 `/model` **不會**跟著搬家過來，
   新視窗一律回到預設。所以每次搬家後，使用者要在**新視窗**自己打一次 `/model sonnet`
   （容器內 Claude 無法代勞，`update_trigger` 的 model 參數對綁定會話的 routine 也無效）。

**「生效條件＝排程搬家」怎麼讀（2026-10-29 查證）**：各段寫的「merge 進 main 後做一次排程搬家才生效」，意思是排程會話 checkout 的分支上要有那份改動
（提示包 gen_*.py、push 觸發的 workflow 檔、`.claude/settings.json`、`check_reports.py`——`check_reports.py` 只在排程會話裡跑，CI 沒跑）。
2026-10-17 起排程會話每天 06:36 先把 origin/main 合併進自己的分支（`git log --first-parent` 每天一筆「merge main」，10/22～10/28 天天都有），
所以**現在 merge 進 main 之後下一班就生效，不必為了生效搬家**；只有排程會話的分支停止合併 main 時才要搬。
查法：`list_triggers` 看綁定會話 → `get_session` 看分支 → `git log --first-parent origin/{分支}` 找最近幾天的「merge main」。
2026-10-29 查：六個排程都綁在 2026-10-16 開的視窗（分支 `claude/exciting-cerf-isj9q7`）。

Routine prompt 原文①——每日全部更新（06:35）：

> （排程自動觸發）全部更新。依 repo CLAUDE.md「指令：全部更新」SOP 完整執行：產提示包 → 平行子代理 WebSearch 產當日新聞（美股 v1/v2、台股、總經、行事曆；嚴守提示包版型——含分析深度六條與每卡 **漲跌分析** 欄（粗體標籤）／禁用詞／每卡連結）→ gen_*.py --check 與 check_reports.py 全 🟢 → 重建儀表板 → pytest 全綠 → commit+push 到本會話指定分支（push 動到 reports/** 會自動觸發 daily.yml）→ 等 main 前進後驗證（新聞今日、產表時戳為 CI、nav_date 推進）。完成或失敗都用 PushNotification 推播一句話結果給使用者（成功：當日 3 條市場重點摘要＋籌碼雷達兩行——git show origin/main:data/lab/val_log.json 取 days 最後一天的 push 欄原文照貼（今天開盤／收盤要做的買賣；有驗證事件才有第二行），讀不到就省略、不擋推播；失敗：卡在哪一步＋影響）。不可宣稱「線上已生效」（本環境看不到 Vercel）。若工作樹有未完成的其他工作，先 stash 或用獨立分支，勿混入每日更新 commit。

Routine prompt 原文②——盤後籌碼即時更新（15:33）：

> （排程自動觸發）盤後籌碼即時更新——GitHub cron 實測遲 1~3 小時，本 Routine 負責準時；全程只做三件事、不跑任何資料抓取腳本、不動 reports/**：① 用 mcp__github__actions_run_trigger（method=run_workflow、workflow_id=afterhours_refresh.yml、ref=main）觸發盤後刷新，成功觸發即收工、不等它跑完；MCP 不可用時備援＝在本會話指定分支寫 .ping/afterhours（內容任意）後 git add -f、commit、push——該路徑 push 會自動觸發同一 workflow。② 前十大簡介缺口順手補（使用者 2026-08-12：不佔早上、掛在本班——本班最輕且在晨間持股抓取之後）：git fetch origin main 讀 data/holdings_intro_gap.json，count=0 → 跳過；count>0 → 依 CLAUDE.md 步驟 9⑤ 極簡迴路：每檔 1 次 WebSearch 查證（公司本業／代號／國別）→ 補 config/holding_profiles.json（{原字串:{intro,ticker,country,verified}}，intro 純事實、避開禁用詞）→ python3 -m pytest -q tests/test_holdings_intro.py → commit「chore: 補持股簡介 N 檔」push 本會話指定分支——push 自動觸發 daily.yml 併檔＋重建上線，不需 PR、不需監看。③ send_later 排 60 分鐘後自驗：git fetch origin main 讀 data/macro_chips.json，若為交易日（以證交所官方休市表為準：python3 -c "from arm import twholidays,clock; print(twholidays.is_closed(clock.today_tw()))" 印 False 才是交易日）而 inst_total 仍缺今日 → 補 dispatch 一次、再 send_later 25 分鐘後檢查，仍缺才 PushNotification 一句話（缺什麼＋afterhours run 日誌看到的原因）；資料已到或休市 → 安靜結束、不推播、不留言（使用者 2026-08-03 指定「失敗才推播」）；若②有補簡介，同回合加驗 origin/main 的 data/holdings_intro_gap.json 已歸 0，仍 >0（分支 workflow 檔太舊、併檔通道沒生效）→ mcp__github__actions_run_trigger dispatch daily.yml（ref=main、news_ref=本會話指定分支）一次即可修復。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

Routine prompt 原文③——晚間 NAV·PCF 即時更新（18:58）：

> （排程自動觸發）晚間數據即時更新（基金 NAV＋主動式 ETF 當日 PCF）——不跑任何資料抓取腳本、不動 reports/**：① mcp__github__actions_run_trigger 連發兩個 dispatch（皆 ref=main）：afterhours_refresh.yml（18 時後場次會加抓基金 NAV）與 etf_holdings.yml；MCP 不可用時備援＝push .ping/afterhours 哨兵（只能觸發前者，後者靠其 17:40 cron 遲到自癒即可）。② send_later 排 45 分鐘後自驗：git fetch origin main，a) data/funds/_index.json 最新 nav_date ≥ 上一交易日、b) data/etf_holdings.json 本家主動式（00991A）揭露日已推進（休市日無新 PCF 屬正常、勿誤報）；異常 → 補 dispatch 一次、25 分鐘後仍異常才 PushNotification 一句話。③ 自驗回合結束前再 send_later 一個台北 23:20 的夜檢：讀 origin/main 的 data/macro_chips.json 與 data/afterhours_alert.json，交易日而 margin_bal 缺今日或 alert missing 非空 → PushNotification 一句話（22:05 cron 整班消失時這是唯一的主動警報）；正常 → 安靜結束。皆「失敗才推播、成功安靜」。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

Routine prompt 原文④——美股收盤序列更新（05:08，2026-08-05 建立、2026-08-07 補記本檔）：

> （排程自動觸發）美股收盤序列更新（費半 ^SOX／台積電 ADR 昨夜收盤入檔，供 06:35 晨報引用；台北 05:08＝美東收盤後，夏令 17:08／冬令 16:08）——全程不跑任何資料抓取腳本、不動 reports/**：① 用 mcp__github__actions_run_trigger（method=run_workflow、workflow_id=afterhours_refresh.yml、ref=main）觸發刷新，成功觸發即收工、不等它跑完；MCP 不可用時備援＝在本會話指定分支寫 .ping/afterhours（內容任意）後 git add -f、commit、push——該路徑 push 會自動觸發同一 workflow。② send_later 排 35 分鐘後自驗：git fetch origin main 讀 data/macro_chips.json，series.sox 與 series.tsm_adr 須含最近一個美股交易日（以前一美東平日為準；美股休市日無新 bar 屬正常、勿誤報——休市日以 arm/usnews._US_MKT_HOLIDAYS（NYSE 公告表）為準）；缺 → 補 dispatch 一次、再 send_later 20 分鐘後檢查，仍缺才 PushNotification 一句話（缺什麼＋afterhours run 日誌看到的原因）；已到或休市 → 安靜結束、不推播（失敗才推播）。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

Routine prompt 原文⑤——ETF 募集週掃（週一 08:05，2026-08-10 建立）：

> （排程自動觸發）ETF 募集週掃——找到新 ETF 募集資訊、主動更新「即將登場」（使用者 2026-08-10 指示：主動更新、一週一次）。依 repo CLAUDE.md「指令：ETF 募集週掃」SOP 執行：全程不跑資料抓取腳本、不動 reports/**、只改 data/etf_upcoming.json。① git fetch origin main 讀 origin/main 的 data/etf_upcoming_gap.json（CI 自動發現的漏網檔）與 data/etf_upcoming.json 現況，pytest tests/test_etfwatch.py 看 stale guard 有無紅；② WebSearch 盤點（鉅亨 IPO 頁 fund.cnyes.com/IPO/index.htm＋MoneyDJ 新基金頁＋工商時報／經濟日報「投信新基金」稿，容器擋原頁就用搜尋摘要），逐檔兩來源核對：新核准檔補登（時程未定 raise_hint＋asof、未派碼 code:null）、hint 檔補正式日期、募集期間／掛牌日／配息頻率異動修正、掛牌逾期條目清理；海外被動指數檔 track:false；本家復華新檔最優先、絕不可漏；③ 更新頂層 as_of＝今日 → pytest 全綠 → commit「chore: ETF 募集週掃 {日期}」push 本會話指定分支（push 動到該檔自動觸發 daily.yml 併入 main 重建上線，不需人工 merge）；③-b 依 CLAUDE.md 週掃步驟 2.5 維護 config/index_reviews.json（被動指數審核時程與官方結果：只改查得到官方公告的日期與名單、不猜，as_of＝今日，pytest tests/test_lab.py 須綠，與 etf_upcoming 同一個 commit push）；④ 有異動 → PushNotification 一句話列出異動檔；無異動 → 安靜結束不推播；失敗 → 推播卡在哪一步。

Routine prompt 原文⑥——策略探勘週報（週日 19:47，2026-10-24 建立）：

> （排程自動觸發）策略探勘週報——依 repo CLAUDE.md「指令：策略探勘週報」SOP 執行；全程不跑資料抓取腳本、不動 reports/**。① git fetch origin main 後把 origin/main 合併進本會話指定分支（候選的程式與檢查要是最新的）；讀 config/strategy_candidates.json 與 config/strategy_board.json 的 cand：還沒決定的已有 10 條 → 不找，PushNotification 一句「策略候選已有 N 條還沒決定，請回試用／納入／不納入」後結束。② WebSearch 找新策略：來源限學術（SSRN、arXiv q-fin、期刊）、AQR／Alpha Architect／Quantpedia／Research Affiliates 等量化研究、台灣投信券商研究報告；挑最多 2 條「規則寫得清楚、有公開成績、現有資料做得出來」、和已有的候選與頁面上的策略不重複的；找不到就安靜結束、不推播。③ 每條寫規格一筆（config/strategy_candidates.json 的 items；欄位照 arm/lab/candspec.py：id 接續編號、found＝今天、name、mk、engine、kind、how 一句白話規則、src 至少一條 https 原文連結、why、p、grid、各型態要的 H／b／pick／ex、sha）＋程式一支 arm/lab/cands/{編號}.py（照 arm/lab/cands/__init__.py 的範本；參數從 p 讀、只用那一天收盤以前的資料、台股財報與月營收一律經過 cands.Fin）；sha 用 python3 -c "from arm.lab import candrun as R; print(R.sha_file(R.PROG/'c00X.py'))" 填；資料不夠的只寫規格、need＝「需要資料：…」、不寫程式。④ TZ=Asia/Taipei python3 scripts/run_cands.py --check 與 python3 -m pytest -q tests/test_cands.py tests/test_candspec.py 全綠 → git add config/strategy_candidates.json arm/lab/cands → commit「chore: 策略候選 {編號} {名稱}」→ push 本會話指定分支（push 自動觸發 strategy_cands.yml：用 main 的檢查、回測、乾淨算完才併進 main、重建頁面）。⑤ 等結果：Bash run_in_background 的 until 迴圈（每 2 分鐘 git fetch origin main，最多 45 分鐘）等 origin/main 的 data/lab/cands_research.json 出現這幾個編號：出現＝安靜結束（星期一 06:35 推播會帶「策略候選」一行）；45 分鐘沒出現＝讀 strategy_cands.yml 那一輪的日誌（mcp__github__actions_list／get_job_logs）：程式出錯或用到未來的資料就修程式（還沒進 main 的候選可以改；修的是程式錯誤，不是看了成績調參數）、重填 sha、再推一次；第二次還是不行 → PushNotification 一句卡在哪裡。

Routine prompt 原文⑦——個股報告（每天 20:47；2026-10-30 建立時是週六 14:17 週更，同日改成每天）：

> （排程自動觸發）個股報告——依 repo 技能 `.claude/skills/equity-report/SKILL.md` 執行（規劃 docs/lab_equity_report_plan.md 第 12 節、docs/lab_eq_request_plan.md 第 3.3 節）；全程不跑資料抓取腳本、只新增 reports/eq/** 的檔（官方文件由 CI 抓）。① git fetch origin main 後把 origin/main 合併進本會話指定分支；跑 TZ=Asia/Taipei python3 scripts/eq_queue.py（今天要做的最多 3 家：先做網頁申請的、再補接下來 2 個交易日要買還沒有報告的、週六另加季更新；每家標來源）：「今天做 0 家」→ 安靜結束、不推播。①-b 台股公司先抓官方文件包（docs/lab_eq_docs_plan.md）：TZ=Asia/Taipei python3 scripts/eq_docs_req.py --send tw:代號…（一次送完，印出編號）→ Bash run_in_background 跑 --wait 編號 --timeout 1500（和產業報告同時進行）；每家照它印的處理：🟢 照常寫；「今天不寫」＝文件包沒抓到，這家今天跳過、明天名單還會有它；「連續 2 天沒抓到」＝照寫、資料侷限寫明。② 先列出要做的公司需要的產業報告（reports/eq/ind/ 31 天內沒有的），每個產業派一個子代理照技能 references/industry.md 做、check_eq.py 🟢；產業報告都好了，再每家公司各派一個子代理照技能步驟做（資料包 scripts/eq_facts.py 代號 --docs .eqdocs/編號 → 先整份讀 .eqdocs/編號/tw-代號.md 再上網查媒體 → 估值 → 寫報告 → scripts/check_eq.py 全 🟢），子代理只回三行。③ 主會話再跑一次 TZ=Asia/Taipei python3 scripts/check_eq.py 全 🟢 → git add 這次新增的 .md 與 .facts.json（寫明路徑）→ commit「chore: 個股報告 {日期}」→ push 本會話指定分支（push 動到 reports/eq/** 會觸發 daily.yml：用 main 的檢查、過了才併進 main 並建頁；報告進 main 之後 eq_inbox.yml 會在申請單回連結並關單）→ eq_docs_req.py --drop 編號（刪本機文件包）。④ 等結果：Bash run_in_background 的 until 迴圈（每 2 分鐘 git fetch origin main，最多 45 分鐘）等 origin/main 出現這幾份報告：出現 → PushNotification 一句「個股報告：{公司 評等（來源）}…（研究紀錄頁可看）」，有今天跳過的加「文件包沒抓到、明天重試：{公司}」；45 分鐘沒出現 → 讀那一輪 daily.yml 的日誌找原因、修報告再推一次，第二次還是不行 → 推播卡在哪一步。推播不寫目標價；評等不影響任何策略、交易計畫或選股名單。

## 已知環境限制與防呆（曾踩過的坑，不要再犯）

- **排程會話的 send_later／create_trigger 被 MCP 審批擋下：`MCP error -32003: MCP tool call requires approval`（2026-08-10 踩坑）**：
  15:33 盤後 Routine 步驟①觸發 workflow 成功（**同回合 github MCP 的 actions_run_trigger 完全沒被擋**、
  當日資料 15:36 照樣入庫），但步驟② send_later 與備援 create_trigger 連續 -32003——無人值守沒人能按核准，
  自驗鏈整條排不了。**同日診斷：非平台級強制審批**——另開互動會話呼叫 send_later 一次成功（無審批即回
  trigger_id），即審批要求是「逐會話授權」：排程綁定會話少了 claude-code-remote 工具的預先核准就會中。修法三道：
  ① **`.claude/settings.json`（2026-08-10 入庫）`permissions.allow` 預先核准**：官方文件確認
    `mcp__<伺服器>__<工具>` 允許規則可免互動核准（伺服器名的連字號／空白會正規化成底線、比對不分大小寫）。
    清單＝claude-code-remote 六個 trigger 工具＋github actions 四工具（後者目前沒被擋，一併免疫）。
    **生效條件＝排程會話 checkout 的分支上要有這支檔**：先 merge 進 main，再做一次「排程搬家」
    （新會話自最新 main 分岔）才會被讀到——與步驟 9⑦ YOUTUBE_API_KEY workflow 檔同型的傳播機制。
  ② **無 MCP 自驗備援（Routine prompt ②③④ 原文已補同一句）**：send_later 回 -32003 → 改用
    `Bash run_in_background` 背景 until 迴圈（每 5 分鐘 `git fetch origin main` 驗一次目標欄位，
    到自驗時點仍缺就輸出 MISSING 結束）；背景任務結束會喚醒會話，續走「補 dispatch → 再等 → 仍缺才推播」。
    注意它只在「容器活著」時有效（閒置回收無官方保證）——跨容器持久性只有 send_later／Routine 有，
    所以 send_later 仍是首選、這是備援；全鏈失敗的最後防線本來就在（CI 看門狗 afterhours_alert＋
    run ❌ failure 信＋cron 兜底）。CronCreate／Monitor 同為會話行程內存機制，**不可**當持久排程替代。
  ③ **立即緩解（不必等 merge）**：使用者在排程綁定的主會話請 Claude 呼叫一次 send_later 並按
    「一律允許」——該會話建立核准後，後續無人值守回合即可通過（此核准能否跨容器重佈建存活，
    官方未載明；根治仍靠 ①）。
