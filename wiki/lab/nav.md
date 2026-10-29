# 導覽與入口

> 頂欄、名詞、查公司、記住上次位置、舊網址、整站建頁的測試夾具。
> 原始資料：CLAUDE.md「導覽與入口」段；規劃 `docs/lab_ia_v5_plan.md` 第 2、10、18、22 節；程式：`arm/lab/appnav.py`
> 最後更新：2026-10-29
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

## 現在怎麼運作

2026-10-28 起「配置」改「選股」，下面「配置頁」＝[選股頁](pick-page.md)（名詞面板、查公司、資料日那一列照舊在 x9.html）。
- 頂欄（`TABS`、`bar(page, cur, search)`、`links()`）兩格：市場＝台股 x9m.html（美股頁 `cur="x9mu.html"`）、選股＝x9.html（鍵 `pick`、`data-k="pick"`、`bar("pick")`）；右邊小字「研究紀錄・名詞・查公司」，再來是深淺色鈕與返回主頁。研究紀錄頁（`bar("r")`）兩格都不亮、小字「研究紀錄」標 `aria-current`。主分頁不放研究紀錄、泡沫、訊號總覽、策略。日期：市場頁在面向標題；配置頁的資料日（`page.asof_line` → `D.asl`）在個股工具那一列（`cfgpage.toolSeg`）。
- 名詞：市場頁＝`x9r.html#mth`（名詞與判定方式）；配置頁＝頁內名詞面板（`.glk` → `openGl()`）；研究紀錄頁＝這頁的「名詞」段（兩份名詞都列）。
- 查公司：配置頁＝點小字打開搜尋框（`copage.SEARCH_HTML` 放在小字那一組裡、`id="cos" hidden`；`.cos` 貼齊頂欄右邊，手機寬度＝頂欄寬、輸入框 16px 免得 iPhone 點進去整頁放大；Esc 或點別處關掉）；其他頁連 `x9.html#q`（到個股工具並打開搜尋框）。
- 兩格各記住上次看到哪裡（`appnav.NAV_HEAD`，localStorage `labLast`）：市場格記 `x9m.html`／`x9mu.html#ix=指數`（美股頁 SWITCH_JS 換指數時記），選股格記 `x9.html`、`?v=us|stk|chip|idx`（`page.urlSet`，研究紀錄身分不記）。畫面出來後沒亮的那一格改連到上次位置、亮的那一格紀錄不是這一頁就記成這一頁；只收這幾種寫法（正規式），讀寫失敗就用預設（台股、配置台股）。x9.html 的那一格點了是頁內切換（研究紀錄身分時讀它的 href 切到上次的分頁）。
- 手機：640px 以下深淺色鈕只留圖示、返回主頁寫「主頁」（`appnav.BACK` 的 `.bk1`）；360px 以上一列放得下；359px 以下小字換到第二列靠右。
- 舊網址（第 10 節第 4 段驗收「六個舊網址都轉得到」）：改版前頂欄六格＋大神策略頁——x9m.html、x9mu.html（同一頁，市場）、x9b.html（市場頁最下面的泡沫；`#tw`／`#ndx` 那個市場、`#ind`… 研究紀錄）、x9o.html（市場頁；`#s=`／`#i=` 那個市場的指標面板、`#r=`／`#p=` 研究紀錄）、x9.html#v=mac（舊「策略」＝研究紀錄・總經策略）、x9.html（舊「個股」＝配置；個股在工具分頁）、x9x.html（總經策略）；`#s=代號`、`#co=代號`、`#gl`、`?v=opp`、`?v=bo&at=…`、`#v=compass` 照舊。`tests/test_old_urls.py` 用無頭瀏覽器逐一打開（24 個網址），另測頂欄記憶與手機寬度 320～414px（把收起來的段落全部打開，檢查不左右捲、圖有樣式）。
- 整站建頁的測試夾具 `tests/conftest.py` 的 `labsite`（session scope：照每天建頁的順序建配置、市場、轉址、研究紀錄頁，整個測試只建一次約 3 分鐘；`test_plain.py`、`test_old_urls.py` 共用）。CI 不跑 pytest——改頂欄、網址、轉址之後自己跑這兩支。
- 主頁頁尾的「·」連 x9m.html（市場・台股）；tests/test_lab.py 守入口只在頁尾。

## 踩過的坑

- 配置頁要載入 corepage 的樣式（`page.render` 的 CSS 有 `corepage.CSS`；「細節」放的是 corepage 的圖表與表格）——第 1 段漏了，打開細節時圖是整片黑塊、兩張圖一起出現、表把整頁撐成 1,213px 寬，到第 4 段量手機寬度才發現。把別的模組的 HTML 搬進一頁時，樣式要一起帶。

## 歷史

- 2026-10-23（IA v5 第 4 段）：照核准過的示意圖，頂欄只剩「市場｜配置」兩格；每格 `data-k`（mkt／cfg），配置格記 `x9.html?v=us|strat|stk|chip|idx`，頁內切換用 `$$('.apptab a[data-k="cfg"]')`。原本頂欄的「資料到…」拿掉。排程搬家（第 10 節第 4 段：「Routine 的分支要有新程式」）：push 觸發的 daily.yml 用「被推分支」上的 workflow 檔（見「全部更新」步驟 9⑦）。查：五個復華排程都綁在 10/16 開的視窗（分支 `claude/exciting-cerf-isj9q7`；10/24 加第六個，2026-10-29 查六個仍綁在這個視窗），從 10/17 起每天 06:36 先把 origin/main 合併進分支才寫新聞（`git log --first-parent` 每天一筆 merge main），10/24 那班已含第 1～3 段；第 4 段也沒有改 workflow 的 `git add` 清單。這次不必搬家。哪天它的分支停止合併 main（first-parent 歷史上沒有 merge main），新加進 workflow 的檔就不會被那一班 commit，那時再做「排程搬家」（並重設 `/model`）。
