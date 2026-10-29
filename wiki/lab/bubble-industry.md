# 產業泡沫

> 台股產業、美股類股與細產業、已下市公司的產業別、台股細分族群。
>
> 這一頁目前是從 CLAUDE.md 逐字搬來的（知識庫第一段），還沒整理；有出入時以 CLAUDE.md 為準。
> 改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產這一頁。

<!-- CLAUDE.md 第 2638–2667 行 -->
- **產業泡沫（第二段，2026-10-19；使用者睡前：「你先把泡沫一路做到底我早上再看」；規劃第 12 節）**：泡沫頁多一段「產業」（`id="ind"`）。
  · **規格** `arm/lab/bubindspec.py` VER 1（看任何產業結果之前 commit，`tests/test_bubindspec.py` 鎖住；門檻、臨界值、分級、重抽全部沿用市場層級 VER 4）。
    三組：台股產業（證交所／櫃買現在的產業別，「其他」不算；指數＝前月底市值 ≥ 40 億、前月底市值加權、月內買進持有、含息，成分 < 3 檔那個月沒有值）、
    美股類股（SPDR 11 檔 ETF，大盤 SPY）、美股 49 細產業（Ken French 不含股利月報酬累乘，大盤＝依平均規模 × 家數加權）。
    P2 另外要**比大盤多漲 50 個百分點**（產業泡沫看「比整個市場熱」）。E＝產業市值 ÷ 近 12 個月營收（只有台股）；G 現在＝預估（台股 Yahoo 依產業、
    美股 S&P 500 成分股依 GICS），過去＝台股產業營收替代；F＝台股換手率、Ken French 家數 12 個月增加率。最高等級：台股 4、美股類股 3、Ken French 2。
    驗證：每個產業每個月一個樣本、以月份為單位 12 個月一塊重抽、段數＝所有產業合起來的時間段；**只有 Ken French（1931 起）判定**，台股、美股類股只描述。
  · **資料**：Ken French 兩個 zip（`bubindfetch.ff49` → `us_ff49x`／`us_ff49n`／`us_ff49s`，整段換）、類股 ETF 與 SPY（`us_etf_*`）、S&P 500 GICS 類別
    （`fwdfetch.update_gics`）——都在 `fetch_heat_us.py` 每天抓；回補 `usfill:ind_ff,ind_etf,gics`。台股產業指數在 `fetch_heat.py` 每天算好存
    `data/lab/indtw/{YYYY-MM}.json.gz`（`bubind.indtw_update`，官方分片有新交易日才重算；回補 `heatfill:indtw`）。
  · **程式**：`arm/lab/bubind.py`（指數、條件、現在的狀態、驗證；美股 49 細產業每天只算最後一個月 `ff_last_row`，和完整算法相同、測試鎖住）、
    `arm/lab/bubindpage.py`（表、點一列展開說明＋歷史圖、驗證）、`bubpage.view()` 呼叫 `bubind.compute()`（約 5.5 秒，失敗只顯示警告）。
    研究檔 `data/lab/bubind_research.json`＝`TZ=Asia/Taipei python3 scripts/run_bubind.py`（約 36 秒；資料或規格改了才重跑）。
  · **結果（規劃第 12.7 節）**：**主要假說成立**——美股 49 細產業「兩年翻倍、比大盤多漲、在高點」之後兩年內跌 40% 的比例 37.7%，全部 12.7%
    （663 個產業月份、30 段，95% 區間 +12.6～+38.1 個百分點、前後兩半同向）；價格爆發、偏離趨勢、價格過熱也都較容易大跌，新公司大量進來單獨看不出。
    台股（2018 起）方向相同但只有 3～4 段，只描述。現在：台股電子零組件業等級 3（價格爆發＋漲得比營收快），等級 2 六個；美股 XLK 等級 2；
    Ken French 等級 2 八個（2026-08）。
  · **已下市公司的產業別（bubindspec VER 2，2026-10-19；`docs/lab_crash_plan.md` 第 21 節）**：原本曾經 ≥ 40 億的 103 檔已下市公司只算進大盤（存活者偏誤）。
    MOPS 月營收彙總表的歷史頁面已重新產製、不含已下市公司，MOPS 公司基本資料對已下市公司回「不繼續公開發行」→ 改用**官方歷史分類行情**：
    證交所 MI_INDEX（type＝產業代碼）、櫃買 stk_wn1430（se＝產業代碼）查 2013 年起每年第一個交易日（`arm/lab/indhist.py` → `data/lab/indsnap.json`，
    CI 回補 `.ping/lab` 第一行 `indfill`），現在產業表沒有的代號用最後一次出現的分類；證交所 07、13 是彙總類（`IND_HIST_AGG`）不算。
    103 檔找到 101 檔（另 2 檔是存託憑證）。`bubind.tw_ind_map()`＝現在的產業表優先＋已下市公司。結果：光電、生技過去的報酬變低（3.11→2.82、1.42→1.29 倍），
    研究判定與現在的狀態都沒變。現在的公司以後下市會留在 `stockmeta`（只增不刪），快照不必每天抓。
  · **台股細分族群（bubindspec VER 3，2026-10-19；`docs/lab_crash_plan.md` 第 21.5～21.6 節）**：使用者選「精選約 15 個電子族群、用現在的成員往回算＋標明、
    CPO 用光通訊代替」。名單＝櫃買中心產業鏈平台（`arm/lab/icchain.py` → `data/lab/icchain.json`；本容器擋 ic.tpex.org.tw，CI 抓：`.ping/lab` 第一行 `icfill`，
    每天 `fetch_heat.py` 30 天內抓過就跳過）。17 個族群在 `bubindspec.TG_GROUPS`（產業鏈代碼、節點名稱、IC 設計分頁），成員只留現在上市櫃、≥ 5 家；
    指數與條件同台股產業（`bubind.tw_build(groups=…)`，一家公司可以在好幾個族群）→ `data/lab/indtg`（每檔帶名單日期 `src`，名單換了整段重算）。
    頁面＝產業段台股產業表下面一張表（class `bgrp`，點一列看成員）；研究檔 `tg` 只描述、不判定、不進訊號總覽。
    ⚠ IC 設計的分頁標題是純文字「LED驅動IC (12家)」不是 `<b>`——解析以「文字(N家)」切段、分頁依序對段落並核對家數；
    ⚠ 泡沫頁的等級磚已經用 `.btg`，第一版表格 class 撞名變成 grid（新 class 先 grep `bubpage.CSS`，`tests/test_bubind_tg.py` 守）。
