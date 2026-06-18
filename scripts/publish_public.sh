#!/usr/bin/env bash
# 一鍵：抓最新數據 → 產儀表板 → 公開上線到 Vercel 正式網址。
#
# 用途：盤後（13:30 收完）想把「同日最新」推上線時，跑這一支即可。
#   抓取：競品持股(etfinfo) + 同類價量(TWSE/TPEx) + 同日求鮮(官方MIS市價 + FHTrust官方NAV/持股)
#   產表：gen_dashboard（三檔、績效歸因三卡、競品掃描…）
#   上線：vercel deploy --prod（**公開**正式網址，使用者已確認資料皆公開來源、不需存取保護）
#
# 公開網址：https://dashboard-delta-eight-41.vercel.app
# 需求：已 `vercel login`、dashboard/ 已 vercel link（本機皆已就緒）。
#
# 預設＝完整刷新：所有文字分析(賣點/想法)、競品、同日市況/績效歸因、自動新聞都更新到最新，再上線。
#   收盤後官方全市場批次未更新時，pipeline 以即時(MIS) 補當日 → 賣點訊號/資料日仍跟到當日
#   （官方淨值未公布的上櫃 NAV 型如 00998A/00986D 會誠實退到最近交易日，市價仍當日）。
# 想快速只刷市況/新聞（不重算賣點，較快）→ 加 --quick。
set -uo pipefail
cd "$(dirname "$0")/.."

QUICK=0; [ "${1:-}" = "--quick" ] && QUICK=1

if [ "$QUICK" = "1" ]; then
  echo "▶ [quick] 只刷市況/績效歸因/自動新聞（不重算賣點，較快）…"
  python3 scripts/fetch_peers.py   || echo "  ⚠ 競品價量失敗，續跑"
  python3 scripts/fetch_fast.py    || echo "  ⚠ 同日求鮮失敗，續跑"
  python3 scripts/fetch_news.py    || echo "  ⚠ 自動新聞失敗，續跑"
  python3 scripts/gen_dashboard.py
else
  echo "▶ [full] 完整刷新：賣點/想法 + 競品 + 同日求鮮 + 自動新聞，全部到最新…"
  bash scripts/daily_routine.sh || echo "  ⚠ 有步驟失敗，續跑（用既有資料）"
fi

echo "▶ 上線：部署 dashboard/ → Vercel（--prod，公開）…"
( cd dashboard && npx --yes vercel@latest deploy --prod --yes )

echo "✅ 完成。公開網址：https://dashboard-delta-eight-41.vercel.app"
echo "   （受眾重整網址即看到最新；資料皆公開來源，無存取保護。）"
