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
