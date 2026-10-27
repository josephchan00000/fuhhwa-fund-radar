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

echo "[1/4] 平行抓取四路資料（持股介紹＋NAV／基金新聞・社群／ETF 數據追蹤／總經・籌碼）…"
# 每支都有時間上限（2026-10-16）：卡住的那支會讓整輪等到 job 逾時、20 分鐘全浪費，連已抓好的也沒 commit。
# 正常各約 1～4 分鐘；逾時＝沿用既有落檔（各腳本本來就是「抓不到就保留舊檔」）。
( timeout -k 10 600 python3 scripts/fetch_holdings.py \
    || echo "  ⚠ 持股抓取失敗或逾時，續跑（用既有 data/funds 快照）" ) >"$LOGD/holdings.log" 2>&1 &
P_HOLD=$!
( timeout -k 10 600 python3 scripts/fetch_fund_news.py \
    || echo "  ⚠ 基金新聞擷取失敗或逾時，續跑（區塊沿用前次落檔或顯示提示）" ) >"$LOGD/fundnews.log" 2>&1 &
P_NEWS=$!
( timeout -k 10 600 python3 -u scripts/fetch_etf_watch.py \
    || echo "  ⚠ ETF 追蹤擷取失敗或逾時，續跑（分頁沿用前次落檔）" ) >"$LOGD/etf.log" 2>&1 &
P_ETF=$!
( timeout -k 10 300 python3 scripts/fetch_macro_chips.py \
    || echo "  ⚠ 總經・籌碼數據擷取失敗或逾時，續跑（市場溫度計沿用前次落檔）" ) >"$LOGD/macro.log" 2>&1 &
P_MACRO=$!
# 註：ETF 每日持股**不在此處抓**（2026-07-29 起）——投信官網幾乎都是 SPA、持股由 XHR
# 動態載入，靜態 HTTP 抓不到（逐家逆向 6 輪的結論）。已改由獨立的
# .github/workflows/etf_holdings.yml 以無頭瀏覽器渲染、自行排程於台北 17:40，
# 只更新 data/etf_holdings.json。放這裡會讓每天多 1–3 分鐘、壓縮 07:03 的目標，
# 且純 HTTP 版每輪對投信站發出上百個註定失敗的請求。儀表板照常讀該落檔建表。

echo "[2/4] 產新聞提示包（昨夜美股／台股／總經政策＋行事曆）…（新聞內容由 LLM 上網查證產出）"
python3 scripts/gen_usnews.py    || echo "  ⚠ 美股提示包產製失敗，續跑"
python3 scripts/gen_twnews.py    || echo "  ⚠ 台股提示包產製失敗，續跑"
python3 scripts/gen_macronews.py || echo "  ⚠ 總經政策提示包產製失敗，續跑"

echo "[3/4] 等四路抓取完成…"
wait "$P_HOLD" || true
wait "$P_NEWS" || true
wait "$P_ETF"  || true
wait "$P_MACRO" || true
echo "── 持股介紹＋NAV ──";      cat "$LOGD/holdings.log"
echo "── 基金新聞・社群 ──";     cat "$LOGD/fundnews.log"
echo "── ETF 數據追蹤 ──";       cat "$LOGD/etf.log"
echo "── 總經・籌碼數據 ──";     cat "$LOGD/macro.log"

echo "[3.5/4] 前十大持股簡介覆蓋率檢查（新持股缺簡介只在 CI 端現形——寫 gap 檔供儀表板 ⚠）…"
TZ=Asia/Taipei python3 scripts/fetch_tw_holidays.py || true      # 證交所官方休市表（一個請求；抓不到沿用既有／內建種子）
TZ=Asia/Taipei python3 scripts/check_holdings_intro.py || true   # 不擋發佈：缺口寫檔、儀表板顯示、下一輪 SOP 補

echo "[3.6/4] 新 ETF 自動發現（市場首見台帳＋募集頁；沒被登錄過的檔只有這裡會現形）…"
TZ=Asia/Taipei python3 scripts/check_new_etfs.py || true         # 同上：缺口寫檔、儀表板 🔴、下一輪 SOP 補 UPCOMING

echo "[3.7/4] 籌碼雷達落檔（ETF 部位＋官方個股價量／籌碼，只補缺）…"
TZ=Asia/Taipei timeout 300 python3 scripts/fetch_lab.py || true   # 不擋發佈：抓不到沿用既有分片
TZ=Asia/Taipei timeout 300 python3 scripts/fetch_fut.py --budget 240 || true  # 台指期逐筆（期交所只留 30 個交易日；docs/lab_fut_plan.md）：只增不改
TZ=Asia/Taipei timeout 120 python3 scripts/run_fut.py || true  # 台指期早盤策略研究重算（只讀已存的逐筆、幾秒）
TZ=Asia/Taipei timeout 420 python3 scripts/fetch_heat.py || true  # 景氣溫度頁（docs/lab_heat_plan.md）：抓不到沿用既有落檔
TZ=Asia/Taipei timeout 420 python3 scripts/fetch_heat_us.py || true  # 美股景氣頁（docs/lab_heat_us_plan.md）：一天抓一次、抓不到沿用
TZ=Asia/Taipei timeout 300 python3 scripts/fetch_ussx_watch.py || true  # 美股三成：持股跌破 50 日線的提醒（docs/lab_us_sleeve_plan.md 第 13.3 節；最多 8 檔）＋美股個股卡的資料（docs/lab_cfg_v2_plan.md 第 4 節）

echo "[4/4] 產儀表板（今日重點 + 新聞 + 總經政策 + 總覽 + 持股介紹）→ dashboard/index.html …"
python3 scripts/gen_fund_dashboard.py || echo "  ⚠ 儀表板產製失敗"

echo "✅ 完成。持股 data/funds/*.json；美股新聞 reports/usnews/{date}_v1|_v2.md；"
echo "   台股新聞 reports/twnews/{date}.md；總經政策 reports/macronews/{date}.md；儀表板 dashboard/index.html"
echo "   合規掃描：gen_usnews.py --check ＆ gen_twnews.py --check ＆ gen_macronews.py --check"
