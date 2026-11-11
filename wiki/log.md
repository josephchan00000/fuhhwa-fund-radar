# 知識庫日誌

> 只往後加，新的寫在最下面。格式：`## [YYYY-MM-DD] 動作 | 標題`；動作＝搬家／收錄／整理／查詢。
> 快到 1.5 萬字上限時，把最舊的整月一字不改搬到 `docs/wiki_log/YYYY-MM.md`（只讀；裡面的「- 刪：」行 `scripts/wiki_facts.py` 照樣會讀）。2026-10 的在 `docs/wiki_log/2026-10.md`，上次「整理」也在那裡。

## [2026-11-01] 收錄 | 參數鄰近檢查（B 段）
- nbrspec VER 1（算結果之前 commit）、`arm/lab/sigrobust.py`、`scripts/run_robust.py` → `data/lab/robust_research.json`：每一組過列出門檻的（訊號, 方向, 看多久）一次動一個參數、往上往下各一個值，每個參數各自至少一半也過才算穩定。2,794 組穩定 74%；原本參數重算和研究檔一模一樣。還沒接上頁面（第 D 段）。新頁 `lab/signals-quality.md`（核對與參數鄰近；`lab/signals.md` 已到長度上限），`lab/chip-ui.md` 連過去（規劃第 12 節）。

## [2026-11-01] 收錄 | EMA 賣壓與天數衰減（C 段）
- emaspec VER 1、decayspec VER 1（都在算結果之前 commit）；`arm/lab/sigema.py`、`arm/lab/sigdecay.py`、`scripts/run_ema.py`、`scripts/run_decay.py`。兩個都沒有比現在好，照規則不換。第 26 版分支併進來、sigage／thermo 研究檔重算，`sigverify.check_thermo` 改比 VER 25 的票。改了 `lab/signals-quality.md`（規劃第 13 節）。

## [2026-11-01] 收錄 | 今天的清單接上第 26～27 版、第二套算法補齊（D 段）
- sigspec VER 27（頁面之前 commit）：參數一動就不成立的不列、放進行中，法人訊號加一句。`sigcat.listing` 接上參數鄰近（`robust_index`、`RB`）；`sigverify.check_age`、`thermo2` 補第 26 版格子與溫度計新票的第二套算法，抓到 S&P 500 2003-10-22 收盤等於月線的浮點誤差並修好（`sigage._sgn`），五個市場 0 個不一致。頁面：每一條寫原因（那一格的數字、出現日、過了幾天、條件、今天看到的那一筆）、進行中（預設收起）、訊號總覽多一欄「今天進場」。新頁 `lab/signals-today.md`（`lab/signals.md` 快到長度上限，今天的清單一節搬過去）；改了 `lab/signals.md`、`lab/signals-quality.md`、`.claude/rules/signals.md`（規劃 `docs/lab_signal_quality_plan.md` 第 14 節、`docs/lab_signal_listing_plan.md` 第 10 節）。


## [2026-11-01] 查詢 | 綜合指標要不要用 EMA／衰減（查證＋不看報酬的數字，等決定）
- 使用者問「各項綜合指標是不是更應該參考EMA或是衰退期的概念」。新規劃 `docs/lab_time_weight_plan.md`：文獻（均線種類不重要、景氣指標讀數普遍加平均／緩衝／持續條件、等權難打敗、小樣本往整體拉）＋翻動次數（溫度計約 4～5 週換一次讀數、第 26 版比第 25 版多換 20%；今天 94 類裡 44 類靠不到 15 次的格子）。選項 T1～T3 等使用者決定。改了 `lab/signals-quality.md`。

## [2026-11-01] 查詢 | 每天看要靈敏又要準：讀數「證據夠才換」與準度現況（等決定）
- 使用者：「我會希望我的訊號是更靈敏的因為我是每天看…而且我希望是要有高的準確度」。`docs/lab_time_weight_plan.md` 加第 9 節（取代第 6、7 節）：每天看的讀數一年換 30 次以上、七成多 5 天內換回、約六成只差一項；「多兩類撐著才換」7～8.5 次、兩成換回、晚約 1 天；準度現況警示 10／15、偏多 0／15。步驟 S1～S5 等使用者決定。改了 `lab/signals-quality.md`。

## [2026-11-01] 查詢 | 合併之後重新評估「今天的訊號」：少而準（等決定）
- 使用者：「你先合併再看一下 重新評估有沒有更好的方法…不要又老毛病一直亂加東西…記得訊號根本的目的」。PR #424 合併、CI 建頁成功後看市場頁：台股「今天的訊號」手機高 1,341 像素、中線讀數「偏多」與「過去讀數這樣的時候」警示 80% 打架、94 類裡只有 9 類之後也成立（偏多 0）。`docs/lab_time_weight_plan.md` 第 10 節：溫度計改大回撤風險、多一票撐著才換、清單只列之後也成立的，示意 1,341 → 約 565 像素。改了 `lab/signals-quality.md`。
- 教訓：合併後把分支重設到 main 再推，推送差異含 `reports/**` 觸發了 daily.yml（18 秒後取消、沒有 commit）；`lessons.md` 加一條。

## [2026-11-01] 收錄 | 使用者決定維持現在的「今天的訊號」，精簡改版不做
- 使用者：「我喜歡現在的版本 因為現在我們的東西還沒有優化完成所以直接下一個絕對的結果我認為是不可靠的 要能夠有細節讓使用者去判斷」。`docs/lab_time_weight_plan.md` 第 10.7 節記下決定（第 6、9、10 節的改法都不做）；`user.md` 加一條偏好；改了 `lab/signals-quality.md`。

## [2026-11-01] 查詢 | ponytail 第一段：程式地圖（只讀）
- 使用者說「好」開始 E 段。新文件 `docs/code_ponytail_map.md`：14 支 workflow、98 支腳本的分類、`arm/` 261 個模組誰在用、沒人用的函式 12 個、寫檔 176 處、外部資料來源 111 個；找到一套沒有 workflow 在跑的舊本機流程（約 6,200 行）。`docs/code_ponytail_plan.md` 加第 6 節。沒有改任何程式。

## [2026-11-01] 查詢 | ponytail 第二段：體檢報告（只出報告）
- 使用者確認舊的本機流程「沒在跑了」。新文件 `docs/code_ponytail_audit.md`：必修 2（`fetch_holdings.py` 持股頁抓不到寫空、`ussxqm.watch` 抓不到洗掉賣出提醒）、該修 5、可以更好 3；舊流程可拿掉 124 個檔約 7.2 萬行（含 `.claude/rules/calendar.md` 要一起改）。地圖補「腳本之間直接 import」（`run_ytd.py` → `run_sxlive_seed.py`）。沒有改任何程式。

## [2026-11-01] 收錄 | 基金持股頁抓不到時沿用上一次（體檢第 1 條）
- 使用者「照建議」開始修。`scripts/fetch_holdings.py` 加 `_keep_holdings`：持股頁出錯或解析 0 筆、舊檔有持股 → 前十大、配置、持股基準日沿用舊檔，淨值照新的；測試 `tests/test_fetch_holdings.py`。改了 `env/container.md`。

## [2026-11-01] 收錄 | 美股強勢品質股每天的 50 日線檢查：抓不到的那一檔沿用上一次（體檢第 2 條）
- `arm/lab/ussxqm.py`：`watch(…, prev)` 同一週紀錄、這一檔抓不到 → 沿用上一次（含已觸發的賣出，標 `carried`）；`watch_failed`／`save_watch` 每一檔都抓不到就不寫檔；`scripts/fetch_ussx_watch.py` 帶上一次的檢查。測試 `tests/test_ussxqm.py`。改了 `lab/us-qm.md`。

## [2026-11-01] 收錄 | 寫檔先寫暫存檔再換名、前瞻紀錄讀到壞檔停下報錯（體檢第 3 條）
- 新模組 `arm/fileio.py`（`write_text`／`write_bytes`／`read_json`）；七本前瞻紀錄要寫回時 strict 讀（`fundnav`、`core`、`valog`、`ytd`、`ussxqm`、`candrun`、`sxlive`，體檢寫四本，另外三本同樣的問題一起修）；會被 `timeout` 砍到的抓取程式寫跨天的檔改用它；`.gitignore` 加 `*.tmp`。測試 `tests/test_fileio.py`。改了 `env/container.md`。

## [2026-11-01] 收錄 | 拿掉沒在跑的舊本機流程（體檢第 7 條）
- 使用者確認舊流程「沒在跑了」、臉書抓取留著。拿掉 117 個檔（腳本 16 支、模組與 `arm/copy/`、`connectors/brokers/`、專用測試 14 支、設定與舊資料、`reports/intel/`）；`arm/connectors/social/` 只留 `facebook`、`base`、`filters`、`__init__`。`.claude/rules/calendar.md` 拿掉 `arm/calendar.py`。改了 `env/git-history.md`、`main/etf-holdings.md`、`main/fund-returns.md`。

## [2026-11-01] 收錄 | 拿掉舊本機流程剩下的零件（體檢第 7 條第二步）
- `arm/config.py` 的 `distributions()`、`connectors/issuers` 只給舊流程用的 `load_holdings`、`competitor_peers` 與 `base.py`、`connectors/etfinfo.py` 的 `latest_market`、`dividends`、`active_flow`、`connectors/tdcc.py` 的受益人數週增與 `arm/db.py`。正式流程用到的 `config.product`、`issuers/pcf.py`、`etfinfo.fetch_etf`／`holdings_fresh`／`list_etfs`、`tdcc._fetch_csv` 都留著。

## [2026-11-01] 收錄 | Google 新聞查詢出錯時，那一組沿用上一次的新聞（體檢第 4 條）
- `arm/connectors/gnews.py`：`search` 出錯時 `FAILS` 加一、只印第一次的原因；`arm/fundnews.py`：`fetch_funds`／`fetch_etf_products`／`assemble` 標出錯的組，`save` 經 `_carry_news` 併入上一次同組 7 天窗內的項目（比照 `_carry_social`）。測試 `tests/test_fundnews.py`。改了 `main/fund-news.md`、`.claude/rules/fundnews.md`。

## [2026-11-01] 收錄 | 美股內部人季資料解析出 0 筆時跳過、不記做完（體檢第 5 條）
- `arm/lab/insider.py` 的 `do_quarters`：一季解析出 0 筆合格的 Form 4 → 不換掉那三個月、不記做完、印警告，下次重抓。測試 `tests/test_insider.py`。改了 `lab/heat-us.md`。

## [2026-11-01] 收錄 | 美股季報、融資維持率、Yahoo 預估讀不到來源就不寫（體檢第 6 條）

## [2026-11-01] 搬家 | 日誌 10 月的部分搬到 `docs/wiki_log/2026-10.md`
- 日誌到 1.5 萬字上限，使用者選「按月封存」；內容一字不改。`scripts/wiki_facts.py` 的 `dropped()` 也讀封存檔的「- 刪：」行。

## [2026-11-01] 收錄 | 拿掉沒人用的小東西（體檢第 8 條）
- 12 個函式＋連帶的 `heatviz._kcard`／`_key_line`／`_verd`／`KEY_SHOW`、9 個常數、8 個 import、7 個區域變數、8 個 f 字串、3 個參數（`ussxmine.mine_fold` 的 `ix_of`、`hotdd.now` 的 `R_mk`、`cnyesfund.search_all` 的 `max_pages`）。研究規格與研究模組裡沒用到的常數（`bubspec`、`crashspec`、`nbrspec`、`superx`、`optim`、`sepa`、`packtest`、`fwd`）照留；`printview.LANE_ORDER` 的說明搬到 `fund_dashboard` 組報告順序那一行。

## [2026-11-01] 收錄 | 直接取今天的地方改用台北時間函式（體檢第 9 條）
- `arm/`、`scripts/` 裡 `date.today()`／`datetime.now()` 換成 `arm/clock.py` 的 `today_tw()`／`now_tw()`（28 個檔）；CI 本來就設台北時區，輸出不變。`tests/test_heatfetch.py` 改換 `today_tw`。改了 `env/container.md`。

## [2026-11-01] 收錄 | PR 進 main 之前自動跑全部測試（體檢第 10 條）
- 新 workflow `.github/workflows/tests.yml`（pull_request 到 main＋手動）：Python 3.12、台北時區，裝 pytest／numpy／pandas／pyyaml／certifi／pypdf／openpyxl，跑 `pytest -q`；沒裝 playwright，瀏覽器兩支自動略過。改了 `ops/ci-budget.md`。

## [2026-11-01] 收錄 | 債務帳（ponytail 第四段）
- 新檔 `docs/code_debt.md`：7 處已知上限，程式旁各一行 `# shortcut: 上限。升級：…`（只加註解）；`tests/test_code_debt.py` 守兩邊對得上。最急的是台股 2027 年休市表：12/1 前要換成證交所正式表，否則 `tests/test_twholidays.py` 會紅。知識庫各頁留到第五段再改。

## [2026-11-01] 收錄 | 債務帳接進知識庫（ponytail 第五段）
- 目錄「原始資料」加 `docs/code_debt.md`；`main/calendar.md`、`ops/deploy.md`、`lab/us-qm.md`、`main/fund-news.md`、`ops/schedule.md`、`main/etf-watch.md` 各加現況與升級時機；`user.md` 加「資料要自動抓，不靠人工清單」。使用者定調預估配息與隔年休市表都改自動抓（另外規劃）。

## [2026-11-01] 收錄 | 預估配息與隔年休市表改自動抓
- 拿掉人工清單 `ANNOUNCED_EST`，預估配息改抓證交所／櫃買除權除息預告表，金額還沒公告時顯示「M/D 除息・金額待公告」；隔年休市表改抓證交所網站版 `NEXT_API`。改了 `main/etf-watch.md`、`main/calendar.md`、`user.md`；債務帳拿掉一列、改一列（規劃 `docs/etf_div_auto_plan.md`）。

## [2026-11-01] 收錄 | 預估配息補新聞備援
- 交易所表「金額待公告」的那幾檔，改從主流媒體新聞標題取投信第一階段公告的預估金額（`etfwatch.news_estimate`）；探針查過觀測站、證交所 etfDiv、集保都沒有預估金額。改了 `main/etf-watch.md`、`user.md`（規劃 `docs/etf_div_auto_plan.md` 第 5 節）。

## [2026-11-03] 收錄 | 行事曆預期欄自動補
- 「預期」空白的列由 CI 從 ForexFactory 週曆、Nasdaq 經濟日曆補市場共識（兩邊不同不補、只補空白、標 *、「註」寫來源；`arm/calcons.py`）。改了 `main/calendar.md`（規劃 `docs/macrocal_fill_plan.md` 第九節）。另修 `tests/test_etfwatch.py`：掛牌當天自動加入追蹤的新 ETF（00416A）還沒有週報酬，比照待首抓。

## [2026-11-03] 收錄 | 溫度計讀數改看兩邊各自的位置（sigspec VER 28～29）
- 讀數不再比偏多、警示的數量占比（警示合格的本來就多），改看兩邊各自和自己過去 10 年比的位置；長條＝位置、旁邊的數字＝亮著的訊號數（VER 29，看過結果後使用者選）。改了 `lab/signals-today.md`、`lab/signals.md`（規劃 `docs/lab_thermo_lean_plan.md`）。

## [2026-11-04] 收錄 | 偏多、警示的強弱：查過、不分（sigspec VER 30～32）
- 「可能落底」框（大跌中的強落底訊號）逐年檢查台股分得出、美股分不出；改成清單分強弱，看多那一邊分不出；使用者選都不標。頁面照舊，研究紀錄「名詞與判定方式」加一段兩張表。改了 `lab/signals-today.md`、`lab/signals.md`（規劃 `docs/lab_thermo_fair_plan.md`）。

## [2026-11-04] 收錄 | 清單照樣標強弱、大跌中另標落底（sigspec VER 33）
- 使用者看過檢查結果仍要標：每一列寫多／偏多、警示／偏警示，大跌中的強落底另標「落底」（進行中也標），看多那一欄標題改「看多」。研究方法的檢查規格寫好、還沒算。改了 `lab/signals-today.md`、`lab/signals.md`（規劃 `docs/lab_thermo_fair_plan.md` 第 11、12 節）。

## [2026-11-04] 收錄 | 研究方法檢查（sigspec 第 5.9 節）
- 落底與強弱的逐年檢查換 7 種算法重算、另寫一套程式核對：程式結果完全一樣；台股落底一直比較好但差距不大、美股分不出；偏多強弱分不出、警示強的略準。研究紀錄加第 ③ 段。改了 `lab/signals-today.md`（規劃 `docs/lab_thermo_fair_plan.md` 第 13 節）。

## [2026-11-04] 收錄 | 個股報告用官方文件重做（暉盛）＋配股調整（eqspec VER 4）
- 暉盛-創用官方文件包重做：減碼、目標價 135 元，改掉舊版 4 處錯。季底之後配股時每股淨值與 EPS 照新股數（規格 VER 4，先寫定再算）。改了 `lab/equity-report.md`（規劃 `docs/lab_equity_report_plan.md` 第 6 節）。

## [2026-11-04] 收錄 | 臻鼎、德宏、騰雲用官方文件重做＋EPS 配股規則修正（eqspec VER 5）
- 三家報告用官方文件包重做（臻鼎中立 400 元、德宏減碼 27.5 元、騰雲減碼 200 元），舊版共 17 處錯被改掉。騰雲抓到 VER 4 把財報公布前的配股多除一次 → VER 5（EPS 只除公布之後的配股）。改了 `lab/equity-report.md`（規劃 `docs/lab_equity_report_plan.md` 第 6 節）。

## [2026-11-04] 收錄 | 美股官方文件包（SEC 10-K／10-Q／8-K）
- 美股報告也改成先讀 CI 抓的官方文件（`eqdocs_us`，請求寫 `us:代號`）；11/04 起的美股報告要引用 10-K、10-Q、寫出最近一次財報新聞稿日期（`eqreport.docs_issues_us`）。排程 ⑦ 的①-b 改成台股、美股一起送。改了 `lab/equity-report.md`、`ops/routines.md`（規劃 `docs/lab_eq_docs_plan.md` 第 13 節）。

## [2026-11-04] 收錄 | Paycom 用 SEC 官方文件重做＋美股文件包漏附件修正
- Paycom 重做（買進、316 美元），舊版 9 處錯；第一次抓包漏掉 8/5 財報新聞稿附件卻顯示 🟢 → `eqdocs_us` VER 2 重試＋記 miss＋缺財報新聞稿附件算沒抓到。改了 `lab/equity-report.md`（規劃 `docs/lab_eq_docs_plan.md` 第 13 節）；文件包臨時分支被 Vercel 預覽部署、失敗寄信 → 臨時分支也放兩支 vercel.json，改了 `ops/deploy.md`。另：抓取紀錄被 `.gitignore` 擋住、從沒寫進 main（隔天重試的「連兩天」判斷沒生效）→ 不再忽略該檔。

## [2026-11-04] 收錄 | 策略熔斷（跟大盤比）與改版觀察期：規格、門檻、每天的檢查
- 使用者貼三條交易紀律問能不能用：熔斷改成跟大盤比、拿錢的規則改版新舊並行 63 天、主觀帳戶只當自己的規矩。ksspec VER 1→2（先做有逐日回測的三份），門檻算好，每天 CI 量落後、推播、交易計畫與選股頁顯示。新頁 `lab/killswitch.md`；改了 `ops/daily-update.md`（推播多一種行）。

## [2026-11-04] 收錄 | 策略熔斷那一塊移到交易計畫的警訊底下（修正）
- 第一版放進 `corepage.card`，那張卡已經沒有頁面在用；研究紀錄・交易計畫是 `cfgpage` 組的 → 改成 `cfgpage.ks_html`（警訊底下，樣式同警訊）。改了 `lab/killswitch.md`。

## [2026-11-04] 收錄 | 策略熔斷第 3 段（改版觀察期）暫停
- 使用者：「先這樣好了」。改了 `lab/killswitch.md`（觀察期只有規格、沒有程式擋改版）；規劃第 9 節。

## [2026-11-04] 收錄 | 台指選擇權分頁規劃＋個股報告排程暫停
- 使用者要一個藏起來的選擇權分頁，用同一套架構規劃台指選擇權策略（只做買方、即時停損、只抓大波動），並先暫停個股報告省 token。規劃 `docs/lab_txo_plan.md`（今天週選結算日的真實成交、振幅天數表、規則與限制、證據、O1～O3、風險收益、要決定的事）；資料探針 `scripts/probe_txo.py`、`probe_txo.yml`（只看資料長相，不算成績）。每天 20:47 個股報告排程 enabled=false，改了 `ops/routines.md`、`lab/equity-report.md`（CLAUDE.md 排程搬家同步註明不建）。

## [2026-11-04] 收錄 | 台指選擇權第 1 段：資料層與資料分支 claude/txo-data
- 使用者決定：三條都做、資金保守、入口＝右下角「選」字、盤中提醒之後再說。新頁 `lab/txo.md`；`arm/lab/txodata.py`、`scripts/fetch_txo.py`、`txo_data.yml`（逐筆分 K、日行情 2002 起、5 秒指數 2016 起，寫進資料分支，絕不合併進 main）。改了 `lab/overview.md`；CLAUDE.md 鐵則加 `claude/txo-data`。

## [2026-11-04] 收錄 | Vercel 部署儲存超過免費 10 GB：網頁沒變就不部署
- 使用者截圖 Deployment Storage 10.12 GB / 10 GB。兩支 `vercel.json` 加 `ignoreCommand`（dashboard/ 跟上次成功部署一樣就略過，拿不準一律部署）；`txo_data.yml` 把兩支 vercel.json 放進資料分支；債務帳那一列與 daily.yml 的 shortcut 註解拿掉。改了 `ops/deploy.md`、`lab/txo.md`。

## [2026-11-05] 收錄 | 台指選擇權第 1 段完成：回補跑完
- 回補 236.5 分鐘：日行情 2002-01～2026-11（299 個月）、5 秒指數 2016 起 2,631 天、逐筆 30 天；資料分支約 128 MB。規劃第 15 節；改了 `lab/txo.md`。

## [2026-11-05] 收錄 | 台指選擇權第 2 段：規格 txospec VER 1
- 使用者說繼續。`arm/lab/txospec.py`（O1 結算日順勢、O2 CPI／FOMC 前買跨式、O3 農曆年前與聖誕行情改買權；成本、上限、判定）、`tests/test_txospec.py`，算成績之前 commit；規劃第 16 節、`lab/txo.md`。

## [2026-11-05] 收錄 | 選擇權風險／報酬計算機第 1 段：作戰表資料
- 使用者要計算機自動帶入數字與情境，先做計算機、回測往後排。`arm/lab/txocalc.py`、`scripts/run_txocalc.py`、`txo_data.yml` 寫回 main 的 `data/lab/txo_calc.json`；規劃第 17 節、`lab/txo.md`。

## [2026-11-05] 收錄 | 選擇權計算機第 2 段：x9op.html 與右下角「選」字
- `arm/lab/txopage.py`、`appnav.OP_ENTRY`／`OP_CSS`、gen_fund_dashboard 建頁、三支 workflow add；`tests/test_txopage.py`。改了 `lab/txo.md`、`lab/nav.md`。

## [2026-11-05] 收錄 | 選擇權自我檢查與驗收步驟
- 使用者要先檢查再交給其他模型測。修：作戰表波動率改用隱含指數水準（txocalc VER 2）、停損成本、過期紅字、表格 class 撞名。新增 `docs/lab_txo_test_plan.md`；改了 `lab/txo.md`。

## [2026-11-05] 收錄 | 選擇權第 3 段：O2、O3 日資料回測
- 盤中報價探針結果（規劃 17 節）、使用者改先做日資料；FOMC 排定聲明日（`txoevents`）、`txobt`／`run_txobt`；O2 沒過、O3 過關。改了 `lab/txo.md`。

## [2026-11-05] 收錄 | 盤前作戰圖規劃
- 新增 `docs/lab_premarket_plan.md`（壓力支撐、事實表、風險報酬試算、05:10 夜盤更新、06:35 推播；待使用者決定 D1～D6）。改了 `lab/txo.md`。

## [2026-11-05] 收錄 | 盤前作戰圖第 1、2 段
- 夜盤探針（MIS 盤後、每日行情盤後列都拿得到）；`premkt`／`premkpage`／`fetch_night`／`run_premkt`、三支 workflow 串接、06:35 推播第二行、`txocalc` VER 3。改了 `lab/txo.md`、`ops/daily-update.md`。

## [2026-11-05] 收錄 | 盤前作戰圖第 3 段驗證
- `futday` 回補（台指期日盤＋夜盤 2017-05 起）、premktspec VER 1→2（開盤改 09:01）、`pmval`／`run_pmval`、規劃第 12、13 節。改了 `lab/txo.md`、`lessons.md`（09:00:05 不是開盤水準）。

## [2026-11-05] 收錄 | 盤前戰情頁改版與入口改成「.」
- 選擇權頁改成深色戰情卡＋四張買賣點卡＋互動價位圖（只標驗證過的數字）；`premkt` VER 2；各頁入口改成最底下右邊的「.」。改了 `lab/txo.md`、`lab/nav.md`、`lab/overview.md`。

## [2026-11-05] 收錄 | 作戰表價平找不到履約價的修正
- 晚間自我檢查：11/5 價平 41,550 沒掛牌 → 波動率空、正常波動退回 20 天、兩張卡沒選擇權；`txocalc` VER 4 改用最近的掛牌履約價。改了 `lab/txo.md`。

## [2026-11-09] 收錄 | 面向指標盤查：新項目先驗證過關才算分（heatspec VER 13、heatspec_us VER 6）
- 使用者：「籌碼面應該還要加入融資維持率之類的吧？」→ 21 個新項目（台股 15、美股 6）＋自算台指選擇權隱含波動率（2002 起）＋大額交易人、借券（2012-03 起）、當沖、NFCI、AAII、非農就業的資料；`arm/lab/heatgate.py` 過關判定（a 方向對且成立、b 樣本 8 年、c 資料新、d 面向不變差），存 `data/lab/heat_gate.json`／`heat_us_gate.json`。過關 6 個（台股 B9、B11、C11；美股 T15、S10×2），融資維持率沒過；NFCI 檔停在 4 月（美股頁早寫過，規劃時沒先查）。下游研究全部重跑；順手修 sigage 買進日超過資料最後一天的 IndexError。改了 `lab/heat-tw.md`、`lab/heat-us.md`（規劃 `docs/lab_dims_plan.md` 第 10～13 節）。

## [2026-11-09] 收錄 | 新台幣 11/6 溫度計那筆當 Yahoo 錯誤
- 資料來源比對抓到溫度計新台幣 11/6 33.109 vs 央行 32.768（差 1.03%），使用者決定當 Yahoo 錯：`srccheck.KNOWN_YAHOO_FX`。改了 `lab/signals-quality.md`。

## [2026-11-09] 收錄 | NFCI 接上新資料站、新指標每年 1 月重驗
- NFCI：無頭瀏覽器探針找到芝加哥聯準銀行新資料站 `api.data.chicagofed.org`（一般下載就抓得到），`heatfetch_us.NFCI_URL` 改過去、重抓到 2026-10-30；G9、R11 重驗照樣看不出、不算分。
- 每年 1 月重驗（使用者：「先通知、你說好才換」）：`arm/lab/gatereview.py`、`scripts/run_gate_review.py`、`gate_review.yml`（1/10）；只寫 `data/lab/heat_gate_review.json`，名單有變推播一行、後台列出。試跑看到 C10 多一天資料就過關（卡在門檻邊，`docs/lab_dims_plan.md` 第 14.4～14.5 節）。改了 `lab/heat-tw.md`、`lab/heat-us.md`、`lab/chip-ui.md`、`ops/daily-update.md`。

## [2026-11-09] 收錄 | 新項目過關改看最近 20 天（heatspec VER 14、heatspec_us VER 7）
- 使用者選「改成看最近 20 天」：每一項在最近 20 個交易日各判一次，算分 ≥ 15 天才算（`heatgate.compute_stable`；研究與每年 1 月重驗都用它）。結果只有那斯達克 100 多算 S10 AAII（16 天），情緒籌碼 45 → 41；台股 C10 10 天不算。改了 `lab/heat-tw.md`、`lab/heat-us.md`。

## [2026-11-11] 查詢 | 選股頁與個股卡優化規劃（等決定）
- 使用者：「你的個股頁面績效很差而且版面沒有一個系統性 台美股也沒一致」。新規劃 `docs/lab_stock_page_plan.md`：這波大跌（加權 10/6～11/6 −20%）拿著的股票多數輸大盤（財報驚喜這一輪 −20.5% 對 −6.9%、美股強勢品質股上線兩週 −15.6% 對 −3.2%），警訊與熔斷都沒有動作；選股頁台美、個股卡台美的版面差異清單；五段做法（成績單、策略卡統一、個股卡統一、防守研究、載入瘦身）。還沒改任何頁面與規則。

## [2026-11-11] 收錄 | 選股頁台美同一個骨架（個股頁優化 A 段）
- `arm/lab/pickpage.py`：成績單（`score_box`，同期大盤 `Bench`）、美股「這週要做的事」（`week_rows`／`week_box` 加 mk）、策略卡同一個模板（`_card`、`hold_table`、`todo_table`、`next_box`）；`sxlive.book_curve`（新飆股那本帳每天淨值與大盤）。不改任何策略規則。
- 改了 [選股頁](lab/pick-page.md)；規劃與結果 `docs/lab_stock_page_plan.md` 第 7 節。

## [2026-11-11] 收錄 | 選擇權結算日案例：txospec VER 2（O1 兩個對照、O4 結算均價）
- 使用者上傳「台指週選結算日交易逆向拆解」：A＝O1（VER 1 已寫好、還沒跑）、B＝新的 O4；使用者選兩條都做、O1 加兩個對照。結算價改照期交所算法（13:00～13:25 每 5 秒＋收盤，301 個）。改了 [台指選擇權](lab/txo.md)；規劃 `docs/lab_txo_plan.md` 第 19 節。
- 結果：O1 沒過（樣本外 387 筆平均 −2,247 元、每年都虧）；O4 只列（15 個結算日 1 筆）。另修逐筆整理漏掉假日順延的到期批（`txodata.SHIFT_DAYS`、`--mode rebars`）。

