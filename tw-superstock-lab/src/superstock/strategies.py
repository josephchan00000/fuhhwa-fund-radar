"""策略（SPEC §6）。目前只有 S01 SEPA（《超級績效》）與它事前寫定的變體；其他策略之後照表補。

S01（SPEC §6，使用者核定）：趨勢樣板 8 條 ＆ VCP 成立 ＆ 收盤突破樞紐 ＆ 量 ≥ 50 日均量 × 1.5 ＆ 大盤濾網
→ 停損 8%（上限 10%）、浮盈 2R 後停損移到成本、收盤跌破 50 日線出場。
細節解讀與變體清單寫在 reports/P4_S01_plan.md（跑結果之前寫定）。
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from .engine import Costs, EngineConfig, Market, Result, run_trades

# 主規格（SPEC §6 S01）；變體只改這裡列出的鍵
S01 = {"entry": "open", "vol": 1.5, "stop_pct": 0.08, "breakeven_r": 2.0, "ma_exit": 50, "market": True,
       "tt": True, "vcp": True, "fund": None, "max_hold": None}

# 事前寫定的變體（reports/P4_S01_plan.md 第 4 節）。名稱 → 與主規格不同的鍵
VARIANTS = {
    "S01": {},
    "S01_stop_entry": {"entry": "stop"},          # 書上的買法：盤中漲過樞紐就買（日線看不到當天的量）
    "S01_no_market": {"market": False},
    "S01_fund": {"fund": "growth"},               # 最新一季 EPS 年增 ≥ 25%、最新月營收年增 ≥ 20%（SPEC S03 的門檻）
    "S01_code33": {"fund": "c33"},                # EPS、營收、毛利率連三季加速
    "S01_be3": {"breakeven_r": 3.0},
    "S01_no_be": {"breakeven_r": None},
    "S01_no_vcp": {"vcp": False},                 # 樣板＋收盤創 50 日新高＋量（看 VCP 本身有沒有加分）
    "S01_no_tt": {"tt": False},                   # VCP＋突破＋量，不看樣板
}
GRID = {"stop_pct": (0.06, 0.08, 0.10), "vol": (1.25, 1.5, 2.0)}      # 參數鄰近 3 × 3


def spec_of(name: str, **kw) -> dict:
    return {**S01, **VARIANTS.get(name, {}), **kw}


def _shift(a: np.ndarray, k: int = 1, fill=np.nan) -> np.ndarray:
    out = np.empty_like(a)
    out[:k] = fill
    out[k:] = a[:-k]
    return out


def s01_mask(m: Market, F: dict, spec: dict) -> np.ndarray:
    """訊號日 × 股票（bool）。open＝今天收盤確認突破（前一天 VCP 成立、今天收盤 > 前一天的樞紐、量夠）→ 明天開盤買；
    stop＝今天 VCP 成立且還沒突破 → 明天盤中漲過樞紐就買。"""
    el = F["elig"]
    with np.errstate(invalid="ignore"):
        if spec["entry"] == "open":
            if spec["vcp"]:
                brk = _shift(F["vcp_ok"], 1, False) & (m.c > _shift(F["vcp_pivot"], 1))
            else:
                h50 = pd.DataFrame(m.h).rolling(50, min_periods=40).max().shift(1).to_numpy()
                brk = m.c > h50
            mask = brk & (m.vol >= spec["vol"] * _shift(F["vol50"], 1)) & el
        else:
            mask = F["vcp_ok"] & (m.c <= F["vcp_pivot"]) & el
    if spec["tt"]:
        mask &= F["tt_pass"]
    return mask


def fund_ok(kind: str, f: dict) -> bool:
    if kind == "growth":
        ey, ry = f.get("ey"), f.get("ry")
        return ey is not None and ry is not None and ey >= 0.25 and ry >= 0.20
    if kind == "c33":
        return f.get("c33") is True
    return True


def signals(m: Market, F: dict, spec: dict, fund=None, tag: str = "S01") -> pd.DataFrame:
    """→ run_trades 用的訊號表。fund(股票, 日索引) → 基本面特徵（只在 spec['fund'] 有設時用）。"""
    mask = s01_mask(m, F, spec)
    ii, jj = np.nonzero(mask)
    rows = []
    for i, j in zip(ii.tolist(), jj.tolist()):
        c = m.stocks[j]
        if spec["fund"] and not fund_ok(spec["fund"], fund(c, i) if fund else {}):
            continue
        r = {"date": m.dates[i], "stock_id": c, "entry": spec["entry"], "stop_pct": spec["stop_pct"],
             "score": float(np.nan_to_num(F["rs"][i, j])), "tag": tag}
        if spec["entry"] == "stop":
            r["pivot"] = float(F["vcp_pivot"][i, j])
        rows.append(r)
    cols = ["date", "stock_id", "entry", "stop_pct", "score", "tag", "pivot"]
    return pd.DataFrame(rows, columns=cols)


def exit_frame(m: Market, F: dict, spec: dict) -> pd.DataFrame | None:
    """收盤跌破 50 日線（還原價）→ 隔天開盤賣。"""
    if not spec["ma_exit"]:
        return None
    with np.errstate(invalid="ignore"):
        x = (m.c < F["ma50"]) & ~np.isnan(m.c)
    return pd.DataFrame(x, index=m.dates, columns=m.stocks)


def config(spec: dict, base: EngineConfig | None = None) -> EngineConfig:
    """SPEC §4 的引擎預設（風險 1%、單檔上限 20%、20 日均量 5%、最多 20 檔、1 張 1,000 股）；lab 面板沒有處置股資料。"""
    cfg = base or EngineConfig(costs=Costs())
    return replace(cfg, breakeven_r=spec["breakeven_r"], market_filter=spec["market"], block_disposition=False,
                   max_hold_days=spec["max_hold"])


def run(m: Market, F: dict, spec: dict, start, end, fund=None, base: EngineConfig | None = None,
        sig: pd.DataFrame | None = None) -> tuple[Result, pd.DataFrame]:
    sig = signals(m, F, spec, fund) if sig is None else sig
    res = run_trades(m, sig, config(spec, base), exit_flags=exit_frame(m, F, spec), start=start, end=end)
    return res, sig
