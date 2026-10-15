# PROGRESS
Phase: P1 · step 3.8 (live run) — full download pending owner · P2 engine done, GATE P2 PASS (reports/gate_P2.md)
Done (2026-10-15, cloud session; live API via GitHub Actions `superstock.yml`, reports/smoke/):
- venv + install + pytest (73 pass). check: universe 2,225 = listed 1,977 (all on TWSE/TPEx official lists) + delisted 248.
- §3.7 verified live: DividendResult/CapitalReduction/Disposition need data_id (global = sponsor) · Split/ParValue global OK (from 2019-09) · Disposition, PriceAdj, HoldingSharesPer = sponsor-only · index ids TAIEX/TPEx OK (TR index 2008→) · TWSE STOCK_DAY parser 4/4 match · MonthRevenue date = 1st of next month · DividendResult after_price = before − cash (53/53) · Financials date = quarter end · Info type ∈ twse/tpex/emerging · institutional data starts 2012-05-02.
- Fixed: no-token limit 300/h; empty global probe → per stock; universe stale-info = delisted (delist date from Delisting table); emerging-board (興櫃) bars before listing / after delisting trimmed by listing.py (62 IPOs: 55 within 1 day of official date, 2 TPEx→TWSE transfers, 0 missed); C12 check; probe + replicate commands.
- P2: engine.py (portfolio + trade mode, costs, sizing caps, limit locks, market filter, metrics, trials.csv, holdout lock) + 20 tests; TAIEX-TR replication 2008–2026 max yearly diff 0.000000%.
Next:
1. Owner: FINMIND_TOKEN + where to run full download (Mac per plan, or cloud env with api.finmindtrade.com allowed).
2. `python -m superstock download` ≈ 11,125 core + 4,450 event calls (Dividend, CapitalReduction per stock) + ~40 → ≈28 h with token / ≈57 h without.
3. build → quality → reconcile (20 stocks) → GATE P1 → P3.
Running jobs: none
Blockers: FINMIND_TOKEN missing; cloud container proxy denies api.finmindtrade.com (CONNECT 403).
Assumptions:
- A1 Repo: `tw-superstock-lab/` inside josephchan00000/fuhhwa-fund-radar (only repo this session can push); root conftest keeps it out of that repo's pytest.
- A2 Executor: cloud Linux container (no caffeinate); live checks on GitHub Actions, data only in runner temp, never committed.
- A3 Emerging-board bars are not research data (SPEC universe excludes 興櫃): detected from FinMind spread rule, official dates only for reconcile.
- A4 Stocks never on main board are dropped; universe delist date only for update skipping/reporting, trimming uses the price data.
- A5 Disposition data unavailable (sponsor) → engine rule present but inactive; S14 (TDCC big holders) blocked unless official TDCC source approved.
- A6 Engine: P&L on adjusted prices (dividends reinvested), lots on raw prices; same-day stop after breakout entry; delisted → exit at last close; rf = 0; costs×2 scales fee, tax, slippage.
- A7 Commit ids use P{n}.8 for live-run steps of §3.8; extra CLI: probe, replicate.
Key numbers: universe 2,225 (TWSE 1,084 · TPEx 893 · delisted 248, 8–26/yr) · ETA ≈28 h (token) · GATE P2 PASS.
