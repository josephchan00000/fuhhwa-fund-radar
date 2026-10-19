"""產業泡沫規格（docs/lab_risk_plan.md 第 12 節；VER 1，2026-10-19 寫定；VER 2、VER 3 同日，docs/lab_crash_plan.md 第 21.2、21.5 節）。

**事前寫定**：範圍、條件、門檻、分級、驗證方法都在算任何產業結果之前寫進這裡並 commit；tests/test_bubindspec.py 鎖住。
要改＝VER＋1，日期與原因寫進規劃文件，不在看過結果之後改舊版本（同 bubspec、heatspec 的紀律）。

使用者決定（規劃第 7 節第 4 點，2026-10-18）：產業泡沫做台股 34 產業＋美股產業（49 產業做歷史驗證、類股 ETF 每天更新）；細分族群之後再說。
2026-10-19 使用者：「把泡沫一路做到底」——這一版的細節（下面各節）都是照市場層級 VER 4 的同一套門檻延伸，沒有另外調。

和市場層級（bubspec VER 4）一樣的地方：PSY 臨界值表（依長期漲勢內插）、連續 3 個月、方向條件、偏離長期趨勢 2 個標準差、
分級（bubspec.level4）、大跌的定義（一年內跌 20%、兩年內跌 40%）、區塊重抽、段數與樣本不足的規則。
不一樣的地方：
  · 兩年翻倍另外要求比大盤多漲 50 個百分點（產業泡沫看的是「這個產業比整個市場熱」；整個市場熱由市場層級負責）；
  · 產業的估值沒有夠長的歷史 → V 不判定；
  · 基本面比值（E）只有台股產業有（產業市值 ÷ 近 12 個月營收）；美股產業沒有長歷史的產業獲利 → 不判定；
  · 未來獲利（G）：台股產業與美股類股現在用分析師預估；過去只有台股產業有替代資料（產業月營收）。
所以：台股產業 0～4 都可能；美股類股最高到 3（只有 G）；美股 49 細產業最高到 2（沒有 E、V、G）。
"""
from __future__ import annotations

from .bubspec import (BUB_BLOCK, BUB_BOOT, BUB_DD, BUB_EPI_GAP, BUB_EPI_MIN, BUB_MIN_HOT, BUB_SEED, DIR_MONTHS,  # noqa: F401
                      E_RUN, EST_COVER_MIN, EST_STALE_DAYS, FUEL_PCT, G_PRICE_DAYS, G_PRICE_MONTHS, LEVELS, PSY, PSY_RUN,
                      RUN2_ATH, RUN2_PCT, TREND, TREND_Z, level4)

VER = 3
SPEC_DATE = "2026-10-19"
GROUPS = ("tw", "us", "ff", "tg")
GROUP_NAMES = {"tw": "台股產業", "us": "美股類股", "ff": "美股 49 細產業", "tg": "台股細分族群"}

# ── 1. 範圍與指數 ───────────────────────────────────────────────────────────
# tw：證交所／櫃買中心產業別（stockmeta.industry_map()，現在的分類套用到過去；歷史上的分類變動不追）。
#     成分＝前一個月底市值 ≥ TW_CAP_MIN 的普通股（bt3d.Panel 的資料範圍：這個門檻以上的股票每個月底都有日線，
#     事前看得到的名單，不用「現在夠大」挑）。指數＝前一個月底市值加權、月內買進持有、每天收盤算一次，價格含息還原（Panel）。
#     某個月成分 < TW_MIN_N 檔＝那個月沒有值（PSY 從缺口之後重新起算）。大盤＝所有產業的成分合起來（同樣規則）。
#     TW_SKIP：不算的產業（「其他」是雜項，不是一個產業）。
# us：SPDR 類股 ETF（Yahoo 收盤：已還原分割、不含股利）；大盤＝SPY 收盤。半導體看泡沫頁的費半，不重複。
# ff：Ken French 49 Industry Portfolios（價值加權、月報酬）；價格指數用不含股利的報酬（Wout_Div 檔），
#     大盤＝49 個產業依前一個月市值（平均公司規模 × 家數）加權的報酬。報酬 ≤ −99.99（沒有資料）＝那個月沒有值。
TW_CAP_MIN = 40e8
TW_MIN_N = 3
TW_START = "2013-01-01"
TW_SKIP = ("其他",)
US_ETF = {"XLB": "原物料", "XLC": "通訊服務", "XLE": "能源", "XLF": "金融", "XLI": "工業", "XLK": "資訊科技",
          "XLP": "必需消費", "XLRE": "不動產", "XLU": "公用事業", "XLV": "醫療保健", "XLY": "非必需消費"}
US_MKT = "SPY"
US_START = "1998-12-01"
# GICS 類別（維基百科 S&P 500 表格的「GICS Sector」欄）→ ETF
GICS_ETF = {"Materials": "XLB", "Communication Services": "XLC", "Energy": "XLE", "Financials": "XLF",
            "Industrials": "XLI", "Information Technology": "XLK", "Consumer Staples": "XLP", "Real Estate": "XLRE",
            "Utilities": "XLU", "Health Care": "XLV", "Consumer Discretionary": "XLY"}
FF_FILES = ("49_Industry_Portfolios_CSV.zip", "49_Industry_Portfolios_Wout_Div_CSV.zip")
FF_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{f}"
FF49 = ("Agric", "Food", "Soda", "Beer", "Smoke", "Toys", "Fun", "Books", "Hshld", "Clths", "Hlth", "MedEq", "Drugs",
        "Chems", "Rubbr", "Txtls", "BldMt", "Cnstr", "Steel", "FabPr", "Mach", "ElcEq", "Autos", "Aero", "Ships", "Guns",
        "Gold", "Mines", "Coal", "Oil", "Util", "Telcm", "PerSv", "BusSv", "Hardw", "Softw", "Chips", "LabEq", "Paper",
        "Boxes", "Trans", "Whlsl", "Rtail", "Meals", "Banks", "Insur", "RlEst", "Fin", "Other")
FF_NAMES = {"Agric": "農業", "Food": "食品", "Soda": "飲料", "Beer": "酒類", "Smoke": "菸草", "Toys": "玩具休閒",
            "Fun": "娛樂", "Books": "出版印刷", "Hshld": "家用品", "Clths": "服飾", "Hlth": "醫療服務", "MedEq": "醫療器材",
            "Drugs": "製藥", "Chems": "化學", "Rubbr": "橡膠塑膠", "Txtls": "紡織", "BldMt": "建材", "Cnstr": "營建",
            "Steel": "鋼鐵", "FabPr": "金屬製品", "Mach": "機械", "ElcEq": "電機設備", "Autos": "汽車", "Aero": "航太",
            "Ships": "船舶鐵道設備", "Guns": "國防", "Gold": "貴金屬", "Mines": "礦業", "Coal": "煤", "Oil": "石油天然氣",
            "Util": "公用事業", "Telcm": "電信", "PerSv": "個人服務", "BusSv": "商業服務", "Hardw": "電腦硬體",
            "Softw": "軟體", "Chips": "半導體與電子零件", "LabEq": "量測設備", "Paper": "紙業", "Boxes": "包裝",
            "Trans": "運輸", "Whlsl": "批發", "Rtail": "零售", "Meals": "餐飲旅館", "Banks": "銀行", "Insur": "保險",
            "RlEst": "不動產", "Fin": "其他金融", "Other": "其他"}
FF_SKIP = ("Other",)
FF_MISSING = -99.99

# ── 1b. 已下市公司的產業別（VER 2；看任何 VER 2 結果之前寫定，docs/lab_crash_plan.md 第 21.2 節） ──────────
# VER 1：現在的產業表（stockmeta）沒有的代號（已下市或改代號）只算進大盤 → 台股產業指數只含現在還在的公司（存活者偏誤）。
# VER 2：這些代號改用「官方歷史分類行情」裡最後一次出現的產業別：
#   快照＝每年第一個交易日（IND_HIST_START 年起到今年；日曆＝data/lab/v3_tr.json 的交易日），
#   證交所 MI_INDEX（type＝產業代碼）＋櫃買中心 stk_wn1430（se＝產業代碼），產業代碼對照 stockmeta.IND_CODE。
#   年度快照裡都找不到的（兩次快照之間上市又下市）→ 補一次快照：它最後一個交易日之前那個月的最後一個交易日；還是找不到＝照舊只算進大盤。
#   分類＝最後一次出現的那一個，套用到它全部的歷史（和現在的公司一樣，歷史上的分類變動不追）。現在還在的公司照舊用現在的分類。
#   快照存 data/lab/indsnap.json（{"twse"|"tpex": {日期: {代號: 產業代碼}}}）；只要有快照，產業別就固定，不會因為重抓而改。
# E、G 的替代資料（月營收）：MOPS 月營收彙總表已重新產製、不含已下市公司（2026-10-19 探針）→「同一批公司」的規則自動排除，不另外處理。
# 台股產業只描述、不判定（JUDGE 不變）；主要假說（美股 49 細產業）不受影響。
IND_HIST_START = 2013
IND_HIST_FILE = "indsnap.json"
IND_HIST_TYPES = tuple(f"{i:02d}" for i in range(1, 40))
# 彙總類（看快照資料時發現、還沒算任何產業指數）：證交所的 07 化學生技醫療＝21＋22、13 電子工業＝24～31，
#   同一家公司會同時出現在彙總類與細分類 → 彙總類不當成產業別（2026-01-02 快照：13 有 452 檔、全部也在 24～31 裡）。
IND_HIST_AGG = ("07", "13")

# ── 1c. 台股細分族群（VER 3；看任何族群指數之前寫定，docs/lab_crash_plan.md 第 21.5 節） ──────────
# 使用者決定（2026-10-19）：精選約 15 個電子族群；用現在的成員往回算＋標明；CPO 沒有獨立節點，用光通訊代替。
# 名單來源：櫃買中心產業鏈平台（ic.tpex.org.tw；arm/lab/icchain.py → data/lab/icchain.json，TG_REFRESH_DAYS 天重抓一次）。
#   族群＝TG_GROUPS 裡列的（產業鏈代碼, 節點名稱, 分頁）：節點名稱 "*"＝那條產業鏈全部節點；同名節點全部算（半導體有兩個
#   「生產製程及檢測設備」）；分頁＝半導體 IC 設計節點的 IC 類別分頁（None＝整個節點）。節點裡全部市場別的代號都收，
#   之後只留現在上市櫃的普通股（stockmeta 產業表有、代號 4 碼不是 0 開頭）——興櫃、知名外國企業自然排除。
#   一家公司可以在好幾個族群（例如台光電在 PCB 材料，也在別的族群）。
# 成員現在上市櫃 < TG_MIN_MEMBERS 家＝這個族群不算（名單太細、指數不穩）。
# 指數、條件、分級：完全照第 1、2、3 節的台股產業（成分＝前一個月底市值 ≥ TW_CAP_MIN 的成員、前月底市值加權、含息；
#   成分 < TW_MIN_N 那個月沒有值；大盤＝台股產業的大盤；P1、P2、P3、E、G、F 同台股產業，E、G 的「同一批公司」＝族群成員）。
# 存活者偏誤（使用者同意、頁面標明）：平台只有現在的名單 → 過去用現在的成員算；已下市或從平台移出的公司不在裡面、
#   後來才成為成員的公司（例如轉型）提早算進來。所以族群過去的漲幅偏高、「兩年翻倍」之類的條件比較容易成立。
#   平台名單改了（重抓後成員不同）＝整段歷史用新名單重算。
# 驗證：只描述、不判定（TESTS["tg"] 同台股產業；JUDGE 不變）；不進訊號總覽的訊號清單（sigspec 不變）。
TG_FILE = "icchain.json"
TG_REFRESH_DAYS = 30
TG_MIN_MEMBERS = 5
TG_GROUPS = (
    ("pcb", "PCB（電路板製造）", (("L000", "硬板、軟板、IC載板製造", None),)),
    ("pcbm", "PCB 材料", tuple(("L000", t, None) for t in ("銅箔基板", "玻璃纖維/玻纖布", "銅箔", "環氧樹脂", "酚醛樹脂", "聚亞醯胺樹脂"))),
    ("passive", "被動元件", (("J000", "*", None),)),
    ("conn", "連接器", (("K000", "連接器設計、組裝及製造", None),)),
    ("thermal", "散熱", (("F000", "散熱片、風扇馬達、散熱模組", None), ("5400", "冷卻設備", None))),
    ("server", "伺服器", (("F000", "伺服器", None),)),
    ("power", "電源供應器", (("F000", "電源供應器", None),)),
    ("chassis", "機殼", (("F000", "機殼", None),)),
    ("ipc", "工業電腦", (("F000", "工業電腦", None),)),
    ("optical", "光通訊（含 CPO 相關）", (("I000", "光通訊設備(如光纖電纜、光傳輸設備)", None), ("D000", "IC設計", "光通訊IC"))),
    ("netcom", "網通設備", (("I000", "網路設備(如數據機、網路卡、閘道器、路由器、網路電話)", None),)),
    ("icd", "IC 設計（含 IP 與設計服務）", (("D000", "IC設計", None), ("D000", "IP設計/IC設計代工服務", None))),
    ("foundry", "晶圓製造", (("D000", "IC/晶圓製造", None),)),
    ("osat", "封測", (("D000", "IC封裝測試", None),)),
    ("semieq", "半導體設備", (("D000", "生產製程及檢測設備", None),)),
    ("memory", "記憶體（晶片、控制 IC、模組）", (("D000", "IC設計", "記憶體IC"), ("D000", "IC設計", "記憶體控制IC"), ("F000", "記憶體", None))),
    ("ai", "人工智慧（平台分類）", (("5300", "*", None),)),
)
TG_NAMES = {k: n for k, n, _ in TG_GROUPS}

# ── 2. 條件 ─────────────────────────────────────────────────────────────────
# P1 價格爆發：同市場層級（bubspec 第 1 節＋VER 3 方向條件）。實質價格＝月平均（tw、us；ff 沒有日資料用月底指數）÷ CPI
#   （前一個月，PSY["cpi_lag"]；台灣主計總處、美國勞工統計局／Shiller，缺月照 bubspec 補），取對數；
#   臨界值表同市場層級（data/lab/heat/psy_cv_drift），連續 PSY_RUN 個月，而且近 DIR_MONTHS 個月實質價格上漲。
#   台股產業的指數含息（市場層級的加權指數不含息），漲勢比較高，臨界值依漲勢內插會自動調高。
# P2 兩年翻倍、比大盤多漲、而且在高點：月底收盤 ÷ 24 個月前月底收盤 − 1 ≥ RUN2_PCT%，
#   而且減掉大盤同期漲幅 ≥ NET_PP 個百分點，而且月底收盤 ≥ 歷史最高月底收盤 ×（1 − RUN2_ATH）。
#   現在：最新收盤 ÷ 24 個月前同一天（那天或之前最後一個交易日）收盤；歷史最高＝之前的月底收盤與最新收盤取高。
#   （Greenwood、Shleifer、You 2019：產業兩年原始與扣大盤報酬都 > 100%；規劃第 4.3 節扣大盤用 50 個百分點。）
# P3 偏離長期趨勢：同市場層級（TREND["min"] 個月；台股產業 2013 起，2033 年以前算不出來＝不判定）。
NET_PP = 50.0
RUN2_MONTHS = 24

# E 價格漲得比基本面快（只有台股產業）：產業 P/S＝成員月底市值合計 ÷ 它們近 12 個月營收合計（同一批公司：
#   月底市值 ≥ TW_CAP_MIN、營收月 m−12～m−1 都有；第 m−1 個月營收第 m 個月 10 日公布，所以月底 m 拿得到）。
#   log P/S 做和 P1 同一套 PSY，連續 E_RUN 個月，而且近 DIR_MONTHS 個月產業指數上漲、P/S 上升。
#   E_SKIP：營收不能代表本業的產業（金融保險的營收含投資損益）。比值和其他月資料一樣下個月 1 日起才用。
E_SKIP = ("金融保險",)
E_SUM = 12

# V 估值：產業沒有夠長（≥ 240 個月）的估值歷史，三組都不判定。

# G 未來獲利跟不上（同市場層級：G1 明年預估成長 < 今年；G2 明年預估比 90 天前低、而且價格比 91 天前高）：
#   tw 現在：Yahoo 預估依產業加總（fwd.est_rows_tw → fwd.aggregate；涵蓋＝用到的公司市值 ÷ 產業全部普通股市值 ≥ EST_COVER_MIN）；
#      價格＝產業指數。
#   tw 過去（替代資料）：產業月營收（同一批公司）。G1＝近 12 個月合計的年增率（24 個月都有營收的公司）比 G1_BACK 個月前低；
#      R＝近 12 個月合計比 R_BACK 個月前的近 12 個月合計低（15 個月都有營收的公司）；G2＝R 而且產業指數比 3 個月前高。
#      第 m 個月營收第 m＋1 個月 10 日起才用（REV_REL）。E_SKIP 的產業不判定。
#   us 現在：S&P 500 成分股依 GICS 類別（GICS_ETF）加總 Yahoo 預估（fwd/us；每家公司資料在 EST_STALE_DAYS 天內）；價格＝ETF 收盤。
#      過去沒有預估資料 → 不判定。
#   ff：沒有產業獲利資料 → 不判定。
G1_BACK = 6
R_BACK = 3
REV_REL = (1, 10)

# F 燃料：
#   tw：成交值 ÷ 市值（成員 20 日平均成交值合計 ÷ 月底市值合計）在自己過去（不含當月）的百分位 ≥ FUEL_PCT，
#       至少 F_MIN_MONTHS["tw"] 個月歷史（2023 年起才判定）。
#   ff：家數（Ken French「Number of Firms in Portfolios」）12 個月增加率在自己過去的百分位 ≥ FUEL_PCT，
#       至少 F_MIN_MONTHS["ff"] 個月歷史（新公司大量進來；Greenwood 等發現新公司比例高的產業比較容易崩）。
#   us：不判定。
F_MIN_MONTHS = {"tw": 120, "ff": 240}

# ── 3. 分級：bubspec.level4（price＝P1、P2、P3 任一；e＝E；v＝False；g＝G；f＝F） ──────────────

# ── 4. 驗證（看結果之前寫定） ─────────────────────────────────────────────────
# 樣本：每個產業每個月的月底（P1、P2 都算得出來的月份起）。
# 結果：從當月月底起，之後 12 個月（月底收盤）內最大回落 ≥ 20%、24 個月內 ≥ 40%（bubspec.BUB_DD 的門檻）；
#   回落＝期間內月底收盤高點到之後低點。tw 用含息指數、us／ff 用不含股利的價格。
# 檢定（panel_crash_test）：成立的樣本大跌比例 − 全部樣本大跌比例；95% 區間用移動區塊重抽：以月份為單位，
#   每塊 BUB_BLOCK 個月（那幾個月所有產業的樣本一起抽），BUB_BOOT 次、種子 BUB_SEED；前後兩半（依月份切）各算一次。
#   段數＝所有產業合起來「有任何產業成立」的月份，中間隔 ≥ BUB_EPI_GAP 個月才算新的一段（同一時間好幾個產業一起熱只算一段）；
#   成立樣本 < BUB_MIN_HOT 或段數 < BUB_EPI_MIN＝樣本不足；判定規則同市場層級。另列產業段數（每個產業各自算段，加總）。
# 比較：P1、P2、P3、F、價格過熱（任一）、P2 而且 F（ff）；E、G、等級 ≥ 3（tw）。另列（描述）成立樣本之後 12、24 個月平均報酬。
# 只有 ff（1926 起）做判定；tw（2013 起）、us（1999 起）樣本太短，只描述；tg（VER 3）有存活者偏誤，只描述。
# 主要假說（只有一個）：H1 美股 49 細產業「兩年翻倍、比大盤多漲而且在高點」（P2）成立的月份，之後 24 個月內跌 40% 的比例高於全部樣本。
DD_MONTHS = ((12, 0.20), (24, 0.40))
TESTS = {"ff": ("P1", "P2", "P3", "F", "PX", "P2F"), "tw": ("P1", "P2", "E", "G", "F", "PX", "L3"),
         "us": ("P1", "P2", "P3", "PX"), "tg": ("P1", "P2", "E", "G", "F", "PX", "L3")}
JUDGE = ("ff",)
PRIMARY = ("ff", "P2", 24)
COND_NAMES = {"P1": "價格爆發（PSY）", "P2": "兩年翻倍、比大盤多漲而且在高點", "P3": "偏離長期趨勢 2 個標準差",
              "E": "價格漲得比營收快", "G": "未來獲利跟不上", "F": "燃料（換手率／新公司）", "PX": "價格過熱（任一價格條件）",
              "P2F": "兩年翻倍而且燃料", "L3": "等級 ≥ 3"}
