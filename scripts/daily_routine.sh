#!/usr/bin/env bash
# 每日 routine 單一進入點（本機 launchd 或雲端 GitHub Actions 共用）。
# 流程：補實 Tier B 情報（etfinfo 競品/法人籌碼）→ 跑全部主角（賣點 + 多元想法 + 報告）。
# 金鑰（皆選用，未設則該層誠實降級）：FINMIND_TOKEN（全分點）、YOUTUBE_API_KEY、
# FB_ACCESS_TOKEN（+ config/social_fb_pages.json）、ANTHROPIC_API_KEY（KOL 逐則深析 + 文案）。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/2] 補實第三方情報（etfinfo 競品持股 + 主動ETF法人籌碼）…"
python3 scripts/fetch_etfinfo.py || echo "  ⚠ etfinfo 補實失敗，續跑（用既有 drop-in）"

echo "[2/3] 跑每日賣點 + 多元想法（含券商分點 Histock live / 社群 KOL / Claude 深析）…"
python3 scripts/run_daily.py all

echo "[3/3] 產每日文案（M6：baseline 四通路 + 合規標注 + 數字防杜撰；有金鑰走 API，否則出 prompt-pack）…"
python3 scripts/gen_copy.py all || echo "  ⚠ 文案層失敗，續跑（想法報告已產出）"

echo "✅ routine 完成。想法報告 reports/{date}_{etf}.md；文案 reports/copy/{date}_{etf}.copy.md"
