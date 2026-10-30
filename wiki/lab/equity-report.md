# 個股深度報告與產業報告

> 投行首次報告格式的個股報告（評等、目標價、同業比較、產業章）與同產業共用的產業報告：資料包、估值規格、檢查、頁面、技能包、網頁申請與每天晚上的名單。
> 原始資料：規劃 `docs/lab_equity_report_plan.md`；程式：`arm/lab/eqspec.py`、`eqfacts.py`、`eqfacts_us.py`、`eqreport.py`、`eqchart.py`、`eqpage.py`、`eqsite.py`、`eqqueue.py`；
> 指令：`scripts/eq_facts.py`、`scripts/check_eq.py`、`scripts/eq_build.py`、`scripts/eq_queue.py`；技能 `.claude/skills/equity-report/`；測試 `tests/test_eqspec.py`、`test_eqfacts.py`、`test_eqfacts_us.py`、`test_eqreport.py`、`test_eqqueue.py`
> 最後更新：2026-10-30
> 正本就是這一頁（2026-10-29 新建，CLAUDE.md 沒有對應段落）。

## 現在怎麼運作

2026-10-29 使用者：「我想要針對篩選出來最強力推薦的公司，可以跑專業的個股分析報告跟同業比較表，像是投行那種的深度產業報告」。
使用者四個決定（AskUserQuestion）：每週新進的＋隨時指定；網頁深度報告（8～12 頁、10～15 張圖、同業表可下載 CSV、可存 PDF）；
照投行給評等與目標價（禁用詞多一個例外，見[內容鐵則](../ops/content-rules.md)）；同產業共用一份產業報告、每月更新。

- **技能包**：Anthropic financial-services-plugins（Apache-2.0）的 initiating-coverage、sector-overview、comps-analysis 等，改寫成專案技能 `.claude/skills/equity-report/`；
  不裝原外掛（綁 12 個付費資料源、產 30～50 頁英文 Word）。出處與改了什麼在技能的 `NOTICE.md`。
- **資料包**（`eqfacts.tw_pack`）：只讀 repo 裡的資料、不連外網（`dashboard/co`、`x9t.json`、`x9f.json`、`data/lab/icchain.json`、`mkt`、`pos`）；
  金額一律億元、比例 %。報告裡的數字只能來自資料包，或同一段附來源連結（`check_eq.py` 會抓）。產業資料包＝`eqfacts.ind_pack_tw`（產業鏈節點、成員、
  成員合計月營收〔同一批公司〕、估值分布、細分族群泡沫等級）。
- **評等與目標價**（`eqspec` VER 3，2026-10-30 使用者：「我不要失真的數據」）：倍數和它乘的 EPS 一定同一把尺、不自己預估 EPS。
  共識法（本公司有 3 位以上分析師共識、同業至少 3 家也有）＝未來 12 個月 EPS × 同業未來本益比（第 25～75 百分位內，預設中位數）；
  其他＝已公布的近四季 EPS × 本益比（本公司近 5 年＋同業現在，都是近四季口徑，預設兩個中位數的平均）；金融保險、虧損或 > 80 倍（`PE_MAX`）用淨值比法。
  放進分布的本益比只收 0～100 倍（`BAND_PE_MAX`），同業中位數也照這個排除（2026-10-30 起頁面同業表照算）。
  未來 12 個月 EPS 依**會計年度結束日**加權（VER 3）。評等由上檔空間決定（≥ 15% 買進、≤ −10% 減碼）。法人共識目標價只當對照。
  頁面也不混口徑：同業散布圖縱軸只放一種本益比、估值區間每條都寫「哪種倍數 × 哪種 EPS」、**只畫實際用的那把尺**（本益比法不畫淨值比區間，反之亦然）、
  財務摘要的歷史年度本益比用當年年底收盤。
- **美股**（`eqfacts_us.us_pack`／`ind_pack_us`；代號是英文字母就走美股）：財報＝SEC 第一次公布（`ussx_fin.json`），股價與分析師＝`ussx_card.json`
  （只有選股頁美股那幾檔有），同業＝S&P 1500 同一個 GICS 細產業、市值最接近的（`ussx_fin` 的同業列，每週）、同業未來本益比＝`fwd/us.json.gz`。
  近四季口徑＝**近四季淨利 ÷ 最新申報的流通股數**（買回股票時和財報 EPS 加總不同，頁面兩個都列）；本公司本益比歷史＝月底市值 ÷ 當時的近四季淨利。
  Yahoo 的 EPS 多為調整後，只和調整後比，不和財報淨利混算。產業代號＝`us-{GICS 細產業}`，段落「美股成員與估值」取代「台灣成員營收與估值」。
  單位：億美元、美元；籌碼段改成分析師評等、做空、法人與內部人（Yahoo）。
- **同業**：台股＝櫃買中心產業鏈同節點的上市櫃公司（最具體節點市值最大的 2 家＋共同節點多、市值接近的）；美股＝同 GICS 細產業。撰寫者最多換 3 家。
- **每天晚上的名單**（`eqqueue.queue`／`scripts/eq_queue.py`；2026-10-30 起，原本是每週六、每週最多 4 家）：①網頁申請的（`data/eq_requests.json`，收件匣排好的順序）→ ②接下來 2 個交易日要買、還沒有新報告的（台股＝選股頁內嵌的 `D.pick.tw.ev` 裡主要策略、有名單的「買進」，`eqqueue.page_pick` 找有 `tw` 的那一個 pick；美股＝`ussx_qm.json` 的 `now.buy`，`now.next` 在這兩天裡）→ ③季更新（只在週六）。每一家都再判一次 90 天內做過又沒新財報的不做；美股只收 `eqinbox.us_codes`；每班最多 `EQ_RUN_MAX`＝3 家，排不到的明天再排。輸出每家標來源（申請 #單號／M/D 要買（策略）／季更新）。
  排程：Routine ⑦「個股報告」台北每天 20:47（[排程](../ops/routines.md)）：「今天做 0 家」安靜結束；先做需要的產業報告、再每家一個子代理，push 經 daily.yml 併檔；推播只寫公司、評等與來源。
- **申請收件匣**（2026-10-30 第一段，`docs/lab_eq_request_plan.md`）：GitHub 申請單 `.github/ISSUE_TEMPLATE/eq-report.yml`（只有「代號」一欄）→ `.github/workflows/eq_inbox.yml`（開單／改單／重開單、`daily.yml` 跑完、每天台北 22:23 兜底、手動）跑 `scripts/eq_inbox.py`＋`arm/lab/eqinbox.py`：每次從 API 重讀開著的單對帳、不用事件內容；看網站的人都能申請（使用者選），站長的單排前面、其餘照先後，每個帳號同時 2 件、佇列 30 件；同一家已在佇列、90 天內做過又沒有新財報（`eqqueue.need`）、資料庫沒有這家（台股 `dashboard/co`；美股要 `ussx_fin`＋`ussx_card` 都有，約 13 檔）→ 回一句並關單；報告日 ≥ 申請日 → 回報告連結並關單。結果 `data/eq_requests.json`（`items` 照做的順序、`done` 留 30 天；不存帳號名稱）。網頁按鈕與每天晚上的排程是第二、三段。
- **網頁上的申請**（第二段）：個股卡、公司卡、美股個股卡最上面那一行（`page.py` 的 `eqRepLine(k, 名稱)`）：有報告＝連結；已申請＝「已申請（M/D），排程照順序做」（`D.eqreq`＝`eqsite.requests_map()`）；都沒有＝「要個股報告」，打開申請單、代號已填好（`eqReqUrl`＝`eqinbox.form_url` 同一個格式；美股只有 `D.equs` 裡的）；按過的這台裝置記 7 天（localStorage `eq.sent`），先寫「已送出，等排程」。選股頁「這週要做的事」買的那幾檔旁邊一個小標記（`pickpage.eq_mark`：報告／已申請／要報告）；研究紀錄頁「個股報告」段上面多「申請中」（`eqsite.requests_block`）。
- **存放**：`reports/eq/{tw|us}/{代號}/{報告日}.md`＋同名 `.facts.json`，不覆蓋舊版（舊版＝評等歷史）；產業 `reports/eq/ind/{產業代號}/`。
- **頁面**：`eqsite.build` → `dashboard/rp/{tw|us}-{代號}.html`、`dashboard/rp/ind-{產業代號}.html`（`<base href="../">`，錨點要寫 `rp/…html#id`）。
  圖是伺服器端畫的 SVG（一條縱軸、兩個單位就上下兩格），列印 A4。頁首「最新收盤」每次建頁讀 `dashboard/x9t.json`，報告本文不動。
- **網站上的入口**（2026-10-29 使用者看過樣本說「好」之後接上）：研究紀錄頁「個股報告」段（`eqsite.research_body`：每家最新一版一列＋產業報告）；
  個股卡、公司卡、美股個股卡最上面一行「個股報告 M/D・評等」（`page.py` 的 JS `eqRepLine`，資料 `D.eq`＝`eqsite.links()`，不寫目標價）。
- **建頁**：`scripts/gen_fund_dashboard.py` 在研究紀錄頁之前跑 `eqsite.build()`；三支建頁 workflow 都 `git add -f dashboard/rp`（沒有報告的舊頁會刪掉）。
- **怎麼上線**：報告（`.md`＋`.facts.json`）推到任何 `claude/**` 分支 → `daily.yml` 併檔段只收 main 還沒有的報告、檔名合格、有資料包，
  並用 **main 的** `scripts/check_eq.py` 檢查，沒過就不併；過了跟當天資料一起 commit 進 main、重建、部署。程式碼不從這條通道進 main。
  這段在 `setup-python` 之前跑，所以檢查程式只能用標準庫（`tests/test_eqreport.py` 守）。

## 不能改的規則

- 規格（`eqspec`）寫在看估值結果之前；要改＝VER＋1、先問使用者。評等不能由撰寫者改，也不影響任何策略、交易計畫、選股名單。
- 「目標價」與評等只准出現在個股報告（`reports/eq/**`、`dashboard/rp/**`）與研究紀錄頁的報告清單（`eqsite.research_body`）；
  卡片上的連結只寫報告日與評等。評等名稱不用「建議」；首頁與附錄有固定的免責聲明。
- 報告進 main 只走 `daily.yml` 的併檔通道（main 的檢查要過、同一天的舊檔不覆蓋）；`reports/eq/**` 推到 `claude/**` 就會觸發 `daily.yml`。
- 容器內不跑資料抓取；資料包只讀 repo。
- 申請單是任何人都能開的外部文字：只交給 `eqinbox.parse` 取代號、不放進任何指令（workflow 不用 `github.event` 內容）；排程只讀 `data/eq_requests.json`。

## 踩過的坑

- 2026-10-30 選股頁新飆股名單的列從 9 欄改成 7 欄（現況移到最後一欄），每週名單 `eqqueue.candidates` 還在讀第 9 欄 → 台股要買的一家都排不進週六排程；隔天週六排程之前發現、改讀最後一欄。測試原本用手寫的舊格式所以沒擋到——現在 `tests/test_pickpage.py` 直接拿 `pickpage.tw_view` 產的事件餵 `eqqueue.upcoming`（同日改成每天晚上的名單、讀「這週要做的事」那份事件），要買的要和新飆股名單標 b 的那幾檔一樣。**改選股頁名單或事件的欄位時，個股報告的名單、個股卡（`eqfacts.pick_info`）要一起看。**

## 歷史

- 2026-10-29：規劃、規格 VER 1、資料包、檢查、頁面、技能包；樣本＝臻鼎-KY（4958，中立、目標價 560 元）＋印刷電路板產業報告。
  使用者看過說「好」→ 同日接上網站（研究紀錄頁清單、三種卡片的連結、建頁、併檔通道）；美股版與每週六排程是下一段。
  看樣本時發現：VER 1 的同業倍數用「近四季本益比」，卻乘在「未來 12 個月 EPS」上，成長快的公司目標價會偏高。
- 2026-10-30：使用者「我不要失真的數據」→ 規格 VER 2（先寫定、commit，再算）。臻鼎-KY 出新一版（10/30）：減碼、目標價 410 元
  （同業未來本益比中位數 17.3 倍）；10/29 那份 VER 1（中立、560 元）留著當評等歷史，附錄標「評等規格第 1 版」。
  同一次把估值區間圖改成名稱在橫條上方（手機上字放大也不會被切掉）。
- 2026-10-30：美股版（規格 VER 3：會計年度結束日、美股近四季口徑，算任何一家美股之前寫定）。樣本＝Paycom（PAYC，買進、目標價 325 美元，
  近四季法、預設倍數 30.05 倍）＋人資與就業服務產業報告。做的時候抓到並修掉：同業中位數把超過 100 倍的也算進去（頁面寫 33.6 倍、估值用 28.5 倍）、
  報告把排除門檻寫成 80 倍（實為 100 倍）、Paycom 大量買回後淨值比區間沒有意義卻畫在估值區間圖、資料包的季營收年增用四捨五入後的數字算、
  美股做空與法人持股比率檢查程式認不得。
