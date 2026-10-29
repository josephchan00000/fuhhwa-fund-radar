# 復華新聞與社群

> 「復華新聞・社群」區塊：新聞從哪抓、四層過濾、Google News 洗日期；社群 PTT、YouTube 三層清單與額度、強基金、分類篩選、落檔防呆。
> 原始資料：CLAUDE.md「已知環境限制與防呆」段的復華新聞與社群各條；規劃 `docs/social_api_plan.md`；程式：`arm/fundnews.py`、`arm/connectors/gnews.py`。
> 最後更新：2026-10-29
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

## 現在怎麼運作

區塊叫「復華新聞・社群」（2026-08-12 前叫「基金相關新聞・社群」；nav、區塊標題、內層標題、鮮度列標籤同步改，section id `#fundnews` 不動）。
抓取全在 CI（容器 proxy 擋 stockfeel、PTT、fundhot），落檔 `data/fund_news.json`，整份「全空不覆寫」只看 brand/funds/social 全空。

### 新聞從哪抓

- Google News RSS 查「品牌＋基金基底名」＋**產品層** `fetch_etf_products()` 逐檔查（`"代碼" OR "產品名"`）：清單 `fh_products()`＝etfwatch watch_tuples（名稱含復華）＋ UPCOMING（含未派碼檔）——
  **募集中新檔（00409A 型）自動涵蓋、掛牌轉正零維護**；`_fh_codes()` 同步吃到 → PTT／YouTube 相關性也認得募集期代碼。群組 `fund_ids` 恆空＋帶 `code` 欄，渲染端據此掛代碼章（無基金詳情卡可跳）。
- RSS 直抓**股感 StockFeel `/feed/`**（WordPress 全站 feed，`feed_relevant`＝含品牌詞或自家代碼才留；CI 可達性看首輪日誌 grep `[fundnews]`，失敗 fail-open 只損失此源）；feed 分流 `route_feeds_to_funds` 認得產品代碼。
- **品牌詞層 `BRAND_TERMS=("復華","金複合")`**：金複合投資法/理財機器人的討論常不寫「復華」，PTT／YouTube／RSS／強基金相關性判準（`_brand_hit`）都認（「金管家」他行也在用、不進清單，靠「復華金管家」寫法自然命中）。

### 四層過濾（全在 `arm/fundnews.py`；讀取端 `sanitize()` 同一套，既有落檔的垃圾連結下輪重建即消失，不必等重抓）

1. **標題 `_JUNK_TITLE`**：「公開說明書／信託契約」與「暫停/恢復＋銷售・申購・受理」公告類轉貼＝非新聞；報價頁「的總覽/的買賣訊號/報酬走勢/淨值及折溢價」（URL 層之外的第二道）；
   **比較誘餌＝農場**：「該怎麼選/該選哪一檔/怎麼挑」問句與「答案在這」賣關子式。**股感式產品解析文（「00409A…｜成分股？配息？優缺點？」多段主題羅列）不是農場、勿誤殺**——那正是使用者要的內容。
2. **網址 `_JUNK_URL`**（標題不一定帶 junk 詞、URL 才是決定性特徵）：**ezfunds.com.tw 整站**（基金銷售平台、被收錄內容全是公告轉貼）、invest.cnyes 基金總覽/買賣訊號頁、fund.cnyes 詳情頁、
   MoneyDJ ETF 報價頁（`/etf/`、`/funddj/yb`）、**CMoney 論壇文（cmoney.tw/forum/）**、Yahoo quote 頁。
3. **日期**（Google News RSS 的 pubDate 不可信）：①**`_title_stale_year()`**：標題自帶「年＋月/年度」日期式樣（民國 1xx 年 +1911／西元 20xx 年）且最近年份早於前年 → 舊文重收、剔除
   （「創2020年以來新高」式引述不受影響——年後接「以來」非月份）；②台帳 `data/fund_news_seen.json`（**必須入庫**，.gitignore 例外＋daily.yml add 皆已設）記每標題「最早見過的日期」——
   同標題再被重標新日期也拉回最早值，出 7 天窗即剔除；③CI 端 `gnews.verify_published()`（`arm/connectors/gnews.py`）解原文頁驗真實刊出日（每輪限 `VERIFY_BUDGET`=24 篇新項目、結果入台帳不重驗），
   驗出窗外→剔除、窗內較早→改標並把連結換成原文 URL。`gnews.resolve()` 走 Google 內部 batchexecute 端點（版式會漂移）——失效時 fail-open 沿用 pubDate、CI 日誌印原因（grep `[gnews]`／`[fundnews]`），
   屆時只修 gnews 解析層、策略層（date_verify）不動。
4. **負面詞**（2026-08-12 使用者重申「不要抓負面的文章」）：司法弊案之外補市況/績效負面（慘賠/套牢/跌破/重挫/暴跌/腰斬/清算/下市/贖回潮/規模縮水…），品牌/產品/基金/社群全適用。

### 社群

相關性判準＝品牌詞**或**自家 ETF 代碼獨立詞（`_code_hit`，00929 討論串常不寫「復華」）。社群清單上方 `#socbar` chips＝全部／ETF／主動ETF／基金／市場趨勢（帶數量、空分組不渲染）：
**全部社群項目**（官方/相關/熱門/PTT/強基金）都經 `fundnews.social_group()` 掛 `data-fcat`（etf/active/fund/trend/other；other 僅「全部」可見），點 chip 前端 toggle `.fnit.fhide`——CSS 三處已一起加（隱藏規則/chip 樣式 `.sg`/active 態，2026-07-31 教訓）。

- **PTT＝股票板＋基金板雙板**（2026-08-07 使用者需求）：`fetch_ptt()` 依 `PTT_BOARDS` 兩板各抓 3 頁、跨板以網址去重、項目帶 `board` 供渲染標板名。
- **YouTube**（社群＝PTT＋YouTube 與三層清單：2026-08-06 使用者需求與規劃）：`fundnews.fetch_youtube()` 走 YouTube Data API v3，金鑰＝Actions secret `YOUTUBE_API_KEY`（v0.12 舊金鑰未曾建成 repo secret、已隨舊容器佚失，2026-08-06 使用者重設一把；本機備援 `~/.fh_youtube_key`）。
  無金鑰／被擋回 []、只剩 PTT，fetch_fund_news.py 會印「未設 YOUTUBE_API_KEY」提示。三層清單共用 seen 去重、官方優先：
  1. **官方** `YT_OFFICIAL_CHANNELS`——**兩個頻道**（使用者提供）：@fhifund 主頻道（UCD3J90bNoHykt6Eru8YxUmQ，金管家系列在此）＋@fhetf ETF 專屬頻道（handle 執行期以 channels.list forHandle 解析；config 鍵吃 UC id 或 @handle 皆可）
     ——近窗**全部上傳**（uploads 播放清單 UC→UU、每頻道 1 單位，依日期序、掛「官方」章）。
  2. **相關**＝search 4 組（復華投信／復華 基金／復華 ETF／00929）依觀看數**取前 3**；標題只寫自家 ETF 代碼、沒寫「復華」的也算（`_fh_codes()` 動態取 etfwatch 清單中名稱含復華者）。
     代碼須為**獨立詞**、**集數式前綴**（Ep -／第…／No. 接代碼）不算命中、**純代碼命中須含漢字**（relevanceLanguage 只是偏好非過濾）。自家內容歸這層不重複。
  3. **市場熱門**（原「同業熱門」）＝`YT_PEER_QUERIES` **7 組主題桶**（台股 ETF／高股息 ETF／ETF 投資／債券 ETF／基金 投資／主動式 ETF／台股）各近 `YT_PEER_FRESH_DAYS`=5 天依觀看數搜尋
     （maxResults=25——**search 成本與 10 筆同為 100 單位**，放大 pool 零額度成本）。`yt_peer_relevant` 三路徑任一即收：**同業代碼**（`_peer_codes()`）／ETF・基金**主題詞**（高觀看的泛 ETF 討論多不寫代碼）／
     **市場趨勢詞**（`_YT_TREND`：大盤行情、總經政策、資產配置）。排除：純海外（美股代碼/「美股ETF」連語且無台股代碼）、無漢字、**個股本位**（`_STOCK_FOCUS` 只驗標題：知名個股名／個股・飆股・選股・當沖・漲停／
     非 00 開頭 4 碼代號——**僅在無任何產品面（主題詞/台股 ETF 代碼）時生效**，「台積電還能買嗎」擋、「台股ETF 台積電權重過半」收）。再經 `_select_peers`：**同片跨頻道去重**（聯播節目三立/94要賺錢同片異 id，
     正規化＝去尾端「｜頻道名」段）→ **觀看門檻** `YT_PEER_MIN_VIEWS`=5000（全數未達才 fallback 取前 2、不留白）→ **分類配額**（`yt_topic` 七類：債券／高股息／主動式／市值型／基金／市場趨勢／綜合，
     **每類 2、總上限 10**——viewCount 排序易被單一題材洗版，配額保多樣性）；`cat` 一律寫入、儀表板章「熱門・{類別}」（綜合＝素「熱門」、舊落檔無 cat 顯示原「同業熱門」）。
  - 日文：`fundnews._is_japanese()`＝平/片假名**字母** ぁ-ゖ／ァ-ヺ（排除台灣商品名風格用字「の」），抓取端 `yt_relevant`/`yt_peer_relevant` 與讀取端 `_social_ok` 都接。
    讀取端 `sanitize()`：非官方且標題無漢字、黑名單 `YT_BLOCK_IDS` 一律剔除——舊落檔與 `_carry_social` 沿用款不必等重抓即消失。
  - **時長 ≤3 分標 Shorts**（連結走 /shorts/、來源標「YouTube Shorts」）。
  - **額度**：search 11 組 ×100（相關 4＋熱門 7）＋playlistItems 2＋channels 1＋videos.list **分批**（單次上限 50 支）數單位 ≈每輪 1,110 單位（日限 10,000）；配額於太平洋時間午夜（台北 15~16 時）重置。
- **強基金 fundhot**（`fetch_fundhot`）：台灣最大共同基金討論社群、金複合討論主場；渲染＝💬 章＋「強基金・板名」來源標。兩套站並抓（新站 `fundhot.com/forum/{分類}/{slug}/{id}` 列表頁 regex＋舊 phpBB
  `forum.fundhot.com/feed.php?mode=topics` Atom），同標題跨源去重、單源失敗不牽連；新站解析 0 筆會印**結構探針**片段（grep `[fundhot]`）供一輪收斂。
  - 新站種子＝實際存在的分類（股票基金／ETF／資產配置）＋由**總覽頁話題連結的分類段自尋**（`FUNDHOT_MAX_PAGES`=6 上限），標頭 `FUNDHOT_HEADERS`（Accept／Accept-Language／Referer，UA 仍誠實標研究用途）——
    但實際只拿得到 `/forum` 總覽頁（見坑）。`feed.php?mode=topics` 對訪客常被關閉 → 加舊站「最新討論」HTML 備援（`FUNDHOT_ACTIVE`＝`search.php?search_id=active_topics`，`parse_phpbb_topics`；
    href 內分隔字元是 **`&amp;`** 不是 `&`，網址正規化成 `viewtopic.php?t={id}` 去掉 sid，否則 first_seen 台帳與去重永遠對不上同一篇）。
  - 日期：新站列表是 `<span class="text-auxiliary …">10小時前</span>` 這種**相對時間**，夾在標題 `</a>` 與作者連結之間 → `parse_fundhot_page` 有 `<time datetime>` 用它，否則 `_rel_date()` 解析成真日期
    （分鐘/小時照實扣，清晨跑時「10小時前」＝昨天），窗口切在**下一個 `<a `** 之前以免抓到下一列的時間；不猜純文字日期（猜錯會把鄰列日期安到別篇上）。有日期者由 `fetch_fundhot` 照時窗老化；
    無日期者由 `_stamp_first_seen()` 記**首見日**（同 url 沿用最早值），`_social_in_window()` 據以老化、儀表板標「首見 M/D」。
- **FB／IG／Threads 擴充規劃見 `docs/social_api_plan.md`**（2026-08-06 查證：Threads 公開關鍵字搜尋為第一優先、需使用者建 Meta App＋過審 `threads_keyword_search`；FB 只做自家粉專、IG hashtag 額度緊排最後）。

### 落檔防呆

- **`_carry_social` 來源級沿用**：單一平台本次全空且既有落檔該平台非空 → 沿用舊項目（ISO 日期出 7 天窗剔除、看點重算），平台清單含 fundhot；只擋「單平台全空」（剩 1 支不觸發）、時窗檢查對「無 ISO 日期」一律豁免。
- **儀表板 `_yt_watch_chip`**：social 段存在而 youtube 0 支 → 「網頁更新時間」列紅章，配 SOP 步驟 9⑦ 的每日驗證（根因與補救見 9⑦：push 觸發用舊分支 workflow 檔）。

## 不能改的規則

- 舊文重收的同型問題先想「標題有沒有自帶年代」這條，不要只補站台黑名單。
- 外語誤收的判準優先想「該語言的獨有字符」，別逐詞窮舉外語詞彙；**用 Unicode 區段當語言判準時，先確認區段內的「記號」是否也被目標語言以外的文字共用**，並在上線前拿既有落檔全量跑一次誤殺檢查。
- **YouTube 勿再隨意加查詢組，加組前先算這筆帳**；密集除錯日請把「YouTube 縮水」當預期現象，等重置後一輪補回，勿當新 bug 追。
- **強基金取得範圍就是 `/forum` 總覽頁那一份清單，別再往「多加幾支網址、換標頭」修**（兩輪已證偽）；真要擴，只剩「偽裝瀏覽器 UA」或放棄此來源，那是要先問使用者的取捨。
  **強基金天生是低流量來源，別期待每天有新卡**（總覽頁本身有在更新，探針見新話題 id 13930，只是符合復華相關性判準的討論本來就少）。
- 抓取一律 `retries=1／timeout=12`——整站被擋時預設 3×25s 會讓每頁空轉逾一分鐘（每日 routine 全長才 ~80 秒）。失敗印訊息本體，不靜默 `except: break`／`except: continue`。

## 踩過的坑

- **Google News 洗日期（2026-08-06 使用者抓包「基金新聞很多都是舊的」）**：Google 重新收錄舊頁時 pubDate 變 re-crawl 時間——傘型ETF 4/15 掛牌稿（工商時報 4/14）標 08-01、
  中租基智網（ezfunds）一年前的公告標 08-04，各以「新聞」姿態掛版整週。修＝日期三道（`_JUNK_TITLE` 擋公告轉貼、台帳、`verify_published`）。
- **品質重規劃（2026-08-12 使用者抓包：股感 00409A 開募文全漏、清單全是「跳到基金網頁」的報價頁與 CMoney 重複比較文）**：新聞查詢過去只有「品牌＋基金基底名」，自家 ETF 完全不在清單。
  修＝產品層、`_JUNK_URL`（`_JUNK_TITLE` 同輪補報價頁詞）、比較誘餌、負面詞擴充；加股感 feed、`VERIFY_BUDGET` 16→24。同日第二輪（使用者追加）：區塊改名、品牌詞層、社群加強基金。
- **ezfunds 二度肇事（2026-08-17 使用者抓包：民國110/111年「台灣好收益暫停銷售」公告以 08-16 姿態上版）**：08-06 與本次皆它。修＝`fundnews._JUNK_URL` 剔除整站、`_JUNK_TITLE` 補公告詞、通用防呆 `_title_stale_year()`。
- **一輪沒金鑰就把 7 則社群洗成 0（2026-08-07 踩坑）**：整份「全空不覆寫」防呆擋不住單段全空。修＝`_carry_social`＋`_yt_watch_chip` 兩道。
- **代碼誤收**：曾誤收日文單字卡課號「L#00929」→ 獨立詞；**獨立詞仍不夠**（2026-08-14 使用者抓包可蘭經朗誦《Surah Rahman | Ep - 00929》以集數編號誤入）→ 集數前綴、含漢字、`YT_BLOCK_IDS`。
- **熱門觀看數太少（2026-08-14 使用者：「觀看數超級少……應該會有超級多討論 ETF 等等基金類的影片」）**：舊判準只收同業代碼，泛 ETF 討論全殺 → 第三層擴編；
  2026-08-15 再擴「投資相關（不要個股）」（使用者「投資相關的（不要個股）」）＝趨勢詞＋個股本位排除。同日清單太長（使用者：「太長了…有分類可以點然後就可以篩選」）→ 分類篩選 chips。
- **videos.list 靜默截斷（2026-08-14 修）**：舊版 `ids[:50]` 其餘 0 觀看沉底 → 分批。
- **誤收日文影片（2026-08-17 使用者：「這是日本的影片我只要台灣的」）**：「標題須含漢字」**擋不住日文**（日文本來就用漢字——両学長「米国高配当株ETF」滿足漢字＋主題詞 ETF，海外排除又只認「美股/美國」不認「米国」）。
  決定性特徵＝**假名字母** → `_is_japanese()`，該支 FAkMraqLuko 入 `YT_BLOCK_IDS`。
  **同日第二坑（使用者：「YouTube 影片怎麼都不見了」）：範圍不可含片假名「記號區」**——首版用整段 `[ぁ-ゟ゠-ヿ]`，把 **U+30FB「・」與 U+30FC「ー」**（台灣標題極常用的全形間隔號／長音符）當日文，**抓取端整批誤殺、YouTube 從 14 支砍到剩 1 支**；
  `_carry_social` 剩 1 支不觸發沿用，落檔直接被洗掉。修＝限縮到假名字母（當時只測了 4 個新造標題、沒掃既有 14 支）。
- **單日多輪 CI 重跑把配額燒完（2026-08-17 實戰）**：連環修正日 dispatch 約 10 輪 → search 全 403 quotaExceeded，日誌型態＝「官方 1・相關 0・同業 0」（殘額 <100 單位時 search 被拒、1 單位的 playlist 仍過），
  隔輪自癒，落檔靠 `_carry_social` 不會全滅但會縮水。修＝搜尋層錯誤印進 CI 日誌（`_search_all`）。
- **強基金「都沒有在更新」＝三個結構性缺陷疊加（2026-09-01 使用者回報；同一組項目連掛一週以上）**：CI 日誌 `[fundhot]` 每天印三行失敗、卻沒人看得出原因。
  ①**取得範圍只剩總覽頁一頁**：舊種子的 `/forum/股票` 是舊 phpBB 版名、新站沒有此分類；改種子＋自尋後**當輪 CI 揭曉真正原因＝全部 403，不是網址寫錯**：`/forum` 總覽頁 200，
  但**每一支分類頁與舊站 feed.php／search.php 全部 HTTP 403**——站方對「不像瀏覽器」的請求擋動態路由；補 `FUNDHOT_HEADERS` **無效、第二輪照樣全 403**——**已確定是 UA／IP 層的擋機房行為**。
  ②**失敗只印 `type(e).__name__`**＝「RuntimeError」，看不出是 404 還是被擋（`get_bytes` 的訊息本體已含 URL 與 HTTP 狀態，只是被丟掉）；同型的靜默 `except: break` 也存在於 `fetch_ptt`
  （「PTT 0 則」被擋還是查無討論，日誌長得一樣）——兩處都改印訊息本體。③**新站列表頁項目沒有日期**，時窗豁免 → 來源掛掉時原地凍結、看起來就像今天的新討論 → 首見日老化、舊站 HTML 備援；
  ③-2 **日期在版式裡、只是不是 `<time>`**（加寬探針後一輪解決）→ `_rel_date()`，first_seen 仍留著當後備。
