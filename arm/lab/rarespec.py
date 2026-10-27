"""少見但勝率高的策略（docs/lab_rare_plan.md）——規格 VER 1（2026-10-27 寫定）。

使用者（2026-10-27）：「有其他的策略可以研發嗎？幫我深度研究一下還有回測那些的，不用很常觸發但可以有機會勝率高就好」。

要回答的事：**網頁上還沒有、一年頂多出現一兩次、但出現之後買進的勝率高的做法，在我們的資料上（含來源沒用到的期間）還成不成立？**
九條規則（第 3 節），參數照原說法；五個市場都算（台股、S&P 500、那斯達克、那斯達克 100、費半）——美國的規則以 S&P 500 為主
（原說法的市場），其他市場看能不能推廣；台灣的規則只算台股。判定照總經策略落底型（xstratspec VER 6），結果可以直接和策略頁比。

**事前寫定**：規則、參數與參數鄰近、評估期間、成本、進出時點、判定、建議的條件、只描述的項目，都在算任何一個報酬之前寫進這裡並 commit；
tests/test_rarespec.py 鎖住。要改＝VER＋1、日期與原因寫進規劃文件，不在看過結果之後改舊版本。

**寫這一版之前已經看過的**（規劃第 3、4 節）：
  ·各來源宣稱的成績（期中選舉後一年 S&P 500 1950 年以來每次都漲；聖誕老人行情約 78%；一月上漲、全年上漲約八成；
   封關前最後一週約八成上漲、開紅盤後 20 個交易日 92% 上漲；隔一年以上的第一個歷史新高、一年後 13／14 次上漲；
   熊市後漲兩成、一年後 92% 上漲；國安基金進場隔天上漲約 86%；VIX 期限倒掛「沒有方向上的優勢」）。
  ·每個規則、每個市場的觸發次數與日期（只數次數，沒有算報酬）。
  ·憑記憶知道的：2000 年兩次國安基金進場之後一年台股是跌的；2008、2020 年大跌之後一年是漲的。
**沒有算過**：任何一條規則在我們資料上的報酬、賺錢比例、和隨便挑一天的比較。
"""
from __future__ import annotations

VER = 1
SPEC_DATE = "2026-10-27"

# ── 1. 市場與期間 ───────────────────────────────────────────────────────────
# 收盤＝xstrat.data（總經策略、景氣頁同一份；指數不含息）。資料第一天：台股 1990-01-04、S&P 500 1927-12-30、
# 那斯達克 1971-02-05、那斯達克 100 1985-10-01、費半 1994-05-04。
# 評估起點：S&P 500 從 1950 年（來源都從 1950 年起算）；其他從資料第一天之後滿一年（新高、熊市要有一年以上的歷史）。
# 只算買進日 ≥ 起點、賣出日在資料裡的那幾次。
MARKETS = ("tw", "spx", "ixic", "ndx", "sox")
NAMES = {"tw": "台股", "spx": "S&P 500", "ixic": "那斯達克", "ndx": "那斯達克 100", "sox": "費半"}
START = {"tw": "1991-01-04", "spx": "1950-01-01", "ixic": "1972-02-07", "ndx": "1986-10-01", "sox": "1995-05-04"}
# S&P 500 1950 年以前（1928～1949，買進日在這段）：來源都從 1950 起算，這一段是「來源沒用到的期間」，同一套規則另外算、只描述。
EARLY = ("spx", "1928-01-01", "1949-12-31")
RECENT_YEARS = 10            # 近 10 年＝資料最後一天往前 10 年（同總經策略）

# ── 2. 成本與進出時點（同總經策略） ─────────────────────────────────────────
# 成本（每一邊，ETF）：台股 0.1%、美股 0.025%（同 xstratspec.COST）。淨報酬＝賣出價 ÷ 買進價 ×（1 − 成本）÷（1 ＋ 成本）− 1。
# 指數不含息（同總經策略；抱一年的規則少算約 1.5～3% 的股息，「隨便挑一天」也一樣少算）。
COST = {"tw": 0.001, "spx": 0.00025, "ixic": 0.00025, "ndx": 0.00025, "sox": 0.00025}
# 進出時點兩種：
#   排定（sched）：事先知道的日子（選舉日、12 月最後幾個交易日、封關日），照排定那天收盤買賣，沒有落後（同月底月初、Halloween）。
#   訊號（sig）：看收盤才知道的（一月漲跌、新高、熊市、VIX、國安基金公告）：訊號那天收盤之後才知道，隔一個交易日收盤買（LAG），
#     抱 H 個交易日、第 H 天收盤賣；一次訊號之後 H 個交易日內再出現不算新的一次（同總經策略落底型 xstrat.dedupe）。
LAG = 1
WHEN = ("sched", "sig")

# ── 3. 規則（參數照原說法；grid＝參數鄰近，含主參數） ─────────────────────────
GROUPS = {"cal": "日曆（每年或每四年一次）", "event": "少見的市場狀態", "tw": "台股專屬"}
US_HOME = "spx"

RULES = (
    {"k": "mid", "name": "期中選舉後抱一年", "grp": "cal", "when": "sched", "mk": MARKETS, "home": "spx",
     "who": "Yale Hirsch（Stock Trader's Almanac 的總統週期）；LPL Research、BNY、U.S. Bank 的統計",
     "src": ("https://www.bny.com/investments/us/en/individual/articles/markets-and-economy/how-do-midterm-elections-impact-markets-over-time.html",
             "https://www.usbank.com/investing/financial-perspectives/market-news/stock-market-performance-after-midterm-elections.html"),
     "claim": "1950 年以來美國期中選舉之後 12 個月，S&P 500 每一次都上漲（19 次，平均約 12～18%）",
     "logic": "美國期中選舉（每四年一次、在總統任期第二年的 11 月）之後一年，正好是總統任期的第三年；"
              "執政黨為了兩年後的大選，常在這段時間推出刺激經濟的政策，選舉的不確定也結束了。",
     "p": {"H": 250}, "grid": {"H": (190, 250, 310)}, "pub": None},
    {"k": "santa", "name": "聖誕老人行情", "grp": "cal", "when": "sched", "mk": MARKETS, "home": "spx",
     "who": "Yale Hirsch（Stock Trader's Almanac，1972）",
     "src": ("https://www.lpl.com/research/blog/will-the-santa-claus-rally-spark-a-bullish-start-to-2026.html",
             "https://corporatefinanceinstitute.com/resources/uncategorized/santa-claus-rally/"),
     "claim": "每年 12 月最後 5 個交易日加隔年 1 月前 2 個交易日，S&P 500 1950 年以來約 78% 上漲、平均約 1.3%",
     "logic": "年底假期交易清淡、年終獎金與退休金進場、節稅賣壓在 12 月中以前結束，年底這幾天常是小漲。",
     "p": {"before": 5, "after": 2}, "grid": {"before": (4, 5, 6), "after": (1, 2, 3)}, "pub": 1973},
    {"k": "jan", "name": "一月晴雨表（一月漲就抱到年底）", "grp": "cal", "when": "sig", "mk": MARKETS, "home": "spx",
     "who": "Yale Hirsch（Stock Trader's Almanac）；Cooper、McConnell、Ovtchinnikov（2006）",
     "src": ("https://doi.org/10.1016/j.jfineco.2006.03.001",
             "https://www.cnbc.com/2020/01/02/januarys-first-five-days-has-a-track-record-at-predicting-full-year.html",
             "https://www.fidelity.com/viewpoints/active-investor/january-barometer"),
     "claim": "一月上漲的年份，之後 11 個月平均明顯比一月下跌的年份好（1940～2003）；"
              "也有研究把資料拉長到 1926～2012 後發現這個現象不見了（Darrat、Li、Chung 2013）",
     "logic": "一月是法人調整一年部位的月份，一月的方向常反映當年的資金與景氣看法。",
     "p": {"th": 0.0}, "grid": {"th": (0.0, 0.01, 0.02)}, "pub": 2004},
    {"k": "ath", "name": "隔一年以上的第一個歷史新高", "grp": "event", "when": "sig", "mk": MARKETS, "home": "spx",
     "who": "Ned Davis Research；Schaeffer's Research；SentimenTrader",
     "src": ("https://www.schaeffersresearch.com/content/analysis/2024/01/24/when-to-buy-stocks-after-a-fresh-spx-record",
             "https://sentimentrader.com/blog/the-first-sp-500-new-all-time-high-in-more-than-a-year"),
     "claim": "S&P 500 隔一年以上才再創歷史新高之後一年，13／14 次上漲、平均約 14%（Ned Davis 1954～2016：九成以上上漲）",
     "logic": "空頭或盤整一年以上之後重新創新高，代表套牢的賣壓消化完了，常是新一段多頭的確認。",
     "p": {"gap": 250, "H": 250}, "grid": {"gap": (190, 250, 375)}, "pub": 2017},
    {"k": "bull", "name": "熊市後漲兩成（新多頭確認）", "grp": "event", "when": "sig", "mk": MARKETS, "home": "spx",
     "who": "Bank of America（Savita Subramanian）；Carson Group（Ryan Detrick）；CFRA（Sam Stovall）",
     "src": ("https://marketgauge.com/resources/market-outlook/the-sp-500-enters-a-new-bull-market-2/",
             "https://www.lpl.com/content/dam/lpl-www/documents/asset-library/weekly-market-commentary-06262023.pdf"),
     "claim": "S&P 500 從熊市低點漲 20% 之後一年，約 92% 繼續上漲（1950 年代以來）",
     "logic": "跌兩成以上（熊市）之後又從低點漲回兩成，通常代表最壞的時候過了；之後一年多半還在漲。",
     "p": {"th": 0.20, "H": 250}, "grid": {"th": (0.15, 0.20, 0.25)}, "pub": None},
    {"k": "vixinv", "name": "VIX 期限結構倒掛", "grp": "event", "when": "sig", "mk": MARKETS, "home": "spx",
     "who": "Johnson（2017）；Fassas、Hourvouliades（2019）；交易員常用的恐慌高點訊號",
     "src": ("https://mdpi-res.com/d_attachment/jrfm/jrfm-12-00113/article_deploy/jrfm-12-00113-v2.pdf",
             "https://flashalpha.com/articles/vix-term-structure-inversions-since-2018-data-study"),
     "claim": "近月恐慌指數 VIX 高過三個月期的 VIX3M（倒掛）＝短期恐慌比長期還高，常出現在急跌的低點附近；"
              "也有研究（FlashAlpha 2026）發現倒掛之後 4 週沒有方向上的優勢",
     "logic": "平常長天期的波動率比短天期高；倒過來代表市場正在恐慌、急著買短期保險，恐慌通常不會持續太久。",
     "p": {"th": 1.00, "reset": 60, "H": 60}, "grid": {"th": (1.00, 1.05, 1.10)}, "pub": None},
    {"k": "lnypre", "name": "封關前一週（紅包行情）", "grp": "tw", "when": "sched", "mk": ("tw",), "home": "tw",
     "who": "Yuan、Gupta（2014，亞洲七個市場的農曆年前效應）；投信統計",
     "src": ("https://ideas.repec.org/a/eee/quaeco/v54y2014i4p529-537.html",
             "https://wantrich.chinatimes.com/news/20251229900005-420101"),
     "claim": "農曆年休市前幾天，台股等亞洲市場的報酬明顯偏高（1999～2012）；投信統計封關前最後一週約八成上漲",
     "logic": "長假前散戶不願抱股過年、法人卻常在封關前作帳，加上年終獎金與節慶氣氛，封關前常是小漲。",
     "p": {"k": 5}, "grid": {"k": (3, 5, 7)}, "pub": 2013},
    {"k": "lnypost", "name": "封關日買、抱過開紅盤 20 天", "grp": "tw", "when": "sched", "mk": ("tw",), "home": "tw",
     "who": "中央社（2019）引用的統計；Minh、Son（2019，台灣有年後效應）",
     "src": ("https://www.cna.com.tw/news/afe/201902100118.aspx",
             "https://vjol.info.vn/DHNHHCM/article/view/40166"),
     "claim": "開紅盤後 20 個交易日上漲機率約 92%（過去 12 年）",
     "logic": "年後資金回流、新年度的資金布局開始，開紅盤之後幾週常是漲的。",
     "p": {"H": 20}, "grid": {"H": (10, 20, 40)}, "pub": 2019},
    {"k": "nsf", "name": "國安基金進場", "grp": "tw", "when": "sig", "mk": ("tw",), "home": "tw",
     "who": "國家金融安定基金歷次護盤紀錄（公視 2023 整理表、商業周刊、工商時報）",
     "src": ("https://news.pts.org.tw/article/632082",
             "https://www.businessweekly.com.tw/focus/blog/3018235",
             "https://ctee.com.tw/news/finance/350284.html",
             "https://technews.tw/2025/04/08/support/"),
     "claim": "國安基金進場隔天加權指數上漲機率約 86%；九次護盤除了 2000 年 3 月第一次，其他都是獲利出場",
     "logic": "國安基金只在股市急跌、恐慌時進場，進場本身代表政府表態穩定市場，常接近波段低點。",
     "p": {"H": 250}, "grid": {"H": (60, 120, 250)}, "pub": None},
)
KEYS = tuple(R["k"] for R in RULES)
BY_KEY = {R["k"]: R for R in RULES}

# ── 4. 規則的精確定義（t＝訊號那天；b＝買進那天；q＝賣出那天；都是收盤；天數＝交易日） ─────────────
# mid     選舉日 E＝11 月第一個星期一之後的星期二（年份除以 4 餘 2；1950、1954、…、2026）。
#         b＝E 當天或之前最後一個交易日（1968 年以前 NYSE 選舉日休市）；q＝b＋H。
# santa   y 年 12 月的交易日 Dy、y＋1 年 1 月的交易日 Jy：b＝Dy 倒數第 before＋1 天（＝最後 before 天之前那一天）、
#         q＝Jy 第 after 天（從 1 數）。Dy 至少 before＋1 天、Jy 至少 after 天才算。
# jan     y 年 1 月最後一個交易日 J、y−1 年 12 月最後一個交易日 P：收盤 J ÷ 收盤 P − 1 > th → t＝J、b＝J＋LAG、
#         q＝y 年 12 月最後一個交易日（資料要有 y＋1 年的交易日，12 月才算走完）。
# ath     t：收盤比之前所有日子（從資料第一天起）都高，而且上一次創新高是 gap 個交易日以前或更早（t − 上一次創新高那天 ≥ gap）。
#         b＝t＋LAG、q＝b＋H。
# bull    從資料第一天起記住最高收盤 M；收盤 ≤（1 − th）× M＝進入熊市，之後記住熊市裡的最低收盤 L；
#         收盤 ≥（1 ＋ th）× L＝新多頭確認（t），之後 M 從 t 的收盤重新記、等下一次熊市。b＝t＋LAG、q＝b＋H。
# vixinv  r＝VIX ÷ VIX3M（美股＝同一天；台股＝收盤時已經知道的前一個美股交易日，同總經策略 VIX 衝上 40）。
#         t：r ≥ th，而且之前 reset 個交易日的 r 都有值、都 < th。b＝t＋LAG、q＝b＋H。VIX3M 2006-07 才有。
# lnypre  封關日 C＝y 年 1/10～2/28 之間、和下一個交易日相隔最多日曆天的那一個交易日（農曆年休市）。b＝C 往前第 k 個交易日、q＝C。
# lnypost b＝C、q＝C＋H（＝開紅盤之後第 H−1 個交易日）。
# nsf     國安基金每一次護盤的起始日 S（第 5 節，都是交易日）：t＝S、b＝t＋LAG（比國安基金第一天進場晚一天，那時一定已經公告）、q＝b＋H。
# 評估：只算 b ≥ 起點（START）、q 在資料裡的；事件型（sig）照 b 的先後去重（同總經策略：上一次訊號之後 H 個交易日內的不算）。
LNY_WINDOW = ("01-10", "02-28")

# ── 5. 國安基金護盤起始日（各來源不一致時取較晚的一天——再晚一天買，不會用到還沒公告的消息） ──────
#   2000-03：3/15、3/16 兩種說法；2008-09：9/18、9/19；2011-12：12/20、12/21；2020-03：3/19 盤後決議、3/20 起進場；
#   2022-07：7/12 決議、7/13 起；2025-04：4/8 盤後決議、4/9 起。
NSF = (
    ("2000-03-16", "首次政黨輪替"),
    ("2000-10-03", "網路泡沫、油價上漲"),
    ("2004-05-20", "總統大選 319 槍擊案後"),
    ("2008-09-19", "金融海嘯"),
    ("2011-12-21", "歐債危機"),
    ("2015-08-25", "人民幣貶值、中國股災"),
    ("2020-03-20", "新冠疫情"),
    ("2022-07-13", "升息、俄烏戰爭"),
    ("2025-04-09", "美國對等關稅"),
)

# ── 6. 判定（同總經策略落底型 VER 6，xstratspec 第 6 節） ─────────────────────────
# 一次的淨報酬 r；n＝次數；win＝r > 0 的比例；med＝中位數；trim＝排除極端的平均（robust.trim_mean：去掉最好和最差各 TRIM_Q，
# 次數少於 TRIM_N 時各去掉一次）；base＝隨便挑一天：評估期間每一天都當買進日、抱一樣多天（同樣扣成本）賺錢的比例，
# 每一次用它自己的天數、再平均（同 xstrat.base_win）。
# 過關＝n ≥ N_MIN、win ≥ WIN、win ≥ base、med > 0、trim > 0。
# 近 10 年：買進日在近 10 年的那幾次；N10 次以上才看，同一條（不看次數下限）。參數鄰近：grid 每一組（含主參數）全期間過關的比例。
# ★ good：全期間過關、近 10 年過關或不到 N10 次、參數鄰近 ≥ GRID_OK；● ref：全期間過關，其他沒過；○ none；— few：不到 N_MIN 次。
# 不到 FEW_TAG 次另外標「次數少」（只是標示，判定不變）。
N_MIN = 5
N10 = 5
WIN = 0.60
TRIM_Q = 0.05
TRIM_N = 20
GRID_OK = 2 / 3
FEW_TAG = 15
TIERS = ("good", "ref", "none", "few")
TIER_MARK = {"good": "★", "ref": "●", "none": "○", "few": "—"}
TIER_NAMES = {"good": "好策略", "ref": "可參考", "none": "不推薦", "few": "次數不夠"}

# ── 7. 建議的條件（給使用者的建議照這一條，不在看過結果之後挑） ──────────────────
# 主要市場＝home。另外看的期間（OUT）：來源之後（買進日在 pub 年 1 月 1 日或之後）與 S&P 500 1950 年以前（EARLY），
# 那一段有 OUT_N 次以上才看。
# rec   建議試用：主要市場 ★，而且每一段「另外看的期間」的賺錢比例都不低於同一段的隨便挑一天。
# watch 可以觀察：主要市場 ●；或 ★ 但另外看的期間有一段沒過。
# no    不建議：主要市場 ○ 或 —。
OUT_N = 3
REC = ("rec", "watch", "no")
REC_NAMES = {"rec": "建議試用", "watch": "可以觀察", "no": "不建議"}

# ── 8. 只描述、不影響判定 ───────────────────────────────────────────────
# 打亂測試：把買進日整段循環挪動（次數、每一次抱的天數不變；挪動量在評估期間長度的 LUCK_SHIFT 之間）LUCK_DRAWS 次，
#   賺錢比例 ≥ 實際的次數 ＋ 1 再 ÷（LUCK_DRAWS ＋ 1）（同 xstrat.luck_trade；種子＝LUCK_SEED 與「規則:市場」）。
# 二項檢定（單尾）：如果每一次賺錢的機率＝隨便挑一天，至少出現這麼多次賺錢的機率。
# 前後兩半：依買進日先後分成前一半、後一半（奇數時中間那一次算前一半），各自的次數、賺錢比例、中位數。
# 抱的期間中途最多跌（買進價到持有期間最低收盤）：中位數、最差一次。
# 全部資金照做（其他時間空手、不算利息）：年化、最大回撤、在場時間；同一段一直抱著的年化、最大回撤。
# 每一次的清單；現在（資料最後一天：持有中到哪天賣、下一次排定的日子、事件型離觸發還差多少）。
LUCK_DRAWS = 400
LUCK_SEED = 20261027
LUCK_SHIFT = (0.15, 0.85)
