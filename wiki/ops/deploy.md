# 部署與「線上沒更新」

> 線上沒更新時照順序診斷（資料日期、產表時戳、部署步驟日誌、Vercel 部署上限，最後才查 Vercel Deployments）；「內容在 main」不等於線上已部署；Deploy Hook、對時哨兵、煙霧測試、快取。
> 原始資料：CLAUDE.md「全部更新」步驟 9 的「內容在 main ≠ 線上已部署」條、「每日固定時間自動更新」段的「部署」「Vercel 免費方案每日部署上限」「多人化硬化」三條；規劃 `docs/multi_user_plan.md`；程式：`scripts/check_live_deploy.py`、`scripts/smoke_dashboard.py`、兩支 `vercel.json`。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

### 線上沒更新：先照這個順序診斷

使用者回報線上沒更新、或對時哨兵紅了，照下面走，數分鐘可判。**別從抓取端查起**：這類「線上舊」的坑，資料端全綠是常態；
**哨兵紅≠資料有問題**（資料多半已入 main）。

1. `git show origin/main:data/macro_chips.json` 看序列最後日期 → 是今日就不是抓取問題。
2. 儀表板產表時戳是否為該班時間 → 是就不是建表問題。
3. **讀該班 run 部署步驟（「觸發 Vercel 部署」）的日誌**（`mcp__github__get_job_logs`）：
   - 印「未設…跳過」＝secret 沒生效（被刪或失效）。當下緩解與根治見下方「Deploy Hook」。
   - 印 `HTTP 2xx` 才算真的打出去。
   - 步驟耗時也是判準：未設時瞬間 echo 完就 exit（0 秒），真打出去約 3~4 秒。
4. 部署步驟印 2xx、線上仍是舊版（哨兵紅）：讀 PR 的 commit status（`pull_request_read` get_status，context＝Vercel），
   描述是「Deployment rate limited — retry in 24 hours」＝撞到 Vercel 免費方案每日部署上限（見「踩過的坑」）。
5. 以上都不是，才請使用者查 Vercel Deployments 對到哪個 commit。

另一種徵狀「**新聞會動、淨值不動**」（舊架構的坑）：先查 main 最新 commit 的 `data/funds/*.json` `nav_date` 是否真的新
（否則是 `news_ref` 沒帶到／CI 沒抓到資料），再查 Vercel 部署對到哪個 commit。

**驗證 secret 要挑對 workflow**：`daily.yml` 的部署步驟沒有任何 `if:` 守門、無條件執行——要驗就 dispatch 它（`news_ref` 留空），
必定跑到那步、必定有日誌可讀。`afterhours_refresh.yml`／`etf_holdings.yml` 的同一步有 `if: steps.guard.outputs.changed == 'true'`，
資料沒變動的空轉輪會**整步跳過**，拿那種 run 驗會什麼都看不到、誤以為沒生效。

### 完成的定義：「內容在 main」≠「線上已部署」

- **我（容器內 Claude）看不到 Vercel 線上頁**（proxy CONNECT 403），所以不可只憑「main 檔已更新」就宣稱「線上已生效」。
  我的完成定義只到「**CI commit 在 main＋該 `daily.yml` run success＋該 commit `nav_date` 已推進**」；
  「線上真的更新」需使用者端或 Deploy Hook 確認。
- **單一 commit 架構**（[全部更新](daily-update.md)步驟 7）：main 每天只有一筆權威 CI commit（新聞＋真實資料＋建表同一筆），
  根治「兩筆 commit」問題，不會再有「合併版舊資料」被誤部署。

### Deploy Hook（主動部署）

- CI commit 後打 `secrets.VERCEL_DEPLOY_HOOK`（`daily.yml` 末步「打 Vercel Deploy Hook」），直接觸發 production 部署 main 最新，
  **不靠 Vercel 自動偵測**（自動偵測曾卡 Initializing／部到舊版／漏接）。`daily.yml`／`afterhours_refresh.yml`／`etf_holdings.yml`
  **三支都讀這把 secret，建一次三班全生效**，程式碼不必動。未設時該步自動跳過、不影響 commit。
- **2026-08-13 起 secret 已建立並驗證通過**（dispatch `daily.yml` run 31690853627）：部署步驟日誌印 `VERCEL_DEPLOY_HOOK: ***`
  （讀到了、遮罩顯示）＋ `{"job":{"id":"…","state":"PENDING"…}}` ＋ `HTTP 201`——hook 真的打出去、Vercel 已排程部署（`PENDING` job）。
- **怎麼建（secret 被刪要重建時）**：Vercel 專案 Settings→Git→Deploy Hooks 建 `main` 分支 hook → 複製 URL →
  GitHub repo Settings→Secrets and variables→**Actions**→New repository secret，Name 一字不差填 `VERCEL_DEPLOY_HOOK`、Secret 貼 URL。
  **別建成 Variables 或 Environment secret**，workflow 讀的是 repository secret。
- **secret 沒生效時的當下緩解**：dispatch 一輪 `daily.yml`（ref=main、`news_ref` 留空＝只用 main 現有新聞重刷資料），
  產生新的 commit＋push 事件，給自動偵測第二次機會（2026-08-13 實測有效，17:24 那筆上線）。**根治只有把 secret 建起來**。

### 快取

兩支 `vercel.json`（根目錄與 dashboard/）都設 `Cache-Control: no-cache`：瀏覽器可存但**每次都必須向伺服器 revalidate**——
內容沒變回 304（~1KB）、變了才全量下載，300 人重複造訪省流。304 是否生效看對時哨兵日誌的「（記錄）帶 If-None-Match 重打」行。
因為每次都 revalidate，瀏覽器快取不可能是線上舊的原因（見「不能改的規則」第一條）。

### 多人化硬化（2026-08-14；規劃全文 `docs/multi_user_plan.md`）

實際規模＝**家人約 30 人分享、非商用**，Vercel Hobby 合規、無需升 Pro。**讀取端不隨人數產生成本**：CI 分鐘按排程固定、
資料來源站只有 CI 會碰、使用者只從 CDN 抓單一自包 HTML，30 人約 0.4GB/月＝免費額 0.4%。硬化的價值主要在**省維護者自己的除錯時間**，與人數無關。

1. **對時哨兵 `scripts/check_live_deploy.py`**：三支 workflow 部署步驟後輪詢**線上頁**（Actions 網路可達 vercel.app，容器不行），
   比對 `data-gen` 產表時戳已追上 main（4 分鐘內），沒追上→run ❌ 寄信。根治 08-13 型「資料進 main、線上停舊版」的發現延遲。
2. **煙霧測試 `scripts/smoke_dashboard.py`**：daily.yml 建表後 headless Chromium 驗 console 零錯誤／關鍵區塊／`__EH`／時戳。
   **兩段式**：env `SMOKE_ENFORCE=0` 觀察期只告警，誤報率歸零後改 `'1'` 攔截（攔截＝該輪不 commit 不部署、線上維持前一版）。
   afterhours／etf_holdings 走 `--lite` 零依賴結構檢查（截斷/區塊消失才紅，直接攔截）。
3. 長開分頁逾 6 小時提示重新整理（`fund_dashboard.py` 頁齡 IIFE）。
4. 快取 no-store→no-cache（上一節）。

CI 分鐘帳（私有時期的帳；2026-10-16 起 repo 已公開，一般機器不計分鐘）：免費額 2,000 分/月，此前用量 ~1,000，哨兵＋煙測估 +200~300。
獨立 30 分 cron 哨兵就是因 +1,440 分/月被否決、改成接在部署步驟後面（piggyback）。2026-10-16 實測帳見 [GitHub Actions 額度](ci-budget.md)。

## 不能改的規則

- **「線上看到舊的一律是「沒部署」而非快取」的診斷鐵則不變**：別叫使用者清快取白忙。
- 不可只憑「main 檔已更新」就宣稱「線上已生效」（上面的完成定義）。
- **兩支 vercel.json 根目錄與 dashboard/ 都要一致**。工作分支的預覽部署用 `"git": {"deploymentEnabled": {"claude/**": false}}` 關掉，
  **main 不得關掉**（`tests/test_multiuser_hardening.py` 守）。
- **煙測只擋結構壞頁；數字對錯仍走 factcheck 不擋發佈**，「防線不可硬到什麼都沒更新」原則不變。
- **新增排程/步驟前先想分鐘帳**。

## 踩過的坑

- **「內容在 main」被當成「線上已部署」（2026-07-17）**：舊架構一天兩筆 commit，徵狀是「新聞會動、淨值不動」；
  同日我只憑「main 檔已更新」就宣稱「線上已生效」，是誤報。修法：單一 commit 架構（步驟 7）＋上面的完成定義；同時規劃 Deploy Hook。
- **secret 一直沒建 →「資料準時進 main、線上停在舊版」（2026-08-13 使用者回報「今天 15:40 的還沒更新」）**：
  當天 15:33 Routine 準時開跑、`afterhours_refresh` run **success**、15:34 就 commit 進 main（`21b5bcb`；
  2026-10-16 改寫歷史後這個編號已不存在，見 [git 歷史](../env/git-history.md)），三大法人／外資台指期／P/C 比／全球溫度計全是當日值、
  儀表板產表時戳 15:34 也對——**資料層與 CI 全鏈零異常**，線上卻是舊版。**決定性證據**＝該 run「觸發 Vercel 部署」步驟的日誌印
  「（未設 VERCEL_DEPLOY_HOOK secret，跳過主動部署）」、env 區 `VERCEL_DEPLOY_HOOK:` 是空值——這把 secret 自 07-17 規劃以來從沒建成，
  每天都在空跳，部署一直只靠 Vercel 自動偵測 git push；當天那筆偵測漏接，線上就停在舊版
  （「資料準時進 main、CI 全 success、線上卻停在舊版」）。
  緩解：dispatch `daily.yml`（17:24 那筆上線）。✅ 已解決：當晚使用者建立 secret，run 31690853627 驗證通過。
  防呆：上面的診斷順序、2026-08-14 加的對時哨兵。
- **Vercel 免費方案每日部署上限（2026-10-15：對時哨兵連三輪紅、線上停在 20:53）**：每推一次 `claude/**` 工作分支，Vercel 就多做一次預覽部署；
  main 每筆 CI commit 又部署兩次（自動偵測＋Deploy Hook）。當天工作分支推了幾十次、超過上限後，Deploy Hook 照樣回 `HTTP 201`，
  但部署建不起來，線上停在舊版。診斷見上面第 4 步。當下對策：當天少推分支，等限制解除，下一班 CI 會自動部署。
  根治：兩支 vercel.json 加 `"git": {"deploymentEnabled": {"claude/**": false}}`，停掉工作分支的預覽部署
  （2026-10-16 使用者同意、已改，`tests/test_multiuser_hardening.py` 守）。

## 歷史

- 2026-07-17：誤報「線上已生效」；`daily.yml` 末步規劃「打 Vercel Deploy Hook」，但 secret 沒建成。
- 2026-08-13：查出 secret 從沒建過；當晚使用者建立，run 31690853627 印 `HTTP 201`。
- 2026-08-14：多人化硬化：對時哨兵、煙霧測試、頁齡提示；`Cache-Control` 由 no-store 改 no-cache（多人化 Phase 1）。
- 2026-10-15：撞到 Vercel 每日部署上限。
- 2026-10-16：兩支 vercel.json 停掉 `claude/**` 預覽部署；repo 改公開，一般機器不計 Actions 分鐘。
