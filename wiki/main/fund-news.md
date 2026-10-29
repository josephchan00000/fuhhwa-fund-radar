# 復華新聞與社群

> 「復華新聞・社群」區塊的新聞從哪裡抓、標題／網址／日期／負面詞四層過濾、Google News 洗日期與 ezfunds 的坑；社群平台細節在 [復華社群](fund-news-social.md)。
> 原始資料：CLAUDE.md「已知環境限制與防呆」段的「Google News RSS 的 pubDate 不可信」「基金新聞品質重規劃」「舊公告被 Google 洗日期」三條（社群那幾條整理在 [復華社群](fund-news-social.md)）；程式：`arm/fundnews.py`、`arm/connectors/gnews.py`、`scripts/fetch_fund_news.py`
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

主頁區塊叫「復華新聞・社群」（2026-08-12 前叫「基金相關新聞・社群」；nav、區塊標題、內層標題、鮮度列標籤一起改過，section id `#fundnews` 沒動）。
上半是新聞、下半是社群。抓取全在 CI（`scripts/fetch_fund_news.py`；容器 proxy 擋 Google News、stockfeel、PTT、fundhot，見 [容器的限制](../env/container.md)），
落檔 `data/fund_news.json`。整份防呆＝「全空不覆寫」（本次 brand/funds/social 全空、既有落檔非空就不覆寫）；單一社群平台全空另有 `_carry_social` 沿用（見社群頁）。

### 新聞從哪裡抓

| 來源 | 查什麼 | 留哪些 |
|---|---|---|
| Google News RSS：品牌與基金 | 「品牌＋基金基底名」 | 過下面四層 |
| Google News RSS：產品層 `fetch_etf_products()` | 每一檔自家 ETF 查 `"代碼" OR "產品名"` | 過下面四層 |
| 股感 StockFeel `/feed/`（RSS 直抓） | WordPress 全站 feed | `feed_relevant`＝含品牌詞或自家代碼才留 |

- 產品清單 `fh_products()`＝etfwatch watch_tuples（名稱含復華）＋ UPCOMING（含未派碼檔）：**募集中新檔（00409A 型）自動涵蓋、掛牌轉正零維護**。
  產品群組 `fund_ids` 恆空、帶 `code` 欄，渲染端據此掛代碼章（沒有基金詳情卡可跳）。
- feed 分流 `route_feeds_to_funds` 認得產品代碼。
- 股感 feed：容器 proxy 擋 stockfeel，CI 可達性看首輪日誌 grep `[fundnews]`；失敗 fail-open，只損失這一個來源。

### 怎麼判斷「跟復華有關」

- **品牌詞** `BRAND_TERMS=("復華","金複合")`：金複合投資法／理財機器人的討論常不寫「復華」。PTT／YouTube／RSS／強基金的相關性判準（`_brand_hit`）都認。
  「金管家」他行也在用、不進清單，靠「復華金管家」寫法自然命中。
- **自家代碼** `_fh_codes()`：同步吃到產品清單 → PTT／YouTube 相關性也認得募集期代碼。

### 四層過濾

抓取端與讀取端 `sanitize()` 同一套：改了過濾規則，既有落檔的垃圾連結下輪重建即消失，不必等重抓。

1. **標題 `_JUNK_TITLE`**
   - 公告類轉貼不是新聞：「公開說明書／信託契約」、「暫停/恢復＋銷售・申購・受理」。
   - 報價頁標題：「的總覽/的買賣訊號/報酬走勢/淨值及折溢價」（網址層之外的第二道）。
   - 比較誘餌＝農場：「該怎麼選/該選哪一檔/怎麼挑」問句、「答案在這」賣關子式。
     **股感式產品解析文（「00409A…｜成分股？配息？優缺點？」多段主題羅列）不是農場、勿誤殺**——那正是使用者要的內容。
2. **網址 `_JUNK_URL`**（標題不一定帶 junk 詞，URL 才是決定性特徵）：**ezfunds.com.tw 整站**（基金銷售平台，被收錄的內容全是公告轉貼）、
   invest.cnyes 基金總覽／買賣訊號頁、fund.cnyes 詳情頁、MoneyDJ ETF 報價頁（`/etf/`、`/funddj/yb`）、**CMoney 論壇文（cmoney.tw/forum/）**、Yahoo quote 頁。
3. **日期**（Google News 的 pubDate 不可信，三道）：
   - 標題自帶年代 `_title_stale_year()`：標題有「年＋月/年度」日期式樣（民國 1xx 年 +1911／西元 20xx 年）且最近年份早於前年 → 舊文重收、剔除。
     「創2020年以來新高」式引述不受影響（年後接「以來」，不是月份）。
   - 台帳 `data/fund_news_seen.json`：記每個標題「最早見過的日期」，同一標題又被重標新日期也拉回最早值，出 7 天窗即剔除。
   - CI 端 `gnews.verify_published()` 解原文頁驗真實刊出日：每輪最多 `VERIFY_BUDGET`=24 篇新項目（2026-08-12 由 16 調高），結果入台帳不重驗；
     驗出在窗外 → 剔除，窗內但較早 → 改標日期並把連結換成原文 URL。
     `gnews.resolve()` 走 Google 內部 batchexecute 端點（版式會漂移），失效時 fail-open 沿用 pubDate、CI 日誌印原因（grep `[gnews]`／`[fundnews]`）。
4. **負面詞**（使用者 2026-08-12 重申「不要抓負面的文章」）：司法弊案之外，市況／績效負面也擋（慘賠/套牢/跌破/重挫/暴跌/腰斬/清算/下市/贖回潮/規模縮水…），
   品牌／產品／基金／社群全適用。

### 社群（細節見 [復華社群](fund-news-social.md)）

| 平台 | 抓什麼 |
|---|---|
| PTT | 股票板＋基金板 |
| YouTube | 三層清單：官方（兩個頻道）、相關（search 4 組）、市場熱門（7 組主題桶） |
| 強基金 fundhot | 新站 `/forum` 總覽頁＋舊站 phpBB |

社群清單上方有分類篩選 chips（全部／ETF／主動ETF／基金／市場趨勢）。FB／IG／Threads 還沒做，規劃在 `docs/social_api_plan.md`。

## 不能改的規則

- `data/fund_news_seen.json` **必須入庫**（.gitignore 例外＋daily.yml add 皆已設）。
- 舊文重收的同型問題，先想「標題有沒有自帶年代」這條，不要只補站台黑名單。
- `gnews.resolve()` 失效時只修 gnews 解析層，策略層（date_verify）不動。
- 股感式產品解析文不是農場，比較誘餌規則不可擴到它。

## 踩過的坑

- **Google News 把舊文標成近期日期（2026-08-06 使用者抓包「基金新聞很多都是舊的」）**：Google 重新收錄舊頁時 pubDate 變成 re-crawl 時間。
  實例：傘型ETF 4/15 掛牌稿（工商時報 4/14）標成 08-01、中租基智網（ezfunds）一年前的公告標成 08-04，各以「新聞」姿態掛版整週。
  修法＝三道防線（都在 `arm/fundnews.py`＋`arm/connectors/gnews.py`）：①「公開說明書／信託契約」公告類轉貼入 `_JUNK_TITLE`（`sanitize()` 讀取端也濾、舊落檔立即生效）；
  ②台帳 `data/fund_news_seen.json`；③`gnews.verify_published()`（`VERIFY_BUDGET` 當時是 16）。
- **自家新檔全漏、清單全是報價頁（2026-08-12）**：使用者抓包股感 00409A 開募文全漏、清單全是「跳到基金網頁」的報價頁與 CMoney 重複比較文。
  原因：新聞查詢只有「品牌＋基金基底名」，自家 ETF 完全不在清單；報價頁、論壇文的標題不帶 junk 詞。
  修法＝四層（全在 `arm/fundnews.py`）：①產品層 `fetch_etf_products()`；②URL 級過濾 `_JUNK_URL`（標題層 `_JUNK_TITLE` 同輪補報價頁詞當第二道）；
  ③比較誘餌＝農場；④負面詞擴充。同輪加股感 `/feed/`、`VERIFY_BUDGET` 16→24。
- **ezfunds 二度肇事：民國年舊公告上版（2026-08-17）**：使用者抓包民國110/111年「台灣好收益暫停銷售」公告以 08-16 姿態上版；08-06 與這次都是 ezfunds。
  修法三層：①`fundnews._JUNK_URL` 把 **ezfunds.com.tw 整站**剔除；②`_JUNK_TITLE` 補「暫停/恢復＋銷售・申購・受理」公告詞；
  ③通用防呆 `_title_stale_year()`。`sanitize()` 讀取端同一套。

## 歷史

- 2026-08-06：Google News 洗日期三道防線；社群加 YouTube（見社群頁）。
- 2026-08-07：PTT 改雙板、社群防呆兩道（見社群頁）。
- 2026-08-12：品質重規劃四層、加股感 feed、區塊改名「復華新聞・社群」、加品牌詞層、社群加強基金。
- 2026-08-14～08-15：YouTube 第三層擴編、分類篩選 chips（見社群頁）。
- 2026-08-17：ezfunds 二度肇事、加 `_title_stale_year()`；同日社群的日文影片兩坑、YouTube 配額燒完（見社群頁）。
- 2026-09-01：強基金「都沒有在更新」的三個缺陷（見社群頁）。
