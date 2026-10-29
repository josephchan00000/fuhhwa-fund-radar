# 新策略候選

> 規格＋程式、三種引擎、用到未來資料的檢查、放進計畫試算、合併通道、使用者的決定。
> 原始資料：CLAUDE.md「新策略候選」段；規劃 `docs/lab_ia_v5_plan.md` 第 6、24 節；程式：`arm/lab/candspec.py`（框架規格 VER 2）
> 最後更新：2026-10-29
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

## 現在怎麼運作

2026-10-24（IA v5 第 5 段）起，使用者（第 13 節 Q4 選 A）：每週找新的策略，先寫規則與程式再回測，配置頁策略表（今在研究紀錄）「候選」分組列出，使用者在對話回「試用／納入／不納入」。怎麼找、推、等結果見[「指令：策略探勘週報」](../ops/strategy-scouting.md)。
- 一條候選＝規格一筆＋程式一支：`config/strategy_candidates.json` 的 `items`（欄位 `candspec.FIELDS`／`PROGRAM`／`NEED_BY`）＋`arm/lab/cands/c###.py`（範本與 `Fin` 在 `arm/lab/cands/__init__.py`；程式的 sha256 寫在規格）。**進 main 之後一個字都不能改**：要改規則或參數＝新的編號、`prev` 指到舊的。資料不夠＝只寫規格＋`need`（「需要資料：…」），不寫程式、不回測。
- 三種引擎，判定和頁面上同一類的策略一樣（`arm/lab/candrun.py`）：
  · 指數型（tw、spx、ixic、ndx、sox；trade／dip／alloc）＝總經策略的 xstrat：程式註冊成 `xstrat.PLUGINS["cand_編號"]`（`Ctx.trades／pos／dip_raw` 先查外掛；沒有外掛時原本的策略結果逐位相同），判定照 xstratspec VER 6，一律 ETF 成本、隔天收盤。
  · 台股個股（per；b＝L 大型、M 中型）＝回測方法 v3 的長歷史面板 `bt3d.Panel`＋`bt3.account`；程式回傳每個形成日的分數（`rows`），財報與月營收一律經過 `cands.Fin`（`fs_q`＝法定期限已過的最新一季、`rev_ym`＝次月 10 日以後才能用）；判定＝報酬型態（全部、後一半、參數鄰近 ≥ 2/3），另列帳戶年化對加權報酬指數與同一批股票等權。
  · 美股個股（book）＝資料分支的 `ussxqm.context`＋`ussxbook.run`（閒置的錢放現金、海外券商成本；ex 寫檔數與出場）；判定＝年化贏 S&P 500 含息（全部、後一半、參數鄰近 ≥ 2/3）。2010 起照做、2014 起算成績。
  · 頁面說法：過關／部分過關／沒過／次數不夠；另有需要資料、沒算出來、用到未來的資料（`candspec.VERDICT`）。
- 用到未來的資料：兩道檢查（指數型 `peek_index`、台股個股 `peek_tw`；美股面板太大不做）：①資料截在 70%、85%、97% 重算，截點以前的部位／交易／訊號／名單要和完整資料一模一樣；②（VER 2）檢查日（那一天、之後最近的月底與週末；台股＝最近的形成日）以後的價格、量、市值乘上亂數，檢查日以前就決定好的要一模一樣。沒過＝判「用到未來的資料」、不判定；**新候選沒過就不合併**。
- 放進計畫試算（只描述，不影響判定）：台股＝★ 那一半平分給 N＋1 條（N＝`data/lab/sig_stock.json` 判定 good 的個股策略條數，讀不到＝3）；美股＝機動一半照原本（強勢品質股判定過＝它，否則指數）、一半這條；三條（100 萬較多、前後兩半都不少、最慘最多深 10 點）都過＝「有幫助」。台股的「現在」重算要能重現研究檔的計畫（`tw_plan_parts`，實測 100 萬 → 1,307.2 萬逐位相同）。
- 合併通道 `.github/workflows/strategy_cands.yml`：push 到 `claude/**` 而且動到規格、`arm/lab/cands/**` 或 `config/strategy_board.json` 就跑——從那個分支只拿規格、`c###.py`、board 的 `cand` 一段（其他欄位照 main），用 main 的 `run_cands.py --merge-from`＋`tests/test_cands.py` 驗（舊的一字不差、新的最多 2 條、還沒決定的最多 10 條、sha 對、決定的格式對；分支比 main 舊時 main 上有、分支沒有的候選照留，決定逐條併、日期新的贏——舊分支推上來不會洗掉較新的候選或決定）→ 回測新的（有美股的另外 sparse checkout 資料分支）→ 新候選乾淨地算完才 commit 進 main（規格、程式、結果、決定同一筆）→ 派 daily.yml 重建。每週日台北 19:00 排程：試用中的補紀錄、沒結果的補算。main 上還沒有機制時（`scripts/run_cands.py` 不在）整輪略過。**分支改不了規則**：檢查程式一律用 main 的。
- 使用者的決定＝`config/strategy_board.json` 的 `cand`（`{編號: {dec: trial|adopt|reject, d, why}}`），也走同一條通道進 main（board.json 原本沒有自動通道，只能 PR）。狀態：沒決定＝候選、試用與納入＝觀察中、不納入＝淘汰（`candspec.DEC_STATUS`）。試用＝每週把照做的每天報酬記進 `data/lab/cands_live.json`（只增不改；台股個股用 `v3live.live_panel(Data(long=True))`，長歷史 v3px 平常不更新），滿 63 個交易日才列照做對一直抱著。納入＝「納入，等放上選股頁」，選股頁加上卡片（另外規劃、先問使用者）才改使用中（2026-10-28 前是「等計畫改版」）。
- 頁面（`arm/lab/candpage.py`）：策略表的列（`board.cand_rows` → `candpage.board_rows`：名稱連 `x9r.html#cand-編號`、旁邊「來源」連原文、成績一行＋「放進計畫：100 萬變 X 萬（現在 Y 萬）」、今天＝「過關，等你決定」「試用中・記了 N 天」…；照主頁面用字）；研究紀錄頁「策略候選」一段（`#cand`：總表＋每條一張卡：來源、為什麼挑、規則與參數、判定依據、放進計畫試算、試用紀錄、決定）；從策略表點進來（`x9r.html#cand-c001`）會打開那張卡並捲過去（`research_page.OPEN_JS`，2026-10-24 起；任何 `#段落 id` 都適用，`#s=` 等帶 = 的照舊給全部指標）。06:35 推播：第一次有結果的候選多一行「策略候選：新增 X（市場），過去成績…；回「試用／納入／不納入」。」（`valog.cand_state`／`cand_line`，對前一個資料日的編號比；還沒決定的第一次到 10 條時同一行寫「週報先停」）。
- 測試：`tests/test_candspec.py`（規格鎖定）、`tests/test_cands.py`（格式、合併、只拿那三個地方、外掛結果等於內建、兩道檢查抓得到偷看、計畫試算、試用只增不改、workflow 內容）、`tests/test_candpage.py`（列、白話、研究卡、推播一行）。

## 踩過的坑

- 只做①抓不到「每月換股、偷看 5 天後收盤」的程式（截點前面剛好沒有換股日；寫測試時實測），所以 VER 2 加②。
