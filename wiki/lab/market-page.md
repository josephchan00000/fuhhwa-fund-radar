# 市場頁

> 四塊版面、全部指標、泡沫與產業泡沫、轉址、美股點到才下載。
> 原始資料：CLAUDE.md「市場頁」段；規劃 `docs/lab_ia_v5_plan.md` 第 15.1、18.1、20、25 節；程式：`heatviz`、`heatpage_us`、`sigpage`、`bubpage`
> 最後更新：2026-10-30
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

## 現在怎麼運作

兩個景氣頁（台股 x9m.html、美股四個指數 x9mu.html）＝市場頁；泡沫頁、訊號總覽併進來。
- 由上而下四塊（`heatviz.main_view`）：面向（`face_html`：標題列 `_face_head`＝指數收盤・資料日・離 60 日高點或一段大跌中＋落底訊號・泡沫等級〔點了捲到最下面〕・融資維持率〔只有台股，`xstratpage.mr_chip`〕；五個面向分數〔點了開面向面板〕；雷達＋今天的訊號〔`today_html`：溫度計＋清單＋「之後怎麼走？」；電腦左右、手機雷達在上〕；這週變化〔兩欄下面整條〕；收起：和指數走勢比較 `#cmpd`〔打開時重畫〕、價位 `#tad`）→ 全部指標（`sigpage.block_html`）→ 泡沫（`bubpage.block_html`）→ 頁尾一行（研究紀錄・名詞・資料日，`foot_html`）。市場切換一排 `heatpage.market_row`（台股是連結、美股四個是切換按鈕，`.ixsw`）。
- 研究畫面留在市場頁：`#v=research／phase／terrain`（資料在 x9mh.json／x9muh-*.json），最上面一列 `research_bar`（‹ 研究紀錄｜三個畫面｜回到市場頁）；研究紀錄頁列入口。
- 全部指標（JS `window.sgInit()` 可重跑：AbortController 拿掉上一次的事件；`SG.emb`＝固定市場、清單預設收起〔點分類、搜尋、「列出全部」才展開〕）：頁面層一份 `#sgd`（`heatpage.page_parts`→`sigpage.block_data(市場)`；美股頁四個指數＋美股產業共用，`SG.usx`；目前市場讀 `#ixc` 的 data-ix），面板 `sigpage.PANEL` 在模板外面；每一次的清單 `x9oh-{市場}.json`（`detail_name`，點開才下載；三支 workflow 各兩行 `git add -f dashboard/x9oh-*.json`）。`#sgd` 只放這一頁的市場名稱（`page_json` 的 emb 分支：mk／pxn／總經策略的 mkn 與 spec）。網址：`#i=指標`、`#s=訊號`（`hsWith` 保留 `#ix=`、`#v=`）。面板裡的 `<a data-sg="訊號">` 由 sigpage 攔下、在同一頁開指標面板。
- 泡沫（`bubpage.block_html(mk)`：`bubble.last(mk)`＝景氣頁同一個程序算好的等級；`industries()`＝`bubind.compute` 一個程序只算一次）：`#bubd`＝`block_data`（不含 1990 年以前的延伸樣本）；圖的預設期間＝按下去的那顆（`defRg`，市場頁近 30 年、研究紀錄全部）；美股頁四個指數各一塊、產業表四塊相同（換指數時 `SWITCH_JS` 呼叫 `bubDraw(ix)`、`sgInit()`）。CSS 拆成 `CHART_CSS`（共用）＋頁面專用。
- 泡沫那一塊等級與七個條件下面一行「產業過熱有多廣（參考）」（2026-10-30，`bubpage.breadth_line`，`.bbw`；`docs/lab_breadth_plan.md` 第 11 節）：台股＝產業幾個過熱、占市值、細分族群；美股＝48 細產業（月資料，寫「到 幾月」）、占市值、11 類股；比過去最多、最後一句驗證的結果。驗證沒過所以只是參考讀數，不改等級。
- 產業泡沫單獨一張卡（2026-10-29；`bubpage.ind_card(mk)`，接在市場泡沫卡後面、`id="bubi"`；規劃 `docs/lab_us_chip_plan.md` 第 3、6 節）：使用者：「產業泡沫我覺得蠻重要的，可以規劃放到首頁泡沫那邊 排版想一下要乾淨」，選電腦熱度格、手機分級清單。電腦（≥640px，`.mbtl`）＝等級 2 以上一個產業一格（底色淡化的等級色、左邊色條、等級與成立的條件），每組最後一格「其他 N 個・沒有過熱」；手機（`.mbls`）＝一個等級一列（4／3／2，列裡再分組，等級 3 以上寫條件），最後一行「其他 N 個沒有過熱」。兩種都由 CSS 切換、內容同一份。點一格／一個名稱＝打開「全部產業」表、展開那一列並捲過去（`data-bn`＝`組:代號`，表上每一列 `data-n` 同一個值；美股細產業沒有歷史圖，只捲過去標亮）。美股各指數相關產業排最前面（`IND_REL`：費半＝半導體與電子零件、電腦硬體、資訊科技；那斯達克兩檔＝資訊科技、通訊服務、軟體、電腦硬體、半導體與電子零件；就算等級 0 也列，其他組不重複）。面向標題列多一格「產業泡沫 N ＋產業名」（`ind_chip`：最高等級、同等級時相關產業優先，點了捲到 `#bubi`；沒有等級 2 以上寫「沒有過熱」）。
- 跳段：`#at=段落`（例 `x9m.html#at=bub`、`x9mu.html#ix=sox&at=bub`）在整頁 load 之後才捲（全部指標、泡沫的程式在後面，先捲位置會跑掉）；捲完拿掉參數。
- 轉址：`x9o.html`（`sigpage.REDIRECT`：`#s=`／`#i=` 是市場的 → 那個市場頁；其他 → `x9r.html`＋原 hash；沒有 → x9m）、`x9b.html`（`bubpage.REDIRECT`：`#tw`… → `#at=bub`；`#lv／ind／indv／types／mth` → `x9r.html#bub-…`）。頂欄拿掉這兩格。
- 研究紀錄頁放：訊號研究（`sigpage.research_body`＝研究結論、完整研究表、全部指標〔含個股訊號與策略；籌碼頁 `sjLink` 連 `x9r.html#s=stk:sig:…`〕、名詞與判定方式，非 emb 模式的同一支 JS）＋泡沫研究（`bubpage.research_body／research_data`）。`research_page.render(SV, BV)`：不給就讀 `sigpage.LAST`／`bubpage.view()`。
- 美股頁點到才下載：頁面只放 S&P 500 的主畫面；每個指數一個 `x9mup-{指數}.json`（`heatpage_us.assemble`）＝細項面板 `tpl`（S&P 500 的約 31KB 壓縮）＋其他三個指數的整份內容 `main` 與全部指標的列 `sg`（各約 130KB 壓縮）。
  · 切換指數（`SWITCH_JS`）：下載那個指數的檔，市場列旁邊寫「載入中…」、內容變淡（`aria-busy`），換上後重跑 heatInit／sgInit／bubDraw；載不到寫「載入失敗，請重新整理頁面」。
  · 細項面板：S&P 500 第一次打開面板（面向分數、項目名稱、今天的訊號、「之後怎麼走？」、`#o=scen`）才下載 `x9mup-spx.json`，面板先寫「載入中…」再換上（`heatviz.openD` 的 lazy、`window.heatPanels`）；對照圖選多條線時情境個數也等下載完才寫（`heatpage.scenHint`）。
  · 全部指標：`#sgd` 只放頁面那個指數＋美股產業；指標用列的位置對到列（`inds` 第 6 欄），`heatpage_us.split_sgd` 拆的時候兩邊各自重新編號、`sgAdd` 併回去時把位置往後挪（對不起來就整份留在頁面）。
  · 網址指到別的指數（`#ix=ndx`）：`window.__heatWait` 讓頁面程式先不畫 S&P 500（省下它 595KB 的對照圖資料），換好內容才初始化；heatpage、sigpage 的 JS 最後一行都看這個旗標（台股頁、研究紀錄頁沒有這個旗標，照常初始化）。
- 測試：`tests/test_sigpage.py`（block、轉址、每個市場一個清單檔）、`tests/test_bubpage.py`（市場頁那一塊、研究紀錄的內容、轉址 node 實跑）、`tests/test_research_page.py`（放進來的研究、景氣入口）、`tests/test_heatviz.py`／`test_heatpage*.py`（四塊順序、研究畫面列、跳段）、`tests/test_heatpage_us.py`（分檔、拆列與併回、初始化順序）、`tests/test_plain.py`（美股每個指數先 `window.heatPanels()` 再掃面板、要有自己指數的列）、`tests/test_old_urls.py`。

## 不能改的規則

- 只改呈現，數字、規格、研究檔都不動。
- 景氣的右側面板與指標面板不同時開：`openD` 先 `sgClose(true)`、`openInd` 先 `heatClose(true)`（q＝true＝只關面板、不動瀏覽紀錄——兩邊都用 pushState，非同步的 history.back 會把剛開的另一個關掉）。`data-open` 是景氣面板專用的屬性（「列出全部」改用 `data-all`）。
- sigpage 改 #sgd 的格式時（尤其新增依市場分的欄位），要一起改 split_sgd 與 sgAdd。
- 美股頁看不到台股的文字、不出現台股產業。產業泡沫只顯示、不算進指數的分數（使用者 Q4）。

## 歷史

- 2026-10-23（IA v5 第 2 段）：拿掉的（第 3 節①、第 8 節、第 13 節、第 14 節第 4 點）：市場狀態那一行 `state_line`（10 個月均線、情境兩格不再放；情境在「之後怎麼走？」）、頁首說明句與「怎麼看」（說明搬到研究紀錄頁「名詞與判定方式」的「今天的訊號（市場頁）」，`sigpage.method_html`）、全部項目 `#items`（每一項在面向面板與全部指標）、今天的訊號裡的總經策略（它是動作，放配置頁；`xstratpage.board／chip／summary／summary_line／today_line` 一併刪掉）、原本訊號總覽的五市場＋個股「今天有效的訊號」（`sigpage.today_html` 刪掉；個股訊號在研究紀錄頁的全部指標）、舊的 `dashboard/x9oh.json`、主畫面的視角切換鈕。大小：x9m.html 1.56MB（壓縮 285KB）；可見文字台股 2,147 字、美股 1,893 字（手機）；美股頁 4.04MB（壓縮 618KB）。
- 2026-10-24（IA v5 第 6 段）：美股頁點到才下載，x9mu.html 3.97MB（壓縮 619KB）降到約 1.07MB（壓縮 223KB），第一次打開（頁面＋S&P 500 對照圖資料）手機下載 1.21MB 降到約 0.82MB（壓縮後）。
