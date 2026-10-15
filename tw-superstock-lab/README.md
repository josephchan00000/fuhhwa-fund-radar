# 台股飆股研究系統（tw-superstock-lab）

用資料回答三件事：台股飆股起漲前長什麼樣（逆向拆解）、GitHub 知名策略放到台股還有沒有效（策略體檢）、每天收盤後該看哪些股票（每日選股）。

- 給 AI 的執行規格：`SPEC.md`（Claude Code 從 `CLAUDE.md` → `PROGRESS.md` 開始）
- 規劃書（人看的版本）：https://claude.ai/code/artifact/3047ae10-23d1-40f5-99c0-9174296cc61c

## 快速開始（Phase 1 資料層）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" && pytest
cp .env.example .env            # 填入 FINMIND_TOKEN
python -m superstock check      # 看股票池大小與預估下載時間
caffeinate -is nohup python -m superstock download > data/logs/download.log 2>&1 &
python -m superstock status     # 看進度；中斷後重跑同一指令會續傳
python -m superstock build && python -m superstock quality && python -m superstock reconcile
```

資料只留在本機（`data/` 不進 git）；報告在 `reports/`。本系統是研究工具，不是投資建議。
