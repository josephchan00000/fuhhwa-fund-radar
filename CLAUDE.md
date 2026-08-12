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
     行事曆涵蓋**美國＋歐盟＋中國＋日本**重點數據與**重要企業財報／法說**，項目加「美：／歐：／中：／日：／財報：」前綴；
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
   - **費半／台積電 ADR 收盤同走官方落檔（2026-08-04 新增，根治「收盤稿互斥查無一致值」）**：
     `macrochips.GLOBAL_SPECS` 已加 `sox`（^SOX）／`tsm_adr`（TSM）兩序列，CI 每日自 Yahoo 官方
     序列抓進 `data/macro_chips.json`（僅資料層，溫度計表未加列）——報告引用費半／ADR 收盤值
     一律優先讀此落檔；落檔尚無序列時才用「媒體兩來源一致」。⚠ 媒體收盤稿的坑：搜尋引擎會把
     **他日**收盤稿混進當日結果（自由財經等網址無日期，08-04 險些把他日「費半重挫 5.71%」當
     週一收盤），引用前先核對文內有無**當日專屬事件標記**，對不上就棄用。
   - **卡數下限＝每報 ≥4 卡**（2026-07 由 6 調降以省時；門檻仍為重要度 6/10 以上、上不封頂，深度文照樣保底 1 篇）。
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
   **每卡摘要或影響分析非空**／行事曆為今日）——「摘要／影響分析皆空」該項是 2026-07-31 新增的防呆，
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
     - **主動部署**：`daily.yml` 末步已加「打 **Vercel Deploy Hook**」（`secrets.VERCEL_DEPLOY_HOOK`）——CI commit 完直接觸發 production 部署 main 最新，**不靠 Vercel 自動偵測**（自動偵測曾卡 Initializing／部到舊版）。**使用者需先建 hook**：Vercel 專案 Settings→Git→Deploy Hooks 建 `main` 分支 hook → URL 存成 repo secret `VERCEL_DEPLOY_HOOK`。未設時該步自動跳過、不影響 commit。
     - Vercel `vercel.json` 已設 `Cache-Control: no-store`（全站不快取）→ **線上看到舊的一律是「沒部署」而非快取**，別叫使用者清快取白忙。
   - **⑤ 前十大簡介缺口（2026-07-23 使用者：一再漏掉；2026-08-12 全自動落地；同日改「主責＝15:33 盤後班」）**：讀
     `git show origin/main:data/holdings_intro_gap.json`。**晨間本步驟只讀不補**（使用者 2026-08-12：
     不佔早上、跟最簡單的那班）——count>0 → 成功推播裡帶一句「缺 N 檔簡介，15:33 班會補」即可；
     **補齊主責＝15:33 盤後籌碼 Routine 步驟②**（該班最輕、又在晨間持股抓取之後，缺口當天下午清）。
     **連兩天 count>0**（昨天下午沒清＝排程搬家前過渡期或該班失效）才在晨間親自跑下列迴路並查原因。
     **極簡迴路**（15:33 班與晨間 backstop 共用；全程 ~5 分鐘、不跑任何抓取腳本）：
     ① gap 檔 `items[].name` 就是快照原字串——**每檔 1 次 WebSearch** 查證（公司本業／代號／國別）；
     ② 補進 `config/holding_profiles.json`（`{原字串: {intro, ticker, country, verified}}`，
        intro 純事實、避開禁用詞；country＝公司母國，如英飛凌→德國）；
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
     · `pipeline` 欄（申請中、審查未過、或申報生效日尚未到）＝不警示不上版也**不登錄**，
       生效後下輪自動升進 `items` 再處理。
     機制與坑見下方「新 ETF『自動發現』層」專節。
   - 註：持股基準為月度值（顯示上月底）——不是資料沒更新。

## 指令：「ETF 募集週掃」（2026-08-10 建立——使用者：「找到募集的資訊然後主動更新，一週一次」）

**與每日 SOP 步驟 9⑧ 的分工（2026-08-10 使用者釐清後定調，勿混淆）**：
「一週一次」講的是**主動出去掃描**的頻率；**已被發現層列名的缺口不等週一、當天就補**
（見步驟 9⑧）。所以本週掃的價值在**每日流程做不到的那些事**：全面盤點（發現層兩個來源
都沒收錄的檔）、既有條目的日期／頻率異動核對、hint 檔補正式日期、過期條目清理、
`pipeline` 內申請中檔有無新生效。正常情況下每日已把新缺口補掉，週掃多半只是核對與清理。

每週 Routine（台北週一 08:05）火進綁定會話執行；使用者手動打「ETF 募集週掃」也照跑。
**全程不跑資料抓取腳本、不動 reports/**、只改 `data/etf_upcoming.json`**：

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
3. 更新頂層 `as_of`＝今日 → pytest 全綠 → commit `chore: ETF 募集週掃 {日期}` push 本會話
   指定分支——**push 動到該檔會自動觸發 daily.yml**（on.push.paths 含它），併檔段驗證後
   帶進 main 重建上線，**不需人工 merge**。
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

> （排程自動觸發）全部更新。依 repo CLAUDE.md「指令：全部更新」SOP 完整執行：產提示包 → 平行子代理 WebSearch 產當日新聞（美股 v1/v2、台股、總經、行事曆；嚴守版型／禁用詞／每卡連結）→ gen_*.py --check 與 check_reports.py 全 🟢 → 重建儀表板 → pytest 全綠 → commit+push 到本會話指定分支（push 動到 reports/** 會自動觸發 daily.yml）→ 等 main 前進後驗證（新聞今日、產表時戳為 CI、nav_date 推進）。完成或失敗都用 PushNotification 推播一句話結果給使用者（成功：當日 3 條市場重點摘要；失敗：卡在哪一步＋影響）。不可宣稱「線上已生效」（本環境看不到 Vercel）。若工作樹有未完成的其他工作，先 stash 或用獨立分支，勿混入每日更新 commit。

Routine prompt 原文②——盤後籌碼即時更新（15:33）：

> （排程自動觸發）盤後籌碼即時更新——GitHub cron 實測遲 1~3 小時，本 Routine 負責準時；全程只做三件事、不跑任何資料抓取腳本、不動 reports/**：① 用 mcp__github__actions_run_trigger（method=run_workflow、workflow_id=afterhours_refresh.yml、ref=main）觸發盤後刷新，成功觸發即收工、不等它跑完；MCP 不可用時備援＝在本會話指定分支寫 .ping/afterhours（內容任意）後 git add -f、commit、push——該路徑 push 會自動觸發同一 workflow。② 前十大簡介缺口順手補（使用者 2026-08-12：不佔早上、掛在本班——本班最輕且在晨間持股抓取之後）：git fetch origin main 讀 data/holdings_intro_gap.json，count=0 → 跳過；count>0 → 依 CLAUDE.md 步驟 9⑤ 極簡迴路：每檔 1 次 WebSearch 查證（公司本業／代號／國別）→ 補 config/holding_profiles.json（{原字串:{intro,ticker,country,verified}}，intro 純事實、避開禁用詞）→ python3 -m pytest -q tests/test_holdings_intro.py → commit「chore: 補持股簡介 N 檔」push 本會話指定分支——push 自動觸發 daily.yml 併檔＋重建上線，不需 PR、不需監看。③ send_later 排 60 分鐘後自驗：git fetch origin main 讀 data/macro_chips.json，若為交易日（當日 reports/macrocal 市況段「台股」不含休市）而 inst_total 仍缺今日 → 補 dispatch 一次、再 send_later 25 分鐘後檢查，仍缺才 PushNotification 一句話（缺什麼＋afterhours run 日誌看到的原因）；資料已到或休市 → 安靜結束、不推播、不留言（使用者 2026-08-03 指定「失敗才推播」）；若②有補簡介，同回合加驗 origin/main 的 data/holdings_intro_gap.json 已歸 0，仍 >0（分支 workflow 檔太舊、併檔通道沒生效）→ mcp__github__actions_run_trigger dispatch daily.yml（ref=main、news_ref=本會話指定分支）一次即可修復。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

Routine prompt 原文③——晚間 NAV·PCF 即時更新（18:58）：

> （排程自動觸發）晚間數據即時更新（基金 NAV＋主動式 ETF 當日 PCF）——不跑任何資料抓取腳本、不動 reports/**：① mcp__github__actions_run_trigger 連發兩個 dispatch（皆 ref=main）：afterhours_refresh.yml（18 時後場次會加抓基金 NAV）與 etf_holdings.yml；MCP 不可用時備援＝push .ping/afterhours 哨兵（只能觸發前者，後者靠其 17:40 cron 遲到自癒即可）。② send_later 排 45 分鐘後自驗：git fetch origin main，a) data/funds/_index.json 最新 nav_date ≥ 上一交易日、b) data/etf_holdings.json 本家主動式（00991A）揭露日已推進（休市日無新 PCF 屬正常、勿誤報）；異常 → 補 dispatch 一次、25 分鐘後仍異常才 PushNotification 一句話。③ 自驗回合結束前再 send_later 一個台北 23:20 的夜檢：讀 origin/main 的 data/macro_chips.json 與 data/afterhours_alert.json，交易日而 margin_bal 缺今日或 alert missing 非空 → PushNotification 一句話（22:05 cron 整班消失時這是唯一的主動警報）；正常 → 安靜結束。皆「失敗才推播、成功安靜」。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

Routine prompt 原文④——美股收盤序列更新（05:08，2026-08-05 建立、2026-08-07 補記本檔）：

> （排程自動觸發）美股收盤序列更新（費半 ^SOX／台積電 ADR 昨夜收盤入檔，供 06:35 晨報引用；台北 05:08＝美東收盤後，夏令 17:08／冬令 16:08）——全程不跑任何資料抓取腳本、不動 reports/**：① 用 mcp__github__actions_run_trigger（method=run_workflow、workflow_id=afterhours_refresh.yml、ref=main）觸發刷新，成功觸發即收工、不等它跑完；MCP 不可用時備援＝在本會話指定分支寫 .ping/afterhours（內容任意）後 git add -f、commit、push——該路徑 push 會自動觸發同一 workflow。② send_later 排 35 分鐘後自驗：git fetch origin main 讀 data/macro_chips.json，series.sox 與 series.tsm_adr 須含最近一個美股交易日（以前一美東平日為準；美股休市日無新 bar 屬正常、勿誤報——拿不準就查前一日 reports/macrocal 市況段「美股」欄）；缺 → 補 dispatch 一次、再 send_later 20 分鐘後檢查，仍缺才 PushNotification 一句話（缺什麼＋afterhours run 日誌看到的原因）；已到或休市 → 安靜結束、不推播（失敗才推播）。send_later／create_trigger 若回 MCP error -32003（需審批、無人值守無法核准）：勿跳過自驗、也勿只推播「排程失敗」了事——改用 Bash run_in_background 背景 until 迴圈（每 5 分鐘 git fetch origin main 檢查一次直到自驗時點）等到時點喚醒後照樣自驗與後續處置，機制見 CLAUDE.md「已知環境限制與防呆」-32003 條。

Routine prompt 原文⑤——ETF 募集週掃（週一 08:05，2026-08-10 建立）：

> （排程自動觸發）ETF 募集週掃——找到新 ETF 募集資訊、主動更新「即將登場」（使用者 2026-08-10 指示：主動更新、一週一次）。依 repo CLAUDE.md「指令：ETF 募集週掃」SOP 執行：全程不跑資料抓取腳本、不動 reports/**、只改 data/etf_upcoming.json。① git fetch origin main 讀 origin/main 的 data/etf_upcoming_gap.json（CI 自動發現的漏網檔）與 data/etf_upcoming.json 現況，pytest tests/test_etfwatch.py 看 stale guard 有無紅；② WebSearch 盤點（鉅亨 IPO 頁 fund.cnyes.com/IPO/index.htm＋MoneyDJ 新基金頁＋工商時報／經濟日報「投信新基金」稿，容器擋原頁就用搜尋摘要），逐檔兩來源核對：新核准檔補登（時程未定 raise_hint＋asof、未派碼 code:null）、hint 檔補正式日期、募集期間／掛牌日／配息頻率異動修正、掛牌逾期條目清理；海外被動指數檔 track:false；本家復華新檔最優先、絕不可漏；③ 更新頂層 as_of＝今日 → pytest 全綠 → commit「chore: ETF 募集週掃 {日期}」push 本會話指定分支（push 動到該檔自動觸發 daily.yml 併入 main 重建上線，不需人工 merge）；④ 有異動 → PushNotification 一句話列出異動檔；無異動 → 安靜結束不推播；失敗 → 推播卡在哪一步。

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
    交易日（讀當日 macrocal 市況段判休市）16:30 後三大法人須含今日、22:45 後融資融券須含今日且
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
- **部署**：CI commit 後打 `secrets.VERCEL_DEPLOY_HOOK` 主動部署；**該 secret 未設前**，部署仍靠 Vercel 自動偵測
  （曾卡 Initializing）——如使用者回報線上沒更新，先問 Vercel Deployments 對到哪個 commit。

## 已知環境限制與防呆（曾踩過的坑，不要再犯）

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
  - **防呆（兩道）**：
    ① **派工時寫明版型**（步驟 2）：子代理 prompt 必須要求欄位標籤帶 `**粗體**`——這是唯一的源頭預防。
    ② **`check_reports.py` 擋下**（步驟 3）：每卡斷言 `summary` 或 `points` 至少一項非空，
       🔴 訊息直接點名「標籤未加 **粗體**」。已用 2026-07-31 的壞檔驗證過會紅（6 卡全中）。
  - **修法＝改報告、不要改渲染端**：把該報告的 `N. 標籤：` 補成 `N. **標籤**：` 即可
    （`新聞摘要`／`一句話重點`／`對…影響`／`為什麼值得讀` 都要）。
    **不要為了「相容無粗體寫法」去放寬 `extract_cards()` 的 regex**——粗體同時是儀表板的視覺格式來源，
    放寬會讓沒粗體的內文行被誤判成欄位。
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
  **三層清單（2026-08-06 使用者規劃）**：①**官方**＝`YT_OFFICIAL_CHANNELS`——**兩個頻道**
  （使用者提供）：@fhifund 主頻道（UCD3J90bNoHykt6Eru8YxUmQ，金管家系列在此）＋@fhetf
  ETF 專屬頻道（handle 執行期以 channels.list forHandle 解析；config 鍵吃 UC id 或 @handle
  皆可）——近窗**全部上傳**（uploads 播放清單 UC→UU、每頻道 1 單位，依日期序、掛「官方」章）；②**相關**＝search 4 組（復華投信／
  復華 基金／復華 ETF／00929）依觀看數**取前 3**——標題只寫自家 ETF 代碼、沒寫「復華」的
  影片也算相關（`_fh_codes()` 動態取 etfwatch 清單中名稱含復華者；代碼須為**獨立詞**——
  曾誤收日文單字卡課號「L#00929」）；③**同業熱門**＝近 2 天依觀看數排序的「台股 ETF」
  搜尋中含**同業代碼**（`_peer_codes()`）者**取前 2**（掛「同業熱門」章；自家內容歸②
  不重複）。三層共用 seen 去重、官方優先。**時長 ≤3 分標 Shorts**（連結走 /shorts/、
  來源標「YouTube Shorts」）。額度：search 5 組×100＋playlistItems 1＋videos.list 1
  ≈每輪 502 單位（日限 10,000）——**勿再隨意加查詢組**。
  **FB／IG／Threads 擴充規劃見 `docs/social_api_plan.md`**（2026-08-06 查證：Threads 公開
  關鍵字搜尋為第一優先、需使用者建 Meta App＋過審 `threads_keyword_search`；FB 只做自家
  粉專、IG hashtag 額度緊排最後）。
- **新聞來源黑名單**：排除「富聯網」（moneylink）。
- **禁用詞**（正文不得出現，機構觀點也要改寫避開）：保證、穩賺、必賺、包賺、必漲、必跌、一定會、唯一、
  建議買賣、建議買、建議賣、目標價、零風險、無風險、穩賺不賠。

## 儀表板「🕒 資料更新時間」區塊

`arm/fund_dashboard.py` 的 `_freshness_view()`，顯示各資料來源鮮度（皆台北時間）：
NAV 日／持股基準（月度）／持股快照抓取／美股新聞／台股新聞／總經・政策／經濟行事曆／基金新聞・社群／
ETF 數據追蹤／ETF 持股揭露／總經・籌碼數據／儀表板產表。新增資料來源時請同步加進此區塊。

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

追蹤台股被動 ETF（0056/00878/00919/00929/0050/006208）＋**主動式股票 ETF** 15 檔（含本家 00991A、
2026-07 新增熱門／新募集 00988A/00990A/00403A/00407A）＋**「其他」組**（2026-07-20 新增：本家上櫃
00998A 主動復華金融股息／00986D 主動復華金融債息，`kind="other"`、Yahoo 代碼字尾 .TWO；
本家各檔不整列高亮，改在產品名內把「復華」標品牌金色 `.fh`）的
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
**上櫃檔（櫃買掛牌，如統一 00411A/00987D）kind 填 other**——同 00998A 慣例，etfinfo 未收錄）。
消費端（rows／load stub／fetch_etf_holdings targets）都吃 `watch_tuples()`，掛牌當天 CI 就抓
績效＋持股，stub 先上代碼／名稱／頻率。**仍需人工的兩件事**：①UPCOMING 登錄本身（募集／掛牌
公告無統一 API）；②掛牌後要「轉正」進 WATCHLIST（查證成立日／頻率、補 SEED_PERF）——
`tests/test_etfwatch.py::test_upcoming_graduation_guard` 守著：**掛牌逾 14 天未轉正 → 紅**，
逼下一輪收斂時處理（同持股簡介覆蓋率的逼補模式）。首例＝00410A（8/3 掛牌、8/5 轉正）。
**「即將登場」五狀態三分組改版（2026-08-10 使用者兩輪指示：研討會投影片抓包資料不齊全＋
「太長記得分類一下，尤其是只有核准還沒確定募集時間的」）**：
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
