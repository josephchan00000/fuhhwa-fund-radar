# 部署與「線上沒更新」

> 內容在 main 不等於線上已部署、Deploy Hook、診斷順序、Vercel 部署上限、多人化硬化、快取。
>
> 這一頁目前是從 CLAUDE.md 逐字搬來的（知識庫第一段），還沒整理；有出入時以 CLAUDE.md 為準。
> 改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產這一頁。

<!-- CLAUDE.md 第 262–288 行 -->
   - ⚠️ **「內容在 main」≠「線上已部署」——2026-07-17 踩過的大坑，務必分清**：
     - **單一 commit 架構（步驟 7）已根治「兩筆 commit」問題**：main 每天只有一筆權威 CI commit（新聞＋真實資料＋建表同一筆），不會再有「合併版舊資料」被誤部署。舊坑徵狀是「**新聞會動、淨值不動**」——若再出現，先查 main 最新 commit 的 `data/funds/*.json` `nav_date` 是否真的新（否則是 `news_ref` 沒帶到／CI 沒抓到資料），再查 Vercel 部署對到哪個 commit。
     - **我（容器內 Claude）看不到 Vercel 線上頁**（proxy CONNECT 403），所以**不可只憑「main 檔已更新」就宣稱「線上已生效」**——那是我 07-17 誤報的錯。我的完成定義只到「**CI commit 在 main＋該 `daily.yml` run success＋該 commit `nav_date` 已推進**」；「**線上真的更新**」需使用者端或 Deploy Hook 確認。
     - **主動部署**：`daily.yml` 末步已加「打 **Vercel Deploy Hook**」（`secrets.VERCEL_DEPLOY_HOOK`）——CI commit 完直接觸發 production 部署 main 最新，**不靠 Vercel 自動偵測**（自動偵測曾卡 Initializing／部到舊版）。**使用者需先建 hook**：Vercel 專案 Settings→Git→Deploy Hooks 建 `main` 分支 hook → 複製 URL → GitHub repo Settings→Secrets and variables→**Actions**→New repository secret，Name 一字不差填 `VERCEL_DEPLOY_HOOK`、Secret 貼 URL（**注意別建成 Variables 或 Environment secret**，workflow 讀的是 repository secret）。`daily.yml`／`afterhours_refresh.yml`／`etf_holdings.yml` **三支都已寫好讀這把 secret，建一次三班全生效**，程式碼不必動。未設時該步自動跳過、不影響 commit。
     - **⚠ 踩過的坑：secret 一直沒建 →「資料準時進 main、線上停在舊版」（2026-08-13 使用者回報「今天 15:40 的還沒更新」）**：
       當天 15:33 Routine 準時開跑、`afterhours_refresh` run **success**、15:34 就 commit 進 main（`21b5bcb`），
       三大法人／外資台指期／P/C 比／全球溫度計全是當日值、儀表板產表時戳 15:34 也對——**資料層與 CI 全鏈零異常**，
       線上卻是舊版。**決定性證據＝該 run「觸發 Vercel 部署」步驟的日誌印「（未設 VERCEL_DEPLOY_HOOK secret，
       跳過主動部署）」、env 區 `VERCEL_DEPLOY_HOOK:` 是空值**——這把 secret 自 07-17 規劃以來從沒建成，
       每天都在空跳，部署一直只靠 Vercel 自動偵測 git push；當天那筆偵測漏接，線上就停在舊版。
       · **診斷順序（下次照這條走，數分鐘可判；別再從抓取端查起——這類「線上舊」的坑，資料端全綠是常態）**：
         ①`git show origin/main:data/macro_chips.json` 看序列最後日期 → 是今日就不是抓取問題；
         ②儀表板產表時戳是否為該班時間 → 是就不是建表問題；
         ③**讀該 run 部署步驟的日誌**（`mcp__github__get_job_logs`）→ 印「未設…跳過」＝secret 沒生效、
         印 `HTTP 2xx` 才算真的打出去 → 若已打出去仍是舊版，才輪到請使用者查 Vercel Deployments。
       · **當下緩解**＝dispatch 一輪 `daily.yml`（ref=main、`news_ref` 留空＝只用 main 現有新聞重刷資料）
         產生新的 commit＋push 事件，給自動偵測第二次機會（2026-08-13 實測有效，17:24 那筆上線）；
         **根治只有把 secret 建起來**。
       · **✅ 已解決（2026-08-13 當晚使用者建立 secret，dispatch `daily.yml` run 31690853627 驗證通過）**：
         該輪部署步驟日誌印 `VERCEL_DEPLOY_HOOK: ***`（讀到了、遮罩顯示）＋
         `{"job":{"id":"…","state":"PENDING"…}}` ＋ **`HTTP 201`**——hook 真的打出去、Vercel 已排程部署。
         **步驟耗時也是判準**：未設時瞬間 echo 完就 exit（0 秒），真打出去約 3~4 秒。
       · **驗證要挑對 workflow（實測差異）**：**`daily.yml` 的部署步驟沒有任何 `if:` 守門、無條件執行**
         ——要驗 secret 就 dispatch 它（`news_ref` 留空），必定跑到那步、必定有日誌可讀；
         `afterhours_refresh.yml`／`etf_holdings.yml` 的同一步有 `if: steps.guard.outputs.changed == 'true'`，
         資料沒變動的空轉輪會**整步跳過**，拿那種 run 驗會什麼都看不到、誤以為沒生效。
     - Vercel `vercel.json` 已設 `Cache-Control: no-cache`（2026-08-14 多人化 Phase 1 由 no-store 改，**兩支 vercel.json 根目錄與 dashboard/ 都要一致**）：瀏覽器可存但**每次都必須向伺服器 revalidate**——內容沒變回 304（~1KB）、變了才全量下載，300 人重複造訪省流；**「線上看到舊的一律是「沒部署」而非快取」的診斷鐵則不變**（每次都 revalidate，瀏覽器快取不可能是原因），別叫使用者清快取白忙。304 是否生效看對時哨兵日誌的「（記錄）帶 If-None-Match 重打」行。
<!-- CLAUDE.md 第 532–559 行 -->
- **部署**：CI commit 後打 `secrets.VERCEL_DEPLOY_HOOK` 主動部署（`daily.yml`／`afterhours_refresh.yml`／
  `etf_holdings.yml` 三支皆已接好）。**2026-08-13 起 secret 已建立並驗證通過**（run 31690853627 部署步驟印
  `HTTP 201`＋Vercel 回 `PENDING` job）。**在此之前這把 secret 從沒建過**，部署一直只靠 Vercel 自動偵測
  git push（曾卡 Initializing／漏接），偵測漏接就會出現「資料準時進 main、CI 全 success、線上卻停在舊版」
  ——原委與診斷順序見步驟 9 的「主動部署」與其下踩坑條。**如使用者回報線上沒更新，先讀該班 run 部署步驟的
  日誌**（印 `HTTP 2xx`＝真的打出去了；印「未設…跳過」＝secret 被刪或失效），再問 Vercel Deployments 對到哪個 commit。
- **⚠ Vercel 免費方案每日部署上限（2026-10-15 踩坑：對時哨兵連三輪紅、線上停在 20:53）**：每推一次 `claude/**`
  工作分支，Vercel 就多做一次預覽部署；main 每筆 CI commit 又部署兩次（自動偵測＋Deploy Hook）。當天工作分支推了
  幾十次、超過上限後，Deploy Hook 照樣回 `HTTP 201`，但部署建不起來，線上停在舊版。**診斷**：哨兵紅、部署步驟
  卻印 2xx 時，讀 PR 的 commit status（`pull_request_read` get_status，context＝Vercel），描述是
  「Deployment rate limited — retry in 24 hours」就是這個。**對策**：當天少推分支，等限制解除，下一班 CI 會自動部署；
  根治是在兩支 vercel.json 加 `"git": {"deploymentEnabled": {"claude/**": false}}`，停掉工作分支的預覽部署
  （2026-10-16 使用者同意、已改，`tests/test_multiuser_hardening.py` 守；main 不得關掉）。
- **多人化硬化（2026-08-14；規劃全文 `docs/multi_user_plan.md`。實際規模＝**家人約 30 人分享、非商用**，
  Vercel Hobby 合規、無需升 Pro；**讀取端不隨人數產生成本**——CI 分鐘按排程固定、資料來源站只有 CI 會碰、
  使用者只從 CDN 抓單一自包 HTML，30 人約 0.4GB/月＝免費額 0.4%。硬化的價值主要在**省維護者自己的
  除錯時間**，與人數無關）**：
  ① **對時哨兵 `scripts/check_live_deploy.py`**——三支 workflow 部署步驟後輪詢**線上頁**（Actions 網路
    可達 vercel.app，容器不行），比對 `data-gen` 產表時戳已追上 main（4 分鐘內），沒追上→run ❌ 寄信。
    根治 08-13 型「資料進 main、線上停舊版」的發現延遲；**哨兵紅≠資料有問題**（資料多半已入 main），
    診斷照上一條的順序走。② **煙霧測試 `scripts/smoke_dashboard.py`**——daily.yml 建表後 headless Chromium
    驗 console 零錯誤／關鍵區塊／`__EH`／時戳（**兩段式：env `SMOKE_ENFORCE=0` 觀察期只告警，誤報率
    歸零後改 `'1'` 攔截**——攔截＝該輪不 commit 不部署、線上維持前一版）；afterhours／etf_holdings 走
    `--lite` 零依賴結構檢查（截斷/區塊消失才紅，直接攔截）。**煙測只擋結構壞頁；數字對錯仍走 factcheck
    不擋發佈**，「防線不可硬到什麼都沒更新」原則不變。③ 長開分頁逾 6 小時提示重新整理（`fund_dashboard.py`
    頁齡 IIFE）。④ 快取 no-store→no-cache 見上方步驟 9 該條。CI 分鐘帳（2026-10-16 起 repo 已公開，一般機器不計分鐘；以下為私有時期的帳）：免費額 2,000 分/月，
    此前用量 ~1,000，哨兵＋煙測估 +200~300——**新增排程/步驟前先想分鐘帳**（獨立 30 分 cron 哨兵就是
    因 +1,440 分/月被否決改 piggyback 的）。**2026-10-16 實測帳見下一條。**
