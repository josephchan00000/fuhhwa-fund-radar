# 美股景氣頁

> 四個指數、規格、泡沫模型、資料、各指數自己的情緒籌碼。
>
> 這一頁目前是從 CLAUDE.md 逐字搬來的（知識庫第一段），還沒整理；有出入時以 CLAUDE.md 為準。
> 改內容先改 CLAUDE.md，再跑 `python3 scripts/wiki_split.py` 重產這一頁。

<!-- CLAUDE.md 第 2522–2584 行 -->
## 「美股景氣」頁＋泡沫面向（2026-10-18 使用者需求；規劃、規格、結果 `docs/lab_heat_us_plan.md`）

使用者原話：「如果套用在美股呢？nasdaq sp500 費半指數 詳細規劃後執行，然後你也順便去找外面各大的泡沫模型去加入，邏輯跟之前一樣」
＋「我想要點那個 . 之後先出現景氣頁面，個股頁面放旁邊」。四個決定（AskUserQuestion）：**一頁切換指數**；**泡沫模型台美都加**
（台股頁變六個面向，原本五個不變）；**點「·」先到景氣頁、不要窄欄**（三頁共用頂欄 台股景氣｜美股景氣｜個股）；**那斯達克兩個都做**（共四個指數）。
- **規格事前寫定**（看任何美股與泡沫結果之前 commit）：`arm/lab/heatspec_us.py` VER 1（`tests/test_heatspec_us.py` 鎖住）＋`heatspec.py` VER 7（台股泡沫面向）；
  規劃文件第 15 節是規格、第 15.9 節是寫程式時補的細節（都在看結果之前）、第 16 節是結果。**要改＝VER＋1，不在看過結果之後改。**
  · 四個指數：S&P 500（Yahoo `^GSPC` 1927-12-30 起，**驗證從 1950-01-01 起**，之前只暖身）、那斯達克（1971）、那斯達克 100（1985）、費半（1994）。
  · 五個面向：基本面（F1～F9）、情緒籌碼（S1～S5）、資金（R1～R10）三個面向四個指數共用；技術（T1～T4、T8、T9、T11～T13）、泡沫（X1～X9）依指數各算；
    費半另加 F10 全球半導體銷售、F11 台積電營收；那斯達克兩檔與費半另加 T14 相對 S&P 500、X11 扣掉 S&P 500 的兩年漲幅；S&P 500 另加 X10 股價 ÷ 股利 PSY。
  · 美國資料當天收盤就用（台股頁「美國資料晚一天」不適用）；有效聯邦基金利率晚一天；CFTC 資料日＋4 天、H.4.1 ＋2 天才算拿得到。
  · 和台股頁共用、被當成函式預設參數的統計常數一律從 heatspec 匯入（兩邊同一份，tests 守）。
- **泡沫模型**（`arm/lab/heatbubble.py`，和直接算的版本逐項比對，`tests/test_heatbubble.py`）：
  · **PSY**（Phillips–Shi–Yu）：實質股價取對數、BSADF（視窗至少 60 個月）；同長度隨機漫步模擬 2,000 次的臨界值存 `data/lab/heat/psy_cv.json.gz`
    （中位數＝50、95% 臨界值＝80）；缺口之後重新起算。**長期趨勢偏離**：對數實質股價對月份回歸（至少 240 個月），50＋15z。
    **LPPLS**：每週最後一個交易日、125 個視窗 × (m, ω, tc) 網格（numpy），正泡沫比例 − 負泡沫比例 → 50＋100×差；網格近似、沒做 Shu & Zhu 的殘差檢定，頁面照寫。
    **兩年漲幅、加速度**和自己過去 10 年（2,500 個交易日）比；**CAPE** 用延後 6 個月的 10 年平均實質盈餘；**巴菲特指標、Tobin's Q**＝最新拿得到的 Z.1 季資料
    乘 S&P 500 漲跌推到月底、除長期趨勢後比過去 120 個月。台股泡沫：PSY、趨勢偏離（國發會月平均 1982 起）、兩年漲幅與加速度（加權指數 1990 起）、
    LPPLS、上市櫃本益比、上市櫃市值 ÷ GDP（2013 起）。
  · **LPPLS 歷史**一次算好入庫（`data/lab/heat/us_lppls_{spx,ixic,ndx,sox}.json.gz`、`tw_lppls.json.gz`；`scripts/run_heat_us.py --lppls`，4 個行程 334 秒）；
    每天只補新的週，**週中算的那一筆會拿掉重算**，所以每天補的和整段一次算的一樣（測試守）。LPPLS 多數週是 0（S&P 500 5,019 週只有 793 週非 0）＝正常。
  · **參考讀數（不進分數）**：Hussman 條件數、RSP ÷ SPY 1 年變化、高盛熊市風險指標近似；台股：台積電市值占比。
  · **泡沫事件驗證**（`heatspec.BUB_*`）：月底讀數 ≥ 80 之後一年內最大跌幅 ≥ 20%、兩年內 ≥ 40%（收盤高點到之後低點，t＋1 起算）的比例 vs 所有月份；
    12 個月區塊重抽；≥ 80 少於 12 個月或少於 4 段＝樣本不足。台股另用國發會月平均（含 1990 泡沫）做延伸樣本，只當穩健度。
- **程式**：`heatspec.use(heatspec_us.spec_for(idx))` 換規格、`heatpage.use_market(...)` 換說法（台股／S&P 500…、加權指數／指數名、休市表），
  所以 heatcalc／heatrel／heatreg／heatpage 台美共用同一套；`arm/lab/heatcalc_us.py`（組資料、長歷史接法、CAPE、Z.1、研究）、`heatcalc_bub.py`（台股泡沫）、
  `heatpage_us.py`（美股頁）、`appnav.py`（共用頂欄）。研究 `TZ=Asia/Taipei python3 scripts/run_heat_us.py`（四個指數各一個行程，2026-10-18 實測 938 秒）
  → `data/lab/heat_us_research.json`（約 6MB；資料或規格改了才重跑）；台股 `run_heat.py` 加了泡沫之後約 510 秒。
- **資料**（`arm/lab/heatfetch_us.py`、`scripts/fetch_heat_us.py`；只在 CI 抓）：Yahoo（四個指數、VXN、VIX3M、美元指數、RSP、SPY）、DBnomics 轉載聯準會
  H.15／H.4.1／H.6 M2／Z.1、BEA GDP、CFTC（資產管理人 E-mini、槓桿基金 VIX、非商業大型＋E-mini）、費城聯準銀行（製造業指數、ADS）、OECD 領先指標、
  勞工部初領救濟金、勞工統計局（失業率、CPI、核心 CPI）、密西根大學、聯準會超額債券溢酬、Shiller 資料檔、WSTS、證交所 FMTQIK 1990～1998、主計總處季 GDP。
  每天：afterhours 每班與 `daily_fund.sh` 跑 `fetch_heat_us.py`（timeout 420；已到最近美股收盤日就不再打 Yahoo、週月季資料一天一次、LPPLS 有新週才算）；
  回補：`.ping/lab` 第一行 `usfill`。daily／afterhours 安裝 numpy xlrd openpyxl（失敗只告警）。U1 探針確認不收：芝加哥聯準銀行兩個指數的檔案停在 2026-04（改用費城聯準銀行 ADS）、FINRA 融資 403（改用 Z.1 家計證券融資）。
- **頁面** `dashboard/x9mu.html`（一頁四個指數：頁面只放 S&P 500 的主畫面；細項面板與其他三個指數放 `dashboard/x9mup-{指數}.json`，點到才下載，
  2026-10-24 起，見「市場頁」專段最後一條；切換時換上內容、換 `window.HEAT_META`、呼叫 `window.heatInit()`，用 AbortController 拿掉上一次掛在
  document／window 的事件；網址 `#ix=ndx` 可直開）＋對照圖資料每個指數一檔 `dashboard/x9muh-{spx,ixic,ndx,sox}.json`（選到才下載；S&P 500 約 2.5MB、
  壓縮 595KB）。台股頁的「泡沫」卡與「泡沫事件」驗證表 2026-10-18 起搬到泡沫頁（見「泡沫頁」節），對照圖預設只選前 5 條。三支 workflow 各兩行
  `git add -f dashboard/x9mu.html`、各兩行 `git add -f dashboard/x9muh-*.json`、各兩行 `git add -f dashboard/x9mup-*.json`（分開 add；本機不 commit，同 x9m.html）。
- **結果（2026-10-18，規劃文件第 16 節；只當參考）**：台美一致的只有三件事——基本面熱了之後較弱（台股、S&P 500、那斯達克）、美國貨幣基金 ÷ S&P 500
  熱了之後較強（只有 2015-12 起）、泡沫面向分數本身看不出。泡沫項目「熱了之後較容易大跌」只在 PSY（S&P 500 一年內 32% 對 16%、那斯達克 64% 對 33%、
  台股延伸樣本 71% 對 33%）、那斯達克兩年漲幅、費半的估值（兩年內）出現，多半兩年內就看不出；S&P 500 的 CAPE、巴菲特指標、Tobin's Q 反而是兩年內較少大跌
  （高估值可以維持很多年）。第六版主要假說四個指數都沒過。**不因結果不好看改規格**（同其他研究的紀律）。
- **各指數自己的情緒籌碼（heatspec_us VER 3，2026-10-29；規劃、探針、規格 `docs/lab_us_chip_plan.md`）**：使用者：「費半、納指的籌碼指標都跟
  s&p500 一樣，是不是不太合理」。VER 2 的 S1～S5 四個指數共用（舊分數和費半之後 10 日漲跌的等級相關只有 −0.019），使用者選「自己的優先、沒有就用最接近的代理」、
  成分股內部人一起做。項目（`ONLY` 決定哪個指數有）：S&P 500＝S1、S2（S&P 500 期貨）；那斯達克兩檔與費半＝S8、S9（那斯達克 100 期貨，CFTC 209742／209741；
  費半沒有期貨、用它代理）；四個都有 S3、S4、S5（名稱標「全市場」）、**S6 槓桿 ETF 做多比重**（3 倍多空一對近 20 日成交金額，SPXL／SPXS、TQQQ／SQQQ、SOXL／SOXS；
  Direxion 沒有發行份數歷史，所以一律用成交金額、不用資金流）、**S7 成分股內部人淨買比例**（`arm/lab/insider.py`）。第六版核心項目那斯達克兩檔與費半用 S8、S9 取代 S1、S2（`spec_for` 換 DERIV、M6_GROUPS）。
  · **內部人資料**：SEC 每季資料集（2006q1 起；網址從資料集頁讀，`/files/structureddata/…` 與 `/files/datastandardsinnovation/…` 混用）＋最新一季之後的 EDGAR 每日索引 Form 4 原件；
    只留 Form 4（不含 4/A）、非衍生性交易、代碼 P／S、申報人之一是董事或經理人；存 `data/lab/ins/{YYYY-MM}.json.gz`（依申報日，`{日: {CIK: [淨股數, 當時在 S&P 500]}}`），
    名單 `data/lab/heat/ins_members`（S&P 500 歷史期間、現在的那斯達克 100、產業代碼 3674 ∪ 現在的費半）、進度 `ins_state`（`through`＝涵蓋到哪天，之後的交易日 S7 沒有值）。
    SEC 聯絡 email **只從 secret `SEC_CONTACT_EMAIL` 讀**（afterhours 的美股景氣步驟與 lab_backfill 有帶），程式與存檔不出現（`tests/test_insider.py` 守）。
    每天 `fetch_heat_us.py` 一天一次（150 秒上限、做不完下次續做）；回補 `.ping/lab` 第一行 `uschipfill`（或 `uschipfill:ins`、`:lev`、`:cftc_nq`，時間上限 3300 秒）。
  · **大跌後買點 C5 不改**：bottomspec 規定四個指數都用 S&P 500 期貨（S2 原始值）；VER 3 起那斯達克頁的 B 沒有 S2，另外放 `B["xraw"]["S2"]`（`heatcalc_us.build`），bottom.py 先找 raw 再找 xraw。
  · 大跌風險 crashspec VER 2、反向檢查 hotchspec VER 2 的美股變數跟著依指數（`PRED[idx]`、`CHIP_VARS[idx]`、`hotchpage.ORDER[mk]`）。
  · **結果（規劃第 9 節；只當參考）**：情緒籌碼面向 60 日 S&P 500、那斯達克、那斯達克 100 從「看不出」變「熱了之後較弱」（−0.155／−0.144／−0.158），
    主力是 S6（60 日 −0.17～−0.23）；**費半換成自己的籌碼仍看不出**（SOXL／SOXS 前後兩半方向相反）；**S7 內部人四個指數都看不出**（照規格留著，要換算法＝新版本、先問使用者）。
    那斯達克兩檔 S6 熱之後大跌風險、反向檢查的回撤都較大。
- **踩過的坑**：①**Granger 多重比較要分家族**——第一次跑台股時 51 項放同一家族，原本 44 項的 q 值全動、「台灣 CPI：台股 → 這一項」從看不出變成立；
  改成「原本項目／泡沫項目／面向分數」三個家族（`heatrel.gr_families()`），原本五個面向的結果和第六版一樣（照實記錄是看到輸出後才決定）；
  ②X2、X3 的 10 年百分位要在**指數自己的交易日**上算再對齊（直接在台股頁日曆上算，覆蓋只到 2002-06 起）；③分數四捨五入會跨區（79.6 寫成「80 偏熱」）
  → `heatpage.n0()`／頁面 JS `sc0()`：跨到下一區時改成無條件捨去到一位小數；④本機建台股頁到暫存目錄要 `HP.build(out, data_out)` 兩個路徑都給，
  只給 out 會把 `dashboard/x9mh.json`（有入庫）改掉——改到就 `git checkout -- dashboard/x9mh.json`。

