# 持股簡介補齊

> 前十大簡介一再漏掉的根因、三道防呆（10/21 起也含 ETF 持股、10/24 起含美股）、補簡介格式。
> 原始資料：CLAUDE.md「已知環境限制與防呆」段的前十大持股簡介一條；每天怎麼補見 [全部更新](../ops/daily-update.md) 步驟 9⑤ 與 [排程](../ops/routines.md) 的 15:33 盤後籌碼班；
> 程式：`scripts/check_holdings_intro.py`、`config/holding_profiles.json`、`tests/test_holdings_intro.py`
> 最後更新：2026-10-29
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

## 現在怎麼運作

基金前十大持股每一檔都要在 `config/holding_profiles.json` 有一段簡介。持股在 CI 每天抓，缺的簡介由三道防呆抓出來、每天下午補上：

1. **CI 端即時偵測**：`daily_fund.sh` 在建表前跑 `scripts/check_holdings_intro.py`，把缺口寫 `data/holdings_intro_gap.json`（入庫），
   儀表板「網頁更新時間」列顯示 🔴「N 檔缺簡介」警示章。
2. **每日固定補齊迴路**：主責＝15:33 盤後籌碼 Routine 步驟②；晨間 9⑤ 只讀、連兩天紅才 backstop。讀 gap 檔見 🔴 → WebSearch 補 `config/holding_profiles.json` 並 push。
   **push 就落地**：該檔已入 daily.yml 自動併檔通道（防呆＝JSON 驗證＋有簡介筆數不得減少、壞檔/倒灌保 main 版），不需 PR/merge/dispatch/監看。
3. **pytest 守覆蓋**：`tests/test_holdings_intro.py` 斷言「已入庫的基金快照前十大 100% 有簡介」，容器端一旦看到含新標的的快照就會紅、逼在發佈前補齊。

範圍：1、2 從 2026-10-21 起也含 ETF 完整持股、10-24 起含美股強勢品質股的股票（見 [全部更新](../ops/daily-update.md) 9⑤）；3 只守基金，ETF 持股另有 `test_etf_持股簡介覆蓋率不倒退`。

### 補簡介格式

`config/holding_profiles.json` 的 `profiles` 下 `{持股原字串: {intro, ticker, country, verified}}`：
- key 必須是 `data/funds/*.json` 內 `top_holdings[].name` 的**原字串**（含 `*` 等後綴，精確對應）；
- intro 純事實描述、非投資建議、避開禁用詞（見 [內容鐵則](../ops/content-rules.md)）；
- 冷門標的先 WebSearch 查證再寫。

### 不必另設「每月固定更新時間」

前十大是官網**月度**揭露（`as_of` 顯示上月底，換月時點由投信定、實務約次月上旬～中旬），而 CI **每天**都抓（06:35 Routine＋07:15 cron 兜底）——
官網哪天換月，當天早上就自動帶入、`as_of` 自動推進。日頻管線天然涵蓋月頻資料源，另設月更排程只是多一個要維護的東西。
換月常伴新標的缺簡介 → 由上面三道防呆＋9⑤ 迴路吃掉。

## 不能改的規則

- 三道防呆缺一不可。
- profiles 的 key 一律用快照裡的原字串，不可自己改寫名稱。
- 補簡介走 push 自動併檔通道；舊流程（開 PR 人工 merge，首例 #200）已淘汰。

## 踩過的坑

- **前十大持股「簡介一再漏掉」（2026-07-23 使用者多次反映）**：持股在**正式區 CI 抓**（本容器 proxy 擋 fhtrust，抓不到）——每月換持股時，
  新標的名**只會出現在 CI 產出的 `data/funds/*.json`**，容器端（主會話）看到的是舊快照，本地檢查／pytest 自然抓不到新標的缺簡介 → 漏的簡介直接隨 CI commit 上線。
  這不是誰忘了，是「抓取在 CI、補簡介在容器」的時間差結構性造成。修法：上面三道防呆。

## 歷史

- 2026-07-23：使用者多次反映簡介一再漏掉；查出根因、建三道防呆。
- 2026-08-12：補上最後一哩——profiles 檔進 daily.yml 自動併檔通道，push 即落地；舊的開 PR 流程淘汰。補齊主責改到 15:33 盤後班（見 9⑤）。
