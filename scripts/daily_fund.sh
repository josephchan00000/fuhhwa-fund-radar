#!/usr/bin/env bash
# 復華基金追蹤版本 · 每日 routine 本機單一進入點。
# 流程：抓 25 檔基金持股介紹（海外＋台股）→ 產新聞提示包 → 產儀表板。
# 註：新聞「內容」需會上網查證的 LLM 產出（純 Python 不杜撰新聞），用「訂閱制用量」的 Claude、非計量 API：
#   · 本機：跑完本腳本後，在 Claude Code 直接說
#       「依 reports/usnews/prompts/{date}.md 上網查證，產 v1/v2 兩檔」→ 回存 reports/usnews/{date}_v1.md、_v2.md；
#       「依 reports/twnews/prompts/{date}.md 上網查證，產台股重點」→ 回存 reports/twnews/{date}.md；
#     再重跑一次 gen_fund_dashboard.py 讓新聞入板。
#   · 雲端（GitHub Actions）：由 anthropics/claude-code-action 帶 CLAUDE_CODE_OAUTH_TOKEN
#     （訂閱制 OAuth 權杖）在 CI 全自動查證產出，見 .github/workflows/daily.yml。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/4] 抓持股介紹（復華官網：NAV / 十大持有標的 / 國家・產業配置 / 月報）…"
python3 scripts/fetch_holdings.py || echo "  ⚠ 持股抓取失敗，續跑（用既有 data/funds 快照）"

echo "[2/4] 產昨夜美股新聞提示包（兩版型）…（新聞內容由 LLM 上網查證產出，見檔頭說明）"
python3 scripts/gen_usnews.py || echo "  ⚠ 美股提示包產製失敗，續跑"

echo "[3/4] 產台股盤後重點提示包…（內容由 LLM 上網查證產出，見檔頭說明）"
python3 scripts/gen_twnews.py || echo "  ⚠ 台股提示包產製失敗，續跑"

echo "[4/4] 產儀表板（今日重點 + 總覽 + 新聞連動 + 台股/美股新聞 + 持股介紹）→ dashboard/index.html …"
python3 scripts/gen_fund_dashboard.py || echo "  ⚠ 儀表板產製失敗"

echo "✅ 完成。持股 data/funds/*.json；美股新聞 reports/usnews/{date}_v1|_v2.md；"
echo "   台股新聞 reports/twnews/{date}.md；儀表板 dashboard/index.html"
echo "   合規掃描：python3 scripts/gen_usnews.py --check ＆ python3 scripts/gen_twnews.py --check"
