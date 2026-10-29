# 指令「策略探勘週報」

> 每週日 19:47（或使用者打「策略探勘週報」）WebSearch 找最多 2 條新策略，先寫規格與程式再推，合併通道回測乾淨才併進 main；使用者回「試用／納入／不納入」。
> 原始資料：CLAUDE.md「指令：策略探勘週報」段；規劃 `docs/lab_ia_v5_plan.md` 第 6、24 節；Routine prompt 原文⑥ 在 [排程與「排程搬家」](routines.md)；機制（三種引擎、兩道檢查、合併通道）見 [新策略候選](../lab/candidates.md)。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

每週日台北 19:47 Routine 火進綁定會話執行；使用者手動打「策略探勘週報」也照跑。
框架規格 `arm/lab/candspec.py`（VER 2），程式 `arm/lab/candrun.py`、`scripts/run_cands.py`，合併通道 `.github/workflows/strategy_cands.yml`。
**全程不跑資料抓取腳本、不動 reports/**。

### 指令：「策略探勘週報」步驟

1. 先把 origin/main 合併進本會話分支（候選的程式與檢查要最新的）。讀 `config/strategy_candidates.json` 與 `config/strategy_board.json` 的 `cand`：
   還沒決定的已有 10 條 → 不找，推播提醒使用者回「試用／納入／不納入」。
2. **找**（WebSearch）：來源限學術（SSRN、arXiv q-fin、期刊）、大型資產管理公司與知名量化部落格（AQR、Alpha Architect、Quantpedia、
   Research Affiliates…）、台灣投信券商研究報告。每週**最多 2 條**，四個條件都要：
   - 規則寫得清楚（參數有數字、能直接寫成程式）；
   - 有公開成績；
   - **現有資料做得到**（指數收盤、VIX、漲跌家數、融資維持率；台股長歷史價量、月營收、季財報、EPS；美股資料分支的價量與 SEC 財報）；
   - 和已有的候選與頁面上的策略不重複。

   找不到就不湊、安靜結束。
3. **先寫規格再算**：
   - 規格一筆：`config/strategy_candidates.json` 的 `items`；欄位照 candspec：id 接續編號、found＝今天、name、mk、engine、kind、
     how 一句白話規則、src 至少一條 https 原文連結、why、p、grid、各型態要的 H／b／pick／ex、sha。
   - 程式一支 `arm/lab/cands/{編號}.py`：照 `arm/lab/cands/__init__.py` 的範本；參數從 p 讀、只用那一天收盤以前的資料、
     台股財報與月營收一律經過 `cands.Fin`。
   - sha＝`python3 -c "from arm.lab import candrun as R; print(R.sha_file(R.PROG/'c00X.py'))"`。
   - 資料不夠的只寫規格、`need`＝「需要資料：…」、不寫程式（使用者說要才去補資料）。
4. `TZ=Asia/Taipei python3 scripts/run_cands.py --check` 與 `python3 -m pytest -q tests/test_cands.py tests/test_candspec.py` 全綠
   → `git add config/strategy_candidates.json arm/lab/cands` → commit「chore: 策略候選 {編號} {名稱}」→ push 本會話分支。
   **push 就觸發合併通道**：用 main 的檢查、回測（指數型＝xstrat、台股個股＝回測方法 v3、美股個股＝ussxbook；有美股的另外拿資料分支）、
   用到未來資料的兩道檢查、放進計畫試算；**新候選乾淨地算完才併進 main**（規格、程式、結果同一筆 commit），再派 daily.yml 重建頁面。
5. 等結果（Bash `run_in_background` until 迴圈，每 2 分鐘 `git fetch origin main`，最多 45 分鐘）：
   - `origin/main` 的 `data/lab/cands_research.json` 出現這幾個編號＝安靜結束（星期一 06:35 推播會帶「策略候選：新增…」一行）。
   - 沒出現＝讀那一輪 strategy_cands.yml 的日誌：程式出錯或「用到未來的資料」→ 修程式、重填 sha、再推一次；
     第二次還是不行 → 推播一句卡在哪裡。

### 使用者的決定

使用者在任何對話回「試用 X／納入 X／不納入 X」：改 `config/strategy_board.json` 的 `cand`（`{編號: {dec: trial／adopt／reject, d: 日期, why: 原因}}`）→ push 任何 `claude/**` 分支 → 合併通道只拿 `cand` 那一段併進 main（其他欄位照 main）。

- **試用**：每週日排程記紙上成績（`data/lab/cands_live.json`，只增不改），滿 63 個交易日列照做對一直抱著。
- **納入**：全部策略表「觀察中・納入，等放上選股頁」；選股頁加上這條策略的卡片（pickpage，另外規劃、先問使用者）時用 override 改「使用中」。
- **不納入**：淘汰一行。

## 不能改的規則

- 步驟 5 修的是程式錯誤，不是看了成績調參數；**還沒進 main 的候選可以改**。
- **不做**：通用規則語言（每條候選都是一支小程式＋鎖定）、看過結果改參數（要改＝新的編號，`prev` 指到舊的）、網頁上的按鈕。

## 歷史

- 2026-10-24：建立（IA v5 第 5 段，`docs/lab_ia_v5_plan.md` 第 6、24 節）。
- 2026-10-28：配置頁拿掉，「納入」改成看選股頁；之前是「等計畫改版」（交易計畫出新版本才改使用中）。
