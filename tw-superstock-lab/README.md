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
mkdir -p data/logs
caffeinate -is nohup python -m superstock download > data/logs/download.log 2>&1 &
python -m superstock status     # 看進度；中斷後重跑同一指令會續傳
python -m superstock official   # 官方處置公告（2008 起）＋集保股權分散表（download 結束時也會自動跑）
python -m superstock build && python -m superstock quality && python -m superstock reconcile
```

FinMind 免費帳號拿不到處置股與集保股權分散表（贊助會員才有），改抓官方網站（`official` 指令，約 3 分鐘）：
證交所／櫃買處置公告逐年查詢；集保開放資料只有最新一週，每次執行存一份往後累積
（大戶指標沒有免費的長歷史，S14 只能從開始累積那週起算）。

其他指令：`python -m superstock probe`（實測各資料集欄位與語意 → `reports/live_probe.md`）、
`python -m superstock replicate`（P2 關卡：回測引擎複製加權報酬指數）。

雲端 Claude 的工作環境連不到 FinMind，實測改在 GitHub Actions 跑：在 repo 根目錄寫 `.ping/superstock`
（第一個字＝`smoke`／`probe`／`diag`／`official`／`officialdl`）推上 `claude/**` 分支即觸發 `.github/workflows/superstock.yml`，
資料只留在 runner 暫存，跑完回寫 `reports/smoke/`。

資料只留在本機（`data/` 不進 git）；報告在 `reports/`。本系統是研究工具，不是投資建議。
