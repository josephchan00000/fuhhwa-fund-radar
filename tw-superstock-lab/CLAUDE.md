# CLAUDE.md
Read `PROGRESS.md` first, then only the `SPEC.md` sections you need. SPEC.md is the source of truth.
- Owner: JC — reply in Traditional Chinese, short. Ask only for: FinMind token, paid data, gate FAIL, irreversible actions.
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pytest`
- Never commit `data/` or `.env`; never print the token; no live orders; no look-ahead.
- Long jobs: `caffeinate -is nohup python -m superstock download > data/logs/download.log 2>&1 &` — resumable, rerun same command.
- Update `PROGRESS.md` after every step; write `reports/gate_P{n}.md` at each gate.
