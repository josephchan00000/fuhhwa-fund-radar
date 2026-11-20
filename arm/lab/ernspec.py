"""台股財報季的規格（docs/lab_earnings_plan.md 第 10 節；使用者 2026-11-20 回「A」＝做第 3 段台股財報季）。

VER 1（2026-11-20，第一次正式算之前寫定；第 3 節的試算是看過之後才寫這份，照實寫在這裡）
1. 清單＝三個來源的台股（4 碼代號）聯集，每家記「誰持有」：
   (a) 復華基金月報前十大（data/funds/*.json 的 top_holdings，名稱經 config/holding_profiles.json 對到代號）；
   (b) 復華自家 ETF（arm/etfwatch.WATCHLIST 名稱有「復華」的）的台股持股（data/etf_holdings.json）；
   (c) 選股頁各策略現在拿著的股票（dashboard/x9.html 內嵌的 pick.tw.pos）。
2. 這一季＝法定期限已過的最新一季（arm/lab/packtest.deadline）。資料：dashboard/co/{代號}.json（公開資訊觀測站彙總表，累計相減成單季；arm/lab/eqfacts.quarters）。
   這一季還沒進資料的照列「資料還沒進來」（期限後第 2～7 天、14～45 天各補抓一次，arm/lab/v3data.FS_RE）。
3. 單季每股盈餘：累計相減；單季每股盈餘和單季淨利（母公司）一正一負時（年中股數變了，相減失真），
   改用「今年累計每股盈餘 × 單季淨利 ÷ 今年累計淨利」，標「股數有變，用淨利比例換算」。
4. 每家：營收、每股盈餘比去年同季；毛利率、營益率和上一季、去年同季比；近 8 季營收年增；最近 3 個月月營收年增；近 1 個月股價。
5. 營收降速＝這一季營收年增比上一季少 DECEL 個百分點以上。
6. 全年預估（FactSet／Yahoo，同個股卡 arm/lab/eqfacts.consensus）；這一季是第 1～3 季才算（第 4 季全年已知，不算）：
   剩下要賺＝全年預估 − 今年累計；照去年季節＝這一季 × 去年剩下幾季合計 ÷ 去年同一季
   （這一季、去年同一季、去年剩下幾季合計都 > 0，且 去年剩下幾季合計 ÷ 去年同一季 在 去年剩下季數 ÷ SEAS_MAX ～ 去年剩下季數 × SEAS_MAX 之內才算）。
   比值＝剩下要賺 ÷ 照去年季節；< LOW「全年預估看起來偏低」、> HIGH「偏高」、其他「合理」；算不了照寫原因。
   預估日期早於這一季季底後 STALE_DAYS 天＝「預估可能還沒反映這一季」。
7. 待查：營收比去年同季多 SUSPECT_REV% 以上、每股盈餘卻由正轉負（第 3 點換算之後）→ 標「待查」，不進彙總的成長／衰退。
8. 彙總：清單幾家、這一季已進資料幾家；每股盈餘比去年同季 成長（> +FLAT%）／差不多／衰退（< −FLAT%）；全年預估 偏低／合理／偏高／算不了；營收降速幾家；待查幾家。
9. 基金持股成績：每檔復華基金（與自家 ETF）的持股一列一家：比重、每股盈餘年增、營收年增、全年預估、近 1 個月股價。
10. 只寫已經發生的；不寫「之後會怎樣」。財報後股價要等台股每家公布日有資料再加（另一版規格）。
"""
from __future__ import annotations

import hashlib
import json

VER = 1
SPEC_DATE = "2026-11-20"

DECEL = 10.0          # 營收年增比上一季少幾個百分點算降速
SEAS_MAX = 3.0        # 去年季節倍數的合理範圍（相對於剩下季數）
LOW, HIGH = 0.85, 1.15
STALE_DAYS = 30
SUSPECT_REV = 20.0
FLAT = 5.0


def fingerprint() -> str:
    keys = ("VER", "DECEL", "SEAS_MAX", "LOW", "HIGH", "STALE_DAYS", "SUSPECT_REV", "FLAT")
    g = globals()
    return hashlib.sha256(json.dumps({k: g[k] for k in keys}, sort_keys=True).encode()).hexdigest()[:12]
