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

echo "[3/4] 產每日文案（M6：baseline 四通路 + 合規標注 + 數字防杜撰；有金鑰走 API，否則出 prompt-pack）…"
python3 scripts/gen_copy.py all || echo "  ⚠ 文案層失敗，續跑（想法報告已產出）"

echo "[4/6] 同日求鮮（13:30 收盤後即更新，不等晚間批次）：官方即時(MIS) 市價 + FHTrust 官方 NAV/持股 → 績效歸因…"
python3 scripts/fetch_peers.py  || echo "  ⚠ 競品價量失敗，續跑"
python3 scripts/fetch_fast.py   || echo "  ⚠ 同日求鮮失敗，續跑（用既有 DB 數據）"

echo "[5/6] 自動新聞（近 7 天、帶發文時間）：Google News 台灣繁中 → 本檔話題+口碑自動更新…"
python3 scripts/fetch_news.py   || echo "  ⚠ 自動新聞失敗，續跑"

echo "[6/6] 產靜態儀表板（M7：績效歸因同日最新 + 今日切角 + 自動新聞 + 四通路文案）…"
python3 scripts/gen_dashboard.py || echo "  ⚠ 儀表板產製失敗，續跑（文案/報告已產出）"

echo "✅ routine 完成。想法 reports/{date}_{etf}.md；文案 reports/copy/{date}_{etf}.copy.md；儀表板 dashboard/index.html"
