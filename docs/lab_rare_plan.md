# 少見但勝率高的策略（2026-10-27）

## 1. 要回答的事

使用者（2026-10-27）：

> 有其他的策略可以研發嗎？幫我深度研究一下還有回測那些的，不用很常觸發但可以有機會勝率高就好

所以這一份研究找的是：**網頁上還沒有、一年頂多出現一兩次（有的四年一次）、出現之後買進的勝率高的做法**，
照原說法的參數，在我們的資料上（含來源沒用到的期間）回測，看還成不成立。

先講清楚一件事（之前研究過、會影響怎麼看結果）：**次數少的訊號，過去的勝率之後縮得很多**
（`docs/lab_practical_plan.md` 第 1～3 節逐年檢查：次數 5～14 次的訊號，之後那一年的勝率大多回到接近平常）。
所以這一份除了看全期間，還另外看三段「規則挑選時沒用到的期間」：來源發表之後、S&P 500 1950 年以前、近 10 年；
另外列打亂測試與二項檢定，讓「勝率高」有多少是運氣看得出來。

## 2. 盤點：網頁上已經有的（不重複做）

| 已經有的 | 在哪裡 |
|---|---|
| RSI(2) 超賣反彈、VIX 衝刺、月底月初、Halloween、10 個月均線、200 日均線、12 個月動能 | 總經策略（xstratspec） |
| Coppock、VIX 衝上 40、Zweig 寬度衝刺、跟進日、季線乖離 −15%、融資維持率跌破 140%、融資去化、Lowry 90% 日 | 總經策略落底型 |
| 大跌後的落底訊號（5 日急跌、跌 10% 之後的 C1～C9） | 大跌後檢查（bottomspec）、訊號總覽 |
| 景氣項目過熱過冷、技術事件、法人買賣超、情境、泡沫 | 訊號總覽（sigspec） |
| 期貨加碼（200 日均線上加碼等） | 研究結論第 2 則（tiltspec） |
| 選擇權到期週（不納入）、毛利 ÷ 總資產（試用）、低波動（候選） | 策略候選 c001～c003 |

這一份的九條都不在上面。

## 3. 來源（每條規則的原說法）

| 代號 | 規則 | 原說法 | 出處 |
|---|---|---|---|
| mid | 期中選舉後抱一年 | 1950 年以來美國期中選舉之後 12 個月，S&P 500 每一次都上漲（19 次，平均約 12～18%） | Yale Hirsch 總統週期；[BNY](https://www.bny.com/investments/us/en/individual/articles/markets-and-economy/how-do-midterm-elections-impact-markets-over-time.html)、[U.S. Bank](https://www.usbank.com/investing/financial-perspectives/market-news/stock-market-performance-after-midterm-elections.html)、LPL Research |
| santa | 聖誕老人行情 | 12 月最後 5 個交易日＋1 月前 2 個交易日，1950 年以來約 78% 上漲、平均約 1.3% | Yale Hirsch（1972）；[LPL Research](https://www.lpl.com/research/blog/will-the-santa-claus-rally-spark-a-bullish-start-to-2026.html)、[CFI](https://corporatefinanceinstitute.com/resources/uncategorized/santa-claus-rally/) |
| jan | 一月晴雨表 | 一月上漲的年份，之後 11 個月比一月下跌的年份好（1940～2003）；拉長到 1926～2012 這個現象不見了 | [Cooper、McConnell、Ovtchinnikov（2006, JFE）](https://doi.org/10.1016/j.jfineco.2006.03.001)；Darrat、Li、Chung（2013）；[CNBC](https://www.cnbc.com/2020/01/02/januarys-first-five-days-has-a-track-record-at-predicting-full-year.html)、[Fidelity](https://www.fidelity.com/viewpoints/active-investor/january-barometer) |
| ath | 隔一年以上的第一個歷史新高 | 之後一年 13／14 次上漲、平均約 14%；Ned Davis 1954～2016：九成以上上漲 | [Schaeffer's（2024）](https://www.schaeffersresearch.com/content/analysis/2024/01/24/when-to-buy-stocks-after-a-fresh-spx-record)、[SentimenTrader](https://sentimentrader.com/blog/the-first-sp-500-new-all-time-high-in-more-than-a-year) |
| bull | 熊市後漲兩成 | 從熊市低點漲 20% 之後一年約 92% 繼續上漲（1950 年代以來） | Bank of America（經 [MarketGauge](https://marketgauge.com/resources/market-outlook/the-sp-500-enters-a-new-bull-market-2/) 轉述）、Carson Group、[LPL（2023）](https://www.lpl.com/content/dam/lpl-www/documents/asset-library/weekly-market-commentary-06262023.pdf) |
| vixinv | VIX 期限結構倒掛 | 近月 VIX 高過三個月期 VIX3M＝恐慌，常在急跌低點附近；也有研究發現倒掛之後 4 週沒有方向優勢 | Johnson（2017, JFQA）；[Fassas、Hourvouliades（2019）](https://mdpi-res.com/d_attachment/jrfm/jrfm-12-00113/article_deploy/jrfm-12-00113-v2.pdf)；反例 [FlashAlpha（2026）](https://flashalpha.com/articles/vix-term-structure-inversions-since-2018-data-study) |
| lnypre | 封關前一週 | 農曆年休市前，亞洲七個市場（含台灣）報酬明顯偏高（1999～2012）；投信統計封關前最後一週約八成上漲 | [Yuan、Gupta（2014, QREF 54(4)）](https://ideas.repec.org/a/eee/quaeco/v54y2014i4p529-537.html)；[中時（2025）](https://wantrich.chinatimes.com/news/20251229900005-420101) |
| lnypost | 封關日買、抱過開紅盤 20 天 | 開紅盤後 20 個交易日上漲機率約 92%（過去 12 年） | [中央社（2019）](https://www.cna.com.tw/news/afe/201902100118.aspx)；[Minh、Son（2019）](https://vjol.info.vn/DHNHHCM/article/view/40166)：台灣有年後效應 |
| nsf | 國安基金進場 | 進場隔天上漲機率約 86%；九次除了 2000 年 3 月第一次都獲利出場 | [公視 2023 整理表](https://news.pts.org.tw/article/632082)、[商業周刊](https://www.businessweekly.com.tw/focus/blog/3018235)、[工商時報](https://ctee.com.tw/news/finance/350284.html)、[TechNews 2025-04-08](https://technews.tw/2025/04/08/support/) |

國安基金九次的起始日（來源不一致時取較晚的一天）：2000-03-16、2000-10-03、2004-05-20、2008-09-19、2011-12-21、2015-08-25、
2020-03-20、2022-07-13、2025-04-09。

看過、沒有做的：

- **聯準會在歷史新高附近降息**（Carson、Citi、SentimenTrader：之後一年每次都漲）：需要 1990 年以前的利率目標表（容器與 CI 都拿不到聯準會網站），
  而且同一輪降息的幾次會被當成同一次——1990 年以後去重只剩 4 次，次數不夠。
- **連跌 5 週**：SentimenTrader（2026）整理 1921 年以來的結果「好壞參半、平均比平常差」，不是勝率高的做法。
- **節日前一天**：一年 9 次左右，不算少見，而且單日報酬扣成本後很小。

## 4. 事前事實（只數次數，沒有算報酬）

評估起點（第 5 節）之後的觸發次數（事件型是去重以前的次數）：

| 規則 | 台股 | S&P 500 | 那斯達克 | 那斯達克 100 | 費半 |
|---|---|---|---|---|---|
| 期中選舉 | 8 | 19 | 13 | 10 | 7 |
| 聖誕老人行情 | 35 | 76 | 54 | 40 | 31 |
| 一月晴雨表（一月上漲的年／完整的年） | 18／35 | 46／76 | 36／54 | 27／39 | 18／30 |
| 隔一年以上的新高 | 3 | 15 | 8 | 3 | 6 |
| 熊市後漲兩成 | 19 | 13 | 20 | 16 | 31 |
| VIX 期限倒掛 | 22 | 23 | 23 | 23 | 23 |
| 封關日（1990～2026，和農曆年日期逐年核對全部對得上） | 37 | | | | |
| 國安基金 | 9 | | | | |

S&P 500 隔一年以上的新高：1954-09、1958-09、1961-01、1963-09、1967-05、1972-03、1980-07、1982-11、1985-01、1989-07、
1995-02、2007-05、2013-03、2016-07、2024-01。台股只有 3 次（2020-07、2024-02、2025-08）＝次數不夠。

## 5. 規格（`arm/lab/rarespec.py` VER 1，算任何報酬之前寫定）

- **資料**：總經策略同一份收盤（指數不含息）；VIX、VIX3M＝景氣頁同一份（VIX3M 2006-07 起）。
- **期間**：S&P 500 從 1950 年（來源都從 1950 年起算）；其他從資料第一天之後滿一年：台股 1991-01、那斯達克 1972-02、
  那斯達克 100 1986-10、費半 1995-05。S&P 500 1928～1949 另外算一次（來源沒用到的期間，只描述）。
- **成本**：台股每一邊 0.1%、美股 0.025%（同總經策略，用 ETF 的成本）。
- **進出時點**：事先知道的日子（選舉日、12 月最後幾天、封關日）照排定那天收盤買賣；看收盤才知道的（一月漲跌、新高、熊市、VIX、
  國安基金公告）隔一個交易日收盤買，抱固定的交易日數。國安基金比它第一天進場晚一天買。
- **每一條的精確定義與參數鄰近**：見規格第 3、4 節。
- **判定**（同總經策略落底型 VER 6）：至少 5 次、賺錢的比例 ≥ 60% 而且不低於隨便挑一天（抱一樣多天）、中位數 ＞ 0、排除極端的平均 ＞ 0；
  ★＝近 10 年（5 次以上才看）也過、參數鄰近至少三分之二過；●＝只有全期間過；○ 沒過；— 次數不夠。不到 15 次另外標「次數少」。
- **建議的條件**（事前寫定，第 7 節）：主要市場（美國規則＝S&P 500，台灣規則＝台股）★，而且「來源發表之後」與「S&P 500 1950 年以前」
  （有 3 次以上的那一段）賺錢比例都不低於同一段的隨便挑一天＝**建議試用**；主要市場 ●、或 ★ 但另外那段沒過＝**可以觀察**；其他＝**不建議**。
- **只描述**：打亂測試、二項檢定、前後兩半、中途最多跌、全部資金照做的年化與最大回撤、每一次的清單、現在的狀態。

要注意的事：九條規則 × 最多五個市場＝33 組，就算每一條都沒用，也會有一兩組碰巧看起來很好——所以建議只看主要市場，
其他市場是看能不能推廣；打亂測試與二項檢定一起列。

## 6. 結果

（規格 commit 之後才算，結果寫在這裡。）
