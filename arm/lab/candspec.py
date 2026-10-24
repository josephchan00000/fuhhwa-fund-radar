"""新策略候選的框架規格（docs/lab_ia_v5_plan.md 第 6、24 節）。VER 1、VER 2：2026-10-24 寫定，任何一條候選算出來之前 commit。

使用者 2026-10-23（IA v5 第 13 節 Q4 選 A）：每週一次（台北週日 20:00 的 Routine「策略探勘週報」）找新的策略，
先寫規則與程式 commit，CI 回測，配置頁策略表的「候選」分組列出，使用者在對話回「試用／納入／不納入」。

這支檔寫的是每一條候選都共用的規則：怎麼算、怎麼判、怎麼試算放進計畫、怎麼試用、怎麼合併進 main。
每一條候選自己的規則與參數寫在 config/strategy_candidates.json（一條一筆），程式放 arm/lab/cands/{編號}.py。
這裡要改＝VER＋1、寫進規劃文件第 24 節，不在看過任何候選的結果之後改舊版本。

VER 2（2026-10-24，同一天；還沒有任何候選算出來）：「用到未來的資料」的檢查只靠截資料不夠——每月換股的程式如果偷看幾天後的價格，
  截點前面剛好沒有換股日就抓不到（寫測試時用「看 5 天後收盤」的程式實測抓不到）。另外加「打亂之後的價格」：在每個 CUTS 位置
  附近挑檢查日（指數型＝那一天、最近的月底、最近的週末；台股個股＝最近的形成日），把檢查日以後的價格、量、市值都乘上亂數
  （每天、每檔不同，PEEK_SIGMA、PEEK_SEED），檢查日（含）以前的結果必須一模一樣。截資料那一關照舊。
  合併通道另外寫明：新的候選要乾淨地算完（沒有出錯、沒有用到未來的資料）才合併；沒算完＝這一輪什麼都不合併，
  還沒進 main 的候選可以修好程式再推（分支上的 commit 留著當紀錄；修的是程式錯誤，不是看了成績再調參數）。

一、候選怎麼來（Routine，規劃第 24.4 節）
  來源限：學術（SSRN、arXiv q-fin、期刊）、大型資產管理公司與知名量化部落格（AQR、Alpha Architect、Quantpedia、
  Research Affiliates 等）、台灣投信券商研究報告。每週最多 MAX_NEW 條「規則寫得清楚、有公開成績、現有資料做得出來」的，
  找不到就不湊。還沒決定的候選到 MAX_OPEN 條時，週報先停、提醒使用者清。

二、一條候選＝規格一筆＋程式一支（規劃第 24.2 節）
  規格欄位見 FIELDS／NEED_BY；資料不夠的寫 need（「需要資料：…」），不寫程式、不回測。
  要改規則或參數＝新的編號（prev 指到舊的）；舊的那一筆與程式一個字都不能改（tests/test_cands.py 與合併檢查都會擋）。
  程式只准用到「那一天收盤以前就拿得到」的資料。指數型與台股個股型，CI 會把價格截在 CUTS 三個位置重算，
  截點以前的結果必須和完整資料一模一樣；VER 2 起另外把檢查日以後的價格打亂重算（見上），兩關沒過都判「用到未來的資料」、不判定。
  財報、月營收要用公布期限（packtest.deadline、月營收次月 REV_DAY 日以後）才能用：台股個股一律經過 cands.Fin（只給那一天拿得到的）。

三、三種引擎（判定方式和頁面上同一類的策略一樣）
  index（指數型；市場 tw、spx、ixic、ndx、sox）：總經策略的引擎 xstrat，程式註冊成外掛（trade 型寫 trades、dip 型寫 dip_raw、
    alloc 型寫 pos）。成本、隔天收盤進出、評估起點、參數鄰近、判定（good／ref／none／few）全部照 xstratspec VER 6；
    候選一律照 ETF 成本、隔天收盤（不用台指期、不用當天收盤）。
  tw_stock（台股個股；b＝L 大型股或 M 中型股）：回測方法 v3 的長歷史面板（bt3d.Panel，2013 起）與資金帳戶（bt3.account，
    成本照 bt3：手續費 2.8 折、證交稅、滑價）。程式回傳每個形成日的分數（rows），pick 決定一期買幾檔。
    每一期扣成本後的報酬看報酬型態（bt3.payoff：賺錢的期數 ≥ 60% 而且每月平均 ≥ +1%，或 ≥ 40%、賺賠比 ≥ 2.5、每月平均 ≥ +2%）：
      good＝全部期數過、後一半的期數也過、參數鄰近至少 GRID_OK 的組合（全部期數）也過；ref＝全部期數過；none＝沒過；
      few＝不到 TW_N_MIN 期。
  us_stock（美股個股）：資料分支的美股面板（ussxqm.context）與帳戶引擎（ussxbook.run；閒置的錢放現金、成本照 ussxspec 的海外券商）。
    程式回傳每週的名單（signals）；ex 寫出場與檔數。帳戶從 US_Y0 年第一個交易日的前一天收盤起算、成績從 US_EVAL 年起。
      good＝年化贏 S&P 500 含息、後一半也贏、參數鄰近至少 GRID_OK 的組合也贏；ref＝年化贏；none＝沒贏；few＝不到 US_YEARS_MIN 年。
  頁面的說法（VERDICT）：good 過關、ref 部分過關、none 沒過、few 次數不夠；need 需要資料、err 沒算出來、peek 用到未來的資料。

四、放進計畫試算（只描述，不影響判定；規劃第 24.3 節）
  有交易計畫的市場（PLAN_OF）另算：機動裡多一份給這條候選，和現在的計畫同一段期間比。
    台股：★ 那一半平分給 N＋1 條（N＝現在台股機動裡的 ★ 條數＝data/lab/sig_stock.json 裡有逐筆交易的個股策略判定 good 的條數；
      讀不到＝STAR_N_DEFAULT），新飆股那一半不動；期間、警訊、換現金、成本照 corespec 現在的版本（core.research 的 plan 那一段）。
    美股（spx、ndx）：機動一半照原本（美股強勢品質股判定過＝它，否則指數）、一半這條候選；期間照 ussx_qm.json 的計畫那一段。
    候選每天的報酬：指數型＝有部位的日子拿含息指數、沒有部位拿現金利息、換邊付 ETF 成本；個股型＝帳戶淨值的報酬，
      沒有持股的日子拿現金利息。
  三條：① 100 萬比較多 ② 前半、後半都不比較少 ③ 最慘時跌得不比現在深超過 PLAN_MDD_MORE。三條都過＝「放進計畫有幫助」。

五、決定與試用（規劃第 24.5 節）
  使用者在對話回「試用 X／納入 X／不納入 X」→ 記在 config/strategy_board.json 的 cand（{編號: {dec, d, why}}）。
    試用（trial）＝策略表「觀察中」；決定日之後第一個交易日起，每週把照規則做的每天報酬記下來（data/lab/cands_live.json，只增不改），
      滿 TRIAL_CHECK 個交易日列照做對一直抱著的報酬。
    納入（adopt）＝策略表「觀察中」並寫「納入，等計畫改版」；交易計畫出新版本（corespec VER＋1）才改「使用中」（override）。
    不納入（reject）＝「淘汰」，一句原因。

六、合併進 main（.github/workflows/strategy_cands.yml；規劃第 24.6 節）
  push 到 claude/** 而且動到 config/strategy_candidates.json 或 arm/lab/cands/ 就跑：從那個分支只拿這兩個地方的檔案，
  用 main 上的檢查（scripts/run_cands.py --merge-from、tests/test_cands.py）驗過才合併：JSON 讀得到、欄位齊、
  舊的那幾筆與程式一字不差、新的程式 sha 對得上、沒有刪掉任何一筆、一次最多 MAX_NEW 條新的、還沒決定的不超過 MAX_OPEN 條。
  驗過就算新候選；新的候選乾淨地算完（VER 2）才把規格、程式、結果一起 commit 進 main，再派一輪 daily.yml 重建頁面。
  每週日台北 WEEKLY_HM 另外跑一次（排程）：試用中的候選補紙上成績、還沒算出結果的補算。
"""
from __future__ import annotations

VER = 2
SPEC_DATE = "2026-10-24"

# ── 候選的規格（config/strategy_candidates.json 的 items） ────────────────────────────
ID_RE = r"^c\d{3}$"                      # c001、c002……；改規則＝新的編號
ENGINES = {"index": ("trade", "dip", "alloc"), "tw_stock": ("per",), "us_stock": ("book",)}
ENGINE_NAMES = {"index": "指數型", "tw_stock": "台股個股", "us_stock": "美股個股"}
MARKETS = {"index": ("tw", "spx", "ixic", "ndx", "sox"), "tw_stock": ("tw",), "us_stock": ("us",)}
MK_NAMES = {"tw": "台股", "spx": "S&P 500", "ixic": "那斯達克", "ndx": "那斯達克 100", "sox": "費半", "us": "美股"}
FIELDS = ("id", "found", "name", "mk", "engine", "kind", "how", "src", "why")    # 每一筆都要有
PROGRAM = ("p", "grid", "sha")                                                   # 有程式的（沒有 need）都要有
NEED_BY = {"dip": ("H",), "per": ("b", "pick"), "book": ("ex",)}                  # 依型態另外要有
OPTIONAL = ("prev", "need", "note")
TW_BUCKETS = ("L", "M")
PICK_KEYS = ("top", "nmin", "umin", "asc", "event")
US_EX_KEYS = ("slots", "hold", "ma", "trail", "stop")
GRID_MAX = 9                             # 參數鄰近最多幾組（含原本那一組）
NAME_MAX = 24                            # 名稱最多幾個字

# ── 判定 ─────────────────────────────────────────────────────────────────────
GRID_OK = 2 / 3                          # 參數鄰近至少幾成的組合也要過（同 xstratspec.GRID_OK）
TW_N_MIN = 10                            # 台股個股：至少幾期
US_Y0, US_EVAL = 2010, 2014              # 美股個股：帳戶起點、成績起點（同 ussxspec QM_Y0、QM_EVAL）
US_YEARS_MIN = 5
TIERS = ("good", "ref", "none", "few")
VERDICT = {"good": "過關", "ref": "部分過關", "none": "沒過", "few": "次數不夠",
           "need": "需要資料", "err": "沒算出來", "peek": "用到未來的資料"}
CUTS = (0.70, 0.85, 0.97)                # 用到未來的資料：價格截在日曆的這幾個位置重算
PEEK_SIGMA = 0.08                        # VER 2：檢查日以後的價格乘上 exp(常態亂數 × 這個數)（每天、每檔不同）
PEEK_SEED = 20261024
REV_DAY = 10                             # 月營收：次月 10 日以後才拿得到

# ── 放進計畫試算 ─────────────────────────────────────────────────────────────
PLAN_OF = {"tw": ("tw",), "spx": ("spx",), "ndx": ("ndx",), "us": ("spx", "ndx")}   # 哪幾個市場的候選試算哪個計畫
STAR_N_DEFAULT = 3
PLAN_MDD_MORE = 0.10

# ── 決定與試用 ───────────────────────────────────────────────────────────────
DECISIONS = {"trial": "試用", "adopt": "納入", "reject": "不納入"}
DEC_STATUS = {"trial": "obs", "adopt": "obs", "reject": "out"}                  # 策略表的狀態
TRIAL_CHECK = 63

# ── 週報與合併 ───────────────────────────────────────────────────────────────
MAX_NEW = 2                              # 一次（一週）最多幾條新的
MAX_OPEN = 10                            # 還沒決定的最多幾條
WEEKLY_HM = "19:00"                      # 每週日台北（strategy_cands.yml 的排程；Routine 是 20:00）
ROUTINE_HM = "20:00"
SPEC_FILE = "config/strategy_candidates.json"
PROG_DIR = "arm/lab/cands"
RES_FILE = "cands_research.json"         # data/lab/
LIVE_FILE = "cands_live.json"            # data/lab/
