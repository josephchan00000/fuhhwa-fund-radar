#!/usr/bin/env bash
# 重產儀表板 → 本機直推 dashboard/ 到 Vercel（純靜態、無雲端 build）。
#
# 為何「本機直推」而非 Git 自動部署：dashboard/index.html 與 data/arm.db 都不入庫
# （產出物＋資料），雲端 build 沒有 DB 可重產 → 一律在本機產好再上傳整個 dashboard/。
#
# ⚠ 存取控制（重要）：本頁是復華內部競品/Tier B 情報，Vercel 部署網址「預設公開」。
#   發布前務必擇一鎖存取，否則知道網址就看得到：
#     · Vercel Pro：專案 → Settings → Deployment Protection →
#         Vercel Authentication（限團隊成員登入）或 Password Protection（設密碼）。
#     · 免費替代：改用現有 Cloudflare Pages + Zero Trust Access（email 白名單，scripts/publish.sh）。
#   本腳本只負責「產 + 推」，不會幫你鎖；未鎖前請勿散布網址。dashboard/vercel.json 已加
#   X-Robots-Tag: noindex（擋搜尋引擎索引），但那不是存取控制。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "▶ 1/2 重產儀表板…"
python3 scripts/gen_dashboard.py

echo "▶ 2/2 部署 dashboard/ → Vercel（首次會引導登入 / 綁定專案）…"
npx --yes vercel@latest deploy dashboard --prod --yes

echo "✅ 完成。提醒：未在 Vercel 設 Deployment Protection 前，網址等於公開——先鎖再散布。"
