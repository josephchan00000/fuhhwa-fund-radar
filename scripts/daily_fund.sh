#!/usr/bin/env bash
# 復華基金追蹤版本 · 每日 routine 單一進入點（海外版 + 台股版整合）。
# 流程：抓海外 11 檔 + 台股 12 檔持股介紹（月度快照）→ 產昨夜美股 + 台股新聞提示包
#       → 產整合頁 dashboard/index.html（上層「海外／台股」切換）＋ 台股獨立頁 dashboard/tw.html。
# 註：新聞「兩版型內容」需會上網查證的 LLM 產出（純 Python 不杜撰新聞）：
#   · 昨夜美股：依 reports/usnews/prompts/{date}.md 產 reports/usnews/{date}_v1|_v2.md；
#   · 台股（盤後重點＋盤前美股影響）：依 reports/twnews/prompts/{date}.md 產 reports/twnews/{date}_v1|_v2.md；
#   · 在 Claude Code 中直接說「依此提示包上網查證，產 v1/v2 兩檔」，或貼進聯網 Claude 回存。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/5] 抓海外版持股介紹（復華官網：NAV / 十大持有標的 / 國家・產業配置 / 月報）…"
python3 scripts/fetch_holdings.py || echo "  ⚠ 海外版持股抓取失敗，續跑（用既有 data/funds 快照）"

echo "[2/5] 抓台股版持股介紹（12 檔 → data/funds_tw/）…"
python3 scripts/fetch_holdings.py --market tw || echo "  ⚠ 台股版持股抓取失敗，續跑（用既有 data/funds_tw 快照）"

echo "[3/5] 產昨夜美股新聞提示包…（新聞內容由 LLM 上網查證產出，見檔頭說明）"
python3 scripts/gen_usnews.py || echo "  ⚠ 昨夜美股提示包產製失敗，續跑"

echo "[4/5] 產台股新聞提示包（台股盤後重點＋盤前美股影響）…"
python3 scripts/gen_twnews.py || echo "  ⚠ 台股新聞提示包產製失敗，續跑"

echo "[5/5] 產儀表板（整合頁 index.html：海外／台股切換 ＋ 台股獨立頁 tw.html）…"
python3 scripts/gen_fund_dashboard.py || echo "  ⚠ 整合頁儀表板產製失敗"
python3 scripts/gen_fund_dashboard.py --market tw || echo "  ⚠ 台股獨立頁產製失敗"

echo "✅ 完成。持股 data/funds/*.json + data/funds_tw/*.json；"
echo "   新聞 reports/usnews/{date}_v*.md + reports/twnews/{date}_v*.md；"
echo "   儀表板 dashboard/index.html（整合頁）+ dashboard/tw.html（台股獨立頁）"
echo "   合規掃描：python3 scripts/gen_usnews.py --check ；python3 scripts/gen_twnews.py --check"
