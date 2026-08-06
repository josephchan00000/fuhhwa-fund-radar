# 社群監看擴充規劃：Facebook／Instagram／Threads（2026-08-06）

使用者需求：「幫我規劃 Facebook、IG、Threads 的 API」。本文件為三平台官方 API 的可行性
評估與分期路線（2026-08 以 WebSearch 查證現況），實作時逐平台開工，全部沿用本 repo
社群層慣例：**只存標題／連結／聲量 proxy、不落全文；無金鑰或被擋一律誠實降級回 []；
負面司法題材過濾同 PTT／YouTube**（`fundnews.is_negative_title`）。

## 結論先講

| 平台 | 能拿到什麼 | 門檻 | 建議 |
|---|---|---|---|
| **Threads** | **公開貼文關鍵字搜尋**（`/keyword_search`，可搜「復華投信」「00929」） | 需 App 審核過 `threads_keyword_search` 權限；未過審前只能搜自家帳號貼文。限 2,200 查詢/24h（本工具每日僅需個位數） | **第一優先**——三平台唯一有官方公開搜尋、且額度綽綽有餘 |
| **Facebook** | 自家粉專貼文＋互動數（Page token）；**他人粉專公開內容需 Page Public Content Access 審核（最難）** | 自家粉專：粉專管理員授權即可；公開內容：App 審核門檻最高 | 第二優先只做**自家粉專動態**；他人粉專暫緩 |
| **Instagram** | 自家商業帳號貼文＋洞察；hashtag 搜尋（#復華投信 #00929） | 需 IG **商業/創作者帳號＋綁 FB 粉專**；hashtag 搜尋需審核，且**每帳號 7 天只能搜 30 個不同 hashtag** | 第三優先——hashtag 額度緊、個人帳號完全不可用 |

## 分期路線

### Phase 0（前置，需使用者操作一次）
1. [Meta for Developers](https://developers.facebook.com/) 建開發者帳號 → 建 **Business 型 App**。
2. App 加入產品：**Threads API**（Phase 1）、之後視需要加 Instagram／Facebook Login for Business。
3. 產生長效 token（60 天效期、可程式 refresh），存 GitHub Actions secrets：
   - `THREADS_ACCESS_TOKEN`（Phase 1）
   - `FB_ACCESS_TOKEN`（Phase 2，Page token；secret 名沿用 v0.12 舊 slot，`arm/connectors/social/facebook.py` 已有現成 adapter 與 `config/social_fb_pages.json` 設定檔）
   - `IG_ACCESS_TOKEN`＋`IG_USER_ID`（Phase 3）

### Phase 1：Threads 公開關鍵字搜尋（最高價值）
- `fundnews.fetch_threads()` 比照 `fetch_youtube()`：查「復華投信」「00929」→ 留相關＋非負面
  → `{platform:"threads", title(貼文前 80 字), url, date, likes}` 併入 `social`；儀表板加 Threads 章。
- **未過審前**該權限只搜得到自家帳號貼文——先上線「復華官方 Threads 動態」，過審後自動變公開搜尋
  （同一支端點，行為隨權限升級，程式不用改）。
- App 審核要準備的：App 用途說明（品牌聲量監測、唯讀、不儲存全文）、示範影片。

### Phase 2：Facebook 自家粉專動態
- Page token 讀自家粉專貼文＋讚/留言/分享數（`pages_read_engagement`，粉專管理員授權即可、不需公開內容審核）。
- 復用 `arm/connectors/social/facebook.py`；粉專清單在 `config/social_fb_pages.json`。
- 他人粉專公開內容（Page Public Content Access）審核門檻最高、對本工具增量有限 → **暫緩**。

### Phase 3：Instagram hashtag
- 需求：IG 帳號轉**商業/創作者**＋綁定 FB 粉專（個人帳號 API 全面不可用）。
- hashtag 搜尋（Instagram Public Content Access 審核後）：**每帳號 7 天 30 個 hashtag**——
  固定只搜 `#復華投信`、`#00929` 等 2～4 個，額度即可控。
- 自家帳號貼文＋觸及洞察不需公開內容審核，可與 Phase 2 同批上。

## 維運注意
- **Token 60 天過期**：三平台 token 皆需續期。失效時比照 `YOUTUBE_API_KEY` 模式——誠實降級
  ＋ CI 日誌印提示（`fetch_fund_news.py` 每輪可見），不壞版；可另設每 50 天的 Routine 提醒續期。
- **額度**：Threads 2,200/24h、IG 200 req/h＋30 hashtag/7 天——本工具每日輪次個位數查詢，皆遠低於上限。
- **不走非官方爬蟲**（Apify 等第三方刮取服務違反平台 ToS，與本 repo 授權註記原則不符）。

## 查證來源（2026-08-06）
- Threads keyword search：[Meta 官方文件](https://developers.facebook.com/docs/threads/keyword-search/)、[ppc.land 報導](https://ppc.land/meta-introduces-new-search-and-analytics-features-to-threads-api-platform/)
- IG Graph API 現況：[Meta 官方 Instagram Platform 文件](https://developers.facebook.com/docs/instagram-platform/overview/)、[2026 開發者指南](https://www.netrows.com/blog/instagram-graph-api-guide-2026)
