"""美股財報季的規格（docs/lab_earnings_plan.md 第 11.2 節；使用者 2026-11-20「好 繼續」＝做第 4 段美股）。

VER 1（2026-11-20，第一次正式算之前寫定）
事前看過的東西，照實寫：資料探針（scripts/probe_earnus.py）印了 NVDA、MSFT、CROX、MANH 的 Yahoo 資料與那斯達克 11/18、11/19、10/28
三天裡 WMT、PANW、TJX、LOW、TGT、MSFT 的列（實際 EPS 都比預估高或差不多，PANW 低 11.5%），用來確認欄位；第 3 節的試算
（美股 186 家：那斯達克高於 93、差不多 14、低於 19）也是更早看過的。下面的門檻不是照這些數字調的。

1. 清單＝三個來源的美股聯集，每家記「誰持有」：
   (a) 復華基金月報前十大（data/funds/*.json 的 top_holdings），名稱經 config/holding_profiles.json 對到國別「美國」且有代號的；
   (b) 復華自家 ETF（arm/etfwatch.WATCHLIST 名稱有「復華」的）持股代號以「 US」結尾的（data/etf_holdings.json）；
   (c) 美股強勢品質股（arm/fund_intro.qm_codes：手上的、要買的、名單前 5 名裡手上沒有的）。
   排除 ETF（holding_profiles 的名稱或簡介有「ETF」）；同一家公司兩種股別只留一個（ALIAS，例 GOOG → GOOGL）。
2. 資料（CI 每個美股收盤抓一次，arm/lab/earnusdata.py → data/lab/earn_us_raw.json；本容器擋 Yahoo、那斯達克）：
   Yahoo quoteSummary：近 4 季的期末日、公布時間（美東）、實際 EPS、當時的預估 EPS、營收、淨利；目前這一季的 EPS 與營收預估、家數；下次財報日。
   Yahoo 季資料（fundamentals-timeseries）：更早幾季的營收、淨利（算比去年同季）。Yahoo 日線。
   那斯達克財報行事曆：公布那一天的實際 EPS、預估、預估家數、會計季。
3. 季的歸屬：期末日往前 QMAP_DAYS 天落在哪一個日曆季，就算那一季（10/31 結帳＝第三季、1/31＝前一年第四季）。
   這一季＝今天往前 SEASON_LAG 天之前，最近一個日曆季底所屬的季（11/20＝第三季；1/10 還是第三季、1/15 起第四季）。
   每家「這一季」＝歸屬這一季、已公布的那一季；還沒公布的照列「還沒公布」＋下次財報日（Yahoo；日期是估的照寫）。
4. EPS 對預估（兩個來源）：Yahoo（實際 vs 當時的預估）、那斯達克（公布那天的實際 vs 預估；同代號、公布日相差 1 天以內、會計季的月份對得上）。
   各自：|實際 − 預估| ≤ max(FLAT_PCT × |預估|, FLAT_ABS) 美元＝「差不多」；其他照正負「高於」「低於」。
   兩家都有、結論一樣＝標那個結論；結論不一樣＝「兩家不一致」，寫出兩邊的數字；只有一家＝標那個結論、註明只有哪一家。
5. 營收對預估（只有 Yahoo 一個來源，照寫）：實際營收 vs「公布前最後一版」的 Yahoo 單季營收預估。
   公布前最後一版＝CI 每天記目前這一季的預估，公布時間過了那一季就不再改。開始記之前就公布的季寫「沒有公布前的營收預估紀錄」。
   |實際 ÷ 預估 − 1| ≤ REV_FLAT%＝差不多。
6. 比去年同季：營收、淨利（同台股 VER 2，用淨利不用每股盈餘）。去年同季的淨利 ≤ 0 或今年 ≤ 0 時不算百分比，寫「轉盈」「轉虧」「虧損」。
   成長／差不多／衰退＝淨利年增 > +FLAT%／之間／< −FLAT%。
7. 財報後股價：看公布時間（美東）：OPEN 以前＝前一個交易日收盤 → 當天收盤；CLOSE 以後＝當天收盤 → 下一個交易日收盤；
   盤中或沒有時間＝前一個交易日收盤 → 下一個交易日收盤。要用的那一天還沒收盤＝先不寫。
   近 1 個月股價＝最近收盤比 PX1M 個交易日前。
8. 待查：營收比去年同季多 SUSPECT_REV% 以上、淨利卻由正轉負 → 標「待查」，不進彙總的成長／衰退（同台股第 7 點）。
9. 彙總：清單幾家；這一季已公布幾家、還沒公布幾家（接下來 UPCOMING_DAYS 天要公布的列出來）；
   EPS 對預估 高於／差不多／低於／兩家不一致／沒有預估；營收對預估（有紀錄的）高於／差不多／低於；
   獲利比去年同季 成長／差不多／衰退；財報後股價 上漲／下跌家數與中位數。
10. 基金持股成績：每檔復華基金（與自家 ETF、美股強勢品質股）的持股一列一家：比重、EPS 對預估、營收年增、獲利年增、財報後股價、近 1 個月股價。
11. 只寫已經發生的；不寫「之後會怎樣」。
"""
from __future__ import annotations

import hashlib
import json

VER = 1
SPEC_DATE = "2026-11-20"

QMAP_DAYS = 45        # 期末日往前幾天決定歸哪一個日曆季
SEASON_LAG = 15       # 季底過了幾天才換到下一季
FLAT_PCT = 0.02       # EPS 差不多：預估的 2%
FLAT_ABS = 0.01       # 或 1 美分（取大的）
REV_FLAT = 1.0        # 營收差不多：±1%
FLAT = 5.0            # 獲利年增差不多：±5%
SUSPECT_REV = 20.0
UPCOMING_DAYS = 14
PX1M = 21
OPEN, CLOSE = "09:30", "16:00"
NQ_DAYS = 1           # 那斯達克的公布日和 Yahoo 相差幾天以內算同一次
ALIAS = {"GOOG": "GOOGL", "BRK.A": "BRK.B", "BRK-A": "BRK.B"}


def fingerprint() -> str:
    keys = ("VER", "QMAP_DAYS", "SEASON_LAG", "FLAT_PCT", "FLAT_ABS", "REV_FLAT", "FLAT", "SUSPECT_REV", "UPCOMING_DAYS",
            "PX1M", "OPEN", "CLOSE", "NQ_DAYS", "ALIAS")
    g = globals()
    return hashlib.sha256(json.dumps({k: g[k] for k in keys}, sort_keys=True).encode()).hexdigest()[:12]
