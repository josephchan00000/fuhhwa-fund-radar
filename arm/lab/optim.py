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


# ═══ 改良引擎（第 5c 節；docs 第 11 節第 4 步） ═════════════════════════════════════
# 候選和現行用同一套回測程式：財報、月營收＝bt3.account 的複本加上開高不追、停損；共識加碼＝strategy._trade；
# 長線＝growth._s5_sim；臺灣50＝tw50study.early_picks／early_trades。參數設成現行時結果必須和現行完全相同（測試守）。
# 每次回測輸出 {"u": {單位鍵: (決定日, 扣成本報酬 %, 有沒有買)}, "curve"／"seq": 最大回落用}。

def account_v(P, periods: list, b: str, *, mult: float = 1.0, limit: bool = True, gap: float | None = None,
              stop: float | None = None, log: list | None = None) -> dict:
    """bt3.account 的複本＋兩個候選旋鈕（gap、stop 皆為 None 時逐行等同 bt3.account）：
    gap＝不在原持股的新名單股票，開盤 ≥ 前一日收盤 ×（1＋gap）當期不買（資金留現金）；
    stop＝當期第一天開盤為參考價（續抱股也是），收盤跌破參考價 ×（1 − stop）當天收盤賣出（鎖跌停順延）、持有現金到期末。"""
    from .backtest import LIMIT_UP, exit_day, locked_down
    from .bt3 import side_cost
    S, T, cal = P.s, P.T, P.cal
    cash = 1.0
    hold: dict[str, float] = {}
    last: dict[str, float] = {}
    curve, units = [], []

    def px(c: str, i: int) -> float | None:
        v = S[c]["c"][i]
        if v:
            last[c] = v
        return v or last.get(c)

    def value(i: int) -> float:
        return cash + sum(sh * (px(c, i) or 0.0) for c, sh in hold.items())

    for k, (t, x, picks) in enumerate(periods):
        j = t + 1
        if j > x or j >= T or not picks:
            continue
        V0 = value(t)
        if not curve:
            curve.append((t, V0))
        cost = 0.0
        lim = lock = ngap = nstop = 0
        pend: dict[str, int] = {}
        tgt = set(picks)
        for c in [c for c in hold if c not in tgt]:
            s = S[c]
            if limit and locked_down(s, j):
                pend[c] = exit_day(s, j, T)
                lock += 1
                continue
            p = s["o"][j] or px(c, t)
            amt = hold.pop(c) * p
            cash += amt * (1 - side_cost(b, True, mult))
            cost += amt * side_cost(b, True, mult)
            if log is not None:
                log.append(("s", k, c, j, p, True, "drop"))
        Vo = cash + sum(sh * ((S[c]["o"][j] or px(c, t)) or 0.0) for c, sh in hold.items())
        tv = Vo * (1 - side_cost(b, False, mult)) / len(picks)
        buy = 0.0
        for c in picks:
            s = S[c]
            o = s["o"][j]
            if not o:
                if log is not None and c not in hold:
                    log.append(("x", k, c, j, "noopen"))
                continue
            cur = hold.get(c, 0.0) * o
            diff = tv - cur
            if diff > 0:
                if limit and o >= (s["c"][t] or px(c, t) or o) * LIMIT_UP:
                    lim += c not in hold
                    if log is not None and c not in hold:
                        log.append(("x", k, c, j, "lim"))
                    continue
                if gap is not None and c not in hold and o >= (s["c"][t] or px(c, t) or o) * (1 + gap):
                    ngap += 1
                    if log is not None:
                        log.append(("x", k, c, j, "gap"))
                    continue
                if log is not None and c not in hold:
                    log.append(("b", k, c, j, o))
                cash -= diff * (1 + side_cost(b, False, mult))
                cost += diff * side_cost(b, False, mult)
                hold[c] = hold.get(c, 0.0) + diff / o
                buy += diff
            elif diff < 0:
                cash += -diff * (1 - side_cost(b, True, mult))
                cost += -diff * side_cost(b, True, mult)
                hold[c] = hold.get(c, 0.0) + diff / o
        ref = {c: S[c]["o"][j] for c in hold if S[c]["o"][j]} if stop is not None else {}
        for i in range(j, x + 1):
            for c in [c for c, d2 in pend.items() if d2 == i]:
                p = px(c, i) or 0.0
                amt = hold.pop(c) * p
                cash += amt * (1 - side_cost(b, True, mult))
                cost += amt * side_cost(b, True, mult)
                del pend[c]
                if log is not None:
                    log.append(("s", k, c, i, p, False, "lock"))
            if stop is not None:
                for c in [c for c in hold if c not in pend and ref.get(c)]:
                    cl = S[c]["c"][i]
                    if not cl or cl >= ref[c] * (1 - stop):
                        continue
                    nstop += 1
                    i2 = exit_day(S[c], i, T)
                    if i2 != i:
                        pend[c] = i2                      # 鎖跌停賣不掉：順延（超過期末就留給期末處理）
                        continue
                    amt = hold.pop(c) * cl
                    cash += amt * (1 - side_cost(b, True, mult))
                    cost += amt * side_cost(b, True, mult)
                    if log is not None:
                        log.append(("s", k, c, i, cl, False, "stop"))
            curve.append((i, value(i)))
        nxt = periods[k + 1][0] if k + 1 < len(periods) else None
        if nxt != x:
            for c in list(hold):
                s = S[c]
                i2 = exit_day(s, x, T) if limit else x
                lock += i2 != x
                p = px(c, i2) or px(c, x) or 0.0
                amt = hold.pop(c) * p
                cash += amt * (1 - side_cost(b, True, mult))
                cost += amt * side_cost(b, True, mult)
                if log is not None:
                    log.append(("s", k, c, i2, p, False, "end" if i2 == x else "endlock"))
            curve[-1] = (x, cash)
        V1 = curve[-1][1]
        units.append({"d": cal[t], "t": t, "x": x, "r": (V1 / V0 - 1) * 100 if V0 > 0 else None, "hd": x - t,
                      "to": buy / Vo if Vo > 0 else None, "cost": cost / V0 * 100 if V0 > 0 else None,
                      "n": len(picks), "lim": lim, "lock": lock, "gap": ngap, "stop": nstop})
    return {"units": units, "curve": curve}


def _below(idx: list, ma: list, t: int) -> bool:
    """決定日加權指數收盤低於均線（缺值往前找；不知道＝不算低於）。"""
    from .health import regime
    return regime(idx, ma, t) is False


class PerCtx:
    """財報、月營收（v3 長歷史面板）的變體回測環境：現行規則的已完成各期 rows 只算一次。"""

    def __init__(self, P, E, k: str, *, eps=None, rev=None, until: str | None = None):
        from . import bt3s, v3live
        src, b = {x[0]: (x[1], x[2]) for x in v3live.LIVE}[k]
        self.P, self.k, self.src, self.b = P, k, src, b
        self.umin = v3live.UMIN[src]
        rows = bt3s.p3_rows(P, E, b, P.codes, eps, v3live.HOLD3) if src == "p3" else bt3s.p7_rows(P, E, b, P.codes, rev)
        self.rows = [r for r in rows if r[1] is not None and (until is None or P.cal[r[0]] < until)]
        self._ma: dict[int, list] = {}

    def ma(self, n: int) -> list:
        if n not in self._ma:
            from .ta import sma
            self._ma[n] = sma(self.P.idx, n)
        return self._ma[n]

    def run(self, p: dict, mult: float = 1.0, log: list | None = None) -> dict:
        from . import bt3s
        P = self.P
        pk = bt3s.pick(self.rows, 0.0, p["n"], False, self.umin)
        if (p.get("sleeves") or 1) > 1:
            return self._sleeves(pk, p, mult)
        per, skip = [], []
        d = p.get("delay") or 0
        for t, x, picks in pk:
            if p.get("reg") and _below(P.idx, self.ma(p["reg"]), t):
                skip.append(t)
                continue
            t2, x2 = t + d, x + d
            if p.get("hold") is not None:
                x2 = t2 + p["hold"] if self.src == "p3" else min(t2 + p["hold"], x + d)
            if x2 >= P.T:
                continue
            per.append((t2, x2, picks, t))
        acc = account_v(P, [(a, z, c) for a, z, c, _ in per], self.b, mult=mult, gap=p.get("gap"), stop=p.get("stop"),
                        log=log)
        back = {a: t0 for a, _, _, t0 in per}
        u = {back[x["t"]]: (P.cal[back[x["t"]]], x["r"], True) for x in acc["units"] if x.get("r") is not None}
        for t in skip:
            u[t] = (P.cal[t], 0.0, False)
        return {"u": u, "curve": acc["curve"], "pk": pk}

    def _sleeves(self, pk: list, p: dict, mult: float) -> dict:
        """每月用 1/K 資金買當月名單、各持有 K 期（K 組輪流，每組自己期期相連）。第 k 期的報酬＝合併淨值
        從第 k 個決定日收盤到第 k+1 個決定日收盤；K 組都在場的月份才算。"""
        P, K = self.P, p["sleeves"]
        ts = [t for t, _, _ in pk] + ([pk[-1][1]] if pk else [])
        curves, span = [], []
        for s in range(K):
            ks = list(range(s, len(pk), K))
            per = [(pk[k][0], ts[k + K], pk[k][2]) for k in ks if k + K < len(ts) and ts[k + K] < P.T]
            acc = account_v(P, per, self.b, mult=mult, gap=p.get("gap"), stop=p.get("stop"))
            cv = dict(acc["curve"])
            curves.append(cv)
            span.append((per[0][0], per[-1][1]) if per else (None, None))
        if any(a is None for a, _ in span):
            return {"u": {}, "curve": [], "pk": pk}
        lo, hi = max(a for a, _ in span), min(z for _, z in span)
        days = sorted(i for i in set().union(*curves) if lo <= i <= hi)
        lastv = [None] * K

        def comb(i):
            for s in range(K):
                if i in curves[s]:
                    lastv[s] = curves[s][i]
            return sum(v for v in lastv if v is not None) / K if all(v is not None for v in lastv) else None
        cv = [(i, v) for i in days if (v := comb(i)) is not None]
        val = dict(cv)
        u = {}
        for k in range(len(pk)):
            a, z = ts[k], ts[k + 1] if k + 1 < len(ts) else None
            if z is None or a < lo or z > hi or a not in val or z not in val:
                continue
            u[a] = (P.cal[a], (val[z] / val[a] - 1) * 100, True)
        return {"u": u, "curve": cv, "pk": pk}


def _reg_maps(cal: list[str], idx: list, ns=(150, 200, 250)) -> dict:
    """{均線天數: {日期: 是否在均線（含）之上}}（五年加權指數）。"""
    from .ta import sma
    out = {}
    for n in ns:
        ma = sma(idx, n)
        out[n] = {d: idx[i] >= ma[i] for i, d in enumerate(cal) if idx[i] and ma[i]}
    return out


def _v3_r(r: float, b: str, mult: float, cost: float = 0.585) -> float:
    """策略原本扣舊成本 cost% 的報酬 → 回測方法 v3 成本（含成本倍數）。"""
    from .bt3 import rt_cost
    return r + cost - rt_cost(b, mult) * 100


class S1Ctx:
    """共識加碼：訊號、價格（含 ATR）、加權指數；大盤濾網用五年加權指數。"""

    def __init__(self, keep: dict):
        from . import strategy, ta
        self.D = D = keep["D"]
        self.sigs = strategy._signals("s1", D, keep["sig_hist"], keep["L"], keep["meta"])
        self.st0 = next(s for s in strategy.STRATEGIES if s["key"] == "s1")
        self.idx, self.io, self.T = keep["taiex"], D.taiex_open(), D.T
        self.reg = _reg_maps(keep["DL_cal"], keep["DL_taiex"])
        self.cap_of = _cap_of(keep)
        self._s: dict = {}
        self._ta = ta

    def series(self, c):
        if c not in self._s:
            S = self.D.series(c)
            self._s[c] = (S, self._ta.atr(S["h"], S["l"], S["c"]))
        return self._s[c]

    def run(self, p: dict, mult: float = 1.0, raw: bool = False) -> dict:
        """raw＝回傳原始交易紀錄（不變式測試用）。"""
        from . import strategy
        from .health import bucket, reg_lookup
        D = self.D
        st = {**self.st0, "gap_max": p["gap_max"], "hold": p["hold"], "stop_atr": p["stop_atr"]}
        u, recs = {}, []
        for c, t in self.sigs:
            key = (c, D.cal[t])
            if p.get("reg") and reg_lookup(self.reg[p["reg"]], D.cal, t) is False:
                u[key] = (D.cal[t], 0.0, False)
                continue
            S, atr = self.series(c)
            rec = strategy._trade(st, c, t, S, atr, self.idx, self.T, self.io)
            recs.append((c, t, rec))
            if rec is None or rec.get("st") == "open":
                continue                                  # 還沒出場：不配對
            if rec.get("st") == "skip":
                u[key] = (D.cal[t], 0.0, False)
            else:
                b = bucket(self.cap_of(c, t))
                u[key] = (D.cal[t], _v3_r(rec["r"], b, mult), True, t, t + rec["held"], c)
        return {"u": u, "recs": recs} if raw else {"u": u}


class S5Ctx:
    """長線：候選（每月四關）、價格面板、對同宇宙等權；大盤濾網用五年加權指數。"""

    def __init__(self, keep: dict):
        from . import growth
        self.P = keep["gP"]
        self.D = keep["D"]
        self.cands = growth._s5_cands(self.P, growth.load_rev_hist(), keep["rev_shards"])
        self.idx, self.io = keep["taiex"], self.D.taiex_open()
        try:
            self.ew = growth.ew_index(self.P)
        except Exception:                                 # noqa: BLE001
            self.ew = None
        self.reg = _reg_maps(keep["DL_cal"], keep["DL_taiex"])
        self.cap_of = _cap_of(keep)

    def run(self, p: dict, mult: float = 1.0, raw: bool = False) -> dict:
        from . import growth
        from .health import bucket, reg_lookup
        cal = self.D.cal
        sp = {k: p[k] for k in ("init", "trail", "maxd", "gap", "wait")}
        extra = (lambda c, t: reg_lookup(self.reg[p["reg"]], cal, t) is not False) if p.get("reg") else None
        recs = growth._s5_sim(self.P, self.cands, self.idx, self.io, sp, self.ew, extra)
        u = {(c, cal[t]): (cal[t], 0.0, False) for t, c in self.cands}       # 沒有買（濾掉、持有中不重複買）＝0
        ix = self.D.ix
        for r in recs:
            key = (r["c"], r["d"])
            if r["st"] in ("open", "cand"):
                u.pop(key, None)                          # 還沒出場或還沒進場：不配對
            elif r["st"] == "closed":
                t = ix[r["d"]]
                b = bucket(self.cap_of(r["c"], t))
                j = ix[r["bd"]]
                u[key] = (r["d"], _v3_r(r["r"], b, mult), True, j - 1, ix[r["sd"]], r["c"])
        return {"u": u, "recs": recs} if raw else {"u": u}


class S3Ctx:
    """臺灣50 提前卡位：歷次審核計畫（plans）與排名快取；出場日、停損、檔數、提前天數為旋鈕。"""

    def __init__(self, keep: dict):
        from . import indexes, tw50study
        self.D = D = keep["D"]
        self.cfg = indexes.load_cfg()
        self.ctx = tw50study._Ctx(D, self.cfg)
        self.pl = tw50study.plans(D, self.cfg, self.ctx)

    def trades(self, p: dict) -> list[dict]:
        """所有審核（含下一次）的提前卡位交易，同 tw50study.version_trades 的 early（參數＝現行時完全相同）。"""
        from . import tw50study as TW
        D, out = self.D, []
        for q in self.pl:
            pk = TW.early_picks(self.ctx, q, self.ctx.pres.get(q["review"]) if q["official"] else
                                TW._pre_next(D, q.get("effective")), p["k"], p["n"]) \
                if (p["k"], p["n"]) != (TW.EARLY_K, TW.EARLY_N) else q
            if p["out"] != -1:
                eff_o = next((h.get("eff_override") or {} for h in (self.ctx.ix.get("history") or [])
                              if h.get("review") == q["review"]), {})
                q = {**q, "out": TW.td_shift(q["effective"], p["out"]) if p["out"] else q["effective"],
                     "out_c": {c: (TW.td_shift(v, p["out"]) if p["out"] else v) for c, v in eff_o.items() if v}}
            trs = TW.early_trades(D, self.ctx.P, q, {}, pk, None if pk is q else {})
            if p.get("stop"):
                trs = [_stop_trade(D, self.ctx.P, x, p["stop"]) for x in trs]
            out += trs
        return out

    def run(self, p: dict, mult: float = 1.0, raw: bool = False) -> dict:
        trs = self.trades(p)
        g: dict = {}
        for x in trs:
            g.setdefault(x.get("review"), []).append(x)
        u = {}
        for rv, xs in g.items():
            if any(x.get("st") in ("open", "cand") for x in xs):
                continue                                  # 還沒走完的審核：不配對
            cl = [x for x in xs if x.get("st") == "closed" and x.get("r") is not None]
            if not cl:
                continue
            d = min(x["d"] for x in cl)
            u[rv] = (d, sum(_v3_r(x["r"], "L", mult) for x in cl) / len(cl), True)
        return {"u": u, "recs": trs} if raw else {"u": u}


def _stop_trade(D, P, x: dict, s: float) -> dict:
    """臺灣50 交易套停損：買進後收盤跌破買進價 ×（1 − s）→ 當天收盤賣（鎖跌停順延）；沒觸發＝原樣。"""
    from .backtest import exit_day
    if x.get("st") != "closed" or not x.get("bd") or not x.get("sd") or not x.get("entry"):
        return x
    S = P.s(x["c"])
    i0, i1 = D.ix[x["bd"]], D.ix[x["sd"]]
    end = i1 - 1 if x.get("so") else i1
    for i in range(i0, end + 1):
        cl = S["c"][i]
        if cl and cl < x["entry"] * (1 - s):
            i2 = min(exit_day(S, i, D.T), end)
            r = S["c"][i2] / x["entry"] - 1 - 0.00585
            return {**x, "exit": S["c"][i2], "sd": D.cal[i2], "so": False, "r": round(r * 100, 2),
                    "held": i2 - i0 + 1, "why": "停損"}
    return x


def _cap_of(keep: dict):
    """決定日市值（v3live 面板的月底市值；日期對到每日資料的日曆）。"""
    ctx = keep.get("v3ctx")
    P = ctx[0] if ctx else None
    D = keep["D"]
    pix = P.D.ix if P is not None else {}

    def f(c, t):
        i = pix.get(D.cal[t])
        return (P.cap.get(c) or [None] * P.T)[i] if P is not None and i is not None else None
    return f


# ── 配對比較與分級 ─────────────────────────────────────────────────────

def _main(k: str, d: str) -> bool:
    return k not in HAS_REP or d >= MAIN_FROM


def pairs(u0: dict, u1: dict) -> list[tuple]:
    """現行 u0、候選 u1（{鍵: (決定日, 報酬 %, 有沒有買, …)}）→ 兩邊都有、至少一邊有買的單位：
    [(決定日, 候選 − 現行, 鍵)]，依決定日排序。"""
    out = []
    for key in u0.keys() & u1.keys():
        a, b = u0[key], u1[key]
        if not a[2] and not b[2]:
            continue
        out.append((a[0], b[1] - a[1], key))
    return sorted(out, key=lambda z: (z[0], str(z[2])))


def _t(k: str, ds: list[tuple]) -> float | None:
    """Newey-West t：逐訊號的策略先依訊號月份平均（同一個月的訊號彼此相關），其餘逐單位。"""
    from .bt3 import nw_t
    if k in PER_SIGNAL:
        g: dict = {}
        for d, v, _ in ds:
            g.setdefault(d[:7], []).append(v)
        return nw_t([sum(v) / len(v) for _, v in sorted(g.items())])
    return nw_t([v for _, v, _ in ds])


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def drop_year(ds: list[tuple]) -> float | None:
    """去掉配對差合計最大的一個年份（依決定日）後的平均；只有一個年份回 None。"""
    by: dict = {}
    for d, v, _ in ds:
        by.setdefault(d[:4], []).append(v)
    if len(by) < 2:
        return None
    worst = max(by, key=lambda y: (sum(by[y]), y))
    return _mean([v for y, vs in by.items() if y != worst for v in vs])


def mdd_seq(rs: list[float]) -> float | None:
    """單位報酬（%）依序連乘的淨值最大回落（%）。"""
    if not rs:
        return None
    v = pk = 1.0
    m = 0.0
    for r in rs:
        v *= 1 + r / 100
        pk = max(pk, v)
        m = max(m, 1 - v / pk)
    return m * 100


class _SP:
    """bt3.slots 用的價格介面：.s[代號]＝{o, c}。"""

    def __init__(self, f):
        self._f, self._c = f, {}

    @property
    def s(self):
        return self

    def __getitem__(self, c):
        if c not in self._c:
            self._c[c] = self._f(c)
        return self._c[c]


def mdd_of(k: str, C, run: dict) -> float | None:
    """主要期間的最大回落（%）：定期換股＝資金帳戶逐日淨值；逐訊號＝8 格資金帳戶；臺灣50＝每次審核依序連乘。"""
    from . import bt3
    if isinstance(C, PerCtx):
        cv = [(i, v) for i, v in run.get("curve") or [] if _main(k, C.P.cal[i])]
        return bt3.curve_stats(cv, C.P.cal).get("mdd") if len(cv) > 1 else None
    if isinstance(C, S3Ctx):
        return mdd_seq([v[1] for _, v in sorted(run["u"].items(), key=lambda z: z[1][0])])
    us = [{"t": v[3], "x": v[4], "c": v[5], "r": v[1]} for v in run["u"].values() if v[2] and len(v) > 5]
    if not us:
        return None
    sp = _SP(lambda c: C.series(c)[0]) if isinstance(C, S1Ctx) else _SP(lambda c: C.P.s[c])
    sl = bt3.slots(sp, us, n=8)
    return bt3.curve_stats(sl["curve"], C.D.cal).get("mdd") if len(sl["curve"]) > 1 else None


def _summ(k: str, ds: list[tuple]) -> dict:
    main = [x for x in ds if _main(k, x[0])]
    rep = [x for x in ds if not _main(k, x[0])]
    return {"n": len(main), "months": len({d[:7] for d, _, _ in main}), "mean": _mean([v for _, v, _ in main]),
            "t": _t(k, main), "rep": (_mean([v for _, v, _ in rep]), _t(k, rep)) if k in HAS_REP and rep else None,
            "drop_year": drop_year(main)}


def evaluate(k: str, C, *, log=print) -> dict:
    """一條策略的全部候選（含相鄰檢查）→ 分級。C＝PerCtx／S1Ctx／S5Ctx／S3Ctx。門檻全部來自本檔常數（optim v1）。"""
    import time
    t0 = time.time()
    p0 = params(k)
    cur, cur2 = C.run(p0), C.run(p0, mult=COST_X)
    mdd0 = mdd_of(k, C, cur)
    main0 = [v[1] for v in cur["u"].values() if _main(k, v[0])]
    took0 = [v[1] for v in cur["u"].values() if _main(k, v[0]) and v[2]]
    rows = []
    for key, what, st, nbs in MENU[k]:
        r1, r2 = C.run(params(k, key)), C.run(params(k, key), mult=COST_X)
        ds = pairs(cur["u"], r1["u"])
        sm = _summ(k, ds)
        nb = []
        for i in range(len(nbs)):
            dn = [x for x in pairs(cur["u"], C.run(params(k, key, i))["u"]) if _main(k, x[0])]
            nb.append(_mean([v for _, v, _ in dn]))
        x2 = [x for x in pairs(cur2["u"], r2["u"]) if _main(k, x[0])]
        m1 = [v[1] for v in r1["u"].values() if _main(k, v[0])]
        t1 = [v[1] for v in r1["u"].values() if _main(k, v[0]) and v[2]]
        rows.append({"k": key, "what": what, **sm, "nb": nb, "x2": _mean([v for _, v, _ in x2]),
                     "mdd": mdd_of(k, C, r1), "mdd0": mdd0, "avg0": _mean(main0), "avg1": _mean(m1),
                     "nt1": len(t1), "avgt1": _mean(t1)})
    hs = holm([p_one(r["t"]) for r in rows])
    for r, h in zip(rows, hs):
        r["p"] = p_one(r["t"])
        r["holm"] = h
        r["tier"], r["fails"] = tier(k, r)
    log(f"[opt] {k}：{len(rows)} 個候選、{time.time() - t0:.1f} 秒")
    return {"k": k, "n0": len(main0), "avg0": _mean(main0), "nt0": len(took0), "avgt0": _mean(took0), "mdd0": mdd0,
            "cands": rows}


def _rd(x, k: int = 3):
    if isinstance(x, float):
        return None if x != x else round(x, k)
    if isinstance(x, (list, tuple)):
        return [_rd(v, k) for v in x]
    if isinstance(x, dict):
        return {a: _rd(b, k) for a, b in x.items()}
    return x


def run_all(P=None, keep: dict | None = None, *, log=print) -> dict:
    """每週重跑：六條策略的全部候選。P＝v3 長歷史面板；keep＝analyze.run(keep=…) 的中間物件。"""
    from . import bt3, bt3d
    from . import packtest as PT
    res = {}
    if P is not None:
        E = bt3.Elig(P)
        eps, rev = bt3d.load_eps(), PT.load_rev()
        for k in ("v3l", "v7m", "v7l"):
            res[k] = evaluate(k, PerCtx(P, E, k, eps=eps, rev=rev), log=log)
    if keep is not None:
        for k, cls in (("s1", S1Ctx), ("s5", S5Ctx), ("s3", S3Ctx)):
            try:
                res[k] = evaluate(k, cls(keep), log=log)
            except Exception as e:                        # noqa: BLE001 —— 一條失敗不連累其他
                res[k] = {"k": k, "err": f"{type(e).__name__}: {e}"}
    return {"ver": OPT_VER, "since": OPT_SINCE, "res": _rd(res)}
