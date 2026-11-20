# 美股財報季

> 選擇權頁（隱藏頁）「財報」分頁的美股：復華基金前十大與自家 ETF 的美股、美股強勢品質股，這一季 EPS 對預估（兩家一致才標）、營收對公布前最後一版預估、獲利比去年、財報後股價（看盤前盤後）、接下來兩週要公布的、基金持股成績。
> 原始資料：`docs/lab_earnings_plan.md` 第 11.2 節；程式：`arm/lab/ernusspec.py`（規格）、`arm/lab/earnusdata.py`（CI 抓）、`arm/lab/earnus.py`（算）、`arm/lab/earnpage.py`（頁面）
> 最後更新：2026-11-20

## 現在怎麼運作

使用者 2026-11-20「好 繼續」＝做第 4 段美股（台股見 [台股財報季](earnings-tw.md)）。
- 清單（`earnus.members`）：復華基金前十大裡國別「美國」、有代號的（`config/holding_profiles.json`）＋自家 ETF 持股代號以「 US」結尾的（00409A…）＋美股強勢品質股（`fund_intro.qm_codes`）。ETF 排除（名稱或簡介第一句有 ETF，`earnus._is_etf`）；GOOG 併成 GOOGL（`ernusspec.ALIAS`，同一檔基金兩種股別比重相加）。2026-11-20 是 70 家。
- 資料：`afterhours_refresh.yml` 每一班叫 `scripts/fetch_earn_us.py`（`earnusdata.update`，同一個美股收盤只抓一次，`uscard.last_close`）。一家三個請求：Yahoo quoteSummary（`earnings` 的 earningsChart＝近 4 季實際 EPS、當時預估、期末日、公布時間；financialsChart＝營收、淨利；`earningsTrend` 0q＝目前這一季的預估；`calendarEvents`＝下次財報日；`incomeStatementHistoryQuarterly` 只拿營收，其他欄位 Yahoo 給 0）、Yahoo 季資料（fundamentals-timeseries：更早幾季的營收、淨利，最新一季常晚幾天）、Yahoo 日線（近 150 天）。那斯達克財報行事曆只抓清單內公司公布的那幾天（`nq_need`）。全部落在 `data/lab/earn_us_raw.json`（一家一行）。
- 公布前最後一版營收預估（`earnusdata.snapshot`）：每天記目前這一季的預估，那一季公布時間過了就不再改。2026-11-20 才開始記，所以 2026 第三季全部「沒有公布前的營收預估紀錄」，第四季起才有。
- 計算（`earnus.build`，`scripts/gen_fund_dashboard.py` 建選擇權頁之前叫 `earnus.write` → `data/lab/earn_us.json`）：季的歸屬＝期末日往前 45 天的日曆季（`earnus.cq`：10/31 結帳算第三季）；這一季＝今天往前 15 天之前最近的季底（`earnus.season`）。EPS：Yahoo 與那斯達克各自判高於／差不多／低於（差 ≤ 預估 2%，至少 1 美分），一樣才標，不一樣寫「兩家不一致」與兩邊數字。財報後股價（`earnus.react`）：盤前公布＝前一天收盤 → 當天收盤，盤後＝當天 → 隔天，盤中或沒時間＝前一天 → 隔天。獲利＝淨利；轉盈算成長、轉虧算衰退、兩年都虧不算（`earnus.growth`）。
- 頁面（`earnpage.block(台股, 美股)`）：最上面「台股｜美股」切換（`.ern-mkt`，記在瀏覽器 `ernMk`）；兩個市場各一塊 `.ern-pane`，控制項用 class 找（`.ern-grp`、`.ern-q`、`.ern-n`、`.ern-fs`；美股的 id 加 `-us`，不重複）。美股分組＝誰持有最多／公布日（新到舊，`data-s` 排序鍵，還沒公布排最後）；篩選＝EPS 高於／低於、兩家不一致、比去年好／差、財報後上漲／下跌、還沒公布、我的清單。沒有美股資料時只顯示台股、沒有切換。

## 不能改的規則

- 規格先寫、改＝VER＋1；只寫已經發生的數字，不寫「之後會怎樣」。主頁不放。
- 高於／低於只在兩家一致時標；營收對預估只有 Yahoo 一家，照寫來源；開始記之前公布的季不補。
- 抓取只在 CI（本容器擋 Yahoo、那斯達克）；探針 `scripts/probe_earnus.py`（lab_backfill 的 `earnusprobe` 模式）只印不寫。

## 踩過的坑

- 那斯達克財報行事曆的公布時間一律「沒提供」，分盤前盤後要用 Yahoo earningsChart 的 reportedDate（有到分鐘）。
- 那斯達克和 Yahoo 的實際 EPS 常不是同一個口徑（第 3 節試算：MANH 1.55 vs 1.04），所以才要兩家一致。
- 貝萊德簡介裡寫「旗下 iShares ETF」被當成 ETF 排掉 → 只看名稱和簡介第一句。

## 歷史

- 2026-11-20 規格 VER 1（`5f1f6d77`，算之前寫定）；資料探針同日在 CI 跑過（NVDA、MSFT、CROX、MANH）。
