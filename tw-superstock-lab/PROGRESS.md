# PROGRESS
Phase: P1 Data layer · step 3.8 (live run)
Done:
- 2026-10-15 cloud: P1 starter code + 33 tests (mock FinMind).
- 2026-10-15 cloud: step 1 — venv + `pip install -e ".[dev]"` + pytest → 33 passed (Python 3.13, pandas 3.0.6, numpy 2.5.4, pyarrow 26.0.0).
Next:
1. `.env` with FINMIND_TOKEN (owner) — not set yet; free tier without token = 300/h.
2. Live check on GitHub Actions (cloud container blocks FinMind): `check` → universe size + ETA; smoke `download --stocks 2330 6488 1101 --max-calls 60` → build → quality; fix schema surprises (SPEC §3.7) + tests.
3. Full download (core ≈ stocks×5 calls ≈ 20h with token) — needs owner's Mac or a network that allows api.finmindtrade.com; meanwhile build P2 engine on synthetic data.
Running jobs: none
Blockers: FINMIND_TOKEN missing; cloud container proxy denies api.finmindtrade.com (HTTP 403 on CONNECT, 2026-10-15).
Assumptions:
- A1 Repo: project lives in `tw-superstock-lab/` of josephchan00000/fuhhwa-fund-radar (only repo this session can push); can be split to its own repo later (`git subtree split`). Root `conftest.py` there keeps it out of that repo's pytest.
- A2 Executor: cloud Linux container, no `caffeinate`; long jobs use `nohup … &`.
- A3 Live API checks run on GitHub Actions (workflow `superstock.yml`); downloaded data stays in the runner and is never committed; only `reports/` comes back.
Key numbers: —
