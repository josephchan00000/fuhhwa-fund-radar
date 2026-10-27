"""台指期早盤策略的模擬引擎（docs/lab_fut_plan.md 第 4 節；規格在 arm/lab/futspec.py）。

自己寫的，不跑資料包的程式；只用逐筆成交（秒、價、量，期交所檔案順序）。一天最多一筆：

  進場：決定時間之後的第一筆成交，多單 ＋滑價、空單 −滑價。
  停損：進場價反向 stop 點；移動停損用 1 分 K——多單候選＝上次移動以來「已收完」的 1 分 K 最低點 − buf，
        價格 ≥ 候選 ＋ clear 而且候選比現在的停損高才移（空單相反）；成交價碰到或穿過停損就用那一筆的價格 −（＋）滑價出場。
  停利：進場價順向 target 點的限價單；要有一筆成交「穿過」目標（多單 ≥ 目標 ＋ 1）才算成交在目標價（排隊不一定輪到）。
  收盤：exit_s（13:44:00）以後第一筆成交還沒出場就用那一筆 −（＋）滑價出場。
  同一秒的先後照檔案順序；一筆成交不可能同時碰到停損和停利，所以沒有「哪個先」的問題。

成本另算（cost_pts(價格) 每邊點數），淨點數＝毛點數 − 兩邊成本。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Trade:
    side: str                      # "long" / "short"
    t_in: int                      # 進場那一筆的秒數
    px_in: float                   # 含滑價
    stop0: float
    target: float | None
    t_out: int | None = None
    px_out: float | None = None
    why: str | None = None         # stop / trail / target / close / eod
    gross: float | None = None
    net: float | None = None
    mfe: float = 0.0               # 進場後最有利（點，不含滑價）
    mae: float = 0.0               # 進場後最不利（點，負的）
    moves: list = field(default_factory=list)   # [(秒, 新停損)]

    def as_dict(self) -> dict:
        return asdict(self)


def simulate(ticks: list[tuple[int, int, int, bool]], side: str, decide_s: int, *,
             stop: float, buf: float, clear: float, target: float | None, slip: float,
             exit_s: int, cost_side) -> Trade | None:
    """ticks＝當天這個契約的逐筆（秒、價、量、是否開盤集合競價），依檔案順序。回傳 None＝決定時間之後沒有成交。"""
    sgn = 1 if side == "long" else -1
    i0 = next((i for i, x in enumerate(ticks) if x[0] > decide_s), None)
    if i0 is None:
        return None
    s_in, p_raw = ticks[i0][0], ticks[i0][1]
    px_in = p_raw + sgn * slip
    st = px_in - sgn * stop
    tg = None if target is None else px_in + sgn * target
    tr = Trade(side, s_in, px_in, st, tg)
    bar_m = s_in // 60                       # 進場那一分鐘還沒收完，不算
    cur_lo = cur_hi = None                   # 正在形成的那一根
    rng_ext = None                           # 上次移動以來已收完 K 棒的極值（多單最低、空單最高）
    cand = None
    best = worst = 0.0
    for s, p, _q, _a in ticks[i0 + 1:]:
        m = s // 60
        if m != bar_m:
            if cur_lo is not None:           # 上一根收完
                ext = cur_lo if sgn > 0 else cur_hi
                rng_ext = ext if rng_ext is None else (min(rng_ext, ext) if sgn > 0 else max(rng_ext, ext))
                cand = rng_ext - sgn * buf
            bar_m, cur_lo, cur_hi = m, None, None
        cur_lo = p if cur_lo is None else min(cur_lo, p)
        cur_hi = p if cur_hi is None else max(cur_hi, p)
        fav = sgn * (p - p_raw)
        best, worst = max(best, fav), min(worst, fav)
        if s >= exit_s:
            return _close(tr, s, p - sgn * slip, "eod", best, worst, cost_side)
        if sgn * (p - st) <= 0:
            why = "trail" if tr.moves else "stop"
            return _close(tr, s, p - sgn * slip, why, best, worst, cost_side)
        if tg is not None and sgn * (p - tg) >= 1:
            return _close(tr, s, tg, "target", best, worst, cost_side)
        if cand is not None and sgn * (cand - st) > 0 and sgn * (p - cand) >= clear:
            st = cand
            tr.moves.append((s, st))
            rng_ext, cand = None, None       # 之後重新從這一刻收完的 K 棒算
    s, p = ticks[-1][0], ticks[-1][1]                 # 收盤前資料就沒了（不該發生）：用最後一筆出場
    return _close(tr, s, p - sgn * slip, "close", best, worst, cost_side)


def _close(tr: Trade, s: int, px: float, why: str, best: float, worst: float, cost_side) -> Trade:
    sgn = 1 if tr.side == "long" else -1
    tr.t_out, tr.px_out, tr.why = s, px, why
    tr.gross = round(sgn * (px - tr.px_in), 4)
    tr.net = round(tr.gross - cost_side(tr.px_in) - cost_side(px), 4)
    tr.mfe, tr.mae = best, worst
    return tr


def last_le(ticks: list[tuple[int, int, int, bool]], s: int) -> int | None:
    """s 秒（含）以前最後一筆成交價。"""
    px = None
    for t, p, _q, _a in ticks:
        if t > s:
            break
        px = p
    return px
