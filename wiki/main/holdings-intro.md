# 持股簡介補齊

> 前十大簡介一再漏掉的根因、三道防呆、補簡介格式。
>
> 這一頁目前是從 CLAUDE.md 逐字搬來的（知識庫第一段），還沒整理；有出入時以 CLAUDE.md 為準。
> 改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產這一頁。

<!-- CLAUDE.md 第 672–692 行 -->
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
