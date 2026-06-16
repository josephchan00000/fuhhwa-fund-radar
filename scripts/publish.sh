#!/usr/bin/env bash
# 重產儀表板 → 部署到 Cloudflare Pages（私人網址，固定同一個 URL）。
# 一次性：先 `npx wrangler login`（瀏覽器點 Allow），並在 Cloudflare Zero Trust 設 Access 限定 email。
# 之後每次更新：跑這支即可，受眾重整同一個網址就是最新。
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${CF_PROJECT:-fh-arm-radar}"

echo "▶ 1/3 重產儀表板…"
python3 scripts/gen_dashboard.py

echo "▶ 2/3 確認 Pages 專案（${PROJECT}）…"
npx --yes wrangler@latest pages project create "${PROJECT}" \
  --production-branch main >/dev/null 2>&1 || true   # 已存在就略過

echo "▶ 3/3 部署…"
npx --yes wrangler@latest pages deploy dashboard \
  --project-name "${PROJECT}" \
  --branch main \
  --commit-dirty=true

echo "✅ 完成。私人網址：https://${PROJECT}.pages.dev"
echo "   （記得已在 Cloudflare Zero Trust → Access 限定 email，否則此網址任何人有連結都看得到）"
