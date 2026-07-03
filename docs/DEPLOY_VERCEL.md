# 上線 Vercel（固定網址、連 repo 即自動部署）

儀表板是**單一靜態 `dashboard/index.html`**（零外部請求、零 build、零後端），且該檔已入庫，
所以 Vercel 直接把它當靜態網站服務即可——**不需要 token、不需要 build 指令**。

## A. 一次性設定（約 2 分鐘，在 vercel.com 網頁完成）

1. 到 <https://vercel.com/new>，用 GitHub 帳號登入。
2. **Import** 這個 repo：`josephchan00000/fuhhwa-fund-radar`。
3. 設定專案：
   - **Root Directory** → 選 `dashboard`（重要：讓 `index.html` 與 `vercel.json` 當網站根目錄）
   - **Framework Preset** → `Other`（純靜態，無框架）
   - **Build Command** → 留空
   - **Output Directory** → 留空（直接服務 root）
4. 按 **Deploy**。約數十秒後拿到固定網址，例如 `https://fuhhwa-fund-radar.vercel.app`。

完成後，**每次 push 到 repo，Vercel 自動重新部署**；`dashboard/vercel.json` 已設
`X-Robots-Tag: noindex`（擋搜尋引擎）與 `Cache-Control: no-store`（每次抓最新）。

## B. 每日自動保持最新

`.github/workflows/daily.yml`（台北時間週一~六 08:30，或手動 workflow_dispatch）會：
抓 25 檔基金最新 NAV／持股 → 重建 `dashboard/index.html` → commit 回 repo。
Vercel 監看 repo → 自動部署。**所以資料每天自動更新到同一個網址，無需人工。**

> 新聞內容（美股 `reports/usnews/{date}_v*.md`、台股 `reports/twnews/{date}.md`）仍由
> 會上網查證的 LLM 產出；產好 commit 後，同樣觸發 Vercel 自動部署。

## C. 存取控制（重要）

Vercel 部署網址**預設任何人知道網址就看得到**。`vercel.json` 的 `noindex` 只擋搜尋引擎索引，
**不是存取控制**。若內容需限內部人員：

- **Vercel Pro**：專案 → Settings → **Deployment Protection** → 開 Vercel Authentication
  （限團隊成員登入）或 Password Protection（設密碼）。
- **免費替代**：改用 Cloudflare Pages + Zero Trust Access（email 白名單），見 `scripts/cf_publish.py`。

未鎖前，請勿把網址公開散布。

## D.（進階，選用）改用 Vercel CLI／Actions 自動部署

若不想用 Git 整合、想要更嚴格的部署控制，可用 token 方式（需在本機或 CI 設 `VERCEL_TOKEN`）：

```bash
# 本機一次性：
npx vercel login
npx vercel link --yes            # 在 dashboard/ 綁定專案
# 之後每次：
npx vercel deploy dashboard --prod
```

或把 `VERCEL_TOKEN` 設為 GitHub repo Secret，於 `daily.yml` 末段加一步
`npx vercel deploy dashboard --prod --token=$VERCEL_TOKEN --yes`，
讓每日資料刷新後自動部署（與 A 的 Git 整合二擇一即可，不需並用）。

---

**建議**：先用 **A（Git 整合）** ——零 token、最省事、每天自動更新；需要鎖存取再做 C。
