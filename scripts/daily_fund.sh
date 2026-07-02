#!/usr/bin/env bash
# 復華基金追蹤版本 · 每日 routine 單一進入點。
# 流程：抓 11 檔基金持股介紹（月度快照）→ 產昨夜美股新聞提示包 → 產儀表板。
# 註：昨夜美股「兩版型內容」需會上網查證的 LLM 產出（純 Python 不杜撰新聞）：
#   · 在 Claude Code 中：說「依 reports/usnews/prompts/{date}.md 上網查證，產 v1/v2 兩檔」；
#   · 或把提示包貼進聯網 Claude，回存 reports/usnews/{date}_v1.md 與 _v2.md。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/3] 抓持股介紹（復華官網：NAV / 十大持有標的 / 國家・產業配置 / 月報）…"
python3 scripts/fetch_holdings.py || echo "  ⚠ 持股抓取失敗，續跑（用既有 data/funds 快照）"

echo "[2/3] 產昨夜美股新聞提示包（兩版型）…（新聞內容由 LLM 上網查證產出，見檔頭說明）"
python3 scripts/gen_usnews.py || echo "  ⚠ 提示包產製失敗，續跑"

echo "[3/3] 產儀表板（持股介紹 + 昨夜美股新聞 + 合規燈）→ dashboard/index.html …"
python3 scripts/gen_fund_dashboard.py || echo "  ⚠ 儀表板產製失敗"

echo "✅ 完成。持股 data/funds/*.json；新聞 reports/usnews/{date}_v1|_v2.md；儀表板 dashboard/index.html"
echo "   合規掃描：python3 scripts/gen_usnews.py --check"
