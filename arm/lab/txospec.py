"""台指選擇權（只做買方）候選策略的規格。VER 1：2026-11-05，算任何成績之前寫定（docs/lab_txo_plan.md 第 6、7、16 節）。
VER 2：2026-11-11，O1 加兩個對照、新增 O4 結算均價（第 19 節）；O1～O3 的常數一個都沒改（fingerprint_v1 鎖住），O2、O3 的 VER 1 結果照用。

使用者 2026-11-04 的決定（規劃第 13 節）：三條都做；資金保守——選擇權帳戶＝總資產 3～5%（回測用 ACCOUNT 元），
每筆付出的權利金上限 O1 2%／O2 3%／O3 5%，一天最多賠 4%、一個月最多賠 12%；手續費每口每邊 25 元（另試 50 元）；不做夜盤、只做買方。
寫規格之前只看了資料長相（第 15 節：逐筆 30 天、日行情 2002 起、5 秒指數 2016 起）、事件日期與訊號清單在不在，沒算任何報酬。

共同
  契約乘數 MULT（每點 50 元）；權利金跳動 tick()；成本（每口每邊）＝手續費 FEE（25；COMPARE 另試 FEE_ALT＝50）
  ＋ 期交稅 TAX × 權利金 × MULT ＋ 滑價 SLIP_TICKS 檔（買進加、賣出減）。判定用兩倍成本（手續費、稅、滑價都乘 2）。
  口數＝floor(帳戶 × 該條上限 ÷ (進場價 × MULT ＋ 一邊成本))，算不到 1 口就不做；帳戶＝ACCOUNT 加減已實現損益（不加碼複利以外的錢）。
  一天已實現虧損達 DAY_STOP（4%，用當天開盤前的帳戶算）→ 當天不再進場；一個月達 MONTH_STOP（12%，用月初帳戶算）→ 當月不再進場（三條合計）。
  模型價（只在沒有真實成交時用）：Black-Scholes（r＝0、不配息），時間＝離結算還剩的日盤分鐘 ÷ (SESSION_MIN × 252)；
  隱含波動率＝前一個交易日「同一個契約」的結算價反推（用前一天收盤指數）；反推不出來（價格低於內含價值、或結算價 0）那筆不做。

O1 結算日順勢（5 秒指數 2016 起；選擇權用模型價，2026-09-17 起另用真實分 K 核對）
  哪幾天：週選或月選的到期日（週三；2025-06-27 起也有週五），只買當天到期的那一批。
  高波動過濾：前 VOL_DAYS（10）個交易日（只到昨天）平均日振幅 (高－低)÷前一天收盤 ≥ vol_min（參數）。
  噪音區間（Zarattini、Aziz、Barbon 2024 的做法）：σ(t)＝過去 NOISE_DAYS（14）個交易日在同一時刻 |指數÷當天開盤 − 1| 的平均；
    上緣＝max(今天開盤, 昨天收盤) × (1 ＋ k·σ(t))，下緣＝min(今天開盤, 昨天收盤) × (1 − k·σ(t))；k 是參數。
    今天平均價＝09:00 起 5 秒指數的累計平均（指數沒有成交量）。
  進場：ENTRY_FROM（09:30）～ENTRY_TO（12:30）每 CHECK_MIN（5）分鐘檢查一次：指數 > 上緣且 > 今天平均價 → 買買權；
    < 下緣且 < 今天平均價 → 買賣權。履約價＝價平（離指數最近的 STRIKE_STEP 點整數）往價外 otm 檔（參數）；
    進場價 < MIN_PREM（1.0 點）不做。一天最多 MAX_TRADES（2）筆、輸 MAX_LOSSES（2）筆收工；持有中不再進場、不攤平、不加碼。
  出場（每一個 5 秒點都檢查，誰先到用誰；價格＝該時點的選擇權價減滑價）：
    ① 停損：指數回到噪音區間裡面，或回到今天平均價的另一邊；② 選擇權價 ≤ 進場價 × STOP_PREM（0.5）；③ EXIT_BY（13:00）全部出。
    停利：選擇權價 ≥ 進場價 × TP_MULT（2）先賣一半（奇數口少賣）；剩下的在 ① ② ③，或指數從進場後最遠點回吐超過
    （最遠點 − 進場時指數）× TRAIL_IDX（1/3），或選擇權價從最高點跌 TRAIL_PREM（40%）時出。
  參數表 GRID_O1（vol_min × k × otm，12 組）；每年 1 月 1 日只用以前的年份挑「平均每筆淨損益最高、筆數 ≥ WF_MIN_TRADES」的一組往後走
    （樣本外）。第一年 WF_FIRST_YEAR（2018）之前不算樣本外。
  真實價格核對（MODEL_CHECK）：2026-09-17 起有分 K 的日子，同一筆交易用真實價（進場＝訊號那一分鐘之後第一根 1 分 K 收盤 ＋ 滑價、
    出場同理；前後 2 分鐘沒有成交就記「沒成交」）重算，模型與真實的每邊差距中位數加進成本；差距中位數 > 權利金平均的 MODEL_ERR_MAX（25%）
    → O1 的歷史回測判「不可信」，只看紙上紀錄。

O2 大事件前買跨式（日行情 2002 起，週選 2012 起）
  事件：美國 CPI 公布日（data/lab/heat/reldates 的 cpi，官方日期 2002 起）＋ FOMC 聲明日（第 3 段從聯準會網站抓歷史行程；
    抓不到就只用 CPI，研究紀錄寫明）。兩者都在台灣晚上公布 → 進場＝公布當天台股日盤收盤，出場＝下一個台股交易日日盤收盤。
  買什麼：到期日在出場日之後最近的一批，價平買權＋賣權各一口一組（口數照 3% 上限算組數）；價平＝離當天收盤指數最近的履約價。
  價格：日行情的收盤價（當天沒成交用結算價）；買進加滑價、賣出減滑價。
  不貴過濾：用進場日價平跨式結算價反推的隱含波動率，排在過去 IV_LOOKBACK（250）個交易日的 IV_PCT（50%）以下才做；
    COMPARE 另列「不過濾」。
  （日行情沒有盤中路徑，所以「賺錢那邊漲到倍數先賣」在 VER 1 不做；第 4 段起的紙上紀錄才用分 K。）

O3 已驗證訊號改用選擇權（日行情）
  訊號：少見但勝率高的策略（rarespec VER 1、data/lab/rare_research.json）台股判定為 good、而且持有期 ≤ O3_MAX_HOLD（60）個交易日的：
    lnypre（農曆年前）、santa（聖誕老人行情）。bull（持有 250 天）要買到一年後到期的契約、台指選擇權沒有，VER 1 不收。
  進出場日照原規則（tr 紀錄的進場日、出場日，收盤）。買價平買權，到期日在出場日之後至少 O3_BUFFER（10）個交易日的最近月選；
    價格＝日行情收盤價（沒成交用結算價）。COMPARE 另列：原規則直接買指數、買權價差（買價平、賣價外 SPREAD_OTM 5%）。

判定（JUDGE；看過成績不改）
  ① 平均每筆淨損益（兩倍成本）> 0；O1 用樣本外。
  ② 打亂測試：同樣的進出場規則，O1 方向亂選（同一批日子）、O2 換成同月份隨機的非事件日、O3 換成同一年隨機的進場日（持有天數相同），
     PLACEBO_N 次（種子 SEED），隨機版本的平均 ≥ 實際的比例 ≤ PLACEBO_P。
  ③ 有交易的年份裡至少 YEARS_OK（2/3）不虧（兩倍成本）。
  ④ 帳戶最大回落 ≤ MAX_DD（30%；選擇權帳戶是總資產 3～5%，等於總資產 1～1.5%）。
  ⑤ 筆數 ≥ MIN_N（O1 60、O2 40、O3 10）；不到就只列、不判定。
  ⑥ O1 另外：MODEL_CHECK 可信，而且把模型誤差加進成本後 ① 仍然過。
  全過＝過關；過關的再記 PAPER_DAYS（63）個交易日的紙上紀錄，成績在回測範圍內才放上「今天要做的事」。
只列、不判定（COMPARE）：手續費 50 元、O2 不過濾、O3 買指數與價差、賣方對照（O1 同契約 09:30 賣出到 13:00、O2 賣同一組跨式），
  參數往左右挪一格的成績、扣掉最賺 3 筆後的平均。
不做：賣方策略、夜盤、自動下單、O1 以外的盤中加碼。要改就 VER＋1、寫進規劃，不在舊版本上改。

── VER 2（2026-11-11；使用者上傳「台指週選結算日交易逆向拆解」，決定 E1 兩條都做、E2 加兩個對照；寫的時候 O1 還沒跑過、O4 沒算過任何成績）──

結算價（O1 對照「抱到結算」與 O4 共用）
  期交所的算法（臺指選擇權最後結算價：13:00〔不含〕到 13:25〔含〕每 5 秒的加權指數，加上最後一筆收盤指數，簡單平均）：
  5 秒指數陣列（09:00:00 起，第 0 個是前一天收盤）的第 SETTLE_K[0]～SETTLE_K[1] 個（13:00:05～13:25:00，300 個）＋第 CLOSE_K 個（13:30:00 收盤），
  共 SETTLE_N（301）個的平均，四捨五入到 0.01 點（settle_price）。只看過 2026-11-04 一天的資料長相（42,978.23），沒有用它算任何報酬。

O1 對照（O1_ALT；只列、不判定；參數用主規則每年挑出的那一組，不另外挑）
  two：同一個訊號、同一個方向，同時買兩個履約價——價平（離指數最近的 STRIKE_STEP 整數）與價平往價外 TWO_GAP（2）檔，
       兩檔各用一半的錢（合計仍是 CAP O1）；每一檔各自照 O1 的出場規則，指數停損兩檔一起出。
  hold：進場、出場規則照 O1，但 ③「EXIT_BY 全部出」改成：13:00 還沒出的不賣、13:00 以後不再檢查任何出場條件，抱到結算；
       結算值＝max(結算價 − 履約價, 0)（買權）或 max(履約價 − 結算價, 0)（賣權）；結算那一邊的成本＝手續費＋期交稅×結算值（沒有滑價）。

O4 結算均價（只用真實成交，2026-09-17 起的每分鐘成交；沒有歷史回測可做）
  哪幾天：有分 K 的結算日，只買當天到期那一批，只做買方。
  O4_CHECKS（13:05、13:10、13:15、13:20、13:25）各檢查一次。檢查時刻 t：
    已知：13:00:05 到 t 的 5 秒指數（n 個）合計 Σ、現在的指數 S；還沒過去的＝t 之後到 13:25:00 的 m 個＋收盤 1 個。
    波動範圍 B(t)：過去 O4_BAND_DAYS（60）個交易日（只到昨天，所有交易日、不只結算日），每天算「t 之後到 13:25:00 的每一個 5 秒指數與收盤」
      離那天 t 的指數最遠多少點，取 60 天裡最大的一個。
    結算價最低 L＝(Σ ＋ (m＋1)×(S − B)) ÷ 301，最高 U＝(Σ ＋ (m＋1)×(S ＋ B)) ÷ 301。
    最少值：買權 max(L − 履約價, 0)，賣權 max(履約價 − U, 0)。
  買進價＝t 開始那一根 1 分 K 的收盤（沒有成交就看下一根，兩根都沒有就不買）；
  最少值 − 買進價 − 買進一邊成本（點）− 結算一邊成本（點）≥ O4_EDGE（2 點）才買，抱到結算（成本用一倍；判定用兩倍）。
  同一個契約一天只買一次；一天最多 O4_MAX_DAY（3）筆，同一時刻多筆符合就挑「最少值 − 買進價」最大的；
  每筆付出的權利金 ≤ 帳戶 × O4_CAP_EACH（1%），算不到 1 口不做；帳戶、單日、單月停損照共同規則（O4 自己的帳戶）。
  判定（O4_JUDGE；看過成績不改）：① 平均每筆淨損益（兩倍成本）> 0；② 筆數 ≥ O4_MIN_N（40）而且來自至少 O4_MIN_DAYS（15）個結算日；
    ③ 最賺的一天占總淨損益 ≤ O4_TOP_DAY（50%）；④ 打亂測試：同一天、同一時刻，從當天到期、最少值 > 0、有成交的契約隨機挑同樣筆數
       （不看價格），PLACEBO_N 次，隨機版平均 ≥ 實際的比例 ≤ PLACEBO_P。
    ② 不到之前只列、記紙上紀錄（每週更新）；全過再記 PAPER_DAYS 個交易日，成績在範圍內才放上「今天要做的事」。
  只列：一倍成本、手續費 50 元、O4_EDGE 1 點與 4 點、只看 13:15 以後的檢查、資料核對（深度價內、當天到期的買權在 13:25 以後最後成交價
    與「結算價 − 履約價」差多少）。
"""
from __future__ import annotations

import hashlib
import json

VER = 2
SPEC_DATE = "2026-11-11"

MULT = 50
ACCOUNT = 1_000_000
FEE = 25
FEE_ALT = 50
TAX = 0.001
SLIP_TICKS = 1
CAP = {"O1": 0.02, "O2": 0.03, "O3": 0.05}
DAY_STOP = 0.04
MONTH_STOP = 0.12
SESSION_MIN = 300

VOL_DAYS = 10
NOISE_DAYS = 14
ENTRY_FROM = "09:30"
ENTRY_TO = "12:30"
CHECK_MIN = 5
STRIKE_STEP = 50
MIN_PREM = 1.0
MAX_TRADES = 2
MAX_LOSSES = 2
STOP_PREM = 0.5
EXIT_BY = "13:00"
TP_MULT = 2.0
TRAIL_IDX = 1 / 3
TRAIL_PREM = 0.40
GRID_O1 = {"vol_min": (0.0, 0.008, 0.012), "k": (1.0, 1.5), "otm": (1, 2)}
WF_MIN_TRADES = 20
WF_FIRST_YEAR = 2018
MODEL_ERR_MAX = 0.25

O2_EVENTS = ("cpi", "fomc")
IV_LOOKBACK = 250
IV_PCT = 0.50

O3_RULES = ("lnypre", "santa")
O3_MAX_HOLD = 60
O3_BUFFER = 10
SPREAD_OTM = 0.05

PLACEBO_N = 1000
SEED = 20261105
PLACEBO_P = 0.05
YEARS_OK = 2 / 3
MAX_DD = 0.30
MIN_N = {"O1": 60, "O2": 40, "O3": 10}
PAPER_DAYS = 63

# ── VER 2（2026-11-11）：結算價、O1 對照、O4 ─────────────────────────────────
SETTLE_K = (2881, 3180)          # 5 秒指數陣列的位置：13:00:05～13:25:00
CLOSE_K = 3240                   # 13:30:00 收盤
SETTLE_N = 301
O1_ALT = ("two", "hold")
TWO_GAP = 2
O4_CHECKS = ("13:05", "13:10", "13:15", "13:20", "13:25")
O4_BAND_DAYS = 60
O4_EDGE = 2.0
O4_EDGE_ALT = (1.0, 4.0)
O4_MAX_DAY = 3
O4_CAP_EACH = 0.01
O4_MIN_N = 40
O4_MIN_DAYS = 15
O4_TOP_DAY = 0.50
O4_FROM = "2026-09-17"
V1_DATE = "2026-11-05"
V1_FP = "95b3382fa1b170ae"


def tick(price: float) -> float:
    """台指選擇權權利金跳動：< 10 點 0.1；10～50 0.5；50～500 1；500～1000 5；≥ 1000 10。"""
    if price < 10:
        return 0.1
    if price < 50:
        return 0.5
    if price < 500:
        return 1.0
    if price < 1000:
        return 5.0
    return 10.0


def side_cost(price: float, fee: float = FEE, mult: float = 1.0) -> float:
    """一口一邊的成本（元）：手續費＋期交稅＋滑價；mult＝2 是判定用的兩倍成本。"""
    return mult * (fee + TAX * price * MULT + SLIP_TICKS * tick(price) * MULT)


def lots(account: float, cap: float, price: float, fee: float = FEE) -> int:
    per = price * MULT + side_cost(price, fee)
    return int(account * cap // per) if per > 0 else 0


def grid_o1() -> list[dict]:
    return [{"vol_min": v, "k": k, "otm": o} for v in GRID_O1["vol_min"] for k in GRID_O1["k"] for o in GRID_O1["otm"]]


def settle_price(idx: list[float]) -> float:
    """結算價：13:00:05～13:25:00 的 5 秒指數（300 個）＋13:30:00 收盤，共 301 個的平均，到 0.01 點。"""
    pts = list(idx[SETTLE_K[0]:SETTLE_K[1] + 1]) + [idx[CLOSE_K]]
    assert len(pts) == SETTLE_N
    return round(sum(pts) / SETTLE_N, 2)


_V2_KEYS = ("SETTLE_K", "CLOSE_K", "SETTLE_N", "O1_ALT", "TWO_GAP", "O4_CHECKS", "O4_BAND_DAYS", "O4_EDGE", "O4_EDGE_ALT",
            "O4_MAX_DAY", "O4_CAP_EACH", "O4_MIN_N", "O4_MIN_DAYS", "O4_TOP_DAY", "O4_FROM", "V1_DATE", "V1_FP", "_V2_KEYS")


def fingerprint_v1() -> str:
    """VER 1 那一組常數的指紋：VER 2 只新增、沒改 O1～O3 的任何常數（tests 鎖成 V1_FP）。"""
    keys = sorted(k for k, v in globals().items() if k.isupper() and not callable(v) and k not in _V2_KEYS)
    d = {k: globals()[k] for k in keys}
    d.update(VER=1, SPEC_DATE=V1_DATE)
    blob = json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def fingerprint() -> str:
    """規格常數的指紋（tests 鎖住；改任何一個都要 VER＋1）。"""
    keys = sorted(k for k, v in globals().items() if k.isupper() and not callable(v))
    blob = json.dumps({k: globals()[k] for k in keys}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
