from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from superstock.engine import (Costs, EngineConfig, HoldoutLocked, Market, evaluate, label_hits, log_trial,
                               market_filter, max_drawdown, metrics, replicate_index, run_portfolio, run_trades)

CAP = 1_000_000.0


def market(closes: dict, opens=None, highs=None, lows=None, factor=None, start="2020-01-02",
           value=2e9, volume=1e8, **kw) -> Market:
    stocks = list(closes)
    n = len(closes[stocks[0]])
    dates = pd.bdate_range(start, periods=n)

    def arr(d, default):
        if d is None:
            return default.copy()
        return np.array([d.get(s, default[:, j]) for j, s in enumerate(stocks)], dtype=float).T

    c = np.array([closes[s] for s in stocks], dtype=float).T
    o, h, lo = arr(opens, c), arr(highs, c), arr(lows, c)
    f = arr(factor, np.ones_like(c))
    return Market(dates, stocks, o, h, lo, c, factor=f, value=np.full_like(c, value),
                  volume=np.full_like(c, volume), **kw)


def cfg(**kw) -> EngineConfig:
    base = dict(capital=CAP, lot=1, max_weight=1.0, max_adv=math.inf, market_filter=False)
    base.update(kw)
    return EngineConfig(**base)


def one_day(m: Market, i: int, stocks=None) -> pd.DataFrame:
    stocks = stocks or m.stocks
    return pd.DataFrame({s: [1.0] for s in stocks}, index=[m.dates[i]])


# ---------------------------------------------------------------- GATE P2 四項
def test_zero_signal_is_flat():
    m = market({"A": [100.0 + i for i in range(30)], "B": [50.0] * 30})
    scores = pd.DataFrame(np.nan, index=m.dates[:10], columns=m.stocks)
    res = run_portfolio(m, scores, cfg(), top_n=2)
    assert (res.equity == CAP).all() and res.trades.empty
    res2 = run_trades(m, pd.DataFrame(columns=["date", "stock_id"]), cfg())
    assert (res2.equity == CAP).all()


def _dividend_market():
    raw = [100, 100, 102, 104, 99, 101, 103]          # 第 4 天除息 5 元（104 → 參考價 99）
    f_e = 99 / 104
    factor = [f_e] * 4 + [1.0] * 3
    adj = [r * f for r, f in zip(raw, factor)]
    return market({"A": adj}, factor={"A": factor}), adj, factor


def test_buy_and_hold_equals_adjusted_return_without_costs():
    m, adj, _ = _dividend_market()
    res = run_portfolio(m, one_day(m, 0), cfg(lot=0, costs=Costs.zero()), top_n=1)
    # 第 0 天收盤下單、第 1 天開盤買；含息報酬＝還原價漲幅（除息日沒有假下跌）
    assert res.equity.iloc[-1] / CAP == pytest.approx(adj[-1] / adj[1], rel=1e-12)
    assert res.trades.iloc[0]["reason"] == "end"


def test_buy_and_hold_equals_adjusted_return_minus_costs():
    m, adj, factor = _dividend_market()
    c = Costs()
    res = run_portfolio(m, one_day(m, 0), cfg(costs=c), top_n=1)
    slip = 0.0005                                        # 20 日均成交值 20 億 → 5bp
    raw_buy = adj[1] * (1 + slip) / factor[1]
    rate = c.commission * c.discount
    shares = math.floor(CAP / (raw_buy * (1 + rate)))
    cash = CAP - shares * raw_buy - c.fee(shares * raw_buy)
    gross = shares / factor[1] * adj[-1] * (1 - slip)
    expected = cash + gross - c.fee(gross) - c.tax(gross)
    assert res.equity.iloc[-1] == pytest.approx(expected, rel=1e-12)
    t = res.trades.iloc[0]
    assert t["shares"] == shares and t["pnl"] == pytest.approx(expected - CAP, rel=1e-9)


def test_costs_monotonic():
    m, _, _ = _dividend_market()
    finals = []
    for c in (Costs.zero(), Costs(discount=0.3), Costs(discount=0.6), Costs(discount=1.0),
              Costs(discount=1.0, scale=2.0)):
        finals.append(run_portfolio(m, one_day(m, 0), cfg(costs=c), top_n=1).equity.iloc[-1])
    assert all(a > b for a, b in zip(finals, finals[1:]))
    # 流動性越差滑價越大
    thin = market({"A": [100.0] * 8}, value=5e6)
    thick = market({"A": [100.0] * 8}, value=5e9)
    e_thin = run_portfolio(thin, one_day(thin, 0), cfg(), top_n=1).equity.iloc[-1]
    e_thick = run_portfolio(thick, one_day(thick, 0), cfg(), top_n=1).equity.iloc[-1]
    assert e_thin < e_thick


def test_locked_up_blocks_entry():
    lu = np.zeros((6, 1), dtype=bool)
    lu[1, 0] = True
    m = market({"A": [100.0, 110.0, 112.0, 113.0, 114.0, 115.0]}, locked_up=lu)
    res = run_portfolio(m, one_day(m, 0), cfg(costs=Costs.zero()), top_n=1)
    assert res.trades.empty and (res.equity == CAP).all()
    # 單子有效 2 天：第 2 天開盤買到
    res2 = run_portfolio(m, one_day(m, 0), cfg(costs=Costs.zero(), entry_valid_days=2), top_n=1)
    assert res2.trades.iloc[0]["entry_date"] == m.dates[2]


def test_locked_down_delays_stop_exit():
    c = [100.0, 100.0, 98.0, 85.0, 80.0, 82.0]
    lo = [100.0, 99.0, 97.0, 85.0, 79.0, 81.0]
    op = [100.0, 100.0, 99.0, 85.0, 80.0, 81.0]
    ld = np.zeros((6, 1), dtype=bool)
    ld[3, 0] = True                                       # 第 3 天一價到底跌停
    m = market({"A": c}, opens={"A": op}, lows={"A": lo}, locked_down=ld)
    sig = pd.DataFrame({"date": [m.dates[0]], "stock_id": ["A"], "entry": ["open"], "stop": [90.0]})
    res = run_trades(m, sig, cfg(costs=Costs.zero(), risk_pct=0.5))
    t = res.trades.iloc[0]
    assert t["reason"] == "stop" and t["exit_date"] == m.dates[4] and t["exit_px"] == pytest.approx(80.0)


# ---------------------------------------------------------------- 成交細節
def test_stop_entry_fill_rules():
    n = 5
    c = {"NO": [100.0] * n, "HIT": [100.0] * n, "GAP": [100.0] * n, "LOCK": [100.0] * n}
    op = {"NO": [100, 103, 100, 100, 100], "HIT": [100, 103, 100, 100, 100],
          "GAP": [100, 108, 100, 100, 100], "LOCK": [100, 110, 100, 100, 100]}
    hi = {"NO": [100, 104, 100, 100, 100], "HIT": [100, 107, 100, 100, 100],
          "GAP": [100, 109, 100, 100, 100], "LOCK": [100, 110, 100, 100, 100]}
    lu = np.zeros((n, 4), dtype=bool)
    lu[1, 3] = True
    m = market(c, opens={k: [float(x) for x in v] for k, v in op.items()},
               highs={k: [float(x) for x in v] for k, v in hi.items()}, locked_up=lu)
    sig = pd.DataFrame({"date": [m.dates[0]] * 4, "stock_id": list(c), "entry": ["stop"] * 4,
                        "pivot": [105.0] * 4, "stop": [95.0] * 4})
    res = run_trades(m, sig, cfg(costs=Costs.zero(), risk_pct=0.02, max_weight=0.2))
    got = res.trades.set_index("stock_id")
    assert set(got.index) == {"HIT", "GAP"}
    assert got.loc["HIT", "entry_px"] == pytest.approx(105.0)   # 盤中觸價＝突破價
    assert got.loc["GAP", "entry_px"] == pytest.approx(108.0)   # 開盤跳空在突破價之上＝開盤價


def test_stop_first_when_stop_and_target_same_day():
    m = market({"A": [100.0, 100.0, 100.0, 100.0]}, opens={"A": [100.0, 100.0, 100.0, 100.0]},
               highs={"A": [100.0, 100.0, 112.0, 100.0]}, lows={"A": [100.0, 100.0, 93.0, 100.0]})
    sig = pd.DataFrame({"date": [m.dates[0]], "stock_id": ["A"], "stop": [95.0], "target": [110.0]})
    t = run_trades(m, sig, cfg(costs=Costs.zero(), risk_pct=0.1)).trades.iloc[0]
    assert t["reason"] == "stop" and t["exit_px"] == pytest.approx(95.0)


def test_risk_sizing_and_caps():
    base = dict(capital=10_000_000.0, lot=1000, max_adv=0.05, market_filter=False)

    def shares(stop, volume=1e8):
        m = market({"A": [100.0] * 5}, volume=volume)
        sig = pd.DataFrame({"date": [m.dates[0]], "stock_id": ["A"], "stop": [stop]})
        return run_trades(m, sig, EngineConfig(**base, costs=Costs.zero())).trades.iloc[0]["shares"]

    assert shares(90.0) == 10_000                 # 1% 風險 ÷ 每股 10 元
    assert shares(99.0) == 20_000                 # 每股風險 1 元 → 10 萬股，被單檔 20% 上限壓成 200 萬元
    assert shares(90.0, volume=100_000) == 5_000  # 20 日均量 10 萬股 → 5% = 5,000 股
    assert shares(90.0, volume=109_000) == 5_000  # 5,450 股取整張 → 5 張


def test_market_filter_blocks_new_entries():
    n = 260
    down = [200.0 - 0.5 * i for i in range(n)]
    lvl = pd.Series([20000.0 - 10 * i for i in range(n)], index=pd.bdate_range("2019-01-01", periods=n))
    m = market({"A": down}, start="2019-01-01", index_level=lvl)
    mf = market_filter(m)
    assert not mf[-1]
    sig = pd.DataFrame({"date": [m.dates[-5]], "stock_id": ["A"], "stop_pct": [0.08]})
    assert run_trades(m, sig, cfg(market_filter=True, risk_pct=0.1)).trades.empty
    assert len(run_trades(m, sig, cfg(market_filter=False, risk_pct=0.1)).trades) == 1


def test_disposition_blocks_entry_and_adds_slippage():
    dp = np.zeros((6, 1), dtype=bool)
    dp[1, 0] = True
    m = market({"A": [100.0] * 6}, disposed=dp)
    assert run_portfolio(m, one_day(m, 0), cfg(), top_n=1).trades.empty
    dp2 = np.zeros((6, 1), dtype=bool)
    dp2[3, 0] = True
    m2 = market({"A": [100.0] * 6}, disposed=dp2)
    flags = pd.DataFrame(False, index=m2.dates, columns=["A"])
    flags.iloc[2, 0] = True                        # 第 2 天收盤觸發出場 → 第 3 天（處置中）開盤賣
    t = run_portfolio(m2, one_day(m2, 0), cfg(), top_n=1, exit_flags=flags).trades.iloc[0]
    assert t["exit_date"] == m2.dates[3] and t["exit_px"] == pytest.approx(100.0 * (1 - 0.0005 - 0.005))


def test_delisted_position_exits_at_last_close():
    c = [100.0, 100.0, 101.0, 99.0, np.nan, np.nan]
    m = market({"A": c, "B": [50.0] * 6})
    res = run_portfolio(m, one_day(m, 0, ["A"]), cfg(costs=Costs.zero()), top_n=1)
    t = res.trades.iloc[0]
    assert t["reason"] == "delisted" and t["exit_date"] == m.dates[4] and t["exit_px"] == pytest.approx(99.0)


def test_portfolio_rebalance_switches_holdings():
    m = market({"A": [100.0] * 10, "B": [50.0] * 10})
    scores = pd.DataFrame({"A": [2.0, 1.0], "B": [1.0, 2.0]}, index=[m.dates[0], m.dates[5]])
    res = run_portfolio(m, scores, cfg(costs=Costs.zero()), top_n=1)
    t = res.trades.set_index("stock_id")
    assert t.loc["A", "reason"] == "rebalance" and t.loc["A", "exit_date"] == m.dates[6]
    assert t.loc["B", "entry_date"] == m.dates[6] and t.loc["B", "reason"] == "end"


def test_breakeven_stop_and_min_hold():
    c = [100.0, 100.0, 105.0, 125.0, 100.0, 100.0]
    m = market({"A": c}, lows={"A": [100.0, 100.0, 104.0, 120.0, 99.0, 100.0]},
               opens={"A": [100.0, 100.0, 104.0, 120.0, 101.0, 100.0]})
    sig = pd.DataFrame({"date": [m.dates[0]], "stock_id": ["A"], "stop": [90.0]})
    t = run_trades(m, sig, cfg(costs=Costs.zero(), breakeven_r=2.0, risk_pct=0.1)).trades.iloc[0]
    # 第 3 天收盤 125 ≥ 100 + 2×10 → 停損移到 100；第 4 天最低 99 → 以停損價 100 出場
    assert t["reason"] == "stop" and t["exit_px"] == pytest.approx(100.0)
    m2 = market({"A": [100.0, 100.0, 80.0, 80.0, 80.0]}, lows={"A": [100.0, 100.0, 80.0, 80.0, 80.0]},
                opens={"A": [100.0, 100.0, 85.0, 80.0, 80.0]})
    sig2 = pd.DataFrame({"date": [m2.dates[0]], "stock_id": ["A"], "stop": [90.0]})
    t2 = run_trades(m2, sig2, cfg(costs=Costs.zero(), min_hold_days=2, risk_pct=0.1)).trades.iloc[0]
    assert t2["exit_date"] == m2.dates[3]          # 第 2 天就跌破，但最短持有 2 天 → 第 3 天才賣


# ---------------------------------------------------------------- 指標與紀錄
def test_metrics_known_values():
    idx = pd.to_datetime(["2020-01-01", "2021-01-01", "2022-01-01"])
    eq = pd.Series([100.0, 150.0, 200.0], index=idx)
    mm = metrics(eq)
    years = (idx[-1] - idx[0]).days / 365.25
    assert mm["cagr"] == pytest.approx(2 ** (1 / years) - 1)
    assert max_drawdown(pd.Series([100.0, 120.0, 90.0, 130.0])) == pytest.approx(-0.25)
    bench = pd.Series([100.0, 110.0, 121.0], index=idx)
    mm = metrics(eq, bench=bench)
    assert mm["excess_cagr"] == pytest.approx(mm["cagr"] - mm["bench_cagr"])


def test_label_hits():
    labels = pd.DataFrame({"date": pd.to_datetime(["2020-01-02"] * 4), "stock_id": ["A", "B", "C", "D"],
                           "y_A": [1, 0, 0, 1]})
    entries = pd.DataFrame({"date": pd.to_datetime(["2020-01-02"]), "stock_id": ["A"]})
    out = label_hits(entries, labels, ("y_A",))
    assert out["y_A_precision"] == 1.0 and out["y_A_base"] == 0.5 and out["y_A_lift"] == 2.0
    assert out["y_A_recall"] == 0.5


def test_trials_log_appends(tmp_path):
    path = tmp_path / "trials.csv"
    log_trial(path, "S04", "portfolio", {"top_n": 20}, {"cagr": 0.1234567, "sharpe": float("nan")}, ts="t1")
    log_trial(path, "S04", "portfolio", {"top_n": 10}, {"cagr": 0.2}, ts="t2")
    df = pd.read_csv(path)
    assert list(df["name"]) == ["S04", "S04"] and df["cagr"].iloc[0] == pytest.approx(0.123457)
    assert '"top_n": 10' in df["params"].iloc[1]


def test_replicate_index_matches_yearly():
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2018-03-01", "2021-12-31")
    level = pd.Series(10000 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(dates)))), index=dates)
    rep = replicate_index(level)
    assert len(rep) == 4 and rep["diff"].abs().max() < 1e-9


def test_replicate_cli_writes_report(cfg):
    from superstock.cli import cmd_replicate
    dates = pd.bdate_range("2019-01-02", "2020-12-31")
    tr = pd.Series(np.linspace(20000, 26000, len(dates)), index=dates)
    idx = pd.DataFrame({"date": dates, "index_id": "TAIEX", "level": tr.values / 2, "total_return": tr.values})
    cfg.processed_dir.mkdir(parents=True)
    idx.to_parquet(cfg.processed_dir / "index.parquet", index=False)
    assert cmd_replicate(cfg, None) == 0
    text = (cfg.reports_dir / "replication_P2.md").read_text(encoding="utf-8")
    assert "通過" in text and "| 2020 |" in text


def test_evaluate_logs_trial_and_locks_holdout(tmp_path):
    m = market({"A": [100.0 + i for i in range(20)]}, start="2019-12-02")
    res = run_portfolio(m, one_day(m, 0), cfg(), top_n=1, end="2019-12-31")
    out = evaluate("B", "portfolio", res, {"top_n": 1}, m, reports_dir=tmp_path)
    assert out["trades"] == 1 and (tmp_path / "trials.csv").exists()
    res2 = run_portfolio(m, one_day(m, 0), cfg(), top_n=1)          # 跑到 2020 年，還沒到保留期
    evaluate("B", "portfolio", res2, {"top_n": 1}, m, reports_dir=tmp_path)
    m3 = market({"A": [100.0 + i for i in range(20)]}, start="2022-12-20")
    res3 = run_portfolio(m3, one_day(m3, 0), cfg(), top_n=1)
    with pytest.raises(HoldoutLocked):
        evaluate("B", "portfolio", res3, {}, m3, reports_dir=tmp_path)
    evaluate("B", "portfolio", res3, {}, m3, reports_dir=tmp_path, allow_holdout=True)
    assert len((tmp_path / "holdout_log.csv").read_text(encoding="utf-8").splitlines()) == 1
    assert len(pd.read_csv(tmp_path / "trials.csv")) == 3
