# CLAUDE.md — 復華基金雷達 · 給 Claude 的操作規則

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
     （2026-10-13 起，見下方「行事曆台灣區與精簡規則」專節）；
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
   **2026-10-13 起：頭段總覽／速覽抽得到**（美股 v1／總經「…總覽」、台股「盤前／盤後速覽」；見列印版專節踩坑⑤）／
   **2026-10-13 起：行事曆台灣區與精簡上限**（台／台股列或「本週無」註記、總列數 ≤30、引言 ≤220 字）／
   行事曆為今日）——「摘要／影響分析皆空」該項是 2026-07-31 新增的防呆，
   🔴 訊息會直接指出是標籤沒加 `**粗體**`（見步驟 2 與下方專節），照著把該報告的 `N. 標籤：` 改成
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
       當天 15:33 Routine 準時開跑、`afterhours_refresh` run **success**、15:34 就 commit 進 main（`21b5bcb`），
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
     - Vercel `vercel.json` 已設 `Cache-Control: no-cache`（2026-08-14 多人化 Phase 1 由 no-store 改，**兩支 vercel.json 根目錄與 dashboard/ 都要一致**）：瀏覽器可存但**每次都必須向伺服器 revalidate**——內容沒變回 304（~1KB）、變了才全量下載，300 人重複造訪省流；**「線上看到舊的一律是「沒部署」而非快取」的診斷鐵則不變**（每次都 revalidate，瀏覽器快取不可能是原因），別叫使用者清快取白忙。304 是否生效看對時哨兵日誌的「（記錄）帶 If-None-Match 重打」行。
   - **⑤ 前十大簡介缺口（2026-07-23 使用者：一再漏掉；2026-08-12 全自動落地；同日改「主責＝15:33 盤後班」）**：讀
     `git show origin/main:data/holdings_intro_gap.json`。**晨間本步驟只讀不補**（使用者 2026-08-12：
     不佔早上、跟最簡單的那班）——count>0 → 成功推播裡帶一句「缺 N 檔簡介，15:33 班會補」即可；
     **補齊主責＝15:33 盤後籌碼 Routine 步驟②**（該班最輕、又在晨間持股抓取之後，缺口當天下午清）。
     **連兩天 count>0**（昨天下午沒清＝排程搬家前過渡期或該班失效）才在晨間親自跑下列迴路並查原因。
     **極簡迴路**（15:33 班與晨間 backstop 共用；全程 ~5 分鐘、不跑任何抓取腳本）：
     ① gap 檔 `items[].name` 就是快照原字串——**每檔 1 次 WebSearch** 查證（公司本業／代號／國別）；
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
     機制與坑見下方「新 ETF『自動發現』層」專節。
   - **⑨ 籌碼雷達兩行（2026-10-15 使用者同意：「06:35 推播多帶兩行」）**：成功推播在 3 條市場重點之後，附上
     `git show origin/main:data/lab/val_log.json` 最新資料日（`days` 最後一個鍵）的 `push` 欄**原文照貼**：
     第一行＝下一個交易日開盤／收盤要做的買賣（例「10/16（五）沒有排定的買賣。」），第二行＝策略驗證事件（有事件才有）。
     檔案讀不到或沒有 `push` 就省略這兩行、**不擋推播**。這兩行由 CI 重建籌碼雷達時產生（`arm/lab/valog.py`，見「版面 v4」專節），
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
   漏網檔，見「新 ETF 自動發現層」專節；`items`＝待登錄的已核准／募集中／已掛牌檔＋
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

## 指令：「排程搬家」（2026-07-24 建立；2026-08-03 擴為三個；2026-08-07 四個；2026-08-10 起**五個 Routine 一起搬**）

使用者在**任何**對話窗打**「排程搬家」**（或「搬排程」）＝把**全部五個** Routine（每日：06:35 全部更新、
15:33 盤後籌碼、18:58 晚間 NAV·PCF、05:08 美股收盤序列；每週：週一 08:05 ETF 募集週掃）改綁到**當前**
對話窗。**不要詢問、不要查證其他東西、不改任何檔案、不 commit**——固定「list → 建五個 → 刪舊的」收工（最省 token）：

1. `list_triggers`（先用預設 limit；找不到再用 cursor 翻頁）→ 找**名稱以「復華基金雷達」開頭且
   `enabled:true`** 的 Routine（正常應有 5 個；歷史上只有 1／3／4 個＝尚未擴編，照樣往下走）。
   全部的 `persistent_session_id` 都已是本會話 → 回一句「排程已綁本視窗」結束。
   · **⚠ 輸出會超過工具上限**（2026-08-07 實測 70KB／一行）：帳號裡累積數十個 `send_later` 一次性
     trigger，`list_triggers` 回應會被截斷並存成檔案。**別開子代理讀全文**——直接
     `python3 -c` 讀那支檔 `json.loads` 後只印 `id｜name｜cron_expression｜enabled｜persistent_session_id`
     一行一個，秒級收斂。要看某支的 prompt 原文則印
     `job_config.ccr.events[*].data.message.content`（**頂層沒有 `prompt` 欄位**，只有這裡有）。
2. `create_trigger` ×5（預設自綁本會話，**不帶** `persistent_session_id`／`create_new_session_on_fire`；
   prompt 用下方各自的原文照抄、一字不改）：
   - `復華基金雷達 每日全部更新(台北 06:35・07:03 前完成)`｜cron `35 22 * * *`
   - `復華基金雷達 盤後籌碼即時更新(台北 15:33)`｜cron `33 7 * * 1-5`
   - `復華基金雷達 晚間NAV·PCF即時更新(台北 18:58)`｜cron `58 10 * * 1-5`
   - `復華基金雷達 美股收盤序列更新(台北 05:08)`｜cron `8 21 * * 1-5`
   - `復華基金雷達 ETF募集週掃(台北週一 08:05)`｜cron `5 0 * * 1`
3. `delete_trigger` 逐一刪掉步驟 1 找到的舊 Routine（機制備忘：`update_trigger` 改不了綁定會話、跨會話
   update 也被組織政策擋，但**跨會話 delete 可行**——2026-07-24 實證；所以搬家＝建新＋刪舊，不是改舊）。
4. 一句話回報：五個新 trigger id＋各自下次觸發時間。create_trigger 若警告「no MCP connectors」**可忽略**
   （SOP 第 7 步走 push 自動觸發、驗證用 git，不依賴 MCP）。
   · **步驟 1 若查到「本檔沒記載」的復華 Routine**（2026-08-07 就是這樣發現 05:08 那支）：照樣搬，
     prompt 從舊 trigger 的 `job_config` 原文照抄，並在回報時提一句「本檔要補記」。
5. **回報時務必提醒使用者「模型要重設」**（2026-07-27 使用者踩到：以為設過 sonnet，實際每日跑都是
   新視窗的預設模型）。機制：trigger 的 `job_config` **沒有 model 欄位**，只有 `persistent_session_id`
   ——每日火進哪個視窗，就用**那個視窗當下的模型**。舊視窗設過的 `/model` **不會**跟著搬家過來，
   新視窗一律回到預設。所以每次搬家後，使用者要在**新視窗**自己打一次 `/model sonnet`
   （容器內 Claude 無法代勞，`update_trigger` 的 model 參數對綁定會話的 routine 也無效）。

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

## 每日固定時間自動更新（2026-07-18 建立；同日改「火進主會話」模式）

- **排程 Routine**（claude.ai Routines）：每天 **台北 06:35**（UTC 22:35）**火進主會話**跑「全部更新」SOP。
  目標：**07:03 前線上可看當日內容**（2026-07-20 使用者指示；實測全程 15–28 分，06:35 起跑最壞壓線、
  一般 06:55 完成）。**trigger id 與綁定會話會隨「排程搬家」（見下方專節）改變**——一律以
  `list_triggers` 實查為準，本檔不再記死 id（2026-07-24 起；使用者約每 3–5 天在新視窗搬一次）。
- **為何不用「開新會話」模式（2026-07-18 實測兩次全滅，勿走回頭路）**：fresh-session 點火綁的環境
  （env_01FK…「化學」）沒掛本 repo source，會話起來連最小 heartbeat push 都做不到（第二次點火帶
  「3 分鐘心跳測試」指令仍 18 分鐘零輸出）。改火進主會話後有 repo、有 GitHub MCP、有完整脈絡；
  「火進既有會話」模式在本帳號有 07-13 send_later 成功先例。完成/失敗以 PushNotification 推播使用者。
- **想省 token 改用 sonnet 跑排程（2026-07-23 使用者需求）＝目前工具做不到，機制備忘**：
  ① 本排程 Routine 綁在**持久主會話**，其模型「跟著該會話走」——不是跟著 trigger；
  ② `update_trigger` 改模型全組織停用（回 `model_update_disabled`）；改綁在其他會話的 trigger 也被擋；
  ③ 新開會話仍預設落在無 repo 的「化學」env（同上兩次全滅主因）。
  **唯一可行槓桿＝在「排程當前綁定的主會話」內執行 `/model sonnet`**（會固定生效、
  之後每日火進該會話即用 sonnet）；此動作只能由使用者在該會話操作，容器內 Claude 無法代勞。
  若日後組織開放 routine 模型設定、或把本 repo 掛上某個可排程 env，才談得上「fresh sonnet 會話」路徑。
- 排程點火的回合若 MCP 不可用，SOP 第 7 步照樣走「push 自動觸發」；驗證用 git（fetch origin main
  看是否前進＋檢查檔案內容）即可。
- **盤後數據刷新 `afterhours_refresh.yml`（2026-07-31 建；2026-08-03 大改——見下）**：
  抓取（失敗沿用既有落檔）→ 看門狗寫警示 → check_numbers → 重建 → commit → Deploy Hook →
  完整性斷言；**data/ 無任何變更（休市日）就早退**、不空 commit。不碰 `reports/**`。
- **⚠ GitHub cron 是 best-effort、本 repo 實測「系統性遲到 1~3 小時、偶爾整班消失」（2026-08-03 定調，
  勿再把準時性寄託在 cron 上）**：etf_holdings 17:40 班連五個交易日遲 1.5~3 小時；afterhours 兩班
  自 07-31 建立以來**從沒準時開過工**（史上首次 schedule 觸發＝08-03 18:56，當晚 22:05 班整班消失）。
  這與「三大法人從不抓當日」的程式 bug 疊加成 08-03 的靜默失敗——修法＝三層：
  ① **準時觸發主路徑＝Routine**（15:33 盤後籌碼、18:58 晚間 NAV·PCF，火進主會話打 workflow_dispatch，
    秒級開跑；prompt 原文見「排程搬家」節）；
  ② **cron 三班只當自癒兜底**（15:40／19:10／22:05，遲到也會到）；重複場次由
    `check_afterhours_fresh.py --guard` 守門**零請求早退**——多班次不放大對 TWSE/etfinfo 的請求，
    仍是對齊公布時點的事件驅動、**不是高頻輪詢**（07-31 與使用者確認過不做 30 分鐘輪詢，此原則不變）；
  ③ **當日完整性看門狗**（同腳本 `--write`/`--assert`；根治「run 全綠、無 commit、沒人知道」）：
    交易日（**證交所官方休市表** `arm/twholidays`；2026-10-13 前是讀行事曆市況段，見「資料可信度盤查」專節；官方表未涵蓋時退回市況段，**市況寫了日期就只認今天那一天**——2026-09-24「台股 9/25 因中秋節休市」曾把當日判成非交易日）16:30 後三大法人須含今日、22:45 後融資融券須含今日且
    NAV 不斷更，缺 → `data/afterhours_alert.json` 入板（儀表板「網頁更新時間」列紅章＋瀏覽器端
    16:40／22:50 兩個時窗的延遲橫幅）＋ workflow 最後一步 exit 1（run ❌ → GitHub 寄 failure 信）
    ＋ Routine 自驗 25~60 分後失敗才 PushNotification（使用者 2026-08-03 選「失敗才推播」）。
- **每日更新時點地圖（2026-08-03 起，台北時間；2026-08-07 補入 05:08）**：**05:08 Routine → 費半 ^SOX／
  台積電 ADR 昨夜收盤入檔**（美東收盤後，供 06:35 晨報引用）／06:15 etf_holdings cron（被動式隔夜 PCF）／
  **06:35 Routine 新聞**（push 觸發 daily.yml 全量；07:15 cron 兜底）／**15:33 Routine → 15:40·當日
  三大法人、外資期貨、ETF 當日漲跌、全球溫度計上線**（15:40 cron 兜底；**＋前十大簡介缺口順手補**，
  主責見 9⑤，2026-08-12 使用者指定掛本班）／**18:58 Routine → ~19:10·
  基金 NAV＋主動式 ETF 當日 PCF 上線**（19:10 cron 兜底；etf_holdings 17:40 cron 遲到自癒）／
  22:05 cron·融資融券（~21:30 公布）、P/C 比、NAV 掃尾／23:20 夜檢（Routine 鏈的 send_later，
  只驗不抓）。**週頻**：週一 08:05 Routine → ETF 募集週掃（WebSearch 查證後更新
  `data/etf_upcoming.json`，push 經 daily.yml 併檔自動上線）。
- **備援**：repo cron 移至**台北週一~六 07:15**（2026-07-20 起，原 06:50）——改為「事後兜底」：Routine 失敗時
  新聞沿用前日（或撿分支已推的今日新聞），但 NAV／持股／ETF 照樣更新；頁面瀏覽器端有「逾 2 天未重建」
  紅色警示橫幅當最後防線。
- **部署**：CI commit 後打 `secrets.VERCEL_DEPLOY_HOOK` 主動部署（`daily.yml`／`afterhours_refresh.yml`／
  `etf_holdings.yml` 三支皆已接好）。**2026-08-13 起 secret 已建立並驗證通過**（run 31690853627 部署步驟印
  `HTTP 201`＋Vercel 回 `PENDING` job）。**在此之前這把 secret 從沒建過**，部署一直只靠 Vercel 自動偵測
  git push（曾卡 Initializing／漏接），偵測漏接就會出現「資料準時進 main、CI 全 success、線上卻停在舊版」
  ——原委與診斷順序見步驟 9 的「主動部署」與其下踩坑條。**如使用者回報線上沒更新，先讀該班 run 部署步驟的
  日誌**（印 `HTTP 2xx`＝真的打出去了；印「未設…跳過」＝secret 被刪或失效），再問 Vercel Deployments 對到哪個 commit。
- **⚠ Vercel 免費方案每日部署上限（2026-10-15 踩坑：對時哨兵連三輪紅、線上停在 20:53）**：每推一次 `claude/**`
  工作分支，Vercel 就多做一次預覽部署；main 每筆 CI commit 又部署兩次（自動偵測＋Deploy Hook）。當天工作分支推了
  幾十次、超過上限後，Deploy Hook 照樣回 `HTTP 201`，但部署建不起來，線上停在舊版。**診斷**：哨兵紅、部署步驟
  卻印 2xx 時，讀 PR 的 commit status（`pull_request_read` get_status，context＝Vercel），描述是
  「Deployment rate limited — retry in 24 hours」就是這個。**對策**：當天少推分支，等限制解除，下一班 CI 會自動部署；
  根治是在兩支 vercel.json 加 `"git": {"deploymentEnabled": {"claude/**": false}}`，停掉工作分支的預覽部署
  （2026-10-16 使用者同意、已改，`tests/test_multiuser_hardening.py` 守；main 不得關掉）。
- **多人化硬化（2026-08-14；規劃全文 `docs/multi_user_plan.md`。實際規模＝**家人約 30 人分享、非商用**，
  Vercel Hobby 合規、無需升 Pro；**讀取端不隨人數產生成本**——CI 分鐘按排程固定、資料來源站只有 CI 會碰、
  使用者只從 CDN 抓單一自包 HTML，30 人約 0.4GB/月＝免費額 0.4%。硬化的價值主要在**省維護者自己的
  除錯時間**，與人數無關）**：
  ① **對時哨兵 `scripts/check_live_deploy.py`**——三支 workflow 部署步驟後輪詢**線上頁**（Actions 網路
    可達 vercel.app，容器不行），比對 `data-gen` 產表時戳已追上 main（4 分鐘內），沒追上→run ❌ 寄信。
    根治 08-13 型「資料進 main、線上停舊版」的發現延遲；**哨兵紅≠資料有問題**（資料多半已入 main），
    診斷照上一條的順序走。② **煙霧測試 `scripts/smoke_dashboard.py`**——daily.yml 建表後 headless Chromium
    驗 console 零錯誤／關鍵區塊／`__EH`／時戳（**兩段式：env `SMOKE_ENFORCE=0` 觀察期只告警，誤報率
    歸零後改 `'1'` 攔截**——攔截＝該輪不 commit 不部署、線上維持前一版）；afterhours／etf_holdings 走
    `--lite` 零依賴結構檢查（截斷/區塊消失才紅，直接攔截）。**煙測只擋結構壞頁；數字對錯仍走 factcheck
    不擋發佈**，「防線不可硬到什麼都沒更新」原則不變。③ 長開分頁逾 6 小時提示重新整理（`fund_dashboard.py`
    頁齡 IIFE）。④ 快取 no-store→no-cache 見上方步驟 9 該條。CI 分鐘帳（2026-10-16 起 repo 已公開，一般機器不計分鐘；以下為私有時期的帳）：免費額 2,000 分/月，
    此前用量 ~1,000，哨兵＋煙測估 +200~300——**新增排程/步驟前先想分鐘帳**（獨立 30 分 cron 哨兵就是
    因 +1,440 分/月被否決改 piggyback 的）。**2026-10-16 實測帳見下一條。**
- **⚠ GitHub Actions 額度實測（2026-10-16 使用者：「會不會超過免費用量」）**：以 run 的執行時間（每輪無條件進位到分）
  估 10/1～10/16 約 **1,670 分**／免費 2,000 分——其中約 **735 分是開發**（`lab_backfill.yml` 回補 33 輪×17 分、
  開發分支推送觸發整輪 `daily.yml` 19 輪×7 分），其餘約 930 分是日常（交易日約 50～60 分、假日 10～30 分，
  月約 1,300～1,500 分）。帳單 API 的 `billable` 欄已停用（一律回 0），**正確數字只在 github.com/settings/billing**；
  額度依帳單週期重置（不一定是每月 1 號）。**用完＝私有 repo 的 Actions 全停到下個週期**（沒綁付款方式時）→ 每日資料更新全停。
  四個修法（2026-10-16）：①`daily.yml` 併檔段——推送的分支沒有 main 還沒有的今日新聞或通道檔（開發分支合併 main 後
  推送就是這樣）→ 後續步驟全跳過（`steps.merge.outputs.skip`，每輪 6～7 分 → 約 1 分）；②`daily_fund.sh`／盤後
  的抓取全部加 `timeout`（10/13、10/15 盤後兩班卡滿 30 分；09-24 的上限修法在 10/11～10/16 間不在 main 上——
  **改 workflow 檔要確認 main 上真的有**）；③建頁拿掉白跑的 P1–P7 回測、重複讀檔改 `store.memo`（85 → 65 秒）；
  ④頁面輸出固定順序（三處以集合當順序，同樣的資料每次建頁結果不同 → 每班多一筆 commit 與部署）。
  **2026-10-16 起 repo 改公開，額度問題解除**；四條修法仍保留（省時間、少部署）。`tests/test_ci_budget.py` 守這四條。**開發時少推送、回補一次跑滿再推、別為小改動 dispatch**——開發的分鐘一樣算在同一個額度。

## 已知環境限制與防呆（曾踩過的坑，不要再犯）

- **⚠ 2026-10-16 改寫過整段 git 歷史（使用者要公開 repo 前說：「把我的名字跟email拿掉」）**：
  早期 17 個 commit 作者欄的姓名、Gmail、Mac 主機名換成 `josephchan00000 <51159474+josephchan00000@users.noreply.github.com>`；
  檔案內容 `/Users/<名字>` 換成 `$HOME`、兩個 email 換成 `user@example.com`（`git filter-repo --sensitive-data-removal --mailmap --replace-text`，
  2,141 個 commit 全部改寫，每個分支的檔案內容只差 `scripts/daily_run.sh`、`scripts/cf_publish.py` 各一行）。
  · **本檔與 docs 提到的舊 commit 編號（例 `21b5bcb`、`01767f9e7`）在分支上已不存在**，新 main 從 `945a995cd` 起算。
  · **之後所有 commit 一律用 noreply 身分**（CI 與 Claude 會話本來就是）；`tests/test_privacy.py` 守程式、設定、文件不出現個人 email 與本機使用者路徑。
  · 91 個舊分支的改寫版都封存在 `claude/archive-old-branches`（每個「archive: 分支名」commit 的第二個 parent 就是該分支）。
    **這個環境的 git proxy 擋推標籤、刪分支、一次推多個分支（HTTP 403）**，一次只能推一個分支——批次整理舊分支要由擁有者在自己電腦上做，不要一個一個推來繞過。
  · 本地還是舊歷史的視窗（排程會話、舊對話）不可再推送舊分支或把 origin/main 合併進去（unrelated histories）；改寫後要「排程搬家」到新視窗。
  · GitHub 上的 PR 參照（`refs/pull/*`，使用者無法刪）還指向舊 commit，要請 GitHub 客服清除；**清除前不要把 repo 改成公開**。
  · **現況（2026-10-16）**：擁有者已在 Mac 刪掉 90 個舊分支，GitHub 上只剩 `main`、`claude/etf-holdings-analysis-ui-0vkuak`、
    `claude/archive-old-branches`、`claude/all-update-45bep4`（都是新歷史，4 個沒合併的舊 PR 隨之關閉）。
    **2026-10-16 使用者為了 Actions 額度把 repo 改成公開**（公開 repo 的一般機器不計分鐘；舊 PR 參照仍含舊歷史、尚未送客服）。要徹底清除就請 GitHub 客服處理，申請要附：
    first changed commit `67dffd35d05eb71f0f120c3b2c4b44cb2b78a819`（舊歷史的根 commit）、受影響的 PR＝#1～#267（全部）。

- **時區**：本機/CI/雲端容器多為 UTC，台北清晨執行時 `date.today()` 會差一天。
  程式內一律用 `arm/clock.py` 的 `today_tw()/now_tw()/stamp_tw()`；跑腳本時帶 `TZ=Asia/Taipei` 雙保險。
- **雲端 Claude 容器的網路政策會擋部分站點**（曾實測被擋：`fhtrust.com.tw`、Google News RSS、PTT；
  proxy 回 CONNECT 403）。被擋時：
  - `fetch_holdings.py` 已內建防呆：抓失敗跳過該檔、保留既有 `data/funds/*.json` 與 `_index.json`，勿手動清檔。
  - `fetch_fund_news.py`／`arm/fundnews.save()` 已內建防呆：本次擷取「全空」且既有落檔非空 → 不覆寫。
    **絕不可把非空的 `data/fund_news.json` 覆寫成全空**；若已誤覆寫，`git checkout -- data/fund_news.json` 還原。
  - NAV／持股快照抓不到就沿用既有快照，GitHub Actions（台北週一~六 06:50）會自動補抓。
  - 新聞查證用 WebSearch（伺服器端、不受 proxy 擋）；WebFetch 個別站點被擋就改用搜尋結果摘要。
  - **`fetch_etf_watch.py` 在此容器會「空轉逾時」而非快速失敗**（2026-07 踩坑）：etfinfo.tw 403 之外，
    報酬還逐檔對 stooq／yahoo／finmind／twse 各發請求，每請求 `timeout=25s`×retries、21 檔×4 源被擋時
    會累積卡 **20+ 分鐘**純空轉。**對策：依上方「效率原則」根本不要在此容器跑這三支抓取腳本**——一律交給
    正式區 `daily.yml`。若因故非跑不可，務必包 `timeout` 硬性上限（例 `timeout 60 python3 …`）避免空轉。
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
- **新聞卡「詳細分析消失、只剩連結」的根因與防呆（2026-07-31 使用者第三次反映，務必守住）**：
  - **徵狀**：儀表板新聞卡展開後**只有參考連結**，摘要與各影響欄整片不見（收合列的「一句話重點」也可能連帶消失）。
  - **根因＝報告端標籤沒加粗體，不是渲染端壞掉**：`arm/usnews.extract_cards()` 抽欄位的 regex 一律要求
    `**標籤**`（`^\s*\d*\.?\s*\*\*新聞摘要\*\*[：:]`／`\*\*一句話重點\*\*`／`^\s*\d+\.\s*\*\*(對…)\*\*`），
    子代理若寫成 `1. 新聞摘要：`（純文字無 `**`）→ `summary`/`oneline`/`points` 全空，
    `_news_view()` 就只剩 `links` 可渲染。**連結與徽章仍在，所以合規掃描 🟢、舊版 check_reports 也 🟢**——
    這是它能連三次靜默上線的原因（同型於「靜默凍結」：防護只保了資料、沒讓異常可見）。
  - **識別法**：`grep -c '^\s*[0-9]*\.\s*\*\*新聞摘要\*\*' reports/twnews/{今日}.md` 應等於卡數；
    為 0 就是踩到了。也可在本地重建後查 HTML 有無 `class="ngs"`／`class="ngpts"`。
  - **防呆（三道，2026-08-19 起）**：
    ① **派工時寫明版型**（步驟 2）：子代理 prompt 必須要求欄位標籤帶 `**粗體**`——源頭預防。
    ② **提示包自帶 `usnews.LABEL_RULE`**（2026-08-19 起）：粗體標籤要求直接寫進五份版型，
       不再只靠派工 prompt 轉述。
    ③ **`check_reports.py` 擋下**（步驟 3）：每卡斷言 `summary` 或 `points` 至少一項非空，
       🔴 訊息直接點名「標籤未加 **粗體**」。已用 2026-07-31 的壞檔驗證過會紅（6 卡全中）；
       2026-08-20 起「漲跌分析」欄缺失同樣被擋。
  - **修法＝改報告、不要改渲染端**：把該報告的 `N. 標籤：` 補成 `N. **標籤**：` 即可
    （`新聞摘要`／`一句話重點`／`漲跌分析`／`對…影響`／`為什麼值得讀` 都要）。
    **不要為了「相容無粗體寫法」去放寬 `extract_cards()` 的 regex**——粗體同時是儀表板的視覺格式來源，
    放寬會讓沒粗體的內文行被誤判成欄位。
- **新聞卡順序（2026-08-16 使用者：「全球的新聞順序很奇怪」）**：儀表板 `_news_view()` **依重要度
  高→低重排**，所以報告檔的撰寫序不等於版面序——當日美股報恰為 8/7/7/6 分時，卡 2 會排到卡 1 前面。
  兩件事已在解析／渲染端根治，**寫報告時不必也不該去配合排序調整卡序**：
  ① `usnews._CARD_SEQ` 在 `extract_cards()` 剝掉裸標題型的「1. ／2、」流水號（重排後那串編號只會
     變成「2./1./3.」的錯亂感）；數字後須接標點才算序號，`10年期公債…` 這類真標題不受影響。
  ② `_news_view()` 排序鍵為 `(是否深度, -重要度)`——**【深度】精選一律殿後**（同報告原檔把
     「深度報告精選」放在卡片群之後）；依分數混排會讓深度文插在事件卡中間、讀起來像插隊。
  兩者皆有測試守（`tests/test_fund_tracker.py::test_news_view_deep_card_goes_last_and_no_serial_numbers`）。
- **「保底要點卡」＝做過又拆掉的功能（2026-08-17 同日上線同日退回，勿再提議）**：曾應使用者要求
  做「台股盤前要點／美股盤後要點」每日保底綜整卡（PR #217：BRIEF_RULE 版型＋etype=brief 置頂
  ＋check_reports 缺卡 🔴），使用者看過成品後決定「拿掉好了，我覺得不好」（PR #218 revert）。
  結論＝新聞區維持純事件卡；市場層級綜整已有頭段速覽／總覽承擔，不要再往新聞卡疊綜整卡。
- **舊公告被 Google 洗日期＝ezfunds 二度肇事後的三層防呆（2026-08-17 使用者抓包：民國110/111年
  「台灣好收益暫停銷售」公告以 08-16 姿態上版）**：①`fundnews._JUNK_URL` 已把 **ezfunds.com.tw 整站**
  剔除（基金銷售平台、被收錄內容全是公告轉貼，08-06 與本次皆它）；②`_JUNK_TITLE` 已補
  「暫停/恢復＋銷售・申購・受理」公告詞；③**通用防呆 `_title_stale_year()`**：標題自帶「年＋月/年度」
  日期式樣（民國 1xx 年 +1911／西元 20xx 年）且最近年份早於前年 → 舊文重收、剔除（「創2020年以來
  新高」式引述不受影響——年後接「以來」非月份）。`sanitize()` 讀取端同一套。同型問題先想
  「標題有沒有自帶年代」這條，不要只補站台黑名單。
- **社群 YouTube 誤收日文影片的防呆（2026-08-17 使用者：「這是日本的影片我只要台灣的」）**：
  「標題須含漢字」**擋不住日文**（日文本來就用漢字——両学長「米国高配当株ETF」滿足漢字＋主題詞
  ETF，海外排除又只認「美股/美國」不認「米国」）。決定性特徵＝**假名字母**：`fundnews._is_japanese()`
  （平/片假名**字母** ぁ-ゖ／ァ-ヺ，排除台灣商品名風格用字「の」）——`yt_relevant`/`yt_peer_relevant`
  抓取端與 `_social_ok` 讀取端都接；該支 FAkMraqLuko 已入 `YT_BLOCK_IDS`。外語誤收的判準優先想
  「該語言的獨有字符」，別逐詞窮舉外語詞彙。
  **⚠ 同日第二坑（使用者：「YouTube 影片怎麼都不見了」）：範圍不可含片假名「記號區」**——
  首版用整段 `[ぁ-ゟ゠-ヿ]`，把 **U+30FB「・」與 U+30FC「ー」**（台灣標題極常用的全形間隔號／
  長音符）當日文，**抓取端整批誤殺、YouTube 從 14 支砍到剩 1 支**；`_carry_social` 只擋
  「單平台全空」、剩 1 支不觸發沿用，所以落檔直接被洗掉。修＝限縮到假名字母；教訓＝
  **用 Unicode 區段當語言判準時，先確認區段內的「記號」是否也被目標語言以外的文字共用**，
  並在上線前拿既有落檔全量跑一次誤殺檢查（當時只測了 4 個新造標題、沒掃既有 14 支）。
- **前十大持股「簡介一再漏掉」的根因與防呆（2026-07-23 使用者多次反映，務必守住）**：
  - **根因**：持股在**正式區 CI 抓**（本容器 proxy 擋 fhtrust，抓不到）——每月換持股時，新標的名
    **只會出現在 CI 產出的 `data/funds/*.json`**，容器端（主會話）看到的是舊快照，本地檢查／pytest
    自然抓不到新標的缺簡介 → 漏的簡介直接隨 CI commit 上線。這不是誰忘了，是「抓取在 CI、補簡介在容器」
    的時間差結構性造成。
  - **防呆（三道，缺一不可）＋自動落地（2026-08-12 補上最後一哩）**：
    ① **CI 端即時偵測**：`daily_fund.sh` 在建表前跑 `scripts/check_holdings_intro.py`，把缺口寫
       `data/holdings_intro_gap.json`（入庫），儀表板「網頁更新時間」列顯示 🔴「N 檔缺簡介」警示章。
    ② **每日固定補齊迴路（主責＝15:33 盤後籌碼 Routine 步驟②；晨間 9⑤ 只讀、連兩天紅才 backstop）**：
       讀 gap 檔見 🔴 → WebSearch 補 `config/holding_profiles.json` 並 push——**push 就落地**：該檔已入
       daily.yml 自動併檔通道（防呆＝JSON 驗證＋有簡介筆數不得減少、壞檔/倒灌保 main 版），
       不需 PR/merge/dispatch/監看。舊流程（開 PR 人工 merge，首例 #200）已淘汰。
    ③ **pytest 守覆蓋**：`tests/test_holdings_intro.py` 斷言「已入庫的基金快照前十大 100% 有簡介」，
       容器端一旦看到含新標的的快照就會紅、逼在發佈前補齊。
  - **「每月固定更新時間」的正解＝不需要另設**：前十大是官網**月度**揭露（`as_of` 顯示上月底，
    換月時點由投信定、實務約次月上旬～中旬），而 CI **每天**都抓（06:35 Routine＋07:15 cron 兜底）
    ——官網哪天換月，當天早上就自動帶入、`as_of` 自動推進；日頻管線天然涵蓋月頻資料源，
    另設月更排程只是多一個要維護的東西。換月常伴新標的缺簡介 → 由上面三道防呆＋9⑤ 迴路吃掉。
  - **補簡介格式**：`config/holding_profiles.json` 的 `profiles` 下 `{持股原字串: {intro, ticker, country, verified}}`；
    key 必須是 `data/funds/*.json` 內 `top_holdings[].name` 的**原字串**（含 `*` 等後綴，精確對應）；
    intro 純事實描述、非投資建議、避開禁用詞。冷門標的先 WebSearch 查證再寫。
- **`check_numbers.py` 在容器內跑會把 `data/factcheck.json` 洗成「全 ⚪」**（2026-07-29 踩坑：
  容器 proxy 擋 twse/taifex → 一項都核不到，CI 的 10 🟢 被覆寫成 0 🟢/11 ⚪ 並隨 commit 上板）。
  已加落檔防呆：**本次 0 🟢 0 🔴、而既有落檔曾核到過 → 不覆寫**。跑完仍請 `git status data/` 確認。
  同型提醒：commit 前用 `git add <明確路徑>`，少用 `git add -A`——本次就是 `-A` 把 smoke-run 的
  degraded 檔一起帶進 commit。
- **Google News RSS 的 pubDate 不可信——舊文會被重標成近期日期（2026-08-06 使用者抓包
  「基金新聞很多都是舊的」）**：Google 重新收錄舊頁時 pubDate 變 re-crawl 時間——實例：
  傘型ETF 4/15 掛牌稿（工商時報 4/14）標 08-01、中租基智網（ezfunds）一年前的公告標 08-04，
  各以「新聞」姿態掛版整週。三道防線（都在 `arm/fundnews.py`＋`arm/connectors/gnews.py`）：
  ①「公開說明書／信託契約」公告類轉貼＝非新聞，入 `_JUNK_TITLE`（`sanitize()` 讀取端也濾、
  舊落檔立即生效）；②台帳 `data/fund_news_seen.json`（**必須入庫**，.gitignore 例外＋daily.yml
  add 皆已設）記每標題「最早見過的日期」——同標題再被重標新日期也拉回最早值，出 7 天窗即剔除；
  ③CI 端 `gnews.verify_published()` 解原文頁驗真實刊出日（每輪限 `VERIFY_BUDGET`=16 篇新項目、
  結果入台帳不重驗），驗出窗外→剔除、窗內較早→改標並把連結換成原文 URL。注意：`gnews.resolve()`
  走 Google 內部 batchexecute 端點（版式會漂移）——失效時 fail-open 沿用 pubDate、CI 日誌印原因
  （grep `[gnews]`／`[fundnews]`），屆時只修 gnews 解析層、策略層（date_verify）不動。
- **基金新聞品質重規劃（2026-08-12 使用者抓包：股感 00409A 開募文全漏、清單全是「跳到
  基金網頁」的報價頁與 CMoney 重複比較文；並重申「不要抓負面的文章」）**——四層修法全在
  `arm/fundnews.py`，`sanitize()` 讀取端同一套（既有落檔的垃圾連結下輪重建即消失，不必等重抓）：
  ① **產品層**：新聞查詢過去只有「品牌＋基金基底名」，自家 ETF 完全不在清單——現
    `fetch_etf_products()` 逐檔查（`"代碼" OR "產品名"`），清單 `fh_products()`＝etfwatch
    watch_tuples（名稱含復華）＋ UPCOMING（含未派碼檔）——**募集中新檔（00409A 型）自動
    涵蓋、掛牌轉正零維護**；`_fh_codes()` 同步吃到 → PTT／YouTube 相關性也認得募集期代碼。
    群組 `fund_ids` 恆空＋帶 `code` 欄，渲染端據此掛代碼章（無基金詳情卡可跳）。
  ② **URL 級垃圾過濾 `_JUNK_URL`**：invest.cnyes 基金總覽/買賣訊號頁、fund.cnyes 詳情頁、
    MoneyDJ ETF 報價頁（`/etf/`、`/funddj/yb`）、**CMoney 論壇文（cmoney.tw/forum/）**、
    Yahoo quote 頁——標題不一定帶 junk 詞、URL 才是決定性特徵（標題層 `_JUNK_TITLE` 同輪
    補了「的總覽/的買賣訊號/報酬走勢/淨值及折溢價」當第二道）。
  ③ **比較誘餌＝農場**：「該怎麼選/該選哪一檔/怎麼挑」問句與「答案在這」賣關子式一律農場；
    **股感式產品解析文（「00409A…｜成分股？配息？優缺點？」多段主題羅列）不是農場、勿誤殺**
    ——那正是使用者要的內容。
  ④ **負面詞擴充**：司法弊案之外補市況/績效負面（慘賠/套牢/跌破/重挫/暴跌/腰斬/清算/下市/
    贖回潮/規模縮水…），品牌/產品/基金/社群全適用。
  另：RSS 直抓加入**股感 StockFeel `/feed/`**（WordPress 全站 feed，`feed_relevant`＝含品牌詞
  或自家代碼才留；容器 proxy 擋 stockfeel、CI 可達性看首輪日誌 grep `[fundnews]`，失敗 fail-open
  只損失此源）；feed 分流 `route_feeds_to_funds` 認得產品代碼；`VERIFY_BUDGET` 16→24。
  **同日第二輪（使用者追加）**：⑤**區塊改名「復華新聞・社群」**（原「基金相關新聞・社群」；
  nav、區塊標題、內層標題、鮮度列標籤同步改，section id `#fundnews` 不動）；⑥**品牌詞層
  `BRAND_TERMS=("復華","金複合")`**——金複合投資法/理財機器人的討論常不寫「復華」，PTT／
  YouTube／RSS／強基金相關性判準（`_brand_hit`）都認（「金管家」他行也在用、不進清單，
  靠「復華金管家」寫法自然命中）；⑦**社群加「強基金 fundhot」**（`fetch_fundhot`）：
  台灣最大共同基金討論社群、金複合討論主場。兩套站並抓（新站 `fundhot.com/forum/{分類}/
  {slug}/{id}` 列表頁 regex＋舊 phpBB `forum.fundhot.com/feed.php?mode=topics` Atom），
  同標題跨源去重、單源失敗不牽連；容器 proxy 擋 fundhot（同 PTT 型）、真正抓取在 CI，
  新站解析 0 筆會印**結構探針**片段（grep `[fundhot]`）供一輪收斂；`_carry_social` 平台
  清單已含 fundhot（來源異常沿用既有項目）。渲染＝💬 章＋「強基金・板名」來源標。
- **⚠ 強基金「都沒有在更新」＝三個結構性缺陷疊加（2026-09-01 使用者回報；同一組項目
  連掛一週以上，勿再走回頭路）**：CI 日誌 `[fundhot]` 每天印三行失敗、卻沒人看得出原因——
  ①**取得範圍只剩總覽頁一頁**：舊種子的 `/forum/股票` 是舊 phpBB 版名、新站沒有此分類；
  改成實際存在的分類（股票基金／ETF／資產配置）＋由**總覽頁話題連結的分類段自尋**補上
  （`FUNDHOT_MAX_PAGES`=6 上限）後，**當輪 CI 揭曉真正原因＝全部 403，不是網址寫錯**：
  `/forum` 總覽頁 200，但**每一支分類頁與舊站 feed.php／search.php 全部 HTTP 403**
  ——站方對「不像瀏覽器」的請求擋動態路由。試過補 Accept／Accept-Language／Referer
  （`FUNDHOT_HEADERS`，UA 仍誠實標研究用途）**無效、第二輪照樣全 403**——即**已確定是
  UA／IP 層的擋機房行為**。結論：**取得範圍就是 `/forum` 總覽頁那一份清單，別再往
  「多加幾支網址、換標頭」修**（兩輪已證偽）；真要擴，只剩「偽裝瀏覽器 UA」或放棄此來源，
  那是要先問使用者的取捨。附帶實證：總覽頁本身有在更新（探針見新話題 id 13930），
  只是符合復華相關性判準的討論本來就少——**強基金天生是低流量來源，別期待每天有新卡**。
  ③-2 **日期在版式裡、只是不是 `<time>`（加寬探針後一輪解決）**：新站列表是
  `<span class="text-auxiliary …">10小時前</span>` 這種**相對時間**，夾在標題 `</a>`
  與作者連結之間 → `_rel_date()` 解析成真日期（分鐘/小時照實扣，清晨跑時「10小時前」
  ＝昨天），窗口切在**下一個 `<a `** 之前以免抓到下一列的時間；有日期者由 `fetch_fundhot`
  照時窗老化。first_seen 仍留著當沒有日期時的後備。
  ②**失敗只印 `type(e).__name__`**＝「RuntimeError」，看不出是 404 還是被擋（`get_bytes` 的
  訊息本體已含 URL 與 HTTP 狀態，只是被丟掉）。**同型的靜默 `except: break` 也存在於
  `fetch_ptt`**（「PTT 0 則」到底是被擋還是查無討論，日誌上長得一模一樣）——兩處都改印訊息本體。
  ③**新站列表頁項目沒有日期**，`_carry_social` 的時窗檢查對「無 ISO 日期」一律豁免 → 來源掛掉
  時原地凍結、版面上那欄還是空白，看起來就像今天的新討論。現：`parse_fundhot_page` 只在
  找得到 `<time datetime>` 時給 date（不猜純文字日期，猜錯會把鄰列日期安到別篇上；
  找不到會印一次探針片段供日後收斂），無日期者由 `_stamp_first_seen()` 記**首見日**
  （同 url 沿用最早值），`_social_in_window()` 據以老化、儀表板標「首見 M/D」。
  另：`feed.php?mode=topics` 對訪客常被關閉 → 加舊站「最新討論」HTML 備援
  （`FUNDHOT_ACTIVE`＝`search.php?search_id=active_topics`，`parse_phpbb_topics`；
  href 內分隔字元是 **`&amp;`** 不是 `&`，網址正規化成 `viewtopic.php?t={id}` 去掉 sid，
  否則 first_seen 台帳與去重永遠對不上同一篇）。抓取一律 `retries=1／timeout=12`——
  整站被擋時預設 3×25s 會讓每頁空轉逾一分鐘（每日 routine 全長才 ~80 秒）。
- **社群討論＝PTT＋YouTube（2026-08-06 使用者需求）**：`fundnews.fetch_youtube()` 走 YouTube
  Data API v3，金鑰＝Actions secret `YOUTUBE_API_KEY`（v0.12 舊金鑰未曾建成 repo secret、
  已隨舊容器佚失，2026-08-06 使用者重設一把；本機備援 `~/.fh_youtube_key`）。無金鑰／被擋
  回 []、只剩 PTT，fetch_fund_news.py 會印「未設 YOUTUBE_API_KEY」提示。
  **PTT＝股票板＋基金板雙板（2026-08-07 使用者需求）**：`fetch_ptt()` 依 `PTT_BOARDS` 兩板
  各抓 3 頁、跨板以網址去重、項目帶 `board` 供渲染標板名；相關性判準同 YouTube 層
  ＝「復華」**或**自家 ETF 代碼獨立詞（`_code_hit`，00929 討論串常不寫「復華」）。
  **社群防呆兩道（2026-08-07 踩坑後建）**：①`_carry_social` 來源級沿用——單一平台本次
  全空且既有落檔該平台非空 → 沿用舊項目（ISO 日期出 7 天窗剔除、看點重算），根治「一輪
  沒金鑰就把 7 則社群洗成 0」（整份「全空不覆寫」防呆只看 brand/funds/social 全空、擋不住
  單段全空）；②儀表板 `_yt_watch_chip`：social 段存在而 youtube 0 支 → 「網頁更新時間」列
  紅章，配 SOP 步驟 9⑦ 的每日驗證。根因與補救見步驟 9⑦（push 觸發用舊分支 workflow 檔）。
  **三層清單（2026-08-06 使用者規劃；2026-08-14 第三層擴編）**：①**官方**＝`YT_OFFICIAL_CHANNELS`——**兩個頻道**
  （使用者提供）：@fhifund 主頻道（UCD3J90bNoHykt6Eru8YxUmQ，金管家系列在此）＋@fhetf
  ETF 專屬頻道（handle 執行期以 channels.list forHandle 解析；config 鍵吃 UC id 或 @handle
  皆可）——近窗**全部上傳**（uploads 播放清單 UC→UU、每頻道 1 單位，依日期序、掛「官方」章）；②**相關**＝search 4 組（復華投信／
  復華 基金／復華 ETF／00929）依觀看數**取前 3**——標題只寫自家 ETF 代碼、沒寫「復華」的
  影片也算相關（`_fh_codes()` 動態取 etfwatch 清單中名稱含復華者；代碼須為**獨立詞**——
  曾誤收日文單字卡課號「L#00929」；**獨立詞仍不夠**：2026-08-14 使用者抓包可蘭經朗誦
  《Surah Rahman | Ep - 00929》以集數編號誤入——再補兩道：**集數式前綴**（Ep -／第…／No.
  接代碼）不算命中、**純代碼命中須含漢字**（relevanceLanguage 只是偏好非過濾），並設
  `YT_BLOCK_IDS` 指名黑名單＋`sanitize()` 讀取端同濾——非官方且標題無漢字／黑名單 id
  一律剔除，舊落檔與 `_carry_social` 沿用款不必等重抓即消失）；③**市場熱門**（原「同業熱門」，
  2026-08-14 使用者：「觀看數超級少……應該會有超級多討論 ETF 等等基金類的影片」後擴編；
  2026-08-15 再擴「投資相關（不要個股）」）＝
  `YT_PEER_QUERIES` **7 組主題桶**（台股 ETF／高股息 ETF／ETF 投資／債券 ETF／基金 投資／
  主動式 ETF／台股）各近 `YT_PEER_FRESH_DAYS`=5 天依觀看數搜尋（maxResults=25——**search
  成本與 10 筆同為 100 單位**，放大 pool 零額度成本），`yt_peer_relevant` 三路徑任一即收：
  **同業代碼**（`_peer_codes()`）／ETF・基金**主題詞**（高觀看的泛 ETF 討論多不寫代碼，
  舊判準全殺）／**市場趨勢詞**（`_YT_TREND`：大盤行情、總經政策、資產配置——2026-08-15
  使用者「投資相關的（不要個股）」）。排除：純海外（美股代碼/「美股ETF」連語且無台股代碼）、
  無漢字、**個股本位**（`_STOCK_FOCUS` 只驗標題：知名個股名／個股・飆股・選股・當沖・漲停／
  非 00 開頭 4 碼代號——**僅在無任何產品面（主題詞/台股 ETF 代碼）時生效**，「台積電還能
  買嗎」擋、「台股ETF 台積電權重過半」收）。再經 `_select_peers`：**同片跨頻道去重**
  （聯播節目三立/94要賺錢同片異 id，正規化＝去尾端「｜頻道名」段）→ **觀看門檻**
  `YT_PEER_MIN_VIEWS`=5000（全數未達才 fallback 取前 2、不留白）→ **分類配額**（`yt_topic`
  七類：債券／高股息／主動式／市值型／基金／市場趨勢／綜合，**每類 2、總上限 10**——
  viewCount 排序易被單一題材洗版，配額保多樣性）；`cat` 一律寫入、儀表板章「熱門・{類別}」
  （綜合＝素「熱門」、舊落檔無 cat 顯示原「同業熱門」）。**版面由前端「分類篩選 chips」控**
  （2026-08-15 使用者：「太長了…有分類可以點然後就可以篩選」）：社群清單上方 `#socbar`
  chips＝全部／ETF／主動ETF／基金／市場趨勢（帶數量、空分組不渲染），**全部社群項目**
  （官方/相關/熱門/PTT/強基金）都經 `fundnews.social_group()` 掛 `data-fcat`
  （etf/active/fund/trend/other；other 僅「全部」可見），點 chip 前端 toggle `.fnit.fhide`
  ——CSS 三處已一起加（隱藏規則/chip 樣式 `.sg`/active 態，2026-07-31 教訓）。
  自家內容歸②不重複。三層共用 seen 去重、官方優先。
  **時長 ≤3 分標 Shorts**（連結走 /shorts/、來源標「YouTube Shorts」）。額度：search 11 組
  ×100（相關 4＋熱門 7）＋playlistItems 2＋channels 1＋videos.list **分批**（單次上限 50 支
  ——舊版 `ids[:50]` 靜默截斷、其餘 0 觀看沉底，2026-08-14 修）數單位 ≈每輪 1,110 單位
  （日限 10,000）——**勿再隨意加查詢組，加組前先算這筆帳**。
  **⚠ 單日多輪 CI 重跑會把配額燒完（2026-08-17 實戰：連環修正日 dispatch 約 10 輪 → search 全
  403 quotaExceeded，日誌型態＝「官方 1・相關 0・同業 0」——殘額 <100 單位時 search 被拒、
  1 單位的 playlist 仍過）**：配額於太平洋時間午夜（台北 15~16 時）重置、隔輪自癒，落檔靠
  `_carry_social` 不會全滅但會縮水。搜尋層錯誤已改為印進 CI 日誌（`_search_all`，不再靜默
  `except: continue`）；密集除錯日請把「YouTube 縮水」當預期現象，等重置後一輪補回，勿當新 bug 追。
  **FB／IG／Threads 擴充規劃見 `docs/social_api_plan.md`**（2026-08-06 查證：Threads 公開
  關鍵字搜尋為第一優先、需使用者建 Meta App＋過審 `threads_keyword_search`；FB 只做自家
  粉專、IG hashtag 額度緊排最後）。
- **新聞來源黑名單**：排除「富聯網」（moneylink）。
- **禁用詞**（正文不得出現，機構觀點也要改寫避開）：保證、穩賺、必賺、包賺、必漲、必跌、一定會、唯一、
  建議買賣、建議買、建議賣、目標價、零風險、無風險、穩賺不賠。
  **唯一例外（2026-10-17 使用者：「直接說目標價不就好了」）**：籌碼雷達公司卡「法人預估」段與飆股段的法人小字，
  引述券商分析師的目標價（附來源連結）時直接寫「目標價」；新聞報告、策略文字、我們自己的參考價位照舊禁用
  （位置由 `tests/test_fcst.py` 的 `FC_FUNCS` 守，見「法人預估與產業比較」專段）。

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

## 行事曆「台灣區與精簡規則」（2026-10-13 使用者兩輪：「行事曆是不是也要把台股的重要公司法說或是財報公布都加進去」→「我希望可以不要讓資訊過於複雜零散」）

- **同日第二輪：加台灣官方數據＋精簡**。評估當時近 12 份行事曆：20–39 列（美國單區 10–24 列，
  CPI 月增／年增／核心拆三列）、引言 314–418 字（「昨夜重點」與同頁政策總覽重複）、非排定的突發新聞
  被硬塞成列（「克宮回應」「WPC 能源大會」掛「歐：」只為了分類）。加資訊的同時把總量上限講死：
  · **「台：」只收六類**——央行理監事會、出口、外銷訂單、CPI、GDP 概估／預測、景氣燈號；≤4 列（`TW_DATA_MAX`）；
    無公布時註「台：本週無台灣重點經濟數據」。
  · **台灣集中一處**：網頁＝全球數據（美歐中日）→ **台灣表（台＋台股合一張）** → 海外財報，仍是三張表；
    列印版同一張表、台灣列綠章（原台股紅章與「中」撞色已改）。`macronews.TW_REGIONS` 為唯一定義。
  · **精簡四條（SPEC_CAL）**：①總列數 ≤30（休市不計，`CAL_MAX_ROWS`）②同一指標口徑併一列
    （「9月CPI（年增；月增／核心月增）」值寫「+3.6%（+0.6%／+0.2%）*」）③只收事先排定事件
    ④引言只寫「更新；市況；本週焦點（≤80 字）」、整行 ≤220 字（`CAL_NOTE_MAX`），**本週焦點內勿用「；」**
    （網頁以「；」切條列，用了會被拆成兩條——當日實際踩到）。來源與口徑說明放表下「註」（網頁與列印都不顯示）。
  · **閘門** `check_reports._check_calendar_slim`：缺台列也缺「台：本週無」註記／台列 >4／總列數 >30／引言 >220 → 🔴。
  · 當日套用結果：28 列 → 24 列（含台股 3 列）、引言 384 → 117 字、列印版 ③ 從頁底擠壓改為留白。
  · `台股：` 上限同日由 10 下修為 8（`TW_CAL_MAX`）。

### 台股公司法說・財報（同日第一輪）

- **缺口**：舊版型只寫「台股台積電等指標企業」歸在「財報：」——歷史行事曆的台股公司事件**只出現過台積電**
  （法說／月營收／除息），復華基金真正重押的台光電、欣興、南電、奇鋐…法說從沒上過行事曆。
- **觀察清單由資料推出、不寫死** `macronews.tw_watch()`：復華基金前十大（`data/funds/*.json` × `holding_profiles` 代號）
  ＋本家 ETF 前十大（etfwatch 名稱含復華者，`data/etf_holdings.json`）＋**0050 前十大**（權值龍頭，每日 PCF 權重）；
  依「持有檔數」排序、00 開頭（組合型基金持有的 0050 等 ETF）排除、名稱取各來源最短者＝常用簡稱。
  **同一份清單兩處用**：行事曆提示包「本週必查」段（`tw_watch_block`）＋儀表板台股列「復華持股」章（`tw_held`）。
- **版型** `SPEC_CAL`：新增「台股：」前綴（法說會／董事會通過季報・年報／台積電月營收／權值龍頭除權息），
  代號必填、≤8 列（`TW_CAL_MAX`，同日第二輪由 10 下修）、清單內本週無事件時「註」必寫「台股：本週無觀察清單內公司法說／財報」；
  「財報：」收窄為海外企業。
- **呈現**：網頁＝台股列放進「台灣：經濟數據・法說財報」表（第二輪與「台：」合併；復華持股掛金章、tooltip 列持有來源）；
  列印版 ① 同一張表、台股列綠「台股」章＋「持股」小章、表底註明意義。
- **過渡相容** `retag_tw()`：舊版型寫在「財報：」且代號在觀察清單內者自動改歸台股——**只認清單內代號**
  （日股代號也是 4 碼，東京威力 8035，不可單憑碼長判斷）。所以排程搬家前的舊格式行事曆也會正確分組。
- **閘門** `check_reports._check_calendar_tw`（2026-10-13 起）：沒有台股列也沒「本週無」註記／台股列缺代號／超過 8 列 → 🔴。
  只確認「有查」，不強求一定有事件（法說淡季本來就可能沒有）。
- **生效條件**：呈現與相容＝merge 進 main；提示包與閘門＝merge 後「排程搬家」（同其他版型規則的傳播機制）。

## 資料可信度盤查與因應（2026-10-13 使用者：「你行事曆的資料是不是第一手的？你抓資料要確認資料的可信度還有穩定度」）

**盤查結論**：行事曆除「台股觀察清單」（讀持股落檔）外，日期／實際值／前值／市況全由子代理每天依搜尋摘要
重寫——非第一手；預期值（市場共識）本來就沒有第一手來源，維持第三方並標 *。三個實證風險：
① **控制面依賴**：盤後看門狗 `check_afterhours_fresh.is_trading_day()` 與鮮度 `_tw_closed_days()` 都讀行事曆
「市況」段決定台股有沒有開——**2026-10-05～08 市況連四天寫「台股 正常交易」，同週 10/09 國慶補假其實休市**
（今日重點 chip 因此連四天告訴讀者「本週無休市」；9/29～10/02 對 9/28 教師節同型）；
② **每日重寫不穩定**：同週相鄰兩日比對 79 組／1,387 列——日期變動 14 次（含 6 月貿易收支 08/04→08/05→08/04
來回翻）、已公布實際值改寫 19 次、前值變動 64 次；③ **年度表到期**：美股假日表只到 2026、無測試守。
**分三階段因應**（使用者同意；第三步非官方但可信度足夠者可收，須註明來源層級）：

### Phase 1：官方休市表（2026-10-13 完成）
- `arm/twholidays.py`：**證交所官方表優先**——CI 每日 `scripts/fetch_tw_holidays.py`（`daily_fund.sh`）抓
  `openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule`（欄位 Name／Date＝民國 7 碼／Weekday／Description；
  週末列、「最後交易日／開始交易日」不算休市、「無交易僅辦理結算交割」算）→ `data/tw_holidays.json`（**必須入庫**，
  `.gitignore` 例外＋daily.yml add 已設）。一年解析 <5 天不採信、抓不到沿用既有（fail-open）、與種子不一致印日誌。
- **內建 2026 種子 `SEED`**（容器擋 twse、不必等 CI 首輪）：18 個平日休市，兩來源核對＋總數自洽
  （2026 平日 261 − 證交所公告交易日 243 ＝ 18）。
- 消費端：`is_trading_day()`／`_tw_closed_days()` 官方表涵蓋的年份**只信官方**（行事曆誤寫休市不入表、
  漏寫也照樣判休市），未涵蓋才退回文字；`usnews.calendar_anchor()` 加「台股近 10 日休市（證交所官方表）」行，
  行事曆提示包也帶入整段錨定。美股表補 2027（NYSE Group 2026–2028 公告；11/26 提前收盤不列）並改名 `_US_MKT_HOLIDAYS`。
- 閘門 `check_reports._check_calendar_holidays`：本週官方休市日市況台股欄沒寫／寫了官方沒有的休市日 → 🔴
  （歷史回測正好抓出上述 8 天）。`tests/test_twholidays.py::test_holiday_tables_cover_next_45_days`：
  台／美任一表未涵蓋「今日＋45 天」→ 紅＝**每年 11 月中逼補下一年**（證交所通常 10 月底公告隔年表）。
- **暫代層 `twholidays.PROVISIONAL`（2026-10-13 補 2027）**：證交所隔年表公告前（2026 年表是 2025-10-29 才公告），
  先放**人事行政總處已核定的辦公日曆**平日放假日（2027＝17 天，2026-05-21 核定；週末 104＋17＝全年 121 天自洽）。
  語意＝「**已知必休**」：辦公日曆放假日 `is_closed`→True；其餘平日→**None（未知）**，交給後備（行事曆文字）——
  因為證交所另有自己加的休市日（春節前「無交易僅結算」兩天，2026 是 2/12、2/13），辦公日曆上沒有，**不猜**。
  提示包把這些日子標「＊」並註明「證交所年度表未公告」；閘門只驗「辦公日曆放假日有沒有寫」、其餘平日不驗。
  證交所表一到（CI 落檔或補進 SEED）即整年取代，CI 日誌印「證交所另加：…」供核對。
  `test_provisional_year_replaced_before_december`：**隔年前一年 12/1 還在暫代 → 紅**＝確認 CI 有沒有抓到；
  官方 API 若不含隔年，就依證交所公告補 `SEED[年]`。同日閘門也補了區間寫法（「2/12–2/20 休市」中間的日子算有寫）。

### Phase 2：以昨日版為底稿＋漂移閘門（2026-10-13 完成）
- **提示包**：`gen_macronews.build_cal_prompt` 附「同週昨日版」全文＋`macronews.CAL_CARRY_RULE`——在昨日版上增修、
  不整份重寫；項目文字不換說法；日期與已公布實際值不得改，除非官方修正／改期並在「註」寫「修正：…（來源）」。
  同週判定 `cal_week_start()`（讀標題「（10/12–10/16）」）＋`target_week_start()`（週末的檔＝下週預覽，
  所以週一的底稿是週末那份）；週一換新週沒有同週前版＝不附、不比。
- **偵測 `macronews.cal_drift()`**：列以「前綴＋項目」正規化對齊（對不上就不比，fail-open）；抓三種：
  日期改了／已公布實際值的**舊數字消失**／已公布退回未公布。**不算改動**：換順序、補細節（舊數字都還在）、
  精度不同（727 萬 vs 727.1 萬）、談話會議列（無數字前值／預期且實際值非數字開頭）換句話說。
  這幾條是回測調出來的——首版逐一比數字序列，26 筆裡有 5 筆是換順序／精度／談話要點的假警報。
- **閘門 `check_reports._check_calendar_drift`（2026-10-14 起）**：有漂移且「註」沒有提到該項目的「修正」行 → 🔴。
  回測 2026-07～10：同週有前版的 84 天中 15 天會紅（日期來回翻 14、實際值改 7——8 月失業率 4.3%→4.1%、
  時薪 3.7%→3.1%、核心 PCE 3.6%→3.3%、財新 PMI 50.9→51.5…），每一筆都是「同一事實兩天兩種說法」。
- 生效條件：閘門＝merge 即生效（容器端 check_reports）；提示包＝merge 後「排程搬家」。

### Phase 3：核心排程錨 `config/official_schedule.json`（2026-10-13 完成）
- **收錄範圍＝少而確實**：各國央行決議（FOMC／ECB／BOJ／台灣央行理監事會）、美國 CPI／非農、台灣官方數據
  （出口、外銷訂單、CPI、GDP 概估／預測、景氣燈號）。日期＝**發布地當地日**（與行事曆慣例一致；台北時間寫在 `time`）。
- **來源層級**（使用者 2026-10-13：「不是官方的但資料可信度你覺得可以還是可以放」）：`official`＝官方排程頁或主管機關
  新聞稿載明（含新聞稿末「下次發布日期」）；`secondary`＝**兩家主流媒體**一致（`source` 至少兩個連結，tests 守）。
  「通常是每月 20 日」這類慣例推估**不收**——查不到確切日期就不列，行事曆照舊由代理查證。
- `match`＝任一組關鍵詞全數出現在行事曆項目即同一事件（前綴須相同——「美：9月CPI」與「中：9月CPI」不會混）。
- 提示包 `macronews.schedule_block()`：「本週核心排程錨」逐條列日期＋時間＋層級；閘門
  `check_reports._check_calendar_anchors`（2026-10-14 起）：本週錨沒列／日期不同且「註」沒有「修正：」→ 🔴。
- **維護**：`tests/test_schedule_anchors.py::test_schedule_not_running_out`——最後一筆在 21 天內 → 紅＝補下一段
  （FOMC／ECB／BOJ／BLS 隔年排程年初前都已公布；台灣各機關新聞稿末段載「下次發布日期」可逐月補）。
  2026-10-13 已補到 **2027-03-18**（BLS 2027 排程 10/9 公告、Fed 2027 暫定排程、ECB／日銀 2027 日程，全為 official）。
  **台灣數據只有「下一次」可查**（財政部／國發會在新聞稿或首頁只預告下一次，主計總處／經濟部的年度發布時間表
  搜尋摘要看不到內容）——所以台灣錨只會零星有幾筆，每次發布後看到「下次發布日期」再補。
- `match` 的月份詞**整詞比**（`anchor_matches`）：「1月」不命中「11月」、「2月」不命中「12月」。

## 儀表板「🕒 資料更新時間」區塊

**版面（2026-09-24 使用者：「要點才會出現對應資訊不好用」，分頁架構維持不動）**：四分頁內的各段
**一律全部顯示**、由上往下排；頂欄第二排標籤＝跳段目錄（點了捲到該段），捲動時 JS `spy()` 自動標亮
目前所在段。`.secradio` 只當「目前段」標記、**不再控制顯示**（2026-09-01～09-23 曾是「一次只顯示
一段」，使用者用過後決定改回）。選取器一律寫 `.sec[data-sec]`——持股表的產業標籤也叫 `class="sec"`
（`.htbl .sec`），寫成裸 `.sec` 會掃到三百多個無關元素。同日頁首瘦身：拿掉品牌橫幅（頂欄已有品牌名）、
本區塊壓成細條（正常時不印說明句，逾期才印紅字）；新聞卡灰字由 `_meta_clean()` 去掉與徽章重複的
【屬性】／重要度。

`arm/fund_dashboard.py` 的 `_freshness_view()`，顯示各資料來源鮮度（皆台北時間）：
NAV 日／持股基準（月度）／持股快照抓取／美股新聞／台股新聞／總經・政策／經濟行事曆／復華新聞・社群（2026-08-12 前叫「基金新聞・社群」）／
ETF 數據追蹤／ETF 持股揭露／總經・籌碼數據／儀表板產表。新增資料來源時請同步加進此區塊。

**逾期判定分兩種口徑（2026-09-28 使用者抓包誤報）**：跟著台股交易日產生的四項——NAV 日、ETF 持股揭露、
多期報酬（鉅亨）、ETF 資料基準——以**交易日**計（`_trade_age`；sources 第 4 欄／`_fresh_chip(trading=True)`），
其餘（新聞、抓取時戳）照日曆天。當時 9/25 中秋＋週末＋9/28 教師節，資料停在 9/24 完全正確，日曆天口徑卻判
「持股揭露／多期報酬逾期」。休市日由 `_tw_closed_days()` 取**證交所官方休市表**（`arm/twholidays`，2026-10-13 起；官方表未涵蓋的年份才退回）讀 `reports/macrocal/*.md` 的週表休市列與市況段
**寫明的日期**（前一天的檔會預告隔天休市，不可把檔案日期當休市）；行事曆沒寫到的休市只會偏嚴、不會漏報。

**注意 `_freshness_view()` 只輸出「逾期」項目**（2026-07-30 踩坑）：資料正常時來源名稱
**完全不會出現在 HTML 裡**——正常時戳一律標在各自區塊標題列的 `_fresh_chip()`。所以
①新增來源要「兩處都加」：逾期清單 ＋ 該區塊標題 chip；②驗證 CI 有沒有重建成功時
**不可用來源名稱當 grep 標記**（我曾以「ETF 持股揭露」找不到就誤判 workflow 沒重建，
實際 push 成功、只是資料新鮮所以那串字不該出現）。改用內容標記（如 `class="hcard"`、
`ehtog` 展開鈕數量）或直接比 commit 內容。

## 「市場溫度計」（總經分頁，2026-07-23 使用者需求）

總經分頁**行事曆／政策新聞之後**的 `#macro-data` 區塊，兩張官方數據表（`arm/macrochips.py`
資料層、`arm/fund_dashboard._macro_data_view()` 渲染），每列＝最新值＋日變化＋近5日＋
近30日 inline SVG sparkline＋資料日：
- **全球市場溫度計**（Yahoo Finance 官方序列）：VIX（附平靜/正常/偏高/恐慌狀態燈）、
  美國 10 年期公債殖利率（`^TNX`÷10、日變化以 bp）、美元指數 DXY、美元兌新台幣、布蘭特原油、黃金。
- **台股籌碼**（TWSE／期交所官方）：三大法人買賣超（**合計主列可點 ▸ 展開外資／投信／自營商分項**，
  `inst_total/inst_foreign/inst_trust/inst_dealer` 四序列，`_twse_inst_all` 解析 BFI82U——
  外資列名為「外資及陸資(不含外資自營商)」含「自營」字樣，故以獨有「陸資」二字辨識，勿用「自營 not in」誤殺）、
  外資台指期未平倉淨部位（`淨空/淨多 X 口`）、融資餘額、融券餘額、台指選擇權 P/C 比。
- **呈現慣例（2026-07-23 使用者需求）**：①每列都帶單位（指數＝點、殖利率＝%、匯率＝元、油＝美元/桶、
  金＝美元/盎司、法人/融資＝億、融券＝張、期貨＝口）；②**指標名稱本身即官方揭露頁可點連結**
  （`_MD_SRC`，非表底 footer）；③**流量（買賣超）走勢用零基準長條圖**（`_spark_bars`，綠買超/紅賣超，
  單日爆量不會把折線拉歪），水準值（指數/價/餘額）才用折線 `_spark`（縮放至區間高低、看相對形狀）。

**踩過的坑：序列「靜默凍結」（2026-07-29 使用者回報「外資淨空單數字是錯的」）**——
`tx_foreign_net` 自 7/23 起停更、儀表板連續 6 天以現值姿態顯示 75,198。根因與三道修法：
- **根因① 抓取單點失效**：`futContractsDateDown` 單一參數組合失效後回 0 列（同時段 `pcRatioDown`
  正常＝非網路問題），舊碼沉默回 `{}`。→ 現改：**queryEndDate 夾到已結算交易日**
  （`_last_settled`，期交所 15:00 後才有當日資料）＋**多組 POST 參數變體依序試**＋**逐日兜底**＋
  **把 HTTP 狀態／例外寫進 CI 日誌**（本容器 proxy 擋期交所，日誌是唯一除錯管道）。
- **根因② 口徑沒鎖**：舊解析只認「列中有外資」，未驗商品 → 期交所若忽略 `commodityId` 就會安靜
  讀到小台／電子期。→ `_tx_rows_to_series` **強制商品＝臺股期貨(TX 大台)＋身份別＝外資（排除外資自營商）**；
  商品名在 CSV 是 rowspan 展平（只出現在該商品首列），故以「最後見到的非空商品名」延續，
  否則外資列會因商品名空白被整批丟棄。儀表板欄名改「外資台指期淨部位（**大台**）」、表註寫明
  **不含小台／微台**，與彙整站常見的「大＋小＋微台合計」口徑本就不會一致。
- **根因③ 過期看不見**：「抓不到就保留舊序列」保護了資料，卻讓凍結靜默。→ `_md_stale_badge()`：
  資料日落後逾 2 個交易日的指標，名稱下方顯示紅色 **⚠ 過期** 章（附落後天數 tooltip）。
- `factcheck.taifex_tx_foreign_net` 已改為呼叫同一支 `macrochips._taifex_tx_foreign`——
  **單一實作**，不要再各留一份解析（兩份會同時失效、又只顯示 ⚪「官方不可得」看不出原因）。
- **不要手動填補缺漏日的值**：實測各彙整站給出互相矛盾的數字（45,869／80,042／82,255），
  正是「誤引彙整站」同型坑。修抓取讓 CI 取官方值，過渡期由 ⚠ 過期章負責誠實揭露。

**踩過的坑：證交所「盤後修正」讓落檔凍住早期快照（2026-08-05 factcheck 4 🔴）**——
08-04 盤後 15:33 抓的三大法人合計 1.1 億（當晚各媒體也都報 1.1 億），證交所後補
**外資自營商分項（+18.9 億）**後合計修正為 20.0 億；落檔「逐日補缺」只抓缺的日期、
已在序列裡的日子永不重抓 → 舊值凍住，隔日報告照抄落檔被 factcheck 用修正後官方值判 🔴
（報告沒錯、落檔也沒錯，是官方自己改了）。三處修法：
① `macrochips.fetch()` BFI82U 段：序列**最新一天每輪重抓一次**讓修正值覆蓋（每輪多 1 請求）；
② `factcheck.extract_claims()` 抽聲明前**先剝 markdown 連結**——「參考連結」列的媒體標題
  （「三大法人買超1.09億元」）曾被抽成本報告聲明、日期還從 URL 片段誤配成 4/10；
③ 外資規則兩條：`twse_inst_flows` 的外資列改以「陸資」辨識（舊 `自營 not in name` 把
  「外資及陸資(不含外資自營商)」整列誤殺 → inst_foreign 永遠 ⚪）；抽取器 `外資(?!自營商)`
  ——「外資自營商買超 X 億」是另一個官方列，抽成 inst_foreign 必然假 🔴。

架構同 etf_watch 慣例：
- **資料層 `data/macro_chips.json` 必須入庫**（`.gitignore` 已加 `!` 例外）——跨日累積序列＋
  來源被擋時的 fallback。合併鐵則 `arm/macrochips._merge()`：本次官方新值覆蓋同日舊值，
  整段抓不到＝保留舊序列，值為 None 一律不寫入，**絕不把非空序列洗成空**；每指標留最近 45 筆。
- **官方抓取重用 `arm/factcheck.py`**（TWSE BFI82U 三大法人、TAIFEX TX 淨額、Yahoo 指數序列同端點）；
  新寫 TWSE MI_MARGN（融資融券）、TAIFEX pcRatioDown（P/C 比）解析。
- **本容器 proxy 擋 twse/taifex/yahoo**——抓取只在正式區 CI（`daily_fund.sh` 平行加跑
  `scripts/fetch_macro_chips.py`、`daily.yml` commit 步驟加 `data/macro_chips.json`）；
  容器內只讀落檔建儀表板。查不到可靠值的指標（如某日 P/C 比）整列不顯示、不留空值。
- **踩過的坑**：①TAIFEX 逐日端點在「今日盤中未結算」時外資淨部位／選擇權會回 `0`——`_taifex_tx_foreign`／
  `_taifex_pc_ratio` 一律**濾掉 0**（0＝無資料哨兵，否則最新值變「淨多 0 口」、走勢尾端插歸零）。
  ②手機排版：`mdtbl` 第一欄（指標）`position:sticky` 凍結、資料日收進名稱下方小字、日變化與近5日併一欄上下疊，
  只留 4 欄（指標／最新值／日變化·近5日／走勢）才塞得下走勢圖；名稱去掉（上市）（未平倉）後綴（移到表註）。
- 種子值以 WebSearch 多來源交叉查證後寫進落檔（例：外資台指期以 7/17 官方 86,189 口為錨逐日自洽）。
- 新增指標：在 `macrochips.GLOBAL_SPECS`／`TW_KEYS` 與 `fund_dashboard._MD_GLOBAL_ROWS`／`_MD_TW_ROWS` 同步加列。
- **資料來源可點連結**（2026-07-23 使用者需求）：每組表底 `fund_dashboard._md_src_footer()` 依 `_MD_SRC`
  列官方揭露頁連結（全球＝Yahoo Finance 各報價頁；台股＝證交所 BFI82U／MI_MARGN、期交所 futContractsDate／pcRatio），
  同機構同頁去重、只列「有資料」的指標。新增指標時記得在 `_MD_SRC` 補對應官方頁 URL。

## 「ETF 數據追蹤」分頁（左上第四分頁）

追蹤台股被動 ETF（0056/00878/00919/00929/0050/006208）＋**主動式 ETF（股票／債券同表）**
（含本家 00991A、2026-07 新增熱門／新募集 00988A/00990A/00403A/00407A，以及上櫃檔
00998A/00986D/00411A/00987D——**2026-08-28 使用者指示：分組照投資型態走，上櫃不再另立
「其他」組**：kind 一律 active／passive、掛牌地在性質欄以「・上櫃」註記；`kind="other"`
機制保留但常態無成員，且 kind/cat 屬顯示靜態值、`load()` 以當前 WATCHLIST 覆蓋落檔舊值，
改分組不必等 CI 重抓。上櫃技術差異與 kind 無關：etfinfo 未收錄靠種子、Yahoo 報酬 .TW→.TWO
自動退；本家各檔不整列高亮，改在產品名內把「復華」標品牌金色 `.fh`）的
規模／成立日期／過去一週・一月報酬／配息殖利率／收益分配頻率；儀表板 ETF 表只把
「代碼／名稱」識別欄 CSS sticky 凍結（`.etftbl`，`nth-child(2)` left:0；代碼自成一行 `.etcode`、
名稱整段換行 `.etname`＋`min-width:92px` 避免名稱首字被擠上代碼列），手機橫向捲動時
恆可見（性質欄隨捲動移出、不佔凍結空間——兩張表已按性質分組，捲動時不需重複顯示）；
**雙資料來源**（各自獨立降級）：規模／年化配息率／配息頻率 ← etfinfo.tw（Tier B）；
**過去一週／一月報酬 ← 多來源自算**（`_fetch_returns`：stooq → Yahoo → FinMind →
`arm/connectors/twse.fetch_month`，依序取第一個歷史夠密者；以最新交易日收盤對回推 7／30 日曆日
前最後交易日計算，並有「基準日須接近目標日」防呆避免稀疏序列算出錯值）；`ret_src` 記每檔實際
用了哪個源供追查。**報酬為總報酬口徑（2026-07-22 修正）**：Yahoo 抓取帶 `events=div`，區間內
除息加回再算（曾踩：7/16 除息 4.75 的 006208 一週報酬比同指數 0050 多跌整整一個股息），儀表板
報酬格標「＋息X」；債券型（`_BOND_CODES`，收盤天然重複）放寬 `_is_degenerate` 髒序列門檻至 15%，
否則 00986D 全源被誤判髒、報酬整片空。上櫃兩檔 etfinfo 未收錄 → 收盤價由報酬序列末值回填、
規模／首配用 WebSearch 查證種子（`SEED_PERF` 含 `last_div`），年化配息率以配息×次數÷序列收盤自算。
**當月預估配息**（etfinfo 只揭露已實際除息者、抓不到投信預告）：依序 MOPS
（`arm/connectors/mops.etf_distributions`，端點多變、常抓不到）→ **`arm/etfwatch.ANNOUNCED_EST`
人工維護清單**（投信官方已公告之首配／當期預估，除息日未到）。取本月未到期者 → 配息欄「預估 X*」，
過月自動失效。**投信新公告配息時，把 `{code: {amount, ex_date}}` 補進 `ANNOUNCED_EST`**
（來源：各投信官網／經濟日報等；除息後 etfinfo 會接手實際值）。例：00991A 首配 0.77（除息 7/21）、0056 Q3 擬配 1.35。
欄位另含**最新收盤價**（etfinfo 市價）與**最近一次配息**（最近一次「實際」除息金額）；
若投信於配息月已公告該月**預計配息金額**（etfinfo 配息表中除息日在本月且未到期／標記預估者），
於配息欄加註「預估 X*」橘標，*＝投信公告非正式配息金額，實際以除息公告為準。
**配息殖利率一律用年化配息率**＝最近一次「實際」配息金額 ÷ 最新市價 × 配息頻率次數
（月配×12／季配×4／半年配×2／年配×1），不是 trailingYield 近12月回溯值；
追蹤清單改 `arm/etfwatch.py` 的 `WATCHLIST` 即可（含**成立日期靜態值**——不需抓、永不空白）。
**表列順序照代碼字典序（2026-08-05 使用者：「不然有點亂」）**：排序在 `etfwatch.load()` 單一入口
（績效表／詳情卡／代碼泡泡三處自動一致），落檔本身仍是抓取順序、資料層不受影響。
**「即將登場」→ 掛牌日自動加入追蹤（2026-08-05 使用者需求，半自動）**：`etfwatch.watch_tuples()`
＝WATCHLIST＋「`UPCOMING` 有 `list_date` 且已到、尚未轉正」的檔自動升級（kind/cat 用條目選填欄，
不填＝active／主動式；債券檔**務必**填 cat 含「債」——`bond_codes()` 靠它放寬髒序列門檻；
**上櫃檔（櫃買掛牌，如統一 00411A/00987D）kind 照型態填 active／passive、cat 加「・上櫃」**——
2026-08-28 使用者指示分組跟型態走，勿再填 other；etfinfo 未收錄等技術差異自動處理）。
消費端（rows／load stub／fetch_etf_holdings targets）都吃 `watch_tuples()`，掛牌當天 CI 就抓
績效＋持股，stub 先上代碼／名稱／頻率。**仍需人工的兩件事**：①UPCOMING 登錄本身（募集／掛牌
公告無統一 API）；②掛牌後要「轉正」進 WATCHLIST（查證成立日／頻率、補 SEED_PERF）——
`tests/test_etfwatch.py::test_upcoming_graduation_guard` 守著：**掛牌逾 14 天未轉正 → 紅**，
逼下一輪收斂時處理（同持股簡介覆蓋率的逼補模式）。首例＝00410A（8/3 掛牌、8/5 轉正）。
· **⚠ 14 天寬限是「逾期才紅」，不是「可以拖 14 天」（2026-09-03 教訓）**：
  `test_seed_file_loads_and_covers_watchlist` 與 `test_fetch_falls_back_to_seed_...`
  這兩支在**掛牌當天就紅**（`Extra items: '00409A'`——watch_tuples 自動升級進表、
  WATCHLIST/SEED_PERF 卻沒有它）。當天判斷「pytest 紅但不擋當日新聞推送」是對的，
  **錯在只在推播附註一句就放著**，隔天使用者才問「ETF 淨值是不是沒更新到」——那時
  儀表板上本家新檔已掛「底稿」標籤、配息頻率空白整整一天。**pytest 見這兩支紅＝
  當天就要轉正**（本家檔尤然，見「本家復華新檔最優先、絕不可漏」），graduation guard
  的 14 天是最後防線、不是排程。
**「即將登場」五狀態三分組改版（2026-08-10 使用者兩輪指示：研討會投影片抓包資料不齊全＋
「太長記得分類一下，尤其是只有核准還沒確定募集時間的」；2026-08-28 加第四組
「已送件・審查中」＝gap 檔 pipeline 自動展示，見步驟 9⑧ 該條）**：
① 狀態＝募集中(now)／即將募集(soon)／掛牌 MM/DD(list)／**募集結束・待掛牌(pend)**／
  已核准・時程未定(hint)——舊版募集結束沒掛牌日的檔會**直接消失**（統一雙檔 8/7 募完當天
  就從版上不見，這是「不齊全」主因之一），現以待掛牌續留最長 45 天；
② `upcoming()` 回三組：raising（卡片）／listing（卡片）／**approved（hint 獨立第三組，
  `_upcoming_hint_row()` 精簡列**——這類條目常一掛一個多月、資訊只有「核准了」，不佔卡片）；
  hint＝`raise_hint` 文字＋`asof` 查證日，**允許 `code: None`（顯示「代號未定」，未派碼常態）**，
  日期公告後改填 raise_start/list_date 即自動移入上方分組；
③ 視窗：已公告掛牌日 **14→45 天**（00409A 的 9/2 一公告就看得到）、募集起日 45 天、
  待掛牌／核准待定各 45 天；募集期間優先於掛牌呈現，募集卡帶「預定掛牌 MM/DD」副標；
④ **`track: False`＝僅前瞻展示、掛牌後不進追蹤表**（海外被動指數檔：009829 大華銀KOSPI50／
  009827 玉山算力／009828 中信台日韓PCB——被動組是策展的 6 檔台股大表，勿自動塞入污染）；
⑤ 守門 `test_upcoming_stale_entries_guard`：募集結束逾 30 天無掛牌日／核准待定（asof）逾 45 天／
  掛牌逾 30 天未清理 → 紅（過期自動下架只是遮問題，守門逼收斂才是防呆本體）；
⑥ **維護 SOP**：每日台股新聞見「新 ETF 核准／開募／掛牌」公告（尤其本家）→ 隨手 WebSearch
  查證（代號／募集期間／掛牌日／頻率，兩來源一致）補進 `UPCOMING`；全面盤點用
  **MoneyDJ 新基金頁 `moneydj.com/funddj/fundmarket.djhtm?a=broncho-1`**（2026-08-10 使用者
  提供之權威彙整；本容器 proxy 擋 moneydj，用 WebSearch 摘要或交給正式區）＋工商時報月度
  「投信新基金」盤點稿；只有核准沒時程（如安聯加密科技、大華銀非投等債）→ hint 形態登錄。
⑦ **條目儲存位置＝`data/etf_upcoming.json`（2026-08-10 起，勿再寫回程式碼）**：
  `etfwatch.UPCOMING` 由 `_load_upcoming()` 讀該檔 items（載入器 fail-open 回空、tests 會紅）。
  搬出程式碼的原因＝每週「ETF 募集週掃」Routine（見下方專節）只推**資料檔**就能經 daily.yml
  併檔段自動入 main 上線，**不需人工 merge 程式碼分支**；daily.yml 併檔段有雙防呆：
  JSON 驗證失敗（壞檔）→ 保留 main 現有版；分支 `as_of` 舊於 main → 不倒灌。
  **改條目＝改 JSON（記得更新頂層 `as_of`＝今日）；改狀態機制／視窗常數才動 etfwatch.py。**

**新 ETF「自動發現」層 `arm/etfdiscover.py`＋`scripts/check_new_etfs.py`（2026-08-10 使用者：
「你是怎麼確保之後都抓得到的呢？」）**——**這條是上面所有守門都補不到的洞**：graduation／
stale guard 都只認得「已登錄」條目，**一檔從沒登錄過的 ETF 對所有測試而言不存在、不會有
任何東西變紅**（08-10 那 4 檔就是靠使用者的研討會投影片才發現）。兩層互補、CI 端每日跑
（`daily_fund.sh` 步驟 3.6，`|| true` 不擋發佈）：
- **① 市場首見台帳（掛牌層，零版式風險）**：TWSE＋TPEx 官方每日收盤取全市場代碼，篩 ETF 型
  （`^00\d{2,4}[A-Z]?$`，個股／ETN 02／權證 03-08 開頭都不會誤入）記入 **`data/etf_seen.json`
  （必須入庫，`.gitignore` 已加例外）** 的「首見日」。首見日在近 `DISCOVER_DAYS`=60 天內、
  又不在 WATCHLIST+UPCOMING → 缺口。走 CI 已用數週的官方端點，抓到時已掛牌（**下限保證：
  沒有任何一檔新 ETF 會完全從雷達上消失**）。
- **② 募集頁前瞻層（雙源、皆 fail-open）**：**交叉條件是關鍵**——募集中的新檔還沒掛牌、
  不在①的台帳裡，所以 `頁面內容 − 已掛牌 − 已登錄 = 真正的新募集候選`，既有 ETF 的參照
  連結自動被濾掉，**版式漂移也不會誤報一堆**。解析失敗＝回空＋印 CI 日誌（grep
  `[新 ETF 發現]`），只損失前瞻性、不影響①。兩源互補：
  · **MoneyDJ 新基金頁＝代碼層**（掃 `00\d{2,4}[A-Z]?` token；CI 可達性未驗證過、可能 WAF）；
  · **鉅亨 IPO 頁 `fund.cnyes.com/IPO/index.htm`＝名稱層**（2026-08-10 使用者提供；cnyes 對
    CI 可達已由 cnyesfund 連接器天天證實，是前瞻層最可靠的一支）——頁面列「基金名稱＋募集
    期間」無代碼，走 `_norm_name()` 正規化比對（去括注／主動式／ETF／基金等詞；<4 字泛稱
    不比），**未派碼的新檔（代碼層天生抓不到）也逮得住**；已掛牌的既有 ETF 廣告連結由
    「台帳名稱」比對濾掉。同一檔可能被兩層各報一筆（無代碼對不上名稱）——週掃補登後一起
    消失，可接受。附結構探針：CI 日誌印內嵌物件鍵名，日後要補「募集期間」欄位一輪收斂。
- 缺口寫 **`data/etf_upcoming_gap.json`（入庫）** → 儀表板「網頁更新時間」列警示章
  （`_new_etf_chip()`）→ SOP 步驟 9⑧ 分級處置（同「前十大持股簡介」的逼補迴路）。
  **警示三級（2026-08-10 使用者：紅章 13 檔長名稱「很躁」，勿走回頭路）**：
  🔴 紅＝`kind=listed` 已掛牌真漏網（附代碼，每日立即補）；⚠ 琥珀＝已核准／募集中待登錄
  （只給檔數不列名稱清單——長名稱堆版頭只是噪音，清單在 gap 檔週掃讀得到）；
  申請中（stage=applied）在 `save_gap()` 資料層就分流進 **`pipeline` 欄**——不進 count、
  不上版，核准後下輪自動升入 items 才計數。
- **第三種狀態 `not_tracked`＝「已掛牌、看到了、刻意不追蹤」（2026-09-21 新增，009829 實例）**：
  **stale guard 與發現層原本互相矛盾**——前者要求「掛牌逾 30 天的條目清出 UPCOMING」（對的，
  否則「即將登場」永遠掛著已掛牌舊檔），但條目一離開 UPCOMING，`known_codes()` 就再也不認得它，
  於是**每天判成 🔴「已掛牌未登錄」真漏網**。009829 大華銀韓國KOSPI50（`track:false` 海外被動檔）
  就是 09-20 週掃依規清理後，隔天起天天誤報——儀表板紅章＋**4 個 pytest 連紅**（`known_codes`／
  seminar／upcoming_view／freshness_view 各一）。**兩邊都沒錯，缺的是第三種狀態。**
  · 登記處＝`data/etf_upcoming.json` 頂層 **`not_tracked`**（與 UPCOMING 同檔＝週掃只推資料檔
    即可經 daily.yml 併檔通道自動入 main；該通道只驗 `items`，新增頂層鍵原封帶過）；
    欄位 `{code, name, issuer, list_date, why, asof}`——**`why` 必填**，這是「把判斷記下來」
    而不是「把警示關掉」，日後要複核才有依據（tests 有守）。
  · `etfwatch.NOT_TRACKED`（`_load_not_tracked()`，壞檔 fail-open 回 `[]`＝該檔重新被警示，
    **寧可多警示、不可靜默漏掉真新檔**）→ `etfdiscover.known_codes()`／`known_names()` 都吃。
  · **`load_gap()` 讀取端再濾一次已登錄代碼**：gap 檔是 CI 快照，補登後到下一輪重算前紅章
    會繼續掛著（補的人看不到自己補好了，以為沒生效）——現在補登後**下一次重建即滅章**，
    `count` 一併重算（否則章上檔數與清單不一致）。未派碼條目（`code: None`）一律保留。
  · **何時該用**：只給「已確認掛牌、且我們決定不納入追蹤表」的檔（目前＝海外被動指數檔，
    因為被動組是策展的 6 檔台股大表）。**本家復華新檔一律不得列此**——那是要轉正進 WATCHLIST 的。
- **三個踩過／預防的坑**：①**baseline**——台帳空時把當下全市場一次認列既有（`first: None`）、
  不報警，否則第一輪噴出市場 200+ 檔；②**baseline 只在市場檔數 ≥`MIN_MARKET_FOR_BASELINE`=100
  時才建**——首建那輪若剛好單邊交易所掛掉（2026-08-05 tpex openapi 曾整輪失敗），
  baseline 只含半個市場，隔天另一半全被誤判成新掛牌；③**來源不可達時「不覆寫」也「不新建」
  gap 檔**（08-10 實跑抓到）——覆寫會把 CI 的真缺口洗成 0、新建則把「沒檢查」寫成「0 缺口 🟢」
  跟著 commit 進去，就是本專案反覆踩的靜默失敗。本容器 proxy 擋 twse/tpex/moneydj/cnyes → 本地跑
  一律 ⚪「未檢查」屬正常，真正的檢查在 CI。
- **CI 首輪實測定案（2026-08-10 run 31351244025，三項修正已入庫，勿走回頭路）**：
  · **baseline 353 檔正常建立**（twse 236＋tpex 117），掛牌層本輪 0 缺口＝符合預期；
  · **MoneyDJ 對 CI 其實可達**（54,564 bytes、非 WAF 空殼）——但**掃出 0 個代碼，因為
    新基金募集頁本來就只列名稱與募集期間、新檔多半尚未派碼**。故代碼層對該頁天生無效，
    已改與 cnyes 同走名稱層（代碼掃描留作「日後頁面補上代碼」的加分項，抓 0 不再視為異常）；
  · **名稱比對必須用「子序列」而非「子字串」**：交易所短名是全名的縮寫、中間會跳字，
    首輪因此把 `富邦科技`(0052) vs `富邦台灣科技指數`、`永豐科技趨勢`(00410A) vs
    `永豐台灣科技趨勢` 判成兩檔而誤報。改子序列後 17→13 筆，四筆濾除全數正確
    （另兩筆＝009826 貝萊德世界股票、00991B 貝萊德A級公司債，早已掛牌在台帳裡）；
  · **名稱 regex 不可限定 CJK 起頭**：`10年期AAA至A級…` 的「10」被切掉 → 名稱殘缺、
    對不上任何清單而誤報。現允許數字/英文起頭，另要求 ≥3 個中文字擋掉 `iShares ETF` 泛稱；
  · **結構探針不要借 `cnyesfund._objects_from_html()`**（它錨定 `"cnyesId"`，IPO 頁沒這個鍵
    → 整輪一行都沒印）。改印「首筆名稱周邊 ±220 字原文片段」——同 2026-07-29 元大那輪的
    教訓：**印次數／鍵名無法決斷結構，印上下文片段才能一輪定位**（募集期間欄長什麼樣）。
- **募集表格解析（`parse_offering_table`／`stage_of`，探針一輪就收斂完成）**：鉅亨 IPO 頁是
  **純 HTML 表格**——`基金名稱｜基金類別｜經理人｜申請日｜核淮日期｜募集期間｜申請額度`
  （「核淮」是頁面自己的錯字，比對時兩種寫法都收；欄位以**表頭文字定位**、不寫死欄序）。
  解析出來的三件事讓缺口從「只有名字」變成「可直接查證」：
  ① **階段 `stage_of()`**＝raising（募集期間已定）／approved（核淮日期已下）／**applied（申請中）**
    ——**申請中 ≠ 已核准**，沒有這層分辨會把還在送件的檔當「已核准待募」登錄上板
    （08-10 實例：中信台灣聚焦成長只有申請日、無核淮日期）。
    **且「核淮日期欄非空」≠ 已核准**（同日 CI 第二輪抓到）：該欄會填**狀態字**——
    `115.9.14申報生效` 才是真核准、`審查中` 是還沒過；只看非空會把聯博兩檔與**本家
    復華台美策略**全誤標成已核准。判準＝**含日期樣式且不含審查／申請中等狀態字**；
  ② 募集期間直接就是要的資料，週掃只需再找第二來源核對，不必從零查；
  ③ 基金類別是權威 ETF 判準（名稱字樣只是啟發式）。
  解析 0 列＝fail-open 退回純名稱層、缺口照報並印探針片段，不因版式改動全盤失效。
資料層 `data/etf_watch.json`：`scripts/fetch_etf_watch.py` 逐檔「欄位級合併」，fallback 鏈為
**本次 etfinfo 新值 → 既有落檔值 → 內建 `SEED_PERF` 週報底稿**（成立日一律取 WATCHLIST 靜態值）。
報酬數據標 `perf_asof` 基準日、規模／殖利率標 `as_of` 抓取日，儀表板分別備註（沿用最近可得值時使用者已同意）。
來源 etfinfo.tw 屬 Tier B，正式對外前以各投信官網核對。

**欄序與當日漲跌（2026-07-29 使用者需求）**：欄序＝最新收盤價／**當日漲跌**／過去一週／過去一月／
最近一次配息／換算年化配息率／收益分配頻率／**規模／成立日期（靜態資料移到最右）**。
當日漲跌由 `_returns_from_series` 以同一份收盤序列的末兩點自算（`chg_pct/chg_amt/prev_close/prev_date`），
**除息日以「除息參考價＝前收 − 每單位配息」為基準**並標【除息】——否則整段配息會被算成跌幅
（同 2026-07-22 區間報酬修過的總報酬坑）。抓不到就沿用既有值，絕不洗成空白。

**⚠ 踩過的坑：當日漲跌與收盤價「差一天並排」、方向可能相反（2026-09-03 使用者抓包
「當日漲跌那些是不是沒更新」）**——比「沒更新」更糟，是**顯示前一交易日的漲跌**：
- **同一列的兩個數字本來就不同源**：收盤價 `close_px` ← etfinfo 市價（日期記在 `as_of`）；
  當日漲跌 `chg_*` ← 報酬序列末兩點（日期記在 `perf_asof`）。兩者各自降級、從無一致性檢查。
- **Yahoo 日線對台股 ETF 的當日 bar 不穩定**：2026-09-02 全天 `perf_asof` 在
  `09-02 → 08-31 → 09-01` 之間跳動甚至**倒退**（同一支 API 每輪回不同長度的序列）。
  缺當日 bar 時末兩點退成「前一交易日 vs 再前一日」，照樣寫進漲跌欄。
- **實例**：0050 收 106.80（9/2、台股當天大跌 784 點），表上卻顯示 **+2.07%**——那是
  9/1 相對 8/31 的漲幅，9/2 實為約 **-1.5%**，**方向完全相反**；當日全表 31/36 檔皆如此。
- **為何全綠**：合併端「算不出就保留既有值（絕不洗成空白）」保護了資料不被洗空，卻讓錯位
  靜默上線；CI 完整性斷言只驗籌碼／NAV、不覆蓋此型；run success、check 全過。
  **與 2026-07-29 外資淨空單「靜默凍結」同型**——防護保了資料、沒讓異常可見。
- **修法（呈現層，寧缺勿錯）**：`fund_dashboard._chg_cell` 比對 `perf_asof` 與 `as_of`，
  序列落後 → **不顯示會誤導的數字**，改標 `⚠ 基準 {序列日}`＋tooltip 說明收盤價已到哪天
  （沿用 `_md_stale_badge` 的過期章）。資料層一律不動（保留供追查）；缺日期資訊 fail-open
  照顯示。tests 守四型（落後／同日／缺日期／本無值）。
- **⚠ 這只是「讓錯位可見」，不等於把漲跌算對**：重抓一輪仍給不出當日 bar（不是暫時抖動）。
  要恢復真數字得修抓取層——**可行方向＝改用 etfinfo 收盤價對序列前收自算**
  （106.80 / 108.45 - 1 = -1.52% 即正確值），**但那是「市價 vs 還原收盤」混用、除息日必錯**
  （同上一段的總報酬坑），動之前要先解決口徑問題，勿草率接上。
- **同型自查**：日後凡「兩個欄位來自不同來源卻並排呈現」，都要問一句**它們是不是同一天的**；
  沒有一致性檢查就等於預設它們永遠同步，而降級機制保證了它們遲早不同步。
- **備案 L1＝官方全市場當日收盤表（2026-09-03 使用者：「沒辦法從其他地方補嗎？」）**：
  `_official_day_quotes()` 取 **TWSE `STOCK_DAY_ALL`＋TPEx 每日收盤 openapi**，
  `{code: {date, close, change}}`——**整輪只 2 個請求**（不是逐檔；`get_json` 另有 30 分快取，
  同輪 check_new_etfs／fetch_etf_holdings 打過就是 cache hit），且**直接給 change 漲跌額**，
  連前收都不必找。⚠ **這條是原本漏掉的**：先前只想到「TWSE 月表一檔 3 請求 × 36 檔太貴」，
  沒想到 CI 每天已在打的這支全市場表——ETF 代碼確定在回傳內（新 ETF 發現層正是靠它篩代碼）。
  · **官方權威、非 Tier B**，且是市價口徑（與 etfinfo `close_px` 同一種價，不是 Yahoo 還原收盤）。
  · 基準 `ref = close − change`：**除息日證交所的 change 本就對「除息參考價」計**，
    與 `_returns_from_series` 的除息處理同口徑，不必另外扣息。
  · `chg_asof` 記**來源自報的 date**——官方表若自己也落後，渲染端的日期判準照樣揭露，不假裝當日。
  · **呼叫務必帶 `retries=1, timeout=12`**（`fetch_today_all(**kw)` 已支援透傳）：預設 3×25s
    在來源被擋時會讓整輪空轉——2026-09-03 首版沒帶，**容器內 pytest 直接逾時、38 個連線失敗**
    （同 fundhot 前例）。**測試一律 mock**：`tests/test_etfwatch.py` 有 autouse fixture
    `_no_network_day_quotes` 預設回空，需要它的測試自行覆寫；別讓測試打外網。
- **備案 L2＝etfinfo 自帶前收自算（零請求退路）**：
  `fetch()` 在 as_of **真的推進**時，把覆蓋前的 `close_px` 降級存成 `prev_px`／`prev_px_date`
  （同 `etfholdings.merge_one` 的 prev 慣例；**同一資料日重抓不得降級**，否則 prev 被洗成
  今天自己、漲跌永遠算成 0）。序列的漲跌比收盤價舊時（`chg_asof < as_of`），改以
  `close_px vs prev_px` 自算——**與收盤價同為 etfinfo 市價、口徑天然一致，且零額外請求**
  （不必為此打 TWSE 的三個月月表：一檔 3 請求 × 36 檔 × 多班次，違反「不放大來源站請求」）。
  除息日仍以「除息參考價＝前收 − 每單位配息」為基準（`_DIV_EVENTS`）。
  · **週／月報酬一律不走 L1**：它們要的是密序列＋除息還原（總報酬口徑），落後一天影響很小；
    L1 只治「當日漲跌」這一格。序列夠新時也一律讓序列走。
  · **溯源欄位**：`chg_asof`（漲跌所屬交易日）與 `chg_src`（`yahoo`／`etfinfo_prev`…）。
    **渲染端的過期判準用 `chg_asof` 而非 `perf_asof`**——L1 成功時序列仍舊、漲跌卻是當日的，
    用 perf_asof 判會把正確值誤標過期（舊落檔無此欄 → 退回 perf_asof，行為不變）。
  · **層級＝一路試到拿得到「當日」為止**（序列 → 官方當日表 → etfinfo 前收），不是「寫入就停」：
    官方表落後而前收可用時，會繼續退到前收拿真正的當日值；全部都落後才保留最後一個並揭露。
  · CI 日誌印「當日漲跌走備案：官方當日表 N 檔、etfinfo 前收自算 M 檔」，常態應為 0；
    **持續非 0＝主序列當日 bar 長期缺**，該回頭查來源端（L3＝選源加新鮮度門檻，尚未實作——見下）。
**⚠ 踩過的坑：來源回「不可能的交易日」bar，整表當日漲跌與週／月報酬全錯（2026-09-21
使用者抓包「當日股價變動%都沒有更新到」「你看你 00998A 整個數字都是錯的」）**——
Yahoo 對**全部 36 檔**都多回一個 **2026-09-20（週日）** 的 bar（`ret_n` 66→67），
序列末兩點變成「9/18 vs 9/20」：0050 掛 **-7.15%**（實為 +1.67%）、0056／00986D／00987D 等
10 檔掛 **0.00%**、00998A 掛 **+4.99%**（實為 -0.46%，**方向相反**），連週／月報酬一起中毒
（00998A 一週 +4.66%／一月 +4.37%，實為約 +0.25%／-0.03%）。
- **為何三道防線全放行**：那個假 bar 的日期**比 etfinfo 資料日還新**（chg_asof 9/20 > as_of 9/18），
  而 L1／L2 備案與渲染端 `_chg_cell` 的判準當時都只寫「序列**落後**」（`chg_asof < as_of`）
  ——**超前**反而直接勝過官方備案並繞過過期章，完全靜默（run success、check 全過）。
  同 2026-09-03 那次的教訓沒吃乾淨：當時只補了單邊。
- **修法三處**：①**根因＝入口濾掉不可能的日期** `etfwatch._sane_series()`（未來日／週六日一律
  剔除，套在 `_fetch_returns` 每個來源上）——當日漲跌與區間報酬讀同一條序列，一次止血；
  剔除摘要印進 CI 日誌（`_BAD_BARS`，常態 0 行，多檔同時中＝來源整批出包）。
  ②**判準改雙向**：L1／L2 觸發與 `_chg_cell`／`printview._etf_chg` 全改 `chg_asof != as_of`。
  ③台股偶有颱風補行交易的週六會被一併丟掉——可接受：區間報酬有 12 天容差、當日漲跌有
  官方當日表頂上，「丟掉一個真 bar」遠輕於「採信一個假 bar」。
- **同型自查**：`_sane_series` 只認「日期本身不可能」這一類。**盤中未收盤的 partial bar**
  日期是合法的（2026-09-17 09:28 那輪 0050 給 +2.07%、收盤實為 +1.69%），靠雙向判準擋。

**⚠ 踩過的坑：防呆訊息本身變成新的錯誤觀感——「⚠ 基準 2026-09-20」印了一個週日
（2026-09-21 使用者回報：「當日漲跌全部變成 ⚠ 基準 2026-09-20，週末當然沒有，你這樣
不就全部都是錯誤了嗎」）**：假 bar 那輪落檔帶 `chg_asof=2026-09-20`，而**重建型班次
不會重抓 etf_watch**（afterhours／只改程式碼的 push 都是），於是「新渲染 ＋ 舊髒資料」
的組合讓整張表 36 列全掛「⚠ 基準 **2026-09-20**」——把一個不可能的日期當「基準」印給
讀者，等於宣告系統把週日當交易日，**看起來比顯示錯數字還糟**，而且讀者無從分辨這是
「資料晚一天」還是「壞了」。
- **修法＝把兩種情況分開**（`fund_dashboard.chg_trust()`，螢幕版與列印版共用，避免兩邊
  規則各寫一套漂移——2026-09-21 前確實漂過）：
  · **lag（`chg_asof < as_of`）＝日期有意義**：數字確實來自某個較早的**交易日**，
    印「⚠ 基準 {日期}」讀者就知道「這格晚一天」→ 保留原樣。
  · **bad（`chg_asof > as_of`，或該日落在週末／解析不了）＝日期無意義**：來源給了
    未收盤或根本不存在的交易日 → 一律退成 **`—⚠`**，**該日期只留在 tooltip 供追查、
    不進可見文字**。
- **教訓（同 2026-07-31「版面類驗證不可拿 class 當代理指標」）**：防呆的**訊息內容**
  也要當版面來驗——「擋下錯值」只是一半，「擋下之後讀者看到什麼」是另一半。
  測試斷言一律剝掉標籤與 `title` 後再比（`tests/test_fund_tracker.py::_vis`），
  否則 tooltip 裡的字會讓斷言誤綠。

**⚠ 踩過的坑：etfinfo 對上櫃檔的市價慢一個交易日、卻標成當日（2026-09-21 使用者：
「ETF 的當日淨值上櫃的沒有更新到」）**——逐日實測（`git log -p data/etf_watch.json` 可複驗）：
`etfinfo close_px@D ≡ 官方收盤@D-1`，上市 32 檔則逐日與官方同值，**所以是 etfinfo 的上櫃口徑
問題、不是合併邏輯**：00998A 17.30@9/18 其實是 9/17 收盤（9/18 實為 17.22）、00411A 9.91@9/18
（實為 10.13）、00986D 14.17@9/18（實為 14.20）。
- **為何修不掉**：`as_of` 只要 etfinfo 回了**任一**欄位就跟著 `mkt_date` 推進，而唯一能修正
  close_px 的路徑（序列末值回填）被 `if close_px is None` 擋住＝**只有史上第一輪生效**，
  之後永遠沿用落後值。灰帶更糟：日期標成當日、值卻是前一天，讀者無從察覺。
- **修法＝`fetch()` 新增步驟 ①-b**：收盤價／資料日改以**官方全市場當日表 `day_q`** 為準
  （`qd >= as_of` 即覆蓋，**同日也覆蓋**——上櫃的坑正是「日期相同、值差一天」），
  `src` 記 `official_px+etfinfo`。官方權威（非 Tier B）、市價口徑與 close_px 一致、
  **整輪只 2 請求且 L1 已取過＝零額外成本**，且與 L1 漲跌天然同日（不會再互相打架）。
  `day_q` 取不到（本容器 proxy 擋 twse/tpex）→ 整段跳過，行為與修法前一致（fail-open）。
- **`prev_px` 降級搬到 ①-b 之後**：判準要用最終 `as_of`（官方表可能比 etfinfo 更新）。

**⚠ 踩過的坑：週／月報酬與收盤價不同日、而且每班都在跳（2026-09-23 使用者：「櫃買的淨值跟
所有的報酬率都是錯的」）**——收盤價走官方當日表（①-b），週／月報酬讀 Yahoo 序列，兩者從不對齊：
9/22 晚間起上市 31 檔序列停在 9/21，表上「9/22 收 111.85」配「截至 9/21 的一週 +4.16%」（實為
+5.27%）；02:00 那輪上櫃也拿到落後序列，00998A 一週在 -0.94%／-1.72% 之間跳。修法＝
`etfwatch._anchor_series()`：報酬序列一律錨定官方當日收盤（晚於官方日的 bar 丟掉、同日以官方為準、
只落後一個交易日才補上官方這一點；落後更多不硬接）。L3 的「選源加新鮮度門檻」因此不再需要。
外部核對：00411A 9/22 收 10.48、+2.54%、週 +8.71%（工商時報）與落檔一致。
**同日第二坑（15:35 班實測）：官方當日表「當天還沒更新」時兩道修法都落空**——TWSE／TPEx 全市場表
在 15:35 仍是前一日，①-b 不覆蓋、錨點也沒有當日價：00998A 被 etfinfo 的 9/22 價 17.16 標成 9/23、
當日漲跌 0.00%，36 檔報酬又落回前一日。修法＝**上櫃檔一律不收 etfinfo 市價與資料日**（只認官方表／
序列回填，etfinfo 只取規模配息）；報酬錨點改為「本列最終採用的 close_px／as_of」（上市 etfinfo
與官方同值，官方表未更新時也能錨定當日）。

**⚠ 踩過的坑：併檔通道把 `not_tracked` 洗掉（2026-09-23）**——09-21 週掃在排程會話的舊分支
（分岔自 not_tracked 上線前）改 `data/etf_upcoming.json`，as_of 與 main 同為 09-21，daily.yml 併檔段
只擋「較舊」→ 整份覆蓋，009829 又被判漏網、3 個 pytest 紅。修法＝併檔段改為「分支版缺
`not_tracked` 時沿用 main 的」；根治仍是排程搬家（排程會話分支太舊）。

- **L3（未實作，要做先算請求帳）**：`_fetch_returns` 的選源判準只有「夠密（≥25 點）＋乾淨」、
  **沒有「夠新」**——所以 Yahoo 回一個 65 點但末日停在 9/1 的序列就立刻中選，
  **TWSE（官方、必有當日收盤）根本輪不到**。加新鮮度門檻可治本，但不夠新就往下退會讓
  TWSE 的月表請求量暴增，需先設計節流（例如只對落後檔往下退、或改用一次拿全市場的
  `twse.fetch_today_all`）。L1／L2 已能吃掉多數情況時，不必急著付這個成本。

## 「ETF 詳情」底部區塊（2026-07-30 使用者指定版面架構；取代表內展開列）

**ETF 表列高（2026-07-30 使用者：每一檔都好長）**：識別欄原本堆四行（代碼／名稱／詳情鈕／
Yahoo 連結），手機列高近 180px。現為兩行——`.etline` 讓**代碼與「詳情 ↓」同一行**、名稱第二行；
**Yahoo 對照連結移到「性質」欄**（該欄原本只有一顆分類 chip、大片空白）。列高 71px，有測試守。

**ETF 分頁二級選單（2026-07-31 使用者指示）**：即將登場／ETF 數據追蹤／ETF 持股詳情＆異動
（錨點 `#etf-upcoming`／`#etfwatch`／`#etf-detail`，有測試守選單與區塊 id 對得上）。

**詳情區＝比照「基金詳情」的卡片版（2026-07-31 使用者指示）**：工具列（🔍 搜尋代碼或名稱
＋分類 chips 全部／被動／主動式／其他＋全部展開／收合，沿用 `.fundbar`／`.fg` 樣式）＋
**每檔一張 `<details class="etfd">` 可收合卡**（summary：代碼名稱・性質・揭露日・異動筆數）。
· **內容延遲渲染**：23 檔各含方塊圖＋兩張表，一次全建進 DOM 會讓頁面又大又慢——第一次
  展開才由前端 `shell()` 建出來（`box.dataset.done` 標記，不重建）；上表「詳情 ↓」會展開
  對應卡並捲過去。每張卡各自保有搜尋／排序／分頁狀態（`ST[code]`）。
· **事件用委派**（`root.addEventListener`）：內容是後來才建的，初始化時綁不到。
· **代碼「泡泡」`#edpick`（2026-07-31 使用者：搜尋的地方也要有泡泡可以直接點）**：
  工具列下方照績效表分被動／主動式／其他三排（`.edprow`／`.edplab`／`.edchip`），
  點一顆＝展開該檔並捲過去；選中狀態由 `syncPick()` 統一同步「該檔卡片是否 open」
  （開合來源不只泡泡，還有卡片自身、全部展開／收合、上表「詳情 ↓」）。
  泡泡標籤**去掉「主動」前綴**（那排標籤已寫著主動式，重複只把泡泡撐寬，15 顆會擠成十幾行），
  但 `data-name` 仍存完整名稱供搜尋比對。搜尋／分類同時篩泡泡，整排被篩空時連標籤一起收。
· **踩過的坑：CSS 隱藏規則沒涵蓋新卡 → 使用者回報「按鈕都不能按」（2026-07-31）**：
  `fhide` 規則原本只寫 `.fund.fhide{display:none}`，ETF 卡是 `.etfd`——分類 chips 與
  搜尋**照樣加了 class、JS 也確實有跑**，畫面卻毫無反應，看起來就像按鈕壞了。同批還有
  `.eg`（ETF 分類 chip）沒併進 `.fg` 的樣式（連選中狀態都看不出來）、`#esearch` 沒併進
  `#fsearch` 的樣式（行動版退回原生搜尋框，多一個放大鏡）。**新增這種工具列時三處要一起加**：
  隱藏規則、chip 樣式、搜尋框樣式（現已合併為 `.fund.fhide,.etfd.fhide,.edchip.fhide`／
  `.fg,.eg,.fexp`／`.fundbar #fsearch,.fundbar #esearch`，有測試守）。
  **驗證教訓**：我的 Playwright 探針當時查的是「有沒有加上 fhide class」而不是「元素是否
  真的看不見」——class 加對了就綠。**版面類驗證一律用 `offsetParent!==null`／截圖判可見性**，
  別用 class 當代理指標。
· **踩過的坑：測試在守死碼（同日發現）**：卡片改版後，舊的「單一面板」JS（`#ed-pick` 一族）
  仍留在 `_JS` 裡，因抓不到 `#ed-pick` 而早退＝死碼 195 行；三個 treemap 測試斷言的
  `fig.hidden=`／`ed-mvfoot`／`it.n && it.n!==it.s` **全是那份死碼的字串**，等於測試綠燈
  卻沒有守到線上實際跑的實作。已刪死碼並把斷言改對到現行的 `wrap.hidden=`／`.mvfoot`／
  `it.n&&it.n!==it.s`。**改版後務必確認舊實作有真的移除，別讓測試對著屍體點頭。**
· **標的簡介**：完整持股明細每列下方整寬一列（`tr.introw`，塞在窄識別欄裡會把列高撐爆）。
  對照鍵＝代號（profile 的 `ticker`）優先、名稱次之，來源 `config/holding_profiles.json`。
  **共用 `{代號: 簡介}` 一份**——同一檔股票出現在多檔 ETF，逐檔各存一份會讓內嵌 JSON 多出
  約 200KB。卡片標題標「N 檔附標的簡介」。
· **覆蓋率＝100%（2026-07-31 使用者「當然要另外補資料啊」後補齊，勿讓它倒退）**：
  簡介庫原本只為「基金前十大」而建（69 筆、ETF 持股只蓋到 33.9% 列／51.9% 權重），
  分三批 WebSearch 查證後補到 **372 筆**，ETF 持股 **1102/1102 列全有簡介**。
  兩道防呆：①`tests/test_holdings_intro.py::test_etf_持股簡介覆蓋率不倒退`（權重覆蓋
  < 95% 即紅——CI 抓到新持股時容器端下一輪就會逼補）；②同檔既有的
  `test_all_committed_funds_top10_have_intro` 顧基金前十大。補的格式與注意事項見
  上方「前十大持股『簡介一再漏掉』」專節（key 須是快照內原字串、含 `*` 等後綴）。
· **代號要正規化再查（2026-07-31 踩坑，光這條就白白落空數十檔）**：ETF 快照的海外代號
  是**彭博式帶交易所碼**（`AMD US`／`8035 JP`／`IFX GY`／`009150 KS`），簡介庫存的是
  純代號 `AMD`——不剝字尾就永遠對不上，明明庫裡有卻顯示不出來。`fund_intro.norm_ticker()`
  負責剝（末段為 ≤3 個字母時視為交易所碼），`intro_lookup()` 兩種鍵都收、`_eh_intros()`
  兩種都試。**新增名稱型別（如某站改用全大寫）時記得兩邊都補**，有測試守。

ETF 分頁改成**上表 → 底部詳情**兩層：ETF 數據追蹤表的代碼／名稱欄是「詳情 ↓」鈕
（`.edjump`），點了選定該檔並捲到 `#etf-detail`。詳情區三段（`_etf_detail_view`）；**ETF 選擇器照上方績效表分「被動／主動式／其他」三排**
（2026-07-30 使用者：23 顆 chip 混在一起不好找）：

1. **持股異動方塊圖（單層、不分產業）**——每格＝一檔異動個股，面積 ∝ |金額|
   （＝Δ股數 × 當日收盤；無報價時退回 |Δ股數| 並在說明標明），加碼·新增紅、
   減碼·出清**綠松**色，**亮度 ∝ 幅度**。座標由 **`arm/treemap.py`（squarify）在 Python
   算成百分比**，前端只畫絕對定位 div。四個「別改回去」的決定（皆為使用者實際看過畫面後定案）：
   · **不分產業**（2026-07-30）：產業別對照抓不齊（海外持股、部分上櫃檔沒有），分層後常出現
     「未分類」群組，或小群組高度不足拿不到標籤、緊貼隔壁產業被誤讀成同一群（0050 實測：
     只有一檔的塑膠工業被擠在「電腦及週邊設備業」標籤下）。資訊價值輸給版面代價 → 單層。
     產業名仍留在每格 tooltip、資料層照樣入庫，日後覆蓋率夠了可再分層（`treemap.grouped()` 保留）。
   · **基本格式＝7 格＋「其他」**（2026-07-30 使用者指定），且**每格都必須有完整資料
     ：代碼＋公司簡稱＋金額**。允許兩種標籤幾何、通過任一種即可——squarify 產生的格子
     有方有扁，只認一種會白白折疊掉放得下的格（實測只認寬版時 0050 從 7 格掉到 4 格）：
     **堆疊版 54×58px**（代碼／簡稱／金額各一行）或**寬版 76×40px**（代碼＋簡稱同行、
     金額第二行）。量尺以手機內容寬 `_TM_W_REF=280px` 為準（窄的過了寬的必過）。
   · **面積 ∝ |金額|^0.5（`_TM_AREA_GAMMA`）而非等比**：這是為了同時滿足「7 格」與
     「每格完整」——嚴格等比時單檔佔六成的日子（0050 的台積電）必然把其餘擠成細條，
     7 格根本放不下。排序與相對大小保留、精確數字每格都印著，圖註以 `_TM_AREA_NOTE`
     寫明口徑。**要改回等比就得放棄「7 格都完整」，兩者不可兼得。**
   · **「其他」固定在右下角、顏色壓低**（2026-07-30 使用者：「既然都叫其他了就不要太明顯」）：
     靠 squarify 的性質——由左上往右下逐段填滿，**最後排入者的矩形一定含右下角**，
     所以 `treemap.layout(..., keep_order=True)` ＋「個股遞減、併格排末端」就會落在右下。
     併格亮度固定 0.20（不隨幅度變亮）、標籤改灰白，讓它視覺上退後。
   · **折疊＝「放不下完整資料就降級到其他」**（使用者原話：「如果會在網頁上圖示顯示不出來，
     表示沒那麼重要，那就歸類到其他」）。作法：**排完版 → 逐格檢查 → 降級最小的一格 →
     重排**，迭代到全部通過；判定一律用最大圖高 `_TM_H_MAX`（先盡量留格）。降級者依方向
     併成「其他 N 檔」；連併格自己都畫不出標籤時整格不入圖。**不要改回固定佔比門檻**。
   · **圖高＝維持「每格完整」前提下最矮的高度**（`_tm_fit_height`，132→300px 由矮往高試）：
     格數少就矮、不留大片空白；**但圖一律要畫**（使用者：「圖還是要畫啦，不然不一致看起來
     很怪」），只有「完全無異動」才把整張深色卡與明細表收掉、換一行淺色提示。
   · **面積依據：全部異動都算得出金額才用金額，否則整張圖改用股數**（2026-07-30 使用者：
     「海外的明明有變動但沒有顯示出來」）。原本只要有一筆有金額就用金額基準，結果全球型
     ETF 那些沒有台股報價的海外持股被靜靜濾掉——00988A 的 6 筆異動只畫得出 1 格。
     跨市場股數不宜直接比大小，但「全部看得到」遠比「只看得到一格」重要，圖註會標明口徑。
   · **小格寧可省金額也要留公司名**（使用者：有些只有代號沒有公司名）。
   · **出清標的的公司名要留住**（2026-07-30 第二輪回報「有兩個股票代碼但沒有公司名」）：
     出清標的今天已不在 holdings 裡，名稱只剩 `prev` 留得住——所以 `merge_one` 的 prev
     改成一併存 `name`。補名順序：**prev 存的 → 當日報價（twse/tpex 有名稱）→ 其他 ETF
     的持股名冊（`annotate` 建全體名冊；某檔出清的股票常還在別檔持股中）→ 最後才退回代號**。
     前端另有保險：名稱等於代號時不印第二次（免得看到「2303 2303」）。
   · **帳要平**：入圖格數 ＋ 併格成員 ＋ 未入圖(`hid`) ＋ 無報價(`nq`) ＋ 超出清單上限(`mr`)
     ＝ 異動總數，有測試守。**無報價**＝全球型 ETF 的海外持股（沒有台股報價、算不出面積），
     曾被靜靜濾掉（00990A 的 18 檔異動只畫 1 格、卻沒交代其餘 17 檔）——現在檔數一律回報。
     揭露文案寫在**異動表底下**（`ed-mvfoot`）而非圖註：圖被收掉時那行仍看得見。
   · **配色是算出來的、不是挑好看的**（用 dataviz skill 的 `validate_palette.js` 五項全過）：
     ①**深色畫布 `#14171b`**——深底上不必靠高飽和就有層次、文字一律白色即可讀；
     ②**綠色刻意偏青 `#159c94`**：純紅×純綠在色盲模擬下分離度只有 ΔE 5.9（**不及格**，
     連「有輔助編碼才可放行」的 6.0 底線都不到），紅 `#e6504c` × 綠松 `#159c94` 為 **12.1**
     通過，而台股「紅加碼綠減碼」語意完全不受影響——**別為了「純綠比較像跌」改回去**；
     ③**亮度上限 0.80**（`al=0.28+0.52×比例^0.55`）：白字對比紅 5.2:1／綠松 4.7:1，過 AA
     正文 4.5:1，拉到 1.0 只有 3.4:1；開 0.55 次方讓小額異動仍看得見；
     ④圖例必列兩個方向與亮度意義（顏色不可是唯一線索），新增／出清用**內縮虛線環**
     （亮度已被幅度佔用，不能再拿來表示進出）。
2. **異動明細表**（`.chgtbl`）：`股票（代碼+名稱）｜張數｜金額｜類型 pill`，張數／金額可點
   排序（作用中欄位標 ↓／↑）。**預設張數帶正負由大到小**（加碼在上、減碼在下）。
   預設列 15 檔，超過時「展開全部 N 檔異動」——0050 這類等比調整日會有 50 檔異動。
3. **完整持股明細**（`.hldtbl`）：「共 N 檔持股・快照 YYYY-MM-DD」＋搜尋框（代號或名稱）＋
   `代號/名稱｜漲跌幅/收盤價｜權重/股數｜貢獻度ⓘpp`（皆可排序，**預設權重↓**）＋
   每頁 15 筆分頁。**貢獻度＝權重% × 個股當日漲跌% ÷ 100**；合計不硬湊等於 ETF 市價漲跌——
   現金／期貨部位、費用、揭露時點差都在殘差，表註誠實寫明。

- **為何不再用表內展開列**：整寬 `colspan` 列的寬度＝整張橫捲表寬，內容自然排版只佔左上角
  （使用者兩次回報「展開後超空」）；23 檔各一份明細也把表格拉得很長。底部單一詳情區
  一次解掉這兩件事，頁面反而變小（少了 23 份重複面板）。
- **前端資料以緊湊陣列內嵌**（`window.__EH`）：完整持股全 23 檔逾 1,100 列，物件鍵名會讓
  內嵌 JSON 膨脹一倍——`mv`＝[代號,名稱,Δ股數,金額,類型]、`al`＝[代號,名稱,權重,股數,
  收盤,漲跌%,貢獻pp]（約 75KB）。JSON 內 `</` 必須轉義成 `<\/`，否則 HTML 解析器會
  提前結束 script（有測試守）。
- **產業別對照** `data/stock_industry.json`（**必須入庫**）：`arm/stockmeta.py` ← 上市
  `openapi.twse.com.tw/v1/opendata/t187ap03_L` ＋ 上櫃 `tpex.org.tw/openapi/v1/mopsfin_t187ap03_O`。
  兩家鍵名不一致且改過名 → 解析走「**鍵名關鍵字比對＋值型態驗證**」而非寫死鍵名，
  解析 0 筆時把實際鍵名印進 CI 日誌供一輪收斂（同 cnyesfund／pcf 做法）；產業別欄可能是
  代碼（`24`）或名稱，代碼以 `stockmeta.IND_CODE` 轉名。**尚未入庫時只有一個「未分類」群組
  → 自動改單層顯示**（那層標題不帶資訊）。
- **`etfholdings.view()` 有補算 fallback**：落檔 detail 缺 `all`（舊 schema／CI 當次沿用舊值）時
  就地以 `holdings`／`prev` 補算「完整持股＋異動」——這兩者是純比較、不需網路，只有收盤價與
  當日漲跌非連網不可；補算後把舊 detail 已有的報價／貢獻依代號嫁接回來（不憑空補價、
  也不讓詳情區空著）。
- **本機驗版可用 Playwright 截圖**（2026-07-30 實證）：Vercel 線上頁被 proxy 擋（CONNECT 403），
  但 **`file://` 開本機 `dashboard/index.html` 完全可行**——`p.chromium.launch(executable_path=
  "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")`，截圖前先把 `.topbar`／`.backtop`
  設 `display:none`（固定元素會蓋住被截的區塊）。版面類需求（treemap、表格排版）從此
  不必等使用者回報螢幕截圖。

- 資料層 `data/etf_holdings.json`（**必須入庫**，`.gitignore` 已加 `!` 例外）：`prev` 存前一揭露日
  股數／權重，**沒有它就沒有「今日 vs 昨日」可比、Δ 整片是 —**（同 etf_watch／fund_nav_history 的坑）。
  合併鐵則 `etfholdings.merge_one()`：本次抓不到＝原封保留；**同一揭露日重抓不可把 prev 洗成今天自己**
  （否則 Δ 全變 0、看起來像「都沒異動」）；揭露日推進時才把舊 holdings 降級為 prev。
- **貢獻在 CI 端算好存進落檔的 `detail`**（`etfholdings.annotate`，個股報價 ← `twse/tpex.fetch_today_all`）——
  容器內 proxy 擋 twse/tpex，建表時取不到報價；儀表板端 `etfholdings.view()` 只讀 `detail` 純渲染。
- **踩過的坑：假的「本次無異動」（2026-07-30 使用者發現 00991A）**——`fhtrust.fetch_holdings`
  原本把**我們請求的日期**當資料日回傳（`"date": iso_date`），但 assetsExcel 端點對不同 ymd
  可能回同一份檔案 → 揭露日往前跳、內容一模一樣，`merge_one` 把舊快照降級成 prev，Δ 全變 0，
  看板顯示「持股股數沒有變化」。**識別法：權重也全等**（權重是市值比重，兩個不同交易日
  不可能 49 檔全部到小數第三位都相同）。三道修法：
  ① `fhtrust._meta_date()` 從 xlsx 單格 meta 掃**檔案自報的資料日**（西元／民國都收），
     以它為 `date`；掃不到才回退請求日，並在 CI 日誌標「⚠ 檔案未見日期、沿用請求日」。
  ② `merge_one` 加「同一份快照」防呆：新舊 holdings 的**股數＋權重全等** → 當同一次揭露
     重抓，**不推進日期、不動 prev**（寧可少報一天鮮度，也不假造零異動日）。
  ③ `_drop_fake_prev()`：既有落檔的 prev 與今日 holdings 全等 → 就地清掉，誠實顯示
     「尚無可對比的前一揭露日」。**etfinfo 來源不受影響**（snapshotDate 是官方欄位，
     實測 21 檔權重都有變動）。
- **踩過的坑：跨來源 diff 的假「全部出清」（2026-08-05 使用者發現 00986D：「全部出清？
  加碼的也出清？」）**——`prev` 存的是前一揭露日的清單、`holdings` 是今天的，**兩者出自
  不同來源時「揭露範圍的差異」會被整批算成新增／出清**。實況：00986D 07-30 fhtrust 的
  xlsx 掃不到檔案自報日期（排序鍵退成空字串）→ **同一個揭露日被 etfinfo 頂掉**，etfinfo
  多給的 11 列（`202609US`／`202609TY` 公債期貨、`M_*` MARGIN、`DA_*` 扣除應付證券款、
  `PFUR_*` 應付買回款、`TLTW US`）全被判「新增」；隔天 fhtrust 回來、揭露日推進 →
  同樣 11 列又全被判「出清」。其中 `PFUR_NTD`／`DA_USD`／`M_AUD` 的前日股數是**負數**
  （應付款），出清 Δ ＝ 0 −(負) ＝ **正值**，於是表上出現「+14,749 張」卻標出清——
  就是使用者說的「加碼的也出清」。**三道修法（缺一不可）**：
  ① **列宇宙對齊 `etfholdings.drop_non_holdings()`**：現金／保證金／應付款／期貨等
     非持股列一律不進 diff（fhtrust 本來就不給、etfinfo 的 PCF 快照會給）。判準＝
     代號 `^(M|DA|PFUR|…)_[A-Z]{3}$`／期貨合約 `^20\d{4}[A-Z]{2,3}$`（年月＋商品碼）／
     名稱含 MARGIN·PAYABLE·AFTER DEDUCTING·現金·應付…。**別誤殺帶交易所碼的外股**
     （`TLTW US` 有空格、不符期貨式樣）。抓取端三個來源共用。
  ② **來源切換時不判定新增／出清**（`contributions` 的 `xsrc`）：`merge_one` 現在記
     `prev_src`；`prev_src != src` 時只比共同持股的加減碼，detail 標 `xsrc=[舊源, 新源]`，
     儀表板異動表底下（`mvfoot`）寫明「僅比對共同持股」。**這是最後一道防線**——
     真出清與「對方沒揭露」本來就分不出來，寧可少報也不假造。
  ③ **換源必須換到更新的快照**（`fetch_etf_holdings._prefer_incumbent`）：贏家不是既有
     來源、既有來源這次也抓得到、且**快照日沒有比既有揭露日更新** → 維持既有來源。
     真有更新的快照時照換（00991A 靠 etfinfo 頂著的情境不受影響）。
  · **待查**：`TLTW US`（權重 3.5% 的 ETF 部位）只出現在 etfinfo，復華 xlsx 沒有——
    若它本該在，就是 `fhtrust._parse_xlsx` 漏了某個區段。抓取端已加「列宇宙差異」
    CI 日誌（僅 fhtrust／僅 etfinfo 各列前 6 個代號），下一輪 run 讀日誌即可判讀。
- **抓取＝彙整站雙源（2026-07-30 最終定案，使用者指示「不必抓官網第一手，彙整站＋雙重驗證」）**：
  `scripts/fetch_etf_holdings.py`＋獨立 workflow `.github/workflows/etf_holdings.yml`
  （台北週一~五 17:40；純 HTTP、每輪數十秒）。
  - **主來源 etfinfo.tw**（Tier B）：`GET /api/etf/{code}` 的 holdings 欄位＝**完整每日快照**
    （stock_id/weight/shares＋snapshotDate），既有連接器 `arm/connectors/etfinfo.py` 的
    `holdings_fresh()` 早已封裝；CI 每天抓規模／殖利率就在打同一 API，可達性已被證實數週。
  - **副來源 Yahoo 股市持股頁**（Tier B）：`tw.stock.yahoo.com/quote/{code}.TW/holding`
    SSR 內嵌 JSON（`parse_embedded_json`；代號帶 .TW/.TWO 字尾已在 `_row_from_mapping` 去尾）。
    **MoneyDJ 已試過並移除**（2026-07-29 實測：basic0007 頁 table×0、SSR 表格已不存在）。
  - **雙重驗證 `etfholdings.cross_check(weights=False)` ＝「構成驗證」**：Yahoo 持股是**月度基準
    前十大**、etfinfo 是每日 PCF 快照——**跨基準日比權重是方法錯誤**（實測 19/21 檔被誤判
    mismatch，權重差 1.2–4.2pp 全是時點差）。只驗前十大構成重合 ≥60% → 🟢「構成相符」；
    重合過低 → **weak「副源過舊・未能驗證」灰章**（多為月內調倉，**不是**主來源錯誤的證據，
    如 00929 月內大調倉重合僅 3/10）；僅一源 → single。紅 ⚠ mismatch 保留給未來同基準日源的
    真衝突。**不比股數**——兩站口徑常不同，比了誤殺。驗證結果存 entry `verify` 隨 detail 入板。
  - **主來源＝快照日最新者，不再硬性「第一手優先」（2026-07-30 使用者：「不能用 etfinfo 頂著嗎」）**：
  復華 assetsExcel 可能連日回同一份舊檔，硬性優先會讓 00991A 天天顯示假的「無異動」。現行規則：
  ①各來源用**自己的快照日**（etfinfo＝官方 `snapshotDate`；fhtrust＝檔案自報日，見下方坑）；
  ②**fhtrust 的日期只有「檔案自報」時才拿來比大小**，沿用請求日的視為未知、排在 etfinfo 之後；
  ③同一天時仍讓第一手 fhtrust 勝（可與 etfinfo 做真正的權重驗證）；④Yahoo 無快照日、永遠墊底。
  曾踩：`fresh[code]["date"]` 對 fhtrust 來源直接寫 `fallback_date`（最近交易日），
  完全沒用到檔案日期——這是 00991A 被標成當日的直接原因。
- **本家三檔（00991A/00998A/00986D）走復華官網 assetsExcel（Tier A 第一手）**：
    `config/products.json` 對映 `fund_id`（ETF23/24/25），舊管線 `arm/pipeline.py` 本就
    以此抓三檔（含前後快照 diff、**排除期貨避險列**——沿用此慣例）。順序＝fhtrust →
    etfinfo（同為每日 PCF 基準，**且兩源快照日相同時**做真正的權重驗證「🟢 雙源相符」，
    否則只驗構成）→ Yahoo。外股 ticker（'C US'）與債券（面額）原生支援；海外持股
    「個股當日漲跌/貢獻」因無台股報價顯示 —（誠實降級）。**2026-07-29 教訓：曾誤標
    00998A/00986D「結構性不支援」——使用者指正後發現限制在自己的 schema（台股 4 碼驗證），
    不在資料；下結論前先查 products.json／既有管線（pipeline.py）有沒有現成能力。**
  - **為何獨立 workflow**：不佔 `daily.yml`「07:03 前線上可看」的關鍵路徑。**已排進每日循環
    （2026-07-30 使用者指示）**：本 job 台北週一~五 17:40 抓持股後**直接重建儀表板＋commit＋
    打 Deploy Hook**——當日貢獻當晚上線，不等隔日早上；早上 daily.yml 重建時亦自然帶入
    main 上最新持股檔。失敗不影響任何現有功能。儀表板「網頁更新時間」有「ETF 持股揭露」
    鮮度列（停更逾 3 天列入紅色逾期警示＝該 workflow 掛了）。
  - **投信官網第一手＝已放棄的路線（逐家逆向 7 輪＋無頭瀏覽器 3 輪的結論，勿走回頭路）**：
    官網幾乎全是 SPA、持股靠 XHR，群益還在 Incapsula 防護後面；瀏覽器雖過得了 WAF，但復華等站
    頁面只 render 前十大、拿不到完整清單。`fetch_etf_holdings_browser.py` 保留為備援、不排程
    （其「攔截 XHR＋DOM 解析＋列表頁自尋」機制若日後需要可直接復用）。
- **第三方交叉驗證＝純 HTTP 已證實不可行（2026-07-30 兩輪 CI 探針，使用者決定收在這裡）**：
  使用者核可三站後實測——**玩股網** `www.wantgoo.com/stock/etf/{code}/constituent`
  兩個 URL 皆 **403**（WAF 擋機房 IP；它的資料基準最理想：官方說明寫含「櫃買中心公開揭露之
  申購買回清單」、每交易日更新，也是唯一涵蓋上櫃的候選，可惜拿不到）；**CMoney**
  `www.cmoney.tw/etf/tw/{code}/fundholding` HTTP 200、259KB，但持股全在 XHR 後面
  （HTML 內「成分股」只出現在 meta 文案；bundle 改成 HEAD 問大小、由大到小深掃主檔後
  **仍找不到任何持股相關端點**）；**ETF觀測站** `fundclear.com.tw`（集保）是**基金**觀測站，
  bundle 撈出的 API 全是 `/api/performance/*`、`/api/offshore/*`，不做 ETF 持股。
  → **結論：要再撿起來只有瀏覽器路線**（`fetch_etf_holdings_browser.py` 已有攔截 XHR＋DOM
  解析的機制；玩股網若是擋 UA／無頭特徵則有機會，若是擋 IP 信譽則一樣不通）。
  現行驗證維持「etfinfo 主＋Yahoo 驗構成」；本家三檔第一手 fhtrust。探針程式碼保留
  （`pcf.third_party_cands()`／`probe_third_party()`，只在 `--probe` 模式跑、不在正式路徑）。
  **決策背景**：第三方源的價值在「假無異動」修好後已從「補涵蓋」降為「多一個驗證章」——
  00998A／00986D 本來就有真實 Δ，不需別人補。
- **`etf_holdings.yml` 有 `probe` 輸入開關**：只跑探針、跳過重建／commit／部署，且
  **探針模式 checkout 被 dispatch 的分支**（正式抓取仍固定 main）——曾踩：workflow 檔取自
  分支、程式碼卻取自 main，探針跑的是舊腳本、日誌零輸出。
- **純 HTTP 路線（`arm/connectors/issuers/pcf.py`）保留為解析層與備援**——沒有跨投信統一官方端點
  （2026-07-29 查證：證交所／櫃買／政府開放平台皆無彙總 API，各投信自行在官網揭露）→
  做成「**候選 URL＋通用解析＋探針**」：
  每檔依序試候選來源，通用解析吃 JSON／HTML 表格／xlsx（重用 `fhtrust._parse_xlsx`），
  抓不到就印 HTTP 狀態／content-type／內容前段。**收斂方式：跑 `scripts/fetch_etf_holdings.py --probe`
  於 CI，讀日誌逐家證實後改 `_cands()`**（同 cnyesfund.py 當初 6 輪 CI 收斂的做法）。
  已知可用型態：元大 `www.yuantaetfs.com/tradeInfo/pcf/{code}`。抓不到的檔安靜降級（該 ETF 就沒有
  展開明細），不影響其餘欄位與其他 ETF。
- **第 1 輪 CI 探針結果（2026-07-29，run 30420827829）**：野村 HTTP 500、統一 302 無限轉址、
  群益／安聯／證交所 ETFortune 全回 **SPA 外殼 HTML**（持股由 JS 動態載入）→ 靜態 HTML 抓不到，
  真正的清單在 XHR 後面。因此探針加 `_api_hints()`：抓到 SPA 外殼時**從 HTML／內嵌 JS 撈出疑似
  資料端點印進日誌**，一輪就能收斂，不必一輪換一個猜測網址。
- **第 2 輪 CI 探針結果（2026-07-29）**：①假陽性防呆生效（日誌現出 `[判為非持股清單：3 檔、帶量 0 檔]`）；
  ②**元大 `tradeInfo/pcf/{code}` 回 1.07 MB HTML**（不是空殼）但表格解析 0 檔 → 資料是**內嵌在 script
  的 JSON**，與 cnyesfund 當初完全同型 → 新增 `parse_embedded_json()`（平衡物件掃描、原文＋反跳脫各試
  一次、只認帶權重或股數者）。③`_API_HINT` 舊版無詞界的 `api` 會匹配 c-**api**-tal（群益 capitalfund），
  整排 hint 都是導覽連結 → 已加詞界。④新增 `_key_hits()`：大頁面零結果時列出疑似鍵名命中次數，
  用來區分「真 SPA 外殼（該找 XHR API）」與「資料就在頁面裡、只是鍵名不同（該補鍵名）」。
- **第 3 輪 CI 探針結果（2026-07-29）**：元大 1.07MB 頁面回
  `鍵名命中={'shares':24,'weight':191,'股數':10,'權重':59,'比重':7,'成分股':63,'持股':9}`
  但 **stockNo／stockId／stockCode 全 0 次** → 代號欄叫別的名字，平衡掃描的錨點一次都沒觸發；
  且 `weight` 那 191 次多半是 CSS `font-weight`（假訊號）。群益的 `證券代號` 只出現 3 次且是
  HTML 文字非 JSON 鍵，帶引號的錨點也匹配不到。修法：①錨點鍵名放寬到
  `code/id/symbol/ticker/secId/secNo`（`_KEY_ID` 同步補 symbol/ticker，否則錨點觸發了
  `_row_from_mapping` 仍取不到值）；②`_key_hits` 扣掉 `font-weight` 假訊號；
  ③**`_key_hits` 改印「資料錨字末次出現的上下文原始片段」**——只印次數無法決斷是
  HTML 表格／內嵌 JSON／純樣板，印片段才能一輪定位結構、不必再猜。
- **第 4 輪 CI 定案：「從頁面 HTML 撈持股」是死路，別再往這條調解析器**。上下文片段證據：
  元大「成分股」末次上下文是**費率表／指數編製規則文案**（`…以下(含)：0.10%…Quarterly re-balance…`）、
  群益「證券代號」是**基金公告內文**（`【基金公告】…群益半導體收益（證券代號：00927）…`）。
  那 1 MB 的元大頁面是把全站文案與路由打包的 SPA bundle，**持股資料不在 HTML 裡、全靠 XHR**。
  → 主力改為 `_bundle_api_hints()`：**從 `<script src>` 抓 JS bundle、再 regex 找 API 路徑字面值**
  （SPA 呼叫的端點一定寫在 bundle 裡）。節流鐵則：**每站台每次執行只掃一次、最多 3 支 bundle**
  （`_bundle_cache` 以 host 為鍵）——23 檔逐檔重掃會對投信站發出上百個不必要請求。
- **第 5～6 輪：bundle 路線有效但踩到自家 bug**。第 5 輪元大 bundle 掃出 **`/api/bridge`**
  （通用 API 閘道，光有路徑打不出請求 → 已加「呼叫脈絡」把端點前後 ~360 字元程式碼一併記錄，
  看得出 method 與 body 參數名）。第 6 輪逐支診斷才發現：群益「bundle」424450B、安聯 9437B
  **與各自的 HTML 頁面同大小** ——**SPA catch-all 路由把 index.html 原封回給任何 .js 路徑**，
  我卻當成 JS 在掃，白掃三輪。防呆：**回應以 `<` 開頭或位元組數等於頁面 → 判為 catch-all 假 bundle**，
  日誌講明；並列出「頁面 script 共 N 支：檔名…」以便挑對主 bundle（元大只抓到 3.3KB 小 chunk）。
- **假陽性防呆 `is_plausible()`（第 1 輪就踩到，務必守住）**：通用解析從 ETFortune 頁面的
  **其他 ETF 推薦連結**刮到 `0050 元大台灣50／0056 元大高股息／0052 富邦科技`，權重股數全 None，
  卻通過舊的「≥5 列」門檻 → 兩檔 ETF 上線了完全錯誤的展開明細。三道驗證：①檔數 ≥10；
  ②**過半列須帶權重或股數**（沒有數量就算不出貢獻）；③不可整份都是 0 開頭的 ETF 代碼
  （只排除「全部」，才不會誤殺真的持有其他 ETF 的組合）。新增 adapter 後務必確認仍過這關。
- **排序配對**：表格排序的 JS 必須把附屬展開列（現存者為總經三大法人的 `.mdsub`）當
  「附屬於前一列」一起搬——獨立排序會與母列脫鉤，且它只有一個 colspan 欄，`cells[i]`
  為 undefined 會讓整個排序爆掉。（ETF 表 2026-07-30 起已無展開列，明細移到底部詳情區。）

**踩過的坑（勿再犯）**：
- `data/etf_watch.json` 曾被 `.gitignore` 的 `data/*` 擋掉沒入庫 → CI 從零抓、etfinfo 缺欄 → 成立日期／
  週月報酬整片變 null。已在 `.gitignore` 加 `!data/etf_watch.json` 例外，此檔**必須入庫**當 fallback。
- 欄位級 fallback 用「值是否為 None」判斷，**不可用 `dict.get(key, default)`**——CI 曾把欄位寫成顯式 `null`，
  `get(key, default)` 會回傳那個 null 而非 default，反而把資料洗空。用 `arm/etfwatch._pick()`。

## 基金多期報酬「每日基準」覆蓋層（2026-07-15 新增，鉅亨 Tier B）

**官網 `/api/fund` 的多期報酬（roiY2D/roi3m/roi1y…）是「月底基準」**——git 史實測 NAV 天天動、
YTD/1y 十四天不變（皆上月底值），使用者已明確要求每日基準。解法：`arm/connectors/cnyesfund.py`
（2026-07-15 歷經 6 輪 CI 收斂的**最終架構**，勿走回頭路）：
- **取數路徑＝「釘選 cnyesId → 直取詳情頁」**：`data/cnyes_fund_map.json`（**入庫**）存全部
  25 檔的 cnyesId（WebSearch 逐檔查回並核對 share class）；詳情頁 `fund.cnyes.com/detail/x/{cnyesId}/`
  的 HTML 以 `_objects_from_html()` 平衡物件掃描抽資料（頁面無 __NEXT_DATA__、狀態以他形內嵌）。
  **新增基金時：WebSearch 查其鉅亨詳情頁 URL、把 cnyesId 補進 map 檔即可。**
- **死路備忘（CI 實測，勿再試）**：`fund.api.cnyes.com` 全路徑 404；`gfe-fund.cnyes.com` 任何
  路徑都回同一張 XHTML 舊頁；搜尋頁 `fund.cnyes.com/search/` SSR 不吃 query（任何 keyword 都
  回同 20 筆熱門清單，名稱比對必零命中）。
- 詳情頁實際鍵：`return1Month/3Month/6Month/1Year/returnYTD`＋`nav/priceDate/change(Percent)`；
  **無 1週／2年／3年獨立鍵**（1週回退自建 NAV 序列自算、3年回退官網月底值——混合基準已在
  總覽副標註明）；複合鍵 `returns` 內部結構每日於 CI 日誌印出（debug 首檔），未來可再收斂。
- `fetch_holdings.py` 抓完官網後 `cnyesfund.apply_overlay()`：寫 `returns_daily`＋`returns_daily_asof`
  進 `data/funds/*.json`；鉅亨 NAV 日**較新**時一併覆蓋 nav（標 `nav_src="cnyes"`）。
- 儀表板 `overview_rows()` 逐欄 fallback：**鉅亨每日值 → 官網月底值**；1週/1月再多一層 → 自建
  NAV 序列自算。總覽區有「多期報酬」鮮度 chip。
- **此容器 proxy 擋 cnyes（CONNECT 403）**——**用 CI 日誌（`mcp__github__get_job_logs`）驗證與
  迭代**，勿在本容器嘗試打 cnyes。整層失敗只是回退官網值，不會壞版面。

## 基金總覽「1週／1月」報酬（2026-07-15 新增）

官網 `/api/fund` 多期報酬**沒有 1週/1月**，由 `arm/fundnav.py` 以自建 NAV 序列自算：
資料層 `data/fund_nav_history.json`（**必須入庫**，`.gitignore` 已加例外——跨日累積的持久層，
CI 從零開始會整片變 —，同 etf_watch 的坑）；`fetch_holdings.py` 抓完自動 `fundnav.record()` 累積，
斷史時 `scripts/backfill_fund_nav.py` 走 git 歷史（`data/funds/_index.json` 每日快照）重建。
計算有「基準日須接近目標日」防呆（1週 tol=5 天、1月 tol=10 天），史料不足回 None → 儀表板顯示 —
（序列自 2026/07/01 起，「1月」欄約 2026/08 初起自然補齊，非資料壞掉）。
舊 `arm/navhist.py` 是 ETF 管線的 sqlite 模組，與此無關、勿混用。

## 「籌碼雷達」ETF 持股個股分析（2026-10-14 使用者需求；入口刻意低調）

使用者原話：「把所有 ETF 持有的個股去做分析……從量、成本、加入時間、哪間看好……實務操作可以拿來賺錢的
深度籌碼跟技術分析」「入口……不想要太容易被看到」。定案：**不用密語、不加密**（使用者：「不用那麼搞剛，
就沒那麼好找到就好了」）；**入口＝主頁頁尾右下角淡色小點** `<a class="fx" href="x9.html">·</a>`，
**不進導覽列、不在任何分頁出現**（tests/test_lab.py 守）。頁面＝`dashboard/x9.html`（Vercel cleanUrls → `/x9`）。
券商分點暫不做（使用者：先不做）；海外持股只做 ETF 面；債券型 ETF 整檔排除。

**模組（`arm/lab/`）**：store（日分片 gzip、決定性輸出）／market（官方全市場端點）／collect（冪等落檔）／
ledger（ETF 部位帳本）／ta（技術指標）／analyze（逐檔彙整＋訊號）／backtest（成績單）／page（獨立頁）。
建頁掛在 `scripts/gen_fund_dashboard.py` 尾端（fail-open）——**凡重建主頁的地方（含 push 重試迴圈）都會一起重建**，
三支 workflow 的 `git add` 都已補 `data/lab dashboard/x9.html`，個股走勢序列 `dashboard/x9s.json` 另起一行 add（缺檔時 git 整行放棄，不可連累分片；tests 守）。

**資料層 `data/lab/`（必須入庫，`.gitignore` 已加例外）**：
- `pos/{揭露日}.json.gz`：各 ETF 每日持股股數／權重（＋揭露當下收盤，供海外估成本）。來源＝`data/etf_holdings.json`，
  etf_holdings.yml 每輪 `fetch_lab.py --pos-only` 寫入；歷史由 `lab_backfill.yml` 走 git 歷史回補（需 fetch-depth 0）。
- `mkt/{交易日}.json.gz`：官方全市場部件 q_tw（MI_INDEX 價量＋加權指數）／q_tp（櫃買日收盤＋發行股數）／
  i_tw（T86）／i_tp（櫃買三大法人）／m_tw・m_tp（融資融券）／l_tw（TWT93U 借券賣出餘額）／x_tw（MI_QFIIS 外資持股比＋發行股數）。
  afterhours 每班與 daily 06:35 跑 `fetch_lab.py`：**只補缺部件**（資料齊的日子零請求），近 10 個日曆天內補洞。
- `tdcc/{資料日}.json.gz`：集保股權分散表（千張大戶%、400 張以上%、股東人數），每週一次。
- `mkt_nodata.json`：官方明示查無的（日期, 部件）——休市日不再重打；近 3 天的查無不登記（可能只是尚未公布）。
- **大 JSON 每天整份重寫會讓 repo 一年多數百 MB**——所以是一天一檔分片、只新增；`KEEP_DAYS`=400 自動清。

**帳本口徑（每條都影響數字，改之前先讀 `arm/lab/ledger.py` 檔頭）**：
- **揭露日＝成交日**：`etf_holdings.json` 的 `date` 是該交易日收盤後部位（10/14 01:08 實證：主動式已是 10-13、
  被動式仍 10-12）→ b 日相對 a 日的變化在 b 日成交、成本用 b 日均價；**訊號最早只能 t+1 開盤進場**。
- **真加碼（conv）＝扣除申贖**：每次揭露取共同持股股數比中位數＝申贖倍率 f，偏離 `前日×f` 才算經理人加減碼。
  不扣的話，申購日全部持股一起「加碼」，投信看好度會被資金流灌爆。被動式的 conv＝指數機械調整，不計入看好度。
- **超配＝主動 ETF 平均權重 − 市值權重**（分母＝上市櫃普通股總市值）；原始權重會誤導（台積電一成是低配）。
- **主動成本只算「觀測期內新建倉」的部位（品質 A）**（2026-10-14 使用者：「這樣算也不準…網路上找不找得到成本」）：
  觀測起點（7/27）前就持有的舊部位（B）原本以首次觀測日均價代入，**占主動成本金額九成、根本不是真實買價**。
  查證結果：投信官網 PCF、證交所 e添富、公會、基金財報投資明細表（只列市值與占淨值比）、第三方 app
  （nStock VIP、大戶投、主動式ETF雷達）**都沒有公布經理人成本**；唯一能算準的是從各 ETF 上市日起的每日持股逐日累計，
  而免費的歷史 PCF 沒有統一來源。使用者選「只算 7/27 後新買的」→ `analyze.active_cost()` 只加總品質 A、
  舊部位在個股卡 ETF 持有表標「舊部位」不顯示成本；成本線（金色虛線）與「成本線回測」訊號同口徑。
  台股約 57% 個股有新建倉成本（台積電這類全是舊部位的就不顯示）。未計配息與手續費。
  · **缺價格部位不以 0 元入帳**：海外持股常缺首日揭露價，舊版當 0 元入帳 → 平均成本被稀釋（村田 2,078 vs 實際約 7,900）。
    `Pos.pend` 記待補股數、下一個有價格的日子按當天均價補入；平均成本＝成本÷已入成本股數。
  · **成本拆解表做過又拿掉（勿再提議）**：曾在個股卡加「起點＋買進－賣出」逐檔拆解表，使用者看截圖：
    「版面變好亂、有看沒有懂」→ 改成重點區一行「近期新建倉的主動 ETF（N 檔）平均買在 X，現價高 Y%」＋走勢線，
    怎麼算放 ⓘ。
- **公司行動**：股數比偏離 f ≥4%＋股價同步反向（誤差 <3%）＋（≥2 檔 ETF 一致或 |r−1|≥12%）→ 換算不記交易。

**官方端點踩坑（2026-10-14 CI 探針實測）**：
- **櫃買三大法人新站表頭沒有分組前綴**（7 組重複「買進股數/賣出股數/買賣超股數」）→ 欄名比對全落空。
  依實測欄序：外資(不含外資自營商) 4、投信 13、自營商合計 22、合計 23（樣本 00411A 加總自洽）。
- 證交所 www 端頻率限制 → 每請求間隔 3 秒；櫃買 1.6 秒。回補一年價量＋三個月籌碼約 40～50 分鐘，可重跑續補。
- 當日尚未公布時，部分端點回「空表」而非查無（m_tp 解析 0 列、l_tw 0 列）→ 歸為 err、不登記查無，下一班自然補上。
- 本容器 proxy 擋 twse/tpex/tdcc——**容器內絕不跑 fetch_lab／backfill_lab 的抓取**；要驗端點就推 `.ping/lab`
  （內容 `probe`＝只印診斷、`full`＝完整回補）觸發 `lab_backfill.yml`，結果 commit 回被推的分支。

**訊號與成績單**：8 個訊號定義在 `analyze.SIG_DEF`（「集體撤退」為風險訊號）；成績單口徑＝t+1 開盤進場、
t+5／t+20 收盤出場、扣來回 0.585%、對加權指數超額、同檔 5 日內重複只計一次、**樣本 <30 灰字不排名**——
ETF 持股史從 2026-07 底才有，初期多數訊號樣本不足屬正常，別調門檻去「湊出好成績」（過擬合）。
用字遵守專案禁用詞（tests 守）：只呈現訊號與歷史統計，不寫建議買賣／目標價。

**擴充 ETF（2026-10-14 使用者：「別的規模大的 ETF 也可以納入」）**：`collect.update_extra_etfs()`——
etf_holdings.yml 每輪 `fetch_lab.py --extra`：etfinfo 全清單依規模取前 45 名候選、排除已追蹤與債券／槓桿／
反向／期貨字尾（B/L/R/U/K/D/C），抓持股後**台股權重 ≥70% 且 ≥10 檔才納入**（其餘記 `skip` 不再重抓），
上限 30 檔。只進 pos 分片與 `data/lab/extra_etfs.json`（頁面標「擴充」），**不碰主頁策展的 ETF 追蹤表**。
已到最新揭露日者跳過，每檔每天約 1～2 個 etfinfo 請求。擴充檔的部位帳本從納入當天起算（成本品質 B）。
**etfinfo 清單鍵名首輪未知**——CI 日誌印「首筆鍵名」，0 候選時照鍵名修 `_pick()`。

**指數調整（2026-10-14 使用者：「被動預計換的時間、依選股邏輯可能加入或踢除的個股」；分階段）**：
`arm/lab/indexes.py`＋`config/index_reviews.json`（時程、規則摘要、歷次官方結果與來源；週掃步驟 2.5 維護、
走 daily.yml 併檔通道）。
- **第一階段（已做）**：①臺灣50 公告前預測——上市普通股總市值排名、40／61 緩衝、固定 50 檔；
  截止日前用「還差幾 %」＋依 60 日波動估跨線機率，**截止日後改用截止日排名（指數公司用的那天）**；
  刪除股賣量＝0050＋006208 實際持股，納入股買量＝ETF 股票部位 × 預估權重（成分股權重／市值中位數反推自由流通）；
  ②回測：用歷次截止日價量重跑規則對照實際結果（審核前成分股＝生效日前一個 0050 揭露、更早的以實際結果往回推）；
  ③所有被動 ETF（含擴充）近 10 日新進／出清／真加減碼彙整——換股期間先反映，不靠任何規則。
  ④（2026-10-14 補）**截止日時還沒上市的非成分股沒有資格**（`indexes.not_listed`；鴻勁 7769 2025-11-27 才由興櫃轉上市，
  修正前 2025-09／12 兩次被誤列預估納入）——上市日＝`stockmeta` 落檔 `listed`（CI 從 t187ap03 抓，欄名不確定，
  0 筆時印鍵名）＋設定檔 `listing` 人工註記（有來源、優先）；預估名單另標 40 日漲幅與「漲勢前一半」。
- **臺灣50 換股研究＋兩個策略版本** 見下方專段。
- **第二階段（2026-10-14 做完）**：00919／00929 照公開規則重算（股利＝證交所除權息表＋FinMind、EPS＝FinMind）；
  0056 試過以殖利率／EPS 代理 I/B/E/S 預估，回放準度太低（7／21）→ **不預測、只列時程**；00878 ESG 評分付費 → 同上。
  詳見下方「高股息四檔換股研究＋預估名單」專段。
- 規則數字多取自規則摘要與媒體交叉（容器打不開官方 PDF）；0056 的 35／66 緩衝僅見轉述，寫進程式前要再核對。


**策略＋前瞻紙上交易（2026-10-14 使用者：「幫我擬定交易策略」→「好」；`arm/lab/strategy.py`、頁面「策略」分頁）**：
- **規則寫死、帶版本與起算日**（`STRATEGIES`，v1 起算 2026-10-14）。紙上交易只記起算日之後的訊號；
  之前只當「樣本內參考」——規則本身就是看那段資料挑的。**要改規則＝新版本＋新起算日＋成績歸零**，不在舊版上改。
- **帳每次由分片重算、不存狀態**（同資料同結果）。進場一律訊號隔日開盤；出場到期或 ATR 停損；
  扣來回 0.585%；超額對加權（訊號日收盤→出場日收盤）。驗證期滿＝30 筆或 30 個交易日，平均超額＞0 且勝率＞50% 才「達標」。
- 現行策略（2026-10-15 v2）：S1 共識加碼・**開盤低於前收才進**、持有 3 日、2×ATR 停損；臺灣50 提前卡位（見下方專段）；
  高股息換股（追買 C、出場規則有效，見高股息專段）；S5 長線投信動能（見下方 S5 專段）。另有「跳空 ≥3% 減碼提醒」（不做放空）。
  **S4 群益新建倉已移除（2026-10-15 使用者：「群益那個策略拿掉吧，不具可靠性」；83% 交易集中在 2026-08 同一個月），勿再加回。**
- **⚠ 踩過的坑：持有期差一天、結論正負顛倒（2026-10-14）**——探索腳本把出場算成 t+6（off-by-one），
  回報給使用者「開低組 5 日 +1.11%、勝率 65%」；正確的 t+5 是 −1.48%。教訓兩條：
  ①**任何策略結論先做「持有期 1～10 日全掃描」**，只有方向不隨持有期改變的才算數
  （當時穩定的：無條件跟單 10 期全負、開高 ≥3% 10 期全負、安聯新建倉全負、群益新建倉全正）；
  ②探索腳本與正式 `backtest._ret` 必須同一個出場索引定義（出場＝c[t+h]），不要各寫一套。
- 實測（7/27～10/13，單一強勢行情）：8 個訊號照「隔日開盤跟進」全數輸大盤；跟主動 ETF 抄作業的好處大多在隔夜跳空裡。
- **策略頁 v2（2026-10-15 使用者：「好亂、用字很 AI、結論不明確。我要看的就是推薦哪檔、建議佈局時間、預估獲利等等
  這種嚴謹的分析」＋「0050 搞了三個策略根本看不出來差在哪、高股息也沒看到策略」；規劃 `docs/strategy_v2_plan.md`）**：
  頁面由上而下＝**本期操作清單**（依策略分組：組頭放共同的時間、進出場條件、預估報酬、每 10 萬損益、部位上限；
  個股卡只放各檔不同的進場價、停損、部位股數、依據）＋觀察名單（C 級）＋出場與避開（高股息換股、開高 ≥3%）→
  **策略評級**總表 → 各策略固定五段（**結論／操作規則／歷史績效／本期名單／風險**；交易明細、持有天數比較、做法比較收在展開）→
  **部位與風控**。今日頁「本期操作」與重點同一份清單（`D.adv.picks`）。
  · **2026-10-15 版面再改成 v3（見下方「版面 v3」專段）**：本期操作清單、評級總表、五段式卡片都已拆掉／搬到驗證頁。
  · **2026-10-15 起評級改用「回測方法 v3」（見下方專段）**；以下 v2 評級（對加權指數、信賴區間）只留在各策略的
    「對加權指數（參考）」區塊、臺灣50 做法比較表與高股息段。
  · **評級在 `arm/lab/advice.py`（門檻寫死）**：短線逐筆、事件型每次審核等額平均；A＝樣本 ≥30 筆（事件 ≥6 次）＋超額報酬
    95% 信賴區間下限 >0（bootstrap 2,000 次、固定種子）＋單月 ≤40%＋前瞻滿 10 筆（事件 2 次）平均超額 >0；C＝樣本 <10（事件 <4）、
    平均超額 ≤0、贏大盤 <50%、單月 >70% 或前瞻不達標；其餘 B。部位：A 每檔 ≤5%、B ≤2%、C 不下單，有停損另限停損虧損 ≤0.5%。
    **只有 A、B 進推薦；評級判定用原始值，輸出（頁面與理由文字）一律取一位小數**——否則同一個信賴區間在理由句寫 +14.4%、
    數字格寫 +14.5%（Python 與瀏覽器捨入方式不同）。
  · 臺灣50 只列「提前卡位」一條策略；公告後進場、官方名單全部只在展開的「三種做法比較」表（含評級與一句由資料算出的差異說明）。
    建倉日前 10 天內才把「以今天排名試算」的名單列進本期操作（`advice.TW50_LEAD`），並標「定案前可能變動」。
  · **「目標價」「建議」是專案禁用詞**——預估報酬寫成「同規則過去交易的中位、一半落在、獲利比例、最差一筆」與每 10 萬損益；
    策略文字（name／kind／basis／risk／rule）與評級規則一併納入 `test_page_has_no_banned_words`。
    用字：結論先講、只寫事實與數字，不用比喻與口語（「在賭什麼」「好處被搶走」），不用破折號堆疊長句。
  · 候選的進場日／出場日用 `strategy.trading_days_after()`（證交所官方休市表）推算；S5 月底篩選日 `growth.next_screen()`。
  · 結論與比較說明由資料即時算（`advice.score`、頁面 `keyLine`／`verWhy`）——**不寫死數字**（樣本會變，S5 翻倍比例
    10/14 重算時已從 31%／17%／10% 變成 41%／37%／22%，寫死的「明顯較高」就會變成錯的）。

**臺灣50 換股研究＋兩個策略版本（2026-10-14 使用者：「公告前就先預估可能納進去的嗎？這樣感覺更有機會賺大錢……
也幫我去歸因哪些股票會漲最多，是納入張數嗎還是市值」）**：`arm/lab/tw50study.py`（研究＋版本交易）、
`strategy.TW50_VERS`／`tw50_versions()`、頁面「指數」分頁「換股研究」段＋策略頁「臺灣50 提前卡位」段（三種做法收在比較表）。
- **資料**：`config/index_reviews.json` 補到 8 次審核（2024-12 起——價量只回補兩年）；`eff_override`＝個股生效日延後
  （南亞科列處置股，依基本規則 3.4.1 延至 2025-12-30）；`listing`（上市日人工註記）；`aum`（0050／006208 規模已知點，
  被動買盤估計用，逐檔線性內插＋今日持股市值）。
- **研究結論（樣本內 19 檔；頁面數字每次建表重算，以下為 10/14 值）**：①名單到資料截止日收盤才準——截止日當天
  19／19 全對、0 多猜，提前 20 個交易日只對 11／19；②截止日到公告兩週納入股平均 −1.6%（32% 上漲），漲幅在公告後
  （公告後開盤買、生效前一天收盤賣：全部 +10.4%、漲勢前一半 +14.9%）；③歸因（對公告後超額的 Spearman）：
  截止前 40 日漲幅 +0.67、週轉率 +0.65、被動買盤 ÷ 日均量 −0.63、**被動買盤張數只有 +0.24**、
  **估計權重（市值 ÷ 前 50 大）只有 +0.10**；同一次審核漲最多的＝截止前漲勢最強（4／4 次），權重最大的只 1／4 次
  （2026-03 權重最大的鴻勁 0.92% 只 +3.9% 超額、欣興 +44.7%）。新進股都剛擠進前 40 名、權重本來就差不多；
  用 0050 實際權重校正自由流通後也只 2／4。**別用原始市值當權重比**：2026 年市值整體變大、那兩次又剛好大漲，
  原始市值的相關會被時間灌高到 +0.49（研究頁已改用權重）。生效日當天（ETF 真正買進那天）納入股多半是跌的——
  被動買盤事先人人算得出來，套利盤提前買、在生效日收盤賣給 ETF。
- **「提前卡位」逐日掃描（2026-10-14 使用者：「我是想要提前鎖定最好的個股進場卡位」）**：截止前 1～20 個交易日
  各自用當天排名挑「漲勢最強 1 檔」，平均報酬在 −2.6%～+27.1% 之間亂跳（提前 15 天 +26.5%、提前 10 天 −2.6%），
  沒有越早越好的規律——截止前名單還在變（會買到沒被納入的萬海、長榮航），「哪檔最強」也還在換（提前 10 天
  2026-03 會選到華邦電而非欣興）。最穩的是**截止日收盤鎖定、隔天開盤只買最強 1 檔、生效前一天賣**：8 次平均 +12.2%、
  中位 +15.2%、7／8 賺，最差藥華藥 −20.1%，扣掉 2026-03、06 仍 +6.1%（5／6）；持有期間跌 5～11% 是常態。
  使用者看完回覆「不用一檔可以 3-4 檔、越早越好」→ 改走上面的提前卡位 4 檔（單押 1 檔沒有採用）。
- **使用者定案（兩輪）**：①AskUserQuestion：兩種進場都紙上比較、生效前一天收盤賣；②看過研究後改口：
  「不用一檔可以 3-4 檔，然後能越早卡位越好」→ 卡位版改為**提前卡位・漲勢前 4 檔**（`tw50study.EARLY_K/N/W`＝25／4／45）：
  截止前第 25 個交易日收盤，從「當天排名的預估納入股＋第 41～45 名非成分股」挑 40 日漲最多的 4 檔、隔天開盤買；
  截止日收盤名單沒有的隔天開盤賣、有但沒買到的依漲勢補到 4 檔；全部生效前一天收盤賣（官方沒納入→公告後第一天開盤賣）。
  另一版＝**公告後進場・漲勢前一半**。兩版 v1、起算 2026-10-14、滿 2 次審核判定（原「截止日隔天開盤・漲勢前一半」
  同日被取代，從未有前瞻交易）。**原 S3（官方名單全部）規則不變、留作對照**——只修正個股生效日延後（`eff_override`）、
  持有天數口徑、資料未到的部位改標待進場／持有中（不再拿最新收盤冒充進場價）。
- **為什麼是 25 日（研究頁「提前幾天建倉？」圖＝`early_scan` 逐日回測 0～35 日，同一套規則）**：單押 1 檔時逐日結果
  −3%～+27% 亂跳（名單與「最強」還在換），**分散到 4 檔＋截止日校正後變平滑**：16～25 日最差一次都只有約 −3%、
  25 日每次平均 +11.6%（8 次賺 7 次）；30 日以上最差一次跌到 −15%～−28%，再早會碰到上一次審核還沒生效。
  等到截止日才買只有 +1.9%（最差 −20%）——漲幅有一大段在截止日之前（股票就是一路漲才擠進前 40）。
  早買後沒進名單的（萬海、長榮航、東元、穎崴…）截止日隔天賣，平均約 −2%。超額（減大盤）每次 +5.3%、8 次贏 5 次——
  2026 年整體大漲，原始報酬好看有一部分是行情；公告後版超額 +7.9%（7 次贏）但多靠兩次週一急跌。
- **頁面（v2）**：策略頁只列提前卡位一條（成績以「每次審核」計：同次幾檔平均分配）；「本期名單」列這一次的時間表
  （選股→建倉→截止校正→公告→出場）與依階段的名單（建倉日前＝試算、建倉後＝持有中、截止後＝校正後持有／賣出／補位）；
  建倉日前 10 天內、持有期間都會進本期操作清單與今日頁「本期操作」。
- **⚠ 公告後版的樣本內領先幾乎都來自兩次（勿當成規律）**：2026-03、2026-06 公告後第一天開盤，納入股跌 9～10%
  （大盤急跌），公告後版剛好買在低點；扣掉這兩次，卡位版 +3.7%、公告後版 +2.1%。頁面由 `_tw50_by_review()` 自己算
  「扣掉差距最大的 2 次」並講出來，展開區有逐次比較表——**樣本變了結論跟著變，說明文字不寫死數字**（同 S5 教訓）。
- **前瞻流程**：`tw50study.plans()` 每次重算歷次＋下一次（config `next`，日期推算、週掃更新）。資料到截止日 → 卡位版名單
  凍結、隔天開盤進場（本期操作清單會列出）；週一 ETF 週掃把官方名單寫進 history → 公告後版進場；出場日＝
  `td_shift(生效日, −1)`（證交所官方休市表）。下一次審核的「審核前成分股」＝生效日前最後一次 0050 揭露
  （生效後、週掃更新前那幾天也不會把新成分股當舊的）。截止日前頁面只列機率 ≥10% 的邊緣股（`D.idx.tw50`）。

**高股息四檔換股研究＋預估名單（2026-10-14 使用者：「幫我套用在高股息ETF」→「好 深度規劃分析後逐步執行」）**：
`arm/lab/hdmodel.py`（資料層）／`hdstudy.py`（事件研究）／`hdpredict.py`（規則重算＋回放＋下一次預估）、
指數頁「高股息 ETF 下一次換股（預估）」＋「高股息 ETF 換股研究」兩段、今日頁一行、個股卡標「預估納入／刪除」。
- **歷次名單**：`config/index_reviews.json` 的 `tw_div`（0056）、`msci_esg30`（00878）、`tip_hd`（00919）、`tip_tech`（00929）
  history（2024 起，代號、資料截止日、公告日、過渡期、規模、來源）。00878 名單不公開——`announce`＝MSCI 公布日、
  `reveal`＝ETF 開始換股（持股揭露看得到）那天。季審只隨母指數刪除（0056 2024-09 新唐、2026-03 裕融；00878 2026-02 正新、
  2026-08 鈊象）也要寫，否則由目前持股往回推的成分股會對不上檔數（`hdstudy.constituents`，各次檔數自洽才用）。
- **被動買賣期間＝官方投信買賣超推得、不是指數過渡期的日子**（`hdstudy.trade_window`）：0056 在生效日（第三個週五）收盤起
  5 天；00919／00929 從公告當天收盤起約 8 天，**00919 有三次在公告前 2～3 天就開始買**（2024-05、2024-12、2025-05——
  每日持股揭露當晚就看得到）；00878 約生效日前 5～6 天到生效後幾天。名單「看得到」＝公告日與第一天換股取早者。
  未來審核用慣例（`_conv_window`）。
- **研究結論（數字由頁面每次重算；以下為 10/14 值，「對其他成分股」＝扣掉高股息類股本身漲跌）**：
  ①**提前卡位沒有空間**：被動買盤開始前 10 個交易日就買（完美預知名單），對其他成分股 00919 −1.1%、00929 −0.5%、
  00878 −2.3%，只有 0056 +8.3%（中位 +3.4%）——但 0056 名單事先猜不準。高股息用殖利率選股，股價跌了殖利率才會變高，
  納入股常是剛跌過的股票（公告前 80～40 日對留任股常是 −8～−16%）。②**漲在被動買盤那幾天**：00919 +2.5%、
  00929 +4.2%（3／3 次為正）、0056 +2.5%、00878 +2.7%（對其他成分股），但逐次很不穩（00919：+4.4、−8.1、−6.6、+15.2）；
  2026-06 00919 換股期間富邦媒、來億-KY 連續漲停是最大的一次。③買盤結束後 10 日對大盤 −3～−6%（多半是高股息類股
  整體輸大盤，對其他成分股約 0）。④**刪除股公告前就先跌**：對其他成分股 0056 −6.3%、00878 −6.0%、00929 −5.2%，
  賣完後沒有反彈。和臺灣50（市值選股＝漲上去的股票被納入）方向相反。
- **預估名單只放 00919、00929**（`hdpredict.PRED_KEYS`）。0056 試了五種「分析師預估股利」近似（近四季股利、
  近四季 EPS×配發率、近兩季年化…），回放最好也只中 7／21、多猜 30——官方用 I/B/E/S 預估加上新進者的分析師家數、
  流動性、6 個月報酬篩選，免費資料重現不了；00878 的 ESG 評級付費、母體不公開。這兩檔只列時程，名單等公告。
- **⚠ 價格口徑（踩過的坑，2026-10-14）**：價量序列＝官方分片（當時價、未還原）＋官方缺的日子用 Yahoo（依目前股數還原），
  兩種口徑在面額變更、減資前後差好幾倍——寶雅 7/30 面額十比一、**緯穎 6/3 前的 Yahoo 歷史價只有官方的三分之一**
  （6/3＝官方分片回補到的那天），直接用會算出 +1024%、+190% 的假報酬、40% 的假殖利率。`HD.ser()` 口徑連續化：
  相鄰兩個有價交易日價格比超過 1.8 倍（台股漲跌幅限制 10%，不可能是真漲跌）＝口徑改變，更早的價格全部換到最新口徑；
  股利用證交所除權息表的「除權息前收盤價」換算（`序列前一天收盤 ÷ 當時前收盤`），沒有前收盤價就除以口徑倍數。
  研究與預測一律用 `HD.ser`／`hdstudy._HPx`，**不要用 `D.series`**（原始口徑）。
- **⚠ 證交所除權息表的「權息」列只有權值＋息值合計**（配股價值也算進去，勝一、洋基工程、愛山林會變成 20～100% 殖利率）→
  這些股票另抓 FinMind 股利政策拿現金部分（`backfill_lab.py --hd` 自動挑出）。
- **資料回補**：`.ping/lab` 寫 `hd*` → `backfill_lab.py --hd`：證交所 TWT49U 一年一請求（含前收盤價）＋FinMind
  單季 EPS（市值前 460＋設定檔歷次異動股）＋上櫃與「權息」股的股利政策；FinMind 未登入每小時約 300 次，限流就停、
  下一輪續補（EPS／股利各自記抓取日，20 天內抓過的跳過）。

**高股息被動買盤大小（權重）＋策略延伸＋被動買賣提醒（2026-10-14 使用者：「延伸更多可能的交易策略，包含權重問題——
高股息的權重就有可能會大幅拉高吧」）**：`arm/lab/hdflow.py`、指數頁「高股息：被動買盤大小（權重）與策略測試」段、
策略頁「高股息換股」段（追買評級 C、出場規則有效；本期名單＝依 ETF／換股分組的出場與避開日期）＋本期操作清單的
「出場與避開」、今日頁風險提醒一列、個股卡一格。
- **量法**：官方投信買賣超在被動買賣期間（`hdstudy.anchors`）的合計，扣平常水準（之前第 25～6 個交易日中位數）
  × 期間均價＝實際被動買賣金額；÷ 20 日均成交金額＝幾天的量。投信買賣超是全體投信合計（含其他基金）＝近似；
  台積電這類每天投信進出上百億的權值股量不出來（雜訊蓋過）。
- **權重的答案**：同一次換股，被買進金額和市值的等級相關約 0.8～0.9、占市值約 2～7%（0056 2.8%、00878 4.5%、
  00919 4.5%、00929 2.4%）——權重跟著市值走，殖利率高不會讓權重遠超過市值比例；被「大幅拉高」的是**相對成交量**：
  冷門中型股一次 10～30 天的量（來億-KY 2026-05 約 33 天）。
- **事前估計**＝市值 × f_k（同 ETF 其他次審核「買進占市值」中位數），以「單檔權重上限 × 規模」封頂。三種模型對照實際：
  這個誤差中位約 ±45%、無偏；「規模 × 股利金額占比」±70%；舊的「規模 × 殖利率占比」高估約 1.7 倍（已換掉）。
  **不封頂會出事**：00929 12 月「配息 ≥2 次優先」會把台積電、聯發科排進預估名單（2025-12 實際也有納入），
  市值 × f 估出 1.5 兆。刪除股的被動賣出＝ETF 目前實際持股 × 收盤（`data/etf_holdings.json`）。
- **策略測試（樣本內，每次審核等權；10/14 值）**：追買（名單公開後買大買盤股、最後一天賣）14 次 7 次賺、中位為負 → 不採用；
  估計 ≥5 日量的納入股，被動買盤結束後 10 日對大盤平均 −5.1%、14 次只有 2 次為正，對其他成分股也輸（買盤小的不會）；
  刪除股賣完後 10 日 −3.6%（17 次 5 次為正，沒有反彈）；回落後再撿、預估刪除先避開、同期多檔疊加、0056 公告後兩週空窗、
  第一天投信買超確認都試過，方向不一致 → 只做成「被動買賣提醒」（不做放空），v1 起算 2026-10-14，滿 2 次審核看前瞻。
- **留任股的權重調整**事前算不出來（要指數公司權重公式＋當天價格）；被調降（被賣 ≥5 日量）期間約 −3.5%。
- 00919 12 月預估納入可能超過「最多換 8 檔」（前 20 名直接納入＋市值配額）：試過在配額後再強制 8 檔，回放反而少中 1 檔 →
  維持照名次全列，頁面加註。

**高股息「依編製規則提前卡位＋大權重」回測（2026-10-15 使用者：「為什麼高股息不是用指數編纂邏輯去提前試算可能加入的公司，
而且可能加入的權重會很大的公司，用這個邏輯去延伸投資架構跟回測」；`arm/lab/hdpre.py`、規劃與結果 `docs/hd_preposition_plan.md`）**：
- **權重公式要用實際持股校準，不要信媒體描述**：00919 媒體寫「股利率加權」，實際持股是**市值加權**（log 權重對 log 市值 R² 0.97）；
  00929 才是殖利率加權。預估買進＝預估成分股裡的權重 × ETF 規模（`hdpre.index_weights`／`est_amounts`；00919 上限 15%，2025-05 前 10%）。
- **結果（9 次審核，2024-05～2026-06）**：被動買盤期間，預估 ≥10 日量的納入股平均贏大盤 +5.7%（<3 日量 +0.5%），買盤結束後 10 日 −5.4%
  ——假設只在被動買盤那幾天成立。可操作的主規格（截止日收盤選 ≥5 日量的預估納入股、隔天開盤買、被動買盤最後一天賣；`MAIN` 寫死、
  不得事後改）每次 −2.3%、1／9 贏大盤 → C。原因：名單會猜錯（截止日 130 檔猜中 95、多猜 68；2025 規則改版前更差）、截止日到
  買盤開始前沒漲、00919／00929 常提前幾天開始買。「公告前 3 日買」是看結果後才加的做法（−0.3%），只能看前瞻。
- **資料**：五年日線另存 `data/lab/yhl/`（`backfill_lab.py --yhl`，`.ping/lab` 寫 `yhl`），**只有 `analyze.Data(long=True)` 會讀**
  ——不要併進 `yh`：會讓長線成長股的篩選月份、各訊號成績單的回測期間跟著變。`hdpre.page_data()` 自己載入長資料重算，約 15 秒，
  掛在 `analyze.run`（失敗不影響其他區塊）。證交所除權息補到 2018（00929 要 5 年股利）。
- 00929 2025-12 前每年只有 6 月一次成分股審核；2024-06 沒有過渡期（生效日收盤一次換完）→ `hdstudy._conv_window` 已處理。
  00919 2023-12 名單查得到（東元等 8 進 8 出，兩來源），換股日期查不到 → 不納入（不猜日期）。00929 規模補 2024-06 2006 億、2025-06 1650 億（`aum_src`）。

**歷史價量備援（Yahoo 逐檔，2026-10-14）**：證交所 www 端對 GitHub runner 嚴格限流（每請求間隔 3 秒仍有 1/4 回 611B 擋頁，
加冷卻後 50 分鐘只補到 6/3），逐日 MI_INDEX 回補一年不可行。改 `backfill_lab.py --yahoo`（`.ping/lab` 寫 `yahoo`）：
宇宙＝上市市值前 250＋ETF 曾持有台股＋臺灣50 歷次異動股＋加權指數（^TWII），每檔一請求取兩年日線存 `data/lab/yh/{代號}.json.gz`。
`analyze.Data.quote()` **只在官方分片缺該日時才用 Yahoo**（官方兩市齊全卻沒有此檔＝當天沒交易，不備援）；
Yahoo 無成交金額 → 均價退回收盤；週末與今日以後的 bar 一律丟（2026-09-20 週日 bar 事件同型防呆）。

**資料包策略測試與回測紀律（2026-10-15 使用者附上策略資料包：「把能用的拿來用就好」；規劃與結果 `docs/strategy_pack_plan.md`）**：
- **能用＝現有資料能回測**。新策略五條（`arm/lab/packtest.py`，主規格回測前寫定並先 commit，`tests/test_lab.py::test_pack_main_specs_are_fixed` 守）：
  P1 相對強勢月換股（S11）、P2 趨勢樣板＋突破（S09 Minervini）、P3 財報驚喜 SUE（S10，法定公告期限次一交易日進場）、
  P4 價值＋動能（S16）、P5 短期反轉週換股（S13）；P6＝CAN SLIM 的 C／M 加在長線策略上當對照（`growth.s5_trades` 的 `alt`，S5 規則不變）。
  結果全部 C（P2 平均 +2.3% 但 74% 輸大盤、去掉最好一筆轉負；P3 對同一批股票 +3.0% 但只贏加權 +0.6%）——只放在策略頁「資料包策略測試」表，不進本期操作。
- **存活者偏誤處理**：Yahoo 五年宇宙是「目前市值前約 600 名」。形成日另要求市值 ≥300 億（只漏掉之後跌超過三分之二的），並對「同一批股票的等權平均」算 xe；
  `advice.score(..., xe_rule=True)`（S5、P1–P5）平均沒贏同一批股票 → C。
- **回測紀律（全部策略）**：`advice.robust()` 算成本加倍、去掉最好一筆、最大累計回落、最長連虧、大盤年線上／下（`packtest.regime_map`，五年日線算 200 日均線）；
  參數鄰近＝主規格兩個參數各 ±1 檔共 9 組（`packtest.grid`；S1 持有天數×ATR、臺灣50 提前天數×檔數 `tw50study.early_grid`、S5 初始停損×回落、P1–P5 各自）。
  **評級加嚴**：A 另需成本加倍後 >0 且鄰近 9 組 ≥6 組為正；鄰近不到一半為正 → C。套用後現有評級都沒變（S1、臺灣50 鄰近 9／9、成本加倍仍正）。
- **成交檢查（D1）**：`backtest.limit_up_open`（開盤 ≥ 前收 × 1.095）／`locked_down`（開＝高＝低＝收且 ≤ 前收 × 0.905）／`exit_day`（鎖跌停順延賣出）。
  臺灣50 漲停開盤順延進場最多 3 天；S1、S5、P2、P1–P5 出場遇鎖跌停順延。歷史上 S1／S5／臺灣50 都是 0 筆。
- **⚠ 2026-07 動能股崩跌是真實行情**（華新科、中探針、禾伸堂等月跌 40～60%、連續跌停）：P1 那個月輸大盤 28%，別當成資料錯誤去修。
- **效能**：`analyze.run` 只載一次 `Data(long=True)`，`hdpre.page_data(D=DL)`、v3 策略、公司分析小表、大盤年線共用；`packtest.Px` 快取合格名單（`elig`）與區間報酬（`_win`），
  參數鄰近重跑不重算。**P1–P7 的 `packtest.run` 2026-10-16 起不在每次建頁重跑**（頁面只用長線 P6 對照列與 `SKIPPED`，P1–P7 列本來就被 `bt3Sec` 濾掉，
  每次白算約 17 秒）；成績留在 docs/strategy_pack_plan.md，要重看手動跑 `packtest.summary(packtest.run(Data(long=True)), reg)`。
- 頁面：各策略「歷史績效」下的「穩健度檢查」（`robTbl`，✓／✗ 三項＝A 級條件，可展開 9 組參數表）＋「樣本內比較過的做法」（`tried` 欄，STRATEGIES／TW50_VERS／S5／hdflow.ALERT）；
  風控段「總部位」（`totPos`）。沒採用的項目與原因在 `packtest.SKIPPED`（不放目標價類內容）。原 `packSec()`（`st-pack`，5 年資料、
  對加權指數）2026-10-15 由回測方法 v3 的全部策略總表 `bt3Sec()`（`st-bt3`）取代。

**回測方法 v3（2026-10-15 使用者：「那些策略是真的不好還是你的參數有問題？回測策略也要深度詳細規劃，不確定的問我」；
規劃、使用者決定與結果全在 `docs/backtest_v3_plan.md`）**：
- **診斷**：舊評級多數 C 的主因是比較基準（加權指數被台積電帶著走）、樣本短（2024 起）、「贏大盤比例」門檻；參數不是主因
  （鄰近 9 組多數全正）。短期反轉是真的不好（各期間都顯著為負）。
- **使用者決定**：基準＝同一批股票的等權平均（不必贏大盤）；大型（月底市值 ≥300 億）與中型（50～300 億）分開測、分開呈現
  （兩者都要 20 日均成交值 ≥5,000 萬）；手續費 2.8 折（來回大型 0.48%、中型 0.68%）；報酬型態「標準」＝賺錢機率 ≥60% 且每月平均
  ≥+1%，或 ≥40%、賺賠比 ≥2.5、每月平均 ≥+2%；每條策略只取最強前 5 檔；本期操作列全部 B 級、依證據強弱排序。
- **評級 v3**（`bt3.grade3`＋`advice.grade_v3`，第 6 節）：A＝選股樣本內 t ≥2、樣本外同號 t ≥1、報酬型態內外都過、穩健度三項
  （成本加倍、參數鄰近 ≥6／9、去掉最好 5%）全過、前瞻滿 10 期（事件 2 次）＞0；B＝樣本內選股與報酬型態過、樣本外沒反向、
  穩健度最多一項未過；其餘 C。t 值用 Newey-West；逐筆型（共識加碼、長線）以月平均算 t。
  **沒有樣本外資料的策略以前瞻代替樣本外**：前瞻滿期數且平均 >0＝樣本外條件過、滿期數而為負＝反向 → C
  （2026-10-15 合併前才把程式對齊第 6c 節；原本程式最高只給 B）。既有策略的前瞻在 `bt3s.existing_eval` 同一套換算。
  **低回落例外**（第 15 節，使用者：「最重要的是要能賺錢……輸但是是正的也不代表不好吧」）：選股沒過但扣成本後賺錢、
  年化少不到 3 個百分點、最大回落 ≤ 同一批股票 0.7 倍、年化÷回落不差、成本加倍與鄰近 ≥5／9 也成立 → 最高 B
  （`bt3.low_dd`；研究檔每列 `lowdd`；頁面總表下「低回落例外檢查」表）。首次結果：沒有版本符合、評級不變。
- **資料（CI 回補，全在 `data/lab`、必須入庫）**：`v3px`（逐檔日線，Yahoo 含 adjclose；已下市用 FinMind）、`v3me_tw`／`v3me_tp`
  （月底收盤＋發行股數；每日 `v3data.me_from_mkt()` 從官方分片補，不發請求）、`v3div`（櫃買除權息）、`divtw`（2013 起）、
  `v3eps`（FinMind）、`v3isq`（公開資訊觀測站綜合損益表彙總，每季 `update_isq()` 補一次）、`v3_tr.json`（加權報酬指數）、
  `rev`（2012-01 起）。回補走 `.ping/lab` 第一行 `v3fill*`（`backfill_lab.py --v3 --budget-min 48`），探針 `probev3`／`probev3b`。
- **模組**：`bt3`（成本、NW t、報酬型態、資金帳戶、對同一批股票、因子五分組、評級）／`bt3d`（長歷史面板：含息價格、月底市值）／
  `bt3s`（各策略形成日與選股）／`bt3l`（樣本內外切開、前 5 檔、匯出）／`v3data`（回補）／`v3live`（每日本期 5 檔、前瞻、
  既有策略重評）／`advice.build_v3`／頁面 `v3Sec`、`bt3Sec`。
- **研究檔 `data/lab/bt3_research.json`**：只在資料或規則改了才重跑 `TZ=Asia/Taipei python3 scripts/run_bt3.py`（約 3 分鐘）；
  每日流程只讀它。名單、進出場日與前瞻（起算 `v3live.SINCE`＝2026-10-15）每日由 `v3live.run` 算，與研究檔同一套規則。
- **結果（2026-10-15）**：前 5 檔版本——大型財報驚喜 B（只差前瞻）、中型月營收驚喜 B、大型月營收驚喜 B（樣本外偏弱 t 0.67）、
  中型財報驚喜 C（樣本內 −3.13%／季，只做紙上記錄）。整組版本——中型月營收驚喜只差前瞻、財報驚喜大中型 B；相對強勢、價值＋動能、
  趨勢突破 C；短期反轉樣本內外都顯著為負。共識加碼、臺灣50、長線用同一套條件重評都是 B（沒有樣本外；共識加碼每筆 +1.22%
  但月平均 t −0.04，排最後）。
- **⚠ 踩過的坑**：
  ①Yahoo 價格已還原股票股利、沒還原現金股利，adjclose 隱含的現金股利有約 2.5% 與官方不同 → 現金部分一律用官方
  「參考價 ÷ 前收」（上市「息」列；上櫃 1 − 現金股利 ÷ 前收），上市「權」「權息」才用 Yahoo 隱含倍數（`bt3d.factor_yahoo`）。
  ②Yahoo `range=max` 回月線 → 一律用 period1／period2。③FinMind 未登入每小時約 300 次 → EPS 改以公開資訊觀測站
  t163sb04 為主（當年累計，Q2～Q4 用相減；前一季缺就不算）。④**財報期限落在週末會前視**（用到週一才公告的財報）→
  形成日＝期限當天或之後的第一個交易日（`packtest.form_after_deadline`）；修正前後評級不變（第 13d 節）。
  ⑤大型股流動性門檻 2 億 → 5,000 萬是在看到任何樣本外績效前改的（2014 年大型股有一半被擋），文件有記錄；
  **之後任何規則變動都要在看結果前寫定並 commit**。⑥每日名單的市值口徑必須和研究一樣（月底快照，`v3live` 覆寫 `P.cap`），
  否則名單會和研究不同。⑦多重檢定：整組版本測 12 組，只靠運氣至少一組 t ≥2.8 的機率約 6%——單一 t 值好看不等於有效。
- **頁面**：評級總表 `grades3`（樣本外／樣本內選股＋t 值、賺錢機率、每月平均）在驗證頁；每條策略最多 5 檔（`advice.PER_STRAT`）；
  各策略段落順序跟評級總表一樣（策略頁 `ADV.book`、驗證頁 `valSecs`）。版面見下方「版面 v3」。

**版面 v3（同日稍晚由版面 v4 取代分頁架構，見下一段）：策略、訊號頁「操作在前、驗證分開」（2026-10-15 使用者：「排版好亂……我到底該在什麼時候買進什麼，預期持有多久報酬率多少，
除了超額之外我也要知道實際報酬率多少吧，你自己的驗證跟我沒關係應該切開來吧」「尤其針對訊號跟策略」；規劃與決定 `docs/lab_layout_v3_plan.md`）**：
- **使用者四個決定**：策略頁主軸＝依日期的行事曆；驗證另成一頁（頂欄右側「驗證」，和「名詞」並列，不放主分頁列）；
  實際報酬旁只放「同期大盤」（加權報酬指數，含息），「贏同一批股票」只在驗證頁；訊號頁＝結論＋一覽表＋各訊號今天名單（精簡）。
- **策略頁**（`vSt`）：行事曆 `calSec`（`ADV.cal`：今天之後的買進／賣出／換股／調整，依日期、同天開盤在前；只列 A、B 級；
  已買進的部位只出現在賣出日；名單還沒產生的列「名單 X/X 收盤產生」）→ 避開 `avoidSec` → 策略一覽 `bookSec`（`ADV.book`：
  每次／每檔平均與中位、賺錢比例、最差、同期大盤、年化與大盤年化）→ 各策略卡 `stCard`（結論／怎麼做／過去成績／風險；
  有長歷史的放逐年報酬表＋「1 元變多少」策略對大盤曲線）→ 部位 `posSec`。
  **操作頁不得出現 t 值、樣本內外、穩健度、參數鄰近、因子檢定、同一批股票（`test_strategy_tab_v3_calendar_first_and_validation_split` 守）。**
- **驗證頁**（`vVal`，`VIEWS.val`）：評級規則 → 評級總表（`val-grade`）→ 各策略評級依據（`val-{k}`：評級、評級依據、展開細節）→
  全部策略總表（`val-bt3`）。內容全是原本策略頁的，沒有刪。兩頁互連（「評級依據與驗證 →」「操作與實際報酬 →」）。
- **訊號頁**（`vSig`）：結論 `sigConcl`（由資料算）＋一覽表（持有 5／20 天實際平均、賺錢比例、同期大盤、能不能照做 `sigVerdict`；
  共識加碼連到 B 級策略 `SIGST`）；舊「勝率」（＝贏大盤比例）不再出現在訊號頁。手機版 20 天與結論改成每列下面一行（`tr.sgw`）。
- **資料欄位**：`backtest._agg` 補 `rm`（中位）、`rw`（賺錢比例）、`mk`（同一時窗大盤平均＝實際 − 超額）；
  `advice.expect` 補 `avg`、`mk`、`d0`／`d1`；研究檔（`bt3l`）補 `dist.avg`／`dist.mk`（同一段持有期間加權報酬指數，前一天收盤起算）、
  各段 `tr_cagr`／`tr_mdd`、整段 `all`、逐年 `yearly`、月底取樣曲線 `acurve`（策略資金帳戶與買進持有大盤）；`advice._ex_best`＝去掉最好一年的年化。
  **這些只呈現，不參與評級**；重跑研究後評級與原數字零差異。
- 頁長：策略頁電腦 21,210 → 10,513 px、手機 35,483 → 17,380 px。

**版面 v4：整頁以「策略選股」為主軸（2026-10-15 使用者：「整個的編排邏輯都很亂，每個分頁想表達什麼沒辦法一眼看出……應該是要幫助瀏覽者
知道各個不同的策略找出了哪些有機會的股票、建議的策略、還有隱含的獲利如何……另外在後台有一個自我驗證策略然後自己安排每日更新跟我說」；
規劃與決定 `docs/lab_ia_v4_plan.md`）**——取代 v3 的分頁架構（v3 的策略說明卡、驗證內容都保留，只搬位置）：
- **使用者四個決定**：分頁＝機會｜策略｜個股｜籌碼｜指數，頂欄右側小字「後台」「名詞」（首頁＝機會；投信、訊號併入籌碼；研究與驗證全進後台）；
  機會頁依策略分卡、照推薦順序＋上方時間表；推薦＝推薦順序 1～6＋一句理由（資料多長、有沒有事後驗證），A／B／C 照留；
  通知＝06:35 推播多帶兩行——2026-10-15 使用者同意後改了本檔 Routine 原文①與 SOP 步驟 9⑨（讀 `val_log.json` 的 `push` 欄）。
- **頁首**一句網頁目的（`.purp`）；每個分頁最上面一句話說這頁回答什麼（`.intro`）。
- **機會**（`vOpp`，首頁）：摘要（推薦策略 N 條、待買進、持有中、全部照做約占資金；`ADV.opp`）＋時間表（`ADV.cal`，一列一件事）→
  每條推薦策略一張卡（`o-{k}`：做法／隱含獲利／現在（待買進、持有中）／下一批）→ 避開清單。C 級不上機會頁。
- **策略**（`vSt`）：比較表（推薦順序與理由、平均、賺錢比例、同期大盤、年化；手機把同期大盤放在平均下面）→ 說明卡（v3 的結論／怎麼做／過去成績／風險）→ 部位。
- **個股**：表上「策略選到的（N）」篩選、股名下策略標籤（`PK`＝`ADV.picks`，只含 A、B 級）；不在 ETF 持股範圍的股票列在表上方一行；
  個股卡最上面「策略」段（`stCardSec`）。
- **籌碼**（`vChip`）：原今日頁的重點／買賣／新建倉／風險＋投信動向（`issSec`，原投信頁）＋今日訊號（`sigTodaySec`：一句結論＋各訊號今天的股票）。
- **指數**：時程、臺灣50 預測、高股息預估、被動換股、其他；四段研究（臺灣50、高股息研究、買盤大小、提前卡位）搬到後台。
- **後台**（`vBo`，`VIEWS.bo`）：今天的驗證（事件、06:35 推播會帶的兩行）→ 前瞻紀錄（起算日、已出場／A 級門檻、平均報酬、同期大盤、
  比同一批股票、持有中、過去最差）→ 事件紀錄 → 評級規則、評級總表、各策略評級依據、全部策略總表 → 訊號成績 → 換股研究 → 每日更新時程。
- **推薦順序**（`advice.rank`）＝評級總表順序（A 在前；同級依證據強弱），只排 A、B（高股息不排）。理由三種：「N 年資料，事後驗證也贏」
  （樣本外平均贏同一批股票且 t ≥1）／「偏弱」、「資料只有 N 次（YYYY 年起）／N 個月，還沒有事後驗證」。
  **機會、策略兩頁不得出現 t 值、樣本內外、穩健度、參數鄰近、因子檢定、同一批股票**（`test_opp_strategy_chip_backend_v4_structure` 守）。
- **後台自我驗證 `arm/lab/valog.py`**：每次重建頁面算一次（`page.build()` 呼叫），**只有 CI（`GITHUB_ACTIONS=true`）寫回
  `data/lab/val_log.json`**（一天一行、以資料日為鍵、同一天後面的班次覆蓋、內容沒變不動檔、保留 250 天；三支 workflow 的 `git add data/lab` 已涵蓋）。
  每條策略記評級、推薦順序、前瞻筆數與平均報酬、同期大盤、比同一批股票、持有中檔數與平均、待買進檔數、過去最差、起算日。
  事件六種（事前寫定）：評級變動、前瞻滿額、前瞻落後（已出場 ≥ 門檻一半且平均輸同一批股票）、持有中跌得比過去最差一次還多
  （逐檔計的看每檔、其餘看同一批平均）、該出名單沒出（月營收／財報驚喜的形成日已過一個交易日卻沒有那一期；`v3live._due`）、
  資料過期（落後 ≥2 個交易日；14:30 後算今天）。前五種只在第一次出現時記，資料過期每天記。
  `push` 欄＝06:35 推播的兩行文字（第一行＝下一個交易日開盤／收盤要做的事；第二行有事件才有）。
- **前瞻的同期大盤**：v3 前瞻每期加 `mk`（加權報酬指數，決定日收盤→出場日收盤；`v3live._tr_ret`）；加權報酬指數改成每天由
  `fetch_lab.py` 補（`v3data.update_tr_recent`：本月＋上月未完成者，最多 2 請求，已到最新日零請求）。
- **⚠ 修掉的舊坑**：①投信卡的海外代號（`BMNR US` 等）之間沒有斷行點，手機版把整頁撐寬到 594px → `.eit` 改 inline-block；
  ②從個股卡的連結跳分頁時若用 `history.back()` 關卡片，瀏覽器會還原捲動位置、跳不到錨點 → 改用 `replaceState`＋`hideStock()`。
- 頁長（電腦／手機 px）：機會 3,680／6,102、策略 8,469／13,663、籌碼 7,379／12,775、指數 5,756／7,138、後台 20,215／31,741。

**逐筆交易（2026-10-15 使用者：「我希望每個策略都會有像是 0050 策略的逐筆歷史交易，我才能去驗證」；規劃與結果 `docs/lab_trades_plan.md`）**：
- **頁面**：策略頁每張卡多一列「逐筆交易」（`trBox`／`trRender`，預設收起、展開才畫）：一句核對說明（`trCheck`，由資料算）、
  年份、搜尋股票、下載 CSV（`trCsv`，含 BOM、Excel 直接開）；月營收／財報驚喜「每期｜逐筆」、臺灣50／高股息「每次｜逐筆」、
  共識加碼／長線逐筆。舊的三種逐筆表（`tradeTbl`／`pastTrades`／`revTbl`）已拿掉（測試守）。
- **資料流**：`bt3.account(log=...)` 記每筆整檔買進／賣出／沒買到（**加紀錄前後每期數字完全相同**，測試守）→
  `trades.build`（買到賣配對、每期表、還原倍數、依據與名次）→ 研究檔 `bt3_research.json` 每條前 5 檔策略的 `trades`
  （`bt3l.export`；**改了逐筆格式或回測資料就要重跑 `scripts/run_bt3.py`**）＋前瞻 `v3live`（`tr`）＋既有策略
  `trades.pack_simple`（共識加碼 `strat.list[s1].tr`、臺灣50 `vers[early].tr`、長線 `grow.s5.tr`、高股息 `idx.hd.flow.tr`）
  → `advice.trade_book` 集中到 `ADV.trades`（**pop 掉原處**，頁面不重複內嵌）＋`ADV.tnames`（含已下市名稱 `names_hist.json`）。
- **緊湊陣列**：欄位順序 `trades.TR_COLS`／`PER_COLS` 和頁面 `TRC`／`PRC` 必須一致（測試守）；日期＝2013-01-01 起第幾天；
  尾端空值省略；賣出原因代碼 d／l／e／el／bt（`bt`＝期期相連的月營收策略在資料最後一期的結算，不是規則上的賣出）。
- **當時價格（`trades.Raw`）**：Yahoo 開高低收是分批抓的、調整基準不一，且已依配股減資換算 → 乘換算倍數 K（月底官方收盤、
  除權息前一天官方收盤 ÷ Yahoo 同日收盤）；切換日用「價格一定落在升降單位上」找（`on_tick`），分不出來才用除權息日，都不行標「約」。
  驗證：3,038 個買賣價全部落在升降單位上。報酬照回測（含息、股利再投入）；逐筆另給「還原倍數」mul，
  `報酬＝賣出價 ÷ 買進價 × mul ×（1 − 賣出成本）÷（1 ＋ 買進成本）− 1` 可逐筆驗算；mul 和除權息對不上的標 kc（1＝減資分割、2＝資料出入）。
- **核對時發現並修正的回測資料問題**（2026-10-15，`bt3d.py`；先 commit 修正再重跑，16 個研究版本評級都沒變）：
  ①除權息日剛好休市（颱風假，190 筆）整筆略過 → 改算在下一個交易日；②上櫃除權息現金、配股兩欄都空白（505 筆）被當成沒有現金股利 →
  改用 Yahoo 還原收盤隱含的倍數。**同型自查：任何「日期對不上交易日就 continue」的地方都可能靜默丟資料。**
- **既有策略的價格（`trades.reprice`，在 `advice.trade_book` 跑）**：共識加碼、臺灣50、長線、高股息用每日資料回測，官方分片缺價格的日子
  是 Yahoo 補的（已依之後的配股、減資換算，例 京元電子 2026-02-24 Yahoo 301.9、實際 317）→ 不在升降單位上的（`exact_tick`）用 Raw 換回
  當時實際價，報酬照回測；兩邊換算不同時差異寫進 mul、標 ※。**回測本身的價格序列沒改**（改了會動到這幾條的成績，要另外評估）。
- **已下市公司名稱**：`.ping/lab` 寫 `names` → `backfill_lab.py --names` → `data/lab/names_hist.json`（FinMind 下市櫃表，2026-10-15 抓到 101 檔）。

**策略健檢與自我改良（2026-10-16 使用者：「後台加入把你所有推薦策略都依照進場的績效回測跟優化建議…每天自我優化」；
規劃、使用者決定與每次重跑結果全在 `docs/lab_selfopt_plan.md`）**：
- **使用者四個決定**：影子版本達標後通知、回「好」才換（不自動改）；只改執行細節（進場時點、持有／出場、停損、檔數、大盤濾網），
  **選股的分數與門檻不動**；每天體檢、每週一重跑改良回測；目標＝扣成本後報酬變高，而且最大回落不比現行差超過 3 個百分點。
- **候選清單與門檻在跑任何結果之前 commit**（optim v1，48 個候選＋相鄰檢查數字；`arm/lab/optim.py`，`tests/test_selfopt.py` 鎖住）。
  要加候選或改門檻＝`OPT_VER`＋1，日期與原因寫進文件；**不在看過結果之後改 v1**（同回測方法 v3 的事前寫定紀律）。
- **每天（建頁時）**：`health.daily` 算燈號（前瞻平均在回測抽樣分布的百分位，2,000 次、種子 20261016；低於 5％＝明顯低於回測）、
  持有中百分位（逐檔策略每檔、其餘每批，和回測同一持有天數比；低於第 5 百分位→事件）、依進場條件拆解（前後兩半同向且 Welch t ≥2
  才標「差異明顯」）；`optim.page_data` 帶每週結果與影子版本前瞻。結果在 analyze 輸出的 `hl`、`opt`，後台「策略健檢與改良」顯示。
- **每週一 08:30**（`.github/workflows/lab_opt.yml` → `scripts/run_opt.py`，容器實測約 2 分鐘）：v3 長歷史面板的回測參考＋48 個候選全部重跑
  → `data/lab/opt_research.json`；影子版本登記 `data/lab/opt_shadow.json`（證據強才進、每條策略最多 2 個；淘汰或回「不換」冷卻 182 天）。
  只 commit 這兩個檔進 main，不重建、不部署（下一班建頁自然帶入）。**cron 只在 main 上跑，合併前不會執行。**
- **事件**（併進 `val_log.json`，不另開檔）：表現偏離回測（dev）、影子版本達標（shok，推播寫「回『好』才換」）、影子版本淘汰（sout），
  隨 06:35 推播第二行。
- **改良引擎的不變式**：參數設成現行時，結果必須和現行回測完全相同——財報與月營收用 `account_v`（`bt3.account` 的複本＋開高不追、停損），
  共識加碼、長線、臺灣50 直接呼叫原本的交易函式（`strategy._trade`、`growth._s5_sim`、`tw50study.early_picks/early_trades`）。
  **改任何策略的回測程式，要確認 `tests/test_selfopt.py` 的不變式測試仍綠**；`bt3.account` 改了，`account_v` 要同步改。
- **完整交易走私有鍵**：strategy 的 `_all`、臺灣50 的 `_V`、長線的 `_recs`、v3live 的 `_hl`，`analyze._take_full` 取走後才建頁
  ——頁面會內嵌整份資料，漏取會讓頁面暴增（`tests/test_health.py::test_take_full_strips_private_lists` 守）。
- **你回「好」之後怎麼換**：該策略出新版本、新起算日（改策略程式的參數與 since；財報、月營收三條是 `v3live.SINCE`），
  登記檔該項 `st` 改 `switched`；`optim.CURRENT` 同步改並 `OPT_VER`＋1（`test_optim_current_matches_live_rules` 會紅提醒）。
  回「不換」：`st` 改 `declined`、`cool` 加 182 天。
- **第一次重跑（2026-10-16）**：48 個候選沒有一個證據強。最接近＝財報驚喜只買 3 檔（2021-10 起每季多 +5.8%、校正後顯著，
  但 2021-10 之前複驗 t 0.99 不到 1）→ 待觀察。共識加碼訊號只有 4 個月（2026-07 起）→ 全部樣本不足。

**公司分析（點進去才算）＋飆股研究（2026-10-16 使用者附 FinLab 個股頁截圖：「幫我去找這個網頁分析公司的架構，他很著重在財報分析……
變成點進去公司後可以跑公司的分析（可以不用先跑好這樣太浪費用量）」＋「你那個策略會失效也合理因為你沒有把總經考慮進去……先不要管那麼多，
我的重點是要能找到飆股」；規劃、探針與結果全在 `docs/lab_company_plan.md`）**：
- **FinLab 架構**（CI 無頭瀏覽器探針，`.probe/web/` 合併前已刪）：五面向（估值、品質、成長、動能、籌碼）全市場百分位、今日重點、
  歷史估值換算價位、EPS／三率／ROE 8 季、年 EPS、月營收、股利、法人與融資、同業名次、量化訊號、公司簡介。他們是每晚預先產好整頁；
  我們改成**伺服器端只放原始數字、瀏覽器打開那一檔才算**：
  · `dashboard/co/{代號}.json`（每季財報、每月營收與月底股價、股利；`company.build_co`，**內容沒變不改寫**，已下市刪檔）＋
    `co/index.json`（「查公司」搜尋用）＋全市場每日小表 `dashboard/x9t.json`（五面向百分位、體質檢查、`company.TCOLS`）。
    三支 workflow 的 `git add` 各自一行帶 `dashboard/co` 與 `x9t.json`（缺檔不連累其他檔，tests 守）；本機不 commit（同 x9.html）。
  · 入口：個股卡多一段「公司」（`copage.coSec`）、頂欄「查公司」（任何上市櫃，不在籌碼雷達範圍的開 `#co=代號` 卡片）。
  · 頁面 JS 在 `arm/lab/copage.py`，**由 `page.render` 插在頁面初始化之前**（`/*@@COPAGE@@*/`）——初始化會開機會頁與 `#s=` 個股卡，
    接在後面的話頂層 const 還沒初始化（TDZ），直連個股卡會壞（2026-10-16 踩到，tests 守）；會在初始化時呼叫的函式也別用頂層 const。
- **財報資料**：MOPS 綜合損益 `t163sb04`、資產負債 `t163sb05`、現金流量 `t163sb20` 彙總表（一季一市場一請求，回應 1～4 分鐘、
  1～1.6MB），六種產業格式依表頭名稱解析（`market.FS_MAP`；銀行營收＝利息淨收益＋利息以外淨損益）。存 `data/lab/fsq/{年}Q{季}`
  （仟元；損益、現金流量為當年累計，`v3data.load_fs` 相減成單季）。2013Q1 起回補走 `.ping/lab` 第一行 `fsfill`（每輪 48 分鐘、4 並行，
  共 324 請求、分多輪）；每日 `fetch_lab.py` 只在法定期限後補缺（每輪最多 4 請求），期限後 14～45 天補抓一次晚報公司。
- **飆股研究**（`arm/lab/superx.py` 規格 VER 2、`scripts/run_super.py` → `data/lab/super_research.json`，資料或規格改了才重跑）：
  標籤 A＝之後 60 個交易日最高價 ≥ +50%、B＝250 個交易日 ≥ +100%（含息還原、`bt3d.Panel`）；樣本＝每週最後交易日、
  20 日均成交值 ≥ 1,000 萬、上市滿 60 日、**最近月底市值 ≥ 40 億**；22 個特徵（趨勢樣板、RS、營收、財報、規模），不含大盤與總經（使用者指示）。
  樣本內 2014–2019 找條件與規則（2～3 個條件、提升倍數 ≥2、兩個子期間各 ≥1.5）→ 驗證期 2020–2022 選（≥1.5、最多 5 條、重疊 ≤0.8）
  → 保留期 2023 起**只算一次**。計算用整數位元集合（六十萬列 × 數千組合幾秒）。
  · **市值下限是 v2 加的（跑任何結果之前）**：`v3px` 只收「曾經月底市值 ≥40 億」的股票，更小的只有日後長大的才在資料裡＝用未來挑樣本；
    ≥40 億的股票每個月底 100% 有日線，下限內沒有這個偏誤。
  · 體質檢查 11 項（`superx.CHECKS`，《超級績效》固定條件，頁面 `copage.SXCK` 同一份、tests 守）只描述「過去符合時翻倍的比例」與
    「符合幾項」各組比例，不拿來選規則。
  · **結果（2026-10-16，文件第 7 節）**：A（3 個月 +50%）有效——定案 5 條都是「月營收創歷史新高＋近四季 ROE 偏低＋股價強勢」
    的**轉機股**，保留期（2023 起）任一條命中 24.9% vs 全體 9.9%（2.5 倍），3 個月後平均 +15.7% vs +5.1%，但只有 52% 賺錢、
    最大跌幅中位數 −15%；13 年中 11 年明顯高於全體。B（一年翻倍）保留期只剩 1.4 倍、一年後中位數 −16% →
    **保留期出來之後決定不放進候選**（`superx.USE_LABELS = ("A",)`，規則本身沒改，頁面只列成績）。
    ROE ≥ 15% 的績優股反而比全體少漲（0.86 倍）。研究只回答「誰比較可能大漲」，**沒有回測買賣規則**——要變策略得另做逐筆回測。
  · 頁面：A 規則、保留期命中率與 3 個月後報酬、逐年表、B 規則轉弱說明（`copage.sxBody`）——2026-10-16 起收在機會頁「飆股」段的
    「過去成績與研究結論 → 飆股候選規則」，符合的股票以「飆股候選」標籤併進同一份名單（見下一專段）；
    個股卡「飆股體質檢查」旁邊寫各項的過去比例（A 標籤）。每日候選由 `company.market_table(DL, rules=…)` 用同一支 `feats_on` 算
    （合格判斷的市值同研究用月底快照）；規則文字由條件重算（`cond_text`，只影響顯示）。
- **踩過的坑**：①`analyze.run` 裡別用 `rows` 當區域變數（後面頁面的個股列表就叫 rows，蓋掉整頁壞掉；tests 守）；
  ②`.ping/lab` 第一行必須只有模式（`probefs 時間戳` 會落到預設的完整回補）；③MOPS 一個請求 1～4 分鐘，探針要設時間上限、即時輸出；
  ④圖表 X 軸標籤依實際字寬排、最後一個一定顯示（`axisLab`）。

**《超級績效》SEPA、綜合最優解、超級飆股觀察名單（2026-10-16；研究在 `tw-superstock-lab/`，用 lab 長歷史＝PROGRESS A8）**：
- **使用者問「飆股候選是不是照《超級績效》」**：不是——它是 superstock SPEC §5 的逆向拆解（轉機股規則），書中的買賣方法是 SPEC §6 的 S01。
  S01 照原文跑（`reports/P4_S01_plan.md`，跑前 commit）：**固定 3% 轉折的 VCP 在台股幾乎不成立**（九年 26 筆）；v2 改成 max(3%, 1.5×ATR14)
  後 2014–2019 年化 −1.0%（大盤 9.9%）、2020–2022 18.3%（大盤 9.2%），勝率約 30%——成績看行情，不穩。
- **「綜合找到最優解」（`reports/P5_plan.md`／`P5_summary.md`）**：84 組（7 族 × 進場 × 出場 × 大盤）→ 入圍 2 個 → **DSR 都未達、保留期
  （2023 起，已用掉）大輸大盤**：大盤年化 42.4%、一般股票等權 23.6%、飆股候選照頁面做 22.4%（回落 −48%）、加書中 8% 停損反而 4.4%。
  結論＝找不到穩定贏大盤的機械買賣法；**書中停損套在台股飆股候選上把勝率從 47% 打到 18%**。
- **使用者改要「名單裡常出現 2～20 倍股、自己判斷」**（`reports/W1_plan.md` v2／`W1_watch.md`）：9 份每週名單比「早期就列出大飆股」，
  事前規則選中**合併名單 S9＝飆股候選 ∪ VCP＋樣板 ∪ 營收創新高＋樣板**（每週約 22 檔）：2014 年起 5 年 10 倍的 122 檔裡 93 檔在離高點還剩
  ≥3.16 倍時就在名單上（中位數已漲 2.0 倍時列出、之後再 7.2 倍）。**但名單裡多數股票不會變大飆股**（10 倍股比例 2.9%，全體 2.5%）；
  「每週換股的隨機名單」涵蓋面更廣、早期碰到率更高，所以這份名單的價值是「人看得過來、大飆股通常在裡面」，不是挑得準——頁面已寫明。
  · 每日名單在 `company.market_table` 算（`watchlist.tags_for`；VCP 用 `arm/lab/vcp.py` 純 Python 版，`tests/test_watchlist.py`
    逐日比對研究版一致），過去成績讀 `data/lab/watch_research.json`（`tw-superstock-lab/scripts/run_watch.py` → `export_watch.py`，
    規格或資料改了才重跑）。名單只收月底市值 ≥40 億的股票（lab 資料範圍）；起漲時更小的大飆股不在範圍內。
- **名單太長 → 提高命中率（W2～W4，2026-10-16 使用者：「太多了吧你這樣我怎麼看」「超級績效不是也有參考技術線嗎」→
  「你的邏輯不應該是每天給幾檔吧 是要如何把選股的命中率提高」；目標＝一年內翻倍；規劃都在跑之前 commit）**：
  · **交叉比對沒有用**（`reports/W3_plan.md`／`W3_results.md`）：28 個條件（月營收、獲利、價格強度、技術線型、階段、量價、族群；
    `arm/lab/layer.py`）。7 類分數 ≥5 在 2020–2022 只有名單的 1.03 倍（2014–2019 1.11 倍）；最好的兩條件組合（EPS 年增加速 ∧
    相對強勢前 10%）2014–2019 1.85 倍、2020–2022 1.00 倍 → 都沒過關、**頁面不分層**（研究檔 `use: null`，分數只當參考）。
    三段期間都比名單準的只有價格強度（相對強勢前 10% 1.32／1.10／1.44、RS ≥ 90 1.23／1.11／1.29）；基本面條件 2020–2022 反轉；
    **《超級績效》的 VCP（0.71／0.75／0.59）、緊密整理（0.86／0.52／0.72）三段都比名單低**——只拿來標買點與停損，不拿來挑股票。
  · **使用者選「用價格強度縮短名單＋加入大盤時機」**（`reports/W4_plan.md`／`W4_results.md`；小型股不擴：沒有完整 FinMind）：
    價格強度在前段（RS ≥ 90 或相對強勢前 10%）一年內翻倍 14.2%／20.4%／33.3%，名單其餘 8.7%／16.9%／16.5%（整份名單
    11.5／18.7／26.1），12 年有 10 年較高——**這個條件是看過 2020–2022 才選的**，頁面寫明、只做「先列」不當驗證過的分層。
    大盤：加權指數 50 日線 > 200 日線（M2）是 2014–2019 唯一兩半都穩的狀態，2020–2022 在下時名單翻倍 25.3% vs 在上 17.2%（1.47 倍、
    過關），但全部股票也一樣（17.4% vs 11.4%，大跌後一起反彈）、9 年只出現 5 段 → 只寫成一段說明。
  · **頁面＝機會頁「飆股」一段**（`copage.wlSec`，段 `o-sx`；原「飆股候選」與「超級飆股觀察名單」兩段合併，`o-wl` 已拿掉）：
    價格強度在前段的依 RS 排序先列、其餘收進「其他 N 檔」；位置欄＝打底中／準備好／今天突破／突破後仍在買點／突破失敗／漲太遠，
    有買點時附樞紐與停損（`sepa.plan_today`：近 65 個交易日逐日推 `Track`——**別縮短**，20 日會忘記一個多月前的突破、把漲上去的股票
    標成打底中，6416 實例）；交叉比對 N／7（電腦版欄）；大盤 50 日線說明；過去成績、逐年表、研究結論、飆股候選規則收在一個展開區。
    資料流：`company._layer`（失敗印「[layer] 第二層篩選失敗」、不影響其他區塊）→ `market_table` 的 `layer` → `analyze.run` pop 後
    `wl["lay"] = layer.page_data(layer.load_res(), …)`；研究檔 `data/lab/layer_research.json`（`run_w3.py`＋`run_w4.py` 匯出，
    規格或資料改了才重跑）。純 Python 核心 `arm/lab/sepa.py`／`layer.py`，研究版逐日比對在 `tw-superstock-lab/tests/test_layer.py`。
  · **VCP 參數查核（W5，2026-10-16 使用者：「不相信超級績效選出來的命中率會低，是不是參數設錯」；`reports/W5_plan.md`／`W5_summary.md`）**：
    現行 VCP（SPEC §5.3）確實有四點偏離書：容許後一段比前一段深、低點沒墊高也算（只有 35% 墊高）、最後一段在基底下半部也算、
    已突破仍算成形。照書修正（`features.VCP_V3`）後台股九年只有約 25 檔次（2014–2019 12 檔、2020–2022 13 檔），
    事前門檻（每段 50 個股票週）不足 → 判定「樣本不足」，頁面與名單不改。少數案例：一年內翻倍兩段方向相反（22% vs 樣板股 9%、
    13% vs 18%）；先漲 20% 才跌 8% 兩段都較高（44%、63% vs 32%、32%），但只列出不判定。**別再拿更多參數組重跑去「找到」VCP 有效**。
  · **飆股段改成「到買點／快到買點」兩層＋每檔參考價位（W6，2026-10-16 使用者：「不想要太多雜訊、要精準、大飆股不會漏掉、
    給標的也要加進去建議的點」）**：「位置」欄改用照書 VCP（`vcp.SPEC_V3`，`sepa.plan_today` 預設；使用者同意），
    名單成員仍用較寬的 `vcp.SPEC`（研究的名單成績是用它算的；標籤改叫「收斂整理＋樣板」以免和照書版混淆）。
    預設只顯示：到買點（準備好／今天突破／突破後仍在買點：買點～追價上限 1.05 倍、停損）＋快到買點（強勢、打底中、
    離 52 週高點 10% 內：突破 52 週高點才算）；其他強勢（離高點較遠：突破 52 週高點才算；漲太遠：拉回 50 日線參考）與名單其餘收起來，
    一檔都不少。交叉比對分數欄拿掉（研究沒有比較準）。手機版把參考價位放在位置底下、RS 放在收盤底下（不橫捲）。
    參考價位只用名詞「買點、停損、追價上限、拉回參考」——**禁用詞「建議買／建議賣／目標價」不可出現**。

**法人預估與產業比較（2026-10-16 使用者：「這個是不是沒有加入未來營收預估、產業分析或是券商目標價」；規劃、決定與結果 `docs/lab_forward_plan.md`）**：
- **使用者決定**：第一階段＝法人預估＋產業比較（產業鏈上中下游、法說會展望之後再說）；**只顯示當參考，不回測、不拿來篩飆股**。
  用字：10-16 先定「法人預估股價」；**10-17 改口「預估股價 −9% 什麼意思，直接說目標價不就好了；是哪個法人也很重要，
  不一定要列出來但我要能點過去看一下」→ 直接寫「目標價」**，只限這兩處引述分析師數字（JS 函式 fcGr／fcVs／fcSrc／fcWho／fcSec／fcLine
  與名詞「法人預估」，`tests/test_fcst.py::FC_FUNCS` 守），其餘照禁用詞。FactSet 快訊標題**仍不轉載**，只用解析出的數字。
- **資料（`arm/lab/fcst.py`，只在 CI 抓，本容器擋 cnyes／yahoo）**：
  · 鉅亨網「台股預估」分類 `api.cnyes.com/media/api/v1/newslist/category/tw_forecast?startAt=&endAt=&limit=30`＝FactSet 調查快訊，
    共識預估有變動才發一則。EPS 快訊（家數、主要年度 EPS 中位數前值→新值、最高最低、當時的預估股價；內文兩張表＝三年 EPS、三年營收千元）、
    預估股價快訊（中位數前值→新值、幅度、最高最低、評等 積極樂觀／保持中立／保守悲觀）。`data/lab/fcst/factset.json`（一檔一行、newsId 去重、
    只有最新一則 EPS 快訊留三年表格）。2026-10-16 回補：217 檔、9,863 則，2023-01 起（再往前 8 週都沒有＝到底）。
    其他鉅亨端點：搜尋 API 只能翻到約 8 個月前；新聞內文 API `/media/api/v1/news/{id}` 回 422（不用它，清單本身就帶內文）。
  · Yahoo quoteSummary（`fc.yahoo.com` 拿 cookie＋`/v1/test/getcrumb`；上市 `.TW`、上櫃 `.TWO`）：家數、預估股價平均／中位／高／低、今明年 EPS 與營收預估、
    30／90 天前 EPS、近 30 天上修下修、評等分布。**沒有分析師的公司 Yahoo 回 0 值**（營收預估 0、家數 0），第一次回補 1,959 檔全被當成有資料
    → 改看分析師家數（實際 517 檔，3 位以上 223 檔）。`data/lab/fcst/yahoo.json` 一天一次（平日只抓有分析師的、週一重掃全部，全掃約 76 秒），
    每週封存一份到 `data/lab/fcst_y/`。
  · 每日：`afterhours_refresh.yml` 在 fetch_lab 後跑 `scripts/fetch_fcst.py`（timeout 420；快訊每班補到現在、Yahoo 一天一次）。
    回補：`.ping/lab` 第一行 `fcfill`（快訊 260 週＋Yahoo 全掃）。
- **產業比較（`arm/lab/industry.py`）**：證交所／櫃買產業別（34 類，範圍大），在 `company.market_table` 裡算 → 頁面 `D.ind`：產業營收近 3 個月年增
  （**同一批公司**加總——公司數會變，不能直接比總和）、公司中位數、成長加快多少、成員 20／60 日漲跌中位數與排名（有股價的 ≥5 檔才排）、名單檔數；
  金融業不算營收年增（月營收含投資損益）。x9t.json 多 `inds`＋每列 `ii`（產業代號），同業名次在瀏覽器排。
- **頁面（`arm/lab/copage.py`）**：公司卡「法人預估」（`co-fc`）第一行「目標價 X 元，比現價高／低 Y%（N 位分析師的中位數；只有 1 位就寫 1 位分析師）」，
  下一行最高最低＋「來源：」——**來源名稱本身就是連結**（FactSet＝鉅亨網那則快訊 `news.cnyes.com/news/id/{newsId}`、Yahoo＝`finance.yahoo.com/quote/{代號}.TW|.TWO/analysis/`）
  ＋「是哪些法人（目標價新聞）」＝Google 新聞搜尋「{公司名} 目標價」（各家券商的數字只在新聞裡，沒有免費的逐家清單）；
  再下面三年 EPS／營收、比前一年、本益比、今年營收進度、評等、Yahoo 近 30 天修正、FactSet 最近 8 次調整（每則可點原文）；手機只列前兩年。
  「產業比較」（`co-ind`）。資料 `dashboard/x9f.json`（約 300KB，點開公司卡才下載；三支 workflow 各兩行 `git add`）。
  機會頁飆股段每檔一行「N 位分析師：今年 EPS ±X%・30 天上修／下修・目標價 Z（比現價高／低 Y%）」（`D.wl.fc`＝`fcst.briefs`＝
  `[人數, 今年 EPS 比去年%, 30 天方向, 目標價比現價%, 目標價]`；點了直接開公司卡的法人預估段 `openCo(c,'co-fc')`）＋「產業熱度」前 5 名。
  · 舊寫法「預估股價 −9%」只有百分比、看不出誰比誰（6214 精誠：Yahoo 1 位分析師 180 元、收盤 197.5＝目標價比現價低 9%），所以改成先寫目標價再寫比現價高低。
  · **來源怎麼挑在 `fcst.view` 決定、頁面不判斷**：FactSet 最新一則在 `STALE_DAYS`=120 天內用 FactSet，否則用 Yahoo（每天更新），都沒有才用舊 FactSet 並標
    「M/D 的資料，之後沒有更新」（舊資料不進飆股段小字）；只列今年以後的年度；Yahoo 沒有中位數才用平均並標 `avg`。2026-10-17：EPS 用 FactSet 110 檔、Yahoo 395 檔；
    目標價 FactSet 130 檔、Yahoo 339 檔、舊 FactSet 6 檔。
  · **⚠ 踩過的坑（2026-10-17）**：2377 微星的 FactSet EPS 快訊停在 2025-08，飆股段的「今年 EPS +94%」其實是一年多前的預估；1815 分析師人數空白
    （只取 EPS 那邊的人數）→ 上面的 120 天換源＋人數取 EPS 與目標價兩邊較大者。上修／下修用「差額 ÷ 前值絕對值」（虧損 −1.0 → −0.5 是上修，直接相除會變成下修）。
- 測試：`tests/test_fcst.py`（用真實快訊當樣本：解析、去重、一檔一行寫檔、Yahoo 0 值、頁面接線與禁用字）、`tests/test_industry.py`。

**長線「投信動能成長股」與 S5（2026-10-14 使用者：「更為長期波段……找新一波動能成長股、超過 100% 潛在報酬」；`arm/lab/growth.py`）**：
- 四關：投信（官方投信 20 日買超 ≥ 股本 0.5% 且 ≥12 天買超；即時另認主動 ETF 20 日內 ≥2 家新建倉且投信未淨賣）／
  成長（月營收年增 ≥20%、累計 ≥15%；次月 11 日起才算可得）／動能（收盤>MA60>MA120、MA60 上揚、距 120 日高 20% 內、
  離低點 +30%、120 日報酬前 30%）／空間（市值 50～1,500 億、日均成交 ≥1 億）。
- 回測資料：Yahoo 兩年價量（市值 ≥30 億上市櫃，約 1,300 檔）＋官方逐日投信（2024-11 起）＋FinMind 月營收（只抓候選股，僅回測用）。
  `.ping/lab` 寫 `growth-N` 觸發（每輪 50 分鐘，證交所限流時分多輪）。
- 結果（2025-04～2026-09 月選，同檔 6 個月內只算一次）：投信＋動能 6 個月內翻倍 31%（35 筆）vs 只看動能 17%、基準 10%；
  但**整段多頭、進場剛好從關稅崩盤底部開始**，且宇宙只含現存股（倖存者偏差）。
- **出場教訓**：原規則（−10%、+30% 保本、破 60 日線）把持有 6 個月的 +75% 砍成 +31%、中位 −5%——動能股正常回檔就洗出場。
  S5 用「−20% 停損・從最高收盤回落 30%・最長 250 日」：不是樣本內最好（多頭裡一路抱最好看），但在較大群組勝出、且是唯一有下跌保護的版本。
- S5 樣本內交易帳 37 筆：平均 +22%、中位 +3%、勝率 59%——成績集中在 2025/10～2026/2 趨勢段，盤整月份多為 −20% 停損，是動能策略常態。
- **⚠ 踩過的坑**：`store.dates()` 原本取檔名前 10 字當日期，月份分片 `2026-09.json.gz` 變成「2026-09.js」→ 月營收整份讀不到、成長關全落空（測試已守）。

**介面（2026-10-14 改版；使用者：「介面好亂、看不太懂」；規劃與定案見 `docs/lab_ui_plan.md`）**：
六分頁 今日｜個股｜投信｜訊號｜策略｜指數，一打開是「今日」重點（使用者選定；**2026-10-15 版面 v4 改為 機會｜策略｜個股｜籌碼｜指數＋後台，見「版面 v4」專段**）；分頁內各段全部展開＋第二排跳段目錄（同主頁慣例）。
術語旁 ⓘ 讀同一份辭典 `GL`（`page._JS`），原「說明」分頁改為頂欄「名詞」；個股表三視角（ETF 動向／法人籌碼／技術面，
每視角連股票、收盤 ≤9 欄，tests 守）；個股卡電腦（≥1100px）開右側面板不遮表格、手機全螢幕，‹ › 與 ←／→ 依來源清單換檔。
- **走勢圖不畫「ETF 合計持股」**：ETF 陸續進資料集（git 歷史回補、10/13 一次納入 19 檔擴充 ETF）會讓合計持股憑空跳增
  （台積電單日 +16 萬張）。`ser` 改輸出 `qa`＝近 60 日主動 ETF 每日真加減碼，畫在 K 線下方、同一條時間軸；
  K 線上 ▲／▼＝主動 ETF 新建倉／出清（只標觀測期內確知日期者）。
- 投信事件 `iev` 上限 40 → 300：投信頁依股票彙整新建倉／加碼／減碼／出清檔數，40 筆會少算（安聯 5 日就有 212 筆）。
- **CSS 撞名坑**：同一頁的事件卡已用 `.ev`，投信卡項目首版也叫 `.ev` → 手機上變成一格格重疊的框；新增 class 前先 grep。
- 驗證：容器內 `page.render(analyze.run())` 寫到暫存檔、Playwright 開 file:// 截桌機 1280／手機 390；
  `dashboard/x9.html` 本身不 commit（CI 重建，同主頁 index.html 慣例）。
- **個股走勢序列延遲載入（2026-10-14 第 5 階段）**：`ser` 另存 `dashboard/x9s.json`（約 1.9MB），頁面只剩 0.7MB
  （壓縮後 744KB → 187KB）；開個股卡才 fetch（電腦閒置 1.5 秒預抓），載入中顯示「走勢載入中…」、失敗顯示「重試」，
  `file://` 開本機檔也是這樣（瀏覽器擋 file 的 fetch——本機驗版要起 `python3 -m http.server`）。
  序列檔自帶 `dates`：若它比頁面舊，圖照畫到它自己的日期並標「走勢資料到 M/D（尚未更新到最新）」，不會錯位。
  · **過渡期坑**：push 觸發的 daily.yml 用「被推分支」上的 workflow 檔——排程會話分支若分岔自本改版合併前，
    那一輪不會 add `x9s.json`，線上序列檔停在前一班 main workflow（cron／dispatch）產的版本（照上面的日期註記顯示）；
    下一班 cron／dispatch 自然補上，根治＝合併後做一次「排程搬家」。

## 「景氣溫度」頁（2026-10-17 使用者需求；籌碼雷達頂欄「景氣」進入；規劃、決定與結果 `docs/lab_heat_plan.md`）

使用者原話：「在隱藏分頁裡面再多加一個經濟熱度預估的參考……先做台股的。包含融資餘額、外資淨空單、選擇權、期貨、匯率匯出、
台灣景氣燈號、恐慌指標、美國聯準會利率、通膨值、漲跌家數佔比等等……每天提供訊號上我可以做短線中線長線位階的判斷，
另外加一個頁面……跟找股票不要混在一起」＋「我要可以看到裡面的細項影響佔比，各項都有一個 0～100 讓我參考，不然這種綜合指標很容易只有象徵性」。
- **使用者四個決定**：只算驗證過的指標（等權）；期貨選擇權籌碼另列、驗證過才併入；不推播；短線 1～2 週／中線 1～3 個月／長線 6～12 個月。
- **頁面** `dashboard/x9m.html`（`arm/lab/heatpage.py`，純靜態、決定性輸出）：短線、中線、長線、期貨選擇權四張卡——總分、五段色條、和上週比、
  過去同一區之後的表現（樣本外）、判定；**細項一律展開**：每一項自己的 0～100、把總分拉了幾分（＝（熱度 − 50）÷ 有值的項數，
  加起來＋50＝總分，測試守）、佔比、本週增減；沒算進總分的照列 0～100＋原因。下面是走勢、各線指標明細、驗證、資料來源。
  入口只在籌碼雷達頂欄（`page._HTML` 的「景氣」），**主頁不加入口**。`gen_fund_dashboard.py` 在籌碼雷達之後**另外建**（分開失敗）；
  三支 workflow 各兩行 `git add -f dashboard/x9m.html`（本機不 commit，同 x9.html）。
- **規格事前寫定** `arm/lab/heatspec.py`（VER 2，`tests/test_heat.py` 鎖住）：指標、熱的方向、百分位視窗（日 750 天／月 120 個月，過去的資料才用）、
  公布時間差、納入規則（樣本內 Spearman＋移動區塊重抽 95% 信賴區間不含 0、以多數方向為準）、樣本內外切分（日 2014–2019／2020 起；
  長線 1999–2012／2013 起；期貨選擇權到 2021／2022 起）。**要改＝VER＋1、寫進規劃文件第 10 節，不在看過結果之後改舊版本。**
  實作細節（日曆、對齊、買賣超比的天數、月平均、長線每月最後一個交易日一個樣本）也在跑之前寫進第 10.4 節。
- **計算** `arm/lab/heatcalc.py`（研究與每天建頁共用）；研究檔 `data/lab/heat_research.json`＝`TZ=Asia/Taipei python3 scripts/run_heat.py`
  （約 4 分鐘；資料或規格改了才重跑，每天建頁只讀它決定哪些指標算進總分）。
- **資料** `data/lab/heat/*.json.gz`（`arm/lab/heatfetch.py`、`scripts/fetch_heat.py`；只在 CI 抓，本容器擋這些站）：
  FinMind（融資、法人、期貨選擇權法人、小台未平倉）、證交所 FMTQIK（成交金額＋官方加權指數，1999 起）、期交所（P/C 2002 起、台指 VIX 只有近 4 個月）、
  央行（新台幣、M1B／M2）、國發會（燈號、領先指標、PMI）、經濟部（外銷訂單）、主計總處（CPI）、勞工統計局（美國 CPI）、
  DBnomics 轉載聯準會 H.15＋紐約聯準銀行（有效聯邦基金利率 1954 起）、美國財政部（殖利率 1990 起）、Yahoo（^TWII、^VIX、HYG、IEF）；
  廣度（漲跌家數、站上 60 日線、新高新低）用 v3px 面板＋官方分片自算（月底市值 ≥ 40 億）。
  每天：`afterhours_refresh.yml` 每班＋`daily_fund.sh` 跑 `fetch_heat.py`（台灣日資料已有今天的就不再打、月資料一天一次、分片有新交易日才重算廣度）；
  回補：`.ping/lab` 第一行 `heatfill`。
- **踩過的坑（2026-10-17 三輪探針）**：①**FRED 從 CI 連不上**（150 秒都逾時）→ 美國資料全改官方來源，信用利差改 HYG ÷ IEF；
  ②**勞工統計局 v1 的 GET 不吃年份參數**（只回近 3 年），要 POST JSON（一次 10 年，免金鑰每天 25 次）；
  ③**主計總處伺服器沒送中繼憑證** → `config/certs/twca_ssl_ca.pem`（CA 公開發布的 TWCA 中繼憑證，到 2033）加進信任清單，
  **照常完整驗證，不關掉驗證**；④聯準會 DDP 的 CSV 回空檔、ZIP 的 XML 70MB 且官方說要停用 → 用 DBnomics 轉載；
  ⑤期交所期貨、選擇權法人網站只給近 3 年 → FinMind 2018-06 起；台指 VIX 免費只有近 4 個月 → 從 2026-07 起每天存；
  ⑥Yahoo 含息還原收盤（HYG、IEF）遇到新配息會改寫整段歷史 → 每次整段抓、整段換（`heatfetch._replace`，少於原有 9 成只補不換）。
