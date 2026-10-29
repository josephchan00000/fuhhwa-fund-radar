# 法人預估與產業比較

> FactSet 與 Yahoo 資料、目標價的用字例外、產業比較、頁面。
> 原始資料：CLAUDE.md「籌碼雷達」段「法人預估與產業比較」；規劃 `docs/lab_forward_plan.md`；程式：`arm/lab/fcst.py`、`arm/lab/industry.py`、`arm/lab/copage.py`；測試 `tests/test_fcst.py`（用真實快訊：解析、去重、一檔一行寫檔、Yahoo 0 值、頁面接線、禁用字）、`tests/test_industry.py`
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

2026-10-16 使用者：「這個是不是沒有加入未來營收預估、產業分析或是券商目標價」。使用者決定：第一階段＝法人預估＋產業比較（產業鏈上中下游、法說會展望之後再說）；只顯示當參考，不回測、不拿來篩飆股。

### 資料（`arm/lab/fcst.py`，只在 CI 抓，本容器擋 cnyes／yahoo）

- 鉅亨網「台股預估」分類 `api.cnyes.com/media/api/v1/newslist/category/tw_forecast?startAt=&endAt=&limit=30`＝FactSet 調查快訊，共識預估有變動才發一則。
  EPS 快訊（家數、主要年度 EPS 中位數前值→新值、最高最低、當時的預估股價；內文兩張表＝三年 EPS、三年營收千元）、預估股價快訊（中位數前值→新值、幅度、最高最低、評等 積極樂觀／保持中立／保守悲觀）。
  存 `data/lab/fcst/factset.json`（一檔一行、newsId 去重、只有最新一則 EPS 快訊留三年表格）。2026-10-16 回補：217 檔、9,863 則，2023-01 起（再往前 8 週都沒有＝到底）。
- Yahoo quoteSummary（`fc.yahoo.com` 拿 cookie＋`/v1/test/getcrumb`；上市 `.TW`、上櫃 `.TWO`）：家數、預估股價平均／中位／高／低、今明年 EPS 與營收預估、30／90 天前 EPS、近 30 天上修下修、評等分布。存 `data/lab/fcst/yahoo.json` 一天一次（平日只抓有分析師的、週一重掃全部，全掃約 76 秒），每週封存一份到 `data/lab/fcst_y/`。
- 每日：`afterhours_refresh.yml` 在 fetch_lab 後跑 `scripts/fetch_fcst.py`（timeout 420；快訊每班補到現在、Yahoo 一天一次）。回補：`.ping/lab` 第一行 `fcfill`（快訊 260 週＋Yahoo 全掃）。
- 來源怎麼挑在 `fcst.view` 決定、頁面不判斷：
  FactSet 最新一則在 `STALE_DAYS`=120 天內用 FactSet，否則用 Yahoo（每天更新），都沒有才用舊 FactSet、標「M/D 的資料，之後沒有更新」（舊資料不進飆股段小字）。
  只列今年以後的年度；Yahoo 沒有中位數才用平均並標 `avg`；分析師人數取 EPS 與目標價兩邊較大者；上修／下修用「差額÷前值絕對值」（虧損 −1.0→−0.5 是上修，直接相除會變成下修）。
  2026-10-17：EPS 用 FactSet 110 檔、Yahoo 395 檔；目標價 FactSet 130 檔、Yahoo 339 檔、舊 FactSet 6 檔。

### 產業比較（`arm/lab/industry.py`）

證交所／櫃買產業別（34 類，範圍大），在 `company.market_table` 裡算→頁面 `D.ind`：產業營收近 3 個月年增（同一批公司加總：公司數會變，不能直接比總和）、公司中位數、成長加快多少、成員 20／60 日漲跌中位數與排名（有股價的 ≥5 檔才排）、名單檔數；金融業不算營收年增（月營收含投資損益）。x9t.json 多 `inds`＋每列 `ii`（產業代號），同業名次在瀏覽器排。

### 頁面（`arm/lab/copage.py`）

- 公司卡「法人預估」（`co-fc`）第一行「目標價 X 元，比現價高／低 Y%（N 位分析師的中位數；只有 1 位就寫 1 位分析師）」，下一行最高最低＋「來源：」。
  來源名稱本身就是連結（FactSet＝鉅亨網那則快訊 `news.cnyes.com/news/id/{newsId}`、Yahoo＝`finance.yahoo.com/quote/{代號}.TW|.TWO/analysis/`）＋「是哪些法人（目標價新聞）」＝Google 新聞搜尋「{公司名} 目標價」（各家券商的數字只在新聞裡，沒有免費的逐家清單）。
  再下面三年 EPS／營收、比前一年、本益比、今年營收進度、評等、Yahoo 近 30 天修正、FactSet 最近 8 次調整（每則可點原文）；手機只列前兩年。「產業比較」（`co-ind`）。資料 `dashboard/x9f.json`（約 300KB，點開公司卡才下載；三支 workflow 各兩行 `git add`）。
- 機會頁飆股段每檔一行「N 位分析師：今年 EPS ±X%・30 天上修／下修・目標價 Z（比現價高／低 Y%）」（`D.wl.fc`＝`fcst.briefs`＝`[人數, 今年 EPS 比去年%, 30 天方向, 目標價比現價%, 目標價]`；點了直接開公司卡的法人預估段 `openCo(c,'co-fc')`）＋「產業熱度」前 5 名。

## 不能改的規則

- 用字：10-16 先定「法人預估股價」；10-17 改口「預估股價 −9% 什麼意思，直接說目標價不就好了；是哪個法人也很重要，不一定要列出來但我要能點過去看一下」→ 直接寫「目標價」，只限這兩處引述分析師數字（JS 函式 fcGr／fcVs／fcSrc／fcWho／fcSec／fcLine 與名詞「法人預估」，`tests/test_fcst.py::FC_FUNCS` 守），其餘照禁用詞。
- FactSet 快訊標題仍不轉載，只用解析出的數字。

## 踩過的坑

- 舊寫法「預估股價 −9%」只有百分比、看不出誰比誰（6214 精誠：Yahoo 1 位分析師 180 元、收盤 197.5＝目標價比現價低 9%）→ 改成先寫目標價再寫比現價高低。
- 沒有分析師的公司 Yahoo 回 0 值（營收預估 0、家數 0），第一次回補 1,959 檔全被當成有資料→改看分析師家數（實際 517 檔，3 位以上 223 檔）。
- 2026-10-17：2377 微星的 FactSet EPS 快訊停在 2025-08，飆股段的「今年 EPS +94%」其實是一年多前的預估；1815 分析師人數空白（只取 EPS 那邊的人數）→ 改成上面的 120 天換源＋人數取 EPS 與目標價兩邊較大者。
- 鉅亨其他端點：搜尋 API 只能翻到約 8 個月前；新聞內文 API `/media/api/v1/news/{id}` 回 422（不用它，清單本身就帶內文）。
