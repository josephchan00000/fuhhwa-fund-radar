# 每日時點地圖與 cron

> 每天台北時間哪一班做什麼：Routine 負責準時、GitHub cron 只當兜底（實測系統性遲到 1~3 小時）、盤後刷新與當日完整性看門狗、07:15 備援。
> 原始資料：CLAUDE.md「每日固定時間自動更新」段的盤後刷新、cron 遲到、時點地圖、備援四條；程式：`.github/workflows/afterhours_refresh.yml`、`scripts/check_afterhours_fresh.py`。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

### 時點地圖（台北時間；2026-08-03 起，2026-08-07 補入 05:08）

- 05:08 Routine：費半 ^SOX／台積電 ADR 昨夜收盤入檔（美東收盤後，供 06:35 晨報引用）。06:15 etf_holdings cron：被動式隔夜 PCF。
- 06:35 Routine：新聞（push 觸發 daily.yml 全量；07:15 cron 兜底）。
- 08:58～09:00:15 台指期盤前取樣（`fut_preopen.yml` 凌晨 03:47～07:17 五班 cron，最早的那班等到 08:58；docs/lab_fut_plan.md 第 10 節）。
- 15:33 Routine → 15:40·當日三大法人、外資期貨、ETF 當日漲跌、全球溫度計上線（15:40 cron 兜底）；**＋前十大簡介缺口順手補**（主責見 [全部更新](daily-update.md) 9⑤，2026-08-12 使用者指定掛本班）。
- 18:58 Routine → ~19:10·基金 NAV＋主動式 ETF 當日 PCF 上線（19:10 cron 兜底；etf_holdings 17:40 cron 遲到自癒）。
- 22:05 cron：融資融券（~21:30 公布）、P/C 比、NAV 掃尾。23:20 夜檢（Routine 鏈的 send_later，只驗不抓）。
- 週頻：週一 08:05 Routine → [ETF 募集週掃](etf-weekly-scan.md)（更新 `data/etf_upcoming.json`，push 經 daily.yml 併檔上線）；週日 19:00 strategy_cands.yml 排程（試用中的候選補紀錄、補算）、
  19:47 Routine → [策略探勘週報](strategy-scouting.md)（新候選經 strategy_cands.yml 合併通道回測、併進 main、重建）。Routine 見 [排程搬家](routines.md)。

### 三層（2026-08-03）

1. **準時＝Routine**（15:33、18:58）：火進主會話打 workflow_dispatch，秒級開跑。
2. **cron 三班只當自癒兜底**（15:40／19:10／22:05，遲到也會到）；重複場次由 `check_afterhours_fresh.py --guard` **零請求早退**，多班次不放大對 TWSE/etfinfo 的請求。
3. **當日完整性看門狗**（同腳本 `--write`/`--assert`，根治「run 全綠、無 commit、沒人知道」）：交易日 16:30 後三大法人須含今日、22:45 後融資融券須含今日且 NAV 不斷更；
   缺 → `data/afterhours_alert.json` 入板（「網頁更新時間」列紅章＋瀏覽器 16:40／22:50 兩個時窗的延遲橫幅）＋ workflow 最後一步 exit 1（run ❌ → failure 信）
   ＋ Routine 自驗 25~60 分後「失敗才推播」（使用者 2026-08-03 選）。交易日看**證交所官方休市表** `arm/twholidays`（2026-10-13 起，之前讀行事曆市況段，
   見 [行事曆](../main/calendar.md)「資料可信度盤查」）；官方表未涵蓋時退回市況段，**市況寫了日期就只認今天那一天**。

`afterhours_refresh.yml`（2026-07-31 建）：抓取（失敗沿用既有落檔）→ 看門狗寫警示 → check_numbers → 重建 → commit → Deploy Hook → 完整性斷言；
**data/ 無任何變更（休市日）就早退**、不空 commit、不碰 `reports/**`。

**備援**：repo cron **台北週一~六 07:15**（2026-07-20 起，原 06:50）＝「事後兜底」：Routine 失敗時新聞沿用前日（或撿分支已推的今日新聞），NAV／持股／ETF 照樣更新；
頁面瀏覽器端「逾 2 天未重建」紅色橫幅當最後防線。

## 不能改的規則

- **勿再把準時性寄託在 cron 上**；多班次仍是對齊公布時點的事件驅動、**不是高頻輪詢**（07-31 與使用者確認過不做 30 分鐘輪詢）。

## 踩過的坑

- **GitHub cron 是 best-effort，「系統性遲到 1~3 小時、偶爾整班消失」（2026-08-03 定調）**：etf_holdings 17:40 班連五個交易日遲 1.5~3 小時；afterhours 兩班自 07-31 建立**從沒準時開過工**
  （首次 schedule 觸發＝08-03 18:56，當晚 22:05 班整班消失），與「三大法人從不抓當日」的程式 bug 疊加成 08-03 的靜默失敗 → 三層。
- **把預告別天的休市當成今天（2026-09-24）**：市況段「台股 9/25 因中秋節休市」曾把當日判成非交易日 → 只認寫明的那一天。
