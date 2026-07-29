#!/usr/bin/env bash
# 復華基金追蹤版本 · 每日 routine 單一進入點（本機與 GitHub Actions 共用）。
# 流程：三路資料平行抓取（持股NAV／基金新聞／ETF）→ 產新聞提示包 → 產儀表板。
# 註：新聞「內容」採「半自動・用訂閱額度」（純 Python 不杜撰新聞）——本腳本只產「提示包」，
#     新聞內容由「會上網查證的 Claude（你的訂閱額度、非計量 API）」依提示包產出；
#     排程 Routine（台北 06:05）補完新聞 push 後，daily.yml 會自動觸發本腳本做單一 commit。
# 效率（2026-07-18）：三支抓取互不相依（各寫各的落檔、http 快取以 URL 雜湊分檔），
#     改平行執行——CI 牆鐘時間＝最慢一支（基金新聞），而非三支相加。
set -euo pipefail
cd "$(dirname "$0")/.."

LOGD="$(mktemp -d)"

echo "[1/4] 平行抓取五路資料（持股介紹＋NAV／基金新聞・社群／ETF 數據追蹤／ETF 每日持股／總經・籌碼）…"
( python3 scripts/fetch_holdings.py \
    || echo "  ⚠ 持股抓取失敗，續跑（用既有 data/funds 快照）" ) >"$LOGD/holdings.log" 2>&1 &
P_HOLD=$!
( python3 scripts/fetch_fund_news.py \
    || echo "  ⚠ 基金新聞擷取失敗，續跑（區塊沿用前次落檔或顯示提示）" ) >"$LOGD/fundnews.log" 2>&1 &
P_NEWS=$!
( python3 scripts/fetch_etf_watch.py \
    || echo "  ⚠ ETF 追蹤擷取失敗，續跑（分頁沿用前次落檔）" ) >"$LOGD/etf.log" 2>&1 &
P_ETF=$!
( python3 scripts/fetch_macro_chips.py \
    || echo "  ⚠ 總經・籌碼數據擷取失敗，續跑（市場溫度計沿用前次落檔）" ) >"$LOGD/macro.log" 2>&1 &
P_MACRO=$!
# ETF 每日持股（展開明細「加減碼／當日貢獻」資料層）——無跨投信統一端點，逐檔試候選來源；
# 抓不到的檔安靜降級（該 ETF 沒有展開明細），不影響其餘欄位。探針診斷一併印進 CI 日誌。
( python3 scripts/fetch_etf_holdings.py \
    || echo "  ⚠ ETF 每日持股擷取失敗，續跑（展開明細沿用前次落檔）" ) >"$LOGD/etfhold.log" 2>&1 &
P_EHOLD=$!

echo "[2/4] 產新聞提示包（昨夜美股／台股／總經政策＋行事曆）…（新聞內容由 LLM 上網查證產出）"
python3 scripts/gen_usnews.py    || echo "  ⚠ 美股提示包產製失敗，續跑"
python3 scripts/gen_twnews.py    || echo "  ⚠ 台股提示包產製失敗，續跑"
python3 scripts/gen_macronews.py || echo "  ⚠ 總經政策提示包產製失敗，續跑"

echo "[3/4] 等五路抓取完成…"
wait "$P_HOLD" || true
wait "$P_NEWS" || true
wait "$P_ETF"  || true
wait "$P_MACRO" || true
wait "$P_EHOLD" || true
echo "── 持股介紹＋NAV ──";      cat "$LOGD/holdings.log"
echo "── 基金新聞・社群 ──";     cat "$LOGD/fundnews.log"
echo "── ETF 數據追蹤 ──";       cat "$LOGD/etf.log"
echo "── ETF 每日持股 ──";       cat "$LOGD/etfhold.log"
echo "── 總經・籌碼數據 ──";     cat "$LOGD/macro.log"

echo "[3.5/4] 前十大持股簡介覆蓋率檢查（新持股缺簡介只在 CI 端現形——寫 gap 檔供儀表板 ⚠）…"
TZ=Asia/Taipei python3 scripts/check_holdings_intro.py || true   # 不擋發佈：缺口寫檔、儀表板顯示、下一輪 SOP 補

echo "[4/4] 產儀表板（今日重點 + 新聞 + 總經政策 + 總覽 + 持股介紹）→ dashboard/index.html …"
python3 scripts/gen_fund_dashboard.py || echo "  ⚠ 儀表板產製失敗"

echo "✅ 完成。持股 data/funds/*.json；美股新聞 reports/usnews/{date}_v1|_v2.md；"
echo "   台股新聞 reports/twnews/{date}.md；總經政策 reports/macronews/{date}.md；儀表板 dashboard/index.html"
echo "   合規掃描：gen_usnews.py --check ＆ gen_twnews.py --check ＆ gen_macronews.py --check"
