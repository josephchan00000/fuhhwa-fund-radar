# 指令「ETF 募集週掃」

> 每週一 08:05（或使用者打「ETF 募集週掃」）WebSearch 盤點新 ETF 與指數審核時程，只改 `data/etf_upcoming.json`（＋`config/index_reviews.json`），push 即自動上線。
> 原始資料：CLAUDE.md「指令：ETF 募集週掃」段（含週掃步驟 2.5）；Routine prompt 原文⑤ 在 [排程與「排程搬家」](routines.md)；相關：[即將登場與新 ETF 自動發現](../main/etf-upcoming.md)、[指數調整](../lab/index-changes.md)。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

每週 Routine（台北週一 08:05）火進綁定會話執行；使用者手動打「ETF 募集週掃」也照跑。
**全程不跑資料抓取腳本、不動 reports/**、只改 `data/etf_upcoming.json`（＋審核相關時 `config/index_reviews.json`）。

**與每日 SOP 步驟 9⑧ 的分工（2026-08-10 使用者釐清後定調，勿混淆）**：「一週一次」講的是**主動出去掃描**的頻率；
**已被發現層列名的缺口不等週一、當天就補**（見 [全部更新](daily-update.md) 步驟 9⑧）。所以週掃的價值在**每日流程做不到的那些事**：
全面盤點（發現層兩個來源都沒收錄的檔）、既有條目的日期／頻率異動核對、hint 檔補正式日期、過期條目清理、
`pipeline` 內申請中檔有無新生效。正常情況下每日已把新缺口補掉，週掃多半只是核對與清理。

### 指令：「ETF 募集週掃」步驟

1. `git fetch origin main` 後讀 **origin/main** 的 `data/etf_upcoming_gap.json`（CI 自動發現的漏網檔，見「新 ETF 自動發現層」專節，
   在 [即將登場與新 ETF 自動發現](../main/etf-upcoming.md)；`items`＝待登錄的已核准／募集中／已掛牌檔＋
   **`pipeline`＝申請中檔（不警示、僅盤點，本週掃順手看有無新核准）**）與 `data/etf_upcoming.json` 現況；
   跑 `python3 -m pytest tests/test_etfwatch.py -q` 看 stale guard 有無紅（過期條目）。
2. **WebSearch 盤點**（容器擋 moneydj/cnyes/chinatimes 原頁，用搜尋摘要即可）：鉅亨 IPO 頁（`fund.cnyes.com/IPO/index.htm`，
   2026-08-10 使用者提供）＋MoneyDJ 新基金頁＋工商時報／經濟日報「投信新基金」稿＋逐檔精查。**每筆資料兩來源一致才寫**：
   - gap 檔缺口與新核准檔 → 補登（時程未定用 `raise_hint`＋`asof`；未派碼 `code: null`）；
   - hint 檔等到日期公告 → 改填 `raise_start`/`raise_end`/`list_date` 正式欄位；
   - 已登錄檔核對募集期間／掛牌日／配息頻率有無異動；掛牌逾期條目清理；
   - 海外被動指數檔 `track: false`；**本家復華新檔最優先、絕不可漏**。

   2.5 **指數審核維護**（2026-10-14 起；籌碼雷達「指數調整」資料源 `config/index_reviews.json`，見 [指數調整](../lab/index-changes.md)）：
   每週掃一次即可、只在「有事」時改檔——
   - ① `next` 標「推算／未公布」的日期，查官方公告（富時羅素／證交所＝臺灣50、臺灣高股息；MSCI 半年度表＝00878；
     臺灣指數公司 technical notice＝00919／00929，通常前一個月初公布下月時程）→ 查到就改日期、`status:"官方"`；
   - ② 公告日過後把官方納入／刪除寫進 `history`（`adds`/`dels` 用 4 碼代號，`src` 至少一條、兩來源一致才寫），並把 `next` 推到下一次；
   - ③ 規則若改版（成分檔數、緩衝名次）同步改 `rule`，數字不確定寫「未查證」。

   **不猜日期、不猜名單**——查不到就維持「推算」。更新頂層 `as_of`＝今日；`pytest tests/test_lab.py -q` 須綠（守 JSON 格式與代號）。
3. 更新頂層 `as_of`＝今日 → pytest 全綠 → commit `chore: ETF 募集週掃 {日期}` push 本會話指定分支——
   **push 動到該檔會自動觸發 daily.yml**（on.push.paths 含它與 `config/index_reviews.json`），併檔段驗證後帶進 main 重建上線，**不需人工 merge**。
   步驟 2.5 有改 `config/index_reviews.json` 就和 `data/etf_upcoming.json` 同一個 commit push（Routine prompt ⑤ 的寫法）。
4. 結果：**有異動 → PushNotification 一句話**（改了哪幾檔）；無異動 → 安靜結束不推播；失敗 → 推播卡在哪一步。

## 歷史

- 2026-08-10：建立（使用者：「找到募集的資訊然後主動更新，一週一次」）；同日釐清與步驟 9⑧ 的分工，鉅亨 IPO 頁由使用者提供。
- 2026-10-14：加步驟 2.5 指數審核維護。
