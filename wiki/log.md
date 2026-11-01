# 知識庫日誌

> 只往後加，新的寫在最下面。格式：`## [YYYY-MM-DD] 動作 | 標題`；動作＝搬家／收錄／整理／查詢。

## [2026-10-29] 搬家 | 第一段：CLAUDE.md 逐字切成 62 頁

- 來源：CLAUDE.md（main `75d3601e0` 那一版，3,976 行、29.5 萬字）。每一行只落在一頁，`python3 scripts/wiki_split.py --check` 驗證接回去一字不差（檔案標題那一行只留在 CLAUDE.md）。
- 使用者的決定（2026-10-29）：先逐字搬、再整理；CLAUDE.md 先照舊，確定知識庫沒問題再處理；做完事順手改頁面，使用者說「整理知識庫」時才做完整整理。
- 這段期間 CLAUDE.md 是正本：改了 CLAUDE.md 就重跑 `python3 scripts/wiki_split.py`，`tests/test_wiki.py` 會擋兩邊不一致。
- 規劃：`docs/llm_wiki_plan.md`。

## [2026-10-29] 收錄 | 交易計畫與今年逐月表改看 N8

- CLAUDE.md 三處新增（交易計畫 VER 5、飆股前瞻記錄 VER 5＋頁面帳本還原兩次的坑、今年逐月表 ytdspec VER 2），重跑 `scripts/wiki_split.py`：內容進 `lab/core-plan.md`、`lab/boom-live.md`、`lab/cfg-research.md`，其他頁只有行號標記移動。

## [2026-10-29] 整理 | 第二段：ops、env、main 三個資料夾

- 25 頁照第 3.3 節的格式重寫（現在怎麼運作 → 不能改的規則 → 踩過的坑 → 歷史），拿掉逐字切片的行號標記；拆出 7 頁：
  `ops/news-rules-scope`、`ops/news-rules-depth`、`ops/news-rules-style`、`ops/news-rules-numbers`、`ops/routines-prompts`、`main/fund-news-social`、`main/etf-holdings-routes`。
- 新寫兩頁：`user.md`（使用者偏好，每條附原話與日期）、`lessons.md`（跨主題的教訓）。
- 事實比對（`python3 scripts/wiki_facts.py`）：CLAUDE.md 那幾段的 2,296 個事實記號（程式碼片段、日期、帶單位的數字、引號裡的字、run 編號、VER）全部還在，不見 0 個；沒有刪任何記號。
- 六段排程 prompt 原文逐行和 CLAUDE.md 比對一字不差。
- 原文前後說法不一致的地方沒有改，列在 `docs/llm_wiki_plan.md` 第 12 節，等確認。
- 目錄改成：整理過的頁，標題與摘要讀頁面自己的第 1、3 行；逐字的 37 頁（lab）照舊由 `scripts/wiki_split.py` 重產。

## [2026-10-29] 整理 | 第三段：lab 資料夾＋第二段縮回原本長度＋CLAUDE.md 11 處過時用字

- lab 37 頁照第 3.3 節重寫；`lab/signals-versions.md` 原本 2 萬字，拆出 `lab/signals-versions-early.md`（VER 1～16）。
- 第二段變長的頁縮回去：拆頁併回原頁（`ops/news-rules` 四個細則頁、`ops/routines-prompts`、`main/fund-news-social`、`main/etf-holdings-routes`），
  整個知識庫的內文比逐字版多 5.6%（多的是每頁開頭四行），第二段結束時是多 35%。
- CLAUDE.md 第二段列的 11 處前後不一致，逐條對程式查證後改用字（規則、門檻、步驟編號、排程 prompt 都沒動），對應的頁同步改。
- 使用者 2026-10-29：「一些沒用或是明顯被覆蓋的規則可以清除，但我上面提到的大原則絕不要忘記」。只刪原文寫明已被取代的，每條帶走的記號如下：
- 刪：`xstratpage.today_line`——舊訊號總覽 x9o.html 卡片底下的總經策略那一行；x9o.html 2026-10-23 起轉址，市場頁段寫「`xstratpage.board／chip／summary／summary_line／today_line` 一併刪掉」。
- 刪：`heatviz._tz_orig`、`1個月・原本看3個月`——VER 15「溫度計另外算進去的」區的標示；原文寫 VER 21 起該區拿掉。
- 刪：`thermocal.vote(R,cells,H,x)`、`ktab(yk,那一年)`——VER 21「過去讀數這樣的時候」改用 sigoos 格子投票；VER 23 原文寫「`thermocal.vote(R)` 只吃統計、不再用 sigoos 的格子」。
- 刪：`.tzst`、`sigpage.today_html`、`今天有效的訊號`——VER 21 今天的重點裡的總經策略小區、舊訊號總覽的「今天有效的訊號」；市場頁段寫這兩個都已刪掉。

## [2026-10-29] 整理 | 第四段：路徑規則、體檢、「整理知識庫」指令、程式註解

- 18 份路徑規則 `.claude/rules/*.md`：讀到那幾支程式時自動載入，寫先讀哪一頁＋2～5 條不能改的規則（每份 ≤1,500 字，平常不載入）。
- `scripts/wiki_lint.py`（只讀體檢）；CLAUDE.md 加「指令：整理知識庫」，對應新頁 [指令「整理知識庫」](ops/wiki-maintenance.md)。
- 11 處程式註解由「見 CLAUDE.md」改成指向知識庫的頁；`config/index_reviews.json` 的 note 改了會觸發 daily.yml 整輪重跑，留到第 5 段。
- 9 頁原本只有目錄連到，補了頁間連結；`ops/news-rules` 的「生效條件＝排程搬家」補一句現況（指到排程頁）。

## [2026-10-29] 整理 | 第五段：CLAUDE.md 瘦身（29.9 萬字剩 4.2 萬字）

- 使用者選 A：五個指令（全部更新、ETF 募集週掃、策略探勘週報、整理知識庫、排程搬家＋六個排程原文）與 -32003 那一條一字不改；
  加開頭一段、知識庫用法（`@wiki/index.md` 把目錄一起載入）、鐵則 22 條；其他段落搬走，那些頁從此就是正本。
- 指令裡 7 處「見下方…專節」指到已搬走的段落，改成指到知識庫的頁（只換位置說法，規則與步驟沒動）。
- 瘦身前用全文最後比一次：63 頁、7,175 個事實記號，不見 0 個。瘦身前全文 `git show d6ed51029:CLAUDE.md`。
- `scripts/wiki_split.py` 只產目錄與切點；`scripts/wiki_facts.py` 只比 CLAUDE.md 留著的段落（8 頁）；各頁開頭改寫「正本就是這一頁」或「CLAUDE.md 仍留著對應的指令段落」。
- `wiki/user.md` 指使用者的「他」改成「使用者」（原話照舊）。

## [2026-10-29] 整理 | 第一次「整理知識庫」：目錄加頁名對照、8 處把舊頁名當現在寫的地方

- 體檢錯 0、提醒 0；事實比對 8 頁、653 個記號不見 0。上次整理（第三段）之後沒有功能程式改動，只有 CI 的資料更新。
- 掃「現在怎麼運作」「不能改的規則」兩節裡的舊頁名（配置頁、機會頁、策略頁、訊號總覽、泡沫頁、景氣頁）96 行：多數是歷史說法或程式內部名稱，不動；
  目錄開頭加一行頁名對照，一次說清楚舊名對到哪裡（每個對話都會讀到）。
- 改了把舊頁名當成現在的地方：全部策略表在研究紀錄（[台指期早盤](lab/fut.md)、[少見策略](lab/rare.md)）、名詞與查公司在選股頁（[導覽](lab/nav.md)）、
  主頁面用字的兩處例外（[主頁面用字](lab/plain-words.md)）、研究結論在研究紀錄頁（[研究結論](lab/practical.md)）、美股簡介是頁面上取「；」前那一段（CLAUDE.md 9⑤ 與[全部更新](ops/daily-update.md)同步改）。
- 沒有需要使用者決定的矛盾。

## [2026-10-29] 收錄 | 個股深度報告與產業報告
- 新頁 [個股深度報告與產業報告](lab/equity-report.md)；[內容鐵則](ops/content-rules.md) 的「目標價」例外由兩個變三個（個股報告）；CLAUDE.md 鐵則那一行同步改。
- 路徑規則 `.claude/rules/equity.md`。

## [2026-10-29] 收錄 | 個股報告接上網站
- [個股深度報告與產業報告](lab/equity-report.md)：網站入口（研究紀錄頁清單、三種卡片的連結）、建頁、`daily.yml` 併檔通道、VER 2 待決定。
- [內容鐵則](ops/content-rules.md) 第三個例外的位置多了研究紀錄頁的報告清單；路徑規則 `.claude/rules/equity.md` 加回 `reports/eq/**`。

## [2026-10-30] 收錄 | 個股報告評等規格第 2 版（不混口徑）
- [個股深度報告與產業報告](lab/equity-report.md)：使用者「我不要失真的數據」→ eqspec VER 2（倍數和 EPS 同一把尺、不自己預估）；臻鼎-KY 新一版減碼 410 元，舊版留作評等歷史。


## [2026-10-30] 收錄 | 個股報告美股版（規格第 3 版）與每週名單
- [個股深度報告與產業報告](lab/equity-report.md)：美股資料包與頁面、近四季淨利 ÷ 最新股數、每週名單 eq_queue；同業中位數與倍數範圍同一個排除規則、估值圖只畫實際用的那把尺。

## [2026-10-30] 收錄 | 行事曆「待更新」與週末上週結果（補值規劃第一段）
- [行事曆與資料可信度](main/calendar.md)：結束日已過仍未公布＝待更新（網頁、列印、首頁章）；週末版保留上週五與上週未公布的列、網頁收合在最下面；`_check_calendar_lastweek`；規劃 `docs/macrocal_fill_plan.md`。

## [2026-10-30] 收錄 | 行事曆官方自動補值（補值規劃第二段）
- [行事曆與資料可信度](main/calendar.md)：`arm/calfill.py`（六種列、只補空白、不同只加「官方核對」）、CI 兩支接上、公布日重抓（`heatdata.waiting`）。

## [2026-10-30] 收錄 | 資安檢查的低風險修補
- [「全部更新」每日 SOP](ops/daily-update.md)：daily.yml 新聞併檔只收一般檔（擋符號連結把 runner 的檔印上網頁）；網頁外部連結（即將登場、基金月報、基金新聞、社群）一律過 `_safe_url`。高、中風險兩項待使用者決定（舊歷史經 PR 參照仍公開；`claude/**` 分支的程式能帶著密鑰執行）。

## [2026-10-30] 收錄 | 行事曆已過公布時間必補（補值規劃第四段）
- [行事曆與資料可信度](main/calendar.md)：提示包逐列列出已過公布時間還空白的列（`macronews.late_block`）、`_check_calendar_late`（10/31 起）、景氣燈號前值核對（`calfill._ndc_prev`）；每日 SOP 步驟 2、3 補一句（[每日 SOP](ops/daily-update.md)、[新聞規則](ops/news-rules.md)）。

## [2026-10-30] 收錄 | 行事曆官方補值第三段（多接官方來源）
- [行事曆與資料可信度](main/calendar.md)：勞工統計局非農、時薪、季調 CPI、PPI、JOLTS、ECI，歐洲央行決議，主計總處 GDP 年增（`arm/calsrc.py`，有列在等才抓）；初領失業金、台灣出口、零售銷售不接（原因寫在頁上）。

## [2026-10-30] 收錄 | 台股推薦架構第一段（買不買只看策略自己的規則）
- [選股頁](lab/pick-page.md)：新飆股名單拿掉書上的位置與參考買點、加「為什麼不等買點」、位置圖改成上名單週數×強度、原本的飆股名單移到研究紀錄、台股頁最上面「這週要做的事」；推薦架構寫進「不能改的規則」。
- [飆股修正與新飆股前瞻記錄](lab/boom-live.md)：`sxlive.pick_state` 不再算書上的買點與原本的名單。

## [2026-10-30] 收錄 | 新飆股到條件才買（W11）規格 VER 1
- `arm/lab/sxentryspec.py`（`tests/test_sxentryspec.py` 鎖住）、規劃 `docs/lab_pick_arch_plan.md` 第 7 節：E0 現在、E1 開低、E2 拉回 10 日線下、E3 創 20 日新高、E4 一半一半；算報酬之前 commit。

## [2026-10-30] 收錄 | 新飆股到條件才買（W11）結果：不換
- [飆股修正與新飆股前瞻記錄](lab/boom-live.md) 歷史一行；規劃 `docs/lab_pick_arch_plan.md` 第 8 節；`tw-superstock-lab/reports/W11_results.*`。

## [2026-10-30] 收錄 | 個股報告每週名單讀錯新飆股的欄位（已修）
- [個股深度報告與產業報告](lab/equity-report.md) 踩過的坑一行：`eqqueue.candidates` 改讀列的最後一欄；測試改用 `pickpage.boom_box` 產的列。

## [2026-10-30] 收錄 | 個股報告申請收件匣（第一段）
- [個股深度報告與產業報告](lab/equity-report.md) 現在怎麼運作、不能改的規則各一條；路徑提醒 `.claude/rules/equity.md` 加兩個檔；規劃 `docs/lab_eq_request_plan.md` 第 7 節。

## [2026-10-30] 收錄 | 個股報告申請第二、三段：網頁按鈕、每天晚上的名單、⑦ 改每天 20:47
- [個股深度報告與產業報告](lab/equity-report.md) 每天晚上的名單、網頁上的申請；[排程](ops/routines.md) ⑦ 名稱、cron、原文；[時點地圖](ops/schedule.md) 20:47 一行。

## [2026-10-30] 收錄 | 寬度與深度規格 VER 1（第一段）
- `arm/lab/breadthspec.py`（`tests/test_breadthspec.py` 鎖住）、規劃 `docs/lab_breadth_plan.md` 第 9 節：股票層級只當訊號、產業層級當泡沫參考讀數＋美國 48 產業 1931 起驗證；算之前 commit。

## [2026-10-30] 收錄 | 寬度與深度第二段結果
- 規劃 `docs/lab_breadth_plan.md` 第 10 節（`arm/lab/breadth.py`、`scripts/run_breadth.py` → `data/lab/breadth_research.json`）：股票層級警示 0／78 過、偏多 ★ 10 ◆ 10（多半只比平常多 1～2 個百分點）；美國 48 細產業泡沫寬度、深度 ①② 都沒過 → 只當參考讀數；頁面與訊號總覽還沒動。

## [2026-10-30] 收錄 | 寬度與深度第三段：接進訊號總覽（sigspec VER 25）＋市場頁泡沫一行＋研究紀錄圖表
- sigspec VER 25 第 4.15 節（`bd` 只當訊號、進溫度計與預估之後；RES_VER 不改、FWD_VER／CAL_VER 25）；台股讀數 CI 存 `data/lab/heat/bdepth`（`heatfetch.bdepth_update`）；三個研究檔重跑，原本 1,920 列整列一樣（同一份資料比對）。
- 市場頁泡沫那一塊「產業過熱有多廣（參考）」、研究紀錄頁「產業過熱有多廣」四張歷史圖與驗證表；改了 `lab/signals.md`、`lab/signals-versions.md`、`lab/bubble-industry.md`、`lab/market-page.md`。

## [2026-10-30] 收錄 | 新飆股名單位置圖拿掉，改成 8 格＋照規則排隊
- 使用者：「你那個圖超爛我完全看不懂 重新設計詳細規劃後執行」。規劃 `docs/lab_pick_arch_plan.md` 第 9 節；`pickpage.boom_box` 多帶 hold、JS `pkSlots`／`pkBxDraw` 改寫、`pkSpot` 與三個篩選鈕拿掉；不改規則、不重算。改了 `lab/pick-page.md`。

## [2026-10-30] 收錄 | 個股報告官方文件包第一段（CI 抓觀測站文件）
- 使用者看到排程回報「三家都沒讀到公司法說會簡報或觀測站原文」：「這不應該發生吧？」。規劃 `docs/lab_eq_docs_plan.md`（D1 不存、D2 隔天重試、D3 全部重做）；`arm/lab/eqdocs.py`、`scripts/fetch_eqdocs.py`、`scripts/eq_docs_req.py`、`eq_docs.yml`（臨時分支 `claude/eqdocs-tmp/`）；騰雲、暉盛-創、德宏實抓全成功（第 11 節）。報告與檢查怎麼用是第二段。改了 `lab/equity-report.md`。

## [2026-10-30] 收錄 | 文件包臨時分支改由 CI 每天刪
- 容器刪不了別的分支（`git push --delete` 回 403）→ `eq_docs.yml` 加每天台北 03:23 的 schedule，只刪請求日期在今天以前的臨時分支；`eq_docs_req.py --drop` 只試一次。改了 `lab/equity-report.md`、`ops/schedule.md`。

## [2026-10-31] 收錄 | 個股報告官方文件包第二段（報告怎麼用、檢查怎麼擋）
- 規劃 `docs/lab_eq_docs_plan.md` 第 12 節：技能步驟 0／1／3、`eqreport.docs_issues`（2026-10-31 起的台股報告）、`data/eq_docs_log.json` 與 `eqdocs.d2`（隔天重試）、`eqpage.docs_box`、Routine ⑦ prompt。改了 `lab/equity-report.md`、`ops/routines.md`。

## [2026-10-31] 收錄 | 計算正確性核對 A-1（第二套算法＋截斷重建）
- `arm/lab/sigverify.py`、`arm/lab/truncheck.py`、`scripts/run_verify.py` → `data/lab/verify_status.json`；第二套 1,896 個訊號 0 不同，截斷只找到美國 CPI 補缺月偷看（18 條），另查到停擺延後公布、週訊號週中暫定。改了 `lab/heat-us.md`、`lab/heat-tw.md`、`lessons.md`（規劃 `docs/lab_signal_quality_plan.md` 第 9 節）。

## [2026-10-31] 收錄 | 計算正確性 A-1b、A-2（第二套補齊、停擺公布日修正、週訊號等那一週過完）
- 第二套算法補齊研究列、大跌後買點、逐年檢查、溫度計、產業泡沫、型態類技術事件，全部 0 不同；heatspec VER 11、heatspec_us VER 4（補出來的月份等缺口後第一個月、停擺照官方日期、用前月 CPI 的項目同樣），判定 0 個改變；週訊號改用 `heatpos.done_week_ends`。改了 `lab/heat-us.md`、`lab/heat-tw.md`、`lessons.md`（規劃第 10 節）。

## [2026-10-31] 收錄 | 計算核對每週自動跑（A-3a）
- 新增 `.github/workflows/verify.yml`（週六 13:17 跑 `scripts/run_verify.py`、commit `data/lab/verify_status.json`）；不一致時市場頁與研究紀錄頁紅字、後台列例子、推播多一行，過期只推播，不擋發佈。改了 `lab/chip-ui.md`、`ops/schedule.md`、`ops/daily-update.md`（9⑨ 多一行）與 CLAUDE.md 9⑨（規劃第 11 節）。

## [2026-10-31] 收錄 | 資料來源比對（A-3c）與手算固定案例（A-3d）
- `arm/lab/srccheck.py`（法人與融資 FinMind vs 證交所、美債財政部 vs H.15、加權指數 Yahoo vs 證交所／國發會、指數 vs ETF、單日跳動；約 12 萬筆 0 不一致）接進每週核對；`tests/test_golden.py`（歷史收盤值、自營商連 10 天、年線事件）。改了 `lab/chip-ui.md`、`lab/heat-tw.md`（規劃第 11.3、11.4 節）。

## [2026-10-31] 收錄 | 月／季資料照官方實際公布日（A-3b）
- heatspec VER 12、heatspec_us VER 5、bubspec VER 5（含兩次算結果之前的補充）：美國 CPI、就業報告、Z.1 照官方實際公布日（`arm/lab/reldates.py`、`scripts/fetch_reldates.py`，每週跟 `verify.yml` 更新），沒有官方日期的年份照同月份歷年最晚；GDP、企業獲利停擺改期；台灣月資料改保守時程；月營收照申報期限。邊際變化（`heatpos`、`heatreg`）與 CAPE 參考讀數補上實際拿得到的日子；截斷重建也比邊際變化、加 6 個核對日。改了 `lab/heat-tw.md`、`lab/heat-us.md`、`lab/bubble.md`、`lab/chip-ui.md`、`ops/schedule.md`、`lessons.md`（規劃第 11.2 節）。
- 截斷重建新核對日 2026-04-02 查到週訊號的週末在週五休市那一週回測比網頁早一天 → `heatpos.done_week_ends` 與第二套 `sigverify._done_weeks` 改照官方休市表（`market_closed`）；研究檔不變。改了 `lab/chip-ui.md`、`lessons.md`。

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
