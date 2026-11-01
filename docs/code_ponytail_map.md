# 程式地圖（ponytail 第一段，2026-11-01，只讀）

> `docs/code_ponytail_plan.md` 第 4 節第 1 段的結果：誰會跑程式、用到哪些模組、資料從哪來、寫到哪裡、哪些沒人用。
> 全部是讀出來的，**沒有改任何程式**。第二段（體檢）照這份地圖找問題。看的是 main `bfca89a04`（PR #424 合併、CI 建頁之後）。
> 算法：workflow 用 YAML 解析每一步的指令（含它呼叫的 `.sh`）；模組關係用 Python 語法樹找 import（含函式裡的 import 與動態載入）；
> 沒人用的函式用 vulture（60% 以上）再全專案搜尋確認；寫檔用語法樹找寫入呼叫。分析用的暫存程式不放進專案。

## 1. 規模

| 區 | 檔數 | 行數 |
|---|---|---|
| `arm/`（不含 lab） | 75 | 約 2.1 萬 |
| `arm/lab/`（籌碼雷達與研究） | 186 | 約 8.5 萬 |
| `scripts/` | 98 支 Python＋7 支 shell | 約 1.1 萬 |
| `tests/` | 200 | 約 4 萬（2,272 個測試） |
| `tw-superstock-lab/`（飆股研究，自己的 CLAUDE.md） | 58 | 約 1.1 萬 |

預期負載：一個人用、實際約 30 人看的研究與儀表板網站，加上每天十幾班 CI。重點是**算對、資料不丟、CI 不壞、頁面不壞**，不是同時很多人用。

## 2. 入口：誰會跑程式

### 2.1 GitHub Actions（14 支）

| workflow | 怎麼觸發 | 台北時間 | 跑幾支腳本 | 寫回 main |
|---|---|---|---|---|
| daily.yml | 排程、push `reports/**` 等四類檔、手動 | 週一～六 07:15（排程會話 06:35 推報告也會觸發） | 24（含 `daily_fund.sh` 叫的） | dashboard、data、config、reports |
| afterhours_refresh.yml | 排程、push `.ping/afterhours`、手動 | 週一～五 15:40、19:10、22:05 | 17 | dashboard、data、reports |
| etf_holdings.yml | 排程、手動 | 每天 17:40、06:15 | 6 | dashboard、data |
| fut_preopen.yml | 排程、手動 | 週一～五 03:47～07:17 五班 | 1 | data/lab |
| eq_docs.yml | 排程、push `.ping/eqdocs`、手動 | 每天 03:23 | 1 | 不寫 main：文件包推到暫存分支 `claude/eqdocs-tmp/…`，過期自動刪 |
| eq_inbox.yml | issue、排程、手動 | 每天 22:23 | 1 | data |
| strategy_cands.yml | push 候選三類檔、排程、手動 | 週日 19:00 | 2＋pytest | arm/lab/cands、config、data/lab |
| lab_opt.yml | 排程、手動 | 週一 08:30 | 2 | data/lab |
| ussx_weekly.yml | 排程、手動 | 週六 10:05 | 4 | data/lab |
| verify.yml | 排程、手動 | 週六 13:17 | 2 | data/lab |
| lab_backfill.yml | push `.ping/lab`、手動 | — | 19（一次性回補） | data、data/lab |
| superstock.yml | push `.ping/superstock`、手動 | — | 2 | reports |
| probe_fund_ids.yml、probe_nav_history.yml | 只有手動 | — | 各 1 | 不寫回 |

只有 `daily.yml` 透過 shell 再叫腳本（`scripts/daily_fund.sh`）；其他 shell（`daily_routine.sh`、`daily_run.sh`、`publish*.sh`、`install_schedule.sh`）沒有 workflow 在跑，見 2.3。

### 2.2 排程、指令、技能

- 7 個排程（CLAUDE.md 原文①～⑦）與 5 個指令（全部更新、ETF 募集週掃、策略探勘週報、整理知識庫、排程搬家）用到：
  `gen_usnews.py`、`gen_twnews.py`、`gen_macronews.py`、`check_reports.py`、`check_holdings_intro.py`、`check_numbers.py`、`gen_fund_dashboard.py`、
  `run_cands.py`、`eq_queue.py`、`eq_facts.py`、`check_eq.py`、`eq_build.py`、`eq_docs_req.py`、`wiki_split.py`、`wiki_lint.py`、`wiki_facts.py` 等。
- 技能 `.claude/skills/equity-report/` 與路徑規則 `.claude/rules/*.md` 另外提到幾支研究程式（`run_core.py`、`run_thermo.py`、`run_bt3.py`…）。

### 2.3 98 支腳本的分類

| 類 | 支數 | 說明 |
|---|---|---|
| CI 會跑 | 50 | workflow 或 `daily_fund.sh` 直接跑 |
| 排程／指令／技能／路徑規則提到 | 17 | 主會話或排程會話照指令跑 |
| 手動研究 | 20 | 文件或知識庫寫怎麼跑（`run_sig.py`、`run_sigage.py`、`run_robust.py`、`run_decay.py`、`run_ema.py`、`run_tilt.py`、`run_xs.py`…），重跑研究檔用 |
| **舊的本機流程** | 10 | 見下面 |
| 備援 | 1 | `fetch_etf_holdings_browser.py`（知識庫寫「保留為備援、不排程」） |

**舊的本機流程（2026-06 以前的 M1～M7）**：`daily_routine.sh`、`daily_run.sh`、`publish.sh`、`publish_public.sh`、`publish_vercel.sh`、`install_schedule.sh`
→ `run_daily.py`、`gen_copy.py`、`gen_dashboard.py`、`fetch_fast.py`、`fetch_news.py`、`fetch_peers.py`、`fetch_etfinfo.py`、`backfill_nav.py`、`vercel_publish.py`、`cf_publish.py`。
`docs/SPEC.md` 寫它當時用電腦的 launchd 每個平日 17:40 跑（產「每日想法報告」與四通路文案）；現在的網站由 CI 的 `gen_fund_dashboard.py` 建，**沒有任何 workflow 跑這一套**。

## 3. 模組（`arm/` 261 支）

| | 模組數 | 行數 |
|---|---|---|
| CI、排程、指令用得到 | 229 | — |
| **只有舊的本機流程用** | 21 | 4,148 |
| 只有手動研究用 | 6 | 1,012（`decayspec`、`emaspec`、`sigdecay`、`sigema`、`pos`、`posspec`：研究紀錄要能重跑，留著） |
| 只有 `tw-superstock-lab` 的研究程式用 | 5 | 360（`sepaspec`、`superfixspec`、`sxentryspec`、`sxexitspec`、`sxfixspec`：研究規格，留著） |

- **只有舊流程用的 21 個模組**：`arm/pipeline.py`、`ideas.py`、`signals.py`、`themes.py`、`chips.py`、`peers.py`、`metrics.py`、`attribution.py`、`diff_engine.py`、
  `quality.py`、`navhist.py`、`calendar.py`、`firsthand.py`、`dashboard.py`（舊儀表板，1,042 行）、`arm/copy/`（7 個，文案層）。
  另有 13 支測試有測到它們（`test_copy.py`、`test_dashboard.py`、`test_ideas.py`…，974 行；有幾支也順便測到正式流程的模組，拿掉前要逐一看）。`arm/db.py`（SQLite）也被正式流程的 `connectors/tdcc.py` 用到，不算在內。
- **動態載入（刪東西前要特別小心）**：ETF 連接器 `arm/connectors/*` 用名字載入（`fetch_etf_holdings.py`、`check_new_etfs.py`、`etfwatch.py`）；
  策略候選 `arm/lab/cands/c00X.py` 由 `candrun.py` 用編號載入；測試用檔名載入十幾支腳本（`check_reports.py`、`run_verify.py`…）。

## 4. 沒人用的程式（候選，第二段逐條確認）

- **函式（12 個）**：`connectors/issuers/pcf.py` `fetch_one`、`lab/bubble.py` 與 `lab/bubpage.py` 各一個 `clear_cache`、`bubpage._g_src`、`futsim` 的 `as_dict`、
  `heatpage._strips`、`heatviz.key_html`、`heatviz.items_table`、`pickcal.on_or_after`、`usbreadth.ratio_arrays`；`tw-superstock-lab` 的 `industry_counts`、`stop_first`。
  全專案搜尋（程式、測試、workflow、文件）都沒有別的地方提到。（`cands.rev_ym` 是給候選程式用的介面、`heatpos`／`heatreg` 的模組 `__getattr__` 是 Python 自動呼叫的，不算。）
- **常數與變數**：約 25 個定義了沒用到（例 `thermocal.SIDES`、`page.SLUG`、`tilt.LIVE_MIN_DAYS`）。
- **沒用到的 import**：pyflakes 報 166 個（另有 10 個 f 字串沒有變數、7 個區域變數沒用到）；其中有些是刻意轉出（例 `heatspec_us` 從 `heatspec` 轉出常數），要逐一看。

## 5. 資料：從哪來、存在哪、往哪去

- **從哪來**：程式裡出現 111 個外部網址，主要是證交所（www、openapi、mis）、櫃買、期交所、公開資訊觀測站、FinMind、Yahoo、SEC、Nasdaq、
  美國政府統計（BLS、DOL、聯準會、費城聯準會、紐約聯準會、CFTC、OFR）、台灣政府統計（主計總處、央行、經濟部、金管會、投信投顧公會）、
  14 家投信的每日持股、YouTube、PTT、Google 新聞、鉅亨。**全部只在 CI 抓**（容器網路擋這些站）。
- **存在哪**：`data/`（基金、ETF、總經、新聞）、`data/lab/`（籌碼雷達的資料與研究檔，很多是 `.json.gz`）、`config/`（人工維護的清單與規則）、`reports/`（新聞與個股報告）；
  美股個股資料在資料分支 `claude/ussx-data`（不合併進 main）。
- **寫檔的地方**：176 處、110 支檔案（`arm/` 19、`arm/lab/` 50、`scripts/` 56、`tw-superstock-lab/` 51）。落檔的 `save()` 有 25 個，各寫各的；
  有「不把非空的落檔覆寫成空」這類保護的在 `fundnews`、`etfwatch`、`etfholdings`、`macrochips`、`fundnav`、`twholidays`、`calfill`、`etfdiscover` 等（第二段逐一核對）。
- **往哪去**：CI 建 `dashboard/*.html`、`*.json` → commit 進 main → 打 Vercel Deploy Hook 部署；推播與研究紀錄頁讀 `data/lab/*.json`。

## 6. 第二段（體檢）要看的重點

照 ponytail 的順序：正確 → 安全 → 撐得住 → 有測試 → 速度 → 精簡。這份地圖已經看到、要在體檢裡確認的：

1. **舊的本機流程**（10 支腳本＋6 支 shell＋21 個模組＋13 支測試，約 6,200 行）：要先確認**你的電腦上還有沒有在跑**（launchd `com.fhtrust.fharm.daily`）。沒在跑才能考慮拿掉；有在跑就留著。
2. **25 個各寫各的 `save()`**：哪些落檔有「非空不覆寫成空」的保護、哪些沒有（鐵則的那一條）。
3. **沒人用的 12 個函式、約 25 個常數、166 個 import**：逐一確認後列成可以刪的清單。
4. 動態載入的三處（ETF 連接器、策略候選、測試載入腳本）：任何改名或刪除都要先看這裡。
