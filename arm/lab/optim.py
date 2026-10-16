"""籌碼雷達：推薦策略的改良候選與判定（docs/lab_selfopt_plan.md；2026-10-16 使用者確認）。

optim v1 在看任何結果之前寫定並 commit（文件第 3～6 節）：候選清單、比較方法、門檻、影子版本的進出條件。
要加候選或改門檻＝新版本（OPT_VER＋1，日期與原因寫進文件），不在舊版上改；tests/test_selfopt.py 鎖住內容。
使用者的決定（第 9 節）：達標後通知、回「好」才換；只改執行細節（選股分數與門檻不動）；每週一重跑；
目標＝扣成本後報酬變高、最大回落不比現行差超過 3 個百分點。
"""
from __future__ import annotations

import math

OPT_VER = 1
OPT_SINCE = "2026-10-16"
MAIN_FROM = "2021-10-01"            # 主要期間起點（＝bt3l.OOS_END）；之前＝複驗期間

# ── 現行規則（測試核對與各策略程式的常數一致；現行規則改版時這裡跟著改＝新版本） ──────────────
CURRENT = {
    "v3l": {"delay": 0, "gap": None, "hold": 60, "stop": None, "n": 5, "reg": None},
    "v7m": {"delay": 0, "gap": None, "hold": None, "sleeves": 1, "stop": None, "n": 5, "reg": None},
    "v7l": {"delay": 0, "gap": None, "hold": None, "sleeves": 1, "stop": None, "n": 5, "reg": None},
    "s3": {"k": 25, "n": 4, "out": -1, "stop": None},
    "s5": {"init": 0.20, "trail": 0.30, "maxd": 250, "gap": 0.03, "wait": 5, "reg": None},
    "s1": {"gap_max": 0.0, "hold": 3, "stop_atr": 2.0, "reg": None},
}

# ── 候選清單：(代號, 改什麼, 候選參數, [相鄰檢查參數…]) ──────────────────────────────────
# 每個候選只改一項；相鄰檢查的數字只用來檢查、不會被選成影子版本。
_V7 = [
    ("gap3", "開高 3% 以上不買（只看新買進）", {"gap": 0.03}, [{"gap": 0.02}, {"gap": 0.04}]),
    ("delay1", "延後 1 天換股", {"delay": 1}, [{"delay": 2}]),
    ("delay3", "延後 3 天換股", {"delay": 3}, [{"delay": 2}, {"delay": 4}]),
    ("hold10", "持有 10 天後持有現金到下一期", {"hold": 10}, [{"hold": 8}, {"hold": 12}]),
    ("hold2m", "每月一半資金、各持有兩個月", {"sleeves": 2}, [{"sleeves": 3}]),
    ("stop10", "跌 10% 停損（當期第一天開盤起算）", {"stop": 0.10}, [{"stop": 0.08}, {"stop": 0.12}]),
    ("stop15", "跌 15% 停損（當期第一天開盤起算）", {"stop": 0.15}, [{"stop": 0.125}, {"stop": 0.175}]),
    ("n3", "只買 3 檔", {"n": 3}, [{"n": 2}, {"n": 4}]),
    ("n8", "買 8 檔", {"n": 8}, [{"n": 7}, {"n": 9}]),
    ("reg200", "加權指數在 200 日均線下那期不進場", {"reg": 200}, [{"reg": 150}, {"reg": 250}]),
]
MENU = {
    "v3l": [
        ("delay5", "延後 5 天進場", {"delay": 5}, [{"delay": 3}, {"delay": 7}]),
        ("delay10", "延後 10 天進場", {"delay": 10}, [{"delay": 8}, {"delay": 12}]),
        ("gap3", "開高 3% 以上不買", {"gap": 0.03}, [{"gap": 0.02}, {"gap": 0.04}]),
        ("hold40", "持有 40 天", {"hold": 40}, [{"hold": 35}, {"hold": 45}]),
        ("hold80", "持有 80 天", {"hold": 80}, [{"hold": 75}, {"hold": 85}]),
        ("stop15", "跌 15% 停損", {"stop": 0.15}, [{"stop": 0.125}, {"stop": 0.175}]),
        ("stop20", "跌 20% 停損", {"stop": 0.20}, [{"stop": 0.175}, {"stop": 0.225}]),
        ("n3", "只買 3 檔", {"n": 3}, [{"n": 2}, {"n": 4}]),
        ("n8", "買 8 檔", {"n": 8}, [{"n": 7}, {"n": 9}]),
        ("reg200", "加權指數在 200 日均線下那期不進場", {"reg": 200}, [{"reg": 150}, {"reg": 250}]),
    ],
    "v7m": _V7,
    "v7l": _V7,
    "s3": [
        ("k20", "截止前 20 天建倉", {"k": 20}, [{"k": 18}, {"k": 22}]),
        ("k30", "截止前 30 天建倉", {"k": 30}, [{"k": 28}, {"k": 32}]),
        ("eff0", "生效日收盤賣出", {"out": 0}, [{"out": 1}]),
        ("stop10", "跌 10% 停損", {"stop": 0.10}, [{"stop": 0.08}, {"stop": 0.12}]),
        ("n3", "只買 3 檔", {"n": 3}, [{"n": 2}]),
        ("n5", "買 5 檔", {"n": 5}, [{"n": 6}]),
    ],
    "s5": [
        ("trail25", "最高收盤回落 25% 出場", {"trail": 0.25}, [{"trail": 0.225}, {"trail": 0.275}]),
        ("trail35", "最高收盤回落 35% 出場", {"trail": 0.35}, [{"trail": 0.325}, {"trail": 0.375}]),
        ("init15", "跌 15% 停損", {"init": 0.15}, [{"init": 0.125}, {"init": 0.175}]),
        ("init25", "跌 25% 停損", {"init": 0.25}, [{"init": 0.225}, {"init": 0.275}]),
        ("reg200", "加權指數在 200 日均線下不買", {"reg": 200}, [{"reg": 150}, {"reg": 250}]),
    ],
    "s1": [
        ("gapany", "不看開盤，訊號隔天都買", {"gap_max": None}, [{"gap_max": 0.01}, {"gap_max": 0.03}]),
        ("gapm1", "開盤低於前收 1% 以上才買", {"gap_max": -0.01}, [{"gap_max": -0.005}, {"gap_max": -0.015}]),
        ("hold2", "持有 2 天", {"hold": 2}, [{"hold": 1}]),
        ("hold4", "持有 4 天", {"hold": 4}, [{"hold": 5}]),
        ("atr15", "停損 1.5 倍 ATR", {"stop_atr": 1.5}, [{"stop_atr": 1.25}, {"stop_atr": 1.75}]),
        ("atr25", "停損 2.5 倍 ATR", {"stop_atr": 2.5}, [{"stop_atr": 2.25}, {"stop_atr": 2.75}]),
        ("reg200", "加權指數在 200 日均線下不買", {"reg": 200}, [{"reg": 150}, {"reg": 250}]),
    ],
}

# ── 比較方法與門檻（第 5c、5d 節） ─────────────────────────────────────────────
HAS_REP = ("v3l", "v7m", "v7l")     # 有複驗期間（2021-10 之前）的策略
EVENT = ("v3l", "s3")              # 事件型（前瞻門檻以「次」計）
PER_SIGNAL = ("s1", "s5")          # 逐訊號配對；t 值用訊號月份平均
UNIT = {"v3l": "期", "v7m": "期", "v7l": "期", "s3": "次", "s1": "個訊號", "s5": "個訊號"}
ALPHA = 0.05                        # Holm 校正的整體顯著水準（單尾）
T_SIG = 1.645                       # 校正前單尾 5%（待觀察／比較差）
T_REP = 1.0                         # 複驗期間 t 門檻
T_NOREP = 2.5                       # 沒有複驗期間時，校正前 t 門檻
MDD_PP = 3.0                        # 最大回落最多可比現行差幾個百分點
COST_X = 2.0                        # 成本加倍檢查
MIN_N = {"v3l": 8, "v7m": 24, "v7l": 24, "s3": 4, "s1": 30, "s5": 30}
MIN_MONTHS = 6                      # s1、s5 另需 6 個月以上
STRONG, WATCH, NONE, WORSE, SMALL = "證據強", "待觀察", "沒有比較好", "比較差", "樣本不足"

# ── 影子版本（第 6 節） ───────────────────────────────────────────────────
SHADOW_MAX = 2                      # 每條策略同時最多幾個影子版本
COOLDOWN_DAYS = 182                 # 淘汰或使用者回「不換」後，同一候選幾天內不再進影子
NEED = {"v3l": 2, "v7m": 10, "v7l": 10, "s3": 2, "s1": 10, "s5": 10}   # 前瞻完成數門檻

# ── 健檢（第 3、4 節） ─────────────────────────────────────────────────────
BOOT_N, SEED = 2000, 20261016       # 燈號：抽樣次數與種子
LIGHT = ((5.0, "明顯低於回測"), (20.0, "偏弱"), (80.0, "符合回測"))   # 百分位上限 → 燈號；高於 80＝偏強
LIGHT_TOP = "偏強"
FWD_MIN = {"event": 2, "other": 3}  # 前瞻少於這個數不打燈號（樣本太少）
HOLD_PCT_EV = 5.0                   # 持有中低於第 5 百分位 → 事件「表現偏離回測」
SPLIT_MIN_N, SPLIT_T = 10, 2.0      # 拆解：該組至少 10 筆、Welch t ≥ 2、前後兩半同方向
GAP_BINS = ((None, -0.01, "低開"), (-0.01, 0.01, "平開"), (0.01, 0.03, "高開 1～3%"), (0.03, None, "高開 ≥3%"))
REG_MA = 200                        # 拆解的大盤狀態用 200 日均線


def params(k: str, cand: str | None = None, nb: int | None = None) -> dict:
    """策略 k 的現行參數；cand＝候選代號（套上候選參數）；nb＝第幾個相鄰檢查（套上相鄰參數）。"""
    p = dict(CURRENT[k])
    if cand is None:
        return p
    c = next(x for x in MENU[k] if x[0] == cand)
    p.update(c[2] if nb is None else c[3][nb])
    return p


def p_one(t: float | None) -> float:
    """t 值 → 單尾 p 值（常態近似）；沒有 t 值＝1。"""
    if t is None or (isinstance(t, float) and math.isnan(t)):
        return 1.0
    return 0.5 * math.erfc(t / math.sqrt(2))


def holm(ps: list[float], alpha: float = ALPHA) -> list[bool]:
    """Holm 逐步校正：p 值由小到大，第 i 個（從 1 起）和 alpha ÷（m − i + 1）比，一旦不過，後面全部不過。"""
    m = len(ps)
    out = [False] * m
    for i, j in enumerate(sorted(range(m), key=lambda j: ps[j])):
        if ps[j] > alpha / (m - i):
            break
        out[j] = True
    return out


def checks(k: str, c: dict) -> dict:
    """六項檢查（第 5c 節）。c＝{mean, t, holm, rep: (平均, t)|None, nb: [相鄰平均…], drop_year, x2, mdd, mdd0}：
    mean／t＝主要期間配對差平均與 Newey-West t；holm＝Holm 校正後是否顯著；drop_year＝去掉合計最大的一年後的平均；
    x2＝成本加倍後的平均；mdd／mdd0＝候選／現行的最大回落（%）。→ {1..6: True／False}
    第 2 項：有複驗期間的策略＝複驗期間平均 > 0 且 t ≥ 1；沒有複驗期間的（s1、s3、s5）＝主要期間校正前 t ≥ 2.5（第 5d 節）。"""
    pos = lambda v: v is not None and v > 0
    rep = c.get("rep")
    nb = c.get("nb") or []
    t = c.get("t")
    if k in HAS_REP:
        c2 = bool(rep) and pos(rep[0]) and rep[1] is not None and rep[1] >= T_REP
    else:
        c2 = t is not None and t >= T_NOREP
    return {
        1: pos(c.get("mean")) and bool(c.get("holm")),
        2: c2,
        3: bool(nb) and all(v is not None and v >= 0 for v in nb),
        4: pos(c.get("drop_year")),
        5: pos(c.get("x2")),
        6: c.get("mdd") is not None and c.get("mdd0") is not None and c["mdd"] <= c["mdd0"] + MDD_PP,
    }


def tier(k: str, c: dict) -> tuple[str, list[int]]:
    """→ (分級, 沒過的檢查編號)。c 另含 n（主要期間單位數）、months（s1、s5 的月份數）。"""
    if (c.get("n") or 0) < MIN_N[k] or (k in PER_SIGNAL and (c.get("months") or 0) < MIN_MONTHS):
        return SMALL, []
    ck = checks(k, c)
    fails = [i for i, v in ck.items() if not v]
    mean, t = c.get("mean"), c.get("t")
    if not fails:
        return STRONG, []
    if mean is not None and mean < 0 and t is not None and t <= -T_SIG:
        return WORSE, fails
    if mean is not None and mean > 0 and t is not None and t >= T_SIG:
        return WATCH, fails
    return NONE, fails


def light(pct: float | None, n: int, event: bool) -> str:
    """前瞻平均在回測抽樣分布的百分位 → 燈號（第 3c 節）。"""
    if n < FWD_MIN["event" if event else "other"] or pct is None:
        return "樣本太少"
    for hi, lbl in LIGHT:
        if pct < hi:
            return lbl
    return LIGHT_TOP
