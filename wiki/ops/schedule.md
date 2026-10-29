# 每日時點地圖與 cron

> 每天台北時間哪一班做什麼：Routine 負責準時、GitHub cron 只當兜底（實測系統性遲到 1~3 小時）、盤後刷新與當日完整性看門狗、07:15 備援。
> 原始資料：CLAUDE.md「每日固定時間自動更新」段的盤後數據刷新、GitHub cron 遲到、每日更新時點地圖、備援四條；程式：`.github/workflows/afterhours_refresh.yml`、`scripts/check_afterhours_fresh.py`、`arm/twholidays`。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

### 每日時點地圖（台北時間；2026-08-03 起，2026-08-07 補入 05:08）

| 時間 | 誰觸發 | 做什麼 | 兜底 |
|---|---|---|---|
| 05:08 | Routine | 費半 ^SOX／台積電 ADR 昨夜收盤入檔（美東收盤後，供 06:35 晨報引用） | — |
| 06:15 | etf_holdings cron | 被動式隔夜 PCF | — |
| 06:35 | Routine | 新聞（push 觸發 daily.yml 全量） | 07:15 cron |
| 08:58～09:00:15 | `fut_preopen.yml` 凌晨 03:47～07:17 五班 cron | 台指期盤前取樣（最早的那班等到 08:58；docs/lab_fut_plan.md 第 10 節） | — |
| 15:33 | Routine | 15:40·當日三大法人、外資期貨、ETF 當日漲跌、全球溫度計上線；**＋前十大簡介缺口順手補**（主責見 [全部更新](daily-update.md) 9⑤，2026-08-12 使用者指定掛本班） | 15:40 cron |
| 18:58 | Routine | ~19:10·基金 NAV＋主動式 ETF 當日 PCF 上線 | 19:10 cron；etf_holdings 17:40 cron 遲到自癒 |
| 22:05 | cron | 融資融券（~21:30 公布）、P/C 比、NAV 掃尾 | — |
| 23:20 | 夜檢（Routine 鏈的 send_later） | 只驗不抓 | — |

**週頻**：週一 08:05 Routine → [ETF 募集週掃](etf-weekly-scan.md)（WebSearch 查證後更新 `data/etf_upcoming.json`，push 經 daily.yml 併檔自動上線）；
週日 19:00 strategy_cands.yml 排程（試用中的候選補紀錄、補算）；19:47 Routine → [策略探勘週報](strategy-scouting.md)
（新候選 push 經 strategy_cands.yml 合併通道回測、併進 main、重建）。Routine 的 prompt 原文與搬家見 [排程與「排程搬家」](routines.md)。

### 三層：Routine 準時、cron 兜底、看門狗

1. **準時觸發主路徑＝Routine**（15:33 盤後籌碼、18:58 晚間 NAV·PCF）：火進主會話打 workflow_dispatch，秒級開跑；prompt 原文見「排程搬家」節。
2. **cron 三班只當自癒兜底**（15:40／19:10／22:05，遲到也會到）。重複場次由 `check_afterhours_fresh.py --guard` 守門**零請求早退**——
   多班次不放大對 TWSE/etfinfo 的請求。
3. **當日完整性看門狗**（同腳本 `--write`/`--assert`；根治「run 全綠、無 commit、沒人知道」）：
   - 交易日 16:30 後三大法人須含今日；22:45 後融資融券須含今日且 NAV 不斷更。
   - 缺 → `data/afterhours_alert.json` 入板（儀表板「網頁更新時間」列紅章＋瀏覽器端 16:40／22:50 兩個時窗的延遲橫幅）
     ＋ workflow 最後一步 exit 1（run ❌ → GitHub 寄 failure 信）＋ Routine 自驗 25~60 分後失敗才 PushNotification。
   - 交易日看**證交所官方休市表** `arm/twholidays`（2026-10-13 起；之前讀行事曆市況段，見 [行事曆與資料可信度](../main/calendar.md)「資料可信度盤查」專節）。
     官方表未涵蓋時退回市況段，**市況寫了日期就只認今天那一天**。

### 盤後數據刷新 `afterhours_refresh.yml`

抓取（失敗沿用既有落檔）→ 看門狗寫警示 → check_numbers → 重建 → commit → Deploy Hook → 完整性斷言。
**data/ 無任何變更（休市日）就早退**、不空 commit。不碰 `reports/**`。

### 備援：07:15 cron

repo cron 在**台北週一~六 07:15**（2026-07-20 起，原 06:50），定位是「事後兜底」：Routine 失敗時新聞沿用前日（或撿分支已推的今日新聞），
但 NAV／持股／ETF 照樣更新。頁面瀏覽器端有「逾 2 天未重建」紅色警示橫幅當最後防線。

## 不能改的規則

- **勿再把準時性寄託在 cron 上**（2026-08-03 定調）：準時靠 Routine，cron 只兜底。
- 多班次仍是對齊公布時點的事件驅動、**不是高頻輪詢**（07-31 與使用者確認過不做 30 分鐘輪詢，此原則不變）。
- 失敗才推播：使用者 2026-08-03 選「失敗才推播」。

## 踩過的坑

- **GitHub cron「系統性遲到 1~3 小時、偶爾整班消失」→ 2026-08-03 靜默失敗**：GitHub cron 是 best-effort。etf_holdings 17:40 班
  連五個交易日遲 1.5~3 小時；afterhours 兩班自 07-31 建立以來**從沒準時開過工**（史上首次 schedule 觸發＝08-03 18:56，當晚 22:05 班整班消失）。
  這與「三大法人從不抓當日」的程式 bug 疊加成 08-03 的靜默失敗。修法＝上面三層。
- **把預告別天的休市當成今天休市（2026-09-24）**：市況段寫「台股 9/25 因中秋節休市」，曾把當日判成非交易日。
  修法：市況寫了日期就只認那一天；2026-10-13 起改看證交所官方休市表。

## 歷史

- 2026-07-20：repo cron 移到台北週一~六 07:15（原 06:50），改為「事後兜底」。
- 2026-07-31：建 `afterhours_refresh.yml`。
- 2026-08-03：大改：Routine 主路徑＋cron 三班兜底＋當日完整性看門狗；定調不靠 cron 準時。
- 2026-08-07：時點地圖補入 05:08。
- 2026-08-12：15:33 班加掛前十大簡介缺口。
- 2026-10-13：看門狗的交易日改看證交所官方休市表。
