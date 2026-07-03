#!/usr/bin/env bash
# 復華基金追蹤版本 · 每日 routine 單一進入點（本機與 GitHub Actions 共用）。
# 流程：抓 25 檔基金持股介紹（海外＋台股）→ 產新聞提示包 → 產儀表板。
# 註：新聞「內容」採「半自動・用訂閱額度」（純 Python 不杜撰新聞）——本腳本只產「提示包」，
#     新聞內容由「會上網查證的 Claude（你的訂閱額度、非計量 API）」依提示包產出：
#       「依 reports/usnews/prompts/{date}.md 上網查證，產 v1/v2 兩檔」→ 回存 reports/usnews/{date}_v1.md、_v2.md；
#       「依 reports/twnews/prompts/{date}.md 上網查證，產台股重點」→ 回存 reports/twnews/{date}.md；
#     補完後重跑一次 gen_fund_dashboard.py 讓新聞入板。
#   （雲端 CI 只自動刷新 NAV／持股／提示包＋重建儀表板；新聞內容另由 Claude 補，見 .github/workflows/daily.yml。
#    若日後要「新聞也全自動」，需改用計量 API 金鑰——訂閱制 OAuth 權杖不適合 CI 無人值守。）
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/5] 抓持股介紹（復華官網：NAV / 十大持有標的 / 國家・產業配置 / 月報）…"
python3 scripts/fetch_holdings.py || echo "  ⚠ 持股抓取失敗，續跑（用既有 data/funds 快照）"

echo "[2/5] 產昨夜美股新聞提示包（兩版型）…（新聞內容由 LLM 上網查證產出，見檔頭說明）"
python3 scripts/gen_usnews.py || echo "  ⚠ 美股提示包產製失敗，續跑"

echo "[3/5] 產台股盤前/盤後重點提示包…（內容由 LLM 上網查證產出，見檔頭說明）"
python3 scripts/gen_twnews.py || echo "  ⚠ 台股提示包產製失敗，續跑"

echo "[4/5] 產總經／政策面提示包…（內容由 LLM 上網查證產出，見檔頭說明）"
python3 scripts/gen_macronews.py || echo "  ⚠ 總經政策提示包產製失敗，續跑"

echo "[5/5] 產儀表板（今日重點 + 新聞 + 總經政策 + 焦點個股 + 總覽 + 持股介紹）→ dashboard/index.html …"
python3 scripts/gen_fund_dashboard.py || echo "  ⚠ 儀表板產製失敗"

echo "✅ 完成。持股 data/funds/*.json；美股新聞 reports/usnews/{date}_v1|_v2.md；"
echo "   台股新聞 reports/twnews/{date}.md；總經政策 reports/macronews/{date}.md；儀表板 dashboard/index.html"
echo "   合規掃描：gen_usnews.py --check ＆ gen_twnews.py --check ＆ gen_macronews.py --check"
