# CLAUDE.md — 復華基金雷達 · 給 Claude 的操作規則

## 指令：「全部更新」／「資料更新」

使用者只要打**「全部更新」**（或「資料更新」），第一時間直接執行完整每日更新流程，不要再詢問：

1. **抓資料**（失敗照防呆規則降級，勿中斷）：
   - `TZ=Asia/Taipei python3 scripts/fetch_holdings.py`（NAV／持股快照）
   - `TZ=Asia/Taipei python3 scripts/fetch_fund_news.py`（基金新聞・社群）
   - `TZ=Asia/Taipei python3 scripts/fetch_etf_watch.py`（ETF 數據追蹤分頁；etfinfo.tw 被 proxy 擋時
     自動沿用既有 `data/etf_watch.json`，CI 會補抓）
2. **產提示包**：`TZ=Asia/Taipei python3 scripts/gen_usnews.py && TZ=Asia/Taipei python3 scripts/gen_twnews.py && TZ=Asia/Taipei python3 scripts/gen_macronews.py`
3. **上網查證產新聞內容**（純 Python 不杜撰新聞，此步由 Claude 用 WebSearch 補；可派平行子代理，各自嚴守提示包版型）：
   - `reports/usnews/{今日}_v1.md`、`_v2.md`（昨夜美股；先查證美股當日是否休市）
   - `reports/twnews/{今日}.md`（台股；週末/休市日改寫最近交易日並註明）
   - `reports/macronews/{今日}.md`、`reports/macrocal/{今日}.md`（總經政策＋本週行事曆；
     行事曆涵蓋**美國＋歐盟＋中國＋日本**重點數據與**重要企業財報／法說**，項目加「美：／歐：／中：／日：／財報：」前綴）
   - **週末合併時窗**（提示包會自動帶入 `usnews.weekend_note()`）：週六涵蓋週五晚間起、週日再含週六、
     **週一須把週五晚間＋週六＋週日整個週末最重要的新聞一次綜合整理**，不可只看最近一天。
   - 不重複收錄前一日已報導的舊聞；有新進展標【延伸】。每卡至少 1 條真實可點 [標題](URL)。
   - **深度報告精選保底 1 篇**（台股與美股報告各自保底；標題括注用【深度】）：台股從經濟日報／
     工商時報／中央社專題／財訊・今周刊挑；美股從富途牛牛深度文、Reuters Analysis／Bloomberg
     深度專題挑。只挑真深度（產業鏈拆解/商業模式/政策影響），當日不足放寬到近 3 天並註明刊出日。
4. **合規掃描**：`gen_usnews.py --check`、`gen_twnews.py --check`、`gen_macronews.py --check` 全須 🟢。
5. **重建儀表板**：`TZ=Asia/Taipei python3 scripts/gen_fund_dashboard.py`，並確認「🕒 資料更新時間」區塊各欄位已更新。
6. **測試**：`python3 -m pytest -q` 全綠。
7. **commit＋push** 到本次會話指定分支（訊息用 `chore: 每日持股介紹／新聞更新 {日期}` 或依變更內容）。
8. **合併上線（使用者已預先授權，不必再問）**：開 PR 後**立即 merge 進 main**——「全部更新」的完成定義是
   **網頁（Vercel）真的更新**，不是只開 PR。merge 前先把 main 併進分支解衝突（`dashboard/index.html`
   衝突一律重跑 `gen_fund_dashboard.py` 重產解決）。
9. **確認部署**：Vercel 跟著 main 自動部署；為保險起見（bot 身分的 merge commit 可能不觸發 Vercel），
   merge 後手動觸發一次 `daily.yml` 的 `workflow_dispatch`——CI 會以擁有者身分 commit 重產的儀表板，
   確保 Vercel 一定部署最新版。

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
- **新聞來源黑名單**：排除「富聯網」（moneylink）。
- **禁用詞**（正文不得出現，機構觀點也要改寫避開）：保證、穩賺、必賺、包賺、必漲、必跌、一定會、唯一、
  建議買賣、建議買、建議賣、目標價、零風險、無風險、穩賺不賠。

## 儀表板「🕒 資料更新時間」區塊

`arm/fund_dashboard.py` 的 `_freshness_view()`，顯示各資料來源鮮度（皆台北時間）：
NAV 日／持股基準（月度）／持股快照抓取／美股新聞／台股新聞／總經・政策／經濟行事曆／基金新聞・社群／
ETF 數據追蹤／儀表板產表。新增資料來源時請同步加進此區塊。

## 「ETF 數據追蹤」分頁（左上第四分頁）

追蹤台股被動 ETF（0056/00878/00919/00929/0050/006208）＋主動式 ETF 15 檔（含本家 00991A、
2026-07 新增熱門／新募集 00988A/00990A/00403A/00407A；00929/00991A 於表中高亮）的
規模／成立日期／過去一週・一月報酬／配息殖利率／收益分配頻率；儀表板 ETF 表只把
「代碼／名稱」識別欄 CSS sticky 凍結（`.etftbl`，`nth-child(2)` left:0），手機橫向捲動時
恆可見（性質欄隨捲動移出、不佔凍結空間——兩張表已按性質分組，捲動時不需重複顯示）；
**雙資料來源**（各自獨立降級）：規模／年化配息率／配息頻率 ← etfinfo.tw（Tier B）；
**過去一週／一月報酬 ← 多來源自算**（`_fetch_returns`：Yahoo 還原收盤總報酬口徑 → FinMind →
`arm/connectors/twse.fetch_month`，依序取第一個歷史夠密者；以最新交易日收盤對回推 7／30 日曆日
前最後交易日計算，並有「基準日須接近目標日」防呆避免稀疏序列算出錯值）；`ret_src` 記每檔實際
用了哪個源，**儀表板「報酬來源」欄**顯示供追查。
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
資料層 `data/etf_watch.json`：`scripts/fetch_etf_watch.py` 逐檔「欄位級合併」，fallback 鏈為
**本次 etfinfo 新值 → 既有落檔值 → 內建 `SEED_PERF` 週報底稿**（成立日一律取 WATCHLIST 靜態值）。
報酬數據標 `perf_asof` 基準日、規模／殖利率標 `as_of` 抓取日，儀表板分別備註（沿用最近可得值時使用者已同意）。
來源 etfinfo.tw 屬 Tier B，正式對外前以各投信官網核對。

**踩過的坑（勿再犯）**：
- `data/etf_watch.json` 曾被 `.gitignore` 的 `data/*` 擋掉沒入庫 → CI 從零抓、etfinfo 缺欄 → 成立日期／
  週月報酬整片變 null。已在 `.gitignore` 加 `!data/etf_watch.json` 例外，此檔**必須入庫**當 fallback。
- 欄位級 fallback 用「值是否為 None」判斷，**不可用 `dict.get(key, default)`**——CI 曾把欄位寫成顯式 `null`，
  `get(key, default)` 會回傳那個 null 而非 default，反而把資料洗空。用 `arm/etfwatch._pick()`。
