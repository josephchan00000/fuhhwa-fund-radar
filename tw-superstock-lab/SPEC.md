# SUPERSTOCK SPEC v1 — Taiwan explosive-stock research system
Executor: Claude Code on owner's Mac. Owner: JC. Talk to owner in Traditional Chinese, short.
Human plan (owner's doc): https://claude.ai/code/artifact/3047ae10-23d1-40f5-99c0-9174296cc61c
Goal: find what TW superperformers look like BEFORE they run (reverse-engineer, Minervini-style model book), test well-known open-source strategies on TW realities, ship a validated daily screener.

## 0 Protocol
- Session start: read PROGRESS.md (create if missing) → resume at `Next`. Update after every step (≤40 lines: phase.step, done, next, running jobs+PID, blockers, key numbers, assumptions).
- Phases P1→P6 in order. Each ends at GATE → write `reports/gate_P{n}.md` (zh-TW, ≤1 page: criteria vs actual, deviations, decisions). PASS → continue. FAIL → stop, ask owner.
- Decide defaults yourself; log them as Assumptions. Ask owner only for: missing FINMIND_TOKEN, paying for data, gate FAIL, anything irreversible.
- Long jobs (≥1h): background + log (`caffeinate -is nohup <cmd> > data/logs/<name>.log 2>&1 &`), record PID, keep working on other steps, poll log. Downloads are resumable: rerun the same command.
- Hard rules: never commit `data/`, `.env`; never print token; no live orders; no look-ahead (§1.4); every number in reports comes from code output.
- `pytest` green before each commit; commit per step `P{n}.{k}: <what>`.
- Token economy: read only needed files/sections, use `rg`, never dump parquet/CSV, summarize long outputs.

## 1 Locked decisions
1.1 Data: FinMind free tier only (token in `.env` FINMIND_TOKEN; 600 req/h after email verification; 300 without token). No paid data. Per-stock requests only (all-stocks-by-date is sponsor-only).
1.2 Universe: TWSE+TPEx common stocks, id `^[1-9]\d{3}$`; exclude ETF/ETN/warrant/preferred/TDR/emerging. Include stocks delisted after start.
1.3 Dates: download from 2008-01-01 (warm-up). Research from 2010-01-01. IS 2010–2019 (discover+tune, walk-forward inside) · VAL 2020–2022 (select) · HOLDOUT 2023-01-01→latest (open ONCE in P5).
1.4 Point-in-time: monthly revenue usable from 10th of next month. Financials (period ≥2013): Q1 5/15, Q2 8/14, Q3 11/14, Q4 next-year 3/31; (period <2013): Q1 4/30, Q2 8/31, Q3 10/31, Q4 next-year 4/30. Daily chips usable same evening. TDCC weekly: next trading day. Signal at close t → trade t+1.
1.5 Execution: next-day fill (open, or stop-entry at pivot). No pre-approval delay. `min_hold_days` param default 0.
1.6 Daily price limit: 7% before 2015-06-01, 10% after. New listings: no limit first 5 days.
1.7 Outputs: research report (md→HTML), daily screener static HTML, paper-trade CSV. Telegram later.

## 2 Repo layout
```
src/superstock/  config datasets finmind_client storage universe download adjust pit build quality reconcile cli  (P1, done)
                 features labels engine strategies research validate daily  (P2–P6, to build)
tests/  reports/ (committed)  data/{raw,processed,logs,manifest.sqlite} (gitignored)
```

## 3 P1 Data layer — STARTER CODE PROVIDED (33 tests pass; never run against live FinMind)
CLI `python -m superstock <cmd>`: check | download | update | build | quality | reconcile | status. Options: `--groups meta core events extended`, `--stocks ...`, `--max-calls N`, `--enable DS`, `--reset-mode DS`.
3.1 FinMind API (from FinMind 2.0.11 source): GET https://api.finmindtrade.com/api/v4/data ?dataset&data_id&start_date&end_date, header `Authorization: Bearer <token>`, resp `{msg,status,data}`. Quota: GET https://api.web.finmindtrade.com/v2/user_info → {user_count, api_request_limit}. Maintenance Sun 00:00–07:00.
3.2 Datasets (group: names):
- meta: TaiwanStockInfo, TaiwanStockDelisting, TaiwanStockTradingDate, TaiwanStockPrice[TAIEX,TPEx]→IndexPrice, TaiwanStockTotalReturnIndex[TAIEX,TPEx]
- core (per stock): TaiwanStockPrice, TaiwanStockMonthRevenue, TaiwanStockFinancialStatements, TaiwanStockInstitutionalInvestorsBuySell, TaiwanStockMarginPurchaseShortSale
- events (probe 3y without data_id → global yearly chunks, else per stock): TaiwanStockDividendResult, TaiwanStockCapitalReductionReferencePrice, TaiwanStockSplitPrice, TaiwanStockParValueChange, TaiwanStockDispositionSecuritiesPeriod
- extended: TaiwanStockHoldingSharesPer, TaiwanStockBalanceSheet, TaiwanStockShareholding, TaiwanStockPriceAdj (cross-check only), TaiwanStockSecuritiesLending
3.3 Downloader behavior: sliding-window limiter (92% of limit, ≥1s spacing); 402/429/"upper limit" → wait 600s, poll user_info; 5xx/network → exp backoff ×6; same dataset fails on 3 consecutive stocks (4xx) → auto-disable (likely sponsor-only); SQLite manifest per (dataset,key) → resume + incremental (start = last_end − overlap); stock-major order (each stock complete before next), listed first then delisted.
3.4 Build → data/processed: universe, calendar, index, events, prices (raw OHLCV + adj_* + ret + locked_up/down), revenue(+available_date), financials(long, +available_date), institutional (wide net_*), margin, disposition.
- Adjustment: event factor f = after_ref/before_close; adj_price(t) = raw(t) × Π f(events after t). Sources: DividendResult(before_price, after_price), CapitalReduction(ClosingPriceonTheLastTradingDay, PostReductionReferencePrice), Split(before_price, after_price), ParValue(before_close, after_ref_close). Keep f in [0.05, 20].
- locked_up/down: open=high=low=close and |ret| ≥ limit−1.5pp.
3.5 Quality C1–C11 → reports/data_quality.{md,json}: downloads, universe, integrity, unexplained jumps (|ret|>limit+1pp after first 5 days), calendar, gaps>30d, events (+cash-dividend consistency), FinMind-adj cross-check, revenue, financials, chips coverage.
3.6 Reconcile: 20 stocks stratified (5 large TWSE, 5 other TWSE, 6 TPEx, 4 delisted) → auto vs TWSE `https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=YYYYMMDD&stockNo=XXXX&response=json` (unverified; fix parser if needed), rest → manual checklist in reports/reconciliation.md.
3.7 Verify live, fix + add test if wrong: quota response format · events accept no data_id · PriceAdj free? · index id "TPEx" · TWSE endpoint · MonthRevenue `date` meaning (code uses revenue_year/month) · DividendResult after_price = 除權息參考價 (C7) · FinancialStatements `date` = quarter end (C10) · TaiwanStockInfo `type` values.
3.8 Run: venv + `pip install -e ".[dev]"` + pytest → `.env` → `check` (log universe size, ETA) → smoke `download --stocks 2330 6488 1101 --max-calls 60` + build + quality → full `download` in background (core ≈ stocks×5 calls ≈ 20h; events ≈ minutes if global) → meanwhile build P2 on synthetic/partial data → `build`, `quality`, `reconcile` → then start `download --groups extended` in background (needed for C8, S14).
GATE P1: no FAIL in C1–C11; auto reconcile ≥95% match; manual items listed for owner; universe ≈1.8k listed + >0 delisted.

## 4 P2 Backtest engine (`engine.py`)
- Portfolio mode (fast): score/bool frame date×stock → each rebalance pick top N equal-weight → fill next open → hold to next rebalance.
- Trade mode (path-dependent): signals (date, stock, entry next_open | stop@pivot, initial stop). Day loop on OHLC: entry if next-day high ≥ pivot, fill max(open, pivot); no fill if locked_up. Stop: if low ≤ stop fill min(open, stop); locked_down → carry. Both stop & target touched same day → assume stop first.
- Sizing: risk_pct of equity (default 1%) / (entry − stop); lot 1000 shares (param allow odd lots); cap 20% equity per stock; cap 5% of 20d avg volume; max positions param.
- Costs: commission 0.1425% × discount (default 0.6) each side, min NT$20; sell tax 0.3%; slippage per side by 20d avg value: ≥1e9 5bp · 1e8–1e9 15bp · 1e7–1e8 30bp · <1e7 60bp. Disposition period: no new entries (param) and +50bp.
- Market filter (shared): TAIEX close > MA200 and (new 52w highs − new lows) > 0 over universe; off → no new entries.
- Metrics: CAGR, vol, Sharpe, Sortino, MaxDD, Calmar, win rate, payoff, expectancy/trade, avg hold, turnover, exposure, trades; plus label hit stats (precision/recall/lift of entries vs y_A, y_B).
- Benchmark: TAIEX total return (IndexPrice/TotalReturnIndex).
- Trials log: append every run config + metrics to reports/trials.csv (needed for DSR).
GATE P2: unit tests (zero signal flat; single-stock buy&hold = adj return − costs; costs monotonic; limit-lock blocks fills); TAIEX-TR buy&hold replication |annual diff| ≤ 0.5%.

## 5 P3 Reverse engineering / model book (`labels.py`, `features.py`, `research.py`)
5.1 Labels per stock-day (adjusted, future used ONLY for labels):
- y_A = max(adj_high[t+1..t+60]) / adj_close[t] − 1 ≥ 0.50
- y_B = max(adj_high[t+1..t+250]) / adj_close[t] − 1 ≥ 1.00
- y_C = fwd 60d return (adj_close[t+60]/adj_close[t]−1) ≥ 99th pct cross-section same date
- Eligible t: median 20d value (raw Trading_money) ≥ NT$10M, ≥60 trading days since listing, no price gap >10d in prior 60d.
5.2 Episodes (for model book): consecutive y_A (or y_B) days merged if gap <20d; T0 = argmin adj_close in run; peak = argmax adj_high in (T0, T0+60/250]; pivot T1 = first day after T0 with adj_close > max(adj_high[t−50..t−1]) (may be null = V-shape). Record days-to-peak, max drawdown during run, limit-up days.
5.3 Features (PIT, as of close t). Panel = weekly samples (last trading day/week), all eligible stocks.
- Trend: tt_count (0–8) & tt_pass — Minervini template: close>MA150&MA200; MA150>MA200; MA200 up ≥1 month (20d); MA50>MA150&MA200; close>MA50; close ≥1.30×52w low; close ≥0.75×52w high; rs_pct ≥70.
- rs_pct: score=0.4·r63+0.2·r126+0.2·r189+0.2·r252 (r_n=close/close[t−n]−1), cross-section percentile 1–99.
- dist_52w_high, dist_52w_low, days_since_52w_high, ret_20/60/120, ma50_slope20, ma200_slope20, close/MA20, close/MA50, stage2 (close>MA150 & MA150 up), up/down volume ratio 50d, limit-up count 20d, gap≥5% count 20d.
- Contraction: atr14/close, its 1y percentile; bbw20 1y percentile; vol_dryup = vol10/vol50.
- VCP: base start = highest high in last 260d (≥30d ago); zigzag swings (3% threshold) → contraction depths d1..dn; vcp_valid if 2≤n≤6, each d_i < 1.1·d_{i−1}, d1 ≤ 35%, dn ≤ 10%, close ≥ 0.9·pivot (last swing high), vol_dryup ≤ 0.7. Output n, d1, dn, pivot, vcp_valid.
- Revenue (latest available): rev_yoy, rev_yoy_3m (3m sum vs LY), rev_accel (rev_yoy_3m − same 3 months earlier), rev_new_high_12m, rev_new_high_all, rev_mom.
- Financials (latest available quarter): eps_yoy, eps_accel, gross margin & yoy change, op margin & yoy change, code33 (EPS growth, sales growth, margin all accelerating 3 consecutive quarters).
- Chips: trust/foreign net 5d & 20d ÷ volume same window, trust_buy_streak, foreign_buy_streak, margin_chg_20, margin_util (balance/limit); big1000_chg_4w (TDCC ≥1000-lot %, if extended).
- Group/market: industry RS rank (median rs_pct by industry), industry share with tt_pass, mkt_above_ma200, breadth (% above MA50), NH−NL.
- Size/liquidity: log median 60d value.
5.4 Analysis on IS only:
- Per feature: deciles (or bool) → precision, recall, lift = precision / base rate; lift per year (stability). Base rates per label and per year in report.
- Rules: decision tree (depth ≤3) + rule mining over top features → keep rules with lift ≥2, support ≥300 stock-weeks, ≥50 positives, lift ≥1.5 in each IS sub-period (2010–13, 2014–16, 2017–19).
- LightGBM (label y_A and y_B; purged walk-forward by year, 60d embargo) + SHAP top interactions.
- Archetypes: k-means (k 4–6 by silhouette) on standardized T0 features of episodes; name clusters (e.g. revenue-burst, theme-group, chip-accumulation, classic-VCP).
- Model book: per archetype 5 example charts (PNG via mplfinance: candles, MA50/150/200, volume, T0/T1/peak markers, revenue & trust-net subplots) → reports/model_book/.
- Report reports/P3_reverse_engineering.md: base rates, top-20 features by lift, rules table, archetypes, what SEPA rules the data confirms/refutes.
GATE P3: ≥1 rule for y_A or y_B meeting all rule thresholds.

## 6 P4 Strategy zoo (`strategies.py`; one class each: name, source, params, universe(), signal(), exit())
Reimplement on our data (reference repos for logic only: FinMind/FinMind strategies, mlouielu/twstock BestFourPoint, microsoft/qlib Alpha158, stefan-jansen/machine-learning-for-trading 101 alphas, skyte/relative-strength).
| id | rule (entry) | exit / rebalance |
|---|---|---|
| S01 SEPA | tt_pass & vcp_valid & breakout close>pivot & vol≥1.5×vol50 & market filter | stop 8% (≤10%), to breakeven after +2R, exit close<MA50 |
| S02 TrendTemplate-RS | tt_pass, top 20 by rs_pct | weekly |
| S03 CANSLIM-lite | eps_yoy≥25% & rev_yoy≥20% & dist_52w_high≥−15% & rs_pct≥80 & industry RS top 40% & trust_net20>0 & market filter | stop 8%, exit close<MA50 |
| S04 RS leaders | top 20 rs_pct + market filter | weekly |
| S05 Weinstein stage 2 | close crosses above MA150 & MA150 rising & vol≥2×vol50 | exit close<MA150 |
| S06 Darvas | breakout above box top (high not exceeded ≥3 days, box ≤ 20d) with vol≥1.5× | stop box bottom |
| S07 52w-high (George-Hwang 2004) | top decile close/52w high | monthly |
| S08 12-1 momentum (Jegadeesh-Titman) | top decile r(t−252..t−21) | monthly |
| S09 Industry momentum (Moskowitz-Grinblatt) | top 3 industries by 6m return → top RS stocks inside | monthly |
| S10 Revenue momentum (FinLab README) | top 20 rev avg3/avg12 & close>MA60 | monthly, after 10th |
| S11 Revenue new high | rev_new_high_12m & rev_yoy≥20% & close>MA50 | monthly |
| S12 Trust adoption 投信認養 | trust_buy_streak≥3 & trust_net20/vol≥5% & size ≤70th pct | weekly, exit close<MA20 |
| S13 Foreign+trust co-buy | both net20>0 & rs_pct≥70 | weekly |
| S14 Big-holder accumulation | big1000_chg_4w ≥ +1pt & close>MA20 | weekly (needs extended) |
| S15 Margin washout | margin_chg_20 ≤ −10% & close>MA50 & ret_20>0 | weekly |
| S16 Episodic pivot (Qullamaggie) | gap ≥ +7% open & vol ≥3×vol50 & rev_yoy jump ≥30pp latest month | stop = day low, exit close<MA10 |
| S17 FinMind built-ins | InstitutionalInvestorsFollower, ShortSaleMarginPurchaseRatio, MaCrossOver, MacdCrossOver, Kd, KdCrossOver, Bias, NaiveKd, MaxMinPeriodBias | as in source |
| S18 twstock BestFourPoint | buy points | as in source |
| S19 ML | LightGBM y_A prob (features + Alpha158 price subset), top 20 | weekly, purged WF |
| S20+ Model-book rules | one per P3 rule/archetype | per rule |
Baselines: B0 TAIEX total return · B1 equal-weight universe · B2 random picks (same N/turnover, 1000 runs).
Report reports/P4_strategy_zoo.md + leaderboard (IS and VAL columns). Tune on IS only.
GATE P4: ≥1 strategy with VAL excess return >0 after costs and VAL MaxDD ≤ TAIEX MaxDD.

## 7 P5 Combination + final validation (`validate.py`)
- Candidates: top VAL strategies + ensembles (equal-weight sleeves; score-rank average).
- Walk-forward: yearly re-tune on expanding window, test next year.
- Plateau: grid ±20–50% around params; reject if best Sharpe > 1.3× median of neighbors.
- Random portfolios 1000 runs: strategy CAGR ≥95th pct.
- Deflated Sharpe Ratio (Bailey & López de Prado 2014) with N trials from trials.csv: DSR ≥ 0.95.
- Subperiods: yearly + 2011, 2015, 2018, 2020, 2022 corrections. Costs ×2. Capacity NT$1M/10M/100M.
- HOLDOUT once on final 1–3 configs; no tuning after.
- Report reports/P5_final_spec.md: exact rules, params, sizing, risk, expected ranges (from data), failure modes.
GATE P5: holdout excess >0 & DSR ≥0.95 & plateau ok & random ≥95th & cost×2 still beats benchmark.

## 8 P6 Production (`daily.py`)
- `python -m superstock daily`: update → build → features → signals (final strategies) → reports/daily/YYYY-MM-DD.html (watchlist: stock, rule, pivot, stop, risk, chart thumb) + signals CSV.
- Schedule: launchd at 21:45 Asia/Taipei (margin data ~21:30). Paper log: hypothetical next-day fills → reports/paper_trades.csv, weekly summary.
GATE P6: two unattended daily runs OK; paper log appends; owner confirms dashboard.

## 9 Success thresholds (owner-approved)
VAL/HOLDOUT excess return >0 after costs, MaxDD ≤ benchmark · rule lift ≥2 · neighbor-Sharpe drop <30% · DSR ≥0.95 · beats benchmark at cost ×2. Recall of superperformers = diagnostic only.
