"""《超級績效》技術線型（tw-superstock-lab/reports/W2_plan.md v1；2026-10-16 使用者：「名單太多了」「超級績效不是也有參考
技術線嗎」）：每檔股票每天的狀態（今天突破／突破後仍在買點／準備好／突破失敗／漲太遠／打底中）、樞紐、停損、加分。

純 Python（CI 沒有 pandas）。研究版（tw-superstock-lab src/superstock/sepa.py）的狀態轉換、第幾個基底、爆發型
直接呼叫這裡的函式；緊密整理、RS 線、200 日線上揚天數、量價足跡兩邊各算一次，tests 逐日比對一致。
所有判斷只用當天收盤以前的資料。只標位置與書上的算法，不是買賣訊號。"""
from __future__ import annotations

N_SHOW = 10             # 每天最多列幾檔（使用者 2026-10-16）
READY = 0.05            # 準備好：收盤在樞紐 × 0.95 到樞紐之間
BUY = 0.05              # 買點範圍：樞紐到樞紐 × 1.05（歐尼爾的常用標準；書上沒有寫死數字）
BRK_VOL = 1.5           # 突破量 ≥ 到前一天為止的 50 日均量 × 1.5（同 S01）
DRY = 0.7               # 量縮：10 日 ÷ 50 日均量
STOP = 0.08             # 停損：樞紐下 8% 與整理期間最低價取較高者
POST = 5                # 突破後 5 個交易日內算「突破後仍在買點」或「突破失敗」
FAIL = 0.97             # 突破失敗：收盤跌回樞紐 × 0.97 以下
EXT_MA50 = 1.25         # 漲太遠：收盤 > 50 日線 × 1.25
EXT_DAYS = 60           # 或近 60 日內突破過、收盤 > 那次樞紐 × 1.05
NEAR_HIGH = 0.85        # 緊密整理：收盤 ≥ 52 週高點 × 0.85
TIGHT = (10, 0.08)      # 緊密整理（K 日、高低幅度上限）預設；研究在 IS 選定後寫進 data/lab/sepa_research.json
BASE = {"gap": 10, "dd": 0.10, "days": 15}
PP = {"look": 30, "cons_min": 10, "surge_days": 40, "mult": 2.0, "vol_x": 2.0, "dd": 0.20, "dd_low": 0.25,
      "low_px": 50.0, "dd_tight": 0.10}
MA200_UP = 80           # 200 日線連續上揚 ≥ 80 個交易日（書：最好 4～5 個月）加分
UD_DAYS, UD_MIN = 50, 1.2
RS_HI = 90
ST = {-1: "不在名單", 0: "打底中", 1: "今天突破", 2: "突破後仍在買點", 3: "準備好", 4: "突破失敗", 5: "漲太遠"}
SHOW = (1, 2, 3)        # 上頁面的狀態
KIND = {"vcp": "標準 VCP", "tight": "緊密整理", "pp": "爆發型"}
SCORE_ITEMS = ("RS ≥ 90", "RS 線創新高", "第 1、2 個基底", "200 日線上揚 ≥ 4 個月", "營收創新高", "飆股候選",
               "量價足跡 ≥ 1.2", "同族群 ≥ 2 檔")


# ---------------------------------------------------------------------------------------------- 基本計算
def mean_last(xs: list, t: int, n: int, k_min: int):
    """xs[t−n+1..t] 的平均（略過 None），有值的天數 < k_min 回 None；同 pandas rolling(n, min_periods=k_min)。"""
    a = t - n + 1
    if a < 0:
        a = 0
    v = [x for x in xs[a:t + 1] if x is not None]
    return sum(v) / len(v) if len(v) >= k_min else None


def rolling_mean(xs: list, n: int) -> list:
    """每天往前 n 日（含當天）的平均，n 日都有值才算（同 pandas rolling(n, min_periods=n)）。"""
    out = [None] * len(xs)
    s, cnt = 0.0, 0
    for t, x in enumerate(xs):
        if x is not None:
            s += x
            cnt += 1
        if t >= n:
            y = xs[t - n]
            if y is not None:
                s -= y
                cnt -= 1
        if cnt == n:
            out[t] = s / n
    return out


def ma200_info(c: list) -> tuple[list, list, list]:
    """c＝前值補齊的收盤 → (200 日線, 20 日前的 200 日線, 200 日線連續上揚天數)。"""
    ma = rolling_mean(c, 200)
    prev = [None] * 20 + ma[:-20] if len(ma) > 20 else [None] * len(ma)
    up = [0] * len(ma)
    for t in range(1, len(ma)):
        if ma[t] is not None and ma[t - 1] is not None and ma[t] > ma[t - 1]:
            up[t] = up[t - 1] + 1
    return ma, prev, up


def rsl_at(c: list, idx: list, t: int, n: int = 252, k_min: int = 200) -> tuple[bool, bool]:
    """RS 線＝收盤 ÷ 大盤指數（研究：含息收盤 ÷ 加權報酬指數；頁面：收盤 ÷ 加權指數）。
    → (RS 線創 n 日新高, 創新高而收盤還沒創 n 日新高＝領先)。c、idx 都是前值補齊。"""
    if c[t] is None or not idx[t]:
        return False, False
    a = max(0, t - n + 1)
    rs = [c[k] / idx[k] for k in range(a, t + 1) if c[k] is not None and idx[k]]
    cs = [c[k] for k in range(a, t + 1) if c[k] is not None]
    if len(rs) < k_min:
        return False, False
    new = c[t] / idx[t] >= max(rs)
    return new, new and not (len(cs) >= k_min and c[t] >= max(cs))


def tight_at(h: list, l: list, c: list, hi52, t: int, K: int, X: float):
    """緊密整理：近 K 日（含當天）最高 ÷ 最低 − 1 ≤ X，且收盤 ≥ 52 週高點 × 0.85 → (樞紐, 整理低點)；不成立回 None。"""
    if t - K + 1 < 0 or c[t] is None or hi52 is None:
        return None
    hs = [x for x in h[t - K + 1:t + 1] if x is not None]
    ls = [x for x in l[t - K + 1:t + 1] if x is not None]
    if len(hs) < K - 2 or len(ls) < K - 2:
        return None
    H, L = max(hs), min(ls)
    if not L > 0 or H / L - 1 > X or c[t] < NEAR_HIGH * hi52:
        return None
    return H, L


def pp_at(h: list, l: list, c: list, v: list, v50: list, raw_c, dry, t: int, spec: dict = PP):
    """爆發型（Power Play）：近 30 日最高點 p 在 10～30 日前；p 之前 40 日內的最低收盤到 p 漲 ≥ 1 倍、期間有一天量
    ≥ 50 日均量 × 2；p 之後回檔 ≤ 20%（原始收盤 < 50 元時 ≤ 25%），回檔 > 10% 時另要量縮 ≤ 0.7 → (樞紐, 整理低點)。"""
    a = t - spec["look"]
    if a - spec["surge_days"] < 0:
        return None
    p, hp = None, None
    for k in range(a, t + 1):
        x = h[k]
        if x is not None and (hp is None or x > hp):
            p, hp = k, x
    if p is None or t - p < spec["cons_min"]:
        return None
    q, cq = None, None
    for k in range(p - spec["surge_days"], p + 1):
        x = c[k]
        if x is not None and (cq is None or x < cq):
            q, cq = k, x
    if q is None or q >= p or not cq or cq <= 0:
        return None
    cmax = max(x for x in c[q:p + 1] if x is not None)
    if cmax / cq < spec["mult"]:
        return None
    if not any(v[k] is not None and v50[k] and v[k] >= spec["vol_x"] * v50[k] for k in range(q, p + 1)):
        return None
    lows = [x for x in l[p + 1:t + 1] if x is not None]
    if not lows:
        return None
    lo = min(lows)
    dd = 1 - lo / hp
    lim = spec["dd_low"] if raw_c is not None and raw_c < spec["low_px"] else spec["dd"]
    if dd > lim or (dd > spec["dd_tight"] and (dry is None or dry > DRY)):
        return None
    return hp, lo


def base_counts(c: list, ma200: list, ma200p: list, spec: dict = BASE) -> list[int]:
    """第幾個基底（0＝不在第二階段）。第二階段起點＝「收盤 > 200 日線、200 日線比 20 日前高」連續成立的第一天
    （中斷 ≤ 10 個交易日不算中斷）；之後每次「從高點回檔 ≥ 10%、歷時 ≥ 15 個交易日、之後收盤再創新高」算一個
    完成的基底，目前的整理＝完成數 ＋ 1。c＝前值補齊的收盤。"""
    out = [0] * len(c)
    active, gap, peak, pday, mn, done = False, 0, 0.0, 0, 0.0, 0
    for t, x in enumerate(c):
        m, mp = ma200[t], ma200p[t]
        s2 = x is not None and m is not None and mp is not None and x > m and m > mp
        if s2:
            gap = 0
            if not active:
                active, peak, pday, mn, done = True, x, t, x, 0
        elif active:
            gap += 1
            if gap > spec["gap"]:
                active = False
        if not active:
            continue
        if x is not None:
            if x > peak:
                if peak > 0 and 1 - mn / peak >= spec["dd"] and t - pday >= spec["days"]:
                    done += 1
                peak, pday, mn = x, t, x
            elif x < mn:
                mn = x
        out[t] = done + 1
    return out


def ready_at(in_list: bool, el: bool, c, dry, vcp, tight, pp):
    """今天是不是「準備好」→ (樞紐, 整理低點, 種類) 或 None。依序看標準 VCP、緊密整理（兩者要在名單上；緊密整理另要量縮
    ≤ 0.7，VCP 的條件本身已含）、爆發型（不必在名單上，合格股票即可）；收盤在樞紐 × 0.95 到樞紐之間。"""
    if c is None:
        return None
    for kind, x, ok in (("vcp", vcp, in_list), ("tight", tight, in_list and dry is not None and dry <= DRY),
                        ("pp", pp, el)):
        if x is None or not ok:
            continue
        piv, low = x
        if piv * (1 - READY) <= c <= piv:
            return piv, low, kind
    return None


def stop_px(piv: float, low) -> float:
    return max(piv * (1 - STOP), low) if low is not None else piv * (1 - STOP)


class Track:
    """一檔股票逐日往後推的狀態：昨天的「準備好」、最近一次突破。"""

    __slots__ = ("rp", "rl", "rk", "bd", "bp", "bl", "bk", "bf")

    def __init__(self):
        self.rp = self.rl = self.rk = None
        self.bd = self.bp = self.bl = self.bk = None
        self.bf = False

    def step(self, t: int, c, vol, v50_prev, ma50, on: bool, ready):
        """t 日收盤後 → (狀態, 樞紐, 整理低點, 種類)。on＝今天在名單上或是爆發型；ready＝ready_at() 的結果。
        優先順序：今天突破 > 突破後仍在買點 > 準備好 > 突破失敗 > 漲太遠 > 打底中；不在名單上而且不是突破相關 → −1。"""
        st, piv, low, kind = -1, None, None, None
        brk = (self.rp is not None and c is not None and self.rp < c <= self.rp * (1 + BUY) and vol is not None
               and v50_prev and vol >= BRK_VOL * v50_prev)
        recent = self.bd is not None and 0 < t - self.bd <= POST and not self.bf and c is not None
        post = recent and self.bp <= c <= self.bp * (1 + BUY)
        fail = recent and c < self.bp * FAIL
        if brk:
            st, piv, low, kind = 1, self.rp, self.rl, self.rk
            self.bd, self.bp, self.bl, self.bk, self.bf = t, piv, low, kind, False
        elif post:
            st, piv, low, kind = 2, self.bp, self.bl, self.bk
        elif on and ready is not None:
            st, (piv, low, kind) = 3, ready
        elif fail:
            st, piv, low, kind = 4, self.bp, self.bl, self.bk
        elif on and c is not None and ((ma50 and c > EXT_MA50 * ma50) or (
                self.bd is not None and t - self.bd <= EXT_DAYS and c > self.bp * (1 + BUY))):
            st = 5
        elif on:
            st = 0
        if fail:
            self.bf = True
        self.rp, self.rl, self.rk = ready if ready is not None else (None, None, None)
        return st, piv, low, kind


def score(rs, rsl_new: bool, base_no: int, ma_up: int, rnha: bool, a_rule: bool, ud, ind_n: int) -> list[bool]:
    """加分（每項 1 分、權重相同；W2_plan 第 4 節）。順序同 SCORE_ITEMS。"""
    return [rs is not None and rs >= RS_HI, bool(rsl_new), base_no in (1, 2), ma_up >= MA200_UP, bool(rnha),
            bool(a_rule), ud is not None and ud >= UD_MIN, ind_n >= 2]


def ud_at(c: list, v: list, t: int, n: int = UD_DAYS):
    """近 n 日上漲日成交量合計 ÷ 下跌日成交量合計（比前一個有收盤的日子）；有效天數 < n × 0.8 → None；
    沒有下跌日 → 無限大。c 不前值補齊（停牌日 None）。"""
    a = t - n + 1
    if a < 0:
        return None
    up = dn = 0.0
    cnt = 0
    prev = None
    for k in range(a - 1, -1, -1):                       # 區間前最後一個收盤
        if c[k] is not None:
            prev = c[k]
            break
    for k in range(a, t + 1):
        x = c[k]
        if x is None:
            continue
        if prev is not None and v[k] is not None:
            cnt += 1
            if x > prev:
                up += v[k]
            elif x < prev:
                dn += v[k]
        prev = x
    if cnt < int(n * 0.8):
        return None
    return up / dn if dn > 0 else (float("inf") if up > 0 else None)
