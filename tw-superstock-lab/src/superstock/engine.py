"""回測引擎（SPEC §4）：組合模式（定期換股）與交易模式（逐筆、路徑相依），共用同一個逐日撮合。

價格單位
  · 比較與損益一律用還原價（adj_*，向後還原、含息）；訊號給的突破價、停損價也是還原價。
  · 張數、成交值、流動性、滑價級距用原始價（還原價 ÷ adj_factor）。
  · 部位以「還原股數」k = 股數 ÷ 進場日還原因子 記帳：市值 = k × 還原收盤，配息等於再投入同一檔。
時間
  · 訊號在 t 日收盤後算出 → t+1 開盤市價或盤中觸價成交；決策只用 t 日收盤（含）以前的資料。
  · 部位大小以前一日收盤權益計。
成交規則
  · 開盤市價：t+1 一價到底漲停（locked_up）買不到；一價到底跌停（locked_down）賣不掉、延到下一個交易日開盤。
  · 突破進場：t+1 最高 ≥ 突破價才成交，成交價 max(開盤, 突破價)；漲停鎖死不成交。
  · 停損：最低 ≤ 停損價 → 成交價 min(開盤, 停損價)（當天突破進場的用停損價）；跌停鎖死延到下一日開盤。
  · 停損與停利同一天都碰到 → 當作先停損。
  · 下市：最後一筆資料之後的第一個交易日，以最後收盤（扣 delist_haircut）出清。
成本（Costs）
  · 手續費 0.1425% × 折數（預設 0.6）雙邊、最低 20 元；證交稅 0.3%（賣）；
  · 滑價（每邊）依前一日 20 日均成交值：≥10 億 5bp、1–10 億 15bp、1,000 萬–1 億 30bp、<1,000 萬 60bp；
    處置期間另加 50bp。scale 是整體成本倍數（P5 的「成本 ×2」）。
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

NAN = float("nan")


def _ok(x: float) -> bool:
    return x == x  # 不是 NaN


# ---------------------------------------------------------------------------------------------- 設定
@dataclass
class Costs:
    commission: float = 0.001425
    discount: float = 0.6
    min_fee: float = 20.0
    sell_tax: float = 0.003
    slip_tiers: tuple = ((1e9, 0.0005), (1e8, 0.0015), (1e7, 0.0030), (0.0, 0.0060))
    disposition_extra: float = 0.0050
    scale: float = 1.0

    def slippage(self, avg_value: float, disposed: bool = False) -> float:
        s = self.slip_tiers[-1][1]
        if _ok(avg_value):
            for floor, bp in self.slip_tiers:
                if avg_value >= floor:
                    s = bp
                    break
        if disposed:
            s += self.disposition_extra
        return s * self.scale

    def fee(self, value: float) -> float:
        if value <= 0:
            return 0.0
        return max(self.min_fee, value * self.commission * self.discount) * self.scale

    def tax(self, value: float) -> float:
        return max(0.0, value) * self.sell_tax * self.scale

    @classmethod
    def zero(cls) -> "Costs":
        return cls(commission=0.0, min_fee=0.0, sell_tax=0.0, slip_tiers=((0.0, 0.0),), disposition_extra=0.0)


@dataclass
class EngineConfig:
    capital: float = 10_000_000.0
    lot: int = 1000                  # 0 = 可買零股到小數（只用在指數複製）
    risk_pct: float = 0.01           # 交易模式：每筆風險占權益
    max_weight: float = 0.20         # 單一個股上限
    max_adv: float = 0.05            # 不超過 20 日均量的比例
    max_positions: int = 20
    market_filter: bool = True       # 大盤濾網關閉時不進新倉（出場照做）
    block_disposition: bool = True   # 處置期間不進新倉
    min_hold_days: int = 0
    entry_valid_days: int = 1        # 進場單有效幾個交易日
    breakeven_r: float | None = None  # 收盤浮盈達 N 倍初始風險後，停損移到成本
    max_hold_days: int | None = None
    liquidate_at_end: bool = True
    delist_haircut: float = 0.0
    costs: Costs = field(default_factory=Costs)


# ---------------------------------------------------------------------------------------------- 市場資料
class Market:
    """逐日面板（日期 × 股票）。價格欄位為還原價；factor = 還原價 ÷ 原始價。"""

    def __init__(self, dates, stocks, open, high, low, close, factor=None, value=None, volume=None,
                 locked_up=None, locked_down=None, disposed=None,
                 index_level: pd.Series | None = None, index_tr: pd.Series | None = None):
        self.dates = pd.DatetimeIndex(dates)
        self.stocks = [str(s) for s in stocks]
        self.col = {s: j for j, s in enumerate(self.stocks)}
        self.o, self.h, self.l, self.c = (np.asarray(x, dtype=float) for x in (open, high, low, close))
        shape = self.c.shape
        self.f = np.ones(shape) if factor is None else np.asarray(factor, dtype=float)
        self.val = np.full(shape, np.nan) if value is None else np.asarray(value, dtype=float)
        self.vol = np.full(shape, np.nan) if volume is None else np.asarray(volume, dtype=float)
        self.lu = np.zeros(shape, bool) if locked_up is None else np.asarray(locked_up, dtype=bool)
        self.ld = np.zeros(shape, bool) if locked_down is None else np.asarray(locked_down, dtype=bool)
        self.dp = np.zeros(shape, bool) if disposed is None else np.asarray(disposed, dtype=bool)
        # 20 日均成交值／均量（含當日；成交時用前一日的數字）
        self.av = pd.DataFrame(self.val).rolling(20, min_periods=1).mean().to_numpy(dtype=float)
        self.avv = pd.DataFrame(self.vol).rolling(20, min_periods=1).mean().to_numpy(dtype=float)
        self.c_ff = pd.DataFrame(self.c).ffill().to_numpy(dtype=float)  # 停牌日估值用
        has = ~np.isnan(self.c)
        n = shape[0]
        self.last = np.where(has.any(axis=0), n - 1 - np.argmax(has[::-1], axis=0), -1)
        self.index_level = None if index_level is None else index_level.reindex(self.dates).ffill()
        self.index_tr = None if index_tr is None else index_tr.reindex(self.dates).ffill()

    @property
    def n(self) -> int:
        return len(self.dates)

    def i_of(self, date) -> int:
        return int(self.dates.searchsorted(pd.Timestamp(date)))

    def panel(self, arr: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(arr, index=self.dates, columns=self.stocks)

    @classmethod
    def from_frames(cls, prices: pd.DataFrame, index: pd.DataFrame | None = None,
                    disposition: pd.DataFrame | None = None, start=None, end=None) -> "Market":
        """prices＝build 產生的長表（date, stock_id, adj_open…, adj_factor, value, volume, locked_up/down）。"""
        p = prices.copy()
        p["date"] = pd.to_datetime(p["date"])
        p["stock_id"] = p["stock_id"].astype(str)
        if start is not None:
            p = p[p["date"] >= pd.Timestamp(start)]
        if end is not None:
            p = p[p["date"] <= pd.Timestamp(end)]
        close = p.pivot(index="date", columns="stock_id", values="adj_close").sort_index()
        dates, stocks = close.index, list(close.columns)

        def wide(col: str, fill=np.nan, dtype=float) -> np.ndarray:
            if col not in p.columns:
                return np.full((len(dates), len(stocks)), fill, dtype=dtype)
            w = p.pivot(index="date", columns="stock_id", values=col).reindex(index=dates, columns=stocks)
            if dtype is bool:
                return w.fillna(False).to_numpy(dtype=bool)
            return w.to_numpy(dtype=float)

        disposed = None
        if disposition is not None and not disposition.empty:
            disposed = np.zeros((len(dates), len(stocks)), dtype=bool)
            col = {s: j for j, s in enumerate(stocks)}
            d = disposition.copy()
            d["stock_id"] = d["stock_id"].astype(str)
            for r in d.itertuples(index=False):
                j = col.get(r.stock_id)
                a, b = pd.to_datetime(r.period_start, errors="coerce"), pd.to_datetime(r.period_end, errors="coerce")
                if j is None or pd.isna(a) or pd.isna(b):
                    continue
                disposed[dates.searchsorted(a):dates.searchsorted(b, side="right"), j] = True
        level = tr = None
        if index is not None and not index.empty:
            ix = index.copy()
            ix["date"] = pd.to_datetime(ix["date"])
            taiex = ix[ix["index_id"].astype(str) == "TAIEX"].set_index("date").sort_index()
            if "level" in taiex:
                level = pd.to_numeric(taiex["level"], errors="coerce").dropna()
            if "total_return" in taiex:
                tr = pd.to_numeric(taiex["total_return"], errors="coerce").dropna()
        return cls(dates, stocks, wide("adj_open"), wide("adj_high"), wide("adj_low"), close.to_numpy(float),
                   factor=wide("adj_factor", 1.0), value=wide("value"), volume=wide("volume"),
                   locked_up=wide("locked_up", False, bool), locked_down=wide("locked_down", False, bool),
                   disposed=disposed, index_level=level, index_tr=tr)

    @classmethod
    def load(cls, processed_dir: str | Path, start=None, end=None) -> "Market":
        d = Path(processed_dir)
        prices = pd.read_parquet(d / "prices.parquet")
        index = pd.read_parquet(d / "index.parquet") if (d / "index.parquet").exists() else None
        disp = pd.read_parquet(d / "disposition.parquet") if (d / "disposition.parquet").exists() else None
        return cls.from_frames(prices, index, disp, start, end)


def market_filter(m: Market, ma: int = 200, window: int = 252, nhnl_days: int = 1) -> np.ndarray:
    """大盤濾網（每日 bool）：加權指數收盤 > 200 日均線，且全體股票「52 週新高家數 − 新低家數」> 0。
    新高／新低以還原收盤對自身近 252 日收盤的最高／最低（含當日）判斷；歷史不足 80% 窗長的股票不計。"""
    n = m.n
    if m.index_level is None:
        above = np.ones(n, dtype=bool)
    else:
        lv = m.index_level
        above = (lv > lv.rolling(ma, min_periods=ma).mean()).to_numpy()
    c = pd.DataFrame(m.c)
    mp = max(2, int(window * 0.8))
    hi = c.rolling(window, min_periods=mp).max()
    lo = c.rolling(window, min_periods=mp).min()
    nh = (c >= hi).sum(axis=1)
    nl = (c <= lo).sum(axis=1)
    nhnl = (nh - nl).rolling(nhnl_days, min_periods=1).sum()
    return above & (nhnl > 0).to_numpy()


# ---------------------------------------------------------------------------------------------- 撮合
@dataclass
class Order:
    s: int
    kind: str = "open"           # open = 開盤市價；stop = 盤中觸價（突破 pivot）
    pivot: float = NAN
    stop: float = NAN
    stop_pct: float = NAN        # 以成交價往下 N% 當停損（沒給 stop 時）
    target: float = NAN
    weight: float = NAN          # 組合模式的目標權重；NaN = 用風險比例算張數
    score: float = 0.0
    signal_i: int = 0
    until_i: int = 0
    tag: str = ""


@dataclass
class Position:
    s: int
    k: float                     # 還原股數
    shares: float
    entry_i: int
    signal_i: int
    entry_px: float              # 還原價成交價（含滑價）
    cost_in: float               # 買進總支出（元，含手續費）
    how: str = "open"
    stop: float = NAN
    target: float = NAN
    r0: float = NAN              # 初始每股風險（還原價）
    tag: str = ""
    exit_pending: str | None = None


class Simulator:
    def __init__(self, m: Market, cfg: EngineConfig, exit_flags: np.ndarray | None = None,
                 mf: np.ndarray | None = None):
        self.m, self.cfg, self.costs = m, cfg, cfg.costs
        self.exit_flags = exit_flags
        self.mf = mf if mf is not None else np.ones(m.n, dtype=bool)
        self.cash = float(cfg.capital)
        self.pos: dict[int, Position] = {}
        self.orders: list[Order] = []
        self.trades: list[dict] = []
        self.entries: list[tuple[int, int]] = []   # (signal_i, s)：給標籤命中率用
        self.turnover = 0.0
        self.eq_prev = float(cfg.capital)

    # ---- 共用 ----
    def _tradable(self, i: int, s: int) -> bool:
        return _ok(self.m.o[i, s]) and _ok(self.m.c[i, s])

    def _prev(self, arr: np.ndarray, i: int, s: int) -> float:
        return float(arr[i - 1, s]) if i > 0 else NAN

    def value(self, i: int) -> float:
        m = self.m
        return sum(p.k * (m.c[i, p.s] if _ok(m.c[i, p.s]) else m.c_ff[i, p.s]) for p in self.pos.values())

    def _lots(self, shares: float) -> float:
        lot = self.cfg.lot
        if lot <= 0:
            return max(0.0, shares)
        return float(math.floor(shares / lot) * lot)

    def _buy(self, i: int, o: Order, px_adj: float, how: str) -> bool:
        m, cfg, costs = self.m, self.cfg, self.costs
        s = o.s
        f = float(m.f[i, s])
        if not (f > 0 and px_adj > 0):
            return False
        slip = costs.slippage(self._prev(m.av, i, s), bool(m.dp[i, s]))
        px = px_adj * (1 + slip)
        raw = px / f
        equity = self.eq_prev
        stop = o.stop if _ok(o.stop) else (px * (1 - o.stop_pct) if _ok(o.stop_pct) else NAN)
        if _ok(o.weight):
            target_value = o.weight * equity
        else:
            if not (_ok(stop) and px > stop):
                return False
            target_value = cfg.risk_pct * equity / ((px - stop) / f) * raw
        target_value = min(target_value, cfg.max_weight * equity)
        shares = target_value / raw
        adv = self._prev(m.avv, i, s)
        if _ok(adv) and cfg.max_adv < math.inf:
            shares = min(shares, cfg.max_adv * adv)
        # 現金上限（含手續費；最低手續費時逐張往下減）
        rate = costs.commission * costs.discount * costs.scale
        shares = self._lots(min(shares, self.cash / (raw * (1 + rate))))
        while shares > 0 and shares * raw + costs.fee(shares * raw) > self.cash + 1e-6:
            shares = self._lots(shares - cfg.lot) if cfg.lot > 0 else shares * 0.999
        if shares <= 0:
            return False
        value = shares * raw
        fee = costs.fee(value)
        self.cash -= value + fee
        self.turnover += value
        self.pos[s] = Position(s, shares / f, shares, i, o.signal_i, px, value + fee, how, stop, o.target,
                               (px - stop) if _ok(stop) else NAN, o.tag)
        self.entries.append((o.signal_i, s))
        return True

    def _sell(self, i: int, p: Position, px_adj: float, reason: str, slip: bool = True) -> None:
        m, costs = self.m, self.costs
        s = p.s
        sl = costs.slippage(self._prev(m.av, i, s), bool(m.dp[i, s])) if slip else 0.0
        px = px_adj * (1 - sl)
        gross = p.k * px
        fee, tax = costs.fee(gross), costs.tax(gross)
        net = gross - fee - tax
        self.cash += net
        self.turnover += gross
        self.trades.append({
            "stock_id": m.stocks[s], "tag": p.tag, "signal_date": m.dates[p.signal_i], "entry_date": m.dates[p.entry_i],
            "exit_date": m.dates[min(i, m.n - 1)], "entry_px": p.entry_px, "exit_px": px, "shares": p.shares,
            "cost_in": p.cost_in, "proceeds": net, "pnl": net - p.cost_in, "ret": net / p.cost_in - 1.0,
            "gross_ret": px / p.entry_px - 1.0, "r_mult": (px - p.entry_px) / p.r0 if p.r0 > 0 else NAN,
            "hold_days": i - p.entry_i, "how": p.how, "reason": reason,
        })
        del self.pos[s]

    # ---- 一天 ----
    def step(self, i: int, decide: Callable[[int, "Simulator"], list[Order]]) -> float:
        m, cfg = self.m, self.cfg
        # 0) 下市：上一個交易日已是最後一筆資料
        for s, p in list(self.pos.items()):
            if m.last[s] < i:
                self._sell(i, p, m.c[m.last[s], s] * (1 - cfg.delist_haircut), "delisted", slip=False)
        # 1) 開盤：待出場（跌停鎖死賣不掉，延到明天）
        for s, p in list(self.pos.items()):
            if p.exit_pending and i - p.entry_i >= cfg.min_hold_days and self._tradable(i, s) and not m.ld[i, s]:
                self._sell(i, p, m.o[i, s], p.exit_pending)
        # 2) 開盤市價進場、3) 盤中突破進場（依分數高到低）
        keep: list[Order] = []
        for kind in ("open", "stop"):
            for o in sorted((o for o in self.orders if o.kind == kind), key=lambda o: -o.score):
                if o.s in self.pos:
                    continue
                filled = False
                if len(self.pos) < cfg.max_positions and self._tradable(i, o.s) and not m.lu[i, o.s]:
                    if kind == "open":
                        filled = self._buy(i, o, m.o[i, o.s], "open")
                    elif m.h[i, o.s] >= o.pivot:
                        filled = self._buy(i, o, max(m.o[i, o.s], o.pivot), "stop")
                if not filled and i < o.until_i:
                    keep.append(o)
        self.orders = keep
        # 4) 盤中停損／停利（同日兩者都碰到＝先停損）
        for s, p in list(self.pos.items()):
            if i - p.entry_i < cfg.min_hold_days or not self._tradable(i, s):
                continue
            op, lo, hi = m.o[i, s], m.l[i, s], m.h[i, s]
            if _ok(p.stop) and lo <= p.stop:
                if m.ld[i, s]:
                    p.exit_pending = "stop"
                    continue
                # 當天才進場：突破單是先買後跌破 → 停損價；開盤買在停損之上 → 停損價；開盤就在停損之下 → 開盤價
                same_day = p.entry_i == i and (p.how == "stop" or op > p.stop)
                self._sell(i, p, p.stop if same_day else min(op, p.stop), "stop")
            elif _ok(p.target) and hi >= p.target:
                self._sell(i, p, p.target if p.entry_i == i else max(op, p.target), "target")
        # 5) 收盤：移動停損、出場條件
        for s, p in self.pos.items():
            c = m.c[i, s]
            if not _ok(c):
                continue
            if cfg.breakeven_r and p.r0 > 0 and c >= p.entry_px + cfg.breakeven_r * p.r0:
                p.stop = max(p.stop, p.entry_px) if _ok(p.stop) else p.entry_px
            if self.exit_flags is not None and self.exit_flags[i, s]:
                p.exit_pending = p.exit_pending or "rule"
            if cfg.max_hold_days and i - p.entry_i >= cfg.max_hold_days:
                p.exit_pending = p.exit_pending or "time"
        # 6) 收盤後決策：明天的單
        if i + 1 < m.n:
            pending = {o.s for o in self.orders}
            for o in decide(i, self):
                if o.s in self.pos or o.s in pending:
                    continue
                if cfg.block_disposition and m.dp[i + 1, o.s]:
                    continue
                o.signal_i = i
                o.until_i = i + max(1, cfg.entry_valid_days)
                self.orders.append(o)
                pending.add(o.s)
        eq = self.cash + self.value(i)
        self.eq_prev = eq
        return eq

    def run(self, decide: Callable[[int, "Simulator"], list[Order]], start=None, end=None) -> "Result":
        m = self.m
        i0 = m.i_of(start) if start is not None else 0
        i1 = (m.dates.searchsorted(pd.Timestamp(end), side="right") - 1) if end is not None else m.n - 1
        eq, inv = [], []
        for i in range(i0, i1 + 1):
            e = self.step(i, decide)
            if i == i1 and self.cfg.liquidate_at_end:
                for s, p in list(self.pos.items()):
                    px = m.c[i, s] if _ok(m.c[i, s]) else m.c_ff[i, s]
                    self._sell(i, p, px, "end")
                e = self.cash
            eq.append(e)
            inv.append(self.value(i) / e if e > 0 else 0.0)
        idx = m.dates[i0:i1 + 1]
        trades = pd.DataFrame(self.trades)
        return Result(pd.Series(eq, index=idx, name="equity"), trades, pd.Series(inv, index=idx, name="exposure"),
                      self.turnover, [(m.dates[a], m.stocks[s]) for a, s in self.entries])


# ---------------------------------------------------------------------------------------------- 兩種模式
def _flags(m: Market, frame: pd.DataFrame | None) -> np.ndarray | None:
    if frame is None:
        return None
    f = frame.reindex(index=m.dates, columns=m.stocks)
    return f.fillna(False).to_numpy(dtype=bool)


def run_portfolio(m: Market, scores: pd.DataFrame, cfg: EngineConfig | None = None, top_n: int = 20,
                  exit_flags: pd.DataFrame | None = None, start=None, end=None) -> "Result":
    """組合模式：scores（訊號日 × 股票，越大越好；NaN／False＝不選）每一列是一次換股。
    取前 top_n 等權（以前一日收盤權益 ÷ top_n），t+1 開盤成交，持有到下一次換股；不在名單內的賣出。
    exit_flags（日期 × 股票 bool）＝收盤出場條件（例如跌破 20 日線），隔日開盤賣、到下次換股前不補。"""
    cfg = cfg or EngineConfig()
    cfg = EngineConfig(**{**asdict(cfg), "costs": cfg.costs, "max_positions": top_n})
    sc = scores.where(scores) if all(dt == bool for dt in scores.dtypes) else scores   # bool：False＝不選
    sc = sc.astype(float).reindex(columns=m.stocks)
    days = set(m.dates)
    rows = {m.i_of(d): sc.loc[d].to_numpy(dtype=float) for d in sc.index if pd.Timestamp(d) in days}
    mf = market_filter(m) if cfg.market_filter else np.ones(m.n, dtype=bool)
    flags = _flags(m, exit_flags)
    order_ix = np.arange(len(m.stocks))

    def decide(i: int, sim: Simulator) -> list[Order]:
        row = rows.get(i)
        if row is None:
            return []
        ok = ~np.isnan(row) & (row > -np.inf) & ~np.isnan(m.c[i])
        if flags is not None:
            ok &= ~flags[i]
        cand = np.flatnonzero(ok)
        cand = cand[np.lexsort((order_ix[cand], -row[cand]))][:top_n]
        target = set(cand.tolist())
        for s, p in sim.pos.items():
            if s not in target:
                p.exit_pending = p.exit_pending or "rebalance"
            elif p.exit_pending == "rebalance":
                p.exit_pending = None
        sim.orders = [o for o in sim.orders if o.s in target]
        if not mf[i]:
            return []
        return [Order(s, "open", weight=1.0 / top_n, score=float(row[s])) for s in cand if s not in sim.pos]

    sim = Simulator(m, cfg, exit_flags=flags, mf=mf)
    return sim.run(decide, start, end)


def run_trades(m: Market, signals: pd.DataFrame, cfg: EngineConfig | None = None,
               exit_flags: pd.DataFrame | None = None, start=None, end=None) -> "Result":
    """交易模式：signals 欄位 date, stock_id, entry（open|stop）, pivot, stop, stop_pct, target, score, tag。
    訊號日收盤後下單，隔日成交；部位大小＝風險比例（risk_pct × 權益 ÷ 每股風險），再受各上限限制。"""
    cfg = cfg or EngineConfig()
    mf = market_filter(m) if cfg.market_filter else np.ones(m.n, dtype=bool)
    flags = _flags(m, exit_flags)
    sig = signals.copy()
    sig["date"] = pd.to_datetime(sig["date"])
    sig["stock_id"] = sig["stock_id"].astype(str)
    by_day: dict[int, list[Order]] = {}
    for r in sig.to_dict("records"):
        s = m.col.get(r["stock_id"])
        if s is None:
            continue
        i = m.i_of(r["date"])
        if i >= m.n or m.dates[i] != r["date"]:
            continue

        def g(k):
            v = r.get(k, NAN)
            return float(v) if v is not None and v == v else NAN
        by_day.setdefault(i, []).append(Order(
            s, str(r.get("entry") or "open"), pivot=g("pivot"), stop=g("stop"), stop_pct=g("stop_pct"),
            target=g("target"), score=g("score") if _ok(g("score")) else 0.0, tag=str(r.get("tag") or "")))

    def decide(i: int, sim: Simulator) -> list[Order]:
        if not mf[i]:
            return []
        return [Order(**{**o.__dict__}) for o in by_day.get(i, [])]

    sim = Simulator(m, cfg, exit_flags=flags, mf=mf)
    return sim.run(decide, start, end)


# ---------------------------------------------------------------------------------------------- 結果與指標
@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame
    exposure: pd.Series
    turnover_value: float
    entries: list

    def metrics(self, bench: pd.Series | None = None, labels: pd.DataFrame | None = None) -> dict:
        out = metrics(self.equity, self.trades, bench, self.exposure, self.turnover_value)
        if labels is not None:
            out.update(label_hits(pd.DataFrame(self.entries, columns=["date", "stock_id"]), labels))
        return out


def _cagr(eq: pd.Series) -> float:
    eq = eq.dropna()
    if len(eq) < 2 or eq.iloc[0] <= 0:
        return NAN
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    return (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if years > 0 else NAN


def max_drawdown(eq: pd.Series) -> float:
    eq = eq.dropna()
    return float((eq / eq.cummax() - 1).min()) if len(eq) else NAN


def metrics(equity: pd.Series, trades: pd.DataFrame | None = None, bench: pd.Series | None = None,
            exposure: pd.Series | None = None, turnover_value: float = 0.0) -> dict:
    eq = equity.dropna()
    r = eq.pct_change().dropna()
    years = (eq.index[-1] - eq.index[0]).days / 365.25 if len(eq) > 1 else 0.0
    ppy = len(r) / years if years > 0 else 252.0
    sd = float(r.std(ddof=1)) if len(r) > 1 else NAN
    down = float(np.sqrt(np.mean(np.minimum(r.to_numpy(), 0.0) ** 2))) if len(r) else NAN
    cagr = _cagr(eq)
    mdd = max_drawdown(eq)
    out = {
        "start": str(eq.index[0].date()) if len(eq) else None, "end": str(eq.index[-1].date()) if len(eq) else None,
        "years": round(years, 3), "cagr": cagr, "vol": sd * math.sqrt(ppy) if sd == sd else NAN,
        "sharpe": float(r.mean()) / sd * math.sqrt(ppy) if sd and sd == sd and sd > 0 else NAN,
        "sortino": float(r.mean()) * ppy / (down * math.sqrt(ppy)) if down and down > 0 else NAN,
        "maxdd": mdd, "calmar": cagr / abs(mdd) if mdd and mdd < 0 and cagr == cagr else NAN,
        "n_obs": int(len(r)), "skew": float(r.skew()) if len(r) > 2 else NAN,
        "kurt": float(r.kurt()) + 3.0 if len(r) > 3 else NAN,   # 一般峰態（常態＝3），DSR 用
        "exposure": float(exposure.mean()) if exposure is not None and len(exposure) else NAN,
        "turnover": (turnover_value / 2.0) / float(eq.mean()) / years if years > 0 and len(eq) else NAN,
    }
    t = trades if trades is not None else pd.DataFrame()
    if len(t):
        wins, losses = t[t["pnl"] > 0], t[t["pnl"] <= 0]
        out.update({
            "trades": int(len(t)), "win_rate": float(len(wins) / len(t)),
            "payoff": float(wins["ret"].mean() / abs(losses["ret"].mean()))
            if len(wins) and len(losses) and losses["ret"].mean() < 0 else NAN,
            "expectancy": float(t["ret"].mean()), "avg_hold": float(t["hold_days"].mean()),
        })
    else:
        out.update({"trades": 0, "win_rate": NAN, "payoff": NAN, "expectancy": NAN, "avg_hold": NAN})
    if bench is not None:
        b = bench.reindex(eq.index).ffill().dropna()
        if len(b) > 1:
            out["bench_cagr"] = _cagr(b)
            out["bench_maxdd"] = max_drawdown(b)
            out["excess_cagr"] = cagr - out["bench_cagr"]
    return out


def label_hits(entries: pd.DataFrame, labels: pd.DataFrame, cols: tuple[str, ...] = ("y_A", "y_B")) -> dict:
    """進場訊號（訊號日, 股票）對標籤的精確率、召回率、提升倍數（lift＝精確率 ÷ 基準率）。"""
    out = {}
    if entries.empty or labels is None or labels.empty:
        return out
    e = entries.copy()
    e["date"] = pd.to_datetime(e["date"])
    e["stock_id"] = e["stock_id"].astype(str)
    lab = labels.copy()
    lab["date"] = pd.to_datetime(lab["date"])
    lab["stock_id"] = lab["stock_id"].astype(str)
    lo, hi = e["date"].min(), e["date"].max()
    lab = lab[(lab["date"] >= lo) & (lab["date"] <= hi)]
    for col in cols:
        if col not in lab.columns:
            continue
        y = lab[["date", "stock_id", col]].dropna()
        base = float(y[col].mean()) if len(y) else NAN
        hit = e.merge(y, on=["date", "stock_id"], how="inner")
        prec = float(hit[col].mean()) if len(hit) else NAN
        out[f"{col}_precision"] = prec
        out[f"{col}_recall"] = float(hit[col].sum() / y[col].sum()) if len(y) and y[col].sum() else NAN
        out[f"{col}_lift"] = prec / base if base and base == base and base > 0 and prec == prec else NAN
        out[f"{col}_base"] = base
    return out


# ---------------------------------------------------------------------------------------------- 試驗紀錄
TRIAL_COLS = ["ts", "name", "mode", "start", "end", "cagr", "vol", "sharpe", "sortino", "maxdd", "calmar",
              "trades", "win_rate", "payoff", "expectancy", "avg_hold", "exposure", "turnover",
              "bench_cagr", "bench_maxdd", "excess_cagr", "n_obs", "skew", "kurt", "params"]


def log_trial(path: str | Path, name: str, mode: str, params: dict, m: dict, ts: str | None = None) -> None:
    """每次回測的設定與成績附加到 reports/trials.csv（DSR 要用全部試驗數）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {k: m.get(k, "") for k in TRIAL_COLS}
    row.update({"ts": ts or pd.Timestamp.now(tz="Asia/Taipei").strftime("%Y-%m-%d %H:%M:%S"), "name": name,
                "mode": mode, "params": json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)})
    for k, v in row.items():
        if isinstance(v, float):
            row[k] = "" if v != v else round(v, 6)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRIAL_COLS)
        if new:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------------------------------------- 大盤複製（關卡）
def replicate_index(level: pd.Series, capital: float = 10_000_000.0, costs: Costs | None = None) -> pd.DataFrame:
    """把報酬指數當成一檔股票，用引擎買進持有（預設零成本、可買小數股），逐年報酬與指數本身比較（GATE P2）。"""
    lv = level.dropna().sort_index()
    dates = lv.index
    arr = lv.to_numpy(dtype=float)[:, None]
    m = Market(dates, ["TR"], arr, arr, arr, arr, value=np.full_like(arr, 1e15), volume=np.full_like(arr, 1e15))
    cfg = EngineConfig(capital=capital, lot=0, max_weight=1.0, max_adv=math.inf, market_filter=False,
                       block_disposition=False, liquidate_at_end=False, costs=costs or Costs.zero())
    scores = pd.DataFrame({"TR": [1.0]}, index=dates[:1])
    res = run_portfolio(m, scores, cfg, top_n=1)
    eq, lv = res.equity.iloc[1:], lv.iloc[1:]          # 第一天收盤下單、第二天開盤（＝當天指數）買進
    rows = []
    for y in sorted(set(eq.index.year)):
        e, b = eq[eq.index.year == y], lv[lv.index.year == y]
        pe, pb = eq[eq.index.year < y], lv[lv.index.year < y]
        e0 = pe.iloc[-1] if len(pe) else e.iloc[0]
        b0 = pb.iloc[-1] if len(pb) else b.iloc[0]
        rows.append({"year": y, "engine": e.iloc[-1] / e0 - 1, "index": b.iloc[-1] / b0 - 1})
    out = pd.DataFrame(rows)
    out["diff"] = out["engine"] - out["index"]
    return out
