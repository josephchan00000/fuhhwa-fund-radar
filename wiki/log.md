# 知識庫日誌

> 只往後加，新的寫在最下面。格式：`## [YYYY-MM-DD] 動作 | 標題`；動作＝搬家／收錄／整理／查詢。
> 快到 1.5 萬字上限時，把最舊的整月（只剩當月時，搬最早的幾天）一字不改搬到 `docs/wiki_log/YYYY-MM.md`（只讀；裡面的「- 刪：」行 `scripts/wiki_facts.py` 照樣會讀）。2026-10 的在 `docs/wiki_log/2026-10.md`（上次「整理」也在那裡），2026-11-01 的在 `docs/wiki_log/2026-11.md`。

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

## [2026-11-11] 收錄 | 個股卡台美同一組頁籤（個股頁優化 B 段）
- 台股個股卡、公司卡、美股個股卡同一組頁籤與順序；法人預估→分析師、產業比較→同產業；美股補「重點」（`uscardpage.sum_html`）；新飆股補買進時／現在對照（`sxlive.hold_cmp`）。
- 改了 [選股頁](lab/pick-page.md)、[公司分析](lab/company.md)、[研究紀錄](lab/cfg-research.md)、[法人預估](lab/forecast.md)、[內容鐵則](ops/content-rules.md)；結果見規劃第 8 節。

## [2026-11-11] 收錄 | 選擇權結算日案例（txospec VER 2、O1 沒過、O4 只列）
- 使用者上傳結算日案例報告：O1 照 VER 1 跑＋兩個對照、新增 O4；結算價改照期交所算法（301 個平均）。O1 沒過（樣本外每筆 −2,247 元、每年都虧），O4 只列（1 筆）。另修逐筆漏存假日順延的到期批（`txodata.SHIFT_DAYS`）。改了 [台指選擇權](lab/txo.md)；規劃第 19 節。

## [2026-11-11] 收錄 | 個股策略防守研究（defspec VER 1）：三種都沒過
- 規格算結果前 commit；基準重跑三條都和官方對上（新飆股 50.74%、財報驚喜 30.4%、美股 20.15%）。D1 60 日線下不買、D2 同一類最多 2 檔、D3 熔斷 × 1.0 不偷看：9 個判定都沒過，規則不換。結果 `data/lab/def_research.json`、規劃第 11 節。日誌 11-01 那天搬到 `docs/wiki_log/2026-11.md`（只剩 11 月、到上限）。改了 [選股頁](lab/pick-page.md)、[策略熔斷](lab/killswitch.md)。

## [2026-11-11] 收錄 | 選擇權 11/11 案例還原（只是事實）
- 結算價 43,991.65；截圖賣價只在 13:04～13:14 出現，買價最近在 12:56～13:01（13:00 以後 5 分鐘指數漲 156 點）。O1 那天兩次都 5 秒後停損、吃不到那段；O4 沒有符合。日誌 11-01 那天搬到 `docs/wiki_log/2026-11.md`（同防守研究分支）。改了 [台指選擇權](lab/txo.md)；規劃 19.9。

## [2026-11-11] 收錄 | 選股頁載入瘦身（個股頁優化 D 段）
- 台股走勢序列分成十六份 `x9s-{0..f}.json`、開哪一檔才抓那一份（不再預抓 518 KB）；美股個股卡資料另存 `x9uc.json`、開第一張才抓；選股頁壓縮後 653→562 KB。三支 workflow 各自 add、`git add -A` 帶走舊 `x9s.json`。改了 [籌碼雷達總覽](lab/overview.md)、[介面改版](lab/chip-ui.md)、[選股頁](lab/pick-page.md)；規劃第 12 節。

## [2026-11-12] 收錄 | 新 ETF 掛牌日漏填紅章＋05:08 補跑 ETF 持股
- 00418A 已掛牌卻沒進追蹤表（登錄檔沒填掛牌日）→ 補 `list_date`，並加紅章：有代號、募集結束超過 10 天沒掛牌日就提醒。ETF 持股明細一堆「待收盤」（cron 晚跑、美股還沒收）→ 05:08 排程多 dispatch 一次 etf_holdings。改了 [即將登場](main/etf-upcoming.md)、[ETF 持股](main/etf-holdings.md)、[排程](ops/routines.md)。

## [2026-11-12] 收錄 | 選擇權頁分四個分頁、拿掉買賣點卡、選股頁搬進來
- 使用者：選擇權判斷很爛、新策略沒看到、把個股頁挪進選擇權頁。照實檢查 4 天 16 張卡（7 張幾分鐘內停損；價位擋不住、停損太近、開盤估差）→ 拿掉買賣點卡，改放「今天可能走多遠」與最近 10 天成績；新「策略」分頁列 O1～O4；選股頁放進「個股」分頁框裡、頂欄拿掉「選股」；推播不帶壓力支撐。改了 [台指選擇權](lab/txo.md)、[導覽](lab/nav.md)、[選股頁](lab/pick-page.md)、[每日 SOP](ops/daily-update.md)；規劃第 20 節。
