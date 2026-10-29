# ETF 持股：放棄的抓取路線

> 投信官網第一手、從頁面 HTML 撈持股、第三方站交叉驗證都已證實不可行（勿走回頭路）；保留的探針程式與六輪 CI 探針的經過。
> 原始資料：CLAUDE.md「ETF 詳情」底部區塊段的「投信官網第一手」「第三方交叉驗證」「純 HTTP 路線」與第 1～6 輪探針各條；程式：`arm/connectors/issuers/pcf.py`、`scripts/fetch_etf_holdings.py --probe`、`scripts/fetch_etf_holdings_browser.py`。
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

現在實際在用的來源（etfinfo 主＋Yahoo 驗構成；本家三檔第一手 fhtrust）見 [ETF 持股資料](etf-holdings.md)。

## 現在怎麼運作

這些路線都**不在正式路徑**，只留程式當解析層、備援或探針：

| 路線 | 結論 | 留下的程式 |
|---|---|---|
| 投信官網第一手（逐家逆向 7 輪＋無頭瀏覽器 3 輪） | **已放棄，勿走回頭路**：官網幾乎全是 SPA、持股靠 XHR，群益還在 Incapsula 防護後面；瀏覽器雖過得了 WAF，但復華等站頁面只 render 前十大、拿不到完整清單 | `fetch_etf_holdings_browser.py` 保留為備援、不排程（其「攔截 XHR＋DOM 解析＋列表頁自尋」機制若日後需要可直接復用） |
| 純 HTTP 投信官網（候選 URL＋通用解析） | 「從頁面 HTML 撈持股」是死路（第 4 輪定案） | `arm/connectors/issuers/pcf.py` 保留為解析層與備援 |
| 第三方交叉驗證（玩股網、CMoney、ETF觀測站） | **純 HTTP 已證實不可行**（2026-07-30 兩輪 CI 探針，使用者決定收在這裡） | 探針 `pcf.third_party_cands()`／`probe_third_party()`，只在 `--probe` 模式跑、不在正式路徑 |

- **為什麼要做「候選 URL＋通用解析＋探針」**：沒有跨投信統一官方端點（2026-07-29 查證：證交所／櫃買／政府開放平台皆無彙總 API，各投信自行在官網揭露）。
  `pcf.py` 每檔依序試候選來源，通用解析吃 JSON／HTML 表格／xlsx（重用 `fhtrust._parse_xlsx`），抓不到就印 HTTP 狀態／content-type／內容前段。
  已知可用型態：元大 `www.yuantaetfs.com/tradeInfo/pcf/{code}`。抓不到的檔安靜降級（該 ETF 就沒有展開明細），不影響其餘欄位與其他 ETF。
- **收斂方式**：跑 `scripts/fetch_etf_holdings.py --probe` 於 CI，讀日誌逐家證實後改 `_cands()`（同 cnyesfund.py 當初 6 輪 CI 收斂的做法）。
  探針要用 `etf_holdings.yml` 的 `probe` 開關（探針模式 checkout 被 dispatch 的分支，見 [ETF 持股資料](etf-holdings.md)）。
- **第三方站的價值已降低**：第三方源的價值在「假無異動」修好後已從「補涵蓋」降為「多一個驗證章」——00998A／00986D 本來就有真實 Δ，不需別人補。
  **要再撿起來只有瀏覽器路線**（`fetch_etf_holdings_browser.py` 已有攔截 XHR＋DOM 解析的機制；玩股網若是擋 UA／無頭特徵則有機會，若是擋 IP 信譽則一樣不通）。

## 不能改的規則

- **勿走回頭路**：投信官網第一手、「從頁面 HTML 撈持股」、第三方站純 HTTP 都已證實不可行；別再往頁面 HTML 調解析器。
- **節流鐵則**：掃 JS bundle 時**每站台每次執行只掃一次、最多 3 支 bundle**（`_bundle_cache` 以 host 為鍵）——23 檔逐檔重掃會對投信站發出上百個不必要請求。
- **假陽性防呆 `is_plausible()` 務必守住**（三道，見 [ETF 持股資料](etf-holdings.md)），新增 adapter 後要確認仍過這關。
- **探針零結果時印上下文原始片段，不要只印次數**：只印次數無法決斷是 HTML 表格／內嵌 JSON／純樣板，印片段才能一輪定位結構、不必再猜。

## 踩過的坑

- **SPA catch-all 假 bundle（第 6 輪才發現，白掃三輪）**：群益「bundle」424450B、安聯 9437B **與各自的 HTML 頁面同大小**——
  **SPA catch-all 路由把 index.html 原封回給任何 .js 路徑**，我卻當成 JS 在掃。防呆：**回應以 `<` 開頭或位元組數等於頁面 → 判為 catch-all 假 bundle**，日誌講明；
  並列出「頁面 script 共 N 支：檔名…」以便挑對主 bundle（元大只抓到 3.3KB 小 chunk）。
- **`_API_HINT` 沒有詞界**：舊版無詞界的 `api` 會匹配 c-**api**-tal（群益 capitalfund），整排 hint 都是導覽連結 → 已加詞界（第 2 輪）。
- **`weight` 的假訊號**：元大頁面 `weight` 那 191 次多半是 CSS `font-weight` → `_key_hits` 扣掉 `font-weight` 假訊號（第 3 輪）。
- **代號鍵名對不上**：元大 **stockNo／stockId／stockCode 全 0 次** → 代號欄叫別的名字，平衡掃描的錨點一次都沒觸發。
  錨點鍵名放寬到 `code/id/symbol/ticker/secId/secNo`，`_KEY_ID` 同步補 symbol/ticker（否則錨點觸發了 `_row_from_mapping` 仍取不到值）（第 3 輪）。
- **別的 ETF 推薦連結被當成持股**（第 1 輪）：見 [ETF 持股資料](etf-holdings.md) 的 `is_plausible()` 那條。

## 歷史

純 HTTP 投信官網的 CI 探針，一輪一輪的經過：

- **第 1 輪（2026-07-29，run 30420827829）**：野村 HTTP 500、統一 302 無限轉址、群益／安聯／證交所 ETFortune 全回 **SPA 外殼 HTML**（持股由 JS 動態載入）→
  靜態 HTML 抓不到，真正的清單在 XHR 後面。因此探針加 `_api_hints()`：抓到 SPA 外殼時**從 HTML／內嵌 JS 撈出疑似資料端點印進日誌**，一輪就能收斂，不必一輪換一個猜測網址。
  同一輪踩到假陽性（推薦連結）→ 加 `is_plausible()`。
- **第 2 輪（2026-07-29）**：①假陽性防呆生效（日誌現出 `[判為非持股清單：3 檔、帶量 0 檔]`）；
  ②**元大 `tradeInfo/pcf/{code}` 回 1.07 MB HTML**（不是空殼）但表格解析 0 檔 → 資料是**內嵌在 script 的 JSON**，與 cnyesfund 當初完全同型 →
  新增 `parse_embedded_json()`（平衡物件掃描、原文＋反跳脫各試一次、只認帶權重或股數者）；③`_API_HINT` 加詞界；
  ④新增 `_key_hits()`：大頁面零結果時列出疑似鍵名命中次數，用來區分「真 SPA 外殼（該找 XHR API）」與「資料就在頁面裡、只是鍵名不同（該補鍵名）」。
- **第 3 輪（2026-07-29）**：元大 1.07MB 頁面回 `鍵名命中={'shares':24,'weight':191,'股數':10,'權重':59,'比重':7,'成分股':63,'持股':9}`，
  但代號鍵名全 0 次；群益的 `證券代號` 只出現 3 次且是 HTML 文字非 JSON 鍵，帶引號的錨點也匹配不到。
  修法：錨點鍵名放寬、`_key_hits` 扣掉 `font-weight`、**`_key_hits` 改印「資料錨字末次出現的上下文原始片段」**。
- **第 4 輪：定案「從頁面 HTML 撈持股」是死路，別再往這條調解析器**。上下文片段證據：元大「成分股」末次上下文是**費率表／指數編製規則文案**
  （`…以下(含)：0.10%…Quarterly re-balance…`）、群益「證券代號」是**基金公告內文**（`【基金公告】…群益半導體收益（證券代號：00927）…`）。
  那 1 MB 的元大頁面是把全站文案與路由打包的 SPA bundle，**持股資料不在 HTML 裡、全靠 XHR**。
  → 主力改為 `_bundle_api_hints()`：**從 `<script src>` 抓 JS bundle、再 regex 找 API 路徑字面值**（SPA 呼叫的端點一定寫在 bundle 裡），並加上面的節流鐵則。
- **第 5～6 輪：bundle 路線有效但踩到自家 bug**。第 5 輪元大 bundle 掃出 **`/api/bridge`**（通用 API 閘道，光有路徑打不出請求 →
  已加「呼叫脈絡」把端點前後 ~360 字元程式碼一併記錄，看得出 method 與 body 參數名）。第 6 輪逐支診斷才發現 catch-all 假 bundle（見踩過的坑）。
- **投信官網第一手總結**：逐家逆向 7 輪＋無頭瀏覽器 3 輪，結論見上表；2026-07-30 使用者指示「不必抓官網第一手，彙整站＋雙重驗證」，改走彙整站雙源。

第三方交叉驗證（2026-07-30 兩輪 CI 探針，使用者核可三站後實測）：

- **玩股網** `www.wantgoo.com/stock/etf/{code}/constituent` 兩個 URL 皆 **403**（WAF 擋機房 IP）。它的資料基準最理想：官方說明寫含「櫃買中心公開揭露之申購買回清單」、
  每交易日更新，也是唯一涵蓋上櫃的候選，可惜拿不到。
- **CMoney** `www.cmoney.tw/etf/tw/{code}/fundholding` HTTP 200、259KB，但持股全在 XHR 後面（HTML 內「成分股」只出現在 meta 文案；
  bundle 改成 HEAD 問大小、由大到小深掃主檔後**仍找不到任何持股相關端點**）。
- **ETF觀測站** `fundclear.com.tw`（集保）是**基金**觀測站，bundle 撈出的 API 全是 `/api/performance/*`、`/api/offshore/*`，不做 ETF 持股。
- 結論：現行驗證維持「etfinfo 主＋Yahoo 驗構成」；本家三檔第一手 fhtrust。
