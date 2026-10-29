# 復華社群：PTT、YouTube、強基金

> 社群三個平台怎麼抓、YouTube 三層清單與額度、分類篩選、落檔防呆；日文影片、配額燒完、強基金 403 等坑。
> 原始資料：CLAUDE.md「已知環境限制與防呆」段的「社群討論＝PTT＋YouTube」「強基金都沒有在更新」「社群 YouTube 誤收日文影片」三條，與「基金新聞品質重規劃」的⑥⑦（從 [復華新聞與社群](fund-news.md) 拆出來）；
> 規劃 `docs/social_api_plan.md`；程式：`arm/fundnews.py`、`scripts/fetch_fund_news.py`、`arm/fund_dashboard.py`
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

三個平台都在 CI 抓（容器 proxy 擋 PTT、fundhot）。相關性判準都一樣：品牌詞（`_brand_hit`：「復華」或「金複合」，見 [復華新聞與社群](fund-news.md)）
**或**自家 ETF 代碼獨立詞（`_code_hit`；00929 討論串常不寫「復華」）。

| 平台 | 抓什麼 | 程式 | 版面 |
|---|---|---|---|
| PTT | 股票板＋基金板（`PTT_BOARDS`），各抓 3 頁，跨板以網址去重，項目帶 `board` | `fetch_ptt()` | 標板名 |
| YouTube | 三層清單（下一節），走 YouTube Data API v3 | `fundnews.fetch_youtube()` | 「官方」章、「熱門・{類別}」章 |
| 強基金 fundhot | 台灣最大共同基金討論社群、金複合討論主場；新站＋舊站兩套並抓 | `fetch_fundhot` | 💬 章＋「強基金・板名」來源標 |

### YouTube 三層清單

金鑰＝Actions secret `YOUTUBE_API_KEY`（2026-08-06 使用者重設一把；v0.12 舊金鑰未曾建成 repo secret、已隨舊容器佚失；本機備援 `~/.fh_youtube_key`）。
無金鑰／被擋就回 []、只剩 PTT，`fetch_fund_news.py` 會印「未設 YOUTUBE_API_KEY」提示。

1. **官方** `YT_OFFICIAL_CHANNELS`：**兩個頻道**（使用者提供）——@fhifund 主頻道（UCD3J90bNoHykt6Eru8YxUmQ，金管家系列在此）＋@fhetf ETF 專屬頻道
   （handle 執行期以 channels.list forHandle 解析；config 鍵吃 UC id 或 @handle 皆可）。近窗**全部上傳**（uploads 播放清單 UC→UU、每頻道 1 單位），依日期序、掛「官方」章。
2. **相關**：search 4 組（復華投信／復華 基金／復華 ETF／00929）依觀看數**取前 3**。標題只寫自家 ETF 代碼、沒寫「復華」的影片也算
   （`_fh_codes()` 動態取 etfwatch 清單中名稱含復華者）。代碼命中要過三道：代碼須為**獨立詞**；**集數式前綴**（Ep -／第…／No. 接代碼）不算命中；
   **純代碼命中須含漢字**（relevanceLanguage 只是偏好、不是過濾）。自家內容歸這一層，不和第三層重複。
3. **市場熱門**（原「同業熱門」）：`YT_PEER_QUERIES` **7 組主題桶**（台股 ETF／高股息 ETF／ETF 投資／債券 ETF／基金 投資／主動式 ETF／台股），
   各搜近 `YT_PEER_FRESH_DAYS`=5 天、依觀看數排序，maxResults=25（**search 成本與 10 筆同為 100 單位**，放大 pool 零額度成本）。
   - 收：`yt_peer_relevant` 三路徑任一——**同業代碼**（`_peer_codes()`）／ETF・基金**主題詞**（高觀看的泛 ETF 討論多不寫代碼）／
     **市場趨勢詞**（`_YT_TREND`：大盤行情、總經政策、資產配置）。
   - 排除：純海外（美股代碼／「美股ETF」連語且無台股代碼）、無漢字、**個股本位**（`_STOCK_FOCUS` 只驗標題：知名個股名／個股・飆股・選股・當沖・漲停／
     非 00 開頭 4 碼代號；**僅在無任何產品面〔主題詞／台股 ETF 代碼〕時生效**——「台積電還能買嗎」擋、「台股ETF 台積電權重過半」收）。
   - 再經 `_select_peers`：**同片跨頻道去重**（聯播節目三立/94要賺錢同片異 id，正規化＝去尾端「｜頻道名」段）
     → **觀看門檻** `YT_PEER_MIN_VIEWS`=5000（全數未達才 fallback 取前 2、不留白）
     → **分類配額**（`yt_topic` 七類：債券／高股息／主動式／市值型／基金／市場趨勢／綜合，**每類 2、總上限 10**；viewCount 排序易被單一題材洗版，配額保多樣性）。
   - `cat` 一律寫入，儀表板章「熱門・{類別}」（綜合＝素「熱門」；舊落檔沒有 cat 顯示原「同業熱門」）。

三層共用 seen 去重、官方優先。各層共通的排除：
- 日文：`fundnews._is_japanese()`＝平/片假名**字母** ぁ-ゖ／ァ-ヺ（排除台灣商品名風格用字「の」），抓取端 `yt_relevant`/`yt_peer_relevant` 與讀取端 `_social_ok` 都接。
- 讀取端 `sanitize()`：非官方且標題無漢字、黑名單 `YT_BLOCK_IDS` 一律剔除——舊落檔與 `_carry_social` 沿用款不必等重抓即消失。

**時長 ≤3 分標 Shorts**：連結走 /shorts/、來源標「YouTube Shorts」。

**額度帳**（日限 10,000）：search 11 組 ×100（相關 4＋熱門 7）＋playlistItems 2＋channels 1＋videos.list **分批**（單次上限 50 支）數單位 ≈ 每輪 1,110 單位。
配額於太平洋時間午夜（台北 15~16 時）重置。

### 分類篩選 chips

社群清單上方 `#socbar` chips＝全部／ETF／主動ETF／基金／市場趨勢（帶數量、空分組不渲染）。**全部社群項目**（官方/相關/熱門/PTT/強基金）
都經 `fundnews.social_group()` 掛 `data-fcat`（etf/active/fund/trend/other；other 僅「全部」可見），點 chip 前端 toggle `.fnit.fhide`。
CSS 三處一起加（隱藏規則／chip 樣式 `.sg`／active 態；2026-07-31 教訓，見 [ETF 詳情卡畫面](etf-detail.md)）。

### 強基金怎麼抓

- **兩套站並抓**：新站 `fundhot.com/forum/{分類}/{slug}/{id}` 列表頁 regex＋舊 phpBB `forum.fundhot.com/feed.php?mode=topics` Atom；同標題跨源去重、單源失敗不牽連。
- **新站實際只拿得到 `/forum` 總覽頁那一份清單**（分類頁全部 HTTP 403，見坑）。種子是實際存在的分類（股票基金／ETF／資產配置）＋由總覽頁話題連結的分類段自尋，
  上限 `FUNDHOT_MAX_PAGES`=6；標頭 `FUNDHOT_HEADERS`（Accept／Accept-Language／Referer，UA 仍誠實標研究用途）。
- **舊站備援**：`feed.php?mode=topics` 對訪客常被關閉 → 加舊站「最新討論」HTML（`FUNDHOT_ACTIVE`＝`search.php?search_id=active_topics`，`parse_phpbb_topics`）。
  href 內分隔字元是 **`&amp;`** 不是 `&`；網址正規化成 `viewtopic.php?t={id}` 去掉 sid，否則 first_seen 台帳與去重永遠對不上同一篇。
- **日期**：新站列表是 `<span class="text-auxiliary …">10小時前</span>` 這種**相對時間**，夾在標題 `</a>` 與作者連結之間。
  `parse_fundhot_page` 先找 `<time datetime>`，沒有就用 `_rel_date()` 解析成真日期（分鐘/小時照實扣，清晨跑時「10小時前」＝昨天）；
  窗口切在**下一個 `<a `** 之前以免抓到下一列的時間。不猜其他純文字日期（猜錯會把鄰列日期安到別篇上）。
  有日期的由 `fetch_fundhot` 照時窗老化；沒日期的由 `_stamp_first_seen()` 記**首見日**（同 url 沿用最早值），`_social_in_window()` 據以老化、儀表板標「首見 M/D」。
- 新站解析 0 筆會印**結構探針**片段（grep `[fundhot]`）供一輪收斂。
- 抓取一律 `retries=1／timeout=12`。
- **強基金天生是低流量來源**：總覽頁本身有在更新（探針見新話題 id 13930），只是符合復華相關性判準的討論本來就少，別期待每天有新卡。

### 落檔防呆

- 整份「全空不覆寫」（`arm/fundnews.save()`）只看 brand/funds/social 全空，擋不住單段全空，所以另有：
- **`_carry_social` 來源級沿用**：單一平台本次全空、既有落檔該平台非空 → 沿用舊項目（ISO 日期出 7 天窗剔除、看點重算）。平台清單含 fundhot。
  只擋「單平台全空」——剩 1 支就不觸發（見下面日文影片第二坑）；時窗檢查對「無 ISO 日期」一律豁免（所以強基金沒日期的項目改用首見日老化）。
- **儀表板 `_yt_watch_chip`**：social 段存在而 youtube 0 支 → 「網頁更新時間」列紅章，配 [全部更新](../ops/daily-update.md) 步驟 9⑦ 的每日驗證
  （根因與補救也在 9⑦：push 觸發用舊分支 workflow 檔）。
- **失敗一律印訊息本體**：強基金與 `fetch_ptt` 印 `get_bytes` 的訊息（含 URL 與 HTTP 狀態）；YouTube 搜尋層錯誤由 `_search_all` 印進 CI 日誌。

### 還沒做

FB／IG／Threads 擴充規劃見 `docs/social_api_plan.md`（2026-08-06 查證：Threads 公開關鍵字搜尋為第一優先、需使用者建 Meta App＋過審 `threads_keyword_search`；
FB 只做自家粉專、IG hashtag 額度緊排最後）。

## 不能改的規則

- **YouTube 勿再隨意加查詢組，加組前先算額度帳**（每輪 ≈1,110 單位、日限 10,000）。
- **強基金的取得範圍就是 `/forum` 總覽頁那一份清單**，別再往「多加幾支網址、換標頭」修（兩輪已證偽）；真要擴，只剩「偽裝瀏覽器 UA」或放棄此來源，那是要先問使用者的取捨。
- 抓取一律 `retries=1／timeout=12`：整站被擋時預設 3×25s 會讓每頁空轉逾一分鐘（每日 routine 全長才 ~80 秒）。
- 外語誤收的判準優先想「該語言的獨有字符」，別逐詞窮舉外語詞彙。用 Unicode 區段當語言判準時，先確認區段內的「記號」是否也被目標語言以外的文字共用，
  並在上線前拿既有落檔全量跑一次誤殺檢查。
- 例外不可靜默吞掉（`except: break`、`except: continue`），要印訊息本體。
- 密集除錯日把「YouTube 縮水」當預期現象，等配額重置後一輪補回，勿當新 bug 追。

## 踩過的坑

- **一輪沒金鑰就把 7 則社群洗成 0（2026-08-07）**：push 觸發的 daily.yml 用被推分支上的 workflow 檔，那一輪 env 沒有 `YOUTUBE_API_KEY`（見 9⑦）。
  整份「全空不覆寫」只看 brand/funds/social 全空，擋不住單段全空。修法：`_carry_social` 來源級沿用＋`_yt_watch_chip` 紅章。
- **日文單字卡課號被當成 00929**：曾誤收「L#00929」。修法：代碼須為獨立詞。
- **可蘭經朗誦被當成 00929（2026-08-14 使用者抓包）**：《Surah Rahman | Ep - 00929》以集數編號誤入——獨立詞仍不夠。
  修法：集數式前綴不算命中、純代碼命中須含漢字、設 `YT_BLOCK_IDS` 指名黑名單＋`sanitize()` 讀取端同濾。
- **市場熱門觀看數太少（2026-08-14 使用者：「觀看數超級少……應該會有超級多討論 ETF 等等基金類的影片」）**：舊判準只收同業代碼，高觀看的泛 ETF 討論多不寫代碼、全被殺。
  修法：第三層擴編（主題詞、7 組主題桶、觀看門檻、分類配額）。2026-08-15 再擴「投資相關（不要個股）」（使用者「投資相關的（不要個股）」）：市場趨勢詞 `_YT_TREND`＋個股本位排除。
- **videos.list 靜默截斷（2026-08-14 修）**：舊版 `ids[:50]` 只查前 50 支，其餘 0 觀看沉底。修法：分批查（單次上限 50 支）。
- **社群清單太長（2026-08-15 使用者：「太長了…有分類可以點然後就可以篩選」）**：加「分類篩選 chips」（上面）。
- **誤收日文影片（2026-08-17 使用者：「這是日本的影片我只要台灣的」）**：「標題須含漢字」**擋不住日文**（日文本來就用漢字——
  両学長「米国高配当株ETF」滿足漢字＋主題詞 ETF，海外排除又只認「美股/美國」不認「米国」）。決定性特徵＝**假名字母** → `fundnews._is_japanese()`；
  該支 FAkMraqLuko 入 `YT_BLOCK_IDS`。
- **假名範圍含「記號區」，YouTube 從 14 支砍到剩 1 支（2026-08-17 同日，使用者：「YouTube 影片怎麼都不見了」）**：首版用整段 `[ぁ-ゟ゠-ヿ]`，
  把 **U+30FB「・」與 U+30FC「ー」**（台灣標題極常用的全形間隔號／長音符）當日文，抓取端整批誤殺；`_carry_social` 只擋「單平台全空」、剩 1 支不觸發沿用，落檔直接被洗掉。
  修法：限縮到假名字母。當時只測了 4 個新造標題、沒掃既有 14 支（所以有「上線前全量跑誤殺檢查」那條規則）。
- **單日多輪 CI 重跑把配額燒完（2026-08-17）**：連環修正日 dispatch 約 10 輪 → search 全 403 quotaExceeded，日誌型態＝「官方 1・相關 0・同業 0」
  （殘額 <100 單位時 search 被拒、1 單位的 playlist 仍過）。隔輪自癒，落檔靠 `_carry_social` 不會全滅但會縮水。
  修法：搜尋層錯誤改印進 CI 日誌（`_search_all`，不再靜默 `except: continue`）。
- **強基金「都沒有在更新」＝三個結構性缺陷疊加（2026-09-01 使用者回報）**：同一組項目連掛一週以上；CI 日誌 `[fundhot]` 每天印三行失敗，卻沒人看得出原因。
  - ① **取得範圍只剩總覽頁一頁**：舊種子的 `/forum/股票` 是舊 phpBB 版名、新站沒有此分類。改成實際存在的分類＋自尋（`FUNDHOT_MAX_PAGES`=6）後，
    當輪 CI 揭曉真正原因＝全部 403、不是網址寫錯：`/forum` 總覽頁 200，但每一支分類頁與舊站 feed.php／search.php 全部 HTTP 403——站方對「不像瀏覽器」的請求擋動態路由。
    補 `FUNDHOT_HEADERS` **無效、第二輪照樣全 403**，已確定是 UA／IP 層的擋機房行為（所以有上面「取得範圍就是總覽頁」那條規則）。
  - ② **失敗只印 `type(e).__name__`**＝「RuntimeError」，看不出是 404 還是被擋（`get_bytes` 的訊息本體已含 URL 與 HTTP 狀態，只是被丟掉）。
    同型的靜默 `except: break` 也存在於 `fetch_ptt`（「PTT 0 則」到底是被擋還是查無討論，日誌上長得一模一樣）。兩處都改印訊息本體。
  - ③ **新站列表頁項目沒有日期**：`_carry_social` 的時窗檢查對「無 ISO 日期」一律豁免 → 來源掛掉時原地凍結，版面上那欄還是空白，看起來就像今天的新討論。
    修法：當時 `parse_fundhot_page` 只在找得到 `<time datetime>` 時給 date（找不到印一次探針片段），無日期者由 `_stamp_first_seen()` 記首見日、`_social_in_window()` 老化；
    `feed.php?mode=topics` 加「最新討論」HTML 備援。
  - ③-2 **日期其實在版式裡、只是不是 `<time>`**：加寬探針後一輪解決——相對時間交給 `_rel_date()`；first_seen 仍留著當沒有日期時的後備。

## 歷史

- 2026-08-06：使用者需求：社群討論＝PTT＋YouTube；使用者規劃 YouTube 三層清單、重設金鑰；查證 FB／IG／Threads（`docs/social_api_plan.md`）。
- 2026-08-07：使用者需求 PTT 改股票板＋基金板雙板；社群防呆兩道。
- 2026-08-12：加品牌詞層（金複合）；社群加強基金 fundhot。
- 2026-08-14：第三層由「同業熱門」擴編為市場熱門；代碼命中加集數前綴與漢字兩道；videos.list 分批。
- 2026-08-15：市場趨勢詞與個股本位排除；分類篩選 chips。
- 2026-08-17：日文影片兩坑；YouTube 配額燒完、搜尋錯誤改印日誌。
- 2026-09-01：強基金三個缺陷；PTT 失敗也改印訊息本體。
