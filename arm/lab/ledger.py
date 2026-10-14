"""ETF 部位帳本——籌碼雷達的核心，所有「量／成本／加入日／誰在加碼」都從這裡來。

口徑（每一條都是踩坑後的決定，改之前先讀 CLAUDE.md 籌碼雷達專節）：

1. **揭露日＝成交日**：data/etf_holdings.json 的 `date` 是「該交易日收盤後的部位」
   （2026-10-14 實證：10/14 01:08 時主動式已是 10-13、被動式仍是 10-12）。
   所以 b 日相對 a 日的股數變化，是在 b 日成交的 → 成本用 b 日均價。
2. **申贖分解**：ETF 有申購時「所有持股等比例增加」，那不是經理人看好。
   每次揭露取共同持股「股數比」的中位數當申贖倍率 f；預期股數＝前日×f，
   實際偏離預期的部分才是「真加減碼」（conv）。被動式的真加減碼＝指數機械調整。
3. **平均成本法**：加碼按當日均價（成交金額÷成交股數；缺則收盤）入帳；減碼按平均成本
   沖銷、記已實現損益。**觀測起點前就持有的部位，成本以首次觀測日均價計**（品質 B），
   觀測期內才建倉者為品質 A——頁面據此標註，不假裝知道更早的買價。
4. **公司行動**：減資／股票股利／面額變更會讓股數跳動但不是交易。判準＝股數比 r 偏離
   申贖倍率 ≥4%，且股價同時反向變動同比例（|價比×r−1|<3%），並且（≥2 檔 ETF 同向一致，
   或 |r−1|≥12% 超出漲跌幅限制）→ 股數與每股成本一起換算、不記交易。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

NEW, EXIT, ADD, CUT, HOLD = "new", "exit", "add", "cut", "hold"

SIG_REL = 0.02          # 真加減碼門檻：偏離預期股數 ≥2%
SIG_ABS_TW = 1000       # 且 ≥1 張（台股）；海外以 1 股計
FLOW_MIN_COMMON = 5     # 共同持股少於 5 檔時不估申贖倍率（f=1）
CA_REL = 0.04
CA_PX_TOL = 0.03
CA_BIG = 0.12


def is_tw(code: str) -> bool:
    return len(code) >= 4 and code[:4].isdigit() and " " not in code


@dataclass
class Pos:
    shares: float = 0.0
    cost: float = 0.0              # 總成本（台股＝新台幣；海外＝原幣）
    realized: float = 0.0
    first: str | None = None       # 本次持有的建倉日（揭露日）
    exact: bool = False            # 建倉日是否在觀測期內（True＝真實；False＝≤觀測起點）
    quality: str = "B"             # 成本品質：A 全程觀測／B 含期初假設
    streak_add: int = 0            # 連續真加碼次數（以該 ETF 揭露序計）
    streak_cut: int = 0
    last_kind: str | None = None
    last_date: str | None = None
    unpriced: int = 0              # 有交易但缺價格的次數（成本不精確）

    @property
    def avg(self) -> float | None:
        return self.cost / self.shares if self.shares > 0 and self.cost > 0 else None


@dataclass
class Event:
    date: str
    etf: str
    code: str
    kind: str
    s0: float
    s1: float
    conv: float                    # 扣除申贖後的真加減碼（股）
    raw: float                     # 原始股數變化
    price: float | None
    flow: float                    # 該 ETF 當次申贖倍率
    streak: int = 0                # 事件後的連續真加碼（正）／減碼（負）次數


@dataclass
class Ledger:
    pos: dict = field(default_factory=dict)        # (etf, code) -> Pos（含已出清者，shares=0）
    events: list = field(default_factory=list)     # 所有非 HOLD 事件＋HOLD 的 conv 也記（供日序列）
    flows: dict = field(default_factory=dict)      # (etf, date) -> 申贖倍率
    ca: list = field(default_factory=list)         # 公司行動 [(date, code, r)]
    first_obs: dict = field(default_factory=dict)  # etf -> 首次觀測日
    last_obs: dict = field(default_factory=dict)   # etf -> 最新揭露日
    snaps: dict = field(default_factory=dict)      # etf -> [(date, {code: shares})]
    daily_cost: dict = field(default_factory=dict) # date -> {(etf, code): (shares, cost)}（揭露日當下狀態）


def _flow_factor(prev: dict, cur: dict) -> float:
    rs = [cur[c] / prev[c] for c in prev if prev[c] and cur.get(c)]
    if len(rs) < FLOW_MIN_COMMON:
        return 1.0
    f = statistics.median(rs)
    return 1.0 if abs(f - 1) < 0.002 else f


def _kind(s0: float, s1: float, conv: float, code: str) -> str:
    if s0 <= 0 and s1 > 0:
        return NEW
    if s0 > 0 and s1 <= 0:
        return EXIT
    thr = SIG_ABS_TW if is_tw(code) else 1
    if s0 > 0 and abs(conv) / s0 >= SIG_REL and abs(conv) >= thr:
        return ADD if conv > 0 else CUT
    return HOLD


def build(pos_docs: list[tuple[str, dict]], price, *, skip_etfs: set[str] | None = None) -> Ledger:
    """pos_docs＝store.load("pos")；price(code, date)->(均價, 收盤) 或 None。"""
    skip_etfs = skip_etfs or set()
    L = Ledger()
    # 每檔 ETF 的揭露序列
    for d, doc in pos_docs:
        for etf, ent in (doc.get("etf") or {}).items():
            if etf in skip_etfs:
                continue
            h = {c: float(v[0]) for c, v in (ent.get("h") or {}).items()
                 if v and v[0] is not None and float(v[0]) > 0}
            if h:
                L.snaps.setdefault(etf, []).append((d, h))
    for etf in L.snaps:
        L.snaps[etf].sort()

    # 第一遍：收集各 (code, date) 的股數比 r，供公司行動跨 ETF 一致性判斷
    ratios: dict[tuple[str, str], list[float]] = {}
    for etf, seq in L.snaps.items():
        for (a, ha), (b, hb) in zip(seq, seq[1:]):
            f = _flow_factor(ha, hb)
            for c in ha:
                if c in hb and ha[c] > 0:
                    r = hb[c] / (ha[c] * f)
                    if abs(r - 1) >= CA_REL:
                        ratios.setdefault((c, b), []).append(r)

    def _is_ca(c: str, a: str, b: str, r: float) -> bool:
        if not is_tw(c):
            return False
        pa, pb = price(c, a), price(c, b)
        if not pa or not pb or not pa[1] or not pb[1]:
            return False
        if abs(pb[1] / pa[1] * r - 1) >= CA_PX_TOL:
            return False
        peers = ratios.get((c, b)) or []
        agree = sum(1 for x in peers if abs(x - r) < 0.01)
        return agree >= 2 or abs(r - 1) >= CA_BIG

    # 第二遍：逐 ETF 記帳
    for etf, seq in L.snaps.items():
        d0, h0 = seq[0]
        L.first_obs[etf], L.last_obs[etf] = d0, seq[-1][0]
        for c, s in h0.items():
            p = price(c, d0)
            px = (p[0] or p[1]) if p else None
            P = Pos(shares=s, cost=(s * px) if px else 0.0, first=d0, exact=False,
                    quality="B", last_date=d0, unpriced=0 if px else 1)
            L.pos[(etf, c)] = P
        L.daily_cost.setdefault(d0, {}).update(
            {(etf, c): (L.pos[(etf, c)].shares, L.pos[(etf, c)].cost) for c in h0})
        for (a, ha), (b, hb) in zip(seq, seq[1:]):
            f = _flow_factor(ha, hb)
            L.flows[(etf, b)] = f
            for c in set(ha) | set(hb):
                s0, s1 = ha.get(c, 0.0), hb.get(c, 0.0)
                P = L.pos.get((etf, c))
                if P is None:
                    P = L.pos[(etf, c)] = Pos()
                if s0 > 0 and s1 > 0:
                    r = s1 / (s0 * f)
                    if abs(r - 1) >= CA_REL and _is_ca(c, a, b, r):
                        L.ca.append((b, c, round(r, 4)))
                        P.shares *= r                        # 股數換算、總成本不變
                        s0 = s0 * r
                expected = s0 * f
                conv = s1 - expected
                raw = s1 - s0
                kind = _kind(s0, s1, conv, c)
                p = price(c, b)
                px = (p[0] or p[1]) if p else None
                # —— 記帳
                if raw > 0:
                    if px:
                        P.cost += raw * px
                    else:
                        P.unpriced += 1
                    P.shares += raw
                elif raw < 0 and P.shares > 0:
                    sold = min(-raw, P.shares)
                    avg = P.cost / P.shares if P.shares else 0.0
                    if px and avg:
                        P.realized += sold * (px - avg)
                    P.cost -= sold * avg
                    P.shares -= sold
                if kind == NEW:
                    P.first, P.exact, P.quality = b, True, "A"
                    P.shares, P.cost = s1, (s1 * px if px else 0.0)
                    P.streak_add, P.streak_cut = 1, 0
                elif kind == EXIT:
                    P.shares, P.cost = 0.0, 0.0
                    P.streak_add, P.streak_cut = 0, 0
                elif kind == ADD:
                    P.streak_add += 1
                    P.streak_cut = 0
                elif kind == CUT:
                    P.streak_cut += 1
                    P.streak_add = 0
                else:
                    P.streak_add = P.streak_cut = 0
                if kind != HOLD:
                    P.last_kind, P.last_date = kind, b
                if kind != HOLD or abs(conv) > 0:
                    L.events.append(Event(b, etf, c, kind, s0, s1, conv, raw, px, f,
                                          P.streak_add if P.streak_add else -P.streak_cut))
            L.daily_cost.setdefault(b, {}).update(
                {(etf, c): (L.pos[(etf, c)].shares, L.pos[(etf, c)].cost)
                 for c in set(ha) | set(hb) if (etf, c) in L.pos})
    return L
