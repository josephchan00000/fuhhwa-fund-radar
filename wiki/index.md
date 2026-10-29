# 知識庫目錄

> 復華基金雷達的知識庫（做法照 Karpathy 的 LLM Wiki）：先看這份目錄，再讀相關的頁；做完事更新那一頁，[日誌](log.md) 加一行。
> 規劃：`docs/llm_wiki_plan.md`。
> 目前是第一段：每一頁都從 CLAUDE.md 逐字搬來、還沒整理，以 CLAUDE.md 為準；改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產各頁與這份目錄。

## 每天的作業（ops）

- [「全部更新」每日 SOP](ops/daily-update.md)：效率原則、產提示包、合規掃描與 QA、重建驗證、commit、CI 單一 commit、步驟 9 驗證線上內容（含 9⑤～9⑨）。
- [新聞報告規則（全部更新步驟 2）](ops/news-rules.md)：週末時窗、三報守備範圍、來源、經濟日報頭條、查證字句、籌碼讀落檔、深度與漲跌分析、選題、速覽文風、卡片可讀性、粗體標籤、子代理回傳。
- [部署與「線上沒更新」](ops/deploy.md)：內容在 main 不等於線上已部署、Deploy Hook、診斷順序、Vercel 部署上限、多人化硬化、快取。
- [指令「ETF 募集週掃」](ops/etf-weekly-scan.md)：每週一主動盤點新 ETF、與每日缺口處理的分工、指數審核維護。
- [指令「策略探勘週報」](ops/strategy-scouting.md)：每週日找新策略、先寫規格與程式再回測、等合併通道結果、使用者的決定。
- [排程與「排程搬家」](ops/routines.md)：六個排程、搬家步驟、prompt 原文、為什麼火進主會話、模型要重設。
- [每日時點地圖與 cron](ops/schedule.md)：盤後刷新、GitHub cron 遲到、當日完整性看門狗、每日時點地圖、備援。
- [GitHub Actions 額度](ops/ci-budget.md)：實測用量、四個省分鐘的修法、repo 公開之後。
- [內容鐵則：新聞來源黑名單與禁用詞](ops/content-rules.md)：禁用詞清單與「目標價」的兩個例外。

## 環境與限制（env）

- [2026-10-16 改寫 git 歷史（隱私）](env/git-history.md)：作者欄換成 noreply、舊分支封存、PR 參照；本頁開頭也是「已知環境限制與防呆」段的標題。
- [容器的限制](env/container.md)：時區、被擋的站與空轉、check_numbers 洗檔、git add 寫明路徑。
- [排程會話 MCP 審批（-32003）](env/mcp-approval.md)：send_later 被擋的原因、settings.json 預先核准、背景迴圈備援。

## 主儀表板（復華雷達）（main）

- [新聞卡](main/news-cards.md)：詳細分析消失的根因（粗體標籤）、卡片排序、做過又拿掉的保底要點卡。
- [復華新聞與社群](main/fund-news.md)：Google News 洗日期、ezfunds、品質重規劃、強基金、YouTube 三層清單、PTT、日文影片。
- [持股簡介補齊](main/holdings-intro.md)：前十大簡介一再漏掉的根因、三道防呆、補簡介格式。
- [列印版／存 PDF](main/print.md)：獨立列印樹、五組重點、分頁規則、驗證方法、踩過的坑。
- [行事曆與資料可信度](main/calendar.md)：台灣區與精簡規則、台股法說財報、官方休市表與颱風、昨日版底稿與漂移閘門、核心排程錨。
- [資料更新時間區塊](main/freshness.md)：版面、只列逾期、交易日口徑、不能拿來源名稱當 grep 標記。
- [市場溫度計（總經分頁）](main/macro-thermometer.md)：全球與台股籌碼兩張表、外資淨空單凍結、證交所盤後修正、資料層鐵則。
- [ETF 數據追蹤表](main/etf-watch.md)：追蹤清單、雙來源、報酬與配息、預估配息、欄序、落檔與欄位級合併。
- [即將登場與新 ETF 自動發現](main/etf-upcoming.md)：掛牌自動加入追蹤、上櫃檔分組、五狀態三分組、發現層、not_tracked、募集表格解析、併檔通道。
- [ETF 當日漲跌的坑](main/etf-daily-change.md)：差一天並排、官方表與前收備案、假 bar、上櫃慢一天、週月報酬錨定、今天對前天、除息日。
- [ETF 詳情卡畫面](main/etf-detail.md)：列高、卡片與泡泡、方塊圖、異動與持股表、產業別、本機截圖驗版、表格排序。
- [ETF 持股資料](main/etf-holdings.md)：貢獻與報價日、假無異動、假全部出清、彙整站雙源、本家第一手、第三方探針、期貨部位。
- [基金多期報酬](main/fund-returns.md)：鉅亨每日基準覆蓋層、自建 NAV 序列算 1 週／1 月。

## 籌碼雷達與研究（lab）

- [籌碼雷達總覽](lab/overview.md)：入口、x9.html 兩種身分、模組、建頁接在哪裡、workflow 要裝 numpy。
- [籌碼雷達資料層](lab/chip-data.md)：data/lab 分片、帳本口徑、官方端點坑、擴充 ETF、Yahoo 歷史價量備援。
- [籌碼雷達的訊號與第一代策略](lab/chip-strategy.md)：8 個訊號與成績單、紙上交易規則、S1 等策略、策略頁 v2、持有期差一天的坑。
- [指數調整](lab/index-changes.md)：臺灣50 與高股息的審核時程、公告前預測、被動 ETF 動向。
- [臺灣50 換股研究與提前卡位](lab/tw50.md)：研究結論、歸因、提前 25 日買 4 檔、兩個版本、前瞻流程。
- [高股息換股研究](lab/high-dividend.md)：四檔名單與買賣期間、預估名單、價格口徑、被動買盤大小、依編製規則提前卡位。
- [資料包策略測試與回測紀律](lab/strategy-pack.md)：P1～P6、存活者偏誤、成本加倍與參數鄰近、成交檢查、效能。
- [回測方法 v3](lab/backtest-v3.md)：比較基準、大型與中型、評級條件、資料、模組、結果、踩過的坑、頁面。
- [籌碼雷達介面改版歷史](lab/chip-ui.md)：版面 v3、版面 v4（機會｜策略｜個股｜籌碼｜指數＋後台）、後台自我驗證、2026-10-14 介面。
- [逐筆交易](lab/trades.md)：頁面、資料流、緊湊陣列、當時價格換算、核對時修正的回測資料問題。
- [策略健檢與自我改良](lab/selfopt.md)：影子版本、事前寫定的候選、每天體檢、每週重跑、不變式。
- [公司分析與飆股研究](lab/company.md)：點進去才算的公司卡、財報資料、飆股規則（superx）與結果。
- [《超級績效》SEPA 與飆股名單研究](lab/superstock.md)：S01、綜合最優解、W1～W6 名單研究、W9 照書選股的結論。
- [法人預估與產業比較](lab/forecast.md)：FactSet 與 Yahoo 資料、目標價的用字例外、產業比較、頁面。
- [長線投信動能成長股（S5）](lab/growth-s5.md)：四關、回測、出場教訓。
- [台股景氣溫度頁](lab/heat-tw.md)：各版本規格、計算、資料來源、驗證結果、踩過的坑。
- [美股景氣頁](lab/heat-us.md)：四個指數、規格、泡沫模型、資料、各指數自己的情緒籌碼。
- [泡沫（市場層級）](lab/bubble.md)：VER 1～4 的等級條件、規格、程式、頁面、結果。
- [產業泡沫](lab/bubble-industry.md)：台股產業、美股類股與細產業、已下市公司的產業別、台股細分族群。
- [大跌相關研究卡](lab/crash-cards.md)：短線大跌風險、過熱後 3 個月回撤、反向檢查、大跌後檢查、部位參考（做了又拿掉）。
- [實戰模擬、研究結論、期貨加碼](lab/practical.md)：照網頁操作能不能比一直抱著好、研究結論的問答、200 日線上才加碼。
- [交易計畫（長抱＋機動）](lab/core-plan.md)：corespec VER 1～4、兩期重疊重複計算的修正、計算、結果、頁面。
- [美股個股策略與美股強勢品質股](lab/us-qm.md)：美股資料、三條個股策略、美股飆股研究、強勢品質股 VER 3～8。
- [飆股修正與新飆股前瞻記錄](lab/boom-live.md)：W7、W8、前瞻記錄 VER 1～4（接手、N8）。
- [台指期早盤策略（股票期貨人生）](lab/fut.md)：估算開盤的想法、規格 VER 1～2、資料、盤前取樣、結果、頁面。
- [少見但勝率高的策略](lab/rare.md)：九條規則、結果、上線與觸發前提醒。
- [訊號總覽（一）：基本規則與頁面](lab/signals.md)：sigspec VER 1～3、6：判定、訊號清單、計算、頁面、景氣頁瘦身、指標頁、警示改看最大回撤、法人買賣超。
- [訊號總覽（二）：後續版本](lab/signals-versions.md)：VER 4～5、9～24：情境、進場後報酬、打亂測試、溫度計、預估之後、盤查、每一天一樣重、最差一次。
- [選股頁](lab/pick-page.md)：台股｜美股｜個股、進場行事曆、策略卡、新飆股卡 v2、行事曆 v2。
- [配置頁（已改成選股頁）與研究紀錄](lab/cfg-research.md)：x9.html 兩種身分、配置頁 v1／v2、美股個股卡、全部策略表、研究紀錄頁。
- [市場頁](lab/market-page.md)：四塊版面、全部指標、泡沫與產業泡沫、轉址、美股點到才下載。
- [主頁面用字](lab/plain-words.md)：不能出現的詞、比較的寫法、test_plain 怎麼掃。
- [導覽與入口](lab/nav.md)：頂欄、名詞、查公司、記住上次位置、舊網址、整站建頁的測試夾具。
- [新策略候選](lab/candidates.md)：規格＋程式、三種引擎、用到未來資料的檢查、放進計畫試算、合併通道、使用者的決定。
- [總經策略／個股策略頁](lab/strategy-pages.md)：一份頁面兩種身分、網址、說明卡、時間軸共用、x9x 轉址。
- [總經策略（原大神策略）](lab/expert.md)：xstratspec VER 1～6：短線、落底、季節性、風險控制、融資維持率、判定。
- [景氣頁與個股頁的視覺化](lab/heat-viz.md)：雷達、比較日期、溫度計、這週變化、階段時間軸、證據地圖、3D 地形、日夜間按鈕、個股頁三張圖。

## 原始資料（不在知識庫裡，頁面會連過去）

- `docs/*_plan.md`：每個功能的規劃、使用者的決定、結果。
- `docs/prompt_audit/`：2026-09-24 prompt 稽核。
- `tw-superstock-lab/`：飆股研究（自己的 CLAUDE.md、PROGRESS.md、reports/）。
- `reports/`：每天的新聞報告；`data/`：資料與研究檔。
